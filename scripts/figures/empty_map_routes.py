"""An empty map: one discovery agent that never reads a sign, run and drawn.

A 30 x 30 m floor: a hall at the bottom, three rooms above it, a corridor on
top. Two exits: one in the hall's south wall, whose sign faces out of the
building, and one at the corridor's west end, whose sign faces down the
corridor, behind the rooms' walls. One agent, familiarity 0, spawns in the
east of the hall. Sight is clear air (fdsvismap ray casting on the walkable
polygon), and the shaded cells are those from which the model reads a sign.

The script asserts what the figure claims (issue #91): the agent's map holds
the spawn and nothing else for the whole run, it never re-decides its route,
no exit sign is legible from any point of its walk, and it still leaves by
the exit geometrically nearest its start. The scene is built here in code,
not read from ``assets/``: the talk's version was hand-drawn over a video
frame and has no deck to re-run.

Run from the repository root::

    uv run python scripts/figures/empty_map_routes.py

Writes ``site/static/images/wayfinding/empty_map_routes.png``.
"""

import json
import shutil
import tempfile
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns
from matplotlib.colors import ListedColormap
from matplotlib.lines import Line2D
from matplotlib.patches import FancyArrowPatch, Patch
from shapely.geometry import Point, box
from shapely.ops import unary_union

from pyfds_evac import RerouteConfig, VisibilityModel, load_scenario, run_scenario
from pyfds_evac.core.visibility import extract_sign_descriptors

OUT = Path(__file__).resolve().parents[2] / "site" / "static" / "images" / "wayfinding"

# Shared palette of the concept figures: one meaning, one colour, one style.
CHOSEN = "#4575b4"  # chosen / walked route: solid line
REFUSED = "#d73027"  # refused route: dashed line, hatched bar
OPTION = "#969696"  # candidate neither chosen nor refused
KNOWN = "#324465"  # stage in the map: filled marker
UNKNOWN = "#bdbdbd"  # stage not in the map: hollow marker, dashed edge
LEGIBLE = "#fee090"  # legible sign: yellow fill with a gold outline
LEGIBLE_EDGE = "#c89b00"
EXIT = "#33a02c"  # exit door
AGENT = "#1a1a1a"  # agent: star marker
WALL = "dimgrey"
FLOOR = "#f7f7f7"
TEXT = "dimgrey"

SIZE = 30.0
WALL_T = 0.4  # two cells at CELL_M, so no wall leaks sight
CELL_M = 0.1
SHADE_M = 0.2  # sampling of the drawn legible region
Y_LOW, Y_HIGH = 12.5, 25.0
# door gaps on both horizontal walls; the middle column is open end to end
DOORS = {"C": (3.5, 6.0), "B": (7.5, 12.5), "A": (20.0, 22.5)}
SIDE_DOOR = (17.5, 20.0)  # in both walls of the middle column
SPAWN = (24.5, 6.5, 26.5, 8.5)
# exit polygon, sign position and bearing (degrees clockwise from north; the
# sign is read from the side it faces)
EXITS = {
    "south": dict(box=(1.0, 0.2, 4.0, 1.0), sign=(2.5, 0.25), alpha=180),
    "west": dict(box=(0.2, 25.6, 1.0, 29.4), sign=(0.25, 27.5), alpha=90),
}
SEED = 1


def rect(x0, y0, x1, y1):
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]


def wall_runs(lo, hi, gaps):
    """Solid intervals of [lo, hi] once the gaps are cut out."""
    edges = [lo] + [v for gap in sorted(gaps) for v in gap] + [hi]
    return list(zip(edges[::2], edges[1::2]))


def build_walls():
    """Wall rectangles: two horizontal walls and the middle column's sides."""
    walls = []
    for y in (Y_LOW, Y_HIGH):
        runs = wall_runs(0.0, SIZE, DOORS.values())
        walls += [box(a, y - WALL_T / 2, b, y + WALL_T / 2) for a, b in runs]
    for x in DOORS["B"]:
        runs = wall_runs(Y_LOW, Y_HIGH, [SIDE_DOOR])
        walls += [box(x - WALL_T / 2, a, x + WALL_T / 2, b) for a, b in runs]
    return walls


def write_deck(folder, walls):
    """A scenario folder: walkable WKT and a one-agent discovery config."""
    walkable = box(0, 0, SIZE, SIZE).difference(unary_union(walls))
    params = {
        "number": 1,
        "radius": 0.2,
        "distribution_mode": "by_number",
        "familiarity": 0.0,
    }
    exits = {
        name: {
            "type": "polygon",
            "coordinates": rect(*e["box"]),
            "sign": {"x": e["sign"][0], "y": e["sign"][1], "alpha": e["alpha"], "c": 3},
        }
        for name, e in EXITS.items()
    }
    cfg = {
        "project_version": "2.0",
        "config": {
            "simulation_settings": {
                "simulationParams": {
                    "max_simulation_time": 90,
                    "dt": 0.01,
                    "model_type": "CollisionFreeSpeedModel",
                },
                "baseSeed": SEED,
            }
        },
        "exits": exits,
        "distributions": {
            "spawn": {
                "type": "polygon",
                "coordinates": rect(*SPAWN),
                "parameters": params,
            }
        },
        "checkpoints": {},
        "journeys": [],
        "transitions": [],
    }
    (folder / "config.json").write_text(json.dumps(cfg))
    (folder / "geometry.wkt").write_text(walkable.wkt)


