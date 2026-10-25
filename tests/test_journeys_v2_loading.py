"""journeys_v2 with several journeys per start area, and loop (#900)."""

from __future__ import annotations

import contextlib
import copy
import io
import json
import shutil
from pathlib import Path

import pyfds_evac.core.simulation_init as simulation_init
from pyfds_evac.core.run_outputs import _export_app_bundle
from pyfds_evac.core.scenario import (
    _migrate_journeys_v2,
    load_scenario,
    run_scenario,
)

ASSETS = Path(__file__).resolve().parents[1] / "assets"


def _v2_deck(weights: list[dict], journeys_v2: list[dict]) -> dict:
    return {
        "distributions": {"d0": {"journey_weights": weights}},
        "journeys_v2": journeys_v2,
    }


def test_a_start_area_split_over_two_journeys_gets_both():
    deck = _v2_deck(
        [{"journey_id": "a", "weight": 70}, {"journey_id": "b", "weight": 30}],
        [
            {"id": "a", "sequence": ["cp", "exit_a"]},
            {"id": "b", "sequence": ["cp", "exit_b"]},
        ],
    )
    _migrate_journeys_v2(deck)
    assert [(j["id"], j["stages"], j["spawn_weight"]) for j in deck["journeys"]] == [
        ("a", ["d0", "cp", "exit_a"], 70.0),
        ("b", ["d0", "cp", "exit_b"], 30.0),
    ]


def test_loop_closes_the_sequence():
    deck = _v2_deck(
        [{"journey_id": "p", "weight": 100}],
        [{"id": "p", "sequence": ["c1", "c2", "c3"], "loop": True}],
    )
    _migrate_journeys_v2(deck)
    pairs = [(t["from"], t["to"]) for t in deck["journeys"][0]["transitions"]]
    assert pairs == [("d0", "c1"), ("c1", "c2"), ("c2", "c3"), ("c3", "c1")]


def test_a_repeated_journey_keeps_every_weight():
    deck = _v2_deck(
        [{"journey_id": "a", "weight": w} for w in (10, 10, 80)],
        [{"id": "a", "sequence": ["exit"]}],
    )
    _migrate_journeys_v2(deck)
    ids = [j["id"] for j in deck["journeys"]]
    assert len(set(ids)) == 3
    assert [j["spawn_weight"] for j in deck["journeys"]] == [10.0, 10.0, 80.0]


def test_loop_must_be_true():
    deck = _v2_deck(
        [{"journey_id": "p", "weight": 100}],
        [{"id": "p", "sequence": ["c1", "c2"], "loop": "false"}],
    )
    _migrate_journeys_v2(deck)
    pairs = [(t["from"], t["to"]) for t in deck["journeys"][0]["transitions"]]
    assert pairs == [("d0", "c1"), ("c1", "c2")]


def test_unusable_weights_are_skipped():
    deck = _v2_deck(
        [
            {"journey_id": "a", "weight": 0},
            {"journey_id": "b", "weight": -5},
            {"journey_id": "c", "weight": "x"},
        ],
        [{"id": k, "sequence": ["exit"]} for k in "abc"],
    )
    _migrate_journeys_v2(deck)
    assert "journeys" not in deck


def _trajectories(folder: Path, raw: dict, max_time: float):
    (folder / "config.json").write_text(json.dumps(raw), encoding="utf-8")
    scenario = load_scenario(str(folder / "config.json")).copy()
    scenario.set_max_time(max_time)
    with contextlib.redirect_stdout(io.StringIO()):
        result = run_scenario(scenario, seed=1)
    try:
        frame = result.trajectory_dataframe()
        # JuPedSim numbers agents from a process-wide counter: count from 0 per run.
        frame["id"] = frame["id"].rank(method="dense").astype(int) - 1
        return frame.sort_values(["frame", "id"]).reset_index(drop=True)
    finally:
        result.cleanup()


def _copy_case(case: str, tmp_path: Path, name: str) -> tuple[Path, dict]:
    folder = tmp_path / name
    shutil.copytree(ASSETS / case, folder)
    raw = json.loads((ASSETS / case / "config.json").read_text(encoding="utf-8"))
    return folder, raw


def _as_v2(raw: dict, journeys_v2: list[dict], weights: list[dict]) -> dict:
    v2 = copy.deepcopy(raw)
    for key in ("journeys", "transitions", "waypoint_routing"):
        v2.pop(key, None)
    v2["journeys_v2"] = journeys_v2
    (dist,) = v2["distributions"].values()
    dist["journey_weights"] = weights
    return v2


