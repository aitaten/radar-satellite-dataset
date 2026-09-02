import os
import sys
import warnings
import traceback
import datetime as dt
from pathlib import Path
from typing import Tuple, Dict, Any, Optional

import numpy as np
import h5py
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from pyproj import CRS, Transformer

import matplotlib.pyplot as plt
import matplotlib.colors as colors
import cartopy.crs as ccrs
import cartopy.feature as cfeature

# Suppress minor PyProj warning when converting to PROJ string
warnings.filterwarnings("ignore", category=UserWarning, module="pyproj")

# ==============================================================================
# PIPELINE CONFIGURATION
# ==============================================================================
DOWNLOAD_DIR = Path("./tmp_opera")
OUTPUT_DIR = Path("./output")

# Ensure output directory exists
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ==============================================================================
# HELPER: CONVERT PROJ4 / HDF5 PROJDEF TO CARTOPY CRS
# ==============================================================================
def projdef_to_cartopy(projdef: str) -> ccrs.Projection:
    """Parses a PROJ4 string into a native Cartopy Projection subclass."""
    crs_pyproj = CRS.from_proj4(projdef)
    proj_dict = crs_pyproj.to_dict()

    proj_name = proj_dict.get("proj", "").lower()

    globe_kwargs = {}
    if "ellps" in proj_dict:
        globe_kwargs["ellipse"] = proj_dict["ellps"]
    elif "a" in proj_dict and "b" in proj_dict:
        globe_kwargs["semimajor_axis"] = proj_dict["a"]
        globe_kwargs["semiminor_axis"] = proj_dict["b"]
    elif "a" in proj_dict:
        globe_kwargs["semimajor_axis"] = proj_dict["a"]

    globe = ccrs.Globe(**globe_kwargs) if globe_kwargs else None

    if proj_name == "laea":
        return ccrs.LambertAzimuthalEqualArea(
            central_latitude=proj_dict.get("lat_0", 0.0),
            central_longitude=proj_dict.get("lon_0", 0.0),
            false_easting=proj_dict.get("x_0", 0.0),
            false_northing=proj_dict.get("y_0", 0.0),
            globe=globe,
        )
    elif proj_name in ["stere", "sterea"]:
        return ccrs.Stereographic(
            central_latitude=proj_dict.get("lat_0", 0.0),
            central_longitude=proj_dict.get("lon_0", 0.0),
            false_easting=proj_dict.get("x_0", 0.0),
            false_northing=proj_dict.get("y_0", 0.0),
            true_scale_latitude=proj_dict.get("lat_ts", None),
            globe=globe,
        )
    elif proj_name == "merc":
        return ccrs.Mercator(
            central_longitude=proj_dict.get("lon_0", 0.0),
            false_easting=proj_dict.get("x_0", 0.0),
            false_northing=proj_dict.get("y_0", 0.0),
            globe=globe,
        )
    else:
        return ccrs.PlateCarree()


# ==============================================================================
# MODULE 1: OPERA HDF5 DATA READER
# ==============================================================================
class OPERADataReader:
    """Modular reader for EUMETNET OPERA ODIM HDF5 Composite Files."""

    @staticmethod
    def get_crs_and_coords(h5_file: str) -> Tuple[ccrs.Projection, np.ndarray, np.ndarray]:
        with h5py.File(h5_file, "r") as f:
            where = f["where"].attrs
            xsize = int(where["xsize"])
            ysize = int(where["ysize"])

            projdef = where["projdef"]
            if isinstance(projdef, bytes):
                projdef = projdef.decode("utf-8")

            LL_lon, LL_lat = float(where["LL_lon"]), float(where["LL_lat"])
            LR_lon, LR_lat = float(where["LR_lon"]), float(where["LR_lat"])
            UL_lon, UL_lat = float(where["UL_lon"]), float(where["UL_lat"])

        cartopy_crs = projdef_to_cartopy(projdef)

        crs_native = CRS.from_proj4(projdef)
        crs_geo = CRS.from_epsg(4326)
        forward = Transformer.from_crs(crs_geo, crs_native, always_xy=True)

        x_LL, y_LL = forward.transform(LL_lon, LL_lat)
        x_LR, _ = forward.transform(LR_lon, LR_lat)
        _, y_UL = forward.transform(UL_lon, UL_lat)

        x = np.linspace(x_LL, x_LR, xsize)
        y = np.linspace(y_LL, y_UL, ysize)

        return cartopy_crs, x, y

    @classmethod
    def read_composite(cls, h5_file: str) -> Tuple[np.ndarray, Dict[str, Any]]:
        with h5py.File(h5_file, "r") as f:
            data_node = f["dataset1/data1/data"] if "dataset1/data1/data" in f else f["dataset1/data1"]
            raw_data = data_node[:].astype(float)

            what_attrs = {}
            for path in ["dataset1/data1/what", "dataset1/what", "what"]:
                if path in f:
                    what_attrs = dict(f[path].attrs)
                    break

            gain = float(what_attrs.get("gain", data_node.attrs.get("gain", 1.0)))
            offset = float(what_attrs.get("offset", data_node.attrs.get("offset", 0.0)))
            nodata = float(what_attrs.get("nodata", data_node.attrs.get("nodata", 255.0)))
            undetect = float(what_attrs.get("undetect", data_node.attrs.get("undetect", 0.0)))
            quantity = what_attrs.get("quantity", b"UNKNOWN")
            if isinstance(quantity, bytes):
                quantity = quantity.decode("utf-8")

        physical_data = raw_data * gain + offset

        mask_nodata = (raw_data == nodata)
        mask_undetect = (raw_data == undetect)

        physical_data[mask_nodata] = np.nan
        
        if quantity == "DBZH":
            physical_data[mask_undetect] = np.nan
            unit = "dBZ"
        elif quantity == "RATE":
            physical_data[mask_undetect] = 0.0
            unit = "mm/h"
        else:
            physical_data[mask_undetect] = np.nan
            unit = "units"

        meta = {
            "quantity": quantity,
            "unit": unit,
            "gain": gain,
            "offset": offset,
            "nodata": nodata,
            "undetect": undetect
        }

        return np.flipud(physical_data), meta