def legible_cells(vis, node_id):
    """Boolean grid (rows y, cols x) of the cells that read *node_id*'s sign."""
    c = np.arange(SHADE_M / 2, SIZE, SHADE_M)
    return np.array([[vis.node_is_visible(0.0, x, y, node_id) for x in c] for y in c])


def simulate(walls):
    """Run the deck; return trajectory, map history, switches and sight."""
    folder = Path(tempfile.mkdtemp(prefix="empty_map_"))
    try:
        write_deck(folder, walls)
        scenario = load_scenario(str(folder))
        signs = extract_sign_descriptors(scenario.raw)
        vis = VisibilityModel.clear_air(
            scenario.walkable_polygon, signs, cell_size_m=CELL_M
        )
        result = run_scenario(
            scenario,
            seed=SEED,
            reroute_config=RerouteConfig(reevaluation_interval_s=1.0),
            vis_model=vis,
            collect_cognitive_map_history=True,
        )
        traj = result.trajectory_dataframe().sort_values("frame")
        xy = traj[["x", "y"]].to_numpy()
        out = dict(
            xy=xy,
            t=traj["frame"].to_numpy() / result.frame_rate,
            history=list(result.cognitive_map_history or []),
            switches=list(result.route_history or []),
            evac_time=result.evacuation_time,
            evacuated=result.agents_evacuated,
            # every sampled position of the walk, asked of the same model
            seen=sorted(
                {
                    name
                    for x, y in xy
                    for name in EXITS
                    if vis.node_is_visible(0.0, x, y, name)
                }
            ),
            legible={name: legible_cells(vis, name) for name in EXITS},
        )
        result.cleanup()
        return out
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def check_claims(run):
    """Fail loudly if the run no longer shows an empty map (#91)."""
    maps = {tuple(h["known_nodes"]) for h in run["history"]}
    if maps != {("spawn",)}:
        raise SystemExit(f"the map grew: {sorted(maps)}")
    if run["switches"]:
        raise SystemExit(f"the agent re-decided: {run['switches']}")
    if run["seen"]:
        raise SystemExit(f"signs legible from the walk: {run['seen']}")
    if not run["evacuated"]:
        raise SystemExit("the agent did not leave")
    start, end = Point(*run["xy"][0]), Point(*run["xy"][-1])
    polys = {name: box(*e["box"]) for name, e in EXITS.items()}
    dist = {name: p.distance(start) for name, p in polys.items()}
    taken = min(polys, key=lambda n: polys[n].distance(end))
    nearest = min(dist, key=dist.get)
    if taken != nearest:
        raise SystemExit(f"left by {taken}, but {nearest} is nearest")
    return taken, dist


def draw_floor(ax, walls):
    ax.add_patch(plt.Rectangle((0, 0), SIZE, SIZE, fc=FLOOR, ec="none", zorder=0))
    for w in walls:
        x0, y0, x1, y1 = w.bounds
        ax.add_patch(plt.Rectangle((x0, y0), x1 - x0, y1 - y0, fc=WALL, lw=0, zorder=3))
    ax.add_patch(
        plt.Rectangle((0, 0), SIZE, SIZE, fc="none", ec=WALL, lw=1.6, zorder=3)
    )


def draw_legible(ax, masks):
    """Cells from which any exit sign is legible: yellow, gold outline."""
    union = np.logical_or.reduce(list(masks.values()))
    ax.imshow(
        np.where(union, 1.0, np.nan),
        origin="lower",
        extent=(0, SIZE, 0, SIZE),
        cmap=ListedColormap([LEGIBLE]),
        alpha=0.8,
        interpolation="nearest",
        zorder=1,
    )
    c = np.arange(SHADE_M / 2, SIZE, SHADE_M)
    ax.contour(
        c, c, union.astype(float), levels=[0.5], colors=LEGIBLE_EDGE, linewidths=0.8
    )


def draw_exits(ax, taken, dist):
    """Exits: hollow and dashed (not in the map), sign plate and its facing."""
    for name, e in EXITS.items():
        x0, y0, x1, y1 = e["box"]
        ax.add_patch(
            plt.Rectangle(
                (x0, y0),
                x1 - x0,
                y1 - y0,
                fc="white",
                ec=CHOSEN if name == taken else UNKNOWN,
                lw=1.8,
                ls="--",
                zorder=5,
            )
        )
        sx, sy = e["sign"]
        a = np.deg2rad(e["alpha"])
        ax.add_patch(
            FancyArrowPatch(
                (sx, sy),
                (sx + 2.2 * np.sin(a), sy + 2.2 * np.cos(a)),
                arrowstyle="-|>",
                mutation_scale=12,
                color=OPTION,
                lw=1.8,
                zorder=6,
                clip_on=False,
            )
        )
    label = dict(fontsize=8.5, color=TEXT, zorder=7)
    ax.text(
        4.4,
        -0.3,
        f"exit south, {dist['south']:.0f} m from the start\n"
        "sign faces out of the building",
        ha="left",
        va="top",
        **label,
    )
    ax.text(
        1.6,
        29.2,
        f"exit west, {dist['west']:.0f} m from the start\n"
        "sign faces along the corridor",
        ha="left",
        va="top",
        **label,
    )


