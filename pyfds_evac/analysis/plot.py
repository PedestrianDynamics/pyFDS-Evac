"""Draw ASET, RSET and DIFF maps with matplotlib.

matplotlib is imported inside ``plot_maps``, so importing
``pyfds_evac.analysis`` stays cheap. The figure is a ``matplotlib.figure.Figure``
without pyplot, so it needs no display; save it with ``fig.savefig``.
"""

from __future__ import annotations

import numpy as np

from .aset_rset import AsetMap, CellState, DiffMap, Grid, RsetMap

_GREY = "#e3e3e3"
_FAIL_EDGE = "black"


def _extent(grid: Grid) -> tuple[float, float, float, float]:
    """imshow extent of a map with row 0 at the largest y (origin upper)."""
    return (grid.x_edges[0], grid.x_edges[-1], grid.y_edges[0], grid.y_edges[-1])


def _outline(walkable):
    """Exterior and interior rings of a Shapely polygon or a pedpy WalkableArea."""
    polygon = getattr(walkable, "polygon", walkable)
    return [polygon.exterior, *polygon.interiors]


def _mask_image(ax, grid: Grid, mask: np.ndarray, color: str, zorder: float) -> None:
    from matplotlib.colors import ListedColormap

    shown = np.ma.masked_where(~mask, np.ones(mask.shape))
    ax.imshow(
        shown,
        extent=_extent(grid),
        cmap=ListedColormap([color]),
        interpolation="nearest",
        zorder=zorder,
    )


def _fail_cells(ax, grid: Grid, fail: np.ndarray) -> None:
    """Hatch and outline each failing cell."""
    from matplotlib.collections import PatchCollection
    from matplotlib.patches import Rectangle

    ny = grid.shape[0]
    cells = [
        Rectangle(
            (float(grid.x_edges[c]), float(grid.y_edges[ny - 1 - r])),
            grid.cell_m,
            grid.cell_m,
        )
        for r, c in np.argwhere(fail)
    ]
    if cells:
        ax.add_collection(
            PatchCollection(
                cells,
                facecolor="none",
                edgecolor=_FAIL_EDGE,
                hatch="////",
                linewidth=0.6,
                zorder=4,
            )
        )


def _colorbar(fig, ax, image) -> None:
    """A colorbar as tall as the map, whatever the room's aspect."""
    bar = fig.colorbar(image, cax=ax.inset_axes((1.02, 0.0, 0.03, 1.0)))
    bar.set_label("s", color="dimgrey")
    bar.ax.tick_params(length=0, labelcolor="dimgrey")


def _time_panel(fig, ax, grid, values, vmax, title):
    image = ax.imshow(
        np.ma.masked_invalid(values),
        extent=_extent(grid),
        cmap="cividis",
        vmin=0.0,
        vmax=vmax,
        interpolation="nearest",
        zorder=2,
    )
    _colorbar(fig, ax, image)
    ax.set_title(title, loc="left", color="dimgrey")


def _diff_panel(fig, ax, grid, diff: DiffMap):
    from matplotlib.colors import TwoSlopeNorm

    finite = diff.diff_s[np.isfinite(diff.diff_s)]
    low = float(min(finite.min(), -1.0)) if finite.size else -1.0
    high = float(max(finite.max(), 1.0)) if finite.size else 1.0
    image = ax.imshow(
        np.ma.masked_invalid(diff.diff_s),
        extent=_extent(grid),
        cmap="RdBu",
        norm=TwoSlopeNorm(vmin=low, vcenter=0.0, vmax=high),
        interpolation="nearest",
        zorder=2,
    )
    _colorbar(fig, ax, image)
    _fail_cells(ax, grid, diff.state == CellState.FAIL)
    bounded = np.isin(
        diff.state,
        (CellState.ASET_OPEN, CellState.RSET_CENSORED, CellState.UNDETERMINED),
    )
    _mask_image(ax, grid, bounded, "#b8a3cf", zorder=1.5)
    ax.set_title("DIFF = ASET − RSET (hatched: fail)", loc="left", color="dimgrey")


def _deciding_panel(ax, grid, aset: AsetMap):
    from matplotlib.colors import ListedColormap
    from matplotlib.patches import Patch

    names = aset.deciding()
    labels = sorted({n for n in names.ravel() if n})
    if not labels:
        ax.set_title("deciding criterion: none crossed", loc="left", color="dimgrey")
        return
    codes = np.full(names.shape, np.nan)
    for i, label in enumerate(labels):
        codes[names == label] = i
    colours = [f"C{i % 10}" for i in range(len(labels))]
    ax.imshow(
        np.ma.masked_invalid(codes),
        extent=_extent(grid),
        cmap=ListedColormap(colours),
        vmin=-0.5,
        vmax=len(labels) - 0.5,
        interpolation="nearest",
        zorder=2,
    )
    handles = [Patch(color=c, label=n) for c, n in zip(colours, labels, strict=True)]
    ax.legend(handles=handles, loc="upper left", fontsize=8, framealpha=0.85)
    ax.set_title("criterion that sets ASET", loc="left", color="dimgrey")


def plot_maps(
    grid: Grid,
    aset: AsetMap,
    rset: RsetMap,
    diff: DiffMap,
    *,
    walkable=None,
    deciding: bool = True,
    figsize: tuple[float, float] | None = None,
):
    """Return a figure with the ASET, RSET and DIFF maps, all in seconds.

    Cells without data are white. In the RSET and DIFF panels cells that had
    fire data but nobody visited are grey. Failing cells (DIFF < 0) are
    hatched; open and censored cells, whose DIFF is only a bound, are lilac.
    With *deciding* a fourth panel shows ``AsetMap.deciding``. *walkable*, a
    Shapely polygon or a ``pedpy.WalkableArea``, draws the floor outline.
    """
    from matplotlib.figure import Figure

    panels = 4 if deciding else 3
    rows, cols = (2, 2) if deciding else (1, 3)
    fig = Figure(
        figsize=figsize or ((12, 7) if deciding else (14, 3.8)), layout="constrained"
    )
    axes = list(fig.subplots(rows, cols, squeeze=False).ravel())[:panels]
    times = np.concatenate([aset.time_s.ravel(), rset.time_s.ravel()])
    finite = times[np.isfinite(times)]
    vmax = float(finite.max()) if finite.size else 1.0
    unvisited = diff.state == CellState.ASET_ONLY

    _time_panel(fig, axes[0], grid, aset.time_s, vmax, "ASET: earliest criterion")
    _time_panel(fig, axes[1], grid, rset.time_s, vmax, "RSET: last time occupied")
    _mask_image(axes[1], grid, unvisited, _GREY, zorder=1.5)
    _diff_panel(fig, axes[2], grid, diff)
    _mask_image(axes[2], grid, unvisited, _GREY, zorder=1.5)
    if deciding:
        _deciding_panel(axes[3], grid, aset)
    for ax in axes:
        _style(ax, grid, walkable)
    return fig


def _style(ax, grid: Grid, walkable) -> None:
    ax.set_xlim(grid.x_edges[0], grid.x_edges[-1])
    ax.set_ylim(grid.y_edges[0], grid.y_edges[-1])
    ax.set_aspect("equal")
    ax.set_xlabel("x [m]", color="dimgrey")
    ax.set_ylabel("y [m]", color="dimgrey")
    ax.tick_params(length=0, labelcolor="dimgrey")
    if walkable is None:
        return
    for ring in _outline(walkable):
        xs, ys = ring.xy
        ax.plot(xs, ys, color="dimgrey", linewidth=0.9, zorder=5)
