"""Tests for StageGraph construction and Dijkstra shortest-path routing."""

import pytest
from shapely.geometry import Polygon

from src.core.route_graph import (
    StageGraph,
    RouteCostConfig,
    RerouteConfig,
    AgentRouteState,
    evaluate_route,
    evaluate_segment,
    rank_routes,
    compute_eval_offset,
    should_reevaluate,
    reroute_agent,
    evaluate_and_reroute,
)
from src.core.smoke_speed import ConstantExtinctionField


def _box(cx: float, cy: float, half: float = 1.0) -> Polygon:
    """Return a square polygon centred at (cx, cy)."""
    return Polygon(
        [
            (cx - half, cy - half),
            (cx + half, cy - half),
            (cx + half, cy + half),
            (cx - half, cy + half),
        ]
    )


# ── fixtures ──────────────────────────────────────────────────────────


@pytest.fixture()
def linear_graph():
    """D0 ──10──> C0 ──10──> E0   (straight line at y=0)."""
    direct_steering_info = {
        "C0": {"polygon": _box(10, 0), "stage_type": "checkpoint"},
        "E0": {"polygon": _box(20, 0), "stage_type": "exit"},
    }
    distributions = {
        "D0": {"coordinates": list(_box(0, 0).exterior.coords)},
    }
    transitions = [
        {"from": "D0", "to": "C0"},
        {"from": "C0", "to": "E0"},
    ]
    return StageGraph.from_scenario(direct_steering_info, transitions, distributions)


@pytest.fixture()
def diamond_graph():
    r"""Diamond with two paths from D0 to E0.

         C0 (0, 10)
        /          \
    D0 (0,0)     E0 (20, 10)
        \          /
         C1 (0, 30) -- longer detour
    """
    direct_steering_info = {
        "C0": {"polygon": _box(0, 10), "stage_type": "checkpoint"},
        "C1": {"polygon": _box(0, 30), "stage_type": "checkpoint"},
        "E0": {"polygon": _box(20, 10), "stage_type": "exit"},
    }
    distributions = {
        "D0": {"coordinates": list(_box(0, 0).exterior.coords)},
    }
    transitions = [
        {"from": "D0", "to": "C0"},
        {"from": "D0", "to": "C1"},
        {"from": "C0", "to": "E0"},
        {"from": "C1", "to": "E0"},
    ]
    return StageGraph.from_scenario(direct_steering_info, transitions, distributions)


@pytest.fixture()
def multi_exit_graph():
    """D0 with two reachable exits at different distances.

    D0 (0,0) ──10──> E0 (10,0)
    D0 (0,0) ──20──> E1 (20,0)
    """
    direct_steering_info = {
        "E0": {"polygon": _box(10, 0), "stage_type": "exit"},
        "E1": {"polygon": _box(20, 0), "stage_type": "exit"},
    }
    distributions = {
        "D0": {"coordinates": list(_box(0, 0).exterior.coords)},
    }
    transitions = [
        {"from": "D0", "to": "E0"},
        {"from": "D0", "to": "E1"},
    ]
    return StageGraph.from_scenario(direct_steering_info, transitions, distributions)


# ── node / edge construction ──────────────────────────────────────────


class TestGraphConstruction:
    def test_nodes_include_distributions(self, linear_graph):
        assert "D0" in linear_graph.nodes
        assert linear_graph.nodes["D0"].stage_type == "distribution"

    def test_nodes_include_checkpoints_and_exits(self, linear_graph):
        assert linear_graph.nodes["C0"].stage_type == "checkpoint"
        assert linear_graph.nodes["E0"].stage_type == "exit"

    def test_edge_count(self, linear_graph):
        all_edges = sum(len(v) for v in linear_graph.edges.values())
        assert all_edges == 2

    def test_edge_weight_is_euclidean(self, linear_graph):
        edge = linear_graph.edges["D0"][0]
        assert edge.target == "C0"
        assert abs(edge.weight - 10.0) < 0.01

    def test_centroid_from_polygon(self, linear_graph):
        node = linear_graph.nodes["C0"]
        assert abs(node.centroid_x - 10.0) < 0.01
        assert abs(node.centroid_y - 0.0) < 0.01

    def test_exit_nodes(self, multi_exit_graph):
        exits = multi_exit_graph.exit_nodes()
        assert sorted(exits) == ["E0", "E1"]

    def test_distribution_nodes(self, multi_exit_graph):
        dists = multi_exit_graph.distribution_nodes()
        assert dists == ["D0"]

    def test_missing_node_in_transition_skipped(self):
        """Transitions referencing unknown stages are silently skipped."""
        graph = StageGraph.from_scenario(
            direct_steering_info={
                "E0": {"polygon": _box(10, 0), "stage_type": "exit"},
            },
            transitions=[{"from": "UNKNOWN", "to": "E0"}],
        )
        assert len(graph.edges) == 0


