"""Scenario loading, journey migration and flow-schedule normalisation.

Pins what ``load_scenario`` accepts (directory, JSON file, ZIP bundle) and
the errors it raises, the ``journeys_v2`` -> ``journeys``/``transitions``
migration of editor decks, the one flow-schedule normaliser that the
setter, the views and the run share, and the input checks of the public
``Scenario`` setters.
"""

import json
import zipfile

import pytest

from pyfds_evac.core import simulation_init
from pyfds_evac.core.scenario import (
    Scenario,
    _distribution_agent_budget,
    _migrate_journeys_v2,
    _normalize_flow_schedule_entry,
    _normalized_flow_schedule,
    load_scenario,
    run_scenario,
)

WALKABLE = "POLYGON ((0 0, 10 0, 10 5, 0 5, 0 0))"


def _square(x0: float, y0: float, size: float = 1.0) -> list[list[float]]:
    return [
        [x0, y0],
        [x0 + size, y0],
        [x0 + size, y0 + size],
        [x0, y0 + size],
        [x0, y0],
    ]


def _deck(**extra) -> dict:
    """A minimal scenario JSON: one distribution, one checkpoint, two exits."""
    data = {
        "config": {
            "simulation_settings": {
                "baseSeed": 7,
                "simulationParams": {"model_type": "CollisionFreeSpeedModelV2"},
            }
        },
        "distributions": {
            "jps-distributions_0": {
                "coordinates": _square(1, 1),
                "parameters": {"number": 3, "radius": 0.2, "v0": 1.2},
            },
            "jps-distributions_1": {
                "coordinates": _square(1, 3),
                "parameters": {"number": 2},
            },
        },
        "exits": {
            "jps-exits_0": {"coordinates": _square(9, 1)},
            "jps-exits_1": {"coordinates": _square(9, 3)},
        },
        "checkpoints": {
            "jps-checkpoints_0": {"coordinates": _square(5, 2), "waiting_time": 1.0}
        },
        "zones": {"zone_0": {"coordinates": _square(3, 2), "speed_factor": 0.5}},
    }
    data.update(extra)
    return data


def _scenario(data: dict | None = None) -> Scenario:
    data = _deck() if data is None else data
    settings = data["config"]["simulation_settings"]
    return Scenario(
        raw=data,
        walkable_area_wkt=WALKABLE,
        model_type=settings["simulationParams"]["model_type"],
        seed=settings["baseSeed"],
        sim_params=settings["simulationParams"],
    )


# ---------------------------------------------------------------------------
# load_scenario
# ---------------------------------------------------------------------------


def test_directory_prefers_config_json_and_geometry_wkt(tmp_path):
    (tmp_path / "a_other.json").write_text("{not json", encoding="utf-8")
    (tmp_path / "a_other.wkt").write_text("not wkt", encoding="utf-8")
    (tmp_path / "config.json").write_text(json.dumps(_deck()), encoding="utf-8")
    (tmp_path / "geometry.wkt").write_text(WALKABLE + "\n", encoding="utf-8")

    scenario = load_scenario(str(tmp_path))

    assert scenario.walkable_area_wkt == WALKABLE
    assert scenario.model_type == "CollisionFreeSpeedModelV2"
    assert scenario.seed == 7
    assert scenario.source_path == str(tmp_path.resolve())


def test_directory_falls_back_to_first_sorted_json_and_wkt(tmp_path):
    (tmp_path / "b.json").write_text("{not json", encoding="utf-8")
    (tmp_path / "a.json").write_text(json.dumps(_deck()), encoding="utf-8")
    (tmp_path / "b.wkt").write_text("not wkt", encoding="utf-8")
    (tmp_path / "a.wkt").write_text(WALKABLE, encoding="utf-8")

    scenario = load_scenario(str(tmp_path))

    assert scenario.walkable_area_wkt == WALKABLE
    assert scenario.walkable_polygon.area == pytest.approx(50.0)


