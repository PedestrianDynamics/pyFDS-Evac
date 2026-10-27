"""Hand-computed values of the stage graph search and exit schedule (#816).

Each test fixes one behaviour of ``route_graph`` to numbers that can be
checked on paper: the half-open schedule window, which stages a closure
removes, the cost and path of a search from a point off the graph, and
the predecessor chosen between equal-cost paths. Graphs are built from
explicit edge weights so the expected costs are sums of those weights.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pytest
from test_rerouting_golden import (
    _additive,
    _choices,
    _diamond,
    _edges,
    _gate,
    _graph,
    _wait_info,
)

from pyfds_evac.core.route_graph import (
    AgentRouteState,
    RerouteConfig,
    StageEdge,
    StageGraph,
    StageNode,
    evaluate_and_reroute,
    evaluate_route,
    rank_routes,
    stage_closed,
    stage_closed_down,
    without_closed_stages,
)

pytestmark = pytest.mark.usefixtures("bounded_search")


def _line_graph(
    kinds: dict[str, str], weights: dict[tuple[str, str], float]
) -> StageGraph:
    """Nodes on a line, one per id; edges with the given weights."""
    nodes = {
        sid: StageNode(stage_id=sid, centroid_x=float(i), centroid_y=0.0, stage_type=k)
        for i, (sid, k) in enumerate(kinds.items())
    }
    graph = StageGraph(nodes=nodes)
    for (src, dst), w in weights.items():
        graph.edges.setdefault(src, []).append(
            StageEdge(source=src, target=dst, weight=w)
        )
    return graph


def _scheduled(open_from_s=None, closed_after_s=None) -> StageGraph:
    node = StageNode(
        "E",
        0.0,
        0.0,
        "exit",
        open_from_s=open_from_s,
        closed_after_s=closed_after_s,
    )
    return StageGraph(nodes={"E": node})


class TestScheduleWindow:
    def test_closed_before_open_open_at_open_closed_at_close(self):
        node = StageNode("E", 0, 0, "exit", open_from_s=10.0, closed_after_s=20.0)
        assert node.is_open(9.999) is False
        assert node.is_open(10.0) is True
        assert node.is_open(19.999) is True
        assert node.is_open(20.0) is False

    def test_open_only_schedule_never_closes(self):
        node = StageNode("E", 0, 0, "exit", open_from_s=10.0)
        assert [node.is_open(t) for t in (9.999, 10.0, 1e9)] == [False, True, True]

    def test_close_only_schedule_is_open_from_the_start(self):
        node = StageNode("E", 0, 0, "exit", closed_after_s=20.0)
        assert [node.is_open(t) for t in (0.0, 19.999, 20.0)] == [True, True, False]


class TestStageClosed:
    def test_not_yet_opened_exit_is_closed_but_not_closed_down(self):
        graph = _scheduled(open_from_s=10.0, closed_after_s=20.0)
        assert stage_closed(graph, "E", 5.0) is True
        assert stage_closed_down(graph, "E", 5.0) is False

    def test_closed_down_starts_at_closed_after(self):
        graph = _scheduled(open_from_s=10.0, closed_after_s=20.0)
        assert stage_closed_down(graph, "E", 19.999) is False
        assert stage_closed_down(graph, "E", 20.0) is True
        assert stage_closed(graph, "E", 19.999) is False
        assert stage_closed(graph, "E", 20.0) is True

    def test_open_only_exit_is_never_closed_down(self):
        graph = _scheduled(open_from_s=10.0)
        assert stage_closed_down(graph, "E", 1e9) is False

    def test_unknown_or_missing_stage_is_not_closed(self):
        graph = _scheduled(closed_after_s=0.0)
        for stage_id in ("nope", None):
            assert stage_closed(graph, stage_id, 5.0) is False
            assert stage_closed_down(graph, stage_id, 5.0) is False


class TestWithoutClosedStages:
    @staticmethod
    def _scheduled_graph() -> StageGraph:
        """D reaches E0 (open), E1 (closes at 50) and C (opens at 100).

        C reaches E0 at cost 1, so D->C->E0 (2) beats D->E0 (5) while C is open.
        """
        graph = _line_graph(
            {"D": "distribution", "C": "checkpoint", "E0": "exit", "E1": "exit"},
            {("D", "C"): 1.0, ("D", "E0"): 5.0, ("D", "E1"): 2.0, ("C", "E0"): 1.0},
        )
        graph.nodes["C"] = StageNode("C", 1.0, 0.0, "checkpoint", open_from_s=100.0)
        graph.nodes["E1"] = StageNode("E1", 3.0, 0.0, "exit", closed_after_s=50.0)
        return graph

    def test_closed_stages_and_every_edge_touching_them_are_removed(self):
        sub = without_closed_stages(self._scheduled_graph(), 60.0)
        assert sorted(sub.nodes) == ["D", "E0"]
        assert list(sub.edges) == ["D"]
        assert [(e.source, e.target) for e in sub.edges["D"]] == [("D", "E0")]

    def test_search_on_the_remaining_graph_takes_the_direct_edge(self):
        sub = without_closed_stages(self._scheduled_graph(), 60.0)
        assert sub.shortest_paths_to_exits("D") == {"E0": (5.0, ["D", "E0"])}

    def test_stage_open_at_the_time_stays_with_its_edges(self):
        sub = without_closed_stages(self._scheduled_graph(), 40.0)
        assert sorted(sub.nodes) == ["D", "E0", "E1"]
        assert [e.target for e in sub.edges["D"]] == ["E0", "E1"]

    def test_the_original_graph_is_not_modified(self):
        graph = self._scheduled_graph()
        without_closed_stages(graph, 60.0)
        assert sorted(graph.nodes) == ["C", "D", "E0", "E1"]
        assert len(graph.edges["D"]) == 3


class TestSearchFromAPoint:
    @staticmethod
    def _graph() -> StageGraph:
        return _line_graph(
            {"S": "distribution", "A": "checkpoint", "T": "exit"},
            {("S", "T"): 0.1, ("A", "T"): 2.0},
        )

    def test_source_is_not_seeded_and_its_own_edges_are_replaced(self):
        # A first hop onto the source itself would let the search use the
        # source's out-edge S->T (0.5 + 0.1); the seeded search must use
        # A instead: 1.0 + 2.0.
        graph = self._graph()
        first_hops = {"S": 0.5, "A": 1.0}
        assert graph.shortest_paths_to_exits("S", first_hops=first_hops) == {
            "T": (3.0, ["S", "A", "T"])
        }
        dist, prev = graph._dijkstra("S", first_hops=first_hops)
        assert dist == {"S": math.inf, "A": 1.0, "T": 3.0}
        assert prev == {"S": None, "A": "S", "T": "A"}

    def test_seed_cost_is_the_cost_of_the_first_hop(self):
        dist, _ = self._graph()._dijkstra("S", first_hops={"A": 4.0})
        assert dist["A"] == 4.0
        assert dist["T"] == 6.0

    def test_first_hop_to_an_unknown_node_is_ignored(self):
        paths = self._graph().shortest_paths_to_exits(
            "S", first_hops={"X": 1.0, "A": 1.0}
        )
        assert paths == {"T": (3.0, ["S", "A", "T"])}

    def test_edge_back_into_the_source_is_not_relaxed(self):
        graph = _line_graph(
            {"S": "distribution", "A": "checkpoint", "T": "exit"},
            {("A", "S"): 0.1, ("S", "T"): 0.1, ("A", "T"): 4.0},
        )
        dist, prev = graph._dijkstra("S", first_hops={"A": 1.0})
        assert dist["S"] == math.inf
        assert prev["S"] is None
        assert graph.shortest_paths_to_exits("S", first_hops={"A": 1.0}) == {
            "T": (5.0, ["S", "A", "T"])
        }


class TestDynamicWeights:
    @staticmethod
    def _graph() -> StageGraph:
        """S->A->T costs 1 + 1 statically; S->T costs 3."""
        return _line_graph(
            {"S": "distribution", "A": "checkpoint", "T": "exit"},
            {("S", "A"): 1.0, ("A", "T"): 1.0, ("S", "T"): 3.0},
        )

    def test_static_search_costs_are_the_weight_sums(self):
        paths = self._graph().shortest_paths_to_exits("S")
        assert paths == {"T": (2.0, ["S", "A", "T"])}

    def test_dynamic_weights_replace_the_edge_weights(self):
        weights = {("S", "A"): 10.0, ("A", "T"): 10.0, ("S", "T"): 4.0}
        paths = self._graph().shortest_paths_to_exits("S", dynamic_weights=weights)
        assert paths == {"T": (4.0, ["S", "T"])}

    def test_dynamic_weights_set_the_reported_cost_on_the_same_path(self):
        weights = {("S", "A"): 0.5, ("A", "T"): 0.25, ("S", "T"): 3.0}
        paths = self._graph().shortest_paths_to_exits("S", dynamic_weights=weights)
        assert paths == {"T": (0.75, ["S", "A", "T"])}

    def test_edge_missing_from_dynamic_weights_keeps_its_own_weight(self):
        paths = self._graph().shortest_paths_to_exits(
            "S", dynamic_weights={("S", "A"): 0.5}
        )
        assert paths == {"T": (1.5, ["S", "A", "T"])}


class TestEqualCostPaths:
    def test_tie_keeps_the_first_path_found(self):
        # S->A->T and S->B->T both cost 2. A is expanded before B (equal
        # cost, smaller id), so T keeps A as its predecessor; a relaxation
        # that accepts equal cost would hand T to B.
        graph = _line_graph(
            {"S": "distribution", "A": "checkpoint", "B": "checkpoint", "T": "exit"},
            {("S", "A"): 1.0, ("S", "B"): 1.0, ("A", "T"): 1.0, ("B", "T"): 1.0},
        )
        assert graph.shortest_paths_to_exits("S") == {"T": (2.0, ["S", "A", "T"])}


@dataclass(frozen=True)
class _Hazard:
    """Extinction *k* and FED rate *fed* per minute inside boxes, from *t_on*.

    A box is ``(x_min, x_max, y_min, y_max)``. One object serves as the
    extinction and the FED sampler.
    """

    boxes: tuple[tuple[float, float, float, float], ...]
    k: float = 0.0
    fed: float = 0.0
    t_on: float = 0.0

    def _inside(self, x: float, y: float) -> bool:
        return any(a < x < b and c < y < d for a, b, c, d in self.boxes)

    def sample_extinction(self, time_s: float, x: float, y: float) -> float:
        return self.k if time_s >= self.t_on and self._inside(x, y) else 0.0

    def sample_fed_rate(self, time_s: float, x: float, y: float) -> float:
        return self.fed if time_s >= self.t_on and self._inside(x, y) else 0.0


# Mid-leg boxes on the second leg of each corridor of the graphs below.
_ON_C0_E0 = (2.0, 15.0, 8.0, 12.0)
_ON_C1_E0 = (8.0, 12.0, 18.0, 22.0)
_ON_C2_E0 = (8.0, 12.0, -12.0, -8.0)
_ON_C3_E0 = (8.0, 12.0, -24.0, -16.0)

_LONG_CORRIDOR_M = 30.0 + math.hypot(20.0, 20.0)


def _corridors(count: int) -> StageGraph:
    """D0 to the exit E0 (20, 10) through *count* corridors, cheapest first.

    Corridor i runs D0 > Ci > E0. The lengths are 30, 58.28, 74.72 and
    113.25 m for C0 to C3.
    """
    checkpoints = {
        "C0": (0, 10, "checkpoint"),
        "C1": (0, 30, "checkpoint"),
        "C2": (0, -30, "checkpoint"),
        "C3": (0, -50, "checkpoint"),
    }
    names = list(checkpoints)[:count]
    nodes = {n: checkpoints[n] for n in names} | {"E0": (20, 10, "exit")}
    pairs = [("D0", n) for n in names] + [(n, "E0") for n in names]
    return _graph(nodes, _edges(*pairs))


class _MaxExtinction:
    """The larger extinction of several fields."""

    def __init__(self, *fields):
        self._fields = fields

    def sample_extinction(self, time_s: float, x: float, y: float) -> float:
        return max(f.sample_extinction(time_s, x, y) for f in self._fields)


def _rank(graph, ext, fed, config, **kwargs):
    return rank_routes(graph, "D0", 0.0, 0.0, ext, fed, config, **kwargs)


def _entry(ranked, exit_id="E0"):
    return next(rc for rc in ranked if rc.exit_id == exit_id)


class TestAlternativePathToRefusedExit:
    """#185: an exit whose searched path is refused tries other paths to it."""

    def test_gate_fed_strip_on_the_short_corridor_takes_the_long_one(self):
        hazard = _Hazard((_ON_C0_E0,), fed=10.0)
        ranked = _rank(_diamond(), hazard, hazard, _gate())
        e0 = _entry(ranked)
        assert e0.path == ["D0", "C1", "E0"]
        assert e0.path_length_m == pytest.approx(_LONG_CORRIDOR_M)
        assert e0.travel_time_s == pytest.approx(_LONG_CORRIDOR_M)
        assert (e0.fed_max_route, e0.tau_route) == (0.0, 0.0)
        assert e0.feasible and not e0.rejected
        assert e0.rejection_reason is None

    def test_gate_smoke_that_arrives_after_the_decision_takes_the_long_corridor(self):
        # Clear at t = 0, so the search weighs C0 > E0 as free; the agent is
        # on it from t = 10 s, in smoke: tau 21.82 > 6.
        hazard = _Hazard((_ON_C0_E0,), k=2.0, t_on=5.0)
        ranked = _rank(_diamond(), hazard, None, _gate())
        e0 = _entry(ranked)
        assert e0.path == ["D0", "C1", "E0"]
        assert e0.tau_route == 0.0
        assert e0.feasible and not e0.rejected

    def test_additive_fed_strip_on_the_short_corridor_takes_the_long_one(self):
        hazard = _Hazard((_ON_C0_E0,), fed=10.0)
        ranked = _rank(_diamond(), hazard, hazard, _additive())
        e0 = _entry(ranked)
        assert e0.path == ["D0", "C1", "E0"]
        assert e0.fed_max_route == 0.0
        assert e0.feasible and not e0.rejected

    def test_agent_on_the_refused_walk_is_sent_to_the_other_path_of_its_exit(self):
        hazard = _Hazard((_ON_C0_E0,), fed=10.0)
        graph = _diamond()
        wait_info = _wait_info(
            graph, "D0", "C0", path_choices=_choices("D0", "C0", "E0")
        )
        route_state = AgentRouteState(
            current_exit="E0", current_path=["D0", "C0", "E0"]
        )
        switch = evaluate_and_reroute(
            agent_id=7,
            wait_info=wait_info,
            route_state=route_state,
            graph=graph,
            current_time_s=5.0,
            current_fed=0.0,
            extinction_sampler=hazard,
            fed_rate_sampler=hazard,
            config=RerouteConfig(cost_config=_gate()),
            cached_segments={},
            agent_position=(0.0, 2.0),
        )
        assert switch is not None
        assert (switch.old_exit, switch.new_exit) == ("E0", "E0")
        assert switch.reason == "better_path"
        assert route_state.current_path == ["D0", "C1", "E0"]

    def test_both_corridors_hazardous_keeps_the_searched_path_record(self, monkeypatch):
        hazard = _Hazard((_ON_C0_E0, _ON_C1_E0), fed=60.0)
        ranked = _rank(_diamond(), hazard, hazard, _gate())
        monkeypatch.setattr("pyfds_evac.core.route_graph._PATHS_PER_EXIT", 1)
        one_path = _rank(_diamond(), hazard, hazard, _gate())
        e0 = _entry(ranked)
        assert e0.path == ["D0", "C0", "E0"]
        assert e0.rejected and e0.rejection_reason.startswith("fallback: FED_max")
        assert ranked == one_path

    def test_third_cheapest_corridor_is_found_the_fourth_is_not(self):
        three = _Hazard((_ON_C0_E0, _ON_C1_E0), fed=60.0)
        found = _entry(_rank(_corridors(3), three, three, _gate()))
        assert found.path == ["D0", "C2", "E0"]
        assert found.feasible and not found.rejected
        four = _Hazard((_ON_C0_E0, _ON_C1_E0, _ON_C2_E0), fed=60.0)
        kept = _entry(_rank(_corridors(4), four, four, _gate()))
        assert kept.path == ["D0", "C0", "E0"]
        assert kept.rejected and kept.rejection_reason.startswith("fallback: FED_max")

    def test_of_two_feasible_alternatives_the_one_that_orders_first_wins(self):
        # By length C1 (58.28 m) comes before C2 (74.72 m); C1 gets light
        # smoke at t = 5 s, so on arrival its tau is above C2's zero.
        smoke = _MaxExtinction(
            _Hazard((_ON_C0_E0,), k=2.0, t_on=5.0),
            _Hazard((_ON_C1_E0,), k=0.05, t_on=5.0),
        )
        ranked = _rank(_corridors(3), smoke, None, _gate())
        e0 = _entry(ranked)
        assert e0.path == ["D0", "C2", "E0"]
        assert e0.tau_route == 0.0
        c1 = evaluate_route(
            _corridors(3), ["D0", "C1", "E0"], 0.0, 0.0, smoke, None, _gate()
        )
        assert 0.0 < c1.tau_route < _gate().tau_max
        assert c1.feasible

    def test_equal_alternatives_keep_the_earlier_search_path(self):
        # N and M are mirror images; N is listed first. The Yen order is
        # (cost, hops, path), so M comes first and wins the full tie.
        graph = _graph(
            {
                "C0": (10, 0, "checkpoint"),
                "N": (10, -5, "checkpoint"),
                "M": (10, 5, "checkpoint"),
                "E0": (20, 0, "exit"),
            },
            _edges(
                ("D0", "C0"),
                ("D0", "N"),
                ("D0", "M"),
                ("C0", "E0"),
                ("N", "E0"),
                ("M", "E0"),
            ),
        )
        hazard = _Hazard(((12.0, 18.0, -1.0, 1.0),), fed=60.0)
        e0 = _entry(_rank(graph, hazard, hazard, _gate()))
        assert e0.path == ["D0", "M", "E0"]
        assert e0.feasible

    def test_every_exit_keeps_one_record(self):
        graph = _graph(
            {
                "C0": (0, 10, "checkpoint"),
                "C1": (0, 30, "checkpoint"),
                "E0": (20, 10, "exit"),
                "E1": (-20, 10, "exit"),
            },
            _edges(
                ("D0", "C0"),
                ("D0", "C1"),
                ("C0", "E0"),
                ("C1", "E0"),
                ("C0", "E1"),
                ("C1", "E1"),
            ),
        )
        hazard = _Hazard((_ON_C0_E0, (-15.0, -2.0, 8.0, 12.0)), fed=10.0)
        ranked = _rank(graph, hazard, hazard, _gate())
        assert sorted(rc.exit_id for rc in ranked) == ["E0", "E1"]
        assert all(rc.path[-1] == rc.exit_id for rc in ranked)


