"""Small source-independent data containers.

The project deliberately keeps the core models lightweight. OPERA/EURADCLIM are
raster products, while E-SOH is station data, so they should not be forced into a
single artificial table structure.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass
class RasterField:
    """A georeferenced 2-D field in its native projected coordinate system."""

    data: np.ndarray
    x: np.ndarray
    y: np.ndarray
    crs: Any
    quantity: str
    unit: str
    metadata: dict[str, Any]


@dataclass
class StationObservations:
    """Tabular station observations returned by E-SOH."""

    records: list[dict[str, Any]]

    def as_records(self) -> list[dict[str, Any]]:
        return list(self.records)
