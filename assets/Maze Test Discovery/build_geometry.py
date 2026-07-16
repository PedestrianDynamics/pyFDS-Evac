#!/usr/bin/env python3
"""
Generate geometry.wkt + config.json for a 50 x 50 m corn maze.

Corridor width: 3 m.
Walkable area = union of rectangular corridor strips; walls are the gaps.
16 corridors, 5 horizontal + 11 vertical, creating dead ends and winding paths.
"""

from pathlib import Path
import json

from shapely.geometry import box
from shapely.ops import unary_union

HERE = Path(__file__).parent


def build():
    corridors = []

    # Horizontal corridors (y range = centre +/- 1.5)
    corridors.append(box(0,    3.5,  50,   6.5))  # H5:  full-width spine
    corridors.append(box(0,   13.5,  22,  16.5))  # H15a: left section
    corridors.append(box(28,  13.5,  50,  16.5))  # H15b: right section  (gap x=22..28)
    corridors.append(box(8,   23.5,  50,  26.5))  # H25:  left stub dead end
    corridors.append(box(0,   33.5,  42,  36.5))  # H35:  right stub dead end
    corridors.append(box(6,   43.5,  50,  46.5))  # H45:  left stub dead end

    # Vertical corridors (x range = centre +/- 1.5)
    corridors.append(box(3.5,  0,   6.5,  36))    # V5a:  lower (connects H5..H35)
    corridors.append(box(3.5, 43,   6.5,  50))    # V5b:  top stub  (gap y=36..43 = dead end)
    corridors.append(box(13.5, 5,  16.5,  24))    # V15a: lower corridor
    corridors.append(box(13.5,33,  16.5,  50))    # V15b: upper corridor
    corridors.append(box(23.5, 0,  26.5,  15))    # V25a: lower stub dead end
    corridors.append(box(23.5,24,  26.5,  44))    # V25b: upper corridor
    corridors.append(box(33.5, 5,  36.5,  35))    # V35a: centre corridor
    corridors.append(box(33.5,43,  36.5,  50))    # V35b: top stub dead end
    corridors.append(box(43.5, 0,  46.5,  15))    # V45a: lower stub dead end
    corridors.append(box(43.5,24,  46.5,  50))    # V45b: upper corridor

    walkable = unary_union(corridors)

    if walkable.geom_type not in ("Polygon", "MultiPolygon"):
        raise SystemExit(f"Unexpected geometry type: {walkable.geom_type}")

    wkt_path = HERE / "geometry.wkt"
    wkt_path.write_text(walkable.wkt + "\n", encoding="utf-8")
    print("=== Walkable Area WKT ===")
    print(walkable.wkt[:300], "...")
    print()

    config = {
        "project_version": "2.0",
        "config": {
            "simulation_settings": {
                "simulationParams": {
                    "max_simulation_time": 300,
                    "dt": 0.01,
                    "model_type": "SocialForceModel",
                    "strength_neighbor_repulsion": 2.6,
                    "range_neighbor_repulsion": 0.1,
                    "gcfm_strength_neighbor_repulsion": 0.3,
                    "gcfm_strength_geometry_repulsion": 0.2,
                    "gcfm_max_neighbor_interaction_distance": 2,
                    "gcfm_max_geometry_interaction_distance": 2,
                    "gcfm_max_neighbor_repulsion_force": 9,
                    "gcfm_max_geometry_repulsion_force": 3,
                    "mass": 80, "tau": 0.5, "a_v": 1,
                    "a_min": 0.2, "b_min": 0.2, "b_max": 0.4,
                    "relaxation_time": 0.5,
                    "agent_strength": 2000, "agent_range": 0.08,
                    "sfm_obstacle_scale": 2000,
                    "sfm_body_force": 120000, "sfm_friction": 240000,
                    "T": 1, "s0": 0.5,
                },
                "numberOfSimulations": 1,
                "baseSeed": 42,
            },
            "ui_state": {"useShortestPaths": False, "boundaries": [{"mode": "manual"}]},
        },
        "exits": {}, "distributions": {}, "checkpoints": {},
        "zones": {}, "journeys": [], "transitions": {},
        "obstacles": {}, "journeys_v2": [],
    }

    config_path = HERE / "config.json"
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)

    print(f"Wrote: {wkt_path}")
    print(f"Wrote: {config_path}")
    print(f"Geometry type: {walkable.geom_type}")

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.patches import Polygon as MplPoly
        from matplotlib.ticker import MultipleLocator
        from shapely.geometry import MultiPolygon

        fig, ax = plt.subplots(figsize=(10, 10))
        polys = list(walkable.geoms) if walkable.geom_type == "MultiPolygon" else [walkable]
        for poly in polys:
            xs, ys = poly.exterior.xy
            ax.add_patch(MplPoly(list(zip(xs, ys)), facecolor="#c8d5b9", edgecolor="#2d4a1e", lw=1.2))
            for ring in poly.interiors:
                ix, iy = ring.xy
                ax.add_patch(MplPoly(list(zip(ix, iy)), facecolor="#2d4a1e"))

        ax.set_facecolor("#2d4a1e")  # corn green background = walls
        ax.set_aspect("equal")
        ax.set_xlim(0, 50)
        ax.set_ylim(0, 50)
        ax.xaxis.set_major_locator(MultipleLocator(5))
        ax.yaxis.set_major_locator(MultipleLocator(5))
        ax.set_title("Corn Maze -- 50 x 50 m  (green = walkable path, dark = corn/wall)", fontsize=10)
        ax.grid(alpha=0.2, color="white")
        fig.tight_layout()
        preview_path = HERE / "layout_preview.png"
        fig.savefig(preview_path, dpi=120)
        print(f"Wrote: {preview_path}")
    except ImportError:
        print("(matplotlib not available)")

    return walkable


if __name__ == "__main__":
    build()
