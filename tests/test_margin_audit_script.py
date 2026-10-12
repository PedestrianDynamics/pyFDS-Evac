"""The margin-audit harness decides as the stage-2 plan says (#187).

``scripts/margin_audit.py`` runs the paired base/off arms of a routing
margin and applies a paired permutation test, the plan's floors and its
outcome rule. These tests check the arithmetic on hand-checkable cases and
the metrics on a synthetic run folder; nothing here needs sciebo.
"""

from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "margin_audit.py"


@pytest.fixture(scope="module")
def audit():
    spec = importlib.util.spec_from_file_location("margin_audit", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
        yield module
    finally:
        sys.modules.pop(spec.name, None)


# ── Permutation test ──────────────────────────────────────────────────


def test_exact_p_of_six_equal_differences_is_two_over_64(audit):
    p, method = audit.paired_permutation_p([1.0] * 6)
    assert method == "exact"
    assert p == pytest.approx(2 / 64)


def test_exact_p_by_hand_for_three_differences(audit):
    # Signed sums of (3, 1, 2): 6, 4, 2, 0, 0, -2, -4, -6; |sum| >= 4 in 4 of 8.
    p, _ = audit.paired_permutation_p([3.0, -1.0, 2.0])
    assert p == pytest.approx(0.5)


def test_zero_differences_stay_in_and_give_p_one(audit):
    assert audit.paired_permutation_p([0.0, 0.0, 0.0])[0] == 1.0
    # Three binding seeds of ten: the zeros make the test conservative.
    p_three, _ = audit.paired_permutation_p([1.0, 1.0, 1.0])
    p_ten, _ = audit.paired_permutation_p([1.0, 1.0, 1.0] + [0.0] * 7)
    assert p_three == pytest.approx(0.25)
    assert p_ten == pytest.approx(0.25)


def test_p_is_two_sided(audit):
    d = [2.0, 1.5, 3.0, 0.5, 1.0, 2.5]
    assert (
        audit.paired_permutation_p(d)[0]
        == audit.paired_permutation_p([-x for x in d])[0]
    )


def test_monte_carlo_above_twenty_seeds_is_fixed_and_close_to_exact(audit):
    d = [1.0, -0.5, 2.0, 1.5, 0.0, -1.0, 2.5, 1.0, 0.5, 3.0, 1.0] * 2
    assert len(d) == 22
    p_mc, method = audit.paired_permutation_p(d, draws=20_000, mc_seed=1)
    assert method == "monte-carlo"
    assert p_mc == audit.paired_permutation_p(d, draws=20_000, mc_seed=1)[0]
    p_exact, _ = audit.paired_permutation_p(d, exact_max_n=22)
    assert p_mc == pytest.approx(p_exact, abs=0.005)


def test_no_differences_is_an_error(audit):
    with pytest.raises(ValueError, match="no differences"):
        audit.paired_permutation_p([])


def test_smallest_p_matches_the_plan(audit):
    assert audit.smallest_p(5) == pytest.approx(0.0625)
    assert audit.smallest_p(10) == pytest.approx(0.002, abs=5e-5)


# ── Floors and the outcome rule ───────────────────────────────────────


@pytest.mark.parametrize(
    "metric, base, agents, floor",
    [
        ("returns", 4.0, 100.0, 2.0),
        ("returns", 20.0, 100.0, 5.0),
        ("returns", 1.0, 40.0, 0.8),
        ("switches_per_agent", 0.1, 100.0, 0.05),
        ("switches_per_agent:fallback", 1.0, 100.0, 0.25),
        ("exit_share:A", 0.5, 100.0, 0.05),
        ("fed_p95", 0.2, 100.0, 0.05),
        ("rset_last", 100.0, 100.0, 3.0),
        ("rset_p95", 200.0, 100.0, 4.0),
    ],
)
def test_floor_follows_the_plan_table(audit, metric, base, agents, floor):
    assert audit._floor_rule(metric).floor(base, agents) == pytest.approx(floor)


def test_reported_only_metrics_have_no_floor(audit):
    assert audit._floor_rule("fed_median") is None
    assert audit._floor_rule("n_agents") is None
    assert audit._floor_rule("exit_share:A").worse == 0


def _pairs(base: list[float], off: list[float], metric: str = "returns") -> dict:
    return {
        seed: {
            "base": {metric: b, "n_agents": 100},
            "off": {metric: o, "n_agents": 100},
        }
        for seed, (b, o) in enumerate(zip(base, off), start=1)
    }


def test_judge_finds_a_distinct_worse_effect(audit):
    result = audit.judge("returns", _pairs([2.0] * 6, [6.0] * 6))
    assert result["n"] == 6
    assert result["effect"] == pytest.approx(4.0)
    assert result["p"] == pytest.approx(2 / 64)
    assert result["floor"] == pytest.approx(2.0)
    assert result["distinct"] is True
    assert result["worse"] is True


def test_judge_effect_below_the_floor_is_not_distinct(audit):
    # p = 2/64 but |mean d| = 1 < max(2, 0.5).
    result = audit.judge("returns", _pairs([2.0] * 6, [3.0] * 6))
    assert result["p"] < audit.ALPHA
    assert result["distinct"] is False


def test_judge_a_fall_is_better(audit):
    result = audit.judge("returns", _pairs([8.0] * 6, [2.0] * 6))
    assert result["distinct"] is True
    assert result["worse"] is False


def test_judge_needs_six_seeds(audit):
    result = audit.judge("returns", _pairs([2.0] * 5, [6.0] * 5))
    assert result["p"] == pytest.approx(2 / 32)
    assert result["distinct"] is False


def test_judge_fed_ge_1_counts_the_seeds_that_changed(audit):
    # One changed seed of eight: every sign flip reaches |sum d|, p = 1.
    one = _pairs([0.0] * 8, [3.0] + [0.0] * 7, metric="fed_ge_1")
    result = audit.judge("fed_ge_1", one)
    assert result["changed_seeds"] == 1
    assert result["p"] == 1.0
    assert result["distinct"] is False
    seven = _pairs([0.0] * 8, [3.0] * 7 + [0.0], metric="fed_ge_1")
    result = audit.judge("fed_ge_1", seven)
    assert result["changed_seeds"] == 7
    assert result["floor"] == 2.0
    assert result["p"] == pytest.approx(2 / 128)
    assert result["distinct"] is True


def test_judge_treats_an_unused_exit_as_share_zero(audit):
    pairs = _pairs([0.4] * 6, [0.5] * 6, metric="exit_share:A")
    for pair in pairs.values():
        del pair["base"]["exit_share:A"]
    result = audit.judge("exit_share:A", pairs)
    assert result["n"] == 6
    assert result["effect"] == pytest.approx(0.5)


def test_judge_reports_an_absent_metric(audit):
    assert audit.judge("fed_p95", _pairs([1.0] * 6, [1.0] * 6))["n"] == 0


def test_outcome_rule(audit):
    primary = {"n": 10, "distinct": False, "worse": None}
    assert audit.outcome(primary, []).startswith("remove: no distinct")
    primary = {"n": 10, "distinct": True, "worse": True}
    assert audit.outcome(primary, []).startswith("keep")
    primary = {"n": 10, "distinct": True, "worse": False}
    assert audit.outcome(primary, []).startswith("remove: distinct")
    harmed = [{"metric": "rset_last", "distinct": True, "worse": True}]
    assert audit.outcome(primary, harmed).startswith("maintainer")
    fine = [{"metric": "rset_last", "distinct": True, "worse": False}]
    assert audit.outcome(primary, fine).startswith("remove: distinct")
    assert audit.outcome({"n": 5, "distinct": True, "worse": True}, []).startswith(
        "undecided"
    )


# ── Metrics ───────────────────────────────────────────────────────────


def _row(time_s, agent, old, new, reason="smoke_reroute"):
    return {
        "time_s": str(time_s),
        "agent_id": str(agent),
        "old_exit": old,
        "new_exit": new,
        "reason": reason,
    }


ROUTE_HISTORY = [
    _row(0, 1, "", "A", "initial"),
    _row(0, 2, "", "A", "initial"),
    _row(10, 1, "A", "B"),
    _row(12, 1, "B", "B", "better_path"),
    _row(15, 1, "B", "A"),
    _row(40, 1, "A", "B", "fallback"),
    _row(10, 2, "A", "B"),
]


def test_returns_follow_the_124_definition(audit):
    found = audit.returns(ROUTE_HISTORY)
    assert [(r["agent_id"], r["time_s"], r["since_s"]) for r in found] == [
        ("1", "15", 5.0),
        ("1", "40", 25.0),
    ]
    assert len(audit.switch_rows(ROUTE_HISTORY)) == 5
    assert len(audit.exit_switches(ROUTE_HISTORY)) == 4


def test_route_metrics_count_switches_by_reason(audit):
    metrics = audit._route_metrics(ROUTE_HISTORY, n_agents=2)
    assert metrics["switches"] == 5
    assert metrics["switches_per_agent"] == 2.5
    assert metrics["switches:fallback"] == 1
    assert metrics["switches:better_path"] == 1
    assert metrics["switches:fed_reroute"] == 0
    assert metrics["switches_per_agent:smoke_reroute"] == 1.5
    assert metrics["returns"] == 2
    assert metrics["returns_agents"] == 1
    assert metrics["returns_within_window"] == 1
    assert metrics["returns_since_s_median"] == 15.0


def test_override_routing_sets_the_key_and_keeps_the_rest(audit):
    config = {"routing": {"w_smoke": 5.0}, "exits": {}}
    copy = audit.override_routing(config, "tau_deadband", 0.0)
    assert copy["routing"] == {"w_smoke": 5.0, "tau_deadband": 0.0}
    assert config["routing"] == {"w_smoke": 5.0}
    assert audit.override_routing({}, "tau_deadband", 0.0)["routing"] == {
        "tau_deadband": 0.0
    }


def test_manifest_margin_reads_the_value_the_run_used(audit):
    def manifest(rerouting):
        return {"configuration": {"run": {"rerouting": rerouting}}}

    cost = manifest({"exit_switch_anchor": 0.9, "cost_config": {"tau_deadband": 0.0}})
    assert audit.manifest_margin(cost, "tau_deadband") == 0.0
    assert audit.manifest_margin(cost, "exit_switch_anchor") == 0.9
    assert audit.manifest_margin(cost, "w_smoke") is None
    with pytest.raises(ValueError, match="no rerouting"):
        audit.manifest_margin(manifest(None), "tau_deadband")
    with pytest.raises(ValueError, match="configuration.run.rerouting"):
        audit.manifest_margin({}, "tau_deadband")


def _write_run(folder: Path, fed: bool = True, remaining: int | None = 0) -> None:
    folder.mkdir(parents=True)
    with sqlite3.connect(folder / "trajectory.sqlite") as con:
        con.execute("CREATE TABLE metadata(key TEXT, value TEXT)")
        con.execute("INSERT INTO metadata VALUES ('fps', '10')")
        con.execute("CREATE TABLE trajectory_data(frame INTEGER, id INTEGER)")
        con.executemany(
            "INSERT INTO trajectory_data VALUES (?, ?)",
            [(f, 1) for f in range(0, 101)] + [(f, 2) for f in range(0, 301)],
        )
        if fed:
            con.execute(
                "CREATE TABLE agent_scalars(frame INTEGER, id INTEGER, fed REAL)"
            )
            con.executemany(
                "INSERT INTO agent_scalars VALUES (?, ?, ?)",
                [(0, 1, 0.0), (100, 1, 0.4), (0, 2, 0.0), (300, 2, 1.2)],
            )
    with (folder / "route_history.csv").open("w", newline="") as handle:
        handle.write("time_s,agent_id,old_exit,new_exit,old_cost,new_cost,reason\n")
        handle.write("0,1,,A,0,0,initial\n10,1,A,B,1,2,smoke_reroute\n")
    with (folder / "exit_history.csv").open("w", newline="") as handle:
        handle.write("agent_id,origin,spawn_index,exit_id,exit_in_map\n")
        handle.write("1,o,0,B,True\n2,o,1,A,True\n")
    if remaining is not None:
        (folder / "trajectory.manifest.json").write_text(
            json.dumps({"outcome": {"agents_remaining": remaining}})
        )


def test_run_metrics_from_a_synthetic_run(audit, tmp_path):
    _write_run(tmp_path / "run")
    metrics = audit.run_metrics(tmp_path / "run")
    assert metrics["n_agents"] == 2
    assert metrics["rset_last"] == pytest.approx(30.0)
    assert metrics["rset_p95"] == pytest.approx(29.0)
    assert metrics["censored"] == 0
    assert metrics["fed_max"] == pytest.approx(1.2)
    assert metrics["fed_median"] == pytest.approx(0.8)
    assert metrics["fed_ge_0_3"] == 2
    assert metrics["fed_ge_1"] == 1
    assert metrics["exit_share:A"] == 0.5
    assert metrics["exit_share:B"] == 0.5
    assert metrics["switches"] == 1
    assert metrics["returns"] == 0


def test_run_metrics_without_fed_or_manifest(audit, tmp_path):
    _write_run(tmp_path / "run", fed=False, remaining=None)
    metrics = audit.run_metrics(tmp_path / "run")
    assert metrics["fed_p95"] is None
    assert metrics["fed_ge_1"] is None
    # Agent 2 is still in at the last frame: censored by the frame rule.
    assert metrics["censored"] == 1


# ── Report ────────────────────────────────────────────────────────────


def _write_audit(folder: Path, base: list[float], off: list[float]) -> None:
    folder.mkdir()
    (folder / "manifest.json").write_text(
        json.dumps(
            {
                "margin": "fallback_return_lockout_s",
                "off_value": 0.0,
                "commit": "c" * 40,
                "dirty": [],
            }
        )
    )
    for seed, (b, o) in enumerate(zip(base, off), start=1):
        for arm, value in (("base", b), ("off", o)):
            run = folder / "l_corridor_gate" / f"seed{seed}" / arm
            run.mkdir(parents=True)
            (run / "metrics.json").write_text(
                json.dumps(
                    {
                        "returns": value,
                        "n_agents": 100,
                        "rset_last": 120.0,
                        "wall_s": 1.0,
                        "margin_value": 0.0 if arm == "off" else 10.0,
                    }
                )
            )


def test_analyse_writes_the_report_with_the_outcome(audit, tmp_path, capsys):
    folder = tmp_path / "audit"
    _write_audit(folder, [2.0] * 6, [6.0] * 6)
    code = audit.main(["analyse", str(folder), "--primary-deck", "l_corridor_gate"])
    assert code == 0
    report = json.loads((folder / "report.json").read_text())
    assert report["primary_metric"] == "returns"
    assert report["primary"]["p"] == pytest.approx(2 / 64)
    assert report["primary"]["effect"] == pytest.approx(4.0)
    assert report["primary"]["floor"] == pytest.approx(2.0)
    assert report["outcome"].startswith("keep")
    text = (folder / "report.md").read_text()
    assert "**Outcome: keep" in text
    assert "| returns | 6 | 2 | 6 | 4 | 0.0312 | 2 | True |" in text
    assert "Primary deck: l_corridor_gate" in capsys.readouterr().out


def test_analyse_refuses_an_unknown_primary_deck(audit, tmp_path):
    folder = tmp_path / "audit"
    _write_audit(folder, [2.0] * 6, [2.0] * 6)
    assert audit.main(["analyse", str(folder), "--primary-deck", "world77"]) == 2


def test_analyse_needs_a_metric_for_a_margin_without_a_primary(audit, tmp_path):
    folder = tmp_path / "audit"
    _write_audit(folder, [2.0] * 6, [2.0] * 6)
    manifest = json.loads((folder / "manifest.json").read_text())
    manifest["margin"] = "clean_exit_margin"
    (folder / "manifest.json").write_text(json.dumps(manifest))
    assert (
        audit.main(["analyse", str(folder), "--primary-deck", "l_corridor_gate"]) == 2
    )
    code = audit.main(
        [
            "analyse",
            str(folder),
            "--primary-deck",
            "l_corridor_gate",
            "--metric",
            "returns",
        ]
    )
    assert code == 0


def test_run_refuses_an_unknown_margin_without_an_off_value(audit, capsys):
    code = audit.main(["run", "--margin", "w_smoke", "--decks", "l_corridor_gate"])
    assert code == 2
    assert "pass --off" in capsys.readouterr().out


def test_every_audited_margin_has_a_plan_off_value(audit):
    assert audit.MARGINS["fallback_return_lockout_s"].off == 0.0
    assert audit.MARGINS["tau_deadband"].off == 0.0
    assert audit.MARGINS["fallback_switch_margin"].off == 0.0
    for name in ("fed_return_margin", "path_switch_anchor", "tau_return_margin"):
        assert audit.MARGINS[name].off == 1.0
