"""Visualise cognitive map evolution for a discovery agent (Spec 008 Phase 2).

Produces a 4-panel figure showing what a discovery agent knows at each key
moment of their journey through the T-corridor demo scenario:

  Panel 1 — at spawn (t=0): knows spawn node + any visible neighbours
  Panel 2 — arrives at junction: discovers both exits
  Panel 3 — reroutes at junction: exit B smoke-blocked, takes exit A
  Panel 4 — full-familiarity baseline: knows everything from t=0 at spawn

Agent position moves (spawn → junction → junction → spawn) so panels are
visually distinct.  Panel 3 adds a smoke ramp over the right arm, draws the
refused edge to exit B dashed red and the chosen route to exit A bold blue.  Panel 4 contrasts with Panel 1: same agent position, but
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
import numpy as np
import seaborn as sns
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.lines import Line2D
from shapely.geometry import Polygon

CONFIG_PATH = Path("assets/t_junction/config.json")
CACHE_PATH = Path("assets/t_junction/vismap_cache.npz")
OUT_PATH = Path("assets/t_junction/cognitive_map_evolution.png")

# Shared palette of the concept figures: one meaning, one colour, one style.
SMOKE = LinearSegmentedColormap.from_list("smoke", ["#ffffff00", "#8a8a8a"])
CHOSEN = "#4575b4"  # chosen / walked route: solid line
REFUSED = "#d73027"  # refused route: dashed line
KNOWN = "#324465"  # stage in the map: filled marker
UNKNOWN = "#bdbdbd"  # stage not in the map: hollow marker, dashed edge
EXIT = "#33a02c"  # exit door
AGENT = "#1a1a1a"  # agent: star marker
WALL = "dimgrey"
FLOOR = "#f7f7f7"
TEXT = "dimgrey"

C_KNOWN_NODE = KNOWN
C_UNKNOWN_NODE = UNKNOWN
C_KNOWN_EDGE = KNOWN
C_UNKNOWN_EDGE = UNKNOWN
C_SPAWN = KNOWN
C_CHECKPOINT = KNOWN
C_EXIT_OPEN = EXIT
C_EXIT_BLOCKED = EXIT  # the exit stays a known exit; its edge is refused
C_FLOOR = FLOOR
C_WALL = WALL
C_AGENT = AGENT
C_CHOSEN_ROUTE = CHOSEN

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
        is_refused = highlight_blocked is not None and tgt == highlight_blocked
        if is_bold:
            color, lw, ls = C_CHOSEN_ROUTE, 3.6, "-"
        elif is_refused and known:
            color, lw, ls = REFUSED, 2.2, (0, (4, 2))
        elif known:
            color, lw, ls = C_KNOWN_EDGE, 1.8, "-"
        else:
            color, lw, ls = C_UNKNOWN_EDGE, 1.8, (0, (3, 3))
        ax_plot.plot([sx, tx], [sy, ty], color=color, lw=lw, ls=ls, zorder=3)

    for node_id, (cx, cy, stype) in nodes.items():
        known = node_id in known_nodes
        facecolor = NODE_COLORS.get(node_id, C_CHECKPOINT) if known else "white"

        marker = "s" if stype == "exit" else ("^" if stype == "distribution" else "o")

        ax_plot.scatter(
            cx,
            cy,
            s=150,
            marker=marker,
            facecolors=facecolor,
            edgecolors=KNOWN if known else UNKNOWN,
            linewidths=1.6,
            zorder=5,
        )
        label = NODE_LABELS.get(node_id, node_id)
        # spawn sits low in the stem: label it below, the rest above the corridor
        below = stype == "distribution"
        ax_plot.text(
            cx,
            cy - 1.6 if below else 13.7,
            label,
            ha="center",
            va="center",
            fontsize=8.5,
            color=TEXT if known else UNKNOWN,
            fontweight="bold" if known else None,
            zorder=6,
        )


def draw_smoke(ax_plot, nodes: dict, blocked_id: str):
    """Draw smoke filling the corridor arm of the blocked exit, densest at it."""
    if blocked_id not in nodes:
        return
    cx, _, _ = nodes[blocked_id]
    x0, x1 = min(cx, 23.0), max(cx, 23.0) + 0.5
    xlim, ylim = ax_plot.get_xlim(), ax_plot.get_ylim()
    gx, _ = np.meshgrid(np.linspace(x0, x1, 160), np.linspace(10, 13, 60))
    dens = np.clip((gx - x0) / (x1 - x0), 0, 1) ** 1.2
    ax_plot.imshow(
        dens,
        extent=(x0, x1, 10, 13),
        origin="lower",
        cmap=SMOKE,
        vmin=0,
        vmax=1,
        alpha=0.9,
        aspect="auto",
        zorder=2,
        interpolation="bilinear",
    )
    # imshow rescales the axes; keep the panel on the same floor frame
    ax_plot.set_xlim(xlim)
    ax_plot.set_ylim(ylim)
    ax_plot.set_aspect("equal")
    ax_plot.text(
        0.5 * (x0 + x1),
        9.4,
        "smoke",
        ha="center",
        va="top",
        fontsize=8,
        color=TEXT,
        zorder=7,
    )


def draw_agent(ax_plot, x: float, y: float):
    ax_plot.scatter(x, y, s=260, marker="*", fc=C_AGENT, ec="white", lw=0.8, zorder=8)
    ax_plot.text(
        x + 0.9,
        y + 0.9,
        "agent",
        fontsize=8.5,
        color=TEXT,
        va="center",
        fontweight="bold",
        zorder=9,
    )


def setup_ax(ax_plot, title: str, walkable: Polygon):
    draw_floor(ax_plot, walkable)
    ax_plot.set_xlim(-1, 31)
    ax_plot.set_ylim(-1, 14.6)
    ax_plot.set_aspect("equal")
    ax_plot.set_title(title, fontsize=8.5, pad=4, loc="left")
    # a floor plan has no data axes: grid, ticks and frame add nothing
    ax_plot.axis("off")


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
            title=r"$\bf{1}$  "
            + "spawn (t = 0)\ndiscovery: knows spawn + visible neighbors",
            agent_xy=(spawn_cx, spawn_cy),
            blocked=None,
            bold_path=None,
            smoke=False,
        ),
        dict(
            known=known2,
            edges=edges2,
            title=r"$\bf{2}$  "
            + "arrives at junction\ndiscovery: discovers both exits",
            agent_xy=(junc_cx, junc_cy),
            blocked=None,
            bold_path=None,
            smoke=False,
        ),
        dict(
            known=known3,
            edges=edges3,
            title=r"$\bf{3}$  "
            + "reroutes at junction\ndiscovery: exit B blocked → takes exit A",
            agent_xy=(junc_cx, junc_cy),
            blocked="exit_B_right",
            bold_path=("jps-checkpoints_0", "exit_A_left"),
            smoke=True,
        ),
        dict(
            known=known4,
            edges=edges4,
            title=r"$\bf{4}$  "
            + "spawn (t = 0)\nfull familiarity: knows complete graph",
            agent_xy=(spawn_cx, spawn_cy),
            blocked=None,
            bold_path=None,
            smoke=False,
        ),
    ]

    sns.set_theme(font_scale=1.0, style="whitegrid", font="DejaVu Sans")
    fig, axes = plt.subplots(1, 4, figsize=(14, 4), gridspec_kw=dict(wspace=0.08))
    fig.suptitle("Cognitive map evolution — discovery vs full familiarity", fontsize=11)

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
            markeredgewidth=1.6,
            markersize=8,
            label="unknown node",
        ),
        Line2D(
            [0],
            [0],
            marker="s",
            color="w",
            markerfacecolor=EXIT,
            markeredgecolor=KNOWN,
            markersize=8,
            label="known exit",
        ),
        Line2D([0], [0], color=C_KNOWN_EDGE, lw=1.8, label="known edge"),
        Line2D(
            [0], [0], color=C_UNKNOWN_EDGE, lw=1.8, ls=(0, (3, 3)), label="unknown edge"
        ),
        Line2D([0], [0], color=C_CHOSEN_ROUTE, lw=3.6, label="chosen route"),
        Line2D([0], [0], color=REFUSED, lw=2.2, ls=(0, (4, 2)), label="refused route"),
        Line2D(
            [0],
            [0],
            marker="*",
            color="w",
            markerfacecolor=C_AGENT,
            markersize=12,
            label="agent",
        ),
    ]
    fig.legend(
        handles=legend_elements,
        loc="lower center",
        ncol=8,
        fontsize=8.5,
        frameon=True,
        facecolor="white",
        framealpha=0.8,
        edgecolor="lightgrey",
        labelcolor=TEXT,
        bbox_to_anchor=(0.5, 0.02),
    )
    sns.despine(fig=fig, left=True, bottom=True)
    fig.text(
        0.5,
        -0.02,
        "Panels 2 and 3: the same map. With smoke on exit B's arm the router "
        "takes exit A, and exit B stays in the map.",
        ha="center",
        va="top",
        fontsize=8.5,
        color=TEXT,
        style="italic",
    )

    fig.tight_layout(rect=(0, 0.06, 1, 1))
    fig.savefig(OUT_PATH, dpi=150, bbox_inches="tight")
    print(f"Saved → {OUT_PATH}")
    plt.show()


if __name__ == "__main__":
    main()