@pytest.mark.parametrize("present", ["config.json", "geometry.wkt"])
def test_directory_without_json_or_wkt_is_rejected(tmp_path, present):
    content = json.dumps(_deck()) if present.endswith(".json") else WALKABLE
    (tmp_path / present).write_text(content, encoding="utf-8")
    with pytest.raises(ValueError, match="one JSON and one WKT file"):
        load_scenario(str(tmp_path))


def test_json_file_with_inline_walkable_area(tmp_path):
    path = tmp_path / "deck.json"
    path.write_text(json.dumps(_deck(walkable_area_wkt=WALKABLE)), encoding="utf-8")
    scenario = load_scenario(str(path))
    assert scenario.walkable_area_wkt == WALKABLE
    assert scenario.source_path == str(path.resolve())


def test_json_file_with_walkable_area_under_geometry(tmp_path):
    path = tmp_path / "deck.json"
    deck = _deck(geometry={"walkable_area_wkt": WALKABLE})
    path.write_text(json.dumps(deck), encoding="utf-8")
    assert load_scenario(str(path)).walkable_area_wkt == WALKABLE


def test_json_file_takes_first_sibling_wkt(tmp_path):
    path = tmp_path / "deck.json"
    path.write_text(json.dumps(_deck()), encoding="utf-8")
    (tmp_path / "a.wkt").write_text(WALKABLE + "\n", encoding="utf-8")
    (tmp_path / "b.wkt").write_text("not wkt", encoding="utf-8")
    assert load_scenario(str(path)).walkable_area_wkt == WALKABLE


def test_json_file_without_any_walkable_area_is_rejected(tmp_path):
    path = tmp_path / "deck.json"
    path.write_text(json.dumps(_deck()), encoding="utf-8")
    with pytest.raises(ValueError, match="walkable_area_wkt"):
        load_scenario(str(path))


def test_zip_bundle(tmp_path):
    bundle = tmp_path / "deck.zip"
    with zipfile.ZipFile(bundle, "w") as zf:
        zf.writestr("config.json", json.dumps(_deck()))
        zf.writestr("geometry.wkt", WALKABLE + "\n")
    scenario = load_scenario(str(bundle))
    assert scenario.walkable_area_wkt == WALKABLE
    assert scenario.seed == 7
    assert scenario.source_path == str(bundle.resolve())


@pytest.mark.parametrize(
    ("member", "message"),
    [("geometry.wkt", "no JSON file"), ("config.json", "no WKT file")],
)
def test_zip_bundle_missing_a_member_is_rejected(tmp_path, member, message):
    bundle = tmp_path / "deck.zip"
    with zipfile.ZipFile(bundle, "w") as zf:
        content = json.dumps(_deck()) if member.endswith(".json") else WALKABLE
        zf.writestr(member, content)
    with pytest.raises(ValueError, match=message):
        load_scenario(str(bundle))


def test_missing_path_raises_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_scenario(str(tmp_path / "missing.json"))
    with pytest.raises(FileNotFoundError):
        load_scenario(str(tmp_path / "missing"))


def test_defaults_when_simulation_settings_are_absent(tmp_path):
    deck = _deck(walkable_area_wkt=WALKABLE)
    del deck["config"]
    path = tmp_path / "deck.json"
    path.write_text(json.dumps(deck), encoding="utf-8")

    scenario = load_scenario(str(path))

    assert scenario.model_type == "CollisionFreeSpeedModel"
    assert scenario.seed == 42
    assert scenario.max_simulation_time == 300
    settings = scenario.raw["config"]["simulation_settings"]
    assert settings["baseSeed"] == 42
    assert settings["simulationParams"]["model_type"] == "CollisionFreeSpeedModel"


def test_configured_max_simulation_time_is_kept(tmp_path):
    deck = _deck(walkable_area_wkt=WALKABLE)
    deck["config"]["simulation_settings"]["simulationParams"]["max_simulation_time"] = (
        45.0
    )
    path = tmp_path / "deck.json"
    path.write_text(json.dumps(deck), encoding="utf-8")
    assert load_scenario(str(path)).max_simulation_time == 45.0


