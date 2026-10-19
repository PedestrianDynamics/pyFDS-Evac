"""attribute.py: tree attribution, counters summary, cProfile diff, CLI (Task 2 of the G2 plan)."""
import cProfile
import csv
import json
import sys
from pathlib import Path

import pytest

WT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WT))
import attribute as a  # noqa: E402

FIX = WT / "tests" / "fixtures" / "pyinstrument_small.json"
G1_COUNTERS = WT / "results/raw/G1b_ovhD2_W1_O_study_ctr_s1_rep1_20261017T045502/counters.json"


def test_attribute_tree_fixture():
    tree = a.load_tree(FIX)
    got = a.attribute_tree(tree["root_frame"], a.ISSUE_MAP)
    assert got[("route_segments", "rank_routes")]["cum_s"] == pytest.approx(3.0)
    assert got[("route_segments", "evaluate_segment")]["cum_s"] == pytest.approx(2.0)
    assert got[("route_segments", "TOTAL")]["cum_s"] == pytest.approx(3.0)   # no double count
    assert got[("slice_sampling", "TOTAL")]["cum_s"] == pytest.approx(1.5)
    assert got[("slice_sampling", "sample")]["self_s"] == pytest.approx(1.0)
    assert got[("steering_exit_test", "TOTAL")]["cum_s"] == pytest.approx(2.0)
    assert got[("steering_exit_test", "reached_stage")]["self_s"] == pytest.approx(0.5)
    assert got[("vismap_build", "TOTAL")]["cum_s"] == 0.0
    assert got[("flow_spawn", "TOTAL")]["cum_s"] == 0.0


def test_issue_map_covers_six_issues():
    issues = {i for e in a.ISSUE_MAP for i in e["issues"]}
    assert {"#236", "#241", "#242", "#243", "#739", "#429"} <= issues


@pytest.mark.skipif(not G1_COUNTERS.exists(), reason="G1 evidence not on this machine")
def test_counters_summary_g1_file():
    s = a.counters_summary(G1_COUNTERS)
    assert s["agent_steps"] == 3259925 and s["iterations"] == 40000
    assert s["loop_s"] == pytest.approx(43.313, abs=0.001)
    assert s["us_per_agent_step"] == pytest.approx(13.29, abs=0.01)
    assert s["reroute_evaluations"] == 32497 and s["fdsreader_full_parse"] == 7


def _prof(path, n):
    def work():
        return sum(i * i for i in range(n))
    cProfile.runctx("work()", {"work": work}, {}, filename=str(path))


def test_cprofile_diff(tmp_path):
    _prof(tmp_path / "a.prof", 300000)
    _prof(tmp_path / "b.prof", 100000)
    rows = a.cprofile_diff(tmp_path / "a.prof", tmp_path / "b.prof", must_include=("work",))
    deltas = [r["delta_cum_s"] for r in rows]
    assert deltas == sorted(deltas, reverse=True)
    by_function = {r["function"]: r for r in rows}
    assert by_function["work"]["delta_cum_s"] > 0
    assert by_function["<genexpr>"]["ncalls_O_study"] == 300001
    assert by_function["<genexpr>"]["ncalls_O_norc"] == 100001


def _manifest(run_id, block, profiler, wall, role="rep"):
    return {"run_id": run_id, "block": block, "case": "W1", "variant": "O_study", "seed": 1,
            "repetition": 1, "role": role, "profiler": profiler, "metrics": {"wall_s": wall},
            "host_during": {"contaminated": False, "offenders_max_pcpu": {}}}


def test_cli_writes_attribution_table(tmp_path, monkeypatch):
    raw = tmp_path / "results" / "raw"
    for rid, prof, wall in [("B_W1_O_study_s1_rep1_x", "none", 40.0), ("B_W1_O_study_s1_rep2_x", "none", 42.0),
                            ("B_W1_O_study_pyi_s1_rep1_x", "pyinstrument", 50.0),
                            ("B_W1_O_study_pyi_s1_rep2_x", "pyinstrument", 52.0)]:
        d = raw / rid
        d.mkdir(parents=True)
        (d / "manifest.json").write_text(json.dumps(_manifest(rid, "B", prof, wall)))
        if prof == "pyinstrument":
            (d / "pyinstrument.json").write_text(FIX.read_text())
    monkeypatch.setattr(a, "RAW", raw)
    out = tmp_path / "g2"
    assert a.main(["--block", "B", "--out", str(out)]) == 0
    rows = list(csv.DictReader(open(out / "attribution_B_W1.csv")))
    tot = {r["subsystem"]: r for r in rows if r["function"] == "TOTAL"}
    assert float(tot["route_segments"]["cum_s"]) == pytest.approx(3.0)
    assert float(tot["route_segments"]["profiled_wall_s"]) == pytest.approx(51.0)
    assert float(tot["route_segments"]["plain_wall_s"]) == pytest.approx(41.0)
    assert float(tot["route_segments"]["overhead_bound_s"]) == pytest.approx(10.0)
    assert float(tot["route_segments"]["cost_plain_s"]) == pytest.approx(3.0 * 41 / 51)
    assert float(tot["route_segments"]["agreement_pts"]) == pytest.approx((3 / 50 - 3 / 52) * 100)
    assert tot["vismap_build"]["status"] == "not_observed"
    assert list(rows[0].keys()) == a.ATTRIBUTION_COLUMNS


REAL = WT / "tests" / "fixtures" / "pyinstrument_real.json"
PROG_MAP = [{"subsystem": "prog", "issues": ("x",), "file": "prog.py",
             "functions": ("target", "small")}]


def test_self_time_on_real_pyinstrument_output():
    """pyinstrument 5.1.3 puts own time in ``[self]`` and C calls in ``<built-in>`` children."""
    tree = a.load_tree(REAL)
    got = a.attribute_tree(tree["root_frame"], PROG_MAP)
    # target: 0.098 s [self] + 0.202 s perf_counter; the child leaf (0.2 s) is not own time
    assert got[("prog", "target")]["cum_s"] == pytest.approx(0.5, abs=0.001)
    assert got[("prog", "target")]["self_s"] == pytest.approx(0.3, abs=0.001)
    # small is reached from five call paths of about 10-20 ms each
    assert got[("prog", "small")]["cum_s"] == pytest.approx(0.06, abs=0.001)
    assert got[("prog", "small")]["self_s"] == pytest.approx(0.06, abs=0.001)


def _block_tree(tmp_path, monkeypatch, runs):
    raw = tmp_path / "results" / "raw"
    for rid, prof, variant, wall in runs:
        d = raw / rid
        d.mkdir(parents=True)
        manifest = _manifest(rid, "B", prof, wall)
        manifest["variant"] = variant
        (d / "manifest.json").write_text(json.dumps(manifest))
        if prof == "pyinstrument":
            (d / "pyinstrument.json").write_text(FIX.read_text())
    monkeypatch.setattr(a, "RAW", raw)


@pytest.mark.parametrize("runs,message", [
    ([("p", "none", "O_study", 40.0)], "no profiled (pyinstrument) rep"),
    ([("p1", "pyinstrument", "O_study", 50.0), ("p2", "pyinstrument", "O_study", 51.0)],
     "no plain rep"),
])
def test_cli_exit_2_messages(tmp_path, monkeypatch, capsys, runs, message):
    _block_tree(tmp_path, monkeypatch, runs)
    assert a.main(["--block", "B", "--out", str(tmp_path / "g2")]) == 2
    assert message in capsys.readouterr().err


def test_single_profiled_rep_has_blank_agreement(tmp_path, monkeypatch, capsys):
    _block_tree(tmp_path, monkeypatch, [("p1", "pyinstrument", "O_study", 50.0),
                                        ("n", "none", "O_study", 40.0)])
    out = tmp_path / "g2"
    assert a.main(["--block", "B", "--out", str(out)]) == 0
    rows = list(csv.DictReader(open(next(out.glob("attribution_B_*.csv")))))
    assert rows and all(r["agreement_pts"] == "" and r["n_profiled"] == "1" for r in rows)
    assert "agreement not assessable" in capsys.readouterr().err


def test_rc_diff_exit_2_without_cprofile_rep(tmp_path, monkeypatch, capsys):
    _block_tree(tmp_path, monkeypatch, [("n", "none", "O_study", 40.0)])
    assert a.main(["--rc-diff", "B", "--out", str(tmp_path / "g2")]) == 2
    assert "no cprofile rep of variant O_study" in capsys.readouterr().err


def test_cprofile_diff_missing_must_include(tmp_path):
    _prof(tmp_path / "a.prof", 1000)
    _prof(tmp_path / "b.prof", 1000)
    with pytest.raises(a.AttributionError, match="no_such_function"):
        a.cprofile_diff(tmp_path / "a.prof", tmp_path / "b.prof", must_include=("no_such_function",))


def _rm_manifest(rid, block, variant, wall, termination="completed", contaminated=False,
                 counters=False):
    return {"run_id": rid, "block": block, "case": "W1", "variant": variant, "role": "rep",
            "termination": termination, "metrics": {"wall_s": wall},
            "host_during": {"contaminated": contaminated, "offenders_max_pcpu": {}},
            "counters_path": "counters.json" if counters else None,
            "instrumentation": {"entry_point": "perf_run.py", "stubs": []}}


def _removal_fixture(tmp_path, walls, steps, failed_id=None, rm="R", ctr="C"):
    raw = tmp_path / "results" / "raw"
    for arm, ws in walls.items():
        for i, w in enumerate(ws, 1):
            rid = f"{rm}_W1_{arm}_s1_rep{i}_x"
            d = raw / rid
            d.mkdir(parents=True)
            (d / "manifest.json").write_text(json.dumps(_rm_manifest(
                rid, rm, arm, w, contaminated=(i == 1),
                termination="failed" if rid == failed_id else "completed")))
    for arm, n in steps.items():
        for i in (1, 2):
            rid = f"{ctr}_W1_{arm}_ctr_s1_rep{i}_x"
            d = raw / rid
            d.mkdir(parents=True)
            (d / "manifest.json").write_text(json.dumps(_rm_manifest(rid, ctr, arm, 40.0, counters=True)))
            (d / "counters.json").write_text(json.dumps(
                {"counters": {"agent_steps": n, "iterations": 10},
                 "timers_s": {"loop_first_iterate_to_last_iterate_end": 30.0}}))
    return raw


