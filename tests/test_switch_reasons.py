"""Each route switch is labelled by what caused it (#92).

One case per cause, on the two-exit star of ``test_rerouting_golden``: the
spawn at the origin, ``west`` 20 m away and ``east`` 40 m away. Before #92
every change of exit that was not the first choice, a fallback or a closed
exit was labelled ``smoke_reroute``, in clear air too.
"""

from __future__ import annotations

import math
from dataclasses import replace

import pytest
import test_rerouting_golden as golden

from pyfds_evac.core.cognitive_map import AgentCognitiveMap
from pyfds_evac.core.route_graph import (
    AgentRouteState,
    RerouteConfig,
    RouteCost,
    StageGraph,
    _exit_change_reason,
    evaluate_and_reroute,
    rank_routes,
)


def _reroute(
    graph: StageGraph,
    config,
    route_state: AgentRouteState,
    *,
    target: str | None = None,
    state: str = "to_target",
    extinction=golden._CLEAR,
    fed=None,
    time_s: float = 5.0,
    cmap: AgentCognitiveMap | None = None,
    exit_counts: dict[str, int] | None = None,
):
    """One reevaluation of agent 7 at the spawn, walking to *target*."""
    target = target or route_state.current_exit or "spawn"
    return evaluate_and_reroute(
        agent_id=7,
        wait_info=golden._wait_info(graph, "spawn", target, state=state),
        route_state=route_state,
        graph=graph,
        current_time_s=time_s,
        current_fed=0.0,
        extinction_sampler=extinction,
        fed_rate_sampler=fed,
        config=RerouteConfig(cost_config=config),
        cached_segments={},
        exit_counts=exit_counts,
        cognitive_map=cmap,
    )


def _reason(switch) -> tuple[str, str | None, str]:
    assert switch is not None
    return switch.new_exit, switch.old_exit, switch.reason


def test_clear_air_switch_to_a_nearer_exit_is_shorter_path():
    """The case of the issue: no smoke anywhere, so not ``smoke_reroute``."""
    switch = _reroute(golden._star2(), golden._gate(), AgentRouteState("east"))
    assert _reason(switch) == ("west", "east", "shorter_path")


def test_clean_rival_over_a_dirty_exit_is_smoke_reroute():
    switch = _reroute(
        golden._star2(),
        golden._gate(clean_extinction_threshold=0.03),
        AgentRouteState("west"),
        extinction=golden.ArmField({"west": 0.05}),
    )
    assert _reason(switch) == ("east", "west", "smoke_reroute")


def test_additive_switch_that_needs_the_smoke_term_is_smoke_reroute():
    switch = _reroute(
        golden._star2(),
        golden._additive(w_smoke=5.0),
        AgentRouteState("west"),
        extinction=golden.ArmField({"west": 0.3}),
    )
    assert _reason(switch) == ("east", "west", "smoke_reroute")


@pytest.mark.parametrize("config", [golden._gate(), golden._additive()])
def test_fleeing_a_lethal_dose_is_fed_reroute(config):
    switch = _reroute(
        golden._star2(),
        config,
        AgentRouteState("west"),
        fed=golden.ArmFed({"west": 4.0}),
    )
    assert _reason(switch) == ("east", "west", "fed_reroute")


def test_route_over_dose_and_tau_is_fed_reroute():
    """Gate reports tau for a route over both limits; the dose names the cause."""
    graph, config = golden._star2(), golden._gate()
    smoke, fed = golden.ArmField({"west": 0.4}), golden.ArmFed({"west": 4.0})
    ranked = rank_routes(
        graph, "spawn", 5.0, 0.0, smoke, fed, config, current_exit="west"
    )
    west = next(rc for rc in ranked if rc.exit_id == "west")
    assert west.rejection_reason.startswith("tau")
    assert west.fed_max_route > config.fed_rejection_threshold
    switch = _reroute(graph, config, AgentRouteState("west"), extinction=smoke, fed=fed)
    assert _reason(switch) == ("east", "west", "fed_reroute")


