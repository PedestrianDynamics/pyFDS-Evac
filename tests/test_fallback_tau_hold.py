"""Between two refused routes only a clearly lower tau moves an agent (#458).

Two places keep an agent on its exit when routes are refused: the fallback
order in ``_apply_fallback`` (site 1) and the exit anchor in
``anchor_allows`` (site 2). Both use one rule: the rival wins only if its
optical depth is lower than the current route's by
``fallback_switch_margin``. Equality, taus within ``EPS_TAU`` and both taus 0
keep the current exit; k_max and travel time do not decide. Before #458 site 1
compared k_max and site 2 compared travel time, so a rival with a third of the
smoke but the same worst stretch never won.

Each case runs at both sites and under both cost models, through the public
entry points that existed before the fix, so a failure on the old revision is
an assertion, not a missing name.
"""

from __future__ import annotations

import math
from dataclasses import replace

import pytest
import test_rerouting_golden as golden

from pyfds_evac.core.route_graph import (
    AgentRouteState,
    RerouteConfig,
    RouteCost,
    RouteCostConfig,
    _apply_fallback,
    evaluate_and_reroute,
    policy_for,
)

MODELS = ("gate", "additive")
CURRENT = "east"
RIVAL = "west"


def _config(model: str) -> RouteCostConfig:
    return RouteCostConfig(cost_model=model, base_speed_m_per_s=1.0)


def _refused(exit_id: str, tau: float, rank_cost: float, k_max: float = 6.0):
    """A refused route whose rejection is not one the agent must flee."""
    return RouteCost(
        exit_id=exit_id,
        path=["spawn", exit_id],
        path_length_m=rank_cost,
        k_ave_route=0.5,
        travel_time_s=rank_cost,
        fed_max_route=0.0,
        composite_cost=rank_cost,
        segments=[],
        rejected=True,
        rejection_reason=f"tau {tau:.2f} > 6.00",
        k_max_route=k_max,
        tau_route=tau,
        feasible=False,
        rank_cost=rank_cost,
    )


def _fallback_winner(rival: RouteCost, current: RouteCost, model: str) -> str:
    """Site 1: the exit the all-refused fallback promotes."""
    costs = _apply_fallback([current, rival], _config(model), CURRENT)
    assert costs[0].rejection_reason.startswith("fallback: ")
    return costs[0].exit_id


def _anchor_lets_go(rival: RouteCost, current: RouteCost, model: str) -> bool:
    """Site 2: whether the exit anchor lets the agent leave *current*."""
    cfg = RerouteConfig(cost_config=_config(model), exit_switch_anchor=0.9)
    return policy_for(cfg.cost_config).anchor_allows(rival, current, cfg)


def _assert_decision(rival: RouteCost, current: RouteCost, switch: bool, model):
    expected = RIVAL if switch else CURRENT
    assert _fallback_winner(rival, current, model) == expected
    assert _anchor_lets_go(rival, current, model) is switch


@pytest.mark.parametrize("model", MODELS)
def test_clearly_lower_tau_switches_although_slower(model):
    """The S4 shape: equal k_max, a third of the smoke, a longer walk."""
    rival = _refused(RIVAL, tau=11.0, rank_cost=18.7)
    current = _refused(CURRENT, tau=34.0, rank_cost=8.4)
    _assert_decision(rival, current, switch=True, model=model)


@pytest.mark.parametrize("model", MODELS)
def test_tau_within_margin_holds(model):
    rival = _refused(RIVAL, tau=30.0, rank_cost=5.0)
    current = _refused(CURRENT, tau=34.0, rank_cost=10.0)
    _assert_decision(rival, current, switch=False, model=model)


@pytest.mark.parametrize("model", MODELS)
def test_lower_k_max_at_equal_tau_holds(model):
    """k_max no longer decides: a milder worst stretch alone moves nobody."""
    rival = _refused(RIVAL, tau=20.0, rank_cost=5.0, k_max=1.0)
    current = _refused(CURRENT, tau=20.0, rank_cost=10.0, k_max=6.0)
    _assert_decision(rival, current, switch=False, model=model)


@pytest.mark.parametrize("model", MODELS)
def test_margin_boundary_holds_and_one_ulp_below_switches(model):
    current_tau = 34.0
    limit = current_tau * (1.0 - _config(model).fallback_switch_margin)
    current = _refused(CURRENT, tau=current_tau, rank_cost=10.0)
    at_limit = _refused(RIVAL, tau=limit, rank_cost=5.0)
    below = _refused(RIVAL, tau=math.nextafter(limit, 0.0), rank_cost=5.0)
    _assert_decision(at_limit, current, switch=False, model=model)
    _assert_decision(below, current, switch=True, model=model)


@pytest.mark.parametrize("model", MODELS)
def test_both_taus_zero_hold_although_rival_is_faster(model):
    rival = _refused(RIVAL, tau=0.0, rank_cost=1.0)
    current = _refused(CURRENT, tau=0.0, rank_cost=10.0)
    _assert_decision(rival, current, switch=False, model=model)


