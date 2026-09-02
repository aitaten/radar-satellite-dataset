"""Command-line entry points for the meteorological data project."""

from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path

import numpy as np

from .config import DirectoryConfig, ESoHQueryConfig
from .esoh import ESoHClient
from .euradclim import EURADCLIMClient
from .opera import MeteoGateDownloader, OPERADataReader
from .plotting import plot_raster, plot_raster_comparison, plot_station_observations


def plot_opera() -> None:
    parser = argparse.ArgumentParser(description="Download and plot OPERA radar products.")
    parser.add_argument("--product", default="PAIR", choices=["PAIR", "RATE", "DBZH", "ACRR"], help="PAIR reproduces the original latest RATE + matching DBZH workflow.")
    parser.add_argument("--output-dir", default="output")
    args = parser.parse_args()

    directories = DirectoryConfig(output=Path(args.output_dir))
    directories.ensure()
    downloader = MeteoGateDownloader(directories.opera_cache)
    if args.product == "PAIR":
        rate_file, common_time = downloader.fetch_latest_available("RATE")
        plot_raster(OPERADataReader.read_composite(rate_file), directories.output / "opera_rate_map.png", title=f"EUMETNET OPERA | RATE | {common_time:%Y-%m-%d %H:%M UTC}")
        dbzh_file = downloader.fetch_composite(common_time, standard_name="DBZH")
        plot_raster(OPERADataReader.read_composite(dbzh_file), directories.output / "opera_dbzh_map.png", title=f"EUMETNET OPERA | DBZH | {common_time:%Y-%m-%d %H:%M UTC}")
        return
    path, timestamp = downloader.fetch_latest_available(args.product)
    field = OPERADataReader.read_composite(path)
    output = directories.output / f"opera_{args.product.lower()}_map.png"
    plot_raster(field, output, title=f"EUMETNET OPERA | {args.product} | {timestamp:%Y-%m-%d %H:%M UTC}")
    print(f"Saved: {output}")


def plot_euradclim() -> None:
    parser = argparse.ArgumentParser(description="Download and compare EURADCLIM v3 fields.")
    parser.add_argument("times", nargs="+", help="UTC timestamps, e.g. 2018-07-14T12:00")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    directories = DirectoryConfig()
    directories.ensure()
    times = [dt.datetime.fromisoformat(value) for value in args.times]
    fields = EURADCLIMClient().read_times(times)
    titles = []
    for when, field in zip(times, fields):
        maximum = float(np.nanmax(field.data)) if np.isfinite(field.data).any() else 0.0
        titles.append(f"{when:%Y-%m-%d %H:%M UTC} | Max = {maximum:.2f} mm/h")
    output = Path(args.output) if args.output else directories.output / "euradclim_v3_comparison.png"
    plot_raster_comparison(fields, titles, output, suptitle="EURADCLIM v3 Comparison")
    print(f"Saved: {output}")


def plot_esoh() -> None:
    parser = argparse.ArgumentParser(description="Query E-SOH station observations and plot them.")
    parser.add_argument("parameter", help="E-SOH/CF parameter name")
    parser.add_argument("--hours", type=float, default=0.5)
    parser.add_argument("--bbox", nargs=4, type=float, default=ESoHQueryConfig().bbox, metavar=("W", "S", "E", "N"))
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    directories = DirectoryConfig()
    directories.ensure()
    end = dt.datetime.now(dt.timezone.utc)
    start = end - dt.timedelta(hours=args.hours)
    observations = ESoHClient().observation_records(start=start, end=end, parameters=[args.parameter], bbox=tuple(args.bbox))
    output = Path(args.output) if args.output else directories.output / f"esoh_{args.parameter}.png"
    plot_station_observations(observations.as_records(), output, title=f"E-SOH | {args.parameter} | {end:%Y-%m-%d %H:%M UTC}", value_label=args.parameter)
    print(f"Saved: {output}")
