"""g2_all.sh: status-file rotation, completeness from manifests, horizon glob (Task 3 of the G2 plan)."""
import os
import re
import subprocess
from pathlib import Path

import pytest

WT = Path(__file__).resolve().parents[1]

EXPECTED = {  # run-id prefix -> expected run directories
    "G2_prof_W3_": 4,
    "G2_prof_W1r_": 6,
    "G2_prof_W4flow_": 2,
    "G2_prof_W1_": 6,
    "G2_rc_cprof_W1_O_study_": 1,
    "G2_rc_cprof_W1_O_norc_": 1,
    "G2_ctr_scale_W1_n100_": 4,
    "G2_ctr_scale_W1_O_study": 4,
    "G2_ctr_scale_W1_n400_": 4,
}

STUB_PY = """#!/usr/bin/env bash
echo "$*" >> "$CALLS"
case "$1 $2" in
  "benchmark.py check") echo '{"ok": true}' ;;
  "benchmark.py run") exit 0 ;;
  "-c "*) cat > /dev/null ;;
esac
exit 0
"""


@pytest.fixture
def sim(tmp_path):
    """A scratch copy of g2_all.sh with a stub interpreter and stubbed macOS guards."""
    (tmp_path / "results" / "raw").mkdir(parents=True)
    (tmp_path / "results" / "blocks").mkdir()
    py = tmp_path / "stub_py"
    py.write_text(STUB_PY)
    py.chmod(0o755)
    script = (WT / "g2_all.sh").read_text()
    script = re.sub(r"(?m)^PY=.*$", f"PY={py}", script)
    (tmp_path / "g2_all.sh").write_text(script)
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


def fill_all(sim, skip=()):
    for prefix, n in EXPECTED.items():
        if prefix not in skip:
            make_runs(sim, prefix.rstrip("_"), n)


def drive(sim):
    env = dict(os.environ, PATH=f"{sim / 'bin'}:{os.environ['PATH']}", CALLS=str(sim / "calls"))
    subprocess.run(["bash", str(sim / "g2_all.sh")], cwd=sim, env=env, check=True,
                   capture_output=True, text=True, stdin=subprocess.DEVNULL)
    calls = (sim / "calls").read_text().splitlines() if (sim / "calls").exists() else []
    return (sim / "results" / "blocks" / "g2_status.tsv").read_text(), calls


def test_second_slot_status_file_has_one_start_and_end(sim):
    fill_all(sim)
    old = sim / "results" / "blocks" / "g2_status.tsv"
    old.write_text("2026-10-18T09:00:00Z\tEND\tg2_all\telapsed_s=100\n")
    status, _ = drive(sim)
    assert status.count("\tSTART\tg2_all\t") == 1
    assert status.count("\tEND\tg2_all\t") == 1
    rotated = list((sim / "results" / "blocks").glob("g2_status_*.tsv"))
    assert len(rotated) == 1 and "elapsed_s=100" in rotated[0].read_text()


@pytest.mark.parametrize("termination", ["failed", "timeout", None])
def test_unfinished_runs_are_not_complete(sim, termination):
    fill_all(sim, skip=("G2_prof_W1r_",))
    make_runs(sim, "G2_prof_W1r", 6, termination)
    status, calls = drive(sim)
    assert "ALREADY_COMPLETE" in status
    assert "G2_prof_W1r\tW1r\tPARTIAL\t0/6" in status
    assert not [c for c in calls if "G2_prof_W1r" in c]


def test_partial_block_is_not_rerun_in_place(sim):
    fill_all(sim, skip=("G2_ctr_scale_W1_n100_",))
    make_runs(sim, "G2_ctr_scale_W1_n100", 3)
    status, calls = drive(sim)
    assert "G2_ctr_scale\tW1_n100\tPARTIAL\t3/4" in status
    assert not [c for c in calls if "--case W1_n100" in c]


def test_incomplete_time_limit_and_flows_closed_count_as_complete(sim):
    fill_all(sim, skip=("G2_prof_W4flow_",))
    make_runs(sim, "G2_prof_W4flow", 1, "flows_closed")
    make_runs(sim, "G2_prof_W4flow", 1, "incomplete_time_limit", tag="y")
    status, calls = drive(sim)
    assert "PARTIAL" not in status
    assert not [c for c in calls if c.startswith("benchmark.py run")]


def test_horizon_check_stays_within_the_invocation(sim):
    fill_all(sim, skip=("G2_ctr_scale_W1_O_study",))
    _, calls = drive(sim)
    assert [c for c in calls if c.startswith("benchmark.py run") and "--case W1 " in c]
    assert not [c for c in calls if c.startswith("horizon_check.py")]

