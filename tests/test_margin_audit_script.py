"""The margin-audit harness decides as the stage-2 plan says (#187).

``scripts/margin_audit.py`` runs the paired base/off arms of a routing
margin and applies a paired permutation test, the plan's floors and its
outcome rule. These tests check the arithmetic on hand-checkable cases and
the metrics on a synthetic run folder; nothing here needs sciebo.
"""

from __future__ import annotations

import importlib.util
import json
import os
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


def test_exact_enumeration_holds_up_to_twenty_seeds(audit):
    # "exact up to 20 seeds, else Monte-Carlo": 20 equal differences give
    # p = 2 / 2^20 by enumeration; 21 are sampled.
    p, method = audit.paired_permutation_p([1.0] * 20)
    assert (p, method) == (2 / 2**20, "exact")
    assert audit.paired_permutation_p([1.0] * 21)[1] == "monte-carlo"


def test_a_tie_in_floating_point_counts_as_a_tie(audit):
    # All sign patterns but the two all-same ones sum to less than
    # sum(d) = 1.99 (any flipped entry lowers it by twice its size), so
    # p = 2/64. The sums are computed in different orders and differ in the
    # last bits; without a tolerance the observed assignment would not count
    # itself and p would be 0.
    p, _ = audit.paired_permutation_p([0.41, 0.18, 0.2, 0.3, 0.5, 0.4])
    assert p == pytest.approx(2 / 64)


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
        ("walk_mean", 20.0, 100.0, 1.0),
        ("walk_mean", 100.0, 100.0, 2.0),
    ],
)
def test_floor_follows_the_plan_table(audit, metric, base, agents, floor):
    assert audit._floor_rule(metric).floor(base, agents) == pytest.approx(floor)


def test_reported_only_metrics_have_no_floor(audit):
    assert audit._floor_rule("fed_median") is None
    assert audit._floor_rule("returns_agents") is None
    assert audit._floor_rule("returns_since_s_median") is None
    assert audit._floor_rule("returns_within_window").worse == 1
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


def test_judge_effect_equal_to_the_floor_is_distinct(audit):
    # "|mean d| at least the metric's floor": floor max(2, 0.5) = 2, effect 2.
    result = audit.judge("returns", _pairs([2.0] * 6, [4.0] * 6))
    assert result["floor"] == pytest.approx(2.0)
    assert result["effect"] == pytest.approx(2.0)
    assert result["distinct"] is True


def test_judge_p_between_five_and_ten_percent_is_not_distinct(audit):
    # d = 0.3 five times and -0.1 once: the sign flips reaching |sum d| = 1.4
    # are the all-same-sign patterns (2) and the one with -0.1 flipped alone
    # (2): p = 4/64 = 0.0625. The effect, 0.233, is above the floor 0.05.
    result = audit.judge("fed_p95", _pairs([0.0] * 6, [0.3] * 5 + [-0.1], "fed_p95"))
    assert result["p"] == pytest.approx(4 / 64)
    assert result["effect"] > result["floor"]
    assert result["distinct"] is False


def test_judge_walk_mean_is_judged_against_its_floor(audit):
    # Base 20 s: floor max(0.4, 1.0) = 1.0 s; a 0.8 s rise is below it.
    below = audit.judge("walk_mean", _pairs([20.0] * 6, [20.8] * 6, "walk_mean"))
    assert below["floor"] == pytest.approx(1.0)
    assert below["distinct"] is False
    above = audit.judge("walk_mean", _pairs([20.0] * 6, [21.0] * 6, "walk_mean"))
    assert above["distinct"] is True


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


def test_a_return_counts_in_the_window_up_to_ten_seconds(audit):
    # "returns_within_window": the 10 s of the removed return lockout.
    rows = [
        _row(0, 1, "A", "B"),
        _row(9.9, 1, "B", "A"),
        _row(0, 2, "A", "B"),
        _row(10.1, 2, "B", "A"),
    ]
    metrics = audit._route_metrics(rows, n_agents=2)
    assert metrics["returns"] == 2
    assert metrics["returns_within_window"] == 1


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
    assert metrics["walk_mean"] == pytest.approx(20.0)
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
                "margin": "tau_deadband",
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
            "returns_within_window",
        ]
    )
    assert code == 0


