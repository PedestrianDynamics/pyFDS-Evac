"""The direct-steering state carries each agent's own radius (#408).

The runtime reaches a stage within ``agent_radius + 0.5`` m of its target
point and keeps next-stage targets ``0.8 * agent_radius`` from the
polygon edge, reading the radius from the agent's steering state. Before
#408 no set-up path stored it, so every agent was steered as if its
radius were 0.2 m.

The deck is the synthetic room of ``test_run_outcome`` with a 0.13 m
radius, run once per path that builds a steering state: a journey, the
fallback set-up without journeys, a throttled exit reached without a
journey, and flow spawning with and without journeys.
"""

from __future__ import annotations

import contextlib
import io
import json

import jupedsim as jps
import pedpy
import pytest
from test_run_outcome import ENOUGH_S, SEED, D, _scenario

import pyfds_evac.core.scenario as scenario_module
from pyfds_evac.core.scenario import run_scenario
from pyfds_evac.core.simulation_init import initialize_simulation_from_json

RADIUS = 0.13
FLOW = {"use_flow_spawning": True, "flow_start_time": 0, "flow_end_time": 3}


def _journey(raw):
    pass


def _no_journey(raw):
    raw["journeys"] = []
    raw["transitions"] = []


def _throttled_exit(raw):
    # A distribution without a journey beside one with a journey: its
    # agents walk to the throttled exit on the runtime's steering.
    raw["exits"]["E"]["enable_throughput_throttling"] = True
    raw["exits"]["E"]["max_throughput"] = 2.0
    other = "jps-distributions_1"
    raw["distributions"][other] = {
        "type": "polygon",
        "coordinates": [[1.0, 0.1], [4.0, 0.1], [4.0, 0.95], [1.0, 0.95], [1.0, 0.1]],
        "parameters": dict(raw["distributions"][D]["parameters"], number=1),
    }
    raw["journeys"] = [{"id": "J", "stages": [other, "E"]}]
    raw["transitions"] = [{"from": other, "to": "E", "journey_id": "J"}]


def _flow(prepare):
    def apply(raw):
        prepare(raw)
        raw["distributions"][D]["parameters"].update(FLOW)

    return apply


@pytest.mark.parametrize(
    "prepare",
    [_journey, _no_journey, _throttled_exit, _flow(_journey), _flow(_no_journey)],
    ids=["journey", "no-journey", "throttled-exit", "flow-journey", "flow-no-journey"],
)
def test_stage_reach_uses_the_agent_radius(monkeypatch, prepare):
    scenario = _scenario(ENOUGH_S, radius=RADIUS)
    prepare(scenario.raw)
    radii: list[float] = []
    real_reached = scenario_module.reached_stage

    def reached(x, y, target, stage_cfg, agent_radius):
        radii.append(agent_radius)
        return real_reached(x, y, target, stage_cfg, agent_radius)

    monkeypatch.setattr(scenario_module, "reached_stage", reached)
    with contextlib.redirect_stdout(io.StringIO()):
        result = run_scenario(scenario, seed=SEED)
    try:
        assert result.agents_remaining == 0
    finally:
        result.cleanup()
    assert radii, "no agent was steered by the runtime"
    assert sorted(set(radii)) == [RADIUS]


@pytest.mark.parametrize(
    "prepare",
    [_journey, _no_journey, _throttled_exit],
    ids=["journey", "no-journey", "throttled-exit"],
)
def test_each_agent_is_steered_with_its_sampled_radius(tmp_path, prepare):
    """With a Gaussian radius the state holds each agent's draw, not the mean."""
    scenario = _scenario(
        ENOUGH_S, radius=0.15, radius_distribution="gaussian", radius_std=0.02
    )
    prepare(scenario.raw)
    config = tmp_path / "config.json"
    config.write_text(json.dumps(scenario.raw))
    walkable = pedpy.WalkableArea(scenario.walkable_area_wkt)
    simulation = jps.Simulation(
        model=jps.CollisionFreeSpeedModel(), geometry=walkable.polygon
    )
    with contextlib.redirect_stdout(io.StringIO()):
        _, _, agent_radii, spawning_info = initialize_simulation_from_json(
            str(config), simulation, walkable, seed=SEED
        )
    states = spawning_info["agent_wait_info"]
    assert states
    assert len(set(agent_radii.values())) > 1, "the radii were not sampled"
    for agent_id, state in states.items():
        assert state["agent_radius"] == agent_radii[agent_id]
