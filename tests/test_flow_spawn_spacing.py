"""Flow-spawned agents keep the spacing to the agents in the run (#710).

Twelve agents of radius 0.3 m stand in a 3 x 4 m area (pre-movement
100 s); a flow of twenty agents of radius 0.15 m enters the same area.
Each flow agent must keep twice the larger radius, 0.6 m, from every
agent present when it is added, as the agents of overlapping spawn areas
do (#402). ``Simulation.add_agent`` refuses only closer than the model's
own constraint: 0.45 m for the collision-free speed model, less or
nothing for others. A flow that finds no free position is retried and,
at the end of the run, counted and reported on one line.
"""

from __future__ import annotations

import contextlib
import dataclasses
import io
import math

import jupedsim as jps
import numpy as np
import pytest
from shapely.geometry import Polygon, box
from test_run_outcome import D, _coords, _scenario

from pyfds_evac.core.scenario import run_scenario
from pyfds_evac.core.simulation_init import _RADIUS_SUM_MODELS, _crowds_agents

D1 = "jps-distributions_1"
AREA = box(1.0, 1.0, 4.0, 5.0)
STANDING_R = 0.3
FLOW_R = 0.15


def _scenario_with_flow(model, area, standing, flow, flow_end_s, max_time_s):
    """*standing* agents that wait in *area*, and a flow of *flow* into it."""
    n_standing, r_standing = standing
    n_flow, r_flow = flow
    scenario = _scenario(
        max_time_s,
        number=n_standing,
        radius=r_standing,
        use_premovement=True,
        premovement_distribution="constant",
        premovement_param_a=100.0,
    )
    raw = scenario.raw
    raw["config"]["simulation_settings"]["simulationParams"]["model_type"] = model
    raw["distributions"][D]["coordinates"] = _coords(area)
    flow_params = dict(
        raw["distributions"][D]["parameters"],
        number=n_flow,
        radius=r_flow,
        use_premovement=False,
        use_flow_spawning=True,
        flow_start_time=0,
        flow_end_time=flow_end_s,
    )
    raw["distributions"][D1] = {
        "type": "polygon",
        "coordinates": _coords(area),
        "parameters": flow_params,
    }
    raw["journeys"].append({"id": "J1", "stages": [D1, "E"]})
    raw["transitions"].append({"from": D1, "to": "E", "journey_id": "J1"})
    return dataclasses.replace(scenario, model_type=model)


def _run_recording_gaps(monkeypatch, scenario, seed):
    """Run *scenario*; per added agent, its radius and its smallest gap
    minus twice the larger radius of the pair."""
    added = []
    radii = {}
    add_agent = jps.Simulation.add_agent

    def recording(self, parameters):
        radius = parameters.radius
        slack = min(
            (
                math.dist(agent.position, parameters.position)
                - 2 * max(radius, radii[agent.id])
                for agent in self.agents()
            ),
            default=math.inf,
        )
        agent_id = add_agent(self, parameters)
        radii[agent_id] = radius
        added.append((radius, slack))
        return agent_id

    monkeypatch.setattr(jps.Simulation, "add_agent", recording)
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        result = run_scenario(scenario, seed=seed)
    result.cleanup()
    return added, result, out.getvalue()


@pytest.mark.parametrize(
    "model", ["CollisionFreeSpeedModel", "SocialForceModel", "WarpDriverModel"]
)
@pytest.mark.parametrize("seed", [1, 2, 3])
def test_flow_agents_keep_twice_the_larger_radius(monkeypatch, model, seed):
    scenario = _scenario_with_flow(
        model, AREA, (12, STANDING_R), (20, FLOW_R), 2.0, 3.0
    )
    added, _, _ = _run_recording_gaps(monkeypatch, scenario, seed)
    flow = [slack for radius, slack in added if radius == FLOW_R]
    assert flow
    assert min(flow) >= -1e-9


