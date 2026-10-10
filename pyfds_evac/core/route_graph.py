"""Stage graph for shortest-path routing and smoke-adjusted rerouting."""

from __future__ import annotations

import heapq
import logging
import math
import weakref
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from typing import Protocol

from shapely.geometry import Polygon

from .geometry import node_position as _node_position
from .smoke_speed import speed_factor_from_extinction

_logger = logging.getLogger(__name__)

_SECONDS_PER_MINUTE = 60.0

# Optical depths at most this far apart order as equal under the gate, so
# travel time decides (#452). tau = K_ave * L below 1e-9 needs K_ave < 1e-12 /m
# on routes up to 1 km: physically clear air, and far below FDS's single
# precision. Without it, round-off such as 1e-19 against 4e-15 decided which
# clear exit came first. This is a numerical tie, not the anchor's deadband.
EPS_TAU = 1e-9


def taus_tie(a: float, b: float) -> bool:
    """Whether optical depths *a* and *b* count as equal (``EPS_TAU``).

    Non-finite values never tie: ``inf - inf`` is NaN.
    """
    return abs(a - b) <= EPS_TAU


# A segment is cached per (source, target) and, when anticipating, per exact
# time the agent reaches its start and latest time foresight may read: every
# sample on it is read at a time fixed by those two alone (#650), so a cached
# segment is the one a fresh evaluation would measure.
SegmentCacheKey = tuple[str, str] | tuple[str, str, float, float]
# The walk of one agent to a node: at the decision time (the path search), or
# foreseen, each point at the time the agent reaches it (#650).
WalkKey = str | tuple[str, str]


@dataclass(frozen=True)
class StageNode:
    """A node in the stage graph representing one stage.

    The ``centroid_*`` fields hold :func:`~pyfds_evac.core.geometry.node_position`,
    which is the polygon's centroid for every convex stage but an interior
    point for a concave one, whose centroid falls outside itself.  The names
    predate that distinction and are kept because they are load-bearing across
    the routing layer.
    """

    stage_id: str
    centroid_x: float
    centroid_y: float
    stage_type: str  # "exit", "checkpoint", "distribution", "zone"
    capacity_agents_per_s: float | None = None
    # An exit's schedule: open while open_from_s <= t < closed_after_s. None
    # on either side leaves that side unbounded.
    open_from_s: float | None = None
    closed_after_s: float | None = None

    def is_open(self, time_s: float) -> bool:
        """Whether the stage accepts agents at *time_s*."""
        if self.open_from_s is not None and time_s < self.open_from_s:
            return False
        return self.closed_after_s is None or time_s < self.closed_after_s


@dataclass
class StageEdge:
    """A directed edge in the stage graph."""

    source: str
    target: str
    weight: float  # edge length in metres (polyline or Euclidean)
    waypoints: list[tuple[float, float]] = field(default_factory=list)


@dataclass
class StageGraph:
    """Directed weighted graph of stages for route evaluation.

    Nodes are stages (distributions, checkpoints, exits).
    Edges come from transitions.  Edge weight is the Euclidean distance
    between stage centroids.  The graph is built once at simulation start.
    """

    nodes: dict[str, StageNode] = field(default_factory=dict)
    edges: dict[str, list[StageEdge]] = field(default_factory=dict)
    # Kept so route evaluation can measure distances from an agent's actual
    # position along the walkable area, the same way edges are measured.
    routing_engine: object | None = None
    # The walkable area, to check that an agent fits on a node point (#250),
    # and whether it does, by (node, agent radius).
    walkable_polygon: Polygon | None = None
    node_point_fits: dict[tuple[str, float], bool] = field(
        default_factory=dict, repr=False, compare=False
    )

    @classmethod
    def from_scenario(
        cls,
        direct_steering_info: dict,
        transitions: list[dict],
        distributions: dict | None = None,
        walkable_polygon=None,
    ) -> StageGraph:
        """Build the stage graph from scenario data.

        Parameters
        ----------
        direct_steering_info:
            Maps stage_id -> dict with at least "polygon" (Shapely Polygon)
            and "stage_type" (str).
        transitions:
            List of dicts with "from" and "to" keys defining directed edges.
        distributions:
            Optional dict of distribution_id -> dict with "coordinates".
            Distributions are spawn areas and are added as nodes with type
            "distribution" so that shortest-path queries can start from them.
        walkable_polygon:
            Optional Shapely Polygon of the walkable area.  When provided,
            a JuPedSim RoutingEngine computes polyline waypoints for each
            edge; otherwise a straight centroid-to-centroid ray is used.
        """
        graph = cls()

        routing_engine = None
        if walkable_polygon is not None:
            import jupedsim as jps  # lazy import; jupedsim not always required

            routing_engine = jps.RoutingEngine(walkable_polygon)
        graph.routing_engine = routing_engine
        graph.walkable_polygon = walkable_polygon

        # Add distribution nodes (not in direct_steering_info).
        if distributions:
            for dist_id, dist_info in distributions.items():
                coords = dist_info.get("coordinates")
                if coords is None:
                    polygon = dist_info.get("polygon")
                else:
                    polygon = Polygon(coords)
                if polygon is None:
                    continue
                cx, cy = _node_position(polygon)
                graph.nodes[dist_id] = StageNode(
                    stage_id=dist_id,
                    centroid_x=cx,
                    centroid_y=cy,
                    stage_type="distribution",
                )

        # Add stage nodes from direct_steering_info.
        for stage_id, info in direct_steering_info.items():
            polygon = info.get("polygon")
            if polygon is None:
                continue
            cx, cy = _node_position(polygon)
            stage_type = info.get("stage_type", "checkpoint")
            graph.nodes[stage_id] = StageNode(
                stage_id=stage_id,
                centroid_x=cx,
                centroid_y=cy,
                stage_type=stage_type,
                capacity_agents_per_s=info.get("capacity_agents_per_s"),
                open_from_s=info.get("open_from_s"),
                closed_after_s=info.get("closed_after_s"),
            )

        # Add edges from transitions.
        for tr in transitions:
            src = tr.get("from", "")
            tgt = tr.get("to", "")
            if src not in graph.nodes or tgt not in graph.nodes:
                continue
            src_node = graph.nodes[src]
            tgt_node = graph.nodes[tgt]
            edge = _make_edge(src_node, tgt_node, routing_engine)
            graph.edges.setdefault(src, []).append(edge)

        # With no transitions the author has drawn stages but not routes, so
        # wire the graph by stage type and let cost decide: spawn areas and
        # crossings reach every crossing and every exit, exits are terminal,
        # and nothing points back at a spawn area.
        if not transitions:
            targets = [
                nid
                for nid, n in graph.nodes.items()
                if n.stage_type in ("checkpoint", "exit")
            ]
            sources = [
                nid
                for nid, n in graph.nodes.items()
                if n.stage_type in ("distribution", "checkpoint")
            ]
            # Connect a node only to those reachable without passing another,
            # so "neighbour" keeps its physical meaning.  A complete graph would
            # make it meaningless, and expand_on_arrival reveals every neighbour
            # a vis-model-less run cannot rule out -- so one arrival would
            # expose the whole building and flatten the familiarity gradient.
            # Only crossings can block. An exit is terminal -- you cannot pass
            # through one -- so an exit lying on the way to a farther exit must
            # not prune it, or that farther exit becomes unreachable outright.
            blockers = [
                nid for nid, n in graph.nodes.items() if n.stage_type == "checkpoint"
            ]
            for src_id in sources:
                candidates = [
                    _make_edge(graph.nodes[src_id], graph.nodes[tgt_id], routing_engine)
                    for tgt_id in targets
                    if tgt_id != src_id
                ]
                kept = [
                    edge
                    for edge in candidates
                    if not _passes_through_another_node(
                        graph, src_id, edge, blockers, routing_engine
                    )
                ]
                # Pruning must never strand a node: if everything looked
                # blocked, keep the nearest target so it still has somewhere
                # to go and every exit stays reachable in some number of hops.
                if not kept and candidates:
                    kept = [min(candidates, key=lambda e: e.weight)]
                graph.edges.setdefault(src_id, []).extend(kept)

        return graph

    def exit_nodes(self) -> list[str]:
        """Return IDs of all exit stages."""
        return [sid for sid, node in self.nodes.items() if node.stage_type == "exit"]

    def distribution_nodes(self) -> list[str]:
        """Return IDs of all distribution stages."""
        return [
            sid for sid, node in self.nodes.items() if node.stage_type == "distribution"
        ]

    def shortest_paths_to_exits(
        self,
        source: str,
        dynamic_weights: dict[tuple[str, str], float] | None = None,
        first_hops: dict[str, float] | None = None,
    ) -> dict[str, tuple[float, list[str]]]:
        """Dijkstra from *source* to every reachable exit.

        Returns a dict mapping exit_id -> (cost, path) where path is the
        list of stage IDs from source to exit inclusive.

        When *dynamic_weights* is provided, edge costs are looked up from
        the dict instead of using static Euclidean weights.

        When *first_hops* is provided, the search starts from a point off the
        graph rather than at *source*: it maps each node reachable first to
        the cost of getting there, and replaces *source*'s own out-edges.
        The search never goes back into *source*, so every path has the form
        ``[source, first_hop, ..., exit]`` with *source* once, at index 0, and
        its cost is ``first_hops[first_hop]`` plus the edge weights after it.
        """
        dist, prev = self._dijkstra(
            source, dynamic_weights=dynamic_weights, first_hops=first_hops
        )
        results: dict[str, tuple[float, list[str]]] = {}
        for exit_id in self.exit_nodes():
            if exit_id in dist and math.isfinite(dist[exit_id]):
                path = self._reconstruct(prev, source, exit_id)
                results[exit_id] = (dist[exit_id], path)
        return results

    def shortest_exit(self, source: str) -> tuple[str, float, list[str]] | None:
        """Return (exit_id, cost, path) for the nearest exit from *source*.

        Returns None if no exit is reachable.
        """
        candidates = self.shortest_paths_to_exits(source)
        if not candidates:
            return None
        best_exit = min(candidates, key=lambda eid: candidates[eid][0])
        cost, path = candidates[best_exit]
        return best_exit, cost, path

    def shortest_path_to(
        self,
        source: str,
        target: str,
        dynamic_weights: dict[tuple[str, str], float] | None = None,
    ) -> tuple[float, list[str]] | None:
        """Return (cost, path) for the shortest known path from *source* to *target*.

        Returns None if *target* is not reachable from *source*.
        """
        dist, prev = self._dijkstra(source, dynamic_weights=dynamic_weights)
        if target not in dist or not math.isfinite(dist[target]):
            return None
        return dist[target], self._reconstruct(prev, source, target)

    def _dijkstra(
        self,
        source: str,
        dynamic_weights: dict[tuple[str, str], float] | None = None,
        first_hops: dict[str, float] | None = None,
    ) -> tuple[dict[str, float], dict[str, str | None]]:
        """Run Dijkstra from *source*.  Returns (dist, prev) dicts.

        When *dynamic_weights* is provided, edge cost is looked up from
        the dict instead of using the static edge weight.  Keys are
        ``(source_id, target_id)`` tuples.

        With *first_hops* the search is seeded at those nodes, each with its
        cost and *source* as its predecessor. *source* stands for the agent's
        position only: no edge into it is relaxed, so it is never reached
        through the graph and appears once, at the start of every path.
        """
        if source not in self.nodes:
            return {}, {}
        dist: dict[str, float] = {sid: math.inf for sid in self.nodes}
        prev: dict[str, str | None] = {sid: None for sid in self.nodes}
        heap: list[tuple[float, str]] = []
        if first_hops is None:
            dist[source] = 0.0
            heap.append((0.0, source))
        else:
            for node, cost in first_hops.items():
                if node in dist and node != source and cost < dist[node]:
                    dist[node] = cost
                    prev[node] = source
                    heapq.heappush(heap, (cost, node))

        while heap:
            d, u = heapq.heappop(heap)
            if d > dist[u]:
                continue
            for edge in self.edges.get(u, []):
                if first_hops is not None and edge.target == source:
                    continue
                if dynamic_weights is not None:
                    w = dynamic_weights.get((edge.source, edge.target), edge.weight)
                else:
                    w = edge.weight
                alt = d + w
                if alt < dist[edge.target]:
                    dist[edge.target] = alt
                    prev[edge.target] = u
                    heapq.heappush(heap, (alt, edge.target))

        return dist, prev

    @staticmethod
    def _reconstruct(
        prev: dict[str, str | None], source: str, target: str
    ) -> list[str]:
        """Reconstruct path from prev pointers."""
        path: list[str] = []
        cur: str | None = target
        while cur is not None:
            path.append(cur)
            if cur == source:
                break
            cur = prev.get(cur)
        path.reverse()
        return path


def without_closed_stages(graph: StageGraph, time_s: float) -> StageGraph:
    """Return *graph* without the stages closed at *time_s* and their edges.

    A closed exit is no route and no place to explore. Without a schedule
    nothing is closed and *graph* itself is returned.
    """
    closed = {nid for nid, node in graph.nodes.items() if not node.is_open(time_s)}
    if not closed:
        return graph
    sub = StageGraph(
        routing_engine=graph.routing_engine,
        walkable_polygon=graph.walkable_polygon,
        node_point_fits=graph.node_point_fits,
    )
    sub.nodes = {nid: n for nid, n in graph.nodes.items() if nid not in closed}
    sub.edges = {
        src: [e for e in edges if e.target not in closed]
        for src, edges in graph.edges.items()
        if src not in closed
    }
    return sub


def _passes_through_another_node(
    graph, src_id: str, edge: StageEdge, blockers, routing_engine
) -> bool:
    """Whether some third stage lies on the way from ``src_id`` to the target.

    Betweenness by path length: C is on the way from A to B when going A->C->B
    costs no more than A->B itself, within a small tolerance.  Distances follow
    the walkable area when a routing engine is available, so a node around a
    corner does not count as "in between" merely by being near the straight
    line.

    Only crossings are blockers.  Walking across a spawn area does not make the
    target behind it unreachable, and an exit cannot be passed through at all --
    treating either as a blocker strands whatever lies beyond.
    """
    src = graph.nodes[src_id]
    tgt = graph.nodes[edge.target]
    direct = edge.weight
    if direct <= 1e-9:
        return False
    for mid_id in blockers:
        if mid_id in (src_id, edge.target):
            continue
        mid = graph.nodes[mid_id]
        via = _walkable_distance(
            routing_engine,
            (src.centroid_x, src.centroid_y),
            (mid.centroid_x, mid.centroid_y),
        ) + _walkable_distance(
            routing_engine,
            (mid.centroid_x, mid.centroid_y),
            (tgt.centroid_x, tgt.centroid_y),
        )
        if via <= direct * (1.0 + _BETWEENNESS_TOLERANCE):
            return True
    return False


# A third node counts as 'in between' when the detour through it costs no
# more than this fraction above the direct path.  Small enough that a real
# alternative route is not mistaken for one, large enough to absorb the
# navmesh's polyline discretisation.
_BETWEENNESS_TOLERANCE = 0.05


def _make_edge(src_node: StageNode, tgt_node: StageNode, routing_engine) -> StageEdge:
    """Build a StageEdge between two nodes using polyline or straight-line geometry."""
    straight = [
        (src_node.centroid_x, src_node.centroid_y),
        (tgt_node.centroid_x, tgt_node.centroid_y),
    ]
    waypoints = straight
    if routing_engine is not None:
        # A centroid outside the navmesh makes the routing engine raise.  The
        # edge is still wanted -- a straight ray is a coarse but usable cost --
        # so fall back rather than lose the connection or abort the run.
        try:
            waypoints = list(routing_engine.compute_waypoints(*straight))
        except Exception as exc:
            _logger.warning(
                "Routing %s -> %s failed (%s); using a straight centroid ray",
                src_node.stage_id,
                tgt_node.stage_id,
                exc,
            )
            waypoints = straight
    return StageEdge(
        source=src_node.stage_id,
        target=tgt_node.stage_id,
        weight=_polyline_length(waypoints),
        waypoints=waypoints,
    )


def _euclidean(x1: float, y1: float, x2: float, y2: float) -> float:
    """Euclidean distance between two 2D points."""
    return math.hypot(x2 - x1, y2 - y1)


def _polyline_length(waypoints: list[tuple[float, float]]) -> float:
    """Sum of Euclidean segment lengths along a polyline."""
    total = 0.0
    for i in range(len(waypoints) - 1):
        total += _euclidean(
            waypoints[i][0],
            waypoints[i][1],
            waypoints[i + 1][0],
            waypoints[i + 1][1],
        )
    return total


def _walkable_waypoints(routing_engine, from_xy, to_xy) -> list[tuple[float, float]]:
    """Path through the walkable area, or the straight line if unavailable.

    A wrong path only degrades ranking, so a failed or degenerate query
    falls back rather than ending the run.
    """
    straight = [tuple(from_xy), tuple(to_xy)]
    if routing_engine is None:
        return straight
    try:
        waypoints = list(routing_engine.compute_waypoints(from_xy, to_xy))
    except Exception:
        return straight
    if len(waypoints) < 2:
        return straight
    return waypoints


def _walkable_distance(routing_engine, from_xy, to_xy) -> float:
    """Path length through the walkable area, or straight-line if unavailable."""
    return _polyline_length(_walkable_waypoints(routing_engine, from_xy, to_xy))


# ── Route cost evaluation (Phase 3) ──────────────────────────────────


class ExtinctionSampler(Protocol):
    """Anything that can sample extinction K at a point and time."""

    def sample_extinction(self, time_s: float, x: float, y: float) -> float: ...


