"""NIST TN 1822 Verif.4.1: dynamic availability of exits, NIST's layout.

Ronchi et al. (2013), Verif.4.1: a room 10 m by 15 m, two exits 1 m wide on the
15 m walls and equally distant from the 10 m wall at the end of the room
(Figure 11), one occupant with pre-evacuation time 0 s and a constant walking
speed of 1 m/s, near the middle of the 10 m wall opposite the exits. Exit 1
becomes unavailable after 1 s. Expected result: exit 1 is not used.

ISO 20414 Test 9 is the same test, but the ISO test module puts the occupant
5 m from each door. NIST's layout puts both doors at the far end, so the
occupant is far from them when exit 1 closes. Figure 11 carries no dimension
for the doors; Figure 10 (Verif.3.3, report p. 35) shows the same 10 m x 15 m
room and the same occupant spot and labels the doors 12 m from the occupant's
wall, which is the distance used here. ``test_iso_test_9_dynamic_exit.py`` runs
the ISO layout.

Layout, in metres: the room is x in [0, 10], y in [0, 15]. The doors are on the
15 m walls (x = 0 and x = 10), centred at y = 12 (spans 11.5 to 12.5). The
occupant starts in a 1 m x 1 m area centred at (5, 1), so the two doors are
equidistant to within 0.5 m (the area needs room for the 0.2 m radius); the
fixed seed picks one start.

Hand derivation of the expected values
--------------------------------------

- Door centres are (0, 12) and (10, 12). From the area centre (5, 1) each is
  sqrt(5^2 + 11^2) = sqrt(146) = 12.08 m away: 12.1 s of walking at 1 m/s.
- At t = 1 s the occupant has walked 1 m toward exit 1 (the nearer door for
  this seed, see the control), to about (4.59, 1.91): 11.08 m from exit 1 and
  sqrt(5.41^2 + 10.09^2) = sqrt(131.1) = 11.45 m from exit 2.
- A schedule is event-driven: the route change is made at the closure, and is
  recorded at t = 1.0 s, not at a later reroute check. From then on the only
  door left is exit 2, so the occupant is out at about 1 + 11.45 = 12.45 s.
- Window: the hand values use the centre of the 1 m x 1 m start area. The start
  can lie 0.5 m away in each coordinate, which changes the path by up to about
  0.5 m (0.5 s), and the occupant counts as out at the door line, within the
  0.2 m radius and 1 m door depth, a further few tenths of a second. The window
  is the hand value +- 1 s: 11.45 s to 13.45 s for the closure run, and for
  the control (12.08 s to exit 1, no closure) 11.08 s to 13.08 s.
- Exit 1 usage is the number of occupants leaving by it: 0 of 1. Evacuated
  occupants: 1 of 1.
"""

from __future__ import annotations

import pytest
from shapely.geometry import box

from pyfds_evac.core.route_graph import RerouteConfig
from pyfds_evac.core.scenario import Scenario, run_scenario

pytestmark = pytest.mark.nist_tn1822

ROOM_WIDTH_M = 10.0
ROOM_LENGTH_M = 15.0
EXIT_WIDTH_M = 1.0
EXIT_DEPTH_M = 1.0
DOOR_CENTRE_Y_M = 12.0
SPEED_MPS = 1.0
T_CLOSE_S = 1.0
MAX_TIME_S = 60.0
SEED = 1
REROUTE = RerouteConfig(reevaluation_interval_s=30.0)
START = (ROOM_WIDTH_M / 2.0, 1.0)
START_AREA_M = 0.5
# Hand values for the evacuation time, see the module docstring.
HAND_CLOSURE_S = 1.0 + 11.45
HAND_CONTROL_S = 12.08
WINDOW_S = 1.0


def _coords(polygon) -> list[list[float]]:
    return [[x, y] for x, y in polygon.exterior.coords]


def _doors() -> dict[str, object]:
    lo = DOOR_CENTRE_Y_M - EXIT_WIDTH_M / 2.0
    hi = DOOR_CENTRE_Y_M + EXIT_WIDTH_M / 2.0
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
            "time_s": result.evacuation_time,
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
    assert closed[0]["time_s"] == pytest.approx(T_CLOSE_S, abs=0.1)
    assert run["time_s"] == pytest.approx(HAND_CLOSURE_S, abs=WINDOW_S)


def test_control_without_closure_leaves_by_exit_1():
    """Same seed and start as the closure run, which heads for exit 1 first."""
    run = _run({})
    assert run["evacuated"] == 1
    assert run["remaining"] == 0
    assert run["exits"] == ["exit_1"]
    assert not [r for r in run["routes"] if r["reason"] == "exit_closed"]
    assert run["time_s"] == pytest.approx(HAND_CONTROL_S, abs=WINDOW_S)
