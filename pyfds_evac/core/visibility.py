"""Visibility model wrapping fdsvismap for sign-based route rejection."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np

_logger = logging.getLogger(__name__)


def extract_sign_descriptors(raw_config: dict) -> dict[str, dict]:
    """Return {node_id: {x, y, alpha, c}} for all nodes with a 'sign' field."""
    return {
        node_id: data["sign"]
        for section in ("exits", "checkpoints", "waypoints")
        for node_id, data in raw_config.get(section, {}).items()
        if data.get("sign")
    }


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
        vis.set_waypoint(
            wp_id,
            float(sign["x"]),
            float(sign["y"]),
            c=float(sign.get("c", 3)),
            alpha=float(sign["alpha"]),
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

    If a node has no 'sign' descriptor it is always considered visible
    (fallback to current behaviour).

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
        # Map node_id → internal waypoint index (insertion order preserved)
        self._wp_ids: dict[str, int] = {
            node_id: wp_id for wp_id, node_id in enumerate(sign_descriptors)
        }

    def node_is_visible(self, time: float, x: float, y: float, node_id: str) -> bool:
        """Return True if the sign at *node_id* is visible from (x, y) at *time*.

        Nodes without a sign descriptor always return True.
        """
        wp_id = self._wp_ids.get(node_id)
        if wp_id is None:
            return True
        return self._vis.wp_is_visible(time=time, x=x, y=y, waypoint_id=wp_id)
