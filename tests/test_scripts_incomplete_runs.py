"""Scripts that call run.py report an incomplete run (exit 2) (#449).

Exit 2 means the run reached its time limit with agents inside; its outputs
are written and the scripts use them. They must also say the run was
incomplete. Any other non-zero exit is still an error. ``subprocess`` is
stubbed, so no simulation runs.
"""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _load(relative: str):
    path = SCRIPTS / relative
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _completed(code: int):
    return lambda *a, **k: subprocess.CompletedProcess(a, code, "", "")


def _ab_run(monkeypatch, tmp_path, code: int):
    ab = _load("ab_trajectories.py")
    monkeypatch.setattr(ab.subprocess, "run", _completed(code))
    return ab._run("python", tmp_path, [], tmp_path / "a.sqlite")


def test_ab_trajectories_reports_an_incomplete_run(monkeypatch, tmp_path, capsys):
    _ab_run(monkeypatch, tmp_path, 2)
    assert "incomplete (exit 2)" in capsys.readouterr().err


def test_ab_trajectories_fails_on_a_crash(monkeypatch, tmp_path):
    with pytest.raises(SystemExit):
        _ab_run(monkeypatch, tmp_path, 1)


def _schroeder_run(monkeypatch, tmp_path, code: int):
    maps = _load("docs/schroeder_room_maps.py")
    monkeypatch.setattr(maps, "write_config", lambda *a: a[-1].mkdir(parents=True))
    monkeypatch.setattr(maps.subprocess, "call", lambda *a, **k: code)
    v = SimpleNamespace(layout="L", name="N")
    return maps.run_one(tmp_path, tmp_path / "runs", v, "fds", 1)


def test_schroeder_room_maps_reports_an_incomplete_run(monkeypatch, tmp_path, capsys):
    _schroeder_run(monkeypatch, tmp_path, 2)
    assert "incomplete (exit 2)" in capsys.readouterr().err


def test_schroeder_room_maps_fails_on_a_crash(monkeypatch, tmp_path):
    with pytest.raises(subprocess.CalledProcessError):
        _schroeder_run(monkeypatch, tmp_path, 1)


@pytest.mark.parametrize(
    ("code", "state"),
    [(0, "ok"), (2, "incomplete (exit 2)"), (1, "crashed (1)")],
)
def test_fire_blind_vs_coupled_status(monkeypatch, tmp_path, code, state):
    study = _load("docs/fire_blind_vs_coupled.py")
    monkeypatch.setattr(study, "command", lambda *a: ["run.py"])
    monkeypatch.setattr(study.subprocess, "call", lambda *a, **k: code)
    assert study.execute(("U", 0, 1, tmp_path, "fds"))[3] == state
