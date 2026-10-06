"""Visibility model wrapping fdsvismap for sign-based route rejection."""

from __future__ import annotations

import hashlib
import json
import logging
import math
from pathlib import Path
from typing import Protocol

import numpy as np
from shapely.geometry import Polygon

from . import fds_sampling
from .geometry import node_position


class _VisBackend(Protocol):
    """What VisibilityModel needs from its backend.

    Satisfied by the npz-backed ``_VisMapCache`` and by ``_LiveVisMap``, the
    adapter around a live ``fdsvismap.VisMap`` (the uncached clear-air route).
    """

    def wp_is_visible(
        self, time: float, x: float, y: float, waypoint_id: int
    ) -> bool: ...

    def visibility_to_wp(
        self, time: float, x: float, y: float, waypoint_id: int
    ) -> float: ...


_logger = logging.getLogger(__name__)

# How far a sign can be read in clear air, the fdsvismap default and the value
# of Börger et al. (2024). A sign may override it with ``max_distance``.
DEFAULT_MAX_SIGN_DISTANCE_M = 30.0


def _default_sign(entry: dict) -> dict | None:
    """A reflective, omni-directional sign at the node's centroid.

    alpha is left None on purpose.  fdsvismap reads alpha as a half-plane of
    readability, so a guessed bearing silently blanks the sign for every agent
    on the wrong side however clear the air, whereas None means omni-directional
    and merely omits the orientation effect.
    """
    coords = entry.get("coordinates")
    if not coords or len(coords) < 3:
        return None
    # Configs with unusable polygons simulate fine -- the stage setup skips
    # them -- so a node that cannot yield a position gets no sign rather than
    # aborting the run the moment visibility is switched on.
    #
    # node_position, not the raw centroid: on a non-convex stage the centroid
    # falls outside the polygon, which would bury this sign in a wall where no
    # agent can read it. It is also the point the route graph routes to, and
    # the two must agree or a node is seen from somewhere it is never routed.
    try:
        x, y = node_position(Polygon(coords))
    except Exception as exc:
        _logger.warning("Cannot synthesise a sign from %r: %s", coords, exc)
        return None
    return {"x": x, "y": y, "alpha": None, "c": 3}


def extract_sign_descriptors(raw_config: dict) -> dict[str, dict]:
    """Return {node_id: {x, y, alpha, c}} for every exit, crossing and waypoint.

    Nodes with an authored 'sign' keep it verbatim; the rest get a default so
    that no routable stage escapes smoke-dependent legibility.
    """
    descriptors: dict[str, dict] = {}
    for section in ("exits", "checkpoints", "waypoints"):
        for node_id, data in raw_config.get(section, {}).items():
            sign = data.get("sign") or _default_sign(data)
            if sign is not None:
                descriptors[node_id] = sign
    return descriptors


def _check_max_sign_distance(max_sign_distance_m: float) -> None:
    """Reject a global reading distance that is not finite and positive."""
    if not (math.isfinite(max_sign_distance_m) and max_sign_distance_m > 0):
        raise ValueError(
            "max_sign_distance_m must be finite and positive, "
            f"got {max_sign_distance_m}"
        )


def _sign_caps(sign_descriptors: dict[str, dict]) -> dict[int, float]:
    """Per-waypoint reading distances, for the signs that set ``max_distance``."""
    caps: dict[int, float] = {}
    for wp_id, (node_id, sign) in enumerate(sign_descriptors.items()):
        cap = sign.get("max_distance")
        if cap is None:
            continue
        if not (math.isfinite(float(cap)) and float(cap) > 0):
            raise ValueError(
                f"sign of {node_id!r}: max_distance must be finite and "
                f"positive, got {cap}"
            )
        caps[wp_id] = float(cap)
    return caps


def _apply_distance_caps(
    vis, sign_descriptors: dict[str, dict], max_sign_distance_m: float
) -> None:
    """Cap C/K at the reading distance, per sign where one is given.

    fdsvismap holds one ``max_vis`` and applies it to C/K before the view angle
    and obstructions, inside ``_get_visibility_array``. A sign with its own
    ``max_distance`` swaps that value in for its own waypoint only, so the
    order of operations stays fdsvismap's. This patches a private method,
    which is why fdsvismap is pinned exactly. Workaround: no upstream issue
    yet; regression test ``tests/test_visibility.py`` (per-sign caps); remove,
    and relax the pin, once fdsvismap takes a ``max_vis`` per sign.
    """
    _check_max_sign_distance(max_sign_distance_m)
    vis.set_visibility_bounds(vis.min_vis, max_sign_distance_m)
    caps = _sign_caps(sign_descriptors)
    if not caps:
        return
    base = vis._get_visibility_array

    def capped(waypoint_id, time):
        default = vis.max_vis
        vis.max_vis = caps.get(waypoint_id, default)
        try:
            return base(waypoint_id, time)
        finally:
            vis.max_vis = default

    vis._get_visibility_array = capped


