"""A route leg's FED dose is the mean FED rate along the leg times its walk (#725)."""

import math

import pytest

from pyfds_evac.core.route_graph import (
    RouteCostConfig,
    StageEdge,
    StageGraph,
    StageNode,
    _foresight_clock,
    evaluate_segment,
)
from pyfds_evac.core.smoke_speed import ConstantExtinctionField

CLEAR = ConstantExtinctionField(extinction_per_m=0.0)


class _RateNearStart:
    """6.0 /min for x < 2 m, zero elsewhere: the midpoint of a 0-10 m leg is clean."""

    def sample_fed_rate(self, time_s, x, y):
        return 6.0 if x < 2.0 else 0.0


class _RateAboveY9:
    """1.0 /min for y >= 9 m, zero elsewhere."""

    def sample_fed_rate(self, time_s, x, y):
        return 1.0 if y >= 9.0 else 0.0


class _UniformRate:
    def sample_fed_rate(self, time_s, x, y):
        return 3.0


class _RateFromT5:
    """6.0 /min from t = 5 s on, zero before, everywhere."""

    def sample_fed_rate(self, time_s, x, y):
        return 6.0 if time_s >= 5.0 else 0.0


def _graph(waypoints=None):
    src = StageNode(
        stage_id="A", centroid_x=0.0, centroid_y=0.0, stage_type="distribution"
    )
    tgt = StageNode(stage_id="B", centroid_x=10.0, centroid_y=0.0, stage_type="exit")
    edges = {}
    if waypoints is not None:
        edges = {
            "A": [StageEdge(source="A", target="B", weight=0.0, waypoints=waypoints)]
        }
    return StageGraph(nodes={"A": src, "B": tgt}, edges=edges)


def _leg(graph, fed, config, clock=None):
    return evaluate_segment(
        graph=graph,
        source="A",
        target="B",
        time_s=0.0,
        extinction_sampler=CLEAR,
        fed_rate_sampler=fed,
        config=config,
        clock=clock,
    )


def test_straight_leg_charges_the_mean_rate_not_the_midpoint():
    config = RouteCostConfig(sampling_step_m=1.0)
    seg = _leg(_graph(), _RateNearStart(), config)
    walk_min = seg.travel_time_s / 60.0
    # Midpoint (5, 0) is clean, so the old rule charged nothing.
    assert seg.fed_growth > 0.0
    # Mean rate over the leg is about 6.0 x 2 / 10 = 1.2 /min.
    assert seg.fed_growth == pytest.approx(1.2 * walk_min, rel=0.15)


def test_polyline_leg_charges_the_mean_rate_not_the_midpoint():
    waypoints = [(0.0, 0.0), (0.0, 10.0), (10.0, 10.0), (10.0, 0.0)]
    config = RouteCostConfig(sampling_step_m=1.0)
    seg = _leg(_graph(waypoints), _RateAboveY9(), config)
    walk_min = seg.travel_time_s / 60.0
    # The midpoint (5, 10) reads 1.0 /min; only 12 of the 30 m are at y >= 9.
    assert seg.fed_growth < 0.6 * walk_min
    assert seg.fed_growth == pytest.approx(0.4 * walk_min, rel=0.15)


def test_uniform_rate_gives_the_rate_times_the_walk():
    config = RouteCostConfig(sampling_step_m=1.0)
    seg = _leg(_graph(), _UniformRate(), config)
    assert seg.fed_growth == pytest.approx(3.0 * seg.travel_time_s / 60.0, rel=1e-12)


def test_no_fed_sampler_charges_nothing():
    seg = _leg(_graph(), None, RouteCostConfig(sampling_step_m=1.0))
    assert seg.fed_growth == 0.0


def test_anticipation_reads_each_rate_sample_when_the_agent_gets_there():
    config = RouteCostConfig(sampling_step_m=1.0, anticipate=True)
    clock = _foresight_clock(0.0, 0.0, config, math.inf, None)
    seg = _leg(_graph(), _RateFromT5(), config, clock=clock)
    walk_s = seg.travel_time_s
    # The rate starts at t = 5 s, part-way along the walk; read at the start
    # alone (t = 0) the leg would cost nothing, read at the end all of it.
    share = (walk_s - 5.0) / walk_s
    assert 0.0 < seg.fed_growth < 6.0 * walk_s / 60.0
    assert seg.fed_growth == pytest.approx(6.0 * share * walk_s / 60.0, rel=0.15)
