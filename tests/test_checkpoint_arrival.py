"""A checkpoint reached inside its polygon, through a whole run (#69).

One agent walks a 40 x 4 m corridor through two checkpoints and leaves by
an exit at the far end. Checkpoint A, ``[5, 15] x [0, 4]``, holds the agent
for a constant 3 s. Checkpoint B, ``[6, 22] x [0, 4]``, overlaps all of A
but its first metre, so the agent, which walks on towards A's target while
it waits, stands inside B when its wait ends. The checkpoints are larger than the 0.7 m reach disc
around their target points, so the agent is inside A well before it is near
A's target: the arrival is the containment rule's.

The run is observed through ``reached_stage`` and ``advance_path_target``
as ``run_scenario`` calls them: a stage is reached once, its wait runs from
that step, and the agent moves on from it once, in the order A, B, exit.
"""

from __future__ import annotations

import math

import pytest
from shapely.geometry import Polygon, box

import pyfds_evac.core.scenario as scenario_module
from pyfds_evac.core.direct_steering_runtime import TARGET_REACH_MARGIN_M
from pyfds_evac.core.scenario import Scenario, run_scenario

CORRIDOR = box(0.0, 0.0, 40.0, 4.0)
SPAWN = box(0.5, 1.5, 1.5, 2.5)
CP_A = box(5.0, 0.0, 15.0, 4.0)
CP_B = box(6.0, 0.0, 22.0, 4.0)
EXIT = box(39.8, 0.0, 40.0, 4.0)
WAIT_A_S = 3.0
RADIUS = 0.2
DT_S = 0.01
SEEDS = (1, 2, 3)


def _coords(polygon: Polygon) -> list[list[float]]:
    return [[x, y] for x, y in polygon.exterior.coords]


def _checkpoint(polygon: Polygon, waiting_time: float) -> dict:
    return {
        "type": "polygon",
        "coordinates": _coords(polygon),
        "waiting_time": waiting_time,
        "waiting_time_distribution": "constant",
        "waiting_time_std": 1,
        "enable_throughput_throttling": False,
        "max_throughput": 0,
        "speed_factor": 1,
    }


def _scenario(seed: int) -> Scenario:
    stages = ["jps-distributions_0", "A", "B", "E"]
    transitions = [
        {"from": a, "to": b, "journey_id": "journey_0"}
        for a, b in zip(stages, stages[1:])
    ]
    raw = {
        "project_version": "2.0",
        "config": {
            "simulation_settings": {
                "simulationParams": {
                    "max_simulation_time": 60.0,
                    "model_type": "CollisionFreeSpeedModel",
                },
                "numberOfSimulations": 1,
                "baseSeed": seed,
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
                    "radius": RADIUS,
                    "v0": 1.2,
                    "use_flow_spawning": False,
                    "distribution_mode": "by_number",
                    "use_premovement": False,
                    "radius_distribution": "constant",
                    "v0_distribution": "constant",
                },
            }
        },
        "checkpoints": {"A": _checkpoint(CP_A, WAIT_A_S), "B": _checkpoint(CP_B, 0)},
        "zones": {},
        "journeys": [{"id": "journey_0", "stages": stages, "transitions": transitions}],
        "transitions": transitions,
    }
    sim_params = raw["config"]["simulation_settings"]["simulationParams"]
    return Scenario(
        raw=raw,
        walkable_area_wkt=CORRIDOR.wkt,
        model_type="CollisionFreeSpeedModel",
        seed=seed,
        sim_params=sim_params,
        source_path=None,
    )


def _observed_run(monkeypatch, seed):
    """Run the corridor; return its result, reaches and departures.

    A reach is ``(time, stage, x, y, target)`` for each step on which
    ``reached_stage`` says yes; a departure is ``(time, stage)`` for each
    ``advance_path_target`` call, the agent leaving that stage, and the
    agent's position then.
    """
    reaches: list[tuple] = []
    departures: list[tuple] = []
    clock = {"t": 0.0}
    real_reached = scenario_module.reached_stage
    real_advance = scenario_module.advance_path_target

    def reached(x, y, target, stage_cfg, agent_radius):
        ok = real_reached(x, y, target, stage_cfg, agent_radius)
        if ok:
            stage = next(
                key
                for key, poly in (("A", CP_A), ("B", CP_B), ("E", EXIT))
                if stage_cfg.get("polygon") is not None
                and stage_cfg["polygon"].equals(poly)
            )
            reaches.append((clock["t"], stage, x, y, target))
        return ok

    def advance(wait_info, may_enter=None):
        departures.append(
            (
                clock["t"],
                wait_info.get("current_target_stage"),
                wait_info.get("current_position"),
            )
        )
        return real_advance(wait_info, may_enter=may_enter)

    monkeypatch.setattr(scenario_module, "reached_stage", reached)
    monkeypatch.setattr(scenario_module, "advance_path_target", advance)
    result = run_scenario(_scenario(seed), seed=seed, frame_recorder=_Clock(clock))
    return result, reaches, departures


class _Clock:
    """A frame recorder that only keeps the simulated time of the next step."""

    def __init__(self, clock):
        self.clock = clock

    def start(self, *args, **kwargs):
        pass

    def leaves(self, *args, **kwargs):
        pass

    def after_step(self, simulation, **kwargs):
        self.clock["t"] = float(simulation.elapsed_time())

    def finish(self, *args, **kwargs):
        pass


@pytest.mark.parametrize("seed", SEEDS)
def test_containment_arrival_waits_once_in_order(monkeypatch, seed):
    result, reaches, departures = _observed_run(monkeypatch, seed)
    try:
        assert result.agents_evacuated == 1

        # Each stage is reached once and left once, in route order.
        assert [stage for _, stage, *_ in reaches] == ["A", "B", "E"]
        assert [stage for _, stage, _ in departures] == ["A", "B"]

        # A is reached by containment: inside it, beyond the reach disc.
        t_reach_a, _, x, y, target = reaches[0]
        assert CP_A.covers(box(x, y, x, y))
        reach_disc = RADIUS + TARGET_REACH_MARGIN_M
        assert math.hypot(x - target[0], y - target[1]) > reach_disc

        # The agent leaves A after the whole wait, counted from the reach.
        t_leave_a = departures[0][0]
        assert t_leave_a - t_reach_a == pytest.approx(WAIT_A_S, abs=2 * DT_S)

        # The agent stands inside B as it leaves A, and reaches B on the
        # next step, not before A's wait ends and not twice.
        assert CP_B.covers(box(*departures[0][2], *departures[0][2]))
        t_reach_b = reaches[1][0]
        assert t_leave_a < t_reach_b <= t_leave_a + 2 * DT_S
    finally:
        result.cleanup()
