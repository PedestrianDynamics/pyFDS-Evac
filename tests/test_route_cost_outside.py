"""length_outside_m: route length outside the FDS coverage (#431)."""

import contextlib
import io
import json
from types import SimpleNamespace

import pytest
from shapely.geometry import box
from test_fds_domain import _iso_opts, _iso_scenario
from test_run_outcome import ENOUGH_S, SEED, _scenario

from pyfds_evac.core.fds_coverage import route_length_outside
from pyfds_evac.core.route_graph import (
    RerouteConfig,
    RouteCostConfig,
    StageEdge,
    StageGraph,
)
from pyfds_evac.core.run_config import build_run_kwargs
from pyfds_evac.core.scenario import load_scenario, run_scenario

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


def _iso_rows(tmp_path, rival):
    """Route-cost rows and metrics of the coupled ISO run (5.5 m outside).

    With *rival*, a second exit lies wholly outside the mesh and the single
    exit journey makes the spawn area rank it as a rival, on a graph that
    holds an edge the allocated stage graph does not.
    """
    config_path = _iso_scenario(tmp_path)
    config = json.loads(config_path.read_text())
    if rival:
        config["exits"]["E_far"] = {
            "type": "polygon",
            "coordinates": [[58, -0.5], [59, -0.5], [59, 0.5], [58, 0.5], [58, -0.5]],
            "enable_throughput_throttling": False,
            "max_throughput": 0,
        }
        config["journeys"] = [{"id": "j", "stages": ["jps-distributions_0", "E_end"]}]
        config["transitions"] = [
            {"from": "jps-distributions_0", "to": "E_end", "journey_id": "j"}
        ]
        config_path.write_text(json.dumps(config))
    scenario = load_scenario(str(config_path))
    kwargs = build_run_kwargs(scenario, _iso_opts(enable_rerouting=True))
    kwargs["collect_route_cost_history"] = True
    result = run_scenario(scenario, **kwargs)
    try:
        return list(result.route_cost_history), result.metrics
    finally:
        result.cleanup()


def test_rows_with_fds_carry_the_length_outside(tmp_path):
    rows, metrics = _iso_rows(tmp_path, rival=False)
    assert rows
    edge = metrics["fds_coverage"]["edges_outside_m"]["jps-distributions_0 -> E_end"]
    assert edge == pytest.approx(5.5)
    assert [row["length_outside_m"] for row in rows] == [pytest.approx(edge)] * len(
        rows
    )


def test_rival_route_is_measured_on_the_rival_graph(tmp_path):
    rows, metrics = _iso_rows(tmp_path, rival=True)
    outside = {row["path"]: row["length_outside_m"] for row in rows}
    assert outside["jps-distributions_0 > E_end"] == pytest.approx(5.5)
    assert outside["jps-distributions_0 > E_far"] == pytest.approx(3.0)
    # The rival edge exists only on the rival graph, so the coverage report
    # of the allocated stage graph never measured it.
    assert (
        "jps-distributions_0 -> E_far" not in metrics["fds_coverage"]["edges_outside_m"]
    )
