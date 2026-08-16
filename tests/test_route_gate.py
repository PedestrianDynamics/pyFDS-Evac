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

Smoke decides which exits are available; among the survivors distance decides,
and the visibility band takes no part in the ordering. It used to, and on
l_corridor it -- not the sight gate -- was placing agents on the 58 m route
while both routes were optically clear.
"""

from __future__ import annotations

from dataclasses import replace

from shapely.geometry import box

from pyfds_evac.core.route_graph import (
    AgentRouteState,
    RerouteConfig,
    RouteCost,
    RouteCostConfig,
    StageGraph,
    _adoptable,
    _must_flee_rejection,
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


class TestTauCriterion:
    def test_the_same_smoke_refuses_a_long_route_and_allows_a_short_one(self):
        """The budget is on optical depth, so length is part of the test."""
        graph = build_two_exit_graph()
        ranked = rank_routes(graph, "spawn", 0.0, 0.0, ConstantK(0.2), None, _cfg())
        by_exit = {rc.exit_id: rc for rc in ranked}
        # near is 20 m: tau = 4.0, under the budget of 6. far is 40 m: tau = 8.
        assert by_exit["near"].tau_route < 6.0 <= by_exit["far"].tau_route
        assert not by_exit["near"].rejected
        assert by_exit["far"].rejected
        assert "tau" in (by_exit["far"].rejection_reason or "")

    def test_clear_air_gives_zero_optical_depth(self):
        graph = build_two_exit_graph()
        ranked = rank_routes(graph, "spawn", 0.0, 0.0, ConstantK(0.0), None, _cfg())
        assert all(rc.tau_route == 0.0 for rc in ranked)
        assert not any(rc.rejected for rc in ranked)


class TestSmokeDecidesAvailabilityNotOrder:
    """The gate refuses; it does not also rank.

    This class used to claim a clearer *band* outranked a shorter route, and it
    passed for the wrong reason -- the near exit was refused, so the far one won
    on feasibility and the band never entered it. The band has since been taken
    out of the ordering entirely, and the test still passed, which is what gave
    it away. Assert the mechanism, not the outcome.
    """

    def test_smoke_on_the_near_arm_refuses_it_and_the_far_exit_wins(self):
        graph = build_two_exit_graph()

        class SmokeOnNear:
            def sample_extinction(self, time_s, x, y):
                del time_s, y
                return 0.35 if x < 0 else 0.0

        ranked = rank_routes(graph, "spawn", 0.0, 0.0, SmokeOnNear(), None, _cfg())
        near = next(rc for rc in ranked if rc.exit_id == "near")
        assert near.rejected, "the far exit must win by refusal, not by ranking"
        assert ranked[0].exit_id == "far"

    def test_among_feasible_routes_the_nearer_one_wins_however_smoky(self):
        """Both passable: distance decides, and smoke does not get a second vote."""
        graph = build_two_exit_graph()
        for k in (0.0, 0.05, 0.1):
            ranked = rank_routes(graph, "spawn", 0.0, 0.0, ConstantK(k), None, _cfg())
            feasible = [rc for rc in ranked if not rc.rejected]
            if len(feasible) < 2:
                continue
            assert ranked[0].exit_id == "near", k


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
        assert close_up.tau_route < far_off.tau_route


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

    def test_a_hair_of_cleanliness_does_not_buy_a_long_detour(self):
        """Measured on world100: 2.0 m of sight beat 1.8 m over 29 m of walking.

        Both routes are refused and neither is usable, so the tiny difference in
        extinction is noise. Optical depth carries the distance with it, so the
        least-bad walk is the one with least smoke to walk *through*.
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


class LethalOnTheNearArm:
    """A dose that incapacitates on the west side, nothing on the east."""

    def __init__(self, rate_per_min: float = 8.0):
        self._rate = rate_per_min

    def sample_fed_rate(self, time_s, x, y):
        del time_s, y
        return self._rate if x < 0 else 0.0