def test_removal_table_rows_and_verdicts(tmp_path, monkeypatch):
    walls = {"O_norc": [36.0, 36.2, 36.4, 36.1, 36.3], "nrr": [30.0, 30.2, 30.1, 30.3, 30.4],
             "nss": [34.0, 34.2, 34.1, 34.3, 34.4], "nst": [36.1, 36.3, 36.0, 36.2, 36.4]}
    raw = _removal_fixture(tmp_path, walls, {"O_norc": 1000, "nrr": 900, "nss": 1000, "nst": 1000})
    monkeypatch.setattr(a, "RAW", raw)
    out = tmp_path / "g3"
    assert a.main(["--removal", "R", "--counters-block", "C", "--out", str(out)]) == 0
    with open(out / "removal_R.csv") as fh:
        rows = {r["arm"]: r for r in csv.DictReader(fh)}
    assert list(rows) == ["O_norc", "nrr", "nss", "nst"]
    assert list(rows["nrr"].keys()) == a.REMOVAL_COLUMNS
    assert rows["O_norc"]["verdict"] == "baseline" and rows["O_norc"]["diff_s"] == ""
    assert float(rows["nrr"]["diff_s"]) == pytest.approx(36.2 - 30.2)
    assert float(rows["nrr"]["diff_per_study_s"]) == pytest.approx(60.0)
    assert rows["nrr"]["verdict"] == "fix_first"
    assert rows["nss"]["verdict"] == "below_bar"          # 2.0 s x 10 = 20 s < 23 s, above the spread
    assert rows["nst"]["verdict"] == "tie"                # 0.0 s within the IQR
    assert rows["nrr"]["n_flagged"] == "1" and rows["nrr"]["n_used"] == "5"
    assert float(rows["O_norc"]["us_per_agent_step"]) == pytest.approx(36.2 / 1000 * 1e6)
    assert float(rows["nrr"]["diff_us_per_agent_step"]) == pytest.approx(
        36.2 / 1000 * 1e6 - 30.2 / 900 * 1e6)


def test_removal_exclude_and_failed_reps_are_not_used(tmp_path, monkeypatch):
    walls = {"O_norc": [36.0, 36.2, 99.0], "nrr": [30.0, 30.2, 30.1], "nss": [34.0, 34.2, 34.1],
             "nst": [35.0, 35.2, 35.1]}
    raw = _removal_fixture(tmp_path, walls, {arm: 1000 for arm in walls},
                           failed_id="R_W1_nss_s1_rep3_x")
    monkeypatch.setattr(a, "RAW", raw)
    out = tmp_path / "g3"
    assert a.main(["--removal", "R", "--counters-block", "C", "--out", str(out),
                   "--exclude", "R_W1_O_norc_s1_rep3_x"]) == 0
    with open(out / "removal_R.csv") as fh:
        rows = {r["arm"]: r for r in csv.DictReader(fh)}
    assert rows["O_norc"]["n_reps"] == "3" and rows["O_norc"]["n_used"] == "2"
    assert float(rows["O_norc"]["wall_s_median"]) == pytest.approx(36.1)
    assert rows["nss"]["n_used"] == "2"


def test_removal_missing_arm_exits_2(tmp_path, monkeypatch, capsys):
    raw = _removal_fixture(tmp_path, {"O_norc": [36.0], "nrr": [30.0], "nss": [34.0]},
                           {"O_norc": 1, "nrr": 1, "nss": 1})
    monkeypatch.setattr(a, "RAW", raw)
    assert a.main(["--removal", "R", "--counters-block", "C", "--out", str(tmp_path / "g3")]) == 2
    assert "arm nst has no usable reps" in capsys.readouterr().err


MAIN_WALLS = {"O_norc": [36.0, 36.2, 36.4, 36.1, 36.3], "nrr": [30.0, 30.2, 30.1, 30.3, 30.4],
              "nss": [28.0, 28.2, 28.1, 28.3, 28.4], "nst": [36.1, 36.3, 36.0, 36.2, 36.4]}


def _rerun_args(tmp_path, out):
    return ["--removal", "R", "--counters-block", "C", "--rerun-block", "R2",
            "--rerun-counters-block", "C2", "--out", str(out)]


def _rerun_rows(tmp_path, monkeypatch, rerun_walls, rerun_steps):
    raw = _removal_fixture(tmp_path, MAIN_WALLS, {a_: 1000 for a_ in MAIN_WALLS})
    _removal_fixture(tmp_path, rerun_walls, rerun_steps, rm="R2", ctr="C2")
    monkeypatch.setattr(a, "RAW", raw)
    out = tmp_path / "g3"
    assert a.main(_rerun_args(tmp_path, out)) == 0
    with open(out / "removal_R.csv") as fh:
        return {r["arm"]: r for r in csv.DictReader(fh)}


def test_removal_source_block_column_is_last_and_names_the_main_block(tmp_path, monkeypatch):
    raw = _removal_fixture(tmp_path, MAIN_WALLS, {a_: 1000 for a_ in MAIN_WALLS})
    monkeypatch.setattr(a, "RAW", raw)
    assert a.main(["--removal", "R", "--counters-block", "C", "--out", str(tmp_path / "g3")]) == 0
    with open(tmp_path / "g3" / "removal_R.csv") as fh:
        rows = list(csv.DictReader(fh))
    assert list(rows[0].keys())[-1] == "source_block"
    assert {r["source_block"] for r in rows} == {"R"}


def test_rerun_replaces_nss_with_comparison_against_rerun_baseline(tmp_path, monkeypatch):
    rerun_walls = {"O_norc": [38.0, 38.2, 38.1, 38.3, 38.4], "nss": [27.0, 27.2, 27.1, 27.3, 27.4]}
    rows = _rerun_rows(tmp_path, monkeypatch, rerun_walls, {"O_norc": 2000, "nss": 1500})
    assert {v: r["source_block"] for v, r in rows.items()} == {
        "O_norc": "R", "nrr": "R", "nss": "R2", "nst": "R"}
    assert float(rows["nss"]["wall_s_median"]) == pytest.approx(27.2)
    assert float(rows["nss"]["diff_s"]) == pytest.approx(38.2 - 27.2)       # rerun O_norc, not 36.2
    assert float(rows["nss"]["diff_per_study_s"]) == pytest.approx(110.0)
    assert float(rows["nss"]["diff_us_per_agent_step"]) == pytest.approx(
        38.2 / 2000 * 1e6 - 27.2 / 1500 * 1e6)
    assert rows["nss"]["verdict"] == "fix_first"
    assert float(rows["O_norc"]["wall_s_median"]) == pytest.approx(36.2)    # main baseline row kept


def test_rerun_leaves_the_other_arms_unchanged(tmp_path, monkeypatch):
    raw = _removal_fixture(tmp_path, MAIN_WALLS, {a_: 1000 for a_ in MAIN_WALLS})
    monkeypatch.setattr(a, "RAW", raw)
    plain = tmp_path / "plain"
    assert a.main(["--removal", "R", "--counters-block", "C", "--out", str(plain)]) == 0
    _removal_fixture(tmp_path, {"O_norc": [38.0, 38.2, 38.1], "nss": [37.9, 38.1, 38.0]},
                     {"O_norc": 2000, "nss": 2000}, rm="R2", ctr="C2")
    rerun = tmp_path / "rerun"
    assert a.main(_rerun_args(tmp_path, rerun)) == 0
    with open(plain / "removal_R.csv") as fh:
        before = {r["arm"]: r for r in csv.DictReader(fh)}
    with open(rerun / "removal_R.csv") as fh:
        after = {r["arm"]: r for r in csv.DictReader(fh)}
    for arm in ("O_norc", "nrr", "nst"):
        assert after[arm] == before[arm]
    assert after["nss"]["source_block"] == "R2" and after["nss"]["verdict"] == "tie"


def test_rerun_options_go_together_and_need_removal(tmp_path, capsys):
    with pytest.raises(SystemExit):
        a.main(["--removal", "R", "--counters-block", "C", "--rerun-block", "R2",
                "--out", str(tmp_path)])
    assert "go together" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        a.main(["--counters", "C", "--rerun-block", "R2", "--rerun-counters-block", "C2",
                "--out", str(tmp_path)])
    assert "needs --removal" in capsys.readouterr().err


def test_rerun_block_without_baseline_exits_2(tmp_path, monkeypatch, capsys):
    raw = _removal_fixture(tmp_path, MAIN_WALLS, {a_: 1000 for a_ in MAIN_WALLS})
    _removal_fixture(tmp_path, {"nss": [27.0, 27.2]}, {"nss": 1500}, rm="R2", ctr="C2")
    monkeypatch.setattr(a, "RAW", raw)
    assert a.main(_rerun_args(tmp_path, tmp_path / "g3")) == 2
    assert "arm O_norc has no usable reps" in capsys.readouterr().err


def test_rerun_exclude_applies_to_the_rerun_block(tmp_path, monkeypatch):
    raw = _removal_fixture(tmp_path, MAIN_WALLS, {a_: 1000 for a_ in MAIN_WALLS})
    _removal_fixture(tmp_path, {"O_norc": [38.0, 38.2, 99.0], "nss": [27.0, 27.2, 27.1]},
                     {"O_norc": 2000, "nss": 1500}, rm="R2", ctr="C2")
    monkeypatch.setattr(a, "RAW", raw)
    out = tmp_path / "g3"
    assert a.main(_rerun_args(tmp_path, out) + ["--exclude", "R2_W1_O_norc_s1_rep3_x"]) == 0
    with open(out / "removal_R.csv") as fh:
        rows = {r["arm"]: r for r in csv.DictReader(fh)}
    assert float(rows["nss"]["diff_s"]) == pytest.approx(38.1 - 27.1)


