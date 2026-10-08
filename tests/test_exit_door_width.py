"""An exit removes agents inside its polygon, so the door width sets the flow.

Issue #349: agents were removed within ``agent_radius + 0.5`` m of a target
point inside the exit polygon. The door width played no role and agents
left from beside the door, in the room, before passing it.

The scenario is synthetic: a square room, one door of width ``w`` in the
east wall, and the exit polygon filling the 1 m deep doorway. Every agent
starts in the room and queues at the door.
"""

from __future__ import annotations

import contextlib
import sqlite3

import pytest
from shapely.geometry import Point, Polygon, box

from pyfds_evac.core.direct_steering_runtime import (
    EXIT_REACH_TOLERANCE_M,
    TARGET_REACH_MARGIN_M,
    reached_stage,
)
from pyfds_evac.core.scenario import Scenario, run_scenario

# One worker runs this module, so its module-scoped runs happen once.
pytestmark = pytest.mark.xdist_group("test_exit_door_width")

ROOM_M = 8.0
DOOR_DEPTH_M = 1.0
NUM_AGENTS = 80
V0 = 1.2
RADIUS = 0.2
SEED = 7
MAX_SIM_TIME_S = 200.0
# 0.8 m clogs under the collision-free speed model with 0.2 m radii.
NARROW_M = 1.0
WIDE_M = 2.0


def _exit_polygon(width: float) -> Polygon:
    half = width / 2.0
    mid = ROOM_M / 2.0
    return box(ROOM_M, mid - half, ROOM_M + DOOR_DEPTH_M, mid + half)


def _coords(polygon: Polygon) -> list[list[float]]:
    return [[x, y] for x, y in polygon.exterior.coords]


def _door_scenario(width: float) -> Scenario:
    walkable = box(0.0, 0.0, ROOM_M, ROOM_M).union(_exit_polygon(width))
    raw = {
        "project_version": "2.0",
        "config": {
            "simulation_settings": {
                "simulationParams": {
                    "max_simulation_time": MAX_SIM_TIME_S,
                    "model_type": "CollisionFreeSpeedModel",
                },
                "numberOfSimulations": 1,
                "baseSeed": SEED,
            },
            "ui_state": {"useShortestPaths": False},
        },
        "exits": {
            "door": {
                "type": "polygon",
                "coordinates": _coords(_exit_polygon(width)),
                "enable_throughput_throttling": False,
                "max_throughput": 0,
            }
        },
        "distributions": {
            "room": {
                "type": "polygon",
                "coordinates": _coords(box(0.5, 0.5, 6.0, ROOM_M - 0.5)),
                "parameters": {
                    "number": NUM_AGENTS,
                    "radius": RADIUS,
                    "v0": V0,
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


def _last_positions(result) -> tuple[dict[int, tuple[int, float, float]], float]:
    """Each agent's last recorded (frame, x, y), and the trajectory fps."""
    with contextlib.closing(sqlite3.connect(result.sqlite_file)) as con:
        fps = float(
            con.execute("SELECT value FROM metadata WHERE key='fps'").fetchone()[0]
        )
        rows = con.execute(
            "SELECT id, frame, pos_x, pos_y FROM trajectory_data ORDER BY frame"
        ).fetchall()
    last = {agent_id: (frame, x, y) for agent_id, frame, x, y in rows}
    return last, fps


@pytest.fixture(scope="module")
def runs() -> dict[float, tuple[dict, float, bool]]:
    out = {}
    for width in (NARROW_M, WIDE_M):
        result = run_scenario(_door_scenario(width), seed=SEED)
        try:
            last, fps = _last_positions(result)
            out[width] = (last, fps, result.metrics["all_evacuated"])
        finally:
            result.cleanup()
    return out


def _flow(last: dict, fps: float) -> float:
    """Door flow in persons per second over the middle half of the exits.

    The first and the last quarter are left out: the queue is still forming
    at the start and thinning at the end, so only the middle measures the
    door rather than the approach.
    """
    frames = sorted(frame for frame, _, _ in last.values())
    first, last_ = len(frames) // 4, 3 * len(frames) // 4
    return (last_ - first) / ((frames[last_] - frames[first]) / fps)


@pytest.mark.parametrize("width", [NARROW_M, WIDE_M])
def test_everyone_leaves(runs, width):
    last, _, all_evacuated = runs[width]
    assert all_evacuated
    assert len(last) == NUM_AGENTS


@pytest.mark.parametrize("width", [NARROW_M, WIDE_M])
def test_nobody_leaves_outside_the_exit_polygon(runs, width):
    """The last recorded position lies in the doorway, not in the room.

    Removal follows the last written frame by at most one frame interval,
    so the polygon is widened by the distance walked in that interval plus
    the reach tolerance.
    """
    last, fps, _ = runs[width]
    slack = V0 / fps + EXIT_REACH_TOLERANCE_M + 1e-6
    reach = _exit_polygon(width).buffer(slack)
    outside = {
        aid: (x, y) for aid, (_, x, y) in last.items() if not reach.covers(Point(x, y))
    }
    assert not outside, f"agents removed outside the door: {outside}"


def test_flow_scales_with_door_width(runs):
    """Doubling the door width raises the flow by at least half.

    The ratio is below 2 because a wider door also widens the queue it
    drains, and JuPedSim runs are not bit-reproducible, so the bound is
    loose. With removal near the target point the ratio was about 1.35.
    """
    narrow = _flow(*runs[NARROW_M][:2])
    wide = _flow(*runs[WIDE_M][:2])
    assert wide / narrow > 1.5


EXIT_CFG = {"stage_type": "exit", "polygon": _exit_polygon(NARROW_M)}
TARGET = (ROOM_M + 0.3, ROOM_M / 2.0)


def test_exit_reached_inside_polygon():
    assert reached_stage(ROOM_M + 0.1, ROOM_M / 2.0, TARGET, EXIT_CFG, RADIUS)


def test_exit_not_reached_near_target_outside_polygon():
    """The #349 case: close to the target point but still in the room."""
    x, y = ROOM_M - 0.05, ROOM_M / 2.0 + 0.45
    assert Point(x, y).distance(Point(TARGET)) <= RADIUS + TARGET_REACH_MARGIN_M
    assert not reached_stage(x, y, TARGET, EXIT_CFG, RADIUS)


def test_checkpoint_keeps_distance_rule():
    cfg = {"stage_type": "checkpoint", "polygon": _exit_polygon(NARROW_M)}
    assert reached_stage(ROOM_M - 0.05, ROOM_M / 2.0 + 0.45, TARGET, cfg, RADIUS)
    assert not reached_stage(ROOM_M - 1.0, ROOM_M / 2.0, TARGET, cfg, RADIUS)


def test_exit_without_polygon_falls_back_to_distance():
    cfg = {"stage_type": "exit", "polygon": None}
    assert reached_stage(TARGET[0] - 0.6, TARGET[1], TARGET, cfg, RADIUS)
    assert not reached_stage(TARGET[0] - 0.8, TARGET[1], TARGET, cfg, RADIUS)