_EXTINCTION_QUANTITY = "SOOT EXTINCTION COEFFICIENT"


def _extinction_slice_index(fds_dir: str, slice_height_m: float) -> int:
    """Index of the extinction slice that sign legibility reads.

    The slice is chosen by ``fds_sampling.select_horizontal_slice``, the rule
    the walking-speed and FED samplers use, and handed to fdsvismap by its
    index in ``Simulation.slices``. fdsvismap 0.3.1 applies the same rule
    itself (fdsvismap#55); passing the index keeps one owner of the rule and
    its height-mismatch warning.
    """
    from fdsreader import Simulation

    collection = Simulation(fds_dir).slices
    slices = list(collection)
    extinction = collection.filter_by_quantity(_EXTINCTION_QUANTITY)
    chosen = fds_sampling.select_horizontal_slice(
        extinction, slice_height_m, _EXTINCTION_QUANTITY, fds_dir
    )
    return next(i for i, s in enumerate(slices) if s is chosen)


def _vismap_time_points(t_end: float, time_step_s: float) -> list[float]:
    """Times 0, step, 2 step, ... before *t_end*, then *t_end* itself.

    No point lies past the last FDS frame: a step that does not divide T_END
    would otherwise add a point after it, which fdsvismap answers with the
    last frame (0.3.2) or rejects (fdsvismap#86).  The filter also drops a
    point that ``arange`` rounds onto or past *t_end*.
    """
    t_end = float(t_end)
    points = np.arange(0.0, t_end, time_step_s)
    return [*points[points < t_end * (1 - 1e-9)].tolist(), t_end]


def _build_vismap(
    fds_dir: str,
    sign_descriptors: dict[str, dict],
    time_step_s: float,
    slice_height_m: float,
    max_sign_distance_m: float = DEFAULT_MAX_SIGN_DISTANCE_M,
):
    from fdsvismap import VisMap

    vis = VisMap()
    vis.read_fds_data(
        fds_dir,
        fds_slc_height=slice_height_m,
        fds_slc_index=_extinction_slice_index(fds_dir, slice_height_m),
    )
    vis.set_time_points(_vismap_time_points(vis.fds_time_points.max(), time_step_s))
    for wp_id, (node_id, sign) in enumerate(sign_descriptors.items()):
        alpha = sign.get("alpha")
        vis.add_sign(
            wp_id,
            float(sign["x"]),
            float(sign["y"]),
            c=float(sign.get("c", 3)),
            # None is meaningful: fdsvismap reads it as omni-directional.
            alpha=None if alpha is None else float(alpha),
        )
    # fdsvismap clips visibility inside the array build, so the caps have to
    # be in place before compute_all.
    _apply_distance_caps(vis, sign_descriptors, max_sign_distance_m)
    vis.compute_all(view_angle=True, obstructions=True, aa=True)
    return vis


def _make_meta(
    fds_dir: str,
    sign_descriptors: dict[str, dict],
    time_step_s: float,
    slice_height_m: float,
    max_sign_distance_m: float = DEFAULT_MAX_SIGN_DISTANCE_M,
) -> dict:
    """Build a metadata dict that uniquely identifies a vismap cache.

    Includes the resolved FDS directory so that caches built from different
    FDS datasets are never silently reused even if the waypoint list matches.
    """
    waypoints = [
        [
            node_id,
            sign.get("x"),
            sign.get("y"),
            sign.get("alpha"),
            sign.get("c", 3),
            sign.get("max_distance"),
        ]
        for node_id, sign in sign_descriptors.items()
    ]
    return {
        "fds_dir": str(Path(fds_dir).resolve()),
        "waypoints": waypoints,
        "time_step_s": time_step_s,
        "slice_height_m": slice_height_m,
        "max_sign_distance_m": max_sign_distance_m,
        # Bumped when the arrays change shape or meaning. Caches written before
        # sighting distances were stored hold booleans only, and must be
        # rebuilt rather than read as metres. Format 3 caps at the sign's
        # reading distance instead of the domain diagonal. Format 4 reads the
        # extinction slice nearest the height, not the first one declared.
        # Format 5 is fdsvismap 0.3.1, where a directional sign is legible
        # from its own cell; earlier caches hold NaN there.
        # Format 6 ends the time points at the last FDS frame and stores the
        # extinction slice's output interval; earlier caches may hold a point
        # past it.
        "format": 6,
    }


