"""Tests for VisibilityModel cache load/recompute behaviour."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from pyfds_evac.core.visibility import (
    VisibilityModel,
    _make_meta,
    extract_sign_descriptors,
)

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


class TestSignSynthesis:
    """Every routable stage carries a sign, so nothing opts out of smoke gating.

    A node with no sign descriptor reports visible unconditionally, which made
    it permanently known however dense the smoke.  Synthesising a default sign
    at the node centroid closes that hole.
    """

    @staticmethod
    def _square(x, y):
        return [[x, y], [x + 2, y], [x + 2, y + 2], [x, y + 2], [x, y]]

    def _config(self):
        return {
            "exits": {
                "e0": {"coordinates": self._square(0, 0)},
                "e1": {
                    "coordinates": self._square(10, 0),
                    "sign": {"x": 11.0, "y": 0.5, "alpha": 90, "c": 8},
                },
            },
            "checkpoints": {"c0": {"coordinates": self._square(5, 0)}},
            "distributions": {"d0": {"coordinates": self._square(20, 0)}},
        }

    def test_every_exit_and_crossing_gets_a_descriptor(self):
        signs = extract_sign_descriptors(self._config())
        assert set(signs) == {"e0", "e1", "c0"}

    def test_synthesised_sign_sits_at_the_node_centroid(self):
        signs = extract_sign_descriptors(self._config())
        assert signs["e0"]["x"] == pytest.approx(1.0)
        assert signs["e0"]["y"] == pytest.approx(1.0)

    def test_synthesised_sign_is_omnidirectional_and_reflective(self):
        signs = extract_sign_descriptors(self._config())
        assert signs["c0"]["alpha"] is None
        assert signs["c0"]["c"] == 3

    def test_authored_sign_is_left_alone(self):
        signs = extract_sign_descriptors(self._config())
        assert signs["e1"] == {"x": 11.0, "y": 0.5, "alpha": 90, "c": 8}

    def test_degenerate_coordinates_are_skipped_not_fatal(self):
        """simulation_init tolerates unusable polygons, so sign synthesis must too.

        A two-point ring cannot make a Polygon; the node simply gets no
        synthesised sign instead of aborting the run.
        """
        config = {"exits": {"bad": {"coordinates": [[0, 0], [1, 1]]}}}

        signs = extract_sign_descriptors(config)

        assert "bad" not in signs

    def test_distributions_get_no_sign(self):
        """Spawn areas are sources, never navigation targets."""
        signs = extract_sign_descriptors(self._config())
        assert "d0" not in signs

    def test_none_alpha_is_passed_through_not_coerced(self):
        """fdsvismap reads alpha=None as omni-directional; float(None) raises."""
        from unittest.mock import MagicMock, patch

        from pyfds_evac.core.visibility import _build_vismap

        fake = MagicMock()
        fake.fds_time_points.max.return_value = 10.0
        with patch("fdsvismap.VisMap", return_value=fake):
            _build_vismap(
                "unused",
                {"c0": {"x": 1.0, "y": 2.0, "alpha": None, "c": 3}},
                time_step_s=5.0,
                slice_height_m=2.0,
            )
        assert fake.set_waypoint.call_args.kwargs["alpha"] is None

    def test_synthesised_sign_is_genuinely_gated_end_to_end(self):
        """A previously-unsigned node must now be visibility-gated, not just present.

        Exercises VisibilityModel.node_is_visible on a synthesised sign (no
        authored 'sign' in the config) through the real lookup path, using a
        fake VisMap in place of FDS data. Asserts both directions: visible
        where the underlying data says visible, not visible where it says
        invisible. A descriptor merely existing is not enough -- before this
        change such a node was hard-coded True regardless of the data.
        """
        config = {"exits": {"e0": {"coordinates": self._square(0, 0)}}}
        signs = extract_sign_descriptors(config)
        assert signs["e0"]["alpha"] is None  # confirm synthesised, not authored

        class _GatedFakeVis:
            vismap_time_points = np.array([0.0])
            all_x_coords = np.array([0.0, 1.0])
            all_y_coords = np.array([0.0])
            all_time_all_wp_vismap_array_list = [
                [np.array([[True, False]])],
            ]

        with patch(
            "pyfds_evac.core.visibility._build_vismap",
            return_value=_GatedFakeVis(),
        ):
            model = VisibilityModel("unused", signs)

        assert model.node_is_visible(time=0.0, x=0.0, y=0.0, node_id="e0") is True
        assert model.node_is_visible(time=0.0, x=1.0, y=0.0, node_id="e0") is False
