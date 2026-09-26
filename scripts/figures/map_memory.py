"""Cognitive map memory (assets/cognitive_map_memory), redrawn for the deck.

A 4 x 32 m corridor, exit at the end, and a side exit at (4, 20) whose sign
faces west. fdsvismap's rule view_angle * visibility >= distance makes that
sign legible only for y in [12.5, 27.5]. A discovery agent is probed at six
positions: what is in its map and which exit it would take from there.
Outcomes from the asset README.
The outcomes are drawn as recorded; this script does not rerun the asset.

Run from the repository root::

    .venv/bin/python scripts/figures/map_memory.py

Writes ``site/static/images/concepts/map_memory.png``.
"""

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

OUT = Path(__file__).resolve().parents[2] / "site" / "static" / "images" / "concepts"

BLUE = "#023d6b"
GREY = "#5a6b7d"
LIGHT = "#c3cad3"
ORANGE = "#e4661b"
GREEN = "#2e7d32"
FLOOR = "#f2f4f7"
WALL = "#4a4a4a"

W, L = 4.0, 32.0
BAND = (12.5, 27.5)
SIDE_Y = 20.0
PROBES = [
    (4, "unknown", "end"),
    (10, "unknown", "end"),
    (14, "legible", "side"),
    (20, "legible", "side"),
    (26, "legible", "side"),
    (30, "remembered", "side"),
]
STATE_COLOUR = {"unknown": "white", "legible": GREEN, "remembered": ORANGE}


def main():
    """Render the six-probe figure.

    Saves
    -----
    site/static/images/concepts/map_memory.png
    """
    plt.rcParams["font.family"] = "DejaVu Sans"
    fig, axes = plt.subplots(
        1, len(PROBES), figsize=(9.0, 4.6), dpi=150, gridspec_kw=dict(wspace=0.15)
    )
    for ax, (y, state, take) in zip(axes, PROBES):
        ax.add_patch(Rectangle((0, 0), W, L, fc=FLOOR, ec=WALL, lw=1.4, zorder=0))
        ax.add_patch(
            Rectangle(
                (0, BAND[0]),
                W,
                BAND[1] - BAND[0],
                fc=GREEN,
                alpha=0.10,
                ec="none",
                zorder=1,
            )
        )
        # end exit, always known
        ax.add_patch(
            Rectangle((W / 2 - 0.7, L - 0.3), 1.4, 0.6, fc=GREEN, ec="none", zorder=4)
        )
        # side exit, state-dependent
        ax.add_patch(
            Rectangle(
                (W - 0.3, SIDE_Y - 0.9),
                0.6,
                1.8,
                fc=STATE_COLOUR[state],
                ec=LIGHT if state == "unknown" else STATE_COLOUR[state],
                lw=1.4,
                zorder=4,
            )
        )
        # the agent probe and where it would go
        ax.scatter(
            [W / 2], [y], s=110, marker="*", fc=ORANGE, ec="white", lw=0.6, zorder=6
        )
        y_to = L - 0.8 if take == "end" else SIDE_Y
        x_to = W / 2 if take == "end" else W - 0.5
        ax.annotate(
            "",
            xy=(x_to, y_to),
            xytext=(W / 2, y),
            arrowprops=dict(arrowstyle="-|>", color=ORANGE, lw=1.6, mutation_scale=11),
            zorder=5,
        )
        ax.set_xlim(-0.6, W + 0.9)
        ax.set_ylim(-1.5, L + 1.5)
        ax.set_aspect("equal")
        ax.axis("off")
        ax.set_title(f"y = {y} m\ntakes: {take}", fontsize=8.5, color=BLUE, pad=4)

    # shared annotations on the first and last panels
    axes[0].text(
        -0.4, BAND[0], "12.5", fontsize=7, color=GREEN, ha="right", va="center"
    )
    axes[0].text(
        -0.4, BAND[1], "27.5", fontsize=7, color=GREEN, ha="right", va="center"
    )
    axes[0].text(
        -0.4,
        SIDE_Y,
        "side sign\nlegible\nin band",
        fontsize=7,
        color=GREEN,
        ha="right",
        va="center",
    )
    axes[0].text(
        W / 2, L + 0.9, "end", fontsize=7, color=GREEN, ha="center", va="bottom"
    )
    handles = [
        Rectangle(
            (0, 0), 1, 1, fc="white", ec=LIGHT, lw=1.4, label="side exit unknown"
        ),
        Rectangle((0, 0), 1, 1, fc=GREEN, label="in map, sign legible now"),
        Rectangle((0, 0), 1, 1, fc=ORANGE, label="in map, sign no longer legible"),
    ]
    fig.legend(
        handles=handles,
        loc="lower center",
        ncol=3,
        fontsize=8.5,
        frameon=True,
        facecolor="white",
        framealpha=0.8,
        edgecolor="lightgrey",
        labelcolor="dimgrey",
        bbox_to_anchor=(0.5, -0.02),
    )
    out = OUT
    out.mkdir(parents=True, exist_ok=True)
    fig.savefig(out / "map_memory.png", dpi=150, bbox_inches="tight")


if __name__ == "__main__":
    main()