def _blocked_runs(walkable, x_coords, y_coords, cell_size_m: float):
    """Yield (x1, x2, y1, y2) rectangles covering every non-walkable cell.

    Consecutive blocked cells in a row are merged into one rectangle, so a long
    wall costs one call rather than one per cell, and the result still follows
    an arbitrary polygon outline to the resolution of the grid.
    """
    from shapely.geometry import Point

    half = cell_size_m / 2
    for y in y_coords:
        run_start = None
        for i, x in enumerate(x_coords):
            blocked = not walkable.covers(Point(float(x), float(y)))
            if blocked and run_start is None:
                run_start = x
            elif not blocked and run_start is not None:
                yield (
                    float(run_start) - half,
                    float(x_coords[i - 1]) + half,
                    float(y) - half,
                    float(y) + half,
                )
                run_start = None
        if run_start is not None:
            yield (
                float(run_start) - half,
                float(x_coords[-1]) + half,
                float(y) - half,
                float(y) + half,
            )


class _VisMapCache:
    """Lightweight visibility lookup backed by pre-computed numpy arrays.

    Answers the ``_VisBackend`` queries without carrying any of the heavy FDS
    reader state or requiring pickle.
    """

    def __init__(
        self,
        time_points: np.ndarray,
        x_coords: np.ndarray,
        y_coords: np.ndarray,
        vis: np.ndarray,  # shape (T, N_wp, H, W), dtype bool
        metres: np.ndarray | None = None,  # same shape, float: sighting distance
        output_interval_s: float | None = None,  # FDS output interval, None: clear air
    ) -> None:
        self._time_points = time_points
        self.output_interval_s = output_interval_s
        self._x_coords = x_coords
        self._y_coords = y_coords
        self._vis = vis
        self._metres = metres

    @staticmethod
    def _nearest(coords: np.ndarray, value: float) -> int:
        idx = int(np.searchsorted(coords, value))
        if idx <= 0:
            return 0
        if idx >= len(coords):
            return len(coords) - 1
        return (
            idx if abs(coords[idx] - value) < abs(value - coords[idx - 1]) else idx - 1
        )

    def wp_is_visible(self, time: float, x: float, y: float, waypoint_id: int) -> bool:
        t_id = self._nearest(self._time_points, time)
        x_id = self._nearest(self._x_coords, x)
        y_id = self._nearest(self._y_coords, y)
        return bool(self._vis[t_id, waypoint_id, y_id, x_id])

    def visibility_to_wp(
        self, time: float, x: float, y: float, waypoint_id: int
    ) -> float:
        if self._metres is None:
            raise RuntimeError("this cache holds no sighting distances")
        t_id = self._nearest(self._time_points, time)
        x_id = self._nearest(self._x_coords, x)
        y_id = self._nearest(self._y_coords, y)
        return float(self._metres[t_id, waypoint_id, y_id, x_id])


class _LiveVisMap:
    """Adapter from a live ``fdsvismap.VisMap`` to ``_VisBackend``.

    The one place that names fdsvismap's per-cell query methods. Answers are
    fdsvismap's own, in float64; only a cache stores float16.
    """

    def __init__(self, vismap) -> None:
        self.vismap = vismap

    def wp_is_visible(self, time: float, x: float, y: float, waypoint_id: int) -> bool:
        return bool(
            self.vismap.sign_is_visible(time=time, x=x, y=y, sign_id=waypoint_id)
        )

    def visibility_to_wp(
        self, time: float, x: float, y: float, waypoint_id: int
    ) -> float:
        return float(
            self.vismap.get_visibility_to_sign(time=time, x=x, y=y, sign_id=waypoint_id)
        )


def _vis_bool_array(vis) -> np.ndarray:
    """Convert VisMap's nested list to a (T, N_wp, H, W) bool array."""
    return np.array(
        [list(ts) for ts in vis.all_time_all_sign_vismap_list],
        dtype=bool,
    )


