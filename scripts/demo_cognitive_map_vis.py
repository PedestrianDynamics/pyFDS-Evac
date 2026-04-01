"""Visualise cognitive map evolution for a discovery agent (Spec 008 Phase 2).

Produces a 4-panel figure showing what a discovery agent knows at each key
moment of their journey through the T-corridor demo scenario:

  Panel 1 — at spawn (t=0): knows spawn node + any visible neighbours
  Panel 2 — arrives at junction: discovers both exits
  Panel 3 — reroutes at junction: exit B smoke-blocked, takes exit A
  Panel 4 — full-familiarity baseline: knows everything from t=0 at spawn

Agent position moves (spawn → junction → junction → spawn) so panels are
visually distinct.  Panel 3 adds a smoke overlay on exit B and a bold route
arrow to exit A.  Panel 4 contrasts with Panel 1: same agent position, but
complete knowledge from the start.

Usage:
    uv run python scripts/demo_cognitive_map_vis.py [--no-cache]
"""

from __future__ import annotations

import argparse
import json
import pickle
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from shapely.geometry import Polygon

CONFIG_PATH = Path("assets/demo/config.json")
CACHE_PATH = Path("fds_data/demo/vismap_cache.pkl")
OUT_PATH = Path("assets/demo/cognitive_map_evolution.png")

# Colours
C_KNOWN_NODE = "#2196F3"
C_UNKNOWN_NODE = "#BDBDBD"
C_KNOWN_EDGE = "#2196F3"
C_UNKNOWN_EDGE = "#E0E0E0"
C_SPAWN = "#FF9800"
C_CHECKPOINT = "#4CAF50"
C_EXIT_OPEN = "#4CAF50"
C_EXIT_BLOCKED = "#F44336"
C_FLOOR = "#F5F5F5"
C_WALL = "#757575"
C_AGENT = "#FF5722"
C_CHOSEN_ROUTE = "#1565C0"  # bold blue for selected path in panel 3

NODE_LABELS = {
    "jps-distributions_0": "spawn",
    "jps-checkpoints_0": "junction",
    "exit_A_left": "exit A",
    "exit_B_right": "exit B",
}

NODE_COLORS = {
    "jps-distributions_0": C_SPAWN,
    "jps-checkpoints_0": C_CHECKPOINT,
    "exit_A_left": C_EXIT_OPEN,
    "exit_B_right": C_EXIT_BLOCKED,
}


def load_config(path: Path) -> dict:
    return json.loads(path.read_text())


def build_stage_graph(cfg: dict):
    """Return (nodes, edges) where nodes = {id: (cx, cy, type)}."""
    nodes = {}
    for section, stype in (
        ("distributions", "distribution"),
        ("checkpoints", "checkpoint"),
        ("exits", "exit"),
    ):
        for node_id, data in cfg.get(section, {}).items():
            coords = data.get("coordinates", [])
            if not coords:
                continue
            poly = Polygon(coords[:-1] if coords[0] == coords[-1] else coords)
            nodes[node_id] = (poly.centroid.x, poly.centroid.y, stype)

    edges = []
    for tr in cfg.get("transitions", []):
        src, tgt = tr["from"], tr["to"]
        if src in nodes and tgt in nodes:
            edges.append((src, tgt))
    return nodes, edges


def build_walkable_polygon(cfg: dict) -> Polygon:
    from shapely.ops import unary_union

    corridor = Polygon([(0, 10), (30, 10), (30, 13), (0, 13)])
    branch = Polygon([(17, 0), (23, 0), (23, 10), (17, 10)])
    return unary_union([corridor, branch])


def try_load_vismap(cache_path: Path):
    if cache_path.exists():
        with cache_path.open("rb") as f:
            return pickle.load(f)
    return None


def get_sign_descriptors(cfg: dict) -> dict[str, dict]:
    signs = {}
    for section in ("exits", "checkpoints"):
        for node_id, data in cfg.get(section, {}).items():
            sign = data.get("sign")
            if sign:
                signs[node_id] = sign
    return signs


def node_is_visible_at_spawn(
    vis, signs: dict, node_id: str, ax: float, ay: float, time_s: float
) -> bool:
    if vis is None or node_id not in signs:
        return True
    wp_ids = list(signs.keys())
    wp_id = wp_ids.index(node_id)
    try:
        return bool(vis.wp_is_visible(time=time_s, x=ax, y=ay, waypoint_id=wp_id))
    except Exception:
        return True


