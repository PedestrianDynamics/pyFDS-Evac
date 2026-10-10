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
import json
import math

import jupedsim as jps
import pedpy
import pytest
from shapely.geometry import Point, box
from test_run_outcome import D, _coords, _scenario

import pyfds_evac.core.simulation_init as simulation_init_mod
from pyfds_evac.core.scenario import run_scenario
from pyfds_evac.core.simulation_init import (
    SpawnCapacityError,
    _distribute_beside,
    _free_area,
    _seed_shared_areas,
    initialize_simulation_from_json,
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


def _spawn(area, number, radius, index, key):
    params = {"number": number, "radius": radius}
    return {"area": area, "params": params, "index": index, "dist_key": key}


def _closest(first, second):
    return min(math.dist(a, b) for a, b in itertools.product(first, second))


@pytest.mark.parametrize("radii", [(0.3, 0.15), (0.15, 0.3)], ids=["big", "small"])
@pytest.mark.parametrize("seed", CLASHING_SEEDS)
def test_unequal_radii_keep_twice_the_larger_radius(seed, radii):
    room_r, inner_r = radii
    spawns = [_spawn(ROOM, 40, room_r, 0, D), _spawn(INNER, 5, inner_r, 1, D1)]
    placed = _seed_shared_areas(spawns, seed)
    assert [len(placed[0]), len(placed[1])] == [40, 5]
    assert _closest(placed[0], placed[1]) >= 2 * max(radii)


@pytest.mark.parametrize("seed", CLASHING_SEEDS)
def test_a_small_area_seeded_before_the_room_around_it(seed):
    spawns = [_spawn(INNER, 5, RADIUS, 0, D), _spawn(ROOM, 40, RADIUS, 1, D1)]
    placed = _seed_shared_areas(spawns, seed)
    assert placed[0] == _seed_shared_areas(spawns[:1], seed)[0]
    assert [len(placed[0]), len(placed[1])] == [5, 40]
    assert _closest(placed[0], placed[1]) >= 2 * RADIUS


@pytest.mark.parametrize("seed", CLASHING_SEEDS)
def test_three_overlapping_areas_keep_the_spacing(seed):
    third = box(22, 2, 27, 6)
    spawns = [
        _spawn(ROOM, 40, RADIUS, 0, D),
        _spawn(INNER, 5, RADIUS, 1, D1),
        _spawn(third, 8, RADIUS, 2, "jps-distributions_2"),
    ]
    placed = _seed_shared_areas(spawns, seed)
    assert [len(placed[i]) for i in range(3)] == [40, 5, 8]
    for a, b in itertools.combinations(range(3), 2):
        assert _closest(placed[a], placed[b]) >= 2 * RADIUS


def test_without_journeys_a_b_a_seeds_both_a_before_b():
    """Distributions over one polygon are seeded together, at the first's turn."""
    a2 = "jps-distributions_2"
    spawns = [
        _spawn(INNER, 5, RADIUS, 0, D),
        _spawn(ROOM, 40, RADIUS, 1, D1),
        _spawn(INNER, 4, RADIUS, 2, a2),
    ]
    placed = _seed_shared_areas(spawns, 7)
    both_a = _seed_shared_areas([spawns[0], spawns[2]], 7)
    assert (placed[0], placed[2]) == (both_a[0], both_a[2])
    assert _closest(placed[0] + placed[2], placed[1]) >= 2 * RADIUS


def test_a_split_free_area_is_seeded_in_both_parts():
    """A placed agent whose hole cuts a 0.5 m strip in two; each half seats one."""
    strip = box(0, 0, 4, 0.5)
    hole_agent = (2.0, 0.25)
    placed = [(box(0, 0, 4, 4), [hole_agent], 0.3, [D])]
    positions = _distribute_beside(strip, [D1], 2, 4, RADIUS, 1, placed)
    assert len(positions) == 2
    assert sorted(x < 2 for x, _ in positions) == [False, True]
    assert _closest([hole_agent], positions) >= 2 * 0.3


def test_a_split_area_too_small_for_the_count_is_a_capacity_error():
    strip = box(0, 0, 4, 0.5)
    placed = [(box(0, 0, 4, 4), [(2.0, 0.25)], 0.3, [D])]
    with pytest.raises(
        SpawnCapacityError,
        match=rf"^Distribution '{D1}': could not place the 12 requested agents "
        r"\(only \d+ fit in the 2 parts left free\)\.",
    ):
        _distribute_beside(strip, [D1], 12, 12, RADIUS, 1, placed)


def test_a_full_part_is_not_asked_again(monkeypatch):
    """Each failed sampler call stalls 10 000 draws, so their number is bounded.

    The two halves of the strip seat 6 agents; asking for 100 tried the
    full halves again with ever larger counts (23 failed calls).
    """
    failed = []
    real = jps.distribute_by_number

    def counting(**kwargs):
        try:
            return real(**kwargs)
        except jps.AgentNumberError:
            failed.append(kwargs["number_of_agents"])
            raise

    monkeypatch.setattr(simulation_init_mod.jps, "distribute_by_number", counting)
    placed = [(box(0, 0, 4, 4), [(2.0, 0.25)], 0.3, [D])]
    with pytest.raises(SpawnCapacityError, match=r"only 6 fit in the 2 parts"):
        _distribute_beside(box(0, 0, 4, 0.5), [D1], 100, 99, RADIUS, 1, placed)
    assert len(failed) <= 4


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
    assert _closest(triangle, positions) >= 2 * RADIUS


def _overlapping_scenario(with_journeys: bool, spawns=None):
    """The room with *spawns* ``(key, polygon, number)``: by default the issue's."""
    spawns = spawns or [(D, ROOM, 40), (D1, INNER, 5)]
    scenario = _scenario(1.0, number=40, radius=RADIUS)
    scenario = dataclasses.replace(scenario, walkable_area_wkt=box(0, 0, 30, 10).wkt)
    raw = scenario.raw
    raw["exits"]["E"]["coordinates"] = _coords(box(29.8, 4, 30, 6))
    params = raw["distributions"][D]["parameters"]
    raw["distributions"] = {
        key: {
            "type": "polygon",
            "coordinates": _coords(polygon),
            "parameters": dict(params, number=number),
        }
        for key, polygon, number in spawns
    }
    raw["journeys"] = []
    raw["transitions"] = []
    if with_journeys:
        for key, *_ in spawns:
            raw["journeys"].append({"id": f"J{key}", "stages": [key, "E"]})
            raw["transitions"].append({"from": key, "to": "E", "journey_id": f"J{key}"})
    return scenario


@pytest.mark.parametrize("with_journeys", [True, False], ids=["journeys", "seeded"])
def test_overlapping_distributions_run(with_journeys):
    """Seed 7 is the clash of the issue, with and without journeys."""
    with contextlib.redirect_stdout(io.StringIO()):
        result = run_scenario(_overlapping_scenario(with_journeys), seed=7)
    assert result.total_agents == 45


@pytest.mark.parametrize("with_journeys", [True, False], ids=["journeys", "seeded"])
@pytest.mark.parametrize("seed", CLASHING_SEEDS)
def test_a_b_a_places_everybody_apart(tmp_path, with_journeys, seed):
    """A, B, A over the inner box and the room, with and without journeys.

    With journeys the second A is seeded last, around the first A and B.
    """
    spawns = [(D, INNER, 5), (D1, ROOM, 40), ("jps-distributions_2", INNER, 4)]
    scenario = _overlapping_scenario(with_journeys, spawns)
    config = tmp_path / "config.json"
    config.write_text(json.dumps(scenario.raw))
    walkable = pedpy.WalkableArea(scenario.walkable_area_wkt)
    simulation = jps.Simulation(
        model=jps.CollisionFreeSpeedModel(), geometry=walkable.polygon
    )
    with contextlib.redirect_stdout(io.StringIO()):
        initialize_simulation_from_json(str(config), simulation, walkable, seed=seed)
    positions = [agent.position for agent in simulation.agents()]
    assert len(positions) == 49
    closest = min(math.dist(a, b) for a, b in itertools.combinations(positions, 2))
    assert closest >= 2 * RADIUS


@pytest.mark.parametrize("placed_radius", [0.15, RADIUS, 0.3])
def test_a_hole_keeps_the_full_circle_free(placed_radius):
    """The buffered hole is a polygon; its edges must not cut into the circle."""
    agent = (2.0, 2.0)
    room = box(0, 0, 4, 4)
    free = _free_area(room, RADIUS, [(room, [agent], placed_radius, [D])])
    hole = 2 * max(RADIUS, placed_radius) - RADIUS
    assert free.distance(Point(agent)) >= hole - 1e-9


@pytest.mark.parametrize("seed", [44, 65, 69, 96])
def test_a_dense_room_leaves_the_inner_box_its_spacing(seed):
    """100 agents in a 5.7 m square, then 2 in a 2 m box inside it.

    Under these seeds a hole inscribed in its circle, not circumscribed,
    lets an agent of the box land 0.39952-0.39998 m from one of the room's.
    """
    spawns = [
        _spawn(box(0.3, 0.3, 6, 6), 100, RADIUS, 0, D),
        _spawn(box(2, 2, 4, 4), 2, RADIUS, 1, D1),
    ]
    placed = _seed_shared_areas(spawns, seed)
    assert _closest(placed[0], placed[1]) >= 2 * RADIUS
