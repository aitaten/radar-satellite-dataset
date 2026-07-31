import os
import json
import zipfile
from pathlib import Path
import datetime as dt
import numpy as np
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import h5py
from pyproj import CRS, Transformer
import matplotlib.pyplot as plt
import matplotlib.colors as colors
import cartopy.crs as ccrs
import cartopy.feature as cfeature

# ======================================================
# CONFIGURATION & SECRET LOADING
# ======================================================
BASE_URL = "https://api.dataplatform.knmi.nl/open-data/v1"
DATASET = "RAD_OPERA_HOURLY_RAINFALL_ACCUMULATION_EURADCLIM"
VERSION = "3.0"

# Load API key safely from local secret file
SECRET_FILE = "secret_API.json"
if not os.path.exists(SECRET_FILE):
    raise FileNotFoundError(
        f"Missing '{SECRET_FILE}'. Please create it with your KNMI key: "
        '{"API_KEY": "your_key_here"}'
    )

with open(SECRET_FILE, "r") as f:
    config = json.load(f)
    API_KEY = config["API_KEY"]

TMP_DIR = "./tmp_data"
OUTPUT_DIR = "./output"
os.makedirs(TMP_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Timestamps to compare
event_times = [
    dt.datetime(2018, 7, 14, 12, 0),
    dt.datetime(2021, 7, 14, 12, 0)
]

# ======================================================
# ROBUST API SESSION SETUP
# ======================================================
retry = Retry(
    total=10, 
    backoff_factor=1, 
    status_forcelist=[429, 500, 502, 503, 504],
    respect_retry_after_header=True 
)
adapter = HTTPAdapter(max_retries=retry)

# 1. KNMI API Session (WITH API Key)
api_session = requests.Session()
api_session.mount("https://", adapter)
api_session.headers.update({"Authorization": API_KEY})

# 2. AWS S3 Download Session (WITHOUT API Key)
s3_session = requests.Session()
s3_session.mount("https://", adapter)

# ======================================================
# API & DOWNLOAD FUNCTIONS
# ======================================================
def get_zip_filename(year_month):
    """Find the ZIP name locally first, then page through the API."""
    prefix = f"RAD_OPERA_HOURLY_RAINFALL_ACCUMULATION_EURADCLIM_{year_month}"
    
    # Check local directory first
    for f in os.listdir(TMP_DIR):
        if f.startswith(prefix) and f.endswith(".zip"):
            if os.path.getsize(os.path.join(TMP_DIR, f)) > 0:
                print(f"Found existing local ZIP: {f}")
                return f

    # Page through API to locate exact monthly package
    url = f"{BASE_URL}/datasets/{DATASET}/versions/{VERSION}/files"
    params = {"maxKeys": 100}

    print(f"Searching API for ZIP file matching prefix: {prefix}...")
    while True:
        r = api_session.get(url, params=params)
        r.raise_for_status()
        data = r.json()
        
        for f in data.get("files", []):
            filename = f.get("filename", "")
            if filename.startswith(prefix) and filename.endswith(".zip"):
                return filename
                
        if data.get("isTruncated") and data.get("nextPageToken"):
            params["nextPageToken"] = data.get("nextPageToken")
        else:
            break
            
    raise RuntimeError(f"No ZIP file found for {year_month} on KNMI API.")

def get_download_url(filename):
    """Get temporary download URL from KNMI API."""
    url = f"{BASE_URL}/datasets/{DATASET}/versions/{VERSION}/files/{filename}/url"
    r = api_session.get(url)
    r.raise_for_status()
    return r.json()["temporaryDownloadUrl"]

def download_zip(filename):
    """Download ZIP via S3 session without authorization headers."""
    path = os.path.join(TMP_DIR, filename)
    
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return path

    print(f"Downloading: {filename}")
    url = get_download_url(filename)
    
    r = s3_session.get(url, stream=True)
    r.raise_for_status()
    
    with open(path, "wb") as f:
        for chunk in r.iter_content(8192):
            f.write(chunk)
            
    return path

def extract_zip(zip_path):
    """Extract ZIP if not already extracted."""
    extract_dir = os.path.join(TMP_DIR, Path(zip_path).stem)
    
    if os.path.exists(extract_dir) and any(os.scandir(extract_dir)):
        print(f"Already extracted in: {extract_dir}")
        return extract_dir

    print(f"Extracting: {zip_path} to {extract_dir}")
    os.makedirs(extract_dir, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as z:
        z.extractall(extract_dir)
    return extract_dir

# ======================================================
# HDF5 & COORDINATE PROCESSING
# ======================================================
def get_native_crs_and_xy(file):
    """Extract LAEA projection CRS and clean 1D x, y grid coordinates in meters."""
    with h5py.File(file, "r") as f:
        where = f["where"].attrs
        xsize, ysize = where["xsize"], where["ysize"]
        
        projdef = where["projdef"]
        if isinstance(projdef, bytes):
            projdef = projdef.decode()

        LL_lon, LL_lat = where["LL_lon"], where["LL_lat"]
        LR_lon, LR_lat = where["LR_lon"], where["LR_lat"]
        UL_lon, UL_lat = where["UL_lon"], where["UL_lat"]

    crs_laea = CRS.from_proj4(projdef)
    crs_geo = CRS.from_epsg(4326)
    forward = Transformer.from_crs(crs_geo, crs_laea, always_xy=True)

    x_LL, y_LL = forward.transform(LL_lon, LL_lat)
    x_LR, _ = forward.transform(LR_lon, LR_lat)
    _, y_UL = forward.transform(UL_lon, UL_lat)

    x = np.linspace(x_LL, x_LR, xsize)
    y = np.linspace(y_LL, y_UL, ysize)
    
    cartopy_crs = ccrs.Projection(crs_laea)
    return cartopy_crs, x, y

def read_rain(file):
    """Extract rainfall matrix, preserving 0.0 mm/h and masking invalid data as NaN."""
    with h5py.File(file, "r") as f:
        data_node = f["dataset1/data1"]
        if "data" in data_node:
            rain = data_node["data"][:].astype(float)
        else:
            rain = data_node[:].astype(float)
            
        gain = 1.0
        offset = 0.0
        nodata = -9999000.0  
        
        if "dataset1/data1/what" in f:
            what = f["dataset1/data1/what"].attrs
            gain = what.get("gain", gain)
            offset = what.get("offset", offset)
            nodata = what.get("nodata", nodata)
        elif "dataset1/what" in f:
            what = f["dataset1/what"].attrs
            nodata = what.get("nodata", nodata)
            
        gain = data_node.attrs.get("gain", gain)
        offset = data_node.attrs.get("offset", offset)
        nodata = data_node.attrs.get("nodata", nodata)

    rain = rain * gain + offset
    
    # Mask missing values as NaN
    rain[rain == nodata] = np.nan
    
    # Convert low or negative values to explicit 0.0 mm/h
    rain[(rain < 0.1) & (~np.isnan(rain))] = 0.0

    return np.flipud(rain)

# ======================================================
# DATA INGESTION
# ======================================================
fields = []
maxvals = []
native_crs = None
x_coords = None
y_coords = None

for event_time in event_times:
    ym = event_time.strftime("%Y%m")
    
    zip_name = get_zip_filename(ym)
    zip_path = download_zip(zip_name)
    extract_dir = extract_zip(zip_path)

    timestamp_str = event_time.strftime("%Y%m%d%H")
    all_files = list(Path(extract_dir).rglob("*.h5"))
    target_file = next((f for f in all_files if timestamp_str in f.name), None)

    if not target_file:
        raise RuntimeError(f"File for {timestamp_str} not found in {extract_dir}")

    print(f"Reading: {target_file}")
    rain = read_rain(target_file)
    
    if native_crs is None:
        native_crs, x_coords, y_coords = get_native_crs_and_xy(target_file)

    fields.append(rain)
    maxvals.append(np.nanmax(rain) if not np.all(np.isnan(rain)) else 0.0)

# ======================================================
# PLOTTING IN NATIVE LAEA PROJECTION
# ======================================================
print("\nPlotting in native projection with distinct NaN vs 0.0 visualization...")

# Setup discrete color boundaries
boundaries = [0.0, 0.01, 0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 20.0, 50.0, 100.0]
norm = colors.BoundaryNorm(boundaries, ncolors=256, clip=False)

cmap = plt.get_cmap("turbo").copy()
cmap.set_under(color="white")          # 0.0 mm/h renders as WHITE
cmap.set_bad(color="dimgrey", alpha=0.8) # Missing data (NaN) renders as DARK GREY

fig = plt.figure(figsize=(20, 8))
gs = fig.add_gridspec(1, 2, hspace=0.12, wspace=0.02)

for i in range(len(event_times)):
    ax = fig.add_subplot(gs[0, i], projection=native_crs)
    rain = fields[i]

    p = ax.pcolormesh(
        x_coords, y_coords, rain,
        cmap=cmap,
        norm=norm,
        shading="auto"
    )

    ax.add_feature(cfeature.COASTLINE, linewidth=0.8)
    ax.add_feature(cfeature.BORDERS, linestyle=":", linewidth=0.5)
    
    gl = ax.gridlines(draw_labels=True, linestyle="--", alpha=0.4, color="black")
    gl.top_labels = False
    gl.right_labels = False

    plt.colorbar(p, ax=ax, label="mm/h", extend="min", pad=0.02, shrink=0.8)
    ax.set_title(f"{event_times[i]} | Max = {maxvals[i]:.2f} mm/h", fontsize=14, fontweight="bold")

plt.suptitle("EURADCLIM v3 Comparison (Native Grid)", fontsize=18, y=1.02)

outfile = os.path.join(OUTPUT_DIR, "v3_native_comparison.png")
plt.savefig(outfile, dpi=200, bbox_inches="tight")
print(f"Saved: {outfile}")