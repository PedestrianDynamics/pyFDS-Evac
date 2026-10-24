"""An exit or checkpoint with "sign": false is never discovered by sight (#376)."""

import csv
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from pyfds_evac.core.cognitive_map import expand_on_arrival, init_cognitive_map
from pyfds_evac.core.route_graph import StageEdge, StageGraph, StageNode
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


@pytest.mark.parametrize("vis_model", [_SeesEverything(), None])
def test_unsigned_exit_is_not_seen_from_the_spawn(vis_model):
    cmap = init_cognitive_map("S", _graph(), "discovery", vis_model, 0.0)
    if vis_model is not None:
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
    subprocess.run(
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
        check=False,
    )
    with exits_csv.open() as handle:
        chosen = [
            row["exit_id"]
            for row in csv.DictReader(handle)
            if row["exit_in_map"] == "True"
        ]
    assert chosen
    assert set(chosen) == {"exit_A_left"}
