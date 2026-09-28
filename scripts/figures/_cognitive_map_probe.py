"""Probe what a discovery agent knows and chooses in assets/cognitive_map_memory.

The figures of the map-memory demo and their test draw from this one sweep, so
a routing change that moves an outcome breaks the test instead of silently
invalidating a figure.

The agent walks the centreline x = 2 north through ``ys``, learning from what
it sees in clear air, then walks back south through ``return_ys`` with the map
it has built. At each position it records the map state of every exit and the
exit ``rank_routes`` would choose from there.
"""

from __future__ import annotations

import importlib.util
import json
from dataclasses import dataclass
from pathlib import Path

from shapely import wkt as shapely_wkt
from shapely.geometry import Polygon

from pyfds_evac.core.cognitive_map import expand_from_visibility, init_cognitive_map
from pyfds_evac.core.route_graph import RouteCostConfig, StageGraph, rank_routes
from pyfds_evac.core.smoke_speed import ConstantExtinctionField
from pyfds_evac.core.visibility import VisibilityModel

ASSET = Path(__file__).resolve().parents[2] / "assets" / "cognitive_map_memory"
ORIGIN = "jps-distributions_0"
CENTRELINE_X = 2.0
CELL_SIZE_M = 0.25
COST = RouteCostConfig(base_speed_m_per_s=1.3, w_smoke=0.0, w_fed=0.0)


@dataclass(frozen=True)
class Probe:
    """One probe position and what the agent knows and chooses there.

    ``states`` maps each exit to ``"unknown"``, ``"legible"`` (in the map and
    its sign readable now) or ``"remembered"`` (in the map, sign unreadable).
    ``distance_m`` holds the walking distance from the probe to each exit in
    the map: clear-air travel time times the walking speed.
    """

    y: float
    heading: str  # "north" on the way up, "south" on the way back
    states: dict[str, str]
    choice: str  # exit id without the "E_" prefix
    distance_m: dict[str, float]

    @property
    def side(self) -> str:
        """Map state of the side exit."""
        return self.states["E_side"]


def load_builder():
    """Import the asset's ``build_geometry.py`` for its geometry constants."""
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
    walkable = shapely_wkt.loads((ASSET / "geometry.wkt").read_text().strip())
    vis = VisibilityModel.clear_air(walkable, signs, cell_size_m=CELL_SIZE_M)
    return graph, vis


def _probe(graph, vis, cmap, y, heading):
    expand_from_visibility(cmap, ORIGIN, graph, vis, 0.0, CENTRELINE_X, y)
    states = {}
    for eid in sorted(n for n in graph.nodes if n.startswith("E_")):
        known = eid in cmap.known_nodes
        legible = vis.node_is_visible(0.0, CENTRELINE_X, y, eid)
        states[eid] = (
            "unknown" if not known else ("legible" if legible else "remembered")
        )
    ranked = rank_routes(
        graph,
        ORIGIN,
        0.0,
        0.0,
        ConstantExtinctionField(0.0),
        None,
        COST,
        cognitive_map=cmap,
        agent_position=(CENTRELINE_X, y),
    )
    return Probe(
        y=float(y),
        heading=heading,
        states=states,
        choice=ranked[0].exit_id.removeprefix("E_") if ranked else "-",
        distance_m={
            rc.exit_id: rc.travel_time_s * COST.base_speed_m_per_s for rc in ranked
        },
    )


def probe_cognitive_map(ys, return_ys=()):
    """Sweep a discovery agent north through ``ys``, then back through ``return_ys``.

    Parameters
    ----------
    ys : iterable of float
        Centreline positions on the way north; the map grows at each one.
    return_ys : iterable of float
        Positions on the way back south, probed with the map built on the way
        up.

    Returns
    -------
    list of Probe
        One per position, northbound probes first.
    """
    graph, vis = _load()
    cmap = init_cognitive_map(ORIGIN, graph, "discovery", vis_model=vis, time_s=0.0)
    probes = [_probe(graph, vis, cmap, float(y), "north") for y in ys]
    probes += [_probe(graph, vis, cmap, float(y), "south") for y in return_ys]
    return probes


if __name__ == "__main__":
    for p in probe_cognitive_map([4, 10, 14, 20, 26, 30], [10]):
        lengths = "  ".join(f"{e}={d:.2f} m" for e, d in p.distance_m.items())
        print(f"{p.heading:5s} y={p.y:4.0f}  {p.side:10s} -> {p.choice:4s}  {lengths}")
