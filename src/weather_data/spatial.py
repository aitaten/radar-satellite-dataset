"""Projection and geographic-coordinate helpers shared by raster products."""

from __future__ import annotations

import warnings

import cartopy.crs as ccrs
import numpy as np
from pyproj import CRS, Transformer


warnings.filterwarnings("ignore", category=UserWarning, module="pyproj")


def projdef_to_cartopy(projdef: str) -> ccrs.Projection:
    """Convert a PROJ string to a suitable Cartopy projection."""

    crs_pyproj = CRS.from_proj4(projdef)
    proj_dict = crs_pyproj.to_dict()
    proj_name = proj_dict.get("proj", "").lower()

    globe_kwargs = {}
    if "ellps" in proj_dict:
        globe_kwargs["ellipse"] = proj_dict["ellps"]
    elif "a" in proj_dict and "b" in proj_dict:
        globe_kwargs["semimajor_axis"] = proj_dict["a"]
        globe_kwargs["semiminor_axis"] = proj_dict["b"]
    elif "a" in proj_dict:
        globe_kwargs["semimajor_axis"] = proj_dict["a"]

    globe = ccrs.Globe(**globe_kwargs) if globe_kwargs else None

    if proj_name == "laea":
        return ccrs.LambertAzimuthalEqualArea(
            central_latitude=proj_dict.get("lat_0", 0.0),
            central_longitude=proj_dict.get("lon_0", 0.0),
            false_easting=proj_dict.get("x_0", 0.0),
            false_northing=proj_dict.get("y_0", 0.0),
            globe=globe,
        )
    if proj_name in {"stere", "sterea"}:
        return ccrs.Stereographic(
            central_latitude=proj_dict.get("lat_0", 0.0),
            central_longitude=proj_dict.get("lon_0", 0.0),
            false_easting=proj_dict.get("x_0", 0.0),
            false_northing=proj_dict.get("y_0", 0.0),
            true_scale_latitude=proj_dict.get("lat_ts"),
            globe=globe,
        )
    if proj_name == "merc":
        return ccrs.Mercator(
            central_longitude=proj_dict.get("lon_0", 0.0),
            false_easting=proj_dict.get("x_0", 0.0),
            false_northing=proj_dict.get("y_0", 0.0),
            globe=globe,
        )
    return ccrs.PlateCarree()


def grid_coordinates_from_corners(
    projdef: str,
    xsize: int,
    ysize: int,
    ll_lon: float,
    ll_lat: float,
    lr_lon: float,
    lr_lat: float,
    ul_lon: float,
    ul_lat: float,
) -> tuple[ccrs.Projection, np.ndarray, np.ndarray]:
    """Create native projected x/y coordinates from three geographic corners."""

    native = CRS.from_proj4(projdef)
    geo = CRS.from_epsg(4326)
    forward = Transformer.from_crs(geo, native, always_xy=True)

    x_ll, y_ll = forward.transform(ll_lon, ll_lat)
    x_lr, _ = forward.transform(lr_lon, lr_lat)
    _, y_ul = forward.transform(ul_lon, ul_lat)

    x = np.linspace(x_ll, x_lr, int(xsize))
    y = np.linspace(y_ll, y_ul, int(ysize))
    return projdef_to_cartopy(projdef), x, y