def test_shares_written_as_journeys_run_as_before(tmp_path):
    """t_junction's 1/99 split at the checkpoint, as two weighted journeys."""
    journeys = [
        {"id": "a", "sequence": ["jps-checkpoints_0", "exit_A_left"]},
        {"id": "b", "sequence": ["jps-checkpoints_0", "exit_B_right"]},
    ]
    a, b = {"journey_id": "a"}, {"journey_id": "b"}
    decks = {
        "as_written": (journeys, [{**a, "weight": 1}, {**b, "weight": 99}]),
        "swapped": (journeys, [{**b, "weight": 99}, {**a, "weight": 1}]),
        "all_b": (journeys[1:], [{**b, "weight": 100}]),
    }
    old_dir, raw = _copy_case("t_junction", tmp_path, "old")
    old = _trajectories(old_dir, raw, 60.0)
    # Some agent turns west of the checkpoint, so the window sees the 1 % share.
    assert old.groupby("id")["x"].min().lt(15).any()
    same = {}
    for name, (journeys_v2, weights) in decks.items():
        folder, _ = _copy_case("t_junction", tmp_path, name)
        new = _trajectories(folder, _as_v2(raw, journeys_v2, weights), 60.0)
        same[name] = old.equals(new)
    assert same == {"as_written": True, "swapped": False, "all_b": False}


def test_a_loop_patrols_as_before(tmp_path):
    """One lap of fed_incap_co_2000ppm's patrol, closed by loop."""
    old_dir, raw = _copy_case("fed_incap_co_2000ppm", tmp_path, "old")
    (journey,) = raw["journeys"]
    start = journey["stages"][0]
    lap = journey["stages"][1:5]
    stages = [start, *lap]
    pairs = [*zip(stages, stages[1:]), (lap[-1], lap[0])]
    journey["stages"] = stages
    journey["transitions"] = [
        {"from": a, "to": b, "journey_id": journey["id"]} for a, b in pairs
    ]
    raw["transitions"] = journey["transitions"]
    weights = [{"journey_id": "patrol", "weight": 100}]
    old = _trajectories(old_dir, raw, 60.0)
    assert len(old) > 0
    same = {}
    for name, loop in (("loop", True), ("no_loop", False)):
        folder, _ = _copy_case("fed_incap_co_2000ppm", tmp_path, name)
        deck = _as_v2(raw, [{"id": "patrol", "sequence": lap, "loop": loop}], weights)
        same[name] = old.equals(_trajectories(folder, deck, 60.0))
    assert same == {"loop": True, "no_loop": False}


def _t_junction_v2(tmp_path: Path, keep_routing: bool) -> Path:
    folder, raw = _copy_case("t_junction", tmp_path, "v2")
    v2 = _as_v2(
        raw,
        [{"id": "journey_0", "sequence": ["jps-checkpoints_0", "exit_B_right"]}],
        [{"journey_id": "journey_0", "weight": 100}],
    )
    if keep_routing:
        v2["waypoint_routing"] = raw["waypoint_routing"]
    (folder / "config.json").write_text(json.dumps(v2), encoding="utf-8")
    return folder / "config.json"


def test_waypoint_routing_shares_scale_the_journey_weight(tmp_path, monkeypatch):
    """A journey's weight is split by its waypoint_routing shares, not replaced."""
    shares = []
    build = simulation_init._create_journeys_with_percentages

    def spy(*args, **kwargs):
        out = build(*args, **kwargs)
        for variants in out["journeys_per_distribution"].values():
            shares.extend(v["variant_data"]["percentage"] for v in variants)
        return out

    monkeypatch.setattr(simulation_init, "_create_journeys_with_percentages", spy)
    scenario = load_scenario(str(_t_junction_v2(tmp_path, keep_routing=True))).copy()
    scenario.set_max_time(1.0)
    with contextlib.redirect_stdout(io.StringIO()):
        run_scenario(scenario, seed=1).cleanup()
    assert sorted(shares) == [1.0, 99.0]


def test_exported_bundle_is_plain_journeys_v2(tmp_path):
    """The exported file carries journeys_v2 only, and reloads to the same journeys."""
    path = _t_junction_v2(tmp_path, keep_routing=False)
    scenario = load_scenario(str(path))
    _export_app_bundle(scenario, str(tmp_path / "bundle"))
    exported = json.loads((tmp_path / "bundle" / "config.json").read_text())
    assert "journeys_v2" in exported
    assert "journeys" not in exported
    assert "transitions" not in exported
    reloaded = load_scenario(str(tmp_path / "bundle"))
    assert reloaded.journeys == scenario.journeys
