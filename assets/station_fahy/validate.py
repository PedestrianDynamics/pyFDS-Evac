#!/usr/bin/env python3
"""Compare a run against Fahy Table 2, row by row.

Usage:
    .venv/bin/python assets/station_fahy/validate.py RUN.sqlite \\
        --config assets/station_fahy/config.json [--plot out.png]

Each agent is attributed to the spawn area whose polygon contains its **first**
recorded position, and to the door whose polygon it finished nearest (within
``--reach``). That gives an observed origin->exit matrix directly comparable to
the paper's, with two rules that keep the comparison honest:

* Rows are renormalised over the four modelled doors, **per row** -- see
  :mod:`fahy_table2`. Windows carried 27.9 % of real egress and 45 of the 75
  people by the stage; comparing raw counts would make that row unmatchable.
* Agents that never reach a door are reported separately and excluded from the
  shares, rather than being silently dropped or counted against a door.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import fahy_table2 as F  # noqa: E402

DOOR_BY_EXIT_ID = {
    "jps-exits_0": "front",
    "jps-exits_1": "bar_door",
    "jps-exits_2": "kitchen",
    "jps-exits_3": "stage",
}


def _load(config_path: Path):
    import json

    from shapely.geometry import Polygon

    cfg = json.loads(config_path.read_text())
    exits = {k: Polygon(v["coordinates"]) for k, v in cfg["exits"].items()}
    areas = {
        k: (Polygon(v["coordinates"]), v["parameters"].get("fahy_row", k))
        for k, v in cfg["distributions"].items()
    }
    return exits, areas


def observed_matrix(sqlite_path: Path, config_path: Path, reach: float):
    from shapely.geometry import Point

    exits, areas = _load(config_path)
    con = sqlite3.connect(sqlite_path)
    rows = con.execute(
        "SELECT id, frame, pos_x, pos_y FROM trajectory_data ORDER BY id, frame"
    ).fetchall()

    first: dict[int, tuple[float, float]] = {}
    last: dict[int, tuple[float, float]] = {}
    for aid, _frame, x, y in rows:
        first.setdefault(aid, (x, y))
        last[aid] = (x, y)

    matrix: dict[str, dict[str, int]] = {}
    stuck: dict[str, int] = {}
    for aid, start in first.items():
        p0 = Point(*start)
        origin = next(
            (label for _, (poly, label) in areas.items() if poly.contains(p0)), None
        )
        if origin is None:
            continue
        p1 = Point(*last[aid])
        near = min(exits.items(), key=lambda kv: p1.distance(kv[1]))
        if p1.distance(near[1]) > reach:
            stuck[origin] = stuck.get(origin, 0) + 1
            continue
        door = DOOR_BY_EXIT_ID[near[0]]
        matrix.setdefault(origin, {}).setdefault(door, 0)
        matrix[origin][door] += 1
    return matrix, stuck


def report(matrix, stuck) -> int:
    print(
        f"{'area at ignition':32s} {'n':>4s}  " + "".join(f"{d:>10s}" for d in F.DOORS)
    )
    print(f"{'':32s} {'':>4s}  " + "".join(f"{'obs / Fahy':>10s}" for _ in F.DOORS))
    print("-" * 84)

    worst = 0.0
    for row in F.PLACEABLE:
        target = F.door_shares(row)
        if not target:
            continue
        obs = matrix.get(row, {})
        n = sum(obs.values())
        if n == 0:
            print(f"{row:32s} {0:4d}   (no agent reached a door)")
            continue
        cells = []
        for d in F.DOORS:
            o = obs.get(d, 0) / n
            cells.append(f"{o:4.0%}/{target[d]:<5.0%}")
            worst = max(worst, abs(o - target[d]))
        print(f"{row:32s} {n:4d}  " + "".join(f"{c:>10s}" for c in cells))

    total = sum(sum(v.values()) for v in matrix.values())
    front = sum(v.get("front", 0) for v in matrix.values())
    print("-" * 84)
    print(f"agents reaching a door: {total}   never reached one: {sum(stuck.values())}")
    if total:
        print(
            f"front-door share: {front / total:.1%}   "
            f"(Fahy: {F.aggregate_door_shares()['front']:.1%} of door users, "
            f"and >= {F.front_door_attempt_floor():.0%} of all survivors tried it)"
        )
    print(f"largest per-row deviation: {worst:.0%}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("sqlite", type=Path)
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument(
        "--reach",
        type=float,
        default=2.0,
        help="metres from a door polygon that counts as using it",
    )
    args = ap.parse_args()
    matrix, stuck = observed_matrix(args.sqlite, args.config, args.reach)
    return report(matrix, stuck)


if __name__ == "__main__":
    raise SystemExit(main())