def draw_floor(ax_plot, walkable: Polygon):
    x, y = walkable.exterior.xy
    ax_plot.fill(x, y, color=C_FLOOR, zorder=0)
    ax_plot.plot(x, y, color=C_WALL, lw=1.5, zorder=1)


def draw_graph(
    ax_plot,
    nodes: dict,
    all_edges: list[tuple],
    known_nodes: set[str],
    known_edges: set[tuple[str, str]],
    highlight_blocked: str | None = None,
    bold_path: tuple[str, str] | None = None,
):
    """Draw stage graph with known/unknown styling.

    bold_path: (src, tgt) edge to draw as a thick coloured arrow (chosen route).
    """
    for src, tgt in all_edges:
        if src not in nodes or tgt not in nodes:
            continue
        sx, sy, _ = nodes[src]
        tx, ty, _ = nodes[tgt]
        known = (src, tgt) in known_edges
        is_bold = bold_path is not None and (src, tgt) == bold_path

        ax_plot.annotate(
            "",
            xy=(tx, ty),
            xytext=(sx, sy),
            arrowprops=dict(
                arrowstyle="->" if (known or is_bold) else "-",
                color=C_CHOSEN_ROUTE
                if is_bold
                else (C_KNOWN_EDGE if known else C_UNKNOWN_EDGE),
                lw=3.5 if is_bold else (2.0 if known else 1.0),
                connectionstyle="arc3,rad=0.0",
                alpha=1.0 if (known or is_bold) else 0.4,
            ),
            zorder=3 if is_bold else 2,
        )

    for node_id, (cx, cy, stype) in nodes.items():
        known = node_id in known_nodes
        base_color = NODE_COLORS.get(node_id, C_CHECKPOINT)

        if node_id == highlight_blocked:
            facecolor = C_EXIT_BLOCKED if known else C_UNKNOWN_NODE
            edgecolor = C_EXIT_BLOCKED
        else:
            facecolor = base_color if known else C_UNKNOWN_NODE
            edgecolor = base_color if known else C_UNKNOWN_NODE

        marker = "s" if stype == "exit" else ("^" if stype == "distribution" else "o")
        size = 160 if stype == "exit" else 140

        ax_plot.scatter(
            cx,
            cy,
            s=size,
            marker=marker,
            facecolors=facecolor if known else "white",
            edgecolors=edgecolor,
            linewidths=2,
            zorder=4,
        )
        label = NODE_LABELS.get(node_id, node_id)
        ax_plot.text(
            cx,
            cy + 0.8,
            label,
            ha="center",
            va="bottom",
            fontsize=7,
            color="#333333" if known else "#AAAAAA",
            zorder=5,
        )


def draw_smoke(ax_plot, nodes: dict, blocked_id: str):
    """Draw a translucent smoke cloud over the blocked exit."""
    if blocked_id not in nodes:
        return
    cx, cy, _ = nodes[blocked_id]
    from matplotlib.patches import Ellipse

    smoke = Ellipse(
        (cx, cy),
        width=5,
        height=2.5,
        facecolor="#9E9E9E",
        alpha=0.45,
        zorder=6,
    )
    ax_plot.add_patch(smoke)
    ax_plot.text(
        cx,
        cy,
        "smoke",
        ha="center",
        va="center",
        fontsize=6,
        color="white",
        fontweight="bold",
        zorder=7,
    )


def draw_agent(ax_plot, x: float, y: float):
    ax_plot.scatter(x, y, s=200, marker="*", color=C_AGENT, zorder=8)
    ax_plot.text(
        x + 0.8,
        y,
        "agent",
        fontsize=7,
        color=C_AGENT,
        va="center",
        fontweight="bold",
        zorder=9,
    )


