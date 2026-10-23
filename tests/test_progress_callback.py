"""Tests for the optional progress_callback hook on run_scenario."""

import json
import shutil

from pyfds_evac.core import ProgressEvent, load_scenario, run_scenario


def test_progress_callback_receives_events():
    scenario = load_scenario("assets/ISO-table21")
    events: list[ProgressEvent] = []
    result = run_scenario(scenario, seed=420, progress_callback=events.append)
    result.cleanup()

    assert events, "expected at least one progress event"
    assert all(isinstance(e, ProgressEvent) for e in events)
    last = events[-1]
    assert last.total == result.total_agents == 1
    assert events[0].sim_time == 0.0
    assert last.sim_time > events[0].sim_time
    assert last.wall_time > events[0].wall_time > 0.0


def test_run_scenario_without_callback_is_unchanged():
    scenario = load_scenario("assets/ISO-table21")
    result = run_scenario(scenario, seed=420)
    result.cleanup()

    assert result.metrics
    assert result.total_agents >= 1


def _three_agent_room(tmp_path):
    """``single_exit_clear_air`` with 2 + 1 agents, so 100 * k / 3 is not integral."""
    room = tmp_path / "room"
    shutil.copytree("assets/single_exit_clear_air", room)
    config = json.loads((room / "config.json").read_text(encoding="utf-8"))
    numbers = [d["parameters"] for d in config["distributions"].values()]
    numbers[1]["number"] = 1
    (room / "config.json").write_text(json.dumps(config), encoding="utf-8")
    return load_scenario(str(room))


def test_progress_events_report_the_evacuated_share_rounded_down(tmp_path):
    """Three agents leave one by one: the percentage steps 0, 33, 66.

    The values are the floor of 100 * evacuated / 3 by hand; a constant 0 or
    a rounded-up percentage (34, 67) fails. The loop stops once the room is
    empty, so no event reports 100.
    """
    events: list[ProgressEvent] = []
    result = run_scenario(
        _three_agent_room(tmp_path), seed=420, progress_callback=events.append
    )
    result.cleanup()

    assert result.total_agents == 3
    assert result.agents_evacuated == 3
    assert {e.total for e in events} == {3}
    by_count = {}
    for event in events:
        by_count.setdefault(event.evacuated, set()).add(event.pct)
    assert by_count == {0: {0}, 1: {33}, 2: {66}}

    times = [e.sim_time for e in events]
    assert times == sorted(set(times)), "sim_time must strictly increase"
    assert times[0] == 0.0
    counts = [e.evacuated for e in events]
    assert counts == sorted(counts), "evacuated must not decrease"
    assert counts[-1] <= result.agents_evacuated
