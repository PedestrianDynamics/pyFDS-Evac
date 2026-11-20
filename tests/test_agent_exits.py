"""The output sqlite keeps each agent's exit time for rset_map (#1001)."""

from __future__ import annotations

import argparse
import contextlib
import copy
import json
import sqlite3
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from pyfds_evac import cli
from pyfds_evac.config.script import python_script
from pyfds_evac.core.agent_scalars import write_agent_exits
from pyfds_evac.core.run_outputs import apply_outputs
from pyfds_evac.core.scenario import run_scenario

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_initial_exit_per_agent import SEED, _room_scenario  # noqa: E402

pytest.importorskip("pedpy", minversion="1.5.1")

from pyfds_evac.analysis import load_exit_times  # noqa: E402


def _empty_sqlite(path: Path) -> Path:
    with contextlib.closing(sqlite3.connect(path)) as con:
        con.execute("CREATE TABLE metadata(key TEXT, value TEXT)")
        con.commit()
    return path


def _room(max_time_s: float):
    scenario = _room_scenario()
    raw = copy.deepcopy(scenario.raw)
    raw["distributions"]["room"]["parameters"]["number"] = 15
    scenario = replace(scenario, raw=raw)
    scenario.set_max_time(max_time_s)
    return scenario


@pytest.mark.parametrize("max_time_s", [8.0, 60.0])  # some inside; all out
def test_cli_output_round_trips_the_run_exit_times(tmp_path, max_time_s):
    scenario = _room(max_time_s)
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
    assert result.exit_times
    assert (result.agents_remaining > 0) == (max_time_s == 8.0)
    assert load_exit_times(out) == result.exit_times


def test_generated_script_writes_the_exit_times(tmp_path):
    scenario = _room(8.0)
    path = tmp_path / "scenario.json"
    path.write_text(
        json.dumps({**scenario.raw, "walkable_area_wkt": scenario.walkable_area_wkt})
    )
    out_dir = tmp_path / "out"
    code = python_script(
        cli._build_parser().parse_args(["--scenario", str(path), "--seed", str(SEED)]),
        output_dir=str(out_dir),
    )
    script = tmp_path / "run_script.py"
    script.write_text(code)
    subprocess.run([sys.executable, str(script)], check=False, cwd=tmp_path)
    trajectory = out_dir / "trajectory.sqlite"
    exits = load_exit_times(trajectory)
    with contextlib.closing(sqlite3.connect(trajectory)) as con:
        ids = {i for (i,) in con.execute("SELECT DISTINCT id FROM trajectory_data")}
    assert exits and set(exits) < ids  # some still inside at 8 s
    # Agent ids depend on the process's earlier runs; the times do not.
    expected = run_scenario(_room(8.0), seed=SEED).exit_times
    assert sorted(exits.values()) == sorted(expected.values())


def test_an_agent_still_inside_has_no_row_and_nobody_left_is_an_empty_table(tmp_path):
    db = _empty_sqlite(tmp_path / "t.sqlite")
    write_agent_exits(db, {3: 12.5, 1: 4.0})
    assert load_exit_times(db) == {1: 4.0, 3: 12.5}
    write_agent_exits(db, {})  # rewritten, not appended
    assert load_exit_times(db) == {}


def test_a_file_without_the_table_is_refused_not_guessed(tmp_path):
    db = _empty_sqlite(tmp_path / "old.sqlite")
    with pytest.raises(ValueError, match="no agent_exits table"):
        load_exit_times(db)
