"""SocialForceModel decks that omit agent keys, and how spawn errors surface (#568).

A deck's ``simulationParams`` may omit ``relaxation_time``, ``agent_strength``
or ``agent_range``. Each missing key takes the value the SFM branch of
``create_agent_parameters`` uses without global parameters (0.5, 2000, 0.08,
equal to JuPedSim 1.4.2's ``SocialForceModelAgentParameters`` defaults). The
missing key used to raise ``AttributeError``, which the journey path then
reported as a spawn area that is too small.

Fixture: ``assets/t_junction`` (one distribution, journeys, flow spawning).
"""

from __future__ import annotations

import contextlib
import io
import json
import math
from types import SimpleNamespace

import jupedsim as jps
import pedpy
import pytest

from pyfds_evac.core import load_scenario, run_scenario, simulation_init
from pyfds_evac.core.scenario import _build_model
from pyfds_evac.core.simulation_init import create_agent_parameters

SFM_KEYS = ("relaxation_time", "agent_strength", "agent_range")
DEFAULTS = {"relaxation_time": 0.5, "agent_strength": 2000, "agent_range": 0.08}
SET = {"relaxation_time": 0.7, "agent_strength": 1500, "agent_range": 0.1}
T_JUNCTION = "assets/t_junction"


def _sfm(global_params):
    params = create_agent_parameters(
        "SocialForceModel", (0.0, 0.0), {"v0": 1.0}, global_params=global_params
    )
    return {
        "relaxation_time": params.reaction_time,
        "agent_strength": params.agent_scale,
        "agent_range": params.force_distance,
    }


def test_sfm_keys_all_missing_take_the_defaults():
    assert _sfm(SimpleNamespace()) == pytest.approx(DEFAULTS)


@pytest.mark.parametrize("missing", SFM_KEYS)
def test_sfm_one_key_missing_keeps_the_others(missing):
    given = {k: v for k, v in SET.items() if k != missing}
    assert _sfm(SimpleNamespace(**given)) == pytest.approx(
        {**SET, missing: DEFAULTS[missing]}
    )


def _sfm_scenario_without_keys():
    scenario = load_scenario(T_JUNCTION)
    scenario.set_model_type("SocialForceModel")
    for key in SFM_KEYS:
        scenario.sim_params.pop(key, None)
        scenario._simulation_params().pop(key, None)
    return scenario


def _initialize_t_junction(tmp_path, **parameters):
    """Journey path, immediate spawning of 5 agents on t_junction."""
    scenario = load_scenario(T_JUNCTION)
    raw = json.loads(json.dumps(scenario.raw))
    for dist in raw["distributions"].values():
        dist["parameters"].update(
            {"use_flow_spawning": False, "number": 5, **parameters}
        )
    deck = tmp_path / "deck.json"
    deck.write_text(json.dumps(raw), encoding="utf-8")
    walkable = scenario.walkable_polygon
    simulation = jps.Simulation(
        model=_build_model("CollisionFreeSpeedModel", {}), geometry=walkable
    )
    with contextlib.redirect_stdout(io.StringIO()):
        simulation_init.initialize_simulation_from_json(
            str(deck), simulation, pedpy.WalkableArea(walkable), seed=1
        )


@pytest.mark.parametrize("error", [KeyError, ValueError, RuntimeError])
def test_journey_path_keeps_the_type_of_a_non_placement_error(
    tmp_path, monkeypatch, error
):
    def broken(*args, **kwargs):
        raise error("not a placement error")

    monkeypatch.setattr(simulation_init, "create_agent_parameters", broken)
    with pytest.raises(error) as excinfo:
        _initialize_t_junction(tmp_path)
    assert "spawn area is too small" not in str(excinfo.value)


def test_journey_path_reports_a_configuration_error_as_such(tmp_path):
    with pytest.raises(ValueError) as excinfo:
        _initialize_t_junction(
            tmp_path, use_premovement=True, premovement_distribution="typo"
        )
    assert "spawn area is too small" not in str(excinfo.value)


def test_journey_path_reports_an_overfull_area_as_placement(tmp_path):
    with pytest.raises(Exception, match="spawn area is too small") as excinfo:
        _initialize_t_junction(tmp_path, number=100000)
    assert isinstance(excinfo.value.__cause__, Exception)


def test_flow_spawning_with_sfm_keys_missing_spawns_agents():
    scenario = _sfm_scenario_without_keys()
    scenario.set_max_time(15)
    with contextlib.redirect_stdout(io.StringIO()):
        result = run_scenario(scenario, seed=1)
    try:
        assert result.metrics["agents_not_spawned"] < 200
    finally:
        result.cleanup()


# --- model-level SFM parameters (#611) and the friction clamp (#635) --------

WALL_DECK_GEOMETRY = [(0, 0), (60, 0), (60, 4), (0, 4)]
WALL_DECK_EXIT = [(58, 0), (60, 0), (60, 4), (58, 4)]


def _sfm_model(params):
    return _build_model("SocialForceModel", params)


def test_sfm_body_force_is_read_from_the_deck():
    assert _sfm_model({"sfm_body_force": 50000.0}).body_force == 50000.0


def test_sfm_body_force_defaults_to_jupedsim_and_ignores_agent_strength():
    assert _sfm_model({}).body_force == 120000.0
    assert _sfm_model({"agent_strength": 1500}).body_force == 120000.0


