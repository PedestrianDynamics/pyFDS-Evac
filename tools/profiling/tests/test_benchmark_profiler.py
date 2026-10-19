"""benchmark.py: profiler list, run-id tags, command heads (Task 1 of the G2 plan)."""
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

WT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WT))
import benchmark as b  # noqa: E402

PY = "/Users/chraibi/profiling-stage/wt_8f7d29a2/.venv/bin/python"
PROF_PY = "/Users/chraibi/profiling-stage/venv_prof_8f7d29a2/bin/python"


def _args(**kw):
    base = dict(py=PY, prof_py=PROF_PY, stage="/Users/chraibi/profiling-stage",
                capture_result=False, case="W1")
    base.update(kw)
    return SimpleNamespace(**base)


@pytest.mark.parametrize("prof,tag", [("none", ""), ("pyinstrument", "_pyi"), ("cprofile", "_cpr"),
                                      ("scalene", "_scl"), ("memray", "_mem")])
def test_profiler_tag(prof, tag):
    assert b.profiler_tag(prof) == tag


def test_profilers_constant():
    assert b.PROFILERS == ("none", "cprofile", "pyinstrument", "scalene", "memray")


def test_build_command_heads(tmp_path):
    case = b.CASES["W1"]
    plain = b.build_command(_args(), case, "O_study", 1, tmp_path, tmp_path, None, None,
                            profiler="none")
    assert plain[4] == PY and plain[5] == "run.py"
    prof = b.build_command(_args(), case, "O_study", 1, tmp_path, tmp_path, None, None,
                           profiler="pyinstrument")
    assert prof[4] == PROF_PY and prof[5:8] == ["-m", "pyinstrument", "-r"]
    assert prof[prof.index("-p") + 1] == "processor_options.filter_threshold=0"
    assert "-p" not in plain
    cpr = b.build_command(_args(), case, "O_study", 1, tmp_path, tmp_path, None, None,
                          profiler="cprofile")
    assert cpr[5:7] == ["-m", "cProfile"]


def test_dry_run_interleaves_plain_and_profiled():
    out = subprocess.run([PY, "benchmark.py", "run", "--dry-run", "--shared", "--block", "T",
                          "--case", "W1", "--warmup", "0", "--reps", "1",
                          "--profiler", "none,pyinstrument"], cwd=WT, capture_output=True,
                         text=True, check=True).stdout
    ids = [doc["run_id"] for doc in _run_objects(out)]
    assert len(ids) == 2
    assert ids[0].startswith("T_W1_O_study_s1_rep1_")
    assert ids[1].startswith("T_W1_O_study_pyi_s1_rep1_")


def _run_objects(text):
    """Decode the per-run JSON objects of the dry-run stdout.

    The slot line printed first is cut at 600 characters and is not valid JSON, so decoding
    starts at each line that opens an object with a run_id.
    """
    decoder, docs, pos = json.JSONDecoder(), [], 0
    while (start := text.find('{\n "run_id"', pos)) != -1:
        doc, pos = decoder.raw_decode(text, start)
        docs.append(doc)
    return docs


def test_w1_nrr_command_switches_rerouting_off_only(tmp_path):
    norc = b.build_command(_args(), b.CASES["W1"], "O_norc", 1, tmp_path, tmp_path, None, None,
                           profiler="none")
    nrr = b.build_command(_args(), b.CASES["W1"], "nrr", 1, tmp_path, tmp_path,
                          None, None, profiler="none")
    assert "--no-enable-rerouting" in nrr and "--no-enable-rerouting" not in norc
    assert [a for a in nrr if a != "--no-enable-rerouting"] == norc


def test_w1_norc_and_nrr_arms_share_one_abba_block():
    out = subprocess.run([PY, "benchmark.py", "run", "--dry-run", "--shared", "--block", "T",
                          "--case", "W1", "--variants", "O_norc,nrr", "--order", "abba",
                          "--warmup", "0", "--reps", "2"], cwd=WT, capture_output=True,
                         text=True, check=True).stdout
    arms = [doc["run_id"].split("_s1_")[0] for doc in _run_objects(out)]
    assert arms == ["T_W1_O_norc", "T_W1_nrr", "T_W1_nrr", "T_W1_O_norc"]


def test_plain_command_and_env_unchanged_without_wrapper(tmp_path):
    cmd = b.build_command(_args(), b.CASES["W1"], "O_norc", 1, tmp_path, tmp_path, None, None,
                          profiler="none")
    assert cmd[4:6] == [PY, "run.py"]
    env = b.child_env("/Users/chraibi/profiling-stage", "rid", None, None, False)
    assert "PYFDS_PERF_STUB" not in env


