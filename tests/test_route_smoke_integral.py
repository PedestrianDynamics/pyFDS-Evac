"""Smoke sampled along route polylines and the helpers around it.

``_polyline_stats`` feeds ``k_avg`` and ``k_max`` of every route edge, and
``_polyline_midpoint`` places the visibility test of an edge. These tests
pin their arithmetic with synthetic extinction fields, so no FDS output is
read. The sampling rule they pin: each segment of length ``L`` is sampled at
``max(2, ceil(L / step_m) + 1)`` evenly spaced points including both ends,
and the mean is taken over all samples of all segments.
"""

import pytest
from shapely.geometry import Polygon

from pyfds_evac.core.route_graph import (
    AgentRouteState,
    StageEdge,
    StageGraph,
    _passes_through_another_node,
    _polyline_midpoint,
    _polyline_stats,
    _position_aware_length,
    _reconstruct_committed_path,
    _walkable_waypoints,
    compute_eval_offset,
    integrated_extinction_along_polyline,
    should_reevaluate,
)
from pyfds_evac.core.smoke_speed import ConstantExtinctionField


class _LinearInX:
    """K(x, y) = x, which makes every sample mean easy to compute by hand."""

    def sample_extinction(self, time_s: float, x: float, y: float) -> float:
        return x


class _Step:
    """K = high for x < x_step, low elsewhere."""

    def __init__(self, x_step: float, high: float, low: float = 0.0) -> None:
        self.x_step = x_step
        self.high = high
        self.low = low

    def sample_extinction(self, time_s: float, x: float, y: float) -> float:
        return self.high if x < self.x_step else self.low


class _Recording:
    """Constant field that records every sampled point and time."""

    def __init__(self, k: float = 1.0) -> None:
        self.k = k
        self.calls: list[tuple[float, float, float]] = []

    def sample_extinction(self, time_s: float, x: float, y: float) -> float:
        self.calls.append((time_s, x, y))
        return self.k


def _box(cx: float, cy: float, half: float = 1.0) -> Polygon:
    return Polygon(
        [
            (cx - half, cy - half),
            (cx + half, cy - half),
            (cx + half, cy + half),
            (cx - half, cy + half),
        ]
    )


