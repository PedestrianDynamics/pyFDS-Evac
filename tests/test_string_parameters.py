"""String-encoded distribution ``parameters`` on the run path (#644).

A scenario may give a distribution's ``parameters`` as an object or as a
JSON-encoded string. The initialisers read both; the discovery check, the
familiarity and entrance lookup of ``run_scenario`` and the
``no_known_exit`` lookup used to crash on the string or treat it as unset.
An unparseable string or ``null`` reads as no parameters, as in the
initialisers.
"""

from __future__ import annotations

import contextlib
import copy
import io
import json

import pytest

from pyfds_evac.config import rules
from pyfds_evac.config.rules import has_discovery_agents
from pyfds_evac.core.cognitive_map import distribution_no_known_exit
from pyfds_evac.core.scenario import load_scenario, run_scenario


def _raw(parameters) -> dict:
    return {"distributions": {"d0": {"parameters": parameters}}}


@pytest.mark.parametrize(
    ("parameters", "expected"),
    [
        (json.dumps({"familiarity": "discovery"}), True),
        (json.dumps({"familiarity": 0.5}), True),
        (json.dumps({"familiarity": "full"}), False),
        (json.dumps({"number": 3}), False),
        ("{not json", False),
        (None, False),
    ],
)
def test_has_discovery_agents_reads_both_forms(parameters, expected):
    assert has_discovery_agents(_raw(parameters)) is expected


def test_no_known_exit_is_read_from_a_string():
    raw = {
        "distributions": {
            "a": {"parameters": {"no_known_exit": "explore"}},
            "b": {"parameters": json.dumps({"no_known_exit": "explore"})},
            "c": {"parameters": "{not json"},
        }
    }
    assert distribution_no_known_exit(raw) == {
        "a": "explore",
        "b": "explore",
        "c": "default_route",
    }


def test_bad_no_known_exit_in_a_string_names_the_distribution():
    with pytest.raises(ValueError, match="distribution 'd0'"):
        distribution_no_known_exit(_raw(json.dumps({"no_known_exit": "bogus"})))


def test_front_ends_refuse_a_string_no_known_exit_before_a_run():
    class Opts:
        smoke_blind = True
        enable_rerouting = True

    issue = rules.no_known_exit_issue(
        Opts(), _raw(json.dumps({"no_known_exit": "stay"}))
    )
    assert issue is not None and issue.rule == "D33"


def _run(scenario) -> tuple[dict, object]:
    with contextlib.redirect_stdout(io.StringIO()):
        result = run_scenario(scenario, seed=1)
    try:
        metrics = {k: v for k, v in result.metrics.items() if k != "walkable_polygon"}
        # JuPedSim numbers agents per process, so a second run has other ids.
        return metrics, result.trajectory_dataframe().drop(columns="id")
    finally:
        result.cleanup()


def test_string_parameters_run_as_the_object_form():
    """t_junction (discovery agents, flow spawning) with an entrance, 8 s."""
    as_object = load_scenario("assets/t_junction")
    as_object.sim_params["max_simulation_time"] = 8.0
    params = as_object.raw["distributions"]["jps-distributions_0"]["parameters"]
    params["entrance"] = "exit_A_left"
    as_string = copy.deepcopy(as_object)
    as_string.raw["distributions"]["jps-distributions_0"]["parameters"] = json.dumps(
        params
    )

    metrics, trajectories = _run(as_object)
    string_metrics, string_trajectories = _run(as_string)
    assert metrics["total_agents"] > 0
    assert string_metrics == metrics
    assert string_trajectories.equals(trajectories)


def _stringified(asset: str):
    """*asset* loaded, and a copy with every ``parameters`` JSON-encoded."""
    as_object = load_scenario(asset)
    as_string = copy.deepcopy(as_object)
    for dist in as_string.raw["distributions"].values():
        dist["parameters"] = json.dumps(dist["parameters"])
    return as_object, as_string


