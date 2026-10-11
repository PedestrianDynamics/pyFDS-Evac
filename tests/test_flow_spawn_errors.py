"""A flow spawn retries only a position JuPedSim refuses (#753).

A flow agent that cannot be configured (no valid entry stage, no exit,
an agent parameter ``add_agent`` rejects) fails the run with the flow's
distribution and the candidate position named, instead of being counted
as having found no free position. ``_refuses_position`` tells the two
apart by the messages of JuPedSim 1.4.2, which are pinned here.
"""

from __future__ import annotations

import contextlib
import io

import jupedsim as jps
import pytest
from shapely.geometry import Polygon, box
from test_flow_spawn_spacing import (
    AREA,
    D1,
    FLOW_R,
    STANDING_R,
    _run_recording_gaps,
    _scenario_with_flow,
)

import pyfds_evac.core.simulation_init as simulation_init
from pyfds_evac.core.scenario import run_scenario
from pyfds_evac.core.simulation_init import _refuses_position

POSITION = r"at \(\d+\.\d{3}, \d+\.\d{3}\)"


def _flow(n_flow=5, journey=True):
    """Five flow agents of radius 0.15 m into an empty area, with or
    without a journey of their own."""
    scenario = _scenario_with_flow(
        "CollisionFreeSpeedModel", AREA, (0, STANDING_R), (n_flow, FLOW_R), 2.0, 3.0
    )
    if not journey:
        scenario.raw["journeys"] = [
            j for j in scenario.raw["journeys"] if j["id"] != "J1"
        ]
        scenario.raw["transitions"] = [
            t for t in scenario.raw["transitions"] if t["journey_id"] != "J1"
        ]
    return scenario


def _run(scenario):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        result = run_scenario(scenario, seed=1)
    result.cleanup()
    return result, out.getvalue()


def _raises(scenario, error, match):
    out = io.StringIO()
    with pytest.raises(error, match=match) as info, contextlib.redirect_stdout(out):
        run_scenario(scenario, seed=1)
    assert "found no free position" not in out.getvalue()
    return info.value


def test_a_variant_without_entry_stage_fails_the_run(monkeypatch):
    """A zero-weight variant passes the setup check but is still drawn
    when it is the only one; its entry stage is a distribution."""
    initialize = simulation_init.initialize_simulation_from_json

    def without_entry_stage(*args, **kwargs):
        result = initialize(*args, **kwargs)
        for flow_dist in result[3]["flow_distributions"]:
            for variant_info in flow_dist["journey_info"]:
                variant_info["variant_data"]["entry_stages"] = [D1]
                variant_info["variant_data"]["percentage"] = 0
        return result

    monkeypatch.setattr(
        simulation_init, "initialize_simulation_from_json", without_entry_stage
    )
    error = _raises(_flow(), ValueError, f"'{D1}' \\(source 0\\) {POSITION}")
    assert "No valid entry stage" in str(error)


def test_no_exit_for_a_flow_agent_fails_the_run(monkeypatch):
    def no_exit(*args, **kwargs):
        raise ValueError("No exits available")

    monkeypatch.setattr(simulation_init, "_find_nearest_exit", no_exit)
    error = _raises(
        _flow(journey=False), ValueError, f"'{D1}' \\(source 0\\) {POSITION}"
    )
    assert "No exits available" in str(error)
    assert isinstance(error.__cause__, ValueError)


def test_a_flow_without_journey_still_spawns():
    """The nearest-exit path itself is unchanged."""
    result, out = _run(_flow(journey=False))
    assert result.agents_not_spawned == 0
    assert "found no free position" not in out


def _refusing(monkeypatch, message):
    """``add_agent`` raises *message* for every flow agent."""
    add_agent = jps.Simulation.add_agent

    def refusing(self, parameters):
        if parameters.radius == FLOW_R:
            raise RuntimeError(message)
        return add_agent(self, parameters)

    monkeypatch.setattr(jps.Simulation, "add_agent", refusing)


def test_a_boundary_refusal_defers_the_flow(monkeypatch):
    _refusing(
        monkeypatch,
        "Model constraint violation: Agent (1.1, 2) too close to geometry "
        "boundaries, distance <= 0.15",
    )
    _, result, out = _run_recording_gaps(monkeypatch, _flow(), 1)
    assert result.agents_not_spawned == 5
    assert result.metrics["flow_spawns_deferred"] > 0
    assert f"Flow spawning: '{D1}' found no free position" in out


