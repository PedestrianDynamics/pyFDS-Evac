"""Every operational model must expose its desired speed to the hazard code.

``set_agent_smoke_factor`` and ``set_agent_fic_factor`` reduce an agent's speed
by writing the desired-speed attribute of its model state. The attribute is
named differently by each JuPedSim model, so ``_MODEL_SPEED_ATTRS`` maps state
class to attribute name -- and a model missing from that map fails *silently*:
``get_agent_desired_speed`` returns ``None``, the setter gives up, and the agent
walks at v0 through smoke and irritants with nothing logged.

Three models were in ``_MODEL_BUILDERS`` but not in the map
(``AnticipationVelocityModel``, ``GeneralizedCentrifugalForceModel``,
``WarpDriverModel``). A test asserting only that the map has the right keys
would not have caught it either -- the attribute must actually round-trip. So
this drives a real simulation per model.
"""

from __future__ import annotations

import jupedsim as jps
import pytest
from shapely.geometry import box

from pyfds_evac.core.direct_steering_runtime import (
    _MODEL_SPEED_ATTRS,
    get_agent_desired_speed,
    set_agent_desired_speed,
)
from pyfds_evac.core.scenario import _MODEL_BUILDERS
from pyfds_evac.core.simulation_init import create_agent_parameters

AREA = box(0.0, 0.0, 10.0, 10.0)
V0 = 1.5


def _sim_with_one_agent(model_type: str):
    simulation = jps.Simulation(
        model=_MODEL_BUILDERS[model_type]({}), geometry=AREA, dt=0.05
    )
    waypoint = simulation.add_waypoint_stage((9.0, 5.0), 0.5)
    journey = simulation.add_journey(jps.JourneyDescription([waypoint]))
    simulation.add_agent(
        create_agent_parameters(
            model_type,
            position=(1.0, 5.0),
            params={"v0": V0, "radius": 0.15},
            journey_id=journey,
            stage_id=waypoint,
        )
    )
    return simulation, next(iter(simulation.agents()))


@pytest.mark.parametrize("model_type", sorted(_MODEL_BUILDERS))
def test_every_model_is_mapped(model_type):
    """The map is keyed by state class name, so name the class, not a guess."""
    _, agent = _sim_with_one_agent(model_type)
    assert type(agent.model).__name__ in _MODEL_SPEED_ATTRS


@pytest.mark.parametrize("model_type", sorted(_MODEL_BUILDERS))
def test_desired_speed_round_trips(model_type):
    """Read the configured speed back, then halve it and see the change stick.

    The read alone is not enough: an attribute that exists but is ignored by the
    setter would still return v0 and look correct.
    """
    _, agent = _sim_with_one_agent(model_type)

    assert get_agent_desired_speed(agent) == pytest.approx(V0, rel=1e-6)
    assert set_agent_desired_speed(agent, V0 / 2)
    assert get_agent_desired_speed(agent) == pytest.approx(V0 / 2, rel=1e-6)


@pytest.mark.parametrize("model_type", sorted(_MODEL_BUILDERS))
def test_the_model_obeys_the_write(model_type):
    """Halving the desired speed must halve the distance actually walked.

    The round-trip test above cannot catch a model that stores the attribute
    and ignores it -- both sides of it are our own code. That is the failure
    mode worth fearing here, because a model that plans over a horizon
    (WarpDriver: time_horizon 2 s, step_size 0.5 s, against our dt of 0.05 s)
    could reasonably re-read desired speed only on replan. If it never
    re-read it, every smoke and FIC slowdown would vanish while the smoke CSV
    kept printing the factor -- silent, and indistinguishable from working.

    Measured over 4 s, long enough to cover several WarpDriver replans.
    """
    walked = {}
    for factor in (1.0, 0.5):
        simulation, agent = _sim_with_one_agent(model_type)
        set_agent_desired_speed(agent, V0 * factor)
        start = agent.position[0]
        while simulation.elapsed_time() < 4.0:
            simulation.iterate()
        walked[factor] = next(iter(simulation.agents())).position[0] - start

    # Free walking down an empty corridor, so distance tracks desired speed
    # directly. 15 % absorbs each model's acceleration ramp.
    assert walked[1.0] > 1.0, "the agent did not walk at all"
    assert walked[0.5] / walked[1.0] == pytest.approx(0.5, rel=0.15)
