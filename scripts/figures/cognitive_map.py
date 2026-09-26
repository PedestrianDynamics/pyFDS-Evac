"""Cognitive-map evolution on the T-corridor demo, four panels.

1. At spawn (t = 0), discovery tier: the agent knows the spawn node and the
   junction whose sign is in view.
2. At the junction: both exits become legible down their arms.
3. Smoke fills the right arm; exit B stays known and the router picks exit A.
4. Full-familiarity agent at spawn: knows the whole graph from t = 0.

Schematic geometry, not the asset's exact coordinates. The panels are drawn
from the rules in ``pyfds_evac.core.cognitive_map``; nothing is simulated.

Run from the repository root::

    .venv/bin/python scripts/figures/cognitive_map.py

Writes ``site/static/images/concepts/cognitive_map.png``.
"""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.lines import Line2D
from matplotlib.patches import Polygon as MplPolygon

try:
    import seaborn as sns
except ImportError:  # seaborn only sets the theme; fall back to rcParams
    sns = None

OUT = Path(__file__).resolve().parents[2] / "site" / "static" / "images" / "concepts"

BLUE = "#023d6b"
GREY = "#5a6b7d"
LIGHT = "#c3cad3"
ORANGE = "#e4661b"
GREEN = "#2e7d32"
RED = "#b3261e"
FLOOR = "#f2f4f7"
WALL = "#4a4a4a"
SMOKE = LinearSegmentedColormap.from_list("smoke", ["#ffffff00", "#8a8a8a"])

# T-corridor: horizontal corridor on top, stem down to the spawn area
CORRIDOR = [(0, 9), (30, 9), (30, 13), (0, 13)]
STEM = [(12, 0), (18, 0), (18, 9), (12, 9)]
NODES = {
    "spawn": dict(
        xy=(15.0, 3.0), marker="^", label="spawn", lab_xy=(15.0, 1.2), ha="center"
    ),
    "junction": dict(
        xy=(15.0, 11.0), marker="o", label="junction", lab_xy=(15.0, 13.7), ha="center"
    ),
    "exit A": dict(
        xy=(1.0, 11.0), marker="s", label="exit A", lab_xy=(1.0, 13.7), ha="center"
    ),
    "exit B": dict(
        xy=(29.0, 11.0), marker="s", label="exit B", lab_xy=(29.0, 13.7), ha="center"
    ),
}
EDGES = [("spawn", "junction"), ("junction", "exit A"), ("junction", "exit B")]

PANELS = [
    dict(
        kicker="1  At spawn, t = 0",
        sub="discovery: spawn + junction with sign in view",
        known={"spawn", "junction"},
        agent=(16.6, 3.4),
        smoke=False,
        chosen=None,
    ),
    dict(
        kicker="2  Arrives at the junction",
        sub="discovery: both exits become legible",
        known={"spawn", "junction", "exit A", "exit B"},
        agent=(16.6, 10.2),
        smoke=False,
        chosen=None,
    ),
    dict(
        kicker="3  Smoke fills the right arm",
        sub="discovery: router picks exit A",
        known={"spawn", "junction", "exit A", "exit B"},
        agent=(16.6, 10.2),
        smoke=True,
        chosen=("junction", "exit A"),
    ),
    dict(
        kicker="4  At spawn, t = 0",
        sub="full familiarity: whole graph known",
        known={"spawn", "junction", "exit A", "exit B"},
        agent=(16.6, 3.4),
        smoke=False,
        chosen=None,
    ),
]


def draw_floor(ax):
    """Floor fill and the outer wall of the T."""
    outline = [(0, 9), (9, 9), (9, 0), (21, 0), (21, 9), (30, 9), (30, 13), (0, 13)]
    ax.add_patch(MplPolygon(outline, closed=True, fc=FLOOR, ec=WALL, lw=1.6, zorder=0))


def draw_smoke(ax):
    """Smoke filling the right arm, densest at exit B."""
    gx, _ = np.meshgrid(np.linspace(17, 30, 160), np.linspace(9, 13, 60))
    dens = np.clip((gx - 18.5) / 9.5, 0, 1) ** 1.2
    ax.imshow(
        dens,
        extent=(17, 30, 9, 13),
        origin="lower",
        cmap=SMOKE,
        vmin=0,
        vmax=1,
        alpha=0.9,
        aspect="auto",
        zorder=2,
        interpolation="bilinear",
    )
    ax.text(25.0, 8.4, "smoke", fontsize=8, color=GREY, ha="center", va="top", zorder=6)


