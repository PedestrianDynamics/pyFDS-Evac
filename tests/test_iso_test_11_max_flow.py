"""ISO 20414:2020 Test 11 (Table 12): maximum flow rate at an exit.

Setup of the test: 100 occupants in an 8 m x 5 m room with an exit of 1 m
width centred on one 5 m wall. The flow over the whole period must not exceed
a pre-defined maximum. The standard reads the test as verification when the
flow is restricted by the user and as validation when it is emergent; the
tester states which. MSC.1/Circ.1238 gives 1.33 persons/m/s as an example.

Here the room is 8 m wide (x) and 5 m long (y); the exit is a 1 m x 1 m door
strip behind the east wall, centred at y = 2.5 m. The 100 occupants start
anywhere in a 7 m x 4 m area (radius 0.15 m) with pre-evacuation time 0 s.
The seed is fixed.

Measured flow: with exit times t_i the specific flow over the whole period is
(N - 1) / (t_last - t_first) / width. The exit time of an occupant is the
time of its last recorded trajectory frame (frames are 0.1 s apart).

Hand derivation of the expected values (not taken from the code under test):

- Limit: 1.33 persons/m/s x 1 m = 1.33 persons/s, one occupant per 0.752 s.
- Throttled run: the 99 intervals between 100 removals last at least
  99 / 1.33 = 74.4 s, so (N - 1) / (t_last - t_first) <= 1.33 p/s. Frame
  quantisation (each time is read to 0.1 s) can move t_last - t_first by at
  most one frame, 0.1 s of 74.4 s = 0.13 %; the upper tolerance is 1 %.
- Lower bound: an exit that throttles to zero, or far below its cap, fails
  the test. The room is dense enough that an occupant waits at the exit
  throughout, so the exit runs at its cap and the measured flow is near
  1.33 p/s. The accepted band is >= 0.95 x the limit (1.26 p/s, a 78.4 s
  evacuation of the 99 intervals). The throttle's interval is quantised to
  the simulation step, which puts the flow about 1 % under the cap, the
  same on every seed; 5 % covers that and rejects a throttle that holds
  occupants 10 % too long.
- Unthrottled run: the emergent reading (validation, not a verification).
  JuPedSim's CollisionFreeSpeedModel gives 3.8-4.1 persons/m/s through
  this exit over seeds 1-5; the measured value is printed and not
  asserted against the limit. Only the evacuation of all 100 occupants is
  asserted.

Measured (seed 1, JuPedSim CollisionFreeSpeedModel): throttled 1.316
p/m/s, unthrottled 3.779 p/m/s.

Default reading: pyFDS-Evac throttles no exit unless
``enable_throughput_throttling`` is set, so the default reading is the
emergent one (throttling off).
"""

from __future__ import annotations

import contextlib
import io
import sqlite3

import pytest
from shapely.geometry import box

from pyfds_evac.core.scenario import Scenario, run_scenario

pytestmark = pytest.mark.iso20414

ROOM_WIDTH_M = 8.0
ROOM_LENGTH_M = 5.0
EXIT_WIDTH_M = 1.0
EXIT_DEPTH_M = 1.0
N_OCCUPANTS = 100
RADIUS_M = 0.15
SPEED_MPS = 1.3
MAX_FLOW_PER_M_S = 1.33
MAX_THROUGHPUT = MAX_FLOW_PER_M_S * EXIT_WIDTH_M
MAX_TIME_S = 200.0
SEED = 1
FRAME_S = 0.1
# Upper tolerance on the flow: frame rounding, 0.13 % at the expected
# evacuation time, rounded up to 1 %.
UPPER_TOLERANCE = 0.01
LOWER_FRACTION = 0.95
START_AREA = box(0.5, 0.5, 7.5, 4.5)


def _coords(polygon) -> list[list[float]]:
    return [[x, y] for x, y in polygon.exterior.coords]


def _scenario(throttled: bool) -> Scenario:
    mid = ROOM_LENGTH_M / 2.0
    door = box(
        ROOM_WIDTH_M,
        mid - EXIT_WIDTH_M / 2.0,
        ROOM_WIDTH_M + EXIT_DEPTH_M,
        mid + EXIT_WIDTH_M / 2.0,
    )
    walkable = box(0.0, 0.0, ROOM_WIDTH_M, ROOM_LENGTH_M).union(door)
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
        "exits": {
            "exit": {
                "type": "polygon",
                "coordinates": _coords(door),
                "enable_throughput_throttling": throttled,
                "max_throughput": MAX_THROUGHPUT if throttled else 0,
            }
        },
        "distributions": {
            "room": {
                "type": "polygon",
                "coordinates": _coords(START_AREA),
                "parameters": {
                    "number": N_OCCUPANTS,
                    "radius": RADIUS_M,
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


def _exit_times(result) -> list[float]:
    """Exit time of each occupant: its last recorded frame, in seconds."""
    with contextlib.closing(sqlite3.connect(result.sqlite_file)) as con:
        rows = con.execute(
            "SELECT id, MAX(frame) FROM trajectory_data GROUP BY id"
        ).fetchall()
    return sorted(frame * FRAME_S for _, frame in rows)


def _run(throttled: bool) -> tuple[int, list[float]]:
    with contextlib.redirect_stdout(io.StringIO()):
        result = run_scenario(_scenario(throttled), seed=SEED)
    try:
        return result.agents_evacuated, _exit_times(result)
    finally:
        result.cleanup()


def _flow_per_m_s(times: list[float]) -> float:
    return (len(times) - 1) / (times[-1] - times[0]) / EXIT_WIDTH_M


def test_throttled_exit_flow_stays_at_the_limit():
    """Verification reading: the user-defined maximum is 1.33 p/m/s."""
    evacuated, times = _run(throttled=True)
    flow = _flow_per_m_s(times)
    print(f"ISO 11 throttled flow: {flow:.3f} p/m/s")
    assert evacuated == N_OCCUPANTS
    assert len(times) == N_OCCUPANTS
    assert flow <= MAX_FLOW_PER_M_S * (1.0 + UPPER_TOLERANCE)
    assert flow >= LOWER_FRACTION * MAX_FLOW_PER_M_S


def test_unthrottled_exit_flow_is_reported_not_asserted():
    """Validation reading: the emergent flow of the movement model."""
    evacuated, times = _run(throttled=False)
    flow = _flow_per_m_s(times)
    print(f"ISO 11 unthrottled (emergent) flow: {flow:.3f} p/m/s")
    assert evacuated == N_OCCUPANTS
