"""Write an optional agent_scalars side table into a JuPedSim sqlite.

The base JuPedSim schema (trajectory_data, metadata, geometry, frame_data) is
never touched, so jupedsim replay and Web-Based-JuPedSim still read the file.
fds-viewer reads agent_scalars to colour agents by FED or speed.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any


def write_agent_scalars(
    sqlite_path: str | Path, fed_history: Iterable[Mapping[str, Any]]
) -> None:
    """Populate agent_scalars(frame, id, fed, heat_fed, speed, in_fds_domain).

    frame = round(time_s * fps), with fps read from the metadata table. speed =
    base_speed * speed_factor. in_fds_domain is 1 where the FDS slices cover
    the agent, 0 where it read ambient air, NULL when the row has no flag. No-op when fed_history is empty. Re-invocation
    replaces any existing rows rather than appending duplicates.

    ``CREATE TABLE IF NOT EXISTS`` is a no-op against a pre-existing table
    with a different schema -- fine here because ``sqlite_path`` is always a
    fresh per-run tempfile (see ``scenario.py``), never a stale file from
    before ``heat_fed`` existed.
    """
    rows = list(fed_history)
    if not rows:
        return

    con = sqlite3.connect(str(sqlite_path))
    try:
        fps = _read_fps(con)
        con.execute(
            "CREATE TABLE IF NOT EXISTS agent_scalars("
            "frame INTEGER NOT NULL, id INTEGER NOT NULL, fed REAL, "
            "heat_fed REAL, speed REAL, in_fds_domain INTEGER)"
        )
        con.execute("DELETE FROM agent_scalars")
        con.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS agent_scalars_idx "
            "ON agent_scalars(frame, id)"
        )
        con.executemany(
            "INSERT OR REPLACE INTO agent_scalars"
            "(frame, id, fed, heat_fed, speed, in_fds_domain) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [_scalar_row(r, fps) for r in rows],
        )
        con.commit()
    finally:
        con.close()


def _read_fps(con: sqlite3.Connection) -> float:
    row = con.execute("SELECT value FROM metadata WHERE key = 'fps'").fetchone()
    if row is None:
        raise ValueError("sqlite metadata table has no 'fps' row")
    return float(row[0])


def _scalar_row(
    row: Mapping[str, Any], fps: float
) -> tuple[int, int, float, float, float, int | None]:
    frame = round(float(row["time_s"]) * fps)
    agent_id = int(row["agent_id"])
    fed = float(row["fed_cumulative"])
    heat_fed = float(row.get("heat_fed_cumulative", 0.0))
    speed = float(row["base_speed"]) * float(row["speed_factor"])
    flag = row.get("in_fds_domain")
    in_domain = None if flag is None else int(bool(flag))
    return (frame, agent_id, fed, heat_fed, speed, in_domain)