def test_load_migrates_editor_journeys(tmp_path):
    deck = _deck(
        walkable_area_wkt=WALKABLE,
        journeys_v2=[
            {"id": "j1", "sequence": ["jps-checkpoints_0", "jps-exits_1"]},
        ],
    )
    deck["distributions"]["jps-distributions_0"]["journey_weights"] = [
        {"journey_id": "j1", "weight": 100}
    ]
    path = tmp_path / "deck.json"
    path.write_text(json.dumps(deck), encoding="utf-8")

    scenario = load_scenario(str(path))

    assert scenario.journeys == [
        {
            "id": "j1",
            "stages": ["jps-distributions_0", "jps-checkpoints_0", "jps-exits_1"],
            "transitions": [
                {
                    "from": "jps-distributions_0",
                    "to": "jps-checkpoints_0",
                    "journey_id": "j1",
                },
                {"from": "jps-checkpoints_0", "to": "jps-exits_1", "journey_id": "j1"},
            ],
        }
    ]


# ---------------------------------------------------------------------------
# _migrate_journeys_v2
# ---------------------------------------------------------------------------


def _editor_deck(weights: dict[str, list], journeys_v2) -> dict:
    deck = _deck(journeys_v2=journeys_v2)
    for dist_id, entries in weights.items():
        deck["distributions"][dist_id]["journey_weights"] = entries
    return deck


def test_migration_builds_one_chain_per_distribution():
    deck = _editor_deck(
        {
            "jps-distributions_0": [{"journey_id": "j1", "weight": 100}],
            "jps-distributions_1": [{"journey_id": "j2", "weight": 100}],
        },
        [
            {
                "id": "j1",
                "name": "via checkpoint",
                "sequence": ["jps-checkpoints_0", "jps-exits_0"],
            },
            {"id": "j2", "sequence": ["jps-exits_1"]},
        ],
    )

    _migrate_journeys_v2(deck)

    assert [j["id"] for j in deck["journeys"]] == ["j1", "j2"]
    assert deck["journeys"][0]["stages"] == [
        "jps-distributions_0",
        "jps-checkpoints_0",
        "jps-exits_0",
    ]
    assert deck["journeys"][1]["stages"] == ["jps-distributions_1", "jps-exits_1"]
    assert deck["transitions"] == [
        {"from": "jps-distributions_0", "to": "jps-checkpoints_0", "journey_id": "j1"},
        {"from": "jps-checkpoints_0", "to": "jps-exits_0", "journey_id": "j1"},
        {"from": "jps-distributions_1", "to": "jps-exits_1", "journey_id": "j2"},
    ]


def test_migration_gives_a_shared_journey_a_unique_id_per_distribution():
    shared = [{"journey_id": "j1", "weight": 100}]
    deck = _editor_deck(
        {"jps-distributions_0": shared, "jps-distributions_1": list(shared)},
        [{"id": "j1", "sequence": ["jps-exits_0"]}],
    )

    _migrate_journeys_v2(deck)

    ids = [j["id"] for j in deck["journeys"]]
    assert ids == ["j1", "j1::jps-distributions_1"]
    assert {t["journey_id"] for t in deck["transitions"]} == set(ids)


def test_migration_skips_distributions_split_across_journeys():
    deck = _editor_deck(
        {
            "jps-distributions_0": [
                {"journey_id": "j1", "weight": 50},
                {"journey_id": "j2", "weight": 50},
            ],
            "jps-distributions_1": [{"journey_id": "j2", "weight": 100}],
        },
        [
            {"id": "j1", "sequence": ["jps-exits_0"]},
            {"id": "j2", "sequence": ["jps-exits_1"]},
        ],
    )

    _migrate_journeys_v2(deck)

    assert [j["stages"][0] for j in deck["journeys"]] == ["jps-distributions_1"]


