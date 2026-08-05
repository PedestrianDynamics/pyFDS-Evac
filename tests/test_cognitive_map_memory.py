"""A cognitive map remembers; a visibility query does not.

Drives the ``assets/cognitive_map_memory`` scenario through the real map
expansion code.  A discovery agent walks a corridor past a side exit whose sign
is legible only from a band of positions, and the scenario separates two claims
that a pure visibility query cannot tell apart:

* **acquisition** -- the exit enters the map when its sign first becomes
  legible;
* **persistence** -- it stays in the map once the agent walks on and the sign
  becomes illegible again.

Persistence is the one that matters.  Delete the expansion rules and
acquisition still appears to work for any agent that happens to start inside
the band; only persistence catches it.

No FDS output is needed: ``VisMapClearAir`` reimplements fdsvismap's clear-air
rule so the test exercises our map and routing rather than the third-party
solver.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest
from shapely.geometry import Polygon

from pyfds_evac.core.cognitive_map import (
    expand_from_visibility,
    init_cognitive_map,
)
from pyfds_evac.core.route_graph import RouteCostConfig, StageGraph, rank_routes
from pyfds_evac.core.smoke_speed import ConstantExtinctionField

ASSET = Path("assets/cognitive_map_memory")
MAX_VIS_M = 30.0
CENTRELINE_X = 2.0


class VisMapClearAir:
    """fdsvismap's clear-air legibility rule: view_angle * max_vis >= distance."""

    def __init__(self, signs: dict[str, dict], max_vis: float = MAX_VIS_M):
        self._signs = signs
        self._max_vis = max_vis

    def node_is_visible(self, time: float, x: float, y: float, node_id: str) -> bool:
        del time
        sign = self._signs.get(node_id)
        if sign is None:
            return True
        dx, dy = x - float(sign["x"]), y - float(sign["y"])
        distance = math.hypot(dx, dy)
        if distance == 0.0:
            return True
        alpha = sign.get("alpha")
        if alpha is None:
            view_angle = 1.0
        else:
            a = math.radians(float(alpha))
            view_angle = min(
                1.0, max(0.0, (math.sin(a) * dx + math.cos(a) * dy) / distance)
            )
        return view_angle * self._max_vis >= distance


def _load():
    raw = json.loads((ASSET / "config.json").read_text(encoding="utf-8"))
    stages = {
        exit_id: {"polygon": Polygon(data["coordinates"]), "stage_type": "exit"}
        for exit_id, data in raw["exits"].items()
    }
    distributions = {
        dist_id: {"coordinates": data["coordinates"]}
        for dist_id, data in raw["distributions"].items()
    }
    graph = StageGraph.from_scenario(
        stages, raw["transitions"], distributions=distributions, walkable_polygon=None
    )
    signs = {eid: data["sign"] for eid, data in raw["exits"].items()}
    spawn = Polygon(next(iter(distributions.values()))["coordinates"]).centroid
    return graph, (spawn.x, spawn.y), VisMapClearAir(signs)


def _walk(y_positions):
    """Walk the centreline, expanding the map at each step.

    Returns the known-exit set after each position, so a test can assert both
    what was acquired and what survived.
    """
    graph, _spawn, vis = _load()
    cmap = init_cognitive_map(
        "jps-distributions_0", graph, "discovery", vis_model=vis, time_s=0.0
    )
    history = [{n for n in cmap.known_nodes if n.startswith("E_")}]
    for y in y_positions:
        expand_from_visibility(
            cmap, "jps-distributions_0", graph, vis, 0.0, CENTRELINE_X, y
        )
        history.append({n for n in cmap.known_nodes if n.startswith("E_")})
    return history, cmap, graph, vis


class TestScenarioPremises:
    """The experiment is meaningless if these drift."""

    def test_side_exit_is_unknown_at_spawn(self):
        _, spawn, vis = _load()
        assert not vis.node_is_visible(0.0, *spawn, "E_side")

    def test_default_exit_is_known_at_spawn(self):
        """Without a default target the agent explores, which is another test."""
        _, spawn, vis = _load()
        assert vis.node_is_visible(0.0, *spawn, "E_end")

    def test_the_side_sign_really_does_go_illegible_again(self):
        """Persistence is untestable if the sign stays readable to the end."""
        _, _, vis = _load()
        assert vis.node_is_visible(0.0, CENTRELINE_X, 20.0, "E_side"), "mid-window"
        assert not vis.node_is_visible(0.0, CENTRELINE_X, 30.0, "E_side"), "past it"

    def test_side_exit_is_the_closer_one_once_known(self):
        """So acquisition has a behavioural consequence, not just a state change."""
        graph, _, _ = _load()
        side, end = graph.nodes["E_side"], graph.nodes["E_end"]
        assert side.centroid_y < end.centroid_y