class TestDoseVetoesAnExit:
    """Dose gates availability; it does not rank.

    This is FDS+Evac's other branch, the one selected when FED_DOOR_CRIT is
    positive (evac.f90, Change_Target_Door): score a door by the dose already
    taken plus the dose predicted over the walk to it, and strike it out when
    that reaches incapacitation. Here it only strikes out -- the surviving
    routes are still ordered by time, not by dose.
    """

    def test_a_lethal_route_is_refused_and_the_long_clean_one_wins(self):
        graph = build_two_exit_graph()
        ranked = rank_routes(
            graph,
            "spawn",
            0.0,
            0.0,
            ConstantK(0.0),  # clear air: the sight gate cannot be the cause
            LethalOnTheNearArm(),
            _cfg(),
        )
        by_exit = {rc.exit_id: rc for rc in ranked}
        assert by_exit["near"].fed_max_route > 1.0
        assert by_exit["near"].rejected
        assert "FED" in (by_exit["near"].rejection_reason or "")
        assert not by_exit["far"].rejected
        # The near exit is half the distance and still loses: dose vetoed it.
        assert ranked[0].exit_id == "far"

    def test_dose_below_the_threshold_leaves_the_nearer_exit_alone(self):
        graph = build_two_exit_graph()
        ranked = rank_routes(
            graph,
            "spawn",
            0.0,
            0.0,
            ConstantK(0.0),
            LethalOnTheNearArm(rate_per_min=0.05),
            _cfg(),
        )
        by_exit = {rc.exit_id: rc for rc in ranked}
        assert by_exit["near"].fed_max_route < 1.0
        assert not by_exit["near"].rejected
        assert ranked[0].exit_id == "near"

    def test_a_dose_rejection_lets_the_agent_flee_past_the_anchor(self):
        """Hysteresis must not pin an agent to an exit that will kill it."""
        graph = build_two_exit_graph()
        ranked = rank_routes(
            graph,
            "spawn",
            0.0,
            0.0,
            ConstantK(0.0),
            LethalOnTheNearArm(),
            _cfg(),
            current_exit="near",
        )
        near = next(rc for rc in ranked if rc.exit_id == "near")
        assert _must_flee_rejection(near, _cfg())


class TestClearAirIsUntouched:
    """At small but nonzero K the gate must still reduce to nearest-exit.

    Tested at K = 1e-4 rather than at 0: a check at exactly zero cannot fail,
    and that hole hid the visibility-band defect twice. The promotion scan added
    with `_anchor_allows` is the newest thing that could break this -- it walks
    the ranked list looking for a route the anchor would accept, and in clear
    air it must find nothing to promote, because every bypass is dead (no route
    is clean, every band saturates) and a farther exit cannot beat the anchor on
    time.
    """

    def test_no_route_is_promoted_over_the_current_exit(self):
        graph = build_two_exit_graph()
        state = AgentRouteState(current_exit="near", current_path=["spawn", "near"])
        ranked = rank_routes(
            graph, "spawn", 0.0, 0.0, ConstantK(1e-4), None, _cfg(), current_exit="near"
        )
        config = RerouteConfig(cost_config=_cfg())
        assert ranked[0].exit_id == "near", "clear air must rank the nearer exit first"
        far = next(rc for rc in ranked if rc.exit_id == "far")
        assert not _adoptable(far, ranked, state, config), (
            "the farther exit must not be adoptable in clear air"
        )

    def test_the_tier_never_discriminates_in_clear_air(self):
        graph = build_two_exit_graph()
        for k in (0.0, 1e-4, 1e-3):
            ranked = rank_routes(graph, "spawn", 0.0, 0.0, ConstantK(k), None, _cfg())
            assert len({rc.clean for rc in ranked}) == 1, k
            assert all(rc.tau_route <= k * 45.0 for rc in ranked), k
            assert ranked[0].exit_id == "near", k
