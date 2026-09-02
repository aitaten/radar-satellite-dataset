# Meteorological Data Reader & Visualization Pipeline

A small, modular Python application/project for reading and visualising several meteorological data sources.

The project currently covers:

- **EUMETNET OPERA** near-real-time radar composites from MeteoGate.
- **EURADCLIM v3** hourly rainfall fields from the KNMI Data Platform.
- **E-SOH** surface weather observations through the public OGC API - EDR service.

A future satellite reader can be added as another data-source module without changing the map plotting layer.

## Why this structure?

The repository is intentionally a **modular application**, not a large generic framework. The readers know how to acquire and decode their own source data. Plotting only knows about generic geospatial products such as a raster field or station observations.

That keeps the call chain simple:

```text
source/API/file -> reader -> small data object -> plotting function -> output figure
```

There is deliberately no `BaseReader`, factory hierarchy, plugin system, or other abstraction until the project actually needs one.

## Repository layout

```text
radar-satellite-dataset/
├── README.md
├── pyproject.toml
├── environment.yml
├── .gitignore
│
├── src/
│   └── weather_data/
│       ├── __init__.py
│       ├── config.py
│       ├── covjson.py
│       ├── esoh.py
│       ├── euradclim.py
│       ├── http.py
│       ├── models.py
│       ├── opera.py
│       ├── plotting.py
│       └── spatial.py
│
├── scripts/
│   ├── plot_esoh.py
│   ├── plot_euradclim.py
│   └── plot_opera.py
│
├── cache/
└── output/
```

`cache/` is for downloaded/raw local data and API cache files. `output/` is for generated figures. Both are ignored by Git.

## Installation

### Conda/Mamba

```bash
mamba env create -f environment.yml
mamba activate meteorological_data_env
```

### pip / uv

Create a virtual environment with Python 3.10+ and install the project in editable mode:

```bash
python -m pip install -e .
```

or:

```bash
uv pip install -e .
```

## KNMI credentials for EURADCLIM

EURADCLIM uses the KNMI Data Platform API. Provide the key either as an environment variable:

```bash
export KNMI_API_KEY="your-key"
```

or create `secret_API.json` in the repository root:

```json
{
  "API_KEY": "your-key"
}
```

`secret_API.json` is ignored by Git and should never be committed.

## Running the programs

### OPERA

Fetch the latest available product and plot it:

```bash
python scripts/plot_opera.py                 # original RATE + matching DBZH workflow
python scripts/plot_opera.py --product RATE
python scripts/plot_opera.py --product DBZH
```

### EURADCLIM v3

Compare specific hourly timestamps:

```bash
python scripts/plot_euradclim.py \
    2018-07-14T12:00 \
    2021-07-14T12:00
```

### E-SOH

Plot station observations for a parameter over the last 30 minutes across the default European bounding box:

```bash
python scripts/plot_esoh.py air_temperature
python scripts/plot_esoh.py precipitation_amount
python scripts/plot_esoh.py wind_speed
```

The public E-SOH service is used through its OGC API - EDR endpoints. The client exposes metadata, locations, area, position, and single-location retrieval so application code can use the observations without involving plotting.

## Using the modules from another program

The main benefit of the reorganisation is that another Python program can import the readers directly rather than launching these scripts.

```python
import datetime as dt

from weather_data.opera import MeteoGateDownloader, OPERADataReader
from weather_data.plotting import plot_raster

when = dt.datetime.now(dt.timezone.utc)
downloader = MeteoGateDownloader()
path, timestamp = downloader.fetch_latest_available("RATE")
field = OPERADataReader.read_composite(path)
plot_raster(field, "output/rate.png", title=f"OPERA RATE | {timestamp:%Y-%m-%d %H:%M UTC}")
```

Likewise, an application can query E-SOH without generating a figure:

```python
import datetime as dt

from weather_data.esoh import ESoHClient

client = ESoHClient()
end = dt.datetime.now(dt.timezone.utc)
observations = client.observation_records(
    start=end - dt.timedelta(minutes=30),
    end=end,
    parameters=["air_temperature"],
    bbox=(-12, 34, 32, 72),
)
records = observations.as_records()
```

## Design decisions

### 1. Readers are independent

`opera.py`, `euradclim.py`, and `esoh.py` each contain source-specific API/download/parsing logic. They do not know how another source works.

### 2. Plotting is source-independent

`plotting.py` provides generic functions for:

- native-grid raster maps (`plot_raster`),
- side-by-side raster comparisons (`plot_raster_comparison`),
- station-value scatter maps (`plot_station_observations`).

This is the part intended to make a later satellite reader easy to add. A satellite raster reader should return the same simple `RasterField` concept whenever its native grid can be represented that way.

### 3. Raster and station data stay different

OPERA and EURADCLIM are gridded raster products. E-SOH is station observations. The project therefore does **not** force them into one universal dataframe/model merely for the sake of abstraction.

### 4. Scripts are thin

The files in `scripts/` are command-line entry points and demonstrations. They should remain small. Reusable functionality belongs in `src/weather_data/`.

## Existing EURADCLIM behaviour retained

The original EURADCLIM program downloaded monthly ZIP packages, cached them locally, extracted HDF5 files, read the native LAEA grid, preserved `0.0` rainfall separately from missing data, and produced a native-projection comparison figure. That behaviour is now distributed across `EURADCLIMClient` and the generic raster plotting functions rather than being embedded in one long script.

## Sources / API documentation

The E-SOH reader is based on the public E-SOH / MeteoGate OGC API - EDR service described in the EUMETNET E-SOH documentation. The main public service is:

`https://observations.meteogate.eu/`

The API documentation is available from its `/docs` endpoint.

## Notes for future satellite integration

When the satellite reader is added, prefer this sequence:

```text
satellite.py
    -> download/open satellite product
    -> return RasterField (or another small source-specific object)

plotting.py
    -> plot_raster(...)
```

If the satellite product is swath-based, vector-based, or otherwise not naturally representable by `RasterField`, add a small dedicated model/plot function rather than making `RasterField` contain every possible geospatial case.