def _vis_metre_array(vis) -> np.ndarray:
    """Sighting distance in metres per (time, waypoint, cell).

    The product below is the one ``VisMap.get_visibility_to_sign`` forms per
    cell: Jin's c / K_ave along the sight line, then the sign's readable
    half-plane, then obstructions. It is duplicated here only to vectorise it --
    calling the public method per cell would be H*W*T*N calls. fdsvismap 0.3.2
    has no vectorised masked accessor, so this is the one place that mirrors it.
    No upstream issue yet; regression test
    ``tests/test_fdsvismap_adapter.py``, which compares it with
    ``get_visibility_to_sign``; remove once fdsvismap exposes the masked array.

    float16 gives 0.1 m resolution at these magnitudes, which is far finer than
    the question ("can this route be walked") needs.
    """
    frames = []
    for time in vis.vismap_time_points:
        per_wp = []
        for wp_id in vis.all_sign_dict:
            masked = (
                vis.all_sign_angle_array_dict[wp_id]
                * vis._get_visibility_array(wp_id, time)
                * vis.all_sign_non_concealed_cells_array_dict[wp_id]
            )
            per_wp.append(masked)
        frames.append(per_wp)
    return np.array(frames, dtype=np.float16)


def _save_vismap_cache(
    path: Path,
    vis,
    arrays: np.ndarray,
    meta: dict,
    metres: np.ndarray | None = None,
    output_interval_s: float | None = None,
) -> None:
    """Serialise VisMap arrays to an npz file (no pickle, safe to load)."""
    npz_path = path.with_suffix(".npz")
    if path.suffix and path.suffix != ".npz":
        _logger.warning(
            "Cache path %r has suffix %r; writing to %r instead.",
            str(path),
            path.suffix,
            str(npz_path),
        )
    npz_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        npz_path,
        time_points=vis.vismap_time_points,
        x_coords=vis.all_x_coords,
        y_coords=vis.all_y_coords,
        vis=arrays,
        metres=(metres if metres is not None else np.zeros((0,), dtype=np.float16)),
        # NaN for clear air, which has no FDS output.
        output_interval_s=np.array(
            np.nan if output_interval_s is None else output_interval_s
        ),
        meta=np.array(json.dumps(meta)),
    )


def _resolve_vis(
    fds_dir: str,
    sign_descriptors: dict[str, dict],
    time_step_s: float,
    slice_height_m: float,
    cache: Path | None,
    force_recompute: bool,
    expected_meta: dict,
    max_sign_distance_m: float = DEFAULT_MAX_SIGN_DISTANCE_M,
) -> _VisMapCache:
    """Return a _VisMapCache, loading from disk or computing from FDS data."""
    if not force_recompute and cache:
        cached = _load_vismap_cache(cache, expected_meta)
        if cached is not None:
            return cached
    return _build_cache_from_fds(
        fds_dir,
        sign_descriptors,
        time_step_s,
        slice_height_m,
        cache,
        expected_meta,
        max_sign_distance_m,
    )


def _build_cache_from_fds(
    fds_dir: str,
    sign_descriptors: dict[str, dict],
    time_step_s: float,
    slice_height_m: float,
    cache: Path | None,
    expected_meta: dict,
    max_sign_distance_m: float = DEFAULT_MAX_SIGN_DISTANCE_M,
) -> _VisMapCache:
    """Build VisMapCache from FDS data and optionally save to disk."""
    vis_obj = _build_vismap(
        fds_dir, sign_descriptors, time_step_s, slice_height_m, max_sign_distance_m
    )
    arrays = _vis_bool_array(vis_obj)
    metres = _vis_metre_array(vis_obj)
    # The extinction slice's own spacing, not the vismap step: the horizon
    # window has to match the one the preflight and the slice samplers use.
    interval = fds_sampling._output_interval(vis_obj.fds_time_points)
    result = _VisMapCache(
        time_points=vis_obj.vismap_time_points,
        x_coords=vis_obj.all_x_coords,
        y_coords=vis_obj.all_y_coords,
        vis=arrays,
        metres=metres,
        output_interval_s=interval,
    )
    if cache:
        _save_vismap_cache(
            cache,
            vis_obj,
            arrays,
            expected_meta,
            metres=metres,
            output_interval_s=interval,
        )
    return result


