"""An allocated exit is a preference unless the journey sets ``"allocation": "hard"``.

Issue #854. A journey that reaches one exit used to leave the route graph one
exit, so the allocation could not be revised. Now an agent spawned at such a
node (a *preference node*: one exit reachable from it, no journey of it
``hard``, at least two exits in the deck) is ranked on a second graph that
adds the exits its spawn area sees directly. It keeps the allocated exit
unless a rival costs less than ``exit_switch_anchor`` (0.9) times as much,
strictly; the allocated exit is its current exit for the ordering.

Layers, cheapest first:

* classification and graph construction, pure;
* the opening choice and the reroute pass on hand-built graphs, with the
  hand values 0.85, 0.90 and 0.95 of the rival over the allocated cost;
* smoke at rank level, with stub fields (what the code does; the run on a
  fire deck is not part of this change);
* runs of a synthetic hall with two exits and two spawn areas, one at ratio
  0.85 and one at 0.95, in clear air.
"""

from __future__ import annotations

import contextlib
import io
import math

import pytest
import test_rerouting_golden as golden
from shapely.geometry import box

from pyfds_evac.config.parameters import REROUTE_INTERVAL_S
from pyfds_evac.core import scenario as scenario_mod
from pyfds_evac.core.cognitive_map import init_cognitive_map
from pyfds_evac.core.route_graph import (
    AgentRouteState,
    RerouteConfig,
    RouteCostConfig,
    StageGraph,
    evaluate_and_reroute,
    journey_allocation,
    preference_nodes,
    rank_routes,
    with_rival_edges,
)
from pyfds_evac.core.scenario import (
    Scenario,
    _assign_initial_exit,
    _migrate_journeys_v2,
    run_scenario,
)

# ── Classification ────────────────────────────────────────────────────


def _raw(
    journeys: list[dict],
    exits=("A", "B"),
    dists=("D0",),
    transitions: list[dict] | None = None,
) -> dict:
    """A deck skeleton; transitions default to those of the journeys' stages."""
    if transitions is None:
        transitions = [
            {"from": a, "to": b, "journey_id": j["id"]}
            for j in journeys
            for a, b in zip(j["stages"], j["stages"][1:])
        ]
    return {
        "exits": {e: {} for e in exits},
        "distributions": {d: {} for d in dists},
        "journeys": journeys,
        "transitions": transitions,
    }


def _journey(jid: str, stages: list[str], **extra) -> dict:
    return {"id": jid, "stages": stages} | extra


def test_single_exit_journey_makes_a_preference_node():
    assert preference_nodes(_raw([_journey("j", ["D0", "A"])])) == {"D0"}


def test_hard_journey_makes_a_hard_node():
    raw = _raw([_journey("j", ["D0", "A"], allocation="hard")])
    assert preference_nodes(raw) == frozenset()


def test_explicit_preference_is_the_default():
    raw = _raw([_journey("j", ["D0", "A"], allocation="preference")])
    assert preference_nodes(raw) == {"D0"}


def test_two_exit_journey_is_not_a_preference_node():
    raw = _raw([_journey("j", ["D0", "A"]), _journey("k", ["D0", "B"])])
    assert preference_nodes(raw) == frozenset()


def test_one_exit_deck_has_no_preference_node():
    raw = _raw([_journey("j", ["D0", "A"])], exits=("A",))
    assert preference_nodes(raw) == frozenset()


def test_deck_without_journeys_has_no_preference_node():
    assert preference_nodes(_raw([], transitions=[])) == frozenset()


def test_deck_without_transitions_has_no_preference_node():
    raw = _raw([_journey("j", ["D0", "A"])], transitions=[])
    assert preference_nodes(raw) == frozenset()


def test_one_hard_journey_makes_the_node_hard():
    raw = _raw(
        [
            _journey("j", ["D0", "A"]),
            _journey("k", ["D0", "A"], allocation="hard"),
        ]
    )
    assert preference_nodes(raw) == frozenset()


