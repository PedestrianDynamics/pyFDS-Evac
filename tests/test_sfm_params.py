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


def test_journey_path_keeps_the_type_of_a_non_placement_error(tmp_path, monkeypatch):
    scenario = load_scenario(T_JUNCTION)
    raw = json.loads(json.dumps(scenario.raw))
    for dist in raw["distributions"].values():
        dist["parameters"]["use_flow_spawning"] = False
        dist["parameters"]["number"] = 5
    deck = tmp_path / "deck.json"
    deck.write_text(json.dumps(raw), encoding="utf-8")

    def broken(*args, **kwargs):
        raise KeyError("not a placement error")

    monkeypatch.setattr(simulation_init, "create_agent_parameters", broken)
    walkable = scenario.walkable_polygon
    simulation = jps.Simulation(
        model=_build_model("CollisionFreeSpeedModel", {}), geometry=walkable
    )
    with pytest.raises(KeyError) as excinfo, contextlib.redirect_stdout(io.StringIO()):
        simulation_init.initialize_simulation_from_json(
            str(deck), simulation, pedpy.WalkableArea(walkable), seed=1
        )
    assert "spawn area is too small" not in str(excinfo.value)


def test_flow_spawning_with_sfm_keys_missing_spawns_agents():
    scenario = _sfm_scenario_without_keys()
    scenario.set_max_time(15)
    with contextlib.redirect_stdout(io.StringIO()):
        result = run_scenario(scenario, seed=1)
    try:
        assert result.metrics["agents_not_spawned"] < 200
    finally:
        result.cleanup()