class TestAcquisitionAndPersistence:
    def test_side_exit_is_acquired_on_entering_the_window(self):
        history, _, _, _ = _walk([8.0, 14.0])
        assert history[0] == {"E_end"}, "unknown before the window"
        assert history[1] == {"E_end"}, "still unknown just below it"
        assert history[2] == {"E_end", "E_side"}, "acquired inside the window"

    def test_side_exit_persists_after_its_sign_goes_illegible(self):
        """The map remembers. This is the claim a visibility query cannot make."""
        history, _, _, vis = _walk([14.0, 30.0])
        assert history[-1] == {"E_end", "E_side"}
        assert not vis.node_is_visible(0.0, CENTRELINE_X, 30.0, "E_side"), (
            "the sign must be unreadable at y=30 or persistence is not being tested"
        )

    def test_an_agent_that_never_enters_the_window_never_learns_it(self):
        """Control: acquisition requires perception, not merely walking."""
        history, _, _, _ = _walk([6.0, 8.0, 10.0])
        assert all(known == {"E_end"} for known in history)

    def test_a_remembered_exit_is_routable_though_illegible(self):
        """Membership, not current legibility, decides what routing offers.

        Before the visibility consolidation this failed: the router vetoed any
        route whose first hop had an unreadable sign, so an agent could know an
        exit and still be forbidden to use it.
        """
        _, cmap, graph, _ = _walk([14.0, 30.0])
        ranked = rank_routes(
            graph,
            "jps-distributions_0",
            0.0,
            0.0,
            ConstantExtinctionField(0.0),
            None,
            RouteCostConfig(base_speed_m_per_s=1.3, w_smoke=0.0, w_fed=0.0),
            cognitive_map=cmap,
            agent_position=(CENTRELINE_X, 30.0),
        )
        assert {rc.exit_id for rc in ranked} == {"E_end", "E_side"}
        assert not any(rc.rejected for rc in ranked)

    def test_acquiring_the_side_exit_changes_where_the_agent_would_go(self):
        """Acquisition has a behavioural consequence, not just a state change.

        The README claimed the agent diverts once it knows the side exit, but
        nothing asserted it -- and the state plot marched a probe straight past
        the side exit, implying the opposite.  Routing switches at y = 14, the
        moment the exit enters the map.
        """
        graph, _spawn, vis = _load()
        cmap = init_cognitive_map(
            "jps-distributions_0", graph, "discovery", vis_model=vis, time_s=0.0
        )

        def choice_at(y):
            expand_from_visibility(
                cmap, "jps-distributions_0", graph, vis, 0.0, CENTRELINE_X, y
            )
            ranked = rank_routes(
                graph,
                "jps-distributions_0",
                0.0,
                0.0,
                ConstantExtinctionField(0.0),
                None,
                RouteCostConfig(base_speed_m_per_s=1.3, w_smoke=0.0, w_fed=0.0),
                cognitive_map=cmap,
                agent_position=(CENTRELINE_X, y),
            )
            return ranked[0].exit_id

        assert choice_at(10.0) == "E_end", "below the window only E_end is known"
        assert choice_at(14.0) == "E_side", "inside it, the nearer exit wins"
        assert choice_at(30.0) == "E_side", "and it is still preferred from memory"

    def test_full_familiarity_knows_both_from_the_start(self):
        """Contrast: nothing to acquire when the map is pre-loaded."""
        graph, spawn, vis = _load()
        cmap = init_cognitive_map(
            "jps-distributions_0", graph, "full", vis_model=vis, time_s=0.0
        )
        assert cmap.familiarity == "full"
        ranked = rank_routes(
            graph,
            "jps-distributions_0",
            0.0,
            0.0,
            ConstantExtinctionField(0.0),
            None,
            RouteCostConfig(base_speed_m_per_s=1.3, w_smoke=0.0, w_fed=0.0),
            cognitive_map=cmap,
            agent_position=spawn,
        )
        assert {rc.exit_id for rc in ranked} == {"E_end", "E_side"}


class TestLegibilityWindowIsDerived:
    def test_builder_window_matches_the_visibility_rule(self):
        """The window is computed from the geometry, never hand-tuned."""
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "cmm_builder", ASSET / "build_geometry.py"
        )
        assert spec is not None and spec.loader is not None
        builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(builder)

        low, high = builder.legibility_window(*builder.E_SIDE_SIGN)
        _, _, vis = _load()
        assert low == pytest.approx(12.5, abs=0.1)
        assert high == pytest.approx(27.5, abs=0.1)
        assert vis.node_is_visible(0.0, CENTRELINE_X, (low + high) / 2, "E_side")
        assert not vis.node_is_visible(0.0, CENTRELINE_X, low - 1.0, "E_side")
        assert not vis.node_is_visible(0.0, CENTRELINE_X, high + 1.0, "E_side")
