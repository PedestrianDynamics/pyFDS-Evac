# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "matplotlib",
#     "numpy",
#     "pandas",
#     "pillow",
#     "seaborn",
#     "shapely",
# ]
# ///
"""Figures for the verification test "Familiarity: known exits vs discovered exits".

``assets/familiarity_test_full`` and ``assets/familiarity_test_discovery`` are
one 20 x 18 m plan with one exit, four signed checkpoints and 20 agents; only
the spawn group's ``familiarity`` differs. The expected behaviour is derived
here from the geometry alone, with no pyFDS-Evac code:

* shortest paths: a visibility graph over the walkable polygon (shapely);
* the stage graph: every spawn/checkpoint is wired to each checkpoint/exit it
  reaches without passing another checkpoint (detour <= 5 %), the rule of
  Models > Wayfinding, recomputed with those shortest paths;
* legibility in clear air: a sign at s with facing n (compass bearing alpha) is
  legible from p when the segment p-s stays in the walkable area and
  n.(p - s) / |p - s| * 30 m >= |p - s|; an unoriented sign only needs
  |p - s| <= 30 m;
* discovery at t = 0: spawn plus the spawn's neighbours whose sign is legible
  from the spawn's centroid; then the nearest known, unvisited node, until the
  exit is legible.

The runs are read from ``--data``; nothing is simulated here. ``DIR`` holds
``full/`` and ``discovery_cell<c>/`` for each clear-air grid c, each with the
``run.sqlite`` and ``routes.csv`` that ``run.py`` wrote.

Run from the repository root::

    uv run python scripts/verification/familiarity_figures.py --data DIR

Writes ``familiarity_setup.png``, ``familiarity_paths.png``,
``familiarity_egress.png`` and ``familiarity.gif`` to
``site/static/images/verification/``.
"""

import argparse
import heapq
import json
import math
import sqlite3
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib.animation import PillowWriter
from matplotlib.collections import LineCollection
from matplotlib.lines import Line2D
from matplotlib.patches import FancyArrowPatch, Patch, Rectangle
from matplotlib.patches import Polygon as MplPolygon
from shapely import wkt
from shapely.geometry import LineString, Point, Polygon

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "site" / "static" / "images" / "verification"
SCENARIO = ROOT / "assets" / "familiarity_test_discovery"
MAIN_CELL = 0.05  # two cells across the deck's 0.1 m walls
READ_M = 30.0  # clear-air reading distance of a sign
DETOUR = 0.05  # betweenness tolerance of the automatic wiring
FPS = 10  # trajectory frames per second in run.sqlite

# One meaning, one colour, one style across the four figures.
FULL = "#4575b4"  # full tier: blue, solid
DISC = "#fc8d59"  # discovery tier: orange, dashed
WALL = "dimgrey"
FLOOR = "#f7f7f7"
TEXT = "dimgrey"
SPAWN = "#fc8d59"
EXIT = "#33a02c"
# destination of an agent: one colour per node, and the node's label
DEST = {
    "CP0": "#d73027",
    "CP1": "#e6ab02",
    "CP2": "#74add1",
    "CP3": "#324465",
    "E": "#33a02c",
    "S": "#bdbdbd",
}
PATTERN_COLORS = {
    "direct: S-CP3-E": FULL,
    "predicted tour: CP0-CP1-CP2-CP3-E": "#fee090",
    "other order, no turn-back": "#74add1",
    "turned back at CP3 (wander)": "#d73027",
}
LEGEND = dict(
    frameon=True,
    facecolor="white",
    framealpha=0.8,
    edgecolor="lightgrey",
    labelcolor="dimgrey",
)


# --- Geometry: shortest paths and legibility, no pyFDS-Evac code ---


