"""``premovement_offset_s``: a fixed delay added to every pre-movement draw.

Absent, nothing changes. Present, it must be a finite number >= 0 and
needs ``use_premovement: true``, or set-up stops with a ValueError that
names the distribution.
"""

from __future__ import annotations

import contextlib
import sqlite3

import numpy as np
import pytest
from shapely.geometry import box

from pyfds_evac.core.scenario import Scenario, run_scenario
from pyfds_evac.core.simulation_init import (
    _offset_times,
    _premovement_offset,
    _premovement_offset_unused,
)

V0 = 1.25
EXIT = box(0.0, 0.0, 0.5, 2.0)


def test_absent_offset_leaves_the_draw_untouched():
    times = np.array([1.0, 2.5])
    assert _offset_times(times, {}, "d") is times


def test_offset_is_added_to_every_draw():
    shifted = _offset_times(np.array([1.0, 2.5]), {"premovement_offset_s": 5}, "d")
    assert shifted.tolist() == [6.0, 7.5]


@pytest.mark.parametrize("bad", [-1.0, float("nan"), float("inf"), "5", True])
def test_bad_offset_is_an_error_naming_the_distribution(bad):
    with pytest.raises(ValueError, match="'room'.*premovement_offset_s"):
        _premovement_offset({"premovement_offset_s": bad}, "room")


def test_offset_without_premovement_is_an_error():
    with pytest.raises(ValueError, match="'room'.*use_premovement"):
        _premovement_offset_unused({"premovement_offset_s": 2.0}, "room")
    _premovement_offset_unused({}, "room")


def _journey_scenario(offset: float | None) -> Scenario:
    """A 10 x 2 m corridor, one agent, a journey to the west exit."""
    params = {
        "number": 1,
        "radius": 0.2,
        "v0": V0,
        "v0_distribution": "constant",
        "use_premovement": True,
        "premovement_distribution": "constant",
        "premovement_param_a": 1.0,
    }
    if offset is not None:
        params["premovement_offset_s"] = offset
    raw = {
        "config": {
            "simulation_settings": {
                "simulationParams": {
                    "max_simulation_time": 60,
                    "model_type": "CollisionFreeSpeedModel",
                },
                "baseSeed": 3,
            }
        },
        "exits": {"E": {"type": "polygon", "coordinates": _ring(EXIT)}},
        "distributions": {
            "jps-distributions_0": {
                "type": "polygon",
                "coordinates": _ring(box(7.5, 0.6, 8.5, 1.4)),
                "parameters": params,
            }
        },
        "journeys": [
            {
                "id": "journey_0",
                "stages": ["jps-distributions_0", "E"],
                "transitions": [
                    {
                        "from": "jps-distributions_0",
                        "to": "E",
                        "journey_id": "journey_0",
                    }
                ],
            }
        ],
        "transitions": [
            {"from": "jps-distributions_0", "to": "E", "journey_id": "journey_0"}
        ],
    }
    sim = raw["config"]["simulation_settings"]["simulationParams"]
    return Scenario(
        raw=raw,
        walkable_area_wkt=box(0, 0, 10, 2).wkt,
        model_type="CollisionFreeSpeedModel",
        seed=3,
        sim_params=sim,
        source_path=None,
    )


def _ring(polygon) -> list[list[float]]:
    return [[x, y] for x, y in polygon.exterior.coords]


def _start_and_removal(scenario: Scenario) -> tuple[float, float]:
    result = run_scenario(scenario, seed=3)
    try:
        assert result.metrics["all_evacuated"]
        with contextlib.closing(sqlite3.connect(result.sqlite_file)) as con:
            fps = float(
                con.execute("SELECT value FROM metadata WHERE key='fps'").fetchone()[0]
            )
            rows = con.execute(
                "SELECT frame, pos_x FROM trajectory_data ORDER BY frame"
            ).fetchall()
    finally:
        result.cleanup()
    return rows[0][1], rows[-1][0] / fps


def test_offset_applies_in_a_scenario_with_journeys():
    """R1: the journey path rebuilt the parameters without the key."""
    x_start, removed = _start_and_removal(_journey_scenario(2.0))
    walk = (x_start - EXIT.bounds[2]) / V0
    assert removed == pytest.approx(1.0 + 2.0 + walk, abs=0.15)


def test_bad_offset_is_rejected_in_a_scenario_with_journeys():
    with pytest.raises(ValueError, match="premovement_offset_s"):
        run_scenario(_journey_scenario(-1.0), seed=3)
