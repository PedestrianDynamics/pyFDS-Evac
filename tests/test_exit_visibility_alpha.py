"""Sign legibility decides what a discovery agent knows, and so where it goes.

Drives the ``assets/exit_visibility_alpha`` scenario through the real routing
code.  The two configs differ in exactly one value -- the viewing bearing of
the near exit's sign -- so any difference in the chosen exit is attributable to
sign orientation and nothing else.

Routing consults the agent's cognitive map, never sign legibility directly, so
an illegible exit is *absent from the graph* rather than present-and-rejected.
That is why the agents are ``discovery`` tier: a ``full`` agent knows every
exit from t=0 and would walk to the near one under either bearing -- correctly,
since it does not need to read a sign to find a door it already knows.

No FDS output is needed.  ``VisibilityModel.clear_air`` drives fdsvismap itself
fdsvismap applies in clear air, so the test exercises our routing decision
rather than the third-party visibility solver.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest
from shapely import wkt as shapely_wkt
from shapely.geometry import Polygon

from pyfds_evac.core.cognitive_map import init_cognitive_map
from pyfds_evac.core.route_graph import RouteCostConfig, StageGraph, rank_routes
from pyfds_evac.core.smoke_speed import ConstantExtinctionField
from pyfds_evac.core.visibility import VisibilityModel

ASSET = Path("assets/exit_visibility_alpha")


# fdsvismap's clear-air visibility distance saturates at this default.
MAX_VIS_M = 30.0
# Fine enough that this asset's walls still occlude; see
# VisibilityModel.clear_air on why the rasterisation resolution matters.
CELL_SIZE_M = 0.25


def _load(config_name: str):
    """Return (graph, spawn_centroid, vis_model) for one asset config."""
    raw = json.loads((ASSET / f"{config_name}.json").read_text(encoding="utf-8"))

    stages = {
        exit_id: {"polygon": Polygon(data["coordinates"]), "stage_type": "exit"}
        for exit_id, data in raw["exits"].items()
    }
    distributions = {
        dist_id: {"coordinates": data["coordinates"]}
        for dist_id, data in raw["distributions"].items()
    }
    graph = StageGraph.from_scenario(
        stages,
        raw["transitions"],
        distributions=distributions,
        walkable_polygon=None,
    )
    signs = {eid: data["sign"] for eid, data in raw["exits"].items()}
    spawn = Polygon(next(iter(distributions.values()))["coordinates"]).centroid
    walkable = shapely_wkt.loads((ASSET / "geometry.wkt").read_text().strip())
    vis = VisibilityModel.clear_air(walkable, signs, cell_size_m=CELL_SIZE_M)
    return graph, (spawn.x, spawn.y), vis


def _known_exits(config_name: str) -> set[str]:
    """Exits in a discovery agent's cognitive map at spawn."""
    graph, position, vis_model = _load(config_name)
    cmap = init_cognitive_map(
        "jps-distributions_0", graph, "discovery", vis_model=vis_model, time_s=0.0
    )
    return {n for n in cmap.known_nodes if n.startswith("E_")}


def _reachable_exits(config_name: str, familiarity: str = "discovery") -> set[str]:
    """Exits rank_routes can actually offer, given what the agent knows."""
    graph, position, vis_model = _load(config_name)
    cmap = init_cognitive_map(
        "jps-distributions_0", graph, familiarity, vis_model=vis_model, time_s=0.0
    )
    ranked = rank_routes(
        graph,
        "jps-distributions_0",
        0.0,
        0.0,
        ConstantExtinctionField(0.0),
        None,
        RouteCostConfig(base_speed_m_per_s=1.3, w_smoke=0.0, w_fed=0.0, w_queue=0.0),
        cognitive_map=cmap,
        agent_position=position,
    )
    return {rc.exit_id for rc in ranked}


