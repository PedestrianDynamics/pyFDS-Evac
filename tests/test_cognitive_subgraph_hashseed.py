"""Exact route ties do not depend on the hash seed (#199).

``cognitive_subgraph`` used to fill the agent's subgraph in the iteration
order of the ``known_nodes`` and ``known_edges`` sets. String hashes are
randomised per process, so two routes tied on every ranking key came out in
a different order from one run to the next, and with them the exit the
agent chose.
"""

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# Four exits 10 m east, north, west and south of the agent in clear air:
# every route ties on optical depth, travel time and path length, so only the
# subgraph's iteration order can separate them.
_RANK_TIED_EXITS = """
from pyfds_evac.core.cognitive_map import AgentCognitiveMap
from pyfds_evac.core.route_graph import (
    RouteCostConfig, StageEdge, StageGraph, StageNode, rank_routes,
)
from pyfds_evac.core.smoke_speed import ConstantExtinctionField

points = {"exit_e": (10.0, 0.0), "exit_n": (0.0, 10.0),
          "exit_w": (-10.0, 0.0), "exit_s": (0.0, -10.0)}
exits = sorted(points)
nodes = {"O": StageNode("O", 0.0, 0.0, "distribution")}
nodes.update({e: StageNode(e, *xy, "exit") for e, xy in points.items()})
graph = StageGraph(nodes=nodes)
graph.edges = {
    "O": [
        StageEdge("O", e, 10.0, [(0.0, 0.0), points[e]]) for e in exits
    ]
}
cmap = AgentCognitiveMap(
    familiarity="discovery",
    known_nodes={"O", *exits},
    known_edges={("O", e) for e in exits},
)
for model in ("gate", "additive"):
    config = RouteCostConfig(cost_model=model, anticipate=False, w_queue=0.0)
    ranked = rank_routes(
        graph, "O", 0.0, 0.0, ConstantExtinctionField(0.0), None, config,
        cognitive_map=cmap,
    )
    print(model, [rc.exit_id for rc in ranked])
"""


def _rank_under(hash_seed: str) -> str:
    env = {**os.environ, "PYTHONHASHSEED": hash_seed, "PYTHONPATH": str(REPO)}
    done = subprocess.run(
        [sys.executable, "-c", _RANK_TIED_EXITS],
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    return done.stdout


# Exact ties go to the alphabetically first exit.
_EXPECTED = (
    "gate ['exit_e', 'exit_n', 'exit_s', 'exit_w']\n"
    "additive ['exit_e', 'exit_n', 'exit_s', 'exit_w']\n"
)


def test_tied_routes_rank_the_same_under_every_hash_seed():
    outputs = {_rank_under(seed) for seed in ("0", "1", "7", "42", "12345")}
    assert outputs == {_EXPECTED}
