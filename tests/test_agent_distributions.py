"""Labelled runs write which distribution each agent started in (#383).

``assets/station_fahy/validate.py`` excludes victims and unplaced survivors by
the ``population`` label of the distribution an agent was placed in. The
trajectory does not say which that was, so a run of a labelled scenario
carries an ``agent_distributions`` table. Runs of other scenarios do not.
"""

from __future__ import annotations

import argparse
import contextlib
import copy
import sqlite3
import sys
from dataclasses import replace
from pathlib import Path

from shapely.geometry import box

from pyfds_evac.core.run_outputs import apply_outputs
from pyfds_evac.core.scenario import run_scenario

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_initial_exit_per_agent import (  # noqa: E402
    LENGTH_M,
    SEED,
    WIDTH_M,
    _coords,
    _room_scenario,
)


def _two_halves(labels: dict[str, str | None]):
    """The room of the exit-choice tests, as a west and an east distribution."""
    scenario = _room_scenario()
    raw = copy.deepcopy(scenario.raw)
    template = raw["distributions"].pop("room")
    areas = {
        "west": box(0.3, 0.3, LENGTH_M / 2 - 0.3, WIDTH_M - 0.3),
        "east": box(LENGTH_M / 2 + 0.3, 0.3, LENGTH_M - 0.3, WIDTH_M - 0.3),
    }
    for key, area in areas.items():
        params = {**template["parameters"], "number": 5}
        if labels[key] is not None:
            params["population"] = labels[key]
        raw["distributions"][key] = {
            "type": "polygon",
            "coordinates": _coords(area),
            "parameters": params,
        }
    return replace(scenario, raw=raw)


def _run(tmp_path, labels):
    scenario = _two_halves(labels)
    result = run_scenario(scenario, seed=SEED)
    out = tmp_path / "run.sqlite"
    opts = argparse.Namespace(
        output_sqlite=str(out),
        output_smoke_history=None,
        output_fed_history=None,
        output_route_history=None,
        output_route_cost_history=None,
        cleanup=True,
    )
    apply_outputs(result, scenario, opts, log=lambda *_: None)
    return result, out


def _tables(db: Path) -> set[str]:
    with contextlib.closing(sqlite3.connect(db)) as con:
        rows = con.execute("SELECT name FROM sqlite_master WHERE type='table'")
        return {name for (name,) in rows}


def test_labelled_run_maps_every_agent_to_its_distribution(tmp_path):
    result, out = _run(tmp_path, {"west": "placed", "east": "victim"})
    assert result.agent_distributions is not None
    assert sorted(result.agent_distributions.values()) == ["east"] * 5 + ["west"] * 5
    with contextlib.closing(sqlite3.connect(out)) as con:
        rows = dict(con.execute("SELECT id, distribution FROM agent_distributions"))
        first = dict(
            con.execute(
                "SELECT id, pos_x FROM trajectory_data "
                "WHERE frame = (SELECT MIN(frame) FROM trajectory_data)"
            )
        )
    assert rows == result.agent_distributions
    for agent_id, key in rows.items():
        assert (first[agent_id] < LENGTH_M / 2) == (key == "west")


def test_run_without_labels_writes_no_mapping_table(tmp_path):
    _, out = _run(tmp_path, {"west": None, "east": None})
    assert "agent_distributions" not in _tables(out)