def test_nodes_are_classified_one_by_one():
    raw = _raw(
        [
            _journey("j", ["D0", "A"]),
            _journey("k", ["D1", "B"], allocation="hard"),
            _journey("m", ["D2", "A"]),
            _journey("n", ["D2", "B"]),
        ],
        dists=("D0", "D1", "D2"),
    )
    assert preference_nodes(raw) == {"D0"}


def test_exits_reached_through_a_checkpoint_are_counted():
    raw = _raw([_journey("j", ["D0", "C", "A"])])
    assert preference_nodes(raw) == {"D0"}
    raw["transitions"].append({"from": "C", "to": "B", "journey_id": "j"})
    assert preference_nodes(raw) == frozenset()


@pytest.mark.parametrize("value", ["soft", "", None, True, 1])
def test_unknown_allocation_names_the_journey(value):
    raw = _raw([_journey("walk_out", ["D0", "A"], allocation=value)])
    with pytest.raises(ValueError, match="walk_out.*allocation"):
        preference_nodes(raw)


def test_unknown_allocation_is_refused_even_in_a_one_exit_deck():
    raw = _raw([_journey("j", ["D0", "A"], allocation="x")], exits=("A",))
    with pytest.raises(ValueError, match="'j'"):
        preference_nodes(raw)


def test_journey_allocation_defaults_to_preference():
    assert journey_allocation({"id": "j"}) == "preference"
    assert journey_allocation({"id": "j", "allocation": "hard"}) == "hard"


def test_journeys_v2_allocation_reaches_the_legacy_journey():
    data = {
        "distributions": {
            "D0": {"journey_weights": [{"journey_id": "v"}]},
            "D1": {"journey_weights": [{"journey_id": "w"}]},
        },
        "journeys_v2": [
            {"id": "v", "sequence": ["A"], "allocation": "hard"},
            {"id": "w", "sequence": ["A"]},
        ],
    }
    _migrate_journeys_v2(data)
    by_id = {j["id"]: j for j in data["journeys"]}
    assert by_id["v"]["allocation"] == "hard"
    assert "allocation" not in by_id["w"]


# ── Graph ─────────────────────────────────────────────────────────────


def _hall_graph(a_len: float, b_len: float, **exit_info) -> StageGraph:
    """D0 at the origin, exit A on the west at a_len, exit B on the east at b_len.

    The journey is D0 -> A, so A is the allocated exit. Speed is 1 m/s in the
    cost configs below, so a route's cost is its length.
    """
    stages = {
        "A": {"polygon": golden._box(-a_len, 0), "stage_type": "exit"} | exit_info,
        "B": {"polygon": golden._box(b_len, 0), "stage_type": "exit"},
    }
    spawn = {"D0": {"coordinates": list(golden._box(0, 0).exterior.coords)}}
    return StageGraph.from_scenario(stages, [{"from": "D0", "to": "A"}], spawn)


def _targets(graph: StageGraph, src: str = "D0") -> list[str]:
    return [e.target for e in graph.edges.get(src, [])]


def test_rival_graph_adds_the_other_exit_without_duplicating_the_journey_edge():
    g1 = _hall_graph(10, 9)
    before = {src: list(out) for src, out in g1.edges.items()}
    g2 = with_rival_edges(g1, ["D0"])
    assert _targets(g2) == ["A", "B"]
    assert g1.edges == before
    assert g2.edges["D0"][0] is g1.edges["D0"][0]
    assert g2.nodes is g1.nodes


def test_rival_graph_adds_nothing_for_a_single_exit_deck():
    stages = {"A": {"polygon": golden._box(-10, 0), "stage_type": "exit"}}
    spawn = {"D0": {"coordinates": list(golden._box(0, 0).exterior.coords)}}
    g1 = StageGraph.from_scenario(stages, [{"from": "D0", "to": "A"}], spawn)
    assert with_rival_edges(g1, ["D0"]).edges == g1.edges