def integrated_extinction_along_los(
    x_from: float,
    y_from: float,
    x_to: float,
    y_to: float,
    time_s: float,
    extinction_sampler: ExtinctionSampler,
    step_m: float = 2.0,
) -> float:
    """Return the Beer-Lambert path-integrated mean extinction coefficient.

    Computes the arithmetic mean of K sampled at uniform intervals along
    the line of sight from (x_from, y_from) to (x_to, y_to), which is
    the discrete form of Boerger et al. (2024) Eq. 8-9:

        sigma_bar = (1 / |P|) * sum_p K_p

    This gives the effective extinction that an observer at the source
    would experience looking toward the target through an inhomogeneous
    smoke field.

    Parameters
    ----------
    x_from, y_from : float
        Observer position.
    x_to, y_to : float
        Target position (e.g. exit sign / waypoint).
    time_s : float
        Simulation time for the extinction snapshot.
    extinction_sampler : ExtinctionSampler
        Provides ``sample_extinction(time_s, x, y) -> float``.
    step_m : float
        Maximum spacing between sample points along the ray.

    Returns
    -------
    float
        Path-integrated mean extinction coefficient in 1/m.
    """
    if step_m <= 0:
        raise ValueError(f"step_m must be positive, got {step_m}")
    length = _euclidean(x_from, y_from, x_to, y_to)
    if length < 1e-9:
        return extinction_sampler.sample_extinction(time_s, x_from, y_from)

    return _los_stats(
        x_from, y_from, x_to, y_to, time_s, extinction_sampler, step_m, length
    )[0]


def _los_stats(
    x_from: float,
    y_from: float,
    x_to: float,
    y_to: float,
    time_s: float,
    extinction_sampler: ExtinctionSampler,
    step_m: float,
    length: float,
    clock: _ForesightClock | None = None,
) -> tuple[float, float]:
    """Mean and worst K sampled along a line of sight.

    The mean is what a route costs to walk; the worst is what stops an agent
    walking it, and averaging hides exactly the wall of smoke a person refuses
    to enter. Both come from one traverse.

    Every sample is read at *time_s*, or with a *clock* at the time the agent
    reaches it (#650).
    """
    n_samples = max(2, int(math.ceil(length / step_m)) + 1)
    total = 0.0
    worst = 0.0
    for i in range(n_samples):
        t = i / (n_samples - 1)
        x = x_from + t * (x_to - x_from)
        y = y_from + t * (y_to - y_from)
        ts = time_s if clock is None else clock.at(t * length)
        k = extinction_sampler.sample_extinction(ts, x, y)
        total += k
        worst = max(worst, k)
    return total / n_samples, worst


def integrated_extinction_along_polyline(
    waypoints: list[tuple[float, float]],
    time_s: float,
    extinction_sampler: ExtinctionSampler,
    step_m: float = 2.0,
) -> float:
    """Return the Beer-Lambert path-integrated mean extinction along a polyline.

    Samples K at uniform intervals along each segment of the polyline,
    takes the mean per segment and returns the mean of those, weighted by
    segment length (see :func:`_polyline_stats`).
    """
    if step_m <= 0:
        raise ValueError(f"step_m must be positive, got {step_m}")
    if len(waypoints) < 2:
        if waypoints:
            return extinction_sampler.sample_extinction(
                time_s, waypoints[0][0], waypoints[0][1]
            )
        return 0.0

    return _polyline_stats(waypoints, time_s, extinction_sampler, step_m)[0]


def _polyline_stats(
    waypoints: list[tuple[float, float]],
    time_s: float,
    extinction_sampler: ExtinctionSampler,
    step_m: float,
    clock: _ForesightClock | None = None,
) -> tuple[float, float]:
    """Mean and worst K along a polyline -- see :func:`_los_stats`.

    Each segment is sampled as a line of sight by :func:`_los_stats`, and
    the segment means are combined weighted by segment length:

        K_poly = sum_s L_s * K_s / sum_s L_s

    so the result approximates (1 / L) * integral K ds and does not depend
    on where the polyline has its vertices. Zero-length segments are sampled
    once, count towards the worst K and carry no weight; if every segment
    has zero length the mean is the plain mean of those samples. A polyline
    with one segment of non-zero length returns that segment's mean as is.
    """
    if len(waypoints) < 2:
        if waypoints:
            k = extinction_sampler.sample_extinction(
                time_s, waypoints[0][0], waypoints[0][1]
            )
            return k, k
        return 0.0, 0.0
    segment_means: list[tuple[float, float]] = []
    degenerate_ks: list[float] = []
    worst = 0.0
    walked = 0.0
    for i in range(len(waypoints) - 1):
        x0, y0 = waypoints[i]
        x1, y1 = waypoints[i + 1]
        seg_len = _euclidean(x0, y0, x1, y1)
        sub = None if clock is None else clock.shifted(walked)
        walked += seg_len
        if seg_len < 1e-9:
            ts = time_s if sub is None else sub.at(0.0)
            k = extinction_sampler.sample_extinction(ts, x0, y0)
            degenerate_ks.append(k)
            worst = max(worst, k)
            continue
        mean, seg_worst = _los_stats(
            x0, y0, x1, y1, time_s, extinction_sampler, step_m, seg_len, sub
        )
        segment_means.append((mean, seg_len))
        worst = max(worst, seg_worst)

    return _length_weighted_mean(segment_means, degenerate_ks), worst


def _length_weighted_mean(
    segment_means: list[tuple[float, float]], degenerate_ks: list[float]
) -> float:
    """Combine ``(mean, length)`` pairs of a polyline, weighted by length.

    One segment returns its mean unchanged (no ``mean * L / L`` rounding);
    no segment of non-zero length falls back to the mean of
    ``degenerate_ks``.
    """
    if len(segment_means) == 1:
        return segment_means[0][0]
    if not segment_means:
        return sum(degenerate_ks) / len(degenerate_ks) if degenerate_ks else 0.0
    weighted = sum(mean * length for mean, length in segment_means)
    total_length = sum(length for _, length in segment_means)
    return weighted / total_length


def _polyline_midpoint(
    waypoints: list[tuple[float, float]],
) -> tuple[float, float]:
    """Return the point at half the arc length along a polyline.

    Raises:
        ValueError: If ``waypoints`` is empty. Callers must ensure the list
            contains at least one point.
    """
    if not waypoints:
        raise ValueError("waypoints must not be empty")
    if len(waypoints) == 1:
        return waypoints[0]

    total = _polyline_length(waypoints)
    if total < 1e-9:
        return waypoints[0]

    half = total / 2.0
    acc = 0.0
    for i in range(len(waypoints) - 1):
        x0, y0 = waypoints[i]
        x1, y1 = waypoints[i + 1]
        seg = _euclidean(x0, y0, x1, y1)
        if acc + seg >= half:
            t = (half - acc) / seg if seg > 1e-9 else 0.0
            return (x0 + t * (x1 - x0), y0 + t * (y1 - y0))
        acc += seg
    return waypoints[-1]


class FedRateSampler(Protocol):
    """Anything that can return a FED rate in 1/min at a point and time."""

    def sample_fed_rate(self, time_s: float, x: float, y: float) -> float: ...


ROUTE_COST_MODELS = ("gate", "additive")


def _unknown_cost_model(cost_model: object) -> ValueError:
    """The error for a cost_model that names no route cost model."""
    return ValueError(
        f"Unknown routing cost_model {cost_model!r}; "
        f"expected one of {ROUTE_COST_MODELS}"
    )


@dataclass(frozen=True)
class RouteCostConfig:
    """Weights and thresholds for route cost evaluation."""

    w_smoke: float = 1.0
    w_fed: float = 10.0
    # Off by default. The term is
    #     w_queue * base_speed_m_per_s * N / capacity_agents_per_s
    # with N a *global* tally of every agent targeting the exit. (The paper
    # writes this v0 * N / c; base_speed_m_per_s is that conversion constant,
    # NOT any agent's desired speed.) With both speed and capacity at their
    # 1.3 defaults the penalty is simply w_queue * N metres: it grows without
    # bound in the
    # population while the path lengths it competes against are fixed by the
    # geometry. No constant is therefore right at more than one crowd size --
    # 1.0 put 333 m on a door at Station scale, and the 0.03 that fixes that is
    # inert (0.8 m at N = 25) in an ordinary room. Rather than ship a number
    # calibrated on one deck as the default for every deck, congestion-aware
    # routing is opt-in; assets/station_fahy sets it in its own routing block.
    # See issue #89 for the perceivable-queue form that would remove the scale
    # dependence.
    w_queue: float = 0.0
    fed_rejection_threshold: float = 1.0
    # Asymmetric FED hysteresis (Schmitt trigger) to stop agents flip-flopping
    # when a route's predicted dose wobbles across the rejection threshold. The
    # agent's *current* exit is rejected only above fed_rejection_threshold (it
    # still flees the instant dose crosses incapacitation — safety unchanged),
    # but a *different* exit is only accepted as a switch target if its dose is
    # below fed_rejection_threshold * fed_return_margin, i.e. clearly safe, not
    # merely back under threshold. Never makes it harder to LEAVE a bad exit.
    fed_return_margin: float = 0.9
    visibility_extinction_threshold: float = 0.5
    # Above this route-average extinction, a smoke/visibility rejection is
    # treated as an impassable hazard the agent flees regardless of the anchor
    # (like an FED-lethal rejection). At or below it, low visibility is a soft
    # cost only and stays subject to the exit-switch anchor — this is what stops
    # mild smoke (k_ave just over visibility_extinction_threshold) from flipping
    # an agent off its committed exit every tick. Physically ~1 m visibility
    # (S ~ C/K); NOT calibrated, but chosen to sit well above the mild haze that
    # caused the demo flip-flop (k_ave <= ~0.9) and below genuine walls of smoke.
    impassable_extinction_threshold: float = 3.0
    sampling_step_m: float = 2.0
    base_speed_m_per_s: float = 1.3
    alpha: float = 0.706
    beta: float = -0.057
    min_speed_factor: float = 0.1
    default_exit_capacity: float = 1.3

    # ── Gate model ────────────────────────────────────────────────────────
    # "gate": distance is the objective and smoke decides which exits remain
    # available; "additive": the historical w_smoke/w_fed toll, kept because
    # the smoke term multiplies route *length*, so a long clean detour pays for
    # its own length and can never win however large w_smoke is (sweeping it
    # 1 -> 20 on assets/world_100 moved 12 of 120 agents). Matched exactly;
    # any other value raises ValueError.
    cost_model: str = "gate"
    # A route is refused when the sighting distance at its worst point falls
    # below this fraction of the distance still to walk -- FDS+Evac's own door
    # criterion (evac.f90: "Check that visibility > 0.5*distance to the door").
    # Being distance-relative is the point: haze 5 m from an exit is usable and
    # the same haze at 40 m is not, which no absolute extinction limit can say.
    # Tier 1: an exit is "clean" while the smokiest leg of the route to it
    # stays under this. Off by default -- see docs/gate-model-review-notes.md
    # for why it does not survive contact with either reference deck.
    clean_extinction_threshold: float = 0.0
    # Hysteresis on tier membership for the exit the agent already heads for,
    # from FDS+Evac's FAC_DOOR_OLD = 0.1 (evac.f90:1571).
    clean_exit_margin: float = 0.1
    # The route the agent will accept, as an optical depth: tau = K_ave * L,
    # the soot column it walks through. Refused above this.
    #
    # 6 is FDS+Evac's own threshold, not an analogy: evac.f90:16458 computes
    # L2_tmp = d * 0.5 / (3/K_ave) = K_ave * d / 6, and :16463 refuses the door
    # at L2_tmp >= 1, which is tau >= 6. Writing it as an optical depth is what
    # made that visible.
    #
    # Three things still differ from the source: the quantity (a straight sight
    # line there, a walked polyline here, so this is exposure rather than
    # sight), the scope (there it is a last-resort branch over known-or-visible
    # doors), and the memory (there a strike-out lasts one call; the only
    # lasting mark is on a lone agent's previous target once K_ave >= 0.3 /m,
    # evac.f90:16292-16301, and it acts weakly -- see docs/model-comparison.md).
    # Citable as a threshold, uncalibrated as an exposure budget --
    # docs/gate-model-review-notes.md.
    tau_max: float = 6.0
    # How far apart two routes' optical depths must be before the difference
    # overrides the exit an agent already walks to. Ours: the reference applies
    # no hysteresis to this veto (evac.f90:16463 tests the raw value).
    tau_deadband: float = 0.1
    current_exit_discount: float = 0.9
    # A rival exit must come in under tau_max * this before an agent switches
    # onto it, so a route sitting near the budget does not toggle. Ours: the
    # reference applies no hysteresis to this veto (evac.f90:16463 tests the
    # raw value); its 0.1 hysteresis is on the tier-1 test at :16255.
    tau_return_margin: float = 0.8
    # Charge each leg the smoke present when the agent would arrive there,
    # rather than the smoke standing there while it decides.
    anticipate: bool = True
    # Cap on how far ahead that reaches. Unbounded is perfect foresight; a
    # finite horizon models an occupant who can only judge the near future.
    foresight_horizon_s: float = math.inf
    # Between two refused routes the agent keeps its exit unless the rival's
    # optical depth tau is more than this fraction lower (#458) -- without it the
    # least-bad choice changes with every flicker of the field.
    fallback_switch_margin: float = 0.2
    # After an exit switch between two refused routes, a switch straight back
    # to the exit just left, again between two refused routes, is blocked for
    # this many seconds (#458). A route smoke sample that steps over a narrow
    # plume core can swing tau past the margin and back within one or two
    # evaluations (#653); this keeps that from reversing the agent. 0 turns
    # it off.
    fallback_return_lockout_s: float = 10.0

    def __post_init__(self) -> None:
        """Reject an unknown cost_model and a negative or non-numeric lockout."""
        if self.cost_model not in ROUTE_COST_MODELS:
            raise _unknown_cost_model(self.cost_model)
        lockout = self.fallback_return_lockout_s
        if (
            isinstance(lockout, bool)
            or not isinstance(lockout, (int, float))
            or not lockout >= 0.0
        ):
            raise ValueError(
                "routing.fallback_return_lockout_s must be a number of seconds "
                f">= 0, got {lockout!r}"
            )

    @classmethod
    def from_routing_params(cls, routing: dict | None) -> RouteCostConfig:
        """Build the cost model from a scenario's ``routing`` block.

        Route costs are needed for the initial exit assignment whether or not
        rerouting is enabled, so this lives here rather than inside the reroute
        configuration -- otherwise a run with rerouting off would rank the
        opening choice under different weights than the same run with it on.
        """
        routing = routing or {}
        return cls(
            cost_model=routing.get("cost_model", "gate"),
            clean_extinction_threshold=routing.get("clean_extinction_threshold", 0.0),
            clean_exit_margin=routing.get(
                "clean_exit_margin", RouteCostConfig.clean_exit_margin
            ),
            tau_max=routing.get("tau_max", RouteCostConfig.tau_max),
            tau_deadband=routing.get("tau_deadband", RouteCostConfig.tau_deadband),
            current_exit_discount=routing.get(
                "current_exit_discount", RouteCostConfig.current_exit_discount
            ),
            tau_return_margin=routing.get(
                "tau_return_margin", RouteCostConfig.tau_return_margin
            ),
            anticipate=routing.get("anticipate", True),
            foresight_horizon_s=routing.get("foresight_horizon_s", math.inf),
            fallback_switch_margin=routing.get("fallback_switch_margin", 0.2),
            fallback_return_lockout_s=routing.get(
                "fallback_return_lockout_s", RouteCostConfig.fallback_return_lockout_s
            ),
            w_smoke=routing.get("w_smoke", 1.0),
            w_fed=routing.get("w_fed", 10.0),
            w_queue=routing.get("w_queue", 0.0),
            fed_rejection_threshold=routing.get("fed_rejection_threshold", 1.0),
            visibility_extinction_threshold=routing.get(
                "visibility_extinction_threshold", 0.5
            ),
            sampling_step_m=routing.get("sampling_step_m", 2.0),
            base_speed_m_per_s=routing.get("base_speed_m_per_s", 1.3),
            alpha=routing.get("alpha", 0.706),
            beta=routing.get("beta", -0.057),
            min_speed_factor=routing.get("min_speed_factor", 0.1),
            default_exit_capacity=routing.get("default_exit_capacity", 1.3),
        )


@dataclass(frozen=True)
class SegmentCost:
    """Cost breakdown for one edge (segment) of a route."""

    source: str
    target: str
    length_m: float
    k_avg: float
    speed_factor: float
    travel_time_s: float
    fed_growth: float
    visible: bool
    k_max: float = 0.0
    arrival_time_s: float = 0.0


@dataclass(frozen=True)
class RouteCost:
    """Full cost evaluation for one candidate route."""

    exit_id: str
    path: list[str]
    path_length_m: float
    k_ave_route: float
    travel_time_s: float
    fed_max_route: float
    composite_cost: float
    segments: list[SegmentCost]
    rejected: bool
    rejection_reason: str | None
    queue_time_s: float = 0.0
    # Gate model only. `tau_route` is the route's optical depth, K_ave times
    # the distance still to walk -- the soot column the agent passes through --
    # and `feasible` whether that and the predicted dose both allow the route.
    k_max_route: float = 0.0
    tau_route: float = 0.0
    feasible: bool = True
    # What the whole pipeline orders on -- ranking, the exit-switch anchor and
    # the same-exit path test all read this, so a model change lands in one
    # place. Under "additive" it is the composite; under "gate" it is time,
    # which only decides within a visibility band.
    rank_cost: float = 0.0
    # Tier 1 membership: the smokiest leg of this route is below the clean-door
    # criterion. Clean exits are preferred outright; time decides among them.
    k_leg_max: float = 0.0
    clean: bool = True
    # The travel time the route would take in clear air: travel_time_s with
    # every speed factor 1. Labels only (``smoke_reroute``, #92), so it takes
    # no part in comparing two routes; None when the route was not measured
    # by evaluate_route.
    clear_travel_time_s: float | None = field(default=None, compare=False)
    # The limits the route breaks, in the order they were recorded: "fed",
    # "tau", "all_segments_non_visible". Must-flee reads these, not the
    # rejection reason, which names only the last one (#128).
    violation_kinds: tuple[str, ...] = ()


