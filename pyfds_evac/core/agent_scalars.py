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
    """Populate agent_scalars(frame, id, fed, speed) in an existing sqlite.

    frame = round(time_s * fps), with fps read from the metadata table. speed =
    base_speed * speed_factor. No-op when fed_history is empty. Re-invocation
    replaces any existing rows rather than appending duplicates.
    """
    rows = list(fed_history)
    if not rows:
        return

    con = sqlite3.connect(str(sqlite_path))
    try:
        fps = _read_fps(con)
        con.execute(
            "CREATE TABLE IF NOT EXISTS agent_scalars("
            "frame INTEGER NOT NULL, id INTEGER NOT NULL, fed REAL, speed REAL)"
        )
        con.execute("DELETE FROM agent_scalars")
        con.executemany(
            "INSERT INTO agent_scalars(frame, id, fed, speed) VALUES (?, ?, ?, ?)",
            [_scalar_row(r, fps) for r in rows],
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS agent_scalars_idx ON agent_scalars(frame, id)"
        )
        con.commit()
    finally:
        con.close()


def _read_fps(con: sqlite3.Connection) -> float:
    row = con.execute("SELECT value FROM metadata WHERE key = 'fps'").fetchone()
    if row is None:
        raise ValueError("sqlite metadata table has no 'fps' row")
    return float(row[0])


def _scalar_row(row: Mapping[str, Any], fps: float) -> tuple[int, int, float, float]:
    frame = round(float(row["time_s"]) * fps)
    agent_id = int(row["agent_id"])
    fed = float(row["fed_cumulative"])
    speed = float(row["base_speed"]) * float(row["speed_factor"])
    return (frame, agent_id, fed, speed)
