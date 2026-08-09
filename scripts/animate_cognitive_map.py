#!/usr/bin/env python3
"""Animate what one agent knows as it walks, straight from the engine.

    .venv/bin/python scripts/animate_cognitive_map.py --scenario DECK -o out.mp4

The frames are engine truth: ``run_scenario`` is asked for
``collect_cognitive_map_history``, which records the agent's known nodes and
edges every time they change. Nothing here re-implements the map -- that would
test the replay rather than the call sites in ``scenario.py``, which is where a
bug would live.

Clear-air visibility
--------------------
With ``vis_model=None`` the perception step adds nothing
(``cognitive_map._expand_visible``), leaving a discovery agent's map frozen at
its spawn node. A deck with no fire still has geometry and signs, so
:meth:`VisibilityModel.clear_air` builds the model from those -- fdsvismap's own
ray casting, view angle and ``max_vis`` handling, with a uniform zero
extinction field.
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import sqlite3
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.animation import FFMpegWriter, PillowWriter  # noqa: E402
from shapely import wkt as shapely_wkt  # noqa: E402
from shapely.geometry import Point, Polygon  # noqa: E402

from pyfds_evac.core import load_scenario, run_scenario  # noqa: E402
from pyfds_evac.core.route_graph import RerouteConfig, RouteCostConfig  # noqa: E402
from pyfds_evac.core.visibility import (  # noqa: E402
    VisibilityModel,
    extract_sign_descriptors,
)

UNKNOWN, KNOWN, AGENT = "#c4c4cc", "#d62728", "#5b4fc4"


def inward_alpha(exit_polygon: Polygon, interior_point) -> float:
    """Bearing from an exit's sign toward the space it serves.

    A door sign is mounted to be read by people coming at it from inside the
    building, so the readable half-plane should face the interior. Returns the
    compass bearing (degrees from north, clockwise) from the exit centroid to
    *interior_point*.
    """
    c = exit_polygon.centroid
    return (
        math.degrees(math.atan2(interior_point.x - c.x, interior_point.y - c.y)) % 360
    )


def _interior_reference(cfg: dict, deck: Path):
    """A point inside the occupied space, to aim the exit signs at.

    Prefers the mean of the checkpoint centroids: those are the nodes the author
    placed inside the building, so they locate the occupied space without
    hard-coding a coordinate. A deck may legitimately have no checkpoints -- this
    script exists to fit out sparse decks -- so it falls back to the spawn areas,
    and finally to a representative point of the walkable polygon, which every
    deck has.
    """
    for section in ("checkpoints", "distributions"):
        centroids = [
            Polygon(v["coordinates"]).centroid
            for v in (cfg.get(section) or {}).values()
            if len(v.get("coordinates") or ()) >= 3
        ]
        if centroids:
            n = len(centroids)
            return Point(
                sum(p.x for p in centroids) / n, sum(p.y for p in centroids) / n
            )
    walkable = shapely_wkt.loads((deck / "geometry.wkt").read_text().strip())
    return walkable.representative_point()


def build_variant(deck: Path, out: Path, familiarity: float) -> tuple[Path, dict]:
    """Write a deck with a familiarity and inward-facing sign angles set."""
    out.mkdir(parents=True, exist_ok=True)
    cfg = json.loads((deck / "config.json").read_text())

    interior_point = _interior_reference(cfg, deck)

    angles = {}
    for node_id, data in cfg["exits"].items():
        poly = Polygon(data["coordinates"])
        alpha = inward_alpha(poly, interior_point)
        c = poly.centroid
        data["sign"] = {"x": c.x, "y": c.y, "alpha": round(alpha, 1), "c": 3.0}
        angles[node_id] = round(alpha, 1)
    for v in cfg["distributions"].values():
        v["parameters"]["familiarity"] = familiarity

    (out / "config.json").write_text(json.dumps(cfg))
    shutil.copy(deck / "geometry.wkt", out / "geometry.wkt")
    return out, angles


def run(bundle: Path, seed: int, sqlite_out: Path):
    scenario = load_scenario(str(bundle))
    walkable = shapely_wkt.loads((bundle / "geometry.wkt").read_text().strip())
    vis = VisibilityModel.clear_air(walkable, extract_sign_descriptors(scenario.raw))
    result = run_scenario(
        scenario,
        seed=seed,
        reroute_config=RerouteConfig(
            reevaluation_interval_s=1.0, cost_config=RouteCostConfig()
        ),
        vis_model=vis,
        collect_cognitive_map_history=True,
    )
    shutil.copy(result.sqlite_file, sqlite_out)
    history = list(result.cognitive_map_history or [])
    switches = list(result.route_history or [])
    result.cleanup()
    return history, switches


def animate(
    bundle: Path,
    sqlite_path: Path,
    history,
    out_path: Path,
    fps: int,
    agent_id: int | None = None,
) -> None:
    """Render one agent's walk with the nodes it knows highlighted."""
    cfg = json.loads((bundle / "config.json").read_text())
    walkable = shapely_wkt.loads((bundle / "geometry.wkt").read_text().strip())
    nodes = {}
    for section, marker in (("exits", "s"), ("checkpoints", "o")):
        for node_id, data in (cfg.get(section) or {}).items():
            c = Polygon(data["coordinates"]).centroid
            nodes[node_id] = (c.x, c.y, marker)
    for node_id, data in (cfg.get("distributions") or {}).items():
        c = Polygon(data["coordinates"]).centroid
        nodes[node_id] = (c.x, c.y, "*")

    # One agent per movie: a multi-agent run would otherwise interleave every
    # agent's positions into a single path, and the highlighted nodes would be
    # one agent's knowledge drawn over everybody's trajectory.
    with sqlite3.connect(sqlite_path) as con:
        if agent_id is None:
            row = con.execute("SELECT MIN(id) FROM trajectory_data").fetchone()
            agent_id = int(row[0])
        frames = con.execute(
            "SELECT frame, pos_x, pos_y FROM trajectory_data WHERE id = ? "
            "ORDER BY frame",
            (agent_id,),
        ).fetchall()
        fps_db = con.execute("SELECT value FROM metadata WHERE key='fps'").fetchone()
        sim_fps = float(fps_db[0]) if fps_db else 20.0
    if not frames:
        raise SystemExit(f"no trajectory rows for agent {agent_id}")
    history = [e for e in history if e["agent_id"] == agent_id]

    fig, ax = plt.subplots(figsize=(9, 7))
    writer = (
        FFMpegWriter(fps=fps)
        if shutil.which("ffmpeg") and out_path.suffix == ".mp4"
        else PillowWriter(fps=fps)
    )
    with writer.saving(fig, str(out_path), dpi=130):
        for i, (frame, x, y) in enumerate(frames):
            t = frame / sim_fps
            known = _known_at(history, t)
            ax.clear()
            ax.set_facecolor("#f4f1ea")
            bx, by = walkable.exterior.xy
            ax.plot(bx, by, color="#9298a8", lw=1)
            for ring in walkable.interiors:
                rx, ry = ring.xy
                ax.plot(rx, ry, color="#9298a8", lw=1)
            for node_id, (nx, ny, marker) in nodes.items():
                on = node_id in known
                ax.plot(
                    nx,
                    ny,
                    marker=marker,
                    ms=13 if on else 8,
                    color=KNOWN if on else UNKNOWN,
                    mec="#40404a",
                    mew=0.6,
                    zorder=4,
                )
            ax.plot(
                [p[1] for p in frames[: i + 1]],
                [p[2] for p in frames[: i + 1]],
                color=AGENT,
                lw=2,
                alpha=0.75,
            )
            ax.plot(x, y, marker="o", ms=11, color=AGENT, zorder=6)
            ax.set_title(
                f"t = {t:5.2f} s     known nodes: {len(known)} / {len(nodes)}",
                fontsize=11,
            )
            ax.set_aspect("equal")
            ax.set_xlim(-20, 20)
            ax.set_ylim(-15, 14)
            ax.set_xticks([])
            ax.set_yticks([])
            writer.grab_frame()
    plt.close(fig)