def setup_ax(ax_plot, title: str, walkable: Polygon):
    draw_floor(ax_plot, walkable)
    ax_plot.set_xlim(-1, 31)
    ax_plot.set_ylim(-1, 14)
    ax_plot.set_aspect("equal")
    ax_plot.set_title(title, fontsize=8.5, pad=4)
    ax_plot.set_xticks([])
    ax_plot.set_yticks([])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-cache", action="store_true")
    args = parser.parse_args()

    cfg = load_config(CONFIG_PATH)
    nodes, edges = build_stage_graph(cfg)
    walkable = build_walkable_polygon(cfg)
    signs = get_sign_descriptors(cfg)

    vis = None if args.no_cache else try_load_vismap(CACHE_PATH)
    if vis is not None:
        print("Loaded cached vismap.")
    else:
        print("No vismap cache — visibility check at spawn defaults to True.")

    spawn_poly = Polygon(
        cfg["distributions"]["jps-distributions_0"]["coordinates"][:-1]
    )
    spawn_cx, spawn_cy = spawn_poly.centroid.x, spawn_poly.centroid.y

    junc_cx, junc_cy, _ = nodes["jps-checkpoints_0"]

    all_edges_set = set(edges)

    # ── Build cognitive map states ────────────────────────────────────────────
    spawn_node = "jps-distributions_0"

    # Panel 1: at spawn, t=0
    known1: set[str] = {spawn_node}
    edges1: set[tuple[str, str]] = set()
    for src, tgt in edges:
        if src == spawn_node:
            if node_is_visible_at_spawn(vis, signs, tgt, spawn_cx, spawn_cy, 0.0):
                known1.add(tgt)
                edges1.add((src, tgt))

    # Panel 2: arrived at junction
    arrived = "jps-checkpoints_0"
    known2 = known1 | {arrived}
    edges2 = edges1.copy()
    for src, tgt in edges:
        if src == arrived:
            known2.add(tgt)
            edges2.add((src, tgt))

    # Panel 3: same knowledge as panel 2, smoke blocks exit_B
    known3 = known2.copy()
    edges3 = edges2.copy()

    # Panel 4: full familiarity — agent at spawn but knows everything
    known4 = set(nodes.keys())
    edges4 = set(edges)

    panels = [
        dict(
            known=known1,
            edges=edges1,
            title="Panel 1 — spawn (t = 0)\ndiscovery: knows spawn + visible neighbors",
            agent_xy=(spawn_cx, spawn_cy),
            blocked=None,
            bold_path=None,
            smoke=False,
        ),
        dict(
            known=known2,
            edges=edges2,
            title="Panel 2 — arrives at junction\ndiscovery: discovers both exits",
            agent_xy=(junc_cx, junc_cy),
            blocked=None,
            bold_path=None,
            smoke=False,
        ),
        dict(
            known=known3,
            edges=edges3,
            title="Panel 3 — reroutes at junction\ndiscovery: exit B blocked → takes exit A",
            agent_xy=(junc_cx, junc_cy),
            blocked="exit_B_right",
            bold_path=("jps-checkpoints_0", "exit_A_left"),
            smoke=True,
        ),
        dict(
            known=known4,
            edges=edges4,
            title="Panel 4 — spawn (t = 0)\nfull familiarity: knows complete graph",
            agent_xy=(spawn_cx, spawn_cy),
            blocked=None,
            bold_path=None,
            smoke=False,
        ),
    ]

    fig, axes = plt.subplots(1, 4, figsize=(14, 4))
    fig.suptitle("Cognitive map evolution — discovery vs full familiarity", fontsize=10)

    for ax_plot, p in zip(axes, panels):
        setup_ax(ax_plot, p["title"], walkable)
        draw_graph(
            ax_plot,
            nodes,
            list(all_edges_set),
            p["known"],
            p["edges"],
            highlight_blocked=p["blocked"],
            bold_path=p["bold_path"],
        )
        if p["smoke"]:
            draw_smoke(ax_plot, nodes, "exit_B_right")
        draw_agent(ax_plot, *p["agent_xy"])

    legend_elements = [
        Line2D(
            [0],
            [0],
            marker="o",
            color="w",
            markerfacecolor=C_KNOWN_NODE,
            markeredgecolor=C_KNOWN_NODE,
            markersize=8,
            label="known node",
        ),
        Line2D(
            [0],
            [0],
            marker="o",
            color="w",
            markerfacecolor="white",
            markeredgecolor=C_UNKNOWN_NODE,
            markersize=8,
            label="unknown node",
        ),
        Line2D([0], [0], color=C_KNOWN_EDGE, lw=2, label="known edge"),
        Line2D([0], [0], color=C_UNKNOWN_EDGE, lw=1, label="unknown edge"),
        Line2D([0], [0], color=C_CHOSEN_ROUTE, lw=3, label="chosen route"),
        Line2D(
            [0],
            [0],
            marker="*",
            color="w",
            markerfacecolor=C_AGENT,
            markersize=10,
            label="agent",
        ),
    ]
    fig.legend(
        handles=legend_elements,
        loc="lower center",
        ncol=6,
        fontsize=8,
        frameon=False,
        bbox_to_anchor=(0.5, -0.02),
    )

    fig.tight_layout(rect=(0, 0.06, 1, 1))
    fig.savefig(OUT_PATH, dpi=150, bbox_inches="tight")
    print(f"Saved → {OUT_PATH}")
    plt.show()


if __name__ == "__main__":
    main()
