"""Trajectory hash used by the determinism and equivalence checks (review O3).

Usage: python traj_hash.py RUN.sqlite [...]

Canonical recipe ("repr-v1"): rows of trajectory_data
``frame, id, pos_x, pos_y, ori_x, ori_y`` ordered by ``frame, id``; each row
is the comma-joined ``repr()`` of the six values (Python floats, so repr is
the shortest round-trip form), rows joined by "\\n" with a trailing "\\n";
sha256 of the UTF-8 bytes.

The G0 handoffs quoted a different recipe ("sqlite-cli"): the sqlite3 command
line tool in list mode,
``sqlite3 RUN.sqlite "select frame,id,pos_x,pos_y,ori_x,ori_y from
trajectory_data order by frame,id" | shasum -a 256``, i.e. "|"-separated
values in sqlite's own float formatting (%!.15g), one row per line. The two
recipes give different digests for the same file; both are printed.
"""

import hashlib
import sqlite3
import subprocess
import sys

QUERY = "select frame,id,pos_x,pos_y,ori_x,ori_y from trajectory_data order by frame,id"


def traj_hash(path: str) -> str:
    h = hashlib.sha256()
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        for row in con.execute(QUERY):
            h.update((",".join(repr(v) for v in row) + "\n").encode())
    finally:
        con.close()
    return h.hexdigest()


def traj_hash_sqlite_cli(path: str) -> str | None:
    try:
        out = subprocess.run(["sqlite3", path, QUERY], capture_output=True, check=True).stdout
    except Exception:
        return None
    return hashlib.sha256(out).hexdigest()


if __name__ == "__main__":
    for p in sys.argv[1:]:
        print(f"repr-v1 {traj_hash(p)}  sqlite-cli {traj_hash_sqlite_cli(p)}  {p}")