# ==============================================================================
# MODULE 2: METEOGATE / CLOUDFERRO S3 DOWNLOADER
# ==============================================================================
class MeteoGateDownloader:
    """Downloader handling MeteoGate REST API & S3 Direct Fallbacks with temporal cadence rules."""

    API_BASE = "https://api.meteogate.eu/eu-eumetnet-weather-radar/collections/observations/locations/0-20010-0-OPERA"
    S3_BASE = "https://s3.waw3-1.cloudferro.com/openradar-24h"

    CADENCE_MINUTES = {
        "DBZH": 5,
        "RATE": 15,
        "ACRR": 60
    }

    def __init__(self, download_dir: Path = DOWNLOAD_DIR):
        self.download_dir = Path(download_dir)
        self.download_dir.mkdir(parents=True, exist_ok=True)
        
        self.session = requests.Session()
        retry = Retry(total=3, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503, 504])
        self.session.mount("https://", HTTPAdapter(max_retries=retry))

    def snap_timestamp(self, timestamp: dt.datetime, standard_name: str) -> dt.datetime:
        """Snaps timestamp down to the valid cadence interval for the product."""
        interval = self.CADENCE_MINUTES.get(standard_name, 5)
        snapped_minute = (timestamp.minute // interval) * interval
        return timestamp.replace(minute=snapped_minute, second=0, microsecond=0)

    def fetch_composite(self, timestamp: dt.datetime, standard_name: str = "DBZH", fmt: str = "ODIM") -> str:
        timestamp = self.snap_timestamp(timestamp, standard_name)
        time_str = timestamp.strftime("%Y%m%dT%H%M")
        local_filename = self.download_dir / f"OPERA_{time_str}_{standard_name}.h5"

        if local_filename.exists() and local_filename.stat().st_size > 0:
            print(f"--> Found cached local file: {local_filename.name}")
            return str(local_filename)

        s3_url = f"{self.S3_BASE}/{timestamp.strftime('%Y/%m/%d')}/OPERA/COMP/OPERA@{time_str}@0@{standard_name}.h5"

        r = self.session.get(s3_url, stream=True)
        if r.status_code == 200:
            with open(local_filename, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
            print(f"--> Downloaded via S3: {local_filename.name}")
            return str(local_filename)

        iso_start = timestamp.strftime("%Y-%m-%dT%H:%MZ")
        iso_end = (timestamp + dt.timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%MZ")
        
        params = {
            "datetime": f"{iso_start}/{iso_end}",
            "standard_name": standard_name,
            "format": fmt,
            "f": "CoverageJSON"
        }

        r_api = self.session.get(self.API_BASE, params=params)
        
        if r_api.status_code in (204, 404):
            raise FileNotFoundError(f"File for {time_str} ({standard_name}) not found on server (HTTP {r_api.status_code}).")
        
        r_api.raise_for_status()

        data = r_api.json()
        file_urls = data.get("referencing", [])
        if not file_urls:
            raise FileNotFoundError(f"No file links in API response for {time_str}")

        download_url = file_urls[0]
        r_dl = self.session.get(download_url, stream=True)
        r_dl.raise_for_status()

        with open(local_filename, "wb") as f:
            for chunk in r_dl.iter_content(chunk_size=8192):
                f.write(chunk)

        print(f"--> Downloaded via API: {local_filename.name}")
        return str(local_filename)

    def fetch_latest_available(
        self, standard_name: str = "DBZH", initial_lag_minutes: int = 30, max_lookback_hours: int = 3
    ) -> Tuple[str, dt.datetime]:
        now = dt.datetime.now(dt.timezone.utc)
        step_minutes = self.CADENCE_MINUTES.get(standard_name, 5)
        
        start_time = now - dt.timedelta(minutes=initial_lag_minutes)
        start_time = self.snap_timestamp(start_time, standard_name)

        steps = (max_lookback_hours * 60) // step_minutes

        print(f"--> Scanning for latest available {standard_name} (step: {step_minutes}m) starting from {start_time.strftime('%H:%M')} UTC...")

        for step in range(steps):
            check_time = start_time - dt.timedelta(minutes=step * step_minutes)
            try:
                filepath = self.fetch_composite(check_time, standard_name=standard_name)
                print(f"--> Successfully found composite for {check_time.strftime('%Y-%m-%d %H:%M')} UTC!")
                return filepath, check_time
            except FileNotFoundError:
                continue

        raise FileNotFoundError(f"Could not find any available OPERA composite within the last {max_lookback_hours} hours.")


# ==============================================================================
# MODULE 3: OPERA CARTOPY PLOTTER
# ==============================================================================
class OPERAPlotter:
    """Plotting module for OPERA Composites."""

    @staticmethod
    def get_style(quantity: str) -> Tuple[colors.BoundaryNorm, plt.cm.ScalarMappable]:
        if quantity == "DBZH":
            bounds = [-10, 0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70]
            cmap = plt.get_cmap("turbo").copy()
            cmap.set_bad(color="none")
            norm = colors.BoundaryNorm(bounds, ncolors=cmap.N)
        elif quantity == "RATE":
            bounds = [0.0, 0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 20.0, 50.0, 100.0]
            cmap = plt.get_cmap("viridis").copy()
            cmap.set_under(color="white")
            cmap.set_bad(color="dimgrey", alpha=0.5)
            norm = colors.BoundaryNorm(bounds, ncolors=cmap.N)
        else:
            bounds = np.linspace(0, 100, 10)
            cmap = plt.get_cmap("Blues")
            norm = colors.BoundaryNorm(bounds, ncolors=cmap.N)

        return norm, cmap

    @classmethod
    def plot(cls, h5_file: str, output_path: Path):
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        crs, x, y = OPERADataReader.get_crs_and_coords(h5_file)
        data, meta = OPERADataReader.read_composite(h5_file)

        quantity = meta["quantity"]
        unit = meta["unit"]
        norm, cmap = cls.get_style(quantity)

        fig = plt.figure(figsize=(12, 10))
        ax = fig.add_subplot(1, 1, 1, projection=crs)

        p = ax.pcolormesh(
            x, y, data,
            cmap=cmap,
            norm=norm,
            shading="auto"
        )

        ax.add_feature(cfeature.COASTLINE, linewidth=0.8, edgecolor="black")
        ax.add_feature(cfeature.BORDERS, linestyle=":", linewidth=0.6, edgecolor="black")
        
        gl = ax.gridlines(draw_labels=True, linestyle="--", alpha=0.3, color="black")
        gl.top_labels = False
        gl.right_labels = False

        cbar = plt.colorbar(p, ax=ax, pad=0.02, shrink=0.85, extend="max" if quantity == "RATE" else "neither")
        cbar.set_label(f"{quantity} ({unit})", fontsize=12, fontweight="bold")

        filename_str = Path(h5_file).name
        ax.set_title(f"EUMETNET OPERA Composite | {quantity}\nFile: {filename_str}", fontsize=13, fontweight="bold")

        plt.savefig(output_path, dpi=200, bbox_inches="tight")
        plt.close()
        print(f"--> Map saved to: {output_path}")


# ==============================================================================
# PIPELINE EXECUTION DEMONSTRATION
# ==============================================================================
if __name__ == "__main__":
    downloader = MeteoGateDownloader(download_dir=DOWNLOAD_DIR)
    
    print("=== OPERA Composite Pipeline ===")

    try:
        # 1. Fetch latest RATE (15-min cadence)
        rate_file, common_time = downloader.fetch_latest_available(standard_name="RATE", initial_lag_minutes=30)
        OPERAPlotter.plot(rate_file, output_path=OUTPUT_DIR / "opera_rate_map.png")

        # 2. Fetch matching DBZH for the same 15-min timestamp
        print(f"\n--> Fetching Reflectivity (DBZH) for matching timestamp {common_time.strftime('%H:%M')} UTC...")
        dbzh_file = downloader.fetch_composite(common_time, standard_name="DBZH")
        OPERAPlotter.plot(dbzh_file, output_path=OUTPUT_DIR / "opera_dbzh_map.png")

    except Exception as e:
        print(f"\n[!] Pipeline Execution Error: {e}")
        traceback.print_exc()