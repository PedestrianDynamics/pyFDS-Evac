"""Tier A verification of the per-agent cognitive map (SPEC 012 section 4).

The cognitive-map logic is exercised independently of fdsvismap via a
deterministic fake visibility model driven by a configurable allow-set,
so the map behaviour is asserted against hand-computed expected sets.
"""

from __future__ import annotations

from pyfds_evac.core.cognitive_map import (
    cognitive_subgraph,
    expand_from_visibility,
    expand_on_arrival,
    init_cognitive_map,
)
from pyfds_evac.core.route_graph import StageEdge, StageGraph, StageNode


class FakeVisibility:
    """Deterministic stand-in for VisibilityModel.

    ``node_is_visible`` returns True only for node IDs in *allow*.  An empty
    allow-set makes every node invisible; passing all node IDs makes every
    node visible.  The signature matches the positional call in
    ``cognitive_map._expand_visible``: ``(time_s, x, y, node_id)``.
    """

    def __init__(self, allow: set[str]) -> None:
        self.allow = set(allow)

    def node_is_visible(self, time_s: float, x: float, y: float, node_id: str) -> bool:
        del time_s, x, y  # position is irrelevant; visibility is driven by allow-set
        return node_id in self.allow


def _build_graph() -> StageGraph:
    """Branched 5-node graph; every node is reachable from spawn ``S``.

    Topology (directed)::

        S -> A -> C -> E
        S -> B -> E

    Two branches out of S and two paths into E make "discovery converges to
    the full reachable set" a non-trivial assertion: a single linear walk
    discovers all nodes but misses the (B, E) edge unless B is expanded too.
    """
    graph = StageGraph()
    graph.nodes = {
        "S": StageNode("S", 0.0, 0.0, "distribution"),
        "A": StageNode("A", 1.0, 1.0, "checkpoint"),
        "B": StageNode("B", 1.0, -1.0, "checkpoint"),
        "C": StageNode("C", 2.0, 1.0, "checkpoint"),
        "E": StageNode("E", 3.0, 0.0, "exit"),
    }
    graph.edges = {
        "S": [
            StageEdge("S", "A", 1.0),
            StageEdge("S", "B", 1.0),
        ],
        "A": [StageEdge("A", "C", 1.0)],
        "B": [StageEdge("B", "E", 1.0)],
        "C": [StageEdge("C", "E", 1.0)],
    }
    return graph


_ALL_NODES = {"S", "A", "B", "C", "E"}
_ALL_EDGES = {("S", "A"), ("S", "B"), ("A", "C"), ("B", "E"), ("C", "E")}


def _expand_at(graph: StageGraph, cmap, vis_model, node_id: str) -> None:
    """Expand visibility from a node's own centroid (agent standing there)."""
    node = graph.nodes[node_id]
    expand_from_visibility(
        cmap, node_id, graph, vis_model, 0.0, node.centroid_x, node.centroid_y
    )


# A4.1 -- full familiarity knows the entire graph and subgraph is identity.


def test_full_knows_all_nodes_and_edges() -> None:
    graph = _build_graph()
    cmap = init_cognitive_map("S", graph, "full", vis_model=None, time_s=0.0)

    assert cmap.familiarity == "full"
    assert cmap.known_nodes == _ALL_NODES
    assert cmap.known_edges == _ALL_EDGES


def test_full_subgraph_returns_original_graph_object() -> None:
    graph = _build_graph()
    cmap = init_cognitive_map("S", graph, "full", vis_model=None, time_s=0.0)

    assert cognitive_subgraph(cmap, graph) is graph


# A4.2 -- discovery with an all-visible fake converges to the full set.


def test_discovery_all_visible_known_at_spawn() -> None:
    graph = _build_graph()
    vis_model = FakeVisibility(_ALL_NODES)

    cmap = init_cognitive_map("S", graph, "discovery", vis_model, time_s=0.0)

    # At spawn the agent knows S plus its visible neighbours A and B.
    assert cmap.known_nodes == {"S", "A", "B"}
    assert cmap.known_edges == {("S", "A"), ("S", "B")}