def test_gate_switch_won_only_by_smoke_slowdown_is_smoke_reroute():
    """Within the tau deadband, but quicker only because smoke slows the old route.

    West is 20 m, at K = 0.45 beyond the spawn (tau 8.2, under tau_max 100;
    31 s against 20 s in clear air), east 26 m in clear air.
    """
    config = golden._gate(beta=-0.6, tau_max=100.0)
    switch = _reroute(
        golden._star({"west": 20.0, "east": 26.0}),
        config,
        AgentRouteState("west"),
        extinction=golden.ArmField({"west": 0.45}),
    )
    assert _reason(switch) == ("east", "west", "smoke_reroute")


def test_additive_switch_that_needs_the_dose_term_is_fed_reroute():
    """The near route's dose stays under the limit; its cost term decides."""
    switch = _reroute(
        golden._star2(),
        golden._additive(w_fed=100.0),
        AgentRouteState("west"),
        fed=golden.ArmFed({"west": 1.5}),
    )
    assert _reason(switch) == ("east", "west", "fed_reroute")


@pytest.mark.parametrize("config", [golden._gate(), golden._additive()])
def test_switch_that_needs_the_queue_term_is_congestion(config):
    switch = _reroute(
        golden._star2(),
        replace(config, w_queue=1.0),
        AgentRouteState("west"),
        exit_counts={"west": 40, "east": 0},
    )
    assert _reason(switch) == ("east", "west", "congestion")


def test_switch_to_an_exit_learned_since_the_last_evaluation_is_learned_exit():
    """The agent walks to east, then learns west, nearer, in clear air."""
    graph = golden._star2()
    cmap = AgentCognitiveMap(
        familiarity="discovery",
        known_nodes={"spawn", "east"},
        known_edges={("spawn", "east")},
    )
    route_state = AgentRouteState("east")
    assert _reroute(graph, golden._gate(), route_state, cmap=cmap) is None
    cmap.known_nodes.add("west")
    cmap.known_edges.add(("spawn", "west"))
    switch = _reroute(graph, golden._gate(), route_state, cmap=cmap, time_s=6.0)
    assert _reason(switch) == ("west", "east", "learned_exit")


def test_exit_learned_before_the_first_evaluation_is_learned_exit():
    """The map seeded at spawn counts as the previous evaluation's."""
    graph = golden._star2()
    cmap = AgentCognitiveMap(
        familiarity="discovery",
        known_nodes={"spawn", "east", "west"},
        known_edges={("spawn", "east"), ("spawn", "west")},
    )
    route_state = AgentRouteState(
        "east", known_at_last_eval=frozenset({"spawn", "east"})
    )
    switch = _reroute(graph, golden._gate(), route_state, cmap=cmap)
    assert _reason(switch) == ("west", "east", "learned_exit")


def test_switch_to_an_exit_known_before_is_not_learned_exit():
    """With the map unchanged, the same move is a shorter path."""
    graph = golden._star2()
    cmap = AgentCognitiveMap(
        familiarity="discovery",
        known_nodes={"spawn", "east", "west"},
        known_edges={("spawn", "east"), ("spawn", "west")},
    )
    route_state = AgentRouteState("east")
    route_state.last_eval_time_s = 4.0
    route_state.known_at_last_eval = frozenset(cmap.known_nodes)
    switch = _reroute(graph, golden._gate(), route_state, cmap=cmap)
    assert _reason(switch) == ("west", "east", "shorter_path")


def test_switch_to_an_exit_that_opened_since_the_last_evaluation_is_exit_opened():
    graph = golden._star2()
    graph.nodes["west"] = replace(graph.nodes["west"], open_from_s=6.0)
    route_state = AgentRouteState("east")
    assert _reroute(graph, golden._gate(), route_state) is None
    switch = _reroute(graph, golden._gate(), route_state, time_s=7.0)
    assert _reason(switch) == ("west", "east", "exit_opened")


def test_leaving_a_closed_exit_is_exit_closed():
    graph = golden._star2()
    graph.nodes["west"] = replace(graph.nodes["west"], closed_after_s=4.0)
    switch = _reroute(graph, golden._gate(), AgentRouteState("west"))
    assert _reason(switch) == ("east", "west", "exit_closed")


def test_leaving_an_exit_with_no_route_is_exit_unreachable():
    switch = _reroute(
        golden._star2(), golden._gate(), AgentRouteState("gone"), target="west"
    )
    assert _reason(switch) == ("west", "gone", "exit_unreachable")


def test_idle_agent_routed_to_its_own_exit_is_resume():
    switch = _reroute(
        golden._star2(), golden._gate(), AgentRouteState("west"), state="idle"
    )
    assert _reason(switch) == ("west", "west", "resume")


