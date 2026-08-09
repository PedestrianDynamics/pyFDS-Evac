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
    # Nodes the agent has physically stood on. A visited node is a closed
    # frontier: standing there taught the agent everything that position will
    # ever teach, however little that was (see nearest_frontier_target).
    visited_nodes: set[str] = field(default_factory=set)


def familiarity_probability(value) -> float:
    """Normalise a familiarity setting to the probability an exit is known.

    Accepts the historical names as well as a number, so existing scenarios and
    the scalar form can coexist:

        "full"      -> 1.0     the agent knows the whole building
        "discovery" -> 0.0     it knows only what it can perceive
        0.0 .. 1.0  -> itself  the probability each exit is in its map at t=0

    A binary cannot express a real crowd. At The Station 29.2 % of patrons were
    there for the first time and about two dozen were regulars -- a gradient.
    """
    if isinstance(value, str):
        if value == "full":
            return 1.0
        if value == "discovery":
            return 0.0
        raise ValueError(
            f"unknown familiarity {value!r}: expected 'full', 'discovery', "
            "or a probability in [0, 1]"
        )
    probability = float(value)
    if not 0.0 <= probability <= 1.0:
        raise ValueError(
            f"familiarity {probability} is outside [0, 1]; it is the probability "
            "that an exit is already known"
        )
    return probability


def _learn_route_to(cmap: AgentCognitiveMap, graph, source: str, target: str) -> bool:
    """Add the shortest path to *target*, nodes and edges, to the map.

    Knowing an exit has to mean knowing how to reach it.  Routing runs on the
    subgraph of known nodes *and* known edges, so an exit added on its own would
    sit in the map unreachable -- present, and useless.
    """
    paths = graph.shortest_paths_to_exits(source)
    entry = paths.get(target)
    if entry is None:
        return False
    _cost, path = entry
    for node_id in path:
        cmap.known_nodes.add(node_id)
    for a, b in zip(path, path[1:]):
        cmap.known_edges.add((a, b))
    return True


def init_cognitive_map(
    spawn_node: str,
    graph,
    familiarity,
    vis_model,
    time_s: float,
    *,
    rng=None,
    entrance: str | None = None,
    no_visibility: bool = False,
) -> AgentCognitiveMap:
    """Initialise a cognitive map for an agent spawning at *spawn_node*.

    *familiarity* is the probability that each exit is already known (see
    :func:`familiarity_probability`); 1.0 is the historical ``full`` tier and
    0.0 the ``discovery`` one.

    *entrance* names the exit the agent walked in through, which it knows
    whatever its familiarity.  At The Station every patron entered by the front
    door, and that one fact is the mechanism behind the crush: the exit everyone
    knew was the one everyone went back to.

    *rng* makes the draw reproducible; without one no probabilistic knowledge is
    added, so a caller that forgets it gets the conservative result rather than
    an irreproducible one.  *no_visibility* skips the perception step, for
    callers testing the initial draw alone.
    """
    probability = familiarity_probability(familiarity)

    if probability >= 1.0:
        all_edges = {
            (e.source, e.target) for edges in graph.edges.values() for e in edges
        }
        return AgentCognitiveMap(
            familiarity="full",
            known_nodes=set(graph.nodes),
            known_edges=all_edges,
        )

    cmap = AgentCognitiveMap(
        familiarity="discovery",
        known_nodes={spawn_node},
        visited_nodes={spawn_node},
    )

    if entrance is not None and entrance in graph.nodes:
        _learn_route_to(cmap, graph, spawn_node, entrance)

    if rng is not None and probability > 0.0:
        for exit_id in graph.exit_nodes():
            if exit_id not in cmap.known_nodes and rng.random() < probability:
                _learn_route_to(cmap, graph, spawn_node, exit_id)

    node = graph.nodes.get(spawn_node)
    if node is not None and not no_visibility:
        _expand_visible(
            cmap, spawn_node, graph, vis_model, time_s, node.centroid_x, node.centroid_y
        )
    return cmap


def _learn_edge(cmap: AgentCognitiveMap, graph, source: str, target: str) -> None:
    """Learn an edge, and its reverse when the graph has one.

    Route edges are directed, but knowledge of a corridor is not: an agent
    that knows the leg A->B can walk it back. The reverse is added only when
    the graph offers it -- exits are terminal and spawn areas have no inbound
    edges -- so routing invariants hold. Without this, a discovery agent whose
    arrival at a node reveals nothing new holds a known subgraph with no
    outgoing edge, and :func:`nearest_frontier_target` cannot route it back
    out of a dead end it can physically leave.
    """
    cmap.known_edges.add((source, target))
    if any(edge.target == source for edge in graph.edges.get(target, [])):
        cmap.known_edges.add((target, source))


