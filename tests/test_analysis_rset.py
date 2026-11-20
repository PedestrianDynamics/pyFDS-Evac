"""The RSET map on PedPy's grid, and its alignment with the ASET grid (#210).

These tests fail when PedPy changes its edges, its orientation or its bin
rule, which is why they probe PedPy instead of remembering its shapes.
"""

import logging

import numpy as np
import pandas as pd
import pytest
from shapely import box

pedpy = pytest.importorskip("pedpy", minversion="1.5.1")

from pyfds_evac.analysis import (  # noqa: E402
    AsetMap,
    CellState,
    Grid,
    PointCrossing,
    aset_map,
    cell_membership,
    diff_map,
    grid_from_walkable,
    measures,
    rset_map,
)

CELL = 0.6
GEOMETRIES = {
    "wide": box(0, 0, 30, 10),
    "square": box(0, 0, 10, 10),
    "short_of_a_cell": box(0, 0, 6, 4),  # 4 / 0.6 is not whole
    "negative_origin": box(-3.3, -2.1, 3.1, 2.4),
}


def _trajectory(rows, fps=1.0):
    frame = pd.DataFrame(rows, columns=["id", "frame", "x", "y"])
    return pedpy.TrajectoryData(data=frame, frame_rate=fps)


def _pedpy_shape(polygon):
    """PedPy's own map shape, probed with one point."""
    x0, y0, _, _ = polygon.bounds
    result = pedpy.compute_rset_map(
        traj_data=_trajectory([(1, 0, x0, y0)]),
        walkable_area=pedpy.WalkableArea(polygon),
        grid_size=CELL,
        method=pedpy.RsetMethod.MAX,
    )
    return result.shape


@pytest.fixture(params=sorted(GEOMETRIES))
def room(request):
    polygon = GEOMETRIES[request.param]
    return polygon, grid_from_walkable(polygon, CELL)


def test_grid_shape_is_the_shape_pedpy_returns(room):
    polygon, grid = room
    assert grid.shape == _pedpy_shape(polygon)
    assert len(grid.x_edges) == grid.shape[1] + 1
    assert len(grid.y_edges) == grid.shape[0] + 1


def test_floor_area_is_the_room_inside_the_cells(room):
    polygon, grid = room
    assert grid.area.sum() == pytest.approx(polygon.area)
    assert grid.area.max() == pytest.approx(CELL**2)


def test_clipped_edge_cells_and_the_extra_column_have_their_true_area():
    wide = grid_from_walkable(GEOMETRIES["wide"], CELL)
    assert wide.area[0, 0] == pytest.approx(CELL * 0.4)  # top row, y 9.6..10.0
    assert wide.area[-1, 0] == pytest.approx(CELL**2)
    if wide.shape[1] == 51:  # PedPy's float arange overshoots the room by a column
        assert (wide.area[:, -1] == 0.0).all()


def _cell_of(grid, x, y):
    _, rows, cols = cell_membership(grid, np.array([x]), np.array([y]))
    assert len(rows) == 1, (x, y)
    return int(rows[0]), int(cols[0])


def test_agent_at_each_corner_lands_in_the_cell_the_grid_names(room):
    """PedPy and the grid agree on the cell, with row 0 at the largest y."""
    polygon, grid = room
    x0, y0, x1, y1 = polygon.bounds
    area = pedpy.WalkableArea(polygon)
    for x, y in [
        (x0 + 0.1, y0 + 0.1),
        (x1 - 0.1, y0 + 0.1),
        (x0 + 0.1, y1 - 0.1),
        (x1 - 0.1, y1 - 0.1),
    ]:
        result = pedpy.compute_rset_map(
            traj_data=_trajectory([(1, 7, x, y)]),
            walkable_area=area,
            grid_size=CELL,
            method=pedpy.RsetMethod.MAX,
        )
        assert np.argwhere(~np.isnan(result)).tolist() == [list(_cell_of(grid, x, y))]
    ny, _ = grid.shape
    assert _cell_of(grid, x0 + 0.1, y0 + 0.1) == (ny - 1, 0)  # low y is the last row
    assert _cell_of(grid, x0 + 0.1, y1 - 0.1)[0] == 0  # high y is row 0


