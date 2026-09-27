"""Tests for familiarity-driven routing added in the discovery/full work:

  * ``StageGraph.shortest_path_to`` — single-target Dijkstra.
  * ``nearest_frontier_target`` — discovery agents heading to the nearest
    known-but-unexplored node when no exit is reachable yet.
  * ``evaluate_and_reroute`` — the ``better_path`` (cheaper path to the same
    exit) and ``explore`` (frontier) branches.

Self-contained: builds its own graphs/wait_info so it doesn't depend on the
private fixtures in test_route_graph.py.
"""

import math

import pytest
from shapely.geometry import Polygon

from pyfds_evac.core.cognitive_map import (
    AgentCognitiveMap,
    cognitive_subgraph,
    nearest_frontier_target,
)
from pyfds_evac.core.route_graph import (
    AgentRouteState,
    RerouteConfig,
    RouteCostConfig,
    StageGraph,
    evaluate_and_reroute,
    rank_routes,
)
from pyfds_evac.core.smoke_speed import ConstantExtinctionField


def _box(cx: float, cy: float, half: float = 1.0) -> Polygon:
    return Polygon(
        [
            (cx - half, cy - half),
            (cx + half, cy - half),
            (cx + half, cy + half),
            (cx - half, cy + half),
        ]
    )


def _graph(
    nodes: dict, transitions: list, dist_id: str = "D0", dist_at=(0, 0)
) -> StageGraph:
    """Build a StageGraph from {id: (cx, cy, type)} nodes + transitions."""
    dsi = {
        nid: {"polygon": _box(cx, cy), "stage_type": st}
        for nid, (cx, cy, st) in nodes.items()
    }
    dists = {dist_id: {"coordinates": list(_box(*dist_at).exterior.coords)}}
    return StageGraph.from_scenario(dsi, transitions, dists)


def _linear_graph() -> StageGraph:
    """D0 ──> C0 ──> E0 (straight line)."""
    return _graph(
        {"C0": (10, 0, "checkpoint"), "E0": (20, 0, "exit")},
        [{"from": "D0", "to": "C0"}, {"from": "C0", "to": "E0"}],
    )


def _diamond_graph() -> StageGraph:
    """Short path D0→C0→E0 (~30) and long detour D0→C1→E0 (~58)."""
    return _graph(
        {
            "C0": (0, 10, "checkpoint"),
            "C1": (0, 30, "checkpoint"),
            "E0": (20, 10, "exit"),
        },
        [
            {"from": "D0", "to": "C0"},
            {"from": "D0", "to": "C1"},
            {"from": "C0", "to": "E0"},
            {"from": "C1", "to": "E0"},
        ],
    )


def _stage_configs(graph: StageGraph) -> dict:
    return {
        sid: {
            "polygon": _box(node.centroid_x, node.centroid_y),
            "stage_type": node.stage_type,
            "waiting_time": 0.0,
            "waiting_time_distribution": "constant",
            "waiting_time_std": 0.0,
            "speed_factor": 1.0,
        }
        for sid, node in graph.nodes.items()
    }


