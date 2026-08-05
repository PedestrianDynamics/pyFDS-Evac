"""Smoke reprices routes, and the exit choice follows the price.

Drives the existing ``assets/t_junction`` asset -- the scenario already built
for this mechanism -- through the real cost function at a range of ``w_smoke``.

The T puts exit B 10 m from the junction and exit A 20 m, so **distance alone
always prefers B**.  Putting smoke on B's arm and raising ``w_smoke`` must
eventually flip the choice to A, and the flip must come from the smoke, not
from anything else.  Three controls pin that down:

* the clear route's cost never moves across the sweep;
* the smoky route's cost rises monotonically;
* *uniform* smoke never flips the choice at any weight, because it scales both
  routes together and B is simply shorter.

The last one is the important one.  Without it, "smoke changed the exit" could
just mean "any large cost term changes the exit".

Familiarity is deliberately not involved: no cognitive map is passed, so the
whole graph is visible and knowledge cannot confound the cost question.  The
asset's own config uses the discovery tier, which is exercised elsewhere.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from shapely.geometry import Polygon

from pyfds_evac.core.route_graph import RouteCostConfig, StageGraph, rank_routes

ASSET = Path("assets/t_junction")

NEAR_EXIT = "exit_B_right"  # 10 m from the junction
FAR_EXIT = "exit_A_left"  # 20 m from the junction
SPAWN = "jps-distributions_0"


class SmokeOnTheNearArm:
    """Heavy extinction on the right arm of the T, clear everywhere else."""

    def sample_extinction(self, time_s, x, y):
        del time_s, y
        return 4.0 if x > 23.0 else 0.0


class UniformSmoke:
    """The same extinction everywhere, including both arms."""

    def __init__(self, k: float = 4.0):
        self._k = k

    def sample_extinction(self, time_s, x, y):
        del time_s, x, y
        return self._k


def _graph() -> StageGraph:
    raw = json.loads((ASSET / "config.json").read_text(encoding="utf-8"))
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
    distributions = {
        key: {"coordinates": value["coordinates"]}
        for key, value in raw["distributions"].items()
    }
    return StageGraph.from_scenario(
        stages, raw["transitions"], distributions=distributions
    )


def _costs(graph, field, w_smoke: float) -> dict[str, float]:
    ranked = rank_routes(
        graph,
        SPAWN,
        0.0,
        0.0,
        field,
        None,
        RouteCostConfig(
            base_speed_m_per_s=1.3, w_smoke=w_smoke, w_fed=0.0, w_queue=0.0
        ),
    )
    return {rc.exit_id: rc.composite_cost for rc in ranked}


def _best(graph, field, w_smoke: float) -> str:
    ranked = rank_routes(
        graph,
        SPAWN,
        0.0,
        0.0,
        field,
        None,
        RouteCostConfig(
            base_speed_m_per_s=1.3, w_smoke=w_smoke, w_fed=0.0, w_queue=0.0
        ),
    )
    return ranked[0].exit_id


class TestGeometryPremise:
    """Distance must favour the near exit, or the flip proves nothing."""

    def test_near_exit_is_cheaper_with_no_smoke_weighting(self):
        costs = _costs(_graph(), SmokeOnTheNearArm(), w_smoke=0.0)
        assert costs[NEAR_EXIT] < costs[FAR_EXIT]

    def test_the_asset_still_has_the_two_exits_this_test_assumes(self):
        graph = _graph()
        assert {NEAR_EXIT, FAR_EXIT} <= set(graph.nodes)


class TestSmokeShiftsTheExitChoice:
    def test_no_smoke_weight_gives_the_nearest_exit(self):
        assert _best(_graph(), SmokeOnTheNearArm(), w_smoke=0.0) == NEAR_EXIT

    def test_enough_smoke_weight_flips_to_the_clear_exit(self):
        assert _best(_graph(), SmokeOnTheNearArm(), w_smoke=1.0) == FAR_EXIT

    def test_the_flip_happens_once_and_stays(self):
        """Monotone: no oscillation back to the smoky exit as the weight rises."""
        graph = _graph()
        field = SmokeOnTheNearArm()
        chosen = [_best(graph, field, w) for w in (0.0, 0.5, 1.0, 2.0, 5.0, 10.0)]
        assert chosen[0] == NEAR_EXIT
        assert all(exit_id == FAR_EXIT for exit_id in chosen[1:])

    def test_the_clear_route_is_never_repriced(self):
        """Control: smoke only charges the route that passes through it."""
        graph = _graph()
        field = SmokeOnTheNearArm()
        baseline = _costs(graph, field, 0.0)[FAR_EXIT]
        for w in (0.5, 1.0, 5.0, 10.0):
            assert _costs(graph, field, w)[FAR_EXIT] == pytest.approx(
                baseline, rel=1e-9
            )

    def test_the_smoky_route_gets_monotonically_dearer(self):
        graph = _graph()
        field = SmokeOnTheNearArm()
        costs = [_costs(graph, field, w)[NEAR_EXIT] for w in (0.0, 0.5, 1.0, 2.0, 5.0)]
        assert all(b > a for a, b in zip(costs, costs[1:]))


class TestUniformSmokeDoesNotFlipIt:
    """The strong control: the flip needs *asymmetric* smoke, not merely smoke.

    Uniform extinction scales both routes by the same factor, so the shorter
    one stays cheaper at every weight. Without this, "smoke changed the exit"
    would be indistinguishable from "a large cost term changed the exit".
    """

    def test_the_near_exit_wins_at_every_weight(self):
        graph = _graph()
        field = UniformSmoke(4.0)
        for w in (0.0, 0.5, 1.0, 5.0, 10.0):
            assert _best(graph, field, w) == NEAR_EXIT, f"w_smoke={w}"

    def test_both_routes_get_dearer_together(self):
        graph = _graph()
        field = UniformSmoke(4.0)
        cheap = _costs(graph, field, 0.0)
        dear = _costs(graph, field, 5.0)
        assert dear[NEAR_EXIT] > cheap[NEAR_EXIT]
        assert dear[FAR_EXIT] > cheap[FAR_EXIT]
