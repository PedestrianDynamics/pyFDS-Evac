"""Sign-bearing experiment (assets/exit_visibility_alpha), run and drawn.

A 4 x 30 m corridor, 40 discovery agents spawned at y in [8, 12], an exit at
each end. The two configs differ in one number: the bearing of the near
exit's sign, 0 (facing the agents) or 180 (facing away). Both configs are run
here in clear air (``VisibilityModel.clear_air`` at the 0.25 m cell of
``run.py``, seed 1904 from the configs); in clear air this reproduces the
asset README's FDS-vismap runs exactly. The legible region of the near sign is
the set of grid cells from which the same visibility model reads it, not a
drawn wedge. Exit counts, egress times and walked distances come from the runs.

Run from the repository root::

    uv run python scripts/figures/sign_bearing.py

Writes ``site/static/images/wayfinding/sign_bearing.png``.
"""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns
from matplotlib.colors import ListedColormap
from matplotlib.patches import FancyArrowPatch, Rectangle
from shapely.geometry import Point, Polygon

from pyfds_evac import RerouteConfig, VisibilityModel, load_scenario, run_scenario
from pyfds_evac.core.visibility import extract_sign_descriptors

ROOT = Path(__file__).resolve().parents[2]
ASSET = ROOT / "assets" / "exit_visibility_alpha"
IMAGES = ROOT / "site" / "static" / "images"
OUT = IMAGES / "wayfinding"

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

W, L = 4.0, 30.0
SPAWN = (8.0, 12.0)
CELL_M = 0.25  # run.py's --vis-cell-size default
SEED = 1904
EXIT_KEY = {"E_near": "near", "E_far": "far"}


def legible_cells(vis, node_id):
    """Boolean grid (rows y, cols x) of the cells that read *node_id*'s sign."""
    xs = np.arange(CELL_M / 2, W, CELL_M)
    ys = np.arange(CELL_M / 2, L, CELL_M)
    return np.array([[vis.node_is_visible(0.0, x, y, node_id) for x in xs] for y in ys])


def exit_taken(exits, xy):
    """Exit whose polygon is nearest an agent's last position."""
    p = Point(*xy)
    return min(exits, key=lambda e: exits[e].distance(p))


def simulate(config):
    """Run one config; return counts, times, paths and the legible cells."""
    scenario = load_scenario(str(ASSET / f"{config}.json"))
    signs = extract_sign_descriptors(scenario.raw)
    vis = VisibilityModel.clear_air(
        scenario.walkable_polygon, signs, cell_size_m=CELL_M
    )
    result = run_scenario(
        scenario,
        seed=SEED,
        reroute_config=RerouteConfig(reevaluation_interval_s=1.0),
        vis_model=vis,
    )
    traj = result.trajectory_dataframe().sort_values(["id", "frame"])
    exits = {k: Polygon(d["coordinates"]) for k, d in scenario.raw["exits"].items()}
    paths = [g[["x", "y"]].to_numpy() for _, g in traj.groupby("id")]
    counts = {k: 0 for k in EXIT_KEY.values()}
    for p in paths:
        counts[EXIT_KEY[exit_taken(exits, p[-1])]] += 1
    out = dict(
        counts=counts,
        chosen=max(counts, key=counts.get),
        total=result.total_agents,
        evac_time=result.evacuation_time,
        switches=len(result.route_history or []),
        start=np.array([p[0] for p in paths]),
        walked=float(
            np.median([np.linalg.norm(np.diff(p, axis=0), axis=1).sum() for p in paths])
        ),
        near_legible=legible_cells(vis, "E_near"),
        far_legible=legible_cells(vis, "E_far"),
        alpha=float(signs["E_near"]["alpha"]),
        signs={
            EXIT_KEY[e]: dict(
                y=float(signs[e]["y"]),
                alpha=float(signs[e]["alpha"]),
                from_spawn=vis.node_is_visible(0.0, W / 2, np.mean(SPAWN), e),
            )
            for e in EXIT_KEY
        },
    )
    result.cleanup()
    return out


