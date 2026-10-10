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


GENERIC = "pyfds-evac: warning: import_report.json marks this scenario not runnable\n"


def _run(monkeypatch, capsys, scenario_path) -> str:
    monkeypatch.setattr(cli, "load_scenario", lambda _path: _scenario(ENOUGH_S))
    monkeypatch.setattr(
        "sys.argv", ["pyfds-evac", "--scenario", str(scenario_path), "--export-only"]
    )
    assert cli.main() == 0
    return capsys.readouterr().err


def _write_report(folder, not_runnable) -> None:
    """Write the report as ``init`` does, so its keys stay the real ones."""
    report = ImportReport(
        deck="x.fds", chid="x", kind="evac", not_runnable=not_runnable
    )
    (folder / "import_report.json").write_text(json.dumps(report.to_dict()), "utf-8")


@pytest.mark.parametrize("as_file", [False, True], ids=["dir", "config-json"])
def test_not_runnable_report_warns_once_and_the_run_goes_on(
    monkeypatch, capsys, tmp_path, as_file
):
    _write_report(tmp_path, REASONS)
    config = tmp_path / "config.json"
    config.write_text("{}", "utf-8")
    err = _run(monkeypatch, capsys, config if as_file else tmp_path)
    assert err == (
        "pyfds-evac: warning: import_report.json marks this scenario "
        f"not runnable: {REASONS[0]}; {REASONS[1]}\n"
    )


@pytest.mark.parametrize("written", [True, False], ids=["runnable", "absent"])
def test_runnable_or_absent_report_is_silent(monkeypatch, capsys, tmp_path, written):
    if written:
        _write_report(tmp_path, [])
    assert "warning" not in _run(monkeypatch, capsys, tmp_path)


@pytest.mark.parametrize(
    "reasons",
    [7, "spawn_1 is too small", ["fine", 3], None],
    ids=["number", "string", "mixed-list", "missing"],
)
def test_reasons_that_are_not_a_list_of_strings_give_a_generic_warning(
    monkeypatch, capsys, tmp_path, reasons
):
    report = {"runnable": False}
    if reasons is not None:
        report["not_runnable_reasons"] = reasons
    (tmp_path / "import_report.json").write_text(json.dumps(report), "utf-8")
    assert _run(monkeypatch, capsys, tmp_path) == GENERIC


@pytest.mark.parametrize("text", ["{not json", "[false]", "null"])
def test_malformed_report_does_not_stop_the_run(monkeypatch, capsys, tmp_path, text):
    (tmp_path / "import_report.json").write_text(text, "utf-8")
    assert "warning" not in _run(monkeypatch, capsys, tmp_path)