def main():
    """Run the empty-map scene, check its claims and draw it.

    Saves
    -----
    site/static/images/wayfinding/empty_map_routes.png
    """
    walls = build_walls()
    run = simulate(walls)
    taken, dist = check_claims(run)
    xy, t = run["xy"], run["t"]
    steps = np.linalg.norm(np.diff(xy, axis=0), axis=1)
    walked = float(steps.sum())
    # pre-movement: the agent stands still until its first step
    t_move = float(t[int(np.argmax(steps > 1e-3))])
    print(
        f"map = spawn only for {t[-1]:.1f} s, {len(run['switches'])} switches, "
        f"starts at {t_move:.1f} s, left by {taken} at {run['evac_time']:.1f} s "
        f"after {walked:.1f} m; "
        f"start to exit: " + ", ".join(f"{k} {v:.1f} m" for k, v in dist.items())
    )

    # --- Style Setup ---
    sns.set_theme(font_scale=1.0, style="whitegrid", font="DejaVu Sans")
    fig, ax = plt.subplots(figsize=(6.4, 7.0), dpi=150)

    # --- Plot ---
    draw_legible(ax, run["legible"])
    draw_floor(ax, walls)
    draw_exits(ax, taken, dist)
    ax.plot(xy[:, 0], xy[:, 1], color=CHOSEN, lw=2.6, zorder=4)
    sx = (SPAWN[0] + SPAWN[2]) / 2
    ax.scatter(sx, SPAWN[1] - 0.9, marker="^", s=130, fc=KNOWN, ec=KNOWN, zorder=5)
    ax.scatter(*xy[0], marker="*", s=260, fc=AGENT, ec="white", lw=0.8, zorder=8)
    ax.text(
        SIZE - 0.6,
        SPAWN[1] - 2.2,
        "spawn, the only node in the map",
        fontsize=8.5,
        color=TEXT,
        fontweight="bold",
        ha="right",
        va="top",
        zorder=9,
    )

    ax.set_xlim(-0.5, SIZE + 0.5)
    ax.set_ylim(-3.0, SIZE + 0.5)
    ax.set_aspect("equal")
    # a floor plan has no data axes: grid, ticks and frame add nothing
    ax.axis("off")
    ax.text(
        0.0,
        1.075,
        "An empty map",
        transform=ax.transAxes,
        fontsize=12,
        fontweight="bold",
        ha="left",
        va="bottom",
    )
    ax.text(
        0.0,
        1.02,
        "familiarity 0, clear air, no sign legible anywhere on its path",
        transform=ax.transAxes,
        fontsize=9,
        color=TEXT,
        ha="left",
        va="bottom",
    )

    handles = [
        Line2D([0], [0], color=CHOSEN, lw=2.6, label="walked"),
        Patch(fc=LEGIBLE, ec=LEGIBLE_EDGE, alpha=0.8, label="a sign is legible"),
        Line2D(
            [0],
            [0],
            marker="s",
            color="w",
            mfc="white",
            mec=UNKNOWN,
            mew=1.6,
            ms=9,
            label="exit, not in the map",
        ),
        Line2D(
            [0],
            [0],
            color=OPTION,
            lw=1.8,
            marker=">",
            ms=6,
            markevery=[1],
            label="way a sign faces",
        ),
        Line2D(
            [0],
            [0],
            marker="^",
            color="w",
            mfc=KNOWN,
            mec=KNOWN,
            ms=9,
            label="node in the map",
        ),
        Line2D([0], [0], marker="*", color="w", mfc=AGENT, ms=13, label="agent"),
    ]
    ax.legend(
        handles=handles,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.005),
        ncol=3,
        fontsize=8,
        handlelength=1.8,
        columnspacing=1.0,
        frameon=True,
        facecolor="white",
        framealpha=0.8,
        edgecolor="lightgrey",
        labelcolor="dimgrey",
    )
    sns.despine(fig=fig, left=True, bottom=True)

    ax.text(
        0.5,
        -0.13,
        f"The map holds only the spawn for all {t[-1]:.0f} s and the agent never "
        f"re-decides,\nyet from t = {t_move:.0f} s it walks {walked:.0f} m to "
        f"the nearest exit ({taken}) and is out at {run['evac_time']:.0f} s.",
        transform=ax.transAxes,
        fontsize=8.5,
        color=TEXT,
        style="italic",
        ha="center",
        va="top",
    )

    # --- Save ---
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / "empty_map_routes.png", dpi=150, bbox_inches="tight")


if __name__ == "__main__":
    main()
