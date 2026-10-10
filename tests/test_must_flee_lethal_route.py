"""A FED-lethal route always loses, whatever else refuses it (#128).

Must-flee reads the limits a route breaks (``violation_kinds``), not its
public reason, which names only the last limit: a route over both the FED and
the tau limit reports ``tau ...``. When every route is refused, a route the
agent must flee orders behind every route it need not flee.

Star of ``test_rerouting_golden``: west arm 20 m, east arm 40 m, gate,
1 m/s, current exit west. Hand values: a lethal arm doses 6 FED/min, so 20 s
on the west arm in clear air is FED 2.0 > 1.0. tau is K_ave times the length;
the hub sample is clear air, so K_ave is 20/21 of the arm value on the east
arm and 10/11 on the west arm: east at K 0.2 has tau 40 x 0.2 x 20/21 = 7.62,
over the rival budget 6 x 0.8 = 4.8.
"""

from __future__ import annotations

import pytest
import test_rerouting_golden as golden

from pyfds_evac.core.route_graph import (
    AgentRouteState,
    RerouteConfig,
    RouteCost,
    _anchor_allows,
    _fallback_rival_wins,
    _must_flee_rejection,
    evaluate_and_reroute,
    rank_routes,
)

LETHAL_WEST = golden.ArmFed({"west": 6.0})


def _decide(extinction, fed, **state) -> tuple[str, str | None]:
    """The exit a west-bound agent at the hub takes at 5 s, and why."""
    rs = AgentRouteState(current_exit="west", current_path=["spawn", "west"], **state)
    wait_info = {
        "current_origin": "spawn",
        "current_target_stage": "west",
        "path_choices": {"spawn": [("west", 100.0)]},
        "state": "to_target",
    }
    switch = evaluate_and_reroute(
        7,
        wait_info,
        rs,
        golden._star2(),
        5.0,
        0.0,
        extinction,
        fed,
        RerouteConfig(cost_config=golden._gate()),
    )
    if switch is None:
        return ("stay", None)
    return (switch.new_exit, switch.reason)


def _ranked(extinction, fed, current_exit="west") -> dict[str, RouteCost]:
    ranked = rank_routes(
        golden._star2(),
        "spawn",
        5.0,
        0.0,
        extinction,
        fed,
        golden._gate(),
        current_exit=current_exit,
    )
    return {rc.exit_id: rc for rc in ranked}


def test_lethal_current_in_clear_air_is_left():
    """P1: west lethal, east over tau. Both refused; the agent goes east."""
    smoke = golden.ArmField({"east": 0.2})
    assert _decide(smoke, LETHAL_WEST) == ("east", "fallback")
    routes = _ranked(smoke, LETHAL_WEST)
    assert routes["west"].fed_max_route == pytest.approx(2.0)
    assert routes["west"].violation_kinds == ("fed",)
    assert routes["east"].tau_route == pytest.approx(40 * 0.2 * 20 / 21)
    assert routes["east"].violation_kinds == ("tau",)
    # The lethal route, tau 0, orders behind the one it need not flee.
    assert list(routes) == ["east", "west"]
    assert routes["east"].rejection_reason.startswith("fallback: tau")


def test_lethal_and_smoky_current_is_left():
    """P2: west lethal and over tau, east over tau within the margin.

    East's tau 40 x 0.25 x 20/21 = 9.52 is not 20 % below west's
    20 x 0.5 x 10/11 = 9.09, so the tau rule alone would hold west.
    """
    smoke = golden.ArmField({"west": 0.5, "east": 0.25})
    assert _decide(smoke, LETHAL_WEST) == ("east", "fallback")
    routes = _ranked(smoke, LETHAL_WEST)
    assert routes["west"].tau_route == pytest.approx(20 * 0.5 * 10 / 11)
    assert routes["east"].tau_route == pytest.approx(40 * 0.25 * 20 / 21)
    west = routes["west"]
    assert west.violation_kinds == ("fed", "tau")
    assert west.rejection_reason.startswith("tau")
    assert _must_flee_rejection(west, golden._gate())


def test_return_lockout_yields_to_a_lethal_route():
    """P4b: the agent left east for west 5 s ago; west is now lethal."""
    smoke = golden.ArmField({"west": 0.6, "east": 0.15})
    locked = {"refused_switch_from": "east", "refused_switch_time_s": 0.0}
    assert _decide(smoke, LETHAL_WEST, **locked) == ("east", "fallback")


def test_promoted_route_keeps_its_hazard():
    """Every route lethal: the promoted one keeps its kinds and must be fled."""
    fed = golden.ArmFed({"west": 6.0, "east": 6.0})
    routes = _ranked(golden.ArmField({"east": 0.2}), fed, current_exit=None)
    west = routes["west"]
    assert list(routes) == ["west", "east"]
    assert not west.rejected
    assert west.rejection_reason == "fallback: FED_max 2.000 > 1.000"
    assert west.violation_kinds == ("fed",)
    assert _must_flee_rejection(west, golden._gate())
    assert routes["east"].violation_kinds == ("fed", "tau")


def _refused(exit_id: str, tau: float, kinds: tuple[str, ...], k_ave=0.5):
    return RouteCost(
        exit_id=exit_id,
        path=["spawn", exit_id],
        path_length_m=10.0,
        k_ave_route=k_ave,
        travel_time_s=10.0,
        fed_max_route=0.0,
        composite_cost=10.0,
        segments=[],
        rejected=True,
        rejection_reason="refused",
        tau_route=tau,
        feasible=False,
        rank_cost=10.0,
        violation_kinds=kinds,
    )


def test_fallback_rule_puts_lethal_routes_last():
    """Lethal never displaces non-lethal; two of a kind follow the tau rule."""
    config = golden._gate()
    tau_only = ("tau",)
    lethal = ("fed", "tau")
    # A lethal rival with a far lower tau does not displace the current exit.
    assert not _fallback_rival_wins(
        _refused("east", 1.0, lethal), _refused("west", 30.0, tau_only), config
    )
    # A non-lethal rival with a higher tau displaces a lethal current exit.
    assert _fallback_rival_wins(
        _refused("east", 30.0, tau_only), _refused("west", 1.0, lethal), config
    )
    # Both lethal: the tau rule, 20 % margin.
    assert _fallback_rival_wins(
        _refused("east", 7.9, lethal), _refused("west", 10.0, lethal), config
    )
    assert not _fallback_rival_wins(
        _refused("east", 8.1, lethal), _refused("west", 10.0, lethal), config
    )
    # At the anchor, a non-lethal current exit is not left for a lethal rival.
    cfg = RerouteConfig(cost_config=config)
    assert not _anchor_allows(
        _refused("east", 1.0, lethal), _refused("west", 30.0, tau_only), cfg
    )


@pytest.mark.parametrize(("k_ave", "flee"), [(4.0, True), (2.0, False)])
def test_additive_impassable_smoke_is_fled(k_ave, flee):
    """Additive: a non-visible route is fled only above K_ave 3.0 /m."""
    config = golden._additive()
    rc = _refused("west", 0.0, ("all_segments_non_visible",), k_ave=k_ave)
    assert config.impassable_extinction_threshold == 3.0
    assert _must_flee_rejection(rc, config) is flee
