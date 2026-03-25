"""Tests for StageGraph construction and Dijkstra shortest-path routing."""

import math

import pytest
from shapely.geometry import Polygon

from src.core.route_graph import StageGraph, StageNode, StageEdge


def _box(cx: float, cy: float, half: float = 1.0) -> Polygon:
    """Return a square polygon centred at (cx, cy)."""
    return Polygon(
        [
            (cx - half, cy - half),
            (cx + half, cy - half),
            (cx + half, cy + half),
            (cx - half, cy + half),
        ]
    )


# ── fixtures ──────────────────────────────────────────────────────────


@pytest.fixture()
def linear_graph():
    """D0 ──10──> C0 ──10──> E0   (straight line at y=0)."""
    direct_steering_info = {
        "C0": {"polygon": _box(10, 0), "stage_type": "checkpoint"},
        "E0": {"polygon": _box(20, 0), "stage_type": "exit"},
    }
    distributions = {
        "D0": {"coordinates": list(_box(0, 0).exterior.coords)},
    }
    transitions = [
        {"from": "D0", "to": "C0"},
        {"from": "C0", "to": "E0"},
    ]
    return StageGraph.from_scenario(direct_steering_info, transitions, distributions)


@pytest.fixture()
def diamond_graph():
    r"""Diamond with two paths from D0 to E0.

         C0 (0, 10)
        /          \
    D0 (0,0)     E0 (20, 10)
        \          /
         C1 (0, 30) -- longer detour
    """
    direct_steering_info = {
        "C0": {"polygon": _box(0, 10), "stage_type": "checkpoint"},
        "C1": {"polygon": _box(0, 30), "stage_type": "checkpoint"},
        "E0": {"polygon": _box(20, 10), "stage_type": "exit"},
    }
    distributions = {
        "D0": {"coordinates": list(_box(0, 0).exterior.coords)},
    }
    transitions = [
        {"from": "D0", "to": "C0"},
        {"from": "D0", "to": "C1"},
        {"from": "C0", "to": "E0"},
        {"from": "C1", "to": "E0"},
    ]
    return StageGraph.from_scenario(direct_steering_info, transitions, distributions)


@pytest.fixture()
def multi_exit_graph():
    """D0 with two reachable exits at different distances.

    D0 (0,0) ──10──> E0 (10,0)
    D0 (0,0) ──20──> E1 (20,0)
    """
    direct_steering_info = {
        "E0": {"polygon": _box(10, 0), "stage_type": "exit"},
        "E1": {"polygon": _box(20, 0), "stage_type": "exit"},
    }
    distributions = {
        "D0": {"coordinates": list(_box(0, 0).exterior.coords)},
    }
    transitions = [
        {"from": "D0", "to": "E0"},
        {"from": "D0", "to": "E1"},
    ]
    return StageGraph.from_scenario(direct_steering_info, transitions, distributions)


# ── node / edge construction ──────────────────────────────────────────


class TestGraphConstruction:
    def test_nodes_include_distributions(self, linear_graph):
        assert "D0" in linear_graph.nodes
        assert linear_graph.nodes["D0"].stage_type == "distribution"

    def test_nodes_include_checkpoints_and_exits(self, linear_graph):
        assert linear_graph.nodes["C0"].stage_type == "checkpoint"
        assert linear_graph.nodes["E0"].stage_type == "exit"

    def test_edge_count(self, linear_graph):
        all_edges = sum(len(v) for v in linear_graph.edges.values())
        assert all_edges == 2

    def test_edge_weight_is_euclidean(self, linear_graph):
        edge = linear_graph.edges["D0"][0]
        assert edge.target == "C0"
        assert abs(edge.weight - 10.0) < 0.01

    def test_centroid_from_polygon(self, linear_graph):
        node = linear_graph.nodes["C0"]
        assert abs(node.centroid_x - 10.0) < 0.01
        assert abs(node.centroid_y - 0.0) < 0.01

    def test_exit_nodes(self, multi_exit_graph):
        exits = multi_exit_graph.exit_nodes()
        assert sorted(exits) == ["E0", "E1"]

    def test_distribution_nodes(self, multi_exit_graph):
        dists = multi_exit_graph.distribution_nodes()
        assert dists == ["D0"]

    def test_missing_node_in_transition_skipped(self):
        """Transitions referencing unknown stages are silently skipped."""
        graph = StageGraph.from_scenario(
            direct_steering_info={
                "E0": {"polygon": _box(10, 0), "stage_type": "exit"},
            },
            transitions=[{"from": "UNKNOWN", "to": "E0"}],
        )
        assert len(graph.edges) == 0


# ── Dijkstra shortest path ───────────────────────────────────────────


