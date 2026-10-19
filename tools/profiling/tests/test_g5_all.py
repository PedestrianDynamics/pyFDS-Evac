"""g5_all.sh: block list, skip, partial, equality and pass-tag rules."""
import os
import re
import subprocess
from pathlib import Path

import pytest

WT = Path(__file__).resolve().parents[1]

EXPECTED = {  # run-id prefix -> expected run directories
    "G5_memo_W1_W1_": 40,
    "G5_ctr_W1_W1_": 4,
}

STUB_PY = """#!/usr/bin/env bash
echo "$*" >> "$CALLS"
case "$1 $2" in
  "benchmark.py check") echo '{"ok": true}' ;;
  "benchmark.py run")
    if [ -n "${RUN_WARNINGS:-}" ]; then   # write one run directory, as benchmark.py would
      block=${4:-}
      d=results/raw/${block}_W1_x_0
      mkdir -p "$d"
      echo '{"termination": "completed"}' > "$d/manifest.json"
      printf '{\\n "warning_count": %s,\\n "passes": null\\n}\\n' "$RUN_WARNINGS" > "$d/horizon.json"
    fi
    exit 0 ;;
  "attribute.py --equality") exit "${EQUALITY_RC:-0}" ;;
  "-c "*) cat > /dev/null ;;
esac
exit 0
"""

FIX_STAGE = "--wt /Users/chraibi/profiling-stage/wt_29f9d3a5 --py /Users/chraibi/profiling-stage/wt_29f9d3a5/.venv/bin/python"


@pytest.fixture
def sim(tmp_path):
    """A scratch copy of g5_all.sh with a stub interpreter and stubbed macOS guards."""
    (tmp_path / "results" / "raw").mkdir(parents=True)
    (tmp_path / "results" / "blocks").mkdir()
    py = tmp_path / "stub_py"
    py.write_text(STUB_PY)
    py.chmod(0o755)
    script = (WT / "g5_all.sh").read_text()
    script = re.sub(r"(?m)^PY=.*$", f"PY={py}", script)
    (tmp_path / "g5_all.sh").write_text(script)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in (("defaults", "echo 0"), ("launchctl", "echo header"), ("ps", "true")):
        stub = bin_dir / name
        stub.write_text(f"#!/bin/sh\n{body}\n")
        stub.chmod(0o755)
    return tmp_path


def make_runs(sim, prefix, n, termination="completed", tag="x"):
    for i in range(n):
        d = sim / "results" / "raw" / f"{prefix}_{tag}_{i}"
        d.mkdir()
        if termination:
            (d / "manifest.json").write_text(f'{{\n  "termination": "{termination}"\n}}\n')


def drive(sim, status_name="g5_status.tsv", **extra):
    env = dict(os.environ, PATH=f"{sim / 'bin'}:{os.environ['PATH']}", CALLS=str(sim / "calls"),
               **extra)
    subprocess.run(["bash", str(sim / "g5_all.sh")], cwd=sim, env=env, check=True,
                   capture_output=True, text=True, stdin=subprocess.DEVNULL)
    calls = (sim / "calls").read_text().splitlines() if (sim / "calls").exists() else []
    return (sim / "results" / "blocks" / status_name).read_text(), calls


def fill_all(sim, skip=()):
    for prefix, n in EXPECTED.items():
        if prefix not in skip:
            make_runs(sim, prefix.rstrip("_"), n)


def test_dry_run_lists_two_blocks_at_the_fix_stage(sim):
    env = dict(os.environ, G5_DRY_RUN="1", PATH=f"{sim / 'bin'}:{os.environ['PATH']}")
    out = subprocess.run(["bash", str(sim / "g5_all.sh")], cwd=sim, env=env, check=True,
                         capture_output=True, text=True).stdout
    lines = [ln for ln in out.splitlines() if ln.startswith("DRY ")]
    assert [ln.split()[1:3] for ln in lines] == [["block", "G5_memo_W1:"], ["equality", "G5_memo_W1"],
                                                 ["block", "G5_ctr_W1:"]]
    assert all(FIX_STAGE in ln for ln in (lines[0], lines[2]))
    assert ("--case W1 --variants O_norc,nomemo --seeds 1,2,3,4,5,6,7,8,9,10 --order abba "
            "--warmup 1 --reps 1 --label memo") in lines[0]
    assert ("--case W1 --variants O_norc,nomemo --seeds 1 --instrument counters --warmup 0 "
            "--reps 2 --label diagnostic") in lines[2]
    assert "--via-wrapper" not in out and "analyse.py" not in out


