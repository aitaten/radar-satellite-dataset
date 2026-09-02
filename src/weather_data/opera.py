"""OPERA MeteoGate download and ODIM-HDF5 reading."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

import h5py
import numpy as np

from .config import DirectoryConfig
from .http import build_session
from .models import RasterField
from .spatial import grid_coordinates_from_corners


class OPERADataReader:
    """Reader for EUMETNET OPERA ODIM HDF5 composite files."""

    @staticmethod
    def get_crs_and_coords(h5_file: str | Path):
        with h5py.File(h5_file, "r") as f:
            where = f["where"].attrs
            xsize = int(where["xsize"])
            ysize = int(where["ysize"])
            projdef = where["projdef"]
            if isinstance(projdef, bytes):
                projdef = projdef.decode("utf-8")

            return grid_coordinates_from_corners(
                projdef,
                xsize,
                ysize,
                float(where["LL_lon"]), float(where["LL_lat"]),
                float(where["LR_lon"]), float(where["LR_lat"]),
                float(where["UL_lon"]), float(where["UL_lat"]),
            )

    @classmethod
    def read_composite(cls, h5_file: str | Path) -> RasterField:
        with h5py.File(h5_file, "r") as f:
            data_node = f["dataset1/data1/data"] if "dataset1/data1/data" in f else f["dataset1/data1"]
            raw = data_node[:].astype(float)

            attrs: dict[str, Any] = {}
            for path in ("dataset1/data1/what", "dataset1/what", "what"):
                if path in f:
                    attrs = dict(f[path].attrs)
                    break

            gain = float(attrs.get("gain", data_node.attrs.get("gain", 1.0)))
            offset = float(attrs.get("offset", data_node.attrs.get("offset", 0.0)))
            nodata = float(attrs.get("nodata", data_node.attrs.get("nodata", 255.0)))
            undetect = float(attrs.get("undetect", data_node.attrs.get("undetect", 0.0)))
            quantity = attrs.get("quantity", b"UNKNOWN")
            if isinstance(quantity, bytes):
                quantity = quantity.decode("utf-8")

        data = raw * gain + offset
        data[raw == nodata] = np.nan

        if quantity == "DBZH":
            data[raw == undetect] = np.nan
            unit = "dBZ"
        elif quantity == "RATE":
            data[raw == undetect] = 0.0
            unit = "mm/h"
        else:
            data[raw == undetect] = np.nan
            unit = "units"

        crs, x, y = cls.get_crs_and_coords(h5_file)
        metadata = {
            "quantity": quantity,
            "unit": unit,
            "gain": gain,
            "offset": offset,
            "nodata": nodata,
            "undetect": undetect,
            "source_file": str(h5_file),
        }
        return RasterField(np.flipud(data), x, y, crs, quantity, unit, metadata)


class MeteoGateDownloader:
    """Downloader for current OPERA composites with S3-first, EDR fallback."""

    API_BASE = (
        "https://api.meteogate.eu/eu-eumetnet-weather-radar/"
        "collections/observations/locations/0-20010-0-OPERA"
    )
    S3_BASE = "https://s3.waw3-1.cloudferro.com/openradar-24h"
    CADENCE_MINUTES = {"DBZH": 5, "RATE": 15, "ACRR": 60}

    def __init__(self, download_dir: Path | None = None):
        self.download_dir = Path(download_dir or DirectoryConfig().opera_cache)
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.session = build_session(retries=3, backoff_factor=0.5)

    def snap_timestamp(self, timestamp: dt.datetime, standard_name: str) -> dt.datetime:
        interval = self.CADENCE_MINUTES.get(standard_name, 5)
        snapped_minute = (timestamp.minute // interval) * interval
        return timestamp.replace(minute=snapped_minute, second=0, microsecond=0)

    def fetch_composite(
        self, timestamp: dt.datetime, standard_name: str = "DBZH", fmt: str = "ODIM"
    ) -> Path:
        timestamp = self.snap_timestamp(timestamp, standard_name)
        time_str = timestamp.strftime("%Y%m%dT%H%M")
        path = self.download_dir / f"OPERA_{time_str}_{standard_name}.h5"
        if path.exists() and path.stat().st_size > 0:
            return path

        s3_url = (
            f"{self.S3_BASE}/{timestamp.strftime('%Y/%m/%d')}/OPERA/COMP/"
            f"OPERA@{time_str}@0@{standard_name}.h5"
        )
        response = self.session.get(s3_url, stream=True, timeout=30)
        if response.status_code == 200:
            self._save_stream(response, path)
            return path

        iso_start = timestamp.strftime("%Y-%m-%dT%H:%MZ")
        iso_end = (timestamp + dt.timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%MZ")
        params = {"datetime": f"{iso_start}/{iso_end}", "standard_name": standard_name, "format": fmt, "f": "CoverageJSON"}
        api_response = self.session.get(self.API_BASE, params=params, timeout=30)
        if api_response.status_code in (204, 404):
            raise FileNotFoundError(f"No OPERA file for {time_str} ({standard_name}).")
        api_response.raise_for_status()
        data = api_response.json()
        file_urls = data.get("referencing", [])
        if not file_urls:
            raise FileNotFoundError(f"No OPERA download link for {time_str} ({standard_name}).")

        download = self.session.get(file_urls[0], stream=True, timeout=30)
        download.raise_for_status()
        self._save_stream(download, path)
        return path

    @staticmethod
    def _save_stream(response, path: Path) -> None:
        with path.open("wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

    def fetch_latest_available(
        self,
        standard_name: str = "DBZH",
        initial_lag_minutes: int = 30,
        max_lookback_hours: int = 3,
    ) -> tuple[Path, dt.datetime]:
        now = dt.datetime.now(dt.timezone.utc)
        step = self.CADENCE_MINUTES.get(standard_name, 5)
        start = self.snap_timestamp(now - dt.timedelta(minutes=initial_lag_minutes), standard_name)
        steps = (max_lookback_hours * 60) // step
        for index in range(steps):
            check_time = start - dt.timedelta(minutes=index * step)
            try:
                return self.fetch_composite(check_time, standard_name), check_time
            except FileNotFoundError:
                continue
        raise FileNotFoundError(f"No {standard_name} OPERA composite found in the requested lookback window.")