def test_aset_at_a_cell_is_the_value_of_the_point_there_and_rset_nan_coincides(room):
    polygon, grid = room
    xc, yc = grid.centres()
    values = np.arange(xc.size, dtype=float).reshape(xc.shape)
    crossing = PointCrossing("c", xc.ravel(), yc.ravel(), values.ravel(), 1000.0)
    aset = aset_map(grid, [crossing])
    inside = grid.area > 0
    assert (aset.time_s[inside] == values[inside]).all()
    # an agent standing at the centre of the cell (row, col)
    row, col = np.argwhere(inside)[len(np.argwhere(inside)) // 2]
    rset = rset_map(
        _trajectory([(1, 5, xc[row, col], yc[row, col])]),
        polygon,
        grid,
        exit_times={1: 6.0},
    )
    assert np.argwhere(~np.isnan(rset.time_s)).tolist() == [[row, col]]
    assert rset.time_s[row, col] == 5.0
    assert aset.time_s[row, col] == values[row, col]


def test_known_negative_cell_end_to_end():
    """One agent stands in a cell for 20 s, ASET there is 12 s: DIFF -8."""
    polygon = box(0, 0, 1.2, 1.2)
    grid = grid_from_walkable(polygon, CELL)
    assert grid.shape == (2, 2)
    xc, yc = grid.centres()
    stand = [(1, f, xc[0, 0], yc[0, 0]) for f in range(21)]
    rows = stand + [(2, f, xc[1, 1], yc[1, 1]) for f in range(21)]
    traj = _trajectory(rows)
    rset = rset_map(traj, polygon, grid, exit_times={1: 21.0, 2: 21.0})
    assert not rset.censored.any()
    firsts = np.array([12.0, 30.0, np.inf, 30.0])  # cells (0,0) (0,1) (1,0) (1,1)
    aset = aset_map(
        grid,
        [PointCrossing("c", xc.ravel(), yc.ravel(), firsts, 100.0)],
    )
    diff = diff_map(aset, rset, grid)
    assert diff.diff_s[0, 0] == -8.0 and diff.state[0, 0] == CellState.FAIL
    assert diff.diff_s[1, 1] == 10.0 and diff.state[1, 1] == CellState.PASS
    assert diff.state[0, 1] == CellState.ASET_ONLY
    m = measures(diff)
    assert m.c_m2s == pytest.approx(-8.0 * CELL**2)
    assert m.fail_area_m2 == pytest.approx(CELL**2)


def test_agent_left_in_place_censors_its_cell_and_the_one_who_left_does_not():
    polygon = box(0, 0, 1.2, 1.2)
    grid = grid_from_walkable(polygon, CELL)
    xc, yc = grid.centres()
    rows = [(1, f, xc[0, 0], yc[0, 0]) for f in range(21)]  # left at 21 s
    rows += [(2, f, xc[1, 1], yc[1, 1]) for f in range(21)]  # still inside
    rset = rset_map(_trajectory(rows), polygon, grid, exit_times={1: 21.0})
    assert rset.censored.tolist() == [[False, False], [False, True]]
    assert rset.horizon_s == 20.0
    aset = AsetMap(np.array([[50.0, 50.0], [50.0, 25.0]]), 100.0)
    diff = diff_map(aset, rset, grid)
    assert diff.state[1, 1] == CellState.RSET_CENSORED
    assert diff.bound_s[1, 1] == 25.0 - 20.0  # DIFF < 5 s: not a pass
    assert diff.state[0, 0] == CellState.PASS
    both = AsetMap(np.array([[50.0, 50.0], [50.0, np.inf]]), 100.0)
    assert diff_map(both, rset, grid).state[1, 1] == CellState.UNDETERMINED


def test_a_later_passer_by_does_not_censor_the_cell():
    """The cell holds an agent who left, then a later visit sets its RSET."""
    polygon = box(0, 0, 1.2, 1.2)
    grid = grid_from_walkable(polygon, CELL)
    xc, yc = grid.centres()
    rows = [(1, f, xc[0, 0], yc[0, 0]) for f in range(5)]
    rows += [(2, f, xc[0, 0], yc[0, 0]) for f in range(10, 15)]
    rset = rset_map(_trajectory(rows), polygon, grid, exit_times={1: 5.0, 2: 15.0})
    assert not rset.censored.any() and rset.time_s[0, 0] == 14.0


def test_without_exit_times_the_cells_of_the_last_frame_are_censored_with_a_warning(
    caplog,
):
    polygon = box(0, 0, 1.2, 1.2)
    grid = grid_from_walkable(polygon, CELL)
    xc, yc = grid.centres()
    rows = [(1, f, xc[0, 0], yc[0, 0]) for f in range(5)]
    rows += [(2, f, xc[1, 1], yc[1, 1]) for f in range(21)]
    with caplog.at_level(logging.WARNING, logger="pyfds_evac.analysis.rset"):
        rset = rset_map(_trajectory(rows), polygon, grid)
    assert "without exit_times" in caplog.text
    assert rset.censored.tolist() == [[False, False], [False, True]]


def test_a_grid_for_another_cell_size_is_refused():
    polygon = box(0, 0, 6, 4)
    other = grid_from_walkable(polygon, 1.0)
    wrong = Grid(CELL, other.x_edges, other.y_edges, other.area)
    with pytest.raises(ValueError, match="differs from the grid"):
        rset_map(_trajectory([(1, 0, 1.0, 1.0)]), polygon, wrong)
