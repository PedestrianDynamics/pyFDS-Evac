"""Phase 0 of spec 008: vismap baseline plots for the demo scenario.

Computes (or loads from cache) visibility maps for the demo FDS data,
then produces two diagnostic plots:

  1. Time-aggregated, waypoint-aggregated visibility map
     → shows which floor cells can ever see any sign (green/red)
     → validates sign placement before any code changes

  2. ASET map
     → shows when each floor cell first loses visibility to any sign
     → validates that smoke near exit_B causes earliest visibility loss

Waypoints are read from "sign" fields in assets/demo/config.json.
Each exit and checkpoint with a "sign" key contributes one vismap waypoint:
  {"x": <float>, "y": <float>, "alpha": <deg>, "c": <contrast>}

  alpha convention (compass bearing, degrees from north CW):
    90  = visible from east  (sign on left/west wall, seen by agents to its right)
    270 = visible from west  (sign on right/east wall, seen by agents to its left)
    180 = visible from south (sign at junction top, seen by agents in branch below)

Usage:
    uv run python scripts/demo_vismap_phase0.py [--no-cache]
"""

from __future__ import annotations

import argparse
import json
import pickle
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from fdsvismap import VisMap

FDS_DIR = Path("fds_data/demo")
CACHE_PATH = Path("fds_data/demo/vismap_cache.pkl")
CONFIG_PATH = Path("assets/demo/config.json")
OUT_DIR = Path("assets/demo")

TIME_STEP_S = 10  # match reevaluation interval


def _load_waypoints(config_path: Path) -> list[tuple[int, float, float, float, float]]:
    """Read (wp_id, x, y, c, alpha) from all nodes with a 'sign' field in config."""
    cfg = json.loads(config_path.read_text())
    waypoints = []
    wp_id = 0
    for section in ("exits", "checkpoints", "waypoints"):
        for node_id, data in cfg.get(section, {}).items():
            sign = data.get("sign")
            if sign:
                waypoints.append((
                    wp_id,
                    float(sign["x"]),
                    float(sign["y"]),
                    float(sign.get("c", 3)),
                    float(sign["alpha"]),
                ))
                wp_id += 1
    return waypoints


def build_vis(fds_dir: Path, time_step: float) -> VisMap:
    vis = VisMap()
    vis.read_fds_data(str(fds_dir), fds_slc_height=2.0)

    t_max = vis.fds_time_points.max()
    times = list(np.arange(0, t_max + time_step, time_step))
    vis.set_time_points(times)

    # Start point: centroid of spawn area (x=18-22, y=1-8)
    vis.set_start_point(20.0, 4.5)

    for wp_id, x, y, c, alpha in _load_waypoints(CONFIG_PATH):
        vis.set_waypoint(wp_id, x, y, c=c, alpha=alpha)

    vis.compute_all(view_angle=True, obstructions=True, aa=True)
    return vis


def load_or_compute(fds_dir: Path, cache_path: Path, force: bool = False) -> VisMap:
    if cache_path.exists() and not force:
        print(f"Loading cached vismap from {cache_path}")
        with cache_path.open("rb") as f:
            return pickle.load(f)

    print("Computing vismap (this may take a while)…")
    vis = build_vis(fds_dir, TIME_STEP_S)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with cache_path.open("wb") as f:
        pickle.dump(vis, f)
    print(f"Cached to {cache_path}")
    return vis


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--no-cache", action="store_true", help="Recompute even if cache exists"
    )
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    vis = load_or_compute(FDS_DIR, CACHE_PATH, force=args.no_cache)
    vis.set_start_point(20.0, 4.5)  # centroid of spawn area

    # ── Plot 1: time-aggregated, waypoint-aggregated visibility map ────
    fig1, ax1 = vis.create_time_agg_wp_agg_vismap_plot(
        plot_obstructions=True, flip_y_axis=True
    )
    ax1.set_title(
        "Sign coverage map (green = visible from any time, red = never visible)\n"
        "Waypoints: exit_A (0), exit_B (1), junction (2)"
    )
    out1 = OUT_DIR / "vismap_coverage.png"
    fig1.savefig(out1, dpi=150, bbox_inches="tight")
    print(f"Saved: {out1}")
    plt.close(fig1)

    # ── Plot 2: ASET map ───────────────────────────────────────────────
    fig2, ax2 = vis.create_aset_map_plot(
        plot_obstructions=True, flip_y_axis=True
    )
    ax2.set_title(
        "ASET map — first time any sign becomes invisible [s]\n"
        "(earlier = visibility lost sooner; fire source near exit_B)"
    )
    out2 = OUT_DIR / "vismap_aset.png"
    fig2.savefig(out2, dpi=150, bbox_inches="tight")
    print(f"Saved: {out2}")
    plt.close(fig2)


if __name__ == "__main__":
    main()
