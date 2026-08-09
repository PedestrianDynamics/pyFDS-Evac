"""An agent that spawns knowing no exit has to explore to find one.

Drives ``assets/blind_spawn_discovery`` through the real map-expansion and
routing code.  Both exits are behind walls, so a discovery agent's map at t=0
holds no exit at all and ``rank_routes`` returns nothing -- the state every
other discovery asset is built to avoid, and the one the Station's dance floor
is in.

The exits are hidden by **geometry**, not by distance or bearing: both sit
24.7 m from the spawn centroid, inside the 30 m ceiling, and both signs are
omni-directional.  That leaves fdsvismap's line-of-sight term as the only thing
that can hide them:

    view_angle * visibility * non_concealed >= distance

``VisibilityModel.clear_air`` supplies that term: fdsvismap evaluates the scene
from the walkable polygon and a uniform zero extinction field, so the ray
casting is the library's own rather than a local approximation.  No FDS output
is needed.
"""

from __future__ import annotations

import importlib.util
import json
import math
import random
from pathlib import Path

import pytest
from shapely import wkt as shapely_wkt
from shapely.geometry import Polygon

from pyfds_evac.core.cognitive_map import (
    cognitive_subgraph,
    expand_on_arrival,
    init_cognitive_map,
    nearest_frontier_target,
)
from pyfds_evac.core.route_graph import RouteCostConfig, StageGraph, rank_routes
from pyfds_evac.core.smoke_speed import ConstantExtinctionField
from pyfds_evac.core.visibility import VisibilityModel

ASSET = Path("assets/blind_spawn_discovery")
# Below the ~0.4 m walls of this asset: a cell blocks sight when its centre is
# outside the walkable area, so at the 0.5 m default these walls fall between
# centres and stop occluding anything -- which is the premise of the whole file.
CELL_SIZE_M = 0.25
MAX_VIS_M = 30.0
SPAWN = "jps-distributions_0"


