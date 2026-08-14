"""Stage graph for shortest-path routing and smoke-adjusted rerouting."""

from __future__ import annotations

import heapq
import logging
import math
from dataclasses import dataclass, field, replace
from typing import Protocol

from shapely.geometry import Polygon

from .geometry import node_position as _node_position
from .smoke_speed import speed_factor_from_extinction

_logger = logging.getLogger(__name__)

_SECONDS_PER_MINUTE = 60.0

# Clear air is unbounded sight; every route there lands in the top band, so the
# band never discriminates and the model reduces exactly to nearest-exit. Note
# this holds at K = 0 exactly: at K = 1e-4 sight is 30 km and the band index is
# in the thousands, so two physically clear routes can still be ordered by band.
_MAX_BAND = 1_000_000

# Sight is a discriminator while it is scarce. Three classes at the default
# 10 m width means anything past 30 m is simply "clear", which is roughly where
# fdsvismap used to cap and comfortably above the 10 m the C/VM2 tenability
# limit is written at. Routes that saturate tie, and distance decides.
_BAND_SATURATION_CLASSES = 3

# A segment is cached per (source, target) and, when anticipating, per whole
# second of arrival time -- the same edge costs differently to an agent that
# reaches it a minute later.
SegmentCacheKey = tuple[str, str] | tuple[str, str, int]


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
) -> tuple[float, float]:
    """Mean and worst K sampled along a line of sight.

    The mean is what a route costs to walk; the worst is what stops an agent
    walking it, and averaging hides exactly the wall of smoke a person refuses
    to enter. Both come from one traverse.
    """
    n_samples = max(2, int(math.ceil(length / step_m)) + 1)
    total = 0.0
    worst = 0.0
    for i in range(n_samples):
        t = i / (n_samples - 1)
        x = x_from + t * (x_to - x_from)
        y = y_from + t * (y_to - y_from)
        k = extinction_sampler.sample_extinction(time_s, x, y)
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

    return _polyline_stats(waypoints, time_s, extinction_sampler, step_m)[0]


