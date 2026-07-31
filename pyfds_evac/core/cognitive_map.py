"""Per-agent cognitive map for discovery-mode routing (Spec 008 Phase 2)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AgentCognitiveMap:
    """Knowledge state of one agent about the stage graph.

    familiarity='full'      — agent knows the complete graph (trained staff).
    familiarity='discovery' — agent starts with spawn + visible neighbors
                              and expands as they move and see signs.
    """

    familiarity: str  # "full" | "discovery"
    known_nodes: set[str] = field(default_factory=set)
    known_edges: set[tuple[str, str]] = field(default_factory=set)


def init_cognitive_map(
    spawn_node: str,
    graph,
    familiarity: str,
    vis_model,
    time_s: float,
) -> AgentCognitiveMap:
    """Initialise a cognitive map for an agent spawning at *spawn_node*.

    'full'      → knows everything immediately.
    'discovery' → knows spawn node + any adjacent nodes whose sign is
                  visible from the spawn centroid at t=*time_s*.
    """
    if familiarity == "full":
        all_edges = {
            (e.source, e.target) for edges in graph.edges.values() for e in edges
        }
        return AgentCognitiveMap(
            familiarity="full",
            known_nodes=set(graph.nodes),
            known_edges=all_edges,
        )

    cmap = AgentCognitiveMap(familiarity="discovery", known_nodes={spawn_node})
    node = graph.nodes.get(spawn_node)
    if node is not None:
        _expand_visible(
            cmap, spawn_node, graph, vis_model, time_s, node.centroid_x, node.centroid_y
        )
    return cmap


def expand_on_arrival(
    cmap: AgentCognitiveMap,
    arrived_node: str,
    graph,
) -> None:
    """Expand map unconditionally when agent physically arrives at a node.

    The agent can now see all immediate neighbours (they are standing there).
    """
    if cmap.familiarity == "full":
        return
    cmap.known_nodes.add(arrived_node)
    for edge in graph.edges.get(arrived_node, []):
        cmap.known_nodes.add(edge.target)
        cmap.known_edges.add((edge.source, edge.target))


def expand_from_visibility(
    cmap: AgentCognitiveMap,
    current_node: str,
    graph,
    vis_model,
    time_s: float,
    ax: float,
    ay: float,
) -> None:
    """Expand map with adjacent nodes visible from (ax, ay) at *time_s*.

    When *vis_model* is None, all adjacent nodes are added unconditionally
    (no visibility data available → assume all neighbours are reachable).
    """
    if cmap.familiarity == "full":
        return
    _expand_visible(cmap, current_node, graph, vis_model, time_s, ax, ay)


def _expand_visible(
    cmap: AgentCognitiveMap,
    node_id: str,
    graph,
    vis_model,
    time_s: float,
    ax: float,
    ay: float,
) -> None:
    for edge in graph.edges.get(node_id, []):
        tgt = edge.target
        if vis_model is None or vis_model.node_is_visible(time_s, ax, ay, tgt):
            cmap.known_nodes.add(tgt)
            cmap.known_edges.add((edge.source, edge.target))


def cognitive_subgraph(cmap: AgentCognitiveMap, graph):
    """Return a StageGraph restricted to the agent's known nodes and edges.

    For 'full' agents returns the original graph unchanged.
    """
    if cmap.familiarity == "full":
        return graph

    from .route_graph import StageGraph

    sub = StageGraph()
    for node_id in cmap.known_nodes:
        if node_id in graph.nodes:
            sub.nodes[node_id] = graph.nodes[node_id]
    for src, tgt in cmap.known_edges:
        if src in sub.nodes and tgt in sub.nodes:
            for edge in graph.edges.get(src, []):
                if edge.target == tgt:
                    sub.edges.setdefault(src, []).append(edge)
                    break
    return sub


def nearest_frontier_target(
    cmap: AgentCognitiveMap, graph, source: str
) -> tuple[str, list[str]] | None:
    """Return the nearest known-but-unexplored node to head toward, if any.

    A frontier node is one already in the agent's cognitive map whose real
    outgoing edges (in the full *graph*) are not all known yet — a doorway
    the agent has seen but not been through. Used when no exit is reachable
    in the known subgraph: instead of standing still, the agent heads to the
    nearest such node, expanding its knowledge on arrival
    (see :func:`expand_on_arrival`) and re-evaluating from there.

    Returns None once every known node has been fully explored (no frontier
    left — a genuine dead end).
    """
    frontier = {
        node_id
        for node_id in cmap.known_nodes
        if any(
            (edge.source, edge.target) not in cmap.known_edges
            for edge in graph.edges.get(node_id, [])
        )
    }
    if not frontier:
        return None

    sub = cognitive_subgraph(cmap, graph)
    best: tuple[str, float, list[str]] | None = None
    for node_id in sorted(frontier):
        if node_id == source:
            continue
        result = sub.shortest_path_to(source, node_id)
        if result is None:
            continue
        cost, path = result
        if best is None or cost < best[1]:
            best = (node_id, cost, path)

    if best is None:
        return None
    node_id, _cost, path = best
    return node_id, path