def draw_graph(ax, known, chosen):
    """Edges then nodes; unknown ones are hollow and dashed."""
    for a, b in EDGES:
        (x0, y0), (x1, y1) = NODES[a]["xy"], NODES[b]["xy"]
        is_known = a in known and b in known
        is_chosen = (a, b) == chosen
        ax.plot(
            [x0, x1],
            [y0, y1],
            color=ORANGE if is_chosen else (BLUE if is_known else LIGHT),
            lw=3.6 if is_chosen else 1.8,
            ls="-" if is_known else (0, (3, 3)),
            zorder=3,
        )

    for name, n in NODES.items():
        is_known = name in known
        face = BLUE if is_known else "white"
        if is_known and name.startswith("exit"):
            face = GREEN
        ax.scatter(
            *n["xy"],
            marker=n["marker"],
            s=150,
            fc=face,
            ec=BLUE if is_known else LIGHT,
            lw=1.6,
            zorder=5,
        )
        ax.text(
            *n["lab_xy"],
            n["label"],
            fontsize=8.5,
            ha=n["ha"],
            va="center",
            color=BLUE if is_known else LIGHT,
            fontweight="bold" if is_known else None,
            zorder=6,
        )


def draw_agent(ax, xy):
    ax.scatter(*xy, marker="*", s=260, fc=ORANGE, ec="white", lw=0.8, zorder=8)
    ax.text(
        xy[0] + 1.0,
        xy[1],
        "agent",
        fontsize=8.5,
        color=ORANGE,
        ha="left",
        va="center",
        fontweight="bold",
        zorder=9,
    )


def main():
    """Render the four-panel cognitive-map figure.

    Saves
    -----
    site/static/images/concepts/cognitive_map.png
    """
    if sns is not None:
        sns.set_theme(font_scale=1.0, style="white", font="DejaVu Sans")
    else:
        plt.rcParams["font.family"] = "DejaVu Sans"

    fig, axes = plt.subplots(
        1, 4, figsize=(14.5, 3.0), dpi=150, gridspec_kw=dict(wspace=0.08)
    )
    for ax, p in zip(axes, PANELS):
        draw_floor(ax)
        if p["smoke"]:
            draw_smoke(ax)
        draw_graph(ax, p["known"], p["chosen"])
        draw_agent(ax, p["agent"])
        ax.set_xlim(-1, 31)
        ax.set_ylim(-1, 14.6)
        ax.set_aspect("equal")
        ax.axis("off")
        ax.set_anchor("N")
        ax.text(
            0.0,
            1.16,
            p["kicker"],
            transform=ax.transAxes,
            fontsize=10,
            fontweight="bold",
            color=BLUE,
            ha="left",
            va="bottom",
        )
        ax.text(
            0.0,
            1.04,
            p["sub"],
            transform=ax.transAxes,
            fontsize=8,
            color="dimgrey",
            ha="left",
            va="bottom",
        )

    handles = [
        Line2D(
            [0],
            [0],
            marker="o",
            color="w",
            mfc=BLUE,
            mec=BLUE,
            ms=8,
            label="known node",
        ),
        Line2D(
            [0],
            [0],
            marker="o",
            color="w",
            mfc="white",
            mec=LIGHT,
            mew=1.6,
            ms=8,
            label="unknown node",
        ),
        Line2D([0], [0], color=BLUE, lw=1.8, label="known edge"),
        Line2D([0], [0], color=LIGHT, lw=1.8, ls=(0, (3, 3)), label="unknown edge"),
        Line2D([0], [0], color=ORANGE, lw=3.6, label="chosen route"),
        Line2D([0], [0], marker="*", color="w", mfc=ORANGE, ms=12, label="agent"),
    ]
    # anchor the legend just below the drawn floor, whatever the figure height
    fig.canvas.draw()
    y_floor = axes[0].transData.transform((0, -1))[1] / fig.bbox.height
    fig.legend(
        handles=handles,
        loc="upper center",
        ncol=6,
        fontsize=8.5,
        bbox_to_anchor=(0.5, y_floor - 0.02),
        frameon=True,
        facecolor="white",
        framealpha=0.8,
        edgecolor="lightgrey",
        labelcolor="dimgrey",
    )

    out = OUT
    out.mkdir(parents=True, exist_ok=True)
    fig.savefig(out / "cognitive_map.png", dpi=150, bbox_inches="tight")


if __name__ == "__main__":
    main()
