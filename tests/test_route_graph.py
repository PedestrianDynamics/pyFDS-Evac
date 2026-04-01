"""Tests for StageGraph construction and Dijkstra shortest-path routing."""

import pytest
from shapely.geometry import Polygon

from pyfds_evac.core.route_graph import (
    StageEdge,
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
from pyfds_evac.core.smoke_speed import ConstantExtinctionField


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


# ── integrated_extinction_along_los tests ─────────────────────────────


class TestIntegratedExtinctionAlongLos:
    """Tests for the public integrated_extinction_along_los helper."""

    def test_constant_field_returns_constant(self):
        """With uniform extinction, the path-integrated mean equals the constant."""
        from pyfds_evac.core.route_graph import integrated_extinction_along_los

        field = ConstantExtinctionField(extinction_per_m=2.5)
        result = integrated_extinction_along_los(
            0.0,
            0.0,
            10.0,
            0.0,
            time_s=0.0,
            extinction_sampler=field,
            step_m=2.0,
        )
        assert result == pytest.approx(2.5)

    def test_zero_length_los(self):
        """Zero-length LOS returns the extinction at the single point."""
        from pyfds_evac.core.route_graph import integrated_extinction_along_los

        field = ConstantExtinctionField(extinction_per_m=3.0)
        result = integrated_extinction_along_los(
            5.0,
            5.0,
            5.0,
            5.0,
            time_s=0.0,
            extinction_sampler=field,
        )
        assert result == pytest.approx(3.0)

    def test_step_m_validation(self):
        """step_m <= 0 raises ValueError."""
        from pyfds_evac.core.route_graph import integrated_extinction_along_los

        field = ConstantExtinctionField(extinction_per_m=1.0)
        with pytest.raises(ValueError, match="step_m must be positive"):
            integrated_extinction_along_los(
                0.0,
                0.0,
                10.0,
                0.0,
                time_s=0.0,
                extinction_sampler=field,
                step_m=0.0,
            )
        with pytest.raises(ValueError, match="step_m must be positive"):
            integrated_extinction_along_los(
                0.0,
                0.0,
                10.0,
                0.0,
                time_s=0.0,
                extinction_sampler=field,
                step_m=-1.0,
            )

    def test_nontrivial_sampler(self):
        """A spatially varying field produces the expected arithmetic mean."""
        from pyfds_evac.core.route_graph import integrated_extinction_along_los

        class LinearExtinction:
            """K increases linearly with x: K(x) = x."""

            def sample_extinction(self, time_s, x, y):
                return float(x)

        field = LinearExtinction()
        # LOS from x=0 to x=10, step_m=5 -> samples at x=0, 5, 10
        # mean = (0 + 5 + 10) / 3 = 5.0
        result = integrated_extinction_along_los(
            0.0,
            0.0,
            10.0,
            0.0,
            time_s=0.0,
            extinction_sampler=field,
            step_m=5.0,
        )
        assert result == pytest.approx(5.0)

    def test_diagonal_los(self):
        """Diagonal LOS samples correctly along both axes."""
        from pyfds_evac.core.route_graph import integrated_extinction_along_los

        field = ConstantExtinctionField(extinction_per_m=1.5)
        result = integrated_extinction_along_los(
            0.0,
            0.0,
            3.0,
            4.0,
            time_s=10.0,
            extinction_sampler=field,
            step_m=1.0,
        )
        assert result == pytest.approx(1.5)


class TestEdgeWaypoints:
    def test_edge_has_waypoints_field(self):
        edge = StageEdge(
            source="A", target="B", weight=10.0, waypoints=[(0, 0), (5, 5), (10, 0)]
        )
        assert edge.waypoints == [(0, 0), (5, 5), (10, 0)]

    def test_edge_waypoints_defaults_to_empty(self):
        edge = StageEdge(source="A", target="B", weight=10.0)
        assert edge.waypoints == []


class TestPolylineEdges:
    def test_from_scenario_with_walkable_polygon_sets_waypoints(self):
        """When a walkable polygon is provided, edges get polyline waypoints."""
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
        # A simple rectangular walkable area covering all stages.
        walkable = Polygon([(-5, -5), (25, -5), (25, 5), (-5, 5)])
        graph = StageGraph.from_scenario(
            direct_steering_info,
            transitions,
            distributions,
            walkable_polygon=walkable,
        )
        # Each edge should have non-empty waypoints.
        for edges in graph.edges.values():
            for edge in edges:
                assert len(edge.waypoints) >= 2, (
                    f"Edge {edge.source}->{edge.target} has no waypoints"
                )

    def test_from_scenario_without_polygon_uses_centroid_ray(self):
        """Without walkable polygon, edges get 2-point centroid-to-centroid waypoints."""
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
        graph = StageGraph.from_scenario(
            direct_steering_info,
            transitions,
            distributions,
        )
        for edges in graph.edges.values():
            for edge in edges:
                assert len(edge.waypoints) == 2
                src_node = graph.nodes[edge.source]
                tgt_node = graph.nodes[edge.target]
                assert edge.waypoints[0] == pytest.approx(
                    (src_node.centroid_x, src_node.centroid_y)
                )
                assert edge.waypoints[1] == pytest.approx(
                    (tgt_node.centroid_x, tgt_node.centroid_y)
                )

    def test_edge_weight_is_polyline_length(self):
        """Edge weight equals the polyline length, not Euclidean distance."""
        direct_steering_info = {
            "E0": {"polygon": _box(20, 0), "stage_type": "exit"},
        }
        distributions = {
            "D0": {"coordinates": list(_box(0, 0).exterior.coords)},
        }
        transitions = [{"from": "D0", "to": "E0"}]
        # Without walkable polygon, weight = Euclidean = polyline length
        # (2-point straight ray).
        graph = StageGraph.from_scenario(
            direct_steering_info,
            transitions,
            distributions,
        )
        edge = graph.edges["D0"][0]
        expected = 20.0  # Euclidean (0,0)->(20,0)
        assert edge.weight == pytest.approx(expected, abs=0.01)


class TestPolylineSampling:
    def test_extinction_along_polyline_samples_waypoints(self):
        """Extinction sampling should follow polyline, not straight ray."""
        from pyfds_evac.core.route_graph import integrated_extinction_along_polyline

        class SpatialField:
            """Returns K=0 below y=5, K=10 above y=5."""

            def sample_extinction(self, time_s, x, y):
                return 0.0 if y < 5.0 else 10.0

        # Polyline that goes up through the smoky region and back down.
        # (0,0) -> (0,10) -> (10,10) -> (10,0), total arc = 30 m.
        # 20 m is in the smoky region (y>=5): full middle segment + halves of the
        # two vertical segments. The straight centroid ray stays at y=0, giving K=0.
        waypoints = [(0, 0), (0, 10), (10, 10), (10, 0)]
        k_avg = integrated_extinction_along_polyline(
            waypoints=waypoints,
            time_s=0.0,
            extinction_sampler=SpatialField(),
            step_m=1.0,
        )
        # ~2/3 of the path is in smoke (K=10): expected ~6.7.
        assert k_avg == pytest.approx(6.7, abs=1.0)
        # Centroid ray (0,0)->(10,0) stays at y=0 → K=0; polyline is much higher.
        assert k_avg > 4.0

    def test_extinction_along_polyline_two_points_matches_los(self):
        """Two-point polyline should match the straight-line LOS function."""
        from pyfds_evac.core.route_graph import (
            integrated_extinction_along_los,
            integrated_extinction_along_polyline,
        )

        field = ConstantExtinctionField(extinction_per_m=3.0)
        waypoints = [(0, 0), (10, 0)]
        k_poly = integrated_extinction_along_polyline(
            waypoints=waypoints,
            time_s=0.0,
            extinction_sampler=field,
            step_m=2.0,
        )
        k_los = integrated_extinction_along_los(
            0,
            0,
            10,
            0,
            time_s=0.0,
            extinction_sampler=field,
            step_m=2.0,
        )
        assert k_poly == pytest.approx(k_los, abs=0.01)

    def test_evaluate_segment_uses_polyline_waypoints(self):
        """evaluate_segment uses edge waypoints for extinction, not centroid ray."""
        from pyfds_evac.core.route_graph import (
            RouteCostConfig,
            StageEdge,
            StageGraph,
            StageNode,
            evaluate_segment,
        )

        class SmokyAboveY5:
            """K=0 below y=5, K=10 above."""

            def sample_extinction(self, time_s, x, y):
                return 0.0 if y < 5.0 else 10.0

        # Two nodes at (0,0) and (10,0) — centroid ray stays below y=5 (clear).
        src = StageNode(
            stage_id="A", centroid_x=0.0, centroid_y=0.0, stage_type="distribution"
        )
        tgt = StageNode(
            stage_id="B", centroid_x=10.0, centroid_y=0.0, stage_type="exit"
        )
        # Polyline detours through smoky zone: (0,0)->(0,10)->(10,10)->(10,0)
        waypoints = [(0.0, 0.0), (0.0, 10.0), (10.0, 10.0), (10.0, 0.0)]
        edge = StageEdge(source="A", target="B", weight=30.0, waypoints=waypoints)
        graph = StageGraph(
            nodes={"A": src, "B": tgt},
            edges={"A": [edge]},
        )

        cost = evaluate_segment(
            graph=graph,
            source="A",
            target="B",
            time_s=0.0,
            extinction_sampler=SmokyAboveY5(),
            fed_rate_sampler=None,
            config=RouteCostConfig(sampling_step_m=1.0),
        )
        # Polyline is ~2/3 smoky → k_avg ~6.7; centroid ray at y=0 gives 0.
        assert cost.k_avg == pytest.approx(6.7, abs=1.0)
        assert cost.k_avg > 4.0  # definitely not zero (centroid-ray result)

    def test_polyline_midpoint_used_for_fed(self):
        """FED rate is sampled at polyline midpoint, not centroid midpoint."""
        from pyfds_evac.core.route_graph import (
            RouteCostConfig,
            StageEdge,
            StageGraph,
            StageNode,
            evaluate_segment,
        )

        class FedAtY10:
            """FED rate = 1.0/min only at y >= 9, else 0."""

            def sample_fed_rate(self, time_s, x, y):
                return 1.0 if y >= 9.0 else 0.0

        # Centroid midpoint: (5, 0) → FED rate = 0
        # Polyline midpoint of (0,0)->(0,10)->(10,10)->(10,0) is at arc-half
        # Total arc = 10+10+10 = 30, half = 15.
        # Arc 0→10 along first segment: at arc=10 we're at (0,10).
        # Remaining 5 → midpoint is (5, 10), y=10 ≥ 9 → FED rate = 1.
        src = StageNode(
            stage_id="A", centroid_x=0.0, centroid_y=0.0, stage_type="distribution"
        )
        tgt = StageNode(
            stage_id="B", centroid_x=10.0, centroid_y=0.0, stage_type="exit"
        )
        waypoints = [(0.0, 0.0), (0.0, 10.0), (10.0, 10.0), (10.0, 0.0)]
        edge = StageEdge(source="A", target="B", weight=30.0, waypoints=waypoints)
        graph = StageGraph(
            nodes={"A": src, "B": tgt},
            edges={"A": [edge]},
        )

        cost = evaluate_segment(
            graph=graph,
            source="A",
            target="B",
            time_s=0.0,
            extinction_sampler=ConstantExtinctionField(extinction_per_m=0.0),
            fed_rate_sampler=FedAtY10(),
            config=RouteCostConfig(sampling_step_m=1.0),
        )
        assert cost.fed_growth > 0.0  # polyline midpoint is in high-FED zone


# ── Phase 4: Dynamic Dijkstra with smoke-adjusted weights ────────────────


class TestDynamicDijkstra:
    def test_dynamic_weights_override_static(self, diamond_graph):
        """Dijkstra with dynamic weights picks a different path than static."""
        # Static: D0->C0->E0 is shorter than D0->C1->E0.
        static_paths = diamond_graph.shortest_paths_to_exits("D0")
        static_path = static_paths["E0"][1]
        assert "C0" in static_path  # shorter geometric path

        # Dynamic: make D0->C0 very expensive, D0->C1 cheap.
        dynamic_weights = {
            ("D0", "C0"): 1000.0,
            ("D0", "C1"): 1.0,
            ("C0", "E0"): 1.0,
            ("C1", "E0"): 1.0,
        }
        dynamic_paths = diamond_graph.shortest_paths_to_exits(
            "D0", dynamic_weights=dynamic_weights
        )
        dynamic_path = dynamic_paths["E0"][1]
        assert "C1" in dynamic_path  # longer geometric but cheaper dynamic

    def test_dynamic_weights_none_uses_static(self, diamond_graph):
        """When dynamic_weights=None, behavior is unchanged."""
        paths_default = diamond_graph.shortest_paths_to_exits("D0")
        paths_explicit = diamond_graph.shortest_paths_to_exits(
            "D0", dynamic_weights=None
        )
        assert paths_default == paths_explicit


class TestDynamicRanking:
    def test_rank_routes_uses_dynamic_dijkstra(self, diamond_graph):
        """rank_routes should pick the dynamically cheaper path, not geometric shortest."""

        class SpatialSmoke:
            """Heavy smoke near C0 (0,10), clear near C1 (0,30)."""

            def sample_extinction(self, time_s, x, y):
                if abs(y - 10.0) < 5.0:
                    return 5.0  # heavy smoke near C0
                return 0.0

        ranked = rank_routes(
            diamond_graph,
            source="D0",
            time_s=0.0,
            current_fed=0.0,
            extinction_sampler=SpatialSmoke(),
            fed_rate_sampler=None,
            config=RouteCostConfig(),
        )
        assert len(ranked) >= 1
        best = ranked[0]
        # With heavy smoke on the C0 path, the C1 path should win
        # even though it is geometrically longer.
        assert "C1" in best.path, f"Expected C1 path due to smoke, got {best.path}"


class TestFedRateAdapter:
    def test_evaluate_segment_with_fed_sampler(self, linear_graph):
        """evaluate_segment should compute non-zero fed_growth when sampler is provided."""

        class ConstantFedRate:
            def sample_fed_rate(self, time_s, x, y):
                return 0.1  # 0.1 /min everywhere

        seg = evaluate_segment(
            linear_graph,
            "D0",
            "C0",
            time_s=0.0,
            extinction_sampler=ConstantExtinctionField(extinction_per_m=0.0),
            fed_rate_sampler=ConstantFedRate(),
            config=RouteCostConfig(),
        )
        assert seg.fed_growth > 0.0
        # travel_time = 10m / 1.3 m/s ≈ 7.69s; fed_growth = 0.1 * 7.69 / 60
        expected_growth = 0.1 * seg.travel_time_s / 60.0
        assert seg.fed_growth == pytest.approx(expected_growth, rel=0.01)


class TestStageNodeCapacity:
    def test_default_capacity_is_none(self):
        from pyfds_evac.core.route_graph import StageNode

        node = StageNode(
            stage_id="E0",
            centroid_x=0.0,
            centroid_y=0.0,
            stage_type="exit",
        )
        assert node.capacity_agents_per_s is None

    def test_capacity_set_from_constructor(self):
        from pyfds_evac.core.route_graph import StageNode

        node = StageNode(
            stage_id="E0",
            centroid_x=0.0,
            centroid_y=0.0,
            stage_type="exit",
            capacity_agents_per_s=2.5,
        )
        assert node.capacity_agents_per_s == 2.5

    def test_capacity_propagated_from_scenario(self):
        direct_steering_info = {
            "E0": {
                "polygon": _box(10, 0),
                "stage_type": "exit",
                "capacity_agents_per_s": 2.0,
            },
        }
        distributions = {
            "D0": {"coordinates": list(_box(0, 0).exterior.coords)},
        }
        transitions = [{"from": "D0", "to": "E0"}]
        graph = StageGraph.from_scenario(
            direct_steering_info, transitions, distributions
        )
        assert graph.nodes["E0"].capacity_agents_per_s == 2.0
        assert graph.nodes["D0"].capacity_agents_per_s is None


class TestQueueConfigAndFields:
    def test_route_cost_config_defaults(self):
        config = RouteCostConfig()
        assert config.w_queue == 1.0
        assert config.default_exit_capacity == 1.3

    def test_route_cost_config_queue_disabled(self):
        config = RouteCostConfig(w_queue=0.0)
        assert config.w_queue == 0.0

    def test_route_cost_has_queue_time_field(self, linear_graph):
        field = ConstantExtinctionField(0.0)
        config = RouteCostConfig()
        rc = evaluate_route(
            linear_graph, ["D0", "C0", "E0"], 0.0, 0.0, field, None, config
        )
        assert hasattr(rc, "queue_time_s")
        assert rc.queue_time_s == 0.0


class TestQueueCostTerm:
    def test_evaluate_route_adds_queue_cost(self, multi_exit_graph):
        """Queue term increases composite cost for a congested exit."""
        field = ConstantExtinctionField(0.0)
        config = RouteCostConfig(w_smoke=0.0, w_fed=0.0, w_queue=1.0)
        rc_no_queue = evaluate_route(
            multi_exit_graph,
            ["D0", "E0"],
            0.0,
            0.0,
            field,
            None,
            config,
        )
        rc_with_queue = evaluate_route(
            multi_exit_graph,
            ["D0", "E0"],
            0.0,
            0.0,
            field,
            None,
            config,
            exit_counts={"E0": 20, "E1": 0},
        )
        assert rc_with_queue.composite_cost > rc_no_queue.composite_cost
        assert rc_with_queue.queue_time_s > 0.0
        assert rc_no_queue.queue_time_s == 0.0

    def test_queue_cost_uses_distance_equivalent(self, multi_exit_graph):
        """Queue cost = w_queue * base_speed * N / capacity."""
        field = ConstantExtinctionField(0.0)
        base_speed = 1.3
        capacity = 1.3
        n_agents = 10
        config = RouteCostConfig(
            w_smoke=0.0,
            w_fed=0.0,
            w_queue=1.0,
            base_speed_m_per_s=base_speed,
            default_exit_capacity=capacity,
        )
        rc = evaluate_route(
            multi_exit_graph,
            ["D0", "E0"],
            0.0,
            0.0,
            field,
            None,
            config,
            exit_counts={"E0": n_agents},
        )
        expected_queue_time = n_agents / capacity
        expected_queue_distance = base_speed * expected_queue_time
        assert abs(rc.queue_time_s - expected_queue_time) < 1e-6
        assert (
            abs(rc.composite_cost - (rc.path_length_m + expected_queue_distance)) < 0.1
        )

    def test_w_queue_zero_disables_queue(self, multi_exit_graph):
        """w_queue=0 means exit_counts have no effect."""
        field = ConstantExtinctionField(0.0)
        config = RouteCostConfig(w_smoke=0.0, w_fed=0.0, w_queue=0.0)
        rc_no_counts = evaluate_route(
            multi_exit_graph,
            ["D0", "E0"],
            0.0,
            0.0,
            field,
            None,
            config,
        )
        rc_with_counts = evaluate_route(
            multi_exit_graph,
            ["D0", "E0"],
            0.0,
            0.0,
            field,
            None,
            config,
            exit_counts={"E0": 100},
        )
        assert abs(rc_no_counts.composite_cost - rc_with_counts.composite_cost) < 1e-9

    def test_custom_capacity_reduces_penalty(self, multi_exit_graph):
        """Higher capacity -> lower queue penalty for same agent count."""
        field = ConstantExtinctionField(0.0)
        config_low = RouteCostConfig(
            w_smoke=0.0, w_fed=0.0, w_queue=1.0, default_exit_capacity=1.0
        )
        config_high = RouteCostConfig(
            w_smoke=0.0, w_fed=0.0, w_queue=1.0, default_exit_capacity=5.0
        )
        counts = {"E0": 20}
        rc_low = evaluate_route(
            multi_exit_graph,
            ["D0", "E0"],
            0.0,
            0.0,
            field,
            None,
            config_low,
            exit_counts=counts,
        )
        rc_high = evaluate_route(
            multi_exit_graph,
            ["D0", "E0"],
            0.0,
            0.0,
            field,
            None,
            config_high,
            exit_counts=counts,
        )
        assert rc_low.composite_cost > rc_high.composite_cost

    def test_node_capacity_overrides_default(self):
        """StageNode.capacity_agents_per_s overrides config default."""
        from pyfds_evac.core.route_graph import StageGraph

        direct_steering_info = {
            "E0": {
                "polygon": _box(10, 0),
                "stage_type": "exit",
                "capacity_agents_per_s": 10.0,
            },
        }
        distributions = {"D0": {"coordinates": list(_box(0, 0).exterior.coords)}}
        transitions = [{"from": "D0", "to": "E0"}]
        graph = StageGraph.from_scenario(
            direct_steering_info, transitions, distributions
        )
        field = ConstantExtinctionField(0.0)
        config = RouteCostConfig(
            w_smoke=0.0, w_fed=0.0, w_queue=1.0, default_exit_capacity=1.0
        )
        rc = evaluate_route(
            graph, ["D0", "E0"], 0.0, 0.0, field, None, config, exit_counts={"E0": 10}
        )
        # capacity=10 -> queue_time = 10/10 = 1.0s
        assert abs(rc.queue_time_s - 1.0) < 1e-6


class TestRankRoutesWithCongestion:
    def test_congestion_shifts_best_exit(self, multi_exit_graph):
        """With enough agents at E0, E1 becomes cheaper despite being farther."""
        field = ConstantExtinctionField(0.0)
        config = RouteCostConfig(w_smoke=0.0, w_fed=0.0, w_queue=1.0)
        ranked_no_q = rank_routes(multi_exit_graph, "D0", 0.0, 0.0, field, None, config)
        assert ranked_no_q[0].exit_id == "E0"
        ranked_q = rank_routes(
            multi_exit_graph,
            "D0",
            0.0,
            0.0,
            field,
            None,
            config,
            exit_counts={"E0": 50, "E1": 0},
        )
        assert ranked_q[0].exit_id == "E1"

    def test_rank_routes_without_exit_counts_unchanged(self, multi_exit_graph):
        """Omitting exit_counts gives identical results to current behaviour."""
        field = ConstantExtinctionField(0.0)
        config = RouteCostConfig()
        ranked = rank_routes(multi_exit_graph, "D0", 0.0, 0.0, field, None, config)
        assert ranked[0].exit_id == "E0"
        assert ranked[0].queue_time_s == 0.0


class TestEvaluateAndRerouteWithCongestion:
    def test_congestion_triggers_reroute(self, multi_exit_graph):
        """Agent switches from congested E0 to uncongested E1."""
        field = ConstantExtinctionField(0.0)
        cost_config = RouteCostConfig(w_smoke=0.0, w_fed=0.0, w_queue=1.0)
        config = RerouteConfig(reevaluation_interval_s=1.0, cost_config=cost_config)
        wait_info = {
            "mode": "path",
            "current_origin": "D0",
            "current_target_stage": "E0",
            "path_choices": {"D0": [("E0", 100.0)]},
            "stage_configs": {
                "E0": {
                    "polygon": _box(10, 0),
                    "stage_type": "exit",
                    "waiting_time": 0.0,
                    "waiting_time_distribution": "constant",
                    "waiting_time_std": 1.0,
                    "enable_throughput_throttling": False,
                    "max_throughput": 1.0,
                    "speed_factor": 1.0,
                },
                "E1": {
                    "polygon": _box(20, 0),
                    "stage_type": "exit",
                    "waiting_time": 0.0,
                    "waiting_time_distribution": "constant",
                    "waiting_time_std": 1.0,
                    "enable_throughput_throttling": False,
                    "max_throughput": 1.0,
                    "speed_factor": 1.0,
                },
            },
            "state": "to_target",
        }
        route_state = AgentRouteState(current_exit="E0", eval_offset_s=0.0)
        switch = evaluate_and_reroute(
            agent_id=1,
            wait_info=wait_info,
            route_state=route_state,
            graph=multi_exit_graph,
            current_time_s=10.0,
            current_fed=0.0,
            extinction_sampler=field,
            fed_rate_sampler=None,
            config=config,
            exit_counts={"E0": 50, "E1": 0},
        )
        assert switch is not None
        assert switch.new_exit == "E1"
        assert switch.old_exit == "E0"

    def test_no_exit_counts_backward_compatible(self, multi_exit_graph):
        """Without exit_counts, behaviour is identical to current."""
        field = ConstantExtinctionField(0.0)
        config = RerouteConfig(reevaluation_interval_s=1.0)
        wait_info = {
            "mode": "path",
            "current_origin": "D0",
            "current_target_stage": "E0",
            "path_choices": {"D0": [("E0", 100.0)]},
            "stage_configs": {},
            "state": "to_target",
        }
        route_state = AgentRouteState(eval_offset_s=0.0)
        switch = evaluate_and_reroute(
            agent_id=1,
            wait_info=wait_info,
            route_state=route_state,
            graph=multi_exit_graph,
            current_time_s=10.0,
            current_fed=0.0,
            extinction_sampler=field,
            fed_rate_sampler=None,
            config=config,
        )
        assert switch is not None
        assert switch.new_exit == "E0"


# ── cognitive map and visibility rejection tests ──────────────────────


class TestCognitiveMapRouting:
    """rank_routes respects the discovery agent's known subgraph."""

    def test_discovery_agent_cannot_reach_unknown_exit(self, multi_exit_graph):
        """Discovery agent with only E0 in cognitive map cannot rank E1."""
        from pyfds_evac.core.cognitive_map import AgentCognitiveMap

        cmap = AgentCognitiveMap(
            familiarity="discovery",
            known_nodes={"D0", "E0"},
            known_edges={("D0", "E0")},
        )
        field = ConstantExtinctionField(0.0)
        ranked = rank_routes(
            multi_exit_graph,
            "D0",
            0.0,
            0.0,
            field,
            None,
            RouteCostConfig(),
            cognitive_map=cmap,
        )
        exit_ids = [rc.exit_id for rc in ranked]
        assert "E1" not in exit_ids
        assert "E0" in exit_ids

    def test_full_agent_sees_all_exits(self, multi_exit_graph):
        """Full-familiarity cognitive map does not restrict Dijkstra."""
        from pyfds_evac.core.cognitive_map import AgentCognitiveMap

        cmap = AgentCognitiveMap(
            familiarity="full",
            known_nodes={"D0", "E0", "E1"},
            known_edges={("D0", "E0"), ("D0", "E1")},
        )
        field = ConstantExtinctionField(0.0)
        ranked = rank_routes(
            multi_exit_graph,
            "D0",
            0.0,
            0.0,
            field,
            None,
            RouteCostConfig(),
            cognitive_map=cmap,
        )
        exit_ids = [rc.exit_id for rc in ranked]
        assert "E0" in exit_ids
        assert "E1" in exit_ids


class TestVisibilityRejection:
    """rank_routes applies next_node_not_visible rejection unconditionally."""

    def _make_vis_model(self, visible_nodes: set[str]):
        """Return a mock vis_model where only *visible_nodes* are visible."""

        class _MockVis:
            def node_is_visible(self, time, x, y, node_id):
                return node_id in visible_nodes

        return _MockVis()

    def test_invisible_route_rejected(self, multi_exit_graph):
        """E0 route rejected when E0 sign is not visible."""
        field = ConstantExtinctionField(0.0)
        vis = self._make_vis_model(visible_nodes={"E1"})  # E0 not visible
        ranked = rank_routes(
            multi_exit_graph,
            "D0",
            0.0,
            0.0,
            field,
            None,
            RouteCostConfig(),
            vis_model=vis,
        )
        e0 = next(rc for rc in ranked if rc.exit_id == "E0")
        e1 = next(rc for rc in ranked if rc.exit_id == "E1")
        assert e0.rejected
        assert e0.rejection_reason == "next_node_not_visible"
        assert not e1.rejected

    def test_all_invisible_fallback_unrejects_least_bad(self, multi_exit_graph):
        """When all routes are rejected, the fallback un-rejects the cheapest."""
        field = ConstantExtinctionField(0.0)
        vis = self._make_vis_model(visible_nodes=set())  # nothing visible
        ranked = rank_routes(
            multi_exit_graph,
            "D0",
            0.0,
            0.0,
            field,
            None,
            RouteCostConfig(),
            vis_model=vis,
        )
        assert ranked, "should still return routes via fallback"
        assert not ranked[0].rejected, "fallback must un-reject the best route"
        assert ranked[0].rejection_reason is not None
        assert ranked[0].rejection_reason.startswith("fallback")

    def test_agent_position_used_over_centroid(self, multi_exit_graph):
        """agent_position is forwarded to vis_model instead of node centroid."""
        received: list[tuple] = []

        class _RecordingVis:
            def node_is_visible(self, time, x, y, node_id):
                received.append((x, y))
                return True

        field = ConstantExtinctionField(0.0)
        rank_routes(
            multi_exit_graph,
            "D0",
            0.0,
            0.0,
            field,
            None,
            RouteCostConfig(),
            vis_model=_RecordingVis(),
            agent_position=(7.5, 3.0),
        )
        assert received, "vis_model.node_is_visible should have been called"
        assert all(x == 7.5 and y == 3.0 for x, y in received)


# ── VisibilityModel cache tests are in test_visibility.py ─────────────


# ── Auto-edge generation (minimal config: no transitions) ─────────────


class TestAutoEdgeGeneration:
    """StageGraph auto-connects distributions to exits when transitions=[].

    Scenario 009: minimal config with only distributions + exits should
    support full smoke/FED rerouting without explicit transitions.
    """

    def _make_minimal_graph(self) -> StageGraph:
        """D0 → {E0, E1} auto-generated; no explicit transitions."""
        direct_steering_info = {
            "E0": {"polygon": _box(0, 0), "stage_type": "exit"},
            "E1": {"polygon": _box(20, 0), "stage_type": "exit"},
        }
        distributions = {
            "D0": {"coordinates": list(_box(10, 0).exterior.coords)},
        }
        return StageGraph.from_scenario(
            direct_steering_info=direct_steering_info,
            transitions=[],
            distributions=distributions,
        )

    def test_edges_are_generated(self):
        g = self._make_minimal_graph()
        assert "D0" in g.edges, "auto-edges from distribution must be created"
        targets = {e.target for e in g.edges["D0"]}
        assert targets == {"E0", "E1"}

    def test_edge_weights_are_positive(self):
        g = self._make_minimal_graph()
        for edge in g.edges["D0"]:
            assert edge.weight > 0

    def test_rank_routes_finds_both_exits(self):
        """rank_routes must return a cost entry for each exit."""
        g = self._make_minimal_graph()
        field = ConstantExtinctionField(0.0)
        ranked = rank_routes(g, "D0", 0.0, 0.0, field, None, RouteCostConfig())
        exit_ids = {rc.exit_id for rc in ranked}
        assert "E0" in exit_ids
        assert "E1" in exit_ids

    def test_no_auto_edges_when_transitions_defined(self):
        """Explicit transitions must not be augmented by auto-generation."""
        direct_steering_info = {
            "E0": {"polygon": _box(0, 0), "stage_type": "exit"},
            "E1": {"polygon": _box(20, 0), "stage_type": "exit"},
        }
        distributions = {
            "D0": {"coordinates": list(_box(10, 0).exterior.coords)},
        }
        transitions = [{"from": "D0", "to": "E0"}]
        g = StageGraph.from_scenario(
            direct_steering_info=direct_steering_info,
            transitions=transitions,
            distributions=distributions,
        )
        # Only the explicit D0→E0 edge; E1 must not be auto-added.
        targets = {e.target for e in g.edges.get("D0", [])}
        assert targets == {"E0"}, "auto-edges must not appear when transitions defined"
