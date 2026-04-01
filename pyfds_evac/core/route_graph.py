"""Stage graph for shortest-path routing and smoke-adjusted rerouting."""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass, field
from typing import Protocol

from shapely.geometry import Polygon

from .smoke_speed import speed_factor_from_extinction

_SECONDS_PER_MINUTE = 60.0


@dataclass(frozen=True)
class StageNode:
    """A node in the stage graph representing one stage."""

    stage_id: str
    centroid_x: float
    centroid_y: float
    stage_type: str  # "exit", "checkpoint", "distribution", "zone"
    capacity_agents_per_s: float | None = None


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
                cx, cy = polygon.centroid.x, polygon.centroid.y
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
            cx, cy = polygon.centroid.x, polygon.centroid.y
            stage_type = info.get("stage_type", "checkpoint")
            graph.nodes[stage_id] = StageNode(
                stage_id=stage_id,
                centroid_x=cx,
                centroid_y=cy,
                stage_type=stage_type,
                capacity_agents_per_s=info.get("capacity_agents_per_s"),
            )

        # Add edges from transitions.
        for tr in transitions:
            src = tr.get("from", "")
            tgt = tr.get("to", "")
            if src not in graph.nodes or tgt not in graph.nodes:
                continue
            src_node = graph.nodes[src]
            tgt_node = graph.nodes[tgt]
            if routing_engine is not None:
                waypoints = list(
                    routing_engine.compute_waypoints(
                        (src_node.centroid_x, src_node.centroid_y),
                        (tgt_node.centroid_x, tgt_node.centroid_y),
                    )
                )
                weight = _polyline_length(waypoints)
            else:
                waypoints = [
                    (src_node.centroid_x, src_node.centroid_y),
                    (tgt_node.centroid_x, tgt_node.centroid_y),
                ]
                weight = _polyline_length(waypoints)
            edge = StageEdge(source=src, target=tgt, weight=weight, waypoints=waypoints)
            graph.edges.setdefault(src, []).append(edge)

        # When no transitions are defined, auto-connect every distribution to
        # every exit so that smoke/FED-based rerouting works in minimal configs
        # (distributions + exits only, no checkpoints or explicit transitions).
        if not transitions:
            dist_ids = [
                nid for nid, n in graph.nodes.items() if n.stage_type == "distribution"
            ]
            exit_ids = [
                nid for nid, n in graph.nodes.items() if n.stage_type == "exit"
            ]
            for src_id in dist_ids:
                for tgt_id in exit_ids:
                    src_node = graph.nodes[src_id]
                    tgt_node = graph.nodes[tgt_id]
                    if routing_engine is not None:
                        waypoints = list(
                            routing_engine.compute_waypoints(
                                (src_node.centroid_x, src_node.centroid_y),
                                (tgt_node.centroid_x, tgt_node.centroid_y),
                            )
                        )
                        weight = _polyline_length(waypoints)
                    else:
                        waypoints = [
                            (src_node.centroid_x, src_node.centroid_y),
                            (tgt_node.centroid_x, tgt_node.centroid_y),
                        ]
                        weight = _polyline_length(waypoints)
                    edge = StageEdge(
                        source=src_id, target=tgt_id, weight=weight, waypoints=waypoints
                    )
                    graph.edges.setdefault(src_id, []).append(edge)

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
    ) -> dict[str, tuple[float, list[str]]]:
        """Dijkstra from *source* to every reachable exit.

        Returns a dict mapping exit_id -> (cost, path) where path is the
        list of stage IDs from source to exit inclusive.

        When *dynamic_weights* is provided, edge costs are looked up from
        the dict instead of using static Euclidean weights.
        """
        dist, prev = self._dijkstra(source, dynamic_weights=dynamic_weights)
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

    def _dijkstra(
        self,
        source: str,
        dynamic_weights: dict[tuple[str, str], float] | None = None,
    ) -> tuple[dict[str, float], dict[str, str | None]]:
        """Run Dijkstra from *source*.  Returns (dist, prev) dicts.

        When *dynamic_weights* is provided, edge cost is looked up from
        the dict instead of using the static edge weight.  Keys are
        ``(source_id, target_id)`` tuples.
        """
        if source not in self.nodes:
            return {}, {}
        dist: dict[str, float] = {sid: math.inf for sid in self.nodes}
        prev: dict[str, str | None] = {sid: None for sid in self.nodes}
        dist[source] = 0.0
        heap: list[tuple[float, str]] = [(0.0, source)]

        while heap:
            d, u = heapq.heappop(heap)
            if d > dist[u]:
                continue
            for edge in self.edges.get(u, []):
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

    n_samples = max(2, int(math.ceil(length / step_m)) + 1)
    total = 0.0
    for i in range(n_samples):
        t = i / (n_samples - 1)
        x = x_from + t * (x_to - x_from)
        y = y_from + t * (y_to - y_from)
        total += extinction_sampler.sample_extinction(time_s, x, y)
    return total / n_samples


