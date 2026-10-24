"""``scripts/inspect_fds.py`` tells clear air from a missing slice (#326)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("fdsreader")

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "inspect_fds.py"


@pytest.fixture(scope="module")
def inspect_fds():
    spec = importlib.util.spec_from_file_location("inspect_fds", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
        yield module
    finally:
        sys.modules.pop(spec.name, None)


def _run(inspect_fds, monkeypatch, capsys, extinction_max):
    """Run inspect() on a fake case; None means no extinction slice."""
    monkeypatch.setattr(
        "pyfds_evac.core.fdsreader_adapter.open_fds_simulation", lambda _d: object()
    )

    def load(_sim, fds_name, _height):
        if fds_name == "Soot extinction coefficient" and extinction_max is None:
            return None
        return fds_name

    def stats(fds_name, scale):
        peak = extinction_max if fds_name == "Soot extinction coefficient" else 1.0
        t = np.array([0.0, 1.0])
        return t, np.full(2, peak), np.full(2, peak), peak, peak

    monkeypatch.setattr(inspect_fds, "_load_quantity", load)
    monkeypatch.setattr(inspect_fds, "_extract_stats", stats)
    inspect_fds.inspect("fake")
    return capsys.readouterr().out


def test_all_zero_extinction_slice_is_clear_air(inspect_fds, monkeypatch, capsys):
    out = _run(inspect_fds, monkeypatch, capsys, 0.0)
    assert "present, all zero (clear air)" in out
    assert "✓ Extinction coefficient present, all zero" in out
    assert "will NOT" not in out


def test_missing_extinction_slice_keeps_the_failure_wording(
    inspect_fds, monkeypatch, capsys
):
    out = _run(inspect_fds, monkeypatch, capsys, None)
    assert "✗ Extinction coefficient → smoke-speed model will NOT run" in out


def test_nonzero_extinction_slice_runs_the_smoke_model(
    inspect_fds, monkeypatch, capsys
):
    out = _run(inspect_fds, monkeypatch, capsys, 0.2)
    assert "✓ Extinction coefficient → smoke-speed model will run" in out