class TestKShortestPaths:
    @staticmethod
    def _back_edge_graph() -> StageGraph:
        """S, with an edge N > S back into it, and two ways to T."""
        return _line_graph(
            {"S": "distribution", "N": "checkpoint", "M": "checkpoint", "T": "exit"},
            {("S", "N"): 9.0, ("S", "M"): 9.0, ("N", "S"): 1.0, ("N", "T"): 10.0}
            | {("M", "T"): 3.0},
        )

    def test_no_alternative_re_enters_the_source(self):
        from pyfds_evac.core.route_graph import k_shortest_paths

        graph = self._back_edge_graph()
        first_hops = {"N": 1.0, "M": 2.0}
        first = graph.shortest_paths_to_exits("S", first_hops=first_hops)["T"][1]
        assert first == ["S", "M", "T"]
        paths = k_shortest_paths(graph, "S", "T", first, {}, first_hops, k=5)
        assert paths == [["S", "M", "T"], ["S", "N", "T"]]
        assert all("S" not in p[1:] for p in paths)

    def test_banned_first_hop_is_dropped_from_the_seeds(self):
        graph = self._back_edge_graph()
        dist, prev = graph._dijkstra(
            "S", first_hops={"N": 1.0, "M": 2.0}, banned_edges={("S", "M")}
        )
        assert dist["M"] == math.inf
        assert dist["T"] == 11.0
        assert prev["T"] == "N"

    def test_nothing_banned_changes_nothing(self):
        graph = self._back_edge_graph()
        plain = graph._dijkstra("S", first_hops={"N": 1.0, "M": 2.0})
        empty = graph._dijkstra(
            "S",
            first_hops={"N": 1.0, "M": 2.0},
            banned_edges=set(),
            banned_nodes=set(),
        )
        assert plain == empty

    @pytest.mark.parametrize("first_hops", [None, {"A": 1.0, "B": 1.0}])
    def test_nothing_banned_changes_nothing_on_equal_costs(self, first_hops):
        graph = _line_graph(
            {"S": "distribution", "A": "checkpoint", "B": "checkpoint", "T": "exit"},
            {("S", "A"): 1.0, ("S", "B"): 1.0, ("A", "T"): 1.0, ("B", "T"): 1.0},
        )
        plain = graph._dijkstra("S", first_hops=first_hops)
        empty = graph._dijkstra(
            "S", first_hops=first_hops, banned_edges=set(), banned_nodes=set()
        )
        assert plain == empty
        assert plain[1]["T"] == "A"

    def test_nothing_banned_returns_the_search_path_first_on_equal_costs(self):
        from pyfds_evac.core.route_graph import k_shortest_paths

        graph = _line_graph(
            {"S": "distribution", "A": "checkpoint", "B": "checkpoint", "T": "exit"},
            {("S", "A"): 1.0, ("S", "B"): 1.0, ("A", "T"): 1.0, ("B", "T"): 1.0},
        )
        first = graph.shortest_paths_to_exits("S")["T"][1]
        assert first == ["S", "A", "T"]
        assert k_shortest_paths(graph, "S", "T", first, {}, None, k=1) == [first]
        assert k_shortest_paths(graph, "S", "T", first, {}, None, k=3) == [
            ["S", "A", "T"],
            ["S", "B", "T"],
        ]

    def test_equal_costs_order_on_hops_then_path(self):
        from pyfds_evac.core.route_graph import k_shortest_paths

        graph = _line_graph(
            {
                "S": "distribution",
                "A": "checkpoint",
                "B": "checkpoint",
                "C": "checkpoint",
                "D": "checkpoint",
                "T": "exit",
            },
            {
                ("S", "T"): 2.0,
                ("S", "A"): 1.0,
                ("S", "B"): 1.0,
                ("S", "C"): 0.5,
                ("A", "T"): 1.0,
                ("B", "T"): 1.0,
                ("C", "D"): 0.5,
                ("D", "T"): 1.0,
            },
        )
        first = graph.shortest_paths_to_exits("S")["T"][1]
        assert first == ["S", "T"]
        assert k_shortest_paths(graph, "S", "T", first, {}, None, k=4) == [
            ["S", "T"],
            ["S", "A", "T"],
            ["S", "B", "T"],
            ["S", "C", "D", "T"],
        ]

    def test_paths_are_loopless_and_ordered_by_cost(self):
        from pyfds_evac.core.route_graph import k_shortest_paths

        graph = _line_graph(
            {"S": "distribution", "A": "checkpoint", "B": "checkpoint", "T": "exit"},
            {
                ("S", "A"): 1.0,
                ("A", "B"): 1.0,
                ("B", "A"): 1.0,
                ("A", "T"): 5.0,
                ("B", "T"): 1.0,
                ("S", "B"): 4.0,
            },
        )
        first = graph.shortest_paths_to_exits("S")["T"][1]
        paths = k_shortest_paths(graph, "S", "T", first, {}, None, k=9)
        # Costs 3, 5, 6 and 10; S > A > B > A > T would loop.
        assert paths == [
            ["S", "A", "B", "T"],
            ["S", "B", "T"],
            ["S", "A", "T"],
            ["S", "B", "A", "T"],
        ]
        assert all(len(set(p)) == len(p) for p in paths)


