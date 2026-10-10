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

from pyfds_evac.core.scenario import Scenario
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


def _journey_deck(distributions: dict) -> dict:
    """*distributions* on a deck whose one journey leads the first to E2."""
    first = next(iter(distributions))
    return _deck(
        distributions,
        journeys=[{"id": "J", "stages": [first, "E2"]}],
        transitions=[{"journey_id": "J", "from": first, "to": "E2"}],
    )


def test_scheduled_spawn_area_places_its_initial_agents(tmp_path):
    """Initial agents beside a flow schedule start on the journey (#118).

    The area is nearer E1, so an agent left without its journey heads there.
    """
    window = {"flow_start_time": 0, "flow_end_time": 10, "number": 4}
    params = _params(0, initial_number=3, flow_schedule=[window])
    data = _journey_deck({D0: (box(2.0, 2.0, 8.0, 8.0), params)})
    simulation, _, _, info = _initialize(data, tmp_path)
    assert simulation.agent_count() == 3
    targets = [s["current_target_stage"] for s in info["agent_wait_info"].values()]
    assert targets == ["E2"] * 3
    assert info["num_agents_per_source"] == [4]


_SCHEDULE = [
    {"start_time_s": 20, "end_time_s": 30, "sim_count": 5},
    {"flow_start_time": 0, "flow_end_time": 10, "number": 4},
]


@pytest.mark.parametrize("with_journeys", [True, False], ids=["journeys", "seeded"])
def test_flow_schedule_and_initial_number_reach_the_set_up(tmp_path, with_journeys):
    """The scenario JSON's schedule and initial count are what is placed (#390).

    ``number`` (9) is what ``set_flow_schedule`` stores, the scheduled sum;
    it is not placed on its own.
    """
    params = _params(
        9, use_flow_spawning=True, initial_number=3, flow_schedule=_SCHEDULE
    )
    area = {D0: (box(2.0, 2.0, 8.0, 8.0), params)}
    data = _journey_deck(area) if with_journeys else _deck(area)
    simulation, _, _, info = _initialize(data, tmp_path)
    assert simulation.agent_count() == 3
    assert info["num_agents_per_source"] == [4, 5]
    windows = [(f["start_time"], f["end_time"]) for f in info["flow_distributions"]]
    assert windows == [(0.0, 10.0), (20.0, 30.0)]


@pytest.mark.parametrize("with_journeys", [True, False], ids=["journeys", "seeded"])
def test_initial_number_without_a_schedule_is_not_read(tmp_path, with_journeys):
    """A stray ``initial_number`` changes nothing without ``flow_schedule`` (#390).

    D0, with ``number`` 0, lies inside D1, whose 120 agents leave no room;
    it places nobody, as without ``initial_number``, instead of failing to
    place 0 agents.
    """
    placed = []
    for extra in ({}, {"initial_number": 3}):
        area = {
            D1: (box(2.0, 2.0, 8.0, 8.0), _params(120)),
            D0: (box(4.0, 4.0, 5.0, 5.0), _params(0, **extra)),
        }
        data = _journey_deck(area) if with_journeys else _deck(area)
        simulation, _, positions, _ = _initialize(data, tmp_path)
        assert simulation.agent_count() == 120
        placed.append(positions)
    assert placed[0] == placed[1]


@pytest.mark.parametrize("with_journeys", [True, False], ids=["journeys", "seeded"])
@pytest.mark.parametrize(
    ("extra", "message"),
    [
        (
            {
                "flow_schedule": [
                    {"flow_start_time": -1, "flow_end_time": 5, "number": 2}
                ]
            },
            r"Distribution 'jps-distributions_0': flow_schedule: Invalid flow window",
        ),
        (
            {
                "flow_schedule": [
                    {"flow_start_time": 0, "flow_end_time": 5, "number": 0}
                ]
            },
            r"Distribution 'jps-distributions_0': flow_schedule: .*positive integers",
        ),
        (
            {"flow_schedule": _SCHEDULE, "initial_number": "three"},
            r"Distribution 'jps-distributions_0': initial_number must be a number",
        ),
        (
            {"flow_schedule": [{"start_time_s": "nan", "end_time_s": 5, "number": 2}]},
            r"Distribution 'jps-distributions_0': flow_schedule: .*must be finite",
        ),
        (
            {"flow_schedule": [{"start_time_s": 0, "end_time_s": "inf", "number": 2}]},
            r"Distribution 'jps-distributions_0': flow_schedule: .*must be finite",
        ),
        (
            {"flow_schedule": [{"start_time_s": [0], "end_time_s": 5, "number": 2}]},
            r"Distribution 'jps-distributions_0': flow_schedule: .*must be numbers",
        ),
        (
            {"flow_schedule": [[0, 5, 2]]},
            r"Distribution 'jps-distributions_0': flow_schedule: .*must be an object",
        ),
        (
            {"flow_schedule": 5},
            r"Distribution 'jps-distributions_0': flow_schedule: .*must be a list",
        ),
    ],
    ids=[
        "negative-start",
        "empty-window",
        "initial-not-a-number",
        "nan-start",
        "inf-end",
        "list-time",
        "entry-not-an-object",
        "schedule-not-a-list",
    ],
)
def test_invalid_flow_schedule_stops_the_set_up(
    tmp_path, with_journeys, extra, message
):
    """The run reads a schedule as ``Scenario.set_flow_schedule`` does (#390)."""
    area = {D0: (box(2.0, 2.0, 8.0, 8.0), _params(0, **extra))}
    data = _journey_deck(area) if with_journeys else _deck(area)
    with pytest.raises(ValueError, match=message):
        _initialize(data, tmp_path)