class TestIntegratedExtinctionAlongPolyline:
    def test_constant_field_gives_its_value_on_any_polyline(self):
        field = ConstantExtinctionField(0.7)
        waypoints = [(0.0, 0.0), (4.0, 0.0), (4.0, 3.0), (1.0, 7.0)]
        assert integrated_extinction_along_polyline(
            waypoints, 12.0, field
        ) == pytest.approx(0.7)

    def test_linear_field_on_a_straight_line_gives_the_mid_value(self):
        k = integrated_extinction_along_polyline(
            [(0.0, 0.0), (10.0, 0.0)], 0.0, _LinearInX(), step_m=2.0
        )
        assert k == pytest.approx(5.0)

    def test_step_field_halfway_gives_the_sample_fraction(self):
        """10 m at step 2 m gives 6 samples, x = 0, 2, ..., 10; three are below 5."""
        k = integrated_extinction_along_polyline(
            [(0.0, 0.0), (10.0, 0.0)], 0.0, _Step(5.0, high=1.0), step_m=2.0
        )
        assert k == pytest.approx(3 / 6)

    def test_samples_are_evenly_spaced_with_both_ends(self):
        field = _Recording()
        integrated_extinction_along_polyline(
            [(0.0, 0.0), (5.0, 0.0)], 3.5, field, step_m=2.0
        )
        # ceil(5 / 2) + 1 = 4 samples over 5 m.
        xs = [x for _, x, _ in field.calls]
        assert xs == pytest.approx([0.0, 5 / 3, 10 / 3, 5.0])
        assert {t for t, _, _ in field.calls} == {3.5}

    def test_short_segment_still_gets_two_samples(self):
        field = _Recording()
        integrated_extinction_along_polyline(
            [(0.0, 0.0), (0.1, 0.0)], 0.0, field, step_m=2.0
        )
        assert len(field.calls) == 2

    def test_interior_vertex_is_sampled_once_per_segment(self):
        field = _Recording()
        integrated_extinction_along_polyline(
            [(0.0, 0.0), (2.0, 0.0), (4.0, 0.0)], 0.0, field, step_m=2.0
        )
        assert [x for _, x, _ in field.calls] == pytest.approx([0.0, 2.0, 2.0, 4.0])

    def test_single_point_samples_that_point(self):
        field = _Recording(k=0.4)
        k = integrated_extinction_along_polyline([(3.0, 2.0)], 7.0, field)
        assert k == pytest.approx(0.4)
        assert field.calls == [(7.0, 3.0, 2.0)]

    def test_empty_polyline_is_clear_air(self):
        assert integrated_extinction_along_polyline(
            [], 0.0, ConstantExtinctionField(3.0)
        ) == pytest.approx(0.0)

    @pytest.mark.parametrize("step_m", [0.0, -1.0])
    def test_non_positive_step_is_rejected(self, step_m):
        with pytest.raises(ValueError, match="step_m must be positive"):
            integrated_extinction_along_polyline(
                [(0.0, 0.0), (1.0, 0.0)],
                0.0,
                ConstantExtinctionField(1.0),
                step_m=step_m,
            )

    @pytest.mark.xfail(
        strict=True,
        reason="#437: the polyline mean is weighted by sample count, not length",
    )
    def test_collinear_vertices_do_not_change_the_mean(self):
        straight = [(0.0, 0.0), (10.0, 0.0)]
        split = [(0.0, 0.0), (9.0, 0.0), (9.5, 0.0), (10.0, 0.0)]
        field = _LinearInX()
        assert integrated_extinction_along_polyline(
            split, 0.0, field, step_m=2.0
        ) == pytest.approx(
            integrated_extinction_along_polyline(straight, 0.0, field, step_m=2.0),
            rel=0.02,
        )


class TestPolylineStats:
    def test_mean_and_worst_of_a_step_field(self):
        mean, worst = _polyline_stats(
            [(0.0, 0.0), (10.0, 0.0)], 0.0, _Step(5.0, high=2.0, low=0.5), 2.0
        )
        assert mean == pytest.approx((3 * 2.0 + 3 * 0.5) / 6)
        assert worst == pytest.approx(2.0)

    def test_worst_is_found_on_a_later_segment(self):
        mean, worst = _polyline_stats(
            [(0.0, 0.0), (0.0, 4.0), (6.0, 4.0)], 0.0, _LinearInX(), 2.0
        )
        assert worst == pytest.approx(6.0)
        # Samples: x = 0, 0, 0 on the first leg; x = 0, 2, 4, 6 on the second.
        assert mean == pytest.approx(12.0 / 7)

    def test_single_point_returns_its_value_twice(self):
        assert _polyline_stats(
            [(1.0, 1.0)], 0.0, ConstantExtinctionField(0.3), 2.0
        ) == pytest.approx((0.3, 0.3))

    def test_empty_polyline_returns_zeros(self):
        assert _polyline_stats(
            [], 0.0, ConstantExtinctionField(0.3), 2.0
        ) == pytest.approx((0.0, 0.0))

    def test_zero_length_segment_is_sampled_once(self):
        field = _Recording(k=1.5)
        mean, worst = _polyline_stats([(2.0, 2.0), (2.0, 2.0)], 0.0, field, 2.0)
        assert (mean, worst) == pytest.approx((1.5, 1.5))
        assert len(field.calls) == 1

    def test_zero_length_segment_inside_a_polyline(self):
        field = _Recording()
        _polyline_stats([(0.0, 0.0), (2.0, 0.0), (2.0, 0.0)], 0.0, field, 2.0)
        assert [x for _, x, _ in field.calls] == pytest.approx([0.0, 2.0, 2.0])


