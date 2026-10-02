# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "matplotlib",
#     "numpy",
#     "pandas",
#     "pillow",
#     "seaborn",
#     "shapely",
# ]
# ///
"""Figures for the verification test "Familiarity: full map vs discovered map".

``assets/familiarity_test_full`` and ``assets/familiarity_test_discovery`` are
one 20 x 18 m plan with one exit, four signed checkpoints and 20 agents; only
the spawn group's ``familiarity`` differs. The expected behaviour is derived
here from the geometry alone, with no pyFDS-Evac code:

* shortest paths: a visibility graph over the walkable polygon (shapely);
* the stage graph: every spawn/checkpoint is wired to each checkpoint/exit it
  reaches without passing another checkpoint (detour <= 5 %), the rule of
  Models > Wayfinding, recomputed with those shortest paths;
* legibility in clear air, fdsvismap's rule: a sign at s with facing n
  (compass bearing alpha) is legible from p when the segment p-s stays in the
  walkable area and n.(p - s) / |p - s| * 30 m >= |p - s|; an unoriented sign
  only needs |p - s| <= 30 m. The variant with the 30 m cap applied after the
  view angle (front half-disc) is checked to give the same predictions;
* discovery at t = 0: spawn plus the spawn's neighbours whose sign is legible
  from the spawn's centroid; then the nearest known, unvisited node, until the
  exit is legible.

The runs are read from ``--data``; nothing is simulated here. ``DIR`` holds
``full/`` and ``discovery_cell<c>/`` for each clear-air grid c, each with the
``run.sqlite``, ``routes.csv`` and ``cognitive_map.csv`` that
``scripts/verification/familiarity_run.py`` wrote. Every check is made twice:
with no grid tolerance and with the tolerance ``grid_tol`` derives from the
vismap's discretisation.

Run from the repository root::

    uv run python scripts/verification/familiarity_figures.py --data DIR

Writes ``familiarity_setup.png``, ``familiarity_paths.png``,
``familiarity_door.png``, ``familiarity_egress.png`` and ``familiarity.gif`` to
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
TURN = "#8073ac"  # turned back at CP3: purple, hatched; not a node colour
SIGN = "#c89b00"  # sign facing: gold arrow
PATTERN_COLORS = {
    "direct: S-CP3-exit": FULL,
    "tour, then exit": "#fee090",
    "CP2 skipped: sign hidden at CP1": "#80cdc1",
    "CP1 and CP2 skipped: CP1 not learnt": "#dfc27d",
    "tour, turned back at CP3 (#250)": TURN,
}
# discovery grids: one orange ramp, one dash per grid; 0.05 m is the reference
GRID_STYLE = {
    "0.25 m": dict(color="#fdae6b", lw=1.4, ls=(0, (1, 1.2))),
    "0.1 m": dict(color="#fd8d3c", lw=1.3, ls="-."),
    "0.05 m": dict(color="#e6550d", lw=2.4, ls="--"),
    "0.025 m": dict(color="#a63603", lw=1.3, ls=(0, (6, 1.5, 1, 1.5, 1, 1.5))),
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


def grid_tol(cell):
    """Largest shift of the sight boundary the vismap grid can cause [m].

    ``VisibilityModel.clear_air`` and fdsvismap 0.3.1 introduce four errors,
    each a lateral shift of a sight line of at most:

    * the observer snaps to the nearest cell centre: c sqrt(2) / 2;
    * the sign snaps to the nearest cell centre: c sqrt(2) / 2;
    * a wall cell blocks when its centre is outside the walkable area, so a
      wall face moves by up to c / 2;
    * rays are drawn anti-aliased (``skimage.draw.line_aa``), which marks the
      cells up to one cell beside the ideal line: c.

    Their sum is c (sqrt(2) + 3/2), about 2.9 c.
    """
    return cell * (math.sqrt(2.0) + 1.5)


def disc(p, tol):
    """The centre and 48 points on three rings of radius tol/3, 2 tol/3, tol."""
    pts = [p]
    if tol <= 0:
        return pts
    for k, n in ((1, 8), (2, 16), (3, 24)):
        r = tol * k / 3.0
        for t in np.linspace(0.0, 2.0 * math.pi, n, endpoint=False):
            pts.append((p[0] + r * math.cos(t), p[1] + r * math.sin(t)))
    return pts


def legible_somewhere(geo, p, sign, tol, rule=None):
    """Legible from some point within tol of p: not certainly hidden."""
    rule = rule or legible
    return any(rule(geo, q, sign) for q in disc(p, tol))


def legible_everywhere(geo, p, sign, tol, rule=None):
    """Legible from every point within tol of p: certainly legible."""
    rule = rule or legible
    return all(rule(geo, q, sign) for q in disc(p, tol))


def legible_half_disc(geo, p, sign):
    """Variant: the 30 m cap applied after the view angle (front half-disc)."""
    x, y, alpha = sign
    d = math.dist(p, (x, y))
    if d < 1e-9:
        return True
    if d > READ_M or not geo.sees(p, (x, y)):
        return False
    if alpha is None:
        return True
    a = math.radians(alpha)
    return math.sin(a) * (p[0] - x) + math.cos(a) * (p[1] - y) > 0.0


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


def predict_discovery(geo, nodes, signs, edges, rule=legible):
    """Known set at t = 0 and the nearest-frontier tour, from node points."""
    known = {"S"} | {n for n in edges["S"] if rule(geo, nodes["S"], signs[n])}
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
        seen = {n for n in edges.get(here, []) if rule(geo, nodes[here], signs[n])}
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


def short(node_id):
    """Short node name: S, E or CP<k>."""
    names = {"jps-exits_0": "E", "jps-distributions_0": "S"}
    return names.get(node_id, "CP" + str(node_id).rsplit("_", 1)[-1])


def load_run(run_dir):
    con = sqlite3.connect(run_dir / "run.sqlite")
    traj = pd.read_sql(
        "select id, frame, pos_x as x, pos_y as y from trajectory_data "
        "order by id, frame",
        con,
    )
    con.close()
    routes = pd.read_csv(run_dir / "routes.csv")
    routes["target"] = routes["new_exit"].map(short)
    maps = pd.read_csv(run_dir / "cognitive_map.csv", keep_default_na=False)
    maps["nodes"] = maps["known_nodes"].map(lambda s: {short(n) for n in s.split()})
    maps["edges"] = maps["known_edges"].map(
        lambda s: {tuple(short(n) for n in e.split(">")) for e in s.split()}
    )
    return traj, routes, maps


def node_sequence(routes, aid):
    return list(routes.loc[routes["agent_id"] == aid, "target"])


def position(g, t):
    """Agent position at time t, interpolated between the 10 fps frames."""
    ft = g["frame"].to_numpy() / FPS
    return (
        float(np.interp(t, ft, g["x"].to_numpy())),
        float(np.interp(t, ft, g["y"].to_numpy())),
    )


def destinations(traj, routes, full):
    """Per trajectory row, the node the agent is heading for and the reason."""
    if full:
        # full agents walk S -> CP3 -> E; past the partition the exit is next
        dest = np.where(traj["y"].to_numpy() > 13.1, "E", "CP3")
        return dest, np.full(len(traj), "shortest", dtype=object)
    out = np.empty(len(traj), dtype=object)
    why = np.empty(len(traj), dtype=object)
    for aid, idx in traj.groupby("id").groups.items():
        r = routes[routes["agent_id"] == aid]
        t = traj.loc[idx, "frame"].to_numpy() / FPS
        k = np.clip(
            np.searchsorted(r["time_s"].to_numpy(), t, side="right") - 1, 0, None
        )
        out[np.asarray(idx)] = r["target"].to_numpy()[k]
        why[np.asarray(idx)] = r["reason"].to_numpy()[k]
    return out, why


# --- Checks ---


def check_full(geo, polys, traj, routes, maps, edges, v0):
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
    wired = {(a, b) for a, bs in edges.items() for b in bs}
    first = maps.sort_values("time_s").groupby("agent_id").first()
    whole = sum(
        r.nodes == set(edges) | {"E"} and r.edges == wired for r in first.itertuples()
    )
    return df, len(routes), dict(whole_map_at_t0=whole, map_changes=len(maps) - 20)


def _enters(poly, xy):
    return any(poly.contains(Point(p)) for p in xy)


def check_learning(geo, signs, edges, known0, traj, maps, tol):
    """Criteria 2 and 3 from the recorded cognitive maps.

    Returns the agents whose map at t = 0 is not ``known0``, and every node
    learnt later that breaks the rule: it must be a stage-graph neighbour of a
    node already known, and its sign must not be certainly hidden (legible
    from some point within tol of the agent's position at that time).
    """
    wired = {(a, b) for a, bs in edges.items() for b in bs}
    by_id = {aid: g for aid, g in traj.groupby("id")}
    wrong_start, not_neighbour, hidden, learnt = [], [], [], 0
    for aid, m in maps.sort_values("time_s").groupby("agent_id"):
        rows = list(m.itertuples())
        if rows[0].time_s > 0 or rows[0].nodes != known0:
            wrong_start.append(aid)
        for prev, cur in zip(rows, rows[1:]):
            p = position(by_id[aid], cur.time_s)
            for n in sorted(cur.nodes - prev.nodes):
                learnt += 1
                if not any((u, n) in wired for u in prev.nodes):
                    not_neighbour.append((aid, cur.time_s, n))
                if not legible_somewhere(geo, p, signs[n], tol):
                    hidden.append((aid, round(cur.time_s, 2), n, p))
    return dict(
        wrong_start=wrong_start,
        learnt=learnt,
        not_neighbour=not_neighbour,
        hidden=hidden,
    )


def check_decisions(geo, signs, traj, routes, tol):
    """Criteria 4 and 5: the skip of CP2 and every patrol decision.

    A skip, or a patrol, breaks the rule only when the sign it ignores was
    certainly legible: from every point within tol of the agent's position.
    """
    by_id = {aid: g for aid, g in traj.groupby("id")}
    patrols, patrol_seen, skips = [], [], []
    for r in routes.itertuples():
        if r.reason != "wander":
            continue
        p = position(by_id[r.agent_id], r.time_s)
        patrols.append((r.agent_id, r.time_s, p))
        if legible_everywhere(geo, p, signs["E"], tol):
            patrol_seen.append((r.agent_id, r.time_s, p))
    for aid, seq in routes.groupby("agent_id"):
        explore = list(seq.loc[seq["reason"] == "explore", "target"])
        prefix = explore[: explore.index("CP3") + 1] if "CP3" in explore else explore
        if prefix == ["CP0", "CP1", "CP2", "CP3"]:
            skips.append((aid, "as predicted", None))
            continue
        if prefix != ["CP0", "CP1", "CP3"]:
            skips.append((aid, "unexplained", None))
            continue
        t = seq.loc[seq["target"] == "CP3", "time_s"].iloc[0]
        p = position(by_id[aid], t)
        seen = legible_everywhere(geo, p, signs["CP2"], tol)
        skips.append((aid, "unexplained" if seen else "CP2 hidden at CP1", p))
    tour = {"as predicted": 0, "CP2 hidden at CP1": 0, "unexplained": 0}
    for _, kind, _ in skips:
        tour[kind] += 1
    return dict(
        patrols=patrols,
        patrol_seen=patrol_seen,
        tour=tour,
        skipped=[(a, p) for a, k, p in skips if p is not None],
    )


def route_class(seq, turned_back, skipped):
    """One route category per agent; the categories do not overlap."""
    if not seq:
        return "direct: S-CP3-exit"
    if turned_back:
        return "tour, turned back at CP3 (#250)"
    if "CP3" in seq and "CP1" not in seq[: seq.index("CP3")]:
        return "CP1 and CP2 skipped: CP1 not learnt"
    if skipped:
        return "CP2 skipped: sign hidden at CP1"
    return "tour, then exit"


def door_crossings(traj, y_door=13.05, x_lo=17.0, x_hi=18.2):
    """Per agent, the first time its centre crosses the door's mid-line."""
    times = []
    for _, g in traj.groupby("id"):
        y, x = g["y"].to_numpy(), g["x"].to_numpy()
        k = np.flatnonzero((y[:-1] < y_door) & (y[1:] >= y_door))
        k = [i for i in k if x_lo <= x[i] <= x_hi]
        if not k:
            continue
        i = k[0]
        f = (y_door - y[i]) / (y[i + 1] - y[i])
        times.append((g["frame"].iloc[i] + f) / FPS)
    return np.array(times)


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


def scale_bar(ax, x0=0.0, y0=-0.75, length=5.0, fs=7.5):
    """A length bar below the plan: the plan has no axis ticks."""
    ax.plot([x0, x0 + length], [y0, y0], color=TEXT, lw=1.6, solid_capstyle="butt")
    for x in (x0, x0 + length):
        ax.plot([x, x], [y0 - 0.18, y0 + 0.18], color=TEXT, lw=1.0)
    ax.text(
        x0 + length + 0.4, y0, f"{length:g} m", fontsize=fs, color=TEXT, va="center"
    )


def draw_plan(ax, walkable, polys, labels=True, fs=8, bar=True):
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
            "CP2": (-1.0, 0.95),
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
    if bar:
        scale_bar(ax, fs=fs)
    ax.set_xlim(-0.3, 20.3)
    ax.set_ylim(-1.3 if bar else -0.3, 18.3)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])


