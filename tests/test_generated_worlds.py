"""Cognitive-map invariants on randomly generated worlds.

``scripts/generate_discovery_world.py`` produces discoverability-test decks
(open room, convex obstacles, signed checkpoints, exits hidden from the
spawn). The hand-built assets each pin one behaviour; these decks exercise
the whole discovery pipeline on geometry nobody curated, and the assertions
are invariants that must hold on *every* world:

* a cognitive map only ever grows;
* a node enters the map only through evidence -- the sign was legible from
  where the agent stood, or the agent physically arrived next to it;
* a ``full``-familiarity agent knows the complete graph from the start and
  never learns.

Coupled JuPedSim runs are not bit-reproducible under a fixed seed, so exact
trajectories and timelines are deliberately not asserted -- see
docs/testing-familiarity.md.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import sqlite3
from pathlib import Path

import pytest
from shapely import wkt as shapely_wkt

from pyfds_evac.core import load_scenario, run_scenario
from pyfds_evac.core.route_graph import RerouteConfig, RouteCostConfig
from pyfds_evac.core.visibility import VisibilityModel, extract_sign_descriptors

# Keeps a pathological stall from dragging the suite; the small worlds below
# evacuate far earlier, and every invariant holds on a truncated run too.
MAX_SIM_TIME_S = 120
# Nodes this close to the agent count as physical arrival, where the reveal
# is unconditional by design (spawn draw at t=0 likewise).
ARRIVAL_RADIUS_M = 1.2


def _generator():
    spec = importlib.util.spec_from_file_location(
        "gdw", Path("scripts/generate_discovery_world.py")
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _make_deck(tmp_path: Path, seed: int, hide_exits: bool) -> Path:
    gdw = _generator()
    args = argparse.Namespace(
        agents=1,
        obstacles=None,
        exits=2,
        stages=3,
        room_scale=1.0,
        hide_exits=hide_exits,
        random_sign_alpha=False,
    )
    walkable, config = gdw.generate_world(seed, args)
    config["config"]["simulation_settings"]["simulationParams"][
        "max_simulation_time"
    ] = MAX_SIM_TIME_S
    deck = tmp_path / f"world_{seed}"
    deck.mkdir()
    (deck / "geometry.wkt").write_text(walkable.wkt)
    (deck / "config.json").write_text(json.dumps(config))
    return deck


def _run(deck: Path, familiarity: float):
    cfg = json.loads((deck / "config.json").read_text())
    for dist in cfg["distributions"].values():
        dist["parameters"]["familiarity"] = familiarity
    (deck / "config.json").write_text(json.dumps(cfg))

    scenario = load_scenario(str(deck))
    walkable = shapely_wkt.loads((deck / "geometry.wkt").read_text().strip())
    vis = VisibilityModel.clear_air(walkable, extract_sign_descriptors(scenario.raw))
    result = run_scenario(
        scenario,
        seed=1234,
        reroute_config=RerouteConfig(
            reevaluation_interval_s=1.0, cost_config=RouteCostConfig()
        ),
        vis_model=vis,
        collect_cognitive_map_history=True,
    )
    history = list(result.cognitive_map_history or [])
    positions: dict[tuple[int, int], tuple[float, float]] = {}
    with sqlite3.connect(result.sqlite_file) as con:
        fps = float(
            con.execute("SELECT value FROM metadata WHERE key='fps'").fetchone()[0]
        )
        for aid, frame, x, y in con.execute(
            "SELECT id, frame, pos_x, pos_y FROM trajectory_data"
        ):
            positions[(int(aid), int(frame))] = (x, y)
    result.cleanup()
    centroids = _node_centroids(cfg)
    return cfg, vis, history, positions, fps, centroids


def _node_centroids(cfg: dict) -> dict[str, tuple[float, float]]:
    from shapely.geometry import Polygon

    out = {}
    for section in ("exits", "checkpoints", "distributions"):
        for node_id, data in (cfg.get(section) or {}).items():
            c = Polygon(data["coordinates"]).centroid
            out[node_id] = (c.x, c.y)
    return out


SEEDS = [(7, True), (11, False)]


@pytest.mark.parametrize("seed,hide_exits", SEEDS)
class TestDiscoveryInvariants:
    @pytest.fixture()
    def run(self, tmp_path, seed, hide_exits):
        deck = _make_deck(tmp_path, seed, hide_exits)
        return _run(deck, familiarity=0.0)

    def test_the_map_only_ever_grows(self, run):
        _, _, history, _, _, _ = run
        assert history, "a discovery run must record at least the spawn map"
        per_agent: dict[int, tuple[set, set]] = {}
        for event in history:
            nodes = set(event["known_nodes"])
            edges = set(event["known_edges"])
            prev = per_agent.get(event["agent_id"])
            if prev is not None:
                assert prev[0] <= nodes, "known nodes shrank"
                assert prev[1] <= edges, "known edges shrank"
            per_agent[event["agent_id"]] = (nodes, edges)

    def test_every_learned_node_has_evidence(self, run):
        """Sign legible from the agent's position, or physical arrival.

        This is the through-wall audit from PR #96 as a permanent test: a
        node appearing in the map with neither justification is exactly the
        leak that let one hallway arrival reveal rooms the agent had never
        seen.
        """
        _, vis, history, positions, fps, centroids = run
        prev: dict[int, set] = {}
        for event in history:
            new = set(event["known_nodes"]) - prev.get(event["agent_id"], set())
            prev[event["agent_id"]] = set(event["known_nodes"])
            if event["time_s"] == 0.0:
                continue  # spawn draw: seeded before the agent moved
            pos = positions.get((event["agent_id"], round(event["time_s"] * fps)))
            if pos is None:
                continue
            ax, ay = pos
            for node_id in new:
                cx, cy = centroids[node_id]
                if math.hypot(cx - ax, cy - ay) <= ARRIVAL_RADIUS_M:
                    continue
                assert vis.node_is_visible(event["time_s"], ax, ay, node_id), (
                    f"{node_id} learned at t={event['time_s']} without "
                    f"line-of-sight evidence from ({ax:.1f},{ay:.1f})"
                )


@pytest.mark.parametrize("seed,hide_exits", SEEDS)
def test_a_full_agent_knows_everything_and_never_learns(tmp_path, seed, hide_exits):
    deck = _make_deck(tmp_path, seed, hide_exits)
    _, _, history, _, _, centroids = _run(deck, familiarity=1.0)
    events_per_agent: dict[int, int] = {}
    for event in history:
        events_per_agent[event["agent_id"]] = (
            events_per_agent.get(event["agent_id"], 0) + 1
        )
        assert set(event["known_nodes"]) == set(centroids), (
            "a full-familiarity map must hold every node"
        )
    assert all(count == 1 for count in events_per_agent.values()), (
        "a full map never changes, so at most its initial recording exists"
    )
