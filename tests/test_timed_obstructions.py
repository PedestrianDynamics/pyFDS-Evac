"""Sign visibility follows the obstructions FDS creates or removes (#453).

fdsvismap 0.3.3 ignores SubObstruction.hide_times / show_times, so a door leaf
that FDS removes or creates blocked sight lines at every time. The adapter in
``fdsvismap_adapter`` and ``visibility._compute_by_period`` follows the toggles.

Expectations are geometric, not tuned: a cell is legible iff its sight line is
clear, and the sighting distance is the 30 m cap when it is clear and 0 when it
is concealed (the fixture smoke gives C/K >= 44 m along the test lines, above
the cap). No tolerances.

The two FDS 6.10.1 runs in ``tests/data`` are two 4 x 4 m rooms joined by a
wall with two 1.0 m doorways. In ``timed_obst`` leaf A is removed at 5 s
(sign A, y = 1.1) and leaf B is created at 5 s (sign B, y = 2.9); FDS writes
the toggle at 5.063 s, the end of the time step. In ``timed_hole`` doorway A is
a HOLE that opens at 5 s and doorway B is a static HOLE through a panel that
is removed at 5 s.
"""

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

pytest.importorskip("fdsreader")
pytest.importorskip("fdsvismap")

from fdsvismap import VisMap  # noqa: E402

from pyfds_evac.core.fdsvismap_adapter import (  # noqa: E402
    obstruction_periods,
    toggle_times,
)
from pyfds_evac.core.visibility import (  # noqa: E402
    VisibilityModel,
    _compute_by_period,
    _harvest,
    _make_meta,
)

DATA = Path(__file__).parent / "data"
CAP = 30.0
TIMES = range(11)
OPEN_FROM = 6  # first vismap point after the toggle at 5.06 s


def _sub(x, y, hide=(), show=(), z=(0.0, 2.2), mesh="M1"):
    return SimpleNamespace(
        extent={"x": x, "y": y, "z": z},
        hide_times=list(hide),
        show_times=list(show),
        mesh=SimpleNamespace(id=mesh),
    )


class _Obst(list):
    """An fdsreader Obstruction: iterable over its sub-obstructions, with an id."""

    def __init__(self, oid, subs):
        super().__init__(subs)
        self.id = oid


def _legible(model, node, t, viewer):
    sight = model.visibility_to_node(t, *viewer, node)
    legible = model.node_is_visible(t, *viewer, node)
    assert legible == (sight is not None), (node, t)
    assert sight in (None, CAP), (node, t, sight)
    return legible


@pytest.fixture(scope="module")
def obst_model(fds_read_only):
    signs = {
        "a": {"x": 6.1, "y": 1.1, "alpha": None, "c": 3},
        "b": {"x": 6.1, "y": 2.9, "alpha": None, "c": 3},
    }
    return VisibilityModel(
        fds_read_only(DATA / "timed_obst"),
        signs,
        time_step_s=1.0,
        slice_height_m=2.0,
    )


@pytest.fixture(scope="module")
def hole_model(fds_read_only):
    signs = {
        "a": {"x": 6.1, "y": 1.1, "alpha": None, "c": 3},
        "b": {"x": 6.1, "y": 2.9, "alpha": None, "c": 3},
    }
    return VisibilityModel(
        fds_read_only(DATA / "timed_hole"),
        signs,
        time_step_s=1.0,
        slice_height_m=2.0,
    )


# -- FDS fixtures -----------------------------------------------------------


def test_leaf_removed_and_leaf_created_follow_fds(obst_model):
    """Leaf A is gone from 5 s, leaf B stands from 5 s.

    Viewer A (2.1, 1.1) looks through doorway A at sign A, viewer B (2.1, 2.9)
    through doorway B at sign B; each sight line crosses only its own leaf.
    Before the fix every point is False for both.
    """
    for t in TIMES:
        after = t >= OPEN_FROM
        assert _legible(obst_model, "a", t, (2.1, 1.1)) is after, t
        assert _legible(obst_model, "b", t, (2.1, 2.9)) is (not after), t


