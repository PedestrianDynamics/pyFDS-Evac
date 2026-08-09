"""Visibility model wrapping fdsvismap for sign-based route rejection."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np
from shapely.geometry import Polygon

_logger = logging.getLogger(__name__)


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
    # them -- so a node that cannot yield a centroid gets no sign rather than
    # aborting the run the moment visibility is switched on.
    try:
        centroid = Polygon(coords).centroid
    except Exception as exc:
        _logger.warning("Cannot synthesise a sign from %r: %s", coords, exc)
        return None
    return {"x": float(centroid.x), "y": float(centroid.y), "alpha": None, "c": 3}


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


def _build_vismap(
    fds_dir: str,
    sign_descriptors: dict[str, dict],
    time_step_s: float,
    slice_height_m: float,
):
    from fdsvismap import VisMap

    vis = VisMap()
    vis.read_fds_data(fds_dir, fds_slc_height=slice_height_m)
    t_max = vis.fds_time_points.max()
    vis.set_time_points(list(np.arange(0, t_max + time_step_s, time_step_s)))
    for wp_id, (node_id, sign) in enumerate(sign_descriptors.items()):
        alpha = sign.get("alpha")
        vis.set_waypoint(
            wp_id,
            float(sign["x"]),
            float(sign["y"]),
            c=float(sign.get("c", 3)),
            # None is meaningful: fdsvismap reads it as omni-directional.
            alpha=None if alpha is None else float(alpha),
        )
    vis.compute_all(view_angle=True, obstructions=True, aa=True)
    return vis


def _make_meta(
    fds_dir: str,
    sign_descriptors: dict[str, dict],
    time_step_s: float,
    slice_height_m: float,
) -> dict:
    """Build a metadata dict that uniquely identifies a vismap cache.

    Includes the resolved FDS directory so that caches built from different
    FDS datasets are never silently reused even if the waypoint list matches.
    """
    waypoints = [
        [node_id, sign.get("x"), sign.get("y"), sign.get("alpha"), sign.get("c", 3)]
        for node_id, sign in sign_descriptors.items()
    ]
    return {
        "fds_dir": str(Path(fds_dir).resolve()),
        "waypoints": waypoints,
        "time_step_s": time_step_s,
        "slice_height_m": slice_height_m,
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

    Mirrors the ``wp_is_visible`` interface of ``fdsvismap.VisMap`` without
    carrying any of the heavy FDS reader state or requiring pickle.
    """

    def __init__(
        self,
        time_points: np.ndarray,
        x_coords: np.ndarray,
        y_coords: np.ndarray,
        vis: np.ndarray,  # shape (T, N_wp, H, W), dtype bool
    ) -> None:
        self._time_points = time_points
        self._x_coords = x_coords
        self._y_coords = y_coords
        self._vis = vis

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


def _vis_bool_array(vis) -> np.ndarray:
    """Convert VisMap's nested list to a (T, N_wp, H, W) bool array."""
    return np.array(
        [list(ts) for ts in vis.all_time_all_wp_vismap_array_list],
        dtype=bool,
    )


def _save_vismap_cache(path: Path, vis, arrays: np.ndarray, meta: dict) -> None:
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
) -> "_VisMapCache":
    """Return a _VisMapCache, loading from disk or computing from FDS data."""
    if not force_recompute and cache:
        cached = _load_vismap_cache(cache, expected_meta)
        if cached is not None:
            return cached
    return _build_cache_from_fds(
        fds_dir, sign_descriptors, time_step_s, slice_height_m, cache, expected_meta
    )


