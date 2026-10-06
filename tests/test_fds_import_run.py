"""An imported FDS+Evac deck runs: set-up, removal, and one closed-form time.

JuPedSim runs are not bit-reproducible, so only aggregate invariants are
asserted, plus the single-agent removal time of the import contract:
an agent walking straight at v0 to an exit strip of depth d is removed when
its centre comes within 0.03 m of the strip, at (L - d - 0.03) / v0.
"""

from __future__ import annotations

import contextlib
import sqlite3
from collections import Counter

import pytest

from pyfds_evac.core.direct_steering_runtime import EXIT_REACH_TOLERANCE_M
from pyfds_evac.core.fds_import import import_fds_deck
from pyfds_evac.core.scenario import load_scenario, run_scenario

ROOM = """\
&HEAD CHID='room' /
&MESH IJK=100,100,24, XB=0,10,0,10,0,2.4 /
&MESH IJK=100,100,1, XB=0,10,0,10,0.4,1.6, EVACUATION=.TRUE., EVAC_HUMANS=.TRUE.,
      ID='Main' /
&TIME T_END=120 /
&PERS ID='P', VELOCITY_DIST=0, VEL_MEAN=1.25, PRE_MEAN=0, DET_MEAN=0 /
&EXIT ID='West', IOR=-1, XB=0,0,4,6,0.4,1.6 /
&EXIT ID='East', IOR=1, XB=10,10,4,6,0.4,1.6 /
&EVAC ID='g', XB=1,9,1,9,1,1, NUMBER_INITIAL_PERSONS=25, PERS_ID='P',
      KNOWN_DOOR_NAMES='West','East' /
&EVHO XB=4,6,4,6,1,1 /
"""

# A 10 x 2 m corridor with its only exit across the west end.
CORRIDOR = """\
&HEAD CHID='corridor' /
&MESH IJK=100,20,1, XB=0,10,0,2,0.4,1.6, EVACUATION=.TRUE., EVAC_HUMANS=.TRUE.,
      ID='Main' /
&PERS ID='P', VELOCITY_DIST=0, VEL_MEAN=1.25, PRE_MEAN=0, DET_MEAN=0 /
&EXIT ID='West', IOR=-1, XB=0,0,0,2,0.4,1.6 /
&EVAC ID='one', XB=7.5,8.5,0.6,1.4,1,1, NUMBER_INITIAL_PERSONS=1, PERS_ID='P',
      KNOWN_DOOR_NAMES='West' /
"""
DEPTH = 0.5
V0 = 1.25


def _imported(tmp_path, deck: str, wkt: str):
    path = tmp_path / "deck.fds"
    path.write_text(deck, encoding="utf-8")
    result = import_fds_deck(path, walkable_wkt=wkt, exit_depth=DEPTH)
    assert result.report.runnable
    return load_scenario(str(result.write(tmp_path / "scenario")))


def test_imported_room_runs_and_everyone_leaves(tmp_path):
    scenario = _imported(tmp_path, ROOM, "POLYGON((0 0,10 0,10 10,0 10,0 0))")
    result = run_scenario(scenario, seed=7)
    try:
        assert result.metrics["all_evacuated"]
        assert result.metrics["total_agents"] == 25
        used = Counter(entry["exit_id"] for entry in result.exit_history)
        assert sum(used.values()) == 25
        assert set(used) <= {"West", "East"}
    finally:
        result.cleanup()


def test_single_agent_removal_time(tmp_path):
    scenario = _imported(tmp_path, CORRIDOR, "POLYGON((0 0,10 0,10 2,0 2,0 0))")
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
    x_start, last_frame = rows[0][1], rows[-1][0]
    expected = (x_start - DEPTH - EXIT_REACH_TOLERANCE_M) / V0
    # Removal falls after the last written frame and before the next one.
    assert last_frame / fps == pytest.approx(expected, abs=0.15)