# ── Internal route records ───────────────────────────────────────────
#
# What evaluate_route computes, split by concern: what a route measures, which
# limits it breaks, and how it ranks. RouteCost stays the public result and is
# an exact projection of these (_project_route_cost).


@dataclass(frozen=True)
class RouteMeasurements:
    """What a route measures, before any limit or cost model is applied."""

    exit_id: str
    path: list[str]
    segments: list[SegmentCost]
    # Node to node, as RouteCost reports it.
    path_length_m: float
    # From where the agent stands, as tau and the composite use it.
    effective_length_m: float
    k_ave_route: float
    travel_time_s: float
    fed_max_route: float
    composite_cost: float
    queue_time_s: float
    k_max_route: float
    tau_route: float
    k_leg_max: float
    # travel_time_s with every speed factor 1, for the switch label (#92).
    clear_travel_time_s: float | None = None


@dataclass(frozen=True)
class RouteViolation:
    """One limit a route breaks."""

    # "fed", "tau" or "all_segments_non_visible".
    kind: str
    # The public rejection reason this violation reports.
    reason: str
    measured: float
    limit: float


@dataclass(frozen=True)
class RouteFeasibility:
    """Whether a route may be taken, and why not.

    ``feasible`` and ``rejected`` are kept independently: the additive K_vis
    screen sets ``rejected`` and leaves ``feasible`` alone. The public reason
    is that of the last violation recorded, so a route over both the FED and
    the tau limit reports tau.
    """

    feasible: bool
    rejected: bool
    rejection_reason: str | None
    violations: tuple[RouteViolation, ...] = ()


@dataclass(frozen=True)
class RouteAssessment:
    """A measured route judged under one cost model."""

    measurements: RouteMeasurements
    feasibility: RouteFeasibility
    rank_cost: float
    clean: bool


@dataclass(frozen=True)
class RouteDecision:
    """What one reevaluation decided for an agent, before it is applied."""

    # "keep", "switch", "fallback", "explore", "wander", "return", "stay",
    # "default_route" or "look" (walk to the node point before a wander).
    kind: str
    path: list[str] | None = None
    old_exit: str | None = None
    target_id: str | None = None
    old_cost: float | None = None
    new_cost: float | None = None
    # The RouteSwitch reason, exactly as emitted.
    switch_reason: str | None = None
    # Same-exit decisions: the path is recorded whether or not the switch
    # applies, and the exit is left as it is.
    update_cached_path: bool = False
    # A look: the node point the agent walks to.
    point: tuple[float, float] | None = None


def _project_route_cost(assessment: RouteAssessment) -> RouteCost:
    """The public ``RouteCost`` of an assessed route, field for field."""
    m = assessment.measurements
    f = assessment.feasibility
    return RouteCost(
        exit_id=m.exit_id,
        path=m.path,
        path_length_m=m.path_length_m,
        k_ave_route=m.k_ave_route,
        travel_time_s=m.travel_time_s,
        fed_max_route=m.fed_max_route,
        composite_cost=m.composite_cost,
        segments=m.segments,
        rejected=f.rejected,
        rejection_reason=f.rejection_reason,
        queue_time_s=m.queue_time_s,
        k_max_route=m.k_max_route,
        tau_route=m.tau_route,
        feasible=f.feasible,
        rank_cost=assessment.rank_cost,
        k_leg_max=m.k_leg_max,
        clean=assessment.clean,
        clear_travel_time_s=m.clear_travel_time_s,
        violation_kinds=tuple(v.kind for v in f.violations),
    )


def _sample_segment_extinction(
    src_node: StageNode,
    tgt_node: StageNode,
    time_s: float,
    extinction_sampler: ExtinctionSampler,
    step_m: float,
    waypoints: list[tuple[float, float]] | None = None,
    clock: _ForesightClock | None = None,
) -> tuple[float, float, float]:
    """Sample extinction along edge geometry.

    Uses the polyline waypoints if provided, otherwise falls back to the
    centroid-to-centroid line of sight.

    Returns (segment_length, mean_extinction, worst_extinction).
    """
    if waypoints and len(waypoints) >= 2:
        length = _polyline_length(waypoints)
        k_avg, k_max = _polyline_stats(
            waypoints,
            time_s,
            extinction_sampler,
            step_m,
            clock,
        )
    else:
        length = _euclidean(
            src_node.centroid_x,
            src_node.centroid_y,
            tgt_node.centroid_x,
            tgt_node.centroid_y,
        )
        k_avg, k_max = _los_stats(
            src_node.centroid_x,
            src_node.centroid_y,
            tgt_node.centroid_x,
            tgt_node.centroid_y,
            time_s,
            extinction_sampler,
            step_m,
            length,
            clock,
        )
    return length, k_avg, k_max


def _arrival_time(time_s: float, walked_m: float, config: RouteCostConfig) -> float:
    """When the agent would reach a point *walked_m* along its route.

    Uses the unimpeded speed, not the smoke-reduced one: the reduction depends
    on the smoke at the arrival time this is computing, and one pass settles
    what a second would only refine.
    """
    if not config.anticipate:
        return time_s
    speed = max(config.base_speed_m_per_s, 1e-9)
    return time_s + min(walked_m / speed, config.foresight_horizon_s)


# The fields whose foresight cap has been logged. Every run builds its own
# fields, so this logs once per run.
_FORESIGHT_CAP_LOGGED: weakref.WeakSet = weakref.WeakSet()


def _fds_end(*samplers: object) -> tuple[float, object | None]:
    """The earliest last-frame time [s] of *samplers*, and the sampler.

    A field read from FDS output reports ``end_time_s``; a constant or
    synthetic field has none and does not bound foresight: ``(inf, None)``.
    """
    end_s, owner = math.inf, None
    for sampler in samplers:
        sampler_end = getattr(sampler, "end_time_s", None)
        if sampler_end is not None and sampler_end < end_s:
            end_s, owner = float(sampler_end), sampler
    return end_s, owner


def _cap_at_fds_end(
    time_s: float, t_foreseen: float, end_s: float, owner: object | None
) -> float:
    """Hold a foreseen time at the last FDS frame *end_s* (#666).

    Past the last frame there is no smoke record to foresee, so foresight
    reads that frame, as a horizon ending there would, and the run logs it
    once. A decision past *end_s* keeps its own time: the horizon check on
    samples at the decision time (``FdsHorizonError`` or
    ``--allow-fds-horizon-hold``) is unchanged.
    """
    cap = max(time_s, end_s)
    if t_foreseen <= cap:
        return t_foreseen
    if owner is not None and owner not in _FORESIGHT_CAP_LOGGED:
        _FORESIGHT_CAP_LOGGED.add(owner)
        _logger.warning(
            "Route foresight reaches beyond the earliest last FDS frame of "
            "the routing fields (t=%.1f s > %.1f s): smoke and FED ahead are "
            "read from that frame for the rest of the run.",
            t_foreseen,
            end_s,
        )
    return cap


@dataclass(frozen=True)
class _ForesightClock:
    """When the agent reaches the point *d* metres along a sampled geometry.

    ``min(t0 + (d0 + d) / speed, horizon_end_s)``, held at the last FDS frame
    (``_cap_at_fds_end``). *t0* is the time at the start of the geometry,
    *horizon_end_s* the decision time plus the foresight horizon, and *d0*
    the part of the geometry already walked, for a polyline sampled piece by
    piece. The result is ``min(t0 + (d0 + d) / speed, limit)`` with
    ``limit = min(horizon_end_s, max(decision_time_s, end_s))``: it depends
    on *t0* and that limit alone, which is what the segment cache keys on.
    """

    t0: float
    speed: float
    horizon_end_s: float
    decision_time_s: float
    end_s: float
    end_owner: object | None = field(default=None, compare=False)
    d0: float = 0.0

    def at(self, d: float) -> float:
        """The time the agent reaches *d* metres along [s]."""
        t = min(self.t0 + (self.d0 + d) / self.speed, self.horizon_end_s)
        return _cap_at_fds_end(self.decision_time_s, t, self.end_s, self.end_owner)

    def shifted(self, d: float) -> _ForesightClock:
        """The clock of the geometry that starts *d* metres further on."""
        return replace(self, d0=self.d0 + d)


def _foresight_clock(
    t_start: float,
    time_s: float,
    config: RouteCostConfig,
    end_s: float,
    end_owner: object | None,
) -> _ForesightClock:
    """The clock of a geometry the agent starts walking at *t_start* (#650).

    *t_start* was itself foreseen from the decision time *time_s*; the
    horizon runs from *time_s*.
    """
    return _ForesightClock(
        t0=t_start,
        speed=max(config.base_speed_m_per_s, 1e-9),
        horizon_end_s=time_s + config.foresight_horizon_s,
        decision_time_s=time_s,
        end_s=end_s,
        end_owner=end_owner,
    )


def evaluate_segment(
    graph: StageGraph,
    source: str,
    target: str,
    time_s: float,
    extinction_sampler: ExtinctionSampler,
    fed_rate_sampler: FedRateSampler | None,
    config: RouteCostConfig,
    arrival_time_s: float | None = None,
    clock: _ForesightClock | None = None,
) -> SegmentCost:
    """Evaluate cost for one edge of a route.

    *arrival_time_s* is when the agent would reach this edge, so the smoke it
    is charged is the smoke it will meet rather than the smoke standing there
    while it decides. Defaults to *time_s*, which is the no-foresight answer.
    With a *clock*, each extinction sample is read when the agent reaches it
    instead (#650); the FED rate stays one sample at *arrival_time_s*.
    """
    if arrival_time_s is None:
        arrival_time_s = time_s
    src_node = graph.nodes[source]
    tgt_node = graph.nodes[target]

    # Look up edge waypoints.
    waypoints = None
    for edge in graph.edges.get(source, []):
        if edge.target == target:
            waypoints = edge.waypoints
            break

    length, k_avg, k_max = _sample_segment_extinction(
        src_node,
        tgt_node,
        arrival_time_s,
        extinction_sampler,
        config.sampling_step_m,
        waypoints=waypoints,
        clock=clock,
    )
    sf = speed_factor_from_extinction(
        k_avg,
        alpha=config.alpha,
        beta=config.beta,
        min_speed_factor=config.min_speed_factor,
    )
    effective_speed = config.base_speed_m_per_s * sf
    travel_time = length / effective_speed if effective_speed > 1e-9 else math.inf

    fed_growth = 0.0
    if fed_rate_sampler is not None:
        if waypoints and len(waypoints) >= 2:
            mid_x, mid_y = _polyline_midpoint(waypoints)
        else:
            mid_x = (src_node.centroid_x + tgt_node.centroid_x) / 2
            mid_y = (src_node.centroid_y + tgt_node.centroid_y) / 2
        fed_rate = fed_rate_sampler.sample_fed_rate(arrival_time_s, mid_x, mid_y)
        fed_growth = fed_rate * travel_time / _SECONDS_PER_MINUTE

    visible = k_avg < config.visibility_extinction_threshold

    return SegmentCost(
        source=source,
        target=target,
        length_m=length,
        k_avg=k_avg,
        speed_factor=sf,
        travel_time_s=travel_time,
        fed_growth=fed_growth,
        visible=visible,
        k_max=k_max,
        arrival_time_s=arrival_time_s,
    )


@dataclass(frozen=True)
class _FirstLeg:
    """The walk from an agent's position to the next node of a route."""

    waypoints: list[tuple[float, float]]
    length_m: float
    k_avg: float
    k_max: float
    time_s: float


def _first_leg(
    graph: StageGraph,
    agent_position: tuple[float, float],
    node_id: str,
    time_s: float,
    extinction_sampler: ExtinctionSampler,
    config: RouteCostConfig,
    walks: dict[WalkKey, _FirstLeg] | None = None,
    clock: _ForesightClock | None = None,
) -> _FirstLeg:
    """The walk from *agent_position* to *node_id*, sampled for smoke at *time_s*.

    With a *clock*, each point is sampled when the agent reaches it (#650).
    *walks* caches the walks of one agent at one evaluation, keyed on the
    node, and the foreseen walk apart from the one at the decision time. It
    must never be shared between agents: unlike ``cached_segments`` the walk
    starts where this agent stands.
    """
    key: WalkKey = node_id if clock is None else (node_id, "foreseen")
    if walks is not None:
        cached = walks.get(key)
        if cached is not None and cached.time_s == time_s:
            return cached
    node = graph.nodes[node_id]
    waypoints = _walkable_waypoints(
        graph.routing_engine,
        agent_position,
        (node.centroid_x, node.centroid_y),
    )
    k_avg, k_max = _polyline_stats(
        waypoints, time_s, extinction_sampler, config.sampling_step_m, clock
    )
    leg = _FirstLeg(waypoints, _polyline_length(waypoints), k_avg, k_max, time_s)
    if walks is not None:
        walks[key] = leg
    return leg


def _leg_travel_time(
    length_m: float, k_avg: float, config: RouteCostConfig
) -> tuple[float, float]:
    """``(speed_factor, travel_time)`` of a walk through mean extinction *k_avg*.

    Timed as ``evaluate_segment`` times an edge.
    """
    sf = speed_factor_from_extinction(
        k_avg,
        alpha=config.alpha,
        beta=config.beta,
        min_speed_factor=config.min_speed_factor,
    )
    effective_speed = config.base_speed_m_per_s * sf
    travel_time = length_m / effective_speed if effective_speed > 1e-9 else math.inf
    return sf, travel_time


def _dose(fed_rate_per_min: float, travel_time_s: float) -> float:
    """FED taken at *fed_rate_per_min* over *travel_time_s*.

    No dose where the rate is zero, even over an infinite time.
    """
    if fed_rate_per_min == 0.0:
        return 0.0
    return fed_rate_per_min * travel_time_s / _SECONDS_PER_MINUTE


@dataclass(frozen=True)
class _FedRateAsExtinction:
    """A FED-rate sampler read through the extinction-sampler interface.

    Lets ``_polyline_stats`` average the FED rate along a walk at the same
    points it samples the walk's extinction.
    """

    fed_rate_sampler: FedRateSampler

    def sample_extinction(self, time_s: float, x: float, y: float) -> float:
        return self.fed_rate_sampler.sample_fed_rate(time_s, x, y)


def _walk_dose(
    leg: _FirstLeg,
    travel_time_s: float,
    time_s: float,
    fed_rate_sampler: FedRateSampler | None,
    config: RouteCostConfig,
) -> float:
    """The dose of the walk *leg*: its mean FED rate over its time (#171).

    Measured on the walk, as its smoke and time are: the length-weighted
    mean rate at the walk's extinction sample points, every sample read at
    *time_s*, when the walk starts. A single sample would turn one hot
    cell into the dose of a whole walk, which in dense smoke lasts a minute.
    """
    if fed_rate_sampler is None:
        return 0.0
    rate, _ = _polyline_stats(
        leg.waypoints,
        time_s,
        _FedRateAsExtinction(fed_rate_sampler),
        config.sampling_step_m,
    )
    return _dose(rate, travel_time_s)


def _first_share(remaining_m: float, first_length_m: float) -> float:
    """The still-untraversed fraction of a first segment, in (0, 1].

    Floored above zero so an impassable first segment (infinite travel time)
    stays infinite even for an agent standing on its end node.
    """
    if first_length_m <= 1e-9:
        return 1.0
    return min(1.0, max(1e-9, remaining_m / first_length_m))


def _position_aware_length(
    graph: StageGraph,
    path: list[str],
    agent_position: tuple[float, float],
    path_length: float,
    first_length_m: float,
    first_waypoints: list[tuple[float, float]] | None = None,
) -> tuple[float, float]:
    """Haensel path-integrated distance measured from the agent's position.

    Returns ``(effective_length, first_share)``, where ``first_share`` is the
    still-untraversed fraction of the first segment. Smoke, time and dose on
    the first leg are measured on the walk itself, see ``_measure_route``.

    Every route is measured the same way: from where the agent stands to the
    next node on that route, plus the rest of the route from there. The rule is
    deliberately geometry-blind. An earlier version charged a route that
    diverged from the agent's current heading a walk *back to the origin node*
    first, on the reasoning that you must return to a junction to take its other
    arm. That is true of a tree and false of everything else: in an open room
    with two doors it priced a door 3.5 m away at 30 m, and no smoke or dose
    weight could ever overcome the difference. The walkable distance already
    answers the question correctly in both topologies -- around the corner at a
    T-junction, straight across an open floor -- because ``routing_engine``
    computes it on the navigation mesh.

    Without a routing engine ``_walkable_distance`` degrades to Euclidean, which
    can cut through a wall and understate a divergent route. That is a property
    of the fallback, not of this rule, and it applies equally to the route the
    agent is already walking.

    ``first_waypoints``, when given, is the walk from the agent to the next
    node, already computed by the caller; it saves a second engine query.
    """
    first_node = graph.nodes.get(path[0])
    next_node = graph.nodes.get(path[1])
    if first_node is None or next_node is None:
        return path_length, 1.0

    if first_waypoints is None:
        first_waypoints = _walkable_waypoints(
            graph.routing_engine,
            agent_position,
            (next_node.centroid_x, next_node.centroid_y),
        )
    remaining = _polyline_length(first_waypoints)
    return (
        path_length - first_length_m + remaining,
        _first_share(remaining, first_length_m),
    )


