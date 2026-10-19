"""g3_all.sh: block list, skip and partial rules (Task 2 of the G3 plan)."""
import os
import re
import subprocess
from pathlib import Path

import pytest

WT = Path(__file__).resolve().parents[1]

EXPECTED = {  # run-id prefix -> expected run directories
    "G3_rm_W1_W1_": 24,
    "G3_ctr_W1_W1_": 8,
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
      printf '{\n "warning_count": %s,\n "passes": null\n}\n' "$RUN_WARNINGS" > "$d/horizon.json"
    fi
    exit 0 ;;
  "-c "*) cat > /dev/null ;;
esac
exit 0
"""


@pytest.fixture
def sim(tmp_path):
    """A scratch copy of g3_all.sh with a stub interpreter and stubbed macOS guards."""
    (tmp_path / "results" / "raw").mkdir(parents=True)
    (tmp_path / "results" / "blocks").mkdir()
    py = tmp_path / "stub_py"
    py.write_text(STUB_PY)
    py.chmod(0o755)
    script = (WT / "g3_all.sh").read_text()
    script = re.sub(r"(?m)^PY=.*$", f"PY={py}", script)
    (tmp_path / "g3_all.sh").write_text(script)
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


def drive(sim, status_name="g3_status.tsv", **extra):
    env = dict(os.environ, PATH=f"{sim / 'bin'}:{os.environ['PATH']}", CALLS=str(sim / "calls"),
               **extra)
    subprocess.run(["bash", str(sim / "g3_all.sh")], cwd=sim, env=env, check=True,
                   capture_output=True, text=True, stdin=subprocess.DEVNULL)
    calls = (sim / "calls").read_text().splitlines() if (sim / "calls").exists() else []
    return (sim / "results" / "blocks" / status_name).read_text(), calls


def test_dry_run_lists_two_blocks_with_via_wrapper(sim):
    env = dict(os.environ, G3_DRY_RUN="1", PATH=f"{sim / 'bin'}:{os.environ['PATH']}")
    out = subprocess.run(["bash", str(sim / "g3_all.sh")], cwd=sim, env=env, check=True,
                         capture_output=True, text=True).stdout
    lines = [ln for ln in out.splitlines() if ln.startswith("DRY block")]
    assert [ln.split()[2].rstrip(":") for ln in lines] == ["G3_rm_W1", "G3_ctr_W1"]
    assert all("--via-wrapper" in ln and "O_norc,nrr,nss,nst" in ln for ln in lines)
    assert "--order abba --warmup 1 --reps 5 --label end-to-end" in lines[0]
    assert "--instrument counters --warmup 0 --reps 2 --label diagnostic" in lines[1]


def test_complete_blocks_are_skipped_and_status_has_one_start_and_end(sim):
    for prefix, n in EXPECTED.items():
        make_runs(sim, prefix.rstrip("_"), n)
    status, calls = drive(sim)
    assert status.count("\tSTART\t") == 1 and status.count("\tEND\t") == 1
    assert status.count("ALREADY_COMPLETE") == 2
    assert not any("benchmark.py run" in c for c in calls)


def test_partial_block_is_recorded_not_rerun(sim):
    make_runs(sim, "G3_rm_W1_W1", 10)
    make_runs(sim, "G3_ctr_W1_W1", 8)
    status, calls = drive(sim)
    assert "G3_rm_W1\tW1\tPARTIAL\t10/24" in status
    assert not any("benchmark.py run" in c for c in calls)


def test_missing_block_is_run_with_its_flags(sim):
    make_runs(sim, "G3_rm_W1_W1", 24)
    status, calls = drive(sim)
    runs = [c for c in calls if c.startswith("benchmark.py run")]
    assert len(runs) == 1 and "--block G3_ctr_W1 --exclusive" in runs[0]
    assert "--instrument counters" in runs[0] and "--via-wrapper" in runs[0]


def fill_all(sim, skip=()):
    for prefix, n in EXPECTED.items():
        if prefix not in skip:
            make_runs(sim, prefix.rstrip("_"), n)


def test_second_slot_status_file_has_one_start_and_end(sim):
    fill_all(sim)
    old = sim / "results" / "blocks" / "g3_status.tsv"
    old.write_text("2026-10-18T09:00:00Z\tEND\tg3_all\telapsed_s=100\n")
    status, _ = drive(sim)
    assert status.count("\tSTART\tg3_all\t") == 1
    assert status.count("\tEND\tg3_all\t") == 1
    rotated = list((sim / "results" / "blocks").glob("g3_status_*.tsv"))
    assert len(rotated) == 1 and "elapsed_s=100" in rotated[0].read_text()


@pytest.mark.parametrize("termination", ["failed", "timeout", None])
def test_unfinished_runs_are_not_complete(sim, termination):
    fill_all(sim, skip=("G3_ctr_W1_W1_",))
    make_runs(sim, "G3_ctr_W1_W1", 8, termination)
    status, calls = drive(sim)
    assert "ALREADY_COMPLETE" in status
    assert "G3_ctr_W1\tW1\tPARTIAL\t0/8" in status
    assert not [c for c in calls if "G3_ctr_W1" in c]


def test_horizon_check_runs_on_the_new_run_directories(sim):
    fill_all(sim, skip=("G3_ctr_W1_W1_",))
    status, calls = drive(sim, RUN_WARNINGS="0")
    checks = [c for c in calls if c.startswith("horizon_check.py")]
    assert len(checks) == 1 and "G3_ctr_W1_W1_x_0" in checks[0]
    assert "HORIZON_CHECK_FAILED" not in status


def test_foresight_warnings_log_horizon_check_failed(sim):
    fill_all(sim, skip=("G3_ctr_W1_W1_",))
    status, _ = drive(sim, RUN_WARNINGS="3")
    assert "G3_ctr_W1\tW1\tHORIZON_CHECK_FAILED\tG3_ctr_W1_W1_x_0" in status
    assert status.count("HORIZON_CHECK_FAILED") == 1


RERUN = dict(G3_PASS="G3b", G3_ARMS="O_norc,nss")


def test_dry_run_with_two_arms_names_the_pass_and_variants(sim):
    env = dict(os.environ, G3_DRY_RUN="1", PATH=f"{sim / 'bin'}:{os.environ['PATH']}", **RERUN)
    out = subprocess.run(["bash", str(sim / "g3_all.sh")], cwd=sim, env=env, check=True,
                         capture_output=True, text=True).stdout
    lines = [ln for ln in out.splitlines() if ln.startswith("DRY block")]
    assert [ln.split()[2].rstrip(":") for ln in lines] == ["G3b_rm_W1", "G3b_ctr_W1"]
    assert all("--variants O_norc,nss " in ln and "--via-wrapper" in ln for ln in lines)


def test_two_arm_blocks_expect_twelve_and_four_runs(sim):
    make_runs(sim, "G3b_rm_W1_W1", 12)
    make_runs(sim, "G3b_ctr_W1_W1", 4)
    status, calls = drive(sim, "g3b_status.tsv", **RERUN)
    assert status.count("ALREADY_COMPLETE") == 2
    assert "G3b_rm_W1\tW1\tALREADY_COMPLETE\t12" in status
    assert not any("benchmark.py run" in c for c in calls)


def test_two_arm_block_with_missing_runs_is_partial(sim):
    make_runs(sim, "G3b_rm_W1_W1", 11)
    make_runs(sim, "G3b_ctr_W1_W1", 4)
    status, _ = drive(sim, "g3b_status.tsv", **RERUN)
    assert "G3b_rm_W1\tW1\tPARTIAL\t11/12" in status


def test_two_arm_pass_runs_both_blocks_with_its_variants(sim):
    _, calls = drive(sim, "g3b_status.tsv", **RERUN)
    runs = [c for c in calls if c.startswith("benchmark.py run")]
    assert len(runs) == 2
    assert all("--variants O_norc,nss " in c for c in runs)
    assert "--block G3b_rm_W1 --exclusive" in runs[0]


@pytest.mark.parametrize("arms", ["nss", "O_norc,bogus", "nss,O_norc"])
def test_invalid_arms_are_refused(sim, arms):
    env = dict(os.environ, PATH=f"{sim / 'bin'}:{os.environ['PATH']}", G3_ARMS=arms)
    done = subprocess.run(["bash", str(sim / "g3_all.sh")], cwd=sim, env=env,
                          capture_output=True, text=True, stdin=subprocess.DEVNULL)
    assert done.returncode == 2 and "G3_ARMS" in done.stderr
    assert not (sim / "calls").exists()
