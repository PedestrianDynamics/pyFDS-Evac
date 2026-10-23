"""What ``pyfds-evac`` prints through ``main()`` (#876).

``--print-summary`` prints ``Scenario.summary()`` before anything else runs.
After a run, a non-empty ``fds_outside`` count adds the "Outside the FDS
domain" line quoted in ``docs/fds-sampling.md``. The expected lines are
literals: the summary counts are a hand count of the 10 x 6 m room of
``test_run_outcome`` (one exit, one distribution of six agents, one
journey), and the outside line is the documented wording.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from test_run_outcome import ENOUGH_S, _scenario

from pyfds_evac import cli


def _main(monkeypatch, capsys, *args) -> str:
    scenario = _scenario(ENOUGH_S)
    monkeypatch.setattr(cli, "load_scenario", lambda _path: scenario)
    monkeypatch.setattr("sys.argv", ["pyfds-evac", "--scenario", "unused", *args])
    assert cli.main() == 0
    return capsys.readouterr().out


def test_print_summary_prints_the_scenario_summary(monkeypatch, capsys):
    out = _main(monkeypatch, capsys, "--print-summary", "--export-only")
    lines = out.splitlines()
    assert lines[0] == "Initialization started."
    assert lines[1] == "Scenario: (in-memory)"
    assert "  Exits:         1" in lines
    assert "  Distributions: 1" in lines
    assert "  Agents:        ~6" in lines


def test_the_summary_is_not_printed_without_the_flag(monkeypatch, capsys):
    out = _main(monkeypatch, capsys, "--export-only")
    assert "Scenario:" not in out


def _run_printing(monkeypatch, capsys, metrics) -> str:
    result = SimpleNamespace(
        success=True,
        evacuation_time=12.0,
        agents_evacuated=6,
        total_agents=6,
        metrics=metrics,
        cleanup=lambda: None,
    )
    monkeypatch.setattr(cli, "run_scenario", lambda _scenario, **_kw: result)
    monkeypatch.setattr(cli, "apply_outputs", lambda *_a, **_kw: [])
    return _main(monkeypatch, capsys)


def test_outside_the_fds_domain_line_follows_the_summary_line(monkeypatch, capsys):
    """The wording is the one in docs/fds-sampling.md; 56.04 prints as 56.0."""
    outside = {"agents": 8, "rows": 56, "agent_seconds": 56.04}
    out = _run_printing(monkeypatch, capsys, {"fds_outside": outside})
    assert out.splitlines()[-2:] == [
        "Simulation finished in 12.00 s (6/6 evacuated).",
        "Outside the FDS domain: 8 agent(s), 56 sample(s), about 56.0 "
        "agent-seconds of ambient air and clear sight.",
    ]


@pytest.mark.parametrize(
    "metrics",
    [{}, {"fds_outside": None}, {"fds_outside": {"agents": 0, "rows": 0}}],
    ids=["absent", "none", "zero-rows"],
)
def test_no_samples_outside_the_domain_print_no_line(monkeypatch, capsys, metrics):
    out = _run_printing(monkeypatch, capsys, metrics)
    assert "Outside the FDS domain" not in out
