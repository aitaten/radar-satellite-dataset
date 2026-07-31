# EURADCLIM v3 Reader & Visualization Pipeline

A Python pipeline to download, parse, and visualize (_for now_) the **EURADCLIM v3** European climatological gauge-adjusted radar precipitation dataset provided by the **KNMI Data Platform**.

## Key Features
- **Rate-limit Protection:** Employs exponential backoff with retries on HTTP 429 errors.
- **Session Header Isolation:** Uses separate HTTP sessions for KNMI API queries (authenticated) and AWS S3 downloads (unauthenticated presigned URLs).
- **Native Projection Rendering:** Plots directly in Lambert Azimuthal Equal Area (LAEA) projection without spatial resampling or warping artifacts.
- **Data Categorization:** Uses discrete color boundaries (`BoundaryNorm`) to clearly separate:
  - $0.0\text{ mm/h}$ (Dry / No Rain) $\rightarrow$ **White**
  - $\text{NaN}$ (Missing / Out-of-Domain) $\rightarrow$ **Dark Grey**
  - $> 0.1\text{ mm/h}$ (Rain) $\rightarrow$ **Turbo Spectrum**

---

## Configuration & Credentials (`secret_API.json`)

To run this pipeline, you need an API key from the **KNMI Data Platform**.

Create a file named `secret_API.json` in the root directory:

```json
{
    "API_KEY": "YOUR_ACTUAL_KNMI_API_KEY_HERE"
}

```

> **Security Note:** `secret_API.json` is listed in `.gitignore` and will **never** be committed or pushed to remote repositories.

---

## Installation & Environment Setup

You can set up the environment using either **Mamba** (Recommended for geospatial C-bindings) or **`uv`**.

### Option A: Mamba (Recommended)

1. Ensure [Miniforge/Mamba](https://github.com/conda-forge/miniforge) is installed.
2. Create and activate the environment using `environment.yml`:

```bash
# Create environment
mamba env create -f environment.yml

# Activate environment
mamba activate euradclim_env

```

---

### Option B: `uv`

If you prefer using [`uv`](https://github.com/astral-sh/uv):

```bash
# Create a virtual environment with Python 3.10
uv venv .venv --python 3.10

# Activate the virtual environment
# On macOS/Linux:
source .venv/bin/activate
# On Windows:
# .venv\Scripts\activate

# Sync/install dependencies from pyproject.toml
uv pip install -e .

```

---

## Usage

Run the main processing script:

```bash
python read_v3_euradclim.py

```

### Execution Output:

1. **Directory Caching:** Raw dataset packages are downloaded to `./tmp_data/`.
2. **Data Processing:** Extracts hourly precipitation fields and transforms LAEA grid metrics directly.
3. **Visualization:** Generates side-by-side comparative plots saved to `./output/v3_native_comparison.png`.