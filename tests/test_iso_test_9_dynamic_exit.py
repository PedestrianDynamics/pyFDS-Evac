"""ISO 20414:2020 Test 9 (Table 10): dynamic availability of an exit.

Setup of the test: one occupant with pre-evacuation time 0 s and a constant
walking speed of 1 m/s stands in a 10 m x 15 m room with two exits of 1 m
width, each the same distance from the occupant. Exit 1 becomes unavailable
after 1 s. Expected result: exit 1 is not used.

Here the room is 10 m wide (x) and 15 m long (y). Exit 1 is the west door and
exit 2 the east door, both centred at y = 7.5 m, and the occupant starts at
the centre (5 m, 7.5 m), 5 m from each door. The spawn area is 1 m x 1 m
around the centre (the placement needs room for the 0.2 m radius), so the two
doors are equidistant only to within 0.5 m; the fixed seed picks one start.

Hand derivation of the expected values:

- Before the closure the two doors are 5 m away, 5 s of walking at 1 m/s.
- At t = 1 s the occupant has walked 1 m. If it was heading for exit 1 it
  stands 4 m from that door and 6 m from exit 2.
- From then on exit 1 admits nobody, so the only door left to leave through
  is exit 2, at most 6 m away: the occupant leaves by about t = 1 s + 6 s +
  the 1 s reroute check = 8 s, far inside MAX_TIME_S.
- Exit 1 usage is the number of occupants leaving by it: 0 of 1. Evacuated
  occupants: 1 of 1.

Constraints. A schedule (``closed_after_s``) acts only through routing: it
needs rerouting (a ``RerouteConfig``, or a run that re-decides at the
one-second check) and agents routed by pyFDS-Evac. Agents that follow a
journey are rejected when a schedule is set. This test uses a routed agent.
"""

from __future__ import annotations

import pytest
from shapely.geometry import box

from pyfds_evac.core.route_graph import RerouteConfig
from pyfds_evac.core.scenario import Scenario, run_scenario

pytestmark = pytest.mark.iso20414

ROOM_WIDTH_M = 10.0
ROOM_LENGTH_M = 15.0
EXIT_WIDTH_M = 1.0
EXIT_DEPTH_M = 1.0
SPEED_MPS = 1.0
T_CLOSE_S = 1.0
MAX_TIME_S = 40.0
SEED = 1
REROUTE = RerouteConfig(reevaluation_interval_s=30.0)
START = (ROOM_WIDTH_M / 2.0, ROOM_LENGTH_M / 2.0)
# Half the side of the spawn area around the centre.
START_AREA_M = 0.5


def _coords(polygon) -> list[list[float]]:
    return [[x, y] for x, y in polygon.exterior.coords]


def _doors() -> dict[str, object]:
    lo = ROOM_LENGTH_M / 2.0 - EXIT_WIDTH_M / 2.0
    hi = ROOM_LENGTH_M / 2.0 + EXIT_WIDTH_M / 2.0
    return {
        "exit_1": box(-EXIT_DEPTH_M, lo, 0.0, hi),
        "exit_2": box(ROOM_WIDTH_M, lo, ROOM_WIDTH_M + EXIT_DEPTH_M, hi),
    }


def _scenario(exit_1_schedule: dict) -> Scenario:
    doors = _doors()
    walkable = box(0.0, 0.0, ROOM_WIDTH_M, ROOM_LENGTH_M)
    for door in doors.values():
        walkable = walkable.union(door)
    exits = {
        name: {
            "type": "polygon",
            "coordinates": _coords(poly),
            "enable_throughput_throttling": False,
            "max_throughput": 0,
            **(exit_1_schedule if name == "exit_1" else {}),
        }
        for name, poly in doors.items()
    }
    x, y = START
    start = box(x - START_AREA_M, y - START_AREA_M, x + START_AREA_M, y + START_AREA_M)
    sim_params = {
        "max_simulation_time": MAX_TIME_S,
        "model_type": "CollisionFreeSpeedModel",
    }
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
        "exits": exits,
        "distributions": {
            "occupant": {
                "type": "polygon",
                "coordinates": _coords(start),
                "parameters": {
                    "number": 1,
                    "radius": 0.2,
                    "v0": SPEED_MPS,
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
    return Scenario(
        raw=raw,
        walkable_area_wkt=walkable.wkt,
        model_type="CollisionFreeSpeedModel",
        seed=SEED,
        sim_params=sim_params,
        source_path=None,
    )


def _run(exit_1_schedule: dict) -> dict:
    result = run_scenario(_scenario(exit_1_schedule), seed=SEED, reroute_config=REROUTE)
    try:
        return {
            "exits": [r["exit_id"] for r in result.exit_history or []],
            "routes": list(result.route_history or []),
            "evacuated": result.agents_evacuated,
            "remaining": result.agents_remaining,
        }
    finally:
        result.cleanup()


def test_exit_1_unavailable_after_1_s_is_not_used():
    run = _run({"closed_after_s": T_CLOSE_S})
    assert run["evacuated"] == 1
    assert run["remaining"] == 0
    assert run["exits"].count("exit_1") == 0
    assert run["exits"] == ["exit_2"]
    closed = [r for r in run["routes"] if r["reason"] == "exit_closed"]
    assert [(r["old_exit"], r["new_exit"]) for r in closed] == [("exit_1", "exit_2")]
    assert T_CLOSE_S <= closed[0]["time_s"] <= T_CLOSE_S + 1.0


def test_control_without_closure_leaves_by_one_of_the_two_exits():
    run = _run({})
    assert run["evacuated"] == 1
    assert run["remaining"] == 0
    assert len(run["exits"]) == 1
    assert run["exits"][0] in {"exit_1", "exit_2"}
    assert not [r for r in run["routes"] if r["reason"] == "exit_closed"]