def expand_on_arrival(
    cmap: AgentCognitiveMap,
    arrived_node: str,
    graph,
    vis_model=None,
    time_s: float = 0.0,
    ax: float | None = None,
    ay: float | None = None,
) -> None:
    """Expand map when the agent physically arrives at a node.

    Standing on a node does not mean seeing past its walls: auto-wired decks
    keep nodes graph-adjacent to stages in other rooms, so with a visibility
    model and a position each neighbour is revealed only if visible from
    (ax, ay) -- the same gate perception uses in :func:`_expand_visible`.
    Without one there is no evidence either way, and every neighbour is
    revealed so an unperceiving agent can still progress hop by hop.
    """
    if cmap.familiarity == "full":
        return
    cmap.known_nodes.add(arrived_node)
    cmap.visited_nodes.add(arrived_node)
    for edge in graph.edges.get(arrived_node, []):
        if (
            vis_model is not None
            and ax is not None
            and ay is not None
            and not vis_model.node_is_visible(time_s, ax, ay, edge.target)
        ):
            continue
        cmap.known_nodes.add(edge.target)
        _learn_edge(cmap, graph, edge.source, edge.target)


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

    When *vis_model* is None nothing is added; see :func:`_expand_visible`.
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
    """Add the neighbours of *node_id* the agent can see from (ax, ay).

    Without a visibility model there is no evidence the agent can see anything,
    so nothing is added. Graph adjacency is not a stand-in: when the scenario
    declares no transitions the graph is auto-wired spawn-to-every-unblocked
    stage, so treating a neighbour as seen would hand every discovery agent most
    of the building's exits at t=0 and make ``familiarity`` inert in every run
    without a visibility cache. Perception is not the only way a map grows --
    :func:`expand_on_arrival` still reveals visible neighbours on physical
    arrival (and, without a visibility model, all of them), so an agent is
    never stranded by this.
    """
    if vis_model is None:
        return
    for edge in graph.edges.get(node_id, []):
        tgt = edge.target
        if vis_model.node_is_visible(time_s, ax, ay, tgt):
            cmap.known_nodes.add(tgt)
            _learn_edge(cmap, graph, edge.source, edge.target)


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
    cmap: AgentCognitiveMap,
    graph,
    source: str,
    agent_position: tuple[float, float] | None = None,
) -> tuple[str, list[str]] | None:
    """Return the nearest known-but-unvisited node to head toward, if any.

    A frontier node is one already in the agent's cognitive map that the
    agent has never physically stood on — a doorway it has seen but not been
    through. Used when no exit is reachable in the known subgraph: instead of
    standing still, the agent heads to the nearest such node, expanding its
    knowledge on arrival (see :func:`expand_on_arrival`) and re-evaluating
    from there.

    Visiting closes a frontier even when arrival taught nothing: with
    visibility-gated arrival a node can hold unknown edges forever (its
    neighbours' signs face away), and an edges-based frontier keeps offering
    such nodes. Two of them adjacent to each other then trap the explorer —
    the nearest frontier from each is the other — while genuinely unvisited
    nodes wait. Consuming one unvisited node per hop makes exploration
    terminate.

    With *agent_position* the first leg is measured from where the agent
    actually stands rather than from *source*'s centroid, the same substitution
    :func:`~pyfds_evac.core.route_graph._position_aware_length` makes when
    ranking exits. Without it, every agent at a node computes identical costs,
    so a crowd facing two equidistant frontiers sends all of itself through one
    of them — see issue #68 and ``assets/blind_spawn_discovery``, where 30
    agents spread across a 20 m hall all used the same door.

    Exact ties still break on ``sorted(frontier)``, so two agents standing in
    the same place make the same choice.

    Returns None once every known node has been fully explored (no frontier
    left — a genuine dead end).
    """
    frontier = cmap.known_nodes - cmap.visited_nodes
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
        cost = _cost_from_agent(graph, path, cost, agent_position)
        if best is None or cost < best[1]:
            best = (node_id, cost, path)

    if best is None:
        return None
    node_id, _cost, path = best
    return node_id, path


def wander_target(
    cmap: AgentCognitiveMap,
    graph,
    source: str,
    step: int,
) -> tuple[str, list[str]] | None:
    """The *step*-th stop of a patrol over the nodes the agent knows.

    Called when the frontier is exhausted: every known node is visited and
    no exit is reachable, so there is nowhere the agent *knows* to look.
    Standing still would end discovery, but walking does not: perception
    runs from the agent's position, and sign legibility depends on that
    position (distance and the readable half-plane), so a leg between two
    known nodes can make a sign readable that never was from either node.

    The patrol is a deterministic rotation through the known nodes, not a
    random draw: it needs no seeded state, reproduces under a fixed run
    seed, and covers every known leg instead of favouring some. Returns
    None when no other known node is reachable -- an agent alone on its
    spawn node genuinely has nowhere to go.
    """
    candidates = sorted(
        node_id
        for node_id in cmap.known_nodes
        if node_id != source and node_id in graph.nodes
    )
    if not candidates:
        return None
    sub = cognitive_subgraph(cmap, graph)
    for offset in range(len(candidates)):
        node_id = candidates[(step + offset) % len(candidates)]
        result = sub.shortest_path_to(source, node_id)
        if result is None:
            continue
        return node_id, result[1]
    return None


def _cost_from_agent(graph, path, cost: float, agent_position) -> float:
    """Replace the path's first leg with the walk from the agent's position."""
    if agent_position is None or len(path) < 2:
        return cost

    from .route_graph import _walkable_distance

    second = graph.nodes.get(path[1])
    if second is None:
        return cost
    # The edge's own weight -- the number Dijkstra summed into *cost* -- rather
    # than a fresh query for the same two nodes. Recomputing would cost a
    # routing-engine call per frontier candidate and could disagree with the
    # weight actually used: both this and _make_edge fall back to a straight
    # line when the engine declines a query, and they need not decline the same
    # one.
    first_leg = next(
        (e.weight for e in graph.edges.get(path[0], []) if e.target == path[1]),
        None,
    )
    if first_leg is None:
        return cost
    next_xy = (second.centroid_x, second.centroid_y)
    return (
        cost
        - first_leg
        + _walkable_distance(graph.routing_engine, agent_position, next_xy)
    )