def _best_exit(config_name: str, familiarity: str = "discovery") -> str:
    graph, position, vis_model = _load(config_name)
    cmap = init_cognitive_map(
        "jps-distributions_0", graph, familiarity, vis_model=vis_model, time_s=0.0
    )
    ranked = rank_routes(
        graph,
        "jps-distributions_0",
        0.0,
        0.0,
        ConstantExtinctionField(0.0),
        None,
        RouteCostConfig(base_speed_m_per_s=1.3, w_smoke=0.0, w_fed=0.0, w_queue=0.0),
        cognitive_map=cmap,
        agent_position=position,
    )
    return ranked[0].exit_id


class TestAssetIsSingleVariable:
    """The experiment is only meaningful if nothing else differs."""

    def test_configs_differ_only_in_the_near_exit_bearing(self):
        visible = json.loads((ASSET / "config_visible.json").read_text())
        hidden = json.loads((ASSET / "config_hidden.json").read_text())

        assert visible["exits"]["E_near"]["sign"]["alpha"] == 0
        assert hidden["exits"]["E_near"]["sign"]["alpha"] == 180

        # Erase the one intended difference; everything else must match.
        visible["exits"]["E_near"]["sign"]["alpha"] = None
        hidden["exits"]["E_near"]["sign"]["alpha"] = None
        assert visible == hidden

    def test_near_exit_is_genuinely_the_closer_one(self):
        """Distance must favour E_near, or the experiment proves nothing."""
        graph, position, _ = _load("config_visible")
        px, py = position
        near = graph.nodes["E_near"]
        far = graph.nodes["E_far"]

        d_near = math.hypot(px - near.centroid_x, py - near.centroid_y)
        d_far = math.hypot(px - far.centroid_x, py - far.centroid_y)
        assert d_near == pytest.approx(9.3, abs=0.5)
        assert d_far == pytest.approx(19.3, abs=0.5)
        assert d_far > 2 * d_near

    def test_both_exits_are_inside_the_visibility_cap(self):
        """A sign beyond max_vis is illegible at every bearing.

        Without this the hidden run would reject BOTH exits, the fallback would
        reinstate the least-cost rejected route, and agents would take E_near
        regardless -- an experiment that proves nothing while appearing to pass.
        """
        raw = json.loads((ASSET / "config_visible.json").read_text(encoding="utf-8"))
        _, position, vis_model = _load("config_visible")
        px, py = position
        for node_id in ("E_near", "E_far"):
            sign = raw["exits"][node_id]["sign"]
            distance = math.hypot(px - sign["x"], py - sign["y"])
            assert distance < MAX_VIS_M, node_id
            # Legible in the reference config, so the hidden run's rejections
            # can only come from the bearing it changes.
            assert vis_model.node_is_visible(0.0, px, py, node_id), node_id


class TestExitChoiceFollowsLegibility:
    def test_legible_near_exit_enters_the_map_and_is_chosen(self):
        assert _known_exits("config_visible") == {"E_near", "E_far"}
        assert _best_exit("config_visible") == "E_near"

    def test_illegible_near_exit_never_enters_the_map(self):
        """The agent walks 10 m further because it does not know the near exit."""
        assert _known_exits("config_hidden") == {"E_far"}
        assert _best_exit("config_hidden") == "E_far"

    def test_the_near_exit_is_absent_not_rejected(self):
        """Membership is the gate: Dijkstra never sees an unknown exit.

        A rejected route would still appear in the ranking, flagged and sorted
        last, and the all-rejected fallback could reinstate it.  Absence is a
        stronger and different claim.
        """
        assert _reachable_exits("config_hidden") == {"E_far"}

    def test_a_fully_familiar_agent_ignores_the_bearing(self):
        """Signs are wayfinding information; they bind only incomplete knowledge.

        Someone who knows the building does not need to read a sign to use a
        door, so the bearing must make no difference at the full tier.
        """
        for config_name in ("config_visible", "config_hidden"):
            assert _best_exit(config_name, familiarity="full") == "E_near", config_name
