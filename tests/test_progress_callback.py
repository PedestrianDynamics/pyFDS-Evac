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


def test_progress_percentage_and_clocks_follow_the_documented_fields():
    """Four agents: pct is the integer percentage of evacuated/total.

    ``single_exit_clear_air`` has two sources of two agents, so total is 4
    and the percentage after k evacuated agents is ``int(100 * k / 4)``.
    The clocks never run backwards: ``sim_time`` steps from 0 and
    ``wall_time`` is real elapsed time, positive once the run has begun.
    """
    scenario = load_scenario("assets/single_exit_clear_air")
    events: list[ProgressEvent] = []
    result = run_scenario(scenario, seed=420, progress_callback=events.append)
    result.cleanup()

    assert {e.total for e in events} == {4}
    assert events[0].sim_time == 0.0
    assert all(e.pct == int(100 * e.evacuated / 4) for e in events)
    assert max(e.evacuated for e in events) >= 1
    assert max(e.pct for e in events) >= 25
    sim = [e.sim_time for e in events]
    wall = [e.wall_time for e in events]
    assert sim == sorted(sim)
    assert wall == sorted(wall)
    assert wall[-1] > 0.0


def test_run_scenario_without_callback_is_unchanged():
    scenario = load_scenario("assets/single_exit_clear_air")
    events: list[ProgressEvent] = []
    with_callback = run_scenario(scenario, seed=420, progress_callback=events.append)
    with_callback.cleanup()
    plain = run_scenario(scenario, seed=420)
    plain.cleanup()

    assert events
    keys = ("evacuation_time", "agents_evacuated", "agents_remaining", "total_agents")
    assert {k: plain.metrics[k] for k in keys} == {
        k: with_callback.metrics[k] for k in keys
    }
    assert plain.total_agents == 4


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