def draw_legible(ax, mask):
    """Shade the cells that read the near sign, and outline the region."""
    ax.imshow(
        np.where(mask, 1.0, np.nan),
        origin="lower",
        extent=(0, W, 0, L),
        cmap=ListedColormap([LEGIBLE]),
        alpha=0.7,
        interpolation="nearest",
        zorder=1,
    )
    xs = np.arange(CELL_M / 2, W, CELL_M)
    ys = np.arange(CELL_M / 2, L, CELL_M)
    ax.contour(
        xs, ys, mask.astype(float), levels=[0.5], colors=LEGIBLE_EDGE, linewidths=1.0
    )


def legible_span(mask):
    """y range [m] of the rows with at least one legible cell."""
    ys = np.arange(CELL_M / 2, L, CELL_M)[mask.any(axis=1)]
    return ys.min() - CELL_M / 2, ys.max() + CELL_M / 2


def draw_run(ax, title, run):
    """One corridor: signs, the near sign's legible cells, spawn and walk."""
    chosen, alpha_near = run["chosen"], run["alpha"]
    ax.add_patch(Rectangle((0, 0), W, L, fc=FLOOR, ec="none", zorder=0))
    draw_legible(ax, run["near_legible"])
    ax.add_patch(Rectangle((0, 0), W, L, fc="none", ec=WALL, lw=1.6, zorder=2))
    # exits
    for y, name, key in ((L, "far exit", "far"), (0, "near exit", "near")):
        taken = key == chosen
        ax.add_patch(
            Rectangle(
                (W / 2 - 0.6, y - 0.25),
                1.2,
                0.5,
                fc=EXIT,
                ec=CHOSEN if taken else "none",
                lw=2.0,
                zorder=4,
            )
        )
        ax.text(
            W + 0.4,
            y,
            name + ("  ← taken" if taken else ""),
            fontsize=8.5,
            color=CHOSEN if taken else TEXT,
            va="center",
            ha="left",
            fontweight="bold",
        )
    # signs: a plate at the sign's configured y and a bold arrow showing the
    # direction it faces, i.e. the side from which it can be read. Gold when
    # the model reads it from the spawn centroid, grey otherwise. Drawn right
    # of the centre line so the walk arrow never crosses them.
    xs = W / 2 + 1.2
    for key in ("far", "near"):
        sign = run["signs"][key]
        sign_colour = LEGIBLE_EDGE if sign["from_spawn"] else OPTION
        ax.add_patch(
            Rectangle(
                (xs - 0.35, sign["y"] - 0.12),
                0.7,
                0.24,
                fc=sign_colour,
                ec="none",
                zorder=5,
            )
        )
        dy = 2.6 * np.cos(np.deg2rad(sign["alpha"]))
        ax.add_patch(
            FancyArrowPatch(
                (xs, sign["y"]),
                (xs, sign["y"] + dy),
                arrowstyle="-|>",
                mutation_scale=16,
                color=sign_colour,
                lw=2.2,
                zorder=5,
                clip_on=False,
            )
        )
    lo, hi = legible_span(run["near_legible"])
    ax.text(
        W + 0.4,
        1.9,
        f"sign α = {alpha_near:.0f}°, "
        + ("faces the agents" if alpha_near == 0 else "faces away")
        + f"\nlegible for y = {lo:.1f}–{hi:.1f} m",
        fontsize=8,
        color=TEXT,
        va="center",
        ha="left",
    )
    lo_far, hi_far = legible_span(run["far_legible"])
    ax.text(
        W + 0.4,
        L - 1.9,
        f"sign α = 180°, faces the agents\nlegible for y = {lo_far:.1f}–{hi_far:.1f} m",
        fontsize=8,
        color=TEXT,
        va="center",
        ha="left",
    )
    # spawn and the agents' start positions
    ax.add_patch(
        Rectangle(
            (0.3, SPAWN[0]),
            W - 0.6,
            SPAWN[1] - SPAWN[0],
            fc="white",
            ec=TEXT,
            lw=1.2,
            ls="--",
            zorder=3,
        )
    )
    ax.scatter(run["start"][:, 0], run["start"][:, 1], s=9, color=AGENT, zorder=4)
    ax.text(
        W + 0.4,
        np.mean(SPAWN),
        f"{run['total']} agents\nfamiliarity 0",
        fontsize=8,
        color=TEXT,
        va="center",
        ha="left",
    )
    # the walk
    y_to = L - 0.6 if chosen == "far" else 0.6
    ax.add_patch(
        FancyArrowPatch(
            (W / 2 - 0.6, np.mean(SPAWN)),
            (W / 2 - 0.6, y_to),
            arrowstyle="-|>",
            mutation_scale=18,
            color=CHOSEN,
            lw=3.0,
            zorder=6,
        )
    )
    ax.text(
        W + 0.4,
        (np.mean(SPAWN) + y_to) / 2,
        f"{run['counts'][chosen]} of {run['total']}\n"
        f"median walk {run['walked']:.1f} m\nout at {run['evac_time']:.1f} s",
        fontsize=8.5,
        color=CHOSEN,
        ha="left",
        va="center",
        fontweight="bold",
    )

    ax.set_xlim(-1.0, 11)
    ax.set_ylim(-2.5, 31.5)
    ax.set_aspect("equal")
    # a floor plan has no data axes: grid, ticks and frame add nothing
    ax.axis("off")
    ax.set_title(title, fontsize=10, loc="left", pad=6)