def test_migration_is_idempotent():
    deck = _editor_deck(
        {"jps-distributions_0": [{"journey_id": "j1", "weight": 100}]},
        [{"id": "j1", "sequence": ["jps-exits_0"]}],
    )
    _migrate_journeys_v2(deck)
    once = json.loads(json.dumps(deck))

    _migrate_journeys_v2(deck)

    assert deck == once


def test_migration_keeps_existing_legacy_journeys():
    legacy = [{"id": "legacy", "stages": ["jps-distributions_0", "jps-exits_1"]}]
    deck = _editor_deck(
        {"jps-distributions_0": [{"journey_id": "j1", "weight": 100}]},
        [{"id": "j1", "sequence": ["jps-exits_0"]}],
    )
    deck["journeys"] = legacy

    _migrate_journeys_v2(deck)

    assert deck["journeys"] is legacy
    assert "transitions" not in deck


@pytest.mark.parametrize(
    "journeys_v2",
    [
        None,
        [],
        {"id": "j1", "sequence": ["jps-exits_0"]},
        [{"id": "j1", "sequence": []}],
        [{"sequence": ["jps-exits_0"]}],
        ["j1"],
    ],
    ids=["none", "empty", "not-a-list", "empty-sequence", "no-id", "not-a-dict"],
)
def test_migration_ignores_unusable_editor_journeys(journeys_v2):
    deck = _editor_deck(
        {"jps-distributions_0": [{"journey_id": "j1", "weight": 100}]}, journeys_v2
    )
    _migrate_journeys_v2(deck)
    assert "journeys" not in deck
    assert "transitions" not in deck


def test_migration_ignores_weights_naming_an_unknown_journey():
    deck = _editor_deck(
        {"jps-distributions_0": [{"journey_id": "nope", "weight": 100}]},
        [{"id": "j1", "sequence": ["jps-exits_0"]}],
    )
    _migrate_journeys_v2(deck)
    assert "journeys" not in deck


@pytest.mark.parametrize(
    ("drawn_route", "expected_exit"),
    [(False, "jps-exits_0"), (True, "jps-exits_1")],
    ids=["nearest-exit", "drawn-route"],
)
def test_migrated_route_is_the_one_agents_walk(drawn_route, expected_exit):
    # jps-exits_0 is nearest to the distribution; the drawn route leads
    # through the checkpoint to jps-exits_1 instead.
    deck = _deck(
        journeys_v2=[{"id": "j1", "sequence": ["jps-checkpoints_0", "jps-exits_1"]}]
    )
    del deck["distributions"]["jps-distributions_1"]
    dist = deck["distributions"]["jps-distributions_0"]
    dist["parameters"]["use_premovement"] = False
    if drawn_route:
        dist["journey_weights"] = [{"journey_id": "j1", "weight": 100}]
    params = deck["config"]["simulation_settings"]["simulationParams"]
    params.update(model_type="CollisionFreeSpeedModel", max_simulation_time=60)
    _migrate_journeys_v2(deck)

    result = run_scenario(_scenario(deck), seed=1)
    try:
        assert result.agents_evacuated == result.total_agents == 3
        assert {row["exit_id"] for row in result.exit_history} == {expected_exit}
    finally:
        result.cleanup()


# ---------------------------------------------------------------------------
# Flow schedules
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "entry",
    [
        {"flow_start_time": 2, "flow_end_time": "8.5", "number": "4"},
        {"start_time_s": 2, "end_time_s": 8.5, "sim_count": 4.0},
    ],
    ids=["canonical-keys", "alias-keys"],
)
def test_flow_entry_is_normalised_to_canonical_keys_and_types(entry):
    normalized = _normalize_flow_schedule_entry(entry)
    assert normalized == {"flow_start_time": 2.0, "flow_end_time": 8.5, "number": 4}
    assert isinstance(normalized["flow_start_time"], float)
    assert isinstance(normalized["number"], int)


def test_flow_entry_canonical_key_wins_over_alias():
    normalized = _normalize_flow_schedule_entry(
        {
            "flow_start_time": 1,
            "start_time_s": 5,
            "flow_end_time": 3,
            "end_time_s": 9,
            "number": 2,
            "sim_count": 7,
        }
    )
    assert normalized == {"flow_start_time": 1.0, "flow_end_time": 3.0, "number": 2}


