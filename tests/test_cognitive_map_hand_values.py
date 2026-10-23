"""Cognitive-map expansion on a five-node graph, asserted node by node.

    S (0, 0)  --> A (5, 0)  --> X1 (10, 0)        exit
      |            ^  |
      v            |  v
    B (0, 8)  <----+--+                           A <-> B both ways
      |
      v
    X2 (0, 16)                                    exit

Edges: S->A, S->B, A->X1, A->B, B->A, B->X2. The visibility model is a stub
with a fixed set of visible nodes that records every query, so each test
states exactly what the agent sees and exactly what it must then know.
"""

from __future__ import annotations

import random

import pytest
from shapely.geometry import box

from pyfds_evac.core import scenario as scenario_mod
from pyfds_evac.core.cognitive_map import (
    cognitive_subgraph,
    expand_from_visibility,
    expand_on_arrival,
    familiarity_probability,
    init_cognitive_map,
)
from pyfds_evac.core.route_graph import RouteCostConfig, StageGraph


def _b(cx, cy, half=0.5):
    return box(cx - half, cy - half, cx + half, cy + half)


def _graph():
    stages = {
        "A": {"polygon": _b(5, 0), "stage_type": "checkpoint"},
        "B": {"polygon": _b(0, 8), "stage_type": "checkpoint"},
        "X1": {"polygon": _b(10, 0), "stage_type": "exit"},
        "X2": {"polygon": _b(0, 16), "stage_type": "exit"},
    }
    transitions = [
        {"from": "S", "to": "A"},
        {"from": "S", "to": "B"},
        {"from": "A", "to": "X1"},
        {"from": "A", "to": "B"},
        {"from": "B", "to": "A"},
        {"from": "B", "to": "X2"},
    ]
    return StageGraph.from_scenario(
        stages, transitions, distributions={"S": {"polygon": _b(0, 0)}}
    )


class _Vis:
    """Fixed visibility; records (time, x, y, node) for every query."""

    def __init__(self, visible):
        self.visible = set(visible)
        self.calls: list[tuple] = []

    def node_is_visible(self, time_s, ax, ay, node_id):
        self.calls.append((time_s, ax, ay, node_id))
        return node_id in self.visible


class _FixedRng:
    """random() returns the given values in order; counts the draws."""

    def __init__(self, *values):
        self._values = list(values)
        self.draws = 0

    def random(self):
        self.draws += 1
        return self._values.pop(0)


def _blank(graph=None):
    return init_cognitive_map(
        "S", graph or _graph(), 0.0, None, 0.0, no_visibility=True
    )