def test_invalid_spawn_polygon_is_skipped_with_a_warning(tmp_path):
    """A self-intersecting spawn area is warned about and skipped (#118, #508)."""
    bow = Polygon([(1.1, 1.1), (3.9, 4.9), (3.9, 1.1), (1.1, 4.9)])
    data = _journey_deck(
        {D0: (box(12.0, 2.0, 16.0, 8.0), _params(4)), D1: (bow, _params(3))}
    )
    path = tmp_path / "deck.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    simulation = jps.Simulation(model=jps.CollisionFreeSpeedModel(), geometry=WALKABLE)
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        initialize_simulation_from_json(
            str(path), simulation, pedpy.WalkableArea(WALKABLE), seed=SEED
        )
    assert f"Warning: Error processing distribution {D1}: TopologyException" in (
        out.getvalue()
    )
    assert simulation.agent_count() == 4


def test_flow_rate_above_the_area_capacity_stops_a_deck_with_journeys(tmp_path):
    """Raised as without journeys; it was a warning and no agents (#118)."""
    params = _params(500, use_flow_spawning=True, flow_end_time=0.1)
    data = _journey_deck({D0: (box(2.0, 2.0, 3.0, 3.0), params)})
    with pytest.raises(ValueError, match="exceeds area capacity"):
        _initialize(data, tmp_path)


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


@pytest.mark.parametrize("with_journeys", [True, False], ids=["journeys", "seeded"])
@pytest.mark.parametrize(
    ("extra", "expected"),
    [
        ({"percentage": 10}, 14),
        ({"percentage": 90}, 128),
        ({"percentage": 90, "number": 3}, 128),
        ({}, 71),
        ({"distribution_mode": "fill_area", "percentage": 75}, 107),
    ],
    ids=["10", "90", "90-number-ignored", "default-50", "fill-area-75"],
)
def test_by_percentage_count_follows_the_percentage(
    tmp_path, with_journeys, extra, expected
):
    """At the start, ``by_percentage`` fills the area to ``percentage`` (#436).

    floor(capacity estimate x percentage / 100): 36 m2 at radius 0.2 m is
    floor(36 / (pi 0.2^2) / 2) = 143 agents, so 10 % is 14 and 50 % 71.
    ``number`` is not read. ``Scenario.summary()`` counts the same.
    """
    params = {"distribution_mode": "by_percentage", "use_premovement": False}
    params.update(extra)
    area = {D0: (box(2.0, 2.0, 8.0, 8.0), params)}
    data = _journey_deck(area) if with_journeys else _deck(area)
    simulation, _, _, _ = _initialize(data, tmp_path)
    assert simulation.agent_count() == expected
    scenario = Scenario(
        raw=data,
        walkable_area_wkt=WALKABLE.wkt,
        model_type="CollisionFreeSpeedModel",
        seed=SEED,
        sim_params={},
    )
    assert f"  Agents:        ~{expected}" in scenario.summary().splitlines()
    assert scenario.list_distributions()[0]["agents"] == expected


def test_summary_counts_a_flow_spawn_by_percentage_as_the_run(tmp_path):
    """The views counted ``number`` for a flow spawn by percentage (#436)."""
    params = {
        "distribution_mode": "by_percentage",
        "percentage": 50,
        "use_flow_spawning": True,
        "flow_end_time": 60,
    }
    data = _journey_deck({D0: (box(2.0, 2.0, 8.0, 8.0), params)})
    _, _, _, info = _initialize(data, tmp_path)
    assert info["num_agents_per_source"] == [71]
    scenario = Scenario(
        raw=data,
        walkable_area_wkt=WALKABLE.wkt,
        model_type="CollisionFreeSpeedModel",
        seed=SEED,
        sim_params={},
    )
    assert scenario.list_distributions()[0]["agents"] == 71


