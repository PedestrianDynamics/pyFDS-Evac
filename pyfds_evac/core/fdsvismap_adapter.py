"""Obstruction state in time for fdsvismap, from the FDS ``.smv`` toggles.

fdsvismap 0.3.3 builds one obstruction map from ``Simulation.obstructions``
and never reads ``SubObstruction.hide_times`` / ``show_times``, so an
``&OBST`` that FDS removes or creates during the run blocks sight lines at
every time. This module decides which sub-obstructions FDS has at a time and
splits the vismap time points into periods in which that set does not change;
``visibility._build_vismap`` builds one ray-casting cache per period.

The rule: a sub-obstruction is hidden at *t* when its last toggle at or before
*t* is a hide. A piece created later is hidden at 0.0 and shown later; a piece
removed later is only hidden later. FDS has already resolved every ``&HOLE``
into the pieces it writes, so nothing here reads the ``.fds`` deck.
``SubObstruction.get_visible_times`` is not used: it matches times by exact
equality and misses both cases.

Workaround record. Reason: fdsvismap ignores ``hide_times`` / ``show_times``.
Affected versions: fdsvismap 0.2.1 to 0.3.3 (pinned exactly). Upstream issue:
fdsvismap#63. Regression tests: ``tests/test_timed_obstructions.py``. Remove
when fdsvismap reads the toggle times itself.

Workaround record. Reason: fdsvismap builds a non-uniform coordinate grid from
``slc.get_coordinates()`` on decks with mixed mesh resolutions (#928), causing
shape mismatch with ``slc.to_global()``.
Affected versions: fdsvismap 0.2.1 to 0.3.3 (pinned exactly). Upstream issue:
PedestrianDynamics/pyFDS-Evac#928. Regression tests: ``tests/test_mixed_mesh_vismap.py``.
Remove when fdsvismap derives its grid from ``to_global()`` or resamples mixed meshes.
"""

from __future__ import annotations

import math
from bisect import bisect_right
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass(frozen=True)
class ObstructionPeriod:
    """Vismap time points that share one obstruction set.

    ``obstructions`` has the shape of ``VisMap.obstructions_collection``: one
    list of present sub-obstructions per FDS obstruction.
    """

    time_points: tuple[float, ...]
    obstructions: list[list[Any]]


def _spans_height(sub: Any, slice_height_m: float) -> bool:
    """The z test fdsvismap applies, with inclusive bounds."""
    z_range = sub.extent["z"]
    return bool(z_range[0] <= slice_height_m <= z_range[1])


def _is_hidden(sub: Any, time: float, label: str) -> bool:
    hides, shows = sorted(sub.hide_times), sorted(sub.show_times)
    n_hide, n_show = bisect_right(hides, time), bisect_right(shows, time)
    if n_hide == 0:
        return False
    if n_show == 0:
        return True
    last_hide, last_show = hides[n_hide - 1], shows[n_show - 1]
    if last_hide == last_show:
        raise ValueError(
            f"Obstruction state at t = {time} s is undefined for {label}: FDS "
            f"hides and shows it at the same time ({last_hide} s), and "
            "fdsreader does not keep their order."
        )
    return last_hide > last_show


def _label(obstruction: Any, sub: Any) -> str:
    mesh = getattr(getattr(sub, "mesh", None), "id", "?")
    return f"obstruction {getattr(obstruction, 'id', '?')} on mesh {mesh}"


def toggle_times(
    collection: Sequence[Any], slice_height_m: float, last_time: float
) -> list[float]:
    """Distinct toggle times in (0, *last_time*] of the pieces at the slice height.

    A hide at 0.0 is part of the initial state, not a change. Pieces outside
    the slice height never reach the obstruction map and open no period.
    """
    times: set[float] = set()
    for obstruction in collection:
        for sub in obstruction:
            if not _spans_height(sub, slice_height_m):
                continue
            times.update(float(t) for t in (*sub.hide_times, *sub.show_times))
    return sorted(t for t in times if 0.0 < t <= last_time)


def _present(
    collection: Sequence[Any], slice_height_m: float, time: float
) -> list[list[Any]]:
    return [
        [
            sub
            for sub in obstruction
            if not _spans_height(sub, slice_height_m)
            or not _is_hidden(sub, time, _label(obstruction, sub))
        ]
        for obstruction in collection
    ]


