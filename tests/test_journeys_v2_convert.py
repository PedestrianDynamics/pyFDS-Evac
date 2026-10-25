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
    with pytest.raises(JourneyConversionError, match="journey j returns to c2"):
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


def _dest(*shares):
    return {
        "destinations": [{"target": t, "percentage": p} for t, p in shares],
    }


def _agents_per_route(weights, count):
    """The split of `_create_journeys_with_percentages`: rounded shares, the
    last route takes the rest."""
    total = sum(weights)
    left, split = count, []
    for weight in weights[:-1]:
        taken = min(round(count * weight / total), left)
        split.append(taken)
        left -= taken
    return [*split, left]


def _shared_deck(shares, count_of_doors=1):
    doors = [f"jps-checkpoints_{n}" for n in range(count_of_doors)]
    routing = {door: {"j": _dest(*shares)} for door in doors}
    pairs = [("d0", door) for door in doors]
    pairs += [(door, target) for door in doors for target, _ in shares]
    stages = ["d0", *doors, *(target for target, _ in shares)]
    return _deck(stages, pairs, routing)


@pytest.mark.parametrize(
    ("shares", "doors", "count"),
    [
        ((("exit_a", 1), ("exit_b", 5)), 1, 15),
        ((("exit_a", 50), ("exit_b", 50)), 3, 15),
        ((("exit_a", 1), ("exit_b", 99)), 3, 40),
    ],
)
def test_the_agent_split_is_the_same_after_conversion(shares, doors, count):
    deck = _shared_deck(shares, doors)
    old = [pct for _ in range(doors) for _, pct in shares]
    out, _ = convert_legacy_journeys(deck)
    new = [weight for _, weight in _routes(out)["d0"]]
    assert _agents_per_route(new, count) == _agents_per_route(old, count)


def test_weights_stay_as_written_when_scaling_is_not_exact():
    out, _ = convert_legacy_journeys(_shared_deck((("exit_a", 1), ("exit_b", 5))))
    assert [w for _, w in _routes(out)["d0"]] == [1.0, 5.0]


def test_a_start_area_with_a_choice_and_a_route_is_an_error():
    deck = _deck(["d0", "exit_a", "exit_b"], [("d0", "exit_a"), ("d0", "exit_b")])
    deck["journeys"].append({"id": "k", "stages": ["d0", "exit_a"]})
    deck["transitions"].append({"from": "d0", "to": "exit_a", "journey_id": "k"})
    with pytest.raises(JourneyConversionError, match=r"d0.*\bj\b.*\bk\b"):
        convert_legacy_journeys(deck)


def test_shares_totalling_zero_are_an_error():
    deck = _shared_deck((("exit_a", 0), ("exit_b", 0)))
    with pytest.raises(JourneyConversionError, match="d0.*total 0"):
        convert_legacy_journeys(deck)


def test_exit_choice_is_decided_per_start_area():
    deck = _deck(
        ["d0", "d1", "c1", "exit_a", "exit_b"],
        [("d0", "exit_a"), ("d1", "c1"), ("c1", "exit_a"), ("c1", "exit_b")],
        dists=("d0", "d1"),
    )
    out, notes = convert_legacy_journeys(deck)
    assert _routes(out) == {"d0": [(["exit_a"], 100.0)], "d1": []}
    assert [n.split(":")[0] for n in notes] == ["d1"]


def test_stale_journey_weights_are_dropped():
    deck = _deck(["d0", "exit_a", "exit_b"], [("d0", "exit_a"), ("d0", "exit_b")])
    deck["distributions"]["d0"]["journey_weights"] = [{"journey_id": "x", "weight": 1}]
    out, _ = convert_legacy_journeys(deck)
    assert "journey_weights" not in out["distributions"]["d0"]


def test_a_file_with_both_formats_is_an_error():
    deck = _deck(["d0", "exit_a"], [("d0", "exit_a")])
    deck["journeys_v2"] = [{"id": "x", "sequence": ["exit_a"]}]
    with pytest.raises(JourneyConversionError, match="journeys and journeys_v2"):
        convert_legacy_journeys(deck)


def test_a_loop_over_one_stage_is_an_error():
    deck = _deck(["d0", "c1"], [("d0", "c1"), ("c1", "c1")])
    with pytest.raises(JourneyConversionError, match="journey j loops over a single"):
        convert_legacy_journeys(deck)


def test_a_loop_back_from_an_exit_is_an_error():
    deck = _deck(
        ["d0", "c1", "exit_a"], [("d0", "c1"), ("c1", "exit_a"), ("exit_a", "c1")]
    )
    with pytest.raises(JourneyConversionError, match="journey j loops back from"):
        convert_legacy_journeys(deck)


def test_a_taken_id_is_skipped_for_the_second_route():
    deck = _shared_deck((("exit_a", 1), ("exit_b", 99)))
    deck["distributions"]["d1"] = {"parameters": {}}
    deck["journeys"].insert(0, {"id": "j_1", "stages": ["d1", "exit_a"]})
    deck["transitions"].append({"from": "d1", "to": "exit_a", "journey_id": "j_1"})
    out, _ = convert_legacy_journeys(deck)
    assert [j["id"] for j in out["journeys_v2"]] == ["j_1", "j", "j_2"]


def test_the_command_reports_an_error_and_writes_nothing(tmp_path, capsys):
    src, dst = tmp_path / "old.json", tmp_path / "new.json"
    deck = _deck(["d0", "c1", "c2"], [("d0", "c1"), ("c1", "c2"), ("c2", "c2")])
    src.write_text(json.dumps(deck), encoding="utf-8")
    assert main([str(src), "-o", str(dst)]) == 1
    assert capsys.readouterr().err.startswith("error: journey j")
    assert not dst.exists()


def test_the_command_reports_a_missing_or_invalid_input(tmp_path, capsys):
    dst = tmp_path / "new.json"
    assert main([str(tmp_path / "missing.json"), "-o", str(dst)]) == 1
    bad = tmp_path / "bad.json"
    bad.write_text("{", encoding="utf-8")
    assert main([str(bad), "-o", str(dst)]) == 1
    assert capsys.readouterr().err.count("error:") == 2
    assert not dst.exists()
