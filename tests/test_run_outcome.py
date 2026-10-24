"""How a run reports its end: completed, or incomplete.

A run that reaches ``max_simulation_time`` with agents inside, or with flow
agents still to enter, is incomplete: ``success`` is False, ``status`` is
``"incomplete"``, and the metrics, the manifest and the CLI summary give the
agents left (#139, #434). ``end_reason`` says why the run stopped (#742).

The deck is synthetic: a 10 x 6 m room with one exit in the east wall and a
spawn area in the west half, about 6 m from the exit.
"""

from __future__ import annotations

import contextlib
import io
import json
from types import SimpleNamespace

import pytest
from shapely.geometry import Polygon, box

from pyfds_evac.core.scenario import Scenario, run_scenario

SEED = 3
NUM_AGENTS = 6
# Long enough for every agent to leave, and far too short for any to.
ENOUGH_S = 60.0
TOO_SHORT_S = 1.0
WALKABLE = box(0.0, 0.0, 10.0, 6.0)
EXIT = box(9.8, 2.0, 10.0, 4.0)
D = "jps-distributions_0"


def _coords(polygon: Polygon) -> list[list[float]]:
    return [[x, y] for x, y in polygon.exterior.coords]


def _scenario(max_time_s: float, **dist_extra) -> Scenario:
    raw = {
        "project_version": "2.0",
        "config": {
            "simulation_settings": {
                "simulationParams": {
                    "max_simulation_time": max_time_s,
                    "model_type": "CollisionFreeSpeedModel",
                },
                "numberOfSimulations": 1,
                "baseSeed": SEED,
            },
            "ui_state": {"useShortestPaths": False},
        },
        "exits": {"E": {"type": "polygon", "coordinates": _coords(EXIT)}},
        "distributions": {
            D: {
                "type": "polygon",
                "coordinates": _coords(box(1.0, 1.0, 4.0, 5.0)),
                "parameters": {
                    "number": NUM_AGENTS,
                    "radius": 0.15,
                    "v0": 1.3,
                    "distribution_mode": "by_number",
                    "use_premovement": False,
                    "radius_distribution": "constant",
                    "v0_distribution": "constant",
                    "use_flow_spawning": False,
                    **dist_extra,
                },
            }
        },
        "checkpoints": {},
        "zones": {},
        "journeys": [{"id": "J", "stages": [D, "E"]}],
        "transitions": [{"from": D, "to": "E", "journey_id": "J"}],
    }
    return Scenario(
        raw=raw,
        walkable_area_wkt=WALKABLE.wkt,
        model_type="CollisionFreeSpeedModel",
        seed=SEED,
        sim_params=raw["config"]["simulation_settings"]["simulationParams"],
        source_path=None,
    )


@pytest.fixture
def run():
    results = []

    def _run(scenario):
        with contextlib.redirect_stdout(io.StringIO()):
            result = run_scenario(scenario, seed=SEED)
        results.append(result)
        return result

    yield _run
    for result in results:
        result.cleanup()


def _manifest_outcome(result) -> dict:
    with open(result.manifest_file, encoding="utf-8") as fh:
        return json.load(fh)["outcome"]


def _assert_counts(result, *, evacuated, remaining, not_spawned, configured):
    """Every configured agent is evacuated, inside or not spawned.

    ``total_agents`` counts the agents that entered, so it is the evacuated
    and the remaining ones, and with the not spawned ones it is the number
    the deck asked for.
    """
    assert result.agents_evacuated == evacuated
    assert result.agents_remaining == remaining
    assert result.agents_not_spawned == not_spawned
    assert result.total_agents == result.agents_evacuated + result.agents_remaining
    assert result.total_agents + result.agents_not_spawned == configured


def test_run_that_empties_is_completed(run):
    result = run(_scenario(ENOUGH_S))
    _assert_counts(
        result,
        evacuated=NUM_AGENTS,
        remaining=0,
        not_spawned=0,
        configured=NUM_AGENTS,
    )
    assert result.agents_remaining == 0
    assert result.success is True
    assert result.status == "completed"
    assert result.agents_not_spawned == 0
    assert result.end_reason == "all_evacuated"
    assert _manifest_outcome(result) == {
        "status": "completed",
        "end_reason": "all_evacuated",
        "agents_remaining": 0,
        "agents_not_spawned": 0,
    }


def test_time_limit_with_agents_inside_is_incomplete(run):
    result = run(_scenario(TOO_SHORT_S))
    # The exit is 5.8 m or more away: 1 s at 1.3 m/s gets nobody out.
    _assert_counts(
        result,
        evacuated=0,
        remaining=NUM_AGENTS,
        not_spawned=0,
        configured=NUM_AGENTS,
    )
    assert result.evacuation_time >= TOO_SHORT_S
    assert result.agents_remaining == NUM_AGENTS
    assert result.success is False
    assert result.status == "incomplete"
    assert result.metrics["all_evacuated"] is False
    assert result.end_reason == "time_limit"
    assert _manifest_outcome(result) == {
        "status": "incomplete",
        "end_reason": "time_limit",
        "agents_remaining": NUM_AGENTS,
        "agents_not_spawned": 0,
    }


def test_time_limit_before_every_flow_agent_entered_is_incomplete(run):
    # One agent every 10 s: by the limit only the first has entered.
    result = run(
        _scenario(
            TOO_SHORT_S,
            use_flow_spawning=True,
            flow_start_time=0,
            flow_end_time=10 * NUM_AGENTS,
        )
    )
    # One agent every 10 s: the one of t = 0 is in, five are not.
    _assert_counts(
        result,
        evacuated=0,
        remaining=1,
        not_spawned=NUM_AGENTS - 1,
        configured=NUM_AGENTS,
    )
    assert result.success is False
    assert result.status == "incomplete"
    # The flow window is still open at the limit.
    assert result.end_reason == "time_limit"
    assert _manifest_outcome(result)["end_reason"] == "time_limit"
    assert _manifest_outcome(result)["agents_not_spawned"] == (
        result.agents_not_spawned
    )