def test_first_choice_and_fallback_keep_their_labels():
    first = _reroute(golden._star2(), golden._gate(), AgentRouteState(), target="west")
    assert _reason(first) == ("west", None, "initial")
    fallback = _reroute(
        golden._star2(),
        golden._gate(),
        AgentRouteState("east"),
        extinction=golden.ArmField({"west": 0.4, "east": 2.0}),
    )
    assert _reason(fallback) == ("west", "east", "fallback")


def test_every_label_is_listed():
    from pyfds_evac.core.route_graph import SWITCH_REASONS

    assert len(set(SWITCH_REASONS)) == len(SWITCH_REASONS)
    assert {
        "fed_reroute",
        "smoke_reroute",
        "exit_opened",
        "learned_exit",
        "congestion",
        "shorter_path",
        "exit_unreachable",
        "resume",
    } <= set(SWITCH_REASONS)


# ── Attribution on hand-built routes ──────────────────────────────────
#
# A cost term is credited when the switch would not clear the anchor
# without it. The anchor is strict, as in _clears_exit_anchor: a cost of
# exactly old * anchor does not clear, the next float below does.


def _rc(exit_id: str, rank: float, **kw) -> RouteCost:
    base = dict(
        exit_id=exit_id,
        path=["spawn", exit_id],
        path_length_m=rank,
        k_ave_route=0.0,
        travel_time_s=rank,
        fed_max_route=0.0,
        composite_cost=rank,
        segments=[],
        rejected=False,
        rejection_reason=None,
        rank_cost=rank,
        clear_travel_time_s=rank,
    )
    base.update(kw)
    return RouteCost(**base)


def _additive_reason(old: RouteCost, new: RouteCost) -> str:
    config = RerouteConfig(cost_config=golden._additive(w_smoke=1.0, w_fed=100.0))
    return _exit_change_reason(new, "west", old, config, None)


@pytest.mark.parametrize(
    ("smoke_tau", "fed", "reason"),
    [
        # Each hazard alone clears the anchor: the dose is credited (#92 P2).
        (30.0, 0.3, "fed_reroute"),
        (30.0, 0.0, "smoke_reroute"),
        (0.0, 0.3, "fed_reroute"),
        # Neither alone clears (100 < 95.4 fails), both together do (100.8).
        (6.0, 0.06, "fed_reroute"),
        # Length alone clears: no hazard is credited.
        (0.0, 0.0, "shorter_path"),
    ],
)
def test_additive_attribution_of_redundant_hazards(smoke_tau, fed, reason):
    base = 112.0 if (smoke_tau, fed) == (0.0, 0.0) else 100.0
    old = _rc(
        "west",
        base + smoke_tau + 100.0 * fed,
        tau_route=smoke_tau,
        fed_max_route=fed,
    )
    assert _additive_reason(old, _rc("east", 100.0)) == reason


def test_queue_credit_at_the_anchor_boundary():
    """Gate, w_queue 1: the old route queues 10 s. Without the queue term the
    switch clears only strictly below 0.9 x 100 s."""
    config = RerouteConfig(cost_config=golden._gate(w_queue=1.0))
    old = _rc(
        "west", 110.0, travel_time_s=100.0, clear_travel_time_s=100.0, queue_time_s=10.0
    )
    at = 100.0 * config.exit_switch_anchor
    below = math.nextafter(at, 0.0)
    assert (
        _exit_change_reason(_rc("east", at), "west", old, config, None) == "congestion"
    )
    assert (
        _exit_change_reason(_rc("east", below), "west", old, config, None)
        == "shorter_path"
    )


def test_smoke_slowdown_credit_at_the_anchor_boundary():
    """Gate: the old route takes 100 s in smoke, 50 s in clear air."""
    config = RerouteConfig(cost_config=golden._gate())
    old = _rc("west", 100.0, clear_travel_time_s=50.0)
    at = 50.0 * config.exit_switch_anchor
    below = math.nextafter(at, 0.0)
    assert (
        _exit_change_reason(_rc("east", at), "west", old, config, None)
        == "smoke_reroute"
    )
    assert (
        _exit_change_reason(_rc("east", below), "west", old, config, None)
        == "shorter_path"
    )
