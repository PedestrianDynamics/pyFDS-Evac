"""Known defects of how the gate prices the agent's current exit.

Both tests are strict xfails: they state the intended behaviour and fail on
the current code. Each passes once its issue is fixed, and the marker must
then be removed. Neither reads FDS output.

* #451: every exit, the current one included, is priced on the path the
  search finds from the agent's origin node. An agent that has walked past
  smoke near its origin sees its current exit priced on a detour and leaves
  an exit a few seconds ahead.
* #452: the gate orders routes on raw optical depth, while the exit anchor
  treats differences up to ``tau_max * tau_deadband`` as ties. A τ difference
  of 1e-19 then decides whether the agent may switch at all.
"""

import pytest
from test_rerouting_smoke_sweep import FAR_EXIT, NEAR_EXIT, SPAWN, _graph

from pyfds_evac.core.route_graph import (
    AgentRouteState,
    RerouteConfig,
    RouteCostConfig,
    StageEdge,
    StageGraph,
    StageNode,
    _decide_exit_change,
    _euclidean,
    _select_candidate,
    rank_routes,
)


def _gate_config() -> RouteCostConfig:
    return RouteCostConfig(
        cost_model="gate", anticipate=False, base_speed_m_per_s=1.3, w_queue=0.0
    )


def _next_exit(ranked, current_exit: str, config: RerouteConfig) -> str:
    """The exit the agent heads for after one exit decision."""
    best = _select_candidate(ranked, AgentRouteState(current_exit=current_exit), config)
    if best.exit_id == current_exit:
        return current_exit
    old = next(rc for rc in ranked if rc.exit_id == current_exit)
    decision = _decide_exit_change(best, current_exit, old, old.rank_cost, config)
    return decision.target_id if decision.kind == "switch" else current_exit


# ── #451: the current exit priced on a detour ─────────────────────────


def _node(stage_id: str, x: float, y: float, stage_type: str) -> StageNode:
    return StageNode(
        stage_id=stage_id, centroid_x=x, centroid_y=y, stage_type=stage_type
    )


def _edge(graph: StageGraph, source: str, target: str) -> StageEdge:
    a, b = graph.nodes[source], graph.nodes[target]
    return StageEdge(
        source=source,
        target=target,
        weight=_euclidean(a.centroid_x, a.centroid_y, b.centroid_x, b.centroid_y),
        waypoints=[(a.centroid_x, a.centroid_y), (b.centroid_x, b.centroid_y)],
    )


def _detour_graph() -> StageGraph:
    """Origin O, exit E1 20 m east, exit E2 4 m west, checkpoint C off to the side."""
    nodes = [
        _node("O", 0.0, 0.0, "distribution"),
        _node("E1", 20.0, 0.0, "exit"),
        _node("C", 10.0, 10.0, "checkpoint"),
        _node("E2", -4.0, 0.0, "exit"),
    ]
    graph = StageGraph(nodes={n.stage_id: n for n in nodes})
    graph.edges = {
        "O": [_edge(graph, "O", "E1"), _edge(graph, "O", "C"), _edge(graph, "O", "E2")],
        "C": [_edge(graph, "C", "E1")],
    }
    return graph


class _SmokeBehindAgent:
    """K = 2 /m on the stretch of O→E1 just east of O."""

    def sample_extinction(self, time_s: float, x: float, y: float) -> float:
        return 2.0 if 0.5 <= x <= 5.0 and abs(y) < 1.0 else 0.0


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="#451")
def test_agent_past_the_smoke_keeps_the_exit_ahead():
    """The agent at (18, 0) is 2 m from E1 with the smoke behind it.

    Priced from O, E1 goes round C (20.7 s) and E2 (16.9 s) wins; the walk
    the agent is on, O→E1, has 1.6 s to go.
    """
    config = _gate_config()
    ranked = rank_routes(
        _detour_graph(),
        "O",
        0.0,
        0.0,
        _SmokeBehindAgent(),
        None,
        config,
        agent_position=(18.0, 0.0),
        current_target="E1",
        current_exit="E1",
    )
    assert _next_exit(ranked, "E1", RerouteConfig(cost_config=config)) == "E1"


# ── #452: sub-deadband τ decides the switch ───────────────────────────


class _NearArm:
    """K on the arm towards the near exit (x > 23 m), clear elsewhere."""

    def __init__(self, k: float) -> None:
        self.k = k

    def sample_extinction(self, time_s: float, x: float, y: float) -> float:
        return self.k if x > 23.0 else 0.0


def _exit_from_far(field) -> str:
    config = _gate_config()
    ranked = rank_routes(
        _graph(), SPAWN, 0.0, 0.0, field, None, config, current_exit=FAR_EXIT
    )
    return _next_exit(ranked, FAR_EXIT, RerouteConfig(cost_config=config))


def test_clear_air_moves_the_agent_to_the_near_exit():
    """The reference of the #452 test: 14.0 s against 19.4 s clears the anchor."""
    assert _exit_from_far(_NearArm(0.0)) == NEAR_EXIT


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="#452")
def test_negligible_smoke_inside_the_deadband_does_not_block_the_switch():
    assert _exit_from_far(_NearArm(1e-20)) == NEAR_EXIT
