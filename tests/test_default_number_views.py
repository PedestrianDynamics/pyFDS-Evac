"""Inspection views count a distribution without ``number`` as the run does (#647).

The run places ``simulationParams.number``, else 10 agents, for a spawn
area that sets no ``number`` (#567). The scenario summary, layout plot and
distribution listing and the TUI's scenario info used to count 0 (or "?").
"""

from __future__ import annotations

import contextlib
import copy
import io
import json
from pathlib import Path
from types import SimpleNamespace

import jupedsim as jps
import matplotlib
import pytest

from pyfds_evac.core.agent_params import deck_default_number
from pyfds_evac.core.scenario import Scenario, load_scenario
from pyfds_evac.core.simulation_init import initialize_simulation_from_json
from pyfds_evac.tui.model import ScenarioInfo

matplotlib.use("Agg")

# 47 spawn areas, a polygon walkable area (the plot needs one).
ASSET = "assets/station_fahy"


def _without_number(deck_number=None) -> Scenario:
    """station_fahy with every distribution's ``number`` removed, no flow spawning."""
    base = load_scenario(ASSET)
    raw = copy.deepcopy(base.raw)
    for dist in raw["distributions"].values():
        params = dist["parameters"]
        params.pop("number", None)
        params["use_flow_spawning"] = False
    sim_params = raw["config"]["simulation_settings"]["simulationParams"]
    if deck_number is not None:
        sim_params["number"] = deck_number
    return Scenario(
        raw=raw,
        walkable_area_wkt=base.walkable_polygon.wkt,
        model_type=base.model_type,
        seed=1,
        sim_params=sim_params,
        source_path=None,
    )


def _run_count(scenario: Scenario, tmp_path) -> int:
    """Agents the initialiser places for *scenario*."""
    path = tmp_path / "config.json"
    path.write_text(json.dumps(scenario.raw))
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
    return simulation.agent_count()


@pytest.mark.parametrize(("deck_number", "expected"), [(None, 10), (1, 1), ("2", 2)])
def test_views_show_the_count_the_run_places(deck_number, expected, tmp_path):
    scenario = _without_number(deck_number)
    n_dists = len(scenario.distributions)

    listing = scenario.list_distributions()
    assert [d["agents"] for d in listing] == [expected] * n_dists

    summary = scenario.summary()
    assert f"  Agents:        ~{expected * n_dists}\n" in summary
    for dist_id in scenario.distributions:
        assert f"    {dist_id}: {expected} agents" in summary

    ax = scenario.plot()
    labels = [t.get_text() for t in ax.texts if t.get_text().startswith("D")]
    assert labels and all(label.endswith(f"({expected} ag)") for label in labels)
    matplotlib.pyplot.close(ax.figure)

    if deck_number == 1:  # its smaller areas cannot hold 10 agents each
        assert sum(d["agents"] for d in listing) == _run_count(scenario, tmp_path)


def test_a_distribution_number_still_wins():
    scenario = _without_number(3)
    first = next(iter(scenario.distributions))
    scenario.distributions[first]["parameters"]["number"] = 5
    agents = [d["agents"] for d in scenario.list_distributions()]
    assert agents == [5] + [3] * (len(agents) - 1)


def _info(raw) -> ScenarioInfo:
    return ScenarioInfo(path=Path("config.json"), kind="json", name="x", raw=raw)


def test_tui_counts_the_deck_default():
    raw = {"distributions": {"a": {"parameters": {"number": 4}}, "b": {}}}
    assert _info(raw).agents == 14
    raw["config"] = {"simulation_settings": {"simulationParams": {"number": 2}}}
    assert _info(raw).agents == 6


def test_tui_shows_unknown_for_an_invalid_deck_default():
    raw = {
        "config": {"simulation_settings": {"simulationParams": {"number": "many"}}},
        "distributions": {"a": {"parameters": {"number": 4}}, "b": {}},
    }
    assert _info(raw).agents is None
    del raw["distributions"]["b"]
    assert _info(raw).agents == 4


def test_scenario_views_raise_the_runs_error_for_an_invalid_deck_default():
    with pytest.raises(ValueError, match=r"simulationParams\.number must be a number"):
        _without_number("many").list_distributions()


def test_deck_default_number():
    assert deck_default_number(None) == 10
    assert deck_default_number({}) == 10
    assert deck_default_number({"number": None}) == 10
    assert deck_default_number({"number": 0}) == 0
    assert deck_default_number({"number": 3.9}) == 3


@pytest.mark.parametrize("value", [True, -1, "-1"])
def test_deck_default_number_has_the_runs_bounds(value):
    with pytest.raises(ValueError, match=r"simulationParams\.number"):
        deck_default_number({"number": value})