def test_exit_behind_a_journey_checkpoint_is_no_rival():
    """D0 -> C -> A, with both exits lying behind C: wiring gives D0 only C."""
    stages = {
        "C": {"polygon": golden._box(5, 0), "stage_type": "checkpoint"},
        "A": {"polygon": golden._box(10, -1), "stage_type": "exit"},
        "B": {"polygon": golden._box(10, 1), "stage_type": "exit"},
    }
    spawn = {"D0": {"coordinates": list(golden._box(0, 0).exterior.coords)}}
    transitions = [{"from": "D0", "to": "C"}, {"from": "C", "to": "A"}]
    g1 = StageGraph.from_scenario(stages, transitions, spawn)
    g2 = with_rival_edges(g1, ["D0"])
    assert _targets(g2) == ["C"]
    assert g2.edges == g1.edges


def _checkpoint_graph(b_len: float) -> StageGraph:
    """D0 -> C -> A, with A reachable on a direct line and B the rival to the west."""
    stages = {
        "C": {"polygon": golden._box(0, 10), "stage_type": "checkpoint"},
        "A": {"polygon": golden._box(10, 0), "stage_type": "exit"},
        "B": {"polygon": golden._box(-b_len, 0), "stage_type": "exit"},
    }
    spawn = {"D0": {"coordinates": list(golden._box(0, 0).exterior.coords)}}
    transitions = [{"from": "D0", "to": "C"}, {"from": "C", "to": "A"}]
    return StageGraph.from_scenario(stages, transitions, spawn)


def test_rival_graph_never_shortcuts_the_journey_to_its_own_exit():
    g2 = with_rival_edges(_checkpoint_graph(30), ["D0"])
    assert _targets(g2) == ["C", "B"]


def test_agent_on_a_checkpoint_journey_still_passes_the_checkpoint():
    g1 = _checkpoint_graph(30)
    g2 = with_rival_edges(g1, ["D0"])
    wait_info = {
        "mode": "path",
        "current_origin": "D0",
        "current_target_stage": "C",
        "path_choices": {"D0": [("C", 100.0)], "C": [("A", 100.0)]},
        "stage_configs": {
            "C": {"polygon": golden._box(0, 10)},
            "A": {"polygon": golden._box(10, 0)},
            "B": {"polygon": golden._box(-30, 0)},
        },
    }
    chosen = _assign_initial_exit(
        0, wait_info, g1, golden._gate(), None, 0.0, 42, {}, CLEAR,
        spawn_key=("D0", 0), rival_graph=g2,
    )  # fmt: skip
    assert chosen == "A"
    assert wait_info["current_target_stage"] == "C"


# ── Opening choice ────────────────────────────────────────────────────

CLEAR = golden._CLEAR


def _wait_info(b_len: float) -> dict:
    return {
        "mode": "path",
        "current_origin": "D0",
        "current_target_stage": "A",
        "path_choices": {"D0": [("A", 100.0)]},
        "stage_configs": {
            "A": {"polygon": golden._box(-10, 0)},
            "B": {"polygon": golden._box(b_len, 0)},
        },
    }


def _open(g1, g2, b_len: float, cost=None, anchor_config=None):
    """The exit a spawned agent allocated to A is sent to, at t=0 in clear air."""
    wait_info = _wait_info(b_len)
    chosen = _assign_initial_exit(
        0,
        wait_info,
        g1,
        cost or golden._gate(),
        None,
        0.0,
        42,
        {},
        CLEAR,
        spawn_key=("D0", 0),
        rival_graph=g2,
        anchor_config=anchor_config,
    )
    return chosen, wait_info["current_target_stage"]


