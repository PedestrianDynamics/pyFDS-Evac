"""plot_maps draws ASET, RSET and DIFF without pyplot (#1002)."""

import numpy as np
from matplotlib.collections import PatchCollection
from shapely import box

from pyfds_evac.analysis import (
    Grid,
    PointCrossing,
    RsetMap,
    aset_map,
    diff_map,
    plot_maps,
)

INF = np.inf
NAN = np.nan


def _maps():
    grid = Grid(1.0, np.arange(4.0), np.arange(3.0), np.ones((2, 3)))
    x = np.array([0.5, 1.5, 2.5, 0.5, 1.5, 2.5])
    y = np.array([1.5, 1.5, 1.5, 0.5, 0.5, 0.5])
    smoke = PointCrossing(
        "K 0.3", x, y, np.array([10.0, 30.0, INF, 20.0, 5.0, 40.0]), 60.0
    )
    aset = aset_map(grid, [smoke])
    rset = RsetMap(
        np.array([[20.0, 10.0, 15.0], [NAN, 3.0, 50.0]]),
        np.zeros((2, 3), bool),
        55.0,
    )
    return grid, aset, rset, diff_map(aset, rset, grid)


def test_four_panels_with_the_failing_cells_hatched():
    grid, aset, rset, diff = _maps()
    fig = plot_maps(grid, aset, rset, diff, walkable=box(0, 0, 3, 2))
    axes = _panels(fig)
    assert len(axes) == 4
    hatched = [c for c in axes[2].collections if isinstance(c, PatchCollection)]
    assert len(hatched) == 1
    assert len(hatched[0].get_paths()) == int((diff.diff_s < 0).sum()) == 2
    assert axes[3].get_legend() is not None
    fig.savefig(_buffer(), format="png")


def test_three_panels_without_the_deciding_map():
    grid, aset, rset, diff = _maps()
    fig = plot_maps(grid, aset, rset, diff, deciding=False)
    assert len(_panels(fig)) == 3


def test_image_rows_follow_the_grid_orientation():
    """Row 0 is the largest y, so imshow draws it at the top (origin upper)."""
    grid, aset, rset, diff = _maps()
    fig = plot_maps(grid, aset, rset, diff, deciding=False)
    image = _panels(fig)[0].get_images()[0]
    assert image.origin == "upper"
    assert tuple(image.get_extent()) == (0.0, 3.0, 0.0, 2.0)


def test_no_crossing_leaves_the_deciding_panel_empty():
    grid = Grid(1.0, np.arange(2.0), np.arange(2.0), np.ones((1, 1)))
    crossing = PointCrossing(
        "T 45", np.array([0.5]), np.array([0.5]), np.array([INF]), 9.0
    )
    aset = aset_map(grid, [crossing])
    rset = RsetMap(np.array([[3.0]]), np.zeros((1, 1), bool), 9.0)
    fig = plot_maps(grid, aset, rset, diff_map(aset, rset, grid))
    assert "none crossed" in _panels(fig)[-1].get_title(loc="left")


def _panels(fig):
    return [ax for ax in fig.axes if ax.get_label() != "<colorbar>"]


def _buffer():
    import io

    return io.BytesIO()
