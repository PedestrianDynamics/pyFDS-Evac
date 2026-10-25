"""length_outside_m: route length outside the FDS coverage (#431)."""

from types import SimpleNamespace

import pytest
from shapely.geometry import box

from pyfds_evac.core.fds_coverage import route_length_outside
from pyfds_evac.core.route_graph import StageEdge, StageGraph

DOMAIN = box(0, 0, 10, 10)


def _graph(*edges):
    graph = StageGraph()
    for source, target, points in edges:
        graph.edges.setdefault(source, []).append(
            StageEdge(source, target, 0.0, list(points))
        )
    return graph


def _seg(source, target):
    return SimpleNamespace(source=source, target=target)


def test_inside_route_has_no_length_outside():
    graph = _graph(("a", "b", [(1, 1), (9, 1)]))
    assert route_length_outside([_seg("a", "b")], graph, DOMAIN) == 0.0


def test_length_outside_sums_the_route_segments():
    graph = _graph(
        ("a", "b", [(5, 5), (12, 5)]),  # 2 m outside
        ("b", "c", [(12, 5), (12, 8)]),  # 3 m outside
        ("b", "x", [(12, 5), (40, 5)]),  # not on the route
    )
    segments = [_seg("a", "b"), _seg("b", "c")]
    assert route_length_outside(segments, graph, DOMAIN) == pytest.approx(5.0)


def test_segment_without_geometry_counts_zero():
    graph = _graph(("a", "b", [(12, 5)]))
    assert route_length_outside([_seg("a", "b"), _seg("b", "c")], graph, DOMAIN) == 0.0