@pytest.mark.parametrize(
    ("b_len", "expected"),
    [(8.5, "B"), (9.0, "A"), (9.5, "A")],
    ids=["0.85 switches", "0.90 stays (strict)", "0.95 stays"],
)
def test_opening_choice_holds_the_allocation_unless_clearly_cheaper(b_len, expected):
    g1 = _hall_graph(10, b_len)
    g2 = with_rival_edges(g1, ["D0"])
    assert _open(g1, g2, b_len) == (expected, expected)


def test_opening_choice_uses_the_exit_switch_anchor_of_the_run():
    g1 = _hall_graph(10, 9.5)
    g2 = with_rival_edges(g1, ["D0"])
    anchor = RerouteConfig(cost_config=golden._gate(), exit_switch_anchor=0.97)
    assert _open(g1, g2, 9.5, anchor_config=anchor) == ("B", "B")


def test_rank_one_alone_would_move_the_agent_on_a_one_percent_difference():
    """In clear air every tau is 0, so the order key falls to rank_cost."""
    g1 = _hall_graph(10, 9.9)
    g2 = with_rival_edges(g1, ["D0"])
    ranked = rank_routes(g2, "D0", 0.0, 0.0, CLEAR, None, golden._gate())
    assert ranked[0].exit_id == "B"
    assert _open(g1, g2, 9.9) == ("A", "A")


def test_without_the_rival_graph_the_allocation_is_hard():
    g1 = _hall_graph(10, 8.5)
    assert _open(g1, None, 8.5) == ("A", "A")


def test_closed_allocated_exit_gives_way_to_the_open_rival_when_preferred():
    g1 = _hall_graph(10, 12, closed_after_s=0.0)
    g2 = with_rival_edges(g1, ["D0"])
    assert _open(g1, g2, 12) == ("B", "B")


def test_closed_allocated_exit_keeps_the_scripted_exit_when_hard():
    g1 = _hall_graph(10, 12, closed_after_s=0.0)
    assert _open(g1, None, 12) == (None, "A")


def test_a_discovery_agent_sees_no_rival():
    g1 = _hall_graph(10, 8.5)
    g2 = with_rival_edges(g1, ["D0"])
    cmap = init_cognitive_map("D0", g1, "discovery", None, 0.0, entrance="A")
    ranked = rank_routes(
        g2, "D0", 0.0, 0.0, CLEAR, None, golden._gate(), cognitive_map=cmap
    )
    assert [rc.exit_id for rc in ranked] == ["A"]
    full = init_cognitive_map("D0", g1, "full", None, 0.0)
    ranked = rank_routes(
        g2, "D0", 0.0, 0.0, CLEAR, None, golden._gate(), cognitive_map=full
    )
    assert {rc.exit_id for rc in ranked} == {"A", "B"}


# ── Reroute pass ──────────────────────────────────────────────────────


def _walking(origin_x: float, b_len: float):
    """An agent walking D0 -> A, standing at (origin_x, 0)."""
    wait_info = {
        "current_origin": "D0",
        "current_target_stage": "A",
        "path_choices": {"D0": [("A", 100.0)]},
        "state": "to_target",
        "current_position": (origin_x, 0.0),
    }
    return wait_info, AgentRouteState(current_exit="A", current_path=["D0", "A"])


def _pass(graph: StageGraph, x: float):
    wait_info, rs = _walking(x, 10)
    switch = evaluate_and_reroute(
        0,
        wait_info,
        rs,
        graph,
        5.0,
        0.0,
        CLEAR,
        None,
        RerouteConfig(cost_config=golden._gate()),
        agent_position=(x, 0.0),
    )
    return switch, rs


def test_reroute_pass_leaves_the_allocation_for_a_rival_below_the_anchor():
    """At x = 0.8 the rival B is 9.2 m away and A 10.8 m: 0.852."""
    g2 = with_rival_edges(_hall_graph(10, 10), ["D0"])
    switch, rs = _pass(g2, 0.8)
    assert switch is not None
    assert (switch.old_exit, switch.new_exit, switch.reason) == (
        "A",
        "B",
        "shorter_path",
    )
    assert rs.current_exit == "B"


