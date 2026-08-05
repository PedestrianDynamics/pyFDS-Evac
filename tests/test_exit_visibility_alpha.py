"""Exit choice must follow sign legibility, not distance alone.

Drives the ``assets/exit_visibility_alpha`` scenario through the real routing
code.  The two configs differ in exactly one value -- the viewing bearing of
the near exit's sign -- so any difference in the chosen exit is attributable to
sign orientation and nothing else.

No FDS output is needed.  ``VisMapHalfPlane`` below reimplements the rule
fdsvismap applies for a waypoint with a bearing, so the test exercises our
routing decision rather than the third-party visibility solver.
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


class VisMapHalfPlane:
    """fdsvismap's viewing-angle rule, in clear air.

    ``FDSVisMap._get_view_angle_array`` computes
    ``clip((sin(alpha)*(x - wp.x) + cos(alpha)*(y - wp.y)) / distance, 0, 1)``
    for a waypoint with a bearing, so the sign is legible only from the
    half-plane it faces.  With no smoke that factor alone decides legibility.
    """

    def __init__(self, signs: dict[str, dict]):
        self._signs = signs

    def node_is_visible(self, time: float, x: float, y: float, node_id: str) -> bool:
        del time
        sign = self._signs.get(node_id)
        if sign is None or sign.get("alpha") is None:
            return True  # omni-directional or unsigned: always legible
        alpha = math.radians(float(sign["alpha"]))
        dx, dy = x - float(sign["x"]), y - float(sign["y"])
        return math.sin(alpha) * dx + math.cos(alpha) * dy > 0.0


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
    return graph, (spawn.x, spawn.y), VisMapHalfPlane(signs)


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
        assert d_far == pytest.approx(33.3, abs=0.5)
        assert d_far > 3 * d_near


class TestExitChoiceFollowsLegibility:
    def test_legible_near_exit_is_chosen(self):
        assert _best_exit("config_visible") == "E_near"

    def test_illegible_near_exit_is_abandoned_for_the_far_one(self):
        """The agent walks 24 m further because the near sign faces away."""
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
