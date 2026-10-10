"""The internal route records and their projection onto ``RouteCost`` (#187).

The records split what ``evaluate_route`` returns into what was measured,
which limits the route violates, and how it ranks. ``RouteCost`` stays the
public result, so the projection back onto it must be exact.
"""

from __future__ import annotations

from dataclasses import fields, replace

import pytest
import test_rerouting_golden as golden

from pyfds_evac.core.route_graph import (
    AdditivePolicy,
    GatePolicy,
    RouteAssessment,
    RouteCost,
    RouteCostConfig,
    RouteFeasibility,
    RouteMeasurements,
    RouteViolation,
    SegmentCost,
    _assess_measurements,
    _fed_limit,
    _measure_route,
    _must_flee_rejection,
    _project_route_cost,
    evaluate_route,
    policy_for,
    rank_routes,
)


def _assessment_of(
    rc: RouteCost, violations: tuple[RouteViolation, ...] = ()
) -> RouteAssessment:
    """Split a public result into the records it is projected from."""
    return RouteAssessment(
        measurements=RouteMeasurements(
            exit_id=rc.exit_id,
            path=rc.path,
            segments=rc.segments,
            path_length_m=rc.path_length_m,
            effective_length_m=rc.path_length_m,
            k_ave_route=rc.k_ave_route,
            travel_time_s=rc.travel_time_s,
            fed_max_route=rc.fed_max_route,
            composite_cost=rc.composite_cost,
            queue_time_s=rc.queue_time_s,
            k_max_route=rc.k_max_route,
            tau_route=rc.tau_route,
            k_leg_max=rc.k_leg_max,
        ),
        feasibility=RouteFeasibility(
            feasible=rc.feasible,
            rejected=rc.rejected,
            rejection_reason=rc.rejection_reason,
            violations=violations,
        ),
        rank_cost=rc.rank_cost,
        clean=rc.clean,
    )


def test_projection_carries_every_field():
    segment = SegmentCost("a", "b", 1.0, 0.1, 0.9, 1.1, 0.01, True)
    path = ["a", "b"]
    segments = [segment]
    assessment = RouteAssessment(
        measurements=RouteMeasurements(
            exit_id="b",
            path=path,
            segments=segments,
            path_length_m=11.0,
            effective_length_m=12.0,
            k_ave_route=13.0,
            travel_time_s=14.0,
            fed_max_route=15.0,
            composite_cost=16.0,
            queue_time_s=17.0,
            k_max_route=18.0,
            tau_route=19.0,
            k_leg_max=20.0,
            clear_travel_time_s=22.0,
        ),
        feasibility=RouteFeasibility(
            feasible=False,
            rejected=True,
            rejection_reason="why",
        ),
        rank_cost=21.0,
        clean=False,
    )
    rc = _project_route_cost(assessment)
    expected = {
        "exit_id": "b",
        "path": path,
        "path_length_m": 11.0,
        "k_ave_route": 13.0,
        "travel_time_s": 14.0,
        "fed_max_route": 15.0,
        "composite_cost": 16.0,
        "segments": segments,
        "rejected": True,
        "rejection_reason": "why",
        "queue_time_s": 17.0,
        "k_max_route": 18.0,
        "tau_route": 19.0,
        "feasible": False,
        "rank_cost": 21.0,
        "k_leg_max": 20.0,
        "clean": False,
        "clear_travel_time_s": 22.0,
    }
    assert {f.name for f in fields(RouteCost)} == expected.keys()
    assert {f.name: getattr(rc, f.name) for f in fields(RouteCost)} == expected
    # The path is shared, not copied: route state keeps the route's own list.
    assert rc.path is path
    assert rc.segments is segments


def test_projection_round_trips_a_ranked_route():
    case = golden.RANK_CASES["gate_three_exits"]
    ranked = rank_routes(
        case.graph(),
        case.source,
        case.time_s,
        case.current_fed,
        case.extinction,
        case.fed,
        case.config,
        current_exit=case.current_exit,
    )
    assert ranked
    for rc in ranked:
        assert _project_route_cost(_assessment_of(rc)) == rc


_DUAL_SMOKE = golden.ArmField({"west": 0.5})
_DUAL_DOSE = golden.ArmFed({"west": 4.0})


def _assess_west(config, current_exit=None):
    graph = golden._star2()
    path = ["spawn", "west"]
    m = _measure_route(graph, path, 0.0, 0.2, _DUAL_SMOKE, _DUAL_DOSE, config)
    rc = evaluate_route(
        graph,
        path,
        0.0,
        0.2,
        _DUAL_SMOKE,
        _DUAL_DOSE,
        config,
        current_exit=current_exit,
    )
    return m, _assess_measurements(m, config, current_exit), rc


def test_dual_violation_reports_tau_reason():
    """A route over both limits reports tau, and loses the must-flee bypass.

    #128: the tau test overwrites the FED reason. Stage 1 keeps that; the
    violations record both, FED first, and the public reason is the last one.
    """
    config = golden._gate()
    m, assessment, rc = _assess_west(config)
    violations = assessment.feasibility.violations
    assert [v.kind for v in violations] == ["fed", "tau"]
    fed, tau = violations
    assert (fed.measured, fed.limit) == (m.fed_max_route, 1.0)
    assert (tau.measured, tau.limit) == (m.tau_route, config.tau_max)
    assert fed.reason.startswith("FED_max")
    assert tau.reason == rc.rejection_reason
    assert rc.rejection_reason.startswith("tau")
    assert not rc.feasible and rc.rejected
    assert not _must_flee_rejection(rc, config)
    assert _project_route_cost(assessment) == rc


