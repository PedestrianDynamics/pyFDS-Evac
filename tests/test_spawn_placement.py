"""Where agents spawn and which exit or journey they start on.

Covers the placement path of ``simulation_init``:

- the distribution count and percentage parsers;
- the checkpoint-mode normaliser;
- ``_find_nearest_exit`` and ``_random_point_in_polygon``;
- agent placement through ``initialize_simulation_from_json``: the
  nearest-exit journey for agents without a journey, the split of a
  distribution over percentage-routed variants, the clip to the walkable
  area, the capacity check, and the routing validation in
  ``_create_journeys_with_percentages``.

All geometry is synthetic; no FDS output is read.
"""

from __future__ import annotations

import contextlib
import io
import json
import random
from collections import Counter

import jupedsim as jps
import pedpy
import pytest
from shapely.geometry import MultiPolygon, Point, Polygon, box

from pyfds_evac.core.simulation_init import (
    _find_nearest_exit,
    _get_distribution_mode_and_count,
    _get_distribution_percentage,
    _normalize_bool,
    _normalize_checkpoint_mode,
    _random_point_in_polygon,
    initialize_simulation_from_json,
)

SEED = 3
WALKABLE = box(0.0, 0.0, 20.0, 10.0)
WEST_EXIT = box(0.0, 4.0, 0.2, 6.0)
EAST_EXIT = box(19.8, 4.0, 20.0, 6.0)
D0 = "jps-distributions_0"
D1 = "jps-distributions_1"
CP = "jps-checkpoints_0"


def _coords(polygon: Polygon) -> list[list[float]]:
    return [list(c) for c in polygon.exterior.coords]


def _params(number: int, **extra) -> dict:
    return {"number": number, "use_premovement": False, **extra}


def _deck(distributions: dict, **extra) -> dict:
    """A two-exit deck: west exit E1, east exit E2, both unthrottled."""
    return {
        "exits": {
            "E1": {"coordinates": _coords(WEST_EXIT)},
            "E2": {"coordinates": _coords(EAST_EXIT)},
        },
        "distributions": {
            key: {"coordinates": _coords(area), "parameters": params}
            for key, (area, params) in distributions.items()
        },
        **extra,
    }


def _initialize(data: dict, tmp_path, seed: int = SEED):
    path = tmp_path / "deck.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    simulation = jps.Simulation(model=jps.CollisionFreeSpeedModel(), geometry=WALKABLE)
    with contextlib.redirect_stdout(io.StringIO()):
        result, positions, radii, info = initialize_simulation_from_json(
            str(path), simulation, pedpy.WalkableArea(WALKABLE), seed=seed
        )
    return simulation, result, positions, info


# -- count and percentage parsers ---------------------------------------------


@pytest.mark.parametrize(
    ("params", "expected"),
    [
        ({}, ("by_number", 0)),
        ({"number": 7}, ("by_number", 7)),
        ({"number": "12"}, ("by_number", 12)),
        ({"number": -4}, ("by_number", 0)),
        ({"distribution_mode": "by_percentage", "number": 7}, ("by_percentage", 0)),
        ({"distribution_mode": "fill_area"}, ("by_percentage", 0)),
        ({"distribution_mode": "until_full"}, ("by_percentage", 0)),
        ({"distribution_mode": "nonsense", "number": 5}, ("by_number", 5)),
    ],
)
def test_distribution_mode_and_count(params, expected):
    assert _get_distribution_mode_and_count(params) == expected


@pytest.mark.parametrize(
    ("params", "expected"),
    [
        ({"distribution_mode": "by_percentage"}, 50),
        ({"distribution_mode": "fill_area"}, 100),
        ({"distribution_mode": "until_full"}, 100),
        ({"distribution_mode": "by_percentage", "percentage": 30}, 30),
        ({"distribution_mode": "by_percentage", "percentage": "33.7"}, 33),
        ({"distribution_mode": "by_percentage", "percentage": 0}, 1),
        ({"distribution_mode": "by_percentage", "percentage": -20}, 1),
        ({"distribution_mode": "by_percentage", "percentage": 250}, 100),
        ({"distribution_mode": "by_percentage", "percentage": None}, 50),
        ({"distribution_mode": "by_percentage", "percentage": "lots"}, 50),
    ],
)
def test_distribution_percentage_defaults_and_clamps(params, expected):
    assert _get_distribution_percentage(params) == expected