def _measure_route(
    graph: StageGraph,
    path: list[str],
    time_s: float,
    current_fed: float,
    extinction_sampler: ExtinctionSampler,
    fed_rate_sampler: FedRateSampler | None,
    config: RouteCostConfig,
    *,
    cached_segments: dict[SegmentCacheKey, SegmentCost] | None = None,
    exit_counts: dict[str, int] | None = None,
    agent_position: tuple[float, float] | None = None,
    walks: dict[WalkKey, _FirstLeg] | None = None,
) -> RouteMeasurements:
    """Measure a route: its segments, length, smoke, dose, time and queue.

    The measuring half of ``evaluate_route``, which see. No limit and no cost
    model's ranking is applied here. *walks* is the per-agent cache of
    ``_first_leg``.
    """
    segments: list[SegmentCost] = []
    walked = 0.0
    end_s, end_owner = (
        _fds_end(extinction_sampler, fed_rate_sampler)
        if config.anticipate
        else (math.inf, None)
    )
    # With anticipation every sample is read when the agent reaches it, and
    # the walk to it is counted from the agent, not from the route's origin
    # node (#650, #171 item 3). Reading each leg at its start alone made the
    # cost jump at every node boundary: the first leg, which starts where the
    # agent stands, was read at the decision time. So the walk to the next
    # node is foreseen first, and the node legs start where it ends.
    foreseen_leg = None
    if (
        config.anticipate
        and agent_position is not None
        and len(path) >= 2
        and graph.nodes.get(path[1]) is not None
    ):
        foreseen_leg = _first_leg(
            graph,
            agent_position,
            path[1],
            time_s,
            extinction_sampler,
            config,
            walks,
            clock=_foresight_clock(time_s, time_s, config, end_s, end_owner),
        )
    # The latest time any sample may be read at; it depends on the decision
    # time when the horizon is finite or the decision is past the FDS output.
    foresight_limit_s = min(time_s + config.foresight_horizon_s, max(time_s, end_s))
    for i in range(len(path) - 1):
        if i == 1 and foreseen_leg is not None:
            walked = foreseen_leg.length_m
        cache_key: SegmentCacheKey = (path[i], path[i + 1])
        # With anticipation an edge costs what it costs *when you get there*,
        # so the same edge on two routes is two different questions and the
        # cache has to key on both. On the exact start time, not a bucket:
        # each sample is read when the agent reaches it, so two agents a
        # fraction of a second apart can read other frames further along
        # the edge, and one's measurement would stand in for the other's.
        t_arrive = _cap_at_fds_end(
            time_s, _arrival_time(time_s, walked, config), end_s, end_owner
        )
        clock = None
        if config.anticipate:
            cache_key = (path[i], path[i + 1], t_arrive, foresight_limit_s)
            clock = _foresight_clock(t_arrive, time_s, config, end_s, end_owner)
        if cached_segments is not None and cache_key in cached_segments:
            seg = cached_segments[cache_key]
        else:
            seg = evaluate_segment(
                graph,
                path[i],
                path[i + 1],
                time_s,
                extinction_sampler,
                fed_rate_sampler,
                config,
                arrival_time_s=t_arrive,
                clock=clock,
            )
            if cached_segments is not None:
                cached_segments[cache_key] = seg
        segments.append(seg)
        walked += seg.length_m

    path_length = sum(s.length_m for s in segments)

    # Position-aware distance (Haensel path-integrated). Default: the geometric
    # node-to-node path_length (used everywhere agent_position is absent).
    effective_length = path_length
    first_share = 1.0
    # The walk from the agent to the next node, through the walkable area,
    # sampled for smoke when the first segment would be reached.
    first_leg = foreseen_leg
    if agent_position is not None and len(path) >= 2:
        if first_leg is None and graph.nodes.get(path[1]) is not None:
            first_leg = _first_leg(
                graph,
                agent_position,
                path[1],
                segments[0].arrival_time_s,
                extinction_sampler,
                config,
                walks,
            )
        effective_length, first_share = _position_aware_length(
            graph,
            path,
            agent_position,
            path_length,
            segments[0].length_m,
            first_leg.waypoints if first_leg is not None else None,
        )

    # Without a walk, the FED already taken on the traversed part of the first
    # segment is in current_fed, so the first segment's dose is charged pro
    # rata to what is left of it.
    shares = [first_share] + [1.0] * (len(segments) - 1)
    weighted = list(zip(shares, segments))
    if first_leg is not None and graph.nodes.get(path[0]) is not None:
        # Smoke and time on the first leg are those of the walk itself: the
        # smoke ahead of the agent on the way to the next node, and none of the
        # smoke behind it. Charging a share of the segment's mean instead
        # billed an agent past a smoke patch for the patch, and a walk that
        # leaves the segment -- back past the origin, or across a room -- for
        # whatever the segment held rather than what lies on the walk. FDS+Evac
        # likewise prices every door from the agent's position (evac.f90,
        # Change_Target_Door).
        legs = [(first_leg.k_avg, first_leg.length_m)] + [
            (s.k_avg, s.length_m) for s in segments[1:]
        ]
        exposure_length = sum(length for _, length in legs)
        total_k_samples = sum(k * length for k, length in legs)
        k_ave = total_k_samples / exposure_length if exposure_length > 1e-9 else 0.0
        walk_time = _leg_travel_time(first_leg.length_m, first_leg.k_avg, config)[1]
        travel_time = sum([walk_time] + [s.travel_time_s for s in segments[1:]])
        # The dose too is that of the walk: the walk back to the origin node
        # is charged, and a dose already incurred is in current_fed (#171).
        fed_growth = _walk_dose(
            first_leg, walk_time, time_s, fed_rate_sampler, config
        ) + sum(s.fed_growth for s in segments[1:])
        clear_travel_time = _leg_travel_time(exposure_length, 0.0, config)[1]
    else:
        exposure_length = sum(w * s.length_m for w, s in weighted)
        total_k_samples = sum(w * s.k_avg * s.length_m for w, s in weighted)
        k_ave = total_k_samples / exposure_length if exposure_length > 1e-9 else 0.0
        travel_time = sum(w * s.travel_time_s for w, s in weighted)
        clear_travel_time = _leg_travel_time(exposure_length, 0.0, config)[1]
        # The share is capped at 1, so an agent behind the route's origin node
        # would be timed over the node legs alone and not the walk to the
        # origin. That stretch is timed at the route's mean pace, the same
        # assumption tau = K_ave * effective_length makes about its extinction.
        # Only ever a stretch, never a shrink, so an impassable route stays
        # infinite.
        if effective_length > exposure_length > 1e-9:
            travel_time *= effective_length / exposure_length
            clear_travel_time *= effective_length / exposure_length
        fed_growth = sum(w * s.fed_growth for w, s in weighted)
    fed_max = current_fed + fed_growth
    # The worst point on the route, not its average: a route is refused because
    # of the wall of smoke in it, and a mean over 30 clear metres and 3 blind
    # ones reports a walk anyone would take.
    #
    # The first segment is resampled from where the agent stands, because the
    # rest of it is behind them. Taking the whole segment would gate every route
    # through that node on smoke already walked through -- and only the agent's
    # *current* route has a partly-traversed first leg, so the error falls on
    # the committed route alone and pushes the agent off it. Deliberately not
    # written to cached_segments: those entries are shared between agents in one
    # pass and this stretch belongs to one agent's position.
    first_k_max = segments[0].k_max if segments else 0.0
    first_k_avg = segments[0].k_avg if segments else 0.0
    # Resampled for every route, not only the one the agent is walking. The
    # share is clamped at 1.0, so a route the agent has diverged from is
    # otherwise charged its whole first leg including the stretch behind the
    # agent -- and with a binary clean test that asymmetry decided membership:
    # an agent past a smoke blob read its committed route as clean and every
    # rival as dirty, on smoke none of them would walk through.
    #
    # Sampled along the walk itself, around walls, at sampling_step_m over its
    # real length -- which, behind the origin node, is longer than the capped
    # first_share of the segment.
    if first_leg is not None:
        first_k_avg, first_k_max = first_leg.k_avg, first_leg.k_max
    k_max = max(
        [first_k_max] + [s.k_max for _, s in weighted[1:]],
        default=0.0,
    )
    # The smokiest *leg* of the route, each leg taken as its own mean. Not the
    # route mean: that dilutes a smoky stretch with however much clear corridor
    # follows it, so a long route can look cleaner than a short one by being
    # long -- the mirror of the length penalty this model was built to remove.
    # Not the worst *sample* either, which is the step function that made the
    # sighting distance jump between ticks. FDS+Evac applies its 0.03 /m to
    # K_ave_Door, a per-door average, for the same reason.
    k_leg_max = max(
        [first_k_avg] + [s.k_avg for _, s in weighted[1:]],
        default=0.0,
    )
    # Route optical depth: the soot column still to be walked through, and the
    # whole of the smoke criterion. tau = K_ave * L is the integral of
    # extinction along the path, not the sighting distance it grew out of --
    # Jin's S = c/K measures contrast along a straight unobstructed line to a
    # sign, and integrating K around two corners measures exposure instead. The
    # two coincide only on a straight corridor.
    #
    # The mean rather than the worst sample: a maximum over sampled cells is a
    # step function of where the agent stands, and the same 28.9 m route
    # reported 91 m of sight, then 8 m, then 91 m again on consecutive seconds,
    # taking the ordering with it. k_max_route is still reported but no
    # longer decides anything; tau orders and holds the all-refused fallback
    # too (#458).
    tau_route = k_ave * effective_length

    # Composite cost: effective_length * (1 + w_smoke * K_ave) + w_fed * FED_max
    # Under "gate" this is reported but does not rank: see rank_routes.
    composite = (
        effective_length * (1.0 + config.w_smoke * k_ave) + config.w_fed * fed_max
    )

    # Queue cost: convert queue delay to distance-equivalent units.
    queue_time = 0.0
    if exit_counts is not None and config.w_queue > 0 and path:
        _exit_id = path[-1]
        n_exit = exit_counts.get(_exit_id, 0)
        exit_node = graph.nodes.get(_exit_id)
        capacity = (
            exit_node.capacity_agents_per_s
            if exit_node is not None and exit_node.capacity_agents_per_s is not None
            else config.default_exit_capacity
        )
        if capacity > 0:
            queue_time = n_exit / capacity
            queue_distance = config.base_speed_m_per_s * queue_time
            composite += config.w_queue * queue_distance

    return RouteMeasurements(
        exit_id=path[-1] if path else "",
        path=path,
        segments=segments,
        path_length_m=path_length,
        effective_length_m=effective_length,
        k_ave_route=k_ave,
        travel_time_s=travel_time,
        fed_max_route=fed_max,
        composite_cost=composite,
        queue_time_s=queue_time,
        k_max_route=k_max,
        tau_route=tau_route,
        k_leg_max=k_leg_max,
        clear_travel_time_s=clear_travel_time,
    )


# ── Cost-model policies ──────────────────────────────────────────────


def _fed_limit(
    config: RouteCostConfig, exit_id: str, current_exit: str | None
) -> float:
    """The predicted dose above which the route to *exit_id* is refused.

    Asymmetric FED rejection (deadband). The agent's current exit keeps the
    full threshold so it always flees the instant dose crosses incapacitation.
    A different exit is held to the stricter fed_return_margin fraction, so the
    agent only switches onto it once its dose is clearly safe — this stops the
    flip-flop when a marginal route's predicted dose wobbles around 1.0.
    current_exit=None (e.g. initial choice, or a direct evaluate_route call)
    falls back to the plain threshold for every route.
    """
    is_current = current_exit is not None and exit_id == current_exit
    fed_threshold = config.fed_rejection_threshold
    if not is_current and current_exit is not None:
        fed_threshold *= config.fed_return_margin
    return fed_threshold


def _fed_violations(
    m: RouteMeasurements, config: RouteCostConfig, current_exit: str | None
) -> list[RouteViolation]:
    """The FED violation of a measured route, if it has one."""
    fed_max = m.fed_max_route
    fed_threshold = _fed_limit(config, m.exit_id, current_exit)
    if fed_max > fed_threshold:
        return [
            RouteViolation(
                kind="fed",
                reason=f"FED_max {fed_max:.3f} > {fed_threshold:.3f}",
                measured=fed_max,
                limit=fed_threshold,
            )
        ]
    return []


def _clean_limit(
    config: RouteCostConfig, exit_id: str, current_exit: str | None
) -> float:
    """The smokiest leg the route to *exit_id* may have and still be clean.

    Tier 1. The exit the agent is already heading for keeps its place in the
    clean set a little past the criterion, so membership does not flicker.
    """
    is_current = current_exit is not None and exit_id == current_exit
    clean_limit = config.clean_extinction_threshold
    if is_current:
        clean_limit /= max(config.clean_exit_margin, 1e-9)
    return clean_limit


class RouteModePolicy(Protocol):
    """What a cost model decides about a measured route."""

    def edge_weight(self, seg: SegmentCost, config: RouteCostConfig) -> float: ...

    def feasibility(
        self,
        m: RouteMeasurements,
        config: RouteCostConfig,
        current_exit: str | None,
    ) -> RouteFeasibility: ...

    def rank_cost(self, m: RouteMeasurements, config: RouteCostConfig) -> float: ...

    def apply_candidate_set_rules(
        self, costs: list[RouteCost], config: RouteCostConfig
    ) -> list[RouteCost]: ...

    def order_key(
        self, rc: RouteCost, config: RouteCostConfig, current_exit: str | None
    ) -> tuple[int, int, float, float, int]: ...

    def improvement(
        self, candidate: RouteCost, old_rc: RouteCost, config: RerouteConfig
    ) -> bool: ...

    def anchor_allows(
        self,
        candidate: RouteCost,
        old_rc: RouteCost | None,
        config: RerouteConfig,
    ) -> bool: ...

    def scan_before_current_exit(self) -> bool: ...


class _AnchoredPolicy:
    """The exit-switch anchor, shared by both cost models."""

    def improvement(
        self, candidate: RouteCost, old_rc: RouteCost, config: RerouteConfig
    ) -> bool:
        raise NotImplementedError

    def anchor_allows(
        self,
        candidate: RouteCost,
        old_rc: RouteCost | None,
        config: RerouteConfig,
    ) -> bool:
        """Whether the agent may leave *old_rc* for *candidate*.

        No baseline allows, a hazard the agent must flee allows, and between
        two refused routes only a clearly lower tau allows (#458): the time
        anchor does not decide there. Otherwise the cost model says whether
        *candidate* is enough better.
        """
        if old_rc is None:
            return True
        # Must-flee comes first, so a refused rival the agent must also flee
        # is allowed here without the tau margin _apply_fallback asks of it.
        # In a reevaluation that pair never reaches the anchor: when every
        # route is refused, the fallback keeps the current exit ahead of such
        # a rival unless its tau clears the margin, and the scan stops at the
        # current exit (#128).
        if _must_flee_rejection(old_rc, config.cost_config):
            return True
        if not candidate.feasible and not old_rc.feasible:
            return _fallback_rival_wins(candidate, old_rc, config.cost_config)
        return self.improvement(candidate, old_rc, config)


class AdditivePolicy(_AnchoredPolicy):
    """The historical w_smoke/w_fed toll: the composite ranks, dose refuses."""

    def improvement(
        self, candidate: RouteCost, old_rc: RouteCost, config: RerouteConfig
    ) -> bool:
        return _clears_exit_anchor(candidate, old_rc, config)

    def scan_before_current_exit(self) -> bool:
        return False

    def edge_weight(self, seg: SegmentCost, config: RouteCostConfig) -> float:
        # Additive decomposition of the composite formula. current_fed
        # is constant across routes for one agent, so omitting it from
        # edge costs does not affect ranking.
        return (
            seg.length_m * (1.0 + config.w_smoke * seg.k_avg)
            + config.w_fed * seg.fed_growth
        )

    def feasibility(
        self,
        m: RouteMeasurements,
        config: RouteCostConfig,
        current_exit: str | None,
    ) -> RouteFeasibility:
        violations = _fed_violations(m, config, current_exit)
        rejected = bool(violations)
        return RouteFeasibility(
            feasible=not rejected,
            rejected=rejected,
            rejection_reason=violations[-1].reason if violations else None,
            violations=tuple(violations),
        )

    def rank_cost(self, m: RouteMeasurements, config: RouteCostConfig) -> float:
        return m.composite_cost

    def apply_candidate_set_rules(
        self, costs: list[RouteCost], config: RouteCostConfig
    ) -> list[RouteCost]:
        # Sign legibility is not consulted here.  It decides what enters the
        # agent's cognitive map (see cognitive_map.expand_from_visibility), and
        # the map decides what Dijkstra can see -- so an unknown exit is absent
        # from the graph rather than present-and-vetoed.  Checking it again here
        # double-gated the same criterion, blocked agents who already knew the
        # building, and forbade an agent from using an exit it had legitimately
        # learned once the sign went out of view.
        # K_vis fallback: reject routes where all segments are non-visible,
        # but only if at least one other route has visibility.
        #
        # Additive only (GatePolicy has no candidate-set rule). It sets
        # `rejected` without clearing `feasible`, so the two fields disagree.
        any_visible = any(
            any(s.visible for s in rc.segments) for rc in costs if not rc.rejected
        )
        if any_visible:
            updated = []
            for rc in costs:
                if not rc.rejected and not any(s.visible for s in rc.segments):
                    rc = replace(
                        rc,
                        rejected=True,
                        rejection_reason="all segments non-visible",
                        violation_kinds=(
                            *rc.violation_kinds,
                            "all_segments_non_visible",
                        ),
                    )
                updated.append(rc)
            costs = updated
        return costs

    def order_key(
        self, rc: RouteCost, config: RouteCostConfig, current_exit: str | None
    ) -> tuple[int, int, float, float, int]:
        # Ordering. Under "additive" the composite decides, as it always has.
        return (
            1 if rc.rejected else 0,
            0,
            0.0,
            rc.rank_cost,
            len(rc.path),
        )


