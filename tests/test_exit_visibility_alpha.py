"""Exit choice must follow sign legibility, not distance alone.

Drives the ``assets/exit_visibility_alpha`` scenario through the real routing
code.  The two configs differ in exactly one value -- the viewing bearing of
the near exit's sign -- so any difference in the chosen exit is attributable to
sign orientation and nothing else.

No FDS output is needed.  ``VisMapClearAir`` below reimplements the rule
fdsvismap applies in clear air, so the test exercises our routing decision
rather than the third-party visibility solver.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest
from shapely.geometry import Polygon

from pyfds_evac.core.route_graph import RouteCostConfig, StageGraph, rank_routes
from pyfds_evac.core.smoke_speed import ConstantExtinctionField

ASSET = Path("assets/exit_visibility_alpha")


# fdsvismap's clear-air visibility distance saturates at this default.
MAX_VIS_M = 30.0


class VisMapClearAir:
    """fdsvismap's legibility rule, in clear air.

    ``FDSVisMap.get_vismap`` decides

        view_angle * visibility * non_concealed >= distance

    where ``view_angle`` is
    ``clip((sin(alpha)*dx + cos(alpha)*dy) / distance, 0, 1)`` for a signed
    waypoint (1.0 when omni-directional), and ``visibility`` is the
    smoke-limited sight distance capped at ``max_vis``.  With no smoke that cap
    binds, so the rule reduces to ``view_angle * max_vis >= distance``.

    Modelling the distance comparison matters, not just the half-plane: a sign
    beyond ``max_vis`` is illegible at every bearing, which would quietly turn
    the experiment into "neither exit is visible".
    """

    def __init__(self, signs: dict[str, dict], max_vis: float = MAX_VIS_M):
        self._signs = signs
        self._max_vis = max_vis

    def view_angle(self, x: float, y: float, node_id: str) -> float:
        sign = self._signs.get(node_id)
        if sign is None or sign.get("alpha") is None:
            return 1.0  # omni-directional or unsigned
        dx, dy = x - float(sign["x"]), y - float(sign["y"])
        distance = math.hypot(dx, dy)
        if distance == 0.0:
            return 1.0
        alpha = math.radians(float(sign["alpha"]))
        projection = math.sin(alpha) * dx + math.cos(alpha) * dy
        return min(1.0, max(0.0, projection / distance))

    def node_is_visible(self, time: float, x: float, y: float, node_id: str) -> bool:
        del time
        sign = self._signs.get(node_id)
        if sign is None:
            return True
        distance = math.hypot(x - float(sign["x"]), y - float(sign["y"]))
        return self.view_angle(x, y, node_id) * self._max_vis >= distance


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
    return graph, (spawn.x, spawn.y), VisMapClearAir(signs)


def _best_exit(config_name: str) -> str:
    graph, position, vis_model = _load(config_name)
    ranked = rank_routes(
        graph,
        "jps-distributions_0",
        0.0,
        0.0,
        ConstantExtinctionField(0.0),
        None,
        RouteCostConfig(base_speed_m_per_s=1.3, w_smoke=0.0, w_fed=0.0, w_queue=0.0),
        vis_model=vis_model,
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
        _, position, vis_model = _load("config_visible")
        px, py = position
        for node_id in ("E_near", "E_far"):
            sign = vis_model._signs[node_id]
            distance = math.hypot(px - sign["x"], py - sign["y"])
            assert distance < MAX_VIS_M, node_id
            assert vis_model.view_angle(px, py, node_id) * MAX_VIS_M >= distance


class TestExitChoiceFollowsLegibility:
    def test_legible_near_exit_is_chosen(self):
        assert _best_exit("config_visible") == "E_near"

    def test_illegible_near_exit_is_abandoned_for_the_far_one(self):
        """The agent walks 10 m further because the near sign faces away."""
        assert _best_exit("config_hidden") == "E_far"

    def test_the_near_route_is_rejected_for_the_stated_reason(self):
        graph, position, vis_model = _load("config_hidden")
        ranked = rank_routes(
            graph,
            "jps-distributions_0",
            0.0,
            0.0,
            ConstantExtinctionField(0.0),
            None,
            RouteCostConfig(base_speed_m_per_s=1.3, w_smoke=0.0, w_fed=0.0),
            vis_model=vis_model,
            agent_position=position,
        )
        near = next(rc for rc in ranked if rc.exit_id == "E_near")
        assert near.rejected
        assert "not_visible" in (near.rejection_reason or "")

    def test_without_a_visibility_model_distance_wins_in_both_configs(self):
        """Control: with legibility unmodelled, the bearing changes nothing."""
        for config_name in ("config_visible", "config_hidden"):
            graph, position, _ = _load(config_name)
            ranked = rank_routes(
                graph,
                "jps-distributions_0",
                0.0,
                0.0,
                ConstantExtinctionField(0.0),
                None,
                RouteCostConfig(base_speed_m_per_s=1.3, w_smoke=0.0, w_fed=0.0),
                agent_position=position,
            )
            assert ranked[0].exit_id == "E_near", config_name
