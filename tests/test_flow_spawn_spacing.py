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

import pyfds_evac.core.simulation_init as simulation_init
from pyfds_evac.core.scenario import run_scenario
from pyfds_evac.core.simulation_init import (
    _CONTACT_OWN_RADIUS,
    _CONTACT_RADIUS_SUM,
    _crowds_agents,
    _jupedsim_positions,
)

D1 = "jps-distributions_1"
AREA = box(1.0, 1.0, 4.0, 5.0)
STANDING_R = 0.3
FLOW_R = 0.15


def _scenario_with_flow(
    model, area, standing, flow, flow_end_s, max_time_s, premovement_s=100.0
):
    """*standing* agents that wait *premovement_s* in *area*, and a flow of
    *flow* into it."""
    n_standing, r_standing = standing
    n_flow, r_flow = flow
    scenario = _scenario(
        max_time_s,
        number=n_standing,
        radius=r_standing,
        use_premovement=True,
        premovement_distribution="constant",
        premovement_param_a=premovement_s,
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


@pytest.mark.parametrize("model", ["CollisionFreeSpeedModel", "SocialForceModel"])
@pytest.mark.parametrize("seed", [1, 2, 3])
def test_flow_agents_keep_the_spacing_to_walking_agents(monkeypatch, model, seed):
    """The agents already in the area walk off while the flow enters.

    JuPedSim refuses against where they stood at the start of the last
    iteration, not where they are; the spacing holds to where they are.
    """
    scenario = _scenario_with_flow(
        model, AREA, (12, STANDING_R), (20, FLOW_R), 2.0, 3.0, premovement_s=0.0
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


def _count_snapshots(monkeypatch, scenario):
    """Simulated times at which ``_jupedsim_positions`` was taken."""
    calls = []
    take = simulation_init._jupedsim_positions

    def counting(simulation):
        calls.append(simulation.elapsed_time())
        return take(simulation)

    monkeypatch.setattr(simulation_init, "_jupedsim_positions", counting)
    _, result, _ = _run_recording_gaps(monkeypatch, scenario, 1)
    return calls, result


def test_positions_are_not_kept_once_no_flow_can_follow(monkeypatch):
    """The flow window closes at 1 s of a 3 s run (dt 0.01 s)."""
    scenario = _scenario_with_flow(
        "CollisionFreeSpeedModel", AREA, (0, STANDING_R), (50, FLOW_R), 1.0, 3.0
    )
    calls, _ = _count_snapshots(monkeypatch, scenario)
    assert calls
    assert max(calls) <= 1.0 + 1e-9


def test_positions_are_kept_only_before_a_due_spawn(monkeypatch):
    """Five agents over a 2 s window in a 3 s run: a spawn every 0.4 s.

    One snapshot before the run, and one before each step with a spawn
    due, rather than one per step.
    """
    scenario = _scenario_with_flow(
        "CollisionFreeSpeedModel", AREA, (0, STANDING_R), (5, FLOW_R), 2.0, 3.0
    )
    calls, result = _count_snapshots(monkeypatch, scenario)
    assert result.metrics["flow_spawns_deferred"] == 0
    assert 5 <= len(calls) <= 1 + 2 * 5


def _occupied(*agents, seen=None):
    """*agents* ``(position, radius)``; JuPedSim saw them at *seen*, or there."""
    xy = np.array([position for position, _ in agents], dtype=float).reshape(-1, 2)
    radii = np.array([radius for _, radius in agents], dtype=float)
    seen_xy = xy if seen is None else np.array(seen, dtype=float).reshape(-1, 2)
    return xy, radii, seen_xy


def _parameters(position, radius):
    return jps.CollisionFreeSpeedModelAgentParameters(position=position, radius=radius)


# Radii 0.25 and 0.125 m and the gaps below are exact in binary, so that
# contact (0.375 m, or 0.125 m for the social force model) is tested as is.
BIG_R = 0.25
SMALL_R = 0.125
CONTACT = BIG_R + SMALL_R
AFTER_CONTACT = float(np.nextafter(CONTACT, 1.0))
AFTER_OWN = float(np.nextafter(SMALL_R, 1.0))


@pytest.mark.parametrize(
    ("gap", "model", "crowds"),
    [
        (0.5, "CollisionFreeSpeedModel", False),  # clear of 2 * 0.25 m
        (0.4, "CollisionFreeSpeedModel", True),  # the model would add it
        (AFTER_CONTACT, "CollisionFreeSpeedModel", True),
        (CONTACT, "CollisionFreeSpeedModel", False),  # left to the refusal
        (CONTACT, "AnticipationVelocityModel", False),
        (CONTACT, "SocialForceModel", True),
        (AFTER_OWN, "SocialForceModel", True),
        (SMALL_R, "SocialForceModel", False),  # left to the refusal
        (0.0, "WarpDriverModel", True),  # no refusal to leave it to
        (0.0, "GeneralizedCentrifugalForceModel", True),  # not mirrored
    ],
)
def test_crowds_agents(gap, model, crowds):
    occupied = _occupied(((0.0, 0.0), BIG_R))
    parameters = _parameters((gap, 0.0), SMALL_R)
    assert _crowds_agents(model, parameters, SMALL_R, occupied) is crowds


@pytest.mark.parametrize(
    ("now", "seen", "crowds"),
    [
        # Inside contact now, outside where JuPedSim saw it: JuPedSim adds it.
        (0.375, 0.5, True),
        # Outside contact now, inside where JuPedSim saw it: JuPedSim refuses.
        (0.5, 0.375, False),
    ],
)
def test_contact_is_measured_where_jupedsim_saw_the_agent(now, seen, crowds):
    occupied = _occupied(((-now, 0.0), BIG_R), seen=[(-seen, 0.0)])
    parameters = _parameters((0.0, 0.0), SMALL_R)
    model = "CollisionFreeSpeedModel"
    assert _crowds_agents(model, parameters, SMALL_R, occupied) is crowds


def test_an_empty_run_is_never_crowded():
    assert not _crowds_agents(
        "WarpDriverModel", _parameters((1, 1), 0.2), 0.2, _occupied()
    )


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
}


@pytest.mark.parametrize("radii", [(BIG_R, SMALL_R), (SMALL_R, BIG_R)])
@pytest.mark.parametrize(
    "model_type", sorted(_CONTACT_RADIUS_SUM | _CONTACT_OWN_RADIUS)
)
def test_jupedsim_refuses_at_contact_and_spends_an_id(model_type, radii):
    """The JuPedSim facts that ``_crowds_agents`` mirrors.

    The agent added second is refused at contact, inclusive, accepted one
    float further, and the refusal spends an agent id.
    """
    model, parameters = MODELS[model_type]
    simulation = jps.Simulation(model=model(), geometry=box(0, 0, 10, 10))
    exit_stage = simulation.add_exit_stage(Polygon(box(9, 9, 9.5, 9.5)))
    journey = simulation.add_journey(jps.JourneyDescription([exit_stage]))
    standing_r, added_r = radii
    contact = added_r if model_type in _CONTACT_OWN_RADIUS else standing_r + added_r

    def add(x, radius):
        return simulation.add_agent(
            parameters(
                position=(x, 5.0),
                journey_id=journey,
                stage_id=exit_stage,
                radius=radius,
            )
        )

    first = add(5.0, standing_r)
    with pytest.raises(RuntimeError):
        add(5.0 + contact, added_r)
    second = add(float(np.nextafter(5.0 + contact, 10.0)), added_r)
    assert second == first + 2
    standing = next(a for a in simulation.agents() if a.id == first)
    assert standing.model.radius == standing_r


@pytest.mark.parametrize(
    "model_type", sorted(_CONTACT_RADIUS_SUM | _CONTACT_OWN_RADIUS)
)
def test_jupedsim_refuses_where_the_agent_stood_before_the_iteration(model_type):
    """``add_agent`` measures to where a walking agent stood when the last
    iteration began, not to where it is now (``_jupedsim_positions``)."""
    model, parameters = MODELS[model_type]
    simulation = jps.Simulation(model=model(), geometry=box(0, 0, 10, 10), dt=0.05)
    exit_stage = simulation.add_exit_stage(Polygon(box(9.5, 4.5, 10, 5.5)))
    journey = simulation.add_journey(jps.JourneyDescription([exit_stage]))

    def add(x):
        return simulation.add_agent(
            parameters(
                position=(x, 5.0), journey_id=journey, stage_id=exit_stage, radius=0.2
            )
        )

    add(2.0)
    for _ in range(40):
        simulation.iterate()
    seen = _jupedsim_positions(simulation)
    simulation.iterate()
    walker = next(iter(simulation.agents()))
    before = seen[walker.id][0]
    assert walker.position[0] > before
    contact = 0.2 if model_type in _CONTACT_OWN_RADIUS else 0.4
    # Within contact of where it stood, beyond contact of where it is.
    x = (before - contact + walker.position[0] - contact) / 2
    assert walker.position[0] - x > contact
    with pytest.raises(RuntimeError):
        add(x)


def test_jupedsim_refuses_next_to_an_agent_it_just_removed():
    """An agent in ``removed_agents`` after an iteration is still listed,
    and ``add_agent`` still measures to where it stood before that
    iteration; so ``_jupedsim_positions`` keeps it."""
    model, parameters = MODELS["CollisionFreeSpeedModel"]
    simulation = jps.Simulation(model=model(), geometry=box(0, 0, 10, 10), dt=0.01)
    exit_stage = simulation.add_exit_stage(Polygon(box(9, 4, 10, 6)))
    journey = simulation.add_journey(jps.JourneyDescription([exit_stage]))

    def add(x):
        return simulation.add_agent(
            parameters(
                position=(x, 5.0), journey_id=journey, stage_id=exit_stage, radius=0.2
            )
        )

    walker = add(8.5)
    for _ in range(5000):
        seen = _jupedsim_positions(simulation)
        simulation.iterate()
        if list(simulation.removed_agents()):
            break
    assert list(simulation.removed_agents()) == [walker]
    assert [a.id for a in simulation.agents()] == [walker]
    with pytest.raises(RuntimeError):
        add(seen[walker][0] - 0.39)