@pytest.mark.parametrize("missing", ["flow_start_time", "flow_end_time", "number"])
def test_flow_entry_without_a_required_key_is_rejected(missing):
    entry = {"flow_start_time": 0, "flow_end_time": 5, "number": 3}
    del entry[missing]
    with pytest.raises(ValueError, match="must define start/end time and number"):
        _normalize_flow_schedule_entry(entry)


@pytest.mark.parametrize(
    ("entry", "message"),
    [
        (
            {"flow_start_time": -1, "flow_end_time": 5, "number": 3},
            "Invalid flow window",
        ),
        (
            {"flow_start_time": 5, "flow_end_time": 5, "number": 3},
            "Invalid flow window",
        ),
        (
            {"flow_start_time": 6, "flow_end_time": 5, "number": 3},
            "Invalid flow window",
        ),
        ({"flow_start_time": 0, "flow_end_time": 5, "number": 0}, "positive integers"),
        ({"flow_start_time": 0, "flow_end_time": 5, "number": -2}, "positive integers"),
    ],
    ids=["negative-start", "empty-window", "reversed-window", "zero", "negative"],
)
def test_flow_entry_with_invalid_window_or_number_is_rejected(entry, message):
    with pytest.raises(ValueError, match=message):
        _normalize_flow_schedule_entry(entry)


def test_flow_schedule_is_sorted_by_start_then_end():
    schedule = [
        {"flow_start_time": 10, "flow_end_time": 20, "number": 1},
        {"flow_start_time": 0, "flow_end_time": 8, "number": 2},
        {"flow_start_time": 0, "flow_end_time": 4, "number": 3},
    ]
    normalized = _normalized_flow_schedule({"flow_schedule": schedule})
    assert [(e["flow_start_time"], e["flow_end_time"]) for e in normalized] == [
        (0.0, 4.0),
        (0.0, 8.0),
        (10.0, 20.0),
    ]
    assert _normalized_flow_schedule({}) == []
    assert _normalized_flow_schedule({"flow_schedule": []}) == []


@pytest.mark.parametrize(
    ("params", "budget"),
    [
        ({"number": 7}, 7),
        ({}, 0),
        ({"number": None}, 0),
        (
            {
                "number": 99,
                "flow_schedule": [
                    {"flow_start_time": 0, "flow_end_time": 5, "number": 3},
                    {"start_time_s": 5, "end_time_s": 9, "sim_count": 4},
                ],
            },
            7,
        ),
        (
            {
                "initial_number": 2,
                "flow_schedule": [
                    {"flow_start_time": 0, "flow_end_time": 5, "number": 3}
                ],
            },
            5,
        ),
    ],
    ids=[
        "number",
        "empty",
        "none",
        "schedule-overrides-number",
        "initial-plus-schedule",
    ],
)
def test_distribution_agent_budget(params, budget):
    assert _distribution_agent_budget({"parameters": params}) == budget


def test_the_run_reads_flow_schedules_with_the_same_normaliser():
    """One normaliser for the setter, the views and the run (#390)."""
    assert simulation_init._normalized_flow_schedule is _normalized_flow_schedule


@pytest.mark.parametrize(
    "entry",
    [
        {"flow_start_time": -3, "flow_end_time": 4, "number": 2},
        {"flow_start_time": 5, "flow_end_time": 9, "number": 0},
    ],
    ids=["negative-start", "no-agents"],
)
def test_run_rejects_the_flow_windows_the_setter_rejects(entry):
    """The run once clamped a negative start and dropped empty windows (#390)."""
    with pytest.raises(ValueError, match="Distribution 'D': flow_schedule: "):
        simulation_init._convert_flow_schedule({"flow_schedule": [entry]}, "D")


