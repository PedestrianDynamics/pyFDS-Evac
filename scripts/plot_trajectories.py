#!/usr/bin/env python3
"""Plot agent trajectories from a JuPedSim SQLite, coloured by the exit reached.

Every other plot in this repository derives from ``rank_routes`` -- what routing
*would* decide. This one reads what agents *did*, from the trajectory database a
run actually wrote. The distinction is not academic: issue #61 records a case
where the two disagree, so a picture drawn from the router can assert a
behaviour the simulation does not produce.

The exit each agent reached is inferred from its last recorded position: the
nearest exit polygon, provided the agent finished within ``--reach`` metres of
it. Agents that ended elsewhere are drawn grey and counted separately, so a run
where most agents never got out cannot masquerade as a clean result.

Pass ``--route-history`` to colour each path by the exit the agent was aiming
at *at that moment* rather than by the one it eventually used, with a marker
where it changed its mind. Without it a scenario whose whole point is a
mid-corridor switch looks like agents that headed for the near door from the
start -- the destination is visible, the decision is not.

Usage:
    .venv/bin/python scripts/plot_trajectories.py RUN.sqlite \
        --config assets/<scenario>/config.json -o out.png [--title "..."] \
        [--route-history routes.csv]
"""

from __future__ import annotations

import argparse
import bisect
import csv
import json
import sqlite3
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Polygon as MplPoly  # noqa: E402
from shapely.geometry import Point, Polygon  # noqa: E402
from shapely import wkt as shapely_wkt  # noqa: E402

PALETTE = ["#2b7bba", "#d94801", "#31a354", "#756bb1", "#e6ab02"]
UNFINISHED = "#b0b0b0"


def load_tracks(db_path: Path):
    """Return ({agent_id: [(t, x, y), ...]} ordered by time, fps)."""
    with sqlite3.connect(db_path) as con:
        fps = float(dict(con.execute("SELECT * FROM metadata"))["fps"])
        rows = con.execute(
            "SELECT id, frame, pos_x, pos_y FROM trajectory_data ORDER BY id, frame"
        ).fetchall()
    tracks: dict[int, list[tuple[float, float, float]]] = {}
    for agent_id, frame, x, y in rows:
        tracks.setdefault(agent_id, []).append((frame / fps, x, y))
    return tracks


def load_targets(csv_path: Path) -> dict[int, list[tuple[float, str]]]:
    """Return {agent_id: [(time_s, exit_id), ...]} from a route-history CSV.

    Each row is a switch, so the list is a step function: the agent aims at
    ``exit_id`` from ``time_s`` until the next row.
    """
    switches: dict[int, list[tuple[float, str]]] = {}
    with csv_path.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            switches.setdefault(int(row["agent_id"]), []).append(
                (float(row["time_s"]), row["new_exit"])
            )
    for entries in switches.values():
        entries.sort()
    return switches


def target_at(entries: list[tuple[float, str]], t: float) -> str | None:
    """The exit the agent was aiming at at time *t*, or None before its first."""
    idx = bisect.bisect_right([time for time, _ in entries], t) - 1
    return entries[idx][1] if idx >= 0 else None


def draw_by_target(ax, track, entries, colours):
    """Draw one path in segments, recoloured wherever the target changes."""
    run: list[tuple[float, float]] = []
    current: str | None = None
    for t, x, y in track:
        aim = target_at(entries, t)
        if aim != current and run:
            # Carry the joining point into the next run so the line stays whole.
            ax.plot(
                *zip(*run), lw=0.8, alpha=0.6, color=colours.get(current, UNFINISHED)
            )
            ax.plot(
                [x],
                [y],
                marker="o",
                ms=3.0,
                mew=0,
                color=colours.get(aim, UNFINISHED),
                alpha=0.9,
                zorder=5,
            )
            run = [run[-1]]
        current = aim
        run.append((x, y))
    if len(run) > 1:
        ax.plot(*zip(*run), lw=0.8, alpha=0.6, color=colours.get(current, UNFINISHED))


