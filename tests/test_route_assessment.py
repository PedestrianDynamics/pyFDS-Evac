"""The internal route records and their projection onto ``RouteCost`` (#187).

The records split what ``evaluate_route`` returns into what was measured,
which limits the route violates, and how it ranks. ``RouteCost`` stays the
public result, so the projection back onto it must be exact.
"""

from __future__ import annotations

from dataclasses import fields

import test_rerouting_golden as golden

from pyfds_evac.core.route_graph import (
    RouteAssessment,
    RouteCost,
    RouteFeasibility,
    RouteMeasurements,
    RouteViolation,
    SegmentCost,
    _must_flee_rejection,
    _project_route_cost,
    evaluate_route,
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


def test_dual_violation_reports_tau_reason():
    """A route over both limits reports tau, and loses the must-flee bypass.

    #128: the tau test overwrites the FED reason. Stage 1 keeps that; the
    violations list records both, FED first, and the public reason is the
    last one.
    """
    config = golden._gate()
    rc = evaluate_route(
        golden._star2(),
        ["spawn", "west"],
        0.0,
        0.2,
        golden.ArmField({"west": 0.5}),
        golden.ArmFed({"west": 4.0}),
        config,
    )
    assert rc.fed_max_route > config.fed_rejection_threshold
    assert rc.tau_route > config.tau_max
    assert rc.rejection_reason.startswith("tau")
    assert not rc.feasible
    assert not _must_flee_rejection(rc, config)
    violations = (
        RouteViolation(
            kind="fed",
            reason=f"FED_max {rc.fed_max_route:.3f} > "
            f"{config.fed_rejection_threshold:.3f}",
            measured=rc.fed_max_route,
            limit=config.fed_rejection_threshold,
        ),
        RouteViolation(
            kind="tau",
            reason=rc.rejection_reason,
            measured=rc.tau_route,
            limit=config.tau_max,
        ),
    )
    assessment = _assessment_of(rc, violations)
    assert assessment.feasibility.violations[-1].reason == rc.rejection_reason
    assert _project_route_cost(assessment) == rc


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