@pytest.mark.parametrize("model", MODELS)
def test_round_off_taus_tie_and_hold(model):
    """1e-20 is a tenth of 1e-19, but both are round-off (EPS_TAU)."""
    rival = _refused(RIVAL, tau=1e-20, rank_cost=1.0)
    current = _refused(CURRENT, tau=1e-19, rank_cost=10.0)
    _assert_decision(rival, current, switch=False, model=model)


@pytest.mark.parametrize("model", MODELS)
def test_absolute_floor_is_1e_9(model):
    """A difference of exactly 1e-9 ties and holds; one ulp more switches.

    The literal is the contract (#458, second round), not ``EPS_TAU``, so a
    changed constant fails here.
    """
    current_at = _refused(CURRENT, tau=1e-9, rank_cost=10.0)
    current_past = _refused(CURRENT, tau=math.nextafter(1e-9, math.inf), rank_cost=10.0)
    rival = _refused(RIVAL, tau=0.0, rank_cost=1.0)
    _assert_decision(rival, current_at, switch=False, model=model)
    _assert_decision(rival, current_past, switch=True, model=model)


@pytest.mark.parametrize("model", MODELS)
def test_must_flee_overrides_the_hold_at_the_anchor(model):
    """Impassable smoke on the current route lets go whatever the taus say."""
    cc = _config(model)
    rival = _refused(RIVAL, tau=40.0, rank_cost=20.0)
    current = replace(
        _refused(CURRENT, tau=34.0, rank_cost=10.0),
        k_ave_route=cc.impassable_extinction_threshold + 1.0,
        rejection_reason="all segments non-visible",
    )
    assert _anchor_lets_go(rival, current, model) is True


@pytest.mark.parametrize("model", MODELS)
def test_swapped_taus_inside_the_margin_do_not_flicker(model):
    """Two evaluations with the taus swapped: the agent stays both times."""
    first = (_refused(RIVAL, 30.0, 5.0), _refused(CURRENT, 34.0, 10.0))
    second = (_refused(RIVAL, 34.0, 5.0), _refused(CURRENT, 30.0, 10.0))
    for rival, current in (first, second):
        _assert_decision(rival, current, switch=False, model=model)


# ── Return lockout (#458) ─────────────────────────────────────────────
#
# Agent 22's pattern on the t_junction FDS deck, on the two-arm star: a
# fallback switch east -> west between two refused routes, then the smoke
# swings so that east's tau is clearly lower again. The return is blocked
# for fallback_return_lockout_s after the first switch.

_EAST_SMOKY = golden.ArmField({"west": 0.4, "east": 2.0})
_WEST_SMOKY = golden.ArmField({"west": 2.0, "east": 0.4})
_EAST_CLEAR = golden.ArmField({"west": 2.0})


class _Agent:
    """One agent on the star, heading east, evaluated call by call."""

    def __init__(self, lockout: float | None = None) -> None:
        cost = golden._gate()
        if lockout is not None:
            cost = replace(cost, fallback_return_lockout_s=lockout)
        self.config = RerouteConfig(cost_config=cost)
        self.graph = golden._star2()
        self.wait_info = golden._wait_info(
            self.graph, "spawn", CURRENT, path_choices={}, state="to_target"
        )
        self.state = AgentRouteState(current_exit=CURRENT)

    def evaluate(self, time_s: float, field) -> str | None:
        evaluate_and_reroute(
            agent_id=22,
            wait_info=self.wait_info,
            route_state=self.state,
            graph=self.graph,
            current_time_s=time_s,
            current_fed=0.0,
            extinction_sampler=field,
            fed_rate_sampler=None,
            config=self.config,
        )
        return self.state.current_exit


def _left_east_at(time_s: float, lockout: float | None = None) -> _Agent:
    agent = _Agent(lockout)
    assert agent.evaluate(time_s, _EAST_SMOKY) == RIVAL
    assert agent.state.refused_switch_from == CURRENT
    return agent


def test_default_lockout_is_ten_seconds():
    assert RouteCostConfig().fallback_return_lockout_s == 10.0
    assert RouteCostConfig.from_routing_params({}).fallback_return_lockout_s == 10.0


def test_refused_return_within_the_lockout_is_blocked():
    agent = _left_east_at(5.0)
    assert agent.evaluate(7.0, _WEST_SMOKY) == RIVAL
    assert agent.evaluate(15.0, _WEST_SMOKY) == RIVAL  # 10 s: still inside


def test_refused_return_after_the_lockout_is_allowed():
    agent = _left_east_at(5.0)
    assert agent.evaluate(15.5, _WEST_SMOKY) == CURRENT


def test_return_to_a_feasible_route_is_never_blocked():
    agent = _left_east_at(5.0)
    assert agent.evaluate(7.0, _EAST_CLEAR) == CURRENT


def test_zero_lockout_restores_the_plain_rule():
    agent = _left_east_at(5.0, lockout=0.0)
    assert agent.evaluate(7.0, _WEST_SMOKY) == CURRENT


@pytest.mark.parametrize("value", [-1.0, math.nan, "10", True])
def test_lockout_must_be_a_non_negative_number(value):
    with pytest.raises(ValueError, match="fallback_return_lockout_s"):
        RouteCostConfig.from_routing_params({"fallback_return_lockout_s": value})