@pytest.mark.parametrize(
    "message",
    [
        "Unknown stage id: 99",
        "Model constraint violation: radius 0 not in allowed range, "
        "radius needs to be in (0,2]",
    ],
)
def test_an_add_agent_configuration_error_fails_the_run(monkeypatch, message):
    """The spawn keys reject a radius of 0 m before the run; the message
    stands for any agent ``add_agent`` rejects whatever the position."""
    _refusing(monkeypatch, message)
    error = _raises(_flow(), RuntimeError, f"'{D1}' \\(source 0\\) {POSITION}")
    assert message in str(error)


MODELS = {
    "CollisionFreeSpeedModel": (
        jps.CollisionFreeSpeedModel,
        jps.CollisionFreeSpeedModelAgentParameters,
    ),
    "CollisionFreeSpeedModelV2": (
        jps.CollisionFreeSpeedModelV2,
        jps.CollisionFreeSpeedModelV2AgentParameters,
    ),
    "AnticipationVelocityModel": (
        jps.AnticipationVelocityModel,
        jps.AnticipationVelocityModelAgentParameters,
    ),
    "SocialForceModel": (
        jps.SocialForceModel,
        jps.SocialForceModelAgentParameters,
    ),
    "GeneralizedCentrifugalForceModel": (
        jps.GeneralizedCentrifugalForceModel,
        jps.GeneralizedCentrifugalForceModelAgentParameters,
    ),
    "WarpDriverModel": (
        jps.WarpDriverModel,
        jps.WarpDriverModelAgentParameters,
    ),
}
# WarpDriverModel refuses neither an occupied position nor one at a wall.
REFUSES_SPACING = sorted(set(MODELS) - {"WarpDriverModel"})


def _add(model_type, **kwargs):
    """A 10 x 10 m run of *model_type* with one agent at (5, 5); the
    message ``add_agent`` raises for an agent of *kwargs*, or None."""
    model, parameters = MODELS[model_type]
    simulation = jps.Simulation(model=model(), geometry=box(0, 0, 10, 10))
    exit_stage = simulation.add_exit_stage(Polygon(box(9, 9, 9.5, 9.5)))
    journey = simulation.add_journey(jps.JourneyDescription([exit_stage]))
    agent = {"journey_id": journey, "stage_id": exit_stage, "position": (5.0, 5.0)}
    simulation.add_agent(parameters(**agent))
    try:
        simulation.add_agent(parameters(**(agent | kwargs)))
    except RuntimeError as error:
        return error
    return None


@pytest.mark.parametrize("model_type", REFUSES_SPACING)
@pytest.mark.parametrize("position", [(5.0, 5.0), (0.05, 5.0)])
def test_jupedsim_refuses_an_occupied_or_wall_position(model_type, position):
    error = _add(model_type, position=position)
    assert error is not None
    assert _refuses_position(error)


@pytest.mark.parametrize("model_type", sorted(MODELS))
def test_jupedsim_refuses_a_position_outside(model_type):
    error = _add(model_type, position=(11.0, 5.0))
    assert str(error) == "Agent (11, 5) not inside walkable area"
    assert _refuses_position(error)


@pytest.mark.parametrize("model_type", sorted(MODELS))
@pytest.mark.parametrize("ids", [{"stage_id": 99}, {"journey_id": 99}])
def test_unknown_stages_and_journeys_are_not_refused_positions(model_type, ids):
    error = _add(model_type, position=(3.0, 3.0), **ids)
    assert error is not None
    assert not _refuses_position(error)


@pytest.mark.parametrize(
    "model_type",
    [
        "CollisionFreeSpeedModel",
        "CollisionFreeSpeedModelV2",
        "AnticipationVelocityModel",
        "WarpDriverModel",
    ],
)
def test_an_invalid_radius_is_not_a_refused_position(model_type):
    error = _add(model_type, position=(3.0, 3.0), radius=0.0)
    assert error is not None
    assert "radius" in str(error)
    assert not _refuses_position(error)