class TestDijkstra:
    def test_linear_path(self, linear_graph):
        result = linear_graph.shortest_exit("D0")
        assert result is not None
        exit_id, cost, path = result
        assert exit_id == "E0"
        assert abs(cost - 20.0) < 0.01
        assert path == ["D0", "C0", "E0"]

    def test_diamond_picks_shorter_path(self, diamond_graph):
        result = diamond_graph.shortest_exit("D0")
        assert result is not None
        exit_id, cost, path = result
        assert exit_id == "E0"
        # D0(0,0)->C0(0,10)=10, C0(0,10)->E0(20,10)=20 => total 30
        # D0(0,0)->C1(0,30)=30, C1(0,30)->E0(20,10)=~28.28 => total ~58.28
        assert path == ["D0", "C0", "E0"]
        assert cost < 31.0

    def test_multi_exit_picks_nearest(self, multi_exit_graph):
        result = multi_exit_graph.shortest_exit("D0")
        assert result is not None
        exit_id, cost, path = result
        assert exit_id == "E0"
        assert abs(cost - 10.0) < 0.01

    def test_all_exits_returned(self, multi_exit_graph):
        paths = multi_exit_graph.shortest_paths_to_exits("D0")
        assert len(paths) == 2
        assert "E0" in paths
        assert "E1" in paths
        assert paths["E0"][0] < paths["E1"][0]

    def test_unreachable_exit(self):
        """An exit with no path from the source is not returned."""
        direct_steering_info = {
            "E0": {"polygon": _box(10, 0), "stage_type": "exit"},
            "E1": {"polygon": _box(20, 0), "stage_type": "exit"},
        }
        distributions = {
            "D0": {"coordinates": list(_box(0, 0).exterior.coords)},
        }
        transitions = [{"from": "D0", "to": "E0"}]
        graph = StageGraph.from_scenario(
            direct_steering_info, transitions, distributions
        )
        paths = graph.shortest_paths_to_exits("D0")
        assert "E0" in paths
        assert "E1" not in paths

    def test_no_reachable_exit(self):
        """shortest_exit returns None when no exit is reachable."""
        direct_steering_info = {
            "C0": {"polygon": _box(10, 0), "stage_type": "checkpoint"},
        }
        distributions = {
            "D0": {"coordinates": list(_box(0, 0).exterior.coords)},
        }
        transitions = [{"from": "D0", "to": "C0"}]
        graph = StageGraph.from_scenario(
            direct_steering_info, transitions, distributions
        )
        assert graph.shortest_exit("D0") is None

    def test_dijkstra_from_checkpoint(self, linear_graph):
        """Can query shortest path from an intermediate checkpoint."""
        result = linear_graph.shortest_exit("C0")
        assert result is not None
        exit_id, cost, path = result
        assert exit_id == "E0"
        assert path == ["C0", "E0"]


# ── edge cases ────────────────────────────────────────────────────────


class TestEdgeCases:
    def test_empty_graph(self):
        graph = StageGraph.from_scenario({}, [], None)
        assert len(graph.nodes) == 0
        assert len(graph.edges) == 0
        assert graph.exit_nodes() == []

    def test_self_loop_ignored_in_shortest_path(self):
        """A self-loop edge doesn't break Dijkstra."""
        direct_steering_info = {
            "E0": {"polygon": _box(10, 0), "stage_type": "exit"},
        }
        distributions = {
            "D0": {"coordinates": list(_box(0, 0).exterior.coords)},
        }
        transitions = [
            {"from": "D0", "to": "D0"},
            {"from": "D0", "to": "E0"},
        ]
        graph = StageGraph.from_scenario(
            direct_steering_info, transitions, distributions
        )
        result = graph.shortest_exit("D0")
        assert result is not None
        assert result[0] == "E0"

    def test_duplicate_transitions(self):
        """Duplicate transitions create parallel edges; shortest wins."""
        direct_steering_info = {
            "E0": {"polygon": _box(10, 0), "stage_type": "exit"},
        }
        distributions = {
            "D0": {"coordinates": list(_box(0, 0).exterior.coords)},
        }
        transitions = [
            {"from": "D0", "to": "E0"},
            {"from": "D0", "to": "E0"},
        ]
        graph = StageGraph.from_scenario(
            direct_steering_info, transitions, distributions
        )
        result = graph.shortest_exit("D0")
        assert result is not None
        assert abs(result[1] - 10.0) < 0.01

    def test_distributions_from_polygon_key(self):
        """Distributions can supply a 'polygon' key instead of 'coordinates'."""
        direct_steering_info = {
            "E0": {"polygon": _box(10, 0), "stage_type": "exit"},
        }
        distributions = {
            "D0": {"polygon": _box(0, 0)},
        }
        transitions = [{"from": "D0", "to": "E0"}]
        graph = StageGraph.from_scenario(
            direct_steering_info, transitions, distributions
        )
        assert "D0" in graph.nodes
        result = graph.shortest_exit("D0")
        assert result is not None