def test_runs_fix_the_str_hash_seed(audit):
    assert audit.run_env()["PYTHONHASHSEED"] == "0"
    assert set(os.environ) - {"PYTHONHASHSEED"} <= set(audit.run_env())


# ── Clear-air identity (C10) ──────────────────────────────────────────


def _write_arm(folder: Path, geometry_hash: int, frame_x: float = 1.0) -> None:
    """A clear-air run whose trajectory carries JuPedSim's geometry hash."""
    _write_run(folder, fed=False)
    with sqlite3.connect(folder / "trajectory.sqlite") as con:
        con.execute("CREATE TABLE geometry(hash INTEGER, wkt TEXT)")
        con.execute("INSERT INTO geometry VALUES (?, ?)", (geometry_hash, "POLYGON"))
        con.execute(
            "CREATE TABLE frame_data(frame INTEGER, geometry_hash INTEGER, x REAL)"
        )
        con.execute(
            "INSERT INTO frame_data VALUES (?, ?, ?)", (0, geometry_hash, frame_x)
        )


def test_clear_air_compare_ignores_the_geometry_hash(audit, tmp_path):
    _write_arm(tmp_path / "base", geometry_hash=11)
    _write_arm(tmp_path / "off", geometry_hash=22)
    assert audit.run_differences(tmp_path / "base", tmp_path / "off") == []


def test_clear_air_compare_names_the_table_and_file_that_differ(audit, tmp_path):
    _write_arm(tmp_path / "base", geometry_hash=11)
    _write_arm(tmp_path / "off", geometry_hash=11, frame_x=2.0)
    with (tmp_path / "off" / "exit_history.csv").open("a") as handle:
        handle.write("3,o,2,A,True\n")
    assert audit.run_differences(tmp_path / "base", tmp_path / "off") == [
        "exit_history.csv",
        "trajectory.sqlite:frame_data",
    ]


def test_analyse_reports_the_clear_air_gate(audit, tmp_path, capsys):
    folder = tmp_path / "audit"
    folder.mkdir()
    (folder / "manifest.json").write_text(
        json.dumps(
            {
                "margin": "tau_deadband",
                "off_value": 0.0,
                "commit": "c" * 40,
                "dirty": [],
            }
        )
    )
    for seed in range(1, 8):
        run = folder / "familiarity_test_full" / f"seed{seed}"
        _write_arm(run / "base", geometry_hash=seed)
        _write_arm(run / "off", geometry_hash=-seed, frame_x=2.0 if seed == 3 else 1.0)
        for arm in ("base", "off"):
            metrics = audit.run_metrics(run / arm)
            (run / arm / "metrics.json").write_text(json.dumps(metrics))
    code = audit.main(
        ["analyse", str(folder), "--primary-deck", "familiarity_test_full"]
    )
    assert code == 0
    report = json.loads((folder / "report.json").read_text())
    identity = report["decks"]["familiarity_test_full"]["clear_air"]
    assert identity == {
        "seeds": 7,
        "differing": {"3": ["trajectory.sqlite:frame_data"]},
    }
    text = (folder / "report.md").read_text()
    assert (
        "**Clear air: base and off differ on 1 of 7 seeds** (seed 3: trajectory.sqlite:frame_data)."
        in text
    )


def test_clear_air_gate_only_for_decks_without_fds(audit, tmp_path):
    assert audit.clear_air_identity(tmp_path, "l_corridor_gate") is None
    assert audit.clear_air_identity(tmp_path, "unknown_deck") is None


def test_run_refuses_an_unknown_margin_without_an_off_value(audit, capsys):
    code = audit.main(["run", "--margin", "w_smoke", "--decks", "l_corridor_gate"])
    assert code == 2
    assert "pass --off" in capsys.readouterr().out


def test_every_audited_margin_has_a_plan_off_value(audit):
    assert "fallback_return_lockout_s" not in audit.MARGINS  # removed, #187 A1
    assert audit.MARGINS["tau_deadband"].off == 0.0
    assert audit.MARGINS["fallback_switch_margin"].off == 0.0
    assert "fed_return_margin" not in audit.MARGINS  # removed, #187 A2
    assert "path_switch_anchor" not in audit.MARGINS  # removed, #187 A3
    assert "tau_return_margin" not in audit.MARGINS  # removed, #187 A5


# ── Arms: code and config overrides (#187 H1) ─────────────────────────