def test_sight_distance_masks_belong_to_their_period(obst_model):
    """Metres are harvested with the concealment mask of the period itself.

    A mask of the wrong period would keep the 0 of leaf A (or the 30 m of
    leaf B) after the toggle.
    """
    vis = obst_model._vis
    a, b = 0, 1
    assert vis.visibility_to_wp(0.0, 2.1, 1.1, a) == 0.0
    assert vis.visibility_to_wp(0.0, 2.1, 2.9, b) == CAP
    assert vis.visibility_to_wp(6.0, 2.1, 1.1, a) == CAP
    assert vis.visibility_to_wp(6.0, 2.1, 2.9, b) == 0.0


def test_controlled_hole_and_hole_through_timed_panel(hole_model):
    """FDS resolves each HOLE into pieces; their own toggles are enough.

    A: the controlled HOLE opens at 5 s. B: a static HOLE cuts the timed panel,
    so the doorway is clear throughout, and the panel remnant hides the sign
    from a viewer off the doorway axis until it is removed.
    """
    for t in TIMES:
        after = t >= OPEN_FROM
        assert _legible(hole_model, "a", t, (2.1, 1.1)) is after, t
        assert _legible(hole_model, "b", t, (2.1, 2.9)) is True, t
        assert _legible(hole_model, "b", t, (1.8, 2.2)) is after, t


def test_switch_happens_at_the_nearest_vismap_point(obst_model):
    """Run-time queries snap to the nearest point: the door flips at 5.5 s.

    The FDS toggle (5.06 s) lies between the points 5 and 6 s. A query within
    half a step of 5 s sees the 5 s state, one beyond it the 6 s state.
    """
    viewer = (2.1, 1.1)
    assert _legible(obst_model, "a", 5.49, viewer) is False
    assert _legible(obst_model, "a", 5.51, viewer) is True


def test_cache_records_the_toggles_and_format_7(obst_model, fds_read_only, tmp_path):
    signs = {"a": {"x": 6.1, "y": 1.1, "alpha": None, "c": 3}}
    cache = tmp_path / "vis.npz"
    fds_dir = fds_read_only(DATA / "timed_obst")
    VisibilityModel(
        fds_dir, signs, cache_path=cache, time_step_s=1.0, slice_height_m=2.0
    )
    with np.load(cache, allow_pickle=False) as data:
        toggles = data["obstruction_toggles_s"]
    assert toggles.tolist() == pytest.approx([5.063348])
    assert _make_meta(str(fds_dir), signs, 1.0, 2.0)["format"] == 7


# -- time points and periods ------------------------------------------------


def test_time_points_map_to_periods_at_the_toggle():
    """A point belongs to the period of the last toggle at or before it."""
    leaf = _sub((0, 1), (0, 1), hide=[5.0])
    periods = obstruction_periods([[leaf]], 2.0, [0.0, 4.99, 5.0, 5.01, 9.0])
    assert [p.time_points for p in periods] == [(0.0, 4.99), (5.0, 5.01, 9.0)]
    assert [len(p.obstructions[0]) for p in periods] == [1, 0]


def test_half_step_snapping_uses_the_next_vismap_point():
    """A toggle at 5.06 s lands in the period of the 6 s point, not of 5 s."""
    leaf = _sub((0, 1), (0, 1), hide=[5.06])
    periods = obstruction_periods([[leaf]], 2.0, [float(t) for t in range(11)])
    assert periods[0].time_points == (0.0, 1.0, 2.0, 3.0, 4.0, 5.0)
    assert periods[1].time_points[0] == 6.0


# -- the state rule, without FDS --------------------------------------------


def _present_at(subs, time_points):
    periods = obstruction_periods([subs], 2.0, time_points)
    return {t: len(p.obstructions[0]) for p in periods for t in p.time_points}


