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

``OccludingVisMap`` below reimplements that term on the walkable polygon, the
same way ``VisMapClearAir`` in ``test_cognitive_map_memory.py`` reimplements the
view-angle term.  No FDS output is needed.
"""

from __future__ import annotations

import importlib.util
import json
import math
import random
from pathlib import Path

import pytest
from shapely import wkt as shapely_wkt
from shapely.geometry import LineString, Polygon

from pyfds_evac.core.cognitive_map import (
    cognitive_subgraph,
    expand_on_arrival,
    init_cognitive_map,
    nearest_frontier_target,
)
from pyfds_evac.core.route_graph import RouteCostConfig, StageGraph, rank_routes
from pyfds_evac.core.smoke_speed import ConstantExtinctionField

ASSET = Path("assets/blind_spawn_discovery")
MAX_VIS_M = 30.0
SPAWN = "jps-distributions_0"


class OccludingVisMap:
    """Clear-air legibility including the line-of-sight mask.

    ``view_angle`` is 1 for every sign in this asset (all omni-directional) and
    ``visibility`` is ``max_vis`` in clear air, so the rule reduces to
    "within 30 m and not behind a wall".
    """

    def __init__(self, signs: dict[str, dict], walkable, max_vis: float = MAX_VIS_M):
        self._signs = signs
        self._walkable = walkable
        self._max_vis = max_vis

    def node_is_visible(self, time: float, x: float, y: float, node_id: str) -> bool:
        del time
        sign = self._signs.get(node_id)
        if sign is None:
            return True
        target = (float(sign["x"]), float(sign["y"]))
        if math.dist((x, y), target) > self._max_vis:
            return False
        return self._walkable.covers(LineString([(x, y), target]))


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
    return raw, graph, OccludingVisMap(signs, walkable), walkable


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
        open_plan = OccludingVisMap(signs, walkable.envelope)
        walled = OccludingVisMap(signs, walkable)
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


class TestTheFrontierTieBreakIsPositionBlind:
    """A recorded property, not a desired one.

    ``C2`` and ``C3`` are equidistant from ``C1``, and
    ``nearest_frontier_target`` measures from the *node*, never from the agent.
    So every agent standing anywhere at ``C1`` picks ``C2`` -- the run sends
    30/30 through the west door and leaves the east room empty, however the
    crowd is spread across the hall.

    That is why no test here asserts a split. Fixing it means giving the
    frontier choice the agent's position, which is a modelling change, not a
    test fix. Recorded so the behaviour is documented rather than discovered
    again.
    """

    def test_both_doorways_are_equidistant_from_the_first(self):
        _, graph, _, _ = _load()
        weights = {edge.target: edge.weight for edge in graph.edges["C1"]}
        assert weights["C2"] == pytest.approx(weights["C3"])

    def test_the_tie_always_breaks_the_same_way_wherever_the_agent_stands(self):
        _, graph, vis, _ = _load()
        cmap = init_cognitive_map(SPAWN, graph, "discovery", vis, 0.0)
        expand_on_arrival(cmap, "C1", graph)
        chosen = {nearest_frontier_target(cmap, graph, "C1")[0] for _ in range(3)}
        assert chosen == {"C2"}


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
