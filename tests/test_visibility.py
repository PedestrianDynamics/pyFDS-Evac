"""Tests for VisibilityModel cache load/recompute behaviour."""

from __future__ import annotations

import json
import math
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
    - all_time_all_sign_vismap_list  (nested list of per-wp bool arrays)

    Shape convention: 2 time steps × 2 waypoints × 1×1 spatial grid
    (matches the 2 entries in SIGNS).
    """

    vismap_time_points = np.array([0.0, 10.0])
    fds_time_points = np.array([0.0, 10.0])
    all_x_coords = np.array([0.0])
    all_y_coords = np.array([0.0])
    all_time_all_sign_vismap_list = [
        [np.zeros((1, 1), dtype=bool), np.zeros((1, 1), dtype=bool)],
        [np.zeros((1, 1), dtype=bool), np.zeros((1, 1), dtype=bool)],
    ]
    # Sighting distances are cached alongside the booleans, so the fake has to
    # answer the three arrays _vis_metre_array multiplies together.
    all_sign_dict = {0: None, 1: None}
    all_sign_angle_array_dict = {0: np.ones((1, 1)), 1: np.ones((1, 1))}
    all_sign_non_concealed_cells_array_dict = {0: np.ones((1, 1)), 1: np.ones((1, 1))}

    def _get_visibility_array(self, waypoint_id, time):
        del waypoint_id, time
        return np.zeros((1, 1))


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
        output_interval_s=np.array(10.0),
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
        with (
            patch("fdsvismap.VisMap", return_value=fake),
            patch("pyfds_evac.core.visibility._extinction_slice_index", return_value=0),
        ):
            _build_vismap(
                "unused",
                {"c0": {"x": 1.0, "y": 2.0, "alpha": None, "c": 3}},
                time_step_s=5.0,
                slice_height_m=2.0,
            )
        assert fake.add_sign.call_args.kwargs["alpha"] is None

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
            fds_time_points = np.array([0.0])
            all_x_coords = np.array([0.0, 1.0])
            all_y_coords = np.array([0.0])
            all_time_all_sign_vismap_list = [
                [np.array([[True, False]])],
            ]
            # Sight of 12 m where the sign is visible, masked to 0 where it is
            # not -- the shape visibility_to_node has to read.
            all_sign_dict = {0: None}
            all_sign_angle_array_dict = {0: np.array([[1.0, 0.0]])}
            all_sign_non_concealed_cells_array_dict = {0: np.array([[1.0, 1.0]])}

            def _get_visibility_array(self, waypoint_id, time):
                del waypoint_id, time
                return np.array([[12.0, 12.0]])

        with patch(
            "pyfds_evac.core.visibility._build_vismap",
            return_value=_GatedFakeVis(),
        ):
            model = VisibilityModel("unused", signs)

        assert model.node_is_visible(time=0.0, x=0.0, y=0.0, node_id="e0") is True
        assert model.node_is_visible(time=0.0, x=1.0, y=0.0, node_id="e0") is False

        # And the metre-valued reader agrees: a distance where the sign reads,
        # None where the mask zeroes it, because a hidden sign is not a wall.
        assert model.visibility_to_node(0.0, 0.0, 0.0, "e0") == 12.0
        assert model.visibility_to_node(0.0, 1.0, 0.0, "e0") is None
        assert model.visibility_to_node(0.0, 0.0, 0.0, "no_such_node") is None


class TestSignDistanceCap:
    """A sign has a finite reading distance, even in clear air (#173).

    fdsvismap and Börger et al. (2024) cap it at 30 m. A 60 m corridor puts a
    sign 20 m and 40 m from two viewers, on either side of that cap.
    """

    SIGN = {"exit": {"x": 1.0, "y": 2.0, "alpha": None, "c": 3}}
    NEAR = (21.0, 2.0)
    FAR = (41.0, 2.0)

    @staticmethod
    def _corridor():
        from shapely.geometry import box

        return box(0.0, 0.0, 60.0, 4.0)

    def _model(self, signs=None, **kwargs):
        return VisibilityModel.clear_air(
            self._corridor(), signs or self.SIGN, cell_size_m=1.0, **kwargs
        )

    def test_sign_within_30_m_is_legible_by_default(self):
        assert self._model().node_is_visible(0.0, *self.NEAR, "exit")

    def test_sign_beyond_30_m_is_not_legible_by_default(self):
        assert not self._model().node_is_visible(0.0, *self.FAR, "exit")

    def test_per_sign_max_distance_extends_the_reading_distance(self):
        signs = {"exit": {**self.SIGN["exit"], "max_distance": 50.0}}
        assert self._model(signs).node_is_visible(0.0, *self.FAR, "exit")

    def test_per_sign_max_distance_can_shorten_it(self):
        signs = {"exit": {**self.SIGN["exit"], "max_distance": 10.0}}
        assert not self._model(signs).node_is_visible(0.0, *self.NEAR, "exit")

    def test_global_cap_applies_to_signs_without_their_own(self):
        model = self._model(max_sign_distance_m=50.0)
        assert model.node_is_visible(0.0, *self.FAR, "exit")

    def test_sighting_distance_is_capped_per_sign(self):
        signs = {"exit": {**self.SIGN["exit"], "max_distance": 10.0}}
        metres = self._model(signs).visibility_to_node(0.0, *self.NEAR, "exit")
        assert metres == pytest.approx(10.0)

    @pytest.mark.parametrize("cap", [0, -5.0, float("nan"), float("inf")])
    def test_invalid_max_distance_is_rejected(self, cap):
        signs = {"exit": {**self.SIGN["exit"], "max_distance": cap}}
        with pytest.raises(ValueError, match="max_distance"):
            self._model(signs)

    @pytest.mark.parametrize("cap", [0.0, float("nan"), float("inf")])
    def test_invalid_global_cap_is_rejected(self, cap):
        with pytest.raises(ValueError, match="max_sign_distance_m"):
            self._model(max_sign_distance_m=cap)

    @pytest.mark.parametrize("cap", [float("nan"), float("inf")])
    def test_invalid_global_cap_is_rejected_on_a_cache_hit(self, cap):
        """A cache must not let an invalid cap through before it is checked."""
        with patch(
            "pyfds_evac.core.visibility._load_vismap_cache", return_value=object()
        ):
            with pytest.raises(ValueError, match="max_sign_distance_m"):
                self._model(cache_path="unused.npz", max_sign_distance_m=cap)
            with pytest.raises(ValueError, match="max_sign_distance_m"):
                VisibilityModel(
                    FDS_DIR,
                    self.SIGN,
                    cache_path="unused.npz",
                    max_sign_distance_m=cap,
                )

    def test_cap_is_part_of_the_cache_key(self):
        base = _make_meta(FDS_DIR, SIGNS, TIME_STEP, HEIGHT)
        raised = _make_meta(FDS_DIR, SIGNS, TIME_STEP, HEIGHT, max_sign_distance_m=50.0)
        signed = _make_meta(
            FDS_DIR,
            {**SIGNS, "exit_A": {**SIGNS["exit_A"], "max_distance": 50.0}},
            TIME_STEP,
            HEIGHT,
        )
        assert base != raised
        assert base != signed

    def test_cli_default_is_30_m(self):
        import run

        opts = run._build_parser().parse_args(["--scenario", "unused"])
        assert opts.max_sign_distance == 30.0


class TestClearAirCacheHit:
    """#178: a model loaded from a clear-air cache still knows its signs."""

    def test_distance_to_node_after_a_cache_hit(self, tmp_path):
        from shapely.geometry import box

        signs = {"e": {"x": 1.0, "y": 2.0, "alpha": None, "c": 3}}
        cache = tmp_path / "vis.npz"
        built = VisibilityModel.clear_air(
            box(0, 0, 10, 4), signs, cell_size_m=1.0, cache_path=cache
        )
        loaded = VisibilityModel.clear_air(
            box(0, 0, 10, 4), signs, cell_size_m=1.0, cache_path=cache
        )
        assert loaded.distance_to_node(5.0, 2.0, "e") == pytest.approx(
            built.distance_to_node(5.0, 2.0, "e")
        )


class TestClearAirGridResolution:
    """The clear-air grid against the thinnest wall of the deck (#115).

    A cell blocks sight when its centre lies outside the walkable area, so a
    wall no wider than one cell may hold no centre and let sight through.
    """

    SIGN = {"s": {"x": 8.0, "y": 2.0, "alpha": None, "c": 3}}
    WALL_M = 0.4

    def _walkable(self, height=4.0):
        from shapely.geometry import box

        # A 0.4 m wall from the bottom edge, placed so no 0.5 m cell centre
        # (4.75, 5.25) falls inside it while two 0.25 m centres do.
        return box(0, 0, 10, 4).difference(box(4.8, 0, 4.8 + self.WALL_M, height))

    def _warnings(self, caplog):
        return [
            r for r in caplog.records if "Clear-air visibility grid" in r.getMessage()
        ]

    def test_warns_when_the_cell_is_wider_than_a_boundary_wall(self, caplog):
        VisibilityModel.clear_air(self._walkable(3.0), self.SIGN, cell_size_m=0.5)
        (record,) = self._warnings(caplog)
        assert record.levelname == "WARNING"
        assert "about 0.4 m wide" in record.getMessage()

    def test_silent_when_the_cell_is_narrower_than_every_wall(self, caplog):
        VisibilityModel.clear_air(self._walkable(3.0), self.SIGN, cell_size_m=0.25)
        assert not self._warnings(caplog)

    def test_silent_without_any_wall(self, caplog):
        from shapely.geometry import box

        VisibilityModel.clear_air(box(0, 0, 10, 4), self.SIGN, cell_size_m=2.0)
        assert not self._warnings(caplog)

    def test_warns_on_a_cache_hit_too(self, tmp_path, caplog):
        cache = tmp_path / "vis.npz"
        walkable = self._walkable(3.0)
        VisibilityModel.clear_air(
            walkable, self.SIGN, cell_size_m=0.5, cache_path=cache
        )
        caplog.clear()
        VisibilityModel.clear_air(
            walkable, self.SIGN, cell_size_m=0.5, cache_path=cache
        )
        assert len(self._warnings(caplog)) == 1

    @pytest.mark.parametrize(
        ("deck", "cell_size_m", "warns"),
        [
            ("familiarity_test_discovery", 0.25, True),
            # Equal to the 0.1 m walls: warns.
            ("familiarity_test_discovery", 0.1, True),
            ("familiarity_test_discovery", 0.08, False),
            # Its walls touch the outer boundary: no hole of the polygon.
            ("blind_spawn_discovery", 0.5, True),
            ("blind_spawn_discovery", 0.4, True),
            ("blind_spawn_discovery", 0.25, False),
            # Strips of 0.08-0.2 m (#115 record): 0.25 m does not resolve it.
            ("station_fahy", 0.25, True),
        ],
    )
    def test_deck_walls(self, deck, cell_size_m, warns, caplog):
        from shapely import wkt

        from pyfds_evac.core.visibility import unresolved_wall

        text = Path(f"assets/{deck}/geometry.wkt").read_text()
        assert (unresolved_wall(wkt.loads(text), cell_size_m) is not None) is warns

    def test_api_default_is_the_cli_default(self):
        import inspect

        from pyfds_evac.config.parameters import VIS_CELL_SIZE_M

        default = (
            inspect.signature(VisibilityModel.clear_air)
            .parameters["cell_size_m"]
            .default
        )
        assert default == VIS_CELL_SIZE_M == 0.25

    def test_default_grid_blocks_a_wall_the_old_default_lost(self):
        """A 0.4 m partition hides the sign at the default, not at 0.5 m."""
        walkable = self._walkable()
        assert not VisibilityModel.clear_air(walkable, self.SIGN).node_is_visible(
            0.0, 2.0, 2.0, "s"
        )
        coarse = VisibilityModel.clear_air(walkable, self.SIGN, cell_size_m=0.5)
        assert coarse.node_is_visible(0.0, 2.0, 2.0, "s")

    def test_warns_on_a_thin_stem_of_a_large_obstruction(self, caplog):
        """A 0.1 m stem on a 6 m x 4 m base is a 0.1 m wall, not a 1.5 m one."""
        from shapely.geometry import box

        stem = box(9.95, 2, 10.05, 14).union(box(7, 2, 13, 6))
        walkable = box(0, 0, 20, 20).difference(stem)
        sign = {"s": {"x": 11.0, "y": 10.0, "alpha": None, "c": 3}}
        model = VisibilityModel.clear_air(walkable, sign, cell_size_m=0.25)
        (record,) = self._warnings(caplog)
        assert "near (10.00," in record.getMessage()
        assert model.parameters["thin_wall_m"] == pytest.approx(0.1, abs=0.005)
        assert model.parameters["thin_wall_warning"] is True

    @pytest.mark.parametrize(
        "corner",
        [
            # A 0.1 m bevel of a convex room: no wall, nothing to see through.
            [(0, 0), (20, 0), (20, 19.9), (19.9, 20), (0, 20)],
            # A 2 m bevel: its 45 degree corners are not walls either.
            [(0, 0), (20, 0), (20, 18), (18, 20), (0, 20)],
        ],
    )
    def test_silent_on_a_bevelled_exterior_corner(self, corner, caplog):
        from shapely.geometry import Polygon

        model = VisibilityModel.clear_air(Polygon(corner), self.SIGN, cell_size_m=0.25)
        assert not self._warnings(caplog)
        assert model.parameters["thin_wall_m"] is None
        assert model.parameters["thin_wall_warning"] is False

    def test_the_tip_of_an_acute_wedge_is_not_a_wall(self):
        from shapely.geometry import Polygon, box

        from pyfds_evac.core.visibility import unresolved_wall

        wedge = Polygon([(5, 5), (15, 5), (15, 7)])  # 11 degree tip
        assert unresolved_wall(box(0, 0, 20, 20).difference(wedge), 0.25) is None

    @pytest.mark.parametrize(("cell_size_m", "warns"), [(0.5, True), (0.25, False)])
    def test_an_oblique_wall_is_measured_across(self, cell_size_m, warns):
        from shapely import affinity
        from shapely.geometry import box

        from pyfds_evac.core.visibility import unresolved_wall

        wall = affinity.rotate(box(9.8, 5, 10.2, 15), 30)
        found = unresolved_wall(box(0, 0, 20, 20).difference(wall), cell_size_m)
        assert (found is not None) is warns
        if warns:
            assert found[0] == pytest.approx(0.4, abs=1e-6)

    @pytest.mark.parametrize(
        ("cell_size_m", "warns"), [(0.4, True), (0.4 - 1e-6, False)]
    )
    def test_a_cell_equal_to_the_wall_warns(self, cell_size_m, warns):
        from pyfds_evac.core.visibility import unresolved_wall

        found = unresolved_wall(self._walkable(3.0), cell_size_m)
        assert (found is not None) is warns

    def test_parameters_record_the_check_built_and_cached(self, tmp_path):
        from shapely.geometry import box

        cache = tmp_path / "vis.npz"
        walkable = self._walkable(3.0)
        built = VisibilityModel.clear_air(
            walkable, self.SIGN, cell_size_m=0.5, cache_path=cache
        )
        loaded = VisibilityModel.clear_air(
            walkable, self.SIGN, cell_size_m=0.5, cache_path=cache
        )
        assert built.parameters == loaded.parameters
        assert built.parameters["thin_wall_m"] == pytest.approx(0.4)
        assert built.parameters["thin_wall_warning"] is True
        open_room = VisibilityModel.clear_air(box(0, 0, 10, 4), self.SIGN)
        assert open_room.parameters["thin_wall_m"] is None
        assert open_room.parameters["thin_wall_warning"] is False

    @pytest.mark.parametrize("attached", [False, True])
    @pytest.mark.parametrize(
        ("cells", "warns"),
        [(0.9, False), (1.1, True), (1.25, True), (1.5, True), (2.0, True)],
    )
    def test_a_short_stub_longer_than_one_cell_warns(self, cells, warns, attached):
        """A 0.1 m stub 1-1.5 cells long lets most sight through at 0.25 m."""
        from shapely.geometry import box

        from pyfds_evac.core.visibility import unresolved_wall

        length = cells * 0.25
        y0 = 0.0 if attached else 5.0
        stub = box(5.0, y0, 5.1, y0 + length)
        found = unresolved_wall(box(0, 0, 10, 10).difference(stub), 0.25)
        assert (found is not None) is warns

    def test_a_wall_tapering_from_0_1_to_0_2_m_warns(self):
        from shapely.geometry import Polygon, box

        from pyfds_evac.core.visibility import unresolved_wall

        wall = Polygon([(5, 5), (10, 5), (10, 5.2), (5, 5.1)])
        found = unresolved_wall(box(0, 0, 20, 20).difference(wall), 0.25)
        assert found is not None
        # The thin end, by design: the wall is split at width steps.
        assert found[0] == pytest.approx(0.1, abs=0.01)

    @pytest.mark.parametrize("degrees", [11, 20, 30, 45])
    def test_the_tip_of_a_wedge_is_not_a_wall(self, degrees):
        from shapely.geometry import Polygon, box

        from pyfds_evac.core.visibility import unresolved_wall

        tip = 10 * math.tan(math.radians(degrees))
        wedge = Polygon([(5, 5), (15, 5), (15, 5 + tip)])
        assert unresolved_wall(box(0, 0, 30, 30).difference(wedge), 0.25) is None

    @staticmethod
    def _room_minus(*shapes):
        from shapely.geometry import box
        from shapely.ops import unary_union

        return box(0, 0, 20, 20).difference(unary_union(shapes))

    @staticmethod
    def _junctions():
        from shapely.geometry import Polygon, box

        return {
            "0.05+0.2 end": ([box(5, 5, 5.05, 10), box(5, 10, 5.2, 15)], 0.05),
            "0.05 T 0.2": ([box(5, 5, 5.05, 10), box(2, 10, 8, 10.2)], 0.05),
            "0.1+0.2 end": ([box(5, 5, 5.1, 10), box(5, 10, 5.2, 15)], 0.1),
            "0.1+0.13 end": ([box(5, 5, 5.1, 10), box(5, 10, 5.13, 15)], 0.1),
            "0.1+0.4 end": ([box(5, 5, 5.1, 10), box(5, 10, 5.4, 15)], 0.1),
            "0.05+0.2, 0.2 to a tip": (
                [
                    box(5, 5, 5.05, 10),
                    Polygon([(5, 10), (5.2, 10), (5.2, 15), (5, 16.5)]),
                ],
                0.05,
            ),
            "0.05 T 0.2 with a tapered arm": (
                [
                    box(5, 5, 5.05, 10),
                    Polygon([(2, 10), (8, 10), (8, 10.2), (3.5, 10.2)]),
                ],
                0.05,
            ),
        }

    @pytest.mark.parametrize("cell_size_m", [0.25, 0.5])
    @pytest.mark.parametrize(
        "case",
        [
            "0.05+0.2 end",
            "0.05 T 0.2",
            "0.1+0.2 end",
            "0.1+0.13 end",
            "0.1+0.4 end",
            "0.05+0.2, 0.2 to a tip",
            "0.05 T 0.2 with a tapered arm",
        ],
    )
    def test_joined_walls_are_measured_per_wall(self, case, cell_size_m):
        """A junction of walls of different widths reports its thinnest wall."""
        from pyfds_evac.core.visibility import unresolved_wall

        shapes, thinnest = self._junctions()[case]
        found = unresolved_wall(self._room_minus(*shapes), cell_size_m)
        assert found is not None
        assert found[0] == pytest.approx(thinnest, abs=0.01)

    @pytest.mark.parametrize("cell_size_m", [0.2, 0.25, 0.5])
    def test_haspel_names_its_0_05_m_walls(self, cell_size_m):
        """The three 0.05 m walls of Haspel are found, not merged away."""
        from shapely import wkt
        from shapely.geometry import box

        from pyfds_evac.core import visibility as V

        text = Path("assets/Haspel/BUW_Geometrie_EG.wkt").read_text()
        walkable = wkt.loads(text)
        rest = box(*walkable.bounds).difference(walkable)
        faces = rest.boundary.buffer(1e-6)
        walls = [
            (width, wall.representative_point())
            for part in V._polygons(rest)
            for piece in V._lost_parts(part, cell_size_m)
            for width, wall in V._walls(piece, faces, cell_size_m)
        ]
        thin = {
            (round(p.x), round(p.y))
            for width, p in walls
            if width == pytest.approx(0.05, abs=0.005)
        }
        assert {(30, 13), (32, 13), (54, 27)} <= thin
        assert V.unresolved_wall(walkable, cell_size_m)[0] <= 0.05 + 0.005

    def test_station_fahy_names_its_thinnest_strip(self):
        from shapely import wkt

        from pyfds_evac.core.visibility import unresolved_wall

        text = Path("assets/station_fahy/geometry.wkt").read_text()
        found = unresolved_wall(wkt.loads(text), 0.25)
        assert found is not None
        assert found[0] == pytest.approx(0.028, abs=0.003)

    @pytest.mark.parametrize("cell_size_m", [0.1, 0.25, 0.5])
    def test_corners_and_wedges_stay_silent(self, cell_size_m):
        from shapely import affinity
        from shapely.geometry import Polygon, box

        from pyfds_evac.core.visibility import unresolved_wall

        shapes = [
            Polygon([(0, 0), (20, 0), (20, 19.9), (19.9, 20), (0, 20)]),
            Polygon([(0, 0), (20, 0), (20, 18), (18, 20), (0, 20)]),
            self._room_minus(affinity.rotate(box(9.5, 9.5, 10.5, 10.5), 45)),
        ]
        for degrees in (2, 5, 11, 20, 30, 45):
            tip = 10 * math.tan(math.radians(degrees))
            shapes.append(self._room_minus(Polygon([(5, 5), (15, 5), (15, 5 + tip)])))
        assert all(unresolved_wall(g, cell_size_m) is None for g in shapes)