def test_discovery_all_visible_converges_via_visibility() -> None:
    graph = _build_graph()
    vis_model = FakeVisibility(_ALL_NODES)
    cmap = init_cognitive_map("S", graph, "discovery", vis_model, time_s=0.0)

    # Step to A: C becomes newly known (incremental discovery, not endpoint).
    _expand_at(graph, cmap, vis_model, "A")
    assert "C" in cmap.known_nodes
    assert ("A", "C") in cmap.known_edges
    assert "E" not in cmap.known_nodes

    # Expanding at B and C closes the remaining edges into the exit.
    _expand_at(graph, cmap, vis_model, "B")
    _expand_at(graph, cmap, vis_model, "C")

    assert cmap.known_nodes == _ALL_NODES
    assert cmap.known_edges == _ALL_EDGES


def test_discovery_converges_via_arrival() -> None:
    graph = _build_graph()
    vis_model = FakeVisibility(_ALL_NODES)
    cmap = init_cognitive_map("S", graph, "discovery", vis_model, time_s=0.0)

    # Walking S -> A -> B -> C and arriving at each node converges to full.
    for node_id in ("A", "B", "C"):
        expand_on_arrival(cmap, node_id, graph)

    assert cmap.known_nodes == _ALL_NODES
    assert cmap.known_edges == _ALL_EDGES


# A4.3 -- discovery with a nothing-visible fake stays at the spawn node.


def test_discovery_nothing_visible_known_at_spawn_only() -> None:
    graph = _build_graph()
    vis_model = FakeVisibility(set())

    cmap = init_cognitive_map("S", graph, "discovery", vis_model, time_s=0.0)

    assert cmap.known_nodes == {"S"}
    assert cmap.known_edges == set()


def test_discovery_nothing_visible_visibility_adds_nothing() -> None:
    graph = _build_graph()
    vis_model = FakeVisibility(set())
    cmap = init_cognitive_map("S", graph, "discovery", vis_model, time_s=0.0)

    _expand_at(graph, cmap, vis_model, "S")

    assert cmap.known_nodes == {"S"}
    assert cmap.known_edges == set()


def test_discovery_nothing_visible_arrival_adds_neighbours_unconditionally() -> None:
    graph = _build_graph()
    vis_model = FakeVisibility(set())
    cmap = init_cognitive_map("S", graph, "discovery", vis_model, time_s=0.0)

    # Physical arrival ignores visibility: neighbours are added regardless.
    expand_on_arrival(cmap, "S", graph)

    assert cmap.known_nodes == {"S", "A", "B"}
    assert cmap.known_edges == {("S", "A"), ("S", "B")}


# A4.4 -- discovery subgraph is restricted to the known node/edge set.


def test_discovery_subgraph_restricts_to_known_set() -> None:
    graph = _build_graph()
    vis_model = FakeVisibility(_ALL_NODES)
    cmap = init_cognitive_map("S", graph, "discovery", vis_model, time_s=0.0)
    _expand_at(graph, cmap, vis_model, "A")

    sub = cognitive_subgraph(cmap, graph)

    # Known: S, A, B, C and edges S->A, S->B, A->C.  E and edges into E excluded.
    assert set(sub.nodes) == {"S", "A", "B", "C"}
    assert "E" not in sub.nodes

    sub_edges = {(e.source, e.target) for edges in sub.edges.values() for e in edges}
    assert sub_edges == {("S", "A"), ("S", "B"), ("A", "C")}

    # No node lies outside the known set and no edge dangles to an unknown node.
    assert all(nid in cmap.known_nodes for nid in sub.nodes)
    for src, tgt in sub_edges:
        assert src in sub.nodes
        assert tgt in sub.nodes