def test_via_wrapper_head_and_stub_env(tmp_path):
    cmd = b.build_command(_args(), b.CASES["W1"], "nss", 1, tmp_path, tmp_path, None, None,
                          profiler="none", via_wrapper=True)
    assert cmd[4] == PY and cmd[5].endswith("instrument/perf_run.py")
    assert "--no-enable-rerouting" not in cmd
    env = b.child_env("/Users/chraibi/profiling-stage", "rid", None, None, False,
                      stub_env=b.CASES["W1"]["variant_env"]["nst"])
    assert env["PYFDS_PERF_STUB"] == "nst"


def test_stub_variant_without_wrapper_is_refused():
    r = subprocess.run([PY, "benchmark.py", "run", "--dry-run", "--shared", "--block", "T",
                        "--case", "W1", "--variants", "O_norc,nss", "--warmup", "0", "--reps", "1"],
                       cwd=WT, capture_output=True, text=True)
    assert r.returncode == 1 and "stub variants need --via-wrapper: nss" in r.stderr


def test_stub_arms_share_the_norc_output_set(tmp_path):
    norc = b.build_command(_args(), b.CASES["W1"], "O_norc", 1, tmp_path, tmp_path, None, None,
                           profiler="none", via_wrapper=True)
    for arm in ("nss", "nst"):
        cmd = b.build_command(_args(), b.CASES["W1"], arm, 1, tmp_path, tmp_path, None, None,
                              profiler="none", via_wrapper=True)
        assert cmd[4:] == norc[4:]


def test_via_wrapper_with_profiler_is_refused():
    r = subprocess.run([PY, "benchmark.py", "run", "--dry-run", "--shared", "--block", "T",
                        "--case", "W1", "--variants", "nss", "--via-wrapper", "--profiler",
                        "cprofile", "--warmup", "0", "--reps", "1"],
                       cwd=WT, capture_output=True, text=True)
    assert r.returncode == 1 and "--via-wrapper and profilers are separate runs" in r.stderr


def test_nss_description_states_route_line_of_sight_still_reads_slice():
    for path in ("instrument/perf_run.py", "README.md"):
        assert "line-of-sight still reads the slice" in (WT / path).read_text()


def test_four_arms_interleave_abba_and_record_stubs():
    out = subprocess.run([PY, "benchmark.py", "run", "--dry-run", "--shared", "--block", "T",
                          "--case", "W1", "--variants", "O_norc,nrr,nss,nst", "--via-wrapper",
                          "--order", "abba", "--warmup", "0", "--reps", "2"], cwd=WT,
                         capture_output=True, text=True, check=True).stdout
    docs = list(_run_objects(out))
    arms = [d["run_id"].split("_s1_")[0] for d in docs]
    assert arms == ["T_W1_O_norc", "T_W1_nrr", "T_W1_nss", "T_W1_nst",
                    "T_W1_nst", "T_W1_nss", "T_W1_nrr", "T_W1_O_norc"]
    assert all(d["command"][5].endswith("instrument/perf_run.py") for d in docs)
    stubs = [d.get("stubs", d.get("instrumentation", {}).get("stubs")) for d in docs]
    assert stubs[:4] == [[], [], ["nss"], ["nst"]]


STAGE_WT = "/Users/chraibi/profiling-stage/wt_d96894ac"
STAGE_PY = STAGE_WT + "/.venv/bin/python"


def test_stage_pin_known_and_unknown():
    assert b.stage_pin(STAGE_WT) == {"commit": b.MAIN_COMMIT, "uv_lock_sha256": b.LOCK_SHA256}
    assert b.stage_pin("/Users/chraibi/profiling-stage/wt_29f9d3a5") == {"commit": b.FIX_COMMIT, "uv_lock_sha256": b.LOCK_SHA256}
    assert b.stage_pin("/Users/chraibi/profiling-stage/wt_8f7d29a2")["commit"] == b.COMMIT
    assert b.stage_pin("/Users/chraibi/profiling-stage/wt_b6dff31c") == {"commit": b.MAIN2_COMMIT, "uv_lock_sha256": b.LOCK_SHA256}
    assert b.stage_pin("/nowhere/wt_deadbeef") == {"commit": None, "uv_lock_sha256": None}


def test_main_stage_dry_run_is_accepted():
    out = subprocess.run([PY, "benchmark.py", "run", "--dry-run", "--shared", "--block", "T",
                          "--case", "W1", "--variants", "O_norc", "--warmup", "0", "--reps", "1",
                          "--wt", STAGE_WT, "--py", STAGE_PY], cwd=WT, capture_output=True,
                         text=True, check=True).stdout
    docs = list(_run_objects(out))
    assert len(docs) == 1 and docs[0]["command"][4] == STAGE_PY
    ws = b.worktree_state(STAGE_WT)
    assert ws["stage"] == "wt_d96894ac" and ws["commit_ok"] and ws["lock_ok"] and ws["clean"]
    assert ws["commit"] == b.MAIN_COMMIT