class TestUnreachableAndPaths:
    @staticmethod
    def _graph() -> StageGraph:
        return _line_graph(
            {"S": "distribution", "A": "checkpoint", "T": "exit", "U": "exit"},
            {("S", "A"): 1.5, ("A", "T"): 2.5},
        )

    def test_unreachable_exit_is_not_returned(self):
        assert self._graph().shortest_paths_to_exits("S") == {
            "T": (4.0, ["S", "A", "T"])
        }

    def test_unreachable_target_gives_none(self):
        assert self._graph().shortest_path_to("S", "U") is None

    def test_reachable_target_gives_cost_and_path(self):
        graph = self._graph()
        assert graph.shortest_path_to("S", "A") == (1.5, ["S", "A"])
        assert graph.shortest_path_to("S", "T") == (4.0, ["S", "A", "T"])

    def test_source_reaches_itself_at_no_cost(self):
        assert self._graph().shortest_path_to("S", "S") == (0.0, ["S"])

    def test_unknown_source_reaches_nothing(self):
        graph = self._graph()
        assert graph.shortest_paths_to_exits("X") == {}
        assert graph.shortest_path_to("X", "T") is None


class TestReconstruct:
    def test_path_starts_at_the_source_even_if_the_source_has_a_predecessor(self):
        prev = {"S": "X", "X": None, "T": "S"}
        assert StageGraph._reconstruct(prev, "S", "T") == ["S", "T"]


def test_a_zero_weight_self_loop_is_never_relaxed(bounded_search):
    """S has a zero-weight loop and an edge of 2 to T.

    A relaxation takes an edge only for a strictly lower cost, and the loop
    would give S 0 + 0 = 0, no lower than its 0. So S is expanded once and T
    once: two pops, cost 2. A relaxation that accepts equal cost pushes S
    again for ever; the bound turns that into a failure instead of a hang.
    """
    graph = _line_graph(
        {"S": "distribution", "T": "exit"},
        {("S", "S"): 0.0, ("S", "T"): 2.0},
    )
    assert graph.shortest_paths_to_exits("S") == {"T": (2.0, ["S", "T"])}
    assert bounded_search.count == 2