def obstruction_periods(
    collection: Sequence[Any],
    slice_height_m: float,
    time_points: Sequence[float],
) -> list[ObstructionPeriod]:
    """Group *time_points* by the obstruction set FDS has at each of them.

    With sorted toggles T_1 < ... < T_n, period k covers [T_k, T_k+1) and a
    time point belongs to period ``bisect_right(T, time)``: a toggle exactly
    on a point applies at that point. Periods without a point are skipped, and
    neighbouring periods with the same present pieces are merged. Without
    toggles the result is one period holding every point and every piece.
    """
    points = sorted(float(t) for t in time_points)
    if not points:
        return []
    toggles = toggle_times(collection, slice_height_m, points[-1])
    grouped: dict[int, list[float]] = {}
    for time in points:
        grouped.setdefault(bisect_right(toggles, time), []).append(time)
    periods: list[ObstructionPeriod] = []
    previous: frozenset[int] | None = None
    for index in sorted(grouped):
        present = _present(collection, slice_height_m, grouped[index][0])
        ids = frozenset(id(sub) for obstruction in present for sub in obstruction)
        if previous == ids:
            last = periods[-1]
            periods[-1] = ObstructionPeriod(
                (*last.time_points, *grouped[index]), last.obstructions
            )
            continue
        periods.append(ObstructionPeriod(tuple(grouped[index]), present))
        previous = ids
    return periods


def slice_global_coordinates(slc: Any) -> tuple[np.ndarray, np.ndarray] | None:
    """Return the uniform (x, y) coordinates of a horizontal FDS slice.

    fdsreader's ``slc.get_coordinates()`` only concatenates unique coordinate
    ticks across subslices without resampling coarser meshes, producing a
    non-uniform grid when meshes have different resolutions (mixed meshes, #928).
    In contrast, ``slc.to_global()`` builds a uniform Cartesian grid using the
    finest step size across all meshes (step_sizes_min).

    This function extracts that exact finest uniform grid from the slice's
    subslice meshes without loading or allocating the 3D/4D data array.
    """
    subslices = getattr(slc, "_subslices", None)
    if not subslices:
        return None

    orientation = getattr(slc, "orientation", None)
    if orientation != 3:
        return None

    coord_min = {"x": float("inf"), "y": float("inf")}
    coord_max = {"x": float("-inf"), "y": float("-inf")}
    step_sizes_min = {"x": float("inf"), "y": float("inf")}

    for sslc in subslices.values():
        mesh = getattr(sslc, "mesh", None)
        if mesh is None or not hasattr(sslc, "get_coordinates"):
            return None
        coords = sslc.get_coordinates(ignore_cell_centered=True)
        mesh_coords = getattr(mesh, "coordinates", None)
        if mesh_coords is None:
            return None
        for dim in ("x", "y"):
            mesh_nodes = coords.get(dim)
            if mesh_nodes is None or len(mesh_nodes) == 0:
                return None
            coord_min[dim] = min(float(mesh_nodes[0]), coord_min[dim])
            coord_max[dim] = max(float(mesh_nodes[-1]), coord_max[dim])
            dim_coords = mesh_coords.get(dim)
            if dim_coords is None or len(dim_coords) < 2:
                return None
            step = float(dim_coords[1] - dim_coords[0])
            if step <= 0:
                return None
            step_sizes_min[dim] = min(step, step_sizes_min[dim])

    cell_centered = getattr(slc, "cell_centered", False)
    coords_out: dict[str, np.ndarray] = {}
    for dim in ("x", "y"):
        span = coord_max[dim] - coord_min[dim]
        d_min = step_sizes_min[dim]
        if d_min <= 0 or not math.isfinite(d_min) or span < 0:
            return None
        steps = max(int(round(span / d_min)), 1) + (0 if cell_centered else 1)
        if cell_centered:
            half = d_min / 2.0
            coords_out[dim] = np.linspace(
                coord_min[dim] + half, coord_max[dim] - half, steps
            )
        else:
            coords_out[dim] = np.linspace(coord_min[dim], coord_max[dim], steps)

    return coords_out["x"], coords_out["y"]


