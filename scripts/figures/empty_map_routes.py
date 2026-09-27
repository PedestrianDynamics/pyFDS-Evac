"""An empty map: one discovery agent that can read no sign, run and drawn.

A 30 x 30 m floor: a hall at the bottom, three rooms above it, a corridor on
top with the only exit at its west end. One agent, familiarity 0, spawns in
the hall. Sight is clear air (fdsvismap ray casting on the walkable polygon),
so the exit sign is hidden by walls alone, and the script asserts that the
agent's map at t = 0 holds nothing but its spawn.

Three candidate routes, one per door, are drawn in grey; the solid line is
what ``run_scenario`` actually walks. The scene is built here in code, not
read from ``assets/``: the talk's version was hand-drawn over a video frame
and has no deck to re-run.

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
from matplotlib.lines import Line2D
from shapely.geometry import box
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
Y_LOW, Y_HIGH, CORRIDOR_Y = 12.5, 25.0, 27.5
# door gaps on both horizontal walls; the middle column is open end to end
DOORS = {"C": (3.5, 6.0), "B": (7.5, 12.5), "A": (20.0, 22.5)}
SIDE_DOOR = (17.5, 20.0)  # in both walls of the middle column
SPAWN = (24.5, 6.5, 26.5, 8.5)
EXIT_BOX = (0.2, 25.6, 1.0, 29.4)
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
        "exits": {"exit": {"type": "polygon", "coordinates": rect(*EXIT_BOX)}},
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


def simulate(walls):
    """Run the deck; return trajectory, map history and exit time."""
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
        history = list(result.cognitive_map_history or [])
        out = dict(
            xy=traj[["x", "y"]].to_numpy(),
            t=traj["frame"].to_numpy() / result.frame_rate,
            history=history,
            evac_time=result.evacuation_time,
            evacuated=result.agents_evacuated,
        )
        result.cleanup()
        return out
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def door_taken(xy):
    """Letter of the door the walk crosses the hall wall through."""
    i = int(np.argmax(xy[:, 1] > Y_LOW))
    x = xy[i, 0]
    return next((k for k, (a, b) in DOORS.items() if a <= x <= b), "?")


def candidate_routes(start):
    """Spawn -> door -> corridor -> exit, one polyline per door."""
    ex = (EXIT_BOX[0] + EXIT_BOX[2]) / 2
    routes = {}
    for name, (a, b) in DOORS.items():
        xd = (a + b) / 2
        routes[name] = [start, (xd, Y_LOW), (xd, CORRIDOR_Y), (ex, CORRIDOR_Y)]
    return routes


def draw_floor(ax, walls):
    ax.add_patch(plt.Rectangle((0, 0), SIZE, SIZE, fc=FLOOR, ec=WALL, lw=1.6, zorder=0))
    for w in walls:
        x0, y0, x1, y1 = w.bounds
        ax.add_patch(plt.Rectangle((x0, y0), x1 - x0, y1 - y0, fc=WALL, lw=0))


def draw_candidates(ax, routes):
    for k, (name, pts) in enumerate(routes.items()):
        # small vertical offsets keep the three corridor legs apart
        dy = 0.7 * (k - 1)
        xs, ys = zip(*pts)
        ys = [ys[0], ys[1], ys[2] + dy, ys[3] + dy]
        ax.plot(xs, ys, color=OPTION, lw=1.6, ls=(0, (4, 3)), zorder=2)
        ax.text(
            xs[1],
            Y_LOW - 1.3,
            name,
            fontsize=9,
            fontweight="bold",
            color="white",
            ha="center",
            va="center",
            zorder=6,
            bbox=dict(boxstyle="circle,pad=0.25", fc=OPTION, ec="none"),
        )


def draw_nodes(ax, known_at_t0):
    """Spawn node and exit box, filled when in the map at t = 0."""
    sx = (SPAWN[0] + SPAWN[2]) / 2
    spawn_known = "spawn" in known_at_t0
    exit_known = "exit" in known_at_t0
    ax.scatter(
        sx,
        SPAWN[1] - 0.9,
        marker="^",
        s=130,
        fc=KNOWN if spawn_known else "white",
        ec=KNOWN if spawn_known else UNKNOWN,
        lw=1.6,
        zorder=5,
    )
    x0, y0, x1, y1 = EXIT_BOX
    ax.add_patch(
        plt.Rectangle(
            (x0, y0),
            x1 - x0,
            y1 - y0,
            fc=EXIT if exit_known else "white",
            ec=KNOWN if exit_known else UNKNOWN,
            lw=1.8,
            ls="-" if exit_known else "--",
            zorder=5,
        )
    )
    ax.text(
        x1 + 0.5,
        SIZE - 0.35,
        "exit, not in the map",
        fontsize=8.5,
        color=TEXT,
        ha="left",
        va="top",
        zorder=6,
    )


def main():
    """Run the empty-map scene and draw it.

    Saves
    -----
    site/static/images/wayfinding/empty_map_routes.png
    """
    walls = build_walls()
    run = simulate(walls)
    known_t0 = set(run["history"][0]["known_nodes"])
    if known_t0 != {"spawn"}:
        raise SystemExit(f"map at t = 0 is {sorted(known_t0)}, not the spawn alone")
    xy, t = run["xy"], run["t"]
    learned = next(
        (h["time_s"] for h in run["history"] if "exit" in h["known_nodes"]), None
    )
    walked = float(np.linalg.norm(np.diff(xy, axis=0), axis=1).sum())
    door = door_taken(xy)

    # --- Style Setup ---
    sns.set_theme(font_scale=1.0, style="whitegrid", font="DejaVu Sans")
    fig, ax = plt.subplots(figsize=(6.4, 7.0), dpi=150)

    # --- Plot ---
    draw_floor(ax, walls)
    draw_candidates(ax, candidate_routes(tuple(xy[0])))
    ax.plot(xy[:, 0], xy[:, 1], color=CHOSEN, lw=2.6, zorder=4)
    if learned is not None:
        i = int(np.searchsorted(t, learned))
        ax.scatter(
            *xy[i], marker="o", s=70, fc=LEGIBLE, ec=LEGIBLE_EDGE, lw=1.6, zorder=7
        )
        ax.annotate(
            f"exit enters the map, t = {learned:.0f} s",
            xy=xy[i],
            xytext=(14.0, 22.3),
            fontsize=8.5,
            color=TEXT,
            arrowprops=dict(arrowstyle="-", color=TEXT, lw=0.8),
            zorder=8,
        )
    draw_nodes(ax, known_t0)
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
    ax.set_ylim(-0.5, SIZE + 0.5)
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
        "familiarity 0, clear air, no sign legible from the spawn",
        transform=ax.transAxes,
        fontsize=9,
        color=TEXT,
        ha="left",
        va="bottom",
    )

    handles = [
        Line2D([0], [0], color=OPTION, lw=1.6, ls=(0, (4, 3)), label="candidate"),
        Line2D([0], [0], color=CHOSEN, lw=2.6, label="walked"),
        Line2D(
            [0],
            [0],
            marker="^",
            color="w",
            mfc=KNOWN,
            mec=KNOWN,
            ms=9,
            label="known node",
        ),
        Line2D(
            [0],
            [0],
            marker="s",
            color="w",
            mfc="white",
            mec=UNKNOWN,
            mew=1.6,
            ms=9,
            label="unknown node",
        ),
        Line2D(
            [0],
            [0],
            marker="o",
            color="w",
            mfc=LEGIBLE,
            mec=LEGIBLE_EDGE,
            mew=1.6,
            ms=8,
            label="sign read",
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

    outcome = (
        f"walks {walked:.0f} m through door {door} and exits at "
        f"{run['evac_time']:.0f} s"
        if run["evacuated"]
        else f"walks {walked:.0f} m and does not exit in {t[-1]:.0f} s"
    )
    ax.text(
        0.5,
        -0.13,
        f"The map at t = 0 holds only the spawn,\nyet the agent {outcome}.",
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
