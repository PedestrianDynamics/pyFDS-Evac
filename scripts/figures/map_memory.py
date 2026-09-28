"""Cognitive map memory (assets/cognitive_map_memory), redrawn for the deck.

A 4 x 32 m corridor, exit at the end, and a side exit at (4, 20) whose sign
faces west. fdsvismap's rule view_angle * visibility >= distance makes that
sign legible only from a lens-shaped region of the corridor. The shaded cells
are the ones from which the probes' own clear-air visibility model reads it;
the gold ticks mark the span on the centreline. A discovery agent walks north
along the centreline, learning what it sees, then walks back to y = 10 with that
map. Each panel shows what is in its map and which exit it would take there.
The outcomes come from live ``rank_routes`` probes (``_cognitive_map_probe``),
the same probes that ``tests/test_cognitive_map_memory.py`` pins.

Run from the repository root::

    .venv/bin/python scripts/figures/map_memory.py

Writes ``site/static/images/wayfinding/map_memory.png``.
"""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns
from _cognitive_map_probe import CELL_SIZE_M, CENTRELINE_X, _load, probe_cognitive_map
from matplotlib.colors import ListedColormap
from matplotlib.patches import Rectangle

IMAGES = Path(__file__).resolve().parents[2] / "site" / "static" / "images"
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

W, L = 4.0, 32.0
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


def legible_region(vis):
    """Cells of the corridor that read the side sign, and the centreline span.

    The span is sampled finer than the grid, so its ends are the cell edges
    where the model's answer changes. It must be one interval: the figure
    labels it by its two ends.
    """
    xs = np.arange(CELL_SIZE_M / 2, W, CELL_SIZE_M)
    ys = np.arange(CELL_SIZE_M / 2, L, CELL_SIZE_M)
    cells = np.array(
        [[vis.node_is_visible(0.0, x, y, "E_side") for x in xs] for y in ys]
    )
    fine = np.arange(0.0, L, 0.05)
    on_line = np.array(
        [vis.node_is_visible(0.0, CENTRELINE_X, y, "E_side") for y in fine]
    )
    idx = np.flatnonzero(on_line)
    assert idx.size and np.all(np.diff(idx) == 1), "legible span is not one interval"
    # the answer changes between the last miss and the first hit
    edges = (fine[idx[0] - 1 : idx[0] + 1].mean(), fine[idx[-1] : idx[-1] + 2].mean())
    return cells, (float(edges[0]), float(edges[1]))


def main():
    """Render the five-panel figure from live engine probes.

    Saves
    -----
    site/static/images/wayfinding/map_memory.png
    """
    probes = probe_cognitive_map(NORTH_YS, [RETURN_Y])
    by_key = {(p.y, p.heading): p for p in probes}
    panels = [by_key[(float(y), heading)] for y, heading in PANELS]
    up, back = by_key[(float(RETURN_Y), "north")], by_key[(float(RETURN_Y), "south")]
    # the figure's claim: memory, not position, changes the choice
    assert up.choice != back.choice, (up, back)
    cells, band = legible_region(_load()[1])
    print(f"side sign legible on the centreline for y = {band[0]:.2f}-{band[1]:.2f} m")

    sns.set_theme(font_scale=1.0, style="whitegrid", font="DejaVu Sans")
    fig, axes = plt.subplots(
        1, len(panels), figsize=(9.0, 4.6), dpi=150, gridspec_kw=dict(wspace=0.15)
    )
    for ax, probe in zip(axes, panels):
        y, state, take = probe.y, probe.side, probe.choice
        ax.add_patch(Rectangle((0, 0), W, L, fc=FLOOR, ec=WALL, lw=1.4, zorder=0))
        ax.imshow(
            np.where(cells, 1.0, np.nan),
            origin="lower",
            extent=(0, W, 0, L),
            cmap=ListedColormap([LEGIBLE]),
            alpha=0.7,
            interpolation="nearest",
            zorder=1,
        )
        ax.contour(
            np.arange(CELL_SIZE_M / 2, W, CELL_SIZE_M),
            np.arange(CELL_SIZE_M / 2, L, CELL_SIZE_M),
            cells.astype(float),
            levels=[0.5],
            colors=LEGIBLE_EDGE,
            linewidths=0.8,
            zorder=1,
        )
        # where the centreline, the probes' path, enters and leaves the region
        for y_edge in band:
            ax.plot(
                [W / 2 - 0.45, W / 2 + 0.45],
                [y_edge, y_edge],
                color=LEGIBLE_EDGE,
                lw=1.6,
                zorder=2,
            )
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
    for y_edge in band:
        axes[0].text(
            -0.4,
            y_edge,
            f"{y_edge:.1f} on\ncentreline",
            fontsize=6.5,
            color=TEXT,
            ha="right",
            va="center",
        )
    axes[0].text(
        -0.4,
        SIDE_Y,
        "side sign\nlegible\nin shade",
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
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / "map_memory.png", dpi=150, bbox_inches="tight")


if __name__ == "__main__":
    main()