class GatePolicy(_AnchoredPolicy):
    """Smoke decides which exits remain available; time ranks them."""

    @staticmethod
    def _clean_bypass(candidate: RouteCost, old_rc: RouteCost) -> bool:
        """A clean candidate leaves a dirty exit whatever the anchor says."""
        return candidate.clean and not old_rc.clean

    @staticmethod
    def _tau_band(
        candidate: RouteCost, old_rc: RouteCost, cost_config: RouteCostConfig
    ) -> int:
        """+1 if *candidate* is clearly cleaner, -1 if clearly dirtier, else 0.

        A deadband on the quantity the routes are ordered by, symmetric. Clearly
        cleaner is adopted, clearly dirtier is refused, and only a tie falls
        through to time and queue.

        The refusal half was missing, and its absence was the oscillation:
        leaving an exit had to clear a margin in tau, while returning went
        straight to the time comparison, which the nearer exit wins
        unconditionally and permanently. Departure cost a margin and the return
        was free. Same shape as the clean tier's failure one level up --
        hysteresis applied to one side of a disjunction is not hysteresis.

        Absolute rather than a ratio: tau is zero in clear air, where a ratio
        reads 0 < 0, no agent could switch at all, and a congestion weight would
        count for nothing exactly where decks calibrate one.
        """
        margin = cost_config.tau_max * cost_config.tau_deadband
        delta = old_rc.tau_route - candidate.tau_route
        if delta > margin:
            return 1
        if delta < -margin:
            return -1
        return 0

    def improvement(
        self, candidate: RouteCost, old_rc: RouteCost, config: RerouteConfig
    ) -> bool:
        if self._clean_bypass(candidate, old_rc):
            return True
        if not candidate.feasible:
            return _clears_exit_anchor(candidate, old_rc, config)
        band = self._tau_band(candidate, old_rc, config.cost_config)
        if band > 0:
            return True
        if band < 0:
            return False
        return _clears_exit_anchor(candidate, old_rc, config)

    def scan_before_current_exit(self) -> bool:
        return True

    def edge_weight(self, seg: SegmentCost, config: RouteCostConfig) -> float:
        # Per-edge cost. Under "gate" this is the edge's own optical
        # depth, the same quantity the routes are ranked and refused on, so
        # the path chosen to reach an exit and the choice between exits are
        # finally one objective. Before this, Dijkstra minimised the
        # additive composite and the exit was then judged on tau, which
        # meant a gate could refuse an exit on a smoky path while a longer
        # passable path to the same exit existed and was never offered.
        #
        # A floor on length keeps a clear-air graph from collapsing to
        # all-zero weights, where every path ties and Dijkstra returns an
        # arbitrary one.
        return seg.k_avg * seg.length_m + 1e-6 * (seg.length_m)

    @staticmethod
    def _tau_budget(
        config: RouteCostConfig, exit_id: str, current_exit: str | None
    ) -> float:
        """The optical depth above which the route to *exit_id* is refused.

        A rival exit is held to a stricter budget than the one the agent
        already walks to, so a route sitting near tau_max does not toggle in
        and out of the feasible set and take the crowd with it.
        """
        is_current = current_exit is not None and exit_id == current_exit
        budget = config.tau_max
        if not is_current and current_exit is not None:
            budget *= config.tau_return_margin
        return budget

    def feasibility(
        self,
        m: RouteMeasurements,
        config: RouteCostConfig,
        current_exit: str | None,
    ) -> RouteFeasibility:
        violations = _fed_violations(m, config, current_exit)
        feasible = not violations
        # Sight gate: FDS+Evac's rule that a door is only a candidate while the
        # agent can see a useful fraction of the way to it (evac.f90,
        # Change_Target_Door). Being relative to distance is what lets the same
        # smoke allow a near exit and refuse a far one.
        #
        # The gate: refuse a route whose optical depth exceeds the budget.
        # Appended after the dose, so a route over both limits reports tau.
        budget = self._tau_budget(config, m.exit_id, current_exit)
        tau_route = m.tau_route
        if tau_route > budget:
            feasible = False
            violations.append(
                RouteViolation(
                    kind="tau",
                    reason=(
                        f"tau {tau_route:.2f} > {budget:.2f} "
                        f"(K_ave {m.k_ave_route:.3f} x {m.effective_length_m:.1f} m)"
                    ),
                    measured=tau_route,
                    limit=budget,
                )
            )
        return RouteFeasibility(
            feasible=feasible,
            rejected=bool(violations),
            rejection_reason=violations[-1].reason if violations else None,
            violations=tuple(violations),
        )

    def rank_cost(self, m: RouteMeasurements, config: RouteCostConfig) -> float:
        # Queue delay is time, so it belongs beside travel time rather than in
        # the composite the gate ignores -- otherwise opting into congestion-
        # aware routing (w_queue) would silently do nothing.
        # One currency: the quantity that refuses a route also ranks it and is
        # what the anchor compares. Ranking on tau while anchoring on time left
        # the two disagreeing, and a separate "clearly cleaner" bypass fired
        # every time the field flickered -- 109 returns to abandoned exits on
        # l_corridor.
        #
        # rank_cost stays a time. tau orders the routes (see rank_routes), but
        # it is zero in clear air, so using it for the anchor's ratio test would
        # make every comparison 0 < 0 -- no agent could ever switch, and a
        # congestion weight would count for nothing exactly where decks
        # calibrate one.
        return m.travel_time_s + m.queue_time_s * config.w_queue

    def apply_candidate_set_rules(
        self, costs: list[RouteCost], config: RouteCostConfig
    ) -> list[RouteCost]:
        # The additive K_vis screen is retired under the gate. It was a
        # *second* smoke criterion on top of the sight test, and a bare
        # threshold on K with no hysteresis, so a route sitting near it toggled
        # every tick: measured on world100, a 9 m route with a 2 s travel time
        # was struck out and reinstated repeatedly while the agent bounced to a
        # 27 m rival and back. It also set `rejected` without clearing
        # `feasible`, leaving the two fields disagreeing. The plan retired it
        # under the gate; this is that retirement.
        return costs

    @staticmethod
    def _ordering_tau(
        rc: RouteCost, config: RouteCostConfig, current_exit: str | None
    ) -> float:
        # The exit the agent already walks to has its optical depth discounted,
        # so it keeps its place unless a rival is clearly cleaner rather than
        # momentarily cleaner. This is FDS+Evac's FAC_DOOR_OLD2 = 0.9
        # (evac.f90:1507), applied at :16467 inside the IF that ranks doors --
        # the same position, not a separate veto afterwards. Hysteresis belongs
        # in the ordering: bolted on after it, the ordering and the veto
        # disagree and the agent oscillates between what each of them prefers.
        if current_exit is not None and rc.exit_id == current_exit:
            return rc.tau_route * config.current_exit_discount
        return rc.tau_route

    def order_key(
        self, rc: RouteCost, config: RouteCostConfig, current_exit: str | None
    ) -> tuple[int, int, float, float, int]:
        # Ordering. Under "gate" distance decides among routes that are still
        # available, and a route a whole visibility band clearer wins first:
        # smoke says which exits exist, not how much each metre of them is
        # worth.
        # Under "gate" the route's optical depth decides and travel time breaks
        # ties: tau = K_ave * L already contains the distance, so two routes
        # through equally thin haze order by length and in clear air every tau is
        # zero and time decides alone. A cleaner route wins only by enough less
        # smoke to pay for its extra metres -- which is the property a visibility
        # band could not have, since a band compared cleanliness with no reference
        # to how far the agent had to carry it.
        prefer_clean = config.clean_extinction_threshold > 0.0
        tier = 0 if (rc.clean or not prefer_clean) else 1
        return (
            1 if rc.rejected else 0,
            tier,
            self._ordering_tau(rc, config, current_exit),
            rc.rank_cost,
            len(rc.path),
        )


_GATE_POLICY = GatePolicy()
_ADDITIVE_POLICY = AdditivePolicy()


def policy_for(config: RouteCostConfig) -> RouteModePolicy:
    """The policy named by ``config.cost_model``; ValueError for any other name."""
    if config.cost_model == "gate":
        return _GATE_POLICY
    if config.cost_model == "additive":
        return _ADDITIVE_POLICY
    raise _unknown_cost_model(config.cost_model)


def _assess_measurements(
    m: RouteMeasurements, config: RouteCostConfig, current_exit: str | None
) -> RouteAssessment:
    """Judge a measured route under the configured cost model."""
    policy = policy_for(config)
    feasibility = policy.feasibility(m, config, current_exit)
    rank_cost = policy.rank_cost(m, config)
    clean_limit = _clean_limit(config, m.exit_id, current_exit)
    # A zero threshold turns the tier off rather than declaring clear air
    # clean, which would make every route tier 0 and change nothing anyway --
    # but the explicit form says which is meant.
    clean = clean_limit > 0.0 and m.k_leg_max <= clean_limit
    return RouteAssessment(
        measurements=m,
        feasibility=feasibility,
        rank_cost=rank_cost,
        clean=clean,
    )


def evaluate_route(
    graph: StageGraph,
    path: list[str],
    time_s: float,
    current_fed: float,
    extinction_sampler: ExtinctionSampler,
    fed_rate_sampler: FedRateSampler | None,
    config: RouteCostConfig,
    *,
    cached_segments: dict[SegmentCacheKey, SegmentCost] | None = None,
    exit_counts: dict[str, int] | None = None,
    current_exit: str | None = None,
    agent_position: tuple[float, float] | None = None,
    current_target: str | None = None,
) -> RouteCost:
    """Evaluate the composite cost for a full route (list of stage IDs).

    When ``agent_position`` is given, the distance is measured from where the
    agent actually is (Haensel 2014 "path-integrated distance") instead of from
    the route's first graph node, so an agent 1 m from one exit is not priced as
    if standing at the far upstream junction. Every route is measured the same
    way, whatever the agent is currently heading for -- see
    ``_position_aware_length``. The first leg is the walk from the agent to
    ``path[1]``: its smoke and travel time are those of the walk, so smoke
    behind the agent is not charged and smoke on a walk that leaves the first
    segment is. Its dose is that of the walk too, so the walk back to the
    origin node is charged, and a dose already incurred -- carried in
    ``current_fed`` -- is not charged a second time.

    ``current_target`` is accepted and ignored; it is kept so callers that
    already thread it through do not have to change, and so the parameter is
    available if a future rule needs the agent's heading.
    """
    m = _measure_route(
        graph,
        path,
        time_s,
        current_fed,
        extinction_sampler,
        fed_rate_sampler,
        config,
        cached_segments=cached_segments,
        exit_counts=exit_counts,
        agent_position=agent_position,
    )
    return _project_route_cost(_assess_measurements(m, config, current_exit))


def _generate_candidates(
    graph: StageGraph,
    source: str,
    time_s: float,
    extinction_sampler: ExtinctionSampler,
    fed_rate_sampler: FedRateSampler | None,
    config: RouteCostConfig,
    policy: RouteModePolicy,
    *,
    cached_segments: dict[SegmentCacheKey, SegmentCost] | None = None,
    agent_position: tuple[float, float] | None = None,
    current_target: str | None = None,
    walks: dict[WalkKey, _FirstLeg] | None = None,
) -> dict[str, tuple[float, list[str]]]:
    """The cheapest path from *source* to every reachable exit under *policy*.

    Computes dynamic edge weights from current smoke/FED conditions, then runs
    Dijkstra with those weights. *graph* is already restricted to what the
    agent knows. Returns exit_id -> (cost, path), as
    ``StageGraph.shortest_paths_to_exits``.

    With *agent_position* the search starts where the agent stands, not at
    *source*: see ``_first_hops``.
    """
    # Phase 1: evaluate all edges to get dynamic costs.
    dynamic_weights: dict[tuple[str, str], float] = {}
    for src_id, edges in graph.edges.items():
        for edge in edges:
            cache_key = (edge.source, edge.target)
            if cached_segments is not None and cache_key in cached_segments:
                seg = cached_segments[cache_key]
            else:
                seg = evaluate_segment(
                    graph,
                    edge.source,
                    edge.target,
                    time_s,
                    extinction_sampler,
                    fed_rate_sampler,
                    config,
                )
                if cached_segments is not None:
                    cached_segments[cache_key] = seg
            dynamic_weights[cache_key] = policy.edge_weight(seg, config)

    first_hops = None
    if agent_position is not None and _search_from_position(graph, source):
        first_hops = _first_hops(
            graph,
            source,
            agent_position,
            current_target,
            time_s,
            extinction_sampler,
            fed_rate_sampler,
            config,
            policy,
            walks,
        )

    # Phase 2: Dijkstra with dynamic weights.
    all_paths = graph.shortest_paths_to_exits(
        source, dynamic_weights=dynamic_weights, first_hops=first_hops
    )
    return all_paths


def _search_from_position(graph: StageGraph, source: str) -> bool:
    """Whether the candidate search may start from the agent's position.

    Not from an exit, which is its own route, and not from a node outside
    the graph, which has none.
    """
    node = graph.nodes.get(source)
    return node is not None and node.stage_type != "exit"


def _first_hops(
    graph: StageGraph,
    source: str,
    agent_position: tuple[float, float],
    current_target: str | None,
    time_s: float,
    extinction_sampler: ExtinctionSampler,
    fed_rate_sampler: FedRateSampler | None,
    config: RouteCostConfig,
    policy: RouteModePolicy,
    walks: dict[WalkKey, _FirstLeg] | None,
) -> dict[str, float]:
    """The cost of the walk from the agent to each node it can head for first.

    Those nodes are *source*'s successors in *graph* and the node the agent is
    walking to. Each walk is weighted by *policy* as an edge, measured as
    ``_measure_route`` measures a first leg: the smoke on the walk, its time,
    and its dose.
    So every exit, the agent's own included, is searched for from where the
    agent stands and not from the node it last left.
    """
    targets = [e.target for e in graph.edges.get(source, [])]
    if (
        current_target is not None
        and current_target in graph.nodes
        and current_target != source
        and current_target not in targets
    ):
        targets.append(current_target)
    hops: dict[str, float] = {}
    for node_id in targets:
        if node_id == source or node_id in hops:
            continue
        leg = _first_leg(
            graph,
            agent_position,
            node_id,
            time_s,
            extinction_sampler,
            config,
            walks,
        )
        speed_factor, travel_time = _leg_travel_time(leg.length_m, leg.k_avg, config)
        walk = SegmentCost(
            source=source,
            target=node_id,
            length_m=leg.length_m,
            k_avg=leg.k_avg,
            speed_factor=speed_factor,
            travel_time_s=travel_time,
            fed_growth=_walk_dose(leg, travel_time, time_s, fed_rate_sampler, config),
            visible=leg.k_avg < config.visibility_extinction_threshold,
            k_max=leg.k_max,
            arrival_time_s=time_s,
        )
        hops[node_id] = policy.edge_weight(walk, config)
    return hops


def _fallback_rival_wins(
    rival: RouteCost, current: RouteCost, config: RouteCostConfig
) -> bool:
    """Whether a refused *rival* may displace the refused *current* exit.

    Only if its optical depth is more than fallback_switch_margin lower
    (#458): ``rival < current * (1 - margin)``.
    The comparison is strict, so a rival at exactly the margin holds, and
    taus within ``EPS_TAU`` tie and hold too, so round-off (or both taus 0)
    never moves an agent. One rule for the fallback order and the anchor:
    a k_max hold with a time anchor behind it kept agents on an exit with
    three times the smoke.

    A route the agent must flee never displaces one it need not flee, and
    always yields to one (#128); the tau rule decides only between two of a
    kind.
    """
    rival_flee = _must_flee_rejection(rival, config)
    current_flee = _must_flee_rejection(current, config)
    if rival_flee != current_flee:
        return current_flee
    if taus_tie(rival.tau_route, current.tau_route):
        return False
    margin = 1.0 - config.fallback_switch_margin
    return rival.tau_route < current.tau_route * margin


def _apply_fallback(
    costs: list[RouteCost], config: RouteCostConfig, current_exit: str | None
) -> list[RouteCost]:
    """Un-reject the least bad route when every route is refused.

    Fallback: with every route refused the agent still has to go somewhere,
    and the least bad one is one it need not flee (#128), then the one with
    the least smoke to walk through, the smallest optical depth tau, then the
    quickest (#458).

    Refusal is never remembered: the sight criterion is measured against the
    distance *still to walk*, so it relaxes as the agent closes on an exit and
    the smoke that refused a door at 40 m accepts it at 2 m. Recomputing every
    tick is what lets that happen. The price is that in a fire smoky enough to
    refuse everything -- which is most of a real run, see
    docs/gate-model-review-notes.md -- the ordering follows the field, so the
    current exit is held unless a rival's optical depth is clearly lower
    (``_fallback_rival_wins``).

    Ordered by optical depth here too, not by the worst sample: ordering
    refused routes by k_max alone once put a 51 m route ahead of a 22 m one
    on 2.0 m of sight against 1.8 m -- two tenths of a metre of visibility,
    neither usable, deciding a 29 m detour. tau carries the distance with it,
    so the least-bad walk is the one with least smoke to walk through.

    Applies under both cost models. Only the promoted route changes:
    ``rejected`` is cleared, the reason gains a "fallback: " prefix, and
    ``feasible`` is left as it was.
    """
    if costs and all(rc.rejected for rc in costs):
        costs.sort(
            key=lambda rc: (
                _must_flee_rejection(rc, config),
                rc.tau_route,
                rc.rank_cost,
            )
        )
        current = next((rc for rc in costs if rc.exit_id == current_exit), None)
        if current is not None and costs[0].exit_id != current.exit_id:
            if not _fallback_rival_wins(costs[0], current, config):
                costs = [current] + [rc for rc in costs if rc is not current]
        best = costs[0]
        costs[0] = replace(
            best,
            rejected=False,
            rejection_reason=f"fallback: {best.rejection_reason}",
        )
    return costs