# -- checkpoint mode ----------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (True, True),
        (False, False),
        ("true", True),
        (" Yes ", True),
        ("on", True),
        ("1", True),
        ("false", False),
        ("off", False),
        ("", False),
        ("0", False),
        (0, False),
        (1, True),
        (None, False),
    ],
)
def test_normalize_bool(value, expected):
    assert _normalize_bool(value) is expected


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        # A waiting time wins over throttling and a speed factor.
        ((5.0, True, 0.5), (5.0, False, 1.0)),
        # Throttling wins over a speed factor.
        ((0.0, "true", 0.5), (0.0, True, 1.0)),
        # A speed factor alone is kept, capped at 3.
        ((0.0, False, 0.5), (0.0, False, 0.5)),
        ((0.0, False, 7.0), (0.0, False, 3.0)),
        # Invalid inputs fall back to "no effect".
        ((-2.0, False, 1.0), (0.0, False, 1.0)),
        ((float("nan"), False, 1.0), (0.0, False, 1.0)),
        (("soon", False, "fast"), (0.0, False, 1.0)),
        ((0.0, False, -1.0), (0.0, False, 1.0)),
    ],
)
def test_checkpoint_modes_are_mutually_exclusive(args, expected):
    assert _normalize_checkpoint_mode(*args) == pytest.approx(expected)


# -- nearest exit -------------------------------------------------------------


def test_nearest_exit_by_geometry():
    geometries = {"E1": WEST_EXIT, "E2": EAST_EXIT}
    assert _find_nearest_exit((3.0, 5.0), exit_geometries=geometries) == "E1"
    assert _find_nearest_exit((17.0, 5.0), exit_geometries=geometries) == "E2"


def test_nearest_exit_tie_goes_to_the_first_exit():
    # Both exits are exactly 9.75 m from the point.
    west, east = box(0.0, 4.0, 0.25, 6.0), box(19.75, 4.0, 20.0, 6.0)
    assert Point(10.0, 5.0).distance(west) == Point(10.0, 5.0).distance(east)
    geometries = {"E2": east, "E1": west}
    assert _find_nearest_exit((10.0, 5.0), exit_geometries=geometries) == "E2"
    geometries = {"E1": west, "E2": east}
    assert _find_nearest_exit((10.0, 5.0), exit_geometries=geometries) == "E1"


def test_nearest_exit_from_stage_map_prefers_exit_keys():
    stage_map = {D0: -1, "jps-exits_0": 4, "jps-exits_1": 5}
    exits = [WEST_EXIT, EAST_EXIT]
    assert _find_nearest_exit((3.0, 5.0), stage_map=stage_map, exits=exits) == 4
    assert _find_nearest_exit((17.0, 5.0), stage_map=stage_map, exits=exits) == 5


def test_nearest_exit_from_stage_map_matches_exit_in_name():
    stage_map = {"cp": 1, "west_exit": 2, "east_exit": 3}
    exits = [WEST_EXIT, EAST_EXIT]
    assert _find_nearest_exit((17.0, 5.0), stage_map=stage_map, exits=exits) == 3


def test_nearest_exit_from_stage_map_pairs_by_order():
    exits = [WEST_EXIT, EAST_EXIT]
    # One stage per exit: the stage map is paired with the exits in order.
    stage_map = {"a": 7, "b": 8}
    assert _find_nearest_exit((17.0, 5.0), stage_map=stage_map, exits=exits) == 8
    # More stages than exits: the first len(exits) stages are the exits.
    stage_map = {"a": 7, "b": 8, "c": 9}
    assert _find_nearest_exit((17.0, 5.0), stage_map=stage_map, exits=exits) == 8


def test_nearest_exit_skips_distribution_placeholders():
    # Stage id -1 marks a distribution; it is never an exit.
    stage_map = {"a_exit": -1, "b_exit": 8}
    exits = [WEST_EXIT, EAST_EXIT]
    assert _find_nearest_exit((1.0, 5.0), stage_map=stage_map, exits=exits) == 8


