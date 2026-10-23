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

Fire variant (exit made unavailable by smoke, issue #850). No schedule is
set. A step field of extinction K = 5 /m, switched on at t_on = 1 s, fills
the strip x <= 2 m over the full room height and the exit-1 door. The agent
is at x in [3.5, 4.5] at t_on, outside the strip, so it never walks in smoke
and its speed is unchanged.

- Route cost under the gate model is tau = K * L, with L the smoke length on
  the way to the exit node, here 2.0 to 2.5 m: tau_1 = 10 to 12.5. The
  refusal limit is tau_max = 6 and the switch margin is 0.6. tau_2 = 0,
  so exit 1 is refused and exit 2 is cleaner by far more than 0.6.
- The reroute pass runs every 1 s, so the switch falls in
  t_on <= t <= t_on + 1 s + 0.02 s (stagger offset and one step).
- With anticipation off the agent first heads for exit 1, as in the control,
  and switches (``smoke_reroute``). With the default anticipation the
  router reads the prescribed field at the arrival time, sees the smoke at
  the first choice and heads for exit 2 from the start: no switch is
  recorded. In both readings exit 1 is not used.
- The field is sampled every 0.25 m, so tau is within about 2 K * 0.25 m of
  the hand value, well inside the margins above.

Constraints. A schedule (``closed_after_s``) acts only through routing: it
needs rerouting (a ``RerouteConfig``, or a run that re-decides at the
one-second check) and agents routed by pyFDS-Evac. Agents that follow a
journey are rejected when a schedule is set. This test uses a routed agent.
"""

from __future__ import annotations

import pytest
from shapely.geometry import box

from pyfds_evac.core.route_graph import RerouteConfig, RouteCostConfig
from pyfds_evac.core.scenario import Scenario, run_scenario
from pyfds_evac.core.smoke_speed import SmokeSpeedConfig, SmokeSpeedModel

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
SMOKE_K_PER_M = 5.0
SMOKE_ON_S = 1.0
SMOKE_X_MAX_M = 2.0
REROUTE_INTERVAL_S = 1.0
# Stagger offset of the single agent plus one step.
SWITCH_SLACK_S = 0.02


class _BoxSmoke:
    """Step extinction field: K inside the box from ``t_on`` on, else 0."""

    def __init__(self, x_max: float, k: float, t_on: float) -> None:
        self.x_max = x_max
        self.k = k
        self.t_on = t_on

    def sample_extinction(self, t: float, x: float, y: float) -> float:
        inside = -EXIT_DEPTH_M <= x <= self.x_max and -1.0 <= y <= ROOM_LENGTH_M + 1.0
        return self.k if t >= self.t_on and inside else 0.0


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


def test_control_without_closure_leaves_by_exit_1():
    """Same seed and start as the closure run, which heads for exit 1 first."""
    run = _run({})
    assert run["evacuated"] == 1
    assert run["remaining"] == 0
    assert run["exits"] == ["exit_1"]
    assert not [r for r in run["routes"] if r["reason"] == "exit_closed"]


def _run_smoke(anticipate: bool) -> dict:
    field = _BoxSmoke(SMOKE_X_MAX_M, SMOKE_K_PER_M, SMOKE_ON_S)
    model = SmokeSpeedModel(
        field,
        SmokeSpeedConfig(fds_dir=".", speed_law="lund", update_interval_s=1.0),
    )
    reroute = RerouteConfig(
        reevaluation_interval_s=REROUTE_INTERVAL_S,
        cost_config=RouteCostConfig.from_routing_params(
            {"sampling_step_m": 0.25, "anticipate": anticipate}
        ),
    )
    result = run_scenario(
        _scenario({}), seed=SEED, reroute_config=reroute, smoke_speed_model=model
    )
    try:
        x = result.trajectory_dataframe().sort_values(["id", "frame"])["x"]
        return {
            "exits": [r["exit_id"] for r in result.exit_history or []],
            "routes": list(result.route_history or []),
            "evacuated": result.agents_evacuated,
            "x_start": float(x.iloc[0]),
            "x_min": float(x.min()),
        }
    finally:
        result.cleanup()


def test_smoke_makes_exit_1_unavailable_without_anticipation():
    run = _run_smoke(anticipate=False)
    assert run["evacuated"] == 1
    assert run["exits"] == ["exit_2"]
    assert not [r for r in run["routes"] if r["reason"] == "exit_closed"]
    smoke = [r for r in run["routes"] if r["reason"] == "smoke_reroute"]
    assert [(r["old_exit"], r["new_exit"]) for r in smoke] == [("exit_1", "exit_2")]
    latest = SMOKE_ON_S + REROUTE_INTERVAL_S + SWITCH_SLACK_S
    assert SMOKE_ON_S <= smoke[0]["time_s"] <= latest
    # The switch comes from the smoke: the same seed without smoke picks exit 1.
    assert _run({})["exits"] == ["exit_1"]


def test_smoke_makes_exit_1_unavailable_with_default_anticipation():
    run = _run_smoke(anticipate=True)
    assert run["evacuated"] == 1
    assert run["exits"] == ["exit_2"]
    # The spawn choice writes no row and the agent never walks towards exit 1.
    assert run["routes"] == []
    assert run["x_min"] >= run["x_start"] - 0.1