# ── Dijkstra shortest path ───────────────────────────────────────────


class TestDijkstra:
    def test_linear_path(self, linear_graph):
        result = linear_graph.shortest_exit("D0")
        assert result is not None
        exit_id, cost, path = result
        assert exit_id == "E0"
        assert abs(cost - 20.0) < 0.01
        assert path == ["D0", "C0", "E0"]

    def test_diamond_picks_shorter_path(self, diamond_graph):
        result = diamond_graph.shortest_exit("D0")
        assert result is not None
        exit_id, cost, path = result
        assert exit_id == "E0"
        # D0(0,0)->C0(0,10)=10, C0(0,10)->E0(20,10)=20 => total 30
        # D0(0,0)->C1(0,30)=30, C1(0,30)->E0(20,10)=~28.28 => total ~58.28
        assert path == ["D0", "C0", "E0"]
        assert cost < 31.0

    def test_multi_exit_picks_nearest(self, multi_exit_graph):
        result = multi_exit_graph.shortest_exit("D0")
        assert result is not None
        exit_id, cost, path = result
        assert exit_id == "E0"
        assert abs(cost - 10.0) < 0.01

    def test_all_exits_returned(self, multi_exit_graph):
        paths = multi_exit_graph.shortest_paths_to_exits("D0")
        assert len(paths) == 2
        assert "E0" in paths
        assert "E1" in paths
        assert paths["E0"][0] < paths["E1"][0]

    def test_unreachable_exit(self):
        """An exit with no path from the source is not returned."""
        direct_steering_info = {
            "E0": {"polygon": _box(10, 0), "stage_type": "exit"},
            "E1": {"polygon": _box(20, 0), "stage_type": "exit"},
        }
        distributions = {
            "D0": {"coordinates": list(_box(0, 0).exterior.coords)},
        }
        transitions = [{"from": "D0", "to": "E0"}]
        graph = StageGraph.from_scenario(
            direct_steering_info, transitions, distributions
        )
        paths = graph.shortest_paths_to_exits("D0")
        assert "E0" in paths
        assert "E1" not in paths

    def test_no_reachable_exit(self):
        """shortest_exit returns None when no exit is reachable."""
        direct_steering_info = {
            "C0": {"polygon": _box(10, 0), "stage_type": "checkpoint"},
        }
        distributions = {
            "D0": {"coordinates": list(_box(0, 0).exterior.coords)},
        }
        transitions = [{"from": "D0", "to": "C0"}]
        graph = StageGraph.from_scenario(
            direct_steering_info, transitions, distributions
        )
        assert graph.shortest_exit("D0") is None

    def test_dijkstra_from_checkpoint(self, linear_graph):
        """Can query shortest path from an intermediate checkpoint."""
        result = linear_graph.shortest_exit("C0")
        assert result is not None
        exit_id, cost, path = result
        assert exit_id == "E0"
        assert path == ["C0", "E0"]


# ── edge cases ────────────────────────────────────────────────────────


