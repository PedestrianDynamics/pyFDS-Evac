"""Each agent's known exits over time, with how each was learnt (#943).

``ScenarioResult.knowledge_history`` has one row per exit an agent came to
know, the exits known at spawn included. Before it, an exit seen at spawn
left no trace: ``learned_exit`` only marks a switch, and an exit learnt
inside ``init_cognitive_map`` is known before the first choice.
"""

from __future__ import annotations

import csv
import json
import random
import shutil
from pathlib import Path

import pytest
from shapely import wkt as shapely_wkt

from pyfds_evac.core import load_scenario, run_scenario
from pyfds_evac.core.cognitive_map import (
    LEARN_ARRIVAL,
    LEARN_ENTRANCE,
    LEARN_FAMILIARITY,
    LEARN_LOOK,
    LEARN_SIGHT,
    expand_from_visibility,
    expand_on_arrival,
    init_cognitive_map,
)
from pyfds_evac.core.route_graph import (
    RerouteConfig,
    RouteCostConfig,
    StageEdge,
    StageGraph,
    StageNode,
)
from pyfds_evac.core.run_outputs import _write_knowledge_history_csv
from pyfds_evac.core.visibility import VisibilityModel, extract_sign_descriptors

ASSET = Path("assets/blind_spawn_discovery")


class _Sees:
    """A visibility model under which only *visible* nodes are seen."""

    def __init__(self, *visible):
        self.visible = set(visible)

    def node_is_visible(self, time, x, y, node_id):
        return node_id in self.visible


def _graph():
    """S next to three exits; C, one hop on, next to a fourth."""
    nodes = {
        "S": StageNode("S", 0.0, 0.0, "distribution"),
        "A": StageNode("A", 10.0, 0.0, "exit"),
        "B": StageNode("B", -10.0, 0.0, "exit"),
        "D": StageNode("D", 0.0, 10.0, "exit"),
        "C": StageNode("C", 0.0, -10.0, "checkpoint"),
        "F": StageNode("F", 0.0, -20.0, "exit"),
    }

    def edge(a, b):
        return StageEdge(source=a, target=b, weight=10.0)

    edges = {
        "S": [edge("S", "A"), edge("S", "B"), edge("S", "D"), edge("S", "C")],
        "C": [edge("C", "S"), edge("C", "F")],
    }
    return StageGraph(nodes=nodes, edges=edges)


def _events(cmap):
    return {exit_id: (time_s, how) for time_s, exit_id, how in cmap.exit_events}


def test_spawn_knowledge_is_labelled_by_its_step():
    """Entrance, then the familiarity draw, then sight: each exit once."""
    graph = _graph()
    cmap = init_cognitive_map(
        "S",
        graph,
        1.0 - 1e-12,  # every draw hits, but not the 'full' tier
        _Sees("A", "B", "D"),
        3.0,
        rng=random.Random(0),
        entrance="A",
    )
    events = _events(cmap)
    assert events["A"] == (3.0, LEARN_ENTRANCE)
    assert {events[e][1] for e in ("B", "D", "F")} == {LEARN_FAMILIARITY}
    assert len(cmap.exit_events) == 4


def test_an_exit_seen_at_spawn_is_recorded():
    """The #939 spike: learnt inside init_cognitive_map, so never logged."""
    cmap = init_cognitive_map("S", _graph(), "discovery", _Sees("B"), 0.0)
    assert cmap.exit_events == [(0.0, "B", LEARN_SIGHT)]


def test_full_familiarity_knows_every_exit_from_its_draw():
    cmap = init_cognitive_map("S", _graph(), "full", None, 2.0)
    assert sorted(cmap.exit_events) == [
        (2.0, e, LEARN_FAMILIARITY) for e in ("A", "B", "D", "F")
    ]


def test_later_learning_is_labelled_by_how():
    graph = _graph()
    cmap = init_cognitive_map("S", graph, "discovery", None, 0.0, no_visibility=True)
    assert cmap.exit_events == []
    expand_from_visibility(cmap, "S", graph, _Sees("D"), 5.0, 0.0, 0.0)
    expand_on_arrival(cmap, "S", graph, _Sees("A", "C"), 6.0, 0.0, 0.0)
    expand_on_arrival(cmap, "C", graph, None, 7.0, from_node="S", how=LEARN_LOOK)
    expand_on_arrival(cmap, "S", graph, None, 8.0)
    assert cmap.exit_events == [
        (5.0, "D", LEARN_SIGHT),
        (6.0, "A", LEARN_ARRIVAL),
        (7.0, "F", LEARN_LOOK),
        (8.0, "B", LEARN_ARRIVAL),
    ]


def _run(tmp_path: Path):
    bundle = tmp_path / "discovery"
    bundle.mkdir()
    shutil.copy(ASSET / "config_discovery.json", bundle / "config.json")
    shutil.copy(ASSET / "geometry.wkt", bundle / "geometry.wkt")
    scenario = load_scenario(str(bundle))
    walkable = shapely_wkt.loads((bundle / "geometry.wkt").read_text().strip())
    vis = VisibilityModel.clear_air(
        walkable, extract_sign_descriptors(scenario.raw), cell_size_m=0.25
    )
    return run_scenario(
        scenario,
        seed=420,
        reroute_config=RerouteConfig(
            reevaluation_interval_s=1.0, cost_config=RouteCostConfig()
        ),
        vis_model=vis,
        collect_cognitive_map_history=True,
    )


@pytest.fixture(scope="module")
def result(tmp_path_factory):
    run = _run(tmp_path_factory.mktemp("knowledge"))
    yield run
    run.cleanup()


def test_rows_match_the_cognitive_map_history(result):
    """The exits of each agent's last recorded map are exactly its rows."""
    rows = result.knowledge_history
    assert rows
    assert rows == sorted(rows, key=lambda r: (r["time_s"], r["agent_id"]))
    per_agent: dict[int, list[str]] = {}
    for row in rows:
        per_agent.setdefault(row["agent_id"], []).append(row["exit_id"])
    for exits in per_agent.values():
        assert len(exits) == len(set(exits))
    exit_ids = set(json.loads((ASSET / "config_discovery.json").read_text())["exits"])
    last_map = {}
    for event in result.cognitive_map_history:
        last_map[event["agent_id"]] = event
    for agent_id, event in last_map.items():
        known = set(event["known_nodes"]) & exit_ids
        assert set(per_agent.get(agent_id, [])) == known, agent_id


def test_every_exit_left_through_in_the_map_has_a_row(result):
    known = {(r["agent_id"], r["exit_id"]) for r in result.knowledge_history}
    for row in result.exit_history:
        if row["exit_in_map"]:
            assert (row["agent_id"], row["exit_id"]) in known, row


def test_csv_columns(tmp_path, result):
    path = tmp_path / "knowledge.csv"
    _write_knowledge_history_csv(result.knowledge_history, str(path))
    with path.open() as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
    assert reader.fieldnames == ["time_s", "agent_id", "exit_id", "how"]
    assert len(rows) == len(result.knowledge_history)


def test_none_unless_collected(tmp_path):
    bundle = tmp_path / "b"
    bundle.mkdir()
    shutil.copy(ASSET / "config_discovery.json", bundle / "config.json")
    shutil.copy(ASSET / "geometry.wkt", bundle / "geometry.wkt")
    run = run_scenario(
        load_scenario(str(bundle)),
        seed=1,
        reroute_config=RerouteConfig(cost_config=RouteCostConfig()),
    )
    try:
        assert run.knowledge_history is None
    finally:
        run.cleanup()