def test_sfm_declared_friction_is_clamped_with_a_warning(caplog):
    with caplog.at_level("WARNING", logger="pyfds_evac"):
        model = _sfm_model({"sfm_friction": 240000})
    assert model.friction == 0.0
    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert len(warnings) == 1
    assert "1677" in warnings[0].getMessage()
    assert "#635" in warnings[0].getMessage()
    assert "240000" in warnings[0].getMessage()


@pytest.mark.parametrize("params", [{}, {"sfm_friction": 0}])
def test_sfm_friction_is_zero_and_silent_unless_declared_positive(caplog, params):
    with caplog.at_level("WARNING", logger="pyfds_evac"):
        model = _sfm_model(params)
    assert model.friction == 0.0
    assert not [r for r in caplog.records if r.levelname == "WARNING"]


@pytest.mark.parametrize("key", ["sfm_body_force", "sfm_friction"])
@pytest.mark.parametrize("value", [-1.0, float("nan"), float("inf"), "x", True])
def test_sfm_invalid_model_parameter_raises(key, value):
    with pytest.raises(ValueError, match=key):
        _sfm_model({key: value})


def test_sfm_obstacle_scale_is_read_from_the_deck():
    def obstacle_scale(global_params):
        return create_agent_parameters(
            "SocialForceModel", (0.0, 0.0), {"v0": 1.0}, global_params=global_params
        ).obstacle_scale

    assert obstacle_scale(SimpleNamespace(sfm_obstacle_scale=1500)) == 1500
    assert obstacle_scale(SimpleNamespace(agent_strength=1500)) == 2000


def test_sfm_builder_raises_no_deprecation_warning():
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        _sfm_model({"sfm_body_force": 120000.0, "sfm_friction": 0})


def _wall_push_speed(params, *, y=0.25, radius=0.3, mass=80.0, dt=0.01):
    """Normal speed after one step of an agent at rest overlapping a wall."""
    simulation = jps.Simulation(
        model=_sfm_model(params), geometry=WALL_DECK_GEOMETRY, dt=dt
    )
    exit_id = simulation.add_exit_stage(WALL_DECK_EXIT)
    journey = simulation.add_journey(jps.JourneyDescription([exit_id]))
    agent = create_agent_parameters(
        "SocialForceModel",
        (1.0, y),
        {"v0": 0.0, "radius": radius},
        global_params=SimpleNamespace(),
        journey_id=journey,
        stage_id=exit_id,
    )
    agent.mass = mass
    agent_id = simulation.add_agent(agent)
    simulation.iterate()
    return simulation.agent(agent_id).model.velocity[1]


@pytest.mark.parametrize(
    ("body_force", "expected"), [(120000.0, 1.217061), (2000.0, 0.479561)]
)
def test_sfm_wall_push_matches_the_closed_form(body_force, expected):
    """One step: v_y = (A exp((r - d)/B) + k (r - d)) / m * dt, d = 0.25 m.

    A = obstacle_scale 2000 N, B = 0.08 m, r = 0.3 m, m = 80 kg, dt = 0.01 s;
    desired speed 0 and friction 0 leave the radial wall force alone.
    """
    d, r, a, b, m, dt = 0.25, 0.3, 2000.0, 0.08, 80.0, 0.01
    closed_form = (a * math.exp((r - d) / b) + body_force * (r - d)) / m * dt
    assert closed_form == pytest.approx(expected, abs=5e-7)
    speed = _wall_push_speed({"sfm_body_force": body_force, "sfm_friction": 0})
    assert speed == pytest.approx(closed_form, rel=1e-9)


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason="jupedsim#1677: wall friction has the wrong sign; remove the "
    "friction clamp (#635) once a release with the fix is pinned",
)
def test_jupedsim_wall_friction_sign_canary():
    """Canary for #635, on raw JuPedSim with the friction clamp bypassed.

    An agent sliding along a wall at 1 m/s must be slowed by friction. In
    JuPedSim 1.4.2 it is accelerated to about 10.6 m/s in 20 ms, so this
    fails as expected. An XPASS means the installed JuPedSim has the fix:
    raise the pin and remove the clamp. Any other error (e.g. a removed
    API) is not the expected failure and also turns the run red.
    """
    simulation = jps.Simulation(
        model=jps.SocialForceModel(body_force=120000.0, friction=240000.0),
        geometry=WALL_DECK_GEOMETRY,
        dt=0.001,
    )
    exit_id = simulation.add_exit_stage(WALL_DECK_EXIT)
    journey = simulation.add_journey(jps.JourneyDescription([exit_id]))
    agent_id = simulation.add_agent(
        jps.SocialForceModelAgentParameters(
            journey_id=journey,
            stage_id=exit_id,
            position=(1.0, 0.25),
            velocity=(1.0, 0.0),
            desired_speed=1.0,
            reaction_time=0.5,
            radius=0.3,
        )
    )
    for _ in range(20):
        simulation.iterate()
    assert 0.0 <= simulation.agent(agent_id).model.velocity[0] < 0.5


def test_sfm_manifest_records_the_effective_model_parameters():
    scenario = load_scenario(T_JUNCTION)
    scenario.set_model_type("SocialForceModel")
    scenario.sim_params.update({"sfm_body_force": 50000.0, "sfm_friction": 240000})
    scenario.set_max_time(1)
    with contextlib.redirect_stdout(io.StringIO()):
        result = run_scenario(scenario, seed=1)
    try:
        with open(result.manifest_file, encoding="utf-8") as handle:
            recorded = json.load(handle)["sfm"]
    finally:
        result.cleanup()
    assert recorded == {
        "body_force": 50000.0,
        "friction": 0.0,
        "friction_requested": 240000.0,
        "friction_clamped": True,
    }