def test_reroute_pass_keeps_the_allocation_above_the_anchor():
    """At x = 0.3 the ratio is 9.7 / 10.3 = 0.942."""
    g2 = with_rival_edges(_hall_graph(10, 10), ["D0"])
    switch, rs = _pass(g2, 0.3)
    assert switch is None
    assert rs.current_exit == "A"


def test_reroute_pass_on_the_stage_graph_never_switches():
    """The hard case: the stage graph has only the allocated exit."""
    switch, rs = _pass(_hall_graph(10, 10), 0.8)
    assert switch is None
    assert rs.current_exit == "A"


# ── Smoke at rank level ───────────────────────────────────────────────

# Arms 20 m (west, allocated) and 40 m (east), 1 m/s, K_ave of a hub sample
# is 10/11 and 20/21 of the arm value (see test_fallback_hold).


def _arms(west_len: float, east_len: float) -> tuple[StageGraph, StageGraph]:
    stages = {
        "west": {"polygon": golden._box(-west_len, 0), "stage_type": "exit"},
        "east": {"polygon": golden._box(east_len, 0), "stage_type": "exit"},
    }
    spawn = {"D0": {"coordinates": list(golden._box(0, 0).exterior.coords)}}
    g1 = StageGraph.from_scenario(stages, [{"from": "D0", "to": "west"}], spawn)
    return g1, with_rival_edges(g1, ["D0"])


def _smoke_pass(graph: StageGraph, smoke, current_exit="west"):
    wait_info = {
        "current_origin": "D0",
        "current_target_stage": "west",
        "path_choices": {"D0": [("west", 100.0)]},
        "state": "to_target",
    }
    rs = AgentRouteState(current_exit=current_exit, current_path=["D0", "west"])
    switch = evaluate_and_reroute(
        0,
        wait_info,
        rs,
        graph,
        5.0,
        0.0,
        smoke,
        None,
        RerouteConfig(cost_config=golden._gate()),
    )
    return switch


def test_refused_allocation_gives_way_to_a_clean_rival():
    smoke = golden.ArmField({"west": 0.6})
    _, g2 = _arms(20, 40)
    switch = _smoke_pass(g2, smoke)
    assert switch is not None
    assert (switch.new_exit, switch.reason) == ("east", "smoke_reroute")


def test_all_routes_refused_the_allocation_holds_against_a_slightly_cleaner_rival():
    """east tau 40 x 0.25 x 20/21 = 9.52 against 8.73 = 0.8 x west's 10.91."""
    smoke = golden.ArmField({"west": 0.6, "east": 0.25})
    _, g2 = _arms(20, 40)
    assert _smoke_pass(g2, smoke) is None


def test_all_routes_refused_a_clearly_cleaner_rival_takes_the_agent():
    """east tau 40 x 0.2 x 20/21 = 7.62 < 8.73."""
    smoke = golden.ArmField({"west": 0.6, "east": 0.2})
    _, g2 = _arms(20, 40)
    switch = _smoke_pass(g2, smoke)
    assert switch is not None
    assert (switch.new_exit, switch.reason) == ("east", "fallback")


def test_hard_allocation_promotes_the_only_route_by_fallback():
    smoke = golden.ArmField({"west": 0.6, "east": 0.2})
    g1, _ = _arms(20, 40)
    ranked = rank_routes(
        g1, "D0", 5.0, 0.0, smoke, None, golden._gate(), current_exit="west"
    )
    assert [rc.exit_id for rc in ranked] == ["west"]
    assert ranked[0].rejected
    assert _smoke_pass(g1, smoke) is None


# ── Runs: a hall with two exits and two single-exit journeys ──────────