class TestExpandOnArrival:
    def test_only_the_visible_neighbour_is_learned(self):
        graph, vis = _graph(), _Vis({"A"})
        cmap = _blank(graph)
        expand_on_arrival(cmap, "S", graph, vis, 2.5, 1.0, 2.0)
        assert cmap.known_nodes == {"S", "A"}
        assert cmap.known_edges == {("S", "A")}
        assert cmap.visited_nodes == {"S"}

    def test_every_neighbour_is_queried_from_the_agent_position(self):
        graph, vis = _graph(), _Vis(set())
        cmap = _blank(graph)
        expand_on_arrival(cmap, "S", graph, vis, 2.5, 1.0, 2.0)
        assert vis.calls == [(2.5, 1.0, 2.0, "A"), (2.5, 1.0, 2.0, "B")]

    def test_nothing_visible_teaches_only_the_standing_node(self):
        graph = _graph()
        cmap = _blank(graph)
        expand_on_arrival(cmap, "S", graph, _Vis(set()), 0.0, 0.0, 0.0)
        assert cmap.known_nodes == {"S"}
        assert cmap.known_edges == set()

    def test_without_a_vis_model_every_neighbour_is_revealed(self):
        graph = _graph()
        cmap = _blank(graph)
        expand_on_arrival(cmap, "S", graph, None, 0.0)
        assert cmap.known_nodes == {"S", "A", "B"}
        assert cmap.known_edges == {("S", "A"), ("S", "B")}

    def test_a_vis_model_without_a_position_reveals_every_neighbour(self):
        graph, vis = _graph(), _Vis(set())
        cmap = _blank(graph)
        expand_on_arrival(cmap, "S", graph, vis, 0.0)
        assert cmap.known_nodes == {"S", "A", "B"}
        assert vis.calls == []

    def test_a_two_way_neighbour_teaches_both_directions(self):
        graph = _graph()
        cmap = _blank(graph)
        expand_on_arrival(cmap, "A", graph, _Vis({"B"}), 0.0, 5.0, 0.0)
        assert cmap.known_nodes == {"S", "A", "B"}
        assert cmap.known_edges == {("A", "B"), ("B", "A")}

    def test_a_one_way_neighbour_teaches_only_its_direction(self):
        graph = _graph()
        cmap = _blank(graph)
        expand_on_arrival(cmap, "A", graph, _Vis({"X1"}), 0.0, 5.0, 0.0)
        assert cmap.known_nodes == {"S", "A", "X1"}
        assert cmap.known_edges == {("A", "X1")}

    def test_the_walked_leg_is_learned_in_its_own_direction(self):
        graph = _graph()
        cmap = _blank(graph)
        expand_on_arrival(cmap, "A", graph, _Vis(set()), 0.0, 5.0, 0.0, from_node="S")
        assert cmap.known_nodes == {"S", "A"}
        assert cmap.known_edges == {("S", "A")}

    def test_a_leg_walked_against_the_graph_is_learned_as_the_graph_has_it(self):
        graph = _graph()
        cmap = _blank(graph)
        expand_on_arrival(cmap, "A", graph, _Vis(set()), 0.0, 5.0, 0.0, from_node="X1")
        assert cmap.known_nodes == {"S", "A", "X1"}
        assert cmap.known_edges == {("A", "X1")}

    @pytest.mark.parametrize("from_node", [None, "A", "nowhere"])
    def test_no_leg_is_learned_without_a_real_origin(self, from_node):
        graph = _graph()
        cmap = _blank(graph)
        expand_on_arrival(
            cmap, "A", graph, _Vis(set()), 0.0, 5.0, 0.0, from_node=from_node
        )
        assert cmap.known_nodes == {"S", "A"}
        assert cmap.known_edges == set()

    def test_a_full_map_is_left_alone(self):
        graph = _graph()
        cmap = init_cognitive_map("S", graph, 1.0, None, 0.0)
        before = (set(cmap.known_nodes), set(cmap.known_edges))
        vis = _Vis(set())
        expand_on_arrival(cmap, "A", graph, vis, 0.0, 5.0, 0.0, from_node="S")
        assert (cmap.known_nodes, cmap.known_edges) == before
        assert cmap.visited_nodes == set()

    def test_a_full_map_does_not_ask_the_vis_model_on_arrival(self):
        graph, vis = _graph(), _Vis(set())
        cmap = init_cognitive_map("S", graph, 1.0, None, 0.0)
        expand_on_arrival(cmap, "A", graph, vis, 0.0, 5.0, 0.0, from_node="S")
        assert vis.calls == []


class TestExpandFromVisibility:
    def test_visible_neighbours_are_learned_and_the_rest_are_not(self):
        graph, vis = _graph(), _Vis({"B"})
        cmap = _blank(graph)
        expand_from_visibility(cmap, "S", graph, vis, 4.0, 0.5, 0.25)
        assert cmap.known_nodes == {"S", "B"}
        assert cmap.known_edges == {("S", "B")}
        assert vis.calls == [(4.0, 0.5, 0.25, "A"), (4.0, 0.5, 0.25, "B")]

    def test_perception_does_not_mark_a_node_visited(self):
        graph = _graph()
        cmap = _blank(graph)
        expand_from_visibility(cmap, "S", graph, _Vis({"A", "B"}), 0.0, 0.0, 0.0)
        assert cmap.visited_nodes == {"S"}

    def test_no_vis_model_adds_nothing(self):
        graph = _graph()
        cmap = _blank(graph)
        expand_from_visibility(cmap, "S", graph, None, 0.0, 0.0, 0.0)
        assert cmap.known_nodes == {"S"}
        assert cmap.known_edges == set()

    @pytest.mark.parametrize("familiarity", [1.0, "full"])
    def test_a_full_map_does_not_even_ask(self, familiarity):
        graph, vis = _graph(), _Vis({"A"})
        cmap = init_cognitive_map("S", graph, familiarity, None, 0.0)
        expand_from_visibility(cmap, "S", graph, vis, 0.0, 0.0, 0.0)
        assert vis.calls == []


