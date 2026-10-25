"""``premovement_preset``: a constant pre-movement from C/VM2 Table 3.3 (#418)."""

from __future__ import annotations

import contextlib
import sqlite3

import pytest
from shapely.geometry import box

from pyfds_evac.core.premovement_distributions import CVM2_PREMOVEMENT_PRESETS
from pyfds_evac.core.scenario import Scenario, run_scenario
from pyfds_evac.core.simulation_init import _apply_premovement_preset

V0 = 1.25
EXIT = box(0.0, 0.0, 0.5, 2.0)


def test_every_table_row_is_a_preset():
    assert CVM2_PREMOVEMENT_PRESETS == {
        "cvm2_office_origin": 30.0,
        "cvm2_office_remote": 60.0,
        "cvm2_retail_origin": 60.0,
        "cvm2_retail_remote": 120.0,
        "cvm2_retail_origin_voice": 30.0,
        "cvm2_retail_remote_voice": 60.0,
        "cvm2_apartment_origin": 60.0,
        "cvm2_apartment_remote": 300.0,
        "cvm2_hotel_origin": 60.0,
        "cvm2_hotel_remote": 600.0,
        "cvm2_hotel_remote_voice": 300.0,
        "cvm2_daycare_origin": 60.0,
        "cvm2_daycare_remote": 120.0,
        "cvm2_hospital_origin": 60.0,
        "cvm2_hospital_remote": 1800.0,
        "cvm2_focused_origin": 0.0,
    }


def test_preset_becomes_a_constant_premovement():
    assert _apply_premovement_preset(
        {"premovement_preset": "cvm2_hotel_remote"}, "d0"
    ) == {
        "use_premovement": True,
        "premovement_distribution": "constant",
        "premovement_param_a": 600.0,
    }


def test_params_without_a_preset_are_unchanged():
    assert _apply_premovement_preset({"number": 3}, "d0") == {"number": 3}


@pytest.mark.parametrize(
    "clash",
    [
        {"premovement_distribution": "gamma"},
        {"premovement_param_a": 5},
        {"premovement_param_b": 5},
        {"use_premovement": False},
    ],
)
def test_preset_conflicts_are_errors(clash):
    params = {**clash, "premovement_preset": "cvm2_office_origin"}
    with pytest.raises(ValueError, match="d0.*premovement_preset"):
        _apply_premovement_preset(params, "d0")


def test_null_preset_is_dropped_so_the_default_applies():
    params = {"number": 3, "premovement_preset": None}
    assert _apply_premovement_preset(params, "d0") == {"number": 3}


@pytest.mark.parametrize("name", [["cvm2_office_origin"], {}, 30])
def test_non_string_preset_is_a_value_error(name):
    with pytest.raises(ValueError, match="d0.*premovement_preset"):
        _apply_premovement_preset({"premovement_preset": name}, "d0")


def test_preset_is_logged_once(caplog):
    with caplog.at_level("INFO", logger="pyfds_evac.core.simulation_init"):
        _apply_premovement_preset({"premovement_preset": "cvm2_office_origin"}, "d0")
    lines = [r for r in caplog.records if "C/VM2 Table 3.3" in r.getMessage()]
    assert len(lines) == 1
    assert "cvm2_office_origin" in lines[0].getMessage()


def test_preset_is_not_logged_with_flow_spawning(caplog):
    params = {"premovement_preset": "cvm2_office_origin", "use_flow_spawning": True}
    with caplog.at_level("INFO", logger="pyfds_evac.core.simulation_init"):
        _apply_premovement_preset(params, "d0")
    assert not [r for r in caplog.records if "C/VM2 Table 3.3" in r.getMessage()]


def test_unknown_preset_lists_the_names():
    with pytest.raises(ValueError, match="cvm2_office_origin"):
        _apply_premovement_preset({"premovement_preset": "office"}, "d0")


def test_offset_and_seed_are_kept():
    result = _apply_premovement_preset(
        {
            "premovement_preset": "cvm2_office_origin",
            "premovement_offset_s": 30,
            "premovement_seed": 4,
        },
        "d0",
    )
    assert result["premovement_offset_s"] == 30
    assert result["premovement_seed"] == 4


def _journey_scenario(params: dict, journeys: bool = True) -> Scenario:
    """A 10 x 2 m corridor, one agent, optionally a journey to the west exit."""
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
                "parameters": {
                    "number": 1,
                    "radius": 0.2,
                    "v0": V0,
                    "v0_distribution": "constant",
                    **params,
                },
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
    if not journeys:
        del raw["journeys"], raw["transitions"]
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


@pytest.mark.parametrize("journeys", [True, False], ids=["journeys", "no-journeys"])
def test_preset_applies_in_a_run(journeys):
    scenario = _journey_scenario({"premovement_preset": "cvm2_office_origin"}, journeys)
    x_start, removed = _start_and_removal(scenario)
    walk = (x_start - EXIT.bounds[2]) / V0
    assert removed == pytest.approx(30.0 + walk, abs=0.15)
