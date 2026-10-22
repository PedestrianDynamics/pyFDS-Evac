"""NIST TN 1822 Verif.4.1: dynamic availability of exits, NIST's layout.

Ronchi et al. (2013), Verif.4.1: a room 10 m by 15 m, two exits 1 m wide on the
15 m walls and equally distant from the 10 m wall at the end of the room
(Figure 11), one occupant with pre-evacuation time 0 s and a constant walking
speed of 1 m/s, near the middle of the 10 m wall opposite the exits. Exit 1
becomes unavailable after 1 s. Expected result: exit 1 is not used.

ISO 20414 Test 9 is the same test, but the ISO test module puts the occupant
5 m from each door. NIST's Figure 11 puts both doors at the far end, about 14 m
away, so the occupant is far from them when exit 1 closes. This module builds
that layout; ``test_iso_test_9_dynamic_exit.py`` runs the ISO one.

Layout, in metres: the room is x in [0, 10], y in [0, 15]. The doors are on the
15 m walls (x = 0 and x = 10), centred at y = 14 (spans 13.5 to 14.5), 1 m from
the end wall at y = 15. The occupant starts in a 1 m x 1 m area centred at
(5, 1), so the two doors are equidistant to within 0.5 m (the area needs room
for the 0.2 m radius); the fixed seed picks one start.

Hand derivation of the expected values
--------------------------------------

- Door centres are (0, 14) and (10, 14). From the area centre (5, 1) each is
  sqrt(5^2 + 13^2) = 13.93 m away, 13.9 s of walking at 1 m/s.
- At t = 1 s the occupant has walked 1 m toward exit 1 (the nearer door for
  this seed, see the control). It stands near (4.64, 1.93): 12.93 m from
  exit 1 and sqrt(5.36^2 + 12.07^2) = 13.2 m from exit 2.
- From the closure on, exit 1 admits nobody. The occupant turns for exit 2 at
  the next one-second check (at most 1 s later) and walks at most 13.2 m: it
  is out by about 1 + 1 + 13.2 = 15.2 s; the start offset (up to 0.5 m in
  each direction) and the door depth (1 m beyond the wall) move this by under
  1.5 s. The window asserted is 12 s to 18 s.
- Without the closure (control) the occupant walks about 13.9 s to exit 1
  and leaves by it, same window.
- Exit 1 usage is the number of occupants leaving by it: 0 of 1. Evacuated
  occupants: 1 of 1. The route change is recorded once, exit_1 to exit_2, at
  the first reroute check at or after the closure (1 s to 2 s).
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
DOOR_CENTRE_Y_M = 14.0
SPEED_MPS = 1.0
T_CLOSE_S = 1.0
MAX_TIME_S = 60.0
SEED = 1
REROUTE = RerouteConfig(reevaluation_interval_s=30.0)
START = (ROOM_WIDTH_M / 2.0, 1.0)
START_AREA_M = 0.5
# Hand window for the evacuation time, see the module docstring.
EVACUATION_WINDOW_S = (12.0, 18.0)


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
    assert T_CLOSE_S <= closed[0]["time_s"] <= T_CLOSE_S + 1.0
    assert EVACUATION_WINDOW_S[0] <= run["time_s"] <= EVACUATION_WINDOW_S[1]


def test_control_without_closure_leaves_by_exit_1():
    """Same seed and start as the closure run, which heads for exit 1 first."""
    run = _run({})
    assert run["evacuated"] == 1
    assert run["remaining"] == 0
    assert run["exits"] == ["exit_1"]
    assert not [r for r in run["routes"] if r["reason"] == "exit_closed"]
    assert EVACUATION_WINDOW_S[0] <= run["time_s"] <= EVACUATION_WINDOW_S[1]