class TestFamiliarityBoundary:
    def test_exactly_one_is_the_full_map(self):
        graph = _graph()
        cmap = init_cognitive_map("S", graph, 1.0, None, 0.0)
        assert cmap.familiarity == "full"
        assert cmap.known_nodes == set(graph.nodes)
        assert cmap.known_edges == {
            ("S", "A"),
            ("S", "B"),
            ("A", "X1"),
            ("A", "B"),
            ("B", "A"),
            ("B", "X2"),
        }

    def test_just_below_one_is_a_discovery_map(self):
        graph = _graph()
        cmap = init_cognitive_map(
            "S", graph, 1.0 - 1e-12, None, 0.0, rng=_FixedRng(1.0 - 1e-13, 1.0 - 1e-13)
        )
        assert cmap.familiarity == "discovery"
        assert cmap.known_nodes == {"S"}
        assert cmap.visited_nodes == {"S"}

    def test_zero_is_a_discovery_map(self):
        graph = _graph()
        cmap = init_cognitive_map("S", graph, 0.0, None, 0.0)
        assert cmap.familiarity == "discovery"
        assert cmap.known_nodes == {"S"}

    def test_a_full_subgraph_is_the_graph_itself(self):
        graph = _graph()
        cmap = init_cognitive_map("S", graph, "full", None, 0.0)
        assert cognitive_subgraph(cmap, graph) is graph

    def test_a_partial_subgraph_holds_only_known_nodes_and_edges(self):
        graph = _graph()
        cmap = _blank(graph)
        cmap.known_nodes |= {"A", "X1"}
        cmap.known_edges |= {("S", "A"), ("A", "X1"), ("A", "B")}
        sub = cognitive_subgraph(cmap, graph)
        assert set(sub.nodes) == {"S", "A", "X1"}
        assert {s: [e.target for e in es] for s, es in sub.edges.items()} == {
            "S": ["A"],
            "A": ["X1"],
        }


class TestFamiliarityValue:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [("full", 1.0), ("discovery", 0.0), (0, 0.0), (0.25, 0.25), (1, 1.0)],
    )
    def test_accepted_values(self, value, expected):
        assert familiarity_probability(value) == expected

    @pytest.mark.parametrize("value", [-1e-9, 1.0 + 1e-9, -1, 2, "partial", ""])
    def test_rejected_values(self, value):
        with pytest.raises(ValueError, match="familiarity|unknown"):
            familiarity_probability(value)

    def test_the_bounds_are_inclusive(self):
        assert familiarity_probability(0.0) == 0.0
        assert familiarity_probability(1.0) == 1.0
        assert familiarity_probability(1.0 - 1e-12) < 1.0


