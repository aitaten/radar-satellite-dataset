"""Configuration dataclasses and defaults for the meteorological data project."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Tuple


@dataclass(frozen=True)
class DirectoryConfig:
    """Local directories used by readers and plotting scripts."""

    root: Path = Path(".")
    output: Path = Path("output")
    opera_cache: Path = Path("cache/opera")
    euradclim_cache: Path = Path("cache/euradclim")
    esoh_cache: Path = Path("cache/esoh")

    def ensure(self) -> None:
        self.output.mkdir(parents=True, exist_ok=True)
        self.opera_cache.mkdir(parents=True, exist_ok=True)
        self.euradclim_cache.mkdir(parents=True, exist_ok=True)
        self.esoh_cache.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class ESoHParameter:
    """Human-facing definition of one E-SOH observation parameter."""

    name: str
    label: str
    unit: str | None = None
    colorbar_label: str | None = None


ESOH_PARAMETERS: dict[str, ESoHParameter] = {
    "air_temperature": ESoHParameter("air_temperature", "Air temperature", "°C", "Air temperature (°C)"),
    "precipitation_amount": ESoHParameter("precipitation_amount", "Precipitation", "mm", "Precipitation (mm)"),
    "surface_downwelling_shortwave_flux_in_air": ESoHParameter(
        "surface_downwelling_shortwave_flux_in_air",
        "Solar radiation",
        "W m⁻²",
        "Solar radiation (W m⁻²)",
    ),
    "wind_speed": ESoHParameter("wind_speed", "Wind speed", "m s⁻¹", "Wind speed (m s⁻¹)"),
    "wind_from_direction": ESoHParameter(
        "wind_from_direction", "Wind direction", "degree", "Wind direction (°)",
    ),
}


@dataclass(frozen=True)
class MapConfig:
    """Common Cartopy map appearance settings."""

    figsize: Tuple[float, float] = (12.0, 9.0)
    coastlines_linewidth: float = 0.8
    borders_linewidth: float = 0.6
    gridline_alpha: float = 0.3
    show_gridlines: bool = True


@dataclass(frozen=True)
class ESoHQueryConfig:
    """Defaults for E-SOH station observation queries."""

    base_url: str = "https://observations.meteogate.eu"
    collection: str = "observations"
    endpoint: str = "area"
    bbox: tuple[float, float, float, float] = (-12.0, 34.0, 32.0, 72.0)
    lookback_minutes: int = 30
    timeout_seconds: float = 30.0
    params: dict[str, str] = field(default_factory=dict)
