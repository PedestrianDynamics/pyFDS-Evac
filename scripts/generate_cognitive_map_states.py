#!/usr/bin/env python3
"""Plot what an agent knows as it walks, for assets/cognitive_map_memory.

Three states per exit, and the distinction between the last two is the point:

  grey   unknown        never perceived
  red    legible now    in the map, and its sign is currently readable
  amber  remembered     in the map, but its sign is no longer readable

The amber band is the cognitive map doing the one thing a visibility query
cannot: remembering. If red and amber never diverge, there is no memory to
speak of and the map is an expensive way to ask "what can I see".

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
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402
from shapely import wkt as shapely_wkt  # noqa: E402
from shapely.geometry import Polygon  # noqa: E402

from pyfds_evac.core.cognitive_map import (  # noqa: E402
    expand_from_visibility,
    init_cognitive_map,
)
from pyfds_evac.core.route_graph import (  # noqa: E402
    RouteCostConfig,
    StageGraph,
    rank_routes,
)
from pyfds_evac.core.smoke_speed import ConstantExtinctionField  # noqa: E402
from pyfds_evac.core.visibility import VisibilityModel  # noqa: E402

ASSET = Path("assets/cognitive_map_memory")
MAX_VIS_M = 30.0
CENTRELINE_X = 2.0

UNKNOWN, LEGIBLE, REMEMBERED = "#bdbdbd", "#d62728", "#e8a33d"


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

    fig, axes = plt.subplots(1, len(frames_y), figsize=(3.0 * len(frames_y), 7.2))
    for ax, y in zip(axes, frames_y):
        expand_from_visibility(
            cmap_agent, "jps-distributions_0", graph, vis, 0.0, CENTRELINE_X, y
        )
        ax.add_patch(
            Rectangle(
                (walkable[0], walkable[1]),
                walkable[2] - walkable[0],
                walkable[3] - walkable[1],
                fc="#f4f4f4",
                ec="#555",
                lw=1.2,
            )
        )
        for eid, bounds in (("E_end", builder.E_END), ("E_side", builder.E_SIDE)):
            known = eid in cmap_agent.known_nodes
            legible = vis.node_is_visible(0.0, CENTRELINE_X, y, eid)
            colour = (
                LEGIBLE if (known and legible) else (REMEMBERED if known else UNKNOWN)
            )
            ax.add_patch(
                Rectangle(
                    (bounds[0], bounds[1]),
                    bounds[2] - bounds[0],
                    bounds[3] - bounds[1],
                    fc=colour,
                    ec="k",
                    lw=1.0,
                )
            )
            ax.text(
                bounds[0] + 0.1,
                (bounds[1] + bounds[3]) / 2,
                eid.replace("E_", ""),
                fontsize=7,
                va="center",
            )
        ax.plot(CENTRELINE_X, y, "o", ms=10, mfc="#1f77b4", mec="k", zorder=5)
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
        ax.set_title(f"y = {y:.0f} m\nwould take: {choice}", fontsize=9)
        ax.set_xlim(-0.6, 5.6)
        ax.set_ylim(-1, builder.CORRIDOR[3] + 1)
        ax.set_aspect("equal")
        ax.set_xticks([])
        if ax is not axes[0]:
            ax.set_yticks([])
    axes[0].set_ylabel("y [m]")

    handles = [
        Rectangle((0, 0), 1, 1, fc=UNKNOWN, ec="k"),
        Rectangle((0, 0), 1, 1, fc=LEGIBLE, ec="k"),
        Rectangle((0, 0), 1, 1, fc=REMEMBERED, ec="k"),
    ]
    fig.legend(
        handles,
        ["unknown", "in map, sign legible now", "in map, sign no longer legible"],
        loc="lower center",
        ncol=3,
        frameon=False,
        bbox_to_anchor=(0.5, 0.01),
    )
    fig.suptitle(
        "Cognitive map of a discovery agent, probed along the corridor\n"
        "amber = remembered without being visible; that band is the memory. "
        "The probe is not a walk: the agent would leave by 'side' from y = 14.",
        fontsize=11,
    )
    fig.tight_layout(rect=(0.0, 0.06, 1.0, 0.94))
    fig.savefig(out_path, dpi=140)
    print(f"Wrote: {out_path}")
    print(f"Known exits at the end: {sorted(cmap_agent.known_nodes)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-o", "--out", default=str(ASSET / "cognitive_map_states.png"))
    main(Path(parser.parse_args().out))
