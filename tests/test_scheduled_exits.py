"""Exits that open and close on a schedule (issue #373).

An exit with ``open_from_s`` or ``closed_after_s`` accepts agents only while
``open_from_s <= t < closed_after_s``. A closed exit removes nobody, and the
agents heading for it re-decide through the reroute pass, on the exits they
know.

The scenario is synthetic: a 30 x 10 m room with one door in the west wall
and its mirror in the east wall, and one spawn area covering the room.
"""

from __future__ import annotations

import contextlib
import math
import sqlite3

import pytest
from shapely.geometry import Point, Polygon, box

from pyfds_evac.core.route_graph import (
    RerouteConfig,
    StageGraph,
    StageNode,
    without_closed_stages,
)
from pyfds_evac.core.scenario import Scenario, run_scenario

LENGTH_M = 30.0
WIDTH_M = 10.0
DOOR_M = 1.0
DOOR_DEPTH_M = 1.0
NUM_AGENTS = 40
SEED = 7
T_CLOSE_S = 4.0
T_OPEN_S = 8.0
MAX_TIME_S = 90.0
# Agents are removed inside the door polygon, so their last recorded position
# lies within this distance of the door they left through.
AT_DOOR_M = 0.5
# One trajectory frame of slack around a schedule time.
FRAME_S = 0.1
# A long interval: a closure must not wait for the regular re-evaluation.
REROUTE = RerouteConfig(reevaluation_interval_s=30.0)


def _door(west: bool) -> Polygon:
    lo, hi = WIDTH_M / 2.0 - DOOR_M / 2.0, WIDTH_M / 2.0 + DOOR_M / 2.0
    if west:
        return box(-DOOR_DEPTH_M, lo, 0.0, hi)
    return box(LENGTH_M, lo, LENGTH_M + DOOR_DEPTH_M, hi)


DOORS = {"west": _door(True), "east": _door(False)}


def _coords(polygon: Polygon) -> list[list[float]]:
    return [[x, y] for x, y in polygon.exterior.coords]


def _scenario(schedules: dict[str, dict], **dist_params) -> Scenario:
    walkable = box(0.0, 0.0, LENGTH_M, WIDTH_M).union(DOORS["west"])
    walkable = walkable.union(DOORS["east"])
    exits = {
        name: {
            "type": "polygon",
            "coordinates": _coords(poly),
            "enable_throughput_throttling": False,
            "max_throughput": 0,
            **schedules.get(name, {}),
        }
        for name, poly in DOORS.items()
    }
    raw = {
        "project_version": "2.0",
        "config": {
            "simulation_settings": {
                "simulationParams": {
                    "max_simulation_time": MAX_TIME_S,
                    "model_type": "CollisionFreeSpeedModel",
                },
                "numberOfSimulations": 1,
                "baseSeed": SEED,
            },
            "ui_state": {"useShortestPaths": False},
        },
        "exits": exits,
        "distributions": {
            "room": {
                "type": "polygon",
                "coordinates": _coords(box(0.3, 0.3, LENGTH_M - 0.3, WIDTH_M - 0.3)),
                "parameters": {
                    "number": NUM_AGENTS,
                    "radius": 0.2,
                    "v0": 1.2,
                    "use_flow_spawning": False,
                    "distribution_mode": "by_number",
                    "use_premovement": False,
                    "radius_distribution": "constant",
                    "v0_distribution": "constant",
                    **dist_params,
                },
            }
        },
        "checkpoints": {},
        "zones": {},
        "journeys": [],
        "transitions": [],
    }
    sim_params = raw["config"]["simulation_settings"]["simulationParams"]
    return Scenario(
        raw=raw,
        walkable_area_wkt=walkable.wkt,
        model_type="CollisionFreeSpeedModel",
        seed=SEED,
        sim_params=sim_params,
        source_path=None,
    )


def _departures(result) -> list[tuple[float, str | None]]:
    """Each agent's last recorded time and the door it stood in, if any."""
    with contextlib.closing(sqlite3.connect(result.sqlite_file)) as con:
        fps = float(
            con.execute("SELECT value FROM metadata WHERE key='fps'").fetchone()[0]
        )
        rows = con.execute(
            "SELECT id, frame, pos_x, pos_y FROM trajectory_data ORDER BY frame"
        ).fetchall()
    last = {agent_id: (frame, x, y) for agent_id, frame, x, y in rows}
    out = []
    for frame, x, y in last.values():
        door = next(
            (n for n, p in DOORS.items() if p.distance(Point(x, y)) <= AT_DOOR_M),
            None,
        )
        out.append((frame / fps, door))
    return out


def _run(scenario: Scenario, **kwargs) -> dict:
    result = run_scenario(scenario, seed=SEED, **kwargs)
    try:
        return {
            "departures": _departures(result),
            "routes": list(result.route_history or []),
            "evacuated": result.agents_evacuated,
            "remaining": result.agents_remaining,
        }
    finally:
        result.cleanup()


