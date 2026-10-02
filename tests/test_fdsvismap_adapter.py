"""Contract of the fdsvismap boundary, checked against the installed library.

A clear-air room of 10 x 4 m on a 0.5 m grid with a uniform K = 0.5 1/m, so
Jin's c / K_ave is 3 / 0.5 = 6 m along every sight line, below the 30 m cap.
Signs sit on cell centres. No mocks: a renamed or removed fdsvismap method
must fail here rather than turn into a silent fallback.
"""

import math

import pytest
from shapely.geometry import box

from pyfds_evac.core.visibility import VisibilityModel

pytest.importorskip("fdsvismap")

K_PER_M = 0.5
C = 3.0
SIGHT_M = C / K_PER_M
SIGN_XY = (1.25, 2.25)
OBSERVER_XY = (5.25, 2.25)  # 4 m east of the sign, inside 6 m


def _model(alpha):
    signs = {"s": {"x": SIGN_XY[0], "y": SIGN_XY[1], "alpha": alpha, "c": C}}
    return VisibilityModel.clear_air(
        box(0, 0, 10, 4), signs, cell_size_m=0.5, extinction_per_m=K_PER_M
    )


def test_uncached_clear_air_returns_fdsvismaps_sighting_distance():
    """visibility_to_node reads fdsvismap's float64 answer, not None."""
    model = _model(alpha=None)
    assert model.node_is_visible(0.0, *OBSERVER_XY, "s")
    metres = model.visibility_to_node(0.0, *OBSERVER_XY, "s")
    assert metres is not None and math.isfinite(metres)
    assert metres == pytest.approx(SIGHT_M, rel=1e-12)
    vismap = model._vis.vismap
    assert metres == vismap.get_visibility_to_sign(0.0, *OBSERVER_XY, sign_id=0)


def test_uncached_clear_air_answers_any_query_time():
    """A uniform field holds at every time (fdsvismap#45)."""
    model = _model(alpha=None)
    assert model.node_is_visible(500.0, *OBSERVER_XY, "s")
    assert model.visibility_to_node(500.0, *OBSERVER_XY, "s") == pytest.approx(
        SIGHT_M, rel=1e-12
    )


def test_directional_sign_is_legible_from_its_own_cell():
    """The view angle at distance 0 is cos = 1, not 0/0 (fdsvismap 0.3.0)."""
    model = _model(alpha=90.0)
    assert model.node_is_visible(0.0, *SIGN_XY, "s")
    assert model.visibility_to_node(0.0, *SIGN_XY, "s") == pytest.approx(
        SIGHT_M, rel=1e-12
    )


def test_directional_sign_is_hidden_from_behind():
    """alpha = 90 is read from the east only; the half-plane still holds."""
    signs = {"s": {"x": 5.25, "y": 2.25, "alpha": 90.0, "c": C}}
    model = VisibilityModel.clear_air(
        box(0, 0, 10, 4), signs, cell_size_m=0.5, extinction_per_m=K_PER_M
    )
    assert model.node_is_visible(0.0, 7.25, 2.25, "s")
    assert not model.node_is_visible(0.0, 3.25, 2.25, "s")
    assert model.visibility_to_node(0.0, 3.25, 2.25, "s") is None


def test_cached_metres_mirror_fdsvismaps_masked_product(tmp_path):
    """_vis_metre_array matches get_visibility_to_sign cell by cell."""
    signs = {"s": {"x": 5.25, "y": 2.25, "alpha": 90.0, "c": C}}
    walkable = box(0, 0, 10, 4)
    kwargs = dict(cell_size_m=0.5, extinction_per_m=K_PER_M)
    cache = tmp_path / "vis.npz"
    live = VisibilityModel.clear_air(walkable, signs, cache_path=cache, **kwargs)
    cached = VisibilityModel.clear_air(walkable, signs, cache_path=cache, **kwargs)
    assert not hasattr(cached._vis, "vismap")
    vismap = live._vis.vismap
    for x in vismap.all_x_coords:
        for y in vismap.all_y_coords:
            expected = vismap.get_visibility_to_sign(0.0, x, y, sign_id=0)
            got = cached._vis.visibility_to_wp(0.0, x, y, 0)
            assert got == pytest.approx(expected, rel=1e-3)