MAIN2_WT = "/Users/chraibi/profiling-stage/wt_b6dff31c"
MAIN2_PY = MAIN2_WT + "/.venv/bin/python"


def test_main2_stage_dry_run_is_accepted():
    out = subprocess.run([PY, "benchmark.py", "run", "--dry-run", "--shared", "--block", "T",
                          "--case", "W1", "--variants", "O_norc", "--warmup", "0", "--reps", "1",
                          "--wt", MAIN2_WT, "--py", MAIN2_PY], cwd=WT, capture_output=True,
                         text=True, check=True).stdout
    docs = list(_run_objects(out))
    assert len(docs) == 1 and docs[0]["command"][4] == MAIN2_PY
    ws = b.worktree_state(MAIN2_WT)
    assert ws["stage"] == "wt_b6dff31c" and ws["commit_ok"] and ws["lock_ok"] and ws["clean"]
    assert ws["commit"] == b.MAIN2_COMMIT


LOOKUP_WT = "/Users/chraibi/profiling-stage/wt_62106002"
LOOKUP_PY = LOOKUP_WT + "/.venv/bin/python"


def test_stage_pin_lookup_stage():
    assert b.LOOKUP_COMMIT == "621060020b840bff8e7caa5ca82879f31cfcaf5b"
    assert b.stage_pin(LOOKUP_WT) == {"commit": b.LOOKUP_COMMIT, "uv_lock_sha256": b.LOCK_SHA256}
    ws = b.worktree_state(LOOKUP_WT)
    assert ws["stage"] == "wt_62106002" and ws["commit_ok"] and ws["lock_ok"] and ws["clean"]


def test_nlk_without_wrapper_is_refused():
    r = subprocess.run([PY, "benchmark.py", "run", "--dry-run", "--shared", "--block", "T",
                        "--case", "W1", "--variants", "O_norc,nlk", "--warmup", "0", "--reps", "1"],
                       cwd=WT, capture_output=True, text=True)
    assert r.returncode == 1 and "stub variants need --via-wrapper: nlk" in r.stderr


def test_lookup_stage_dry_run_pairs_norc_and_nlk():
    out = subprocess.run([PY, "benchmark.py", "run", "--dry-run", "--shared", "--block", "T",
                          "--case", "W1", "--variants", "O_norc,nlk", "--via-wrapper", "--seeds", "1,2",
                          "--order", "abba", "--warmup", "0", "--reps", "1",
                          "--wt", LOOKUP_WT, "--py", LOOKUP_PY], cwd=WT,
                         capture_output=True, text=True, check=True).stdout
    docs = list(_run_objects(out))
    assert [d["run_id"].split("_rep1_")[0] for d in docs] == [
        "T_W1_O_norc_s1", "T_W1_nlk_s1", "T_W1_nlk_s2", "T_W1_O_norc_s2"]
    assert all(d["command"][4] == LOOKUP_PY and d["command"][5].endswith("instrument/perf_run.py") for d in docs)
    stubs = [d.get("stubs", d.get("instrumentation", {}).get("stubs")) for d in docs]
    assert stubs == [[], ["nlk"], ["nlk"], []]


PRUNE_WT = "/Users/chraibi/profiling-stage/wt_f7efcf9b"
PRUNE_PY = PRUNE_WT + "/.venv/bin/python"


def test_stage_pin_prune_stage():
    assert b.PRUNE_COMMIT == "f7efcf9b25b9fa9dcc001836437c2959e3a906d3"
    assert b.stage_pin(PRUNE_WT) == {"commit": b.PRUNE_COMMIT, "uv_lock_sha256": b.LOCK_SHA256}
    ws = b.worktree_state(PRUNE_WT)
    assert ws["stage"] == "wt_f7efcf9b" and ws["commit_ok"] and ws["lock_ok"] and ws["clean"]


def test_nrp_without_wrapper_is_refused():
    r = subprocess.run([PY, "benchmark.py", "run", "--dry-run", "--shared", "--block", "T",
                        "--case", "W1", "--variants", "O_norc,nrp", "--warmup", "0", "--reps", "1"],
                       cwd=WT, capture_output=True, text=True)
    assert r.returncode == 1 and "stub variants need --via-wrapper: nrp" in r.stderr