@pytest.fixture(scope="module")
def closing_run() -> dict:
    """The west door closes at T_CLOSE_S."""
    scenario = _scenario({"west": {"closed_after_s": T_CLOSE_S}})
    return _run(scenario, reroute_config=REROUTE)


def test_closed_exit_removes_nobody_after_closing(closing_run):
    late = [t for t, door in closing_run["departures"] if door == "west"]
    assert late, "nobody left by the west door before it closed"
    assert max(late) <= T_CLOSE_S + FRAME_S


def test_agents_heading_for_closed_exit_reroute(closing_run):
    closed = [r for r in closing_run["routes"] if r["reason"] == "exit_closed"]
    assert closed
    assert {(r["old_exit"], r["new_exit"]) for r in closed} == {("west", "east")}
    # The closure is acted on at the next one-second reroute check, not after
    # the 30 s re-evaluation interval.
    assert all(T_CLOSE_S <= r["time_s"] <= T_CLOSE_S + 1.0 for r in closed)
    assert not [
        r
        for r in closing_run["routes"]
        if r["new_exit"] == "west" and r["time_s"] >= T_CLOSE_S
    ]


def test_everyone_leaves_by_the_open_exit(closing_run):
    assert closing_run["evacuated"] == NUM_AGENTS
    assert closing_run["remaining"] == 0


def test_exit_opens_on_schedule():
    scenario = _scenario({"east": {"open_from_s": T_OPEN_S}})
    run = _run(scenario, reroute_config=REROUTE)
    east = [t for t, door in run["departures"] if door == "east"]
    assert all(t >= T_OPEN_S for t in east)
    assert run["evacuated"] == NUM_AGENTS


def test_agent_knowing_only_the_closed_exit_learns_no_other():
    """Familiarity holds: a closed entrance does not reveal the other door."""
    scenario = _scenario(
        {"west": {"closed_after_s": T_CLOSE_S}}, familiarity=0.0, entrance="west"
    )
    run = _run(scenario, reroute_config=REROUTE)
    doors = [(t, door) for t, door in run["departures"] if t < MAX_TIME_S - 1.0]
    assert all(door == "west" and t <= T_CLOSE_S + FRAME_S for t, door in doors)
    assert run["remaining"] > 0


def test_unscheduled_exits_are_always_open():
    node = StageNode("e", 0.0, 0.0, "exit")
    assert node.is_open(0.0) and node.is_open(1e9)
    graph = StageGraph(nodes={"e": node})
    assert without_closed_stages(graph, 5.0) is graph


def test_schedule_window_is_half_open():
    node = StageNode("e", 0.0, 0.0, "exit", open_from_s=2.0, closed_after_s=5.0)
    assert [node.is_open(t) for t in (1.99, 2.0, 4.99, 5.0)] == [
        False,
        True,
        True,
        False,
    ]


@pytest.mark.parametrize(
    "schedule, match",
    [
        ({"closed_after_s": -1.0}, "closed_after_s must be finite and >= 0"),
        ({"open_from_s": math.inf}, "open_from_s must be finite and >= 0"),
        ({"open_from_s": "5"}, "open_from_s must be a number"),
        ({"open_from_s": True}, "open_from_s must be a number"),
        (
            {"open_from_s": 5.0, "closed_after_s": 5.0},
            "closed_after_s must be greater than open_from_s",
        ),
    ],
)
def test_invalid_schedule_is_rejected(schedule, match):
    with pytest.raises(ValueError, match=match):
        run_scenario(_scenario({"west": schedule}), reroute_config=REROUTE)


@pytest.mark.parametrize("kwargs", [{}, {"smoke_blind": True}])
def test_schedule_without_rerouting_is_rejected(kwargs):
    scenario = _scenario({"west": {"closed_after_s": T_CLOSE_S}})
    with pytest.raises(ValueError, match="need rerouting"):
        run_scenario(scenario, **kwargs)


def test_journey_agent_with_schedule_is_rejected():
    """An agent on a JuPedSim journey leaves by a JuPedSim exit stage."""
    scenario = _scenario({"west": {"closed_after_s": T_CLOSE_S}})
    raw = scenario.raw
    room = raw["distributions"].pop("room")
    lobby = {
        "type": "polygon",
        "coordinates": _coords(box(20.0, 1.0, 25.0, 4.0)),
        "parameters": dict(room["parameters"], number=5),
    }
    # Journeys name spawn areas by the editor's "jps-distributions_" ids.
    raw["distributions"] = {"jps-distributions_0": room, "jps-distributions_1": lobby}
    raw["journeys"] = [{"id": "j0", "stages": ["jps-distributions_0", "east"]}]
    raw["transitions"] = [
        {"from": "jps-distributions_0", "to": "east", "journey_id": "j0"}
    ]
    with pytest.raises(ValueError, match="walks a JuPedSim journey"):
        run_scenario(scenario, reroute_config=REROUTE)
