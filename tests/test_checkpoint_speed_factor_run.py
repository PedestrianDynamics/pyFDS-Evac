"""A checkpoint's ``speed_factor`` slows the agent inside it, in a whole run.

One agent with ``v0 = 1.0`` m/s walks a 40 x 4 m corridor, through the
checkpoint ``[15, 25] x [0, 4]`` (no waiting time) to an exit at the far
end. ``docs/scenario-json.md`` says the factor multiplies the speed of agents
inside the checkpoint and is clipped to [0, 3]. So the agent's desired speed
is 1.0 m/s before x = 15, ``1.0 * factor`` while inside, and 1.0 m/s again
after x = 25. The desired speed is read from the agent after every step.
"""

from __future__ import annotations

import pytest
from shapely.geometry import Polygon, box

from pyfds_evac.core.scenario import Scenario, run_scenario

CORRIDOR = box(0.0, 0.0, 40.0, 4.0)
SPAWN = box(0.5, 1.5, 1.5, 2.5)
CHECKPOINT = box(15.0, 0.0, 25.0, 4.0)
EXIT = box(38.0, 0.0, 40.0, 4.0)
V0 = 1.0
EDGE_M = 0.5


def _coords(polygon: Polygon) -> list[list[float]]:
    return [[x, y] for x, y in polygon.exterior.coords]


def _scenario(speed_factor) -> Scenario:
    stages = ["jps-distributions_0", "C", "E"]
    transitions = [
        {"from": a, "to": b, "journey_id": "journey_0"}
        for a, b in zip(stages, stages[1:])
    ]
    raw = {
        "project_version": "2.0",
        "config": {
            "simulation_settings": {
                "simulationParams": {
                    "max_simulation_time": 80.0,
                    "model_type": "CollisionFreeSpeedModel",
                },
                "numberOfSimulations": 1,
                "baseSeed": 1,
            },
            "ui_state": {"useShortestPaths": False},
        },
        "exits": {"E": {"type": "polygon", "coordinates": _coords(EXIT)}},
        "distributions": {
            "jps-distributions_0": {
                "type": "polygon",
                "coordinates": _coords(SPAWN),
                "parameters": {
                    "number": 1,
                    "radius": 0.2,
                    "v0": V0,
                    "use_flow_spawning": False,
                    "distribution_mode": "by_number",
                    "use_premovement": False,
                    "radius_distribution": "constant",
                    "v0_distribution": "constant",
                },
            }
        },
        "checkpoints": {
            "C": {
                "type": "polygon",
                "coordinates": _coords(CHECKPOINT),
                "waiting_time": 0,
                "waiting_time_distribution": "constant",
                "waiting_time_std": 1,
                "enable_throughput_throttling": False,
                "max_throughput": 0,
                "speed_factor": speed_factor,
            }
        },
        "zones": {},
        "journeys": [{"id": "journey_0", "stages": stages, "transitions": transitions}],
        "transitions": transitions,
    }
    sim_params = raw["config"]["simulation_settings"]["simulationParams"]
    return Scenario(
        raw=raw,
        walkable_area_wkt=CORRIDOR.wkt,
        model_type="CollisionFreeSpeedModel",
        seed=1,
        sim_params=sim_params,
        source_path=None,
    )


class _SpeedRecorder:
    """A frame recorder that keeps ``(x, desired_speed)`` after each step."""

    def __init__(self):
        self.samples: list[tuple[float, float]] = []

    def start(self, *args, **kwargs):
        pass

    def leaves(self, *args, **kwargs):
        pass

    def after_step(self, simulation, **kwargs):
        for agent in simulation.agents():
            self.samples.append(
                (float(agent.position[0]), float(agent.model.desired_speed))
            )

    def finish(self, *args, **kwargs):
        pass


def _speeds(speed_factor) -> dict[str, set[float]]:
    recorder = _SpeedRecorder()
    result = run_scenario(_scenario(speed_factor), seed=1, frame_recorder=recorder)
    try:
        assert result.agents_evacuated == 1
    finally:
        result.cleanup()
    lo, hi = CHECKPOINT.bounds[0], CHECKPOINT.bounds[2]
    return {
        "before": {round(s, 6) for x, s in recorder.samples if x < lo - EDGE_M},
        "inside": {
            round(s, 6) for x, s in recorder.samples if lo + EDGE_M < x < hi - EDGE_M
        },
        "after": {round(s, 6) for x, s in recorder.samples if x > hi + EDGE_M},
    }


@pytest.mark.parametrize(
    ("speed_factor", "inside"),
    [(0.5, 0.5), (2.0, 2.0), (5.0, 3.0), (-1.0, 1.0)],
)
def test_checkpoint_speed_factor_scales_the_speed_inside_only(speed_factor, inside):
    """Desired speed is 1.0 outside and ``1.0 * clip(factor)`` inside.

    The factor 5.0 is clipped to 3.0 and the negative factor becomes 1.0,
    both from ``docs/scenario-json.md``.
    """
    speeds = _speeds(speed_factor)
    assert speeds["before"] == {V0}
    assert speeds["inside"] == {inside}
    assert speeds["after"] == {V0}