def draw_signs(ax, signs, zorder=9):
    for x, y, alpha in signs.values():
        if alpha is None:
            continue
        a = math.radians(alpha)
        ax.add_patch(
            FancyArrowPatch(
                (x, y),
                (x + 1.4 * math.sin(a), y + 1.4 * math.cos(a)),
                arrowstyle="-|>",
                mutation_scale=10,
                color=SIGN,
                lw=1.6,
                zorder=zorder,
            )
        )


def plot_setup(out, walkable, polys, nodes, signs, edges, known0, full_path, tour_xy):
    fig, ax = plt.subplots(figsize=(7.2, 7.4), dpi=150)
    draw_plan(ax, walkable, polys)
    for src, tgts in edges.items():
        for t in tgts:
            ax.plot(
                *zip(nodes[src], nodes[t]), color="lightgrey", lw=0.8, ls=":", zorder=2
            )
    ax.plot(*zip(*full_path), color=FULL, lw=2.2, zorder=4)
    ax.plot(*zip(*tour_xy), color=DISC, lw=1.8, ls=(0, (4, 2)), zorder=4)
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
    draw_signs(ax, signs)
    ax.text(
        10.0,
        15.4,
        "the partition has one 1.2 m door;\nCP3 is the box just behind it",
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
            marker=r"$\rightarrow$",
            ms=12,
            color=SIGN,
            label="sign, pointing where it faces",
        ),
        Patch(fc=SPAWN, alpha=0.25, label="spawn area, 20 agents"),
        Patch(fc=EXIT, alpha=0.8, label="exit (its sign has no facing)"),
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