@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"exit_geometries": {}},
        {"stage_map": {"jps-exits_0": 1}, "exits": []},
        {"stage_map": {"jps-exits_0": -1}, "exits": [WEST_EXIT]},
    ],
)
def test_nearest_exit_without_exits_raises(kwargs):
    with pytest.raises(ValueError, match="No exits available"):
        _find_nearest_exit((1.0, 1.0), **kwargs)


# -- random point in a polygon -------------------------------------------------


class _ScriptedRng:
    """An rng whose ``uniform`` draws come from a list, then from a fallback."""

    def __init__(self, scripted, then=None):
        self._scripted = list(scripted)
        self._then = then

    def uniform(self, low, high):
        if self._scripted:
            return self._scripted.pop(0)
        if self._then is not None:
            return self._then(low, high)
        return low


@pytest.mark.parametrize("seed", range(20))
def test_random_point_keeps_the_clearance(seed):
    room = box(0.0, 0.0, 4.0, 2.0)
    x, y = _random_point_in_polygon(room, random.Random(seed), min_clearance=0.3)
    assert room.contains(Point(x, y))
    assert room.exterior.distance(Point(x, y)) >= 0.3 - 1e-9


def test_random_point_is_reproducible():
    room = box(0.0, 0.0, 4.0, 2.0)
    first = _random_point_in_polygon(room, random.Random(11))
    again = _random_point_in_polygon(room, random.Random(11))
    other = _random_point_in_polygon(room, random.Random(12))
    assert first == again
    assert first != other


def test_random_point_without_clearance_uses_the_whole_polygon():
    room = box(0.0, 0.0, 1.0, 1.0)
    rng = _ScriptedRng([0.01, 0.01])
    assert _random_point_in_polygon(room, rng, min_clearance=0.0) == (0.01, 0.01)


def test_random_point_in_a_polygon_thinner_than_the_clearance():
    # The inner buffer is empty, so the polygon itself is sampled.
    sliver = box(0.0, 0.0, 5.0, 0.2)
    for seed in range(10):
        x, y = _random_point_in_polygon(sliver, random.Random(seed), min_clearance=0.5)
        assert sliver.contains(Point(x, y))


def test_random_point_uses_the_largest_part_of_a_split_interior():
    # Two rooms joined by a corridor narrower than twice the clearance: the
    # inner buffer splits in two, and only the larger room is sampled.
    big = box(0.0, 0.0, 6.0, 6.0)
    small = box(8.0, 2.0, 10.0, 4.0)
    corridor = box(6.0, 2.9, 8.0, 3.1)
    rooms = big.union(corridor).union(small)
    assert isinstance(rooms.buffer(-0.5), MultiPolygon)
    for seed in range(20):
        x, y = _random_point_in_polygon(rooms, random.Random(seed), min_clearance=0.5)
        assert big.buffer(-0.5).contains(Point(x, y))


def test_random_point_falls_back_to_the_polygon_when_the_interior_misses():
    room = box(0.0, 0.0, 4.0, 2.0)
    # 1000 draws at the corner of the bounding box of the inner polygon,
    # which lies on its boundary and is never contained; then one point
    # inside the room but within the clearance of the wall.
    misses = [0.3, 0.3] * 1000
    rng = _ScriptedRng(misses + [0.1, 1.0])
    assert _random_point_in_polygon(room, rng, min_clearance=0.3) == (0.1, 1.0)


def test_random_point_last_resort_is_a_point_of_the_interior():
    room = box(0.0, 0.0, 4.0, 2.0)
    rng = _ScriptedRng([], then=lambda low, high: low)  # always the corner
    x, y = _random_point_in_polygon(room, rng, min_clearance=0.3)
    assert room.buffer(-0.3).contains(Point(x, y))


# -- placement through initialize_simulation_from_json ------------------------