def integrated_extinction_along_polyline(
    waypoints: list[tuple[float, float]],
    time_s: float,
    extinction_sampler: ExtinctionSampler,
    step_m: float = 2.0,
) -> float:
    """Return the Beer-Lambert path-integrated mean extinction along a polyline.

    Samples K at uniform intervals along each segment of the polyline and
    returns the overall arithmetic mean, weighted by segment length.
    """
    if step_m <= 0:
        raise ValueError(f"step_m must be positive, got {step_m}")
    if len(waypoints) < 2:
        if waypoints:
            return extinction_sampler.sample_extinction(
                time_s, waypoints[0][0], waypoints[0][1]
            )
        return 0.0

    total_k = 0.0
    total_samples = 0
    for i in range(len(waypoints) - 1):
        x0, y0 = waypoints[i]
        x1, y1 = waypoints[i + 1]
        seg_len = _euclidean(x0, y0, x1, y1)
        if seg_len < 1e-9:
            total_k += extinction_sampler.sample_extinction(time_s, x0, y0)
            total_samples += 1
            continue
        n_samples = max(2, int(math.ceil(seg_len / step_m)) + 1)
        for j in range(n_samples):
            t = j / (n_samples - 1)
            x = x0 + t * (x1 - x0)
            y = y0 + t * (y1 - y0)
            total_k += extinction_sampler.sample_extinction(time_s, x, y)
            total_samples += 1

    return total_k / total_samples if total_samples > 0 else 0.0


def _polyline_midpoint(
    waypoints: list[tuple[float, float]],
) -> tuple[float, float]:
    """Return the point at half the arc length along a polyline."""
    if not waypoints:
        return (0.0, 0.0)
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


@dataclass(frozen=True)
class RouteCostConfig:
    """Weights and thresholds for route cost evaluation."""

    w_smoke: float = 1.0
    w_fed: float = 10.0
    w_queue: float = 1.0
    fed_rejection_threshold: float = 1.0
    visibility_extinction_threshold: float = 0.5
    sampling_step_m: float = 2.0
    base_speed_m_per_s: float = 1.3
    alpha: float = 0.706
    beta: float = -0.057
    min_speed_factor: float = 0.1
    default_exit_capacity: float = 1.3


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