def main():
    """Run both configs and render the sign-bearing figure.

    Saves
    -----
    site/static/images/wayfinding/sign_bearing.png
    """
    runs = {c: simulate(c) for c in ("config_visible", "config_hidden")}
    vis_run, hid_run = runs["config_visible"], runs["config_hidden"]
    for name, run in runs.items():
        print(
            f"{name}: near={run['counts']['near']} far={run['counts']['far']} "
            f"egress={run['evac_time']:.2f} s switches={run['switches']} "
            f"median walk={run['walked']:.1f} m"
        )

    # --- Style Setup ---
    sns.set_theme(font_scale=1.0, style="whitegrid", font="DejaVu Sans")
    fig, (ax0, ax1) = plt.subplots(
        1, 2, figsize=(6.8, 5.6), dpi=150, gridspec_kw=dict(wspace=0.02)
    )

    # --- Plot ---
    draw_run(ax0, r"$\bf{(a)}$  Near sign faces the agents", vis_run)
    draw_run(ax1, r"$\bf{(b)}$  Near sign turned around", hid_run)
    fig.legend(
        handles=[
            Rectangle((0, 0), 1, 1, fc=LEGIBLE, ec=LEGIBLE_EDGE, alpha=0.7, lw=1.0)
        ],
        labels=["cells from which the near sign is legible (clear air)"],
        loc="lower left",
        bbox_to_anchor=(0.12, 0.0),
        fontsize=8,
        frameon=True,
        facecolor="white",
        framealpha=0.8,
        edgecolor="lightgrey",
        labelcolor="dimgrey",
    )
    sns.despine(fig=fig, left=True, bottom=True)

    fig.text(
        0.13,
        0.085,
        f"Turning one sign sends {hid_run['counts']['far']} of {hid_run['total']} "
        f"agents to the far exit: egress {hid_run['evac_time']:.1f} s "
        f"instead of {vis_run['evac_time']:.1f} s",
        ha="left",
        va="top",
        fontsize=8.5,
        color=TEXT,
        style="italic",
    )

    # --- Save ---
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / "sign_bearing.png", dpi=150, bbox_inches="tight")


if __name__ == "__main__":
    main()