class Geodesic:
    """Shortest walkable paths by a visibility graph over the polygon corners."""

    def __init__(self, walkable):
        self.cover = walkable.buffer(1e-7)
        rings = [walkable.exterior, *walkable.interiors]
        self.corners = [c for r in rings for c in list(r.coords)[:-1]]
        self.adj = {i: [] for i in range(len(self.corners))}
        for i, a in enumerate(self.corners):
            for j in range(i + 1, len(self.corners)):
                self._link(i, j, a, self.corners[j])

    def _link(self, i, j, a, b):
        if not self.sees(a, b):
            return
        d = math.dist(a, b)
        self.adj[i].append((j, d))
        self.adj[j].append((i, d))

    def sees(self, a, b):
        """Whether the straight segment a-b stays in the walkable area."""
        if math.dist(a, b) < 1e-9:
            return True
        return LineString([a, b]).within(self.cover)

    def path(self, a, b):
        """Length and polyline of the shortest walkable path from a to b."""
        if self.sees(a, b):
            return math.dist(a, b), [a, b]
        n = len(self.corners)
        adj = {k: list(v) for k, v in self.adj.items()}
        adj[n], adj[n + 1] = [], []
        pts = self.corners + [a, b]
        for i, c in enumerate(self.corners):
            for end in (n, n + 1):
                if self.sees(pts[end], c):
                    d = math.dist(pts[end], c)
                    adj[end].append((i, d))
                    adj[i].append((end, d))
        return _dijkstra(adj, pts, n, n + 1)

    def length(self, a, b):
        return self.path(a, b)[0]

    def to_polygon(self, a, poly):
        """Shortest walkable distance from a to the nearest point of poly."""
        best = math.inf
        for c in [a, *self.corners]:
            q = poly.exterior.interpolate(poly.exterior.project(Point(c)))
            q = (q.x, q.y)
            if not self.sees(c, q):
                continue
            best = min(best, self.length(a, c) + math.dist(c, q))
        return best


def _dijkstra(adj, pts, src, dst):
    dist = {src: 0.0}
    prev = {}
    heap = [(0.0, src)]
    while heap:
        d, u = heapq.heappop(heap)
        if u == dst:
            break
        if d > dist.get(u, math.inf):
            continue
        for v, w in adj[u]:
            if d + w < dist.get(v, math.inf):
                dist[v], prev[v] = d + w, u
                heapq.heappush(heap, (d + w, v))
    if dst not in dist:
        return math.inf, []
    chain = [dst]
    while chain[-1] != src:
        chain.append(prev[chain[-1]])
    return dist[dst], [pts[k] for k in reversed(chain)]


def legible(geo, p, sign):
    """Clear-air legibility of a sign from p: sight line, facing, 30 m."""
    x, y, alpha = sign
    d = math.dist(p, (x, y))
    if d < 1e-9:
        return True
    if not geo.sees(p, (x, y)):
        return False
    if alpha is None:
        return d <= READ_M
    a = math.radians(alpha)
    facing = (math.sin(a) * (p[0] - x) + math.cos(a) * (p[1] - y)) / d
    return facing * READ_M >= d


def legible_near(geo, p, sign, tol):
    """Legible from p or from a point within tol of it (grid tolerance)."""
    if legible(geo, p, sign):
        return True
    angles = np.linspace(0.0, 2.0 * math.pi, 8, endpoint=False)
    around = [(p[0] + tol * math.cos(t), p[1] + tol * math.sin(t)) for t in angles]
    return any(legible(geo, q, sign) for q in around)


def legible_all_around(geo, p, sign, tol):
    """Legible from p and from every point within tol of it."""
    angles = np.linspace(0.0, 2.0 * math.pi, 8, endpoint=False)
    around = [(p[0] + tol * math.cos(t), p[1] + tol * math.sin(t)) for t in angles]
    return all(legible(geo, q, sign) for q in [p, *around])


def wire(geo, nodes):
    """Stage graph: an edge unless another checkpoint lies on the way."""
    kinds = {n: n[:2] if n != "E" else "E" for n in nodes}
    sources = [n for n in nodes if kinds[n] in ("S", "CP")]
    targets = [n for n in nodes if kinds[n] in ("CP", "E")]
    checkpoints = [n for n in nodes if kinds[n] == "CP"]
    edges = {}
    for src in sources:
        cands = [t for t in targets if t != src]
        kept = [t for t in cands if not _between(geo, nodes, src, t, checkpoints)]
        if not kept:
            kept = [min(cands, key=lambda t: geo.length(nodes[src], nodes[t]))]
        edges[src] = kept
    return edges


def _between(geo, nodes, src, tgt, checkpoints):
    direct = geo.length(nodes[src], nodes[tgt])
    for mid in checkpoints:
        if mid in (src, tgt):
            continue
        via = geo.length(nodes[src], nodes[mid]) + geo.length(nodes[mid], nodes[tgt])
        if via <= direct * (1.0 + DETOUR):
            return True
    return False


def predict_discovery(geo, nodes, signs, edges):
    """Known set at t = 0 and the nearest-frontier tour, from node points."""
    known = {"S"} | {n for n in edges["S"] if legible(geo, nodes["S"], signs[n])}
    known0 = set(known)
    visited, tour, here = {"S"}, [], "S"
    frontier_log = []
    while "E" not in known:
        frontier = sorted(known - visited)
        if not frontier:
            break
        costs = {n: geo.length(nodes[here], nodes[n]) for n in frontier}
        here = min(frontier, key=costs.get)
        frontier_log.append((tour[-1] if tour else "S", costs))
        tour.append(here)
        visited.add(here)
        seen = {n for n in edges.get(here, []) if legible(geo, nodes[here], signs[n])}
        known |= seen
    return known0, tour + ["E"], frontier_log


