"""Hold the current exit when every route is refused (#696).

``RouteCostConfig.fallback_rule`` is a code-level option with no scenario
key. Under the default ``"tau"`` a refused rival displaces the current exit
when its optical depth is more than ``fallback_switch_margin`` lower (#458).
Under ``"hold"`` it never does; the agent leaves only for a feasible route,
or when the current route must be fled and the rival need not be (#128).

Star of ``test_rerouting_golden``: west arm 20 m, east arm 40 m, gate,
1 m/s. The hub sample is clear air, so K_ave is 10/11 of the arm value on
the west arm and 20/21 on the east arm. West at K 0.6: tau = 20 x 0.6 x
10/11 = 10.91 > 6, refused. East at K 0.15: tau = 40 x 0.15 x 20/21 =
5.71 > 4.8 (rival budget 6 x 0.8), refused. 5.71 < 0.8 x 10.91 = 8.73, so
the tau rule switches a west-bound agent east.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
import test_rerouting_golden as golden

from pyfds_evac.config.effective import _routing
from pyfds_evac.core.route_graph import (
    AgentRouteState,
    RerouteConfig,
    RouteCostConfig,
    _anchor_allows,
    _fallback_rival_wins,
    evaluate_and_reroute,
    rank_routes,
)

SMOKE = golden.ArmField({"west": 0.6, "east": 0.15})
LETHAL_WEST = golden.ArmFed({"west": 6.0})


def _config(rule: str) -> RouteCostConfig:
    return golden._gate(fallback_rule=rule)


def _decide(rule: str, fed=None) -> tuple[str, str | None]:
    """The exit a west-bound agent at the hub takes at 5 s, and why."""
    rs = AgentRouteState(current_exit="west", current_path=["spawn", "west"])
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
        SMOKE,
        fed,
        RerouteConfig(cost_config=_config(rule)),
    )
    if switch is None:
        return ("stay", None)
    return (switch.new_exit, switch.reason)


def _ranked(rule: str, current_exit: str | None, fed=None, smoke=SMOKE):
    return rank_routes(
        golden._star2(),
        "spawn",
        5.0,
        0.0,
        smoke,
        fed,
        _config(rule),
        current_exit=current_exit,
    )


def test_both_routes_refused_by_hand():
    routes = {rc.exit_id: rc for rc in _ranked("tau", "west")}
    assert routes["west"].tau_route == pytest.approx(20 * 0.6 * 10 / 11)
    assert routes["east"].tau_route == pytest.approx(40 * 0.15 * 20 / 21)
    assert routes["west"].violation_kinds == ("tau",)
    assert routes["east"].violation_kinds == ("tau",)


def test_tau_rule_switches_to_the_lower_tau():
    assert _decide("tau") == ("east", "fallback")


def test_hold_keeps_the_current_exit():
    assert _decide("hold") == ("stay", None)
    ranked = _ranked("hold", "west")
    assert ranked[0].exit_id == "west"
    assert ranked[0].rejection_reason.startswith("fallback: tau")


@pytest.mark.parametrize("rule", ["tau", "hold"])
def test_lethal_current_route_is_left_under_both_rules(rule):
    """West doses 6 FED/min, 20 s: FED 2.0. Must-flee overrides hold."""
    assert _decide(rule, LETHAL_WEST) == ("east", "fallback")


@pytest.mark.parametrize("rule", ["tau", "hold"])
def test_first_choice_is_the_lowest_tau(rule):
    """No current exit: east at K 0.2 has tau 7.62 > 6, both refused."""
    ranked = _ranked(rule, None, smoke=golden.ArmField({"west": 0.6, "east": 0.2}))
    assert all(not rc.feasible for rc in ranked)
    assert ranked[0].exit_id == "east"
    assert ranked[0].rejection_reason.startswith("fallback: tau")


@pytest.mark.parametrize(("rule", "wins"), [("tau", True), ("hold", False)])
def test_both_lethal_follow_the_rule(rule, wins):
    """Both routes must be fled: tau switches past the margin, hold keeps."""
    fed = golden.ArmFed({"west": 6.0, "east": 6.0})
    routes = {rc.exit_id: rc for rc in _ranked("tau", "west", fed)}
    west, east = routes["west"], routes["east"]
    assert "fed" in west.violation_kinds
    assert "fed" in east.violation_kinds
    assert _fallback_rival_wins(east, west, _config(rule)) is wins


def test_anchor_refuses_a_refused_rival_under_hold():
    routes = {rc.exit_id: rc for rc in _ranked("tau", "west")}
    west, east = routes["west"], routes["east"]
    assert _anchor_allows(east, west, RerouteConfig(cost_config=_config("tau")))
    assert not _anchor_allows(east, west, RerouteConfig(cost_config=_config("hold")))


def test_default_is_tau_and_no_scenario_key_sets_it():
    assert RouteCostConfig().fallback_rule == "tau"
    cfg = RouteCostConfig.from_routing_params({"fallback_rule": "hold"})
    assert cfg.fallback_rule == "tau"
    # The effective configuration does not present it as a known key.
    (row,) = _routing({"routing": {"fallback_rule": "hold"}})
    assert row.default is None


def test_unknown_rule_is_rejected():
    with pytest.raises(ValueError, match="fallback_rule 'nearest'"):
        RouteCostConfig(fallback_rule="nearest")


def _reroute(graph, config, rs, smoke, fed=None, target=None, time_s=5.0):
    """One reevaluation of agent 7 at the spawn; (new exit, reason) or stay."""
    switch = evaluate_and_reroute(
        7,
        golden._wait_info(graph, "spawn", target or rs.current_exit or "spawn"),
        rs,
        graph,
        time_s,
        0.0,
        smoke,
        fed,
        RerouteConfig(cost_config=config),
        {},
    )
    if switch is None:
        return ("stay", None)
    return (switch.new_exit, switch.reason)


@pytest.mark.parametrize("rule", ["tau", "hold"])
def test_lethal_current_route_overrides_the_return_lockout(rule):
    """The agent left east for west 1 s ago; west turns lethal.

    Both routes stay refused and the return to east is inside the 10 s
    lockout. Must-flee orders first, so the agent goes back to east under
    hold too.
    """
    rs = AgentRouteState(
        current_exit="west",
        current_path=["spawn", "west"],
        refused_switch_from="east",
        refused_switch_time_s=4.0,
    )
    decision = _reroute(golden._star2(), _config(rule), rs, SMOKE, LETHAL_WEST)
    assert decision == ("east", "fallback")


def test_lockout_holds_without_a_lethal_route():
    """Control for the test above: no dose, tau rule, the lockout holds."""
    rs = AgentRouteState(
        current_exit="west",
        current_path=["spawn", "west"],
        refused_switch_from="east",
        refused_switch_time_s=4.0,
    )
    assert _reroute(golden._star2(), _config("tau"), rs, SMOKE) == ("stay", None)


@pytest.mark.parametrize("rule", ["tau", "hold"])
def test_feasible_rival_is_taken_under_both_rules(rule):
    """West refused (tau 10.91), east clear and feasible: hold does not apply."""
    rs = AgentRouteState(current_exit="west", current_path=["spawn", "west"])
    smoke = golden.ArmField({"west": 0.6})
    assert _reroute(golden._star2(), _config(rule), rs, smoke) == (
        "east",
        "smoke_reroute",
    )


# Star3: west 10 m, east 30 m, north 50 m. East at K 0.6 (tau about 17)
# and north at K 0.15 (tau about 7.4) are both over the rival budget 4.8.
# The lowest tau is north, the nearest is east.
STAR3_SMOKE = golden.ArmField({"west": 1.0, "east": 0.6, "north": 0.15})


def _closed_west():
    graph = golden._star3()
    graph.nodes["west"] = replace(graph.nodes["west"], closed_after_s=4.0)
    return graph, AgentRouteState("west"), None


def _no_route():
    return golden._star3(), AgentRouteState("gone"), "west"


def _no_exit_yet():
    return golden._star3(), AgentRouteState(), None


@pytest.mark.parametrize("rule", ["tau", "hold"])
@pytest.mark.parametrize("case", [_closed_west, _no_route, _no_exit_yet])
def test_unavailable_current_exit_takes_the_lowest_tau(rule, case):
    """Hold has no exit to keep: the lowest tau wins, not the nearest.

    Only the exit is checked. The switch is labelled ``fallback`` here,
    which the reason precedence decides, not the fallback rule.
    """
    graph, rs, target = case()
    decision = _reroute(graph, _config(rule), rs, STAR3_SMOKE, target=target)
    assert decision[0] == "north"


@pytest.mark.parametrize(("rule", "expected"), [("tau", "east"), ("hold", "stay")])
def test_additive_both_lethal_follow_the_rule(rule, expected):
    """Additive: both arms dose 6 FED/min, so both routes must be fled.

    Must-flee does not separate them; tau switches east (5.71 < 0.8 x
    10.91), hold keeps west.
    """
    config = golden._additive(fallback_rule=rule)
    rs = AgentRouteState(current_exit="west", current_path=["spawn", "west"])
    fed = golden.ArmFed({"west": 6.0, "east": 6.0})
    decision = _reroute(golden._star2(), config, rs, SMOKE, fed)
    assert decision[0] == expected


@pytest.mark.parametrize("rule", ["tau", "hold"])
def test_additive_lethal_current_is_left(rule):
    config = golden._additive(fallback_rule=rule)
    rs = AgentRouteState(current_exit="west", current_path=["spawn", "west"])
    assert _reroute(golden._star2(), config, rs, SMOKE, LETHAL_WEST)[0] == "east"
