# References

This directory contains the main scientific, technical, and data-source references used in the development of the radar–satellite dataset pipeline.

The references cover four main areas:

1. EURADCLIM precipitation data.
2. OPERA weather-radar products and formats.
3. OPERA-SEVIRI ready combined datasets

## Directory contents

| File | Description | Relevance to this repository |
|---|---|---|
| `references_README.md` | This document. It provides an overview of all references stored in this directory and explains how each one relates to the processing pipeline. | Helps contributors identify the correct source for dataset definitions, file formats, variables, projections, calibration, and processing decisions. |
| `essd-15-1441-2023.pdf` | Scientific description of EURADCLIM, the European high-resolution gauge-adjusted radar precipitation climatology. It explains the input OPERA radar composites, rain-gauge adjustment, quality control, spatial resolution, temporal accumulation, validation, and known limitations. | Main scientific reference for understanding the EURADCLIM precipitation fields used or reproduced by the pipeline. |
| `ODIM_H5_v2.4.1_final.pdf` | EUMETNET OPERA specification for representing weather-radar products in HDF5. It documents the ODIM groups and attributes, including `/what`, `/where`, `/how`, datasets, quantities, gain, offset, `nodata`, `undetect`, projection information, and radar-product metadata. | Main technical reference for reading and interpreting native OPERA and EURADCLIM HDF5 files correctly. |
| `atmosphere-10-00320.pdf` | Scientific overview of the OPERA weather-radar network, European radar-data exchange, composite production, and operational infrastructure. | Provides background on the origin and characteristics of the European radar observations used by EURADCLIM and OPERA products. |

## External resources

The following resources are important for the project but do not necessarily need to be stored as local files. Keeping an official link is usually preferable because the pages or documentation may be updated.

### OPERA–SEVIRI ML/AI Fusion Dataset

Official description of the existing OPERA–SEVIRI fusion dataset hosted in the European Weather Cloud:

- https://europeanweather.cloud/news/opera-seviri-mlai-fusion-dataset-available-ewc

This resource describes the motivation, source datasets, period, temporal frequency, common spatial grid, and intended machine-learning applications of the combined OPERA and SEVIRI dataset. It is the main reference for comparing this repository's output with the previously generated fusion dataset.

### EURADCLIM

Dataset and project information:

- https://dataplatform.knmi.nl/dataset/rad-opera-hourly-rainfall-accumulation-euradclim-3-0

Official dataset and project information should also be referenced from the KNMI Data Platform. The exact dataset version used by the code should always be recorded because metadata, coverage, and processing may differ between EURADCLIM releases.

## Reference scope

The documents in this directory should support the following parts of the pipeline:

- downloading or locating source data;
- interpreting OPERA, EURADCLIM, and SEVIRI metadata;
- decoding packed variables using `gain`, `offset`, `_FillValue`, `nodata`, or `undetect`;
- converting projected coordinates to longitude and latitude;
- identifying channel units and physical meaning;
- applying quality-control rules;
- resampling or reprojecting observations onto a common grid;
- generating temporally aligned radar–satellite fields;
- writing the resulting data to Zarr;
- documenting assumptions and limitations for reproducibility.