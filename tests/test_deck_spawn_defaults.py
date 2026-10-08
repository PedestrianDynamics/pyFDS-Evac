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


@pytest.mark.parametrize("asset", ASSETS)
def test_built_in_defaults_are_pinned(asset, tmp_path):
    """1.25 m/s (FDS+Evac VEL_MEAN), 0.2 m and 10 agents, as literals."""
    raw, keys = _stripped_raw(asset, ("v0", "desired_speed", "radius"))
    spawned = _spawn(asset, raw, tmp_path)
    assert spawned.speeds == {1.25}
    assert spawned.radii == {0.2}
    assert DEFAULT_SPAWN_PARAMS == {"number": 10, "radius": 0.2, "v0": 1.25}


@pytest.mark.parametrize("asset", ASSETS)
def test_numeric_strings_are_converted(asset, tmp_path):
    raw, keys = _stripped_raw(asset, SPAWN_KEYS)
    spawned = _spawn(asset, raw, tmp_path, v0="1.1", radius="0.18", number="3")
    assert spawned.count == 3 * len(keys)
    assert spawned.speeds == {1.1}
    assert spawned.radii == {0.18}


@pytest.mark.parametrize("asset", ASSETS)
@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("v0", "fast"),
        ("radius", [0.2]),
        ("number", "3.9"),
        ("number", float("inf")),
        ("v0", 10**400),
    ],
)
def test_non_numeric_sim_param_names_the_key(asset, key, value, tmp_path):
    raw, _ = _stripped_raw(asset, SPAWN_KEYS)
    with pytest.raises(ValueError, match=rf"simulationParams\.{key} must be a number"):
        _spawn(asset, raw, tmp_path, **{key: value})


@pytest.mark.parametrize("asset", ASSETS)
def test_count_edge_cases(asset, tmp_path):
    """Zero is a count, not unset; a float count is truncated like ``number``."""
    raw, keys = _stripped_raw(asset, ("number",))
    assert _spawn(asset, raw, tmp_path, number=0).count == 0
    assert _spawn(asset, raw, tmp_path, number=3.9).count == 3 * len(keys)
    raw["distributions"][keys[0]]["parameters"]["number"] = 0
    spawned = _spawn(asset, raw, tmp_path, number=3)
    assert spawned.count == 3 * (len(keys) - 1)


@pytest.mark.parametrize("asset", ASSETS)
@pytest.mark.parametrize("key", ["v0", "radius"])
@pytest.mark.parametrize("value", ["1e400", "nan", "inf", float("nan"), 0, -0.5])
def test_non_finite_or_non_positive_sim_param_names_the_key(
    asset, key, value, tmp_path
):
    raw, _ = _stripped_raw(asset, SPAWN_KEYS)
    with pytest.raises(
        ValueError, match=rf"simulationParams\.{key} must be finite and > 0"
    ):
        _spawn(asset, raw, tmp_path, **{key: value})


@pytest.mark.parametrize("asset", ASSETS)
@pytest.mark.parametrize(
    ("key", "value", "message"),
    [
        ("number", -1, "must be >= 0"),
        ("number", "-2", "must be >= 0"),
        ("number", True, "must be a number"),
        ("v0", True, "must be a number"),
        ("radius", False, "must be a number"),
    ],
)
def test_negative_or_boolean_sim_param_names_the_key(
    asset, key, value, message, tmp_path
):
    """A negative count and a boolean are rejected, not read as -1 or 1 (#649).

    One agent per area otherwise, so a valid deck places them all.
    """
    raw, _ = _stripped_raw(asset, SPAWN_KEYS)
    with pytest.raises(ValueError, match=rf"simulationParams\.{key} {message}"):
        _spawn(asset, raw, tmp_path, **{"number": 1, key: value})