def _result(**metrics) -> SimpleNamespace:
    base = {
        "success": True,
        "evacuation_time": 12.5,
        "agents_evacuated": 6,
        "total_agents": 6,
        "agents_remaining": 0,
        "agents_not_spawned": 0,
    }
    return SimpleNamespace(**{**base, **metrics})


def test_cli_summary_of_a_completed_run():
    import run as cli

    assert cli._summary_line(_result()) == (
        "Simulation finished in 12.50 s (6/6 evacuated)."
    )


def test_cli_summary_of_an_incomplete_run():
    import run as cli

    line = cli._summary_line(
        _result(success=False, agents_evacuated=2, agents_remaining=4)
    )
    assert line == (
        "Simulation incomplete: time limit reached after 12.50 s "
        "(2/6 evacuated, 4 remaining)."
    )


def test_cli_summary_counts_flow_agents_not_spawned():
    import run as cli

    line = cli._summary_line(
        _result(
            success=False,
            agents_evacuated=1,
            total_agents=1,
            agents_remaining=0,
            agents_not_spawned=5,
        )
    )
    assert line.endswith("(1/1 evacuated, 0 remaining, 5 not spawned).")


def test_cli_summary_of_a_run_whose_flow_windows_closed():
    import run as cli

    line = cli._summary_line(
        _result(
            success=False,
            agents_evacuated=1,
            total_agents=1,
            agents_not_spawned=5,
            end_reason="flows_closed",
        )
    )
    assert line == (
        "Simulation incomplete: flow windows closed after 12.50 s "
        "(1/1 evacuated, 0 remaining, 5 not spawned)."
    )


def test_cli_summary_of_a_run_whose_mobile_agents_all_left():
    import run as cli

    line = cli._summary_line(
        _result(
            success=False,
            agents_evacuated=4,
            agents_remaining=2,
            end_reason="all_mobile_left",
        )
    )
    assert line == (
        "Simulation incomplete: all mobile agents left after 12.50 s "
        "(4/6 evacuated, 2 remaining)."
    )


def test_run_outcome_words_a_run_that_ended_with_only_dead_agents_inside():
    from pyfds_evac.config.frontend import run_outcome

    outcome = run_outcome("incomplete", 2, 0, "all_mobile_left", incapacitated=2)
    assert outcome.complete is False
    assert outcome.label == "Incomplete: all mobile agents left, 2 incapacitated inside"
    assert outcome.time_label == "Simulated time"
    with_flow = run_outcome("incomplete", 2, 3, "all_mobile_left", incapacitated=2)
    assert with_flow.label.endswith("2 incapacitated inside, 3 not spawned")
    # Without the count, the agents inside are the incapacitated ones.
    assert run_outcome("incomplete", 2, 0, "all_mobile_left").label == outcome.label


def test_generated_script_words_a_run_that_ended_with_only_dead_agents_inside():
    from pyfds_evac.config.script import python_script

    code = python_script({"scenario": "x.json"})
    assert '"all_mobile_left": "all mobile agents left"' in code


def test_cli_summary_of_a_deadlocked_run():
    import run as cli

    line = cli._summary_line(
        _result(
            success=False,
            evacuation_time=118.0,
            agents_evacuated=3,
            total_agents=5,
            agents_remaining=2,
            end_reason="deadlock",
            metrics={"deadlock": {"agents": 2, "since_s": 18.0, "positions": []}},
        )
    )
    assert line == (
        "Simulation incomplete: deadlock, 2 agents stuck since t = 18.00 s, "
        "after 118.00 s (3/5 evacuated, 2 remaining)."
    )


def test_run_outcome_words_a_deadlocked_run():
    from pyfds_evac.config.frontend import run_outcome

    outcome = run_outcome("incomplete", 3, 0, "deadlock", incapacitated=1)
    assert outcome.complete is False
    assert outcome.label == "Incomplete: deadlock, 2 agents stuck"
    assert outcome.time_label == "Simulated time"
    assert run_outcome("incomplete", 1, 4, "deadlock").label == (
        "Incomplete: deadlock, 1 agent stuck, 4 not spawned"
    )


def test_generated_script_words_a_deadlocked_run():
    from pyfds_evac.config.script import python_script

    code = python_script({"scenario": "x.json"})
    assert '"deadlock": "deadlock"' in code


@pytest.mark.parametrize(
    ("max_time_s", "expected"),
    [(ENOUGH_S, 0), (TOO_SHORT_S, 2)],
    ids=["completed", "incomplete"],
)
def test_cli_exit_status(monkeypatch, tmp_path, max_time_s, expected):
    """run.py exits 0 for a completed run and 2 for an incomplete one."""
    import run as cli

    monkeypatch.setattr(cli, "load_scenario", lambda _path: _scenario(max_time_s))
    sqlite = tmp_path / "run.sqlite"
    monkeypatch.setattr(
        "sys.argv",
        ["run.py", "--scenario", "unused.json", "--output-sqlite", str(sqlite)],
    )
    with contextlib.redirect_stdout(io.StringIO()):
        status = cli.main()
    assert status == expected
    assert cli.EXIT_INCOMPLETE == 2
    # An incomplete run still writes its outputs.
    assert sqlite.exists()