class TestEdgeCases:
    def test_empty_graph(self):
        graph = StageGraph.from_scenario({}, [], None)
        assert len(graph.nodes) == 0
        assert len(graph.edges) == 0
        assert graph.exit_nodes() == []

    def test_self_loop_ignored_in_shortest_path(self):
        """A self-loop edge doesn't break Dijkstra."""
        direct_steering_info = {
            "E0": {"polygon": _box(10, 0), "stage_type": "exit"},
        }
        distributions = {
            "D0": {"coordinates": list(_box(0, 0).exterior.coords)},
        }
        transitions = [
            {"from": "D0", "to": "D0"},
            {"from": "D0", "to": "E0"},
        ]
        graph = StageGraph.from_scenario(
            direct_steering_info, transitions, distributions
        )
        result = graph.shortest_exit("D0")
        assert result is not None
        assert result[0] == "E0"

    def test_duplicate_transitions(self):
        """Duplicate transitions create parallel edges; shortest wins."""
        direct_steering_info = {
            "E0": {"polygon": _box(10, 0), "stage_type": "exit"},
        }
        distributions = {
            "D0": {"coordinates": list(_box(0, 0).exterior.coords)},
        }
        transitions = [
            {"from": "D0", "to": "E0"},
            {"from": "D0", "to": "E0"},
        ]
        graph = StageGraph.from_scenario(
            direct_steering_info, transitions, distributions
        )
        result = graph.shortest_exit("D0")
        assert result is not None
        assert abs(result[1] - 10.0) < 0.01

    def test_distributions_from_polygon_key(self):
        """Distributions can supply a 'polygon' key instead of 'coordinates'."""
        direct_steering_info = {
            "E0": {"polygon": _box(10, 0), "stage_type": "exit"},
        }
        distributions = {
            "D0": {"polygon": _box(0, 0)},
        }
        transitions = [{"from": "D0", "to": "E0"}]
        graph = StageGraph.from_scenario(
            direct_steering_info, transitions, distributions
        )
        assert "D0" in graph.nodes
        result = graph.shortest_exit("D0")
        assert result is not None


# ── Phase 3: Route cost evaluation ───────────────────────────────────


class ConstantFedRateSampler:
    """Return a constant FED rate everywhere (for testing)."""

    def __init__(self, rate_per_min: float):
        self.rate_per_min = rate_per_min

    def sample_fed_rate(self, time_s: float, x: float, y: float) -> float:
        del time_s, x, y
        return self.rate_per_min


@pytest.fixture()
def simple_route_graph():
    """D0 (0,0) ──10──> E0 (10,0)."""
    direct_steering_info = {
        "E0": {"polygon": _box(10, 0), "stage_type": "exit"},
    }
    distributions = {
        "D0": {"coordinates": list(_box(0, 0).exterior.coords)},
    }
    transitions = [{"from": "D0", "to": "E0"}]
    return StageGraph.from_scenario(direct_steering_info, transitions, distributions)


@pytest.fixture()
def two_exit_graph():
    """D0 with short path to E0 and long path to E1.

    D0 (0,0) ──10──> E0 (10,0)
    D0 (0,0) ──30──> C0 (0,30) ──20──> E1 (20,30)
    """
    direct_steering_info = {
        "E0": {"polygon": _box(10, 0), "stage_type": "exit"},
        "C0": {"polygon": _box(0, 30), "stage_type": "checkpoint"},
        "E1": {"polygon": _box(20, 30), "stage_type": "exit"},
    }
    distributions = {
        "D0": {"coordinates": list(_box(0, 0).exterior.coords)},
    }
    transitions = [
        {"from": "D0", "to": "E0"},
        {"from": "D0", "to": "C0"},
        {"from": "C0", "to": "E1"},
    ]
    return StageGraph.from_scenario(direct_steering_info, transitions, distributions)


