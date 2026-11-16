"""The queue term counts the agents ahead of the deciding agent (#89).

An agent pays for an exit ``N_ahead / capacity`` seconds, with ``N_ahead`` the
holders of that exit strictly closer to the exit centroid than itself. The
unit tests are hand-checkable on ``ExitQueueIndex``. The run tests recompute
``N_ahead`` from the trajectory and the route history, not from the logged
column, and check every congestion switch against it.

Corridor deck, predictions declared before the run. A corridor of 44 x 3 m,
exit A at the west end (centroid (0.5, 1.5)), exit B at the east end
(centroid (43.5, 1.5)). Forty agents stand on y = 1.5 at x = 42 - 0.5 k,
k = 0 .. 39, all nearer to B, so full familiarity starts every agent on B.
Agent k is 1.5 + 0.5 k m from B and 41.5 - 0.5 k m from A, and k agents are
ahead of it at B. Clear air, gate, ``w_queue = 1``, capacity 1.3 per second,
speed 1.3 m/s, so t_A = (41.5 - 0.5 k) / 1.3 and t_B = (1.5 + 0.5 k) / 1.3.
 - P1: no agent with ``N_ahead = 0`` at its exit switches for ``congestion``;
   agent 0 stays on B. With the global tally agent 0 pays 40 / 1.3 = 30.8 s
   and switches.
 - P2: every congestion switch has ``t_A + N_A / c < 0.9 (t_B + N_B / c)``
   with the independently recomputed counts.
 - P3: an agent switches B -> A only when N_B > c (t_A / 0.9 - t_B)
   + N_A / 0.9, the rule of P2 solved for N_B; checked per switch. The first
   pass sends the agents far from B to A, not the lowest ids. Agent 21 sees
   21 ahead and 41.5 - 10.5 < 1.35 + 9.45 + 18.9 fails, so it stays; agent 22
   switches. The switchers leave B, so every later agent counts the 22 who
   stay: 41.5 - 0.5 k < 1.35 + 0.45 k + 19.8 gives k > 21.4. Predicted:
   k <= 21 stay, k >= 22 switch.
Measured, not gated: the first pass switches k = 23 .. 39 (k = 22 is
refused: 23.6 s against 0.9 x 25.6 s, the walk is a little longer than the
straight line), and the first pass is at t = 1 s, after agent 0 has left, so
agent 1 is the head of the queue that exercises P1.

The corridor is 44 m long. In the 30 m corridor first tried, the agents at
x < 15 m are nearer to A and full familiarity starts them on A, so not every
agent started on B.
"""

from __future__ import annotations

import contextlib
import io
import json
import math
import random
import sqlite3

import pytest
from shapely.geometry import box
from test_rerouting_golden import RankCase, _additive, _star2

from pyfds_evac.core.exit_queue import ExitQueueIndex
from pyfds_evac.core.route_graph import RerouteConfig, RouteCostConfig, rank_routes
from pyfds_evac.core.scenario import load_scenario, run_scenario

CAPACITY = 1.3
ANCHOR = 0.9
T_JUNCTION_POINTS = {"exit_A_left": (0.5, 11.5), "exit_B_right": (29.5, 11.5)}
CORRIDOR_POINTS = {"exit_A_left": (0.5, 1.5), "exit_B_right": (43.5, 1.5)}


def _index(points, holders):
    index = ExitQueueIndex(points)
    index.build(holders)
    return index


# ---- the counting helper, by hand -------------------------------------


def test_ahead_counts_the_strictly_closer_holders():
    """Exit at (0, 0); holders at 1, 2, 3, 4 m. An agent at 2.5 m has two."""
    holders = [(i, "e", (float(i), 0.0)) for i in (1, 2, 3, 4)]
    index = _index({"e": (0.0, 0.0)}, holders)
    assert index.ahead(99, (2.5, 0.0)) == {"e": 2}


def test_a_tie_in_distance_is_not_ahead():
    """An agent at exactly 2.0 m has only the holder at 1 m ahead."""
    holders = [(i, "e", (float(i), 0.0)) for i in (1, 2, 3, 4)]
    index = _index({"e": (0.0, 0.0)}, holders)
    assert index.ahead(99, (0.0, 2.0)) == {"e": 1}