# ---------------------------------------------------------------------------
# Scenario: id resolution, discovery and setters
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("setter", "args", "target"),
    [
        (
            "set_agent_count",
            (5,),
            ("distributions", "jps-distributions_1", "parameters", "number"),
        ),
        ("set_zone_speed_factor", (0.25,), ("zones", "zone_0", "speed_factor")),
        (
            "set_checkpoint_waiting_time",
            (3.5,),
            ("checkpoints", "jps-checkpoints_0", "waiting_time"),
        ),
    ],
)
def test_setters_resolve_ids_by_index_and_by_key(setter, args, target):
    collection, key, *path = target
    index = list(_deck()[collection]).index(key)
    by_index, by_key = _scenario(), _scenario()

    getattr(by_index, setter)(index, *args)
    getattr(by_key, setter)(key, *args)

    for scenario in (by_index, by_key):
        value = scenario.raw[collection][key]
        for part in path:
            value = value[part]
        assert value == args[0]


@pytest.mark.parametrize(
    ("setter", "kind", "args"),
    [
        ("set_agent_count", "Distribution", (5,)),
        ("set_zone_speed_factor", "Zone", (0.5,)),
        ("set_checkpoint_waiting_time", "Stage", (1.0,)),
    ],
)
def test_unknown_ids_are_rejected(setter, kind, args):
    scenario = _scenario()
    method = getattr(scenario, setter)
    with pytest.raises(IndexError, match=f"{kind} index 9 out of range"):
        method(9, *args)
    with pytest.raises(IndexError, match=f"{kind} index -1 out of range"):
        method(-1, *args)
    with pytest.raises(KeyError, match=f"{kind} 'nope' not found"):
        method("nope", *args)


def test_discovery_lists_index_id_and_settings():
    scenario = _scenario()
    scenario.set_flow_schedule(
        1, [{"flow_start_time": 0, "flow_end_time": 5, "number": 4}]
    )
    assert scenario.list_distributions() == [
        {"index": 0, "id": "jps-distributions_0", "agents": 3, "flow": False},
        {"index": 1, "id": "jps-distributions_1", "agents": 4, "flow": True},
    ]
    assert scenario.list_zones() == [{"index": 0, "id": "zone_0", "speed_factor": 0.5}]
    assert scenario.list_stages() == [
        {"index": 0, "id": "jps-checkpoints_0", "waiting_time": 1.0}
    ]


def test_summary_reports_the_agent_budget():
    scenario = _scenario()
    scenario.set_flow_schedule(
        "jps-distributions_1",
        [{"flow_start_time": 0, "flow_end_time": 5, "number": 4}],
        keep_initial_agents=True,
    )
    lines = scenario.summary().splitlines()
    assert "  Agents:        ~9" in lines
    assert "  Model:         CollisionFreeSpeedModelV2" in lines


def test_summary_lists_the_initial_and_scheduled_agents_of_a_spawn_area():
    """Per spawn area, the summary counts what the run places (#390)."""
    scenario = _scenario()
    scenario.set_flow_schedule(
        "jps-distributions_1",
        [
            {"flow_start_time": 0, "flow_end_time": 5, "number": 4},
            {"flow_start_time": 10, "flow_end_time": 12, "number": 1},
        ],
        keep_initial_agents=True,
    )
    lines = scenario.summary().splitlines()
    assert (
        "    jps-distributions_1: 7 agents (2 at the start, flow: 4 in 0-5s, 1 in 10-12s)"
        in lines
    )
    assert "  Agents:        ~10" in lines


def test_summary_counts_spawn_areas_of_any_name_in_the_route():
    """The route counts every key of ``distributions`` as a spawn area (#409)."""
    data = _deck(journeys=[{"id": "J", "stages": ["room", "jps-exits_0"]}])
    data["distributions"] = {"room": data["distributions"]["jps-distributions_0"]}
    lines = _scenario(data).summary().splitlines()
    assert "  Route:         1 distribution, 0 checkpoint, 1 exit" in lines


