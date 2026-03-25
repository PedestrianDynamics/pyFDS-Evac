"""Stage graph for shortest-path routing and smoke-adjusted rerouting."""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass, field

from shapely.geometry import Polygon


@dataclass(frozen=True)
class StageNode:
    """A node in the stage graph representing one stage."""

    stage_id: str
    centroid_x: float
    centroid_y: float
    stage_type: str  # "exit", "checkpoint", "distribution", "zone"


@dataclass
class StageEdge:
    """A directed edge in the stage graph."""

    source: str
    target: str
    weight: float  # Euclidean distance between centroids


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
        """
        graph = cls()

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
            )

        # Add edges from transitions.
        for tr in transitions:
            src = tr.get("from", "")
            tgt = tr.get("to", "")
            if src not in graph.nodes or tgt not in graph.nodes:
                continue
            src_node = graph.nodes[src]
            tgt_node = graph.nodes[tgt]
            weight = _euclidean(
                src_node.centroid_x,
                src_node.centroid_y,
                tgt_node.centroid_x,
                tgt_node.centroid_y,
            )
            edge = StageEdge(source=src, target=tgt, weight=weight)
            graph.edges.setdefault(src, []).append(edge)

        return graph

    def exit_nodes(self) -> list[str]:
        """Return IDs of all exit stages."""
        return [
            sid for sid, node in self.nodes.items() if node.stage_type == "exit"
        ]

    def distribution_nodes(self) -> list[str]:
        """Return IDs of all distribution stages."""
        return [
            sid
            for sid, node in self.nodes.items()
            if node.stage_type == "distribution"
        ]

    def shortest_paths_to_exits(
        self, source: str
    ) -> dict[str, tuple[float, list[str]]]:
        """Dijkstra from *source* to every reachable exit.

        Returns a dict mapping exit_id -> (cost, path) where path is the
        list of stage IDs from source to exit inclusive.
        """
        dist, prev = self._dijkstra(source)
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

    def _dijkstra(self, source: str) -> tuple[dict[str, float], dict[str, str | None]]:
        """Run Dijkstra from *source*.  Returns (dist, prev) dicts."""
        dist: dict[str, float] = {sid: math.inf for sid in self.nodes}
        prev: dict[str, str | None] = {sid: None for sid in self.nodes}
        dist[source] = 0.0
        heap: list[tuple[float, str]] = [(0.0, source)]

        while heap:
            d, u = heapq.heappop(heap)
            if d > dist[u]:
                continue
            for edge in self.edges.get(u, []):
                alt = d + edge.weight
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
