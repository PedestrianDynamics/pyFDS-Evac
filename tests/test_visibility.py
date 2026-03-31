"""Tests for VisibilityModel cache load/recompute behaviour."""

from __future__ import annotations

import pickle
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

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
    """Picklable stand-in for a VisMap object."""

    def wp_is_visible(self, time, x, y, waypoint_id):
        return True


def _write_valid_cache(path: Path, fds_dir: str = FDS_DIR) -> dict:
    """Write a correctly-formatted cache and return the meta dict."""
    meta = _make_meta(fds_dir, SIGNS, TIME_STEP, HEIGHT)
    with path.open("wb") as f:
        pickle.dump({"vis": _FakeVis(), "meta": meta}, f)
    return meta


# ── tests ─────────────────────────────────────────────────────────────


class TestVisibilityModelCache:
    @patch("pyfds_evac.core.visibility._build_vismap")
    def test_valid_cache_loaded_without_recompute(self, mock_build):
        """When meta matches, the cached vismap is used without recomputing."""
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "vis.pkl"
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
            cache = Path(tmp) / "vis.pkl"
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
            cache = Path(tmp) / "vis.pkl"
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
    def test_legacy_single_object_pickle_triggers_recompute(self, mock_build):
        """Old-format single-object pickle (no dict wrapper) triggers recompute."""
        mock_build.return_value = _FakeVis()

        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "vis.pkl"
            # Write the legacy format: raw VisMap object, no metadata dict
            with cache.open("wb") as f:
                pickle.dump(_FakeVis(), f)

            VisibilityModel(
                FDS_DIR,
                SIGNS,
                cache_path=cache,
                time_step_s=TIME_STEP,
                slice_height_m=HEIGHT,
            )

            mock_build.assert_called_once()

    @patch("pyfds_evac.core.visibility._build_vismap")
    def test_recomputed_cache_is_written_with_meta(self, mock_build):
        """After a recompute, the new cache file contains both vis and meta."""
        mock_build.return_value = _FakeVis()

        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "vis.pkl"

            VisibilityModel(
                FDS_DIR,
                SIGNS,
                cache_path=cache,
                time_step_s=TIME_STEP,
                slice_height_m=HEIGHT,
            )

            with cache.open("rb") as f:
                saved = pickle.load(f)

            assert isinstance(saved, dict), "cache must be a dict"
            assert "vis" in saved
            assert "meta" in saved
            assert saved["meta"]["fds_dir"] == str(Path(FDS_DIR).resolve())