def test_no_toggles_is_one_period_with_every_piece():
    subs = [_sub((0, 1), (0, 1)), _sub((1, 2), (0, 1))]
    periods = obstruction_periods([subs], 2.0, [0.0, 1.0, 2.0])
    assert len(periods) == 1
    assert periods[0].obstructions == [subs]
    assert toggle_times([subs], 2.0, 2.0) == []


def test_piece_hidden_at_zero_is_absent_until_shown():
    leaf = _sub((0, 1), (0, 1), hide=[0.0], show=[3.0])
    assert _present_at([leaf], [0.0, 2.0, 3.0, 4.0]) == {
        0.0: 0,
        2.0: 0,
        3.0: 1,
        4.0: 1,
    }


def test_piece_removed_later_is_present_until_hidden():
    leaf = _sub((0, 1), (0, 1), hide=[3.0])
    assert _present_at([leaf], [0.0, 2.0, 3.0, 4.0]) == {
        0.0: 1,
        2.0: 1,
        3.0: 0,
        4.0: 0,
    }


def test_hide_show_hide_follows_the_last_toggle():
    leaf = _sub((0, 1), (0, 1), hide=[1.0, 5.0], show=[3.0])
    assert _present_at([leaf], [0.0, 2.0, 4.0, 6.0]) == {
        0.0: 1,
        2.0: 0,
        4.0: 1,
        6.0: 0,
    }


def test_toggle_on_a_point_applies_at_that_point():
    leaf = _sub((0, 1), (0, 1), hide=[2.0])
    assert _present_at([leaf], [1.0, 2.0]) == {1.0: 1, 2.0: 0}


def test_simultaneous_hide_and_show_raises_naming_the_obstruction():
    leaf = _sub((0, 1), (0, 1), hide=[2.0], show=[2.0], mesh="M7")
    with pytest.raises(ValueError, match=r"obstruction 12 on mesh M7.*2\.0"):
        obstruction_periods([_Obst(12, [leaf])], 2.0, [0.0, 3.0])


def test_piece_outside_the_slice_height_opens_no_period():
    high = _sub((0, 1), (0, 1), hide=[3.0], z=(2.4, 3.0))
    low = _sub((1, 2), (0, 1))
    periods = obstruction_periods([[high, low]], 2.0, [0.0, 4.0])
    assert len(periods) == 1
    assert periods[0].obstructions == [[high, low]]
    assert toggle_times([[high, low]], 2.0, 4.0) == []


def test_slice_height_bounds_are_inclusive():
    leaf = _sub((0, 1), (0, 1), hide=[3.0], z=(0.0, 2.0))
    assert toggle_times([[leaf]], 2.0, 4.0) == [3.0]
    flat = _sub((0, 1), (0, 1), hide=[3.0], z=(0.0, 0.0))
    assert toggle_times([[flat]], 2.0, 4.0) == []


def test_toggles_after_the_last_point_open_no_period():
    leaf = _sub((0, 1), (0, 1), hide=[50.0])
    periods = obstruction_periods([[leaf]], 2.0, [0.0, 10.0])
    assert len(periods) == 1
    assert toggle_times([[leaf]], 2.0, 10.0) == []


def test_pieces_with_one_toggle_time_give_one_period():
    one = _sub((0, 1), (0, 1), hide=[3.0])
    two = _sub((1, 2), (0, 1), hide=[3.0])
    periods = obstruction_periods([[one, two]], 2.0, [0.0, 2.0, 4.0, 6.0])
    assert [p.time_points for p in periods] == [(0.0, 2.0), (4.0, 6.0)]
    assert toggle_times([[one, two]], 2.0, 6.0) == [3.0]


def test_a_period_without_a_point_is_skipped():
    leaf = _sub((0, 1), (0, 1), hide=[1.0, 2.0], show=[1.5])
    periods = obstruction_periods([[leaf]], 2.0, [0.0, 3.0])
    assert [p.time_points for p in periods] == [(0.0,), (3.0,)]


