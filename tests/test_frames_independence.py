"""Observing a run does not change it (#531).

The terminal UI's child sends plan-view frames (and smoke grids read from
the run's own extinction sampler) at a rate capped by wall time. A seeded
coupled run must write the same trajectory and history CSVs with frames
off, at the TUI's rates, with a frame after every step, and as the CLI.
"""

from __future__ import annotations

import argparse
import shlex
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from pyfds_evac.config import events, frontend
from pyfds_evac.tui import model

REPO = Path(__file__).resolve().parents[1]
SCENARIO = REPO / "assets" / "iso_table21_coupled"
SEED = "7"

# Runner settings per variant: frames off, the TUI's 5 Hz and 1 Hz
# (frame_rate()), and a frame after every step.
VARIANTS = {
    "off": {"frames": False},
    "5hz": {"max_hz": 5.0},
    "1hz": {"max_hz": 1.0},
    "dense": {"max_hz": 1e6},
}
# Outputs compared byte for byte: every CSV a front end writes. The bundle
# and the manifest hold paths and times of the run.
CSV_DESTS = sorted(
    dest
    for dest, path in frontend.output_paths("", "x").items()
    if path.endswith(".csv")
)
RESULT_FIELDS = (
    "status",
    "evacuated",
    "total",
    "remaining",
    "incapacitated",
    "not_spawned",
    "end_time_s",
    "seed",
)


def _form() -> model.Form:
    form = model.Form()
    form.scenario = model.read_scenario(SCENARIO)
    form.fds_dir = str(SCENARIO / "fds")
    form.text["seed"] = SEED
    return form


def _run(form: model.Form, label: str, root: Path, **runner) -> tuple:
    from pyfds_evac.tui.runner import ProcessRunner

    base = form.run_folder(label, root)
    ns = form.namespace(form.output_paths(base))
    got: list = []
    proc = ProcessRunner(**runner)
    proc.start(vars(ns), base, got.append)
    assert proc.join(300), label
    assert isinstance(got[-1], events.ResultEvent), (label, got[-3:])
    return ns, got


def _rows(path: str) -> list:
    with sqlite3.connect(path) as db:
        return db.execute("SELECT * FROM trajectory_data ORDER BY frame, id").fetchall()


def _outputs(ns: argparse.Namespace) -> dict:
    files = {}
    for dest in CSV_DESTS:
        path = Path(getattr(ns, dest))
        files[dest] = path.read_bytes() if path.exists() else None
    return {"rows": _rows(ns.output_sqlite), "csv": files}


@pytest.mark.slow
def test_frames_do_not_change_the_run(tmp_path, monkeypatch):
    tmp = tmp_path / "tmp"
    tmp.mkdir()
    monkeypatch.setenv("TMPDIR", str(tmp))
    monkeypatch.setattr(tempfile, "tempdir", str(tmp))
    form = _form()

    runs = {label: _run(form, label, tmp_path, **kw) for label, kw in VARIANTS.items()}

    # Each variant observed the run differently, smoke grids included.
    frames = {
        label: [e for e in got if isinstance(e, events.FrameEvent)]
        for label, (_ns, got) in runs.items()
    }
    assert frames["off"] == []
    for label in ("5hz", "1hz", "dense"):
        grids = [f.smoke for f in frames[label] if f.smoke is not None]
        assert any(g.fds_time_s > 0 for g in grids), label
    assert len(frames["dense"]) > 10 * len(frames["5hz"])

    reference_ns, reference_events = runs["off"]
    reference = _outputs(reference_ns)
    result = reference_events[-1]
    assert result.status == events.STATUS_SUCCESS
    assert result.seed == int(SEED)
    assert reference["rows"]
    assert reference["csv"]["output_smoke_history"] is not None
    for label, (ns, got) in runs.items():
        assert _outputs(ns) == reference, label
        for name in RESULT_FIELDS:
            assert getattr(got[-1], name) == getattr(result, name), (label, name)

    # The CLI writes the same files.
    from pyfds_evac.config.effective import cli_command

    cli_base = form.run_folder("CLI", tmp_path)
    cli_ns = argparse.Namespace(**{**vars(reference_ns), **form.output_paths(cli_base)})
    command = shlex.split(cli_command(cli_ns))
    exe = Path(sys.executable).with_name("pyfds-evac")
    done = subprocess.run([str(exe), *command[1:]], capture_output=True, text=True)
    assert done.returncode == events.EXIT_CODES[result.status], done.stderr
    assert _outputs(cli_ns) == reference
