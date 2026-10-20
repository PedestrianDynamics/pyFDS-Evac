"""Hand-computed boundaries of the routing policy (#816).

The policy decides what the measured route quantities mean: which routes
the gate refuses (optical depth above ``tau_max``), which the FED limit
refuses, when two routes differ by more than the tau deadband, which edge
costs the path search sees, and when a refused route may displace a refused
current exit. Every limit below is tested at the value where the strict
comparison flips, with binary-exact floats, so a ``>`` turned into ``>=``
fails deterministically. Optical depth here is the integral of the
extinction along the route, tau = K_ave * L; routing does not compute a
Jin visibility distance.

Not covered, by design of the model (see tests/AUDIT.md, "Routing: policy"):
the gate has no smoke must-flee (#696, #751) and heat dose takes no part in
route choice.
"""

from __future__ import annotations

import math
from dataclasses import replace

import pytest
from shapely.geometry import Polygon

from pyfds_evac.core.route_graph import (
    EPS_TAU,
    AdditivePolicy,
    GatePolicy,
    RouteCost,
    RouteCostConfig,
    RouteMeasurements,
    SegmentCost,
    StageGraph,
    _fallback_rival_wins,
    evaluate_route,
    taus_tie,
)
from pyfds_evac.core.smoke_speed import ConstantExtinctionField


def _box(cx: float, cy: float, half: float = 1.0) -> Polygon:
    return Polygon(
        [
            (cx - half, cy - half),
            (cx + half, cy - half),
            (cx + half, cy + half),
            (cx - half, cy + half),
        ]
    )


def _corridor(length_m: float) -> StageGraph:
    """D0 (0, 0) -> E0 (length_m, 0), a single edge."""
    return StageGraph.from_scenario(
        {"E0": {"polygon": _box(length_m, 0), "stage_type": "exit"}},
        [{"from": "D0", "to": "E0"}],
        {"D0": {"coordinates": list(_box(0, 0).exterior.coords)}},
    )


class _ConstantFedRate:
    def __init__(self, per_min: float):
        self._rate = per_min

    def sample_fed_rate(self, time_s, x, y):
        del time_s, x, y
        return self._rate


def _route(tau: float, violation_kinds: tuple[str, ...] = ()) -> RouteCost:
    """A route known only by its optical depth and the limits it breaks."""
    return RouteCost(
        exit_id="E",
        path=["D", "E"],
        path_length_m=1.0,
        k_ave_route=0.0,
        travel_time_s=1.0,
        fed_max_route=0.0,
        composite_cost=1.0,
        segments=[],
        rejected=False,
        rejection_reason=None,
        tau_route=tau,
        violation_kinds=violation_kinds,
    )


def _measurements(tau: float = 0.0, fed_max: float = 0.0) -> RouteMeasurements:
    return RouteMeasurements(
        exit_id="E",
        path=["D", "E"],
        segments=[],
        path_length_m=1.0,
        effective_length_m=1.0,
        k_ave_route=tau,
        travel_time_s=1.0,
        fed_max_route=fed_max,
        composite_cost=1.0,
        queue_time_s=0.0,
        k_max_route=tau,
        tau_route=tau,
        k_leg_max=tau,
    )


# ── the tau refusal ──────────────────────────────────────────────────────

TAU_CONFIG = RouteCostConfig(tau_max=2.0)


def test_route_at_tau_max_is_feasible():
    f = GatePolicy().feasibility(_measurements(tau=2.0), TAU_CONFIG)
    assert f.feasible is True
    assert f.rejected is False
    assert f.violations == ()


def test_route_one_ulp_above_tau_max_is_refused_for_tau():
    over = math.nextafter(2.0, math.inf)
    f = GatePolicy().feasibility(_measurements(tau=over), TAU_CONFIG)
    assert f.feasible is False
    assert [v.kind for v in f.violations] == ["tau"]
    assert f.violations[0].measured == over
    assert f.violations[0].limit == 2.0


def test_route_over_both_limits_reports_tau_last():
    m = _measurements(tau=3.0, fed_max=1.5)
    f = GatePolicy().feasibility(m, TAU_CONFIG)
    assert [v.kind for v in f.violations] == ["fed", "tau"]
    assert f.rejection_reason == f.violations[-1].reason


# ── the FED refusal ──────────────────────────────────────────────────────

FED_CONFIG = RouteCostConfig(fed_rejection_threshold=0.75, base_speed_m_per_s=1.0)


def test_fed_at_the_threshold_is_feasible_and_above_it_is_not():
    policy = GatePolicy()
    at = policy.feasibility(_measurements(fed_max=0.75), FED_CONFIG)
    over = policy.feasibility(
        _measurements(fed_max=math.nextafter(0.75, math.inf)), FED_CONFIG
    )
    assert at.feasible is True
    assert at.violations == ()
    assert over.feasible is False
    assert [v.kind for v in over.violations] == ["fed"]
    assert over.violations[0].limit == 0.75


def _fed_route(current_fed: float) -> RouteCost:
    """10 m at 1 m/s in clear air; FED rate 3.0 /min: growth 3 * 10 / 60 = 0.5."""
    return evaluate_route(
        _corridor(10.0),
        ["D0", "E0"],
        0.0,
        current_fed,
        ConstantExtinctionField(0.0),
        _ConstantFedRate(3.0),
        FED_CONFIG,
    )


def test_fed_max_is_the_dose_already_taken_plus_the_growth():
    """0.25 + 0.5 = 0.75 sits on the limit; 0.3125 + 0.5 crosses it."""
    at = _fed_route(0.25)
    assert at.fed_max_route == 0.75
    assert at.violation_kinds == ()
    assert at.feasible is True
    over = _fed_route(0.3125)
    assert over.fed_max_route == 0.8125
    assert over.violation_kinds == ("fed",)
    assert over.feasible is False


