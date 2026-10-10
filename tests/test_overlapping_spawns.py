"""Overlapping spawn areas keep their agents apart (#402).

A 5-agent box inside a 40-agent room (PR #396): seeded one after the
other, an agent of the box could land within a body width of one of the
room's, and ``Simulation.add_agent`` refused it. An area that overlaps one
seeded before it is now seeded around the agents already there; the area
seeded first is placed as before.
"""

from __future__ import annotations

import contextlib
import dataclasses
import io
import itertools
import math

import pytest
from shapely.geometry import Point, box
from test_run_outcome import D, _coords, _scenario

from pyfds_evac.core.scenario import run_scenario
from pyfds_evac.core.simulation_init import (
    SpawnCapacityError,
    _distribute_beside,
    _seed_shared_areas,
)

D1 = "jps-distributions_1"
ROOM = box(0.3, 0.3, 29.7, 9.7)
INNER = box(20, 1, 25, 4)
RADIUS = 0.2
# Seeds under which the inner box clashed with the room before #402.
CLASHING_SEEDS = [1, 5, 7]


def _spawns():
    return [
        {
            "area": ROOM,
            "params": {"number": 40, "radius": RADIUS},
            "index": 0,
            "dist_key": D,
        },
        {
            "area": INNER,
            "params": {"number": 5, "radius": RADIUS},
            "index": 1,
            "dist_key": D1,
        },
    ]


@pytest.mark.parametrize("seed", CLASHING_SEEDS)
def test_overlapping_areas_keep_the_agent_spacing(seed):
    placed = _seed_shared_areas(_spawns(), seed)
    assert [len(placed[0]), len(placed[1])] == [40, 5]
    assert all(INNER.contains(Point(x, y)) for x, y in placed[1])
    closest = min(math.dist(a, b) for a, b in itertools.product(placed[0], placed[1]))
    assert closest >= 2 * RADIUS


@pytest.mark.parametrize("seed", CLASHING_SEEDS)
def test_the_area_seeded_first_is_placed_as_before(seed):
    alone = _seed_shared_areas(_spawns()[:1], seed)
    assert _seed_shared_areas(_spawns(), seed)[0] == alone[0]


def test_a_split_free_area_is_a_capacity_error():
    """A placed agent whose hole cuts a 0.5 m strip in two."""
    strip = box(0, 0, 4, 0.5)
    placed = [(box(0, 0, 4, 4), [(2.0, 0.25)], 0.3, [D])]
    with pytest.raises(
        SpawnCapacityError,
        match=rf"^Distribution '{D1}': could not place the 2 requested agents "
        rf"\(agents of '{D}' split the free area\)\.",
    ):
        _distribute_beside(strip, [D1], 2, 4, RADIUS, 1, placed)


def test_no_free_area_is_a_capacity_error():
    """A placed agent in the middle of a 0.5 m square leaves no seat."""
    square = box(0, 0, 0.5, 0.5)
    placed = [(box(0, 0, 4, 4), [(0.25, 0.25)], RADIUS, [D])]
    with pytest.raises(
        SpawnCapacityError,
        match=rf"\(agents of '{D}' leave no free area\)\.",
    ):
        _distribute_beside(square, [D1], 1, 1, RADIUS, 1, placed)


def test_a_pocket_no_agent_fits_in_is_dropped():
    """Three placed agents 0.4 m apart enclose a pocket between their holes."""
    room = box(0, 0, 3, 3)
    triangle = [(1.5, 1.5), (1.9, 1.5), (1.7, 1.5 + 0.2 * math.sqrt(3))]
    placed = [(room, triangle, RADIUS, [D])]
    positions = _distribute_beside(room, [D1], 10, 20, RADIUS, 1, placed)
    assert len(positions) == 10
    closest = min(math.dist(a, b) for a, b in itertools.product(triangle, positions))
    assert closest >= 2 * RADIUS


def _overlapping_scenario(with_journeys: bool):
    scenario = _scenario(1.0, number=40, radius=RADIUS)
    scenario = dataclasses.replace(scenario, walkable_area_wkt=box(0, 0, 30, 10).wkt)
    raw = scenario.raw
    raw["exits"]["E"]["coordinates"] = _coords(box(29.8, 4, 30, 6))
    room = raw["distributions"][D]
    room["coordinates"] = _coords(ROOM)
    raw["distributions"][D1] = {
        "type": "polygon",
        "coordinates": _coords(INNER),
        "parameters": dict(room["parameters"], number=5),
    }
    if with_journeys:
        raw["journeys"] = [
            {"id": "J", "stages": [D, "E"]},
            {"id": "J1", "stages": [D1, "E"]},
        ]
        raw["transitions"] = [
            {"from": D, "to": "E", "journey_id": "J"},
            {"from": D1, "to": "E", "journey_id": "J1"},
        ]
    else:
        raw["journeys"] = []
        raw["transitions"] = []
    return scenario


@pytest.mark.parametrize("with_journeys", [True, False], ids=["journeys", "seeded"])
def test_overlapping_distributions_run(with_journeys):
    """Seed 7 is the clash of the issue, with and without journeys."""
    with contextlib.redirect_stdout(io.StringIO()):
        result = run_scenario(_overlapping_scenario(with_journeys), seed=7)
    assert result.total_agents == 45