class TestInitialDraw:
    def test_a_draw_below_p_makes_the_exit_known_with_its_route(self):
        cmap = init_cognitive_map(
            "S", _graph(), 0.5, None, 0.0, rng=_FixedRng(0.1, 0.9), no_visibility=True
        )
        assert cmap.known_nodes == {"S", "A", "X1"}
        assert cmap.known_edges == {("S", "A"), ("A", "X1")}

    def test_the_draw_is_strict(self):
        cmap = init_cognitive_map(
            "S", _graph(), 0.5, None, 0.0, rng=_FixedRng(0.5, 0.5), no_visibility=True
        )
        assert cmap.known_nodes == {"S"}

    def test_each_exit_gets_its_own_draw_in_exit_order(self):
        graph = _graph()
        assert graph.exit_nodes() == ["X1", "X2"]
        cmap = init_cognitive_map(
            "S", graph, 0.5, None, 0.0, rng=_FixedRng(0.9, 0.1), no_visibility=True
        )
        assert cmap.known_nodes == {"S", "B", "X2"}
        assert cmap.known_edges == {("S", "B"), ("B", "X2")}

    def test_a_small_p_still_draws(self):
        rng = _FixedRng(0.01, 0.99)
        cmap = init_cognitive_map(
            "S", _graph(), 0.02, None, 0.0, rng=rng, no_visibility=True
        )
        assert rng.draws == 2
        assert cmap.known_nodes == {"S", "A", "X1"}

    def test_zero_never_draws(self):
        rng = _FixedRng()
        cmap = init_cognitive_map(
            "S", _graph(), 0.0, None, 0.0, rng=rng, no_visibility=True
        )
        assert rng.draws == 0
        assert cmap.known_nodes == {"S"}

    def test_without_an_rng_nothing_is_drawn(self):
        cmap = init_cognitive_map("S", _graph(), 0.9, None, 0.0, no_visibility=True)
        assert cmap.known_nodes == {"S"}

    def test_a_seeded_rng_is_reproducible(self):
        graph = _graph()
        maps = [
            init_cognitive_map(
                "S", graph, 0.5, None, 0.0, rng=random.Random(7), no_visibility=True
            )
            for _ in range(2)
        ]
        assert maps[0].known_nodes == maps[1].known_nodes
        assert maps[0].known_edges == maps[1].known_edges

    def test_the_entrance_is_known_whatever_the_familiarity(self):
        cmap = init_cognitive_map(
            "S", _graph(), 0.0, None, 0.0, entrance="X2", no_visibility=True
        )
        assert cmap.known_nodes == {"S", "B", "X2"}
        assert cmap.known_edges == {("S", "B"), ("B", "X2")}

    def test_an_entrance_outside_the_graph_is_ignored(self):
        cmap = init_cognitive_map(
            "S", _graph(), 0.0, None, 0.0, entrance="X9", no_visibility=True
        )
        assert cmap.known_nodes == {"S"}

    def test_the_initial_look_sees_only_what_is_visible(self):
        graph, vis = _graph(), _Vis({"B"})
        cmap = init_cognitive_map("S", graph, 0.0, vis, 3.0)
        assert cmap.known_nodes == {"S", "B"}
        assert cmap.known_edges == {("S", "B")}
        node = graph.nodes["S"]
        assert vis.calls[0] == (3.0, node.centroid_x, node.centroid_y, "A")


class TestInitialExit:
    """``_assign_initial_exit`` ranks on the agent's own map."""

    @pytest.fixture
    def chosen_paths(self, monkeypatch):
        paths: list[list[str]] = []

        def record(_wait_info, path):
            paths.append(list(path))
            return True

        monkeypatch.setattr(scenario_mod, "_apply_initial_path", record)
        return paths

    def _assign(self, familiarity, maps, entrance=None):
        wait_info = {
            "current_origin": "S",
            "current_target_stage": "S",
            "familiarity": familiarity,
        }
        if entrance is not None:
            wait_info["entrance"] = entrance
        return scenario_mod._assign_initial_exit(
            1,
            wait_info,
            _graph(),
            RouteCostConfig(),
            None,
            0.0,
            42,
            maps,
            extinction_sampler=scenario_mod._ZERO_EXTINCTION,
            spawn_key=("hand", 0),
        )

    def test_a_full_map_takes_the_nearest_exit(self, chosen_paths):
        assert self._assign(1.0, {}) == "X1"
        assert chosen_paths == [["S", "A", "X1"]]

    def test_a_stranger_takes_the_entrance_even_when_it_is_farther(self, chosen_paths):
        assert self._assign(0.0, {}, entrance="X2") == "X2"
        assert chosen_paths == [["S", "B", "X2"]]

    def test_the_map_is_kept_for_the_reroute_pass(self, chosen_paths):
        maps: dict = {}
        self._assign(0.0, maps, entrance="X2")
        assert set(maps) == {1}
        assert maps[1].known_nodes == {"S", "B", "X2"}

    def test_a_second_decision_reuses_the_map_the_first_stored(self, chosen_paths):
        """A stranger told the entrance X2 stores a map of S, B and X2. A
        second decision for the same agent, now at familiarity 1.0, would
        take the nearest exit X1 from a fresh full map; it takes X2, from
        the stored one."""
        maps: dict = {}
        assert self._assign(0.0, maps, entrance="X2") == "X2"
        assert self._assign(1.0, maps) == "X2"
        assert chosen_paths == [["S", "B", "X2"], ["S", "B", "X2"]]

    def test_an_existing_map_is_used_not_rebuilt(self, chosen_paths):
        existing = init_cognitive_map(
            "S", _graph(), 0.0, None, 0.0, entrance="X1", no_visibility=True
        )
        maps = {1: existing}
        assert self._assign(0.0, maps, entrance="X2") == "X1"
        assert maps[1] is existing
