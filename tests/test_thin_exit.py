"""Agents leave through an exit polygon thinner than their clearance.

Issue #401: with removal on entering the exit polygon (#392), an agent could
stop 0.01-0.02 m short of a 0.2 m deep exit against a wall and stay there
until ``max_simulation_time``. An exit now also counts as reached within
``EXIT_REACH_TOLERANCE_M`` of its polygon.

The geometry follows the Schröder room: a 30 x 10 m room, exit E1
``[29.8, 30] x [8, 9]`` against the east wall, r = 0.15 m, collision-free
speed model, exit capped at 1 p/s. Twenty agents start near the door, so a
run takes well under a second.
"""

from __future__ import annotations

import contextlib
import sqlite3

import pytest
from shapely.geometry import Point, Polygon, box

from pyfds_evac.core.direct_steering_runtime import (
    EXIT_REACH_TOLERANCE_M,
    reached_stage,
)
from pyfds_evac.core.scenario import Scenario, run_scenario

EXIT = box(29.8, 8.0, 30.0, 9.0)
FLUSH = box(0.0, 0.0, 30.0, 10.0)
# 0.8 m deep jambs either side of the door, as in the Schröder room configs.
JAMBS = Polygon(
    [
        (0, 0),
        (30, 0),
        (30, 7.2),
        (29.2, 7.2),
        (29.2, 8),
        (30, 8),
        (30, 9),
        (29.2, 9),
        (29.2, 10),
        (0, 10),
    ]
)
NUM_AGENTS = 20
RADIUS = 0.15
V0 = 1.3
MAX_SIM_TIME_S = 120.0
SEEDS = range(1, 21)
TARGET = (29.9, 8.5)
EXIT_CFG = {"stage_type": "exit", "polygon": EXIT}


def _coords(polygon: Polygon) -> list[list[float]]:
    return [[x, y] for x, y in polygon.exterior.coords]


def _scenario(walkable: Polygon, seed: int) -> Scenario:
    raw = {
        "project_version": "2.0",
        "config": {
            "simulation_settings": {
                "simulationParams": {
                    "max_simulation_time": MAX_SIM_TIME_S,
                    "model_type": "CollisionFreeSpeedModel",
                },
                "numberOfSimulations": 1,
                "baseSeed": seed,
            },
            "ui_state": {"useShortestPaths": False},
        },
        "exits": {
            "E1": {
                "type": "polygon",
                "coordinates": _coords(EXIT),
                "enable_throughput_throttling": True,
                "max_throughput": 1.0,
            }
        },
        "distributions": {
            "jps-distributions_0": {
                "type": "polygon",
                "coordinates": _coords(box(24.0, 0.5, 29.0, 9.5)),
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
        "journeys": [
            {
                "id": "journey_0",
                "stages": ["jps-distributions_0", "E1"],
                "transitions": [
                    {
                        "from": "jps-distributions_0",
                        "to": "E1",
                        "journey_id": "journey_0",
                    }
                ],
            }
        ],
        "transitions": [
            {"from": "jps-distributions_0", "to": "E1", "journey_id": "journey_0"}
        ],
    }
    sim_params = raw["config"]["simulation_settings"]["simulationParams"]
    return Scenario(
        raw=raw,
        walkable_area_wkt=walkable.wkt,
        model_type="CollisionFreeSpeedModel",
        seed=seed,
        sim_params=sim_params,
        source_path=None,
    )


def _last_positions(result) -> tuple[dict[int, tuple[float, float]], float]:
    """Each agent's last recorded position, and the trajectory fps."""
    with contextlib.closing(sqlite3.connect(result.sqlite_file)) as con:
        fps = float(
            con.execute("SELECT value FROM metadata WHERE key='fps'").fetchone()[0]
        )
        rows = con.execute(
            "SELECT id, pos_x, pos_y FROM trajectory_data ORDER BY frame"
        ).fetchall()
    return {agent_id: (x, y) for agent_id, x, y in rows}, fps


@pytest.mark.parametrize("walkable", [JAMBS, FLUSH], ids=["jambs", "flush"])
def test_everyone_leaves_through_a_thin_exit(walkable):
    """Every agent leaves, from the doorway, for 20 seeds.

    Removal follows the last written frame by at most one frame interval,
    so the door is widened by the distance walked in that interval plus the
    reach tolerance.
    """
    stalled, outside = [], {}
    for seed in SEEDS:
        result = run_scenario(_scenario(walkable, seed), seed=seed)
        try:
            last, fps = _last_positions(result)
            if not result.metrics["all_evacuated"]:
                stalled.append(seed)
            reach = EXIT.buffer(V0 / fps + EXIT_REACH_TOLERANCE_M + 1e-6)
            for aid, (x, y) in last.items():
                if not reach.covers(Point(x, y)):
                    outside[(seed, aid)] = (x, y)
        finally:
            result.cleanup()
    assert not stalled, f"agents left in the room for seeds {stalled}"
    assert not outside, f"agents removed beside the door: {outside}"


@pytest.mark.parametrize(
    "x, y",
    [(29.781, 8.184), (29.789, 8.821), (29.795, 8.177), (29.801, 8.5)],
)
def test_stall_positions_from_issue_count_as_reached(x, y):
    assert reached_stage(x, y, TARGET, EXIT_CFG, RADIUS)


def test_west_exit_stall_position_counts_as_reached():
    cfg = {"stage_type": "exit", "polygon": box(0.0, 8.0, 0.2, 9.0)}
    assert reached_stage(0.214, 8.18, (0.1, 8.5), cfg, RADIUS)


@pytest.mark.parametrize("x, y", [(29.75, 8.5), (29.9, 7.9), (29.9, 9.1)])
def test_beside_or_before_the_door_is_not_reached(x, y):
    assert not reached_stage(x, y, TARGET, EXIT_CFG, RADIUS)