def _sample_segment_extinction(
    src_node: StageNode,
    tgt_node: StageNode,
    time_s: float,
    extinction_sampler: ExtinctionSampler,
    step_m: float,
    waypoints: list[tuple[float, float]] | None = None,
) -> tuple[float, float]:
    """Sample extinction along edge geometry.

    Uses the polyline waypoints if provided, otherwise falls back to the
    centroid-to-centroid line of sight.

    Returns (segment_length, mean_extinction).
    """
    if waypoints and len(waypoints) >= 2:
        length = _polyline_length(waypoints)
        k_avg = integrated_extinction_along_polyline(
            waypoints,
            time_s,
            extinction_sampler,
            step_m,
        )
    else:
        length = _euclidean(
            src_node.centroid_x,
            src_node.centroid_y,
            tgt_node.centroid_x,
            tgt_node.centroid_y,
        )
        k_avg = integrated_extinction_along_los(
            src_node.centroid_x,
            src_node.centroid_y,
            tgt_node.centroid_x,
            tgt_node.centroid_y,
            time_s,
            extinction_sampler,
            step_m,
        )
    return length, k_avg


def evaluate_segment(
    graph: StageGraph,
    source: str,
    target: str,
    time_s: float,
    extinction_sampler: ExtinctionSampler,
    fed_rate_sampler: FedRateSampler | None,
    config: RouteCostConfig,
) -> SegmentCost:
    """Evaluate cost for one edge of a route."""
    src_node = graph.nodes[source]
    tgt_node = graph.nodes[target]

    # Look up edge waypoints.
    waypoints = None
    for edge in graph.edges.get(source, []):
        if edge.target == target:
            waypoints = edge.waypoints
            break

    length, k_avg = _sample_segment_extinction(
        src_node,
        tgt_node,
        time_s,
        extinction_sampler,
        config.sampling_step_m,
        waypoints=waypoints,
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
        fed_rate = fed_rate_sampler.sample_fed_rate(time_s, mid_x, mid_y)
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
    cached_segments: dict[tuple[str, str], SegmentCost] | None = None,
    exit_counts: dict[str, int] | None = None,
) -> RouteCost:
    """Evaluate the composite cost for a full route (list of stage IDs)."""
    segments: list[SegmentCost] = []
    for i in range(len(path) - 1):
        cache_key = (path[i], path[i + 1])
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
            )
            if cached_segments is not None:
                cached_segments[cache_key] = seg
        segments.append(seg)

    path_length = sum(s.length_m for s in segments)
    total_k_samples = sum(s.k_avg * s.length_m for s in segments)
    k_ave = total_k_samples / path_length if path_length > 1e-9 else 0.0
    travel_time = sum(s.travel_time_s for s in segments)
    fed_growth = sum(s.fed_growth for s in segments)
    fed_max = current_fed + fed_growth

    # Composite cost: path_length * (1 + w_smoke * K_ave) + w_fed * FED_max
    composite = path_length * (1.0 + config.w_smoke * k_ave) + config.w_fed * fed_max

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

    rejected = False
    reason = None
    if fed_max > config.fed_rejection_threshold:
        rejected = True
        reason = f"FED_max {fed_max:.3f} > {config.fed_rejection_threshold}"

    return RouteCost(
        exit_id=path[-1] if path else "",
        path=path,
        path_length_m=path_length,
        k_ave_route=k_ave,
        travel_time_s=travel_time,
        fed_max_route=fed_max,
        composite_cost=composite,
        segments=segments,
        rejected=rejected,
        rejection_reason=reason,
        queue_time_s=queue_time,
    )