def align_vismap_grid(vis: Any) -> bool:
    """Ensure VisMap's coordinate grid matches the uniform global extinction slice.

    When FDS meshes have mixed resolutions, ``VisMap.read_fds_data`` assigns
    non-uniform coordinates from ``slc.get_coordinates()``. This function aligns
    ``vis.all_x_coords`` and ``vis.all_y_coords`` to the uniform Cartesian grid
    of ``slc.to_global()``, updates ``vis.fds_grid_shape`` and ``vis.cell_size``,
    and rebuilds the obstruction array if a mismatch was detected.

    Returns True if alignment was performed (grid was updated), False otherwise.
    """
    slc = getattr(vis, "slc", None)
    if slc is None:
        return False

    uniform_coords = slice_global_coordinates(slc)
    if uniform_coords is None:
        return False

    gx, gy = uniform_coords
    cur_x = getattr(vis, "all_x_coords", None)
    cur_y = getattr(vis, "all_y_coords", None)

    if (
        cur_x is not None
        and cur_y is not None
        and len(cur_x) == len(gx)
        and len(cur_y) == len(gy)
        and np.allclose(cur_x, gx, atol=1e-5)
        and np.allclose(cur_y, gy, atol=1e-5)
    ):
        return False

    vis.all_x_coords = gx
    vis.all_y_coords = gy
    vis.fds_grid_shape = (len(gx), len(gy))
    extent = getattr(vis, "extent", None)
    if extent is not None and getattr(extent, "shape", None) == (2, 2):
        dx = float(extent[0, 1] - extent[0, 0]) / len(gx)
        dy = float(extent[1, 1] - extent[1, 0]) / len(gy)
    else:
        dx = float(gx[1] - gx[0]) if len(gx) > 1 else 1.0
        dy = float(gy[1] - gy[0]) if len(gy) > 1 else 1.0
    vis.cell_size = (dx, dy)
    if hasattr(vis, "build_obstructions_array"):
        vis.build_obstructions_array()
    if hasattr(vis, "_invalidate_results"):
        vis._invalidate_results()
    return True


def validate_vismap_shapes(vis: Any) -> None:
    """Validate that VisMap's spatial arrays match the extinction array dimensions.

    Raises ValueError with a clear, descriptive explanation if spatial masks and
    extinction slices have mismatched dimensions.
    """
    all_x = getattr(vis, "all_x_coords", None)
    all_y = getattr(vis, "all_y_coords", None)
    if all_x is None or all_y is None or len(all_x) == 0 or len(all_y) == 0:
        return

    expected_spatial_shape = (len(all_y), len(all_x))

    obstructions = getattr(vis, "obstructions_array", None)
    if obstructions is not None and getattr(obstructions, "size", 0) > 0:
        if obstructions.shape != expected_spatial_shape:
            raise ValueError(
                f"VisMap spatial array shape mismatch: obstructions_array has shape "
                f"{obstructions.shape}, expected {expected_spatial_shape} from coordinates "
                f"({len(all_y)} y, {len(all_x)} x)."
            )

    angle_dict = getattr(vis, "all_sign_angle_array_dict", {})
    non_concealed_dict = getattr(vis, "all_sign_non_concealed_cells_array_dict", {})
    for sign_id, angle_arr in angle_dict.items():
        if (
            isinstance(angle_arr, np.ndarray)
            and angle_arr.shape != expected_spatial_shape
        ):
            raise ValueError(
                f"VisMap spatial array shape mismatch for sign {sign_id}: angle array has shape "
                f"{angle_arr.shape}, expected {expected_spatial_shape} from coordinates "
                f"({len(all_y)} y, {len(all_x)} x)."
            )

    for sign_id, nc_arr in non_concealed_dict.items():
        if isinstance(nc_arr, np.ndarray) and nc_arr.shape != expected_spatial_shape:
            raise ValueError(
                f"VisMap spatial array shape mismatch for sign {sign_id}: non-concealed array has shape "
                f"{nc_arr.shape}, expected {expected_spatial_shape} from coordinates "
                f"({len(all_y)} y, {len(all_x)} x)."
            )

    time_points = getattr(vis, "vismap_time_points", None)
    if (
        time_points is not None
        and len(time_points) > 0
        and hasattr(vis, "get_extco_array_at_time")
    ):
        try:
            extco_array = vis.get_extco_array_at_time(float(time_points[0]))
            if (
                isinstance(extco_array, np.ndarray)
                and extco_array.shape != (len(all_x), len(all_y))
            ):
                raise ValueError(
                    f"VisMap extinction array dimension mismatch: get_extco_array_at_time() returned "
                    f"shape {extco_array.shape} (transposed to {extco_array.T.shape}), but spatial "
                    f"coordinates define shape {expected_spatial_shape} ({len(all_y)} y, {len(all_x)} x). "
                    "This occurs when FDS simulation meshes have mixed resolutions and the grid was not aligned (#928)."
                )
        except Exception as exc:
            if isinstance(exc, ValueError) and "dimension mismatch" in str(exc):
                raise