def test_parse_override_reads_json_inf_and_bare_routing_keys(audit):
    assert audit.parse_override("tau_deadband=0.5") == ("routing.tau_deadband", 0.5)
    key = "routing.fallback_switch_margin"
    assert audit.parse_override(f"{key}=inf") == (key, float("inf"))
    assert audit.parse_override('routing.cost_model="additive"') == (
        "routing.cost_model",
        "additive",
    )
    path = "config.simulation_settings.simulationParams.max_simulation_time"
    assert audit.parse_override(f"{path}=480") == (path, 480)


@pytest.mark.parametrize("text", ["tau_deadband", "=1", "tau_deadband=high"])
def test_parse_override_rejects_malformed_text(audit, text):
    with pytest.raises(ValueError, match="override"):
        audit.parse_override(text)


def test_set_config_path_sets_a_copy_and_keeps_the_rest(audit):
    config = {"routing": {"w_smoke": 5.0}, "config": {"a": {"b": 1}}}
    copy = audit.set_config_path(config, "config.a.b", 2)
    assert copy["config"]["a"]["b"] == 2
    assert config["config"]["a"]["b"] == 1
    new = audit.set_config_path({}, "routing.tau_deadband", 0.0)
    assert new == {"routing": {"tau_deadband": 0.0}}


def test_set_config_path_refuses_a_path_the_config_does_not_have(audit):
    config = {"config": {"a": {"b": 1}}}
    with pytest.raises(ValueError, match="no object at 'config.x'"):
        audit.set_config_path(config, "config.x.b", 2)
    with pytest.raises(ValueError, match="no key 'c'"):
        audit.set_config_path(config, "config.a.c", 2)


SIM_TIME = "config.simulation_settings.simulationParams.max_simulation_time"


def _sim_time(staged: Path) -> int:
    config = json.loads((staged / "config.json").read_text())
    return config["config"]["simulation_settings"]["simulationParams"][
        "max_simulation_time"
    ]


def test_schroeder_decks_run_to_their_fds_end_in_both_arms(audit, tmp_path):
    deck = audit.DECKS["a047_pvc_h40"]
    assert deck.fds_dir == "schroeder2015-route/rerun_796/a047_pvc_h40"
    assert audit.DECKS["a047_pvc_h35"].fds_dir.endswith("a047_pvc_h35")
    assert deck.seeds == tuple(range(1, 11))
    key = "routing.fallback_switch_margin"
    arm = ((key, 0.0),)
    staged = audit._stage_scenario(deck, tmp_path, tmp_path / "s", arm)
    config = json.loads((staged / "config.json").read_text())
    assert _sim_time(staged) == 480
    assert config["routing"]["fallback_switch_margin"] == 0.0
    assert config["routing"]["cost_model"] == "additive"


def test_a_later_override_wins_over_the_deck_override(audit, tmp_path):
    deck = audit.DECKS["a047_pvc_h40"]
    staged = audit._stage_scenario(deck, tmp_path, tmp_path / "s", ((SIM_TIME, 300),))
    assert _sim_time(staged) == 300


def test_unapplied_overrides_name_the_numeric_routing_values_not_reported(audit):
    def manifest(cost):
        return {"configuration": {"run": {"rerouting": {"cost_config": cost}}}}

    key = "routing.fallback_switch_margin"
    seen = manifest({"fallback_switch_margin": 0.0})
    assert audit.unapplied_overrides(seen, ((key, 0.0),)) == []
    missed = manifest({"fallback_switch_margin": 0.2})
    (message,) = audit.unapplied_overrides(missed, ((key, 0.0),))
    assert "fallback_switch_margin=0.2" in message
    # Strings and paths outside routing are not in the run manifest.
    other = (("routing.cost_model", "additive"), ("config.a.b", 1))
    assert audit.unapplied_overrides(manifest({}), other) == []


def _args(audit, argv):
    parser = audit._build_parser()
    return parser.parse_args(["run", "--decks", "l_corridor_gate", *argv])


def test_arms_of_a_margin_sweep_are_this_tree_with_the_key_off(audit):
    label, arms = audit.build_arms(_args(audit, ["--margin", "tau_deadband"]))
    assert label == "tau_deadband"
    assert arms["base"] == audit.Arm(None, ())
    assert arms["off"] == audit.Arm(None, (("routing.tau_deadband", 0.0),))


