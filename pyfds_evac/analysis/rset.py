"""The RSET map from a JuPedSim trajectory: the PedPy adapter.

This is the only module that calls PedPy's ``compute_rset_map``. PedPy is
imported inside the functions, so importing ``pyfds_evac.analysis`` stays
cheap. Needs ``pedpy>=1.5.1`` (the first release with ``compute_rset_map``).

PedPy bins the trajectory on edges ``arange(min, max + cell, cell)`` from the
smallest x and y, flips the rows so that row 0 is the largest y, and drops
points outside. ``grid_from_walkable`` takes the map shape from PedPy's own
output instead of rebuilding it, and ``tests/test_analysis_rset.py`` pins the
alignment, so a PedPy that changes its grid fails there first.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping

import numpy as np

from .aset_rset import Grid, RsetMap

_logger = logging.getLogger(__name__)

_PEDPY_NEEDED = (
    "needs pedpy>=1.5.1 (compute_rset_map); upgrade with: pip install -U pedpy"
)


def _pedpy():
    import pedpy

    if not hasattr(pedpy, "compute_rset_map"):
        raise ImportError(f"RSET maps {_PEDPY_NEEDED}; installed {pedpy.__version__}")
    return pedpy


def _walkable(walkable):
    """A ``pedpy.WalkableArea`` from a WalkableArea or a Shapely polygon."""
    pedpy = _pedpy()
    if isinstance(walkable, pedpy.WalkableArea):
        return walkable
    return pedpy.WalkableArea(walkable)


def load_trajectory(sqlite_file):
    """Trajectory and walkable area of a JuPedSim SQLite file, via PedPy."""
    pedpy = _pedpy()
    return (
        pedpy.load_trajectory_from_jupedsim_sqlite(trajectory_file=sqlite_file),
        pedpy.load_walkable_area_from_jupedsim_sqlite(trajectory_file=sqlite_file),
    )


def _single_point(trajectory_data_cls, x: float, y: float):
    import pandas as pd

    frame = pd.DataFrame({"id": [1], "frame": [0], "x": [x], "y": [y]})
    return trajectory_data_cls(data=frame, frame_rate=1.0)


def grid_from_walkable(walkable, cell_m: float) -> Grid:
    """The map grid PedPy uses for *walkable*, with the floor area per cell.

    The shape comes from a probe of ``compute_rset_map``; edges are
    ``min + k * cell`` from the smallest x and y (PedPy's ``arange`` can
    reach one column past the room, which then has zero floor area). Row 0
    is the largest y.
    """
    import shapely

    pedpy = _pedpy()
    area = _walkable(walkable)
    min_x, min_y, _, _ = area.bounds
    probe = pedpy.compute_rset_map(
        traj_data=_single_point(pedpy.TrajectoryData, min_x, min_y),
        walkable_area=area,
        grid_size=cell_m,
        method=pedpy.RsetMethod.MAX,
    )
    ny, nx = probe.shape
    x_edges = min_x + cell_m * np.arange(nx + 1)
    y_edges = min_y + cell_m * np.arange(ny + 1)
    cells = shapely.box(
        x_edges[None, :-1],
        y_edges[::-1][1:, None],
        x_edges[None, 1:],
        y_edges[::-1][:-1, None],
    )
    floor = shapely.area(shapely.intersection(cells, area.polygon))
    return Grid(float(cell_m), x_edges, y_edges, np.asarray(floor, dtype=float))


def _bin_rows_cols(grid: Grid, x: np.ndarray, y: np.ndarray):
    """The cell of each point by PedPy's rule: half-open bins, last one closed.

    Returns ``(row, col, inside)`` with row 0 at the largest y.
    """
    ny, nx = grid.shape

    def axis(edges, v):
        k = np.searchsorted(edges, v, side="right") - 1
        k = np.where(v == edges[-1], len(edges) - 2, k)
        return k, (v >= edges[0]) & (v <= edges[-1])

    col, in_x = axis(grid.x_edges, x)
    bin_y, in_y = axis(grid.y_edges, y)
    return ny - 1 - bin_y, col, in_x & in_y


def rset_map(
    trajectory,
    walkable,
    grid: Grid,
    *,
    exit_times: Mapping[int, float] | None = None,
) -> RsetMap:
    """RSET per cell, the last time anyone is in it (PedPy, ``RsetMethod.MAX``).

    *exit_times* maps the agents that left to the time they left (the run's
    ``ScenarioResult.exit_times``). An agent in the trajectory with no exit
    time was still inside at the end of the run, so the cell of its last
    position is censored: its RSET is a lower bound. Without *exit_times*
    that cannot be told from the trajectory alone; the cells that hold the
    last frame of the run are censored instead, and a warning says so.
    """
    pedpy = _pedpy()
    area = _walkable(walkable)
    data = trajectory.data
    fps = float(trajectory.frame_rate)
    time = pedpy.compute_rset_map(
        traj_data=trajectory,
        walkable_area=area,
        grid_size=grid.cell_m,
        method=pedpy.RsetMethod.MAX,
    )
    if time.shape != grid.shape:
        raise ValueError(
            f"PedPy RSET map {time.shape} differs from the grid {grid.shape}; "
            "build the grid with grid_from_walkable on the same walkable area "
            "and cell size"
        )
    t_end = float(data["frame"].max()) / fps
    if exit_times is None:
        _logger.warning(
            "rset_map without exit_times: cells holding the last frame of the "
            "run are censored; pass ScenarioResult.exit_times to censor by agent"
        )
        stayed = data[data["frame"] == data["frame"].max()]
    else:
        last = data.loc[data.groupby("id")["frame"].idxmax()]
        stayed = last[~last["id"].isin(list(exit_times))]
    censored = _censored_cells(grid, time, stayed, fps)
    return RsetMap(time, censored, t_end)


def _censored_cells(grid: Grid, time: np.ndarray, stayed, fps: float) -> np.ndarray:
    """Cells whose RSET is the last frame of an agent that never left."""
    out = np.zeros(time.shape, dtype=bool)
    if stayed.empty:
        return out
    row, col, inside = _bin_rows_cols(
        grid, stayed["x"].to_numpy(dtype=float), stayed["y"].to_numpy(dtype=float)
    )
    t_last = stayed["frame"].to_numpy(dtype=float) / fps
    for r, c, t in zip(row[inside], col[inside], t_last[inside]):
        out[r, c] |= bool(time[r, c] >= t - 1e-9)
    return out
