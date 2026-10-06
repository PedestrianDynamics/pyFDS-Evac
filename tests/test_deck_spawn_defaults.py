"""Deck-wide spawn defaults: ``simulationParams.number``, ``.radius``, ``.v0`` (#567).

A distribution that leaves out ``number``, ``radius`` or ``v0`` takes the
deck's ``simulationParams`` value, else 10 agents, 0.2 m and 1.25 m/s. The
same rule holds with journeys (Haspel, complete initialiser) and without
(station_fahy, fallback initialiser); nothing is taken from another
distribution. Before #567 the fallback copied the first distribution's
values and defaulted ``number`` to 100, and the journey path ignored
``simulationParams``.

Pre-movement and flow spawning are off: with pre-movement on, agents spawn
at speed 0 and the assertions would not concern ``v0``.
"""

from __future__ import annotations

import contextlib
import copy
import io
import json
from types import SimpleNamespace

import jupedsim as jps
import pytest

from pyfds_evac.core import simulation_init
from pyfds_evac.core.scenario import Scenario, load_scenario, run_scenario
from pyfds_evac.core.simulation_init import (
    DEFAULT_SPAWN_PARAMS,
    initialize_simulation_from_json,
)

# Haspel has journeys (complete initialiser); station_fahy has none (fallback).
ASSETS = ["assets/Haspel", "assets/station_fahy"]
SPAWN_KEYS = ("number", "radius", "v0", "desired_speed")


def _stripped_raw(asset: str, drop: tuple[str, ...]) -> tuple[dict, list[str]]:
    """The asset's scenario with *drop* removed from every distribution."""
    raw = copy.deepcopy(load_scenario(asset).raw)
    keys = list(raw["distributions"])
    for key in keys:
        params = raw["distributions"][key].get("parameters", {})
        if isinstance(params, str):
            params = json.loads(params)
        for name in [n for n in params if n.startswith(drop)]:
            params.pop(name)
        params["use_premovement"] = False
        params["use_flow_spawning"] = False
        raw["distributions"][key]["parameters"] = params
    return raw, keys


def _first_populated(raw: dict, keys: list[str]) -> str:
    """The first distribution that places agents (Haspel's first has 0)."""
    return next(k for k in keys if raw["distributions"][k]["parameters"].get("number"))


def _spawn(asset: str, raw: dict, tmp_path, **sim_params) -> SimpleNamespace:
    """Initialise *raw* with ``simulationParams`` extended by *sim_params*.

    ``flows`` holds the parameters stored for flow-spawned distributions.
    """
    scenario = load_scenario(asset)
    path = tmp_path / "config.json"
    path.write_text(json.dumps(raw))
    simulation = jps.Simulation(
        model=jps.CollisionFreeSpeedModel(), geometry=scenario.walkable_polygon
    )
    with contextlib.redirect_stdout(io.StringIO()):
        _, _, radii, info = initialize_simulation_from_json(
            str(path),
            simulation,
            SimpleNamespace(polygon=scenario.walkable_polygon),
            seed=1,
            global_parameters=SimpleNamespace(**{**scenario.sim_params, **sim_params}),
        )
    return SimpleNamespace(
        count=simulation.agent_count(),
        speeds={round(a.model.desired_speed, 9) for a in simulation.agents()},
        radii={round(r, 9) for r in radii.values()},
        flows=[flow["params"] for flow in info.get("flow_distributions", [])],
    )


@pytest.mark.parametrize("asset", ASSETS)
def test_no_inheritance_from_the_first_distribution(asset, tmp_path):
    raw, keys = _stripped_raw(asset, ("v0", "desired_speed", "radius"))
    first = _first_populated(raw, keys)
    raw["distributions"][first]["parameters"].update(v0=1.5, radius=0.15)
    spawned = _spawn(asset, raw, tmp_path)
    assert spawned.speeds == {1.5, DEFAULT_SPAWN_PARAMS["v0"]}
    assert spawned.radii == {0.15, DEFAULT_SPAWN_PARAMS["radius"]}


@pytest.mark.parametrize("asset", ASSETS)
def test_sim_params_are_deck_wide_defaults(asset, tmp_path):
    raw, keys = _stripped_raw(asset, SPAWN_KEYS)
    spawned = _spawn(asset, raw, tmp_path, v0=1.1, radius=0.18, number=3)
    assert spawned.count == 3 * len(keys)
    assert spawned.speeds == {1.1}
    assert spawned.radii == {0.18}