# --- Data ---


def load_scenario():
    cfg = json.loads((SCENARIO / "config.json").read_text())
    walkable = wkt.loads((SCENARIO / "geometry.wkt").read_text())
    polys = {"S": Polygon(cfg["distributions"]["jps-distributions_0"]["coordinates"])}
    polys["E"] = Polygon(cfg["exits"]["jps-exits_0"]["coordinates"])
    signs = {}
    for key, cp in cfg["checkpoints"].items():
        name = "CP" + key.rsplit("_", 1)[1]
        polys[name] = Polygon(cp["coordinates"])
        signs[name] = (cp["sign"]["x"], cp["sign"]["y"], cp["sign"]["alpha"])
    nodes = {n: (p.centroid.x, p.centroid.y) for n, p in polys.items()}
    signs["E"] = (*nodes["E"], None)  # synthesised: omni-directional, at the node
    params = cfg["distributions"]["jps-distributions_0"]["parameters"]
    return cfg, walkable, polys, nodes, signs, params


def load_run(run_dir):
    con = sqlite3.connect(run_dir / "run.sqlite")
    traj = pd.read_sql(
        "select id, frame, pos_x as x, pos_y as y from trajectory_data "
        "order by id, frame",
        con,
    )
    con.close()
    routes = pd.read_csv(run_dir / "routes.csv")
    names = {"jps-exits_0": "E", "jps-distributions_0": "S"}
    routes["target"] = routes["new_exit"].map(
        lambda s: names.get(s, "CP" + str(s).rsplit("_", 1)[-1])
    )
    return traj, routes


def node_sequence(routes, aid):
    return list(routes.loc[routes["agent_id"] == aid, "target"])


def classify(seq):
    if not seq:
        return "direct: S-CP3-E"
    if seq == ["CP0", "CP1", "CP2", "CP3", "E"]:
        return "predicted tour: CP0-CP1-CP2-CP3-E"
    return "other order, no turn-back"


def destinations(traj, routes, full):
    """Per trajectory row, the node the agent is heading for."""
    if full:
        # full agents walk S -> CP3 -> E; past the partition the exit is next
        return np.where(traj["y"].to_numpy() > 13.1, "E", "CP3")
    out = np.empty(len(traj), dtype=object)
    for aid, idx in traj.groupby("id").groups.items():
        r = routes[routes["agent_id"] == aid]
        t = traj.loc[idx, "frame"].to_numpy() / FPS
        k = np.searchsorted(r["time_s"].to_numpy(), t, side="right") - 1
        out[np.asarray(idx)] = r["target"].to_numpy()[np.clip(k, 0, None)]
    return out


# --- Checks ---


def check_full(geo, polys, traj, routes, v0):
    rows = []
    for aid, g in traj.groupby("id"):
        xy = g[["x", "y"]].to_numpy()
        entered = {
            n for n in ("CP0", "CP1", "CP2", "CP3") if _enters(polys[n], xy[::5])
        }
        lower = geo.to_polygon(tuple(xy[0]), polys["E"])
        steps = np.linalg.norm(np.diff(xy, axis=0), axis=1)
        walked = float(steps.sum())
        rows.append(
            dict(
                id=aid,
                entered=entered,
                geodesic=lower,
                walked=walked,
                v_max=float(steps.max() * FPS),
                t_out=g["frame"].max() / FPS,
            )
        )
    df = pd.DataFrame(rows)
    df["t_min"] = df["geodesic"] / v0
    return df, len(routes)


def _enters(poly, xy):
    return any(poly.contains(Point(p)) for p in xy)


