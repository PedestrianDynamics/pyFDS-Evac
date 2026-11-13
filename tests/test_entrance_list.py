"""An ``entrance`` list makes the agents know exactly those exits at the start.

The graph is a spawn area S with a direct edge to each of four exits, as the
imported FDS+Evac group of tests/test_fds_import.py sees them: it knows
Bottom and Top (probability 1) and not Left and Right (probability 0).
"""

from __future__ import annotations

import pytest
from shapely.geometry import box

from pyfds_evac.config import rules
from pyfds_evac.core.cognitive_map import (
    distribution_entrances,
    entrance_exits,
    init_cognitive_map,
    stranded_distributions,
)
from pyfds_evac.core.route_graph import StageGraph

EXITS = ("Bottom", "Top", "Left", "Right")


def _graph():
    stages = {
        name: {"polygon": box(10 * i, 0, 10 * i + 1, 1), "stage_type": "exit"}
        for i, name in enumerate(EXITS, start=1)
    }
    transitions = [{"from": "S", "to": name} for name in EXITS]
    return StageGraph.from_scenario(
        stages, transitions, distributions={"S": {"polygon": box(0, 0, 1, 1)}}
    )


def _map(entrance):
    return init_cognitive_map(
        "S", _graph(), "discovery", None, 0.0, entrance=entrance, no_visibility=True
    )


def _known_exits(entrance):
    return {n for n in _map(entrance).known_nodes if n in EXITS}


def test_a_list_teaches_exactly_those_exits():
    assert _known_exits(["Bottom", "Top"]) == {"Bottom", "Top"}


def test_a_string_still_teaches_one_exit():
    assert _known_exits("Left") == {"Left"}


def test_no_entrance_teaches_no_exit():
    assert _known_exits(None) == set()


def test_a_listed_exit_is_reachable_not_just_present():
    cmap = _map(["Top"])
    assert ("S", "Top") in cmap.known_edges
    assert ("S", "Bottom") not in cmap.known_edges


def test_an_unknown_listed_exit_is_ignored():
    assert _known_exits(["Bottom", "Nowhere"]) == {"Bottom"}


@pytest.mark.parametrize("bad", [3, ["Bottom", 3], {"Bottom"}])
def test_a_malformed_entrance_is_refused(bad):
    with pytest.raises(ValueError, match="entrance must be"):
        entrance_exits(bad)


def _raw(entrance):
    params = {"familiarity": "discovery", "no_known_exit": "explore"}
    if entrance is not None:
        params["entrance"] = entrance
    return {"distributions": {"S": {"parameters": params}}}


def test_a_listed_exit_means_the_agents_are_not_stranded():
    graph = _graph()
    assert stranded_distributions(graph, _raw(["Top"])) == []
    assert stranded_distributions(graph, _raw([])) == stranded_distributions(
        graph, _raw(None)
    )


def test_a_malformed_entrance_names_its_distribution():
    raw = {"distributions": {"S": {"parameters": {"entrance": ["Bottom", 3]}}}}
    with pytest.raises(ValueError, match="distribution 'S'.*entrance must be"):
        distribution_entrances(raw)
    issue = rules.scenario_issue(raw)
    assert issue is not None and "entrance must be" in issue.message


def test_well_formed_entrances_are_read_per_distribution():
    raw = {
        "distributions": {
            "a": {"parameters": {"entrance": "Top"}},
            "b": {"parameters": {"entrance": ["Bottom", "Top"]}},
            "c": {"parameters": {}},
        }
    }
    assert distribution_entrances(raw) == {
        "a": ["Top"],
        "b": ["Bottom", "Top"],
        "c": [],
    }
    assert rules.entrance_value_issue(raw) is None
