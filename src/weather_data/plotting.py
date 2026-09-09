"""Source-independent Cartopy plotting functions.

Readers never import this module. This keeps future satellite products on the
same plotting layer without coupling satellite file/API details to the map code.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Mapping, Sequence

import cartopy.crs as ccrs
import cartopy.feature as cfeature
import matplotlib.pyplot as plt
import matplotlib.colors as colors
import numpy as np

from .config import MapConfig
from .models import RasterField


def add_map_features(ax, config: MapConfig = MapConfig()) -> None:
    ax.add_feature(cfeature.COASTLINE, linewidth=config.coastlines_linewidth)
    ax.add_feature(cfeature.BORDERS, linestyle=":", linewidth=config.borders_linewidth)
    if config.show_gridlines:
        gl = ax.gridlines(draw_labels=True, linestyle="--", alpha=config.gridline_alpha, color="black")
        gl.top_labels = False
        gl.right_labels = False


def _raster_style(quantity: str):
    if quantity in {"DBZH", "DBZ"}:
        # bounds = [-10, 0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70]
        bounds = [0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70]
        cmap = plt.get_cmap("turbo").copy()
        cmap.set_under(color="purple", alpha=0.5)
        cmap.set_bad(color="none")
        return colors.BoundaryNorm(bounds, ncolors=cmap.N), cmap
    if quantity in {"RATE", "precipitation"}:
        bounds = [0.01, 0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 20.0, 50.0, 100.0]
        cmap = plt.get_cmap("YlGnBu").copy()
        cmap.set_under(color="white")
        cmap.set_bad(color="dimgrey", alpha=0.5)
        return colors.BoundaryNorm(bounds, ncolors=cmap.N, extend="max"), cmap
    bounds = np.linspace(0, 100, 10)
    cmap = plt.get_cmap("Blues").copy()
    cmap.set_bad(color="none")
    return colors.BoundaryNorm(bounds, ncolors=cmap.N), cmap


def plot_raster(
    field: RasterField,
    output_path: str | Path,
    *,
    title: str,
    config: MapConfig = MapConfig(),
) -> Path:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    norm, cmap = _raster_style(field.quantity)

    fig = plt.figure(figsize=config.figsize)
    ax = fig.add_subplot(1, 1, 1, projection=field.crs)
    #mesh = ax.pcolormesh(field.x, field.y, field.data, cmap=cmap, norm=norm, shading="auto")
    mesh = ax.pcolormesh(
        field.x,
        field.y,
        field.data,
        cmap=cmap,
        norm=norm,
        shading="auto",
        transform=field.crs,
    )

    ax.set_xlim(np.nanmin(field.x), np.nanmax(field.x))
    ax.set_ylim(np.nanmin(field.y), np.nanmax(field.y))
    add_map_features(ax, config)
    extend = "max" if field.quantity == "RATE" else "neither"
    cbar = fig.colorbar(mesh, ax=ax, pad=0.02, shrink=0.85, extend=extend)
    cbar.set_label(f"{field.quantity} ({field.unit})")
    ax.set_title(title)
    fig.savefig(output, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return output


#def plot_raster_comparison(
 #   fields: Sequence[RasterField],
  #  titles: Sequence[str],
   # output_path: str | Path,
   # *,
   # suptitle: str,
   # config: MapConfig = MapConfig(figsize=(20.0, 8.0)),
#) -> Path:
 #   if len(fields) != len(titles):
  #      raise ValueError("fields and titles must have the same length")
   # output = Path(output_path)
   # output.parent.mkdir(parents=True, exist_ok=True)
   # fig = plt.figure(figsize=config.figsize)
   # gs = fig.add_gridspec(1, len(fields), wspace=0.02)
   # for i, (field, title) in enumerate(zip(fields, titles)):
   #     print(f"\nFIELD {i}: {title}")
   #     print("shape:", field.data.shape)
   #     print("x:", field.x[0], field.x[-1], "range:", np.ptp(field.x))
   #     print("y:", field.y[0], field.y[-1], "range:", np.ptp(field.y))
   #     print("crs:", field.crs)

    #    norm, cmap = _raster_style(field.quantity)
    #    ax = fig.add_subplot(gs[0, i], projection=field.crs)
    #    mesh = ax.pcolormesh(field.x, field.y, field.data, cmap=cmap, norm=norm, shading="auto")
    #    add_map_features(ax, config)
    #    fig.colorbar(mesh, ax=ax, label=field.unit, pad=0.02, shrink=0.8, extend="min")
    #    ax.set_title(title)
    #fig.suptitle(suptitle, fontsize=16)
    #fig.savefig(output, dpi=200, bbox_inches="tight")
    #plt.close(fig)
    #return output

def plot_raster_comparison(
    fields,
    titles,
    output_path,
    *,
    suptitle="Raster comparison",
    config=MapConfig(figsize=(16.0, 7.5)),
):
    from pathlib import Path
    import numpy as np
    import matplotlib.pyplot as plt

    if len(fields) != len(titles):
        raise ValueError("fields and titles must have the same length")

    if not fields:
        raise ValueError("fields must not be empty")

    first_quantity = fields[0].quantity
    first_unit = fields[0].unit

    for field in fields[1:]:
        if field.quantity != first_quantity:
            raise ValueError(
                "All fields must have the same quantity for comparison plots"
            )
        if field.unit != first_unit:
            raise ValueError(
                "All fields must have the same unit for comparison plots"
            )

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    norm, cmap = _raster_style(first_quantity)

    fig = plt.figure(figsize=config.figsize)
    gs = fig.add_gridspec(
        1,
        3,
        width_ratios=[1, 1, 0.045],
        wspace=0.08,
    )

    meshes = []

    for i, (field, title) in enumerate(zip(fields, titles)):
        ax = fig.add_subplot(gs[0, i], projection=field.crs)

        mesh = ax.pcolormesh(
            field.x,
            field.y,
            field.data,
            cmap=cmap,
            norm=norm,
            shading="auto",
            transform=field.crs,
        )

        ax.set_xlim(np.nanmin(field.x), np.nanmax(field.x))
        ax.set_ylim(np.nanmin(field.y), np.nanmax(field.y))

        add_map_features(ax, config)
        ax.set_title(title, fontsize=12, pad=8)

        meshes.append(mesh)

    cax = fig.add_subplot(gs[0, 2])
    cbar = fig.colorbar(meshes[-1], cax=cax, extend="max")
    cbar.set_label(first_unit, fontsize=11)

    fig.suptitle(suptitle, fontsize=18, y=0.98)

    fig.savefig(
        output,
        dpi=200,
        bbox_inches="tight",
    )
    plt.close(fig)

    return output

def plot_station_observations(
    records: Iterable[Mapping],
    output_path: str | Path,
    *,
    title: str,
    value_label: str,
    projection: ccrs.CRS | None = None,
    cmap: str = "viridis",
    vmin: float | None = None,
    vmax: float | None = None,
    wind_speed_records: Iterable[Mapping] | None = None,
    wind_direction_records: Iterable[Mapping] | None = None,
) -> Path:
    """Plot station values as point observations; optionally add wind arrows.

    Records need latitude, longitude, and value fields. Wind direction follows
    the meteorological convention: direction *from* which the wind originates.
    """

    #rows = [dict(r) for r in records if r.get("latitude") is not None and r.get("longitude") is not None and r.get("value") is not None]
    #rows = [ dict(r) for r in records if r.get("latitude") is not None and r.get("longitude") is not None and r.get("value") is not None and np.isfinite(float(r["value"])) and float(r["value"]) != -32767.0]
    rows = [dict(r) for r in records if r.get("latitude") is not None and r.get("longitude") is not None and r.get("value") is not None ]

    # E-SOH utiliza al menos -32767 y -32766 como valores inválidos.
    rows = [ r for r in rows if np.isfinite(float(r["value"])) and float(r["value"]) > -1000]
    if not rows:
        raise ValueError("No plottable station records found.")

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    projection = projection or ccrs.PlateCarree()
    transform = ccrs.PlateCarree()

    fig = plt.figure(figsize=(12, 8))
    ax = fig.add_subplot(1, 1, 1, projection=projection)
    ax.set_extent(
        [-12.0, 32.0, 34.0, 72.0], crs=ccrs.PlateCarree(), )
    # values = np.asarray([float(r["value"]) for r in rows])
    values = np.asarray([float(r["value"]) for r in rows],
    dtype=float, )
    print( "Plotting:", len(rows),"records | min:", np.nanmin(values), "| max:", np.nanmax(values),)
    # Precipitation uses the same classification as the raster plots.
    is_precipitation = value_label.lower() in {"precipitation", "precipitation_amount", "precipitation_rate", "rate"}

    if is_precipitation:
        bounds = [0.01, 0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 20.0, 50.0, 100.0]
        cmap_obj = plt.get_cmap("YlGnBu").copy()
        cmap_obj.set_under(color="white")
        cmap_obj.set_bad(color="dimgrey", alpha=0.7)

        norm = colors.BoundaryNorm(bounds, ncolors=cmap_obj.N, extend="max")

        normal = np.ma.masked_where((values > 100) | np.isnan(values), values)
        scatter = ax.scatter(
            [r["longitude"] for r in rows],
            [r["latitude"] for r in rows],
            c=normal,
            cmap=cmap_obj,
            norm=norm,
            s=35,
            edgecolors="lightgrey",  # Soft grey outline around each point
            linewidths=0.6,         # Thin stroke so white centers stay distinct
            transform=transform,
            zorder=3,
        )

        # Extreme precipitation: red + actual value.
        extreme = np.isfinite(values) & (values > 100)
        if np.any(extreme):
            extreme_rows = [r for r, flag in zip(rows, extreme) if flag]
            extreme_values = values[extreme]

            ax.scatter(
                [r["longitude"] for r in extreme_rows],
                [r["latitude"] for r in extreme_rows],
                c="red",
                s=15,
                transform=transform,
                zorder=4,
                alpha=0.4
            )

            for r, value in zip(extreme_rows, extreme_values):
                ax.annotate(
                    f"{value:g}",
                    (r["longitude"], r["latitude"]),
                    xytext=(5, 5),
                    textcoords="offset points",
                    fontsize=8,
                    color="red",
                    transform=transform,
                    zorder=5,
                )
    else:
        scatter = ax.scatter(
            [r["longitude"] for r in rows],
            [r["latitude"] for r in rows],
            c=values,
            cmap="coolwarm",
            vmin=-30,
            vmax=40,
            s=20,
            edgecolors="black",
            linewidths=0.15,
            transform=transform,
            zorder=3,
        )
    add_map_features(ax)
    fig.colorbar(scatter, ax=ax, label=value_label, pad=0.02, shrink=0.85)

    if wind_speed_records is not None and wind_direction_records is not None:
        speeds = {(r.get("station_id") or r.get("location_id") or r.get("station_name"), r.get("datetime")): r for r in wind_speed_records}
        dirs = {(r.get("station_id") or r.get("location_id") or r.get("station_name"), r.get("datetime")): r for r in wind_direction_records}
        u, v, qx, qy = [], [], [], []
        for key, speed_record in speeds.items():
            direction_record = dirs.get(key)
            if not direction_record or speed_record.get("value") is None or direction_record.get("value") is None:
                continue
            lon = speed_record.get("longitude", direction_record.get("longitude"))
            lat = speed_record.get("latitude", direction_record.get("latitude"))
            if lon is None or lat is None:
                continue
            import math
            speed = float(speed_record["value"])
            direction = math.radians(float(direction_record["value"]))
            # Wind direction is FROM; arrows point TOWARD.
            u.append(-speed * math.sin(direction))
            v.append(-speed * math.cos(direction))
            qx.append(lon)
            qy.append(lat)
        if qx:
            ax.quiver(qx, qy, u, v, transform=transform, scale=300, width=0.002, zorder=4)

    ax.set_title(title)
    #fig.savefig(output, dpi=200, bbox_inches="tight")
    fig.savefig(output, dpi=200)
    plt.close(fig)
    return output
