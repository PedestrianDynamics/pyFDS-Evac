"""An exit or checkpoint with "sign": false is never discovered by sight (#376)."""

import csv
import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import jupedsim as jps
import pytest
from shapely import wkt

from pyfds_evac.core.cognitive_map import (
    expand_from_visibility,
    expand_on_arrival,
    init_cognitive_map,
    stranded_distributions,
)
from pyfds_evac.core.route_graph import StageEdge, StageGraph, StageNode
from pyfds_evac.core.scenario import load_scenario
from pyfds_evac.core.simulation_init import initialize_simulation_from_json
from pyfds_evac.core.visibility import extract_sign_descriptors

SQUARE = [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]]
ROOT = Path(__file__).resolve().parents[1]


class _SeesEverything:
    """A visibility model under which every sign is legible."""

    def node_is_visible(self, time, x, y, node_id):
        return True


def _graph():
    nodes = {
        "S": StageNode("S", 0.0, 0.0, "distribution"),
        "E_signed": StageNode("E_signed", 10.0, 0.0, "exit"),
        "E_unsigned": StageNode("E_unsigned", -10.0, 0.0, "exit", signed=False),
    }
    edges = {
        "S": [
            StageEdge(source="S", target="E_signed", weight=10.0),
            StageEdge(source="S", target="E_unsigned", weight=10.0),
        ]
    }
    return StageGraph(nodes=nodes, edges=edges)


def test_sign_false_gets_no_sign_descriptor():
    raw = {
        "exits": {
            "off": {"coordinates": SQUARE, "sign": False},
            "null": {"coordinates": SQUARE, "sign": None},
            "missing": {"coordinates": SQUARE},
        },
        "waypoints": {"wp": {"coordinates": SQUARE, "sign": False}},
    }
    descriptors = extract_sign_descriptors(raw)
    assert set(descriptors) == {"null", "missing"}
    assert descriptors["null"] == descriptors["missing"]


def test_stage_nodes_are_signed_by_default():
    assert StageNode("X", 0.0, 0.0, "exit").signed is True


def test_unsigned_exit_is_not_seen_from_the_spawn():
    cmap = init_cognitive_map("S", _graph(), "discovery", _SeesEverything(), 0.0)
    assert "E_signed" in cmap.known_nodes
    assert "E_unsigned" not in cmap.known_nodes


@pytest.mark.parametrize("vis_model", [_SeesEverything(), None])
def test_unsigned_exit_is_not_revealed_on_arrival_next_to_it(vis_model):
    graph = _graph()
    cmap = init_cognitive_map("S", graph, "discovery", None, 0.0, no_visibility=True)
    expand_on_arrival(cmap, "S", graph, vis_model, 0.0, 0.0, 0.0)
    assert "E_signed" in cmap.known_nodes
    assert "E_unsigned" not in cmap.known_nodes


def test_familiarity_and_entrance_still_teach_an_unsigned_exit():
    graph = _graph()
    full = init_cognitive_map("S", graph, "full", None, 0.0)
    assert "E_unsigned" in full.known_nodes
    entered = init_cognitive_map(
        "S", graph, "discovery", _SeesEverything(), 0.0, entrance="E_unsigned"
    )
    assert "E_unsigned" in entered.known_nodes


def test_arriving_on_an_unsigned_node_learns_it():
    graph = _graph()
    cmap = init_cognitive_map("S", graph, "discovery", None, 0.0, no_visibility=True)
    expand_on_arrival(cmap, "E_unsigned", graph, None, 0.0, -10.0, 0.0, from_node="S")
    assert "E_unsigned" in cmap.known_nodes


def test_unsigned_exit_is_not_used_by_discovery_agents(tmp_path):
    """t_junction discovery: exit B is the one every agent takes, until its sign is off."""
    deck = tmp_path / "t_junction"
    shutil.copytree(ROOT / "assets" / "t_junction", deck)
    config = json.loads((deck / "config_discovery.json").read_text())
    config["exits"]["exit_B_right"]["sign"] = False
    (deck / "config_nosign.json").write_text(json.dumps(config))
    exits_csv = tmp_path / "exits.csv"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pyfds_evac.cli",
            "--scenario",
            str(deck / "config_nosign.json"),
            "--seed",
            "1",
            "--output-exit-history",
            str(exits_csv),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    # Exit 2 is the usual outcome: the 300 s limit ends the run incomplete.
    assert result.returncode in (0, 2), result.stderr[-2000:]
    with exits_csv.open() as handle:
        chosen = [
            row["exit_id"]
            for row in csv.DictReader(handle)
            if row["exit_in_map"] == "True"
        ]
    assert chosen
    assert set(chosen) == {"exit_A_left"}