def test_views_read_string_parameters():
    """summary(), list_distributions() and plot() as for the object form."""
    import matplotlib

    matplotlib.use("Agg")
    as_object, as_string = _stringified("assets/station_fahy")
    assert as_string.list_distributions() == as_object.list_distributions()
    assert as_string.summary() == as_object.summary()
    labels = []
    for scenario in (as_object, as_string):
        ax = scenario.plot()
        labels.append([t.get_text() for t in ax.texts])
        matplotlib.pyplot.close(ax.figure)
    assert labels[0] == labels[1]


@pytest.mark.parametrize(
    ("setter", "kwargs"),
    [
        ("set_agent_params", {"radius": 0.25, "v0": 1.1}),
        ("set_agent_count", {"count": 4}),
        (
            "set_flow_schedule",
            {
                "schedule": [{"flow_start_time": 0, "flow_end_time": 4, "number": 2}],
                "keep_initial_agents": True,
            },
        ),
    ],
)
def test_setters_update_string_parameters(setter, kwargs):
    """A setter parses the string and stores the updated object."""
    as_object, as_string = _stringified("assets/t_junction")
    for scenario in (as_object, as_string):
        getattr(scenario, setter)(0, **kwargs)
    key = "jps-distributions_0"
    assert (
        as_string.distributions[key]["parameters"]
        == (as_object.distributions[key]["parameters"])
    )


@pytest.mark.parametrize("parameters", [None, "{not json"])
def test_setters_start_from_empty_for_null_or_garbage(parameters):
    scenario = load_scenario("assets/t_junction")
    scenario.distributions["jps-distributions_0"]["parameters"] = parameters
    scenario.set_agent_params(0, radius=0.25)
    assert scenario.distributions["jps-distributions_0"]["parameters"] == {
        "radius": 0.25
    }


def test_tui_agent_count_reads_string_parameters():
    from pathlib import Path

    from pyfds_evac.tui.model import ScenarioInfo

    raw = {
        "distributions": {
            "a": {"parameters": json.dumps({"number": 4})},
            "b": {"parameters": {"number": 3}},
        }
    }
    info = ScenarioInfo(path=Path("config.json"), kind="json", name="x", raw=raw)
    assert info.agents == 7


# Haspel has journeys (complete initialiser); station_fahy has none (fallback).
INIT_ASSETS = ["assets/Haspel", "assets/station_fahy"]
_MISSING = object()


def _initialised_count(asset: str, container, tmp_path) -> int:
    """Agents placed when the first area's ``parameters`` is *container*.

    Every other area places none; the deck-wide count is 1, so an area
    whose parameters read as empty places 1 agent.
    """
    from types import SimpleNamespace

    import jupedsim as jps

    from pyfds_evac.core.simulation_init import initialize_simulation_from_json

    scenario = load_scenario(asset)
    raw = copy.deepcopy(scenario.raw)
    keys = list(raw["distributions"])
    for key in keys:
        raw["distributions"][key]["parameters"] = {
            "number": 0,
            "use_premovement": False,
        }
    first = raw["distributions"][keys[0]]
    if container is _MISSING:
        del first["parameters"]
    else:
        first["parameters"] = container
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
            global_parameters=SimpleNamespace(**{**scenario.sim_params, "number": 1}),
        )
    return simulation.agent_count()


@pytest.mark.parametrize("asset", INIT_ASSETS)
@pytest.mark.parametrize(
    "container",
    [_MISSING, None, "null", "[]", "42", "{not json", [], 42],
    ids=[
        "missing",
        "null",
        "str-null",
        "str-list",
        "str-int",
        "garbage",
        "list",
        "int",
    ],
)
def test_initialisers_read_a_non_object_container_as_empty(asset, container, tmp_path):
    """Both initialisers read it as no parameters, as the views do."""
    assert _initialised_count(asset, container, tmp_path) == 1


@pytest.mark.parametrize("asset", INIT_ASSETS)
def test_initialisers_read_an_encoded_object(asset, tmp_path):
    container = json.dumps({"number": 2, "use_premovement": False})
    assert _initialised_count(asset, container, tmp_path) == 2