def exit_reached(last_xy, exits, reach: float):
    """Nearest exit polygon within *reach* of the agent's final position."""
    point = Point(*last_xy)
    best, best_d = None, float("inf")
    for name, poly in exits.items():
        d = poly.distance(point)
        if d < best_d:
            best, best_d = name, d
    return best if best_d <= reach else None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sqlite", type=Path, help="trajectory database from a run")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--geometry", type=Path, default=None, help="WKT walkable area")
    parser.add_argument("-o", "--out", type=Path, required=True)
    parser.add_argument("--title", default=None)
    parser.add_argument(
        "--route-history",
        type=Path,
        default=None,
        help="run.py --output-route-history CSV; colours paths by the exit "
        "targeted at each moment and marks every switch",
    )
    parser.add_argument(
        "--reach",
        type=float,
        default=1.5,
        help="metres from an exit polygon that counts as having reached it",
    )
    args = parser.parse_args()

    raw = json.loads(args.config.read_text(encoding="utf-8"))
    exits = {k: Polygon(v["coordinates"]) for k, v in raw["exits"].items()}
    colours = {name: PALETTE[i % len(PALETTE)] for i, name in enumerate(sorted(exits))}

    tracks = load_tracks(args.sqlite)
    targets = load_targets(args.route_history) if args.route_history else {}
    used: dict[str | None, int] = {}
    switch_count = 0
    fig, ax = plt.subplots(figsize=(6.5, 9))

    geometry_path = args.geometry or args.config.with_name("geometry.wkt")
    if geometry_path.exists():
        walkable = shapely_wkt.loads(geometry_path.read_text().strip())
        polys = getattr(walkable, "geoms", [walkable])
        for poly in polys:
            ax.add_patch(
                MplPoly(list(zip(*poly.exterior.xy)), fc="#f5f5f5", ec="#888", lw=1.0)
            )

    for agent_id, track in tracks.items():
        reached = exit_reached(track[-1][1:], exits, args.reach)
        used[reached] = used.get(reached, 0) + 1
        entries = targets.get(agent_id)
        if entries:
            draw_by_target(ax, track, entries, colours)
            switch_count += max(0, len(entries) - 1)
            continue
        xs = [x for _t, x, _y in track]
        ys = [y for _t, _x, y in track]
        ax.plot(xs, ys, lw=0.8, alpha=0.55, color=colours.get(reached, UNFINISHED))

    for name, poly in exits.items():
        ax.add_patch(
            MplPoly(
                list(zip(*poly.exterior.xy)), fc=colours[name], ec="k", lw=1.2, zorder=4
            )
        )
        cx, cy = poly.centroid.x, poly.centroid.y
        ax.annotate(
            f"{name}: {used.get(name, 0)}",
            (cx, cy),
            textcoords="offset points",
            xytext=(6, 6),
            fontsize=8,
            fontweight="bold",
            zorder=6,
        )

    total = len(tracks)
    stranded = used.get(None, 0)
    summary = "  ".join(f"{n}={used.get(n, 0)}" for n in sorted(exits)) + (
        f"   did not reach an exit={stranded}" if stranded else ""
    )
    subtitle = f"{total} agents:  {summary}"
    if targets:
        subtitle += (
            f"\ncolour = exit targeted at that moment;  dot = switch"
            f"  ({switch_count} in flight)"
        )
    ax.set_title((args.title or args.sqlite.stem) + f"\n{subtitle}", fontsize=9)
    ax.set_xlabel("x [m]")
    ax.set_ylabel("y [m]")
    ax.set_aspect("equal")
    ax.grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(args.out, dpi=140)
    print(f"Wrote: {args.out}")
    print(f"  {total} agents:  {summary}")
    if targets:
        print(f"  {switch_count} mid-run target switches")


if __name__ == "__main__":
    main()
