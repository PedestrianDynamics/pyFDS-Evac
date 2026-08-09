"""Stage graph for shortest-path routing and smoke-adjusted rerouting."""

from __future__ import annotations

import heapq
import logging
import math
from dataclasses import dataclass, field, replace
from typing import Protocol

from shapely.geometry import Polygon

from .smoke_speed import speed_factor_from_extinction

_logger = logging.getLogger(__name__)

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
    # Kept so route evaluation can measure distances from an agent's actual
    # position along the walkable area, the same way edges are measured.
    routing_engine: object | None = None

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


def _walkable_distance(routing_engine, from_xy, to_xy) -> float:
    """Path length through the walkable area, or straight-line if unavailable.

    A wrong distance only degrades ranking, so a failed or degenerate query
    falls back rather than ending the run.
    """
    if routing_engine is None:
        return _euclidean(from_xy[0], from_xy[1], to_xy[0], to_xy[1])
    try:
        waypoints = list(routing_engine.compute_waypoints(from_xy, to_xy))
    except Exception:
        return _euclidean(from_xy[0], from_xy[1], to_xy[0], to_xy[1])
    if len(waypoints) < 2:
        return _euclidean(from_xy[0], from_xy[1], to_xy[0], to_xy[1])
    return _polyline_length(waypoints)


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