SEED = 42
RADIUS_M = 0.2
HALL = (0.0, 0.0, 100.0, 20.0)
DOOR_Y = (9.0, 11.0)
EXIT_BOXES = {
    "west": box(-1.0, DOOR_Y[0], 0.0, DOOR_Y[1]),
    "east": box(HALL[2], DOOR_Y[0], HALL[2] + 1.0, DOOR_Y[1]),
}
WEST_NODE = (-0.5, 10.0)
EAST_NODE = (HALL[2] + 0.5, 10.0)
SPAWN_HALF_M = 0.5
# Both areas are allocated to the west door. Their ratio is the cost of the
# east door over that of the west door, at the centre of the area.
AREAS = {"area_a": (0.85, 6.0), "area_b": (0.95, 14.0)}
AGENTS_PER_AREA = 2


def ratio_at(x: float, y: float) -> float:
    """East over west distance to the exit nodes, straight lines in a convex hall."""
    return math.dist((x, y), EAST_NODE) / math.dist((x, y), WEST_NODE)


def _x_for_ratio(ratio: float, y: float) -> float:
    lo, hi = HALL[0], HALL[2]
    for _ in range(80):
        mid = (lo + hi) / 2.0
        if ratio_at(mid, y) > ratio:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


AREA_CENTRES = {name: (_x_for_ratio(ratio, y), y) for name, (ratio, y) in AREAS.items()}


def _coords(polygon) -> list[list[float]]:
    return [[x, y] for x, y in polygon.exterior.coords]


def _spawn_box(centre: tuple[float, float]):
    x, y = centre
    return box(x - SPAWN_HALF_M, y - SPAWN_HALF_M, x + SPAWN_HALF_M, y + SPAWN_HALF_M)


def single_exit_scenario(
    allocation: str | None = None,
    parameters: dict | None = None,
    exit_extra: dict[str, dict] | None = None,
) -> Scenario:
    """The hall deck. *allocation* is written on both journeys when given."""
    sim_params = {"max_simulation_time": 150.0, "model_type": "CollisionFreeSpeedModel"}
    journeys, transitions, dists = [], [], {}
    for name, centre in AREA_CENTRES.items():
        dists[name] = {
            "type": "polygon",
            "coordinates": _coords(_spawn_box(centre)),
            "parameters": {
                "number": AGENTS_PER_AREA,
                "radius": RADIUS_M,
                "v0": 1.3,
                "use_flow_spawning": False,
                "distribution_mode": "by_number",
                "use_premovement": False,
                "radius_distribution": "constant",
                "v0_distribution": "constant",
            }
            | (parameters or {}),
        }
        transition = {"from": name, "to": "west", "journey_id": f"to_west_{name}"}
        journey = {
            "id": f"to_west_{name}",
            "stages": [name, "west"],
            "transitions": [transition],
        }
        if allocation is not None:
            journey["allocation"] = allocation
        journeys.append(journey)
        transitions.append(transition)
    raw = {
        "project_version": "2.0",
        "config": {
            "simulation_settings": {
                "simulationParams": sim_params,
                "numberOfSimulations": 1,
                "baseSeed": SEED,
            },
            "ui_state": {"useShortestPaths": False},
        },
        "exits": {
            name: {
                "type": "polygon",
                "coordinates": _coords(poly),
                "enable_throughput_throttling": False,
                "max_throughput": 0,
            }
            | (exit_extra or {}).get(name, {})
            for name, poly in EXIT_BOXES.items()
        },
        "distributions": dists,
        "checkpoints": {},
        "zones": {},
        "journeys": journeys,
        "transitions": transitions,
    }
    walkable = box(*HALL).union(EXIT_BOXES["west"]).union(EXIT_BOXES["east"])
    return Scenario(
        raw=raw,
        walkable_area_wkt=walkable.wkt,
        model_type="CollisionFreeSpeedModel",
        seed=SEED,
        sim_params=sim_params,
        source_path=None,
    )