def _segments(xy, dest):
    segs = np.stack([xy[:-1], xy[1:]], axis=1)
    colors = [DEST[d] for d in dest[:-1]]
    return segs, colors


def plot_paths(out, walkable, polys, runs, titles, n_turned, n_west):
    fig, axes = plt.subplots(
        1, 2, figsize=(11.0, 5.5), dpi=150, gridspec_kw=dict(wspace=0.04)
    )
    for ax, (key, title) in zip(axes, titles.items()):
        traj, dest, why = runs[key]["traj"], runs[key]["dest"], runs[key]["why"]
        draw_plan(ax, walkable, polys, fs=7.5)
        for _, idx in traj.groupby("id").groups.items():
            idx = np.asarray(idx)[::3]
            xy = traj.loc[idx, ["x", "y"]].to_numpy()
            segs, colors = _segments(xy, dest[idx])
            patrol = why[idx][:-1] == "wander"
            for mask, ls in ((~patrol, "solid"), (patrol, (0, (2, 1.5)))):
                if not mask.any():
                    continue
                ax.add_collection(
                    LineCollection(
                        segs[mask],
                        colors=[c for c, m in zip(colors, mask) if m],
                        lw=1.0 if ls == "solid" else 1.3,
                        linestyles=ls,
                        alpha=0.8,
                        zorder=3,
                    )
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
        f"{n_west} agents explore\nthe west rooms first",
        ha="center",
        va="center",
        fontsize=9,
        color=TEXT,
    )
    axes[1].annotate(
        f"{n_turned} agents turn back\nat CP3's door (#250)",
        xy=(16.9, 12.9),
        xytext=(12.0, 10.2),
        fontsize=9,
        color=TEXT,
        ha="center",
        bbox=dict(fc="white", ec="none", alpha=0.85, pad=1.5),
        arrowprops=dict(arrowstyle="->", color=TEXT, lw=0.9),
        zorder=9,
    )
    handles = [
        Line2D([0], [0], color=DEST[n], lw=2.0, label=f"heading for {lab}")
        for n, lab in (
            ("CP0", "CP0"),
            ("CP1", "CP1"),
            ("CP2", "CP2"),
            ("CP3", "CP3"),
            ("E", "the exit"),
            ("S", "spawn"),
        )
    ]
    handles.append(
        Line2D([0], [0], color=TEXT, lw=1.3, ls=(0, (2, 1.5)), label="patrol (wander)")
    )
    fig.legend(
        handles=handles,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.08),
        ncol=7,
        fontsize=8,
        **LEGEND,
    )
    fig.savefig(out / "familiarity_paths.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def plot_door(out, walkable, polys, geo, signs, patrols, tol):
    """Zoom on CP3's door: where arrival registers, where the exit is seen."""
    fig, ax = plt.subplots(figsize=(7.0, 5.2), dpi=150)
    x_lo, x_hi, y_lo, y_hi = 16.3, 18.9, 12.35, 14.15
    ax.set_facecolor(WALL)
    ax.add_patch(
        MplPolygon(np.asarray(walkable.exterior.coords), fc=FLOOR, ec=WALL, lw=1.2)
    )
    for ring in walkable.interiors:
        ax.add_patch(MplPolygon(np.asarray(ring.coords), fc=WALL, ec=WALL, lw=1.0))
    # where arrival at CP3 can register: within 0.7 m of a point in its box
    reach = polys["CP3"].buffer(0.7).intersection(walkable)
    for part in getattr(reach, "geoms", [reach]):
        ax.add_patch(
            MplPolygon(
                np.asarray(part.exterior.coords),
                fc="none",
                ec=DEST["CP3"],
                lw=1.0,
                ls="--",
                zorder=3,
            )
        )
    x0, y0, x1, y1 = polys["CP3"].bounds
    ax.add_patch(
        Rectangle(
            (x0, y0),
            x1 - x0,
            y1 - y0,
            fc="none",
            ec=DEST["CP3"],
            lw=1.0,
            hatch="////",
            alpha=0.7,
            zorder=3,
        )
    )
    # the exit sign becomes legible above this line (exact geometry)
    xs = np.linspace(17.0, 18.2, 121)
    ys = np.arange(12.3, 13.4, 0.005)
    y_edge = np.array(
        [next((y for y in ys if legible(geo, (x, y), signs["E"])), np.nan) for x in xs]
    )
    ax.fill_between(xs, y_edge, 13.22, color=EXIT, alpha=0.1, lw=0, zorder=1)
    ax.plot(xs, y_edge, color=EXIT, lw=1.8, zorder=4)
    ax.fill_between(
        xs, y_edge - tol, y_edge + tol, color=EXIT, alpha=0.25, lw=0, zorder=1
    )
    px = np.array([p[0] for _, _, p in patrols])
    py = np.array([p[1] for _, _, p in patrols])
    near = (px > x_lo) & (px < x_hi) & (py > y_lo) & (py < y_hi)
    ax.scatter(
        px[near],
        py[near],
        s=34,
        marker="o",
        fc=TURN,
        ec="black",
        lw=0.8,
        zorder=6,
    )
    ax.annotate(
        "sight line to the exit sign\n(16.5 m west) grazes the west jamb",
        xy=(17.02, 13.1),
        xytext=(16.35, 13.98),
        fontsize=8.5,
        color=TEXT,
        va="center",
        bbox=dict(fc="white", ec="none", alpha=0.85, pad=1),
        arrowprops=dict(arrowstyle="->", color=EXIT, lw=0.9),
        zorder=8,
    )
    ax.text(
        17.55,
        13.5,
        "CP3 box",
        fontsize=8.5,
        color=TEXT,
        ha="center",
        va="center",
        bbox=dict(fc="white", ec="none", alpha=0.85, pad=1),
        zorder=8,
    )
    ax.annotate(
        "arrival at CP3 can register\nhere, before the door",
        xy=(17.1, 12.62),
        xytext=(16.4, 12.45),
        fontsize=8.5,
        color=TEXT,
        va="center",
        bbox=dict(fc="white", ec="none", alpha=0.85, pad=1),
        arrowprops=dict(arrowstyle="->", color=DEST["CP3"], lw=0.9),
        zorder=8,
    )
    handles = [
        Patch(fc="none", ec=DEST["CP3"], hatch="////", label="CP3 box"),
        Line2D(
            [0],
            [0],
            color=DEST["CP3"],
            lw=1.0,
            ls="--",
            label="arrival can register: within 0.7 m of the box (#69)",
        ),
        Line2D([0], [0], color=EXIT, lw=1.8, label="exit sign legible above this line"),
        Patch(fc=EXIT, alpha=0.4, label=f"grid tolerance ±{tol:.2f} m (0.05 m grid)"),
        Line2D(
            [0],
            [0],
            ls="none",
            marker="o",
            mfc=TURN,
            mec="black",
            label=f"{near.sum()} patrol decisions by "
            f"{len({a for (a, _, _), n in zip(patrols, near) if n})} agents, "
            "0.05 m grid",
        ),
    ]
    ax.legend(
        handles=handles,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.1),
        ncol=2,
        fontsize=8,
        **LEGEND,
    )
    ax.set_xlim(x_lo, x_hi)
    ax.set_ylim(y_lo, y_hi)
    ax.set_aspect("equal")
    ax.set_xlabel("x [m]", color=TEXT)
    ax.set_ylabel("y [m]", color=TEXT)
    style_axes(ax)
    fig.savefig(out / "familiarity_door.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def plot_egress(out, curves, refs, patterns, note):
    fig, (ax, axb) = plt.subplots(
        1,
        2,
        figsize=(11.5, 4.8),
        dpi=150,
        gridspec_kw=dict(width_ratios=[1.25, 1.0], wspace=0.55),
    )
    for label, t in curves.items():
        st = GRID_STYLE.get(label, dict(color=FULL, lw=2.2, ls="-"))
        n = np.arange(1, len(t) + 1)
        name = "full" if label == "full" else f"discovery, {label} grid"
        ax.step(np.r_[0.0, t], np.r_[0, n], where="post", label=name, **st)
        ax.text(
            t[-1],
            20.4,
            f"{label.removesuffix(' grid')}\n{t[-1]:.0f} s",
            fontsize=7.5,
            color=TEXT,
            ha="center",
            va="bottom",
        )
    for label, (tb, color) in refs.items():
        ax.axvline(tb, color=color, lw=0.9, ls="-.", zorder=1, label=label)
    ax.text(
        0.97,
        0.55,
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
    ax.set_ylim(0, 25.5)
    ax.set_xlim(0, max(t[-1] for t in curves.values()) + 18)
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
        _bar_labels(axb, left, vals, "white" if color == FULL else "black")
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
            bbox=dict(fc="white", ec="none", pad=1.2, alpha=0.9)
            if color == "black"
            else None,
        )


def render_gif(out, walkable, polys, runs, titles, step_s=1.0, fps=10):
    t_end = max(runs[k]["traj"]["frame"].max() for k in titles) / FPS
    times = np.arange(0.0, t_end + step_s, step_s)
    fig, axes = plt.subplots(1, 2, figsize=(6.6, 3.7), dpi=100)
    fig.subplots_adjust(left=0.01, right=0.99, top=0.87, bottom=0.17, wspace=0.04)
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
    handles = [
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
    ]
    handles.append(
        Line2D(
            [0],
            [0],
            ls="none",
            marker="o",
            mfc="#bdbdbd",
            mec="black",
            mew=1.6,
            label="patrol: thick ring",
        )
    )
    fig.legend(
        handles=handles,
        title="heading for",
        title_fontsize=7,
        loc="lower center",
        ncol=7,
        fontsize=7,
        handletextpad=0.1,
        columnspacing=0.7,
        **LEGEND,
    )
    by_frame = {
        k: {
            f: g
            for f, g in runs[k]["traj"]
            .assign(d=runs[k]["dest"], w=runs[k]["why"])
            .groupby("frame")
        }
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
                    dot.set_linewidths([1.6 if w == "wander" else 0.3 for w in g["w"]])
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
    site/static/images/verification/familiarity_door.png
    site/static/images/verification/familiarity_egress.png
    site/static/images/verification/familiarity.gif
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--data",
        type=Path,
        required=True,
        help="directory with full/ and discovery_cell<c>/ (run.sqlite, routes.csv, "
        "cognitive_map.csv)",
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
    alt = predict_discovery(geo, nodes, signs, edges, rule=legible_half_disc)
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
    print(
        "cap after the view angle (half-disc): same known set and tour:",
        alt[0] == known0 and alt[1] == tour,
    )
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
    traj, routes, maps = load_run(args.data / "full")
    full, n_switch, fmap = check_full(geo, polys, traj, routes, maps, edges, v0)
    dest, why = destinations(traj, routes, full=True)
    runs["full"] = dict(traj=traj, dest=dest, why=why)
    never = sum(not (e & {"CP0", "CP1", "CP2"}) for e in full["entered"])
    via3 = sum("CP3" in e for e in full["entered"])
    t_sorted = np.sort(full.t_out.to_numpy())
    t_door = np.sort(door_crossings(traj))
    flow = (len(t_door) - 1) / (t_door[-1] - t_door[0])
    print(
        f"full: {via3}/20 pass CP3, {never}/20 never enter CP0-CP2, "
        f"{n_switch} route changes; whole map at t = 0 for "
        f"{fmap['whole_map_at_t0']}/20, later map changes {fmap['map_changes']}; "
        f"walked/geodesic {(full.walked / full.geodesic).min():.3f}-"
        f"{(full.walked / full.geodesic).max():.3f}; first out "
        f"{full.t_out.min():.1f} s; min over agents of t_out - L/v0 "
        f"{(full.t_out - full.t_min).min():+.2f} s; max speed "
        f"{full.v_max.max():.2f} m/s; last out {full.t_out.max():.1f} s; "
        f"door (y = 13.05 m) crossed by {len(t_door)} agents from "
        f"{t_door[0]:.1f} to {t_door[-1]:.1f} s: {flow:.2f} 1/s = "
        f"{flow / 1.2:.2f} 1/(s m) of the 1.2 m door"
    )
    curves = {"full": t_sorted}
    patterns = {"full": {"direct: S-CP3-exit": 20}}
    calm_last, last_out, table = [], {}, []
    cells = sorted(
        float(p.name.removeprefix("discovery_cell"))
        for p in args.data.glob("discovery_cell*")
    )
    for cell in reversed(cells):
        traj, routes, maps = load_run(args.data / f"discovery_cell{cell:g}")
        t_out = np.sort(traj.groupby("id")["frame"].max().to_numpy() / FPS)
        last_out[cell] = t_out[-1]
        wanderers = set(routes.loc[routes["reason"] == "wander", "agent_id"])
        res = {}
        for name, tol in (("0", 0.0), ("T", grid_tol(cell))):
            res[name] = check_learning(geo, signs, edges, known0, traj, maps, tol)
            res[name] |= check_decisions(geo, signs, traj, routes, tol)
        r = res["T"]
        skipped = {a for a, _ in r["skipped"]}
        pat = {}
        for a in routes["agent_id"].unique():
            name = route_class(node_sequence(routes, a), a in wanderers, a in skipped)
            pat[name] = pat.get(name, 0) + 1
        label = f"{cell:g} m"
        curves[label] = t_out
        row = f"discovery {cell:g} m"
        if cells_across(cell) == 0:
            row += "\n(sees through the walls)"
        patterns[row] = pat
        last = traj.groupby("id")["frame"].max() / FPS
        calm = last.drop(index=list(wanderers), errors="ignore")
        calm_last.append(calm.max())
        at_cp3 = [p[1] for _, _, p in r["patrols"] if math.dist(p, nodes["CP3"]) < 1.5]
        print(
            f"discovery {label} (T = {grid_tol(cell):.3f} m, cells across the "
            f"partition {cells_across(cell)}): last out {t_out[-1]:.1f} s, first out "
            f"{t_out[0]:.1f} s; never turned back: last out {calm.max():.1f} s; "
            f"turned back {len(wanderers)}; routes {pat}"
        )
        for name in ("0", "T"):
            q = res[name]
            print(
                f"  tol {name}: C2 wrong map at t=0 {len(q['wrong_start'])}; "
                f"C3 learnt {q['learnt']}, not a neighbour "
                f"{len(q['not_neighbour'])}, sign hidden {q['hidden']}; "
                f"C4 tour {q['tour']}; C5 patrols {len(q['patrols'])}, "
                f"exit certainly legible at {q['patrol_seen']}"
            )
        print(
            f"  patrols at CP3: y = {min(at_cp3):.2f}-{max(at_cp3):.2f} m"
            if at_cp3
            else "  no patrols at CP3"
        )
        print(f"  CP2 skipped at CP1: {r['skipped']}")
        first = routes.sort_values("time_s").groupby("agent_id")["target"].first()
        print(f"  first targets {first.value_counts().to_dict()}")
        table.append((cell, r))
        if cell == MAIN_CELL:
            dest, why = destinations(traj, routes, full=False)
            runs["discovery"] = dict(traj=traj, dest=dest, why=why)
            main_patrols = r["patrols"]
            n_turned = len(wanderers)
            n_west = sum(
                bool({"CP1", "CP2"} & set(node_sequence(routes, a)))
                for a in routes["agent_id"].unique()
            )
    fine = sorted(last_out)[:2]
    print(
        "C6 grid convergence: last out "
        + ", ".join(f"{c:g} m {last_out[c]:.1f} s" for c in sorted(last_out))
        + f"; |{fine[0]:g} m - {fine[1]:g} m| = "
        f"{abs(last_out[fine[0]] - last_out[fine[1]]):.1f} s (tolerance 5 s)"
    )
    calm_range = f"{min(calm_last):.0f}–{max(calm_last):.0f} s"

    # --- Plot ---
    plot_setup(OUT, walkable, polys, nodes, signs, edges, known0, full_path, tour_xy)
    titles = {
        "full": "full: knows the plan",
        "discovery": f"discovery: learns it ({MAIN_CELL:g} m grid)",
    }
    plot_paths(OUT, walkable, polys, runs, titles, n_turned, n_west)
    plot_door(OUT, walkable, polys, geo, signs, main_patrols, grid_tol(MAIN_CELL))
    refs = {
        f"L/v0, full: {l_full:.1f} m / {v0:g} m/s = {l_full / v0:.0f} s": (
            l_full / v0,
            FULL,
        ),
        f"L/v0, tour: {l_tour:.1f} m / {v0:g} m/s = {l_tour / v0:.0f} s": (
            l_tour / v0,
            DISC,
        ),
    }
    note = "agents that never turned back\nare out by " + calm_range + "\non every grid"
    plot_egress(OUT, curves, refs, patterns, note)
    frames = render_gif(OUT, walkable, polys, runs, titles)
    size = (OUT / "familiarity.gif").stat().st_size / 1e6
    print(f"familiarity.gif: {frames} frames, {size:.2f} MB")


if __name__ == "__main__":
    main()