def _known_at(history, t: float) -> set[str]:
    """Nodes the agent knew at time *t* (history records only the changes)."""
    known: set[str] = set()
    for event in history:
        if event["time_s"] > t:
            break
        known = set(event["known_nodes"])
    return known


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scenario", type=Path, required=True)
    ap.add_argument("--out", "-o", type=Path, default=Path("cognitive_map.mp4"))
    ap.add_argument("--familiarity", type=float, default=0.0)
    ap.add_argument("--seed", type=int, default=420)
    ap.add_argument("--fps", type=int, default=12)
    ap.add_argument(
        "--agent",
        type=int,
        default=None,
        help="agent to follow (default: the lowest id in the run)",
    )
    ap.add_argument("--work", type=Path, default=Path("results/cognitive_map_movie"))
    args = ap.parse_args()

    bundle, angles = build_variant(args.scenario, args.work / "deck", args.familiarity)
    print("inward-facing sign angles (compass bearing, deg from north CW):")
    for node_id, alpha in angles.items():
        print(f"  {node_id}: alpha={alpha}")

    sqlite_path = args.work / "run.sqlite"
    history, switches = run(bundle, args.seed, sqlite_path)
    print(f"\nlearning events: {len(history)}   route switches: {len(switches)}")
    for event in history:
        print(
            f"  t={event['time_s']:6.2f}  nodes={len(event['known_nodes']):2d} "
            f"edges={len(event['known_edges']):2d}  {sorted(event['known_nodes'])}"
        )
    for s in switches:
        print(f"  switch t={s['time_s']:.2f} -> {s['new_exit']} ({s['reason']})")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    animate(bundle, sqlite_path, history, args.out, args.fps, args.agent)
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