def test_the_agent_itself_is_never_counted():
    holders = [(1, "e", (1.0, 0.0)), (2, "e", (2.0, 0.0)), (3, "e", (3.0, 0.0))]
    index = _index({"e": (0.0, 0.0)}, holders)
    assert index.ahead(2, (2.0, 0.0)) == {"e": 1}
    # An agent that does not hold the exit, standing where a holder stands.
    assert index.ahead(99, (2.0, 0.0)) == {"e": 1}


def test_a_holder_of_another_exit_is_not_counted():
    points = {"e1": (0.0, 0.0), "e2": (10.0, 0.0)}
    index = _index(points, [(1, "e2", (0.1, 0.0)), (2, "e1", (5.0, 0.0))])
    assert index.ahead(99, (3.0, 0.0)) == {"e1": 0, "e2": 0}


def test_ahead_never_exceeds_the_holders_without_the_agent():
    rng = random.Random(89)
    points = {"e1": (0.0, 0.0), "e2": (20.0, 5.0), "e3": (10.0, 10.0)}
    for _ in range(50):
        holders = [
            (i, rng.choice([*points, None]), (rng.uniform(0, 20), rng.uniform(0, 10)))
            for i in range(30)
        ]
        index = _index(points, holders)
        for agent_id, own, position in holders:
            ahead = index.ahead(agent_id, position)
            for exit_id in points:
                held = sum(1 for _, e, _ in holders if e == exit_id)
                assert ahead[exit_id] <= held - (own == exit_id)


def test_queue_time_is_the_count_ahead_over_the_capacity():
    """13 ahead at 1.3 agents/s is 10.0 s."""
    case = RankCase(
        _star2,
        _additive(w_queue=1.0),
        exit_counts={"west": 13, "east": 0},
    )
    ranked = rank_routes(
        case.graph(),
        case.source,
        case.time_s,
        case.current_fed,
        case.extinction,
        case.fed,
        case.config,
        exit_counts=case.exit_counts,
    )
    west = next(rc for rc in ranked if rc.exit_id == "west")
    assert west.queue_time_s == pytest.approx(10.0, abs=1e-9)


def test_a_switch_moves_the_agent_between_the_exit_orderings():
    """Agent 1 moves e1 -> e2 inside a pass; a later evaluator counts it at e2.

    Exits at (0, 0) and (10, 0). Agent 1 stands at (8, 0): 8 m from e1, 2 m
    from e2. An evaluator at (6, 0) is 6 m from e1 and 4 m from e2: before
    the switch agent 1 is behind it at e1 (8 > 6), after it agent 1 is ahead
    of it at e2 (2 < 4).
    """
    points = {"e1": (0.0, 0.0), "e2": (10.0, 0.0)}
    index = _index(points, [(1, "e1", (8.0, 0.0))])
    assert index.ahead(99, (6.0, 0.0)) == {"e1": 0, "e2": 0}
    index.move(1, "e2", (8.0, 0.0))
    assert index.ahead(99, (6.0, 0.0)) == {"e1": 0, "e2": 1}
    index.move(1, None, (8.0, 0.0))
    assert index.ahead(99, (6.0, 0.0)) == {"e1": 0, "e2": 0}


# ---- the runs ----------------------------------------------------------


def _run(scenario, seed, w_queue):
    config = RerouteConfig(
        reevaluation_interval_s=1.0,
        cost_config=RouteCostConfig.from_routing_params(
            {**scenario.raw.get("routing", {}), "w_queue": w_queue}
        ),
    )
    with contextlib.redirect_stdout(io.StringIO()):
        return run_scenario(
            scenario,
            seed=seed,
            reroute_config=config,
            collect_route_cost_history=True,
        )


def _t_junction():
    return load_scenario("assets/t_junction/config_initial_pre0.json")


