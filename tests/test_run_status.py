"""Execution and outcome of a run, and one wording of why it stopped (#535)."""

from __future__ import annotations

import contextlib
import io
from types import SimpleNamespace

import pytest

from pyfds_evac.config import events
from pyfds_evac.config.frontend import execution_outcome, stop_reason_phrase
from pyfds_evac.config.script import python_script
from pyfds_evac.core.run_outputs import summary_line

EXECUTIONS = ("running", "finished", "cancelled", "crashed")
OUTCOMES = ("completed", "incomplete", "rejected", "no_result")

# (execution, outcome) -> (legacy status, exit code). Exit codes are those of
# 0.8.x: 0 success, 2 incomplete, 1 failed, no code for a cancel.
LEGAL = {
    ("finished", "completed"): ("success", 0),
    ("finished", "incomplete"): ("incomplete", 2),
    ("finished", "rejected"): ("failed", 1),
    ("crashed", "no_result"): ("failed", 1),
    ("cancelled", "no_result"): ("cancelled", None),
}


@pytest.mark.parametrize("execution", EXECUTIONS)
@pytest.mark.parametrize("outcome", OUTCOMES)
def test_every_pair_maps_to_a_legacy_status_and_exit_code(execution, outcome):
    pair = (execution, outcome)
    if pair not in LEGAL:
        with pytest.raises(ValueError, match="illegal run state"):
            events.legacy_status(*pair)
        with pytest.raises(ValueError, match="illegal run state"):
            events.exit_code(*pair)
        return
    status, code = LEGAL[pair]
    assert events.legacy_status(*pair) == status
    assert events.exit_code(*pair) == code
    event = events.ResultEvent(status, code, execution=execution, outcome=outcome)
    assert (event.execution, event.outcome) == pair


@pytest.mark.parametrize(
    ("status", "started", "pair"),
    [
        ("success", True, ("finished", "completed")),
        ("incomplete", True, ("finished", "incomplete")),
        ("failed", False, ("finished", "rejected")),
        ("failed", True, ("crashed", "no_result")),
        ("cancelled", True, ("cancelled", "no_result")),
    ],
)
def test_a_legacy_status_maps_back_to_its_pair(status, started, pair):
    assert events.pair_of_status(status, started=started) == pair
    assert events.legacy_status(*pair) == status


def test_a_result_event_without_a_pair_derives_it_from_status():
    event = events.ResultEvent(events.STATUS_INCOMPLETE, 2)
    assert (event.execution, event.outcome) == ("finished", "incomplete")
    failed = events.ResultEvent(events.STATUS_FAILED, 1)
    assert (failed.execution, failed.outcome) == ("crashed", "no_result")


def test_a_result_event_refuses_an_inconsistent_pair():
    with pytest.raises(ValueError, match="does not match"):
        events.ResultEvent("success", 0, execution="finished", outcome="incomplete")
    with pytest.raises(ValueError, match="illegal run state"):
        events.ResultEvent("success", 0, execution="finished", outcome="no_result")
    with pytest.raises(ValueError, match="together"):
        events.ResultEvent("success", 0, execution="finished")


def test_exit_codes_are_unchanged():
    assert events.EXIT_CODES == {
        "success": 0,
        "incomplete": 2,
        "failed": 1,
        "cancelled": None,
    }


def test_stream_run_pairs_of_a_rejected_a_crashed_and_a_cancelled_run(
    monkeypatch, tmp_path
):
    import pyfds_evac.core.run_config as run_config
    import pyfds_evac.core.scenario as scenario_module
    from pyfds_evac.core import run_stream

    missing = run_stream.options({"scenario": str(tmp_path / "missing.json")})
    rejected = run_stream.stream_run(missing, lambda _e: None)
    assert (rejected.execution, rejected.outcome) == ("finished", "rejected")

    monkeypatch.setattr(scenario_module, "load_scenario", lambda _p: SimpleNamespace())
    monkeypatch.setattr(run_config, "build_run_kwargs", lambda *_a, **_k: {})
    plan = events.PlanEvent(
        extent=(0.0, 0.0, 1.0, 1.0),
        walkable=(),
        exits={},
        exit_openings={},
        signs=(),
        spawn_areas={},
        smoke_mode="none",
    )
    monkeypatch.setattr(run_stream, "plan_event", lambda *_a, **_k: plan)
    monkeypatch.setattr(run_stream, "_modelled", lambda _k: False)

    def boom(*_a, **_k):
        raise RuntimeError("solver died")

    monkeypatch.setattr(scenario_module, "run_scenario", boom)
    opts = run_stream.options({"scenario": "x.json"})
    crashed = run_stream.stream_run(opts, lambda _e: None)
    assert crashed.error == "RuntimeError: solver died"
    assert (crashed.execution, crashed.outcome) == ("crashed", "no_result")
    assert (crashed.status, crashed.exit_code) == ("failed", 1)

    cancelled = run_stream.stream_run(opts, lambda _e: None, cancel=lambda: True)
    assert (cancelled.execution, cancelled.outcome) == ("cancelled", "no_result")


