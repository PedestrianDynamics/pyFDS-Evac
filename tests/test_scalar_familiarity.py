"""Familiarity as a probability, and the entrance an agent walked in through.

The `full`/`discovery` binary cannot express a real crowd. At The Station,
29.2 % of patrons were there for the first time, just over 60 % had been five
times or fewer, and about two dozen were regulars -- a gradient, not two camps.

Familiarity is therefore the probability that each exit is already in an agent's
map at t=0. It is an *initialisation* parameter: once the map exists the agent is
either omniscient or learning, so everything downstream is unchanged.

Knowing an exit means knowing how to reach it. An exit added without the route
to it would sit in the map unreachable, since routing runs on the subgraph of
known nodes *and* known edges, so the whole shortest path is added with it.
"""

from __future__ import annotations

import random

import pytest
from shapely.geometry import box

from pyfds_evac.core.cognitive_map import cognitive_subgraph, init_cognitive_map
from pyfds_evac.core.route_graph import StageGraph


def _b(cx, cy, half=1.0):
    return box(cx - half, cy - half, cx + half, cy + half)


def _graph():
    """Spawn, a crossing, and two exits the crossing leads to."""
    stages = {
        "cp": {"polygon": _b(10, 0), "stage_type": "checkpoint"},
        "e_near": {"polygon": _b(20, 0), "stage_type": "exit"},
        "e_far": {"polygon": _b(10, 20), "stage_type": "exit"},
    }
    return StageGraph.from_scenario(
        stages, [], distributions={"spawn": {"polygon": _b(0, 0)}}
    )


def _known_exits(cmap):
    return {n for n in cmap.known_nodes if n.startswith("e_")}


class TestFamiliarityAsAProbability:
    def test_one_point_zero_is_the_old_full_tier(self):
        cmap = init_cognitive_map("spawn", _graph(), 1.0, None, 0.0)
        assert cmap.familiarity == "full"
        assert cmap.known_nodes == set(_graph().nodes)

    def test_zero_is_the_old_discovery_tier(self):
        graph = _graph()
        by_number = init_cognitive_map("spawn", graph, 0.0, None, 0.0)
        by_name = init_cognitive_map("spawn", graph, "discovery", None, 0.0)
        assert by_number.known_nodes == by_name.known_nodes

    def test_the_old_names_still_work(self):
        graph = _graph()
        assert init_cognitive_map("spawn", graph, "full", None, 0.0).familiarity == (
            "full"
        )
        assert (
            init_cognitive_map("spawn", graph, "discovery", None, 0.0).familiarity
            == "discovery"
        )

    def test_a_population_lands_near_the_requested_share(self):
        """Over many agents, the share knowing a given exit approaches p."""
        graph = _graph()
        p = 0.3
        knows = 0
        trials = 400
        for i in range(trials):
            cmap = init_cognitive_map(
                "spawn", graph, p, None, 0.0, rng=random.Random(i), no_visibility=True
            )
            if "e_far" in cmap.known_nodes:
                knows += 1
        assert knows / trials == pytest.approx(p, abs=0.06)

    def test_the_draw_is_reproducible_for_a_given_seed(self):
        graph = _graph()
        a = init_cognitive_map(
            "spawn", graph, 0.5, None, 0.0, rng=random.Random(7), no_visibility=True
        )
        b = init_cognitive_map(
            "spawn", graph, 0.5, None, 0.0, rng=random.Random(7), no_visibility=True
        )
        assert a.known_nodes == b.known_nodes

    def test_a_value_outside_zero_to_one_is_rejected(self):
        for bad in (-0.1, 1.5):
            with pytest.raises(ValueError):
                init_cognitive_map("spawn", _graph(), bad, None, 0.0)


class TestKnowingAnExitMeansKnowingTheRoute:
    def test_a_known_exit_is_actually_reachable(self):
        """An exit without its route would sit in the map unusable."""
        graph = _graph()
        cmap = init_cognitive_map(
            "spawn",
            graph,
            1.0 - 1e-9,
            None,
            0.0,
            rng=random.Random(1),
            no_visibility=True,
        )
        sub = cognitive_subgraph(cmap, graph)
        for exit_id in _known_exits(cmap):
            assert exit_id in sub.shortest_paths_to_exits("spawn"), exit_id

    def test_the_intermediate_crossing_comes_with_the_exit(self):
        graph = _graph()
        cmap = init_cognitive_map(
            "spawn",
            graph,
            1.0 - 1e-9,
            None,
            0.0,
            rng=random.Random(1),
            no_visibility=True,
        )
        if "e_near" in cmap.known_nodes:
            assert "cp" in cmap.known_nodes, "the route to e_near passes cp"


class TestEntranceSeeding:
    """An agent knows the door it walked in through, whatever its familiarity.

    At The Station every patron entered by the front door, and that single fact
    is the mechanism behind the crush: the exit everyone knew was the one
    everyone went back to.
    """

    def test_the_entrance_is_known_even_at_zero_familiarity(self):
        cmap = init_cognitive_map(
            "spawn", _graph(), 0.0, None, 0.0, entrance="e_far", no_visibility=True
        )
        assert "e_far" in cmap.known_nodes

    def test_the_entrance_is_reachable_not_merely_listed(self):
        graph = _graph()
        cmap = init_cognitive_map(
            "spawn", graph, 0.0, None, 0.0, entrance="e_far", no_visibility=True
        )
        assert "e_far" in cognitive_subgraph(cmap, graph).shortest_paths_to_exits(
            "spawn"
        )

    def test_no_entrance_leaves_a_zero_familiarity_agent_knowing_no_exit(self):
        """Control: the entrance is what puts it there, not the default state."""
        cmap = init_cognitive_map("spawn", _graph(), 0.0, None, 0.0, no_visibility=True)
        assert _known_exits(cmap) == set()

    def test_an_unknown_entrance_name_is_ignored_not_fatal(self):
        cmap = init_cognitive_map(
            "spawn",
            _graph(),
            0.0,
            None,
            0.0,
            entrance="not_a_stage",
            no_visibility=True,
        )
        assert _known_exits(cmap) == set()
