"""journeys_v2 with several journeys per start area, and loop (#900)."""

from __future__ import annotations

import contextlib
import copy
import io
import json
import shutil
from pathlib import Path

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
    old_dir, raw = _copy_case("t_junction", tmp_path, "old")
    new_dir, _ = _copy_case("t_junction", tmp_path, "new")
    v2 = _as_v2(
        raw,
        [
            {"id": "a", "sequence": ["jps-checkpoints_0", "exit_A_left"]},
            {"id": "b", "sequence": ["jps-checkpoints_0", "exit_B_right"]},
        ],
        [{"journey_id": "a", "weight": 1}, {"journey_id": "b", "weight": 99}],
    )
    old = _trajectories(old_dir, raw, 20.0)
    new = _trajectories(new_dir, v2, 20.0)
    assert len(old) > 0
    assert old.equals(new)


def test_a_loop_patrols_as_before(tmp_path):
    """fed_incap_co_2000ppm's checkpoint loop, as one journey with loop."""
    old_dir, raw = _copy_case("fed_incap_co_2000ppm", tmp_path, "old")
    new_dir, _ = _copy_case("fed_incap_co_2000ppm", tmp_path, "new")
    (journey,) = raw["journeys"]
    sequence = [s for s in journey["stages"] if s not in raw["distributions"]]
    v2 = _as_v2(
        raw,
        [{"id": "patrol", "sequence": sequence, "loop": True}],
        [{"journey_id": "patrol", "weight": 100}],
    )
    old = _trajectories(old_dir, raw, 60.0)
    new = _trajectories(new_dir, v2, 60.0)
    assert len(old) > 0
    assert old.equals(new)
