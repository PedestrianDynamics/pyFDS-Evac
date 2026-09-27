#!/usr/bin/env python3
"""Plot the exit-visibility scenario: what a discovery agent knows, and where it goes.

Two panels, one per config, differing only in the near exit's sign bearing.
Each cell is shaded by which exit a discovery agent standing there would
choose, given what it can perceive from that spot (the far-exit cells are
hatched as well as coloured). An exit whose sign is legible from the marked
spawn area is drawn as a yellow plate with a gold outline; an illegible one is
hollow and grey.

In the visible panel both exits are in the map everywhere the near sign can be
read, so the split is a cost crossover: the dashed line marks where the choice
changes, computed from the grid. In the hidden panel the near exit is not
*rejected* -- it is absent from the agent's map, so routing never sees it, and
the whole corridor above the near sign takes the far exit.

Usage:
    .venv/bin/python scripts/generate_exit_visibility_map.py [-o OUT.png]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns
from matplotlib import patheffects
from matplotlib.patches import Rectangle

sys.path.insert(0, "tests")
from test_exit_visibility_alpha import _load

from pyfds_evac.core.cognitive_map import init_cognitive_map
from pyfds_evac.core.route_graph import (
    RouteCostConfig,
    rank_routes,
)
from pyfds_evac.core.smoke_speed import ConstantExtinctionField

ASSET = Path("assets/exit_visibility_alpha")
CFG = RouteCostConfig(base_speed_m_per_s=1.3, w_smoke=0.0, w_fed=0.0, w_queue=0.0)
NEAR_C, FAR_C, NONE_C = "#91bfdb", "#fc8d59", "#cccccc"
FAR_HATCH = "////"
# Shared palette of the concept figures: one meaning, one colour, one style.
LEGIBLE = "#fee090"  # legible sign: yellow fill with a gold outline
LEGIBLE_EDGE = "#c89b00"
UNKNOWN = "#bdbdbd"  # sign not legible: hollow marker, grey edge
WALL = "dimgrey"
TEXT = "dimgrey"


def chosen_exit(graph, vis, position):
    """Which exit a discovery agent standing here would take, or None."""
    cmap = init_cognitive_map(
        "jps-distributions_0", graph, "discovery", vis_model=vis, time_s=0.0
    )
    # The agent perceives from where it stands, not from the spawn centroid.
    from pyfds_evac.core.cognitive_map import expand_from_visibility

    expand_from_visibility(
        cmap, "jps-distributions_0", graph, vis, 0.0, position[0], position[1]
    )
    ranked = rank_routes(
        graph,
        "jps-distributions_0",
        0.0,
        0.0,
        ConstantExtinctionField(0.0),
        None,
        CFG,
        cognitive_map=cmap,
        agent_position=position,
    )
    return ranked[0].exit_id if ranked else None


def main(out_path: Path) -> None:
    sns.set_theme(font_scale=1.0, style="whitegrid", font="DejaVu Sans")
    fig, axes = plt.subplots(1, 2, figsize=(8.6, 8.4), sharey=True)
    titles = [
        ("config_visible", r"$\bf{(a)}$  alpha = 0" + "\nnear sign faces the agents"),
        ("config_hidden", r"$\bf{(b)}$  alpha = 180" + "\nnear sign faces away"),
    ]
    step = 0.5
    xs = np.arange(0.25, 4.0, step)
    ys = np.arange(0.25, 30.0, step)

    for ax, (cfg_name, title) in zip(axes, titles):
        graph, spawn, vis = _load(cfg_name)
        grid = np.full((len(ys), len(xs)), np.nan)
        for j, y in enumerate(ys):
            for i, x in enumerate(xs):
                got = chosen_exit(graph, vis, (float(x), float(y)))
                grid[j, i] = {"E_near": 0.0, "E_far": 1.0}.get(got, np.nan)

        ax.imshow(
            grid,
            origin="lower",
            cmap=matplotlib.colors.ListedColormap([NEAR_C, FAR_C]),
            vmin=0,
            vmax=1,
            extent=[float(xs[0]), float(xs[-1]), float(ys[0]), float(ys[-1])],
            aspect="equal",
            interpolation="nearest",
        )
        # far-exit cells are hatched too, so the split survives without colour
        extent = (float(xs[0]), float(xs[-1]), float(ys[0]), float(ys[-1]))
        ax.contourf(
            np.linspace(extent[0], extent[1], len(xs)),
            np.linspace(extent[2], extent[3], len(ys)),
            np.nan_to_num(grid, nan=-1.0),
            levels=[0.5, 1.5],
            colors="none",
            hatches=[FAR_HATCH],
            zorder=2,
        )
        ax.add_patch(
            Rectangle(
                (0, 0), 4.0, 30.0, fill=False, ec=WALL, lw=1.4, zorder=3, clip_on=False
            )
        )
        # rows whose every cell takes E_near below and E_far above: the crossover
        near_rows = np.all(grid == 0.0, axis=1)
        flips = np.flatnonzero(near_rows[:-1] & np.all(grid[1:] == 1.0, axis=1))
        for j in flips:
            y_cross = float(ys[j] + ys[j + 1]) / 2
            ax.plot([0, 4.0], [y_cross, y_cross], color=WALL, lw=1.2, ls="--", zorder=4)
            ax.text(
                4.2,
                y_cross,
                f"cost crossover\ny = {y_cross:.1f} m",
                va="center",
                fontsize=7.5,
                color=TEXT,
                zorder=6,
            )
        # outline only: the exit choice inside the spawn area stays visible
        ax.add_patch(
            Rectangle(
                (0.5, 8.0), 3.0, 4.0, fill=False, ec=TEXT, lw=1.4, ls="--", zorder=4
            )
        )
        ax.text(
            2.0,
            10.0,
            "spawn",
            ha="center",
            va="center",
            color=TEXT,
            fontsize=8,
            fontweight="bold",
            path_effects=[patheffects.withStroke(linewidth=2.5, foreground="white")],
            zorder=5,
        )

        for eid, sy in (("E_near", 0.7), ("E_far", 29.3)):
            legible = vis.node_is_visible(0.0, spawn[0], spawn[1], eid)
            ax.plot(
                2.0,
                sy,
                marker="s",
                ms=13,
                mfc=(LEGIBLE if legible else "white"),
                mec=(LEGIBLE_EDGE if legible else UNKNOWN),
                mew=(2.0 if legible else 1.6),
                zorder=6,
            )
            ax.text(
                2.75,
                sy,
                f"{eid}\n{'legible' if legible else 'NOT legible'} from spawn",
                va="center",
                fontsize=7.5,
                color=TEXT,
                bbox=dict(fc="white", ec="none", alpha=0.8, pad=1.0),
                zorder=6,
            )
        ax.set_title(title, fontsize=10, loc="left", pad=7)
        ax.set_xlabel("x [m]", color=TEXT)
        ax.set_xlim(0, 4)
        ax.grid(False)
        ax.tick_params(axis="both", which="both", length=0, labelcolor=TEXT)
    axes[0].set_ylabel("y [m]", color=TEXT)
    sns.despine(fig=fig, left=True, bottom=True)

    handles = [
        Rectangle((0, 0), 1, 1, fc=NEAR_C, ec="none"),
        Rectangle((0, 0), 1, 1, fc=FAR_C, ec="white", hatch=FAR_HATCH),
        plt.Line2D(
            [], [], marker="s", ls="", ms=9, mfc=LEGIBLE, mec=LEGIBLE_EDGE, mew=2.0
        ),
        plt.Line2D([], [], marker="s", ls="", ms=9, mfc="white", mec=UNKNOWN, mew=1.6),
    ]
    fig.legend(
        handles,
        [
            "would take E_near",
            "would take E_far",
            "sign legible from spawn",
            "sign not legible from spawn",
        ],
        loc="lower center",
        ncol=2,
        fontsize=8.5,
        frameon=True,
        facecolor="white",
        framealpha=0.8,
        edgecolor="lightgrey",
        labelcolor=TEXT,
        bbox_to_anchor=(0.5, 0.0),
    )
    fig.suptitle(
        "Exit a discovery agent would take, by where it stands",
        fontsize=11,
    )
    fig.text(
        0.5,
        0.925,
        "Only the near exit's sign bearing differs. Facing away, the near exit is "
        "absent from the map, not rejected",
        ha="center",
        va="center",
        fontsize=9,
        color=TEXT,
        style="italic",
    )
    fig.tight_layout(rect=(0.0, 0.07, 1.0, 0.91))
    fig.savefig(out_path, dpi=140)
    print(f"Wrote: {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-o", "--out", default=str(ASSET / "exit_choice_map.png"))
    main(Path(parser.parse_args().out))