def test_removal_unknown_exclude_id_exits_2(tmp_path, monkeypatch, capsys):
    raw = _removal_fixture(tmp_path, MAIN_WALLS, {a_: 1000 for a_ in MAIN_WALLS})
    monkeypatch.setattr(a, "RAW", raw)
    assert a.main(["--removal", "R", "--counters-block", "C", "--out", str(tmp_path / "g3"),
                   "--exclude", "R_W1_O_norc_s1_rep9_x"]) == 2
    assert "R_W1_O_norc_s1_rep9_x" in capsys.readouterr().err


def test_removal_zero_agent_steps_exits_2(tmp_path, monkeypatch, capsys):
    raw = _removal_fixture(tmp_path, MAIN_WALLS, {a_: 0 for a_ in MAIN_WALLS})
    monkeypatch.setattr(a, "RAW", raw)
    assert a.main(["--removal", "R", "--counters-block", "C", "--out", str(tmp_path / "g3")]) == 2
    assert "agent-steps" in capsys.readouterr().err


def test_exclude_and_counters_block_need_removal(tmp_path, capsys):
    with pytest.raises(SystemExit):
        a.main(["--counters", "C", "--exclude", "X", "--out", str(tmp_path)])
    assert "--exclude needs --removal, --equality, --paired or --paired-removal" in capsys.readouterr().err
    for mode in ("--counters", "--equality"):
        with pytest.raises(SystemExit):
            a.main([mode, "C", "--counters-block", "C", "--out", str(tmp_path)])
        assert "--counters-block needs --removal" in capsys.readouterr().err


def _route_paths_fixture(tmp_path, with_paths=True):
    """A G4det block: one detail run whose counters.json carries (or lacks) route_paths."""
    raw = tmp_path / "results" / "raw"
    run_id = "G4det_W1_O_norc_det_s1_rep1_x"
    (raw / run_id).mkdir(parents=True)
    counters = raw / run_id / "counters.json"
    (raw / run_id / "manifest.json").write_text(json.dumps({
        "run_id": run_id, "block": "G4det", "case": "W1", "variant": "O_norc", "role": "rep",
        "termination": "incomplete_time_limit", "counters_path": str(counters)}))
    keyed = {"capped": False}
    paths = {
        "evaluate_segment": {"calls": 100, "seconds": 10.0, "self_seconds": 4.0,
                             "by_parent": {"root": 10.0}},
        "first_leg": {"calls": 10, "seconds": 1.0, "self_seconds": 0.5,
                      "by_parent": {"root": 1.0}},
        # cell_los_stats is also reached from first_leg: flat seconds exceed its share in
        # evaluate_segment.
        "cell_los_stats": {"calls": 100, "seconds": 4.0, "self_seconds": 0.5,
                           "by_parent": {"evaluate_segment": 3.0, "first_leg": 1.0}},
        "step_los_stats": {"calls": 0, "seconds": 0.0, "self_seconds": 0.0, "by_parent": {}},
        "read_cells": {"calls": 400, "seconds": 3.0, "self_seconds": 3.0, "total": 400,
                       "distinct": 100, "by_parent": {"cell_los_stats": 3.0}, **keyed},
        "line_parts": {"calls": 400, "seconds": 0.5, "self_seconds": 0.5,
                       "by_parent": {"cell_los_stats": 0.5}},
        "sample_fed_rate": {"calls": 100, "seconds": 2.0, "self_seconds": 2.0, "total": 100,
                            "distinct": 50, "by_parent": {"evaluate_segment": 2.0}, **keyed},
        "sample_route": {"calls": 0, "seconds": 0.0, "self_seconds": 0.0, "total": 0,
                         "distinct": 0, "by_parent": {}, **keyed},
    }
    detail = {"route_paths": paths,
              "route_paths_overhead": {"noop_wrapper_calls": 1_000_000,
                                       "noop_wrapper_seconds": 1.0}} if with_paths else {}
    counters.write_text(json.dumps({"detail": detail}))
    return raw


def test_route_paths_table_rows(tmp_path, monkeypatch):
    monkeypatch.setattr(a, "RAW", _route_paths_fixture(tmp_path))
    out = tmp_path / "g4"
    assert a.main(["--route-paths", "G4det", "--out", str(out)]) == 0
    with open(out / "route_paths_G4det.csv") as fh:
        reader = csv.DictReader(fh)
        rows = {r["path"]: r for r in reader}
    assert list(reader.fieldnames) == a.ROUTE_PATHS_COLUMNS
    assert len(rows) == 10
    rc = rows["read_cells"]
    assert float(rc["overhead_s"]) == pytest.approx(0.0004)
    assert float(rc["hit_share"]) == pytest.approx(0.75)
    assert float(rc["avoidable_s"]) == pytest.approx(0.75 * (3.0 - 0.0004))
    sf = rows["sample_fed_rate"]
    assert float(sf["hit_share"]) == pytest.approx(0.5)
    assert float(sf["avoidable_per_study_s"]) == pytest.approx(10 * 0.5 * (2.0 - 0.0001))
    total = rows["TOTAL"]
    assert float(total["avoidable_per_study_s"]) == pytest.approx(
        10 * (0.75 * 2.9996 + 0.5 * 1.9999))
    assert float(total["net_seconds"]) == pytest.approx((10.0 - 0.0001) + (1.0 - 0.00001))
    assert rows["sample_route"]["hit_share"] == ""
    assert rows["evaluate_segment"]["total"] == ""
    assert rows["read_cells"]["capped"] == "False"
    assert rows["first_leg"]["avoidable_s"] == ""


def test_route_paths_remainder_is_evaluate_segment_self_time(tmp_path, monkeypatch):
    monkeypatch.setattr(a, "RAW", _route_paths_fixture(tmp_path))
    out = tmp_path / "g4"
    assert a.main(["--route-paths", "G4det", "--out", str(out)]) == 0
    with open(out / "route_paths_G4det.csv") as fh:
        rows = {r["path"]: r for r in csv.DictReader(fh)}
    # Not 10 - 4 - 0 - 2: cell_los_stats seconds also hold its first_leg calls.
    assert float(rows["remainder"]["net_seconds"]) == pytest.approx(4.0 - 0.0001)


