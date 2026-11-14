"""B3.1 -- a non-square room catches an x/y transpose in the visibility map.

A square room cannot tell ``[y, x]`` from ``[x, y]``. Here the room is
8 x 4 m on a 0.25 m grid, so the arrays are (16, 32) and a swapped index reads
another cell or raises ``IndexError``. The sign sits on the south wall, off
centre in both axes, facing north, with K = 1 1/m and c = 4.15, so
R = c / K = 4.15 m (below the 30 m cap and below the room diagonal).

The expected set is computed here from the rule, not from fdsvismap. A sign
read through ``cos(theta) * R >= d`` with ``cos(theta) = dy / d`` is visible
iff ``dx**2 + dy**2 <= R * dy`` and ``dy > 0`` (or the cell is the sign's own): the disc of diameter R that is
tangent to the sign (not a fixed-angle cone). R = 4.15 puts no cell centre on
the boundary; ``test_no_cell_sits_on_the_boundary`` asserts the margin so float
rounding cannot flip one.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from shapely.geometry import box

from pyfds_evac.core.fds_sampling import load_slice_sampler
from pyfds_evac.core.visibility import (
    DEFAULT_MAX_SIGN_DISTANCE_M,
    VisibilityModel,
    _build_vismap,
)

pytest.importorskip("fdsvismap")

CELL_M = 0.25
SIGN_X, SIGN_Y = 6.125, 0.125
C = 4.15
K = 1.0
R_M = C / K
XS = 0.125 + CELL_M * np.arange(32)  # 0.125 .. 7.875
YS = 0.125 + CELL_M * np.arange(16)  # 0.125 .. 3.875


def _geometry(r_m: float):
    """Per-cell dy, d^2 and expected visibility, shape (16, 32) = [y, x]."""
    x_grid, y_grid = np.meshgrid(XS, YS)
    dx, dy = x_grid - SIGN_X, y_grid - SIGN_Y
    d2 = dx**2 + dy**2
    # The sign's own cell reads its sign (cos = 1 at d = 0).
    visible = (d2 == 0) | ((dy > 0) & (d2 <= r_m * dy))
    return dy, d2, visible


def _model(alpha, *, k=K, cache_path=None):
    signs = {"s": {"x": SIGN_X, "y": SIGN_Y, "alpha": alpha, "c": C}}
    return VisibilityModel.clear_air(
        box(0, 0, 8, 4),
        signs,
        cell_size_m=CELL_M,
        extinction_per_m=k,
        cache_path=cache_path,
    )


def _read_all(model):
    """(visible map, metres map) read through the public node API."""
    seen = np.zeros((YS.size, XS.size), dtype=bool)
    metres = np.full(seen.shape, np.nan)
    for iy, y in enumerate(YS):
        for ix, x in enumerate(XS):
            seen[iy, ix] = model.node_is_visible(0.0, x, y, "s")
            m = model.visibility_to_node(0.0, x, y, "s")
            if m is not None:
                metres[iy, ix] = m
    return seen, metres


def _idx(y, x):
    return int(np.searchsorted(YS, y)), int(np.searchsorted(XS, x))


def test_no_cell_sits_on_the_boundary():
    dy, d2, _ = _geometry(R_M)
    assert np.abs(d2 - R_M * dy)[dy > 0].min() >= 0.02


def test_expected_set_is_a_proper_non_square_subset():
    _, _, visible = _geometry(R_M)
    assert visible.shape == (16, 32)
    assert 0 < visible.sum() < visible.size
    # By hand: (6.125, 2.125) and (6.125, 3.875) (d^2 = 14.06 <= 15.56) see the
    # sign; (7.875, 3.875) (d^2 = 17.1 > 15.56) does not.
    assert visible[_idx(2.125, 6.125)]
    assert visible[_idx(3.875, 6.125)]
    assert not visible[_idx(3.875, 7.875)]


@pytest.mark.parametrize("cached", [False, True], ids=["live", "cached"])
def test_visibility_map_matches_the_hand_computed_disc(tmp_path, cached):
    dy, d2, visible = _geometry(R_M)
    cache = tmp_path / "vis.npz" if cached else None
    model = _model(0.0, cache_path=cache)
    if cached:
        model = _model(0.0, cache_path=cache)
        assert not hasattr(model._vis, "vismap")
    seen, metres = _read_all(model)
    assert np.array_equal(seen, visible)
    # visibility_to_node is the masked sighting distance R * cos(theta) =
    # R * dy / d on every cell in front of the sign (visible or not: the
    # sight test compares it with d), and None behind or beside it.
    rel = 1e-3 if cached else 1e-9
    front = (dy > 0) | (d2 == 0)
    assert np.array_equal(np.isnan(metres), ~front)
    ahead = dy > 0
    np.testing.assert_allclose(
        metres[ahead], R_M * dy[ahead] / np.sqrt(d2[ahead]), rtol=rel
    )
    assert metres[d2 == 0] == pytest.approx(R_M, rel=rel)  # cos = 1


def test_probes_that_a_transpose_breaks():
    model = _model(0.0)
    assert model.node_is_visible(0.0, 6.125, 2.125, "s")
    assert model.node_is_visible(0.0, 6.125, 3.875, "s")
    assert not model.node_is_visible(0.0, 7.875, 3.875, "s")


def test_cap_binds_when_the_air_is_clear():
    """K = 0 gives R = max_vis = 30 m; the set is the same rule with R = 30."""
    _, _, visible = _geometry(DEFAULT_MAX_SIGN_DISTANCE_M)
    assert 0 < visible.sum() < visible.size  # still excludes cells behind it
    seen, _ = _read_all(_model(0.0, k=0.0))
    assert np.array_equal(seen, visible)


def test_omni_sign_is_seen_from_every_cell():
    model = _model(None, k=0.0)
    assert all(model.node_is_visible(0.0, x, y, "s") for x in XS for y in YS)


T_JUNCTION_DIR = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "figures"
    / "data"
    / "t_junction_fire_2MW_PVC_extinction"
)


def test_fds_slice_orientation_on_the_30_by_13_m_t_junction():
    """fdsvismap's per-cell K lands on the cell the FDS slice put it in.

    ``clear_air`` never goes through fdsreader's ``to_global()`` [x, y] layout,
    which fdsvismap indexes as ``extco[x_id, y_id]`` (its own TODO asks why).
    On the 30 x 13 m slice (121 x 53 cells, tracked, no FDS run) the local
    sight distance min(c / K, max_vis) that fdsvismap reads at a cell must equal
    the one computed from K read at the same point by ``SliceFieldSampler``, an
    independent reader per mesh. A transposed array raises IndexError at
    x_id >= 53 or reads another cell's K. Tolerance: float32 slice precision.
    """
    sign = {"x": 0.5, "y": 11.5, "alpha": 90, "c": 3}
    vismap = _build_vismap(str(T_JUNCTION_DIR), {"a": sign}, 10.0, 2.0)
    sampler = load_slice_sampler(
        str(T_JUNCTION_DIR), "SOOT EXTINCTION COEFFICIENT", slice_height_m=2.0
    )
    time_s = 200.0
    assert (len(vismap.all_x_coords), len(vismap.all_y_coords)) == (121, 53)
    k_values = []
    for x in vismap.all_x_coords[::2]:
        for y in vismap.all_y_coords[::2]:
            k = sampler.sample(time_s, float(x), float(y))
            k_values.append(k)
            expected = DEFAULT_MAX_SIGN_DISTANCE_M if k == 0 else min(3.0 / k, 30.0)
            got = vismap.get_local_visibility(time_s, float(x), float(y), 3.0)
            assert got == pytest.approx(expected, rel=1e-6), (x, y, k)
    # Discriminating: the field is neither empty nor uniform.
    assert sum(k > 0 for k in k_values) > 100
    assert len(set(k_values)) > 100
