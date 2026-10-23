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

Smoke variant (#850): the same room under a spatially uniform, constant
extinction K from t = 0 (``ConstantExtinctionField``), with the smoke-speed
model on (update interval 0.1 s, no rerouting), for K = 0.5, 1 and 3 /m and
both speed laws, throttled and unthrottled. Seed 1, v0 = 1.3 m/s.

Hand values of the speed factor f = w / w_free (w_free = 1.3 m/s):

- Lund: f = 1 - 0.057 K / 0.706 = 0.960, 0.919, 0.758.
- Fridolf (A = 2, V = 2 / K): V = 4, 2, 0.667 m. V > 3 m gives no slowing
  (f = 1); w = 1.3 - 0.34 (3 - V) = 0.96 and 0.507 m/s, so f = 1.000
  (K = 0.5), 0.738 and 0.390.

Derivations of the assertions:

- Throttled: the throttle is a time gate at the exit, independent of the
  walking speed. It releases one occupant per 1 / 1.33 s as long as someone
  waits at the door. The walking speed only needs to keep the door
  supplied, which holds because the unthrottled flow is at least 2.1 p/s,
  above the cap, at every K. The flow is therefore min(cap, unthrottled
  flow) = cap, the same band as in clear air. If the slowing were counted
  twice (once in the speed, once in the gate), the flow would be about
  f x cap: 0.52 p/s for Fridolf K = 3, 0.98 for Fridolf K = 1, 1.01 for
  Lund K = 3, all below the lower bound of 1.26 p/s.
- Fridolf K = 0.5 has f = 1, so the smoke changes no speed and the sorted
  exit times equal the clear-air run to one frame (null check).
- Unthrottled: with r = flow(K) / flow(0) at the same seed, a flow set by
  the walking speed alone would give r = f. A crowd at a 1 m door is limited
  partly by congestion at the door, which does not depend on the free
  speed, so r lies between f and 1: r >= 0.95 f (the band for the single
  seed) and r <= 1.05, and the flow decreases with K, by less than f. The
  1-D estimate of r is not asserted.

Measured (seed 1): see the printed lines of the run (``pytest -s``) and
the ISO 20414 verification page.

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
from pyfds_evac.core.smoke_speed import (
    ConstantExtinctionField,
    SmokeSpeedConfig,
    SmokeSpeedModel,
)

pytestmark = [pytest.mark.iso20414, pytest.mark.nist_tn1822]

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


def _run(throttled: bool, smoke=None) -> tuple[int, list[float]]:
    with contextlib.redirect_stdout(io.StringIO()):
        result = run_scenario(_scenario(throttled), seed=SEED, smoke_speed_model=smoke)
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


# --- Smoke variant (#850) -------------------------------------------------

EXTINCTIONS_PER_M = (0.5, 1.0, 3.0)
SPEED_LAWS = ("lund", "fridolf")
# Hand values of the speed factor (see the module docstring).
SPEED_FACTOR = {
    ("lund", 0.5): 0.960,
    ("lund", 1.0): 0.919,
    ("lund", 3.0): 0.758,
    ("fridolf", 0.5): 1.000,
    ("fridolf", 1.0): 0.738,
    ("fridolf", 3.0): 0.390,
}
# r = flow(K) / flow(0) may exceed 1 by this much (single seed).
R_UPPER = 1.05
R_LOWER_FRACTION = 0.95
CONGESTION_MARGIN = 0.05
SMOKE_RUNS = [
    (law, k, throttled)
    for law in SPEED_LAWS
    for k in EXTINCTIONS_PER_M
    for throttled in (True, False)
]


def _smoke_model(law: str, extinction: float) -> SmokeSpeedModel:
    config = SmokeSpeedConfig(fds_dir=".", speed_law=law, update_interval_s=0.1)
    return SmokeSpeedModel(ConstantExtinctionField(extinction), config)


@pytest.fixture(scope="module")
def clear_air() -> dict[bool, list[float]]:
    return {throttled: _run(throttled)[1] for throttled in (True, False)}


@pytest.fixture(scope="module")
def smoke_runs() -> dict[tuple[str, float, bool], tuple[int, list[float]]]:
    return {
        (law, k, throttled): _run(throttled, _smoke_model(law, k))
        for law, k, throttled in SMOKE_RUNS
    }


@pytest.mark.parametrize(("law", "k", "throttled"), SMOKE_RUNS)
def test_smoke_runs_evacuate_everyone(smoke_runs, law, k, throttled):
    evacuated, times = smoke_runs[(law, k, throttled)]
    assert evacuated == N_OCCUPANTS
    assert len(times) == N_OCCUPANTS


@pytest.mark.parametrize("k", EXTINCTIONS_PER_M)
@pytest.mark.parametrize("law", SPEED_LAWS)
def test_smoke_throttled_flow_stays_at_the_limit(smoke_runs, clear_air, law, k):
    """The cap holds under smoke and is not counted twice."""
    flow = _flow_per_m_s(smoke_runs[(law, k, True)][1])
    clear = _flow_per_m_s(clear_air[True])
    print(f"ISO 11 smoke {law} K={k} throttled: {flow:.3f} p/m/s")
    assert flow <= MAX_FLOW_PER_M_S * (1.0 + UPPER_TOLERANCE)
    assert flow >= LOWER_FRACTION * MAX_FLOW_PER_M_S
    assert flow == pytest.approx(clear, rel=UPPER_TOLERANCE)


@pytest.mark.parametrize("throttled", (True, False))
def test_smoke_without_slowing_leaves_clear_air_exit_times(
    smoke_runs, clear_air, throttled
):
    """Fridolf at K = 0.5 /m has V > 3 m: f = 1, so nothing changes."""
    times = smoke_runs[("fridolf", 0.5, throttled)][1]
    assert times == pytest.approx(clear_air[throttled], abs=FRAME_S)


@pytest.mark.parametrize("law", SPEED_LAWS)
def test_smoke_unthrottled_flow_drops_by_less_than_the_speed_factor(
    smoke_runs, clear_air, law
):
    clear = _flow_per_m_s(clear_air[False])
    ratios = []
    for k in EXTINCTIONS_PER_M:
        f = SPEED_FACTOR[(law, k)]
        r = _flow_per_m_s(smoke_runs[(law, k, False)][1]) / clear
        kind = (
            "free-flow-limited"
            if abs(r - f) <= CONGESTION_MARGIN
            else "congestion-limited"
            if r > f
            else "below f"
        )
        print(f"ISO 11 smoke {law} K={k} unthrottled: r={r:.3f} f={f:.3f} {kind}")
        assert R_LOWER_FRACTION * f <= r <= R_UPPER
        ratios.append(r)
    # Flow decreases with K, and at the largest K by less than f.
    assert ratios[-1] < ratios[0] + 1e-9
    assert ratios[-1] < 1.0
    assert ratios[-1] > SPEED_FACTOR[(law, EXTINCTIONS_PER_M[-1])]