def check_discovery(geo, nodes, signs, known0, traj, routes, cell):
    """Evidence for every decision, and the exit's legibility at each wander."""
    tol = cell / 2.0 * math.sqrt(2.0)
    by_id = {aid: g for aid, g in traj.groupby("id")}
    bad, wander_seen, wander_y = [], [], []
    for r in routes.itertuples():
        g = by_id[r.agent_id]
        past = g[g["frame"] <= round(r.time_s * FPS)][["x", "y"]].to_numpy()
        if r.reason == "wander" and r.target != "S":
            p = tuple(past[-1])
            wander_seen.append(legible_all_around(geo, p, signs["E"], tol))
            if math.dist(p, nodes["CP3"]) < 1.5:
                wander_y.append(p[1])
        if r.target in known0 or r.target == "S":
            continue
        if not any(legible_near(geo, tuple(p), signs[r.target], tol) for p in past):
            bad.append((r.agent_id, r.time_s, r.target))
    first = routes.sort_values("time_s").groupby("agent_id")["target"].first()
    # where an agent skipped CP2: was CP2's sign legible when it chose at CP1?
    skipped = []
    for aid in routes["agent_id"].unique():
        seq = routes[routes["agent_id"] == aid]
        if list(seq["target"].iloc[1:3]) != ["CP1", "CP3"]:
            continue
        t = seq["time_s"].iloc[2]
        g = by_id[aid]
        p = tuple(g[g["frame"] <= round(t * FPS)][["x", "y"]].to_numpy()[-1])
        skipped.append((aid, t, p, legible_near(geo, p, signs["CP2"], tol)))
    return dict(
        evidence_violations=bad,
        first_targets=first.value_counts().to_dict(),
        wanders=len(wander_seen),
        wander_exit_legible=sum(wander_seen),
        wander_y_at_cp3=(min(wander_y), max(wander_y)) if wander_y else None,
        turned_back=routes.loc[routes["reason"] == "wander", "agent_id"].nunique(),
        skipped_cp2=skipped,
        tour=_tour_check(routes, skipped),
    )


def _tour_check(routes, skipped):
    """Agents whose exploration, up to CP3, is the tour or an explained skip."""
    hidden = {aid for aid, _, _, seen in skipped if not seen}
    counts = {"as predicted": 0, "CP2 hidden at CP1": 0, "unexplained": 0}
    for aid, r in routes.groupby("agent_id"):
        explore = list(r.loc[r["reason"] == "explore", "target"])
        prefix = explore[: explore.index("CP3") + 1] if "CP3" in explore else explore
        if prefix == ["CP0", "CP1", "CP2", "CP3"]:
            counts["as predicted"] += 1
        elif prefix == ["CP0", "CP1", "CP3"] and aid in hidden:
            counts["CP2 hidden at CP1"] += 1
        else:
            counts["unexplained"] += 1
    return counts


def door_sight(geo, sign, xs=np.arange(17.2, 18.01, 0.1)):
    """Per x across CP3's door, the lowest y (1 cm steps) the sign is legible."""
    ys = np.arange(12.5, 13.3, 0.01)
    return [next(y for y in ys if legible(geo, (x, y), sign)) for x in xs]


def cells_across(cell, lo=13.0, hi=13.1, origin=0.1):
    """Grid cell centres (origin + c/2 + k c) that fall inside [lo, hi]."""
    k0 = math.ceil((lo - origin - cell / 2) / cell - 1e-9)
    k1 = math.floor((hi - origin - cell / 2) / cell + 1e-9)
    return max(0, k1 - k0 + 1)


# --- Plot helpers ---


def style_axes(ax, frame=True):
    ax.tick_params(axis="both", which="both", length=0, labelcolor="dimgrey")
    ax.grid(False)
    sns.despine(ax=ax, left=True, bottom=True)
    if frame:
        ax.patch.set_edgecolor("lightgrey")
        ax.patch.set_linewidth(0.8)


def draw_plan(ax, walkable, polys, labels=True, fs=8):
    ax.add_patch(
        MplPolygon(np.asarray(walkable.exterior.coords), fc=FLOOR, ec=WALL, lw=1.4)
    )
    for ring in walkable.interiors:
        ax.add_patch(MplPolygon(np.asarray(ring.coords), fc=WALL, ec=WALL, lw=1.0))
    x0, y0, x1, y1 = polys["S"].bounds
    ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fc=SPAWN, ec="none", alpha=0.25))
    x0, y0, x1, y1 = polys["E"].bounds
    ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fc=EXIT, ec=EXIT, alpha=0.8))
    for n in ("CP0", "CP1", "CP2", "CP3"):
        x0, y0, x1, y1 = polys[n].bounds
        ax.add_patch(
            Rectangle(
                (x0, y0),
                x1 - x0,
                y1 - y0,
                fc="none",
                ec=DEST["CP3"],
                lw=0.9,
                hatch="////",
                alpha=0.7,
            )
        )
    if labels:
        offsets = {
            "CP0": (0.0, -0.9),
            "CP1": (0.0, 0.95),
            "CP2": (0.0, 0.95),
            "CP3": (-1.9, 0.0),
            "E": (0.0, -1.2),
            "S": (0.0, 1.45),
        }
        text = {"E": "exit", "S": "spawn"}
        for n, (dx, dy) in offsets.items():
            c = polys[n].centroid
            ax.text(
                c.x + dx,
                c.y + dy,
                text.get(n, n),
                ha="center",
                va="center",
                fontsize=fs,
                color=TEXT,
                weight="semibold",
                bbox=dict(fc="white", ec="none", alpha=0.7, pad=0.5),
                zorder=8,
            )
    ax.set_xlim(-0.3, 20.3)
    ax.set_ylim(-0.3, 18.3)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])


