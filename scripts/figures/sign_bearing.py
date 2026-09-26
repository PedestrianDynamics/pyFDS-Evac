"""Sign-bearing experiment (assets/exit_visibility_alpha), redrawn for the deck.

A 4 x 30 m corridor, 40 discovery agents spawned at y in [8, 12], an exit at
each end. The two runs differ in one number: the bearing of the near exit's
sign. Facing the agents (alpha = 0) the near exit enters every map and all 40
take it. Facing away (alpha = 180) it never enters the map and all 40 walk the
extra 10 m to the far exit. Outcomes from the asset README.
The outcomes are drawn as recorded; this script does not rerun the asset.

Run from the repository root::

    .venv/bin/python scripts/figures/sign_bearing.py

Writes ``site/static/images/concepts/sign_bearing.png``.
"""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyArrowPatch, Rectangle, Wedge

try:
    import seaborn as sns
except ImportError:  # seaborn only sets the theme; fall back to rcParams
    sns = None

OUT = Path(__file__).resolve().parents[2] / "site" / "static" / "images" / "concepts"

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


def walk_end(chosen):
    """y where the walk arrow ends: just inside the chosen exit."""
    return L - 0.6 if chosen == "far" else 0.6


def draw_run(ax, alpha_near, title, chosen, n_taking):
    """One corridor: signs, their legible half-planes, the spawn and the walk."""
    ax.add_patch(Rectangle((0, 0), W, L, fc=FLOOR, ec=WALL, lw=1.6, zorder=0))
    # legible half-plane of each sign: yellow where it reaches the agents,
    # grey hatch where it faces out of the corridor
    for y, alpha in ((L, 180), (0, alpha_near)):
        facing_up = alpha == 0
        theta1, theta2 = (0, 180) if facing_up else (180, 360)
        reaches_agents = (y == L) != facing_up
        ax.add_patch(
            Wedge(
                (W / 2, y),
                9.0,
                theta1,
                theta2,
                fc=LEGIBLE if reaches_agents else "none",
                ec=LEGIBLE_EDGE if reaches_agents else UNKNOWN,
                hatch=None if reaches_agents else "////",
                alpha=0.55 if reaches_agents else 0.8,
                lw=0.8,
                zorder=1,
            )
        )
    # walls again on top of the wedges, so the corridor stays crisp
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
    # signs: a plate on the wall beside each exit and a bold arrow showing
    # the direction the sign faces, i.e. the side from which it can be read.
    # Drawn right of the centre line so the walk arrow never crosses them.
    xs = W / 2 + 1.2
    for y_exit, alpha in ((L, 180), (0, alpha_near)):
        faces_down = alpha == 180
        y_plate = y_exit - 0.45 if y_exit == L else y_exit + 0.45
        if y_exit == 0 and faces_down:
            # near sign turned around: plate inside the corridor, arrow
            # pointing at the exit, so it does not cross the wall
            y_plate = 3.2
        legible = (y_exit == L) == faces_down
        sign_colour = LEGIBLE_EDGE if legible else OPTION
        ax.add_patch(
            Rectangle(
                (xs - 0.35, y_plate - 0.12),
                0.7,
                0.24,
                fc=sign_colour,
                ec="none",
                zorder=5,
            )
        )
        dy = -2.6 if faces_down else 2.6
        ax.add_patch(
            FancyArrowPatch(
                (xs, y_plate),
                (xs, y_plate + dy),
                arrowstyle="-|>",
                mutation_scale=16,
                color=sign_colour,
                lw=2.2,
                zorder=5,
            )
        )
    ax.text(
        W + 0.4,
        1.6,
        f"sign α = {alpha_near}°\n"
        + ("faces the agents" if alpha_near == 0 else "faces away"),
        fontsize=8,
        color=TEXT,
        va="center",
        ha="left",
    )
    ax.text(
        W + 0.4,
        L - 1.6,
        "sign α = 180°\nfaces the agents",
        fontsize=8,
        color=TEXT,
        va="center",
        ha="left",
    )
    # spawn
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
    rng = np.random.default_rng(3)
    ax.scatter(
        rng.uniform(0.6, W - 0.6, 40),
        rng.uniform(*SPAWN, 40),
        s=9,
        color=AGENT,
        zorder=4,
    )
    ax.text(
        W + 0.4,
        np.mean(SPAWN),
        "40 agents\nfamiliarity 0",
        fontsize=8,
        color=TEXT,
        va="center",
        ha="left",
    )
    # the walk
    y_to = walk_end(chosen)
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
        f"{n_taking} of 40\n{abs(y_to - np.mean(SPAWN)):.0f} m",
        fontsize=8.5,
        color=CHOSEN,
        ha="left",
        va="center",
        fontweight="bold",
    )

    ax.set_xlim(-1.0, 11)
    ax.set_ylim(-1.5, 31.5)
    ax.set_aspect("equal")
    # a floor plan has no data axes: grid, ticks and frame add nothing
    ax.axis("off")
    ax.set_title(title, fontsize=10, loc="left", pad=6)


def main():
    """Render the sign-bearing figure.

    Saves
    -----
    site/static/images/concepts/sign_bearing.png
    """
    if sns is not None:
        sns.set_theme(font_scale=1.0, style="whitegrid", font="DejaVu Sans")
    else:
        plt.rcParams["font.family"] = "DejaVu Sans"
    fig, (ax0, ax1) = plt.subplots(
        1, 2, figsize=(6.8, 5.6), dpi=150, gridspec_kw=dict(wspace=0.02)
    )
    n_taking = 40
    draw_run(ax0, 0, r"$\bf{(a)}$  Near sign faces the agents", "near", n_taking)
    draw_run(ax1, 180, r"$\bf{(b)}$  Near sign turned around", "far", n_taking)
    if sns is not None:
        sns.despine(fig=fig, left=True, bottom=True)

    walk = {k: abs(walk_end(k) - np.mean(SPAWN)) for k in ("near", "far")}
    fig.text(
        0.13,
        0.07,
        f"Turning one sign sends all {n_taking} agents {walk['far']:.0f} m "
        f"instead of {walk['near']:.0f} m",
        ha="left",
        va="top",
        fontsize=8.5,
        color=TEXT,
        style="italic",
    )
    out = OUT
    out.mkdir(parents=True, exist_ok=True)
    fig.savefig(out / "sign_bearing.png", dpi=150, bbox_inches="tight")


if __name__ == "__main__":
    main()
