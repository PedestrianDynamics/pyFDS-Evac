"""Exit throughput throttling caps the removal rate (issue #355).

With ``enable_throughput_throttling`` on, an agent that reaches the exit is
removed only if at least 1/``max_throughput`` s have passed since the last
removal there; otherwise it waits. This caps the rate; it is not a door
flow model.

The deck is synthetic and hand-checkable: a 10 x 10 m room, a 2 m exit in
the east wall, N = 20 agents spawned next to it, so that without the cap
they reach the exit faster than the cap allows. At a cap of r agents/s:

* every agent leaves;
* consecutive removals are at least 1/r s apart;
* the last removal comes at least (N - 1)/r s after the first.

Removal times are read from the trajectories: an agent is removed within one
frame of its last recorded position, so each bound is relaxed by one frame.
"""

from __future__ import annotations

import contextlib
import io
import sqlite3

import pytest
from shapely.geometry import Polygon, box

from pyfds_evac.core.scenario import Scenario, run_scenario

SEED = 7
NUM_AGENTS = 20
MAX_TIME_S = 120.0
WALKABLE = box(0.0, 0.0, 10.0, 10.0)
EXIT = box(9.8, 4.0, 10.0, 6.0)
SPAWN = box(6.0, 1.0, 9.4, 9.0)
D = "jps-distributions_0"


def _coords(polygon: Polygon) -> list[list[float]]:
    return [[x, y] for x, y in polygon.exterior.coords]


def _scenario(enabled: bool, max_throughput: float) -> Scenario:
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
        "exits": {
            "E": {
                "type": "polygon",
                "coordinates": _coords(EXIT),
                "enable_throughput_throttling": enabled,
                "max_throughput": max_throughput,
            }
        },
        "distributions": {
            D: {
                "type": "polygon",
                "coordinates": _coords(SPAWN),
                "parameters": {
                    "number": NUM_AGENTS,
                    "radius": 0.15,
                    "v0": 1.3,
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
        "journeys": [{"id": "J", "stages": [D, "E"]}],
        "transitions": [{"from": D, "to": "E", "journey_id": "J"}],
    }
    return Scenario(
        raw=raw,
        walkable_area_wkt=WALKABLE.wkt,
        model_type="CollisionFreeSpeedModel",
        seed=SEED,
        sim_params=raw["config"]["simulation_settings"]["simulationParams"],
        source_path=None,
    )


def _removal_times(enabled: bool, max_throughput: float) -> tuple[list[float], float]:
    """Sorted last-frame times of every agent, and the frame interval [s]."""
    with contextlib.redirect_stdout(io.StringIO()):
        result = run_scenario(_scenario(enabled, max_throughput), seed=SEED)
    try:
        assert result.agents_remaining == 0
        assert result.success
        with contextlib.closing(sqlite3.connect(result.sqlite_file)) as con:
            fps = float(
                con.execute("SELECT value FROM metadata WHERE key='fps'").fetchone()[0]
            )
            rows = con.execute(
                "SELECT id, MAX(frame) FROM trajectory_data GROUP BY id"
            ).fetchall()
    finally:
        result.cleanup()
    assert len(rows) == NUM_AGENTS
    return sorted(frame / fps for _, frame in rows), 1.0 / fps


def _gaps(times: list[float]) -> list[float]:
    return [b - a for a, b in zip(times, times[1:])]


@pytest.mark.parametrize("rate", [1.0, 2.0])
def test_throttled_exit_removes_at_most_max_throughput_per_second(rate):
    times, frame_s = _removal_times(True, rate)
    min_gap = 1.0 / rate
    assert min(_gaps(times)) >= min_gap - frame_s - 1e-9
    assert times[-1] - times[0] >= (NUM_AGENTS - 1) * min_gap - frame_s - 1e-9


@pytest.mark.parametrize(
    "enabled, rate",
    [(False, 1.0), (False, 2.0), (True, 0.0)],
    ids=["disabled-1", "disabled-2", "zero-rate"],
)
def test_unthrottled_exit_releases_faster_than_the_cap(enabled, rate):
    """Without the cap the same crowd leaves faster than 2 agents/s.

    This makes the bounds above sensitive: they hold because of the cap,
    not because the crowd cannot reach the exit any faster. A
    ``max_throughput`` of 0 disables the cap even with throttling on.
    """
    times, frame_s = _removal_times(enabled, rate)
    assert min(_gaps(times)) < 0.5 - frame_s
    assert times[-1] - times[0] < (NUM_AGENTS - 1) * 0.5 - frame_s
