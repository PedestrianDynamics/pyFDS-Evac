"""Tests for the optional progress_callback hook on run_scenario."""

from pyfds_evac.core import ProgressEvent, load_scenario, run_scenario


def test_progress_callback_receives_events():
    scenario = load_scenario("assets/ISO-table21")
    events: list[ProgressEvent] = []
    result = run_scenario(scenario, seed=420, progress_callback=events.append)
    result.cleanup()

    assert events, "expected at least one progress event"
    assert all(isinstance(e, ProgressEvent) for e in events)
    last = events[-1]
    assert 0 <= last.pct <= 100
    assert last.sim_time >= 0.0
    assert last.wall_time >= 0.0
    assert last.total >= 1


def test_run_scenario_without_callback_is_unchanged():
    scenario = load_scenario("assets/ISO-table21")
    result = run_scenario(scenario, seed=420)
    result.cleanup()

    assert result.metrics
    assert result.total_agents >= 1