def _build_cache_from_fds(
    fds_dir: str,
    sign_descriptors: dict[str, dict],
    time_step_s: float,
    slice_height_m: float,
    cache: Path | None,
    expected_meta: dict,
) -> _VisMapCache:
    """Build VisMapCache from FDS data and optionally save to disk."""
    vis_obj = _build_vismap(fds_dir, sign_descriptors, time_step_s, slice_height_m)
    arrays = _vis_bool_array(vis_obj)
    result = _VisMapCache(
        time_points=vis_obj.vismap_time_points,
        x_coords=vis_obj.all_x_coords,
        y_coords=vis_obj.all_y_coords,
        vis=arrays,
    )
    if cache:
        _save_vismap_cache(cache, vis_obj, arrays, expected_meta)
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
            return _VisMapCache(
                time_points=data["time_points"],
                x_coords=data["x_coords"],
                y_coords=data["y_coords"],
                vis=data["vis"],
            )
    except Exception as e:
        _logger.warning("Failed to load vismap cache: %s", e)
        return None


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
    """

    def __init__(
        self,
        fds_dir: str | Path,
        sign_descriptors: dict[str, dict],
        *,
        cache_path: str | Path | None = None,
        time_step_s: float = 10.0,
        slice_height_m: float = 2.0,
        force_recompute: bool = False,
    ) -> None:
        cache = Path(cache_path) if cache_path else None
        expected_meta = _make_meta(
            str(fds_dir), sign_descriptors, time_step_s, slice_height_m
        )

        self._vis: _VisMapCache = _resolve_vis(
            str(fds_dir),
            sign_descriptors,
            time_step_s,
            slice_height_m,
            cache,
            force_recompute,
            expected_meta,
        )
        # An FDS-backed field changes with time, so queries use the real clock.
        self._static_time: float | None = None
        # Map node_id → internal waypoint index (insertion order preserved)
        self._wp_ids: dict[str, int] = {
            node_id: wp_id for wp_id, node_id in enumerate(sign_descriptors)
        }

    @classmethod
    def clear_air(
        cls,
        walkable,
        sign_descriptors: dict[str, dict],
        *,
        cell_size_m: float = 0.5,
        extinction_per_m: float = 0.0,
    ) -> "VisibilityModel":
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
        quadruples the build.
        """
        from fdsvismap import VisMap

        min_x, min_y, max_x, max_y = walkable.bounds
        x_coords = np.arange(min_x + cell_size_m / 2, max_x, cell_size_m)
        y_coords = np.arange(min_y + cell_size_m / 2, max_y, cell_size_m)

        vis = VisMap()
        vis.set_grid(x_coords, y_coords)
        vis.set_uniform_extco(extinction_per_m)
        vis.set_time_points([0.0])
        for wp_id, (_node_id, sign) in enumerate(sign_descriptors.items()):
            alpha = sign.get("alpha")
            vis.set_waypoint(
                wp_id,
                float(sign["x"]),
                float(sign["y"]),
                c=float(sign.get("c", 3)),
                alpha=None if alpha is None else float(alpha),
            )
        for x1, x2, y1, y2 in _blocked_runs(walkable, x_coords, y_coords, cell_size_m):
            vis.add_visual_obstruction(x1, x2, y1, y2)
        vis.compute_all(view_angle=True, obstructions=True, aa=True)

        model = cls.__new__(cls)
        model._vis = vis  # VisMap exposes the same wp_is_visible signature
        # A uniform field does not change, so one time point is computed and
        # every query resolves to it. Without this a query at t > 0 would be
        # rejected as outside the computed range.
        model._static_time = 0.0
        model._wp_ids = {
            node_id: wp_id for wp_id, node_id in enumerate(sign_descriptors)
        }
        return model

    def node_is_visible(self, time: float, x: float, y: float, node_id: str) -> bool:
        """Return True if the sign at *node_id* is visible from (x, y) at *time*.

        Only nodes outside the descriptor set -- spawn areas, and nodes whose
        geometry could not be turned into a centroid -- return True regardless
        of the smoke.
        """
        wp_id = self._wp_ids.get(node_id)
        if wp_id is None:
            return True
        if self._static_time is not None:
            time = self._static_time
        return bool(self._vis.wp_is_visible(time=time, x=x, y=y, waypoint_id=wp_id))