def test_prune_stage_dry_run_pairs_norc_and_nrp():
    out = subprocess.run([PY, "benchmark.py", "run", "--dry-run", "--shared", "--block", "T",
                          "--case", "W1", "--variants", "O_norc,nrp", "--via-wrapper", "--seeds", "1,2",
                          "--order", "abba", "--warmup", "0", "--reps", "1",
                          "--wt", PRUNE_WT, "--py", PRUNE_PY], cwd=WT,
                         capture_output=True, text=True, check=True).stdout
    docs = list(_run_objects(out))
    assert [d["run_id"].split("_rep1_")[0] for d in docs] == [
        "T_W1_O_norc_s1", "T_W1_nrp_s1", "T_W1_nrp_s2", "T_W1_O_norc_s2"]
    assert all(d["command"][4] == PRUNE_PY and d["command"][5].endswith("instrument/perf_run.py") for d in docs)
    stubs = [d.get("stubs", d.get("instrumentation", {}).get("stubs")) for d in docs]
    assert stubs == [[], ["nrp"], ["nrp"], []]


def test_w1_nomemo_arm_uses_derived_scenario_and_norc_outputs(tmp_path):
    case = b.CASES["W1"]
    memo = b.build_command(_args(), case, "O_norc", 1, tmp_path, tmp_path, None, None)
    nomemo = b.build_command(_args(), case, "nomemo", 1, tmp_path, tmp_path, None, None)
    assert memo[memo.index("--scenario") + 1] == "assets/schroeder2015_route/evac/config_gate.json"
    assert nomemo[nomemo.index("--scenario") + 1] == str(b.STUDY / "scenarios/w1_nomemo/config_gate.json")
    strip = lambda c: [a for a in c if not a.endswith("config_gate.json")]  # noqa: E731
    assert strip(memo) == strip(nomemo)
    assert "nomemo" in case["variants"] and "--no-enable-rerouting" not in nomemo


def test_w1_nomemo_scenario_differs_only_in_the_flag():
    base = json.loads((Path(STAGE_WT) / "assets/schroeder2015_route/evac/config_gate.json").read_text())
    derived = json.loads((WT / "scenarios/w1_nomemo/config_gate.json").read_text())
    assert derived["routing"]["fed_rate_memo"] is False
    base["routing"]["fed_rate_memo"] = False
    assert derived == base
    assert (WT / "scenarios/w1_nomemo/geometry.wkt").read_bytes() == \
        (Path(STAGE_WT) / "assets/schroeder2015_route/evac/geometry.wkt").read_bytes()


def test_order_flip_reverses_the_first_rep():
    combos = [("A", "none", "none"), ("B", "none", "none")]
    assert [c[0][0] for c in b.order(combos, 1, "abba")] == ["A", "B"]
    assert [c[0][0] for c in b.order(combos, 1, "abba", flip=True)] == ["B", "A"]
    assert [c[0][0] for c in b.order(combos, 2, "abba", flip=True)] == ["B", "A", "A", "B"]
    assert [c[0][0] for c in b.order(combos, 2, "alternate", flip=True)] == ["A", "B", "A", "B"]


def test_abba_alternates_the_arm_order_across_seeds():
    out = subprocess.run([PY, "benchmark.py", "run", "--dry-run", "--shared", "--block", "T",
                          "--case", "W1", "--variants", "O_norc,nomemo", "--seeds", "1,2,3",
                          "--order", "abba", "--warmup", "0", "--reps", "1",
                          "--wt", STAGE_WT, "--py", STAGE_PY], cwd=WT, capture_output=True,
                         text=True, check=True).stdout
    ids = [d["run_id"] for d in _run_objects(out)]
    arms = [i.split("_W1_")[1].split("_s")[0] for i in ids]
    seeds = [i.split("_s")[1].split("_")[0] for i in ids]
    assert arms == ["O_norc", "nomemo", "nomemo", "O_norc", "O_norc", "nomemo"]
    assert seeds == ["1", "1", "2", "2", "3", "3"]


def test_counters_run_sets_memo_log_env_and_plain_run_does_not(tmp_path):
    env = b.child_env("/Users/chraibi/profiling-stage", "r", tmp_path / "counters.json", None,
                      False, memo_log=tmp_path / "memo.log")
    assert env["PYFDS_PERF_MEMO_LOG"] == str(tmp_path / "memo.log")
    plain = b.child_env("/Users/chraibi/profiling-stage", "r", None, None, False)
    assert "PYFDS_PERF_MEMO_LOG" not in plain and "PYFDS_PERF_COUNTERS_OUT" not in plain


def test_counters_dry_run_records_memo_log_in_the_manifest_env():
    out = subprocess.run([PY, "benchmark.py", "run", "--dry-run", "--shared", "--block", "T",
                          "--case", "W1", "--variants", "O_norc", "--instrument", "none,counters",
                          "--warmup", "0", "--reps", "1", "--wt", STAGE_WT, "--py", STAGE_PY],
                         cwd=WT, capture_output=True, text=True, check=True).stdout
    docs = list(_run_objects(out))
    assert [d["run_id"].split("_s1_")[0] for d in docs] == ["T_W1_O_norc", "T_W1_O_norc_ctr"]
    assert docs[0]["command"][5] == "run.py"
