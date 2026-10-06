"""``desired_speed*`` in a scenario JSON are aliases of the ``v0*`` keys (#143).

``Scenario.set_agent_params`` accepts both key families and writes both into
``raw``; ``run_scenario`` re-reads ``raw`` through
``initialize_simulation_from_json``. The loader copies an alias to its
``v0*`` key, accepts an equal pair and rejects a conflicting pair.

Pre-movement and flow spawning are off: with pre-movement on, agents spawn
at speed 0 and the assertion would not concern the alias.
"""

from __future__ import annotations

import contextlib
import copy
import io
import json
from types import SimpleNamespace

import jupedsim as jps
import pytest
from shapely.geometry import box

from pyfds_evac.core.agent_params import check_speed_aliases
from pyfds_evac.core.scenario import load_scenario
from pyfds_evac.core.simulation_init import (
    create_agent_parameters,
    initialize_simulation_from_json,
)

# Haspel has journeys (complete initialiser); station_fahy has none (fallback).
ASSETS = ["assets/Haspel", "assets/station_fahy"]
SPEED_PREFIXES = ("v0", "desired_speed")


def _raw_without_speed_keys(asset: str) -> tuple[dict, list[str]]:
    scenario = load_scenario(asset)
    raw = copy.deepcopy(scenario.raw)
    keys = list(raw["distributions"])
    for key in keys:
        params = raw["distributions"][key].get("parameters", {})
        if isinstance(params, str):
            params = json.loads(params)
        for name in [n for n in params if n.startswith(SPEED_PREFIXES)]:
            params.pop(name)
        params["use_premovement"] = False
        params["use_flow_spawning"] = False
        raw["distributions"][key]["parameters"] = params
    return raw, keys


def _set_on_all(raw: dict, keys: list[str], **values) -> dict:
    for key in keys:
        raw["distributions"][key]["parameters"].update(values)
    return raw


def _spawn_speeds(asset: str, raw: dict, tmp_path) -> list[float]:
    """Desired speeds of the spawned agents, ordered by agent id."""
    scenario = load_scenario(asset)
    path = tmp_path / "config.json"
    path.write_text(json.dumps(raw))
    simulation = jps.Simulation(
        model=jps.CollisionFreeSpeedModel(), geometry=scenario.walkable_polygon
    )
    with contextlib.redirect_stdout(io.StringIO()):
        initialize_simulation_from_json(
            str(path),
            simulation,
            SimpleNamespace(polygon=scenario.walkable_polygon),
            seed=1,
            global_parameters=SimpleNamespace(**scenario.sim_params),
        )
    agents = sorted(simulation.agents(), key=lambda agent: agent.id)
    assert agents, f"{asset}: no agents spawned"
    return [agent.model.desired_speed for agent in agents]


@pytest.mark.parametrize("asset", ASSETS)
def test_desired_speed_sets_the_spawn_speed(asset, tmp_path):
    raw, keys = _raw_without_speed_keys(asset)
    speeds = _spawn_speeds(asset, _set_on_all(raw, keys, desired_speed=1.5), tmp_path)
    assert set(speeds) == {1.5}


@pytest.mark.parametrize("asset", ASSETS)
def test_gaussian_alias_draws_equal_gaussian_v0(asset, tmp_path):
    raw, keys = _raw_without_speed_keys(asset)
    alias = _set_on_all(
        copy.deepcopy(raw),
        keys,
        desired_speed=1.4,
        desired_speed_distribution="gaussian",
        desired_speed_std=0.2,
    )
    canonical = _set_on_all(raw, keys, v0=1.4, v0_distribution="gaussian", v0_std=0.2)
    alias_speeds = _spawn_speeds(asset, alias, tmp_path)
    assert len(set(alias_speeds)) > 1
    assert alias_speeds == _spawn_speeds(asset, canonical, tmp_path)


def test_conflicting_pair_raises(tmp_path):
    raw, keys = _raw_without_speed_keys(ASSETS[0])
    raw["distributions"][keys[0]]["parameters"].update(desired_speed=1.5, v0=1.2)
    with pytest.raises(ValueError, match=r"desired_speed=1\.5 and v0=1\.2"):
        _spawn_speeds(ASSETS[0], raw, tmp_path)


def test_conflict_in_string_parameters_raises(tmp_path):
    raw, keys = _raw_without_speed_keys(ASSETS[0])
    params = raw["distributions"][keys[0]]["parameters"]
    params.update(desired_speed_std=0.3, v0_std=0.1)
    raw["distributions"][keys[0]]["parameters"] = json.dumps(params)
    with pytest.raises(ValueError, match=r"desired_speed_std=0\.3 and v0_std=0\.1"):
        _spawn_speeds(ASSETS[0], raw, tmp_path)