def _corridor(tmp_path):
    """The 40-agent corridor of the module docstring, written as a deck."""
    exits = {
        name: {
            "type": "polygon",
            "coordinates": [[x0, 0], [x0 + 1, 0], [x0 + 1, 3], [x0, 3], [x0, 0]],
            "sign": {"x": x0 + 0.5, "y": 1.5, "alpha": alpha, "c": 3},
        }
        for name, x0, alpha in (("exit_A_left", 0, 90), ("exit_B_right", 43, 270))
    }
    distributions = {}
    for k in range(40):
        x = 42.0 - 0.5 * k
        distributions[f"jps-distributions_{k}"] = {
            "type": "polygon",
            "coordinates": [
                [x - 0.2, 1.3],
                [x + 0.2, 1.3],
                [x + 0.2, 1.7],
                [x - 0.2, 1.7],
                [x - 0.2, 1.3],
            ],
            "parameters": {
                "number": 1,
                "radius": 0.15,
                "v0": 1.3,
                "use_flow_spawning": False,
                "distribution_mode": "by_number",
                "use_premovement": False,
                "radius_distribution": "constant",
                "v0_distribution": "constant",
                "familiarity": "full",
            },
            "journey_weights": [{"journey_id": "to_B", "weight": 1.0}],
        }
    deck = {
        "project_version": "2.0",
        "config": {
            "simulation_settings": {
                "simulationParams": {
                    "max_simulation_time": 120,
                    "model_type": "CollisionFreeSpeedModel",
                },
                "numberOfSimulations": 1,
                "baseSeed": 1,
            },
            "ui_state": {"useShortestPaths": False},
        },
        "routing": {"base_speed_m_per_s": 1.3, "default_exit_capacity": CAPACITY},
        "walkable_area_wkt": box(0, 0, 44, 3).wkt,
        "exits": exits,
        "distributions": distributions,
        "checkpoints": {},
        "zones": {},
        "journeys_v2": [
            {
                "id": "to_B",
                "name": "to_B",
                "color": "#4e79a7",
                "sequence": ["exit_B_right"],
            }
        ],
    }
    path = tmp_path / "corridor.json"
    path.write_text(json.dumps(deck), encoding="utf-8")
    return load_scenario(str(path))


def _holders_by_switch(result):
    """``(row, holders)`` for every switch: who holds what just before it.

    An agent holds the old exit of its first switch until then, and the exit
    of ``exit_history`` if it never switches. Switches replay in order, so a
    later row of the same pass sees the earlier ones.
    """
    holders = {int(r["agent_id"]): r["exit_id"] for r in result.exit_history}
    rows = [r for r in result.route_history if r.get("old_exit")]
    seen = set()
    for row in rows:
        agent = int(row["agent_id"])
        if agent not in seen:
            holders[agent] = row["old_exit"]
            seen.add(agent)
    replay = []
    for row in rows:
        replay.append((row, dict(holders)))
        holders[int(row["agent_id"])] = row["new_exit"]
    return replay


def _positions(result, time_s):
    with contextlib.closing(sqlite3.connect(result.sqlite_file)) as db:
        (fps,) = db.execute("select value from metadata where key='fps'").fetchone()
        frame = round(time_s * float(fps))
        return {
            int(i): (x, y)
            for i, x, y in db.execute(
                "select id, pos_x, pos_y from trajectory_data where frame=?", (frame,)
            )
        }


def _ahead(position_of, holders, points, agent, exit_id):
    """N_ahead for *agent* at *exit_id*, from positions and holders alone."""
    mine = math.dist(position_of[agent], points[exit_id])
    return sum(
        1
        for i, held in holders.items()
        if i != agent
        and held == exit_id
        and i in position_of
        and math.dist(position_of[i], points[exit_id]) < mine
    )


def _audit_congestion(result, points):
    """``(row, n_old, n_new)`` of every congestion switch, recomputed."""
    out = []
    for row, holders in _holders_by_switch(result):
        if row["reason"] != "congestion":
            continue
        pos = _positions(result, float(row["time_s"]))
        agent = int(row["agent_id"])
        out.append(
            (
                row,
                _ahead(pos, holders, points, agent, row["old_exit"]),
                _ahead(pos, holders, points, agent, row["new_exit"]),
            )
        )
    return out


DECKS = {
    "t_junction": (_t_junction, T_JUNCTION_POINTS),
    "corridor": (None, CORRIDOR_POINTS),
}


