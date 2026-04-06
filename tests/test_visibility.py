"""Tests for VisibilityModel cache load/recompute behaviour."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import numpy as np

from pyfds_evac.core.visibility import VisibilityModel, _make_meta


# ── helpers ───────────────────────────────────────────────────────────

SIGNS = {
    "exit_A": {"x": 1.0, "y": 2.0, "alpha": 90.0, "c": 3},
    "exit_B": {"x": 5.0, "y": 6.0, "alpha": 270.0, "c": 3},
}
FDS_DIR = "/some/fds/dir"
TIME_STEP = 10.0
HEIGHT = 2.0


class _FakeVis:
    """Stand-in for a fdsvismap.VisMap object returned by _build_vismap.

    Provides the minimal attributes accessed by _build_cache_from_fds:
    - vismap_time_points, all_x_coords, all_y_coords  (coordinate arrays)
    - all_time_all_wp_vismap_array_list  (nested list of per-wp bool arrays)

    Shape convention: 2 time steps × 2 waypoints × 1×1 spatial grid
    (matches the 2 entries in SIGNS).
    """

    vismap_time_points = np.array([0.0, 10.0])
    all_x_coords = np.array([0.0])
    all_y_coords = np.array([0.0])
    all_time_all_wp_vismap_array_list = [
        [np.zeros((1, 1), dtype=bool), np.zeros((1, 1), dtype=bool)],
        [np.zeros((1, 1), dtype=bool), np.zeros((1, 1), dtype=bool)],
    ]


def _write_valid_cache(path: Path, fds_dir: str = FDS_DIR) -> dict:
    """Write a correctly-formatted npz cache and return the meta dict."""
    meta = _make_meta(fds_dir, SIGNS, TIME_STEP, HEIGHT)
    npz_path = path.with_suffix(".npz")
    np.savez_compressed(
        npz_path,
        time_points=np.array([0.0, 10.0]),
        x_coords=np.array([0.0]),
        y_coords=np.array([0.0]),
        vis=np.zeros((2, 2, 1, 1), dtype=bool),
        meta=np.array(json.dumps(meta)),
    )
    return meta


# ── tests ─────────────────────────────────────────────────────────────


class TestVisibilityModelCache:
    @patch("pyfds_evac.core.visibility._build_vismap")
    def test_valid_cache_loaded_without_recompute(self, mock_build):
        """When meta matches, the cached vismap is used without recomputing."""
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "vis.npz"
            _write_valid_cache(cache, fds_dir=FDS_DIR)

            VisibilityModel(
                FDS_DIR,
                SIGNS,
                cache_path=cache,
                time_step_s=TIME_STEP,
                slice_height_m=HEIGHT,
            )

            mock_build.assert_not_called()

    @patch("pyfds_evac.core.visibility._build_vismap")
    def test_mismatched_waypoints_triggers_recompute(self, mock_build):
        """Different waypoints cause the cache to be rejected and recomputed."""
        mock_build.return_value = _FakeVis()

        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "vis.npz"
            _write_valid_cache(cache, fds_dir=FDS_DIR)

            different_signs = {"exit_A": {"x": 99.0, "y": 0.0, "alpha": 0.0, "c": 3}}
            VisibilityModel(
                FDS_DIR,
                different_signs,
                cache_path=cache,
                time_step_s=TIME_STEP,
                slice_height_m=HEIGHT,
            )

            mock_build.assert_called_once()

    @patch("pyfds_evac.core.visibility._build_vismap")
    def test_different_fds_dir_triggers_recompute(self, mock_build):
        """Cache created for a different fds_dir is rejected even if waypoints match."""
        mock_build.return_value = _FakeVis()

        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "vis.npz"
            _write_valid_cache(cache, fds_dir="/other/fds/dir")

            VisibilityModel(
                FDS_DIR,
                SIGNS,
                cache_path=cache,
                time_step_s=TIME_STEP,
                slice_height_m=HEIGHT,
            )

            mock_build.assert_called_once()

    @patch("pyfds_evac.core.visibility._build_vismap")
    def test_missing_npz_triggers_recompute(self, mock_build):
        """When no .npz cache exists (e.g. only a legacy .pkl path), recompute fires.

        This replaces the old 'legacy single-object pickle' test: the cache
        format is now always .npz; any other suffix causes a cache miss.
        """
        mock_build.return_value = _FakeVis()

        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "vis.pkl"  # no .npz sibling exists

            VisibilityModel(
                FDS_DIR,
                SIGNS,
                cache_path=cache,
                time_step_s=TIME_STEP,
                slice_height_m=HEIGHT,
            )

            mock_build.assert_called_once()

    @patch("pyfds_evac.core.visibility._build_vismap")
    def test_recomputed_cache_is_written_as_npz(self, mock_build):
        """After a recompute, an npz file is written and contains correct metadata."""
        mock_build.return_value = _FakeVis()

        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "vis.npz"

            VisibilityModel(
                FDS_DIR,
                SIGNS,
                cache_path=cache,
                time_step_s=TIME_STEP,
                slice_height_m=HEIGHT,
            )

            assert cache.exists(), "npz cache file must be written after recompute"
            with np.load(cache, allow_pickle=False) as data:
                saved_meta = json.loads(str(data["meta"]))
            assert saved_meta["fds_dir"] == str(Path(FDS_DIR).resolve())