def _by_rank(rows, rank: dict[int, int]) -> list[dict]:
    return [r | {"agent_id": rank[r["agent_id"]]} for r in rows or []]


def _run(scenario: Scenario, rerouting: bool) -> dict:
    reroute = (
        RerouteConfig(
            reevaluation_interval_s=REROUTE_INTERVAL_S,
            cost_config=RouteCostConfig.from_routing_params({}),
        )
        if rerouting
        else None
    )
    with contextlib.redirect_stdout(io.StringIO()):
        result = run_scenario(scenario, seed=SEED, reroute_config=reroute)
    try:
        df = result.trajectory_dataframe().sort_values(["id", "frame"])
        first = df.groupby("id").first()
        area = {
            int(i): "area_a" if row.y < 10.0 else "area_b"
            for i, row in first.iterrows()
        }
        exits: dict[str, list[str]] = {name: [] for name in AREAS}
        for rec in result.exit_history or []:
            exits[area[rec["agent_id"]]].append(rec["exit_id"])
        # JuPedSim numbers agents process-wide, so compare by creation order.
        rank = {aid: n for n, aid in enumerate(sorted(area))}
        return {
            "exits": exits,
            "history": _by_rank(result.exit_history, rank),
            "switches": _by_rank(result.route_history, rank),
            "evacuated": result.agents_evacuated,
            "total": result.total_agents,
        }
    finally:
        result.cleanup()


def test_hall_areas_sit_at_the_hand_ratios():
    for name, (ratio, _) in AREAS.items():
        x, y = AREA_CENTRES[name]
        assert ratio_at(x, y) == pytest.approx(ratio, abs=1e-9)
        corners = [
            ratio_at(x + dx, y + dy)
            for dx in (-SPAWN_HALF_M, SPAWN_HALF_M)
            for dy in (-SPAWN_HALF_M, SPAWN_HALF_M)
        ]
        # Nowhere in an area is the ratio within 0.03 of the anchor 0.9.
        assert all(abs(c - 0.9) > 0.03 for c in corners), (name, corners)


@pytest.mark.parametrize("rerouting", [False, True], ids=["off", "on"])
def test_single_exit_journey_is_a_preference_in_clear_air(rerouting):
    run = _run(single_exit_scenario(), rerouting)
    assert run["evacuated"] == run["total"] == 2 * AGENTS_PER_AREA
    assert run["exits"]["area_a"] == ["east"] * AGENTS_PER_AREA
    assert run["exits"]["area_b"] == ["west"] * AGENTS_PER_AREA


@pytest.mark.parametrize("rerouting", [False, True], ids=["off", "on"])
def test_hard_allocation_keeps_every_agent_on_its_journey(rerouting):
    run = _run(single_exit_scenario("hard"), rerouting)
    assert run["exits"]["area_a"] == ["west"] * AGENTS_PER_AREA
    assert run["exits"]["area_b"] == ["west"] * AGENTS_PER_AREA
    assert not run["switches"]


@pytest.mark.parametrize("rerouting", [False, True], ids=["off", "on"])
def test_hard_allocation_equals_a_run_without_the_rival_graph(rerouting, monkeypatch):
    """Hard is today's behaviour: the same run as one that has no preference node."""
    hard = _run(single_exit_scenario("hard"), rerouting)
    monkeypatch.setattr(scenario_mod, "preference_nodes", lambda raw: frozenset())
    plain = _run(single_exit_scenario(), rerouting)
    for key in ("history", "switches"):
        assert hard[key] == plain[key], key
    assert hard["history"], "the run recorded no exits"


def test_preference_run_without_the_key_equals_an_explicit_preference():
    implicit = _run(single_exit_scenario(), True)
    explicit = _run(single_exit_scenario("preference"), True)
    assert implicit["history"] == explicit["history"]
    assert implicit["switches"] == explicit["switches"]