def rank_routes(
    graph: StageGraph,
    source: str,
    time_s: float,
    current_fed: float,
    extinction_sampler: ExtinctionSampler,
    fed_rate_sampler: FedRateSampler | None,
    config: RouteCostConfig,
    *,
    cached_segments: dict[SegmentCacheKey, SegmentCost] | None = None,
    exit_counts: dict[str, int] | None = None,
    cognitive_map=None,
    agent_position: tuple[float, float] | None = None,
    current_exit: str | None = None,
    current_target: str | None = None,
    current_path: list[str] | None = None,
) -> list[RouteCost]:
    """Evaluate and rank all routes from *source* to reachable exits.

    Computes dynamic edge weights from current smoke/FED conditions,
    then runs Dijkstra with those weights so pathfinding picks the
    cheapest path under current conditions (not just the geometrically
    shortest).

    With *agent_position* the search starts where the agent stands, so every
    exit is priced on the best path from there (see ``_first_hops``).
    *current_path* is the path the agent is walking; when it leads to
    *current_exit* and orders ahead of the path the search found to that
    exit, it is that exit's entry. The search weighs edges at the present
    time while routes are measured on arrival, so without it the agent's own
    exit could be priced above the walk it is on.

    Returns routes sorted by composite cost (lowest first).
    Rejected routes are sorted to the end.
    If all routes are rejected, the least-bad route is un-rejected
    as a fallback.

    An exit closed at *time_s* is not ranked.
    """
    graph = without_closed_stages(graph, time_s)
    # Restrict graph to agent's known subgraph (discovery mode).
    if cognitive_map is not None:
        from .cognitive_map import cognitive_subgraph

        graph = cognitive_subgraph(cognitive_map, graph)

    policy = policy_for(config)
    # The walks from this agent to the nodes it may head for, shared by the
    # search and the measurement below; never by another agent.
    walks: dict[WalkKey, _FirstLeg] = {}
    all_paths = _generate_candidates(
        graph,
        source,
        time_s,
        extinction_sampler,
        fed_rate_sampler,
        config,
        policy,
        cached_segments=cached_segments,
        agent_position=agent_position,
        current_target=current_target,
        walks=walks,
    )
    if not all_paths:
        return []

    def measure(path: list[str]) -> RouteCost:
        m = _measure_route(
            graph,
            path,
            time_s,
            current_fed,
            extinction_sampler,
            fed_rate_sampler,
            config,
            cached_segments=cached_segments,
            exit_counts=exit_counts,
            agent_position=agent_position,
            walks=walks,
        )
        return _project_route_cost(_assess_measurements(m, config, current_exit))

    # Phase 3: evaluate full routes (reusing cached segments).
    costs = [measure(path) for _dist, path in all_paths.values()]

    def key(rc: RouteCost) -> tuple[int, int, float, float, int]:
        return policy.order_key(rc, config, current_exit)

    if (
        agent_position is not None
        and current_path is not None
        and _prices_current_path(graph, current_path, current_exit)
    ):
        walked = measure(current_path)
        costs = [
            walked
            if rc.exit_id == current_exit
            and _order_routes([rc, walked], key)[0] is walked
            else rc
            for rc in costs
        ]

    costs = policy.apply_candidate_set_rules(costs, config)
    return _apply_fallback(_order_routes(costs, key), config, current_exit)


def _order_routes(
    costs: list[RouteCost],
    key: Callable[[RouteCost], tuple[int, int, float, float, int]],
) -> list[RouteCost]:
    """Sort *costs* on *key*, with ordering taus that tie counted as equal.

    A pairwise tolerance is not transitive, so it cannot drive a comparison
    sort: taus 0, 0.75e-9 and 1.5e-9 with successively faster routes would
    form a preference cycle. Instead, routes sorted on *key* are grouped while
    each ordering tau ties the previous one (:func:`taus_tie`) within the same
    rejection state and tier, and every route in a group takes the group's
    smallest tau. Any two taus within ``EPS_TAU`` then share a group, and the
    remaining keys decide among them, then the input order -- never the raw
    tau. A chain of routes can stretch one group past ``EPS_TAU``. Under
    "additive" the tau slot is always 0.0, so the order is the plain stable
    sort on *key*.
    """
    keys = [key(rc) for rc in costs]
    by_raw = sorted(range(len(costs)), key=lambda i: keys[i])
    group_tau = [0.0] * len(costs)
    prev: tuple[int, int, float, float, int] | None = None
    current = 0.0
    for i in by_raw:
        k = keys[i]
        if prev is None or prev[:2] != k[:2] or not taus_tie(prev[2], k[2]):
            current = k[2]
        group_tau[i] = current
        prev = k
    order = sorted(
        range(len(costs)),
        key=lambda i: (keys[i][0], keys[i][1], group_tau[i], *keys[i][3:], i),
    )
    return [costs[i] for i in order]


def _prices_current_path(
    graph: StageGraph, current_path: list[str], current_exit: str | None
) -> bool:
    """Whether *current_path* is a route to *current_exit* within *graph*."""
    return (
        current_exit is not None
        and len(current_path) >= 2
        and current_path[-1] == current_exit
        and all(n in graph.nodes for n in current_path)
    )


# ── Dynamic rerouting (Phase 4) ──────────────────────────────────────


def _must_flee_rejection(rc: RouteCost, cost_config: RouteCostConfig) -> bool:
    """Whether the agent must abandon its current exit regardless of hysteresis.

    Only genuine hazards bypass the exit-switch anchor:

    * **FED-lethal** — predicted dose incapacitates the agent. Always flee.
    * **Impassably dense smoke** — the route's average extinction exceeds
      ``impassable_extinction_threshold`` (visibility of order a metre). Flee.

    A *mild* visibility rejection (``all segments non-visible`` from light haze,
    or ``next_node_not_visible`` from an unreadable sign) is NOT a hazard: the
    smoke is already in the route cost via ``w_smoke * k_ave``, so also letting
    the rejection bypass the anchor double-counts it and flips the agent off its
    cheaper committed exit onto a costlier one, then back next tick. Those stay
    subject to the anchor. The demo's flip-flop was exactly this — mild smoke
    (k_ave ~0.5-0.9) tripping the binary 0.5 visibility threshold every tick.

    The test reads the limits the route breaks (``violation_kinds``), not
    its public reason, and not ``rejected``: a route over both the FED and the
    tau limit reports ``tau ...`` but is still lethal, and a route the
    all-refused fallback promoted keeps its hazard (#128).

    One hazard this does **not** catch, by construction:

    * **Heat.** The convective heat dose is tracked per agent and can
      incapacitate on its own
      (``TenabilityConfig.resolved_heat_fed_threshold``), but it
      reaches no part of route choice -- ``rank_routes`` is given the gas dose
      and a gas-only rate sampler. An agent can therefore walk into a route
      that will incapacitate it thermally, and nothing here will reject it.
    """
    if "fed" in rc.violation_kinds:
        return True
    if "all_segments_non_visible" in rc.violation_kinds:
        return rc.k_ave_route > cost_config.impassable_extinction_threshold
    return False


@dataclass(frozen=True)
class RerouteConfig:
    """Settings for periodic route reevaluation."""

    reevaluation_interval_s: float = 10.0
    cost_config: RouteCostConfig = field(default_factory=RouteCostConfig)
    # Anchoring / hysteresis for switching to a *different* exit: a rival exit is
    # only adopted if its cost is below this fraction of the current exit's cost
    # (i.e. it must be clearly better, not marginally). Mirrors FDS+Evac's
    # FAC_DOOR_WAIT patience factor (default 0.9 there). Convention from the
    # reference implementation, NOT calibrated — see docs/rerouting-oscillation-notes.md.
    exit_switch_anchor: float = 0.9


@dataclass
class AgentRouteState:
    """Per-agent routing state for reevaluation scheduling."""

    current_exit: str | None = None
    current_path: list[str] = field(default_factory=list)
    last_eval_time_s: float = -math.inf
    eval_offset_s: float = 0.0  # staggering offset
    wander_step: int = 0  # position in the knowledge-exhausted patrol rotation
    # The exit left by the last exit switch, if both its routes were refused,
    # and when; any other exit switch clears it (#458 return lockout).
    refused_switch_from: str | None = None
    refused_switch_time_s: float = -math.inf
    # The exit of the default route the agent follows while it knows no exit
    # (no_known_exit "default_route", #610). current_exit holds only exits
    # the agent knows, so its first known exit is an initial choice, not a
    # switch away from this one.
    default_exit: str | None = None
    # Whether the agent stands because it has nowhere known to go (#610).
    standing: bool = False
    # The agent's known nodes at its last evaluation, to tell a switch to an
    # exit learned since then (``learned_exit``). Labels only; None without a
    # cognitive map or before the first evaluation.
    known_at_last_eval: frozenset[str] | None = None

    @property
    def counted_exit(self) -> str | None:
        """The exit this agent is counted at in ``exit_counts``.

        A default-route agent walks to its default exit and queues there, so
        it is counted at it, as FDS+Evac counts an agent following its flow
        field at the door the field leads to.
        """
        return self.current_exit or self.default_exit


@dataclass(frozen=True)
class RouteSwitch:
    """Record of a route switch for diagnostics.

    ``reason`` is one of :data:`SWITCH_REASONS`. A change of exit is labelled
    by the decision branch that let it through, first match wins:
    ``fallback`` (every route refused), ``initial`` (no exit before),
    ``exit_closed`` (the old exit closed on its schedule), ``fed_reroute``
    (the old route is over the dose limit, or under ``additive`` the dose term
    contributes to a switch that needs the hazard terms), ``smoke_reroute``
    (the old route is refused on smoke alone; under ``gate`` the new route is
    clean where the old is not, clearly lower in tau, or quicker only with
    smoke slowdown; under ``additive`` the switch needs the smoke term and not
    the dose term), ``exit_opened`` (the new exit was closed at the previous
    evaluation), ``learned_exit`` (the new exit was not in the agent's
    cognitive map at the previous evaluation, or at spawn before the first),
    ``congestion`` (the switch needs the queue term),
    ``shorter_path`` (time or length alone clears the anchor). An old exit
    with no route from where the agent stands gives ``exit_unreachable``,
    and an idle agent routed to the exit it already holds ``resume``, unless
    the new exit was opened or learned since the previous evaluation.
    """

    time_s: float
    agent_id: int
    old_exit: str | None
    new_exit: str
    old_cost: float | None
    new_cost: float
    reason: str


#: Every value of :attr:`RouteSwitch.reason`; not in order of precedence.
SWITCH_REASONS = (
    "initial",
    "default_route",
    "fed_reroute",
    "smoke_reroute",
    "exit_closed",
    "exit_opened",
    "learned_exit",
    "congestion",
    "shorter_path",
    "exit_unreachable",
    "resume",
    "fallback",
    "better_path",
    "explore",
    "wander",
    "return",
    "stay",
)


def compute_eval_offset(
    agent_id: int,
    interval_s: float,
    dt_s: float = 0.01,
) -> float:
    """Stagger reevaluation across agents to spread cost.

    *agent_id* is any per-agent integer. ``run_scenario`` passes the
    agent's stagger index, its spawn index within its origin plus one
    (``agent_seed.stagger_index``), not its JuPedSim id.
    """
    if interval_s <= 0 or dt_s <= 0:
        return 0.0
    steps_per_interval = max(1, int(interval_s / dt_s))
    return (agent_id % steps_per_interval) * dt_s


def should_reevaluate(
    current_time_s: float,
    state: AgentRouteState,
    interval_s: float,
) -> bool:
    """Return whether this agent should reevaluate its route now.

    Agent evaluates at times: offset, offset + interval, offset + 2*interval, ...
    """
    if interval_s <= 0:
        return False
    if state.last_eval_time_s < state.eval_offset_s:
        # Never evaluated yet; evaluate once we reach our offset.
        return current_time_s >= state.eval_offset_s
    return current_time_s - state.last_eval_time_s >= interval_s


def reroute_agent(
    wait_info: dict,
    new_path: list[str],
    stage_configs: dict,
) -> bool:
    """Update an agent's wait_info to follow a new route.

    Modifies path_choices so that each stage in the new path leads
    deterministically to the next stage.  Retargets the agent to the
    first remaining stage in the new path that it hasn't passed yet.
    A route is priced as a walk from the node the agent last left to the
    node after it, so when the current target lies further along the new
    path than that node, the agent is retargeted to that node.

    Returns True if the route was actually changed.
    """
    if not new_path or len(new_path) < 2:
        return False

    current_stage = wait_info.get("current_target_stage")
    current_origin = wait_info.get("current_origin")

    # Find where the agent is in the new path.
    # Try current_target_stage first, then current_origin.
    insert_idx = None
    for ref_stage in (current_stage, current_origin):
        if ref_stage and ref_stage in new_path:
            insert_idx = new_path.index(ref_stage)
            break

    if insert_idx is None:
        # Agent is not on the new path yet; retarget from first stage.
        insert_idx = 0

    # The new path was priced from current_origin to the node after it. If
    # the current target is further along, anchoring there would keep the
    # agent on the leg the new path replaced, so anchor at the origin and
    # retarget to the node after it. An idle or waiting agent already stands
    # on its target, so its route goes on from there.
    skips_ahead = False
    if (
        wait_info.get("state") not in ("idle", "waiting")
        and current_origin in new_path
        and current_stage in new_path
        and new_path.index(current_stage) > new_path.index(current_origin) + 1
    ):
        insert_idx = new_path.index(current_origin)
        skips_ahead = True

    # Build deterministic path_choices: each stage → next stage at 100%.
    remaining = new_path[insert_idx:]
    new_choices: dict[str, list[tuple[str, float]]] = {}
    for i in range(len(remaining) - 1):
        new_choices[remaining[i]] = [(remaining[i + 1], 100.0)]

    # Merge new choices into existing path_choices (don't remove
    # choices for stages not on this path).
    old_choices = wait_info.get("path_choices", {})
    old_choices.update(new_choices)
    # The path's terminal is where the agent must stop and re-decide (a
    # frontier hop) or be retired (an exit). A stale leg left there from an
    # earlier route makes advance_path_target walk on instead of going idle,
    # so the agent never re-enters the decision path.
    if remaining[-1] not in new_choices:
        old_choices.pop(remaining[-1], None)
    wait_info["path_choices"] = old_choices

    # If the agent's current target is not on the remaining path, retarget to
    # the next stage after the agent's current position. remaining[0] is the
    # agent's current position; remaining[1] is the next stage it should move
    # toward.
    #
    # An idle agent is retargeted too. It is standing on a stage with no onward
    # plan -- the end of a frontier hop -- so remaining[0] is where it already
    # is and remaining[1] is where it must go next. Without this it would be
    # given path_choices it never consults, and would stand there for the rest
    # of the run.
    idle = wait_info.get("state") == "idle"
    if (current_stage not in remaining or idle or skips_ahead) and len(remaining) >= 2:
        next_stage = remaining[1]
        if next_stage in stage_configs:
            from .direct_steering_runtime import pick_stage_target

            wait_info["current_origin"] = remaining[0]
            wait_info["current_target_stage"] = next_stage
            wait_info["target"] = pick_stage_target(
                wait_info, stage_configs[next_stage]
            )
            wait_info["target_assigned"] = False
            wait_info["state"] = "to_target"
            wait_info["wait_until"] = None

    return True


# Same-exit reroute only fires when the newly ranked path is at least this
# much cheaper than the agent's currently-committed path, so agents don't
# thrash onto a "better" path that's only cheaper by floating-point noise.
# Kept at 0.9 to match RerouteConfig.exit_switch_anchor and FDS+Evac's
# FAC_DOOR_WAIT patience factor (convention, not calibrated).
_PATH_IMPROVEMENT_THRESHOLD = 0.9


def _reconstruct_committed_path(wait_info: dict) -> list[str]:
    """Return the path the agent is *currently* walking, per its own wait_info.

    Walks forward through the deterministic portion of ``path_choices``
    starting at the agent's current position, stopping at a terminal stage
    (no further choices) or the first probabilistic branch (more than one
    choice), where the continuation can't be determined in advance.
    """
    origin = wait_info.get("current_origin")
    target = wait_info.get("current_target_stage")
    if origin is None or target is None:
        return []
    path = [origin, target]
    seen = {origin, target}
    choices = wait_info.get("path_choices", {})
    current = target
    while True:
        options = choices.get(current)
        if not options or len(options) != 1:
            break
        next_stage = options[0][0]
        if next_stage in seen:
            break
        path.append(next_stage)
        seen.add(next_stage)
        current = next_stage
    return path