def test_the_same_growth_alone_is_feasible():
    """With no dose taken, the route's 0.5 growth is under 0.75."""
    rc = _fed_route(0.0)
    assert rc.fed_max_route == 0.5
    assert rc.feasible is True


# ── the tau deadband ─────────────────────────────────────────────────────

BAND_CONFIG = RouteCostConfig(tau_max=2.0, tau_deadband=0.25)  # margin 0.5


def _band(candidate_tau: float, current_tau: float) -> int:
    return GatePolicy._tau_band(_route(candidate_tau), _route(current_tau), BAND_CONFIG)


def test_candidate_cleaner_by_exactly_the_margin_is_not_clearly_cleaner():
    assert _band(1.0, 1.5) == 0


def test_candidate_cleaner_by_more_than_the_margin_is_clearly_cleaner():
    assert _band(0.9375, 1.5) == 1


def test_candidate_dirtier_by_exactly_the_margin_is_not_clearly_dirtier():
    assert _band(1.5, 1.0) == 0


def test_candidate_dirtier_by_more_than_the_margin_is_clearly_dirtier():
    """The refusal half: leaving an exit and returning cost the same margin."""
    assert _band(1.5625, 1.0) == -1


def test_difference_inside_the_margin_is_a_tie_either_way():
    """With no margin at all, 0.25 would count as cleaner or dirtier."""
    assert _band(1.0, 1.25) == 0
    assert _band(1.25, 1.0) == 0


def test_margin_is_tau_max_times_the_deadband_not_a_ratio():
    """In clear air tau is 0 on both sides: no band, however small the margin."""
    assert _band(0.0, 0.0) == 0
    wide = replace(BAND_CONFIG, tau_max=4.0)
    assert GatePolicy._tau_band(_route(1.0), _route(2.0), wide) == 0
    assert GatePolicy._tau_band(_route(0.5), _route(2.0), wide) == 1


# ── the edge weights the search sees ─────────────────────────────────────


def _segment(length_m: float, k_avg: float, fed_growth: float) -> SegmentCost:
    return SegmentCost(
        source="A",
        target="B",
        length_m=length_m,
        k_avg=k_avg,
        speed_factor=1.0,
        travel_time_s=length_m,
        fed_growth=fed_growth,
        visible=True,
    )


def test_additive_edge_weight_is_length_times_smoke_plus_the_fed_toll():
    """4 * (1 + 2 * 0.25) + 10 * 0.5 = 6 + 5 = 11, current FED not included."""
    config = RouteCostConfig(cost_model="additive", w_smoke=2.0, w_fed=10.0)
    assert AdditivePolicy().edge_weight(_segment(4.0, 0.25, 0.5), config) == 11.0


def test_additive_edge_weight_without_fed_growth_is_the_smoke_term_alone():
    config = RouteCostConfig(cost_model="additive", w_smoke=2.0, w_fed=10.0)
    assert AdditivePolicy().edge_weight(_segment(4.0, 0.25, 0.0), config) == 6.0


def test_gate_edge_weight_has_no_fed_term():
    """K_avg * L plus a 1e-6 per metre floor; dose is a refusal, not a cost."""
    config = RouteCostConfig(cost_model="gate", w_fed=10.0)
    weight = GatePolicy().edge_weight(_segment(4.0, 0.25, 0.5), config)
    assert weight == 0.25 * 4.0 + 1e-6 * 4.0


# ── the all-refused fallback ─────────────────────────────────────────────

FALLBACK = RouteCostConfig(fallback_switch_margin=0.25)  # rival must be < 0.75 x


def test_rival_exactly_at_the_margin_holds():
    assert _fallback_rival_wins(_route(3.0), _route(4.0), FALLBACK) is False


def test_rival_below_the_margin_displaces_the_current_exit():
    assert _fallback_rival_wins(_route(2.9375), _route(4.0), FALLBACK) is True


def test_rival_with_the_same_tau_holds():
    assert _fallback_rival_wins(_route(4.0), _route(4.0), FALLBACK) is False


def test_hold_rule_never_switches_on_tau():
    hold = replace(FALLBACK, fallback_rule="hold")
    assert _fallback_rival_wins(_route(0.0), _route(4.0), hold) is False


def test_tau_rule_switches_where_hold_does_not():
    assert _fallback_rival_wins(_route(0.0), _route(4.0), FALLBACK) is True


def test_must_flee_current_yields_to_a_rival_even_under_hold():
    hold = replace(FALLBACK, fallback_rule="hold")
    lethal = _route(4.0, violation_kinds=("fed",))
    assert _fallback_rival_wins(_route(4.0), lethal, hold) is True


def test_must_flee_rival_never_displaces_a_current_exit_that_need_not_flee():
    lethal = _route(0.0, violation_kinds=("fed",))
    assert _fallback_rival_wins(lethal, _route(4.0), FALLBACK) is False


# ── the tie tolerance ────────────────────────────────────────────────────


def test_taus_tie_includes_eps_tau_exactly_and_excludes_beyond():
    assert EPS_TAU == 1e-9
    assert taus_tie(0.0, EPS_TAU) is True
    assert taus_tie(0.0, math.nextafter(EPS_TAU, math.inf)) is False


@pytest.mark.parametrize("tau", [0.0, 1.0, 6.0])
def test_taus_tie_is_reflexive(tau):
    assert taus_tie(tau, tau) is True
