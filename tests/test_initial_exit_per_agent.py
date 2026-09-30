"""The opening exit is ranked from each agent's position, not its spawn area.

Issue #350: ``_assign_initial_exit`` ranked the exits from the spawn area's
graph node, so every agent of one spawn area took the same exit, including
agents standing next to the other door.

The scenario is synthetic: a 30 x 10 m room, one door in the west wall and
its mirror in the east wall, and one spawn area covering the room. Shortest
paths should split the crowd between the doors.
"""

from __future__ import annotations

import contextlib
import sqlite3

import pytest
from shapely.geometry import Point, Polygon, box

from pyfds_evac.core.scenario import Scenario, run_scenario

LENGTH_M = 30.0
WIDTH_M = 10.0
DOOR_M = 1.0
DOOR_DEPTH_M = 1.0
NUM_AGENTS = 100
SEED = 11
NEAR_DOOR_M = 2.0


def _door(west: bool) -> Polygon:
    lo, hi = WIDTH_M / 2.0 - DOOR_M / 2.0, WIDTH_M / 2.0 + DOOR_M / 2.0
    if west:
        return box(-DOOR_DEPTH_M, lo, 0.0, hi)
    return box(LENGTH_M, lo, LENGTH_M + DOOR_DEPTH_M, hi)


DOORS = {"west": _door(True), "east": _door(False)}


def _coords(polygon: Polygon) -> list[list[float]]:
    return [[x, y] for x, y in polygon.exterior.coords]


def _exit(polygon: Polygon) -> dict:
    return {
        "type": "polygon",
        "coordinates": _coords(polygon),
        "enable_throughput_throttling": False,
        "max_throughput": 0,
    }


def _room_scenario() -> Scenario:
    walkable = box(0.0, 0.0, LENGTH_M, WIDTH_M).union(DOORS["west"])
    walkable = walkable.union(DOORS["east"])
    raw = {
        "project_version": "2.0",
        "config": {
            "simulation_settings": {
                "simulationParams": {
                    "max_simulation_time": 1.0,
                    "model_type": "CollisionFreeSpeedModel",
                },
                "numberOfSimulations": 1,
                "baseSeed": SEED,
            },
            "ui_state": {"useShortestPaths": False},
        },
        "exits": {name: _exit(poly) for name, poly in DOORS.items()},
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


def _first_positions(sqlite_file: str) -> dict[int, tuple[float, float]]:
    with contextlib.closing(sqlite3.connect(sqlite_file)) as con:
        rows = con.execute(
            "SELECT id, pos_x, pos_y FROM trajectory_data "
            "WHERE frame = (SELECT MIN(frame) FROM trajectory_data)"
        ).fetchall()
    return {agent_id: (x, y) for agent_id, x, y in rows}


@pytest.fixture(scope="module")
def choices() -> list[tuple[tuple[float, float], str]]:
    """Each agent's start position and the exit it was sent to."""
    result = run_scenario(_room_scenario(), seed=SEED)
    try:
        start = _first_positions(result.sqlite_file)
        exits = {r["agent_id"]: r["exit_id"] for r in result.exit_history}
    finally:
        result.cleanup()
    return [(start[aid], exit_id) for aid, exit_id in exits.items()]


def _exit_name(exit_id: str) -> str:
    return next(name for name in DOORS if exit_id.endswith(name))


def test_every_agent_gets_an_exit(choices):
    assert len(choices) == NUM_AGENTS


def test_crowd_splits_between_mirrored_doors(choices):
    west = sum(_exit_name(e) == "west" for _, e in choices)
    assert 0.35 * NUM_AGENTS <= west <= 0.65 * NUM_AGENTS


def test_agent_beside_a_door_takes_it(choices):
    wrong = [
        (pos, name)
        for pos, exit_id in choices
        for name, door in DOORS.items()
        if door.distance(Point(pos)) <= NEAR_DOOR_M and _exit_name(exit_id) != name
    ]
    assert not wrong, f"agents beside a door sent to the other one: {wrong}"