def _anchor_allows(
    candidate: RouteCost,
    old_rc: RouteCost | None,
    config: RerouteConfig,
) -> bool:
    """Whether the exit-switch anchor lets the agent leave *old_rc* for *candidate*.

    The single statement of that rule. It was once written twice -- here, to
    skip past a promoted route the anchor would refuse, and inline at the
    decision -- and the two drifted, so the copy waved through switches the
    anchor then vetoed.

    Anchoring is bypassed when the old exit is a hazard the agent must flee,
    and when the candidate is clean where the old one is not. Otherwise the
    comparison is a deadband on optical depth, falling through to time only
    when the two routes are within it.
    """
    return policy_for(config.cost_config).anchor_allows(candidate, old_rc, config)


def _clears_exit_anchor(
    candidate: RouteCost, old_rc: RouteCost, config: RerouteConfig
) -> bool:
    """Whether *candidate* beats *old_rc* by the exit_switch_anchor ratio."""
    return candidate.rank_cost < old_rc.rank_cost * config.exit_switch_anchor


def _select_candidate(
    ranked: list[RouteCost],
    route_state: AgentRouteState,
    config: RerouteConfig,
    time_s: float | None = None,
) -> RouteCost:
    """The route the agent would move to: rank 1, or the first it can adopt.

    A route the ordering promoted but the agent cannot adopt must not hide
    the rest of the list. Tier 1 can put a clean exit first that the anchor
    then refuses on time; before this, the agent returned None and never saw
    the rival at rank 2 it would have switched to -- so adding the tier could
    suppress a switch the model made without it, which is strictly worse than
    having no tier at all. Candidates are tried in rank order and the first
    adoptable one wins; if none is, nothing changes, as before.

    Gate only. The scan stops at the agent's own exit and does not skip
    refused routes. With *time_s*, the return lockout applies too.
    """
    best = ranked[0]
    current_exit_now = route_state.current_exit
    if (
        current_exit_now is not None
        and policy_for(config.cost_config).scan_before_current_exit()
        and best.exit_id != current_exit_now
    ):
        for candidate in ranked:
            if candidate.exit_id == current_exit_now:
                break  # the agent's own exit outranks the rest: stay
            if _adoptable(candidate, ranked, route_state, config, time_s):
                best = candidate
                break
    return best


def _adoptable(
    candidate: RouteCost,
    ranked: list[RouteCost],
    route_state: AgentRouteState,
    config: RerouteConfig,
    time_s: float | None = None,
) -> bool:
    """Whether the agent could switch to *candidate* if the ordering offered it.

    With *time_s*, a return the lockout blocks is not adoptable.
    """
    old_exit = route_state.current_exit
    if old_exit is None or candidate.exit_id == old_exit:
        return True
    old_rc = next((rc for rc in ranked if rc.exit_id == old_exit), None)
    if not _anchor_allows(candidate, old_rc, config):
        return False
    return not _return_locked(candidate, old_rc, route_state, time_s, config)


def _both_refused(candidate: RouteCost, old_rc: RouteCost | None) -> bool:
    """Whether a move from *old_rc* to *candidate* is between two refused routes."""
    return old_rc is not None and not candidate.feasible and not old_rc.feasible


def _return_locked(
    candidate: RouteCost,
    old_rc: RouteCost | None,
    route_state: AgentRouteState | None,
    time_s: float | None,
    config: RerouteConfig,
) -> bool:
    """Whether the return lockout blocks leaving *old_rc* for *candidate*.

    After an exit switch between two refused routes, a switch straight back to
    the exit just left, again between two refused routes, waits
    ``fallback_return_lockout_s`` (#458). A feasible route on either side, a
    hazard the agent must flee and a third exit are never blocked. Without a
    route state or a time nothing is blocked.
    """
    lockout = config.cost_config.fallback_return_lockout_s
    if route_state is None or time_s is None or lockout <= 0.0:
        return False
    if candidate.exit_id != route_state.refused_switch_from:
        return False
    if old_rc is None or not _both_refused(candidate, old_rc):
        return False
    if _must_flee_rejection(old_rc, config.cost_config):
        return False
    return time_s - route_state.refused_switch_time_s <= lockout


def _leaves_rejected_path(committed: RouteCost, best: RouteCost) -> bool:
    """Whether the walked path failed a limit and *best* passes them all.

    A rejected walked path is left for a feasible one whatever the time
    saving: the 10 % rule damps churn between acceptable paths, it must not
    hold an agent on one that failed a limit (#184).
    """
    return committed.rejected and best.feasible and not best.rejected


def _path_clearly_cheaper(best: RouteCost, committed: RouteCost) -> bool:
    """Whether *best* beats the walked path by _PATH_IMPROVEMENT_THRESHOLD."""
    return best.rank_cost < committed.rank_cost * _PATH_IMPROVEMENT_THRESHOLD


def _decide_same_exit(
    best: RouteCost,
    old_exit: str | None,
    wait_info: dict,
    graph: StageGraph,
    current_time_s: float,
    current_fed: float,
    extinction_sampler: ExtinctionSampler,
    fed_rate_sampler: FedRateSampler | None,
    config: RerouteConfig,
    cached_segments: dict[SegmentCacheKey, SegmentCost] | None,
    *,
    exit_counts: dict[str, int] | None,
    agent_position: tuple[float, float] | None,
    current_target: str | None,
) -> RouteDecision:
    """Whether to move a walking agent onto a better path to the same exit.

    Only reroute if the newly ranked path to it is meaningfully cheaper than
    the path the agent is actually walking right now (not just whatever was
    last recorded as "best"). That path is measured here, on the full graph,
    with the pass's shared cache and no current exit, and only when it can
    be reconstructed to this exit. Either way the path is recorded, even if
    applying the switch fails.
    """
    committed_path = _reconstruct_committed_path(wait_info)
    if (
        committed_path
        and committed_path[-1] == best.exit_id
        and all(n in graph.nodes for n in committed_path)
    ):
        committed = evaluate_route(
            graph,
            committed_path,
            current_time_s,
            current_fed,
            extinction_sampler,
            fed_rate_sampler,
            config.cost_config,
            cached_segments=cached_segments,
            exit_counts=exit_counts,
            agent_position=agent_position,
            current_target=current_target,
        )
        if _leaves_rejected_path(committed, best) or _path_clearly_cheaper(
            best, committed
        ):
            return RouteDecision(
                kind="switch",
                path=best.path,
                old_exit=old_exit,
                target_id=best.exit_id,
                old_cost=committed.rank_cost,
                new_cost=best.rank_cost,
                switch_reason="better_path",
                update_cached_path=True,
            )
    return RouteDecision(kind="keep", path=best.path, update_cached_path=True)


def _decide_exit_change(
    best: RouteCost,
    old_exit: str | None,
    old_rc: RouteCost | None,
    old_cost: float | None,
    config: RerouteConfig,
    *,
    route_state: AgentRouteState | None = None,
    time_s: float | None = None,
    news: str | None = None,
    current_fed: float = 0.0,
) -> RouteDecision:
    """Whether to move the agent to *best*'s exit, or give it its first one.

    Anchoring / hysteresis: don't abandon the current exit for a *different*
    one unless the new exit is meaningfully better. Without this, near-tied
    exits flip-flop on every reevaluation -- worst at short reroute
    intervals. Anchoring does not apply to the initial choice (old_exit is
    None) or when the old exit is no longer reachable and so was never
    priced. Everything else is _anchor_allows, which is also what chose
    `best`, and, given *route_state* and *time_s*, the return lockout.

    *news* is ``exit_opened`` or ``learned_exit`` when *best*'s exit became
    available to the agent since its previous evaluation; it only labels the
    switch (see :class:`RouteSwitch`), as does *current_fed*, the dose the
    agent has already taken.
    """
    if (
        old_exit is not None
        and old_cost is not None
        and (
            not _anchor_allows(best, old_rc, config)
            or _return_locked(best, old_rc, route_state, time_s, config)
        )
    ):
        return RouteDecision(kind="keep")

    fallback = (best.rejection_reason or "").startswith("fallback")
    if fallback:
        reason = "fallback"
    elif old_exit is None:
        reason = "initial"
    else:
        reason = _exit_change_reason(
            best, old_exit, old_rc, config, news, current_fed=current_fed
        )
    return RouteDecision(
        kind="fallback" if fallback else "switch",
        path=best.path,
        old_exit=old_exit,
        target_id=best.exit_id,
        old_cost=old_cost,
        new_cost=best.rank_cost,
        switch_reason=reason,
    )


def _exit_change_reason(
    best: RouteCost,
    old_exit: str,
    old_rc: RouteCost | None,
    config: RerouteConfig,
    news: str | None,
    *,
    current_fed: float = 0.0,
) -> str:
    """The cause of an allowed change from *old_exit* to *best*.

    Reads only the two priced routes, so it cannot change the decision.
    *current_fed* is the dose already taken, which both routes carry.
    """
    if old_rc is None:
        fallback = "resume" if best.exit_id == old_exit else "exit_unreachable"
        return news or fallback
    if old_rc.rejected:
        return "fed_reroute" if _over_dose(old_rc) else "smoke_reroute"
    hazard = _hazard_reason(best, old_rc, config, current_fed)
    if hazard is not None:
        return hazard
    if news is not None:
        return news
    if not _clears_without(best, old_rc, config, _queue_term):
        return "congestion"
    return "shorter_path"


def _over_dose(rc: RouteCost) -> bool:
    """Whether the route to the agent's own exit breaks the dose limit.

    Read from the limits the route breaks, not the rejection message: under
    ``gate`` a route over both limits reports tau, and the dose still names
    the cause. The kinds were recorded against the limit of the agent's own
    exit, so the label and must-flee agree (#128).
    """
    return "fed" in rc.violation_kinds


def _hazard_reason(
    best: RouteCost,
    old_rc: RouteCost,
    config: RerouteConfig,
    current_fed: float = 0.0,
) -> str | None:
    """``fed_reroute`` or ``smoke_reroute`` if dose or smoke let *best* win.

    Under ``additive`` the dose term is credited on the dose each route adds,
    not on the dose already taken: that part is the same on both routes and
    would decide nothing, yet under the ratio anchor removing it changes the
    comparison.
    """
    cost_config = config.cost_config
    if cost_config.cost_model == "gate":
        cleaner = GatePolicy._clean_bypass(best, old_rc) or (
            GatePolicy._tau_band(best, old_rc, cost_config) > 0
        )
        return (
            "smoke_reroute"
            if cleaner or _slowed_by_smoke(best, old_rc, config)
            else None
        )
    fed_term = _fed_growth_term(current_fed)

    def hazard_terms(rc: RouteCost, cfg: RouteCostConfig) -> float:
        return fed_term(rc, cfg) + _smoke_term(rc, cfg)

    if _clears_without(best, old_rc, config, hazard_terms):
        return None
    if _clears_without(best, old_rc, config, _smoke_term) or not _clears_without(
        best, old_rc, config, fed_term
    ):
        return "fed_reroute"
    return "smoke_reroute"


def _slowed_by_smoke(best: RouteCost, old_rc: RouteCost, config: RerouteConfig) -> bool:
    """Whether the switch fails the anchor with clear-air travel times (gate).

    Gate ranks on travel time, which smoke slows; a switch that clears only
    because of that slowdown is a smoke effect. The queue term is kept.
    """
    if best.clear_travel_time_s is None or old_rc.clear_travel_time_s is None:
        return False
    queue = config.cost_config.w_queue
    new_cost = best.clear_travel_time_s + queue * best.queue_time_s
    old_cost = old_rc.clear_travel_time_s + queue * old_rc.queue_time_s
    return not new_cost < old_cost * config.exit_switch_anchor


def _fed_growth_term(
    current_fed: float,
) -> Callable[[RouteCost, RouteCostConfig], float]:
    """The dose term of the additive composite for the dose the route adds."""

    def term(rc: RouteCost, config: RouteCostConfig) -> float:
        return config.w_fed * (rc.fed_max_route - current_fed)

    return term


def _smoke_term(rc: RouteCost, config: RouteCostConfig) -> float:
    """The smoke term of the additive composite, w_smoke * K_ave * L."""
    return config.w_smoke * rc.tau_route


def _queue_term(rc: RouteCost, config: RouteCostConfig) -> float:
    """The queue term of ``rank_cost`` under either cost model."""
    if config.cost_model == "gate":
        return config.w_queue * rc.queue_time_s
    return config.w_queue * config.base_speed_m_per_s * rc.queue_time_s


def _clears_without(
    best: RouteCost,
    old_rc: RouteCost,
    config: RerouteConfig,
    term: Callable[[RouteCost, RouteCostConfig], float],
) -> bool:
    """Whether *best* would clear the anchor with *term* taken out of both costs."""
    cost_config = config.cost_config
    new_cost = best.rank_cost - term(best, cost_config)
    old_cost = old_rc.rank_cost - term(old_rc, cost_config)
    return new_cost < old_cost * config.exit_switch_anchor


def _exit_news(
    exit_id: str,
    graph: StageGraph,
    route_state: AgentRouteState,
    cognitive_map,
) -> str | None:
    """Whether *exit_id* became available since the agent's last evaluation.

    ``exit_opened`` if the exit was closed then, ``learned_exit`` if it was not
    in the agent's cognitive map then (or, before the first evaluation, in the
    map it was given at spawn), else None. Labels only.
    """
    last = route_state.last_eval_time_s
    node = graph.nodes.get(exit_id)
    if math.isfinite(last) and node is not None and not node.is_open(last):
        return "exit_opened"
    known = route_state.known_at_last_eval
    if cognitive_map is not None and known is not None and exit_id not in known:
        return "learned_exit"
    return None


def _remember_known(route_state: AgentRouteState, cognitive_map) -> None:
    """Keep the agent's known nodes as of this evaluation, for ``learned_exit``.

    A cognitive map only grows, so an unchanged size is an unchanged map.
    """
    if cognitive_map is None:
        return
    known = route_state.known_at_last_eval
    if known is None or len(known) != len(cognitive_map.known_nodes):
        route_state.known_at_last_eval = frozenset(cognitive_map.known_nodes)


def _decide_explore(
    wait_info: dict,
    route_state: AgentRouteState,
    graph: StageGraph,
    source: str,
    cognitive_map,
    agent_position: tuple[float, float] | None,
) -> RouteDecision:
    """Where an agent with no known exit goes: a frontier node, or a patrol.

    Called when no exit is reachable in the agent's known subgraph (typically
    a discovery agent that hasn't found the way out yet). Rather than standing
    still, it heads toward the nearest known-but-unexplored node so the
    cognitive map keeps growing until an exit is found.

    The one state change made here is the patrol step, which advances before
    the next stop is looked up and stays advanced whatever the lookup does.
    Before a patrol leg the agent first looks from the node point (#250):
    that decision leaves the patrol step as it is.
    """
    from .cognitive_map import nearest_frontier_target, wander_target

    idle = wait_info.get("state") == "idle"
    reason = "explore"
    frontier = nearest_frontier_target(cognitive_map, graph, source, agent_position)
    if frontier is None:
        if looking(wait_info):
            # Walking to the node point to look from there: no patrol leg
            # pre-empts the look.
            return RouteDecision(kind="keep")
        # Knowledge exhausted: every known node is visited and none of it
        # leads to an exit. Patrol the known nodes instead of standing --
        # perception runs from the agent's position, so a walked leg can
        # make a sign readable that never was from any node it stood on.
        step = route_state.wander_step
        if idle and route_state.current_path:
            # The previous patrol leg was completed; move on to the next
            # stop, or a single-candidate rotation would re-offer the node
            # the agent is standing on the way to.
            route_state.wander_step += 1
        frontier = wander_target(cognitive_map, graph, source, route_state.wander_step)
        if frontier is not None and idle:
            point = _look_point(wait_info, graph, source, agent_position)
            if point is not None:
                # The patrol leg waits for the look; so does its step.
                route_state.wander_step = step
                return RouteDecision(kind="look", target_id=source, point=point)
        reason = "wander"
    if frontier is None:
        return RouteDecision(kind="keep")
    target_node, path = frontier
    # Already committed to this target: the agent's current target is an
    # intermediate hop of the committed path, not the destination itself,
    # so comparing against current_target_stage alone re-fires the same
    # switch on every reevaluation until arrival. An idle agent is never
    # suppressed -- it is standing with no onward plan and must be routed.
    committed = route_state.current_path
    if not idle and (
        wait_info.get("current_target_stage") == target_node
        or (
            committed
            and committed[-1] == target_node
            and wait_info.get("current_target_stage") in committed
        )
    ):
        return RouteDecision(kind="keep")
    # old_exit is left None on purpose: exploring toward a frontier node
    # does not abandon any exit commitment, so this switch must not drive
    # the caller's exit_counts bookkeeping (new_exit is a checkpoint, not
    # an exit). route_state.current_exit is deliberately unchanged.
    return RouteDecision(
        kind=reason,
        path=path,
        old_exit=None,
        target_id=target_node,
        old_cost=None,
        new_cost=0.0,
        switch_reason=reason,
    )


def looking(wait_info: dict) -> bool:
    """Whether the agent walks to a node point to look from there (#250)."""
    point = wait_info.get("look_point")
    return (
        point is not None
        and wait_info.get("state") == "to_target"
        and wait_info.get("target") == point
    )


def look_radius(wait_info: dict) -> float:
    """The agent's body radius: a look ends with the node point under it."""
    return float(wait_info.get("body_radius", 0.2))