def _deck(name, tmp_path):
    build, points = DECKS[name]
    scenario = _corridor(tmp_path) if build is None else build()
    return scenario, points


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_nobody_ahead_never_switches_for_the_queue_t_junction(seed):
    """Fails with the global tally: on origin/main seed 1 agent 36 and seed 2
    agent 140 switched with nobody ahead of them at the exit."""
    result = _run(_t_junction(), seed, w_queue=1.0)
    try:
        assert result.agents_remaining == 0
        audit = _audit_congestion(result, T_JUNCTION_POINTS)
        assert audit, "no congestion switch to check"
        stuck = [row["agent_id"] for row, n_old, _ in audit if n_old == 0]
        assert not stuck, f"agents with nobody ahead switched for the queue: {stuck}"
    finally:
        result.cleanup()


@pytest.mark.parametrize("seed", [1, 2, 3])
@pytest.mark.parametrize("deck", ["t_junction", "corridor"])
def test_every_congestion_switch_follows_the_rule_on_recomputed_counts(
    deck, seed, tmp_path
):
    """P2 and P3: each switch clears the anchor with the independent counts.

    The counts come from the trajectory and the holders replayed from the
    route history, so the logged column is checked against them, not
    against itself. With t the travel time of the exit's route:
    t_new + N_new / c < 0.9 (t_old + N_old / c), which is
    N_old > c (t_new / 0.9 - t_old) + N_new / 0.9.
    """
    scenario, points = _deck(deck, tmp_path)
    result = _run(scenario, seed, w_queue=1.0)
    try:
        assert result.agents_remaining == 0
        audit = _audit_congestion(result, points)
        assert audit, "no congestion switch to check"
        logged = {
            (float(r["time_s"]), int(r["agent_id"]), r["exit_id"]): r
            for r in result.route_cost_history
        }
        for row, n_old, n_new in audit:
            key = (float(row["time_s"]), int(row["agent_id"]))
            old, new = logged[(*key, row["old_exit"])], logged[(*key, row["new_exit"])]
            # P1: someone is ahead.
            assert n_old > 0
            for entry, n in ((old, n_old), (new, n_new)):
                assert entry["exit_queue_ahead"] == n
                assert entry["queue_time_s"] * entry["exit_capacity"] == pytest.approx(
                    n
                )
            # P2 on the recomputed counts and the logged walking times.
            t_old, t_new = old["travel_time_s"], new["travel_time_s"]
            assert t_new + n_new / CAPACITY < ANCHOR * (t_old + n_old / CAPACITY)
            # P3: the same rule solved for the count ahead at the old exit.
            assert n_old > CAPACITY * (t_new / ANCHOR - t_old) + n_new / ANCHOR
    finally:
        result.cleanup()


def test_the_default_queue_weight_charges_nothing():
    result = _run(_t_junction(), 1, w_queue=0.0)
    try:
        assert {r["exit_queue_ahead"] for r in result.route_cost_history} == {0}
        assert {r["queue_time_s"] for r in result.route_cost_history} == {0.0}
        assert not [r for r in result.route_history if r["reason"] == "congestion"]
    finally:
        result.cleanup()


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_corridor_head_of_the_queue_stays(seed, tmp_path):
    """The agents at the head of the corridor queue stay on B."""
    result = _run(_corridor(tmp_path), seed, w_queue=1.0)
    try:
        k_of = {int(r["agent_id"]): int(r["spawn_index"]) for r in result.exit_history}
        switchers = {
            k_of[int(r["agent_id"])]
            for r in result.route_history
            if r["reason"] == "congestion"
        }
        assert switchers
        assert min(switchers) > 10
    finally:
        result.cleanup()


def test_the_index_is_not_built_at_the_default_queue_weight(monkeypatch):
    """The default path pays nothing: no index exists while w_queue is 0."""

    def refuse(*args, **kwargs):
        raise AssertionError("ExitQueueIndex built with w_queue = 0")

    monkeypatch.setattr("pyfds_evac.core.scenario.ExitQueueIndex", refuse)
    result = _run(_t_junction(), 1, w_queue=0.0)
    result.cleanup()