@pytest.mark.parametrize("asset", ASSETS)
def test_distribution_values_win_over_sim_params(asset, tmp_path):
    raw, keys = _stripped_raw(asset, SPAWN_KEYS)
    for key in keys:
        raw["distributions"][key]["parameters"]["number"] = 2
    raw["distributions"][keys[0]]["parameters"].update(number=4, v0=1.5, radius=0.15)
    spawned = _spawn(asset, raw, tmp_path, v0=1.1, radius=0.18, number=3)
    assert spawned.count == 4 + 2 * (len(keys) - 1)
    assert spawned.speeds == {1.5, 1.1}
    assert spawned.radii == {0.15, 0.18}


@pytest.mark.parametrize("asset", ASSETS)
def test_default_count_is_ten(asset, tmp_path):
    """One distribution without ``number`` places 10; the others keep theirs.

    Only one: station_fahy's smaller spawn areas cannot hold 10 agents.
    """
    raw, keys = _stripped_raw(asset, ())
    first = _first_populated(raw, keys)
    full = _spawn(asset, raw, tmp_path).count
    own = raw["distributions"][first]["parameters"].pop("number")
    assert DEFAULT_SPAWN_PARAMS["number"] == 10
    assert _spawn(asset, raw, tmp_path).count == full - own + 10


def test_whole_area_fallback_uses_the_defaults(tmp_path):
    """Without distributions the walkable area takes the deck-wide defaults."""
    asset = ASSETS[1]
    raw = copy.deepcopy(load_scenario(asset).raw)
    raw["distributions"] = {}
    assert _spawn(asset, raw, tmp_path).count == 10
    spawned = _spawn(asset, raw, tmp_path, number=5, radius=0.18)
    assert spawned.count == 5
    assert spawned.radii == {0.18}


@pytest.mark.parametrize("asset", ASSETS)
def test_alias_wins_over_sim_params(asset, tmp_path):
    """``desired_speed`` is the distribution's own ``v0``, not a deck value."""
    raw, keys = _stripped_raw(asset, ("v0", "desired_speed"))
    raw["distributions"][_first_populated(raw, keys)]["parameters"]["desired_speed"] = (
        1.5
    )
    spawned = _spawn(asset, raw, tmp_path, v0=1.1)
    assert spawned.speeds == {1.5, 1.1}


def _flow_raw(asset: str) -> dict:
    """*asset* with every distribution flow-spawned in 0-1 s, no spawn keys."""
    raw, keys = _stripped_raw(asset, SPAWN_KEYS)
    for key in keys:
        raw["distributions"][key]["parameters"].update(
            use_flow_spawning=True, flow_start_time=0, flow_end_time=1
        )
    return raw


@pytest.mark.parametrize("asset", ASSETS)
def test_flow_distributions_store_the_deck_defaults(asset, tmp_path):
    raw = _flow_raw(asset)
    spawned = _spawn(asset, raw, tmp_path, v0=1.1, radius=0.18, number=3)
    assert len(spawned.flows) == len(raw["distributions"])
    for params in spawned.flows:
        assert (params["number"], params["radius"], params["v0"]) == (3, 0.18, 1.1)


@pytest.mark.parametrize("asset", ASSETS)
def test_flow_agents_spawn_with_the_deck_defaults(asset, monkeypatch):
    """Agents added during the run take ``simulationParams.v0`` and ``.radius``."""
    raw = _flow_raw(asset)
    sim_params = raw["config"]["simulation_settings"]["simulationParams"]
    sim_params.update(max_simulation_time=3.0, v0=1.1, radius=0.18, number=1)
    scenario = Scenario(
        raw=raw,
        walkable_area_wkt=load_scenario(asset).walkable_polygon.wkt,
        model_type="CollisionFreeSpeedModel",
        seed=1,
        sim_params=sim_params,
        source_path=None,
    )
    built = []
    create = simulation_init.create_agent_parameters

    def recording(*args, **kwargs):
        agent = create(*args, **kwargs)
        built.append((round(agent.desired_speed, 9), round(agent.radius, 9)))
        return agent

    monkeypatch.setattr(simulation_init, "create_agent_parameters", recording)
    with contextlib.redirect_stdout(io.StringIO()):
        run_scenario(scenario, seed=1).cleanup()
    # A blocked spawn is retried, so there can be more calls than agents.
    assert len(built) >= len(raw["distributions"])
    assert set(built) == {(1.1, 0.18)}