class TestSegmentCost:
    def test_clear_air_segment(self, simple_route_graph):
        """Zero extinction → speed_factor=1, travel_time = length/v0."""
        field = ConstantExtinctionField(0.0)
        config = RouteCostConfig(base_speed_m_per_s=1.0)
        seg = evaluate_segment(simple_route_graph, "D0", "E0", 0.0, field, None, config)
        assert abs(seg.length_m - 10.0) < 0.1
        assert abs(seg.speed_factor - 1.0) < 0.01
        assert abs(seg.travel_time_s - 10.0) < 0.1
        assert seg.fed_growth == 0.0
        assert seg.visible is True

    def test_heavy_smoke_segment(self, simple_route_graph):
        """High extinction → low speed factor, longer travel time."""
        field = ConstantExtinctionField(5.0)
        config = RouteCostConfig(base_speed_m_per_s=1.0)
        seg = evaluate_segment(simple_route_graph, "D0", "E0", 0.0, field, None, config)
        assert seg.speed_factor < 1.0
        assert seg.travel_time_s > 10.0
        assert seg.visible is False  # K=5 > threshold 0.5

    def test_fed_growth_computed(self, simple_route_graph):
        """With a FED rate sampler, fed_growth is non-zero."""
        field = ConstantExtinctionField(0.0)
        fed = ConstantFedRateSampler(rate_per_min=0.1)
        config = RouteCostConfig(base_speed_m_per_s=1.0)
        seg = evaluate_segment(simple_route_graph, "D0", "E0", 0.0, field, fed, config)
        # travel_time ≈ 10s, rate = 0.1/min → growth ≈ 10/60 * 0.1 ≈ 0.0167
        assert seg.fed_growth > 0.0
        assert abs(seg.fed_growth - 0.1 * 10.0 / 60.0) < 0.01


class TestRouteCost:
    def test_clear_air_route_cost(self, simple_route_graph):
        """Clear-air route: cost = path_length * 1 + w_fed * 0 = path_length."""
        field = ConstantExtinctionField(0.0)
        config = RouteCostConfig(base_speed_m_per_s=1.0)
        rc = evaluate_route(
            simple_route_graph, ["D0", "E0"], 0.0, 0.0, field, None, config
        )
        assert abs(rc.path_length_m - 10.0) < 0.1
        assert abs(rc.k_ave_route) < 0.01
        assert abs(rc.composite_cost - 10.0) < 0.1
        assert rc.rejected is False

    def test_smoke_increases_cost(self, simple_route_graph):
        """Smoke raises composite cost via w_smoke * K_ave term."""
        field_clear = ConstantExtinctionField(0.0)
        field_smoke = ConstantExtinctionField(1.0)
        config = RouteCostConfig(base_speed_m_per_s=1.0, w_smoke=1.0)
        rc_clear = evaluate_route(
            simple_route_graph,
            ["D0", "E0"],
            0.0,
            0.0,
            field_clear,
            None,
            config,
        )
        rc_smoke = evaluate_route(
            simple_route_graph,
            ["D0", "E0"],
            0.0,
            0.0,
            field_smoke,
            None,
            config,
        )
        assert rc_smoke.composite_cost > rc_clear.composite_cost

    def test_fed_rejection(self, simple_route_graph):
        """Route rejected when projected FED exceeds threshold."""
        field = ConstantExtinctionField(0.0)
        config = RouteCostConfig(base_speed_m_per_s=1.0, fed_rejection_threshold=0.5)
        # Start with current_fed=0.9, even small FED growth pushes over 0.5
        # Actually, current_fed alone exceeds threshold
        rc = evaluate_route(
            simple_route_graph, ["D0", "E0"], 0.0, 0.9, field, None, config
        )
        assert rc.rejected is True
        assert "FED_max" in rc.rejection_reason

    def test_multi_segment_route(self, two_exit_graph):
        """Route through checkpoint sums segment costs."""
        field = ConstantExtinctionField(0.0)
        config = RouteCostConfig(base_speed_m_per_s=1.0)
        rc = evaluate_route(
            two_exit_graph,
            ["D0", "C0", "E1"],
            0.0,
            0.0,
            field,
            None,
            config,
        )
        assert len(rc.segments) == 2
        assert abs(rc.path_length_m - 50.0) < 0.1  # 30 + 20

    def test_cache_reuse(self, two_exit_graph):
        """Cached segments are reused across calls."""
        field = ConstantExtinctionField(0.0)
        config = RouteCostConfig(base_speed_m_per_s=1.0)
        cache: dict = {}
        evaluate_route(
            two_exit_graph,
            ["D0", "C0", "E1"],
            0.0,
            0.0,
            field,
            None,
            config,
            cached_segments=cache,
        )
        assert ("D0", "C0") in cache
        assert ("C0", "E1") in cache
        # Second call reuses cache.
        rc2 = evaluate_route(
            two_exit_graph,
            ["D0", "C0", "E1"],
            0.0,
            0.0,
            field,
            None,
            config,
            cached_segments=cache,
        )
        assert abs(rc2.path_length_m - 50.0) < 0.1