def test_discovery_agents_are_unaffected(monkeypatch):
    """Their map is made from the stage graph, so the rival edge is unknown."""
    params = {"familiarity": "discovery", "entrance": "west"}
    scenario = single_exit_scenario(parameters=params)
    run = _run(scenario, True)
    monkeypatch.setattr(scenario_mod, "preference_nodes", lambda raw: frozenset())
    plain = _run(single_exit_scenario(parameters=params), True)
    assert run["history"] == plain["history"]
    assert run["switches"] == plain["switches"]
    assert {e for exits in run["exits"].values() for e in exits} == {"west"}


def test_invalid_allocation_stops_the_run_naming_the_journey():
    scenario = single_exit_scenario("soft")
    with pytest.raises(ValueError, match="to_west_area_a"):
        _run(scenario, False)


def test_scheduled_allocated_exit_closed_at_spawn_takes_the_rival():
    scenario = single_exit_scenario(exit_extra={"west": {"closed_after_s": 0.0}})
    run = _run(scenario, False)
    assert run["exits"]["area_a"] == ["east"] * AGENTS_PER_AREA
    assert run["exits"]["area_b"] == ["east"] * AGENTS_PER_AREA


FLOW = {"use_flow_spawning": True, "flow_start_time": 0, "flow_end_time": 6}


@pytest.mark.parametrize("rerouting", [False, True], ids=["off", "on"])
def test_flow_spawned_agents_hold_the_allocation_as_a_preference(rerouting):
    run = _run(single_exit_scenario(parameters=FLOW), rerouting)
    assert run["evacuated"] == run["total"] == 2 * AGENTS_PER_AREA
    assert run["exits"]["area_a"] == ["east"] * AGENTS_PER_AREA
    assert run["exits"]["area_b"] == ["west"] * AGENTS_PER_AREA


@pytest.mark.parametrize("rerouting", [False, True], ids=["off", "on"])
def test_flow_spawned_agents_keep_a_hard_allocation(rerouting):
    run = _run(single_exit_scenario("hard", parameters=FLOW), rerouting)
    assert run["exits"]["area_a"] == ["west"] * AGENTS_PER_AREA
    assert run["exits"]["area_b"] == ["west"] * AGENTS_PER_AREA


@pytest.mark.parametrize("rerouting", [False, True], ids=["off", "on"])
def test_allocated_exit_closing_mid_run_gives_way_to_the_rival(rerouting):
    """The agents of area_b, still heading west at 20 s, leave it by exit_closed."""
    scenario = single_exit_scenario(exit_extra={"west": {"closed_after_s": 20.0}})
    run = _run(scenario, rerouting)
    closed = [
        (s["old_exit"], s["new_exit"], s["reason"])
        for s in run["switches"]
        if s["reason"] == "exit_closed"
    ]
    assert closed == [("west", "east", "exit_closed")] * AGENTS_PER_AREA
    assert run["exits"]["area_b"] == ["east"] * AGENTS_PER_AREA


@pytest.mark.parametrize("rerouting", [False, True], ids=["off", "on"])
def test_hard_allocation_does_not_leave_an_exit_closing_mid_run(rerouting):
    scenario = single_exit_scenario(
        "hard", exit_extra={"west": {"closed_after_s": 20.0}}
    )
    assert not _run(scenario, rerouting)["switches"]


def test_opening_override_is_logged_at_the_spawn_time():
    run = _run(single_exit_scenario(), True)
    rows = [s for s in run["switches"] if s["reason"] == "allocation_preference"]
    assert [(s["time_s"], s["old_exit"], s["new_exit"]) for s in rows] == [
        (0.0, "west", "east")
    ] * AGENTS_PER_AREA
    assert len(run["switches"]) == len(rows)


def test_allocation_preference_is_a_listed_reason():
    from pyfds_evac.core.route_graph import SWITCH_REASONS

    assert "allocation_preference" in SWITCH_REASONS
