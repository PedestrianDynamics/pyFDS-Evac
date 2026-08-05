#!/usr/bin/env python3
"""Plot the exit-visibility scenario: what a discovery agent knows, and where it goes.

Two panels, one per config, differing only in the near exit's sign bearing.
Each cell is shaded by which exit a discovery agent standing there would
choose, given what it can perceive from that spot. Exits are outlined by
whether their sign is legible from the marked spawn area.

The point is that the near exit is not *rejected* in the hidden panel -- it is
absent from the agent's map, so routing never sees it. That is why the shading
flips wholesale rather than at a cost crossover.

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
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402

sys.path.insert(0, "tests")
from test_exit_visibility_alpha import _load  # noqa: E402

from pyfds_evac.core.cognitive_map import init_cognitive_map  # noqa: E402
from pyfds_evac.core.route_graph import (  # noqa: E402
    RouteCostConfig,
    rank_routes,
)
from pyfds_evac.core.smoke_speed import ConstantExtinctionField  # noqa: E402

ASSET = Path("assets/exit_visibility_alpha")
CFG = RouteCostConfig(base_speed_m_per_s=1.3, w_smoke=0.0, w_fed=0.0, w_queue=0.0)
NEAR_C, FAR_C, NONE_C = "#2b7bba", "#d94801", "#cccccc"


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
    fig, axes = plt.subplots(1, 2, figsize=(8.6, 8.4), sharey=True)
    titles = [
        ("config_visible", "alpha = 0\nnear sign faces the agents"),
        ("config_hidden", "alpha = 180\nnear sign faces away"),
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
        ax.add_patch(
            Rectangle((0.5, 8.0), 3.0, 4.0, fill=False, ec="white", lw=2.5, zorder=4)
        )
        ax.text(
            2.0,
            10.0,
            "spawn",
            ha="center",
            va="center",
            color="white",
            fontsize=8,
            fontweight="bold",
            zorder=5,
        )

        for eid, sy in (("E_near", 0.7), ("E_far", 29.3)):
            legible = vis.node_is_visible(0.0, spawn[0], spawn[1], eid)
            ax.plot(
                2.0,
                sy,
                marker="s",
                ms=13,
                mfc="w",
                mec=("#111" if legible else "#d62728"),
                mew=(1.6 if legible else 3.0),
                zorder=6,
            )
            ax.text(
                2.55,
                sy,
                f"{eid}\n{'legible' if legible else 'NOT legible'} from spawn",
                va="center",
                fontsize=7.5,
                zorder=6,
            )
        ax.set_title(title, fontsize=10)
        ax.set_xlabel("x [m]")
        ax.set_xlim(0, 4)
    axes[0].set_ylabel("y [m]")

    handles = [
        Rectangle((0, 0), 1, 1, fc=NEAR_C),
        Rectangle((0, 0), 1, 1, fc=FAR_C),
    ]
    fig.legend(
        handles,
        ["would take E_near", "would take E_far"],
        loc="lower center",
        ncol=2,
        frameon=False,
        bbox_to_anchor=(0.5, 0.015),
    )
    fig.suptitle(
        "Exit a discovery agent would take, by where it stands\n"
        "only the near exit's sign bearing differs; the near exit is absent "
        "from the map, not rejected",
        fontsize=10.5,
    )
    fig.tight_layout(rect=(0.0, 0.05, 1.0, 0.93))
    fig.savefig(out_path, dpi=140)
    print(f"Wrote: {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-o", "--out", default=str(ASSET / "exit_choice_map.png"))
    main(Path(parser.parse_args().out))
