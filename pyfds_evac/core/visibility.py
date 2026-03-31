"""Visibility model wrapping fdsvismap for sign-based route rejection."""

from __future__ import annotations

# NOTE: The vismap cache is stored as a Python pickle.  Only load cache files
# that you created yourself or fully trust — pickle files can execute
# arbitrary code on load.

import pickle
from pathlib import Path

import numpy as np


def extract_sign_descriptors(raw_config: dict) -> dict[str, dict]:
    """Return {node_id: {x, y, alpha, c}} for all nodes with a 'sign' field."""
    signs: dict[str, dict] = {}
    for section in ("exits", "checkpoints", "waypoints"):
        for node_id, data in raw_config.get(section, {}).items():
            sign = data.get("sign")
            if sign:
                signs[node_id] = sign
    return signs


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
    sign_descriptors: dict[str, dict],
    time_step_s: float,
    slice_height_m: float,
) -> dict:
    """Build a metadata dict that uniquely identifies a vismap cache."""
    waypoints = [
        (node_id, sign.get("x"), sign.get("y"), sign.get("alpha"), sign.get("c", 3))
        for node_id, sign in sign_descriptors.items()
    ]
    return {
        "waypoints": waypoints,
        "time_step_s": time_step_s,
        "slice_height_m": slice_height_m,
    }


class VisibilityModel:
    """Wraps a pre-computed VisMap to answer per-node sign-visibility queries.

    alpha convention (compass bearing, degrees from north CW):
      90  = visible from east  (sign on west wall, seen by agents to its right)
      270 = visible from west  (sign on east wall, seen by agents to its left)
      180 = visible from south (sign at junction top, seen by agents below)

    If a node has no 'sign' descriptor it is always considered visible
    (fallback to current behaviour).

    Cache format: the pickle stores ``{"vis": <VisMap>, "meta": {...}}`` so
    that metadata can be validated before use.  Legacy single-object pickles
    and metadata mismatches (different waypoints or parameters) trigger an
    automatic recompute.
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
        expected_meta = _make_meta(sign_descriptors, time_step_s, slice_height_m)

        loaded = False
        if cache and cache.exists() and not force_recompute:
            with cache.open("rb") as f:
                data = pickle.load(f)
            if isinstance(data, dict) and data.get("meta") == expected_meta:
                self._vis = data["vis"]
                loaded = True
            else:
                print("Vismap cache metadata mismatch or legacy format — recomputing.")

        if not loaded:
            self._vis = _build_vismap(
                str(fds_dir), sign_descriptors, time_step_s, slice_height_m
            )
            if cache:
                cache.parent.mkdir(parents=True, exist_ok=True)
                with cache.open("wb") as f:
                    pickle.dump({"vis": self._vis, "meta": expected_meta}, f)

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
        return bool(self._vis.wp_is_visible(time=time, x=x, y=y, waypoint_id=wp_id))