def test_agents_without_a_journey_start_on_the_nearest_exit(tmp_path):
    """A deck with journeys: a distribution without one heads for its nearest exit."""
    data = _deck(
        {
            D0: (box(8.0, 2.0, 12.0, 8.0), _params(4)),
            D1: (box(16.0, 2.0, 19.0, 8.0), _params(5)),
        },
        journeys=[{"id": "J", "stages": [D0, "E1"]}],
        transitions=[{"journey_id": "J", "from": D0, "to": "E1"}],
    )
    simulation, result, _, info = _initialize(data, tmp_path)
    east = result["stage_map"]["E2"]
    stages = Counter(
        agent.stage_id
        for agent in simulation.agents()
        if agent.position[0] > 15.0  # spawned in D1
    )
    assert stages == {east: 5}
    east_journey = info["exit_to_journey"][east]
    assert {
        agent.journey_id for agent in simulation.agents() if agent.position[0] > 15.0
    } == {east_journey}
    # Every exit has its own journey and its geometry, keyed by stage id.
    assert set(info["exit_to_journey"]) == set(info["exit_geometries"])
    assert set(info["exit_geometries"]) == {
        result["stage_map"]["E1"],
        result["stage_map"]["E2"],
    }


def test_fallback_deck_targets_the_nearest_exit(tmp_path):
    """Without journeys every agent is steered to the exit nearest its spawn."""
    data = _deck(
        {
            D0: (box(1.0, 2.0, 4.0, 8.0), _params(4)),
            D1: (box(16.0, 2.0, 19.0, 8.0), _params(4)),
        }
    )
    simulation, _, _, info = _initialize(data, tmp_path)
    targets = {}
    for agent in simulation.agents():
        exit_id = info["agent_wait_info"][agent.id]["current_target_stage"]
        targets[agent.id] = exit_id
        nearest = "E1" if agent.position[0] < 10.0 else "E2"
        assert exit_id == nearest
    assert Counter(targets.values()) == {"E1": 4, "E2": 4}


def _split_deck(destinations: list[dict], number: int, key: str = D0) -> dict:
    """One distribution through a checkpoint that splits towards E1 and E2."""
    exits = sorted({d["target"] for d in destinations})
    return _deck(
        {key: (box(8.0, 2.0, 12.0, 8.0), _params(number))},
        checkpoints={CP: {"coordinates": _coords(box(9.5, 8.5, 10.5, 9.5))}},
        journeys=[{"id": "J", "stages": [key, CP, *exits]}],
        transitions=[{"journey_id": "J", "from": key, "to": CP}]
        + [{"journey_id": "J", "from": CP, "to": e} for e in exits],
        waypoint_routing={CP: {"J": {"destinations": destinations}}},
    )


def _exit_choices(info) -> Counter:
    return Counter(
        state["path_choices"][CP][0][0] for state in info["agent_wait_info"].values()
    )


def test_percentage_split_assigns_rounded_shares(tmp_path):
    data = _split_deck(
        [{"target": "E1", "percentage": 30}, {"target": "E2", "percentage": 70}], 10
    )
    simulation, _, _, info = _initialize(data, tmp_path)
    assert simulation.agent_count() == 10
    assert _exit_choices(info) == {"E1": 3, "E2": 7}


def test_percentage_split_last_variant_takes_the_remainder(tmp_path):
    # 7 agents at 50/50: round(3.5) = 4 for E1 (round half to even), and the
    # last variant gets what is left, so the total is exact.
    data = _split_deck(
        [{"target": "E1", "percentage": 50}, {"target": "E2", "percentage": 50}], 7
    )
    simulation, _, _, info = _initialize(data, tmp_path)
    assert simulation.agent_count() == 7
    assert _exit_choices(info) == {"E1": 4, "E2": 3}


def test_percentage_weights_need_not_sum_to_100(tmp_path):
    data = _split_deck(
        [{"target": "E1", "percentage": 1}, {"target": "E2", "percentage": 3}], 8
    )
    _, _, _, info = _initialize(data, tmp_path)
    assert _exit_choices(info) == {"E1": 2, "E2": 6}


@pytest.mark.parametrize("key", [D0, "room"])
def test_journey_finds_its_spawn_area_by_key_not_prefix(tmp_path, key):
    """A spawn area is any key of ``distributions``, whatever its name (#409)."""
    data = _deck(
        {key: (box(2.0, 2.0, 8.0, 8.0), _params(6))},
        journeys=[{"id": "J", "stages": [key, "E2"]}],
        transitions=[{"journey_id": "J", "from": key, "to": "E2"}],
    )
    simulation, _, _, info = _initialize(data, tmp_path)
    assert simulation.agent_count() == 6
    states = info["agent_wait_info"].values()
    assert [(s["current_origin"], s["current_target_stage"]) for s in states] == [
        (key, "E2")
    ] * 6


