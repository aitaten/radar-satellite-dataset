"""Small CoverageJSON helpers for E-SOH responses."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from itertools import product
from typing import Any
import numpy as np

def _as_datetime(value: Any) -> datetime | Any:
    if isinstance(value, str):
        text = value.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            return value
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    return value


def coveragejson_to_records(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Convert a CoverageJSON-like object into one record per value.

    The common E-SOH station case is a time series at a fixed point, but this
    also handles simple multi-axis ranges by expanding their flattened values.
    """

    # E-SOH area queries return a CoverageCollection.
    coverages = payload.get("coverages")
    if coverages is not None:
        observations: list[dict[str, Any]] = []
        for coverage in coverages:
            if isinstance(coverage, Mapping):
                observations.extend(coveragejson_to_records(coverage))
        return observations

    domain = payload.get("domain", {})
    axes = domain.get("axes", {})
    ranges = payload.get("ranges", {})
    if not ranges:
        return []

    def axis_values(name: str) -> list[Any]:
        axis = axes.get(name, {})
        values = axis.get("values")
        if values is None:
            return []
        return list(values)

    times = [_as_datetime(v) for v in axis_values("t")]
    xs = axis_values("x")
    ys = axis_values("y")

    observations: list[dict[str, Any]] = []
    for parameter_name, rng in ranges.items():
        if not isinstance(rng, Mapping):
            continue
        values = list(rng.get("values", []))
        shape = list(rng.get("shape", []))
        axis_names = list(rng.get("axisNames", []))

        if not axis_names:
            # EDR responses normally provide axisNames; this fallback is kept
            # deliberately conservative for simple time-series responses.
            if len(times) == len(values):
                axis_names = ["t"]
                shape = [len(values)]
            else:
                axis_names = []

        if not shape and axis_names:
            inferred = []
            for name in axis_names:
                inferred.append(max(1, len(axis_values(name))))
            shape = inferred

        if not shape:
            shape = [len(values)]

        # If the range declares a single dimension whose size matches values,
        # map it directly. This is the normal station time-series case.
        if len(shape) == 1 and shape[0] == len(values):
            for i, value in enumerate(values):
                if parameter_name.startswith("precipitation_amount"):
                    clean_value = np.nan if isinstance(value, (int, float)) and value < 0 else value
                else:
                    clean_value = value
                record: dict[str, Any] = {"parameter": parameter_name, "value": clean_value}
                if axis_names:
                    axis_name = axis_names[0]
                    _attach_axis_value(record, axis_name, i, times, xs, ys)
                # Station locations often have one fixed x/y coordinate.
                if xs and "longitude" not in record:
                    record["longitude"] = xs[0]
                if ys and "latitude" not in record:
                    record["latitude"] = ys[0]
                observations.append(record)
            continue

        # General flattened Cartesian expansion.
        index_shape = [range(int(size)) for size in shape]
        for flat_index, combo in enumerate(product(*index_shape)):
            if flat_index >= len(values):
                break
            value = values[flat_index]
            if parameter_name.startswith("precipitation_amount"):
                clean_value = np.nan if isinstance(value, (int, float)) and value < 0 else value
            else:
                clean_value = value
            record = {"parameter": parameter_name, "value": clean_value}
            for axis_name, index in zip(axis_names, combo):
                _attach_axis_value(record, axis_name, index, times, xs, ys)
            observations.append(record)

    return observations


def _attach_axis_value(
    record: dict[str, Any], axis_name: str, index: int, times: list[Any], xs: list[Any], ys: list[Any]
) -> None:
    if axis_name == "t" and index < len(times):
        record["datetime"] = times[index]
    elif axis_name == "x" and index < len(xs):
        record["longitude"] = xs[index]
    elif axis_name == "y" and index < len(ys):
        record["latitude"] = ys[index]
    else:
        record[axis_name] = index
