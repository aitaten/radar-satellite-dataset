"""Quality-control helpers for station observations."""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any, Iterable

import numpy as np


# Deliberately broad limits: these only reject clearly impossible values.
PHYSICAL_LIMITS = {
    "air_temperature": (-90.0, 60.0),
}


def apply_basic_qc(
    records: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Annotate observations with missing-value and physical-range QC."""

    output = []

    for original in records:
        record = dict(original)
        flags: list[str] = []

        value = record.get("value")
        variable = record.get("variable")

        if value is None:
            record["qc_status"] = "invalid"
            record["qc_flags"] = ["missing"]
            output.append(record)
            continue

        if variable in PHYSICAL_LIMITS:
            lower, upper = PHYSICAL_LIMITS[variable]

            if not lower <= float(value) <= upper:
                flags.append("physical_range")

        record["qc_status"] = "invalid" if flags else "valid"
        record["qc_flags"] = flags

        output.append(record)

    return output


def apply_temporal_qc(
    records: Iterable[dict[str, Any]],
    *,
    max_temperature_change: float = 10.0,
    max_minutes: float = 20.0,
) -> list[dict[str, Any]]:
    """Flag suspicious short-term temperature jumps per station."""

    output = [dict(record) for record in records]

    groups: dict[tuple[str, str], list[int]] = defaultdict(list)

    for i, record in enumerate(output):
        wigos_id = record.get("wigos_id")
        parameter = record.get("parameter")
        timestamp = record.get("datetime")

        if (
            wigos_id is None
            or parameter is None
            or timestamp is None
        ):
            continue

        groups[(wigos_id, parameter)].append(i)

    for indices in groups.values():
        indices.sort(
            key=lambda i: output[i]["datetime"]
        )

        for previous_index, current_index in zip(
            indices[:-1],
            indices[1:],
        ):
            previous = output[previous_index]
            current = output[current_index]

            if (
                previous.get("value") is None
                or current.get("value") is None
            ):
                continue

            dt_minutes = (
                current["datetime"] - previous["datetime"]
            ).total_seconds() / 60.0

            if dt_minutes <= 0 or dt_minutes > max_minutes:
                continue

            if current.get("variable") != "air_temperature":
                continue

            delta = abs(
                float(current["value"])
                - float(previous["value"])
            )

            if delta > max_temperature_change:
                _add_flag(
                    current,
                    "temporal_jump",
                    status="suspect",
                )
                _add_flag(
                    previous,
                    "temporal_jump",
                    status="suspect",
                )

    return output


def _haversine_km(
    lat1: float,
    lon1: float,
    lat2: np.ndarray,
    lon2: np.ndarray,
) -> np.ndarray:
    """Great-circle distance from one point to arrays of points."""

    radius = 6371.0

    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)

    lat2_rad = np.radians(lat2)
    lon2_rad = np.radians(lon2)

    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad

    a = (
        np.sin(dlat / 2.0) ** 2
        + np.cos(lat1_rad)
        * np.cos(lat2_rad)
        * np.sin(dlon / 2.0) ** 2
    )

    return 2.0 * radius * np.arcsin(np.sqrt(a))


def apply_spatial_qc(
    records: Iterable[dict[str, Any]],
    *,
    radius_km: float = 100.0,
    min_neighbours: int = 5,
    absolute_threshold: float = 12.0,
    mad_factor: float = 6.0,
) -> list[dict[str, Any]]:
    """Flag temperature observations inconsistent with nearby stations."""

    output = [dict(record) for record in records]

    # ---------------------------------------------------------
    # Station coordinates
    # ---------------------------------------------------------

    stations: dict[str, tuple[float, float]] = {}

    for record in output:
        wigos_id = record.get("wigos_id")
        lat = record.get("latitude")
        lon = record.get("longitude")

        if wigos_id is None or lat is None or lon is None:
            continue

        stations.setdefault(
            wigos_id,
            (float(lat), float(lon)),
        )

    station_ids = list(stations)

    lats = np.asarray(
        [stations[station][0] for station in station_ids],
        dtype=float,
    )
    lons = np.asarray(
        [stations[station][1] for station in station_ids],
        dtype=float,
    )

    # ---------------------------------------------------------
    # Calculate neighbours once per station
    # ---------------------------------------------------------

    neighbours: dict[str, set[str]] = {}

    for i, station_id in enumerate(station_ids):
        distances = _haversine_km(
            lats[i],
            lons[i],
            lats,
            lons,
        )

        neighbours[station_id] = {
            station_ids[j]
            for j in np.where(
                (distances > 0.0)
                & (distances <= radius_km)
            )[0]
        }

    # ---------------------------------------------------------
    # Group observations by exact timestamp and parameter
    # ---------------------------------------------------------

    groups: dict[tuple[Any, str], list[int]] = defaultdict(list)

    for i, record in enumerate(output):
        timestamp = record.get("datetime")
        parameter = record.get("parameter")

        if timestamp is None or parameter is None:
            continue

        groups[(timestamp, parameter)].append(i)

    # ---------------------------------------------------------
    # Spatial consistency
    # ---------------------------------------------------------

    for indices in groups.values():
        available = {
            output[i].get("wigos_id"): i
            for i in indices
            if output[i].get("wigos_id") is not None
            and output[i].get("value") is not None
            and output[i].get("qc_status") != "invalid"
        }

        for station_id, index in available.items():
            record = output[index]

            if record.get("variable") != "air_temperature":
                continue

            neighbour_values = [
                float(output[available[other]]["value"])
                for other in neighbours.get(station_id, ())
                if other in available
            ]

            if len(neighbour_values) < min_neighbours:
                continue

            values = np.asarray(
                neighbour_values,
                dtype=float,
            )

            median = float(np.median(values))

            mad = float(
                np.median(
                    np.abs(values - median)
                )
            )

            robust_sigma = 1.4826 * mad

            threshold = max(
                absolute_threshold,
                mad_factor * robust_sigma,
            )

            difference = abs(
                float(record["value"]) - median
            )

            if difference > threshold:
                _add_flag(
                    record,
                    "spatial_outlier",
                    status="suspect",
                )

                # Keep diagnostics so QC decisions are auditable.
                record["qc_neighbour_median"] = median
                record["qc_neighbour_count"] = len(values)
                record["qc_neighbour_mad"] = mad
                record["qc_spatial_threshold"] = threshold
                record["qc_spatial_difference"] = difference

    return output


def _add_flag(
    record: dict[str, Any],
    flag: str,
    *,
    status: str,
) -> None:
    """Add a QC flag without downgrading an invalid observation."""

    flags = record.setdefault("qc_flags", [])

    if flag not in flags:
        flags.append(flag)

    if record.get("qc_status") != "invalid":
        record["qc_status"] = status