@pytest.mark.parametrize("asset", ASSETS)
@pytest.mark.parametrize(
    ("key", "value", "message"),
    [
        ("v0", float("nan"), "must be finite and >= 0"),
        ("v0", float("inf"), "must be finite and >= 0"),
        ("v0", "1e400", "must be finite and >= 0"),
        ("v0", -0.5, "must be finite and >= 0"),
        ("v0", "-0.5", "must be finite and >= 0"),
        ("v0", True, "must be a number"),
        ("v0", "fast", "must be a number"),
        ("radius", float("nan"), "must be finite and > 0"),
        ("radius", float("-inf"), "must be finite and > 0"),
        ("radius", 0.0, "must be finite and > 0"),
        ("radius", "0", "must be finite and > 0"),
        ("radius", -0.2, "must be finite and > 0"),
        ("radius", True, "must be a number"),
        ("radius", [0.2], "must be a number"),
        ("number", -1, "must be >= 0"),
        ("number", "-1", "must be >= 0"),
        ("number", True, "must be a number"),
        ("number", "3.9", "must be a number"),
    ],
)
def test_out_of_range_distribution_value_names_key_and_area(
    asset, key, value, message, tmp_path
):
    """A spawn area's own value is read as a deck-wide one, v0 0 aside (#649).

    The scenario is written with ``json.dumps``, so NaN and Infinity reach
    the loader as the JSON literals ``json.loads`` accepts. One agent per
    area otherwise, so the deck is valid without the injected value.
    """
    raw, keys = _stripped_raw(asset, SPAWN_KEYS)
    assert _spawn(asset, raw, tmp_path, number=1).count == len(keys)
    dist = keys[0]
    raw["distributions"][dist]["parameters"][key] = value
    with pytest.raises(
        ValueError, match=rf"Distribution '{dist}': {key} {message}, got "
    ):
        _spawn(asset, raw, tmp_path, number=1)


@pytest.mark.parametrize("asset", ASSETS)
def test_stationary_distribution_keeps_v0_zero(asset, tmp_path):
    """v0 0 places agents that stand still, as the stationary FED checks use."""
    raw, keys = _stripped_raw(asset, SPAWN_KEYS)
    raw["distributions"][keys[0]]["parameters"].update(number=1, v0=0)
    spawned = _spawn(asset, raw, tmp_path, number=0)
    assert spawned.count == 1
    assert spawned.speeds == {0.0}


@pytest.mark.parametrize("asset", ASSETS)
def test_distribution_numeric_strings_are_converted(asset, tmp_path):
    """A spawn area's own numeric strings convert as the deck-wide ones do."""
    raw, keys = _stripped_raw(asset, SPAWN_KEYS)
    for key in keys:
        raw["distributions"][key]["parameters"]["number"] = 0
    raw["distributions"][keys[0]]["parameters"].update(
        number="2", v0="1.1", radius="0.25"
    )
    spawned = _spawn(asset, raw, tmp_path)
    assert spawned.count == 2
    assert spawned.speeds == {1.1}
    assert spawned.radii == {0.25}


@pytest.mark.parametrize("asset", ASSETS)
def test_valid_distribution_values_pass_unchanged(asset, tmp_path):
    """Integer-valued floats, numeric-string counts and a count of 0 still run."""
    raw, keys = _stripped_raw(asset, SPAWN_KEYS)
    for key in keys:
        raw["distributions"][key]["parameters"]["number"] = 0
    raw["distributions"][keys[0]]["parameters"].update(number="2", v0=1, radius=0.25)
    spawned = _spawn(asset, raw, tmp_path)
    assert spawned.count == 2
    assert spawned.speeds == {1.0}
    assert spawned.radii == {0.25}


@pytest.mark.parametrize("asset", ASSETS)
@pytest.mark.parametrize("key", ["number", "v0", "radius"])
def test_null_distribution_value_takes_the_deck_default(asset, key, tmp_path):
    """A spawn area's own ``null`` is unset, as a deck-wide ``null`` is."""
    raw, keys = _stripped_raw(asset, SPAWN_KEYS)
    for dist in keys:
        raw["distributions"][dist]["parameters"].update(number=0, v0=1.5, radius=0.15)
    raw["distributions"][keys[0]]["parameters"].update({"number": 1, key: None})
    spawned = _spawn(asset, raw, tmp_path, number=2, v0=1.1, radius=0.18)
    expected = {
        "number": (2, {1.5}, {0.15}),
        "v0": (1, {1.1}, {0.15}),
        "radius": (1, {1.5}, {0.18}),
    }[key]
    assert (spawned.count, spawned.speeds, spawned.radii) == expected


@pytest.mark.parametrize("asset", ASSETS)
def test_out_of_range_desired_speed_is_named(asset, tmp_path):
    """The error names ``desired_speed`` when the deck set that alias."""
    raw, keys = _stripped_raw(asset, SPAWN_KEYS)
    raw["distributions"][keys[0]]["parameters"]["desired_speed"] = -1
    with pytest.raises(
        ValueError,
        match=rf"Distribution '{keys[0]}': desired_speed must be finite and >= 0",
    ):
        _spawn(asset, raw, tmp_path, number=1)