class TestPolylineMidpoint:
    def test_empty_polyline_is_rejected(self):
        with pytest.raises(ValueError, match="must not be empty"):
            _polyline_midpoint([])

    def test_single_point_is_its_own_midpoint(self):
        assert _polyline_midpoint([(3.0, 4.0)]) == (3.0, 4.0)

    def test_zero_length_polyline_returns_the_first_point(self):
        assert _polyline_midpoint([(1.0, 1.0), (1.0, 1.0)]) == (1.0, 1.0)

    def test_straight_segment(self):
        assert _polyline_midpoint([(0.0, 0.0), (4.0, 2.0)]) == pytest.approx((2.0, 1.0))

    def test_midpoint_is_at_half_the_arc_length(self):
        # Legs of 2 m, 4 m and 2 m: half of 8 m is 2 m into the second leg.
        assert _polyline_midpoint(
            [(0.0, 0.0), (2.0, 0.0), (2.0, 4.0), (4.0, 4.0)]
        ) == pytest.approx((2.0, 2.0))

    def test_midpoint_on_a_vertex(self):
        assert _polyline_midpoint(
            [(0.0, 0.0), (3.0, 0.0), (3.0, 3.0)]
        ) == pytest.approx((3.0, 0.0))

    def test_leading_zero_length_segment_is_skipped(self):
        assert _polyline_midpoint(
            [(0.0, 0.0), (0.0, 0.0), (6.0, 0.0)]
        ) == pytest.approx((3.0, 0.0))


class _Engine:
    """Routing-engine stand-in returning a fixed result or raising."""

    def __init__(self, result=None, error: Exception | None = None) -> None:
        self.result = result
        self.error = error

    def compute_waypoints(self, from_xy, to_xy):
        if self.error is not None:
            raise self.error
        return self.result


class TestWalkableWaypoints:
    def test_no_engine_gives_the_straight_line(self):
        assert _walkable_waypoints(None, (0.0, 0.0), (3.0, 4.0)) == [
            (0.0, 0.0),
            (3.0, 4.0),
        ]

    def test_engine_path_is_used(self):
        path = [(0.0, 0.0), (0.0, 4.0), (3.0, 4.0)]
        assert _walkable_waypoints(_Engine(path), (0.0, 0.0), (3.0, 4.0)) == path

    def test_engine_error_falls_back_to_the_straight_line(self):
        engine = _Engine(error=RuntimeError("no path"))
        assert _walkable_waypoints(engine, (0.0, 0.0), (3.0, 4.0)) == [
            (0.0, 0.0),
            (3.0, 4.0),
        ]

    def test_degenerate_engine_path_falls_back_to_the_straight_line(self):
        engine = _Engine(result=[(0.0, 0.0)])
        assert _walkable_waypoints(engine, (0.0, 0.0), (3.0, 4.0)) == [
            (0.0, 0.0),
            (3.0, 4.0),
        ]


def _two_node_graph() -> StageGraph:
    return StageGraph.from_scenario(
        {
            "a": {"polygon": _box(0.0, 0.0), "stage_type": "checkpoint"},
            "e": {"polygon": _box(10.0, 0.0), "stage_type": "exit"},
        },
        [{"from": "a", "to": "e"}],
    )