@pytest.mark.parametrize("key", [D0, "room"])
def test_split_journey_from_a_spawn_area_of_any_name(tmp_path, key):
    """Routing variants and path states start from the spawn area (#409)."""
    data = _split_deck(
        [{"target": "E1", "percentage": 30}, {"target": "E2", "percentage": 70}],
        10,
        key=key,
    )
    simulation, _, _, info = _initialize(data, tmp_path)
    assert simulation.agent_count() == 10
    assert _exit_choices(info) == {"E1": 3, "E2": 7}
    assert {s["current_origin"] for s in info["agent_wait_info"].values()} == {key}


def test_placement_is_reproducible_and_seed_dependent(tmp_path):
    data = _deck(
        {D0: (box(2.0, 2.0, 8.0, 8.0), _params(12))},
        journeys=[{"id": "J", "stages": [D0, "E1"]}],
        transitions=[{"journey_id": "J", "from": D0, "to": "E1"}],
    )
    _, _, first, _ = _initialize(data, tmp_path, seed=5)
    _, _, again, _ = _initialize(data, tmp_path, seed=5)
    _, _, other, _ = _initialize(data, tmp_path, seed=6)
    assert first == again
    assert first != other


def test_spawn_area_is_clipped_to_the_walkable_area(tmp_path):
    # Half of D0 lies outside the walkable area; D1 lies entirely outside.
    data = _deck(
        {
            D0: (box(-5.0, 2.0, 3.0, 8.0), _params(10)),
            D1: (box(30.0, 2.0, 35.0, 8.0), _params(10)),
        },
        journeys=[{"id": "J", "stages": [D0, "E1"]}],
        transitions=[{"journey_id": "J", "from": D0, "to": "E1"}],
    )
    simulation, _, positions, _ = _initialize(data, tmp_path)
    assert simulation.agent_count() == 10
    inside = box(0.0, 2.0, 3.0, 8.0)
    assert all(inside.contains(Point(p)) for p in positions)


def test_too_many_agents_for_the_area_is_refused(tmp_path):
    data = _deck(
        {D0: (box(2.0, 2.0, 3.0, 3.0), _params(500))},
        journeys=[{"id": "J", "stages": [D0, "E1"]}],
        transitions=[{"journey_id": "J", "from": D0, "to": "E1"}],
    )
    with pytest.raises(
        Exception, match=r"requested 500 agents but area can hold at most"
    ):
        _initialize(data, tmp_path)


@pytest.mark.parametrize(
    ("routing", "message"),
    [
        (None, "Explicit routing required"),
        (
            {"destinations": [{"target": "E1", "percentage": 100}]},
            r"incomplete\. Missing targets: \['E2'\]",
        ),
        (
            {
                "destinations": [
                    {"target": "E1", "percentage": 0},
                    {"target": "E2", "percentage": 0},
                ]
            },
            "invalid percentages",
        ),
    ],
)
def test_split_checkpoint_needs_complete_routing(tmp_path, routing, message):
    data = _split_deck(
        [{"target": "E1", "percentage": 50}, {"target": "E2", "percentage": 50}], 4
    )
    if routing is None:
        data["waypoint_routing"] = {}
    else:
        data["waypoint_routing"] = {CP: {"J": routing}}
    with pytest.raises(ValueError, match=message):
        _initialize(data, tmp_path)


@pytest.mark.xfail(
    strict=True,
    reason="#436: by_percentage ignores percentage for agents placed at start",
)
def test_by_percentage_count_follows_the_percentage(tmp_path):
    counts = {}
    for percentage in (10, 90):
        params = {
            "distribution_mode": "by_percentage",
            "percentage": percentage,
            "use_premovement": False,
        }
        data = _deck(
            {D0: (box(2.0, 2.0, 8.0, 8.0), params)},
            journeys=[{"id": "J", "stages": [D0, "E2"]}],
            transitions=[{"journey_id": "J", "from": D0, "to": "E2"}],
        )
        simulation, _, _, _ = _initialize(data, tmp_path)
        counts[percentage] = simulation.agent_count()
    assert counts[90] > counts[10]