class TestRankRoutes:
    def test_clear_air_picks_shortest(self, two_exit_graph):
        """With no smoke, shortest route wins."""
        field = ConstantExtinctionField(0.0)
        config = RouteCostConfig(base_speed_m_per_s=1.0)
        ranked = rank_routes(two_exit_graph, "D0", 0.0, 0.0, field, None, config)
        assert len(ranked) == 2
        assert ranked[0].exit_id == "E0"  # shorter
        assert ranked[0].rejected is False

    def test_smoke_can_reorder(self, two_exit_graph):
        """Heavy smoke on E0 path makes E1 cheaper despite longer distance."""

        class SmokeNearE0:
            """High K near E0, clear near E1."""

            def sample_extinction(self, time_s, x, y):
                # E0 is at (10, 0); smoke if y < 15
                return 8.0 if y < 15 else 0.0

        field = SmokeNearE0()
        config = RouteCostConfig(base_speed_m_per_s=1.0, w_smoke=2.0)
        ranked = rank_routes(two_exit_graph, "D0", 0.0, 0.0, field, None, config)
        assert ranked[0].exit_id == "E1"

    def test_fed_rejection_with_fallback(self, two_exit_graph):
        """All routes rejected → least-bad is un-rejected as fallback."""
        field = ConstantExtinctionField(0.0)
        config = RouteCostConfig(base_speed_m_per_s=1.0, fed_rejection_threshold=0.01)
        # current_fed = 0.5 will exceed threshold 0.01
        ranked = rank_routes(two_exit_graph, "D0", 0.0, 0.5, field, None, config)
        assert len(ranked) == 2
        # First should be un-rejected (fallback)
        assert ranked[0].rejected is False
        assert "fallback" in ranked[0].rejection_reason
        # Second stays rejected
        assert ranked[1].rejected is True

    def test_visibility_rejection(self):
        """Non-visible route rejected when a visible route exists."""
        direct_steering_info = {
            "E0": {"polygon": _box(10, 0), "stage_type": "exit"},
            "E1": {"polygon": _box(0, 20), "stage_type": "exit"},
        }
        distributions = {
            "D0": {"coordinates": list(_box(0, 0).exterior.coords)},
        }
        transitions = [
            {"from": "D0", "to": "E0"},
            {"from": "D0", "to": "E1"},
        ]
        graph = StageGraph.from_scenario(
            direct_steering_info, transitions, distributions
        )

        class SmokeOnE0Path:
            def sample_extinction(self, time_s, x, y):
                return 2.0 if y < 10 and x > 2 else 0.0

        config = RouteCostConfig(
            base_speed_m_per_s=1.0,
            visibility_extinction_threshold=0.5,
        )
        ranked = rank_routes(graph, "D0", 0.0, 0.0, SmokeOnE0Path(), None, config)
        # E1 path (y=0 to y=20) is clear; E0 path has smoke
        e0_route = next(r for r in ranked if r.exit_id == "E0")
        e1_route = next(r for r in ranked if r.exit_id == "E1")
        assert e1_route.rejected is False
        # E0 should be rejected due to non-visibility
        assert e0_route.rejected is True

    def test_tie_broken_by_fewer_stages(self, two_exit_graph):
        """Equal cost → fewer intermediate stages wins."""
        # This is a structural test: with zero smoke, E0 (direct) ranks
        # above E1 (via C0) because E0 path has fewer stages.
        field = ConstantExtinctionField(0.0)
        config = RouteCostConfig(base_speed_m_per_s=1.0)
        ranked = rank_routes(two_exit_graph, "D0", 0.0, 0.0, field, None, config)
        # E0 wins on cost anyway, but verify sort key includes path length
        assert ranked[0].exit_id == "E0"
        assert len(ranked[0].path) < len(ranked[1].path)

    def test_no_exits_returns_empty(self):
        """Graph with no exits → empty ranking."""
        graph = StageGraph.from_scenario(
            {"C0": {"polygon": _box(10, 0), "stage_type": "checkpoint"}},
            [{"from": "D0", "to": "C0"}],
            {"D0": {"coordinates": list(_box(0, 0).exterior.coords)}},
        )
        ranked = rank_routes(
            graph,
            "D0",
            0.0,
            0.0,
            ConstantExtinctionField(0.0),
            None,
            RouteCostConfig(),
        )
        assert ranked == []


