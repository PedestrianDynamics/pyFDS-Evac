#!/usr/bin/env python3
"""Plot what an agent knows as it walks, for assets/cognitive_map_memory.

Three states per exit, and the distinction between the last two is the point:

  hollow, dashed grey   unknown      never perceived
  green, gold outline   legible now  in the map, and its sign is currently readable
  green, hatched        remembered   in the map, but its sign is no longer readable

The hatched state is the cognitive map doing the one thing a visibility query
cannot: remembering. If legible and remembered never diverge, there is no
memory to speak of and the map is an expensive way to ask "what can I see".

Usage:
    .venv/bin/python scripts/generate_cognitive_map_states.py [-o OUT.png]
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns
from matplotlib.patches import Rectangle
from shapely import wkt as shapely_wkt
from shapely.geometry import Polygon

from pyfds_evac.core.cognitive_map import (
    expand_from_visibility,
    init_cognitive_map,
)
from pyfds_evac.core.route_graph import (
    RouteCostConfig,
    StageGraph,
    rank_routes,
)
from pyfds_evac.core.smoke_speed import ConstantExtinctionField
from pyfds_evac.core.visibility import VisibilityModel

ASSET = Path("assets/cognitive_map_memory")
MAX_VIS_M = 30.0
CENTRELINE_X = 2.0

# Shared palette of the concept figures: one meaning, one colour, one style.
CHOSEN = "#4575b4"  # chosen / walked route: solid line
KNOWN = "#324465"  # stage in the map: filled marker
UNKNOWN = "#bdbdbd"  # stage not in the map: hollow marker, dashed edge
LEGIBLE = "#fee090"  # legible sign: yellow fill with a gold outline
LEGIBLE_EDGE = "#c89b00"
EXIT = "#33a02c"  # exit door
AGENT = "#1a1a1a"  # agent: star marker
WALL = "dimgrey"
FLOOR = "#f7f7f7"
TEXT = "dimgrey"
# exit patch per map state: unknown is hollow and dashed; a known exit is
# filled, outlined in gold while its sign is legible, hatched once it is only
# remembered
STATE_STYLE = {
    "unknown": dict(fc="white", ec=UNKNOWN, ls="--", lw=1.4),
    "legible": dict(fc=EXIT, ec=LEGIBLE_EDGE, lw=1.8),
    "remembered": dict(fc=EXIT, ec=KNOWN, hatch="////", lw=1.2),
}


def _builder():
    spec = importlib.util.spec_from_file_location(
        "cmm_builder", ASSET / "build_geometry.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load():
    raw = json.loads((ASSET / "config.json").read_text(encoding="utf-8"))
    stages = {
        eid: {"polygon": Polygon(d["coordinates"]), "stage_type": "exit"}
        for eid, d in raw["exits"].items()
    }
    dists = {
        did: {"coordinates": d["coordinates"]}
        for did, d in raw["distributions"].items()
    }
    graph = StageGraph.from_scenario(stages, raw["transitions"], distributions=dists)
    signs = {eid: d["sign"] for eid, d in raw["exits"].items()}
    return graph, signs, raw


def main(out_path: Path) -> None:
    builder = _builder()
    graph, signs, _raw = _load()
    walkable = shapely_wkt.loads((ASSET / "geometry.wkt").read_text().strip())
    vis = VisibilityModel.clear_air(walkable, signs, cell_size_m=0.25)

    walkable = builder.CORRIDOR
    frames_y = [4.0, 10.0, 14.0, 20.0, 26.0, 30.0]

    cmap_agent = init_cognitive_map(
        "jps-distributions_0", graph, "discovery", vis_model=vis, time_s=0.0
    )

    sns.set_theme(font_scale=1.0, style="whitegrid", font="DejaVu Sans")
    fig, axes = plt.subplots(
        1,
        len(frames_y),
        figsize=(1.6 * len(frames_y), 7.2),
        gridspec_kw=dict(wspace=0.15),
    )
    for ax, y in zip(axes, frames_y):
        expand_from_visibility(
            cmap_agent, "jps-distributions_0", graph, vis, 0.0, CENTRELINE_X, y
        )
        ax.add_patch(
            Rectangle(
                (walkable[0], walkable[1]),
                walkable[2] - walkable[0],
                walkable[3] - walkable[1],
                fc=FLOOR,
                ec=WALL,
                lw=1.4,
            )
        )
        for eid, bounds in (("E_end", builder.E_END), ("E_side", builder.E_SIDE)):
            known = eid in cmap_agent.known_nodes
            legible = vis.node_is_visible(0.0, CENTRELINE_X, y, eid)
            state = (
                "legible"
                if (known and legible)
                else ("remembered" if known else "unknown")
            )
            ax.add_patch(
                Rectangle(
                    (bounds[0], bounds[1]),
                    bounds[2] - bounds[0],
                    bounds[3] - bounds[1],
                    zorder=4,
                    **STATE_STYLE[state],
                )
            )
            ax.text(
                bounds[2] + 0.15 if eid == "E_side" else (bounds[0] + bounds[2]) / 2,
                (bounds[1] + bounds[3]) / 2 if eid == "E_side" else bounds[3] + 0.3,
                eid.replace("E_", ""),
                fontsize=7,
                color=TEXT,
                ha="left" if eid == "E_side" else "center",
                va="center" if eid == "E_side" else "bottom",
            )
        ax.scatter(
            [CENTRELINE_X],
            [y],
            s=150,
            marker="*",
            fc=AGENT,
            ec="white",
            lw=0.6,
            zorder=6,
        )
        ranked = rank_routes(
            graph,
            "jps-distributions_0",
            0.0,
            0.0,
            ConstantExtinctionField(0.0),
            None,
            RouteCostConfig(base_speed_m_per_s=1.3, w_smoke=0.0, w_fed=0.0),
            cognitive_map=cmap_agent,
            agent_position=(CENTRELINE_X, y),
        )
        choice = ranked[0].exit_id.replace("E_", "") if ranked else "-"
        if ranked:
            target = builder.E_SIDE if choice == "side" else builder.E_END
            ax.annotate(
                "",
                xy=(
                    target[0] - 0.1 if choice == "side" else CENTRELINE_X,
                    (target[1] + target[3]) / 2
                    if choice == "side"
                    else target[1] - 0.1,
                ),
                xytext=(CENTRELINE_X, y),
                arrowprops=dict(
                    arrowstyle="-|>", color=CHOSEN, lw=1.8, mutation_scale=11
                ),
                zorder=5,
            )
        ax.set_title(f"y = {y:.0f} m\nwould take: {choice}", fontsize=9, pad=4)
        ax.set_xlim(-0.6, 5.6)
        ax.set_ylim(-1, builder.CORRIDOR[3] + 1)
        ax.set_aspect("equal")
        ax.grid(False)
        ax.set_xticks([])
        ax.tick_params(axis="both", which="both", length=0, labelcolor=TEXT)
        if ax is not axes[0]:
            ax.set_yticks([])
    axes[0].set_ylabel("y [m]", color=TEXT)
    sns.despine(fig=fig, left=True, bottom=True)

    handles = [
        Rectangle((0, 0), 1, 1, **STATE_STYLE["unknown"]),
        Rectangle((0, 0), 1, 1, **STATE_STYLE["legible"]),
        Rectangle((0, 0), 1, 1, **STATE_STYLE["remembered"]),
        plt.Line2D([], [], color=CHOSEN, lw=1.8),
        plt.Line2D([], [], marker="*", ls="", ms=11, mfc=AGENT, mec="white"),
    ]
    fig.legend(
        handles,
        [
            "unknown",
            "in map, sign legible now",
            "in map, sign no longer legible",
            "exit routing would take",
            "probe position",
        ],
        loc="lower center",
        ncol=3,
        fontsize=8.5,
        frameon=True,
        facecolor="white",
        framealpha=0.8,
        edgecolor="lightgrey",
        labelcolor=TEXT,
        bbox_to_anchor=(0.5, 0.0),
    )
    fig.suptitle(
        "Cognitive map of a discovery agent, probed along the corridor",
        fontsize=11,
    )
    fig.text(
        0.5,
        0.93,
        "Hatched = remembered without being visible; that is the memory.\n"
        "The probe is not a walk: each panel places the agent at that y.",
        ha="center",
        va="center",
        fontsize=8.5,
        color=TEXT,
        style="italic",
    )
    fig.subplots_adjust(left=0.08, right=0.98, bottom=0.12, top=0.84)
    fig.savefig(out_path, dpi=140)
    print(f"Wrote: {out_path}")
    print(f"Known exits at the end: {sorted(cmap_agent.known_nodes)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-o", "--out", default=str(ASSET / "cognitive_map_states.png"))
    main(Path(parser.parse_args().out))