def test_set_flow_schedule_sorts_and_derives_the_window():
    scenario = _scenario()
    scenario.set_flow_schedule(
        "jps-distributions_0",
        [
            {"start_time_s": 10, "end_time_s": 20, "sim_count": 5},
            {"flow_start_time": 0, "flow_end_time": 4, "number": 2},
        ],
    )
    params = scenario.distributions["jps-distributions_0"]["parameters"]
    assert params["flow_schedule"] == [
        {"flow_start_time": 0.0, "flow_end_time": 4.0, "number": 2},
        {"flow_start_time": 10.0, "flow_end_time": 20.0, "number": 5},
    ]
    assert params["use_flow_spawning"] is True
    assert params["distribution_mode"] == "by_number"
    assert params["number"] == 7
    assert params["flow_start_time"] == 0.0
    assert params["flow_end_time"] == 20.0
    assert "initial_number" not in params


def test_set_flow_schedule_keeps_initial_agents_on_request():
    scenario = _scenario()
    window = [{"flow_start_time": 0, "flow_end_time": 4, "number": 2}]

    scenario.set_flow_schedule(0, window, keep_initial_agents=True)
    params = scenario.distributions["jps-distributions_0"]["parameters"]
    assert params["initial_number"] == 3
    assert _distribution_agent_budget({"parameters": params}) == 5

    scenario.set_flow_schedule(0, window)
    assert "initial_number" not in params


@pytest.mark.parametrize("schedule", [[], None, {"number": 1}])
def test_set_flow_schedule_requires_a_non_empty_list(schedule):
    with pytest.raises(ValueError, match="non-empty list"):
        _scenario().set_flow_schedule(0, schedule)


def test_set_flow_schedule_rejects_an_invalid_entry_without_changes():
    scenario = _scenario()
    before = json.loads(json.dumps(scenario.raw))
    with pytest.raises(ValueError, match="Invalid flow window"):
        scenario.set_flow_schedule(
            0,
            [
                {"flow_start_time": 0, "flow_end_time": 4, "number": 2},
                {"flow_start_time": 4, "flow_end_time": 1, "number": 2},
            ],
        )
    assert scenario.raw == before


@pytest.mark.parametrize(
    ("kwargs", "mirrored"),
    [
        ({"desired_speed": 1.5}, {"desired_speed": 1.5, "v0": 1.5}),
        ({"v0": 0.9}, {"desired_speed": 0.9, "v0": 0.9}),
        ({"v0_std": 0.1}, {"desired_speed_std": 0.1, "v0_std": 0.1}),
        (
            {"desired_speed_distribution": "gaussian"},
            {"desired_speed_distribution": "gaussian", "v0_distribution": "gaussian"},
        ),
    ],
)
def test_set_agent_params_mirrors_speed_aliases(kwargs, mirrored):
    # The run reads only the v0* keys (scenario-json.md, #143), so the
    # desired_speed* spellings must reach them.
    scenario = _scenario()
    scenario.set_agent_params("jps-distributions_0", **kwargs)
    params = scenario.distributions["jps-distributions_0"]["parameters"]
    for key, value in mirrored.items():
        assert params[key] == value


def test_set_agent_params_accepts_boundaries():
    scenario = _scenario()
    scenario.set_agent_params(
        0, radius=1.0, desired_speed=5.0, desired_speed_std=0.0, number=1
    )
    params = scenario.distributions["jps-distributions_0"]["parameters"]
    assert (params["radius"], params["v0"], params["v0_std"], params["number"]) == (
        1.0,
        5.0,
        0.0,
        1,
    )


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"radius": 0}, "radius must be in"),
        ({"radius": 1.01}, "radius must be in"),
        ({"radius": "0.2"}, "radius must be in"),
        ({"desired_speed": 0}, "desired_speed/v0 must be in"),
        ({"v0": 5.1}, "desired_speed/v0 must be in"),
        ({"v0_std": -0.1}, "desired_speed_std/v0_std must be non-negative"),
        ({"v0_distribution": "uniform"}, "must be 'constant' or 'gaussian'"),
        ({"number": 0}, "number must be a positive integer"),
        ({"number": 2.0}, "number must be a positive integer"),
    ],
)
def test_set_agent_params_rejects_out_of_range_values(kwargs, message):
    scenario = _scenario()
    before = json.loads(json.dumps(scenario.raw))
    with pytest.raises(ValueError, match=message):
        scenario.set_agent_params(0, **kwargs)
    assert scenario.raw == before