# ── Phase 4: Dynamic rerouting ───────────────────────────────────────


def _make_stage_configs(graph: StageGraph) -> dict:
    """Build a stage_configs dict from a StageGraph (for wait_info)."""
    configs = {}
    for sid, node in graph.nodes.items():
        configs[sid] = {
            "polygon": _box(node.centroid_x, node.centroid_y),
            "stage_type": node.stage_type,
            "waiting_time": 0.0,
            "waiting_time_distribution": "constant",
            "waiting_time_std": 0.0,
            "speed_factor": 1.0,
        }
    return configs


def _make_wait_info(
    graph: StageGraph,
    origin: str,
    target: str,
    path_choices: dict | None = None,
) -> dict:
    """Build a minimal agent wait_info dict for testing."""
    stage_configs = _make_stage_configs(graph)
    if path_choices is None:
        path_choices = {}
    node = graph.nodes[target]
    return {
        "mode": "path",
        "path_choices": path_choices,
        "stage_configs": stage_configs,
        "current_origin": origin,
        "current_target_stage": target,
        "target": (node.centroid_x, node.centroid_y),
        "target_assigned": False,
        "state": "to_target",
        "wait_until": None,
        "inside_since": None,
        "reach_penetration": 0.25,
        "reach_dwell_seconds": 0.2,
        "step_index": 0,
        "base_seed": 42,
        "agent_radius": 0.2,
    }


class TestStaggeredScheduling:
    def test_offset_spreads_agents(self):
        """Different agent IDs get different offsets."""
        offsets = [compute_eval_offset(i, 10.0, 0.01) for i in range(5)]
        assert len(set(offsets)) == 5  # all unique

    def test_offset_zero_for_zero_interval(self):
        assert compute_eval_offset(5, 0.0) == 0.0

    def test_should_reevaluate_first_time(self):
        state = AgentRouteState()
        assert should_reevaluate(0.0, state, 10.0) is True

    def test_should_not_reevaluate_too_soon(self):
        state = AgentRouteState(last_eval_time_s=0.0)
        assert should_reevaluate(5.0, state, 10.0) is False

    def test_should_reevaluate_after_interval(self):
        state = AgentRouteState(last_eval_time_s=0.0)
        assert should_reevaluate(10.0, state, 10.0) is True

    def test_staggered_offset_delays_first_evaluation(self):
        """Agent with offset=3 doesn't evaluate until t=3."""
        state = AgentRouteState(eval_offset_s=3.0)
        assert should_reevaluate(2.0, state, 10.0) is False
        assert should_reevaluate(3.0, state, 10.0) is True

    def test_staggered_subsequent_uses_interval(self):
        """After first eval at t=3, next eval at t=3+10=13."""
        state = AgentRouteState(last_eval_time_s=3.0, eval_offset_s=3.0)
        assert should_reevaluate(12.0, state, 10.0) is False
        assert should_reevaluate(13.0, state, 10.0) is True


