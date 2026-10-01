"""How a run reports its end: completed, or incomplete at the time limit.

A run that reaches ``max_simulation_time`` with agents inside, or with flow
agents still to enter, is incomplete: ``success`` is False, ``status`` is
``"incomplete"``, and the metrics, the manifest and the CLI summary give the
agents left (#139, #434).

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


def test_run_that_empties_is_completed(run):
    result = run(_scenario(ENOUGH_S))
    assert result.agents_remaining == 0
    assert result.success is True
    assert result.status == "completed"
    assert result.agents_not_spawned == 0
    assert _manifest_outcome(result) == {
        "status": "completed",
        "agents_remaining": 0,
        "agents_not_spawned": 0,
    }


def test_time_limit_with_agents_inside_is_incomplete(run):
    result = run(_scenario(TOO_SHORT_S))
    assert result.evacuation_time >= TOO_SHORT_S
    assert result.agents_remaining == NUM_AGENTS
    assert result.success is False
    assert result.status == "incomplete"
    assert result.metrics["all_evacuated"] is False
    assert _manifest_outcome(result) == {
        "status": "incomplete",
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
    assert result.agents_not_spawned > 0
    assert result.success is False
    assert result.status == "incomplete"
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