STRIP = box(2.0, 4.5, 22.0, 5.5)
"""20 x 1 m: estimate 79 at radius 0.2 m, more than the sampler seats."""


@pytest.mark.parametrize("with_journeys", [True, False], ids=["journeys", "seeded"])
def test_fill_area_places_as_many_as_fit_up_to_its_count(tmp_path, with_journeys):
    """100 % of the estimate is an upper bound for ``fill_area`` (#436).

    Seed 3 seats 65 of the 79; the run places them, says so in one line
    and records it, instead of stopping with ``SpawnCapacityError``.
    """
    walkable = box(0.0, 0.0, 30.0, 10.0)
    area = {D0: (STRIP, {"distribution_mode": "fill_area", "use_premovement": False})}
    data = _journey_deck(area) if with_journeys else _deck(area)
    path = tmp_path / "deck.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    simulation = jps.Simulation(model=jps.CollisionFreeSpeedModel(), geometry=walkable)
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        _, _, _, info = initialize_simulation_from_json(
            str(path), simulation, pedpy.WalkableArea(walkable), seed=SEED
        )
    assert simulation.agent_count() == 65
    assert info["fill_placement"] == {D0: {"placed": 65, "upper_bound": 79}}
    assert f"Distribution '{D0}': fill_area placed 65 of at most 79 agents" in (
        out.getvalue().splitlines()
    )


def test_fill_area_shares_a_polygon_after_the_exact_counts(tmp_path):
    """Without journeys, an exact count on the same polygon is placed first.

    The 6 x 6 m area seats 143 at seed 3 of the 100 + 143 asked for; D0
    takes its 100 and the ``until_full`` area D1 the 43 left.
    """
    room = box(2.0, 2.0, 8.0, 8.0)
    data = _deck(
        {
            D0: (room, _params(100)),
            D1: (room, {"distribution_mode": "until_full", "use_premovement": False}),
        }
    )
    simulation, _, _, info = _initialize(data, tmp_path)
    assert simulation.agent_count() == 143
    assert info["fill_placement"] == {D1: {"placed": 43, "upper_bound": 143}}


def test_views_show_the_count_of_a_fill_mode_as_an_upper_bound():
    params = {"distribution_mode": "fill_area", "use_premovement": False}
    data = _deck({D0: (box(2.0, 2.0, 8.0, 8.0), params)})
    scenario = Scenario(
        raw=data,
        walkable_area_wkt=WALKABLE.wkt,
        model_type="CollisionFreeSpeedModel",
        seed=SEED,
        sim_params={},
    )
    lines = scenario.summary().splitlines()
    assert f"    {D0}: up to 143 agents" in lines
    assert "  Agents:        ~143" in lines


@pytest.mark.parametrize("with_journeys", [True, False], ids=["journeys", "seeded"])
def test_inactive_count_fields_are_not_checked(tmp_path, with_journeys):
    """A percentage mode does not read ``number``, nor a deck without a
    schedule ``initial_number``; neither stops the run (#436, #390)."""
    params = {
        "distribution_mode": "by_percentage",
        "percentage": 50,
        "number": -1,
        "initial_number": "x",
        "use_premovement": False,
    }
    area = {D0: (box(2.0, 2.0, 8.0, 8.0), params)}
    data = _journey_deck(area) if with_journeys else _deck(area)
    simulation, _, _, _ = _initialize(data, tmp_path)
    assert simulation.agent_count() == 71


def test_malformed_spawn_coordinates_are_skipped_with_a_warning(tmp_path):
    """Coordinates that are not numbers are skipped as an invalid polygon (#118)."""
    data = _journey_deck(
        {
            D0: (box(12.0, 2.0, 16.0, 8.0), _params(4)),
            D1: (box(2.0, 2.0, 4.0, 4.0), _params(3)),
        }
    )
    data["distributions"][D1]["coordinates"] = [[None, 0], [1, 0], [0, 1]]
    path = tmp_path / "deck.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    simulation = jps.Simulation(model=jps.CollisionFreeSpeedModel(), geometry=WALKABLE)
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        initialize_simulation_from_json(
            str(path), simulation, pedpy.WalkableArea(WALKABLE), seed=SEED
        )
    assert f"Warning: Error processing distribution {D1}: float()" in out.getvalue()
    assert simulation.agent_count() == 4
