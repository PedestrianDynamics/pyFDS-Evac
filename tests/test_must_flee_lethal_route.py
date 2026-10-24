"""A FED-lethal route always loses, whatever else refuses it (#128).

Must-flee reads the limits a route breaks (``violation_kinds``), not its
public reason, which names only the last limit: a route over both the FED and
the tau limit reports ``tau ...``. When every route is refused, a route the
agent must flee orders behind every route it need not flee.

Star of ``test_rerouting_golden``: west arm 20 m, east arm 40 m, gate,
1 m/s, current exit west. Hand values: a lethal arm doses 6 FED/min, read at
the 11 points of the 20 m west leg (the hub point is clear air, 10 of 11 are
on the arm), so the mean rate is 6 x 10/11 and 20 s on the west arm in clear
air is FED 6 x 10/11 x 20/60 = 20/11 = 1.82 > 1.0. tau is K_ave times the length;
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
    RouteCostConfig,
    _anchor_allows,
    _fallback_rival_wins,
    _must_flee_rejection,
    check_removed_routing_keys,
    evaluate_and_reroute,
    policy_for,
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
    assert routes["west"].fed_max_route == pytest.approx(20 / 11)
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


def test_promoted_route_keeps_its_hazard():
    """Every route lethal: the promoted one keeps its kinds and must be fled."""
    fed = golden.ArmFed({"west": 6.0, "east": 6.0})
    routes = _ranked(golden.ArmField({"east": 0.2}), fed, current_exit=None)
    west = routes["west"]
    assert list(routes) == ["west", "east"]
    assert west.rejected
    assert west.rejection_reason == "fallback: FED_max 1.818 > 1.000"
    assert west.violation_kinds == ("fed",)
    assert _must_flee_rejection(west, golden._gate())
    assert routes["east"].violation_kinds == ("fed", "tau")


def _decide_additive(current, extinction, fed=None) -> tuple[str, str | None]:
    """The exit an additive agent at the hub takes at 5 s, and why.

    w_smoke 0, so the composite is length: west 20, east 40.
    """
    rs = AgentRouteState(current_exit=current, current_path=["spawn", current])
    wait_info = {
        "current_origin": "spawn",
        "current_target_stage": current,
        "path_choices": {"spawn": [(current, 100.0)]},
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
        RerouteConfig(cost_config=golden._additive(w_smoke=0.0)),
    )
    return ("stay", None) if switch is None else (switch.new_exit, switch.reason)


def test_additive_dense_smoke_does_not_bypass_the_anchor():
    """Additive: non-visible smoke at K_ave 3.18 is decided by the anchor (#835).

    West (20 m) is non-visible at K 3.5 (K_ave 3.5 x 10/11 = 3.18), east
    (40 m) is clear. East is not below 0.9 x west, so the agent stays; it
    used to leave because K_ave exceeded 3.0.
    """
    smoke = golden.ArmField({"west": 3.5})
    assert _decide_additive("west", smoke) == ("stay", None)
    ranked = rank_routes(
        golden._star2(),
        "spawn",
        5.0,
        0.0,
        smoke,
        None,
        golden._additive(w_smoke=0.0),
        current_exit="west",
    )
    west = next(rc for rc in ranked if rc.exit_id == "west")
    assert west.rejection_reason == "all segments non-visible"
    assert west.k_ave_route == pytest.approx(3.5 * 10 / 11)


def test_additive_dense_smoke_leaves_for_a_cheaper_rival():
    """East (40 m) is non-visible at K 3.5; west (20 m) < 0.9 x 40: leave."""
    smoke = golden.ArmField({"east": 3.5})
    assert _decide_additive("east", smoke)[0] == "west"


def test_additive_dense_smoke_with_lethal_dose_is_still_fled():
    """FED must-flee is unchanged: K_ave 3.18 and FED 2.0 on west leaves."""
    smoke = golden.ArmField({"west": 3.5})
    assert _decide_additive("west", smoke, LETHAL_WEST) == ("east", "fed_reroute")


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


@pytest.mark.parametrize("k_ave", [2.0, 4.0, 100.0])
def test_non_visible_smoke_is_never_a_must_flee(k_ave):
    """Under either model only a FED violation is fled, whatever the density."""
    for config in (golden._gate(), golden._additive()):
        rc = _refused("west", 0.0, ("all_segments_non_visible",), k_ave=k_ave)
        assert not _must_flee_rejection(rc, config)
        assert _must_flee_rejection(_refused("west", 0.0, ("fed",)), config)


def test_the_smoke_must_flee_is_gone():
    assert not hasattr(RouteCostConfig(), "impassable_extinction_threshold")
    assert not hasattr(policy_for(golden._additive()), "must_flee_smoke")


@pytest.mark.parametrize("value", [3.0, float("inf")])
def test_setting_the_removed_threshold_raises(value):
    routing = {"impassable_extinction_threshold": value}
    with pytest.raises(ValueError, match="impassable_extinction_threshold.*#835"):
        RouteCostConfig.from_routing_params(routing)
    with pytest.raises(ValueError, match="impassable_extinction_threshold.*#835"):
        check_removed_routing_keys(routing)


def test_alternating_lethal_dose_switches_every_tick():
    """A see-saw dose makes the agent flee on every tick.

    Both routes stay over tau (west 9.09, east 9.52: inside the 20 % margin,
    so tau alone would hold). The predicted dose alternates which exit is
    lethal: the current exit is over its limit 1.0 and the rival under its
    limit 0.9. Each tick the agent flees its current exit, back onto the one
    it left a second ago. This pins the behaviour
    the contract asks for; it is not a damping guarantee.

    The leg dose is the mean rate over the leg's points, 10/11 of the arm
    rate on the west leg and 20/21 on the east leg (the hub point is clear),
    so the arm rates are the dose-giving rates divided by those fractions:
    west 3.0 x 11/10 = 3.3, 2.5 x 11/10 = 2.75; east 1.2 x 21/20 = 1.26,
    1.5 x 21/20 = 1.575. The predicted doses below are unchanged.
    """
    smoke = golden.ArmField({"west": 0.5, "east": 0.25})
    # Predicted FED: west 1.04, east 0.82 / west 0.87, east 1.02.
    doses = (
        golden.ArmFed({"west": 3.3, "east": 1.26}),
        golden.ArmFed({"west": 2.75, "east": 1.575}),
    )
    config = RerouteConfig(cost_config=golden._gate())
    graph = golden._star2()
    rs = AgentRouteState(current_exit="west", current_path=["spawn", "west"])
    moves = []
    for tick, time_s in enumerate((5.0, 6.0, 7.0, 8.0)):
        current = rs.current_exit
        wait_info = {
            "current_origin": "spawn",
            "current_target_stage": current,
            "path_choices": {"spawn": [(current, 100.0)]},
            "state": "to_target",
        }
        fed = doses[tick % 2]
        ranked = _ranked(smoke, fed, current_exit=current)
        assert "fed" in ranked[current].violation_kinds
        rival = "east" if current == "west" else "west"
        assert ranked[rival].violation_kinds == ("tau",)
        switch = evaluate_and_reroute(
            7, wait_info, rs, graph, time_s, 0.0, smoke, fed, config
        )
        assert switch is not None
        moves.append((switch.old_exit, switch.new_exit, switch.reason))
    assert moves == [
        ("west", "east", "fallback"),
        ("east", "west", "fallback"),
        ("west", "east", "fallback"),
        ("east", "west", "fallback"),
    ]
