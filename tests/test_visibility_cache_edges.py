"""Edges of the cached visibility lookup and of the observer-off-grid rule.

Cache arrays are built by hand, so every expectation is a count or a
literal. The grids are 1 m apart: the time points 0 and 10 s, the x
positions 0, 1, 2 m (cells reach -0.5 to 2.5 m) and the single y row 0.
"""

from unittest.mock import patch

import numpy as np
import pytest

from pyfds_evac.core.visibility import VisibilityModel, _VisMapCache

_COORDS = np.array([0.0, 1.0, 2.0])


@pytest.mark.parametrize(
    ("value", "index"),
    [
        (0.5, 0),  # halfway between 0 and 1: the lower one
        (1.5, 1),  # halfway between 1 and 2: the lower one
        (0.5000001, 1),  # a hair above the middle: the upper one
        (0.4999999, 0),
        (1.0, 1),  # on a coordinate
        (-7.0, 0),  # below the axis: the first
        (9.0, 2),  # above the axis: the last
    ],
)
def test_nearest_coordinate_ties_go_to_the_lower_one(value, index):
    """A value equidistant from two coordinates takes the lower one.

    The tie rule is not documented outside the code. It is the rule of the
    sampler's vector `_nearest_indices` ("ties to the lower"), so the
    literals follow that convention and were not derived from a document.
    """
    assert _VisMapCache._nearest(_COORDS, value) == index


def test_a_one_position_axis_is_always_index_zero():
    only = np.array([4.0])
    assert [_VisMapCache._nearest(only, v) for v in (-1.0, 4.0, 99.0)] == [0, 0, 0]


def _cache():
    """Frames 0 and 10 s, three x positions, two waypoints, one y row.

    metres[t, w, 0, x] = 100 t + 10 w + x + 1, so a wrong index reads a
    different number; vis is True where t + w + x is even.
    """
    vis = np.zeros((2, 2, 1, 3), dtype=bool)
    metres = np.zeros((2, 2, 1, 3))
    for t in range(2):
        for w in range(2):
            for x in range(3):
                vis[t, w, 0, x] = (t + w + x) % 2 == 0
                metres[t, w, 0, x] = 100 * t + 10 * w + x + 1
    return _VisMapCache(
        time_points=np.array([0.0, 10.0]),
        x_coords=_COORDS,
        y_coords=np.array([0.0]),
        vis=vis,
        metres=metres,
        output_interval_s=10.0,
    )


def test_a_query_time_halfway_between_frames_reads_the_earlier_frame():
    """5 s is equidistant from 0 s and 10 s: frame 0 (metres 1, 2, 3 for w = 0)."""
    cache = _cache()
    assert cache.visibility_to_wp(5.0, 2.0, 0.0, 0) == 3.0
    assert cache.visibility_to_wp(5.0000001, 2.0, 0.0, 0) == 103.0
    assert cache.wp_is_visible(5.0, 1.0, 0.0, 0) is False  # frame 0, 0 + 0 + 1 odd


def test_an_x_halfway_between_cells_reads_the_lower_cell():
    """x = 0.5 is equidistant from 0 and 1 m: cell 0, metres 11 for w = 1."""
    assert _cache().visibility_to_wp(0.0, 0.5, 0.0, 1) == 11.0


def _model(cache, signs=None):
    signs = signs or {"s": {"x": 1.0, "y": 0.0}}
    with patch("pyfds_evac.core.visibility._resolve_vis", return_value=cache):
        return VisibilityModel("unused", signs)


class _Raises:
    """A backend whose distance query raises *error*."""

    def __init__(self, error):
        self._error = error

    def visibility_to_wp(self, **_):
        raise self._error


@pytest.mark.parametrize("error", [RuntimeError, IndexError, KeyError])
def test_a_backend_without_an_answer_gives_none(error):
    """RuntimeError, IndexError and KeyError mean "no answer": the caller
    falls back (the docstring of `visibility_to_node`)."""
    model = _model(_cache())
    model._vis = _Raises(error("no answer"))
    assert model.visibility_to_node(0.0, 1.0, 0.0, "s") is None


def test_any_other_backend_error_is_raised():
    model = _model(_cache())
    model._vis = _Raises(ValueError("a defect, not a missing answer"))
    with pytest.raises(ValueError, match="a defect"):
        model.visibility_to_node(0.0, 1.0, 0.0, "s")


def test_a_cache_without_distances_gives_none():
    """An old cache holds no metres: None, not an error."""
    cache = _cache()
    cache._metres = None
    assert _model(cache).visibility_to_node(0.0, 1.0, 0.0, "s") is None


def test_a_sign_beyond_the_cache_waypoints_gives_none():
    """A third sign has index 2; the cache holds waypoints 0 and 1 only."""
    signs = {k: {"x": 1.0, "y": 0.0} for k in ("a", "b", "c")}
    assert _model(_cache(), signs).visibility_to_node(0.0, 1.0, 0.0, "c") is None


def test_a_masked_zero_distance_gives_none_and_a_positive_one_is_returned():
    """Zero metres is "concealed", "behind the sign" or "smoked out": None."""
    cache = _cache()
    cache._metres[0, 0, 0, 1] = 0.0
    model = _model(cache)
    assert model.visibility_to_node(0.0, 1.0, 0.0, "s") is None
    assert model.visibility_to_node(0.0, 2.0, 0.0, "s") == 3.0


def _hidden_model(**sign):
    """No sign visible anywhere on the grid; the sign "s" is at (1, 0)."""
    cache = _cache()
    cache._vis[:] = False
    return _model(cache, {"s": {"x": 1.0, "y": 0.0, **sign}})


def test_an_observer_exactly_at_the_reading_distance_sees_the_sign():
    """Off the grid at x = -4 m, 5 m from the sign, cap 5 m: clear air, seen.

    "Within its reading distance" includes the distance itself.
    """
    model = _hidden_model(max_distance=5)
    assert model.node_is_visible(0.0, -4.0, 0.0, "s") is True
    assert model.node_is_visible(0.0, -4.0000001, 0.0, "s") is False


@pytest.mark.parametrize("x", [-0.5, 2.5])
def test_an_observer_on_the_cell_edge_is_on_the_grid(x):
    """On the edge of the outer cell the grid answers: smoked out, not seen."""
    assert _hidden_model().node_is_visible(0.0, x, 0.0, "s") is False


@pytest.mark.parametrize("x", [-0.5000001, 2.5000001])
def test_an_observer_a_hair_beyond_the_cell_edge_is_off_the_grid(x):
    """A hair beyond the edge the observer is off the grid: clear air, seen."""
    assert _hidden_model().node_is_visible(0.0, x, 0.0, "s") is True