def _polyline_stats(
    waypoints: list[tuple[float, float]],
    time_s: float,
    extinction_sampler: ExtinctionSampler,
    step_m: float,
) -> tuple[float, float]:
    """Mean and worst K along a polyline -- see :func:`_los_stats`."""
    if len(waypoints) < 2:
        if waypoints:
            k = extinction_sampler.sample_extinction(
                time_s, waypoints[0][0], waypoints[0][1]
            )
            return k, k
        return 0.0, 0.0
    total_k = 0.0
    total_samples = 0
    worst = 0.0
    for i in range(len(waypoints) - 1):
        x0, y0 = waypoints[i]
        x1, y1 = waypoints[i + 1]
        seg_len = _euclidean(x0, y0, x1, y1)
        if seg_len < 1e-9:
            k = extinction_sampler.sample_extinction(time_s, x0, y0)
            total_k += k
            worst = max(worst, k)
            total_samples += 1
            continue
        n_samples = max(2, int(math.ceil(seg_len / step_m)) + 1)
        for j in range(n_samples):
            t = j / (n_samples - 1)
            x = x0 + t * (x1 - x0)
            y = y0 + t * (y1 - y0)
            k = extinction_sampler.sample_extinction(time_s, x, y)
            total_k += k
            worst = max(worst, k)
            total_samples += 1

    return (total_k / total_samples if total_samples > 0 else 0.0), worst


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

    # ── Gate model ────────────────────────────────────────────────────────
    # "gate": distance is the objective and smoke decides which exits remain
    # available; "additive": the historical w_smoke/w_fed toll, kept because
    # the smoke term multiplies route *length*, so a long clean detour pays for
    # its own length and can never win however large w_smoke is (sweeping it
    # 1 -> 20 on assets/world_100 moved 12 of 120 agents).
    cost_model: str = "gate"
    # A route is refused when the sighting distance at its worst point falls
    # below this fraction of the distance still to walk -- FDS+Evac's own door
    # criterion (evac.f90: "Check that visibility > 0.5*distance to the door").
    # Being distance-relative is the point: haze 5 m from an exit is usable and
    # the same haze at 40 m is not, which no absolute extinction limit can say.
    sight_distance_fraction: float = 0.5
    # Asymmetric sight gate, mirroring fed_return_margin. A route the agent is
    # already on is judged against the bare criterion; a rival has to clear it
    # by this factor before the agent will switch onto it. Without the deadband
    # a route whose sight sits near the threshold toggles in and out of
    # feasibility every tick and the agent follows it: measured on world100,
    # one exit swung between 2.9 m and 24.2 m of sight on consecutive seconds,
    # producing 169 returns to abandoned exits across 23 agents.
    sight_return_margin: float = 1.25
    # Jin's constant for the sign being read: 3 for light-reflecting signage,
    # 8 for internally illuminated. Sighting distance is S = c / K, uncapped,
    # so clear air gives infinite visibility and the gate never fires there.
    sign_contrast_c: float = 3.0
    # Feasible routes are ranked by visibility band before distance, so a
    # genuinely clearer way wins outright but a 0.02 /m difference does not
    # send anyone 30 m out of their way. 10 m is the sighting distance the
    # C/VM2 optical-density limits are derived from (0.13 /m reflective,
    # 0.347 /m illuminated), which is what makes the band width citable.
    band_width_m: float = 10.0
    # Charge each leg the smoke present when the agent would arrive there,
    # rather than the smoke standing there while it decides.
    anticipate: bool = True
    # Cap on how far ahead that reaches. Unbounded is perfect foresight; a
    # finite horizon models an occupant who can only judge the near future.
    foresight_horizon_s: float = math.inf
    # When every exit is dead, the agent keeps its least-bad target unless a
    # rival's worst extinction is better by this fraction -- without it the
    # least-bad choice changes with every flicker of the field.
    fallback_switch_margin: float = 0.2

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
            sight_distance_fraction=routing.get("sight_distance_fraction", 0.5),
            sight_return_margin=routing.get("sight_return_margin", 1.25),
            sign_contrast_c=routing.get("sign_contrast_c", 3.0),
            band_width_m=routing.get("band_width_m", 10.0),
            anticipate=routing.get("anticipate", True),
            foresight_horizon_s=routing.get("foresight_horizon_s", math.inf),
            fallback_switch_margin=routing.get("fallback_switch_margin", 0.2),
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
    # Gate model only. `min_visibility_m` is Jin's sighting distance at the
    # worst point of the route, `band` the class it falls in, and `feasible`
    # whether sight and dose both allow the route at all.
    k_max_route: float = 0.0
    min_visibility_m: float = math.inf
    band: int = 0
    feasible: bool = True
    # What the whole pipeline orders on -- ranking, the exit-switch anchor and
    # the same-exit path test all read this, so a model change lands in one
    # place. Under "additive" it is the composite; under "gate" it is time,
    # which only decides within a visibility band.
    rank_cost: float = 0.0


def _sample_segment_extinction(
    src_node: StageNode,
    tgt_node: StageNode,
    time_s: float,
    extinction_sampler: ExtinctionSampler,
    step_m: float,
    waypoints: list[tuple[float, float]] | None = None,
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
        )
    return length, k_avg, k_max