def rank_routes(
    graph: StageGraph,
    source: str,
    time_s: float,
    current_fed: float,
    extinction_sampler: ExtinctionSampler,
    fed_rate_sampler: FedRateSampler | None,
    config: RouteCostConfig,
    *,
    cached_segments: dict[tuple[str, str], SegmentCost] | None = None,
    exit_counts: dict[str, int] | None = None,
    vis_model=None,
    cognitive_map=None,
    agent_position: tuple[float, float] | None = None,
) -> list[RouteCost]:
    """Evaluate and rank all routes from *source* to reachable exits.

    Computes dynamic edge weights from current smoke/FED conditions,
    then runs Dijkstra with those weights so pathfinding picks the
    cheapest path under current conditions (not just the geometrically
    shortest).

    Returns routes sorted by composite cost (lowest first).
    Rejected routes are sorted to the end.
    If all routes are rejected, the least-bad route is un-rejected
    as a fallback.
    """
    # Restrict graph to agent's known subgraph (discovery mode).
    if cognitive_map is not None:
        from .cognitive_map import cognitive_subgraph

        graph = cognitive_subgraph(cognitive_map, graph)

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
            # Per-edge cost: additive decomposition of the composite formula.
            # current_fed is constant across routes for one agent, so omitting
            # it from edge costs does not affect ranking.
            dynamic_weights[cache_key] = (
                seg.length_m * (1.0 + config.w_smoke * seg.k_avg)
                + config.w_fed * seg.fed_growth
            )

    # Phase 2: Dijkstra with dynamic weights.
    all_paths = graph.shortest_paths_to_exits(source, dynamic_weights=dynamic_weights)
    if not all_paths:
        return []

    # Phase 3: evaluate full routes (reusing cached segments).
    costs: list[RouteCost] = []
    for exit_id, (_dist, path) in all_paths.items():
        rc = evaluate_route(
            graph,
            path,
            time_s,
            current_fed,
            extinction_sampler,
            fed_rate_sampler,
            config,
            cached_segments=cached_segments,
            exit_counts=exit_counts,
        )
        costs.append(rc)

    # Check visibility rejection.
    if vis_model is not None:
        # Reject any route whose first hop node sign is not visible from the
        # agent's current position.  Prefer the actual agent position over the
        # source node centroid so that large polygons don't introduce bias.
        # Falls back to always-visible for nodes without a sign descriptor.
        if agent_position is not None:
            ax, ay = agent_position
        else:
            src_node = graph.nodes.get(source)
            ax = src_node.centroid_x if src_node is not None else 0.0
            ay = src_node.centroid_y if src_node is not None else 0.0
        updated: list[RouteCost] = []
        for rc in costs:
            if not rc.rejected:
                next_node = rc.path[1] if len(rc.path) > 1 else rc.exit_id
                if not vis_model.node_is_visible(time_s, ax, ay, next_node):
                    rc = RouteCost(
                        exit_id=rc.exit_id,
                        path=rc.path,
                        path_length_m=rc.path_length_m,
                        k_ave_route=rc.k_ave_route,
                        travel_time_s=rc.travel_time_s,
                        fed_max_route=rc.fed_max_route,
                        composite_cost=rc.composite_cost,
                        segments=rc.segments,
                        rejected=True,
                        rejection_reason="next_node_not_visible",
                        queue_time_s=rc.queue_time_s,
                    )
            updated.append(rc)
        costs = updated
    else:
        # K_vis fallback: reject routes where all segments are non-visible,
        # but only if at least one other route has visibility.
        any_visible = any(
            any(s.visible for s in rc.segments) for rc in costs if not rc.rejected
        )
        if any_visible:
            updated = []
            for rc in costs:
                if not rc.rejected and not any(s.visible for s in rc.segments):
                    rc = RouteCost(
                        exit_id=rc.exit_id,
                        path=rc.path,
                        path_length_m=rc.path_length_m,
                        k_ave_route=rc.k_ave_route,
                        travel_time_s=rc.travel_time_s,
                        fed_max_route=rc.fed_max_route,
                        composite_cost=rc.composite_cost,
                        segments=rc.segments,
                        rejected=True,
                        rejection_reason="all segments non-visible",
                        queue_time_s=rc.queue_time_s,
                    )
                updated.append(rc)
            costs = updated

    # Sort: non-rejected first by cost, then rejected by cost.
    # Break ties by fewer intermediate stages.
    def sort_key(rc: RouteCost) -> tuple[int, float, int]:
        return (1 if rc.rejected else 0, rc.composite_cost, len(rc.path))

    costs.sort(key=sort_key)

    # Fallback: if all rejected, un-reject the least-bad.
    if costs and all(rc.rejected for rc in costs):
        best = costs[0]
        costs[0] = RouteCost(
            exit_id=best.exit_id,
            path=best.path,
            path_length_m=best.path_length_m,
            k_ave_route=best.k_ave_route,
            travel_time_s=best.travel_time_s,
            fed_max_route=best.fed_max_route,
            composite_cost=best.composite_cost,
            segments=best.segments,
            rejected=False,
            rejection_reason=f"fallback: {best.rejection_reason}",
            queue_time_s=best.queue_time_s,
        )

    return costs


