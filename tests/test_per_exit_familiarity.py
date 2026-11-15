"""Familiarity as a probability per exit (#136).

``familiarity: {exit_id: p}`` is the per-exit form of the scalar probability and
of FDS+Evac's ``KNOWN_DOOR_PROBS``: a listed exit is known at t=0 with
probability p, an unlisted one with probability 0. The map stays a discovery
map, so learning continues. Each exit not already known takes at most one draw,
in exit order, from the stream the scalar form uses; that makes a uniform
mapping equal the scalar, seed for seed.
"""

from __future__ import annotations

import random

import pytest

from pyfds_evac.config.rules import entrance_value_issue, has_discovery_agents
from pyfds_evac.core.cognitive_map import (
    _must_discover_an_exit,
    distribution_entrances,
    distribution_familiarities,
    expand_on_arrival,
    init_cognitive_map,
    unreachable_known_exits,
)
from pyfds_evac.core.route_graph import StageGraph
from tests.test_scalar_familiarity import _b, _graph, _known_exits


class _Draws:
    """An rng that returns fixed draws and counts the calls."""

    def __init__(self, *values: float) -> None:
        self.values = list(values)
        self.calls = 0

    def random(self) -> float:
        self.calls += 1
        return self.values.pop(0)


def _init(familiarity, rng=None, **kwargs):
    return init_cognitive_map(
        "spawn", _graph(), familiarity, None, 0.0, rng=rng, no_visibility=True, **kwargs
    )


def test_a_certain_exit_is_known_with_its_route():
    cmap = _init({"e_near": 1.0})
    assert _known_exits(cmap) == {"e_near"}
    assert {"spawn", "cp", "e_near"} <= cmap.known_nodes
    assert cmap.familiarity == "discovery"


def test_an_unlisted_exit_is_never_known():
    for seed in range(1000):
        cmap = _init({"e_near": 1.0}, rng=random.Random(seed))
        assert "e_far" not in cmap.known_nodes


@pytest.mark.parametrize("value", [{}, {"e_near": 0.0, "e_far": 0.0}])
def test_an_empty_or_all_zero_mapping_is_discovery(value):
    for seed in range(20):
        assert (
            _init(value, rng=random.Random(seed)).known_nodes
            == _init("discovery", rng=random.Random(seed)).known_nodes
        )


@pytest.mark.parametrize("seed", range(100))
def test_a_uniform_mapping_equals_the_scalar(seed):
    mapped = _init({"e_near": 0.3, "e_far": 0.3}, rng=random.Random(seed))
    scalar = _init(0.3, rng=random.Random(seed))
    assert mapped.known_nodes == scalar.known_nodes
    assert mapped.known_edges == scalar.known_edges
    assert mapped.exit_events == scalar.exit_events


def test_the_known_share_follows_the_probability():
    n = 10_000
    known = sum(
        "e_far" in _init({"e_far": 0.3}, rng=random.Random(s)).known_nodes
        for s in range(n)
    )
    assert known / n == pytest.approx(0.3, abs=0.014)


def test_draws_follow_exit_order():
    cmap = _init({"e_near": 0.5, "e_far": 0.5}, rng=_Draws(0.6, 0.1))
    assert _known_exits(cmap) == {"e_far"}


def test_a_certain_exit_takes_no_draw():
    rng = _Draws(0.4)
    cmap = _init({"e_near": 1.0, "e_far": 0.5}, rng=rng)
    assert _known_exits(cmap) == {"e_near", "e_far"}
    assert rng.calls == 1


def test_a_zero_probability_takes_no_draw():
    rng = _Draws()
    _init({"e_near": 0.0, "e_far": 0.0}, rng=rng)
    assert rng.calls == 0


def test_the_entrance_is_known_whatever_its_probability():
    cmap = _init({"e_near": 0.0}, entrance="e_near", rng=_Draws())
    assert _known_exits(cmap) == {"e_near"}
    assert cmap.exit_events == [(0.0, "e_near", "entrance")]


def test_an_all_ones_mapping_still_learns_on_arrival():
    """Not the ``full`` tier: only the routes to the exits are known at t=0."""
    stages = {
        "cp": {"polygon": _b(10, 0), "stage_type": "checkpoint"},
        "side": {"polygon": _b(10, -10), "stage_type": "checkpoint"},
        "e_near": {"polygon": _b(20, 0), "stage_type": "exit"},
        "e_far": {"polygon": _b(10, 20), "stage_type": "exit"},
    }
    graph = StageGraph.from_scenario(
        stages, [], distributions={"spawn": {"polygon": _b(0, 0)}}
    )
    cmap = init_cognitive_map(
        "spawn", graph, {"e_near": 1.0, "e_far": 1.0}, None, 0.0, no_visibility=True
    )
    assert cmap.familiarity == "discovery"
    assert "side" not in cmap.known_nodes
    expand_on_arrival(cmap, "cp", graph, from_node="spawn")
    assert "side" in cmap.known_nodes


def test_without_an_rng_only_certain_exits_are_known():
    cmap = _init({"e_near": 1.0, "e_far": 0.9})
    assert _known_exits(cmap) == {"e_near"}


def _raw(familiarity=None, entrance=None, exits=("e_near", "e_far")):
    params = {}
    if familiarity is not None:
        params["familiarity"] = familiarity
    if entrance is not None:
        params["entrance"] = entrance
    return {
        "exits": {e: {} for e in exits},
        "distributions": {"d1": {"parameters": params}},
    }


@pytest.mark.parametrize(
    "value",
    [{"nowhere": 0.5}, {"e_near": 1.2}, {"e_near": -0.1}]
    + [{"e_near": "x"}, {"e_near": True}, {"e_near": None}],
)
def test_a_bad_mapping_is_a_load_error_naming_the_distribution(value):
    with pytest.raises(ValueError, match="distribution 'd1'"):
        distribution_familiarities(_raw(value))
    issue = entrance_value_issue(_raw(value))
    assert issue is not None and "d1" in issue.message


def test_an_unknown_entrance_is_a_load_error():
    with pytest.raises(ValueError, match="distribution 'd1'.*'nowhere'"):
        distribution_entrances(_raw(entrance="nowhere"))
    assert distribution_entrances(_raw(entrance=["e_far"])) == {"d1": ["e_far"]}


def test_a_mapping_counts_as_discovery():
    assert has_discovery_agents(_raw({"e_near": 1.0, "e_far": 1.0}))
    assert has_discovery_agents(_raw({}))
    assert not has_discovery_agents(_raw("full"))


def test_a_mapping_that_knows_no_exit_must_discover_one():
    mode = "explore"
    assert _must_discover_an_exit({"familiarity": {}}, mode)
    assert _must_discover_an_exit({"familiarity": {"e_near": 0.0}}, mode)
    assert not _must_discover_an_exit({"familiarity": {"e_near": 0.1}}, mode)
    assert not _must_discover_an_exit({"familiarity": {}, "entrance": "e_near"}, mode)


def test_an_unreachable_known_exit_is_reported():
    graph = _graph()
    raw = _raw({"e_far": 0.5}, entrance="e_near")
    raw["distributions"] = {"spawn": raw["distributions"].pop("d1")}
    assert unreachable_known_exits(graph, raw) == []
    graph.edges["spawn"].clear()  # no route leaves the spawn area
    assert unreachable_known_exits(graph, raw) == [
        ("spawn", "entrance", "e_near"),
        ("spawn", "familiarity", "e_far"),
    ]
