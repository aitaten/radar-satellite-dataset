"""EURADCLIM v3 download, extraction, and HDF5 rainfall reading."""

from __future__ import annotations

import json
import os
import zipfile
import requests
from pathlib import Path
from typing import Iterable

import h5py
import numpy as np

from .config import DirectoryConfig
from .http import build_session
from .models import RasterField
from .spatial import grid_coordinates_from_corners


class EURADCLIMClient:
    """Download and read EURADCLIM v3 monthly packages from KNMI."""

    BASE_URL = "https://api.dataplatform.knmi.nl/open-data/v1"
    DATASET = "RAD_OPERA_HOURLY_RAINFALL_ACCUMULATION_EURADCLIM"
    VERSION = "3.0"

    def __init__(self, api_key: str | None = None, cache_dir: Path | None = None):
        self.api_key = api_key or self._read_api_key()
        self.cache_dir = Path(cache_dir or DirectoryConfig().euradclim_cache)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.api_session = build_session(
            retries=10, backoff_factor=1.0, headers={"Authorization": self.api_key}
        )
        self.s3_session = build_session(retries=10, backoff_factor=1.0)

    @staticmethod
    def _read_api_key() -> str:
        env_key = os.getenv("KNMI_API_KEY")
        if env_key:
            return env_key
        secret_file = Path("secret_API.json")
        if not secret_file.exists():
            raise FileNotFoundError(
                "KNMI API key not found. Set KNMI_API_KEY or create secret_API.json with {\"API_KEY\": \"...\"}."
            )
        with secret_file.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data["API_KEY"]

    def get_zip_filename(self, year_month: str) -> str:
        prefix = f"{self.DATASET}_{year_month}"
        for path in self.cache_dir.iterdir():
            if path.name.startswith(prefix) and path.suffix == ".zip" and path.stat().st_size > 0:
                return path.name

        url = f"{self.BASE_URL}/datasets/{self.DATASET}/versions/{self.VERSION}/files"
        params = {"maxKeys": 100}
        while True:
            response = self.api_session.get(url, params=params)

            if response.status_code != 200:
                print(f"KNMI status code: {response.status_code}")
                print(f"KNMI URL: {response.url}")
                print(f"KNMI response: {response.text[:1000]}")
                print(
                    "Authorization header present:",
                    "Authorization" in self.api_session.headers
                )
                raise requests.HTTPError(
                    f"KNMI request failed with HTTP {response.status_code}",
                    response=response,
                )

            response.raise_for_status()
            data = response.json()
            for item in data.get("files", []):
                filename = item.get("filename", "")
                if filename.startswith(prefix) and filename.endswith(".zip"):
                    return filename
            if data.get("isTruncated") and data.get("nextPageToken"):
                params["nextPageToken"] = data["nextPageToken"]
            else:
                break
        raise FileNotFoundError(f"No EURADCLIM package found for {year_month}.")

    def get_download_url(self, filename: str) -> str:
        url = f"{self.BASE_URL}/datasets/{self.DATASET}/versions/{self.VERSION}/files/{filename}/url"
        response = self.api_session.get(url, timeout=30)
        response.raise_for_status()
        return response.json()["temporaryDownloadUrl"]

    def download_zip(self, filename: str) -> Path:
        path = self.cache_dir / filename
        if path.exists() and path.stat().st_size > 0:
            return path
        url = self.get_download_url(filename)
        response = self.s3_session.get(url, stream=True, timeout=60)
        response.raise_for_status()
        with path.open("wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        return path

    @staticmethod
    def extract_zip(zip_path: Path) -> Path:
        target = zip_path.parent / zip_path.stem
        if target.exists() and any(target.iterdir()):
            return target
        target.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path, "r") as archive:
            archive.extractall(target)
        return target

    def find_file(self, event_time, extract_dir: Path) -> Path:
        token = event_time.strftime("%Y%m%d%H")
        matches = [p for p in extract_dir.rglob("*.h5") if token in p.name]
        if not matches:
            raise FileNotFoundError(f"No EURADCLIM HDF5 file found for {token} in {extract_dir}.")
        return matches[0]

    @staticmethod
    def get_crs_and_coords(h5_file: Path):
        with h5py.File(h5_file, "r") as f:
            where = f["where"].attrs
            projdef = where["projdef"]
            if isinstance(projdef, bytes):
                projdef = projdef.decode()
            return grid_coordinates_from_corners(
                projdef,
                int(where["xsize"]), int(where["ysize"]),
                float(where["LL_lon"]), float(where["LL_lat"]),
                float(where["LR_lon"]), float(where["LR_lat"]),
                float(where["UL_lon"]), float(where["UL_lat"]),
            )

    @staticmethod
    def read_rain(file: Path) -> RasterField:
        with h5py.File(file, "r") as f:
            data_node = f["dataset1/data1"]
            data = data_node["data"][:].astype(float) if "data" in data_node else data_node[:].astype(float)

            gain = 1.0
            offset = 0.0
            nodata = -9999000.0
            for path in ("dataset1/data1/what", "dataset1/what"):
                if path in f:
                    attrs = f[path].attrs
                    gain = attrs.get("gain", gain)
                    offset = attrs.get("offset", offset)
                    nodata = attrs.get("nodata", nodata)
            gain = data_node.attrs.get("gain", gain)
            offset = data_node.attrs.get("offset", offset)
            nodata = data_node.attrs.get("nodata", nodata)

        data = data * gain + offset
        data[data == nodata] = np.nan
        data[(data < 0.1) & ~np.isnan(data)] = 0.0
        crs, x, y = EURADCLIMClient.get_crs_and_coords(file)
        return RasterField(
            np.flipud(data), x, y, crs, "precipitation", "mm/h",
            {"source_file": str(file), "gain": gain, "offset": offset, "nodata": nodata},
        )

    def read_times(self, event_times: Iterable) -> list[RasterField]:
        fields = []
        for event_time in event_times:
            ym = event_time.strftime("%Y%m")
            archive = self.download_zip(self.get_zip_filename(ym))
            extract_dir = self.extract_zip(archive)
            fields.append(self.read_rain(self.find_file(event_time, extract_dir)))
        return fields