def test_set_agent_count_switches_to_by_number():
    scenario = _scenario()
    scenario.distributions["jps-distributions_0"]["parameters"]["distribution_mode"] = (
        "by_percentage"
    )
    scenario.set_agent_count(0, 4)
    params = scenario.distributions["jps-distributions_0"]["parameters"]
    assert (params["number"], params["distribution_mode"]) == (4, "by_number")


@pytest.mark.parametrize("count", [0, -1, 2.0])
def test_set_agent_count_rejects_non_positive_or_non_int(count):
    with pytest.raises(ValueError, match="count must be a positive integer"):
        _scenario().set_agent_count(0, count)


def test_set_seed_max_time_and_model_reach_the_raw_config():
    scenario = _scenario()
    scenario.set_seed(0)
    scenario.set_max_time(12.5)
    scenario.set_model_type("CollisionFreeSpeedModel")
    scenario.set_model_params(strength_neighbor_repulsion=3.0, label="x")

    settings = scenario.raw["config"]["simulation_settings"]
    params = settings["simulationParams"]
    assert scenario.seed == 0 and settings["baseSeed"] == 0
    assert scenario.max_simulation_time == 12.5
    assert params["max_simulation_time"] == 12.5
    assert scenario.model_type == "CollisionFreeSpeedModel"
    assert params["model_type"] == "CollisionFreeSpeedModel"
    assert params["strength_neighbor_repulsion"] == 3.0
    assert scenario.sim_params["label"] == "x"


@pytest.mark.parametrize(
    ("setter", "value", "message"),
    [
        ("set_seed", -1, "seed must be a non-negative integer"),
        ("set_seed", 1.0, "seed must be a non-negative integer"),
        ("set_max_time", 0, "seconds must be a positive number"),
        ("set_max_time", "10", "seconds must be a positive number"),
        ("set_model_type", "SocialForce", "Unknown model"),
    ],
)
def test_scalar_setters_reject_invalid_values(setter, value, message):
    with pytest.raises(ValueError, match=message):
        getattr(_scenario(), setter)(value)


def test_set_model_params_rejects_negative_numbers_without_changes():
    scenario = _scenario()
    with pytest.raises(
        ValueError, match="'range_neighbor_repulsion' must be non-negative"
    ):
        scenario.set_model_params(
            strength_neighbor_repulsion=1.0, range_neighbor_repulsion=-0.1
        )
    assert "strength_neighbor_repulsion" not in scenario.sim_params


@pytest.mark.parametrize(
    ("setter", "value", "message"),
    [
        ("set_zone_speed_factor", -0.1, "factor must be non-negative"),
        ("set_checkpoint_waiting_time", -1, "waiting_time must be non-negative"),
    ],
)
def test_zone_and_checkpoint_setters_reject_negative_values(setter, value, message):
    with pytest.raises(ValueError, match=message):
        getattr(_scenario(), setter)(0, value)


def test_copy_is_independent_and_applies_overrides():
    scenario = _scenario()
    clone = scenario.copy(
        seed=11, walkable_area_wkt="POLYGON ((0 0, 4 0, 4 4, 0 4, 0 0))"
    )
    clone.set_agent_count(0, 9)

    assert clone.seed == 11
    assert clone.raw["config"]["simulation_settings"]["baseSeed"] == 11
    assert clone.walkable_polygon.area == pytest.approx(16.0)
    assert scenario.seed == 7
    assert scenario.walkable_polygon.area == pytest.approx(50.0)
    assert scenario.distributions["jps-distributions_0"]["parameters"]["number"] == 3
    with pytest.raises(AttributeError, match="no attribute 'nope'"):
        scenario.copy(nope=1)
