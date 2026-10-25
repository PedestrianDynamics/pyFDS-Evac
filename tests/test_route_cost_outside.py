"""length_outside_m: route length outside the FDS coverage (#431)."""

import contextlib
import io
from types import SimpleNamespace

import pytest
from shapely.geometry import box
from test_run_outcome import ENOUGH_S, SEED, _scenario

from pyfds_evac.core.fds_coverage import route_length_outside
from pyfds_evac.core.route_graph import (
    RerouteConfig,
    RouteCostConfig,
    StageEdge,
    StageGraph,
)
from pyfds_evac.core.scenario import run_scenario

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


def test_rows_without_fds_have_an_empty_length_outside():
    scenario = _scenario(ENOUGH_S)
    with contextlib.redirect_stdout(io.StringIO()):
        result = run_scenario(
            scenario,
            seed=SEED,
            reroute_config=RerouteConfig(
                reevaluation_interval_s=1.0, cost_config=RouteCostConfig(w_queue=1.0)
            ),
            collect_route_cost_history=True,
        )
    try:
        rows = list(result.route_cost_history or [])
    finally:
        result.cleanup()
    assert rows, "no route was priced"
    assert {row["length_outside_m"] for row in rows} == {""}