def _visibility_band(visibility_m: float, band_width_m: float) -> int:
    """Which class of sight a route falls in, coarse enough to tie often.

    Banding is what keeps distance in charge: two routes a few centimetres of
    visibility apart share a band and the nearer one wins, while a route a
    whole class clearer wins outright however far it is.

    Saturating at ``_BAND_SATURATION_CLASSES`` is what makes that true at the
    top of the range as well as the bottom. Sight is a discriminator while it
    is scarce; past a few tens of metres it is not, and one route seeing 91 m
    where another sees "unbounded" is not a difference anyone acts on. Before
    the ceiling, clear air scored ``_MAX_BAND`` while 91 m of sight scored 9,
    so a trace of smoke -- K = 0.03 /m -- dropped a route five orders of
    magnitude and sent agents 10 m out of their way. Measured on world100: two
    permanently feasible exits traded places every second, 182 times.
    """
    if band_width_m <= 0:
        return _MAX_BAND
    ceiling = _BAND_SATURATION_CLASSES * band_width_m
    if visibility_m >= ceiling:
        return _BAND_SATURATION_CLASSES
    return int(visibility_m // band_width_m)


def _sighting_distance(k: float, contrast_c: float) -> float:
    """Jin's sighting distance S = c / K, in metres, uncapped.

    Uncapped on purpose: clear air is K = 0 and must give infinite sight, or a
    long route would fail a distance-relative criterion with no fire at all.
    fdsvismap reports the same relation but clipped to its ``max_vis`` and
    masked where geometry conceals the sign -- both right for "can this sign be
    read", both wrong for "is this route passable".
    """
    if k <= 1e-9:
        return math.inf
    return contrast_c / k


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


def evaluate_segment(
    graph: StageGraph,
    source: str,
    target: str,
    time_s: float,
    extinction_sampler: ExtinctionSampler,
    fed_rate_sampler: FedRateSampler | None,
    config: RouteCostConfig,
    arrival_time_s: float | None = None,
) -> SegmentCost:
    """Evaluate cost for one edge of a route.

    *arrival_time_s* is when the agent would reach this edge, so the smoke it
    is charged is the smoke it will meet rather than the smoke standing there
    while it decides. Defaults to *time_s*, which is the no-foresight answer.
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
    cached_segments: dict[SegmentCacheKey, SegmentCost] | None = None,
    exit_counts: dict[str, int] | None = None,
    current_exit: str | None = None,
    agent_position: tuple[float, float] | None = None,
    current_target: str | None = None,
    visibility_model=None,
    los_position: tuple[float, float] | None = None,
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
    walked = 0.0
    for i in range(len(path) - 1):
        cache_key = (path[i], path[i + 1])
        # With anticipation an edge costs what it costs *when you get there*,
        # so the same edge on two routes is two different questions and the
        # cache has to key on both. Bucketed to the second: finer than the
        # reroute interval, coarser than nothing, and well under the interval
        # FDS writes slices at.
        t_arrive = _arrival_time(time_s, walked, config)
        if config.anticipate:
            cache_key = (path[i], path[i + 1], round(t_arrive))
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
    if agent_position is not None and first_share < 1.0 and len(path) >= 2:
        next_node = graph.nodes.get(path[1])
        if next_node is not None:
            _, first_k_max = _los_stats(
                agent_position[0],
                agent_position[1],
                next_node.centroid_x,
                next_node.centroid_y,
                segments[0].arrival_time_s,
                extinction_sampler,
                config.sampling_step_m,
                first_share * segments[0].length_m,
            )
    k_max = max(
        [first_k_max] + [s.k_max for _, s in weighted[1:]],
        default=0.0,
    )
    # Sight is estimated from the route's *mean* extinction, not its worst
    # point. FDS+Evac's See_door averages K along the sight line for the same
    # reason: a maximum over sampled cells is a step function of where the
    # agent stands, so one dense cell entering the sample swings the estimate
    # by an order of magnitude between ticks. Measured on world100, the same
    # 28.9 m route reported 91 m of sight, then 8 m, then 91 m again on
    # consecutive seconds, and the ordering flipped with it -- 182 returns to
    # abandoned exits across 26 agents. k_max_route is still reported, and
    # still drives the all-refused fallback, where the question is which walk
    # is survivable rather than which is legible.
    min_visibility = _sighting_distance(k_ave, config.sign_contrast_c)

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

    # Sight gate: FDS+Evac's rule that a door is only a candidate while the
    # agent can see a useful fraction of the way to it (evac.f90,
    # Change_Target_Door). Being relative to distance is what lets the same
    # smoke allow a near exit and refuse a far one.
    #
    # One estimator, applied to every candidate: c / K_ave over the route
    # polyline against the distance still to walk. With k_ave the criterion is
    # exactly an optical depth, tau = K_ave * L <= 2c, which is the same
    # statement FDS+Evac's See_door makes along its sight line -- so the two are
    # the same form, and the polyline is the one available for every exit.
    #
    # fdsvismap's line of sight is *not* used to gate, though it is the more
    # faithful measurement, because it is only defined where a sign resolves.
    # Selecting the criterion per exit made sign geometry decide which exits
    # were gated at all: measured on world100, one exit was sight-tested 43
    # times and fell back 2095 times, and moving a sign 2 m would change which
    # exits are exempt. Mixing them was worse still -- the same 22 m route read
    # 9.9 m on one tick and 68.3 m on the next as the line of sight resolved,
    # and routes flipped feasibility as agents walked past obstructions.
    #
    # Not seeing a sign is a statement about wayfinding, not about whether a
    # route can be walked, so it belongs in the cognitive map, not in this gate.
    feasible = not rejected
    band = _visibility_band(min_visibility, config.band_width_m)
    if config.cost_model == "gate":
        sight = min_visibility
        needed = config.sight_distance_fraction * effective_length
        # A rival exit has to clear the criterion by a margin before the agent
        # will switch onto it. The reason string says so, because reading
        # "6.8 m < 8.4 m (0.5 x 13.4 m)" and finding 0.5 x 13.4 = 6.7 sent a
        # reviewer to the wrong conclusion about which rule refused the route.
        needed_scaled = not is_current and current_exit is not None
        if needed_scaled:
            needed *= config.sight_return_margin
        how = "path"
        if sight < needed:
            feasible = False
            rejected = True
            reason = (
                f"sight ({how}) {sight:.1f} m < {needed:.1f} m "
                f"({config.sight_distance_fraction:g} x {effective_length:.1f} m"
                f"{' x ' + format(config.sight_return_margin, 'g') if needed_scaled else ''})"
            )

    if config.cost_model == "gate":
        # Queue delay is time, so it belongs beside travel time rather than in
        # the composite the gate ignores -- otherwise opting into congestion-
        # aware routing (w_queue) would silently do nothing.
        rank_cost = travel_time + queue_time * config.w_queue
    else:
        rank_cost = composite

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
        k_max_route=k_max,
        min_visibility_m=min_visibility,
        band=band,
        feasible=feasible,
        rank_cost=rank_cost,
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
    cached_segments: dict[SegmentCacheKey, SegmentCost] | None = None,
    exit_counts: dict[str, int] | None = None,
    cognitive_map=None,
    agent_position: tuple[float, float] | None = None,
    current_exit: str | None = None,
    current_target: str | None = None,
    visibility_model=None,
    los_position: tuple[float, float] | None = None,
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
            visibility_model=visibility_model,
            los_position=los_position,
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
    #
    # Additive only. Under the gate this was a *second* smoke criterion on top
    # of the sight test, and a bare threshold on K with no hysteresis, so a
    # route sitting near it toggled every tick: measured on world100, a 9 m
    # route with a 2 s travel time was struck out and reinstated repeatedly
    # while the agent bounced to a 27 m rival and back. It also set `rejected`
    # without clearing `feasible`, leaving the two fields disagreeing. The
    # plan retired it under the gate; this is that retirement.
    any_visible = config.cost_model != "gate" and any(
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

    # Ordering. Under "additive" the composite decides, as it always has.
    # Under "gate" distance decides among routes that are still available, and
    # a route a whole visibility band clearer wins first: smoke says which
    # exits exist, not how much each metre of them is worth.
    # Both models order the same way; only rank_cost differs between them, and
    # evaluate_route already decided which quantity that is. The gate briefly
    # ordered by visibility band first, and the band did not break ties, it
    # decided: on l_corridor it placed agents on the 58 m route while both
    # routes were optically clear (k_ave = 0.000 for each), because a route
    # with any trace of smoke gets a finite S = c/K while one with none got
    # _MAX_BAND. Smoke says which exits exist; it does not also get to say
    # which of the survivors is nearer.
    def sort_key(rc: RouteCost) -> tuple[int, float, int]:
        return (1 if rc.rejected else 0, rc.rank_cost, len(rc.path))

    costs.sort(key=sort_key)

    # Fallback: with every route refused the agent still has to go somewhere,
    # and the least bad one is the one whose worst stretch is least bad -- the
    # question is surviving the walk, not averaging it.
    #
    # Refusal is never remembered: the sight criterion is measured against the
    # distance *still to walk*, so it relaxes as the agent closes on an exit and
    # the smoke that refused a door at 40 m accepts it at 2 m. Recomputing every
    # tick is what lets that happen. The price is that in a fire smoky enough to
    # refuse everything -- which is most of a real run, see
    # docs/gate-model-review-notes.md -- the ordering follows the field, so the
    # current exit is held unless a rival's worst stretch is clearly milder.
    #
    # Banded, not raw: measured on world100, ordering refused routes by k_max
    # alone put a 51 m route ahead of a 22 m one on 2.0 m of sight against 1.8 m.
    # Two tenths of a metre of visibility, neither of them usable, decided a 29 m
    # detour. Sight this poor is a class, not a scale, so the band decides and
    # distance breaks the tie -- the same rule the feasible routes get.
    if costs and all(rc.rejected for rc in costs):
        costs.sort(key=lambda rc: (-rc.band, rc.rank_cost))
        current = next((rc for rc in costs if rc.exit_id == current_exit), None)
        if current is not None and costs[0].exit_id != current.exit_id:
            margin = 1.0 - config.fallback_switch_margin
            if costs[0].k_max_route > current.k_max_route * margin:
                costs = [current] + [rc for rc in costs if rc is not current]
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
    cached_segments: dict[SegmentCacheKey, SegmentCost] | None = None,
    *,
    exit_counts: dict[str, int] | None = None,
    cognitive_map=None,
    agent_position: tuple[float, float] | None = None,
    visibility_model=None,
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
        visibility_model=visibility_model,
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
    old_rc = None
    old_cost = None
    old_must_flee = False
    if old_exit and old_exit != best.exit_id:
        # Find the old exit's route -- for its cost, its visibility band, and
        # whether it is rejected for a *safety* reason (FED-lethal / impassable
        # smoke), which disables anchoring below. A mild visibility rejection
        # (light-haze path / an unreadable sign) is NOT a reason to bypass the
        # anchor — see _must_flee_rejection.
        for rc in ranked:
            if rc.exit_id == old_exit:
                old_rc = rc
                old_cost = rc.rank_cost
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
                visibility_model=visibility_model,
            ).rank_cost
            if best.rank_cost < committed_cost * _PATH_IMPROVEMENT_THRESHOLD:
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
                        new_cost=best.rank_cost,
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
    #
    # Under the gate model this is the *only* churn protection: refusals are not
    # remembered, so nothing else stops an agent following the field.
    #
    # Under the gate model the anchor is applied *within* a visibility band. A
    # rival a whole band clearer is adopted outright: banding is the model's
    # statement that the two routes are not comparable on time, and putting the
    # anchor in front of it would veto exactly the clearer-but-longer switch the
    # gate exists to allow. Once the bands tie, distance is the objective again
    # and the rival has to beat the anchor on time like any other.
    if (
        old_exit is not None
        and old_cost is not None
        and not old_must_flee
        and not (
            config.cost_config.cost_model == "gate"
            and old_rc is not None
            and best.band > old_rc.band
            # Only a route the agent can actually take earns the bypass. When
            # every route is refused the bands compare two walks nobody can
            # make, and letting one of them jump the anchor is what made agents
            # ping-pong: the fallback pushes them onto a rival, the old exit
            # heals a band on the next tick, and back they go on a 1% gain.
            and best.feasible
            # A band is a quantised sighting distance, and a quantiser with no
            # hysteresis oscillates: sight jittering either side of a band edge
            # flips the order every tick, and because the bypass skips the
            # anchor entirely, every flip is an actual switch. Measured on
            # world100, two permanently feasible exits 24.3 m and 34.0 m long
            # traded places every second, 182 times across 26 agents. So the
            # band has to be backed by a real margin in metres before it is
            # allowed to overrule distance -- the same margin the anchor uses.
            and best.min_visibility_m * config.exit_switch_anchor
            > old_rc.min_visibility_m
        )
        and best.rank_cost >= old_cost * config.exit_switch_anchor
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
