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
    """Expand map with adjacent nodes visible from (ax, ay) at *time_s*."""
    if cmap.familiarity == "full" or vis_model is None:
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
