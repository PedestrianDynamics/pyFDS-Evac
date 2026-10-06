"""How the gate prices the agent's current exit and its rivals.

None of these tests reads FDS output.

* #451: exits are priced from where the agent stands. The search starts at
  the agent's position, the first leg is charged the smoke on the walk ahead
  of the agent, and the agent's own exit is never priced above the path it
  is walking. Before, every exit was priced on the path the search found from
  the agent's origin node, and an agent that had walked past smoke near its
  origin saw its current exit priced on a detour.
* #452: the gate ordered routes on raw optical depth, while the exit anchor
  treats differences up to ``tau_max * tau_deadband`` as ties. A τ difference
  of 1e-19 then decided whether the agent may switch at all. Taus within
  ``EPS_TAU`` now order as equal and travel time decides; a real τ
  difference inside the deadband still orders on τ.
"""

import math

import pytest
from test_rerouting_smoke_sweep import FAR_EXIT, NEAR_EXIT, SPAWN, _graph

from pyfds_evac.core.cognitive_map import AgentCognitiveMap
from pyfds_evac.core.route_graph import (
    EPS_TAU,
    AgentRouteState,
    RerouteConfig,
    RouteCostConfig,
    StageEdge,
    StageGraph,
    StageNode,
    _decide_exit_change,
    _euclidean,
    _order_routes,
    _polyline_stats,
    _select_candidate,
    evaluate_route,
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


def _rank_from(graph, position, field=None, config=None, **kwargs):
    return rank_routes(
        graph,
        "O",
        0.0,
        0.0,
        field or _SmokeBehindAgent(),
        None,
        config or _gate_config(),
        agent_position=position,
        **kwargs,
    )


def _by_exit(ranked):
    return {rc.exit_id: rc for rc in ranked}


def test_agent_past_the_smoke_prices_the_exit_ahead_on_the_walk():
    """E1 is priced on the clear 2 m walk to it, not round C."""
    e1 = _by_exit(
        _rank_from(_detour_graph(), (18.0, 0.0), current_target="E1", current_exit="E1")
    )["E1"]
    assert e1.path == ["O", "E1"]
    assert e1.tau_route == 0.0
    assert e1.travel_time_s == pytest.approx(2.0 / 1.3, rel=1e-12)


def test_way_back_is_charged_the_smoke_on_the_walk():
    """E2 lies behind the agent, through the smoke: τ is that of the walk."""
    config = _gate_config()
    e2 = _by_exit(
        _rank_from(_detour_graph(), (18.0, 0.0), current_target="E1", current_exit="E1")
    )["E2"]
    k_walk, _ = _polyline_stats(
        [(18.0, 0.0), (-4.0, 0.0)], 0.0, _SmokeBehindAgent(), config.sampling_step_m
    )
    assert k_walk > 0.0
    assert e2.path == ["O", "E2"]
    assert e2.tau_route == pytest.approx(k_walk * 22.0, rel=1e-12)
    assert e2.rejected


def _variant_graph() -> StageGraph:
    """The detour graph with E2 moved to (10, -10): the walk to it is clear."""
    graph = _detour_graph()
    graph.nodes["E2"] = _node("E2", 10.0, -10.0, "exit")
    graph.edges["O"] = [
        _edge(graph, "O", "E1"),
        _edge(graph, "O", "C"),
        _edge(graph, "O", "E2"),
    ]
    return graph


def test_clear_rival_does_not_beat_the_exit_two_metres_ahead():
    """E2 is reachable through clear air (9.9 s), E1 is 1.5 s away.

    Priced from O, E1 went round C (20.7 s) and E2 won on time.
    """
    config = _gate_config()
    ranked = _rank_from(
        _variant_graph(),
        (18.0, 0.0),
        current_target="E1",
        current_exit="E1",
        current_path=["O", "E1"],
    )
    assert _next_exit(ranked, "E1", RerouteConfig(cost_config=config)) == "E1"


def _rival_graph() -> StageGraph:
    """E1 20 m east of the agent; E3 reached via Y (near) or X (far round)."""
    nodes = [
        _node("O", 0.0, 0.0, "distribution"),
        _node("E1", 30.0, 0.0, "exit"),
        _node("Y", 10.0, 5.0, "checkpoint"),
        _node("X", -5.0, 10.0, "checkpoint"),
        _node("E3", 10.0, 12.0, "exit"),
    ]
    graph = StageGraph(nodes={n.stage_id: n for n in nodes})
    graph.edges = {
        "O": [_edge(graph, "O", "E1"), _edge(graph, "O", "Y"), _edge(graph, "O", "X")],
        "Y": [_edge(graph, "Y", "E3")],
        "X": [_edge(graph, "X", "E3")],
    }
    return graph


def test_rival_is_searched_for_from_the_agent():
    """Smoke near O lies on O→Y but not on the agent's walk to Y.

    From O the search sends E3 round X (23.1 s); from the agent at (6, 0)
    it goes via Y (10.3 s) and beats E1 (18.5 s).
    """
    config = _gate_config()
    ranked = _rank_from(
        _rival_graph(),
        (6.0, 0.0),
        current_target="E1",
        current_exit="E1",
        current_path=["O", "E1"],
    )
    assert _by_exit(ranked)["E3"].path == ["O", "Y", "E3"]
    assert _next_exit(ranked, "E1", RerouteConfig(cost_config=config)) == "E3"


class _SmokeShiftsArms:
    """Smoke on the A arm now and on the B arm later (t >= 3 s), east of x = 10."""

    def sample_extinction(self, time_s: float, x: float, y: float) -> float:
        if x < 10.0:
            return 0.0
        smoky_arm_is_a = time_s < 3.0
        return 1.0 if (y > 0.0) == smoky_arm_is_a else 0.0


def _two_arm_graph() -> StageGraph:
    nodes = [
        _node("O", 0.0, 0.0, "distribution"),
        _node("A", 10.0, 5.0, "checkpoint"),
        _node("B", 10.0, -5.0, "checkpoint"),
        _node("E", 20.0, 0.0, "exit"),
    ]
    graph = StageGraph(nodes={n.stage_id: n for n in nodes})
    graph.edges = {
        "O": [_edge(graph, "O", "A"), _edge(graph, "O", "B")],
        "A": [_edge(graph, "A", "E")],
        "B": [_edge(graph, "B", "E")],
    }
    return graph


def test_current_exit_is_never_priced_above_the_walked_path():
    """With foresight the search and the measurement disagree.

    The search weighs A→E at the present time, when it is smoky, and sends
    the agent's exit via B; on arrival A→E is clear and B→E smoky. The exit
    is priced on the path the agent is walking.
    """
    config = RouteCostConfig(
        cost_model="gate", anticipate=True, base_speed_m_per_s=1.3, w_queue=0.0
    )
    graph, field, walked = _two_arm_graph(), _SmokeShiftsArms(), ["O", "A", "E"]
    ranked = _rank_from(
        graph,
        (0.0, 0.0),
        field,
        config,
        current_target="A",
        current_exit="E",
        current_path=walked,
    )
    on_walk = evaluate_route(
        graph,
        walked,
        0.0,
        0.0,
        field,
        None,
        config,
        current_exit="E",
        agent_position=(0.0, 0.0),
    )
    searched = _by_exit(_rank_from(graph, (0.0, 0.0), field, config, current_exit="E"))[
        "E"
    ]
    assert searched.path == ["O", "B", "E"]
    assert searched.tau_route > on_walk.tau_route + 1.0
    e = _by_exit(ranked)["E"]
    assert e.tau_route <= on_walk.tau_route + 1e-9
    assert e.rank_cost <= on_walk.rank_cost + 1e-9


class _SmokeOnWalkToMLightPastX:
    """K = 2 /m on the agent's walk to M, K = 0.01 /m on X→E."""

    def sample_extinction(self, time_s: float, x: float, y: float) -> float:
        if 9.0 <= x <= 11.0 and 2.0 <= y <= 8.0:
            return 2.0
        return 0.01 if x <= -1.0 and 14.0 <= y <= 16.0 else 0.0


def _back_through_origin_graph() -> StageGraph:
    """From N the agent can go back into O and on to M, or on round X."""
    nodes = [
        _node("O", 0.0, 0.0, "distribution"),
        _node("N", 5.0, 0.0, "checkpoint"),
        _node("M", 10.0, 10.0, "checkpoint"),
        _node("X", -5.0, 15.0, "checkpoint"),
        _node("E", 10.0, 20.0, "exit"),
    ]
    graph = StageGraph(nodes={n.stage_id: n for n in nodes})
    graph.edges = {
        "O": [_edge(graph, "O", "N"), _edge(graph, "O", "M")],
        "N": [_edge(graph, "N", "O"), _edge(graph, "N", "X")],
        "M": [_edge(graph, "M", "E")],
        "X": [_edge(graph, "X", "E")],
    }
    return graph


def test_search_from_the_position_never_routes_back_through_the_origin(
    monkeypatch,
):
    """The agent at (10, 0) has smoke on its walk to M.

    Back through O (walk to N, N→O, O→M, M→E) is the cheapest search path,
    then round X (light smoke), then the walk through the smoke to M. Going
    back into O is not offered, so E goes round X and is priced on that
    path, the one the search costed.
    """
    searches = []
    search = StageGraph.shortest_paths_to_exits

    def spy(self, source, dynamic_weights=None, first_hops=None):
        found = search(
            self, source, dynamic_weights=dynamic_weights, first_hops=first_hops
        )
        searches.append((source, dynamic_weights, first_hops, found))
        return found

    monkeypatch.setattr(StageGraph, "shortest_paths_to_exits", spy)
    graph, field, position = (
        _back_through_origin_graph(),
        _SmokeOnWalkToMLightPastX(),
        (10.0, 0.0),
    )
    (e,) = _rank_from(graph, position, field)
    assert e.path == ["O", "N", "X", "E"]
    on_path = evaluate_route(
        graph, e.path, 0.0, 0.0, field, None, _gate_config(), agent_position=position
    )
    assert e.tau_route == pytest.approx(on_path.tau_route, rel=1e-12)
    assert e.rank_cost == pytest.approx(on_path.rank_cost, rel=1e-12)
    assert searches
    for source, weights, hops, found in searches:
        assert hops is not None
        for cost, path in found.values():
            assert path.count(source) == 1
            legs = zip(path[1:], path[2:])
            searched = hops[path[1]] + sum(weights[leg] for leg in legs)
            assert searched == pytest.approx(cost, rel=1e-12)


def _assert_same_ranking(a, b):
    assert [rc.path for rc in a] == [rc.path for rc in b]
    for x, y in zip(a, b):
        for name in ("tau_route", "rank_cost", "travel_time_s", "composite_cost"):
            assert getattr(x, name) == pytest.approx(
                getattr(y, name), rel=1e-12, abs=1e-12
            ), name


class _FedNearO:
    def sample_fed_rate(self, time_s, x, y):
        return 0.05 if math.hypot(x, y) < 12.0 else 0.0


@pytest.mark.parametrize("cost_model", ["gate", "additive"])
def test_agent_on_the_origin_ranks_as_the_origin(cost_model):
    """An agent standing on the origin centroid gets the origin's ranking."""
    config = RouteCostConfig(
        cost_model=cost_model, anticipate=False, base_speed_m_per_s=1.3
    )
    graph = _detour_graph()
    kwargs = {"current_exit": "E1", "current_target": "E1"}

    def rank(position):
        return rank_routes(
            graph,
            "O",
            0.0,
            0.0,
            _SmokeBehindAgent(),
            _FedNearO(),
            config,
            agent_position=position,
            **kwargs,
        )

    _assert_same_ranking(rank((0.0, 0.0)), rank(None))


def test_walks_stay_out_of_the_shared_segment_cache():
    cache: dict = {}
    _rank_from(
        _detour_graph(),
        (18.0, 0.0),
        cached_segments=cache,
        current_target="E1",
        current_exit="E1",
    )
    graph = _detour_graph()
    edges = {(e.source, e.target) for es in graph.edges.values() for e in es}
    assert {key[:2] for key in cache} <= edges


def test_search_from_the_position_keeps_to_the_known_graph():
    """A current target the agent does not know is not a first hop."""
    cmap = AgentCognitiveMap(
        familiarity="discovery",
        known_nodes={"O", "E1", "C"},
        known_edges={("O", "E1"), ("O", "C"), ("C", "E1")},
    )
    ranked = _rank_from(
        _detour_graph(), (-3.0, 0.0), cognitive_map=cmap, current_target="E2"
    )
    assert {rc.exit_id for rc in ranked} == {"E1"}


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


def test_negligible_smoke_inside_the_deadband_does_not_block_the_switch():
    assert _exit_from_far(_NearArm(1e-20)) == NEAR_EXIT


class _FarArm:
    """K on the arm towards the far exit (x < 17 m), clear elsewhere."""

    def __init__(self, k: float) -> None:
        self.k = k

    def sample_extinction(self, time_s: float, x: float, y: float) -> float:
        return self.k if x < 17.0 else 0.0


@pytest.mark.parametrize(
    "field",
    [_NearArm(0.0), _NearArm(1e-20), _FarArm(1e-20), _NearArm(1e-12), _FarArm(1e-12)],
    ids=["clear", "near-1e-20", "far-1e-20", "near-1e-12", "far-1e-12"],
)
def test_round_off_smoke_on_either_arm_leaves_the_decision_unchanged(field):
    assert _exit_from_far(field) == NEAR_EXIT


def _first_exit(field) -> str:
    ranked = rank_routes(_graph(), SPAWN, 0.0, 0.0, field, None, _gate_config())
    return ranked[0].exit_id


@pytest.mark.parametrize("field", [_NearArm(1e-20), _FarArm(1e-20)])
def test_initial_choice_with_round_off_smoke_is_the_faster_exit(field):
    assert _first_exit(field) == NEAR_EXIT


def test_a_real_tau_difference_still_orders_on_tau():
    """Δτ ≈ 0.01 is far above EPS_TAU and inside the deadband: τ decides."""
    field = _NearArm(1e-3)
    ranked = rank_routes(_graph(), SPAWN, 0.0, 0.0, field, None, _gate_config())
    near = next(rc for rc in ranked if rc.exit_id == NEAR_EXIT)
    assert near.tau_route > 1e3 * EPS_TAU
    assert ranked[0].exit_id == FAR_EXIT
    assert _exit_from_far(field) == FAR_EXIT


def _star_graph() -> StageGraph:
    """Origin O; exit E1 10 m east, E2 14 m west, E3 8 m north, E4 18 m south."""
    nodes = [
        _node("O", 0.0, 0.0, "distribution"),
        _node("E1", 10.0, 0.0, "exit"),
        _node("E2", -14.0, 0.0, "exit"),
        _node("E3", 0.0, 8.0, "exit"),
        _node("E4", 0.0, -18.0, "exit"),
    ]
    graph = StageGraph(nodes={n.stage_id: n for n in nodes})
    graph.edges = {"O": [_edge(graph, "O", e) for e in ("E1", "E2", "E3", "E4")]}
    return graph


class _StarSmoke:
    """K = 0.5 /m towards E3; the given K on the east, west and south arms."""

    def __init__(self, east: float, west: float, south: float = 0.0) -> None:
        self.east, self.west, self.south = east, west, south

    def sample_extinction(self, time_s: float, x: float, y: float) -> float:
        if y > 0.5:
            return 0.5
        if y < -0.5:
            return self.south
        if x > 0.5:
            return self.east
        return self.west if x < -0.5 else 0.0


def _rank_star(field, current_exit: str = "E3") -> list:
    return rank_routes(
        _star_graph(),
        "O",
        0.0,
        0.0,
        field,
        None,
        _gate_config(),
        current_exit=current_exit,
    )


@pytest.mark.parametrize(
    ("east", "west"), [(1e-20, 0.0), (0.0, 1e-20)], ids=["east", "west"]
)
def test_rivals_within_eps_tau_order_by_travel_time(east, west):
    ranked = _rank_star(_StarSmoke(east, west))
    assert [rc.exit_id for rc in ranked] == ["E1", "E2", "E4", "E3"]


def _taus(ranked) -> dict[str, float]:
    return {rc.exit_id: rc.tau_route for rc in ranked}


def test_a_tie_across_a_rounding_boundary_orders_by_travel_time():
    """τ 5.1e-10 against 4.9e-10: a grid of EPS_TAU would split them."""
    ranked = _rank_star(_StarSmoke(east=6.12e-11, west=4.0e-11, south=0.5))
    tau = _taus(ranked)
    assert tau["E2"] < 0.5 * EPS_TAU < tau["E1"]
    assert abs(tau["E1"] - tau["E2"]) < EPS_TAU
    assert [rc.exit_id for rc in ranked][:2] == ["E1", "E2"]


def test_a_tie_with_the_discounted_current_exit_orders_by_travel_time():
    """The current exit's τ is discounted before the tie is tested."""
    ranked = _rank_star(_StarSmoke(east=6.12e-11, west=4.41e-11, south=0.5), "E2")
    tau = _taus(ranked)
    discounted = tau["E2"] * _gate_config().current_exit_discount
    assert discounted < 0.5 * EPS_TAU < tau["E1"] < 0.5 * EPS_TAU + EPS_TAU
    assert [rc.exit_id for rc in ranked][:2] == ["E1", "E2"]


def test_a_chain_of_ties_is_one_group_ordered_by_travel_time():
    """τ 0, 0.75e-9 and 1.5e-9, each faster than the last: no preference cycle.

    Each neighbouring pair ties, so the three share one group and travel time
    orders all of them, although E1 and E4 are 1.5e-9 apart.
    """
    ranked = _rank_star(_StarSmoke(east=1.8e-10, west=6.1e-11))
    tau = _taus(ranked)
    assert tau["E4"] == 0.0
    assert tau["E2"] - tau["E4"] <= EPS_TAU
    assert tau["E1"] - tau["E2"] <= EPS_TAU
    assert tau["E1"] - tau["E4"] > EPS_TAU
    assert [rc.exit_id for rc in ranked] == ["E1", "E2", "E4", "E3"]


def test_equal_keys_in_a_tie_group_keep_the_input_order():
    """Raw τ never decides: equal time and path length keep the input order.

    At the walked-path substitution this keeps the priced route (first) over
    the walked one, as the strict comparison did before #452.
    """
    keys = {"rc": (0, 0, 4e-10, 10.0, 2), "walked": (0, 0, 3e-10, 10.0, 2)}
    assert _order_routes(["rc", "walked"], keys.__getitem__) == ["rc", "walked"]
    keys = {"a": (0, 0, 0.51e-9, 10.0, 2), "b": (0, 0, 0.49e-9, 10.0, 2)}
    assert _order_routes(["a", "b"], keys.__getitem__) == ["a", "b"]
