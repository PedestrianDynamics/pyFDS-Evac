"""Hand-computed values of the stage graph search and exit schedule (#816).

Each test fixes one behaviour of ``route_graph`` to numbers that can be
checked on paper: the half-open schedule window, which stages a closure
removes, the cost and path of a search from a point off the graph, and
the predecessor chosen between equal-cost paths. Graphs are built from
explicit edge weights so the expected costs are sums of those weights.
"""

from __future__ import annotations

import math

import pytest

from pyfds_evac.core.route_graph import (
    StageEdge,
    StageGraph,
    StageNode,
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