def _position_aware_length(
    graph: StageGraph,
    path: list[str],
    agent_position: tuple[float, float],
    path_length: float,
    first_length_m: float,
) -> tuple[float, float]:
    """Haensel path-integrated distance measured from the agent's position.

    Returns ``(effective_length, first_share)``, where ``first_share`` is the
    still-untraversed fraction of the first segment -- the stretch over which
    the smoke and FED integrals are charged, so exposure already incurred is
    not billed twice.

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
    """
    first_node = graph.nodes.get(path[0])
    next_node = graph.nodes.get(path[1])
    if first_node is None or next_node is None:
        return path_length, 1.0

    remaining = _walkable_distance(
        graph.routing_engine,
        agent_position,
        (next_node.centroid_x, next_node.centroid_y),
    )
    if first_length_m <= 1e-9:
        return path_length - first_length_m + remaining, 1.0
    # Floored above zero so an impassable first segment (infinite travel time)
    # stays infinite even for an agent standing on its end node.
    share = min(1.0, max(1e-9, remaining / first_length_m))
    return path_length - first_length_m + remaining, share


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
    ``_position_aware_length``. The smoke and FED terms are credited over the
    same stretch as the distance, so exposure already incurred on the traversed
    part -- and already carried in ``current_fed`` -- is not charged a second
    time.

    ``current_target`` is accepted and ignored; it is kept so callers that
    already thread it through do not have to change, and so the parameter is
    available if a future rule needs the agent's heading.
    """
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

    # Position-aware distance (Haensel path-integrated). Default: the geometric
    # node-to-node path_length (used everywhere agent_position is absent).
    effective_length = path_length
    first_share = 1.0
    if agent_position is not None and len(path) >= 2:
        effective_length, first_share = _position_aware_length(
            graph,
            path,
            agent_position,
            path_length,
            segments[0].length_m,
        )

    # Exposure is accumulated over the same stretch the distance term charges:
    # the smoke and FED the agent already took on the traversed part of the first
    # segment are in current_fed, so charging the full segment would count them
    # twice and inflate the FED and smoke terms of a route it is midway along.
    shares = [first_share] + [1.0] * (len(segments) - 1)
    weighted = list(zip(shares, segments))
    exposure_length = sum(w * s.length_m for w, s in weighted)
    total_k_samples = sum(w * s.k_avg * s.length_m for w, s in weighted)
    k_ave = total_k_samples / exposure_length if exposure_length > 1e-9 else 0.0
    travel_time = sum(w * s.travel_time_s for w, s in weighted)
    fed_growth = sum(w * s.fed_growth for w, s in weighted)
    fed_max = current_fed + fed_growth

    # Composite cost: effective_length * (1 + w_smoke * K_ave) + w_fed * FED_max
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

    # Asymmetric FED rejection (deadband). The agent's current exit keeps the
    # full threshold so it always flees the instant dose crosses incapacitation.
    # A different exit is held to the stricter fed_return_margin fraction, so the
    # agent only switches onto it once its dose is clearly safe — this stops the
    # flip-flop when a marginal route's predicted dose wobbles around 1.0.
    # current_exit=None (e.g. initial choice, or a direct evaluate_route call)
    # falls back to the plain threshold for every route.
    exit_id = path[-1] if path else ""
    is_current = current_exit is not None and exit_id == current_exit
    fed_threshold = config.fed_rejection_threshold
    if not is_current and current_exit is not None:
        fed_threshold *= config.fed_return_margin

    rejected = False
    reason = None
    if fed_max > fed_threshold:
        rejected = True
        reason = f"FED_max {fed_max:.3f} > {fed_threshold:.3f}"

    return RouteCost(
        exit_id=exit_id,
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
    cognitive_map=None,
    agent_position: tuple[float, float] | None = None,
    current_exit: str | None = None,
    current_target: str | None = None,
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
            current_exit=current_exit,
            agent_position=agent_position,
            current_target=current_target,
        )
        costs.append(rc)

    # Sign legibility is not consulted here.  It decides what enters the
    # agent's cognitive map (see cognitive_map.expand_from_visibility), and the
    # map decides what Dijkstra can see -- so an unknown exit is absent from
    # the graph rather than present-and-vetoed.  Checking it again here
    # double-gated the same criterion, blocked agents who already knew the
    # building, and forbade an agent from using an exit it had legitimately
    # learned once the sign went out of view.
    # K_vis fallback: reject routes where all segments are non-visible,
    # but only if at least one other route has visibility.
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
        costs[0] = replace(
            best,
            rejected=False,
            rejection_reason=f"fallback: {best.rejection_reason}",
        )

    return costs


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
    """
    if not rc.rejected:
        return False
    reason = (rc.rejection_reason or "").removeprefix("fallback: ")
    if reason.startswith("FED"):
        return True
    if "visible" in reason:  # smoke-obscured path or unreadable sign
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
    if (current_stage not in remaining or idle) and len(remaining) >= 2:
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
    )
    if not ranked:
        # No exit reachable in the agent's known subgraph (typically a
        # discovery agent that hasn't found the way out yet). Rather than
        # standing still, head toward the nearest known-but-unexplored node
        # so the cognitive map keeps growing until an exit is found.
        route_state.last_eval_time_s = current_time_s
        if cognitive_map is None:
            return None
        from .cognitive_map import nearest_frontier_target, wander_target

        idle = wait_info.get("state") == "idle"
        reason = "explore"
        frontier = nearest_frontier_target(cognitive_map, graph, source, agent_position)
        if frontier is None:
            # Knowledge exhausted: every known node is visited and none of it
            # leads to an exit. Patrol the known nodes instead of standing --
            # perception runs from the agent's position, so a walked leg can
            # make a sign readable that never was from any node it stood on.
            if idle and route_state.current_path:
                # The previous patrol leg was completed; move on to the next
                # stop, or a single-candidate rotation would re-offer the node
                # the agent is standing on the way to.
                route_state.wander_step += 1
            frontier = wander_target(
                cognitive_map, graph, source, route_state.wander_step
            )
            reason = "wander"
        if frontier is None:
            return None
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
            return None
        stage_configs = wait_info.get("stage_configs", {})
        changed = reroute_agent(wait_info, path, stage_configs)
        if not changed:
            return None
        route_state.current_path = path
        # old_exit is left None on purpose: exploring toward a frontier node
        # does not abandon any exit commitment, so this switch must not drive
        # the caller's exit_counts bookkeeping (new_exit is a checkpoint, not
        # an exit). route_state.current_exit is deliberately unchanged.
        return RouteSwitch(
            time_s=current_time_s,
            agent_id=agent_id,
            old_exit=None,
            new_exit=target_node,
            old_cost=None,
            new_cost=0.0,
            reason=reason,
        )

    best = ranked[0]
    if (
        best.rejected
        and best.rejection_reason
        and not best.rejection_reason.startswith("fallback")
    ):
        return None

    old_exit = route_state.current_exit
    old_cost = None
    old_must_flee = False
    if old_exit and old_exit != best.exit_id:
        # Find the old exit's cost (for diagnostics) and whether it is rejected
        # for a *safety* reason (FED-lethal / impassable smoke), which disables
        # anchoring below. A mild visibility rejection (light-haze path / an
        # unreadable sign) is NOT a reason to bypass the anchor — see
        # _must_flee_rejection.
        for rc in ranked:
            if rc.exit_id == old_exit:
                old_cost = rc.composite_cost
                old_must_flee = _must_flee_rejection(rc, config.cost_config)
                break

    route_state.last_eval_time_s = current_time_s

    # An idle agent stands on a node with no onward plan, so there is no
    # committed path to compare against and no churn to protect it from. It must
    # be routed even when the best exit is the one it was nominally assigned at
    # spawn -- an assignment made by straight-line distance before routing ran,
    # over an exit the agent had not yet discovered. Without this, an explorer
    # whose assigned exit happens to be the one it finds is never routed to it
    # and stands at the doorway for the rest of the run.
    if old_exit == best.exit_id and wait_info.get("state") != "idle":
        # Same exit — only reroute if the newly ranked path to it is
        # meaningfully cheaper than the path the agent is actually walking
        # right now (not just whatever was last recorded as "best").
        committed_path = _reconstruct_committed_path(wait_info)
        if (
            committed_path
            and committed_path[-1] == best.exit_id
            and all(n in graph.nodes for n in committed_path)
        ):
            committed_cost = evaluate_route(
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
            ).composite_cost
            if best.composite_cost < committed_cost * _PATH_IMPROVEMENT_THRESHOLD:
                stage_configs = wait_info.get("stage_configs", {})
                changed = reroute_agent(wait_info, best.path, stage_configs)
                if changed:
                    route_state.current_path = best.path
                    return RouteSwitch(
                        time_s=current_time_s,
                        agent_id=agent_id,
                        old_exit=old_exit,
                        new_exit=best.exit_id,
                        old_cost=committed_cost,
                        new_cost=best.composite_cost,
                        reason="better_path",
                    )
        route_state.current_path = best.path
        return None

    # Anchoring / hysteresis: don't abandon the current exit for a *different* one
    # unless the new exit is meaningfully cheaper (beats the current exit's cost by
    # more than the anchor margin). Without this, near-tied exits flip-flop on every
    # reevaluation — worst at short reroute intervals. Anchoring is skipped when:
    #   - it is the initial choice (old_exit is None), or
    #   - the old exit is no longer reachable / priced (old_cost is None), or
    #   - the old exit is FED-lethal (old_must_flee) — the agent must flee a deadly
    #     exit regardless of cost, so hysteresis must not pin it there. A merely
    #     smoke-obscured/low-visibility exit does NOT flee: smoke is already in the
    #     cost, and bypassing the anchor on it causes the flip-flop.
    if (
        old_exit is not None
        and old_cost is not None
        and not old_must_flee
        and best.composite_cost >= old_cost * config.exit_switch_anchor
    ):
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
