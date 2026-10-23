"""GUI run snapshot, export and wording pins (#836 item 1, area F).

Expected texts are written by hand from the parameter pages
(docs/usage.md, docs/coming-from-fds-evac.md) and the documented field
meanings, not read back from the functions under test.
"""

from __future__ import annotations

import argparse
from types import SimpleNamespace

import pytest

pytest.importorskip("fasthtml")

from pyfds_evac.config.frontend import incapacitated_text  # noqa: E402
from pyfds_evac.config.script import ExportError, python_script  # noqa: E402
from pyfds_evac.webapp.pyexport import preview_script, run_status  # noqa: E402
from pyfds_evac.webapp.runner import RunSpec, make_run_spec  # noqa: E402


def _spec(**fields) -> RunSpec:
    base = dict(
        run_id=1,
        scenario_name="t",
        scenario_path="t",
        opts={},
        started_at="2026-09-29T12:00:00+00:00",
        pyfds_evac_version=None,
        git_commit=None,
        git_dirty=None,
        expected_seed=1,
    )
    return RunSpec(**{**base, **fields})


def test_run_snapshot_keeps_the_scenario_time_limit():
    scenario = SimpleNamespace(max_simulation_time=300.0, seed=7)
    spec = make_run_spec(argparse.Namespace(seed=None), scenario, "t", "assets/t")
    assert spec.time_limit == 300.0
    assert spec.expected_seed == 7  # blank seed: the scenario's own


def test_failed_run_is_worded_failed():
    assert run_status(_spec(status="error")) == "failed"
    assert run_status(_spec(status="cancelled")) == "cancelled"


def test_incapacitated_figure_is_not_shown_when_it_is_unknown():
    assert incapacitated_text(None, True) == "not modelled in this run"
    assert incapacitated_text(3, False) == "not modelled in this run"
    assert incapacitated_text(3, True) == "3 agents"


def _preview(dirty):
    return preview_script(
        {"seed": 1, "scenario": "t"},
        "t",
        "assets/t",
        version="1.2.3",
        commit="abc123",
        dirty=dirty,
        baseseed=None,
    ).code


def test_export_header_names_a_dirty_checkout():
    assert "commit abc123 (with uncommitted changes)." in _preview(True)
    clean = _preview(False)
    assert "commit abc123." in clean
    assert "uncommitted" not in clean


@pytest.mark.parametrize("value", [[1, 2], (1, 2), {"a": 1}])
def test_export_refuses_values_that_are_not_plain_literals(value):
    opts = argparse.Namespace(seed=1, scenario="assets/t", reroute_interval=value)
    with pytest.raises(ExportError, match="reroute_interval"):
        python_script(opts)


def test_model_tab_states_the_documented_default_sigma():
    """docs/usage.md: `--susceptibility-sigma` defaults to 0.94."""
    from fasthtml.common import to_xml

    from pyfds_evac.webapp.docs import model_docs

    html = to_xml(model_docs())
    assert r"$\sigma = 0.94$ by default" in html