def test_complete_blocks_are_skipped_and_status_has_one_start_and_end(sim):
    fill_all(sim)
    status, calls = drive(sim)
    assert status.count("\tSTART\t") == 1 and status.count("\tEND\tg5_all\t") == 1
    assert status.count("ALREADY_COMPLETE") == 2
    assert not any("benchmark.py run" in c for c in calls)
    assert any(c.startswith("attribute.py --equality G5_memo_W1 --out results/g5") for c in calls)


def test_partial_memo_block_is_recorded_not_rerun(sim):
    make_runs(sim, "G5_memo_W1_W1", 20)
    make_runs(sim, "G5_ctr_W1_W1", 4)
    status, calls = drive(sim)
    assert "G5_memo_W1\tW1\tPARTIAL\t20/40" in status
    assert not any("benchmark.py run" in c for c in calls)


def test_missing_ctr_block_is_run_with_its_flags(sim):
    make_runs(sim, "G5_memo_W1_W1", 40)
    status, calls = drive(sim)
    runs = [c for c in calls if c.startswith("benchmark.py run")]
    assert len(runs) == 1 and "--block G5_ctr_W1 --exclusive" in runs[0]
    assert "--instrument counters" in runs[0] and FIX_STAGE in runs[0]


def test_equality_failure_is_logged_after_the_memo_block(sim):
    fill_all(sim)
    status, calls = drive(sim, EQUALITY_RC="3")
    assert "G5_memo_W1\tW1\tEQUALITY_FAILED\trc=3" in status
    assert len([c for c in calls if c.startswith("attribute.py --equality")]) == 1


def test_equality_runs_between_the_memo_and_counters_blocks(sim):
    _, calls = drive(sim)
    steps = [c for c in calls if c.startswith(("benchmark.py run", "attribute.py --equality"))]
    assert [c.split()[0:2] for c in steps] == [["benchmark.py", "run"], ["attribute.py", "--equality"],
                                               ["benchmark.py", "run"]]
    assert "--block G5_memo_W1 " in steps[0] and "--block G5_ctr_W1 " in steps[2]


def test_second_slot_status_file_has_one_start_and_end(sim):
    fill_all(sim)
    old = sim / "results" / "blocks" / "g5_status.tsv"
    old.write_text("2026-10-18T09:00:00Z\tEND\tg5_all\telapsed_s=100\n")
    status, _ = drive(sim)
    assert status.count("\tSTART\tg5_all\t") == 1
    assert status.count("\tEND\tg5_all\t") == 1
    rotated = list((sim / "results" / "blocks").glob("g5_status_*.tsv"))
    assert len(rotated) == 1 and "elapsed_s=100" in rotated[0].read_text()


def test_equality_pass_logs_no_failure_line(sim):
    fill_all(sim)
    status, _ = drive(sim)
    assert "EQUALITY_FAILED" not in status


def test_foresight_warnings_log_horizon_check_failed(sim):
    fill_all(sim, skip=("G5_ctr_W1_W1_",))
    status, calls = drive(sim, RUN_WARNINGS="3")
    assert len([c for c in calls if c.startswith("horizon_check.py")]) == 1
    assert "G5_ctr_W1\tW1\tHORIZON_CHECK_FAILED\tG5_ctr_W1_W1_x_0" in status


def test_pass_tag_names_blocks_and_status_file(sim):
    make_runs(sim, "G5b_memo_W1_W1", 40)
    make_runs(sim, "G5b_ctr_W1_W1", 4)
    status, calls = drive(sim, "g5b_status.tsv", G5_PASS="G5b")
    assert "G5b_memo_W1\tW1\tALREADY_COMPLETE\t40" in status
    assert any(c.startswith("attribute.py --equality G5b_memo_W1 ") for c in calls)
