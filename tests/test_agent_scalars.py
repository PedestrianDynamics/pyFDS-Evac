import sqlite3
from pathlib import Path

from pyfds_evac.core.agent_scalars import write_agent_scalars


def _make_base_sqlite(path: Path, fps: float = 10.0) -> None:
    """Minimal JuPedSim-shaped sqlite: metadata + trajectory_data only."""
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    con.execute("INSERT INTO metadata VALUES('fps', ?)", (str(fps),))
    con.execute(
        "CREATE TABLE trajectory_data("
        "frame INTEGER, id INTEGER, pos_x REAL, pos_y REAL, ori_x REAL, ori_y REAL)"
    )
    con.commit()
    con.close()


def test_writes_frame_id_fed_speed(tmp_path):
    db = tmp_path / "run.sqlite"
    _make_base_sqlite(db, fps=10.0)
    fed_history = [
        {
            "time_s": 0.0,
            "agent_id": 1,
            "fed_cumulative": 0.0,
            "base_speed": 1.2,
            "speed_factor": 1.0,
        },
        {
            "time_s": 1.0,
            "agent_id": 1,
            "fed_cumulative": 0.25,
            "base_speed": 1.2,
            "speed_factor": 0.5,
        },
    ]
    write_agent_scalars(db, fed_history)

    con = sqlite3.connect(db)
    rows = con.execute(
        "SELECT frame, id, fed, speed FROM agent_scalars ORDER BY frame"
    ).fetchall()
    con.close()
    assert rows == [(0, 1, 0.0, 1.2), (10, 1, 0.25, 0.6)]


def test_noop_on_empty_history(tmp_path):
    db = tmp_path / "run.sqlite"
    _make_base_sqlite(db)
    write_agent_scalars(db, [])
    con = sqlite3.connect(db)
    exists = con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='agent_scalars'"
    ).fetchone()
    con.close()
    assert exists is None


def test_multiple_agents_same_frame(tmp_path):
    db = tmp_path / "run.sqlite"
    _make_base_sqlite(db, fps=10.0)
    fed_history = [
        {
            "time_s": 1.0,
            "agent_id": 1,
            "fed_cumulative": 0.1,
            "base_speed": 1.0,
            "speed_factor": 1.0,
        },
        {
            "time_s": 1.0,
            "agent_id": 2,
            "fed_cumulative": 0.2,
            "base_speed": 1.0,
            "speed_factor": 0.5,
        },
    ]
    write_agent_scalars(db, fed_history)
    con = sqlite3.connect(db)
    rows = con.execute(
        "SELECT frame, id, fed, speed FROM agent_scalars ORDER BY id"
    ).fetchall()
    con.close()
    assert rows == [(10, 1, 0.1, 1.0), (10, 2, 0.2, 0.5)]


def test_rewrite_replaces_rows(tmp_path):
    db = tmp_path / "run.sqlite"
    _make_base_sqlite(db, fps=10.0)
    history = [
        {
            "time_s": 0.0,
            "agent_id": 1,
            "fed_cumulative": 0.0,
            "base_speed": 1.0,
            "speed_factor": 1.0,
        }
    ]
    write_agent_scalars(db, history)
    write_agent_scalars(db, history)
    con = sqlite3.connect(db)
    (count,) = con.execute("SELECT count(*) FROM agent_scalars").fetchone()
    con.close()
    assert count == 1