# ── Dynamic rerouting (Phase 4) ──────────────────────────────────────


@dataclass(frozen=True)
class RerouteConfig:
    """Settings for periodic route reevaluation."""

    reevaluation_interval_s: float = 10.0
    cost_config: RouteCostConfig = field(default_factory=RouteCostConfig)


@dataclass
class AgentRouteState:
    """Per-agent routing state for reevaluation scheduling."""

    current_exit: str | None = None
    current_path: list[str] = field(default_factory=list)
    last_eval_time_s: float = -math.inf
    eval_offset_s: float = 0.0  # staggering offset


@dataclass(frozen=True)
class RouteSwitch:
    """Record of a route switch for diagnostics."""

    time_s: float
    agent_id: int
    old_exit: str | None
    new_exit: str
    old_cost: float | None
    new_cost: float
    reason: str


def compute_eval_offset(
    agent_id: int,
    interval_s: float,
    dt_s: float = 0.01,
) -> float:
    """Stagger reevaluation across agents to spread cost."""
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

    # Build deterministic path_choices: each stage → next stage at 100%.
    remaining = new_path[insert_idx:]
    new_choices: dict[str, list[tuple[str, float]]] = {}
    for i in range(len(remaining) - 1):
        new_choices[remaining[i]] = [(remaining[i + 1], 100.0)]

    # Merge new choices into existing path_choices (don't remove
    # choices for stages not on this path).
    old_choices = wait_info.get("path_choices", {})
    old_choices.update(new_choices)
    wait_info["path_choices"] = old_choices

    # If the agent's current target is not on the remaining path,
    # retarget to the next stage after the agent's current position.
    # remaining[0] is the agent's current position; remaining[1] is
    # the next stage it should move toward.
    if current_stage not in remaining and len(remaining) >= 2:
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
            wait_info["inside_since"] = None

    return True


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
    cached_segments: dict[tuple[str, str], SegmentCost] | None = None,
    *,
    exit_counts: dict[str, int] | None = None,
    vis_model=None,
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
        vis_model=vis_model,
        cognitive_map=cognitive_map,
        agent_position=agent_position,
    )
    if not ranked:
        return None

    best = ranked[0]
    if (
        best.rejected
        and best.rejection_reason
        and not best.rejection_reason.startswith("fallback")
    ):
        return None

    old_exit = route_state.current_exit
    old_cost = None
    if old_exit and old_exit != best.exit_id:
        # Find the old exit's cost for diagnostics.
        for rc in ranked:
            if rc.exit_id == old_exit:
                old_cost = rc.composite_cost
                break

    route_state.last_eval_time_s = current_time_s

    if old_exit == best.exit_id:
        # Same exit, update path but no switch.
        route_state.current_path = best.path
        return None

    # Reroute.
    stage_configs = wait_info.get("stage_configs", {})
    changed = reroute_agent(wait_info, best.path, stage_configs)
    if not changed:
        return None

    reason = "initial" if old_exit is None else "smoke_reroute"
    if best.rejection_reason and best.rejection_reason.startswith("fallback"):
        reason = "fallback"

    route_state.current_exit = best.exit_id
    route_state.current_path = best.path

    return RouteSwitch(
        time_s=current_time_s,
        agent_id=agent_id,
        old_exit=old_exit,
        new_exit=best.exit_id,
        old_cost=old_cost,
        new_cost=best.composite_cost,
        reason=reason,
    )