def _load_vismap_cache(path: Path, expected_meta: dict) -> _VisMapCache | None:
    """Load cached arrays; return None on metadata mismatch or read error."""
    npz_path = path.with_suffix(".npz")
    if path.suffix and path.suffix != ".npz":
        _logger.warning(
            "Cache path %r has suffix %r; looking for %r instead.",
            str(path),
            path.suffix,
            str(npz_path),
        )
    if not npz_path.exists():
        return None
    try:
        with np.load(npz_path, allow_pickle=False) as data:
            if json.loads(str(data["meta"])) != expected_meta:
                _logger.info("Vismap cache metadata mismatch — recomputing.")
                return None
            if "output_interval_s" not in data.files:
                _logger.info("Vismap cache has no output interval — recomputing.")
                return None
            metres = data["metres"] if "metres" in data.files else None
            if metres is not None and metres.size == 0:
                metres = None
            interval = float(data["output_interval_s"])
            return _VisMapCache(
                time_points=data["time_points"],
                x_coords=data["x_coords"],
                y_coords=data["y_coords"],
                vis=data["vis"],
                metres=metres,
                output_interval_s=None if np.isnan(interval) else interval,
            )
    except Exception as e:
        _logger.warning("Failed to load vismap cache: %s", e)
        return None


def _make_clear_air_meta(
    walkable,
    sign_descriptors: dict[str, dict],
    cell_size_m: float,
    extinction: float,
    max_sign_distance_m: float = DEFAULT_MAX_SIGN_DISTANCE_M,
) -> dict:
    """Identify a clear-air vismap cache by what the grid is computed from."""
    meta = _make_meta("", sign_descriptors, 0.0, 0.0, max_sign_distance_m)
    meta["fds_dir"] = "<clear air>"
    meta["walkable_wkt_hash"] = hashlib.sha256(walkable.wkt.encode()).hexdigest()
    meta["cell_size_m"] = cell_size_m
    meta["extinction_per_m"] = extinction
    return meta


def _grid_bounds(
    x_coords: np.ndarray, y_coords: np.ndarray
) -> tuple[float, float, float, float]:
    """Return the (x_min, x_max, y_min, y_max) the vismap cells cover [m].

    Each value of the grid stands for the cell around it, so the grid reaches
    half a spacing past its first and last coordinate. A point beyond that
    has no cell of its own: the nearest-cell lookup would clamp it onto the
    edge cell (#426).
    """

    def span(coords: np.ndarray) -> tuple[float, float]:
        values = np.asarray(coords, dtype=float)
        if values.size < 2:
            return float(values[0]), float(values[-1])
        return (
            float(values[0] - (values[1] - values[0]) / 2),
            float(values[-1] + (values[-1] - values[-2]) / 2),
        )

    return (*span(x_coords), *span(y_coords))


def _distance_outside(
    bounds: tuple[float, float, float, float], x: float, y: float
) -> float:
    """Distance from (x, y) to the rectangle *bounds*; 0 inside or on it."""
    x_min, x_max, y_min, y_max = bounds
    dx = max(x_min - x, 0.0, x - x_max)
    dy = max(y_min - y, 0.0, y - y_max)
    return float(math.hypot(dx, dy))


def _sign_positions(
    sign_descriptors: dict[str, dict],
) -> dict[str, tuple[float, float]]:
    """Where each sign is, for distance queries that must not need the backend."""
    return {
        node_id: (float(sign["x"]), float(sign["y"]))
        for node_id, sign in sign_descriptors.items()
        if sign.get("x") is not None and sign.get("y") is not None
    }