def test_arms_of_a_code_audit_are_two_commits_with_their_overrides(audit):
    args = _args(
        audit,
        [
            "--base-commit",
            "HEAD",
            "--head-commit",
            "HEAD",
            "--base-set",
            "w_smoke=1",
            "--head-set",
            "w_smoke=2",
            "--head-set",
            "tau_deadband=0",
        ],
    )
    label, arms = audit.build_arms(args)
    assert label == "arms"
    assert len(arms["base"].commit) == 40
    assert arms["base"].commit == arms["off"].commit
    assert arms["base"].overrides == (("routing.w_smoke", 1),)
    assert arms["off"].overrides == (
        ("routing.w_smoke", 2),
        ("routing.tau_deadband", 0),
    )
    assert arms["off"].describe()["overrides"] == {
        "routing.w_smoke": 2,
        "routing.tau_deadband": 0,
    }


def test_an_unknown_commit_is_named(audit, capsys):
    code = audit.main(
        ["run", "--decks", "l_corridor_gate", "--base-commit", "no-such-ref-187"]
    )
    assert code == 2
    assert "unknown commit 'no-such-ref-187'" in capsys.readouterr().out


def test_run_needs_a_margin_or_an_arm_option(audit, capsys):
    assert audit.main(["run", "--decks", "l_corridor_gate"]) == 2
    assert "pass --margin or an arm option" in capsys.readouterr().out


def test_default_folder_names_the_commits_and_tells_overrides_apart(audit, tmp_path):
    arms = {"base": audit.Arm("a" * 40), "off": audit.Arm("b" * 40)}
    path = audit.default_out(tmp_path, "arms", arms)
    assert path.name.startswith("arms_aaaaaaaa_bbbbbbbb_")
    other = {"base": arms["base"], "off": audit.Arm("b" * 40, (("x.y", 1),))}
    assert audit.default_out(tmp_path, "arms", other) != path


def test_rerun_into_a_folder_of_other_arms_is_refused(audit, tmp_path):
    arms = {"base": audit.Arm("a" * 40), "off": audit.Arm("b" * 40)}
    assert audit._arms_clash(tmp_path, arms) is None
    held = {k: a.describe() for k, a in arms.items()}
    (tmp_path / "manifest.json").write_text(json.dumps({"arms": held}))
    assert audit._arms_clash(tmp_path, arms) is None
    moved = {"base": arms["base"], "off": audit.Arm("c" * 40)}
    assert "other arms" in audit._arms_clash(tmp_path, moved)
    # A folder from before the arm options holds no record to compare.
    (tmp_path / "manifest.json").write_text(json.dumps({"margin": "tau_deadband"}))
    assert audit._arms_clash(tmp_path, moved) is None


def test_a_run_uses_the_interpreter_and_checkout_of_its_arm(audit, tmp_path):
    tree = audit.CodeTree(tmp_path / "code", str(tmp_path / "code/.venv/bin/python"))
    deck = audit.DECKS["a047_pvc_h40"]
    argv = audit.run_command(deck, tmp_path, tmp_path, 3, tmp_path, False, tree)
    assert argv[:2] == [tree.python, str(tree.root / "run.py")]
    assert audit.run_env(tree.root)["PYTHONPATH"].split(os.pathsep)[0] == str(tree.root)
    runner = audit.DECKS["fed_near1_hold_gate"]
    argv = audit.run_command(runner, tmp_path, tmp_path, 3, tmp_path, False, tree)
    assert argv[1] == str(tree.root / "tests" / "test_fed_margin_deck.py")


def test_report_lists_the_arms(audit, tmp_path):
    folder = tmp_path / "audit"
    _write_audit(folder, [2.0] * 6, [2.0] * 6)
    manifest = json.loads((folder / "manifest.json").read_text())
    manifest["margin"] = "arms"
    manifest["arms"] = {
        "base": {"commit": "a" * 40, "overrides": {}},
        "off": {"commit": None, "overrides": {"routing.w_smoke": 2}},
    }
    (folder / "manifest.json").write_text(json.dumps(manifest))
    args = ["analyse", str(folder), "--primary-deck", "l_corridor_gate"]
    assert audit.main([*args, "--metric", "returns"]) == 0
    text = (folder / "report.md").read_text()
    assert "Arm base: aaaaaaaa" in text
    assert "Arm off: working tree, routing.w_smoke=2" in text


