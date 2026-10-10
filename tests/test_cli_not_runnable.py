"""``pyfds-evac --scenario DIR`` warns on a folder marked not runnable (#701).

``pyfds-evac init`` writes ``import_report.json`` next to the scenario. When
it says ``runnable: false``, the run prints one warning with the reasons and
goes on: the folder may have been fixed by hand since the import.
"""

from __future__ import annotations

import json

import pytest
from test_run_outcome import ENOUGH_S, _scenario

from pyfds_evac import cli
from pyfds_evac.core.fds_import_report import ImportReport

REASONS = [
    "spawn_1 asks for 600 agents, capacity ~584",
    "no exit door found",
]


def _run(monkeypatch, capsys, folder) -> str:
    monkeypatch.setattr(cli, "load_scenario", lambda _path: _scenario(ENOUGH_S))
    monkeypatch.setattr(
        "sys.argv", ["pyfds-evac", "--scenario", str(folder), "--export-only"]
    )
    assert cli.main() == 0
    return capsys.readouterr().err


def _write_report(folder, not_runnable) -> None:
    """Write the report as ``init`` does, so its keys stay the real ones."""
    report = ImportReport(
        deck="x.fds", chid="x", kind="evac", not_runnable=not_runnable
    )
    (folder / "import_report.json").write_text(json.dumps(report.to_dict()), "utf-8")


def test_not_runnable_report_warns_once_and_the_run_goes_on(
    monkeypatch, capsys, tmp_path
):
    _write_report(tmp_path, REASONS)
    err = _run(monkeypatch, capsys, tmp_path)
    assert err == (
        "pyfds-evac: warning: import_report.json marks this scenario "
        f"not runnable: {REASONS[0]}; {REASONS[1]}\n"
    )


@pytest.mark.parametrize("written", [True, False], ids=["runnable", "absent"])
def test_runnable_or_absent_report_is_silent(monkeypatch, capsys, tmp_path, written):
    if written:
        _write_report(tmp_path, [])
    assert "warning" not in _run(monkeypatch, capsys, tmp_path)