class TestPositionAwareLength:
    def test_unknown_node_returns_the_path_length_unchanged(self):
        assert _position_aware_length(
            _two_node_graph(), ["a", "missing"], (5.0, 0.0), 10.0, 10.0
        ) == (10.0, 1.0)

    def test_zero_length_first_segment_charges_the_whole_walk(self):
        # Agent 4 m from "e" on a first leg of length zero.
        effective, share = _position_aware_length(
            _two_node_graph(), ["a", "e"], (6.0, 0.0), 7.0, 0.0
        )
        assert effective == pytest.approx(7.0 + 4.0)
        assert share == 1.0

    def test_share_is_the_untraversed_fraction_of_the_first_leg(self):
        effective, share = _position_aware_length(
            _two_node_graph(), ["a", "e"], (7.5, 0.0), 10.0, 10.0
        )
        assert effective == pytest.approx(2.5)
        assert share == pytest.approx(0.25)

    def test_share_is_floored_above_zero_at_the_end_node(self):
        _, share = _position_aware_length(
            _two_node_graph(), ["a", "e"], (10.0, 0.0), 10.0, 10.0
        )
        assert 0.0 < share <= 1e-9

    def test_share_is_capped_at_one_behind_the_origin(self):
        _, share = _position_aware_length(
            _two_node_graph(), ["a", "e"], (-5.0, 0.0), 10.0, 10.0
        )
        assert share == 1.0

    def test_given_first_waypoints_replace_the_engine_query(self):
        effective, _ = _position_aware_length(
            _two_node_graph(),
            ["a", "e"],
            (5.0, 0.0),
            10.0,
            10.0,
            first_waypoints=[(5.0, 0.0), (5.0, 3.0), (10.0, 3.0)],
        )
        assert effective == pytest.approx(8.0)


class TestPassesThroughAnotherNode:
    def test_zero_length_edge_is_never_blocked(self):
        graph = StageGraph.from_scenario(
            {
                "a": {"polygon": _box(0.0, 0.0), "stage_type": "checkpoint"},
                "b": {"polygon": _box(0.0, 0.0), "stage_type": "checkpoint"},
                "c": {"polygon": _box(0.0, 0.0), "stage_type": "checkpoint"},
            },
            [],
        )
        edge = StageEdge(source="a", target="b", weight=0.0)
        assert not _passes_through_another_node(graph, "a", edge, ["c"], None)


class TestReevaluationSchedule:
    def test_non_positive_interval_never_reevaluates(self):
        state = AgentRouteState()
        assert not should_reevaluate(100.0, state, 0.0)
        assert not should_reevaluate(100.0, state, -1.0)

    def test_first_evaluation_waits_for_the_offset(self):
        state = AgentRouteState(eval_offset_s=0.3)
        assert not should_reevaluate(0.2, state, 1.0)
        assert should_reevaluate(0.3, state, 1.0)

    def test_later_evaluations_follow_the_interval(self):
        state = AgentRouteState(last_eval_time_s=2.0, eval_offset_s=0.0)
        assert not should_reevaluate(2.9, state, 1.0)
        assert should_reevaluate(3.0, state, 1.0)

    @pytest.mark.parametrize("interval_s, dt_s", [(0.0, 0.01), (1.0, 0.0)])
    def test_offset_is_zero_for_a_non_positive_interval_or_step(self, interval_s, dt_s):
        assert compute_eval_offset(7, interval_s, dt_s) == 0.0

    def test_offsets_wrap_around_the_interval(self):
        assert compute_eval_offset(3, 0.05, 0.01) == pytest.approx(0.03)
        assert compute_eval_offset(8, 0.05, 0.01) == pytest.approx(0.03)


class TestReconstructCommittedPath:
    @pytest.mark.parametrize(
        "wait_info",
        [{}, {"current_origin": "a"}, {"current_target_stage": "b"}],
    )
    def test_missing_origin_or_target_gives_no_path(self, wait_info):
        assert _reconstruct_committed_path(wait_info) == []

    def test_follows_single_choices_to_the_terminal_stage(self):
        info = {
            "current_origin": "a",
            "current_target_stage": "b",
            "path_choices": {"b": [("c", 1.0)], "c": [("e", 1.0)]},
        }
        assert _reconstruct_committed_path(info) == ["a", "b", "c", "e"]

    def test_stops_at_a_probabilistic_branch(self):
        info = {
            "current_origin": "a",
            "current_target_stage": "b",
            "path_choices": {"b": [("c", 0.5), ("d", 0.5)]},
        }
        assert _reconstruct_committed_path(info) == ["a", "b"]

    def test_stops_on_a_cycle(self):
        info = {
            "current_origin": "a",
            "current_target_stage": "b",
            "path_choices": {"b": [("c", 1.0)], "c": [("a", 1.0)]},
        }
        assert _reconstruct_committed_path(info) == ["a", "b", "c"]