# -- one wording ------------------------------------------------------------

DEADLOCK = {"agents": 2, "since_s": 18.0, "positions": []}
REASONS = {
    "time_limit": "time limit reached",
    "flows_closed": "flow windows closed",
    "all_mobile_left": "all mobile agents left",
    "deadlock": "deadlock, 2 agents stuck since t = 18.00 s,",
}


@pytest.mark.parametrize(("end_reason", "phrase"), REASONS.items())
def test_stop_reason_phrase(end_reason, phrase):
    assert stop_reason_phrase(end_reason, DEADLOCK) == phrase


def test_stop_reason_phrase_without_a_reason_is_the_time_limit():
    assert stop_reason_phrase(None) == "time limit reached"
    assert stop_reason_phrase("deadlock", {"agents": 1, "since_s": 5}) == (
        "deadlock, 1 agent stuck since t = 5.00 s,"
    )


def _result(end_reason: str) -> SimpleNamespace:
    metrics = {"deadlock": DEADLOCK} if end_reason == "deadlock" else {}
    return SimpleNamespace(
        success=False,
        evacuation_time=12.5,
        agents_evacuated=4,
        total_agents=6,
        agents_remaining=2,
        agents_not_spawned=0,
        end_reason=end_reason,
        metrics=metrics,
    )


def _script_line(result: SimpleNamespace) -> str:
    """Run the summary block of the generated script on *result*."""
    code = python_script({"scenario": "x.json"})
    block = code[code.index("if result.success:") : code.index("OUTPUT_DIR.mkdir")]
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        exec(block, {"result": result, "stop_reason_phrase": stop_reason_phrase})
    return out.getvalue().strip()


@pytest.mark.parametrize("end_reason", REASONS)
def test_cli_and_exported_script_use_the_shared_wording(end_reason):
    result = _result(end_reason)
    line = summary_line(result)
    assert f"Simulation incomplete: {REASONS[end_reason]} after 12.50 s" in line
    assert _script_line(result) == line


def test_generated_script_imports_the_shared_phrase():
    code = python_script({"scenario": "x.json"})
    assert "from pyfds_evac.config.frontend import stop_reason_phrase" in code
    assert '"deadlock": "deadlock"' not in code


# -- combinations -----------------------------------------------------------


def test_execution_outcome_words_every_legal_pair():
    done = execution_outcome("finished", "completed")
    assert (done.complete, done.label) == (True, "Complete: all agents evacuated")
    for end_reason in ("time_limit", "flows_closed", "all_mobile_left", "deadlock"):
        words = execution_outcome(
            "finished",
            "incomplete",
            remaining=2,
            not_spawned=0,
            end_reason=end_reason,
            incapacitated=0,
        )
        assert words.complete is False and words.label.startswith("Incomplete:")
    rejected = execution_outcome("finished", "rejected")
    assert rejected.label == "Configuration rejected, no simulation was run"
    crashed = execution_outcome("crashed", "no_result")
    assert crashed.label == "Run crashed, no result"
    cancelled = execution_outcome("cancelled", "no_result", sim_time=3.0)
    assert cancelled.label == "Cancelled at sim 3.0 s"
    assert {rejected.complete, crashed.complete, cancelled.complete} == {None}


def test_execution_outcome_refuses_an_illegal_pair():
    with pytest.raises(ValueError, match="illegal run state"):
        execution_outcome("finished", "no_result")
    with pytest.raises(ValueError, match="illegal run state"):
        execution_outcome("running", "completed")