def test_periods_with_the_same_pieces_merge():
    """A second hide changes nothing: its toggle opens no separate cache."""
    leaf = _sub((0, 1), (0, 1), hide=[1.0, 2.0])
    periods = obstruction_periods([[leaf]], 2.0, [0.0, 1.5, 2.5])
    assert [p.time_points for p in periods] == [(0.0,), (1.5, 2.5)]
    assert toggle_times([[leaf]], 2.0, 2.5) == [1.0, 2.0]


# -- synthetic scenes through fdsvismap -------------------------------------

_WALL_X = (4.5, 5.5)
_X = np.arange(0.25, 10.0, 0.5)
_Y = np.arange(0.25, 4.0, 0.5)
_SIGN = (8.25, 2.25)
_POINTS = [0.0, 5.0, 6.0, 10.0]
_AFTER = [False, False, True, True]


def _synthetic(subs):
    """Uniform clear air, a wall at x 4.5-5.5 m, sign at (8.25, 2.25)."""
    vis = VisMap()
    vis.set_grid(_X, _Y)
    vis.set_uniform_extco(0.0)
    vis.fds_slc_height = 2.0
    vis.obstructions_collection = [subs]
    vis.set_time_points(_POINTS)
    vis.add_sign(0, *_SIGN, c=3, alpha=None)
    _compute_by_period(vis)
    return _harvest(vis)


def _cell(harvest, x, y):
    ix, iy = int(np.argmin(abs(_X - x))), int(np.argmin(abs(_Y - y)))
    return harvest.vis[:, 0, iy, ix].tolist(), harvest.metres[:, 0, iy, ix].tolist()


def test_synthetic_door_that_opens():
    wall = [_sub(_WALL_X, (0, 1.5)), _sub(_WALL_X, (2.5, 4))]
    harvest = _synthetic([*wall, _sub(_WALL_X, (1.5, 2.5), hide=[5.5])])
    legible, metres = _cell(harvest, 2.25, 2.25)
    assert legible == _AFTER
    assert metres == [CAP if v else 0.0 for v in _AFTER]
    assert harvest.obstruction_toggles_s.tolist() == [5.5]


def test_synthetic_hold_open_door_that_closes():
    wall = [_sub(_WALL_X, (0, 1.5)), _sub(_WALL_X, (2.5, 4))]
    harvest = _synthetic([*wall, _sub(_WALL_X, (1.5, 2.5), hide=[0.0], show=[5.5])])
    legible, metres = _cell(harvest, 2.25, 2.25)
    assert legible == [not v for v in _AFTER]
    assert metres == [0.0 if v else CAP for v in _AFTER]


def test_synthetic_hole_through_a_timed_obst():
    """FDS leaves the doorway free and gives the panel remnant its toggle."""
    harvest = _synthetic([_sub(_WALL_X, (0, 1.5)), _sub(_WALL_X, (2.5, 4), hide=[5.5])])
    assert _cell(harvest, 2.25, 2.25)[0] == [True] * 4  # on the doorway axis
    assert _cell(harvest, 2.25, 3.25)[0] == _AFTER  # behind the panel remnant


def test_no_toggles_equals_a_plain_compute_all():
    """I1: a scene without timed pieces is one compute_all on the same map."""
    subs = [_sub(_WALL_X, (0, 1.5)), _sub(_WALL_X, (2.5, 4))]
    plain = VisMap()
    plain.set_grid(_X, _Y)
    plain.set_uniform_extco(0.0)
    plain.fds_slc_height = 2.0
    plain.obstructions_collection = [subs]
    plain.build_obstructions_array()
    plain.set_time_points(_POINTS)
    plain.add_sign(0, *_SIGN, c=3, alpha=None)
    plain.compute_all(view_angle=True, obstructions=True, aa=True)
    harvest = _synthetic(subs)
    from pyfds_evac.core.visibility import _vis_bool_array, _vis_metre_array

    assert np.array_equal(harvest.vis, _vis_bool_array(plain))
    assert np.array_equal(harvest.metres, _vis_metre_array(plain))
    assert harvest.obstruction_toggles_s.size == 0
