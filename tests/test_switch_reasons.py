"""Each route switch is labelled by what caused it (#92).

One case per cause, on the two-exit star of ``test_rerouting_golden``: the
spawn at the origin, ``west`` 20 m away and ``east`` 40 m away. Before #92
every change of exit that was not the first choice, a fallback or a closed
exit was labelled ``smoke_reroute``, in clear air too.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
import test_rerouting_golden as golden

from pyfds_evac.core.cognitive_map import AgentCognitiveMap
from pyfds_evac.core.route_graph import (
    AgentRouteState,
    RerouteConfig,
    StageGraph,
    evaluate_and_reroute,
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