class VisibilityModel:
    """Wraps a pre-computed VisMap to answer per-node sign-visibility queries.

    alpha convention (compass bearing, degrees from north CW):
      90  = visible from east  (sign on west wall, seen by agents to its right)
      270 = visible from west  (sign on east wall, seen by agents to its left)
      180 = visible from south (sign at junction top, seen by agents below)

    Every exit, crossing and waypoint carries a descriptor -- authored or
    synthesised at the node centroid -- so only nodes outside that set (spawn
    areas, and nodes whose geometry was unusable) are unconditionally visible.

    Cache format: numpy npz containing the visibility arrays and metadata.
    The cache is safe to load (no pickle / no arbitrary code execution).
    Metadata mismatches trigger an automatic recompute and cache refresh.

    A model built from FDS output stores time points up to the last frame of
    the extinction slice and raises ``FdsHorizonError`` for a query more than
    one output interval of that slice past it, the window the preflight and
    the slice samplers use; unless *allow_horizon_hold* is set: then the last
    time point is held and one warning is logged.  A clear-air model is
    time-invariant and never raises.
    """

    # (last time point, FDS output interval) of an FDS-built model; None for
    # clear air.
    _horizon: tuple[float, float] | None = None
    _allow_horizon_hold = False
    # The settings the model was built with (for the run manifest).
    parameters: dict[str, object] | None = None
    _warned_horizon = False
    # Area the FDS vismap grid covers; None for clear air, whose grid is the
    # walkable area's bounding box and so holds every agent by construction.
    _grid: tuple[float, float, float, float] | None = None
    _require_fds_coverage = False
    _reading_caps: dict[str, float] | None = None

    def __init__(
        self,
        fds_dir: str | Path,
        sign_descriptors: dict[str, dict],
        *,
        cache_path: str | Path | None = None,
        time_step_s: float = 10.0,
        slice_height_m: float = 1.6,
        force_recompute: bool = False,
        max_sign_distance_m: float = DEFAULT_MAX_SIGN_DISTANCE_M,
        allow_horizon_hold: bool = False,
        require_fds_coverage: bool = False,
    ) -> None:
        cache = Path(cache_path) if cache_path else None
        _check_max_sign_distance(max_sign_distance_m)
        _sign_caps(sign_descriptors)
        expected_meta = _make_meta(
            str(fds_dir),
            sign_descriptors,
            time_step_s,
            slice_height_m,
            max_sign_distance_m,
        )

        cache_obj = _resolve_vis(
            str(fds_dir),
            sign_descriptors,
            time_step_s,
            slice_height_m,
            cache,
            force_recompute,
            expected_meta,
            max_sign_distance_m,
        )
        if cache_obj.output_interval_s is None:
            raise ValueError(
                f"vismap built from {fds_dir} carries no FDS output interval"
            )
        self._vis: _VisBackend = cache_obj
        times = np.asarray(cache_obj._time_points, dtype=float)
        self._horizon = (float(times[-1]), cache_obj.output_interval_s)
        self._allow_horizon_hold = allow_horizon_hold
        # Map node_id → internal waypoint index (insertion order preserved)
        self._wp_ids: dict[str, int] = {
            node_id: wp_id for wp_id, node_id in enumerate(sign_descriptors)
        }
        self._sign_xy = _sign_positions(sign_descriptors)
        self.parameters = {
            "kind": "smoky",
            "time_step_s": time_step_s,
            "slice_height_m": slice_height_m,
            "max_sign_distance_m": max_sign_distance_m,
        }
        self._grid = _grid_bounds(self._vis._x_coords, self._vis._y_coords)
        self._require_fds_coverage = require_fds_coverage
        self._reading_caps = {
            node_id: float(sign.get("max_distance") or max_sign_distance_m)
            for node_id, sign in sign_descriptors.items()
        }
        self._check_signs_in_grid()

    @property
    def from_fds(self) -> bool:
        """True for a model built from an FDS run, False for clear air."""
        return self._horizon is not None

    def signs_outside_grid(self) -> dict[str, float]:
        """Return {node_id: distance to the grid [m]} of signs off the vismap grid.

        Empty for a clear-air model. fdsvismap 0.2.1-0.3.2 snaps the ray origin of
        such a sign onto the nearest edge cell while keeping the true distance,
        so the part of the sight line outside the grid takes the mean K of the
        part inside. Workaround: report it (warning, or error with
        ``require_fds_coverage``); no upstream issue yet; regression test
        ``tests/test_fds_domain.py``; remove once fdsvismap treats the part
        outside its grid as clear air.
        """
        if self._grid is None:
            return {}
        outside = {
            node_id: _distance_outside(self._grid, x, y)
            for node_id, (x, y) in self._sign_xy.items()
        }
        return {node_id: d for node_id, d in outside.items() if d > 0.0}

    def _check_signs_in_grid(self) -> None:
        """Warn, or raise in strict mode, for every sign off the vismap grid."""
        outside = self.signs_outside_grid()
        if not outside:
            return
        listed = ", ".join(f"{node} ({d:.2f} m)" for node, d in outside.items())
        message = (
            f"{len(outside)} sign(s) lie outside the FDS extinction slice that "
            f"sign visibility is computed on, by the distance given: {listed}. "
            "fdsvismap casts their sight lines from the nearest grid edge."
        )
        if self._require_fds_coverage:
            raise fds_sampling.FdsDomainError(
                message + " Extend the FDS meshes over the signs, or run "
                "without --require-fds-coverage."
            )
        _logger.warning(message)

    def in_grid(self, x: float, y: float) -> bool:
        """Return whether (x, y) lies on the vismap grid (always for clear air)."""
        return self._grid is None or _distance_outside(self._grid, x, y) == 0.0

    def _sight_outside_grid(
        self, time: float, x: float, y: float, node_id: str
    ) -> bool:
        """Clear-air sight for an observer off the grid (#426), as FDS+Evac.

        FDS+Evac reads K = 0 outside the fire meshes, also along a sight line,
        so an observer outside sees a sign within its reading distance,
        measured from the observer, not from the grid edge. Strict mode
        raises instead.
        """
        if self._require_fds_coverage:
            raise fds_sampling.FdsDomainError(
                fds_sampling.domain_error_message("sign visibility", time, x, y)
            )
        distance = self.distance_to_node(x, y, node_id)
        caps = self._reading_caps or {}
        cap = caps.get(node_id, DEFAULT_MAX_SIGN_DISTANCE_M)
        return distance is not None and distance <= cap

    @classmethod
    def clear_air(
        cls,
        walkable,
        sign_descriptors: dict[str, dict],
        *,
        cell_size_m: float = 0.5,
        extinction_per_m: float = 0.0,
        cache_path: str | Path | None = None,
        max_sign_distance_m: float = DEFAULT_MAX_SIGN_DISTANCE_M,
    ) -> VisibilityModel:
        """Build a model for a scene that has geometry but no fire.

        ``fdsvismap`` normally takes its grid, extinction field and obstructions
        from an FDS run.  Only the field has to: :meth:`VisMap.set_grid` and
        :meth:`VisMap.set_uniform_extco` supply the other two, so a clear-air
        deck is evaluated by the same ray casting, view angle and ``max_vis``
        handling as a fire scene rather than by an approximation written here.

        Obstructions come from *walkable*: every grid cell whose centre is
        outside the walkable polygon blocks sight.  Cells are emitted as runs of
        rectangles per row, which is what ``add_visual_obstruction`` accepts and
        keeps arbitrary wall shapes exact to the grid.

        ``cell_size_m`` is the resolution the scene is rasterised at, and it
        matters.  A cell blocks sight when its centre lies outside *walkable*,
        so **a wall thinner than one cell disappears** and sight passes through
        it -- the same property an FDS mesh has, for the same reason.  An FDS
        deck inherits the resolution from its mesh; here it has to be chosen.
        Pick it below the thinnest wall that must block: at 0.5 m the 0.4 m
        walls of ``assets/blind_spawn_discovery`` vanish entirely, while 0.25 m
        resolves them.  Cost grows as the inverse square, so halving it
        quadruples the build -- which is what ``cache_path`` is for: the grid
        depends only on the geometry, the signs and the resolution, none of
        which change between runs of a deck.
        """
        from fdsvismap import VisMap

        if cell_size_m <= 0:
            raise ValueError(f"cell_size_m must be positive, got {cell_size_m}")
        min_x, min_y, max_x, max_y = walkable.bounds
        x_coords = np.arange(min_x + cell_size_m / 2, max_x, cell_size_m)
        y_coords = np.arange(min_y + cell_size_m / 2, max_y, cell_size_m)
        if x_coords.size < 2 or y_coords.size < 2:
            raise ValueError(
                f"walkable bounds {tuple(round(b, 2) for b in walkable.bounds)} "
                f"span fewer than two cells at cell_size_m={cell_size_m}; "
                "shrink the cell size or check the geometry"
            )

        _check_max_sign_distance(max_sign_distance_m)
        _sign_caps(sign_descriptors)
        expected_meta = _make_clear_air_meta(
            walkable,
            sign_descriptors,
            cell_size_m,
            extinction_per_m,
            max_sign_distance_m,
        )
        clear_air_parameters: dict[str, object] = {
            "kind": "clear-air",
            "cell_size_m": cell_size_m,
            "max_sign_distance_m": max_sign_distance_m,
        }
        cache = Path(cache_path) if cache_path else None
        if cache is not None:
            cached = _load_vismap_cache(cache, expected_meta)
            if cached is not None:
                model = cls.__new__(cls)
                model._vis = cached
                model._wp_ids = {
                    node_id: wp_id for wp_id, node_id in enumerate(sign_descriptors)
                }
                model._sign_xy = _sign_positions(sign_descriptors)
                model.parameters = clear_air_parameters
                return model

        vis = VisMap()
        vis.set_grid(x_coords, y_coords)
        vis.set_uniform_extco(extinction_per_m)
        vis.set_time_points([0.0])
        for wp_id, (_node_id, sign) in enumerate(sign_descriptors.items()):
            alpha = sign.get("alpha")
            vis.add_sign(
                wp_id,
                float(sign["x"]),
                float(sign["y"]),
                c=float(sign.get("c", 3)),
                alpha=None if alpha is None else float(alpha),
            )
        for x1, x2, y1, y2 in _blocked_runs(walkable, x_coords, y_coords, cell_size_m):
            vis.add_visual_obstruction(x1, x2, y1, y2)
        _apply_distance_caps(vis, sign_descriptors, max_sign_distance_m)
        vis.compute_all(view_angle=True, obstructions=True, aa=True)
        if cache is not None:
            _save_vismap_cache(
                cache,
                vis,
                _vis_bool_array(vis),
                expected_meta,
                metres=_vis_metre_array(vis),
            )

        model = cls.__new__(cls)
        model._vis = _LiveVisMap(vis)
        model._wp_ids = {
            node_id: wp_id for wp_id, node_id in enumerate(sign_descriptors)
        }
        model._sign_xy = _sign_positions(sign_descriptors)
        model.parameters = clear_air_parameters
        return model

    def _check_horizon(self, time: float) -> None:
        """Raise, or warn once, when *time* is past the FDS output window."""
        if self._horizon is None:
            return
        last, interval = self._horizon
        if time <= last + interval:
            return
        message = fds_sampling.horizon_error_message(
            "sign visibility", time, last, interval
        )
        if not self._allow_horizon_hold:
            raise fds_sampling.FdsHorizonError(message)
        if self._warned_horizon:
            return
        self._warned_horizon = True
        _logger.warning(
            "Sign visibility past the FDS output (t=%.1f s > %.1f s): holding "
            "the last time point for the rest of the run "
            "(--allow-fds-horizon-hold).",
            time,
            last,
        )

    def node_is_visible(self, time: float, x: float, y: float, node_id: str) -> bool:
        """Return True if the sign at *node_id* is visible from (x, y) at *time*.

        Only nodes outside the descriptor set -- spawn areas, and nodes whose
        geometry could not be turned into a centroid -- return True regardless
        of the smoke.
        """
        wp_id = self._wp_ids.get(node_id)
        if wp_id is None:
            return True
        self._check_horizon(float(time))
        if not self.in_grid(x, y):
            return self._sight_outside_grid(time, x, y, node_id)
        # A clear-air model computes one time point; fdsvismap resolves any
        # query time onto a uniform field itself, so no clamping is needed here.
        return bool(self._vis.wp_is_visible(time=time, x=x, y=y, waypoint_id=wp_id))

    def visibility_to_node(
        self, time: float, x: float, y: float, node_id: str
    ) -> float | None:
        """How far the agent can see toward *node_id*, in metres.

        This is Jin's ``c / K_ave`` with ``K_ave`` averaged along the real sight
        line -- the same aggregation FDS+Evac's ``See_door`` uses, and the
        reason this is worth reading from fdsvismap rather than approximating
        from samples along a walked polyline.

        Returns ``None`` when there is no answer to give: a node with no sign
        descriptor, a backend that holds no distances (an old cache), or a
        masked zero. Zero is ambiguous by construction -- fdsvismap multiplies
        the sight line by the sign's readable half-plane and by obstructions, so
        it means "concealed", "behind the sign" or "smoked out" indistinguishably
        -- and only the last is a statement about whether the route can be
        walked. Callers fall back rather than treat a hidden sign as a wall.
        An observer off the vismap grid also gets ``None`` (#426): the grid
        holds no sight line from there.
        """
        wp_id = self._wp_ids.get(node_id)
        if wp_id is None:
            return None
        self._check_horizon(float(time))
        if not self.in_grid(x, y):
            self._sight_outside_grid(time, x, y, node_id)
            return None
        try:
            metres = self._vis.visibility_to_wp(time=time, x=x, y=y, waypoint_id=wp_id)
        except (RuntimeError, IndexError, KeyError):
            return None
        return metres if metres > 0.0 else None

    def distance_to_node(self, x: float, y: float, node_id: str) -> float | None:
        """Straight-line distance to the sign at *node_id*, or None.

        Computed from the descriptor rather than asked of the backend: a cache
        loaded from disk holds arrays, not the VisMap that could answer, and
        this is the same Euclidean distance ``get_distance_to_sign`` returns.
        Reading it from the backend meant a cached run had no distance, so the
        sight test had nothing to compare against and silently fell back.
        """
        sign = self._sign_xy.get(node_id)
        if sign is None:
            return None
        return float(math.hypot(sign[0] - x, sign[1] - y))