def _builder():
    spec = importlib.util.spec_from_file_location(
        "bsd_builder", ASSET / "build_geometry.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load(variant: str = "discovery"):
    raw = json.loads((ASSET / f"config_{variant}.json").read_text(encoding="utf-8"))
    walkable = shapely_wkt.loads(
        (ASSET / "geometry.wkt").read_text(encoding="utf-8").strip()
    )
    stages = {
        key: {"polygon": Polygon(value["coordinates"]), "stage_type": "exit"}
        for key, value in raw["exits"].items()
    }
    stages.update(
        {
            key: {"polygon": Polygon(value["coordinates"]), "stage_type": "checkpoint"}
            for key, value in raw["checkpoints"].items()
        }
    )
    graph = StageGraph.from_scenario(
        stages,
        [],
        distributions={
            key: {"coordinates": value["coordinates"]}
            for key, value in raw["distributions"].items()
        },
        walkable_polygon=walkable,
    )
    signs = {key: value["sign"] for key, value in raw["exits"].items()}
    for key, value in raw["checkpoints"].items():
        centroid = Polygon(value["coordinates"]).centroid
        # What _default_sign() synthesises for a crossing: omni-directional.
        signs[key] = {"x": centroid.x, "y": centroid.y, "c": 3}
    return (
        raw,
        graph,
        VisibilityModel.clear_air(walkable, signs, cell_size_m=CELL_SIZE_M),
        walkable,
    )


def _spawn_xy(graph):
    node = graph.nodes[SPAWN]
    return node.centroid_x, node.centroid_y


def _ranked_exits(graph, cmap, source, position):
    return [
        rc.exit_id
        for rc in rank_routes(
            graph,
            source,
            0.0,
            0.0,
            ConstantExtinctionField(0.0),
            None,
            RouteCostConfig(base_speed_m_per_s=1.3, w_smoke=0.0, w_fed=0.0),
            cognitive_map=cmap,
            agent_position=position,
        )
    ]


class TestThePremise:
    """The asset is worthless if any of these drift."""

    def test_both_exits_are_inside_the_visibility_ceiling(self):
        """Otherwise they are hidden by distance and occlusion proves nothing."""
        builder = _builder()
        spawn = builder._centroid(builder.SPAWN)
        for bounds in (builder.E_WEST, builder.E_EAST):
            assert math.dist(spawn, builder._centroid(bounds)) < MAX_VIS_M

    def test_both_exits_are_occluded_from_the_spawn_area(self):
        builder = _builder()
        walkable = builder.walkable_area()
        spawn = builder._centroid(builder.SPAWN)
        for bounds in (builder.E_WEST, builder.E_EAST):
            assert not builder.line_of_sight_clear(
                spawn, builder._centroid(bounds), walkable
            )

    def test_the_first_doorway_is_visible_or_there_is_nothing_to_explore(self):
        builder = _builder()
        walkable = builder.walkable_area()
        assert builder.line_of_sight_clear(
            builder._centroid(builder.SPAWN), builder._centroid(builder.C1), walkable
        )

    def test_the_exits_are_symmetric(self):
        """So the split between them cannot be explained by distance."""
        builder = _builder()
        spawn = builder._centroid(builder.SPAWN)
        west = math.dist(spawn, builder._centroid(builder.E_WEST))
        east = math.dist(spawn, builder._centroid(builder.E_EAST))
        assert west == pytest.approx(east)

    def test_removing_the_walls_would_make_the_exits_legible(self):
        """The strong control: occlusion, not bearing or distance, hides them.

        Without this, a bug that made every sign illegible would satisfy the
        occlusion assertions above for entirely the wrong reason.
        """
        _, graph, _, walkable = _load()
        signs = {"E_west": {"x": 6.0, "y": 29.0, "c": 3}}
        open_plan = VisibilityModel.clear_air(
            walkable.envelope, signs, cell_size_m=CELL_SIZE_M
        )
        walled = VisibilityModel.clear_air(walkable, signs, cell_size_m=CELL_SIZE_M)
        x, y = _spawn_xy(graph)
        assert open_plan.node_is_visible(0.0, x, y, "E_west")
        assert not walled.node_is_visible(0.0, x, y, "E_west")


class TestTheGraphIsAChain:
    """Betweenness pruning is what makes this three hops instead of one."""

    def test_the_spawn_area_reaches_only_the_first_doorway(self):
        _, graph, _, _ = _load()
        assert {edge.target for edge in graph.edges[SPAWN]} == {"C1"}

    def test_no_exit_is_adjacent_to_the_spawn_area_or_the_first_doorway(self):
        _, graph, _, _ = _load()
        for node in (SPAWN, "C1"):
            targets = {edge.target for edge in graph.edges[node]}
            assert not targets & {"E_west", "E_east"}

    def test_each_inner_doorway_reaches_its_own_exit(self):
        _, graph, _, _ = _load()
        assert "E_west" in {edge.target for edge in graph.edges["C2"]}
        assert "E_east" in {edge.target for edge in graph.edges["C3"]}


class TestTheAgentSpawnsBlind:
    def test_the_map_holds_the_spawn_area_and_the_first_doorway_only(self):
        _, graph, vis, _ = _load()
        cmap = init_cognitive_map(SPAWN, graph, "discovery", vis, 0.0)
        assert cmap.known_nodes == {SPAWN, "C1"}

    def test_no_exit_is_reachable_so_routing_returns_nothing(self):
        """The state that triggers frontier exploration, and it has never
        occurred in a simulation before this asset."""
        _, graph, vis, _ = _load()
        cmap = init_cognitive_map(SPAWN, graph, "discovery", vis, 0.0)
        assert _ranked_exits(graph, cmap, SPAWN, _spawn_xy(graph)) == []

    def test_the_frontier_is_the_first_doorway(self):
        _, graph, vis, _ = _load()
        cmap = init_cognitive_map(SPAWN, graph, "discovery", vis, 0.0)
        frontier = nearest_frontier_target(cmap, graph, SPAWN)
        assert frontier is not None
        target, path = frontier
        assert target == "C1"
        assert path == [SPAWN, "C1"]


class TestTheMapGrowsHopByHop:
    @staticmethod
    def _explored_to(*arrivals):
        _, graph, vis, _ = _load()
        cmap = init_cognitive_map(SPAWN, graph, "discovery", vis, 0.0)
        for node in arrivals:
            expand_on_arrival(cmap, node, graph)
        return graph, cmap

    def test_arriving_at_the_first_doorway_reveals_the_inner_ones(self):
        graph, cmap = self._explored_to("C1")
        assert {"C2", "C3"} <= cmap.known_nodes

    def test_but_still_no_exit(self):
        """``expand_on_arrival`` ignores visibility and reveals every neighbour,
        so this holds only because pruning kept the exits non-adjacent to C1.

        If pruning regresses, this fails and says so, instead of the scenario
        silently collapsing to a single hop.
        """
        graph, cmap = self._explored_to("C1")
        assert not cmap.known_nodes & {"E_west", "E_east"}
        assert _ranked_exits(graph, cmap, "C1", (12.0, 18.0)) == []

    def test_arriving_at_an_inner_doorway_reveals_its_exit(self):
        graph, cmap = self._explored_to("C1", "C2")
        assert "E_west" in cmap.known_nodes
        assert _ranked_exits(graph, cmap, "C2", (6.0, 22.0)) == ["E_west"]

    def test_three_hops_are_needed_and_two_are_not_enough(self):
        """The scenario's headline shape, asserted rather than assumed."""
        graph, cmap = self._explored_to()
        assert _ranked_exits(graph, cmap, SPAWN, _spawn_xy(graph)) == []
        graph, cmap = self._explored_to("C1")
        assert _ranked_exits(graph, cmap, "C1", (12.0, 18.0)) == []
        graph, cmap = self._explored_to("C1", "C2")
        assert _ranked_exits(graph, cmap, "C2", (6.0, 22.0)) != []


class TestTheFrontierChoiceFollowsThePosition:
    """Where an agent stands decides which doorway it explores (issue #68).

    ``C2`` and ``C3`` are equidistant from ``C1`` by construction, so the node
    distance cannot separate them. Before the fix the choice was measured from
    the node alone and ``sorted(frontier)`` broke the tie identically for
    everyone: 30/30 agents through the west door, the east room never entered,
    however the crowd was spread across the hall.
    """

    @staticmethod
    def _at_c1():
        _, graph, vis, _ = _load()
        cmap = init_cognitive_map(SPAWN, graph, "discovery", vis, 0.0)
        expand_on_arrival(cmap, "C1", graph)
        return graph, cmap

    def test_both_doorways_are_equidistant_from_the_first(self):
        """The premise: node distance cannot decide, so position must."""
        _, graph, _, _ = _load()
        weights = {edge.target: edge.weight for edge in graph.edges["C1"]}
        assert weights["C2"] == pytest.approx(weights["C3"])

    def test_an_agent_to_the_west_explores_the_west_doorway(self):
        graph, cmap = self._at_c1()
        assert nearest_frontier_target(cmap, graph, "C1", (11.2, 18.5))[0] == "C2"

    def test_an_agent_to_the_east_explores_the_east_doorway(self):
        graph, cmap = self._at_c1()
        assert nearest_frontier_target(cmap, graph, "C1", (12.8, 18.5))[0] == "C3"

    def test_without_a_position_the_node_distance_still_decides(self):
        """Backward compatible: callers that pass no position are unchanged."""
        graph, cmap = self._at_c1()
        assert nearest_frontier_target(cmap, graph, "C1")[0] == "C2"

    def test_two_agents_in_the_same_place_agree(self):
        """Determinism survives: the tie-break is still ``sorted(frontier)``."""
        graph, cmap = self._at_c1()
        chosen = {
            nearest_frontier_target(cmap, graph, "C1", (12.0, 18.0))[0]
            for _ in range(3)
        }
        assert len(chosen) == 1


class TestTheOtherThreeConfigs:
    def test_full_familiarity_knows_both_exits_at_spawn(self):
        _, graph, vis, _ = _load("full")
        cmap = init_cognitive_map(SPAWN, graph, "full", vis, 0.0)
        assert {"E_west", "E_east"} <= cmap.known_nodes
        assert set(_ranked_exits(graph, cmap, SPAWN, _spawn_xy(graph))) == {
            "E_west",
            "E_east",
        }

    def test_the_entrance_is_known_and_routable_without_exploring(self):
        """Everyone entered by one door, so everyone knows that door.

        This is the Station crush mechanism in miniature, and until now it was
        wired through the code with no behavioural test anywhere.
        """
        raw, graph, vis, _ = _load("entrance")
        declared = raw["distributions"][SPAWN]["parameters"]["entrance"]
        assert declared == "E_west", "asset changed; this test is now vacuous"
        cmap = init_cognitive_map(
            SPAWN, graph, "discovery", vis, 0.0, entrance=declared
        )
        assert declared in cmap.known_nodes
        assert _ranked_exits(graph, cmap, SPAWN, _spawn_xy(graph)) == [declared]

    def test_the_entrance_does_not_leak_the_other_exit(self):
        """Control: seeding one door must not seed the building."""
        _, graph, vis, _ = _load("entrance")
        cmap = init_cognitive_map(
            SPAWN, graph, "discovery", vis, 0.0, entrance="E_west"
        )
        assert "E_east" not in cmap.known_nodes

    def test_a_mixed_crowd_splits_between_knowing_and_exploring(self):
        raw, graph, vis, _ = _load("mixed")
        probability = raw["distributions"][SPAWN]["parameters"]["familiarity"]
        assert probability == 0.5, "asset changed; the band below assumes 0.5"
        knew = 0
        population = 400  # far more than the asset's 30, to test the draw itself
        for agent_id in range(population):
            cmap = init_cognitive_map(
                SPAWN,
                graph,
                probability,
                vis,
                0.0,
                rng=random.Random(1301 + agent_id * 7919),
            )
            if cmap.known_nodes & {"E_west", "E_east"}:
                knew += 1
        share = knew / population
        # Each of the two exits is drawn independently at p=0.5, so the share
        # knowing *at least one* is 1 - 0.5^2 = 0.75, not 0.5.
        assert 0.70 < share < 0.80, share

    def test_the_mixed_draw_is_reproducible(self):
        _, graph, vis, _ = _load("mixed")

        def draw():
            return [
                sorted(
                    init_cognitive_map(
                        SPAWN,
                        graph,
                        0.5,
                        vis,
                        0.0,
                        rng=random.Random(1301 + i * 7919),
                    ).known_nodes
                )
                for i in range(30)
            ]

        assert draw() == draw()


class TestTheKnownSubgraphIsHonest:
    def test_an_unknown_exit_is_absent_not_merely_rejected(self):
        """Absence is a stronger claim than rejection: a rejected route still
        appears in the ranking and the all-rejected fallback can reinstate it.
        """
        _, graph, vis, _ = _load()
        cmap = init_cognitive_map(SPAWN, graph, "discovery", vis, 0.0)
        sub = cognitive_subgraph(cmap, graph)
        assert "E_west" not in sub.nodes
        assert "E_east" not in sub.nodes