def test_a_run_ending_at_the_time_limit_with_agents_left_is_usable(audit):
    left = {"outcome": {"agents_remaining": 3}}
    assert audit.exit_status(0, None) == (True, "ok")
    assert audit.exit_status(0, left) == (True, "ok")
    assert audit.exit_status(2, left) == (True, "ok (incomplete: 3 remaining)")


@pytest.mark.parametrize(
    ("code", "manifest"),
    [
        (2, None),  # argparse also exits 2, and writes nothing
        (2, {"outcome": {"agents_remaining": 0}}),
        (2, {}),
        (1, {"outcome": {"agents_remaining": 3}}),
    ],
)
def test_any_other_non_zero_exit_is_a_failed_run(audit, code, manifest):
    assert audit.exit_status(code, manifest) == (False, f"failed (exit {code})")


def test_routing_keys_are_the_ones_the_loader_reads(audit):
    keys = audit.routing_keys()
    assert {"anticipate", "cost_model", "w_smoke", "fed_rate_memo"} <= keys
    assert "fallback_rule" not in keys
    assert "anticpate" not in keys


@pytest.mark.parametrize("value", ["false", '"additive"', "1"])
def test_a_misspelt_routing_key_fails_whatever_its_value_type(audit, value):
    for path in (f"anticpate={value}", f"routing.anticpate={value}"):
        overrides = (audit.parse_override(path),)
        with pytest.raises(ValueError, match="routing.anticpate"):
            audit.check_override_keys(overrides)
    good = (audit.parse_override("anticipate=false"),)
    audit.check_override_keys(good)


def test_a_bad_override_fails_before_any_run_starts(audit, capsys, monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("a run was started")

    monkeypatch.setattr(audit.subprocess, "call", refuse)
    base = ["run", "--decks", "a047_pvc_h40", "--data-root", "/nonexistent"]
    code = audit.main([*base, "--head-set", "anticpate=false"])
    assert code == 2
    assert "routing.anticpate" in capsys.readouterr().out


def test_a_bad_config_path_fails_before_any_run_starts(audit, tmp_path, monkeypatch):
    root = tmp_path / "data"
    fds = root / audit.DECKS["a047_pvc_h40"].fds_dir
    fds.mkdir(parents=True)

    def refuse(*args, **kwargs):
        raise AssertionError("a run was started")

    monkeypatch.setattr(audit.subprocess, "call", refuse)
    args = ["run", "--decks", "a047_pvc_h40", "--data-root", str(root)]
    args += ["--allow-dirty"]
    args += ["--head-set", "config.simulation_settings.nope.x=1"]
    assert audit.main(args) == 2


def test_code_audit_outcome_is_worded_neutrally(audit):
    def primary(**kw):
        base = {"n": 10, "distinct": False, "worse": True, "effect": 3.0}
        return {**base, **kw}

    assert audit.code_audit_outcome(primary(), []) == (
        "no distinct effect on the primary metric"
    )
    worse = audit.code_audit_outcome(primary(distinct=True), [])
    assert worse.startswith("distinct effect on the primary metric: worse")
    better = audit.code_audit_outcome(primary(distinct=True, worse=False), [])
    assert "primary metric: better" in better
    assert "primary metric: changed" in audit.code_audit_outcome(
        primary(distinct=True, worse=None), []
    )
    harmed = [{"metric": "returns", "distinct": True, "worse": True}]
    assert "returns" in audit.code_audit_outcome(primary(distinct=True), harmed)
    assert audit.code_audit_outcome(primary(n=3), []).startswith("undecided")
    for text in (worse, better):
        assert "remove" not in text


def test_a_code_audit_report_does_not_say_remove(audit, tmp_path):
    folder = tmp_path / "audit"
    _write_audit(folder, [2.0] * 6, [2.0] * 6)
    path = folder / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest["margin"] = "arms"
    path.write_text(json.dumps(manifest))
    args = ["analyse", str(folder), "--primary-deck", "l_corridor_gate"]
    assert audit.main([*args, "--metric", "returns"]) == 0
    text = (folder / "report.md").read_text()
    assert "**Outcome: no distinct effect on the primary metric**" in text
    assert "remove" not in text
