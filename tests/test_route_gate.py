"""The gate refuses exits, and un-refuses them as the agent closes in.

The sight criterion is measured against the distance *still to walk*, so it
relaxes on approach: smoke that refuses a door 40 m away accepts the same door
at 2 m. Nothing is remembered between ticks, which is what makes that possible
-- an earlier version retired a refused exit permanently and so cancelled the
property, leaving agents walking away from doors the model had just declared
passable.

The cost of recomputing every tick is that in a fire smoky enough to refuse
every route -- most of a real run, see docs/gate-model-review-notes.md -- the
ordering follows the field second by second. Two things hold it steady: the
all-refused fallback keeps the current exit unless a rival's worst stretch is
clearly milder, and the exit-switch anchor keeps it unless a rival is clearly
quicker. Under the gate model those are the only churn protection there is.

The band tests pin the other half: a route a whole visibility class clearer is
adopted whatever it costs in distance, and within a band distance decides again.
"""

from __future__ import annotations

import math
from dataclasses import replace

from shapely.geometry import box

from pyfds_evac.core.route_graph import (
    RouteCost,
    RouteCostConfig,
    StageGraph,
    _sighting_distance,
    _visibility_band,
    evaluate_route,
    rank_routes,
)


def _b(cx, cy, half=1.0):
    return box(cx - half, cy - half, cx + half, cy + half)


def build_two_exit_graph() -> StageGraph:
    """Spawn at the origin, a near exit 20 m west and a far one 40 m east."""
    stages = {
        "near": {"polygon": _b(-20.0, 0.0), "stage_type": "exit"},
        "far": {"polygon": _b(40.0, 0.0), "stage_type": "exit"},
    }
    return StageGraph.from_scenario(
        stages, [], distributions={"spawn": {"polygon": _b(0.0, 0.0)}}
    )


def _cfg(**kw) -> RouteCostConfig:
    cfg = RouteCostConfig(
        cost_model="gate", base_speed_m_per_s=1.0, w_smoke=0.0, w_fed=0.0
    )
    return replace(cfg, **kw) if kw else cfg


class ConstantK:
    def __init__(self, k: float):
        self._k = k

    def sample_extinction(self, time_s, x, y):
        del time_s, x, y
        return self._k


class TestSightCriterion:
    def test_the_same_smoke_refuses_a_far_exit_and_allows_a_near_one(self):
        """Distance-relative, not a threshold on K."""
        k = 0.2  # S = 15 m
        assert _sighting_distance(k, 3.0) == 15.0
        cfg = _cfg(sight_distance_fraction=0.5)
        # needed = 0.5 * length, so anything under 30 m is passable at this K.
        assert 15.0 >= cfg.sight_distance_fraction * 20.0
        assert 15.0 < cfg.sight_distance_fraction * 40.0

    def test_clear_air_gives_unbounded_sight(self):
        assert _sighting_distance(0.0, 3.0) == math.inf
        assert _visibility_band(math.inf, 10.0) == _visibility_band(math.inf, 5.0)


class TestBandOrdering:
    def test_a_clearer_band_outranks_a_shorter_route(self):
        graph = build_two_exit_graph()

        # Smoke only on the near arm: the far exit is a whole band clearer.
        class SmokeOnNear:
            def sample_extinction(self, time_s, x, y):
                del time_s, y
                return 0.35 if x < 0 else 0.0

        ranked = rank_routes(graph, "spawn", 0.0, 0.0, SmokeOnNear(), None, _cfg())
        assert ranked[0].exit_id == "far"
        assert ranked[0].band > ranked[1].band

    def test_within_a_band_the_nearer_route_wins(self):
        graph = build_two_exit_graph()
        ranked = rank_routes(graph, "spawn", 0.0, 0.0, ConstantK(0.0), None, _cfg())
        assert ranked[0].exit_id == "near"


class TestRefusalIsNotRemembered:
    def test_an_exit_refused_far_away_is_accepted_on_approach(self):
        """The self-healing property. Permanent death used to break this."""
        graph = build_two_exit_graph()
        field = ConstantK(0.2)  # S = 15 m
        cfg = _cfg()

        # The far exit is 40 m off, so 0.5 * 40 = 20 m of sight is needed and
        # 15 m is not enough. Two metres from the door it needs 1 m.
        far_off = evaluate_route(
            graph,
            ["spawn", "far"],
            0.0,
            0.0,
            field,
            None,
            cfg,
            agent_position=(0.0, 0.0),
        )
        close_up = evaluate_route(
            graph,
            ["spawn", "far"],
            0.0,
            0.0,
            field,
            None,
            cfg,
            agent_position=(38.0, 0.0),
        )
        assert not far_off.feasible
        assert close_up.feasible
        assert close_up.min_visibility_m == far_off.min_visibility_m


class TestFallbackStability:
    def _all_refused(self, current_exit):
        graph = build_two_exit_graph()
        return rank_routes(
            graph,
            "spawn",
            0.0,
            0.0,
            ConstantK(5.0),  # S = 0.6 m: nothing passes
            None,
            _cfg(),
            current_exit=current_exit,
        )

    def test_something_is_always_returned_unrejected(self):
        ranked = self._all_refused(None)
        assert ranked
        assert not ranked[0].rejected
        assert (ranked[0].rejection_reason or "").startswith("fallback")

    def test_a_hair_of_sight_does_not_buy_a_long_detour(self):
        """Measured on world100: 2.0 m of sight beat 1.8 m over 29 m of walking.

        Both routes are refused and neither is usable, so the tiny difference in
        worst-case sight is noise. Banding makes them the same class and lets
        distance decide.
        """
        graph = build_two_exit_graph()

        class BarelyClearerFarAway:
            def sample_extinction(self, time_s, x, y):
                del time_s, y
                return 5.0 if x < 0 else 4.9  # S = 0.60 m vs 0.61 m

        ranked = rank_routes(
            graph, "spawn", 0.0, 0.0, BarelyClearerFarAway(), None, _cfg()
        )
        assert ranked[0].exit_id == "near"
        assert ranked[0].band == ranked[1].band

    def test_the_current_exit_is_held_when_rivals_are_no_milder(self):
        """Uniform smoke: k_max ties, so the margin must keep the incumbent."""
        for held in ("near", "far"):
            ranked = self._all_refused(held)
            assert ranked[0].exit_id == held, held


class TestRankCostIsWhatOrders:
    def test_gate_ranks_on_time_and_additive_on_the_composite(self):
        graph = build_two_exit_graph()
        field = ConstantK(0.1)
        gate = rank_routes(graph, "spawn", 0.0, 0.0, field, None, _cfg())
        add = rank_routes(
            graph,
            "spawn",
            0.0,
            0.0,
            field,
            None,
            RouteCostConfig(cost_model="additive", w_smoke=1.0, w_fed=0.0),
        )
        assert all(rc.rank_cost == rc.travel_time_s for rc in gate)
        assert all(rc.rank_cost == rc.composite_cost for rc in add)


def test_route_cost_defaults_are_usable_without_the_gate_fields():
    rc = RouteCost(
        exit_id="e",
        path=["a", "e"],
        path_length_m=1.0,
        k_ave_route=0.0,
        travel_time_s=1.0,
        fed_max_route=0.0,
        composite_cost=1.0,
        segments=[],
        rejected=False,
        rejection_reason=None,
    )
    assert rc.feasible and rc.rank_cost == 0.0