def test_equal_pair_is_accepted(tmp_path):
    """``set_agent_params`` writes both families with equal values."""
    raw, keys = _raw_without_speed_keys(ASSETS[0])
    raw = _set_on_all(raw, keys, desired_speed=1.5, v0=1.5)
    assert set(_spawn_speeds(ASSETS[0], raw, tmp_path)) == {1.5}


def test_social_force_default_speed_is_1_25():
    simulation = jps.Simulation(
        model=jps.SocialForceModel(), geometry=box(0.0, 0.0, 10.0, 10.0)
    )
    waypoint = simulation.add_waypoint_stage((9.0, 5.0), 0.5)
    journey = simulation.add_journey(jps.JourneyDescription([waypoint]))
    simulation.add_agent(
        create_agent_parameters(
            "SocialForceModel",
            position=(1.0, 5.0),
            params={"radius": 0.15},
            journey_id=journey,
            stage_id=waypoint,
        )
    )
    assert next(iter(simulation.agents())).model.desired_speed == 1.25


def _run_error(raw: dict, tmp_path) -> str:
    with pytest.raises(ValueError) as exc:
        _spawn_speeds(ASSETS[0], copy.deepcopy(raw), tmp_path)
    return str(exc.value)


@pytest.mark.parametrize("encode", [False, True], ids=["dict", "string"])
def test_check_raises_the_run_error_and_leaves_raw_untouched(encode, tmp_path):
    """#612: the configuration check rejects what the run rejects, read-only."""
    raw, keys = _raw_without_speed_keys(ASSETS[0])
    params = raw["distributions"][keys[0]]["parameters"]
    params.update(desired_speed=1.5, v0=1.2, desired_speed_std=0.3)
    if encode:
        raw["distributions"][keys[0]]["parameters"] = json.dumps(params)
    before = copy.deepcopy(raw)
    with pytest.raises(ValueError) as exc:
        check_speed_aliases(raw)
    assert raw == before
    assert str(exc.value) == _run_error(raw, tmp_path)


def test_check_reports_the_first_conflicting_distribution(tmp_path):
    raw, keys = _raw_without_speed_keys(ASSETS[0])
    assert len(keys) > 1
    raw["distributions"][keys[0]]["parameters"].update(v0_std=0.1)
    raw["distributions"][keys[0]]["parameters"].update(desired_speed_std=0.2)
    raw["distributions"][keys[1]]["parameters"].update(desired_speed=1.5, v0=1.2)
    with pytest.raises(ValueError) as exc:
        check_speed_aliases(raw)
    assert repr(keys[0]) in str(exc.value)
    assert str(exc.value) == _run_error(raw, tmp_path)


@pytest.mark.parametrize(
    "parameters",
    [
        {"desired_speed": 1.5},
        {"desired_speed": 1.5, "v0": 1.5},
        {"desired_speed_std": 0.1, "v0": 1.2},
        "{not json",
        None,
    ],
)
def test_check_accepts_what_the_run_accepts(parameters):
    raw = {"distributions": {"a": {"parameters": parameters}, "b": "x"}}
    before = copy.deepcopy(raw)
    check_speed_aliases(raw)
    check_speed_aliases({"distributions": []})
    check_speed_aliases([])
    assert raw == before


@pytest.mark.parametrize("encode", [False, True], ids=["dict", "string"])
def test_check_reports_speed_before_distribution_before_std(encode):
    """Within one distribution the pairs are checked in alias-table order."""
    params = {
        "desired_speed": 1.5,
        "v0": 1.2,
        "desired_speed_distribution": "gaussian",
        "v0_distribution": "constant",
        "desired_speed_std": 0.3,
        "v0_std": 0.1,
    }
    expected = [
        "Distribution 'a' sets desired_speed=1.5 and v0=1.2; "
        "desired_speed is an alias of v0, set one of them",
        "Distribution 'a' sets desired_speed_distribution='gaussian' and "
        "v0_distribution='constant'; desired_speed_distribution is an alias "
        "of v0_distribution, set one of them",
        "Distribution 'a' sets desired_speed_std=0.3 and v0_std=0.1; "
        "desired_speed_std is an alias of v0_std, set one of them",
    ]
    for message in expected:
        encoded = json.dumps(params) if encode else dict(params)
        with pytest.raises(ValueError) as exc:
            check_speed_aliases({"distributions": {"a": {"parameters": encoded}}})
        assert str(exc.value) == message
        alias = next(iter(params))
        params.pop(alias)
        params.pop(alias.replace("desired_speed", "v0"))
