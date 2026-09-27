"""Full versus discovery familiarity: walked paths on the same deck.

Runs ``assets/familiarity_test_full`` and ``assets/familiarity_test_discovery``,
two configs that differ only in the spawn distribution's ``familiarity``:
same 20 x 18 m floor, same four signed checkpoints, same exit, 20 agents,
seed 420. Sight is clear air (fdsvismap ray casting on the walkable
polygon) at a 0.05 m grid, two cells across the deck's 0.1 m walls, so no
partition leaks sight. Each panel draws the stage graph as the discovery
tier knows it at t = 0 (full knows all of it) and the 20 walked paths.

Run from the repository root::

    uv run python scripts/figures/full_vs_discovery_paths.py

Writes ``site/static/images/wayfinding/full_vs_discovery_paths.png``.
"""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns
from matplotlib.lines import Line2D
from matplotlib.patches import Polygon as MplPolygon
from shapely.geometry import Polygon

from pyfds_evac import RerouteConfig, VisibilityModel, load_scenario, run_scenario
from pyfds_evac.core.visibility import extract_sign_descriptors

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "site" / "static" / "images" / "wayfinding"

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
DISCOVERY = "#fc8d59"  # discovery tier, as in scripts/run_familiarity_comparison.py

# the tier is encoded by panel title, colour and line style
TIERS = {
    "full": dict(color=CHOSEN, ls="-"),
    "discovery": dict(color=DISCOVERY, ls=(0, (3, 1.5))),
}
SEED = 420
CELL_M = 0.05


def simulate(tier):
    """Run one tier; return paths, map at t = 0 and egress numbers."""
    scenario = load_scenario(str(ROOT / "assets" / f"familiarity_test_{tier}"))
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
    traj = result.trajectory_dataframe().sort_values(["id", "frame"])
    paths = [g[["x", "y"]].to_numpy() for _, g in traj.groupby("id")]
    lengths = [np.linalg.norm(np.diff(p, axis=0), axis=1).sum() for p in paths]
    history = result.cognitive_map_history or []
    out = dict(
        scenario=scenario,
        paths=paths,
        known_t0=set(history[0]["known_nodes"]) if history else set(),
        evac_time=result.evacuation_time,
        evacuated=result.agents_evacuated,
        total=result.total_agents,
        length=float(np.median(lengths)),
    )
    result.cleanup()
    return out


def stage_nodes(raw):
    """(id, kind, centroid) for the exit, the checkpoints and the spawn."""
    kinds = {"exits": "exit", "checkpoints": "checkpoint", "distributions": "spawn"}
    nodes = []
    for section, kind in kinds.items():
        for node_id, data in raw.get(section, {}).items():
            c = Polygon(data["coordinates"]).centroid
            nodes.append((node_id, kind, (c.x, c.y)))
    return nodes


def draw_floor(ax, walkable):
    ax.add_patch(
        MplPolygon(np.asarray(walkable.exterior.coords), fc=FLOOR, ec=WALL, lw=1.6)
    )
    for ring in walkable.interiors:
        ax.add_patch(MplPolygon(np.asarray(ring.coords), fc=WALL, ec=WALL, lw=1.0))


def draw_nodes(ax, nodes, known):
    markers = {"exit": "s", "checkpoint": "o", "spawn": "^"}
    for node_id, kind, xy in nodes:
        is_known = node_id in known
        face = KNOWN if is_known else "white"
        if is_known and kind == "exit":
            face = EXIT
        ax.scatter(
            *xy,
            marker=markers[kind],
            s=150 if kind == "exit" else 90,
            fc=face,
            ec=KNOWN if is_known else UNKNOWN,
            lw=1.6,
            linestyle="-" if is_known else "--",
            zorder=5,
        )


def draw_panel(ax, label, tier, run, known):
    style = TIERS[tier]
    draw_floor(ax, run["scenario"].walkable_polygon)
    for p in run["paths"]:
        # every second 10 fps frame: the same line at half the file size
        ax.plot(
            p[::2, 0],
            p[::2, 1],
            color=style["color"],
            ls=style["ls"],
            lw=0.9,
            alpha=0.7,
            zorder=3,
        )
    draw_nodes(ax, stage_nodes(run["scenario"].raw), known)
    ax.set_aspect("equal")
    # a floor plan has no data axes: grid, ticks and frame add nothing
    ax.axis("off")
    ax.set_title(
        r"$\bf{(" + label + r")}$" + f"  {tier}",
        loc="left",
        fontsize=11,
        color=style["color"],
        pad=18,
    )
    ax.text(
        0.0,
        1.01,
        f"last agent out at {run['evac_time']:.1f} s, "
        f"{run['evacuated']}/{run['total']} evacuated, "
        f"median path {run['length']:.0f} m",
        transform=ax.transAxes,
        fontsize=8.5,
        color=TEXT,
        ha="left",
        va="bottom",
    )


def main():
    """Run both tiers and draw their walked paths side by side.

    Saves
    -----
    site/static/images/wayfinding/full_vs_discovery_paths.png
    """
    runs = {tier: simulate(tier) for tier in TIERS}
    disc_known = runs["discovery"]["known_t0"]
    all_nodes = {n for n, _, _ in stage_nodes(runs["full"]["scenario"].raw)}

    # --- Style Setup ---
    sns.set_theme(font_scale=1.0, style="whitegrid", font="DejaVu Sans")
    fig, axes = plt.subplots(
        1, 2, figsize=(11, 5.4), dpi=150, gridspec_kw=dict(wspace=0.06)
    )

    # --- Plot ---
    draw_panel(axes[0], "a", "full", runs["full"], all_nodes)
    draw_panel(axes[1], "b", "discovery", runs["discovery"], disc_known)

    handles = [
        Line2D([0], [0], color=CHOSEN, lw=1.6, label="full: walked path"),
        Line2D(
            [0],
            [0],
            color=DISCOVERY,
            lw=1.6,
            ls=(0, (3, 1.5)),
            label="discovery: walked path",
        ),
        Line2D(
            [0],
            [0],
            marker="o",
            color="w",
            mfc=KNOWN,
            mec=KNOWN,
            ms=8,
            label="known at t = 0",
        ),
        Line2D(
            [0],
            [0],
            marker="o",
            color="w",
            mfc="white",
            mec=UNKNOWN,
            mew=1.6,
            ms=8,
            label="unknown at t = 0",
        ),
        Line2D(
            [0], [0], marker="s", color="w", mfc=EXIT, mec=KNOWN, ms=9, label="exit"
        ),
        Line2D(
            [0], [0], marker="^", color="w", mfc=KNOWN, mec=KNOWN, ms=9, label="spawn"
        ),
    ]
    fig.legend(
        handles=handles,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.12),
        ncol=6,
        fontsize=8.5,
        frameon=True,
        facecolor="white",
        framealpha=0.8,
        edgecolor="lightgrey",
        labelcolor="dimgrey",
    )
    sns.despine(fig=fig, left=True, bottom=True)

    full, disc = runs["full"], runs["discovery"]
    fig.text(
        0.5,
        0.03,
        f"Same deck, seed and exit; only the initial map differs. Discovery "
        f"starts knowing {len(disc_known)} of {len(all_nodes)} stages and needs "
        f"{disc['evac_time'] - full['evac_time']:.0f} s more to empty the floor "
        f"({disc['evac_time'] / full['evac_time']:.1f}x).",
        ha="center",
        va="top",
        fontsize=9,
        color=TEXT,
        style="italic",
    )

    # --- Save ---
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / "full_vs_discovery_paths.png", dpi=150, bbox_inches="tight")


if __name__ == "__main__":
    main()
