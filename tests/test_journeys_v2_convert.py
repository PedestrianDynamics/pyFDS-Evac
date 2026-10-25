"""Old-format journeys to journeys_v2 (#900)."""

from __future__ import annotations

import json

import pytest
from pyfds_evac.core.journeys_v2 import (
    JourneyConversionError,
    convert_legacy_journeys,
    main,
)


def _deck(stages, pairs, routing=None, dists=("d0",), **journey_keys):
    journey = {"id": "j", "stages": list(stages), **journey_keys}
    journey["transitions"] = [{"from": a, "to": b, "journey_id": "j"} for a, b in pairs]
    return {
        "distributions": {d: {"parameters": {}} for d in dists},
        "exits": {"exit_a": {}, "exit_b": {}},
        "journeys": [journey],
        "transitions": list(journey["transitions"]),
        "waypoint_routing": routing or {},
    }


def _routes(converted):
    by_id = {j["id"]: j for j in converted["journeys_v2"]}
    return {
        d: [
            (by_id[w["journey_id"]]["sequence"], w["weight"])
            for w in dist.get("journey_weights", [])
        ]
        for d, dist in converted["distributions"].items()
    }


def test_a_linear_journey_becomes_one_entry():
    out, notes = convert_legacy_journeys(
        _deck(["d0", "cp", "exit_a"], [("d0", "cp"), ("cp", "exit_a")])
    )
    assert _routes(out) == {"d0": [(["cp", "exit_a"], 100.0)]}
    assert notes == []
    assert not {"journeys", "transitions", "waypoint_routing"} & set(out)


def test_allocation_stays_on_the_entry():
    out, _ = convert_legacy_journeys(
        _deck(["d0", "exit_a"], [("d0", "exit_a")], allocation="hard")
    )
    assert out["journeys_v2"][0]["allocation"] == "hard"


CP, CP1, CP2 = "jps-checkpoints_0", "jps-checkpoints_1", "jps-checkpoints_2"


def test_shares_become_one_entry_per_branch():
    routing = {
        CP: {
            "j": {
                "destinations": [
                    {"target": "exit_a", "percentage": 1},
                    {"target": "exit_b", "percentage": 99},
                ]
            }
        }
    }
    deck = _deck(
        ["d0", CP, "exit_a", "exit_b"],
        [("d0", CP), (CP, "exit_a"), (CP, "exit_b")],
        routing,
    )
    out, _ = convert_legacy_journeys(deck)
    assert _routes(out) == {"d0": [([CP, "exit_a"], 1.0), ([CP, "exit_b"], 99.0)]}


def test_a_branch_at_spawn_with_shares_is_cut_after_the_first_exit():
    split = {
        "destinations": [
            {"target": "exit_a", "percentage": 50},
            {"target": "exit_b", "percentage": 50},
        ]
    }
    routing = {CP1: {"j": split}, CP2: {"j": split}}
    pairs = [
        ("d0", CP1),
        ("d0", CP2),
        (CP1, "exit_a"),
        (CP1, "exit_b"),
        (CP2, "exit_a"),
        (CP2, "exit_b"),
    ]
    out, _ = convert_legacy_journeys(
        _deck(["d0", CP1, CP2, "exit_a", "exit_b"], pairs, routing)
    )
    assert _routes(out) == {
        "d0": [
            ([CP1, "exit_a"], 25.0),
            ([CP1, "exit_b"], 25.0),
            ([CP2, "exit_a"], 25.0),
            ([CP2, "exit_b"], 25.0),
        ]
    }


def test_a_patrol_loop_becomes_loop():
    pairs = [("d0", "c1"), ("c1", "c2"), ("c2", "c3"), ("c3", "c1")]
    out, _ = convert_legacy_journeys(_deck(["d0", "c1", "c2", "c3"], pairs))
    (entry,) = out["journeys_v2"]
    assert entry["sequence"] == ["c1", "c2", "c3"]
    assert entry["loop"] is True


def test_a_loop_into_the_middle_is_an_error():
    pairs = [("d0", "c1"), ("c1", "c2"), ("c2", "c3"), ("c3", "c2")]
    with pytest.raises(JourneyConversionError, match="j"):
        convert_legacy_journeys(_deck(["d0", "c1", "c2", "c3"], pairs))


def test_exit_choice_without_shares_writes_no_journey():
    pairs = [("d0", "exit_a"), ("d0", "exit_b"), ("d1", "exit_a"), ("d1", "exit_b")]
    out, notes = convert_legacy_journeys(
        _deck(["d0", "d1", "exit_a", "exit_b"], pairs, dists=("d0", "d1"))
    )
    assert out["journeys_v2"] == []
    assert _routes(out) == {"d0": [], "d1": []}
    assert [n.split(":")[0] for n in notes] == ["d0", "d1"]


def test_a_file_without_old_journeys_keeps_its_journeys_v2():
    raw = {
        "distributions": {},
        "journeys": [],
        "transitions": [],
        "journeys_v2": [{"id": "x", "sequence": ["exit_a"]}],
    }
    out, notes = convert_legacy_journeys(raw)
    assert out["journeys_v2"] == raw["journeys_v2"]
    assert "journeys" not in out and "transitions" not in out
    assert notes == []


def test_the_command_writes_the_file_and_prints_the_notes(tmp_path, capsys):
    pairs = [("d0", "exit_a"), ("d0", "exit_b")]
    src, dst = tmp_path / "old.json", tmp_path / "new.json"
    src.write_text(
        json.dumps(_deck(["d0", "exit_a", "exit_b"], pairs)), encoding="utf-8"
    )
    assert main([str(src), "-o", str(dst)]) == 0
    assert json.loads(dst.read_text(encoding="utf-8"))["journeys_v2"] == []
    assert capsys.readouterr().out.startswith("d0:")
