"""VisMap grid alignment for FDS decks with mixed mesh resolutions (#928).

fdsvismap 0.3.3 reads slice coordinates via ``slc.get_coordinates()``, which
concatenates unique ticks across sub-slices without resampling coarser meshes.
On decks with mixed 0.2 m / 0.4 m mesh sizes this produces a non-uniform grid
(e.g. shape (316, 341)) while ``slc.to_global()`` builds a uniform Cartesian
grid at the finest step (e.g. shape (356, 419)).  The mismatch triggers::

    ValueError: operands could not be broadcast together with shapes (316,341) (356,419)

``align_vismap_grid`` detects and corrects the mismatch; ``validate_vismap_shapes``
raises a descriptive error if shapes still disagree.  These pure-Python tests
exercise both functions with lightweight mock objects so they run offline without
any FDS data.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from pyfds_evac.core.fdsvismap_adapter import (
    align_vismap_grid,
    slice_global_coordinates,
    validate_vismap_shapes,
)


# ---------------------------------------------------------------------------
# Helpers — fake fdsreader objects
# ---------------------------------------------------------------------------


def _mesh_coords(x_nodes: np.ndarray, y_nodes: np.ndarray) -> dict[str, np.ndarray]:
    """Return a mesh.coordinates dict from node arrays (face nodes)."""
    return {"x": x_nodes, "y": y_nodes}


def _subslice(
    mesh_x: np.ndarray, mesh_y: np.ndarray, x_nodes: np.ndarray, y_nodes: np.ndarray
) -> SimpleNamespace:
    """Fake SubSlice whose get_coordinates returns the given node arrays."""
    mesh = SimpleNamespace(coordinates=_mesh_coords(mesh_x, mesh_y))

    def get_coordinates(ignore_cell_centered: bool = False) -> dict[str, np.ndarray]:
        return {"x": x_nodes, "y": y_nodes}

    return SimpleNamespace(mesh=mesh, get_coordinates=get_coordinates)


def _slice_with_subslices(
    subslices: dict[str, Any],
    orientation: int = 3,
    cell_centered: bool = False,
) -> SimpleNamespace:
    """Fake fdsreader Slice with the given _subslices mapping."""
    return SimpleNamespace(
        _subslices=subslices,
        orientation=orientation,
        cell_centered=cell_centered,
    )


def _fine_mesh_subslice(
    x_min: float = 0.0,
    x_max: float = 10.0,
    y_min: float = 0.0,
    y_max: float = 8.0,
    step: float = 0.2,
) -> SimpleNamespace:
    """A fine-mesh (0.2 m) sub-slice covering the given range."""
    xs = np.arange(x_min, x_max + step / 2, step)
    ys = np.arange(y_min, y_max + step / 2, step)
    return _subslice(xs, ys, xs, ys)


def _coarse_mesh_subslice(
    x_min: float = 10.0,
    x_max: float = 20.0,
    y_min: float = 0.0,
    y_max: float = 8.0,
    step: float = 0.4,
) -> SimpleNamespace:
    """A coarse-mesh (0.4 m) sub-slice covering the given range."""
    xs = np.arange(x_min, x_max + step / 2, step)
    ys = np.arange(y_min, y_max + step / 2, step)
    return _subslice(xs, ys, xs, ys)


# ---------------------------------------------------------------------------
# slice_global_coordinates — unit tests
# ---------------------------------------------------------------------------


class TestSliceGlobalCoordinates:
    """slice_global_coordinates returns the uniform grid matching to_global()."""

    def test_single_uniform_mesh_returns_its_own_grid(self):
        """With one mesh there is no ambiguity; the returned grid equals the mesh."""
        step = 0.2
        xs = np.arange(0.0, 10.0 + step / 2, step)
        ys = np.arange(0.0, 8.0 + step / 2, step)
        sslc = _subslice(xs, ys, xs, ys)
        slc = _slice_with_subslices({"m1": sslc})
        gx, gy = slice_global_coordinates(slc)
        assert len(gx) == len(xs)
        assert len(gy) == len(ys)
        np.testing.assert_allclose(gx[0], 0.0, atol=1e-9)
        np.testing.assert_allclose(gx[-1], 10.0, atol=1e-5)

    def test_mixed_mesh_grid_uses_finest_step(self):
        """Fine (0.2 m) + coarse (0.4 m): result uses 0.2 m across the full span."""
        fine = _fine_mesh_subslice(0.0, 10.0, 0.0, 8.0, step=0.2)
        coarse = _coarse_mesh_subslice(10.0, 20.0, 0.0, 8.0, step=0.4)
        slc = _slice_with_subslices({"m1": fine, "m2": coarse})
        gx, gy = slice_global_coordinates(slc)
        # x spans [0, 20] at 0.2 m step -> 101 nodes
        expected_nx = int(round(20.0 / 0.2)) + 1
        assert len(gx) == expected_nx, f"expected {expected_nx} x-points, got {len(gx)}"
        # y spans [0, 8] at 0.2 m step -> 41 nodes
        expected_ny = int(round(8.0 / 0.2)) + 1
        assert len(gy) == expected_ny, f"expected {expected_ny} y-points, got {len(gy)}"
        # uniform spacing throughout
        diffs_x = np.diff(gx)
        diffs_y = np.diff(gy)
        np.testing.assert_allclose(diffs_x, 0.2, atol=1e-6)
        np.testing.assert_allclose(diffs_y, 0.2, atol=1e-6)

    def test_non_horizontal_slice_returns_none(self):
        """Only orientation == 3 (horizontal) is supported."""
        fine = _fine_mesh_subslice()
        slc = _slice_with_subslices({"m1": fine}, orientation=1)
        assert slice_global_coordinates(slc) is None

    def test_empty_subslices_returns_none(self):
        slc = _slice_with_subslices({})
        assert slice_global_coordinates(slc) is None

    def test_missing_slc_attribute_returns_none(self):
        """A VisMap without a ``slc`` attribute returns None gracefully."""
        result = slice_global_coordinates(SimpleNamespace())
        assert result is None

    def test_grid_boundaries_match_all_submesh_extents(self):
        """The returned grid starts at the global min and ends at the global max."""
        fine = _fine_mesh_subslice(2.0, 8.0, 1.0, 5.0, step=0.2)
        coarse = _coarse_mesh_subslice(8.0, 14.0, 1.0, 5.0, step=0.4)
        slc = _slice_with_subslices({"m1": fine, "m2": coarse})
        gx, gy = slice_global_coordinates(slc)
        np.testing.assert_allclose(gx[0], 2.0, atol=1e-5)
        np.testing.assert_allclose(gx[-1], 14.0, atol=1e-5)
        np.testing.assert_allclose(gy[0], 1.0, atol=1e-5)
        np.testing.assert_allclose(gy[-1], 5.0, atol=1e-5)


# ---------------------------------------------------------------------------
# align_vismap_grid — unit tests
# ---------------------------------------------------------------------------


def _make_vis(
    *,
    n_x: int,
    n_y: int,
    x_range: tuple = (0.0, 20.0),
    y_range: tuple = (0.0, 8.0),
    with_slc: bool = True,
    sign_ids: list | None = None,
) -> SimpleNamespace:
    """Build a minimal fake VisMap with shape (n_y, n_x)."""
    xs = np.linspace(x_range[0], x_range[1], n_x)
    ys = np.linspace(y_range[0], y_range[1], n_y)

    build_calls: list = []
    invalidate_calls: list = []

    def build_obstructions_array():
        build_calls.append("called")

    def _invalidate_results():
        invalidate_calls.append("called")

    sign_ids = sign_ids or [0]
    angle_dict = {sid: np.ones((n_y, n_x)) for sid in sign_ids}
    nc_dict = {sid: np.ones((n_y, n_x)) for sid in sign_ids}

    vis = SimpleNamespace(
        all_x_coords=xs,
        all_y_coords=ys,
        fds_grid_shape=(n_x, n_y),
        cell_size=(
            float(xs[1] - xs[0]) if n_x > 1 else 1.0,
            float(ys[1] - ys[0]) if n_y > 1 else 1.0,
        ),
        obstructions_array=np.zeros((n_y, n_x)),
        all_sign_angle_array_dict=angle_dict,
        all_sign_non_concealed_cells_array_dict=nc_dict,
        build_obstructions_array=build_obstructions_array,
        _invalidate_results=_invalidate_results,
        _build_calls=build_calls,
        _invalidate_calls=invalidate_calls,
    )

    if with_slc:
        mesh_x = np.linspace(x_range[0], x_range[1], n_x)
        mesh_y = np.linspace(y_range[0], y_range[1], n_y)
        sslc = _subslice(mesh_x, mesh_y, mesh_x, mesh_y)
        vis.slc = _slice_with_subslices({"m1": sslc})
    return vis


def _make_mixed_mesh_vis(
    *,
    nonuniform_n_x: int,
    nonuniform_n_y: int,
    x_min: float = 0.0,
    x_max: float = 20.0,
    y_min: float = 0.0,
    y_max: float = 8.0,
    fine_step: float = 0.2,
    coarse_step: float = 0.4,
    split_x: float = 10.0,
) -> SimpleNamespace:
    """VisMap whose slc has mixed meshes but whose arrays have the non-uniform shape."""
    xs_nu = np.linspace(x_min, x_max, nonuniform_n_x)
    ys_nu = np.linspace(y_min, y_max, nonuniform_n_y)

    build_calls: list = []
    invalidate_calls: list = []

    def build_obstructions_array():
        build_calls.append("called")

    def _invalidate_results():
        invalidate_calls.append("called")

    vis = SimpleNamespace(
        all_x_coords=xs_nu,
        all_y_coords=ys_nu,
        fds_grid_shape=(nonuniform_n_x, nonuniform_n_y),
        cell_size=(float(xs_nu[1] - xs_nu[0]), float(ys_nu[1] - ys_nu[0])),
        obstructions_array=np.zeros((nonuniform_n_y, nonuniform_n_x)),
        all_sign_angle_array_dict={},
        all_sign_non_concealed_cells_array_dict={},
        build_obstructions_array=build_obstructions_array,
        _invalidate_results=_invalidate_results,
        _build_calls=build_calls,
        _invalidate_calls=invalidate_calls,
    )

    # Mixed-mesh slice: fine mesh [x_min, split_x] and coarse mesh [split_x, x_max]
    fine = _fine_mesh_subslice(x_min, split_x, y_min, y_max, step=fine_step)
    coarse = _coarse_mesh_subslice(split_x, x_max, y_min, y_max, step=coarse_step)
    vis.slc = _slice_with_subslices({"m_fine": fine, "m_coarse": coarse})
    return vis


class TestAlignVisMapGrid:
    """align_vismap_grid corrects shape mismatches caused by mixed mesh sizes."""

    def test_uniform_grid_returns_false_no_rebuild(self):
        """Grid already matches -> returns False and does not call build_obstructions_array."""
        vis = _make_vis(n_x=51, n_y=41)
        changed = align_vismap_grid(vis)
        assert changed is False
        assert vis._build_calls == []
        assert vis._invalidate_calls == []

    def test_mixed_mesh_returns_true(self):
        """Mixed mesh -> returns True (grid was replaced)."""
        vis = _make_mixed_mesh_vis(nonuniform_n_x=76, nonuniform_n_y=41)
        changed = align_vismap_grid(vis)
        assert changed is True

    def test_mixed_mesh_grid_shape_becomes_uniform(self):
        """After alignment the x-coords have the uniform fine-step count."""
        vis = _make_mixed_mesh_vis(
            nonuniform_n_x=76,
            nonuniform_n_y=41,
            fine_step=0.2,
            coarse_step=0.4,
        )
        align_vismap_grid(vis)
        expected_nx = int(round(20.0 / 0.2)) + 1  # 101
        expected_ny = int(round(8.0 / 0.2)) + 1   # 41
        assert len(vis.all_x_coords) == expected_nx
        assert len(vis.all_y_coords) == expected_ny

    def test_mixed_mesh_triggers_build_obstructions_array(self):
        """build_obstructions_array is called once after a grid realignment."""
        vis = _make_mixed_mesh_vis(nonuniform_n_x=76, nonuniform_n_y=41)
        align_vismap_grid(vis)
        assert len(vis._build_calls) == 1

    def test_mixed_mesh_triggers_invalidate_results(self):
        """_invalidate_results is called once after a grid realignment."""
        vis = _make_mixed_mesh_vis(nonuniform_n_x=76, nonuniform_n_y=41)
        align_vismap_grid(vis)
        assert len(vis._invalidate_calls) == 1

    def test_grid_coords_are_uniformly_spaced_after_alignment(self):
        """The aligned x-coords are equally spaced (uniform Cartesian grid)."""
        vis = _make_mixed_mesh_vis(nonuniform_n_x=76, nonuniform_n_y=41)
        align_vismap_grid(vis)
        diffs = np.diff(vis.all_x_coords)
        np.testing.assert_allclose(diffs, diffs[0], rtol=1e-6)

    def test_no_slc_attribute_returns_false(self):
        """A VisMap without a slc attribute is left untouched."""
        vis = _make_vis(n_x=51, n_y=41, with_slc=False)
        changed = align_vismap_grid(vis)
        assert changed is False

    def test_fds_grid_shape_updated_after_alignment(self):
        """fds_grid_shape is updated to match the new coord lengths."""
        vis = _make_mixed_mesh_vis(nonuniform_n_x=76, nonuniform_n_y=41)
        align_vismap_grid(vis)
        assert vis.fds_grid_shape == (len(vis.all_x_coords), len(vis.all_y_coords))

    def test_idempotent_called_twice(self):
        """A second call after alignment detects no further mismatch."""
        vis = _make_mixed_mesh_vis(nonuniform_n_x=76, nonuniform_n_y=41)
        first = align_vismap_grid(vis)
        second = align_vismap_grid(vis)
        assert first is True
        assert second is False  # already aligned
        assert len(vis._build_calls) == 1  # built only once


# ---------------------------------------------------------------------------
# validate_vismap_shapes — unit tests
# ---------------------------------------------------------------------------


def _make_valid_vis_for_validate(n_x: int = 51, n_y: int = 41) -> SimpleNamespace:
    """VisMap where all arrays are consistent -> validate should not raise."""
    xs = np.linspace(0.0, 10.0, n_x)
    ys = np.linspace(0.0, 8.0, n_y)
    return SimpleNamespace(
        all_x_coords=xs,
        all_y_coords=ys,
        obstructions_array=np.zeros((n_y, n_x)),
        all_sign_angle_array_dict={0: np.ones((n_y, n_x))},
        all_sign_non_concealed_cells_array_dict={0: np.ones((n_y, n_x))},
        vismap_time_points=[0.0, 1.0],
    )


class TestValidateVisMapShapes:
    """validate_vismap_shapes raises ValueError on shape mismatches."""

    def test_valid_shapes_does_not_raise(self):
        """Consistent shapes -> no exception."""
        vis = _make_valid_vis_for_validate()
        validate_vismap_shapes(vis)  # must not raise

    def test_obstructions_mismatch_raises(self):
        """obstructions_array with wrong shape raises ValueError."""
        vis = _make_valid_vis_for_validate(n_x=51, n_y=41)
        # Simulate what happens before fix: obstruction built on (356,419) while coords say (41,51)
        vis.obstructions_array = np.zeros((356, 419))
        with pytest.raises(ValueError, match="obstructions_array"):
            validate_vismap_shapes(vis)

    def test_angle_dict_mismatch_raises(self):
        """An angle array with shape mismatching the coordinates raises ValueError."""
        vis = _make_valid_vis_for_validate(n_x=51, n_y=41)
        vis.all_sign_angle_array_dict = {0: np.ones((316, 341))}
        with pytest.raises(ValueError, match="angle array"):
            validate_vismap_shapes(vis)

    def test_non_concealed_dict_mismatch_raises(self):
        """A non-concealed-cells array with wrong shape raises ValueError."""
        vis = _make_valid_vis_for_validate(n_x=51, n_y=41)
        vis.all_sign_non_concealed_cells_array_dict = {0: np.ones((316, 341))}
        with pytest.raises(ValueError, match="non-concealed array"):
            validate_vismap_shapes(vis)

    def test_error_message_contains_expected_shape(self):
        """The ValueError message names the wrong shape for easy debugging."""
        vis = _make_valid_vis_for_validate(n_x=51, n_y=41)
        vis.obstructions_array = np.zeros((356, 419))
        with pytest.raises(ValueError) as exc_info:
            validate_vismap_shapes(vis)
        msg = str(exc_info.value)
        # Must mention the wrong shape and the expected shape
        assert "356" in msg or "419" in msg
        assert "41" in msg or "51" in msg

    def test_no_coords_does_not_raise(self):
        """Missing coordinate arrays -> function returns without checking."""
        vis = SimpleNamespace(all_x_coords=None, all_y_coords=None)
        validate_vismap_shapes(vis)  # must not raise

    def test_multiple_signs_all_checked(self):
        """All signs in the dicts are validated, not just the first."""
        vis = _make_valid_vis_for_validate(n_x=51, n_y=41)
        vis.all_sign_angle_array_dict = {
            0: np.ones((41, 51)),  # correct
            1: np.ones((316, 341)),  # wrong - shape from #928
        }
        with pytest.raises(ValueError, match="sign 1"):
            validate_vismap_shapes(vis)


# ---------------------------------------------------------------------------
# Integration: broadcast-safe after alignment
# ---------------------------------------------------------------------------


class TestBroadcastSafeAfterAlignment:
    """After align_vismap_grid the shapes involved in _vis_metre_array are compatible.

    The crash in #928 is::

        masked = angle_array * extco_array.T * nc_array   # (316,341)*(356,419)*(316,341)

    After alignment ``angle_array`` and ``nc_array`` must have shape
    (n_y_uniform, n_x_uniform).
    """

    def test_original_shapes_would_have_broadcast_error(self):
        """Confirm that the original (non-uniform) x (uniform) shapes raise.

        This documents the exact error #928 triggers before the fix.
        """
        angle_arr = np.ones((316, 341))
        nc_arr = np.ones((316, 341))
        extco_arr_T = np.ones((356, 419))

        with pytest.raises(ValueError, match="broadcast"):
            _ = angle_arr * extco_arr_T * nc_arr

    def test_after_alignment_shapes_are_compatible(self):
        """After align_vismap_grid all arrays can be multiplied element-wise."""
        vis = _make_mixed_mesh_vis(nonuniform_n_x=76, nonuniform_n_y=41)
        align_vismap_grid(vis)

        ny = len(vis.all_y_coords)
        nx = len(vis.all_x_coords)
        spatial_shape = (ny, nx)

        angle_arr = np.ones(spatial_shape)
        extco_T = np.ones(spatial_shape)
        nc_arr = np.ones(spatial_shape)

        result = angle_arr * extco_T * nc_arr
        assert result.shape == spatial_shape

    def test_aligned_shapes_do_not_broadcast_error(self):
        """After alignment both sides of the multiplication share the same shape."""
        vis = _make_mixed_mesh_vis(nonuniform_n_x=76, nonuniform_n_y=41)
        align_vismap_grid(vis)

        ny = len(vis.all_y_coords)
        nx = len(vis.all_x_coords)
        extco_arr_T = np.ones((ny, nx))
        angle_arr = np.ones((ny, nx))
        nc_arr = np.ones((ny, nx))

        result = angle_arr * extco_arr_T * nc_arr
        assert result.shape == (ny, nx)