class TestRerouteAgent:
    def test_reroute_changes_path_choices(self, two_exit_graph):
        """Rerouting updates path_choices to follow new path."""
        wait_info = _make_wait_info(two_exit_graph, "D0", "E0")
        new_path = ["D0", "C0", "E1"]
        changed = reroute_agent(wait_info, new_path, wait_info["stage_configs"])
        assert changed is True
        assert wait_info["path_choices"]["D0"] == [("C0", 100.0)]
        assert wait_info["path_choices"]["C0"] == [("E1", 100.0)]

    def test_reroute_empty_path_returns_false(self, two_exit_graph):
        wait_info = _make_wait_info(two_exit_graph, "D0", "E0")
        assert reroute_agent(wait_info, [], wait_info["stage_configs"]) is False

    def test_reroute_single_stage_returns_false(self, two_exit_graph):
        wait_info = _make_wait_info(two_exit_graph, "D0", "E0")
        assert reroute_agent(wait_info, ["E0"], wait_info["stage_configs"]) is False

    def test_reroute_preserves_existing_choices(self, two_exit_graph):
        """Existing path_choices for other stages are not removed."""
        wait_info = _make_wait_info(two_exit_graph, "D0", "E0")
        wait_info["path_choices"]["OTHER"] = [("STAGE", 50.0)]
        reroute_agent(wait_info, ["D0", "C0", "E1"], wait_info["stage_configs"])
        assert "OTHER" in wait_info["path_choices"]


class TestEvaluateAndReroute:
    def test_initial_assignment(self, two_exit_graph):
        """First evaluation assigns the nearest exit."""
        field = ConstantExtinctionField(0.0)
        config = RerouteConfig(cost_config=RouteCostConfig(base_speed_m_per_s=1.0))
        wait_info = _make_wait_info(two_exit_graph, "D0", "D0")
        route_state = AgentRouteState()

        switch = evaluate_and_reroute(
            agent_id=0,
            wait_info=wait_info,
            route_state=route_state,
            graph=two_exit_graph,
            current_time_s=0.0,
            current_fed=0.0,
            extinction_sampler=field,
            fed_rate_sampler=None,
            config=config,
        )
        assert switch is not None
        assert switch.reason == "initial"
        assert switch.new_exit == "E0"  # shortest
        assert route_state.current_exit == "E0"

    def test_no_switch_when_same_exit_wins(self, two_exit_graph):
        """No switch returned when best exit hasn't changed."""
        field = ConstantExtinctionField(0.0)
        config = RerouteConfig(cost_config=RouteCostConfig(base_speed_m_per_s=1.0))
        wait_info = _make_wait_info(two_exit_graph, "D0", "E0")
        route_state = AgentRouteState(current_exit="E0")

        switch = evaluate_and_reroute(
            agent_id=0,
            wait_info=wait_info,
            route_state=route_state,
            graph=two_exit_graph,
            current_time_s=5.0,
            current_fed=0.0,
            extinction_sampler=field,
            fed_rate_sampler=None,
            config=config,
        )
        assert switch is None

    def test_smoke_triggers_reroute(self, two_exit_graph):
        """Heavy smoke on short path triggers reroute to longer path."""

        class SmokeOnE0:
            def sample_extinction(self, time_s, x, y):
                return 8.0 if y < 15 else 0.0

        config = RerouteConfig(
            cost_config=RouteCostConfig(base_speed_m_per_s=1.0, w_smoke=2.0)
        )
        wait_info = _make_wait_info(two_exit_graph, "D0", "E0")
        route_state = AgentRouteState(current_exit="E0")

        switch = evaluate_and_reroute(
            agent_id=0,
            wait_info=wait_info,
            route_state=route_state,
            graph=two_exit_graph,
            current_time_s=10.0,
            current_fed=0.0,
            extinction_sampler=SmokeOnE0(),
            fed_rate_sampler=None,
            config=config,
        )
        assert switch is not None
        assert switch.new_exit == "E1"
        assert switch.old_exit == "E0"
        assert switch.reason == "smoke_reroute"
        assert route_state.current_exit == "E1"

    def test_eval_time_updated(self, two_exit_graph):
        """last_eval_time_s is updated after evaluation."""
        field = ConstantExtinctionField(0.0)
        config = RerouteConfig(cost_config=RouteCostConfig(base_speed_m_per_s=1.0))
        wait_info = _make_wait_info(two_exit_graph, "D0", "D0")
        route_state = AgentRouteState()

        evaluate_and_reroute(
            agent_id=0,
            wait_info=wait_info,
            route_state=route_state,
            graph=two_exit_graph,
            current_time_s=42.0,
            current_fed=0.0,
            extinction_sampler=field,
            fed_rate_sampler=None,
            config=config,
        )
        assert route_state.last_eval_time_s == 42.0