def _wait_info(graph, origin, target, path_choices=None) -> dict:
    node = graph.nodes[target]
    return {
        "mode": "path",
        "path_choices": path_choices or {},
        "stage_configs": _stage_configs(graph),
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


_CLEAR = ConstantExtinctionField(0.0)
_DIST_ONLY = RouteCostConfig(
    base_speed_m_per_s=1.0, w_smoke=0.0, w_fed=0.0, w_queue=0.0
)


# ── shortest_path_to ──────────────────────────────────────────────────


class TestShortestPathTo:
    def test_reachable_returns_cost_and_path(self):
        cost, path = _linear_graph().shortest_path_to("D0", "E0")
        assert path == ["D0", "C0", "E0"]
        assert cost == pytest.approx(20.0, abs=0.5)

    def test_unreachable_returns_none(self):
        # E0 is an exit with no outgoing edges → can't reach D0 from it.
        assert _linear_graph().shortest_path_to("E0", "D0") is None

    def test_source_equals_target(self):
        assert _linear_graph().shortest_path_to("D0", "D0") == (0.0, ["D0"])

    def test_missing_source_returns_none(self):
        assert _linear_graph().shortest_path_to("nope", "E0") is None

    def test_dynamic_weights_route_around_expensive_edge(self):
        g = _diamond_graph()
        res = g.shortest_path_to("D0", "E0", dynamic_weights={("D0", "C0"): 999.0})
        assert res is not None
        _cost, path = res
        assert "C1" in path and "C0" not in path


# ── nearest_frontier_target ───────────────────────────────────────────


class TestNearestFrontierTarget:
    def test_returns_nearest_known_but_unexplored_node(self):
        g = _diamond_graph()
        cmap = AgentCognitiveMap(
            familiarity="discovery",
            known_nodes={"D0", "C0"},
            known_edges={("D0", "C0")},
        )
        node, path = nearest_frontier_target(cmap, g, "D0")
        assert node == "C0"
        assert path == ["D0", "C0"]

    def test_picks_nearer_frontier_over_farther(self):
        g = _graph(
            {
                "A": (0, 5, "checkpoint"),
                "B": (0, 20, "checkpoint"),
                "AX": (0, 6, "exit"),
                "BX": (0, 21, "exit"),
            },
            [
                {"from": "D0", "to": "A"},
                {"from": "D0", "to": "B"},
                {"from": "A", "to": "AX"},
                {"from": "B", "to": "BX"},
            ],
        )
        cmap = AgentCognitiveMap(
            familiarity="discovery",
            known_nodes={"D0", "A", "B"},
            known_edges={("D0", "A"), ("D0", "B")},
        )
        node, _ = nearest_frontier_target(cmap, g, "D0")
        assert node == "A"  # dist 5 beats dist 20

    def test_none_when_fully_explored(self):
        g = _linear_graph()
        cmap = AgentCognitiveMap(
            familiarity="discovery",
            known_nodes={"D0", "C0", "E0"},
            known_edges={("D0", "C0"), ("C0", "E0")},
            # Explored means visited: with gated arrival a visited node may
            # keep unknown edges forever, so edge-completeness no longer
            # defines the frontier (see nearest_frontier_target).
            visited_nodes={"D0", "C0", "E0"},
        )
        assert nearest_frontier_target(cmap, g, "D0") is None

    def test_tie_breaks_deterministically_by_node_id(self):
        # n_a and n_b are equidistant from D0; the id sorting first wins.
        g = _graph(
            {
                "n_a": (3, 4, "checkpoint"),
                "n_b": (4, 3, "checkpoint"),
                "ax": (3, 5, "exit"),
                "bx": (5, 3, "exit"),
            },
            [
                {"from": "D0", "to": "n_a"},
                {"from": "D0", "to": "n_b"},
                {"from": "n_a", "to": "ax"},
                {"from": "n_b", "to": "bx"},
            ],
        )
        cmap = AgentCognitiveMap(
            familiarity="discovery",
            known_nodes={"D0", "n_a", "n_b"},
            known_edges={("D0", "n_a"), ("D0", "n_b")},
        )
        node, _ = nearest_frontier_target(cmap, g, "D0")
        assert node == "n_a"


# ── evaluate_and_reroute: better_path (same exit) ─────────────────────


class TestBetterPathReroute:
    def _run(self, graph, wait_info, route_state):
        return evaluate_and_reroute(
            agent_id=1,
            wait_info=wait_info,
            route_state=route_state,
            graph=graph,
            current_time_s=5.0,
            current_fed=0.0,
            extinction_sampler=_CLEAR,
            fed_rate_sampler=None,
            config=RerouteConfig(cost_config=_DIST_ONLY),
        )

    def test_switches_to_cheaper_path_to_same_exit(self):
        g = _diamond_graph()
        wait_info = _wait_info(
            g,
            "D0",
            "C1",
            path_choices={"D0": [("C1", 100.0)], "C1": [("E0", 100.0)]},
        )
        rs = AgentRouteState(current_exit="E0", current_path=["D0", "C1", "E0"])
        switch = self._run(g, wait_info, rs)
        assert switch is not None
        assert switch.reason == "better_path"
        assert switch.new_exit == "E0"
        assert switch.old_exit == "E0"  # same exit → exit_counts net-neutral
        assert "C0" in rs.current_path  # now on the short leg

    def test_no_switch_when_already_on_cheapest_path(self):
        g = _diamond_graph()
        wait_info = _wait_info(
            g,
            "D0",
            "C0",
            path_choices={"D0": [("C0", 100.0)], "C0": [("E0", 100.0)]},
        )
        rs = AgentRouteState(current_exit="E0", current_path=["D0", "C0", "E0"])
        assert self._run(g, wait_info, rs) is None


class _SmokeBelowAxis:
    """K = 0.4 /m south of y = 0, clear air north of it.

    Along the southern path that is an optical depth of about 6.9, over the
    gate's budget of 6, while slowing the walk by only about 3 %.
    """

    def sample_extinction(self, time_s: float, x: float, y: float) -> float:
        return 0.4 if y < 0.0 else 0.0


def _twin_graph() -> StageGraph:
    """Two near-equal paths to E0: D0→C1→E0 (south) and D0→C0→E0 (north).

    The northern leg is slightly longer, so on time alone it is never 10 %
    better than the southern one.
    """
    return _graph(
        {
            "C0": (10, 2, "checkpoint"),
            "C1": (10, -1, "checkpoint"),
            "E0": (20, 0, "exit"),
        },
        [
            {"from": "D0", "to": "C0"},
            {"from": "D0", "to": "C1"},
            {"from": "C0", "to": "E0"},
            {"from": "C1", "to": "E0"},
        ],
    )


class TestSameExitLeavesRejectedPath:
    """#184: the 10 % time rule must not keep an agent on a rejected path."""

    def _run(self, extinction_sampler):
        g = _twin_graph()
        wait_info = _wait_info(
            g,
            "D0",
            "C1",
            path_choices={"D0": [("C1", 100.0)], "C1": [("E0", 100.0)]},
        )
        rs = AgentRouteState(current_exit="E0", current_path=["D0", "C1", "E0"])
        switch = evaluate_and_reroute(
            agent_id=1,
            wait_info=wait_info,
            route_state=rs,
            graph=g,
            current_time_s=5.0,
            current_fed=0.0,
            extinction_sampler=extinction_sampler,
            fed_rate_sampler=None,
            config=RerouteConfig(cost_config=RouteCostConfig(base_speed_m_per_s=1.0)),
        )
        return switch, rs

    def test_leaves_a_smoke_rejected_path_for_a_feasible_one(self):
        switch, rs = self._run(_SmokeBelowAxis())
        assert switch is not None
        assert switch.new_exit == "E0"
        assert "C0" in rs.current_path

    def test_keeps_the_walked_path_when_it_is_feasible(self):
        """Without the smoke the northern leg is not 10 % faster."""
        switch, rs = self._run(_CLEAR)
        assert switch is None


# ── evaluate_and_reroute: explore (frontier) ──────────────────────────


class TestExploreReroute:
    def _run(self, graph, wait_info, route_state, cmap):
        return evaluate_and_reroute(
            agent_id=1,
            wait_info=wait_info,
            route_state=route_state,
            graph=graph,
            current_time_s=3.0,
            current_fed=0.0,
            extinction_sampler=_CLEAR,
            fed_rate_sampler=None,
            config=RerouteConfig(cost_config=RouteCostConfig(base_speed_m_per_s=1.0)),
            cognitive_map=cmap,
        )

    def test_explores_frontier_when_no_exit_known(self):
        g = _diamond_graph()
        cmap = AgentCognitiveMap(
            familiarity="discovery",
            known_nodes={"D0", "C0"},
            known_edges={("D0", "C0")},
        )
        wait_info = _wait_info(g, "D0", "E0")  # scripted toward an unreachable exit
        rs = AgentRouteState()
        switch = self._run(g, wait_info, rs, cmap)
        assert switch is not None
        assert switch.reason == "explore"
        assert switch.new_exit == "C0"
        assert switch.old_exit is None  # exploring is not abandoning an exit

    def test_no_explore_when_exit_is_known(self):
        g = _linear_graph()
        cmap = AgentCognitiveMap(
            familiarity="discovery",
            known_nodes={"D0", "C0", "E0"},
            known_edges={("D0", "C0"), ("C0", "E0")},
        )
        wait_info = _wait_info(g, "D0", "C0")
        rs = AgentRouteState()
        switch = self._run(g, wait_info, rs, cmap)
        assert switch is None or switch.reason != "explore"


# ── walls: discovery measures distance the way full does (issue #172) ─


def _corridor_graph(walkable, nodes: dict, transitions: list) -> StageGraph:
    """A StageGraph with a routing engine over *walkable*."""
    dsi = {
        nid: {"polygon": _box(cx, cy, half=0.5), "stage_type": st}
        for nid, (cx, cy, st) in nodes.items()
    }
    return StageGraph.from_scenario(dsi, transitions, walkable_polygon=walkable)


class TestDiscoveryMeasuresAroundWalls:
    """A discovery agent must measure its first leg through the walkable area.

    Familiarity decides what an agent knows, not how it measures. Before the
    fix the known subgraph dropped the routing engine, so a discovery agent
    measured the walk to its next node as a straight line through the wall
    while a full agent at the same spot walked around it.
    """

    @staticmethod
    def _l_graph() -> StageGraph:
        """An L corridor; the exit sits up the vertical leg, behind the corner."""
        from shapely.geometry import box
        from shapely.ops import unary_union

        return _corridor_graph(
            unary_union([box(0, 0, 20, 3), box(17, 0, 20, 20)]),
            {"j": (18.5, 1.5, "checkpoint"), "e0": (18.5, 18.0, "exit")},
            [{"from": "j", "to": "e0"}],
        )

    @staticmethod
    def _rank(graph, cmap, agent):
        return rank_routes(
            graph,
            "j",
            0.0,
            0.0,
            _CLEAR,
            None,
            _DIST_ONLY,
            cognitive_map=cmap,
            agent_position=agent,
        )

    def test_known_subgraph_keeps_the_routing_engine(self):
        g = self._l_graph()
        cmap = AgentCognitiveMap(
            familiarity="discovery",
            known_nodes={"j", "e0"},
            known_edges={("j", "e0")},
        )
        assert cognitive_subgraph(cmap, g).routing_engine is g.routing_engine

    def test_first_leg_matches_the_full_tier_behind_a_wall(self):
        g = self._l_graph()
        agent = (5.0, 1.5)  # the straight line to e0 leaves the corridor
        full = AgentCognitiveMap(familiarity="full")
        discovery = AgentCognitiveMap(
            familiarity="discovery",
            known_nodes={"j", "e0"},
            known_edges={("j", "e0")},
        )

        (full_route,) = self._rank(g, full, agent)
        (disc_route,) = self._rank(g, discovery, agent)

        straight = math.hypot(18.5 - agent[0], 18.0 - agent[1])
        assert full_route.composite_cost > straight + 1.0
        assert disc_route.composite_cost == pytest.approx(full_route.composite_cost)

    def test_frontier_distance_follows_the_corridor(self):
        """Two frontiers; the nearer one as the crow flies is behind a wall.

        A U corridor: the agent stands high in the left arm. Frontier ``a`` is
        across the gap in the right arm (17 m straight, ~45 m walked); frontier
        ``b`` is in the bottom leg (~18 m straight, ~24 m walked).
        """
        from shapely.geometry import box
        from shapely.ops import unary_union

        g = _corridor_graph(
            unary_union([box(0, 0, 20, 3), box(0, 0, 3, 20), box(17, 0, 20, 20)]),
            {
                "s": (1.5, 10.0, "checkpoint"),
                "a": (18.5, 17.0, "checkpoint"),
                "b": (10.0, 1.5, "checkpoint"),
            },
            [{"from": "s", "to": "a"}, {"from": "s", "to": "b"}],
        )
        cmap = AgentCognitiveMap(
            familiarity="discovery",
            known_nodes={"s", "a", "b"},
            known_edges={("s", "a"), ("s", "b")},
            visited_nodes={"s"},
        )
        node, _ = nearest_frontier_target(cmap, g, "s", (1.5, 17.0))
        assert node == "b"