def test_route_paths_without_route_paths_exits_2(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(a, "RAW", _route_paths_fixture(tmp_path, with_paths=False))
    assert a.main(["--route-paths", "G4det", "--out", str(tmp_path / "g4")]) == 2
    assert "no route_paths" in capsys.readouterr().err


def _memo_fixture(tmp_path, seeds=(1, 2), differ_seed=None, drop=None, block="G5_memo_W1"):
    """Timed reps of O_norc and nomemo per seed with outputs on disk; differ_seed gets a different
    nomemo exit.csv; drop=(seed, arm) leaves that rep out."""
    raw = tmp_path / "results" / "raw"
    for seed in seeds:
        for arm in a.MEMO_ARMS:
            if drop == (seed, arm):
                continue
            rid = f"{block}_W1_{arm}_s{seed}_rep1_x"
            out = tmp_path / "runs" / rid
            out.mkdir(parents=True)
            (out / "exit.csv").write_text("exit\n" + ("x\n" if seed == differ_seed and arm == "nomemo" else ""))
            (out / "rh.csv").write_text("rh\n")
            d = raw / rid
            d.mkdir(parents=True)
            man = _rm_manifest(rid, block, arm, 30.0 + seed + (0.5 if arm == "nomemo" else 0.0),
                               termination="incomplete_time_limit")
            man.update({"seed": seed, "outputs_dir": str(out)})
            (d / "manifest.json").write_text(json.dumps(man))
    return raw


def test_equality_all_pairs_equal_exits_0(tmp_path, monkeypatch):
    monkeypatch.setattr(a, "RAW", _memo_fixture(tmp_path))
    out = tmp_path / "g5"
    assert a.main(["--equality", "G5_memo_W1", "--out", str(out)]) == 0
    with open(out / "equality_G5_memo_W1.csv") as fh:
        rows = list(csv.DictReader(fh))
    assert [r["seed"] for r in rows] == ["1", "2"] and list(rows[0]) == a.EQUALITY_COLUMNS
    assert rows[0]["memo_run_id"] == "G5_memo_W1_W1_O_norc_s1_rep1_x"
    assert all(r["exit_csv_equal"] == "True" and r["rh_csv_equal"] == "True" for r in rows)


def test_equality_differing_pair_exits_3_with_the_table(tmp_path, monkeypatch):
    monkeypatch.setattr(a, "RAW", _memo_fixture(tmp_path, differ_seed=2))
    out = tmp_path / "g5"
    assert a.main(["--equality", "G5_memo_W1", "--out", str(out)]) == 3
    with open(out / "equality_G5_memo_W1.csv") as fh:
        rows = {r["seed"]: r for r in csv.DictReader(fh)}
    assert rows["2"]["exit_csv_equal"] == "False" and rows["2"]["rh_csv_equal"] == "True"
    assert rows["1"]["exit_csv_equal"] == "True"


def test_equality_seed_with_both_arms_crashed_exits_2(tmp_path, monkeypatch, capsys):
    raw = _memo_fixture(tmp_path, seeds=(1, 2, 3))
    for arm in a.MEMO_ARMS:
        path = raw / f"G5_memo_W1_W1_{arm}_s2_rep1_x" / "manifest.json"
        manifest = json.loads(path.read_text())
        manifest["termination"] = "crashed"
        path.write_text(json.dumps(manifest))
    monkeypatch.setattr(a, "RAW", raw)
    assert a.main(["--equality", "G5_memo_W1", "--out", str(tmp_path / "g5")]) == 2
    assert "seed 2 lacks a usable rep" in capsys.readouterr().err
    assert not (tmp_path / "g5").exists()


def test_equality_manifest_without_outputs_dir_or_seed_exits_2(tmp_path, monkeypatch, capsys):
    raw = _memo_fixture(tmp_path)
    path = raw / "G5_memo_W1_W1_nomemo_s1_rep1_x" / "manifest.json"
    manifest = json.loads(path.read_text())
    del manifest["outputs_dir"]
    path.write_text(json.dumps(manifest))
    monkeypatch.setattr(a, "RAW", raw)
    assert a.main(["--equality", "G5_memo_W1", "--out", str(tmp_path / "g5")]) == 2
    assert "outputs_dir missing" in capsys.readouterr().err
    del manifest["seed"]
    path.write_text(json.dumps(manifest))
    assert a.main(["--equality", "G5_memo_W1", "--out", str(tmp_path / "g5")]) == 2
    assert "seed missing" in capsys.readouterr().err


def test_equality_missing_arm_or_file_exits_2(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(a, "RAW", _memo_fixture(tmp_path, drop=(2, "nomemo")))
    assert a.main(["--equality", "G5_memo_W1", "--out", str(tmp_path / "g5")]) == 2
    assert "seed 2 lacks a usable rep" in capsys.readouterr().err
    raw = _memo_fixture(tmp_path / "b")
    monkeypatch.setattr(a, "RAW", raw)
    (tmp_path / "b" / "runs" / "G5_memo_W1_W1_nomemo_s1_rep1_x" / "rh.csv").unlink()
    assert a.main(["--equality", "G5_memo_W1", "--out", str(tmp_path / "g5b")]) == 2
    assert "rh.csv" in capsys.readouterr().err


def _paired_fixture(tmp_path, memo, nomemo, steps=1000, differ_seed=None, drop=None,
                    memo_lines=("FED-rate memo: 300 hits, 100 misses, 0 clears",
                                "FED-rate memo: 0 hits, 0 misses, 0 clears")):
    """Memo block G5_memo_W1 with per-seed walls (memo[i], nomemo[i] for seed i+1) and outputs on disk,
    plus counters block G5_ctr_W1 (two reps per arm, memo.log from memo_lines; None = no file)."""
    raw = tmp_path / "results" / "raw"
    for i, (wm, wn) in enumerate(zip(memo, nomemo), 1):
        for arm, wall in (("O_norc", wm), ("nomemo", wn)):
            if drop == (i, arm):
                continue
            rid = f"G5_memo_W1_W1_{arm}_s{i}_rep1_x"
            out = tmp_path / "runs" / rid
            out.mkdir(parents=True)
            (out / "exit.csv").write_text("exit\n" + ("x\n" if i == differ_seed and arm == "nomemo" else ""))
            (out / "rh.csv").write_text("rh\n")
            d = raw / rid
            d.mkdir(parents=True)
            man = _rm_manifest(rid, "G5_memo_W1", arm, wall, contaminated=(i == 1 and arm == "nomemo"),
                               termination="incomplete_time_limit")
            man.update({"seed": i, "outputs_dir": str(out)})
            (d / "manifest.json").write_text(json.dumps(man))
    for arm, line in zip(a.MEMO_ARMS, memo_lines):
        for r in (1, 2):
            rid = f"G5_ctr_W1_W1_{arm}_ctr_s1_rep{r}_x"
            d = raw / rid
            d.mkdir(parents=True)
            man = _rm_manifest(rid, "G5_ctr_W1", arm, 40.0, counters=True, termination="incomplete_time_limit")
            man["seed"] = 1
            (d / "manifest.json").write_text(json.dumps(man))
            (d / "counters.json").write_text(json.dumps(
                {"counters": {"agent_steps": steps, "iterations": 10},
                 "timers_s": {"loop_first_iterate_to_last_iterate_end": 30.0}}))
            if line is not None:
                (d / "memo.log").write_text(line + "\n")
    return raw


def _paired_rows(tmp_path, monkeypatch, raw, exclude=()):
    monkeypatch.setattr(a, "RAW", raw)
    out = tmp_path / "g5"
    argv = ["--paired", "G5_memo_W1", "--counters-block", "G5_ctr_W1", "--out", str(out)]
    for rid in exclude:
        argv += ["--exclude", rid]
    assert a.main(argv) == 0
    with open(out / "paired_G5_memo_W1.csv") as fh:
        rows = list(csv.DictReader(fh))
    return {r["seed"]: r for r in rows}, rows


def test_paired_fix_first_by_hand(tmp_path, monkeypatch):
    rows, ordered = _paired_rows(tmp_path, monkeypatch,
                                 _paired_fixture(tmp_path, [30.0, 31.0, 32.0], [34.0, 36.0, 35.0]))
    assert [r["seed"] for r in ordered] == ["1", "2", "3", "ALL"] and list(ordered[0]) == a.PAIRED_COLUMNS
    assert [float(rows[s]["d_s"]) for s in "123"] == [4.0, 5.0, 3.0]
    assert rows["1"]["flagged_nomemo"] == "True" and rows["1"]["flagged_memo"] == "False"
    assert all(rows[s]["outputs_equal"] == "True" for s in "123") and rows["1"]["verdict"] == ""
    total = rows["ALL"]
    assert total["n_seeds"] == "3" and total["n_seeds_dropped"] == "0"
    assert float(total["median_d_s"]) == 4.0 and float(total["iqr_d_s"]) == 2.0   # quartiles of [3, 4, 5]: 3 and 5
    assert float(total["diff_per_study_s"]) == 40.0 and float(total["sum_d_s"]) == 12.0
    assert float(total["agent_steps_median"]) == 1000.0
    assert float(total["d_us_per_agent_step"]) == pytest.approx(4000.0)
    assert total["verdict"] == "fix_first"


def test_paired_tie_inside_the_iqr(tmp_path, monkeypatch):
    rows, _ = _paired_rows(tmp_path, monkeypatch,
                           _paired_fixture(tmp_path, [30.0, 30.0, 30.0], [30.5, 29.6, 30.3]))
    total = rows["ALL"]
    assert float(total["median_d_s"]) == pytest.approx(0.3) and float(total["iqr_d_s"]) == pytest.approx(0.9)
    assert total["verdict"] == "tie"


def test_paired_below_bar(tmp_path, monkeypatch):
    rows, _ = _paired_rows(tmp_path, monkeypatch,
                           _paired_fixture(tmp_path, [30.0, 30.0, 30.0], [31.0, 31.1, 31.2]))
    total = rows["ALL"]
    assert float(total["diff_per_study_s"]) == pytest.approx(11.0) and total["verdict"] == "below_bar"


def test_paired_differing_outputs_invalidate_the_verdict(tmp_path, monkeypatch):
    rows, _ = _paired_rows(tmp_path, monkeypatch,
                           _paired_fixture(tmp_path, [30.0, 31.0, 32.0], [34.0, 36.0, 35.0], differ_seed=2))
    assert rows["2"]["outputs_equal"] == "False" and rows["1"]["outputs_equal"] == "True"
    assert rows["ALL"]["verdict"] == "invalid_outputs_differ"


def test_paired_drops_a_seed_with_one_arm_and_counts_it(tmp_path, monkeypatch):
    rows, ordered = _paired_rows(tmp_path, monkeypatch,
                                 _paired_fixture(tmp_path, [30.0, 31.0, 32.0], [34.0, 36.0, 35.0],
                                                 drop=(3, "nomemo")))
    assert [r["seed"] for r in ordered] == ["1", "2", "ALL"]
    assert rows["ALL"]["n_seeds"] == "2" and rows["ALL"]["n_seeds_dropped"] == "1"
    assert float(rows["ALL"]["median_d_s"]) == 4.5


def test_paired_exclude_drops_the_excluded_rep(tmp_path, monkeypatch):
    raw = _paired_fixture(tmp_path, [30.0, 31.0, 32.0], [34.0, 36.0, 35.0])
    rows, _ = _paired_rows(tmp_path, monkeypatch, raw, exclude=["G5_memo_W1_W1_nomemo_s3_rep1_x"])
    assert rows["ALL"]["n_seeds"] == "2" and rows["ALL"]["n_seeds_dropped"] == "1"


def test_paired_unknown_exclude_id_exits_2(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(a, "RAW", _paired_fixture(tmp_path, [30.0, 31.0], [34.0, 36.0]))
    assert a.main(["--paired", "G5_memo_W1", "--counters-block", "G5_ctr_W1", "--out", str(tmp_path / "g5"),
                   "--exclude", "G5_memo_W1_W1_nomemo_s3_rep1_TYPO"]) == 2
    assert "--exclude ids match no rep: G5_memo_W1_W1_nomemo_s3_rep1_TYPO" in capsys.readouterr().err


def test_paired_counts_a_seed_with_no_usable_rep_in_either_arm(tmp_path, monkeypatch):
    raw = _paired_fixture(tmp_path, [30.0, 31.0, 32.0], [34.0, 36.0, 35.0])
    rows, _ = _paired_rows(tmp_path, monkeypatch, raw, exclude=["G5_memo_W1_W1_nomemo_s3_rep1_x",
                                                               "G5_memo_W1_W1_O_norc_s3_rep1_x"])
    assert rows["ALL"]["n_seeds"] == "2" and rows["ALL"]["n_seeds_dropped"] == "1"


def test_paired_no_seed_with_both_arms_exits_2(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(a, "RAW", _paired_fixture(tmp_path, [30.0], [34.0], drop=(1, "nomemo")))
    assert a.main(["--paired", "G5_memo_W1", "--counters-block", "G5_ctr_W1", "--out", str(tmp_path / "g5")]) == 2
    assert "no seed with a usable rep in both arms" in capsys.readouterr().err


def test_paired_zero_agent_steps_exits_2(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(a, "RAW", _paired_fixture(tmp_path, [30.0], [34.0], steps=0))
    assert a.main(["--paired", "G5_memo_W1", "--counters-block", "G5_ctr_W1", "--out", str(tmp_path / "g5")]) == 2
    assert "zero agent-steps" in capsys.readouterr().err


def test_paired_differing_outputs_override_a_tie(tmp_path, monkeypatch):
    rows, _ = _paired_rows(tmp_path, monkeypatch,
                           _paired_fixture(tmp_path, [30.0, 30.0, 30.0], [30.5, 29.6, 30.3], differ_seed=2))
    assert rows["ALL"]["verdict"] == "invalid_outputs_differ"


def test_paired_median_equal_to_the_iqr_is_a_tie(tmp_path, monkeypatch):
    # d = [2, 4, 6]: quartiles 2 and 6 give IQR 4 == median 4
    rows, _ = _paired_rows(tmp_path, monkeypatch,
                           _paired_fixture(tmp_path, [30.0, 30.0, 30.0], [32.0, 34.0, 36.0]))
    total = rows["ALL"]
    assert float(total["median_d_s"]) == 4.0 and float(total["iqr_d_s"]) == 4.0
    assert total["verdict"] == "tie"


def test_memo_counters_table(tmp_path, monkeypatch):
    raw = _paired_fixture(tmp_path, [30.0], [34.0],
                          memo_lines=("FED-rate memo: 300 hits, 100 misses, 0 clears", None))
    monkeypatch.setattr(a, "RAW", raw)
    out = tmp_path / "g5"
    assert a.main(["--memo-counters", "G5_ctr_W1", "--out", str(out)]) == 0
    with open(out / "memo_counters_G5_ctr_W1.csv") as fh:
        rows = list(csv.DictReader(fh))
    assert list(rows[0]) == a.MEMO_COUNTERS_COLUMNS and len(rows) == 4
    memo = [r for r in rows if r["variant"] == "O_norc"]
    assert memo[0]["hits"] == "300" and memo[0]["misses"] == "100" and float(memo[0]["hit_share"]) == 0.75
    assert memo[0]["agent_steps"] == "1000"
    nomemo = [r for r in rows if r["variant"] == "nomemo"]
    assert nomemo[0]["hits"] == "" and nomemo[0]["hit_share"] == ""


def test_paired_needs_counters_block(tmp_path, capsys):
    with pytest.raises(SystemExit):
        a.main(["--paired", "G5_memo_W1", "--out", str(tmp_path)])
    assert "needs --counters-block" in capsys.readouterr().err


def _removal_pair_fixture(tmp_path, base, arm, steps=1000, drop=None, arm_name="nss",
                          block="G6_nss_W1", ctr="G6_ctr_W1"):
    """Removal block with per-seed walls (base[i] for O_norc, arm[i] for arm_name, seed i+1), outcomes on
    the manifests (O_norc 400 s / 199 evacuated, arm 313.53 s / 200), plus a counters block (two O_norc reps
    and two arm reps, agent_steps = steps). drop=(seed, variant) leaves that rep out."""
    raw = tmp_path / "results" / "raw"
    for i, (wb, wa) in enumerate(zip(base, arm), 1):
        for variant, wall in (("O_norc", wb), (arm_name, wa)):
            if drop == (i, variant):
                continue
            rid = f"{block}_W1_{variant}_s{i}_rep1_x"
            d = raw / rid
            d.mkdir(parents=True)
            man = _rm_manifest(rid, block, variant, wall, contaminated=(i == 1 and variant == arm_name),
                               termination="incomplete_time_limit" if variant == "O_norc" else "completed")
            man["seed"] = i
            man["outcome"] = ({"status": "incomplete", "sim_time_s": 400.0, "evacuated": 199, "total": 200}
                              if variant == "O_norc" else
                              {"status": "completed", "sim_time_s": 313.53, "evacuated": 200, "total": 200})
            (d / "manifest.json").write_text(json.dumps(man))
    for variant in ("O_norc", arm_name):
        for r in (1, 2):
            rid = f"{ctr}_W1_{variant}_ctr_s1_rep{r}_x"
            d = raw / rid
            d.mkdir(parents=True)
            man = _rm_manifest(rid, ctr, variant, 40.0, counters=True, termination="incomplete_time_limit")
            man["seed"] = 1
            (d / "manifest.json").write_text(json.dumps(man))
            (d / "counters.json").write_text(json.dumps(
                {"counters": {"agent_steps": steps if variant == "O_norc" else steps * 2, "iterations": 10},
                 "timers_s": {"loop_first_iterate_to_last_iterate_end": 30.0}}))
    return raw


def _removal_pair_rows(tmp_path, monkeypatch, raw, exclude=()):
    monkeypatch.setattr(a, "RAW", raw)
    out = tmp_path / "g6"
    argv = ["--paired-removal", "G6_nss_W1", "--arm", "nss", "--counters-block", "G6_ctr_W1", "--out", str(out)]
    for rid in exclude:
        argv += ["--exclude", rid]
    assert a.main(argv) == 0
    with open(out / "paired_removal_G6_nss_W1_nss.csv") as fh:
        rows = list(csv.DictReader(fh))
    return {r["seed"]: r for r in rows}, rows


def test_paired_removal_fix_first_by_hand(tmp_path, monkeypatch):
    rows, ordered = _removal_pair_rows(tmp_path, monkeypatch,
                                      _removal_pair_fixture(tmp_path, [34.0, 36.0, 35.0], [30.0, 31.0, 32.0]))
    assert [r["seed"] for r in ordered] == ["1", "2", "3", "ALL"] and list(ordered[0]) == a.PAIRED_REMOVAL_COLUMNS
    assert [float(rows[s]["d_s"]) for s in "123"] == [4.0, 5.0, 3.0]
    assert rows["1"]["flagged_arm"] == "True" and rows["1"]["flagged_base"] == "False"
    assert float(rows["1"]["sim_time_base_s"]) == 400.0 and float(rows["1"]["sim_time_arm_s"]) == 313.53
    assert int(rows["1"]["evacuated_base"]) == 199 and int(rows["1"]["evacuated_arm"]) == 200
    assert rows["1"]["base_run_id"] == "G6_nss_W1_W1_O_norc_s1_rep1_x" and rows["1"]["verdict"] == ""
    total = rows["ALL"]
    assert total["n_seeds"] == "3" and total["n_seeds_dropped"] == "0"
    assert float(total["median_d_s"]) == 4.0 and float(total["iqr_d_s"]) == 2.0   # quartiles of [3, 4, 5]: 3 and 5
    assert float(total["diff_per_study_s"]) == 40.0 and float(total["sum_d_s"]) == 12.0
    assert float(total["agent_steps_median"]) == 1000.0
    assert float(total["d_us_per_agent_step"]) == pytest.approx(4000.0)
    assert total["verdict"] == "fix_first"


def test_paired_removal_tie_inside_the_iqr(tmp_path, monkeypatch):
    rows, _ = _removal_pair_rows(tmp_path, monkeypatch,
                                 _removal_pair_fixture(tmp_path, [30.5, 29.6, 30.3], [30.0, 30.0, 30.0]))
    total = rows["ALL"]
    assert float(total["median_d_s"]) == pytest.approx(0.3) and float(total["iqr_d_s"]) == pytest.approx(0.9)
    assert total["verdict"] == "tie"


def test_paired_removal_below_bar(tmp_path, monkeypatch):
    rows, _ = _removal_pair_rows(tmp_path, monkeypatch,
                                 _removal_pair_fixture(tmp_path, [31.0, 31.1, 31.2], [30.0, 30.0, 30.0]))
    total = rows["ALL"]
    assert float(total["diff_per_study_s"]) == pytest.approx(11.0) and total["verdict"] == "below_bar"


def test_paired_removal_drops_a_seed_with_one_arm_and_counts_it(tmp_path, monkeypatch):
    rows, ordered = _removal_pair_rows(tmp_path, monkeypatch,
                                      _removal_pair_fixture(tmp_path, [34.0, 36.0, 35.0], [30.0, 31.0, 32.0],
                                                            drop=(3, "nss")))
    assert [r["seed"] for r in ordered] == ["1", "2", "ALL"]
    assert rows["ALL"]["n_seeds"] == "2" and rows["ALL"]["n_seeds_dropped"] == "1"
    assert float(rows["ALL"]["median_d_s"]) == 4.5


def test_paired_removal_exclude_drops_the_excluded_rep(tmp_path, monkeypatch):
    raw = _removal_pair_fixture(tmp_path, [34.0, 36.0, 35.0], [30.0, 31.0, 32.0])
    rows, _ = _removal_pair_rows(tmp_path, monkeypatch, raw, exclude=["G6_nss_W1_W1_nss_s3_rep1_x"])
    assert rows["ALL"]["n_seeds"] == "2" and rows["ALL"]["n_seeds_dropped"] == "1"


def test_paired_removal_cli_guards(tmp_path, capsys):
    with pytest.raises(SystemExit):
        a.main(["--paired-removal", "G6_nss_W1", "--counters-block", "G6_ctr_W1", "--out", str(tmp_path)])
    assert "needs --arm" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        a.main(["--paired-removal", "G6_nss_W1", "--arm", "nss", "--out", str(tmp_path)])
    assert "needs --counters-block" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        a.main(["--counters", "G6_ctr_W1", "--arm", "nss", "--out", str(tmp_path)])
    assert "needs --paired-removal" in capsys.readouterr().err


def test_paired_removal_unknown_arm_exits_2(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(a, "RAW", _removal_pair_fixture(tmp_path, [34.0], [30.0]))
    for arm in ("O_norc", "foo"):
        rc = a.main(["--paired-removal", "G6_nss_W1", "--arm", arm, "--counters-block", "G6_ctr_W1",
                     "--out", str(tmp_path / "g6")])
        assert rc == 2 and "--arm must be one of" in capsys.readouterr().err


def _lookup_pair_fixture(tmp_path, base, arm, steps=1000, drop=None, differ=None,
                         block="G8_lk_W1", ctr="G8_ctr_W1", arm_name="nlk"):
    """Lookup block with per-seed walls (base[i] for O_norc, arm[i] for arm_name, seed i+1), the three output
    files of every rep on disk, plus a counters block (two reps per arm). drop=(seed, variant) leaves that
    rep out; differ=(seed, name) writes a different output file for the arm_name rep of that seed."""
    raw = tmp_path / "results" / "raw"
    for i, (wb, wa) in enumerate(zip(base, arm), 1):
        for variant, wall in (("O_norc", wb), (arm_name, wa)):
            if drop == (i, variant):
                continue
            rid = f"{block}_W1_{variant}_s{i}_rep1_x"
            out = tmp_path / "runs" / rid
            out.mkdir(parents=True)
            for name in a.LOOKUP_EQUALITY_FILES:
                other = differ == (i, name) and variant == arm_name
                (out / name).write_text(name + ("\nchanged\n" if other else "\n"))
            d = raw / rid
            d.mkdir(parents=True)
            man = _rm_manifest(rid, block, variant, wall, contaminated=(i == 1 and variant == arm_name),
                               termination="incomplete_time_limit")
            man.update({"seed": i, "outputs_dir": str(out)})
            (d / "manifest.json").write_text(json.dumps(man))
    for variant in ("O_norc", arm_name):
        for r in (1, 2):
            rid = f"{ctr}_W1_{variant}_ctr_s1_rep{r}_x"
            d = raw / rid
            d.mkdir(parents=True)
            man = _rm_manifest(rid, ctr, variant, 40.0, counters=True, termination="incomplete_time_limit")
            man["seed"] = 1
            (d / "manifest.json").write_text(json.dumps(man))
            (d / "counters.json").write_text(json.dumps(
                {"counters": {"agent_steps": steps, "iterations": 10},
                 "timers_s": {"loop_first_iterate_to_last_iterate_end": 30.0}}))
    return raw


def _lookup_rows(tmp_path, monkeypatch, raw, exclude=(), expect_rc=0, arm_name="nlk",
                 block="G8_lk_W1", ctr="G8_ctr_W1", out_name="g8"):
    monkeypatch.setattr(a, "RAW", raw)
    out = tmp_path / out_name
    argv = ["--paired-lookup", block, "--arm", arm_name, "--counters-block", ctr, "--out", str(out)]
    for rid in exclude:
        argv += ["--exclude", rid]
    assert a.main(argv) == expect_rc
    with open(out / f"paired_lookup_{block}_{arm_name}.csv") as fh:
        rows = list(csv.DictReader(fh))
    return {r["seed"]: r for r in rows}, rows


def test_paired_lookup_fix_first_by_hand(tmp_path, monkeypatch):
    rows, ordered = _lookup_rows(tmp_path, monkeypatch,
                                 _lookup_pair_fixture(tmp_path, [30.0, 31.0, 32.0], [34.0, 36.0, 35.0]))
    assert [r["seed"] for r in ordered] == ["1", "2", "3", "ALL"] and list(ordered[0]) == a.PAIRED_LOOKUP_COLUMNS
    assert [float(rows[s]["d_s"]) for s in "123"] == [4.0, 5.0, 3.0]          # wall(nlk) - wall(O_norc)
    assert rows["1"]["flagged_arm"] == "True" and rows["1"]["flagged_base"] == "False"
    assert all(rows[s]["outputs_equal"] == "True" for s in "123") and rows["1"]["verdict"] == ""
    assert rows["1"]["base_run_id"] == "G8_lk_W1_W1_O_norc_s1_rep1_x" and rows["1"]["arm_run_id"].endswith("nlk_s1_rep1_x")
    total = rows["ALL"]
    assert total["n_seeds"] == "3" and total["n_seeds_dropped"] == "0"
    assert float(total["median_d_s"]) == 4.0 and float(total["iqr_d_s"]) == 2.0   # quartiles of [3, 4, 5]: 3 and 5
    assert float(total["diff_per_study_s"]) == 40.0 and float(total["sum_d_s"]) == 12.0
    assert float(total["agent_steps_median"]) == 1000.0
    assert float(total["d_us_per_agent_step"]) == pytest.approx(4000.0)
    assert total["verdict"] == "fix_first"


def test_paired_lookup_differing_output_withholds_the_verdict(tmp_path, monkeypatch):
    raw = _lookup_pair_fixture(tmp_path, [30.0, 31.0, 32.0], [34.0, 36.0, 35.0], differ=(2, "fed.csv"))
    rows, _ = _lookup_rows(tmp_path, monkeypatch, raw, expect_rc=3)
    assert [rows[s]["outputs_equal"] for s in "123"] == ["True", "False", "True"]
    assert rows["ALL"]["verdict"] == "invalid_outputs_differ"


def test_paired_lookup_tie_inside_the_iqr(tmp_path, monkeypatch):
    rows, _ = _lookup_rows(tmp_path, monkeypatch,
                           _lookup_pair_fixture(tmp_path, [30.0, 30.0, 30.0], [30.5, 29.6, 30.3]))
    total = rows["ALL"]
    assert float(total["median_d_s"]) == pytest.approx(0.3) and float(total["iqr_d_s"]) == pytest.approx(0.9)
    assert total["verdict"] == "tie"


def test_paired_lookup_below_bar(tmp_path, monkeypatch):
    rows, _ = _lookup_rows(tmp_path, monkeypatch,
                           _lookup_pair_fixture(tmp_path, [30.0, 30.0, 30.0], [31.0, 31.1, 31.2]))
    total = rows["ALL"]
    assert float(total["diff_per_study_s"]) == pytest.approx(11.0) and total["verdict"] == "below_bar"


def test_paired_lookup_drops_a_seed_with_one_arm_and_counts_it(tmp_path, monkeypatch):
    rows, ordered = _lookup_rows(tmp_path, monkeypatch,
                                 _lookup_pair_fixture(tmp_path, [30.0, 31.0, 32.0], [34.0, 36.0, 35.0],
                                                      drop=(3, "nlk")))
    assert [r["seed"] for r in ordered] == ["1", "2", "ALL"]
    assert rows["ALL"]["n_seeds"] == "2" and rows["ALL"]["n_seeds_dropped"] == "1"
    assert float(rows["ALL"]["median_d_s"]) == 4.5


def test_paired_lookup_exclude_drops_the_excluded_rep(tmp_path, monkeypatch):
    raw = _lookup_pair_fixture(tmp_path, [30.0, 31.0, 32.0], [34.0, 36.0, 35.0])
    rows, _ = _lookup_rows(tmp_path, monkeypatch, raw, exclude=["G8_lk_W1_W1_nlk_s3_rep1_x"])
    assert rows["ALL"]["n_seeds"] == "2" and rows["ALL"]["n_seeds_dropped"] == "1"


def test_paired_lookup_cli_guards(tmp_path, capsys):
    with pytest.raises(SystemExit):
        a.main(["--paired-lookup", "G8_lk_W1", "--counters-block", "G8_ctr_W1", "--out", str(tmp_path)])
    assert "--paired-lookup needs --arm" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        a.main(["--paired-lookup", "G8_lk_W1", "--arm", "nlk", "--out", str(tmp_path)])
    assert "--paired-lookup needs --counters-block" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        a.main(["--counters", "G8_ctr_W1", "--arm", "nlk", "--out", str(tmp_path)])
    assert "--arm needs --paired-removal or --paired-lookup" in capsys.readouterr().err


def test_paired_lookup_unknown_arm_exits_2(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(a, "RAW", _lookup_pair_fixture(tmp_path, [30.0], [34.0]))
    rc = a.main(["--paired-lookup", "G8_lk_W1", "--arm", "nss", "--counters-block", "G8_ctr_W1",
                 "--out", str(tmp_path / "g8")])
    assert rc == 2 and "--arm must be nlk" in capsys.readouterr().err


def test_paired_lookup_accepts_the_prune_arm(tmp_path, monkeypatch):
    raw = _lookup_pair_fixture(tmp_path, [30.0, 31.0, 32.0], [34.0, 36.0, 35.0], arm_name="nrp",
                               block="G11_pr_W1", ctr="G11_ctr_W1")
    rows, ordered = _lookup_rows(tmp_path, monkeypatch, raw, arm_name="nrp", block="G11_pr_W1",
                                 ctr="G11_ctr_W1", out_name="g11")
    assert rows["1"]["arm_run_id"].endswith("nrp_s1_rep1_x") and rows["1"]["base_run_id"].startswith("G11_pr_W1_")
    assert float(rows["ALL"]["median_d_s"]) == 4.0 and rows["ALL"]["verdict"] == "fix_first"


def test_paired_lookup_prune_arm_differing_output_withholds_the_verdict(tmp_path, monkeypatch):
    raw = _lookup_pair_fixture(tmp_path, [30.0, 31.0, 32.0], [34.0, 36.0, 35.0], differ=(2, "exit.csv"),
                               arm_name="nrp", block="G11_pr_W1", ctr="G11_ctr_W1")
    rows, _ = _lookup_rows(tmp_path, monkeypatch, raw, arm_name="nrp", block="G11_pr_W1",
                           ctr="G11_ctr_W1", out_name="g11", expect_rc=3)
    assert rows["ALL"]["verdict"] == "invalid_outputs_differ"


def test_paired_lookup_rejects_an_arm_of_another_mode(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(a, "RAW", _lookup_pair_fixture(tmp_path, [30.0], [34.0]))
    rc = a.main(["--paired-lookup", "G8_lk_W1", "--arm", "nst", "--counters-block", "G8_ctr_W1",
                 "--out", str(tmp_path / "g11")])
    assert rc == 2 and "--arm must be nlk or nrp" in capsys.readouterr().err


def _frame(function, file_path, time, *children):
    return {"function": function, "file_path": file_path, "time": time, "children": list(children)}


def _reroute_root(reroute_s=30.0, second_call_s=None):
    """A profiled tree with both rerouting entry points; ``second_call_s`` adds a second
    call of the same evaluate_and_reroute > rank_routes path from another call site."""
    rg = "/stage/pyfds_evac/core/route_graph.py"
    rank = _frame("rank_routes", rg, reroute_s * 2 / 3,
                  _frame("evaluate_segment", rg, reroute_s * 0.4, _frame("tiny", rg, 0.5)))
    reroute = _frame("evaluate_and_reroute", rg, reroute_s, rank,
                     _frame("[self]", rg, 2.0), _frame("sum", "<built-in>", reroute_s - rank["time"] - 2.0))
    sc = "/stage/pyfds_evac/core/scenario.py"
    initial = _frame("_assign_initial_exit", sc, 5.0, _frame("rank_routes", rg, 3.0))
    callers = [_frame("_reevaluate", sc, reroute_s, reroute), _frame("_initial_exit_choice", sc, 5.0, initial)]
    if second_call_s:
        callers.append(_frame("_other", sc, second_call_s,
                              _frame("evaluate_and_reroute", rg, second_call_s,
                                     _frame("rank_routes", rg, second_call_s))))
    return _frame("<root>", "", 100.0, _frame("run", "run.py", 100.0, *callers))


def _tree_fixture(tmp_path, monkeypatch, profiled, plain=(40.0,), block="T"):
    """profiled: list of (wall_s, root_frame[, termination]); plain: wall_s per plain rep."""
    raw = tmp_path / "results" / "raw"
    runs = [(f"{block}_pyi_{i}", "pyinstrument", item[0], item[2] if len(item) > 2 else "completed", item[1])
            for i, item in enumerate(profiled, 1)]
    runs += [(f"{block}_plain_{i}", "none", wall, "completed", None) for i, wall in enumerate(plain, 1)]
    for rid, prof, wall, termination, root in runs:
        d = raw / rid
        d.mkdir(parents=True)
        manifest = _manifest(rid, block, prof, wall)
        manifest.update({"variant": "O_norc", "termination": termination})
        (d / "manifest.json").write_text(json.dumps(manifest))
        if root is not None:
            (d / "pyinstrument.json").write_text(json.dumps({"root_frame": root}))
    monkeypatch.setattr(a, "RAW", raw)
    return raw


def _tree_rows(tmp_path, monkeypatch, profiled, plain=(40.0,), exclude=()):
    _tree_fixture(tmp_path, monkeypatch, profiled, plain)
    path = a.reroute_tree_table("T", tmp_path / "g13", exclude=exclude)
    assert path == tmp_path / "g13" / "reroute_tree_T.csv"
    with open(path) as fh:
        reader = csv.DictReader(fh)
        assert reader.fieldnames == a.REROUTE_TREE_COLUMNS
        return {(r["entry"], r["path"]): r for r in reader}


def test_reroute_tree_rows_and_scaling(tmp_path, monkeypatch):
    rows = _tree_rows(tmp_path, monkeypatch, [(100.0, _reroute_root()), (100.0, _reroute_root())])
    first = "evaluate_and_reroute"
    expected = {(first, first): (12.0, 120.0, "above_bar"),
                (first, f"{first} > rank_routes"): (8.0, 80.0, "above_bar"),
                (first, f"{first} > rank_routes > evaluate_segment"): (4.8, 48.0, "above_bar"),
                ("_assign_initial_exit", "_assign_initial_exit"): (2.0, 20.0, "below_bar"),
                ("_assign_initial_exit", "_assign_initial_exit > rank_routes"): (1.2, 12.0, "below_bar")}
    assert list(rows) == list(expected)
    for key, (cost, study, verdict) in expected.items():
        assert float(rows[key]["cost_plain_s"]) == pytest.approx(cost)
        assert float(rows[key]["cost_per_study_s"]) == pytest.approx(study)
        assert rows[key]["verdict"] == verdict
    top = rows[(first, first)]
    assert (top["depth"], top["file"], top["n_profiled"], top["n_plain"]) == ("0", "route_graph.py", "2", "1")
    assert float(top["cum_s"]) == pytest.approx(30.0) and float(top["share_profiled"]) == pytest.approx(0.3)
    # own time = the [self] child (2 s) plus the <built-in> child (8 s); neither is a row
    assert float(top["self_s"]) == pytest.approx(10.0)
    assert float(top["profiled_wall_s"]) == 100.0 and float(top["plain_wall_s"]) == 40.0
    assert not any("tiny" in path or "[self]" in path or "sum" in path for _, path in rows)


def test_reroute_tree_sums_repeated_call_paths_and_takes_medians(tmp_path, monkeypatch):
    rows = _tree_rows(tmp_path, monkeypatch, [(100.0, _reroute_root(reroute_s=10.0 + 10 * i, second_call_s=1.0))
                                              for i in range(3)])
    # evaluate_and_reroute is reached from two call sites: 10+1, 20+1, 30+1 -> median 21
    top = rows[("evaluate_and_reroute", "evaluate_and_reroute")]
    assert float(top["cum_s"]) == pytest.approx(21.0)
    ranked = rows[("evaluate_and_reroute", "evaluate_and_reroute > rank_routes")]
    assert float(ranked["cum_s"]) == pytest.approx(20 * 2 / 3 + 1.0)
    assert float(top["agreement_pts"]) == pytest.approx(20.0)


def test_reroute_tree_excludes_a_named_rep_and_ignores_unusable_terminations(tmp_path, monkeypatch):
    profiled = [(100.0, _reroute_root(10.0)), (100.0, _reroute_root(30.0)), (100.0, _reroute_root(50.0), "failed")]
    rows = _tree_rows(tmp_path, monkeypatch, profiled)
    assert rows[("evaluate_and_reroute", "evaluate_and_reroute")]["n_profiled"] == "2"
    assert float(rows[("evaluate_and_reroute", "evaluate_and_reroute")]["cum_s"]) == pytest.approx(20.0)
    rows = _tree_rows(tmp_path / "x", monkeypatch, profiled[:2], exclude=["T_pyi_1"])
    assert rows[("evaluate_and_reroute", "evaluate_and_reroute")]["n_profiled"] == "1"
    assert float(rows[("evaluate_and_reroute", "evaluate_and_reroute")]["cum_s"]) == pytest.approx(30.0)


def test_reroute_tree_errors_and_cli(tmp_path, monkeypatch, capsys):
    _tree_fixture(tmp_path / "none", monkeypatch, [], plain=(40.0,))
    assert a.main(["--reroute-tree", "T", "--out", str(tmp_path / "o")]) == 2
    assert "no usable profiled" in capsys.readouterr().err
    _tree_fixture(tmp_path / "noplain", monkeypatch, [(100.0, _reroute_root())], plain=())
    assert a.main(["--reroute-tree", "T", "--out", str(tmp_path / "o")]) == 2
    assert "no plain rep" in capsys.readouterr().err
    _tree_fixture(tmp_path / "noentry", monkeypatch, [(100.0, _frame("<root>", "", 100.0))])
    assert a.main(["--reroute-tree", "T", "--out", str(tmp_path / "o")]) == 2
    assert "no frame matches" in capsys.readouterr().err
    _tree_fixture(tmp_path / "ok", monkeypatch, [(100.0, _reroute_root())])
    assert a.main(["--reroute-tree", "T", "--out", str(tmp_path / "o")]) == 0
    assert (tmp_path / "o" / "reroute_tree_T.csv").exists()
    assert a.main(["--reroute-tree", "T", "--out", str(tmp_path / "o"), "--exclude", "nope"]) == 2
    assert "match no rep" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        a.main(["--block", "T", "--exclude", "x", "--out", str(tmp_path / "o")])
    assert "--reroute-tree" in capsys.readouterr().err


def test_reroute_tree_plain_reps_honour_exclude_and_termination(tmp_path, monkeypatch):
    rows = _tree_rows(tmp_path, monkeypatch, [(100.0, _reroute_root())], plain=(40.0, 60.0, 80.0),
                      exclude=["T_plain_2"])
    top = rows[("evaluate_and_reroute", "evaluate_and_reroute")]
    assert (top["n_plain"], float(top["plain_wall_s"])) == ("2", 60.0)
    raw = _tree_fixture(tmp_path / "failed", monkeypatch, [(100.0, _reroute_root())], plain=(40.0, 60.0, 80.0))
    manifest = raw / "T_plain_3" / "manifest.json"
    manifest.write_text(json.dumps({**json.loads(manifest.read_text()), "termination": "failed"}))
    path = a.reroute_tree_table("T", tmp_path / "failed" / "g13")
    with open(path) as fh:
        top = next(csv.DictReader(fh))
    assert (top["n_plain"], float(top["plain_wall_s"])) == ("2", 50.0)


def test_reroute_tree_frame_below_both_entry_points_has_a_row_under_each(tmp_path, monkeypatch):
    rg, sc = "/stage/pyfds_evac/core/route_graph.py", "/stage/pyfds_evac/core/scenario.py"
    shared = _frame("rank_routes", rg, 4.0)
    nested = _frame("evaluate_and_reroute", rg, 10.0, _frame("_assign_initial_exit", sc, 6.0, shared))
    rows = _tree_rows(tmp_path, monkeypatch, [(100.0, _frame("<root>", "", 100.0, nested))])
    first, second = "evaluate_and_reroute", "_assign_initial_exit"
    assert list(rows) == [(first, first), (first, f"{first} > {second}"), (first, f"{first} > {second} > rank_routes"),
                          (second, second), (second, f"{second} > rank_routes")]
    assert float(rows[(first, f"{first} > {second} > rank_routes")]["cum_s"]) == pytest.approx(4.0)
    assert float(rows[(second, f"{second} > rank_routes")]["cum_s"]) == pytest.approx(4.0)
    assert rows[(second, second)]["depth"] == "0" and rows[(first, f"{first} > {second}")]["depth"] == "1"


def test_reroute_tree_nested_instance_of_an_entry_starts_no_second_subtree(tmp_path, monkeypatch):
    rg = "/stage/pyfds_evac/core/route_graph.py"
    inner = _frame("evaluate_and_reroute", rg, 6.0, _frame("rank_routes", rg, 5.0))
    outer = _frame("evaluate_and_reroute", rg, 20.0, _frame("rank_routes", rg, 8.0, inner))
    rows = _tree_rows(tmp_path, monkeypatch, [(100.0, _frame("<root>", "", 100.0, outer))])
    first = "evaluate_and_reroute"
    depth0 = [key for key, row in rows.items() if row["depth"] == "0"]
    assert depth0 == [(first, first)] and float(rows[(first, first)]["cum_s"]) == pytest.approx(20.0)
    assert float(rows[(first, f"{first} > rank_routes > {first}")]["cum_s"]) == pytest.approx(6.0)
    assert (first, f"{first} > rank_routes > {first} > rank_routes") in rows
    assert (first, f"{first} > rank_routes") in rows and float(rows[(first, f"{first} > rank_routes")]["cum_s"]) == 8.0


def test_reroute_tree_absent_path_counts_as_zero_in_median_and_filter(tmp_path, monkeypatch):
    rg = "/stage/pyfds_evac/core/route_graph.py"
    with_extra = _frame("evaluate_and_reroute", rg, 30.0, _frame("extra", rg, 5.0))
    without = _frame("evaluate_and_reroute", rg, 30.0)
    key = ("evaluate_and_reroute", "evaluate_and_reroute > extra")
    two = [(100.0, _frame("<root>", "", 100.0, root)) for root in (with_extra, without)]
    rows = _tree_rows(tmp_path, monkeypatch, two)
    assert float(rows[key]["cum_s"]) == pytest.approx(2.5) and float(rows[key]["share_profiled"]) == pytest.approx(0.025)
    three = two + [two[1]]
    assert key not in _tree_rows(tmp_path / "x", monkeypatch, three)


def test_reroute_tree_siblings_order_by_cum_s_descending(tmp_path, monkeypatch):
    rg = "/stage/pyfds_evac/core/route_graph.py"
    root = _frame("evaluate_and_reroute", rg, 40.0,
                  _frame("small", rg, 5.0, _frame("leaf_a", rg, 3.0)), _frame("big", rg, 20.0, _frame("leaf_b", rg, 2.0)),
                  _frame("mid", rg, 9.0))
    rows = _tree_rows(tmp_path, monkeypatch, [(100.0, _frame("<root>", "", 100.0, root))])
    first = "evaluate_and_reroute"
    assert [path for _, path in rows] == [first] + [f"{first} > {p}" for p in
                                                    ("big", "big > leaf_b", "mid", "small", "small > leaf_a")]


def test_reroute_tree_notes_a_single_profiled_rep(tmp_path, monkeypatch, capsys):
    _tree_rows(tmp_path, monkeypatch, [(100.0, _reroute_root())])
    assert "one profiled rep, agreement not assessable" in capsys.readouterr().err


def _ceiling_tree(tmp_path, drop=None):
    """A G13-style tree CSV: _first_leg on three paths (10 + 15 + 8 s) and one nested under itself (3 s)."""
    rows = [("a > _first_leg", "_first_leg", 10.0), ("a > b > _first_leg", "_first_leg", 15.0),
            ("a > c > _first_leg", "_first_leg", 8.0), ("a > _first_leg > x > _first_leg", "_first_leg", 3.0),
            ("a > d > _first_leg_dose", "_first_leg_dose", 14.5), ("a > e > evaluate_segment", "evaluate_segment", 20.5)]
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "tree.csv"
    with open(path, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["entry", "path", "depth", "function", "file", "cost_per_study_s", "verdict"])
        for tree_path, function, cost in rows:
            if function != drop:
                writer.writerow(["a", tree_path, 1, function, "route_graph.py", cost, "below_bar"])
    return path


def _ceiling_fixture(tmp_path, counts, drop=None):
    """G14_cnt_W1: one detail run per seed; counts[seed][path] = (total, distinct)."""
    raw = tmp_path / "results" / "raw"
    for seed, paths in counts.items():
        run_id = f"G14_cnt_W1_s{seed}"
        (raw / run_id).mkdir(parents=True)
        counters = raw / run_id / "counters.json"
        route_paths = {p: {"total": t, "distinct": d, "capped": False}
                       for p, (t, d) in paths.items() if p != drop}
        counters.write_text(json.dumps({"detail": {"route_paths": route_paths}}))
        (raw / run_id / "manifest.json").write_text(json.dumps({
            "run_id": run_id, "block": "G14_cnt_W1", "role": "rep", "seed": seed,
            "termination": "incomplete_time_limit", "counters_path": str(counters)}))
    return raw


CEILING_COUNTS = {
    1: {"first_leg": (1000, 400), "first_leg_dose": (500, 100), "segment": (200, 20),
        "first_leg_r01": (1000, 500)},
    2: {"first_leg": (1000, 200), "first_leg_dose": (500, 100), "segment": (200, 20),
        "first_leg_r01": (1000, 500)},
}


def _ceiling_rows(tmp_path, monkeypatch, counts=None, exclude=()):
    monkeypatch.setattr(a, "RAW", _ceiling_fixture(tmp_path, counts or CEILING_COUNTS))
    out = tmp_path / "g14"
    argv = ["--repeat-ceiling", "G14_cnt_W1", "--tree", str(_ceiling_tree(tmp_path)), "--out", str(out)]
    for run_id in exclude:
        argv += ["--exclude", run_id]
    assert a.main(argv) == 0
    with open(out / "repeat_ceiling_G14_cnt_W1.csv") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)
    assert reader.fieldnames == a.REPEAT_CEILING_COLUMNS
    return rows


def test_repeat_ceiling_rows_and_arithmetic(tmp_path, monkeypatch):
    rows = _ceiling_rows(tmp_path, monkeypatch)
    assert [(r["seed"], r["path"]) for r in rows] == [
        (str(s), p) for s in (1, 2) for p in a.REPEAT_PATHS]
    by = {(r["seed"], r["path"]): r for r in rows}
    first = by[("1", "first_leg")]
    assert (first["total"], first["distinct"], first["capped"]) == ("1000", "400", "False")
    assert float(first["hit_share"]) == pytest.approx(0.6)
    assert float(first["cost_per_study_s"]) == pytest.approx(33.0)
    assert float(first["ceiling_per_study_s"]) == pytest.approx(19.8)
    assert first["verdict"] == "below_bar"
    assert float(by[("1", "first_leg_dose")]["ceiling_per_study_s"]) == pytest.approx(11.6)
    assert float(by[("1", "segment")]["ceiling_per_study_s"]) == pytest.approx(18.45)
    assert float(by[("2", "first_leg")]["ceiling_per_study_s"]) == pytest.approx(26.4)
    assert by[("2", "first_leg")]["verdict"] == "above_bar"
    r01 = by[("1", "first_leg_r01")]
    assert r01["verdict"] == "info" and float(r01["cost_per_study_s"]) == pytest.approx(33.0)


def test_repeat_ceiling_exclude_and_errors(tmp_path, monkeypatch, capsys):
    rows = _ceiling_rows(tmp_path / "ex", monkeypatch, exclude=["G14_cnt_W1_s2"])
    assert {r["seed"] for r in rows} == {"1"} and len(rows) == 4
    zero = {1: {**CEILING_COUNTS[1], "segment": (0, 0)}}
    by = {r["path"]: r for r in _ceiling_rows(tmp_path / "zero", monkeypatch, zero)}
    assert by["segment"]["hit_share"] == "" and by["segment"]["ceiling_per_study_s"] == ""
    tree = _ceiling_tree(tmp_path)
    monkeypatch.setattr(a, "RAW", _ceiling_fixture(tmp_path / "miss", CEILING_COUNTS, drop="first_leg_dose"))
    argv = ["--repeat-ceiling", "G14_cnt_W1", "--tree", str(tree), "--out", str(tmp_path / "o")]
    assert a.main(argv) == 2
    assert "first_leg_dose" in capsys.readouterr().err
    monkeypatch.setattr(a, "RAW", _ceiling_fixture(tmp_path / "tree", CEILING_COUNTS))
    no_segment = _ceiling_tree(tmp_path / "ns", drop="evaluate_segment")
    argv = ["--repeat-ceiling", "G14_cnt_W1", "--tree", str(no_segment), "--out", str(tmp_path / "o")]
    assert a.main(argv) == 2
    assert "evaluate_segment" in capsys.readouterr().err


def test_repeat_ceiling_cli_guards(tmp_path, monkeypatch, capsys):
    tree = str(_ceiling_tree(tmp_path))
    with pytest.raises(SystemExit) as exc:
        a.main(["--repeat-ceiling", "G14_cnt_W1", "--out", str(tmp_path)])
    assert exc.value.code == 2 and "--repeat-ceiling needs --tree" in capsys.readouterr().err
    with pytest.raises(SystemExit) as exc:
        a.main(["--counters", "C", "--tree", tree, "--out", str(tmp_path)])
    assert exc.value.code == 2 and "--tree needs --repeat-ceiling" in capsys.readouterr().err
    monkeypatch.setattr(a, "RAW", _ceiling_fixture(tmp_path, CEILING_COUNTS))
    assert a.main(["--repeat-ceiling", "G14_cnt_W1", "--tree", tree, "--out", str(tmp_path / "o")]) == 0
    assert (tmp_path / "o" / "repeat_ceiling_G14_cnt_W1.csv").exists()


def test_repeat_ceiling_unreadable_tree_exits_2(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(a, "RAW", _ceiling_fixture(tmp_path, CEILING_COUNTS))
    wrong = tmp_path / "wrong.csv"
    wrong.write_text("function,calls\n_first_leg,3\n")
    for tree in (tmp_path / "missing.csv", wrong):
        argv = ["--repeat-ceiling", "G14_cnt_W1", "--tree", str(tree), "--out", str(tmp_path / "o")]
        assert a.main(argv) == 2
        assert str(tree) in capsys.readouterr().err
