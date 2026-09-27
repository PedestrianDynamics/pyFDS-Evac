"""Cognitive map memory (assets/cognitive_map_memory), redrawn for the deck.

A 4 x 32 m corridor, exit at the end, and a side exit at (4, 20) whose sign
faces west. fdsvismap's rule view_angle * visibility >= distance makes that
sign legible only for y in [12.5, 27.5]. A discovery agent walks north along
the centreline, learning what it sees, then walks back to y = 10 with that
map. Each panel shows what is in its map and which exit it would take there.
The outcomes come from live ``rank_routes`` probes (``_cognitive_map_probe``),
the same probes that ``tests/test_cognitive_map_memory.py`` pins.

Run from the repository root::

    .venv/bin/python scripts/figures/map_memory.py

Writes ``site/static/images/wayfinding/map_memory.png`` and, until the docs
move there, ``site/static/images/concepts/map_memory.png``.
"""

from pathlib import Path

import matplotlib.pyplot as plt
import seaborn as sns
from _cognitive_map_probe import probe_cognitive_map
from matplotlib.patches import Rectangle

IMAGES = Path(__file__).resolve().parents[2] / "site" / "static" / "images"
OUTS = [IMAGES / "wayfinding", IMAGES / "concepts"]

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

W, L = 4.0, 32.0
BAND = (12.5, 27.5)
SIDE_Y = 20.0
NORTH_YS = [4, 10, 14, 20, 30]
RETURN_Y = 10
PANELS = [(4, "north"), (14, "north"), (20, "north"), (30, "north"), (10, "south")]
# side-exit patch per map state: unknown is hollow and dashed; a known exit
# is filled, outlined in gold while its sign is legible, hatched once it is
# only remembered
STATE_STYLE = {
    "unknown": dict(fc="white", ec=UNKNOWN, ls="--", lw=1.4),
    "legible": dict(fc=EXIT, ec=LEGIBLE_EDGE, lw=1.4),
    "remembered": dict(fc=EXIT, ec=KNOWN, hatch="////", lw=1.2),
}


def main():
    """Render the five-panel figure from live engine probes.

    Saves
    -----
    site/static/images/wayfinding/map_memory.png
    site/static/images/concepts/map_memory.png
    """
    probes = probe_cognitive_map(NORTH_YS, [RETURN_Y])
    by_key = {(p.y, p.heading): p for p in probes}
    panels = [by_key[(float(y), heading)] for y, heading in PANELS]
    up, back = by_key[(float(RETURN_Y), "north")], by_key[(float(RETURN_Y), "south")]
    # the figure's claim: memory, not position, changes the choice
    assert up.choice != back.choice, (up, back)

    sns.set_theme(font_scale=1.0, style="whitegrid", font="DejaVu Sans")
    fig, axes = plt.subplots(
        1, len(panels), figsize=(9.0, 4.6), dpi=150, gridspec_kw=dict(wspace=0.15)
    )
    for ax, probe in zip(axes, panels):
        y, state, take = probe.y, probe.side, probe.choice
        ax.add_patch(Rectangle((0, 0), W, L, fc=FLOOR, ec=WALL, lw=1.4, zorder=0))
        ax.add_patch(
            Rectangle(
                (0, BAND[0]),
                W,
                BAND[1] - BAND[0],
                fc=LEGIBLE,
                alpha=0.5,
                ec="none",
                zorder=1,
            )
        )
        for y_edge in BAND:
            ax.plot([0, W], [y_edge, y_edge], color=LEGIBLE_EDGE, lw=0.8, zorder=1)
        # end exit, always known
        ax.add_patch(
            Rectangle((W / 2 - 0.7, L - 0.3), 1.4, 0.6, fc=EXIT, ec="none", zorder=4)
        )
        # side exit, state-dependent
        ax.add_patch(
            Rectangle(
                (W - 0.3, SIDE_Y - 0.9),
                0.6,
                1.8,
                zorder=4,
                **STATE_STYLE[state],
            )
        )
        # the agent probe and where it would go
        ax.scatter(
            [W / 2], [y], s=130, marker="*", fc=AGENT, ec="white", lw=0.6, zorder=6
        )
        y_to = L - 0.8 if take == "end" else SIDE_Y
        x_to = W / 2 if take == "end" else W - 0.5
        ax.annotate(
            "",
            xy=(x_to, y_to),
            xytext=(W / 2, y),
            arrowprops=dict(arrowstyle="-|>", color=CHOSEN, lw=1.8, mutation_scale=11),
            zorder=5,
        )
        ax.set_xlim(-0.6, W + 0.9)
        ax.set_ylim(-1.5, L + 1.5)
        ax.set_aspect("equal")
        # a floor plan has no data axes: grid, ticks and frame add nothing
        ax.axis("off")
        where = f"y = {y:.0f} m" + (", back" if probe.heading == "south" else "")
        ax.set_title(f"{where}\ntakes: {take}", fontsize=8.5, pad=4)
        if probe.heading == "south":
            # the walk back from the top of the sweep, with the map it built
            ax.annotate(
                "",
                xy=(0.6, y + 1.0),
                xytext=(0.6, max(NORTH_YS)),
                arrowprops=dict(
                    arrowstyle="-|>", color=TEXT, lw=1.0, ls=":", mutation_scale=9
                ),
                zorder=5,
            )

    # shared annotations on the first and last panels
    axes[0].text(-0.4, BAND[0], "12.5", fontsize=7, color=TEXT, ha="right", va="center")
    axes[0].text(-0.4, BAND[1], "27.5", fontsize=7, color=TEXT, ha="right", va="center")
    axes[0].text(
        -0.4,
        SIDE_Y,
        "side sign\nlegible\nin band",
        fontsize=7,
        color=TEXT,
        ha="right",
        va="center",
    )
    axes[0].text(
        W / 2, L + 0.9, "end", fontsize=7, color=TEXT, ha="center", va="bottom"
    )
    handles = [
        Rectangle((0, 0), 1, 1, label="side exit unknown", **STATE_STYLE["unknown"]),
        Rectangle(
            (0, 0), 1, 1, label="in map, sign legible now", **STATE_STYLE["legible"]
        ),
        Rectangle(
            (0, 0),
            1,
            1,
            label="in map, sign no longer legible",
            **STATE_STYLE["remembered"],
        ),
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
    sns.despine(fig=fig, left=True, bottom=True)

    fig.text(
        0.5,
        -0.06,
        f"Same place, different history: at y = {RETURN_Y} m, {up.choice} on the "
        f"way up, {back.choice} on the way back\nwith the side exit in memory, it "
        f"is the nearer one ({back.choice} {back.distance_m['E_' + back.choice]:.1f}"
        f" m vs {up.choice} {back.distance_m['E_' + up.choice]:.1f} m)",
        ha="center",
        va="top",
        fontsize=8.5,
        color=TEXT,
        style="italic",
    )
    for out in OUTS:
        out.mkdir(parents=True, exist_ok=True)
        fig.savefig(out / "map_memory.png", dpi=150, bbox_inches="tight")


if __name__ == "__main__":
    main()