def test_a_full_area_defers_the_flow_and_reports_it(monkeypatch):
    """Four agents fill a 1.2 m square; the flow of five never finds room."""
    scenario = _scenario_with_flow(
        "CollisionFreeSpeedModel", box(1.0, 1.0, 2.2, 2.2), (4, 0.2), (5, 0.2), 1.0, 2.0
    )
    added, result, out = _run_recording_gaps(monkeypatch, scenario, 1)
    assert len(added) == 4
    assert result.agents_not_spawned == 5
    assert result.metrics.get("flow_spawns_deferred", 0) > 0
    reports = [line for line in out.splitlines() if "found no free position" in line]
    assert reports == [
        f"Flow spawning: '{D1}' found no free position at "
        f"{result.metrics['flow_spawns_deferred']} steps between t=0.00 s and "
        "t=1.00 s; 5 of its 5 agents did not enter"
    ]


def test_an_uncrowded_flow_defers_nothing(monkeypatch):
    scenario = _scenario_with_flow(
        "CollisionFreeSpeedModel", AREA, (0, STANDING_R), (5, FLOW_R), 2.0, 3.0
    )
    _, result, out = _run_recording_gaps(monkeypatch, scenario, 1)
    assert result.metrics["flow_spawns_deferred"] == 0
    assert "found no free position" not in out


def _occupied(*agents):
    xy = np.array([position for position, _ in agents], dtype=float).reshape(-1, 2)
    return xy, np.array([radius for _, radius in agents], dtype=float)


def _parameters(position, radius):
    return jps.CollisionFreeSpeedModelAgentParameters(position=position, radius=radius)


@pytest.mark.parametrize(
    ("gap", "model", "crowds"),
    [
        (0.61, "CollisionFreeSpeedModel", False),  # clear of 0.6 m
        (0.5, "CollisionFreeSpeedModel", True),  # the model would add it
        (0.4, "CollisionFreeSpeedModel", False),  # left to the model's refusal
        (0.4, "WarpDriverModel", True),  # no refusal to leave it to
    ],
)
def test_crowds_agents(gap, model, crowds):
    occupied = _occupied(((0.0, 0.0), STANDING_R))
    parameters = _parameters((gap, 0.0), FLOW_R)
    assert _crowds_agents(model, parameters, FLOW_R, occupied) is crowds


def test_an_empty_run_is_never_crowded():
    assert not _crowds_agents(
        "WarpDriverModel", _parameters((1, 1), 0.2), 0.2, _occupied()
    )


def _model_and_parameters(model_type):
    if model_type == "CollisionFreeSpeedModel":
        return jps.CollisionFreeSpeedModel(), jps.CollisionFreeSpeedModelAgentParameters
    if model_type == "CollisionFreeSpeedModelV2":
        return (
            jps.CollisionFreeSpeedModelV2(),
            jps.CollisionFreeSpeedModelV2AgentParameters,
        )
    return (
        jps.AnticipationVelocityModel(),
        jps.AnticipationVelocityModelAgentParameters,
    )


@pytest.mark.parametrize("model_type", sorted(_RADIUS_SUM_MODELS))
def test_jupedsim_refuses_below_the_radius_sum_and_spends_an_id(model_type):
    """The two JuPedSim facts that ``_RADIUS_SUM_MODELS`` relies on."""
    model, parameters = _model_and_parameters(model_type)
    simulation = jps.Simulation(model=model, geometry=box(0, 0, 10, 10))
    exit_stage = simulation.add_exit_stage(Polygon(box(9, 9, 9.5, 9.5)))
    journey = simulation.add_journey(jps.JourneyDescription([exit_stage]))

    def add(x, radius):
        return simulation.add_agent(
            parameters(
                position=(x, 5.0),
                journey_id=journey,
                stage_id=exit_stage,
                radius=radius,
            )
        )

    first = add(5.0, STANDING_R)
    with pytest.raises(RuntimeError):
        add(5.0 + STANDING_R + FLOW_R - 0.01, FLOW_R)
    second = add(5.0 + STANDING_R + FLOW_R + 0.01, FLOW_R)
    assert second == first + 2
