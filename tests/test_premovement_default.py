"""A distribution that sets no pre-movement gets the FDS+Evac default, 10 s.

FDS+Evac's default pre-movement is a constant ``PRE_MEAN`` = 10 s. A scenario
that says nothing about pre-movement gets the same, with a warning; any
explicit setting, including ``use_premovement: false``, is respected.
"""

import copy
import json
import logging
import math
import sqlite3

import jupedsim as jps
import numpy as np
import pedpy
import pytest

from pyfds_evac.core import load_scenario, run_scenario
from pyfds_evac.core.premovement_distributions import (
    PREMOVEMENT_PRESETS,
    create_premovement_distribution,
)
from pyfds_evac.core.simulation_init import (
    DEFAULT_PREMOVEMENT_S,
    _apply_default_premovement,
    _premovement_params,
    initialize_simulation_from_json,
)


def test_default_is_the_fds_evac_pre_mean():
    assert DEFAULT_PREMOVEMENT_S == 10.0
    assert PREMOVEMENT_PRESETS["constant"]["a"] == 10.0


def test_constant_distribution_gives_every_agent_the_same_time():
    times = create_premovement_distribution("constant", {"a": 30.0}).sample(5)
    assert np.array_equal(times, np.full(5, 30.0))


def test_constant_needs_only_param_a():
    assert _premovement_params("constant", 30.0, None)["a"] == 30.0
    # Other distributions still need both parameters to leave the presets.
    assert _premovement_params("uniform", 30.0, None) == PREMOVEMENT_PRESETS["uniform"]


def test_unset_premovement_gets_the_default_and_warns(caplog):
    with caplog.at_level(logging.WARNING):
        params = _apply_default_premovement({"number": 3}, "d0")
    assert params["use_premovement"] is True
    assert params["premovement_distribution"] == "constant"
    assert params["premovement_param_a"] == DEFAULT_PREMOVEMENT_S
    assert "d0" in caplog.text and "10 s" in caplog.text


@pytest.mark.parametrize(
    "params",
    [
        {"use_premovement": False},
        {"use_premovement": True, "premovement_distribution": "gamma"},
        {"premovement_distribution": "uniform"},
        {"use_flow_spawning": True},
    ],
)
def test_explicit_settings_are_respected(params, caplog):
    with caplog.at_level(logging.WARNING):
        assert _apply_default_premovement(dict(params), "d0") == params
    assert not caplog.text


def _first_agent_x(scenario, frames):
    result = run_scenario(scenario, seed=420)
    try:
        con = sqlite3.connect(result.sqlite_file)
        try:
            rows = con.execute(
                "SELECT frame, pos_x FROM trajectory_data "
                "WHERE id = (SELECT MIN(id) FROM trajectory_data)"
            ).fetchall()
        finally:
            con.close()
    finally:
        result.cleanup()
    x = dict(rows)
    return [x[f] for f in frames]


def _iso_table21(**premovement):
    scenario = load_scenario("assets/ISO-table21")
    for distribution in scenario.raw["distributions"].values():
        params = distribution["parameters"]
        for key in list(params):
            if key == "use_premovement" or key.startswith("premovement_"):
                del params[key]
        params.update(premovement)
    scenario.set_max_time(14.0)
    return scenario


def test_a_run_without_premovement_keys_waits_10_s():
    """At 10 fps the agent holds still until 10 s, then walks."""
    x0, x9, x14 = _first_agent_x(_iso_table21(), (0, 90, 140))
    assert math.fabs(x9 - x0) < 1.0
    assert x14 - x9 > 3.0


def test_use_premovement_false_still_starts_at_once():
    x0, x9, _ = _first_agent_x(_iso_table21(use_premovement=False), (0, 90, 140))
    assert x9 - x0 > 8.0


@pytest.mark.parametrize(
    "asset",
    [
        "assets/ISO-table21",  # no journeys: the fallback initialiser
        "assets/fed_incap_co_2000ppm",  # journeys: the full-config initialiser
    ],
)
def test_both_initialisers_apply_the_default(asset, tmp_path):
    raw = copy.deepcopy(load_scenario(asset).raw)
    for distribution in raw["distributions"].values():
        params = distribution["parameters"]
        for key in list(params):
            if key == "use_premovement" or key.startswith("premovement_"):
                del params[key]
    config = tmp_path / "config.json"
    config.write_text(json.dumps(raw))
    walkable = pedpy.WalkableArea(load_scenario(asset).walkable_area_wkt)
    simulation = jps.Simulation(
        model=jps.CollisionFreeSpeedModel(), geometry=walkable.polygon
    )
    _, positions, _, info = initialize_simulation_from_json(
        str(config), simulation, walkable, seed=1
    )
    times = [v["premovement_time"] for v in info["premovement_times"].values()]
    assert len(times) == len(positions) > 0
    assert set(times) == {DEFAULT_PREMOVEMENT_S}