def test_additive_records_the_dose_only():
    """The additive model has no sight gate: the same route breaks FED alone."""
    config = golden._additive()
    _, assessment, rc = _assess_west(config)
    violations = assessment.feasibility.violations
    assert [v.kind for v in violations] == ["fed"]
    assert violations[0].reason == rc.rejection_reason
    assert _must_flee_rejection(rc, config)
    assert _project_route_cost(assessment) == rc


def test_rival_limits_carry_their_margins():
    """A rival exit is held to the margin-adjusted limits, the current one not."""
    config = golden._gate()
    for current_exit, fed_limit, tau_limit in (
        (None, 1.0, config.tau_max),
        ("west", 1.0, config.tau_max),
        (
            "east",
            config.fed_rejection_threshold * config.fed_return_margin,
            config.tau_max * config.tau_return_margin,
        ),
    ):
        _, assessment, rc = _assess_west(config, current_exit)
        fed, tau = assessment.feasibility.violations
        assert fed.limit == fed_limit == _fed_limit(config, "west", current_exit)
        assert tau.limit == tau_limit
        assert tau_limit == GatePolicy._tau_budget(config, "west", current_exit)
        assert _project_route_cost(assessment) == rc


def test_policy_for_picks_the_named_policy():
    assert isinstance(policy_for(golden._gate()), GatePolicy)
    assert isinstance(policy_for(golden._additive()), AdditivePolicy)


_BAD_COST_MODELS = ("Gate", "gates", "", " gate", None, 1)


@pytest.mark.parametrize("model", _BAD_COST_MODELS)
def test_unknown_cost_model_is_rejected(model):
    """An unknown cost_model raises instead of running the additive model (#305)."""
    with pytest.raises(ValueError, match=r"Unknown routing cost_model"):
        RouteCostConfig(cost_model=model)
    with pytest.raises(ValueError, match=r"Unknown routing cost_model"):
        RouteCostConfig.from_routing_params({"cost_model": model})
    with pytest.raises(ValueError, match=r"Unknown routing cost_model"):
        replace(golden._gate(), cost_model=model)


@pytest.mark.parametrize("model", ("gate", "additive"))
def test_known_cost_model_is_accepted(model):
    assert RouteCostConfig(cost_model=model).cost_model == model
    assert RouteCostConfig.from_routing_params({"cost_model": model}) == (
        RouteCostConfig(cost_model=model)
    )


def test_absent_cost_model_means_gate():
    assert RouteCostConfig.from_routing_params({}).cost_model == "gate"
    assert RouteCostConfig.from_routing_params(None).cost_model == "gate"


def test_policy_for_rejects_a_bypassed_cost_model():
    """No dispatch maps an unknown name to a policy, even past validation."""
    config = golden._gate()
    object.__setattr__(config, "cost_model", "Gate")
    with pytest.raises(ValueError, match=r"Unknown routing cost_model 'Gate'"):
        policy_for(config)


def test_kvis_rejection_keeps_route_feasible():
    """The additive K_vis screen sets ``rejected`` and leaves ``feasible``."""
    case = golden.RANK_CASES["additive_nonvisible"]
    ranked = rank_routes(
        case.graph(),
        case.source,
        case.time_s,
        case.current_fed,
        case.extinction,
        case.fed,
        case.config,
    )
    west = next(rc for rc in ranked if rc.exit_id == "west")
    assert west.rejected
    assert west.feasible
    assert west.rejection_reason == "all segments non-visible"
    violation = RouteViolation(
        kind="all_segments_non_visible",
        reason=west.rejection_reason,
        measured=west.k_ave_route,
        limit=case.config.visibility_extinction_threshold,
    )
    assessment = _assessment_of(west, (violation,))
    assert assessment.feasibility.feasible and assessment.feasibility.rejected
    assert _project_route_cost(assessment) == west


def test_clean_limit_divides_by_the_margin():
    """The current exit's clean limit is threshold / margin, computed as such.

    0.3 / 0.7 and 0.3 * (1 / 0.7) differ in the last bit, and a route whose
    smokiest leg sits exactly on the quotient is clean under the first and not
    under the second, so this pins the operation, not just the value.
    """
    k_leg_max = 0.4285714285714286
    assert 0.3 / 0.7 == k_leg_max != 0.3 * (1 / 0.7)
    m = RouteMeasurements(
        exit_id="west",
        path=["spawn", "west"],
        segments=[],
        path_length_m=10.0,
        effective_length_m=10.0,
        k_ave_route=0.1,
        travel_time_s=10.0,
        fed_max_route=0.0,
        composite_cost=10.0,
        queue_time_s=0.0,
        k_max_route=k_leg_max,
        tau_route=1.0,
        k_leg_max=k_leg_max,
    )
    config = golden._gate(clean_extinction_threshold=0.3, clean_exit_margin=0.7)
    assert _assess_measurements(m, config, "west").clean
    assert not _assess_measurements(m, config, "east").clean
