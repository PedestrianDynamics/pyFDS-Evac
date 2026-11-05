"""``--output-pre-evacuation-times``: one pre-movement row per held agent (#120).

``ScenarioResult.pre_evacuation_times`` lists every agent that had a
pre-movement time: its distribution, the drawn time and the simulation time
it was released. Both initialisers (with and without journeys) fill it.
"""

from __future__ import annotations

import argparse
import csv

import pytest
from shapely.geometry import box

from pyfds_evac.core.run_outputs import (
    _write_pre_evacuation_times_csv,
    apply_outputs,
)
from pyfds_evac.core.scenario import Scenario, run_scenario

EXIT = box(0.0, 0.0, 0.5, 2.0)
DIST = "jps-distributions_0"
COLUMNS = ["agent_id", "distribution", "premovement_time_s", "movement_start_s"]


def _ring(polygon) -> list[list[float]]:
    return [[x, y] for x, y in polygon.exterior.coords]


def _corridor(*, journeys: bool, premovement: dict, horizon: float = 60) -> Scenario:
    """A 10 x 2 m corridor, one agent, the exit at the west end."""
    params = {
        "number": 1,
        "radius": 0.2,
        "v0": 1.25,
        "v0_distribution": "constant",
        **premovement,
    }
    raw = {
        "config": {
            "simulation_settings": {
                "simulationParams": {
                    "max_simulation_time": horizon,
                    "model_type": "CollisionFreeSpeedModel",
                },
                "baseSeed": 3,
            }
        },
        "exits": {"E": {"type": "polygon", "coordinates": _ring(EXIT)}},
        "distributions": {
            DIST: {
                "type": "polygon",
                "coordinates": _ring(box(7.5, 0.6, 8.5, 1.4)),
                "parameters": params,
            }
        },
    }
    if journeys:
        transition = {"from": DIST, "to": "E", "journey_id": "journey_0"}
        raw["journeys"] = [
            {"id": "journey_0", "stages": [DIST, "E"], "transitions": [transition]}
        ]
        raw["transitions"] = [transition]
    sim = raw["config"]["simulation_settings"]["simulationParams"]
    return Scenario(
        raw=raw,
        walkable_area_wkt=box(0, 0, 10, 2).wkt,
        model_type="CollisionFreeSpeedModel",
        seed=3,
        sim_params=sim,
        source_path=None,
    )


HELD_1_S = {
    "use_premovement": True,
    "premovement_distribution": "constant",
    "premovement_param_a": 1.0,
}


def _rows(scenario: Scenario):
    result = run_scenario(scenario, seed=3)
    try:
        return result.pre_evacuation_times
    finally:
        result.cleanup()


@pytest.mark.parametrize("journeys", [True, False], ids=["journeys", "fallback"])
def test_a_held_agent_gets_its_distribution_time_and_release(journeys):
    rows = _rows(_corridor(journeys=journeys, premovement=HELD_1_S))
    assert len(rows) == 1
    row = rows[0]
    assert row["distribution"] == DIST
    assert row["premovement_time_s"] == 1.0
    # Released at the first step at or after the drawn time.
    assert 1.0 <= row["movement_start_s"] < 1.1


def test_an_agent_without_premovement_has_no_row():
    rows = _rows(_corridor(journeys=True, premovement={"use_premovement": False}))
    assert rows == []


def test_an_agent_still_held_at_the_end_has_no_start():
    held = {**HELD_1_S, "premovement_param_a": 1000.0}
    rows = _rows(_corridor(journeys=True, premovement=held, horizon=2))
    assert rows[0]["premovement_time_s"] == 1000.0
    assert rows[0]["movement_start_s"] is None


def test_the_csv_has_the_four_columns_and_an_empty_start(tmp_path):
    path = tmp_path / "out" / "pre.csv"
    _write_pre_evacuation_times_csv(
        [
            {
                "agent_id": 3,
                "distribution": DIST,
                "premovement_time_s": 10.0,
                "movement_start_s": 10.01,
            },
            {
                "agent_id": 4,
                "distribution": DIST,
                "premovement_time_s": 99.0,
                "movement_start_s": None,
            },
        ],
        str(path),
    )
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames == COLUMNS
        rows = list(reader)
    assert rows[0] == {
        "agent_id": "3",
        "distribution": DIST,
        "premovement_time_s": "10.0",
        "movement_start_s": "10.01",
    }
    assert rows[1]["movement_start_s"] == ""


class _Result:
    pre_evacuation_times = [
        {
            "agent_id": 0,
            "distribution": DIST,
            "premovement_time_s": 1.0,
            "movement_start_s": 1.0,
        }
    ]
    smoke_history = fed_history = route_history = None
    route_cost_history = exit_history = sqlite_file = None
    metrics: dict = {}


def _opts(**extra) -> argparse.Namespace:
    fields = dict(
        output_sqlite=None,
        output_smoke_history=None,
        output_fed_history=None,
        output_route_history=None,
        output_route_cost_history=None,
    )
    return argparse.Namespace(**{**fields, **extra})


def test_apply_outputs_writes_the_file_when_asked(tmp_path):
    path = tmp_path / "pre.csv"
    artifacts = apply_outputs(
        _Result(), None, _opts(output_pre_evacuation_times=str(path)), log=print
    )
    assert artifacts == [f"Pre-evacuation times CSV: {path}"]
    assert path.read_text().splitlines()[0] == ",".join(COLUMNS)


def test_apply_outputs_without_the_option_writes_nothing(tmp_path):
    assert apply_outputs(_Result(), None, _opts(), log=print) == []