def _look_point(
    wait_info: dict,
    graph: StageGraph,
    source: str,
    agent_position: tuple[float, float] | None,
) -> tuple[float, float] | None:
    """The node point an agent about to patrol walks to first, or None.

    An agent that completed its visit to *source* short of the node point,
    where routing measures from and the node's sign hangs, may not have
    seen what is visible from there (#250). Before patrolling, it walks
    until the point lies under its body and looks again. None when it is
    there already, has looked on this visit, *source* has no stage to steer
    to, or the agent does not fit on the point.
    """
    if agent_position is None or wait_info.get("looked_node") == source:
        return None
    node = graph.nodes.get(source)
    stage = wait_info.get("stage_configs", {}).get(source)
    if node is None or stage is None or stage.get("polygon") is None:
        return None
    point = (node.centroid_x, node.centroid_y)
    radius = look_radius(wait_info)
    gap = math.hypot(agent_position[0] - point[0], agent_position[1] - point[1])
    if gap <= radius or not _node_point_fits(graph, source, point, radius):
        return None
    return point


def _node_point_fits(
    graph: StageGraph, node_id: str, point: tuple[float, float], radius: float
) -> bool:
    """Whether an agent of *radius* fits on *node_id*'s node point.

    Without a walkable area there is no way to tell, and no look. A point
    the agent does not fit on is not replaced by another: the look point
    must be the point routing measures from.
    """
    key = (node_id, radius)
    fits = graph.node_point_fits.get(key)
    if fits is not None:
        return fits
    walkable = graph.walkable_polygon
    if walkable is None:
        return False
    from shapely.geometry import Point

    fits = bool(walkable.buffer(-radius).covers(Point(point)))
    if not fits:
        _logger.warning(
            "Node point (%.2f, %.2f) of stage %s leaves no room for an agent "
            "of radius %.2f m: agents patrol from there without looking from it.",
            point[0],
            point[1],
            node_id,
            radius,
        )
    graph.node_point_fits[key] = fits
    return fits


def _start_look(wait_info: dict, node_id: str, point: tuple[float, float]) -> None:
    """Send the agent to *node_id*'s node point, once per visit."""
    wait_info["looked_node"] = node_id
    wait_info["look_point"] = point
    wait_info["current_origin"] = node_id
    wait_info["current_target_stage"] = node_id
    wait_info["target"] = point
    wait_info["target_assigned"] = False
    wait_info["state"] = "to_target"
    wait_info["wait_until"] = None
    wait_info.pop("look_deadline", None)


def end_look(wait_info: dict) -> None:
    """End a look: the agent stands at its node with no onward plan."""
    wait_info.pop("look_point", None)
    wait_info.pop("look_deadline", None)
    wait_info["state"] = "idle"


def _apply_decision(
    decision: RouteDecision,
    agent_id: int,
    wait_info: dict,
    route_state: AgentRouteState,
    current_time_s: float,
) -> RouteSwitch | None:
    """Carry out *decision* on the agent and report the switch it made.

    A same-exit decision (``update_cached_path``) records its path whether or
    not the switch applies and leaves the exit alone. An exit change records
    exit and path only once the agent has been rerouted. An explore or wander
    decision records the path only once the agent has been rerouted, and
    never touches the exit.
    """
    if decision.kind == "keep":
        if decision.update_cached_path:
            route_state.current_path = decision.path
        return None
    if decision.kind == "look":
        # Not a route decision: no switch is recorded, and the patrol state
        # is left for the decision after the look.
        if decision.target_id is not None and decision.point is not None:
            _start_look(wait_info, decision.target_id, decision.point)
        return None
    if looking(wait_info):
        # A decision during the look replaces it, as it would have replaced
        # the patrol of an agent standing at the node.
        end_look(wait_info)
    if decision.kind == "stay":
        _stand(wait_info, route_state, decision.target_id)
        return _switch_record(decision, agent_id, current_time_s)
    if decision.kind == "default_route" and not decision.path:
        # The scripted plan already leads to the default exit; only the
        # bookkeeping changes.
        _follow_default_route(route_state, decision, [])
        return _switch_record(decision, agent_id, current_time_s)
    stage_configs = wait_info.get("stage_configs", {})
    changed = reroute_agent(wait_info, decision.path, stage_configs)
    if not changed:
        if decision.update_cached_path:
            route_state.current_path = decision.path
        return None
    if route_state.standing:
        route_state.standing = False
    if decision.kind == "default_route":
        _follow_default_route(route_state, decision, decision.path or [])
        return _switch_record(decision, agent_id, current_time_s)
    if decision.kind in ("switch", "fallback") and not decision.update_cached_path:
        route_state.current_exit = decision.target_id
        if route_state.default_exit is not None:
            route_state.default_exit = None
    route_state.current_path = decision.path
    return _switch_record(decision, agent_id, current_time_s)


def _switch_record(
    decision: RouteDecision, agent_id: int, current_time_s: float
) -> RouteSwitch:
    return RouteSwitch(
        time_s=current_time_s,
        agent_id=agent_id,
        old_exit=decision.old_exit,
        new_exit=decision.target_id,
        old_cost=decision.old_cost,
        new_cost=decision.new_cost,
        reason=decision.switch_reason,
    )


def _follow_default_route(
    route_state: AgentRouteState, decision: RouteDecision, path: list[str]
) -> None:
    """Record that the agent now walks the default route to its exit."""
    route_state.current_exit = None
    route_state.default_exit = decision.target_id
    route_state.standing = False
    route_state.current_path = list(path)


def _stand(wait_info: dict, route_state: AgentRouteState, node: str | None) -> None:
    """Stop the agent where it is, with no onward plan, at *node*.

    Idle keeps it in the reroute pass, so it moves on once a decision gives
    it somewhere to go. Its target becomes the point it stands on, which
    the runtime assigns: an idle agent is otherwise left walking to the
    target it had.
    """
    wait_info["state"] = "idle"
    if node is not None:
        wait_info["current_origin"] = node
        wait_info["current_target_stage"] = node
    # Without a recorded position the runtime stands it where it is next.
    position = wait_info.get("current_position")
    wait_info["target"] = tuple(position) if position is not None else None
    wait_info["target_assigned"] = False
    wait_info["wait_until"] = None
    route_state.standing = True
    route_state.current_path = []


def terminal_exit(wait_info: dict, graph_nodes: dict) -> str | None:
    """The exit the agent's scripted plan ends at, or None.

    Follows the first choice of each stage's ``path_choices`` from the
    current target.
    """
    if wait_info.get("mode") != "path":
        return None
    path_choices = wait_info.get("path_choices", {})
    stage = wait_info.get("current_target_stage")
    visited = set()
    while stage and stage in path_choices and stage not in visited:
        visited.add(stage)
        choices = path_choices[stage]
        if choices:
            stage = (
                choices[0][0] if isinstance(choices[0], (list, tuple)) else choices[0]
            )
        else:
            break
    if stage and stage in graph_nodes:
        node = graph_nodes[stage]
        if node.stage_type == "exit":
            return stage
    fallback = wait_info.get("current_target_stage")
    if (
        fallback
        and fallback in graph_nodes
        and graph_nodes[fallback].stage_type == "exit"
    ):
        return fallback
    return None


def _walking_first_hops(
    graph: StageGraph, source: str, agent_position: tuple[float, float]
) -> dict[str, float]:
    """The walking distance from the agent to each successor of *source*."""
    hops: dict[str, float] = {}
    for edge in graph.edges.get(source, []):
        node = graph.nodes[edge.target]
        hops[edge.target] = _walkable_distance(
            graph.routing_engine, agent_position, (node.centroid_x, node.centroid_y)
        )
    return hops


def nearest_exit_by_walking(
    graph: StageGraph,
    source: str,
    agent_position: tuple[float, float] | None,
) -> tuple[str, list[str]] | None:
    """The exit of *graph* nearest by walking distance, and the path to it.

    Path lengths are the edge weights, which follow the walkable area. With
    *agent_position* the search starts where the agent stands, as route
    ranking's does: the first leg is the walk to each of *source*'s
    successors, so a path that is longer from *source* but shorter from the
    agent is not pruned. Ties go to the exit whose id sorts first. Pass a
    graph without closed stages.
    """
    from .cognitive_map import _cost_from_agent

    first_hops = None
    if agent_position is not None and _search_from_position(graph, source):
        first_hops = _walking_first_hops(graph, source, agent_position)
    paths = graph.shortest_paths_to_exits(source, first_hops=first_hops)
    best: tuple[str, float, list[str]] | None = None
    for exit_id, (cost, path) in sorted(paths.items()):
        if len(path) < 2:
            continue
        if first_hops is None:
            cost = _cost_from_agent(graph, path, cost, agent_position)
        if best is None or cost < best[1]:
            best = (exit_id, cost, path)
    if best is None:
        return None
    return best[0], best[2]


def _decide_no_known_exit(
    wait_info: dict,
    route_state: AgentRouteState,
    graph: StageGraph,
    source: str,
    cognitive_map,
    agent_position: tuple[float, float] | None,
) -> RouteDecision:
    """What an agent with no reachable known exit does, by its mode (#610).

    *graph* is the stage graph without closed stages.
    """
    from .cognitive_map import no_known_exit_mode

    mode = no_known_exit_mode(wait_info.get("no_known_exit"))
    if mode == "default_route":
        return _decide_default_route(
            wait_info, route_state, graph, source, agent_position
        )
    if mode == "stay":
        return _decide_stay(route_state, source)
    if mode == "return":
        decision = _decide_return(wait_info, route_state, graph, source, cognitive_map)
        if decision is not None:
            return decision
    decision = _decide_explore(
        wait_info, route_state, graph, source, cognitive_map, agent_position
    )
    if decision.kind != "keep":
        return decision
    # Nothing to explore: an agent must not walk on toward a node it does
    # not know (C4), such as the first stage of a journey or the exit
    # nearest its spawn point.
    if wait_info.get("current_target_stage") in cognitive_map.known_nodes:
        return decision
    return _decide_stay(route_state, source)


def _decide_stay(route_state: AgentRouteState, source: str) -> RouteDecision:
    """Stand where the agent is, once; later evaluations keep it standing."""
    if route_state.standing:
        return RouteDecision(kind="keep")
    return RouteDecision(
        kind="stay", target_id=source, new_cost=0.0, switch_reason="stay"
    )


def _decide_default_route(
    wait_info: dict,
    route_state: AgentRouteState,
    graph: StageGraph,
    source: str,
    agent_position: tuple[float, float] | None,
) -> RouteDecision:
    """Follow the default route: the scripted plan, else the nearest exit.

    The scripted plan is the distribution's journey, or for a distribution
    without one the exit nearest the spawn point by walking distance. It is
    kept while it leads to an open exit. An idle agent, or one whose plan
    ends at a closed exit or nowhere, is sent to the nearest open exit by
    walking distance. This is the FDS+Evac counterpart: an agent with no
    known door follows the modeller's flow field. The exit is not in the
    agent's map; leaving through it is flagged in the exit history.
    """
    idle = wait_info.get("state") == "idle"
    exit_id = None if idle else terminal_exit(wait_info, graph.nodes)
    path: list[str] = []
    if exit_id is None:
        found = nearest_exit_by_walking(graph, source, agent_position)
        if found is None:
            return RouteDecision(kind="keep")
        exit_id, path = found
    elif route_state.default_exit == exit_id and route_state.current_exit is None:
        return RouteDecision(kind="keep")
    return RouteDecision(
        kind="default_route",
        path=path,
        old_exit=route_state.current_exit,
        target_id=exit_id,
        new_cost=0.0,
        switch_reason="default_route",
    )


def _decide_return(
    wait_info: dict,
    route_state: AgentRouteState,
    graph: StageGraph,
    source: str,
    cognitive_map,
) -> RouteDecision | None:
    """Walk back over known legs to the nearest node with a known exit.

    A known exit can be out of reach from where the agent stands and in
    reach from a node it passed: routes are directed and a one-way leg
    leads only forward. The agent retraces known legs in either direction
    to the nearest such node; None when there is none.
    """
    from .cognitive_map import _undirected_known_path, cognitive_subgraph

    sub = cognitive_subgraph(cognitive_map, graph)
    best: tuple[float, str, list[str]] | None = None
    for node_id in sorted(cognitive_map.known_nodes):
        if node_id == source or node_id not in graph.nodes:
            continue
        if not sub.shortest_paths_to_exits(node_id):
            continue
        path = _undirected_known_path(cognitive_map, graph, source, node_id)
        if path is None:
            continue
        length = sum(
            math.hypot(
                graph.nodes[a].centroid_x - graph.nodes[b].centroid_x,
                graph.nodes[a].centroid_y - graph.nodes[b].centroid_y,
            )
            for a, b in zip(path, path[1:])
        )
        if best is None or length < best[0]:
            best = (length, node_id, path)
    if best is None:
        return None
    _length, node_id, path = best
    committed = route_state.current_path
    if (
        wait_info.get("state") != "idle"
        and committed
        and committed[-1] == node_id
        and wait_info.get("current_target_stage") in committed
    ):
        return RouteDecision(kind="keep")
    return RouteDecision(
        kind="return",
        path=path,
        target_id=node_id,
        new_cost=0.0,
        switch_reason="return",
    )


def evaluate_and_reroute(
    agent_id: int,
    wait_info: dict,
    route_state: AgentRouteState,
    graph: StageGraph,
    current_time_s: float,
    current_fed: float,
    extinction_sampler: ExtinctionSampler,
    fed_rate_sampler: FedRateSampler | None,
    config: RerouteConfig,
    cached_segments: dict[SegmentCacheKey, SegmentCost] | None = None,
    *,
    exit_counts: dict[str, int] | None = None,
    cognitive_map=None,
    agent_position: tuple[float, float] | None = None,
) -> RouteSwitch | None:
    """Evaluate routes and reroute the agent if a better exit is found.

    Returns a RouteSwitch record if the agent switched, else None.
    """
    # Determine the source node for ranking.  Prefer current_origin
    # (where the agent is coming from) because current_target_stage may
    # be an exit with no outgoing edges.
    source = wait_info.get("current_origin") or wait_info.get("current_target_stage")
    if source is None or source not in graph.nodes:
        return None

    # The node the agent is currently walking toward, so position-aware costs can
    # credit progress along that leg and penalize routes that diverge from it.
    current_target = wait_info.get("current_target_stage")

    ranked = rank_routes(
        graph,
        source,
        current_time_s,
        current_fed,
        extinction_sampler,
        fed_rate_sampler,
        config.cost_config,
        cached_segments=cached_segments,
        exit_counts=exit_counts,
        cognitive_map=cognitive_map,
        agent_position=agent_position,
        current_exit=route_state.current_exit,
        current_target=current_target,
        current_path=_reconstruct_committed_path(wait_info),
    )
    if not ranked:
        # No exit reachable in the agent's known subgraph (typically a
        # discovery agent that hasn't found the way out yet). Its
        # distribution's no_known_exit mode decides what it does (#610).
        route_state.last_eval_time_s = current_time_s
        _remember_known(route_state, cognitive_map)
        if cognitive_map is None:
            return None
        decision = _decide_no_known_exit(
            wait_info,
            route_state,
            without_closed_stages(graph, current_time_s),
            source,
            cognitive_map,
            agent_position,
        )
        return _apply_decision(
            decision, agent_id, wait_info, route_state, current_time_s
        )

    best = _select_candidate(ranked, route_state, config, current_time_s)

    if (
        best.rejected
        and best.rejection_reason
        and not best.rejection_reason.startswith("fallback")
    ):
        return None

    old_exit = route_state.current_exit
    old_rc = None
    old_cost = None
    if old_exit and old_exit != best.exit_id:
        # Find the old exit's route: its cost, its band and whether it is
        # clean all feed _anchor_allows, which also decides whether it is a
        # hazard the agent must flee.
        for rc in ranked:
            if rc.exit_id == old_exit:
                old_rc = rc
                old_cost = rc.rank_cost
                break

    news = _exit_news(best.exit_id, graph, route_state, cognitive_map)
    route_state.last_eval_time_s = current_time_s
    _remember_known(route_state, cognitive_map)

    # An idle agent stands on a node with no onward plan, so there is no
    # committed path to compare against and no churn to protect it from. It must
    # be routed even when the best exit is the one it was nominally assigned at
    # spawn -- an assignment made by straight-line distance before routing ran,
    # over an exit the agent had not yet discovered. Without this, an explorer
    # whose assigned exit happens to be the one it finds is never routed to it
    # and stands at the doorway for the rest of the run.
    if old_exit == best.exit_id and wait_info.get("state") != "idle":
        decision = _decide_same_exit(
            best,
            old_exit,
            wait_info,
            graph,
            current_time_s,
            current_fed,
            extinction_sampler,
            fed_rate_sampler,
            config,
            cached_segments,
            exit_counts=exit_counts,
            agent_position=agent_position,
            current_target=current_target,
        )
    else:
        decision = _decide_exit_change(
            best,
            old_exit,
            old_rc,
            old_cost,
            config,
            route_state=route_state,
            time_s=current_time_s,
            news=news,
            current_fed=current_fed,
        )
        if decision.kind == "switch" and stage_closed(graph, old_exit, current_time_s):
            decision = replace(decision, switch_reason="exit_closed")
    switch = _apply_decision(decision, agent_id, wait_info, route_state, current_time_s)
    if decision.kind in ("switch", "fallback") and switch is not None:
        _remember_exit_switch(route_state, switch, _both_refused(best, old_rc))
    return switch


def _remember_exit_switch(
    route_state: AgentRouteState, switch: RouteSwitch, refused: bool
) -> None:
    """Record the exit an applied switch left, for the return lockout."""
    if switch.old_exit is None or switch.old_exit == switch.new_exit:
        return
    route_state.refused_switch_from = switch.old_exit if refused else None
    route_state.refused_switch_time_s = switch.time_s if refused else -math.inf


def stage_closed(graph: StageGraph, stage_id: str | None, time_s: float) -> bool:
    """Whether *stage_id* is a stage of *graph* closed at *time_s*."""
    node = graph.nodes.get(stage_id) if stage_id is not None else None
    return node is not None and not node.is_open(time_s)