def _gateway_graph(gateway_signed):
    nodes = {
        "S": StageNode("S", 0.0, 0.0, "distribution"),
        "CP": StageNode("CP", 5.0, 0.0, "checkpoint", signed=gateway_signed),
        "E": StageNode("E", 10.0, 0.0, "exit"),
    }
    edges = {
        "S": [StageEdge(source="S", target="CP", weight=5.0)],
        "CP": [StageEdge(source="CP", target="E", weight=5.0)],
    }
    return StageGraph(nodes=nodes, edges=edges)


@pytest.mark.parametrize("vis_model", [_SeesEverything(), None])
def test_unsigned_gateway_keeps_the_exit_behind_it_unknown(vis_model):
    """Nothing is learnt past a node nobody can see: sight and contact stop there."""
    graph = _gateway_graph(gateway_signed=False)
    cmap = init_cognitive_map("S", graph, "discovery", vis_model, 0.0)
    expand_from_visibility(cmap, "S", graph, vis_model, 0.0, 0.0, 0.0)
    expand_on_arrival(cmap, "S", graph, vis_model, 0.0, 0.0, 0.0)
    assert cmap.known_nodes == {"S"}


def test_arriving_on_an_unsigned_gateway_reveals_the_exit_behind_it():
    graph = _gateway_graph(gateway_signed=False)
    cmap = init_cognitive_map("S", graph, "discovery", None, 0.0, no_visibility=True)
    expand_on_arrival(cmap, "CP", graph, None, 0.0, 5.0, 0.0, from_node="S")
    assert "E" in cmap.known_nodes


def _raw(no_known_exit="explore", familiarity="discovery", **params):
    parameters = {
        "familiarity": familiarity,
        "no_known_exit": no_known_exit,
        **params,
    }
    return {"distributions": {"S": {"parameters": parameters}}}


def test_a_spawn_behind_an_unsigned_gateway_is_reported_stranded():
    assert stranded_distributions(_gateway_graph(False), _raw()) == ["S"]


@pytest.mark.parametrize(
    "graph, raw",
    [
        pytest.param(_gateway_graph(True), _raw(), id="signed gateway"),
        pytest.param(_graph(), _raw(), id="a signed exit in reach"),
        pytest.param(
            _gateway_graph(False), _raw("default_route"), id="default route walks on"
        ),
        pytest.param(
            _gateway_graph(False), _raw(familiarity="full"), id="full familiarity"
        ),
        pytest.param(
            _gateway_graph(False), _raw(entrance="E"), id="entrance teaches the exit"
        ),
    ],
)
def test_other_spawns_are_not_reported_stranded(graph, raw):
    assert stranded_distributions(graph, raw) == []


def test_every_exit_unsigned_strands_an_explore_spawn():
    graph = _graph()
    graph.nodes["E_signed"] = StageNode("E_signed", 10.0, 0.0, "exit", signed=False)
    assert stranded_distributions(graph, _raw()) == ["S"]


def _initialised_graph(config, tmp_path, walkable):
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    simulation = jps.Simulation(model=jps.CollisionFreeSpeedModel(), geometry=walkable)
    _, _, _, info = initialize_simulation_from_json(
        str(path),
        simulation,
        SimpleNamespace(polygon=walkable),
        seed=1,
        model_type="CollisionFreeSpeedModel",
        global_parameters=SimpleNamespace(),
    )
    return StageGraph.from_scenario(info["direct_steering_info"], config["transitions"])


@pytest.mark.parametrize("with_journeys", [True, False])
def test_both_initialisation_paths_mark_unsigned_nodes(with_journeys, tmp_path):
    """The journey set-up and the fallback set-up each carry "sign": false."""
    scenario = load_scenario(
        str(ROOT / "assets" / "t_junction" / "config_discovery.json")
    )
    walkable = wkt.loads(scenario.walkable_area_wkt)
    config = json.loads(json.dumps(scenario.raw))
    config["exits"]["exit_A_left"]["sign"] = False
    config["exits"]["exit_B_right"]["sign"] = None
    config["checkpoints"]["jps-checkpoints_0"]["sign"] = False
    if not with_journeys:
        config["journeys"] = {}
        config["transitions"] = []
    graph = _initialised_graph(config, tmp_path, walkable)
    assert graph.nodes["exit_A_left"].signed is False
    assert graph.nodes["exit_B_right"].signed is True
    assert graph.nodes["jps-checkpoints_0"].signed is False
    config["checkpoints"]["jps-checkpoints_0"].pop("sign")
    graph = _initialised_graph(config, tmp_path, walkable)
    assert graph.nodes["jps-checkpoints_0"].signed is True