def draw_signs(ax, signs):
    for n, (x, y, alpha) in signs.items():
        ax.plot(x, y, marker="D", ms=4.5, mfc="#fee090", mec="#c89b00", zorder=6)
        if alpha is None:
            continue
        a = math.radians(alpha)
        ax.add_patch(
            FancyArrowPatch(
                (x, y),
                (x + 1.2 * math.sin(a), y + 1.2 * math.cos(a)),
                arrowstyle="-|>",
                mutation_scale=8,
                color="#c89b00",
                lw=1.0,
                zorder=6,
            )
        )


def plot_setup(out, walkable, polys, nodes, signs, edges, known0, full_path, tour_xy):
    fig, ax = plt.subplots(figsize=(7.2, 7.0), dpi=150)
    draw_plan(ax, walkable, polys)
    for src, tgts in edges.items():
        for t in tgts:
            ax.plot(
                *zip(nodes[src], nodes[t]), color="lightgrey", lw=0.8, ls=":", zorder=2
            )
    ax.plot(*zip(*full_path), color=FULL, lw=2.2, zorder=4)
    ax.plot(*zip(*tour_xy), color=DISC, lw=1.8, ls=(0, (4, 2)), zorder=4)
    draw_signs(ax, signs)
    for n in nodes:
        known = n in known0
        ax.scatter(
            *nodes[n],
            s=46,
            marker="o",
            fc=DEST["CP3"] if known else "white",
            ec=DEST["CP3"],
            lw=1.2,
            zorder=7,
        )
    ax.text(
        10.0,
        15.4,
        "the partition has one door (CP3):\nevery route to the exit passes it",
        ha="center",
        va="center",
        fontsize=8.5,
        color=TEXT,
        bbox=dict(fc="white", ec="none", alpha=0.85, pad=2),
    )
    ax.text(
        3.6,
        8.0,
        "dead end:\nthe west rooms\nhold no exit",
        ha="center",
        va="center",
        fontsize=8.5,
        color=TEXT,
    )
    handles = [
        Line2D([0], [0], color=FULL, lw=2.2, label="full: shortest path"),
        Line2D(
            [0],
            [0],
            color=DISC,
            lw=1.8,
            ls=(0, (4, 2)),
            label="discovery: predicted tour",
        ),
        Line2D([0], [0], color="lightgrey", lw=0.8, ls=":", label="stage-graph edge"),
        Line2D(
            [0],
            [0],
            ls="none",
            marker="o",
            mfc=DEST["CP3"],
            mec=DEST["CP3"],
            label="known to discovery at t = 0",
        ),
        Line2D(
            [0],
            [0],
            ls="none",
            marker="o",
            mfc="white",
            mec=DEST["CP3"],
            label="unknown at t = 0",
        ),
        Line2D(
            [0],
            [0],
            ls="none",
            marker="D",
            mfc="#fee090",
            mec="#c89b00",
            label="sign (arrow: facing)",
        ),
        Patch(fc=SPAWN, alpha=0.25, label="spawn area, 20 agents"),
        Patch(fc=EXIT, alpha=0.8, label="exit"),
    ]
    ax.legend(
        handles=handles,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.01),
        ncol=2,
        fontsize=8,
        **LEGEND,
    )
    style_axes(ax, frame=False)
    fig.savefig(out / "familiarity_setup.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def _dest_segments(xy, dest):
    segs = np.stack([xy[:-1], xy[1:]], axis=1)
    colors = [DEST[d] for d in dest[:-1]]
    return segs, colors


def plot_paths(out, walkable, polys, runs, titles):
    fig, axes = plt.subplots(
        1, 2, figsize=(11.0, 5.2), dpi=150, gridspec_kw=dict(wspace=0.04)
    )
    for ax, (key, title) in zip(axes, titles.items()):
        traj, dest = runs[key]["traj"], runs[key]["dest"]
        draw_plan(ax, walkable, polys, fs=7.5)
        for _, idx in traj.groupby("id").groups.items():
            idx = np.asarray(idx)[::3]
            xy = traj.loc[idx, ["x", "y"]].to_numpy()
            segs, colors = _dest_segments(xy, dest[idx])
            ax.add_collection(
                LineCollection(segs, colors=colors, lw=1.0, alpha=0.75, zorder=3)
            )
        ax.set_title(title, loc="left", fontsize=10, color=TEXT, pad=4)
        style_axes(ax, frame=False)
    axes[0].text(
        10.0,
        8.0,
        "no agent enters\nthe west rooms",
        ha="center",
        va="center",
        fontsize=9,
        color=TEXT,
    )
    axes[1].text(
        3.6,
        8.5,
        "every agent explores\nthe west rooms first",
        ha="center",
        va="center",
        fontsize=9,
        color=TEXT,
    )
    handles = [
        Line2D([0], [0], color=DEST[n], lw=2.0, label=f"heading for {lab}")
        for n, lab in (
            ("CP0", "CP0"),
            ("CP1", "CP1"),
            ("CP2", "CP2"),
            ("CP3", "CP3"),
            ("E", "the exit"),
            ("S", "spawn (patrol)"),
        )
    ]
    fig.legend(
        handles=handles,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.1),
        ncol=6,
        fontsize=8,
        **LEGEND,
    )
    fig.savefig(out / "familiarity_paths.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def plot_egress(out, curves, bounds, patterns, note):
    fig, (ax, axb) = plt.subplots(
        1,
        2,
        figsize=(11.5, 4.6),
        dpi=150,
        gridspec_kw=dict(width_ratios=[1.25, 1.0], wspace=0.5),
    )
    styles = {
        "full": dict(color=FULL, lw=2.2, ls="-"),
        f"discovery, {MAIN_CELL:g} m": dict(color=DISC, lw=2.2, ls="--"),
    }
    for label, t in curves.items():
        st = styles.get(label, dict(color="#969696", lw=0.9, ls=":"))
        n = np.arange(1, len(t) + 1)
        ax.step(np.r_[0.0, t], np.r_[0, n], where="post", label=label, **st)
        tag = label.removeprefix("discovery, ") if label not in styles else ""
        ax.text(
            t[-1],
            len(t) + 0.4,
            f"{tag}\n{t[-1]:.0f} s".strip(),
            fontsize=7.5,
            color=TEXT,
            ha="center",
            va="bottom",
        )
    for label, (tb, color) in bounds.items():
        ax.axvline(tb, color=color, lw=0.9, ls="-.", zorder=1, label=label)
    ax.text(
        0.97,
        0.6,
        note,
        transform=ax.transAxes,
        fontsize=8,
        color=TEXT,
        ha="right",
        va="top",
    )
    ax.set_xlabel("time [s]", color=TEXT)
    ax.set_ylabel("agents out [-]", color=TEXT)
    ax.set_yticks([0, 5, 10, 15, 20])
    ax.set_ylim(0, 23.5)
    ax.set_xlim(0, max(t[-1] for t in curves.values()) + 15)
    ax.legend(loc="lower right", fontsize=7.5, **LEGEND)
    ax.set_title("Agents out over time", loc="left", fontsize=10, color=TEXT)
    style_axes(ax)

    labels = list(patterns)
    left = np.zeros(len(labels))
    for name, color in PATTERN_COLORS.items():
        vals = np.array([patterns[k].get(name, 0) for k in labels])
        hatch = "////" if "turned back" in name else None
        axb.barh(
            labels, vals, left=left, color=color, ec="white", hatch=hatch, label=name
        )
        _bar_labels(axb, left, vals, "white" if color in (FULL, "#d73027") else "black")
        left += vals
    axb.invert_yaxis()
    axb.set_xlim(0, 20)
    axb.set_xlabel("agents [-]", color=TEXT)
    axb.set_title("Route of each of the 20 agents", loc="left", fontsize=10, color=TEXT)
    axb.legend(
        loc="upper center", bbox_to_anchor=(0.35, -0.16), ncol=2, fontsize=7.5, **LEGEND
    )
    style_axes(axb, frame=False)
    fig.savefig(out / "familiarity_egress.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def _bar_labels(ax, left, vals, color):
    for y, (lo, v) in enumerate(zip(left, vals)):
        if not v:
            continue
        ax.text(
            lo + v / 2,
            y,
            str(v),
            ha="center",
            va="center",
            fontsize=8,
            color=color,
            weight="semibold",
            bbox=dict(fc="#d73027", ec="none", pad=1)
            if color == "white" and lo > 0
            else None,
        )


def render_gif(out, walkable, polys, runs, titles, step_s=1.0, fps=10):
    t_end = max(runs[k]["traj"]["frame"].max() for k in titles) / FPS
    times = np.arange(0.0, t_end + step_s, step_s)
    fig, axes = plt.subplots(1, 2, figsize=(6.6, 3.55), dpi=100)
    fig.subplots_adjust(left=0.01, right=0.99, top=0.86, bottom=0.14, wspace=0.04)
    dots, counters = [], []
    for ax, (key, title) in zip(axes, titles.items()):
        draw_plan(ax, walkable, polys, fs=6)
        dots.append(ax.scatter([], [], s=20, ec="black", lw=0.3, zorder=5))
        ax.set_title(title, fontsize=8.5, color=TEXT, loc="left", pad=3)
        counters.append(
            ax.text(19.8, 17.4, "", fontsize=7.5, color=TEXT, ha="right", va="top")
        )
        style_axes(ax, frame=False)
    clock = fig.text(0.99, 0.965, "", fontsize=9, color=TEXT, ha="right", va="top")
    fig.legend(
        handles=[
            Line2D(
                [0],
                [0],
                ls="none",
                marker="o",
                mfc=DEST[n],
                mec="black",
                mew=0.3,
                label=lab,
            )
            for n, lab in (
                ("CP0", "CP0"),
                ("CP1", "CP1"),
                ("CP2", "CP2"),
                ("CP3", "CP3"),
                ("E", "exit"),
                ("S", "spawn"),
            )
        ],
        title="heading for",
        title_fontsize=7,
        loc="lower center",
        ncol=6,
        fontsize=7,
        handletextpad=0.1,
        columnspacing=0.8,
        **LEGEND,
    )
    by_frame = {
        k: {f: g for f, g in runs[k]["traj"].assign(d=runs[k]["dest"]).groupby("frame")}
        for k in titles
    }
    writer = PillowWriter(fps=fps)
    with writer.saving(fig, out / "familiarity.gif", dpi=100):
        for t in times:
            for dot, counter, key in zip(dots, counters, titles):
                g = by_frame[key].get(int(round(t * FPS)))
                n_in = 0 if g is None else len(g)
                xy = np.empty((0, 2)) if g is None else g[["x", "y"]].to_numpy()
                dot.set_offsets(xy)
                if g is not None:
                    dot.set_facecolor([DEST[d] for d in g["d"]])
                counter.set_text(f"out: {20 - n_in} / 20")
            clock.set_text(f"t = {t:3.0f} s")
            writer.grab_frame()
    plt.close(fig)
    return len(times)


def main():
    """Derive the expected behaviour, check both runs, draw the figures.

    Parameters
    ----------
    --data : path
        Directory with ``full/`` and ``discovery_cell<c>/`` run folders.

    Saves
    -----
    site/static/images/verification/familiarity_setup.png
    site/static/images/verification/familiarity_paths.png
    site/static/images/verification/familiarity_egress.png
    site/static/images/verification/familiarity.gif
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--data",
        type=Path,
        required=True,
        help="directory with full/ and discovery_cell<c>/ (run.sqlite, routes.csv)",
    )
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    # --- Style Setup ---
    sns.set_theme(font_scale=1.0, style="whitegrid", font="DejaVu Sans")

    # --- Expected: geometry only ---
    cfg, walkable, polys, nodes, signs, params = load_scenario()
    v0 = float(params["v0"])
    geo = Geodesic(walkable)
    edges = wire(geo, nodes)
    known0, tour, frontier_log = predict_discovery(geo, nodes, signs, edges)
    l_full, full_path = geo.path(nodes["S"], nodes["E"])
    tour_xy, l_tour = [nodes["S"]], 0.0
    for a, b in zip(["S", *tour], tour):
        d, pts = geo.path(nodes[a], nodes[b])
        l_tour += d
        tour_xy += pts[1:]
    n_edges = sum(len(v) for v in edges.values())
    print(f"edges ({n_edges}):", {k: sorted(v) for k, v in edges.items()})
    print("discovery known at t = 0:", sorted(known0))
    for here, costs in frontier_log:
        print(f"  frontier from {here}:", {k: round(v, 1) for k, v in costs.items()})
    print("predicted tour:", " -> ".join(["S", *tour]))
    print(f"shortest S -> E: {l_full:.2f} m ({l_full / v0:.1f} s at {v0} m/s)")
    print(f"tour S -> E: {l_tour:.2f} m ({l_tour / v0:.1f} s), x{l_tour / l_full:.2f}")
    y_first = door_sight(geo, signs["E"])
    print(
        "exit sign legible from the CP3 point:",
        legible(geo, nodes["CP3"], signs["E"]),
        f"| across the door (x 17.2-18.0) first legible at y = "
        f"{min(y_first):.2f}-{max(y_first):.2f} m",
    )

    # --- Data: runs ---
    runs = {}
    traj, routes = load_run(args.data / "full")
    full, n_switch = check_full(geo, polys, traj, routes, v0)
    runs["full"] = dict(traj=traj, dest=destinations(traj, routes, full=True))
    never = sum(not (e & {"CP0", "CP1", "CP2"}) for e in full["entered"])
    via3 = sum("CP3" in e for e in full["entered"])
    print(
        f"full: {via3}/20 pass CP3, {never}/20 never enter CP0-CP2, "
        f"{n_switch} route changes; walked/geodesic "
        f"{(full.walked / full.geodesic).min():.3f}-"
        f"{(full.walked / full.geodesic).max():.3f}; first out "
        f"{full.t_out.min():.1f} s; min over agents of t_out - L/v0 "
        f"{(full.t_out - full.t_min).min():+.2f} s; max speed "
        f"{full.v_max.max():.2f} m/s; last out "
        f"{full.t_out.max():.1f} s"
    )
    curves = {"full": np.sort(full.t_out.to_numpy())}
    patterns = {"full": {"direct: S-CP3-E": 20}}
    calm_last = []
    cells = sorted(
        float(p.name.removeprefix("discovery_cell"))
        for p in args.data.glob("discovery_cell*")
    )
    for cell in reversed(cells):
        traj, routes = load_run(args.data / f"discovery_cell{cell:g}")
        res = check_discovery(geo, nodes, signs, known0, traj, routes, cell)
        t_out = np.sort(traj.groupby("id")["frame"].max().to_numpy() / FPS)
        label = f"discovery, {cell:g} m"
        curves[label] = t_out
        seqs = {a: node_sequence(routes, a) for a in routes["agent_id"].unique()}
        wanderers = set(routes.loc[routes["reason"] == "wander", "agent_id"])
        pat = {}
        for a, s in seqs.items():
            name = "turned back at CP3 (wander)" if a in wanderers else classify(s)
            pat[name] = pat.get(name, 0) + 1
        patterns[f"discovery {cell:g} m"] = pat
        print(
            f"{label}: last out {t_out[-1]:.1f} s; cells across the partition "
            f"{cells_across(cell)}; first targets {res['first_targets']}; "
            f"evidence violations {len(res['evidence_violations'])}; turned back "
            f"{res['turned_back']}; wander decisions {res['wanders']} "
            f"(exit legible all around at {res['wander_exit_legible']}); routes {pat}; "
            f"tour up to CP3 {res['tour']}; y of wanders at CP3 {res['wander_y_at_cp3']}"
        )
        last = traj.groupby("id")["frame"].max() / FPS
        calm = last.drop(index=list(wanderers), errors="ignore")
        print(
            f"  first out {t_out[0]:.1f} s (tour bound {l_tour / v0:.1f} s); last out "
            f"of agents that never turned back: {calm.max():.1f} s"
        )
        calm_last.append(calm.max())
        for aid, t, p, seen in res["skipped_cp2"]:
            print(
                f"  agent {aid} chose CP3 over CP2 at t = {t:.0f} s from "
                f"({p[0]:.2f}, {p[1]:.2f}); CP2 sign legible there: {seen}"
            )
        if cell == MAIN_CELL:
            runs["discovery"] = dict(
                traj=traj, dest=destinations(traj, routes, full=False)
            )

    calm_range = f"{min(calm_last):.0f}\u2013{max(calm_last):.0f} s"

    # --- Plot ---
    plot_setup(OUT, walkable, polys, nodes, signs, edges, known0, full_path, tour_xy)
    titles = {
        "full": "full: knows the plan",
        "discovery": f"discovery: learns it ({MAIN_CELL:g} m grid)",
    }
    plot_paths(OUT, walkable, polys, runs, titles)
    bounds = {
        f"bound, full: {l_full:.1f} m / v0 = {l_full / v0:.0f} s": (l_full / v0, FULL),
        f"bound, tour: {l_tour:.1f} m / v0 = {l_tour / v0:.0f} s": (l_tour / v0, DISC),
    }
    note = "agents that never turned back\nare out by " + calm_range + "\nat every grid"
    plot_egress(OUT, curves, bounds, patterns, note)
    frames = render_gif(OUT, walkable, polys, runs, titles)
    size = (OUT / "familiarity.gif").stat().st_size / 1e6
    print(f"familiarity.gif: {frames} frames, {size:.2f} MB")


if __name__ == "__main__":
    main()
