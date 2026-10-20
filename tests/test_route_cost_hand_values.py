"""Hand-computed values of the route cost measurements (#816).

Each test fixes one measured quantity of ``route_graph`` to a number that
can be checked on paper: the optical depth tau = K_ave * L, the length
weighting of the extinction mean, the time an agent reaches a point, the
FED taken over a walk and the speed the router assumes in smoke. Routing
does not compute a visibility distance here; tau is the integral of the
extinction along the walked route.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from shapely.geometry import Polygon

from pyfds_evac.core.route_graph import (
    RouteCostConfig,
    StageGraph,
    _arrival_time,
    _cap_at_fds_end,
    _dose,
    _fds_end,
    _foresight_clock,
    _ForesightClock,
    _leg_travel_time,
    _length_weighted_mean,
    evaluate_route,
    evaluate_segment,
    integrated_extinction_along_polyline,
)
from pyfds_evac.core.smoke_speed import (
    ConstantExtinctionField,
    SmokeSpeedConfig,
    SmokeSpeedModel,
)


def _box(cx: float, cy: float, half: float = 1.0) -> Polygon:
    return Polygon(
        [
            (cx - half, cy - half),
            (cx + half, cy - half),
            (cx + half, cy + half),
            (cx - half, cy + half),
        ]
    )


def _corridor(length_m: float) -> StageGraph:
    """D0 (0, 0) -> E0 (length_m, 0), a single edge."""
    return StageGraph.from_scenario(
        {"E0": {"polygon": _box(length_m, 0), "stage_type": "exit"}},
        [{"from": "D0", "to": "E0"}],
        {"D0": {"coordinates": list(_box(0, 0).exterior.coords)}},
    )


def _measure(graph, k, config=None, current_fed=0.0):
    return evaluate_route(
        graph,
        ["D0", "E0"],
        0.0,
        current_fed,
        ConstantExtinctionField(k),
        None,
        config or RouteCostConfig(),
    )


class _Step:
    """K = 1 on the line y = 0, none elsewhere."""

    def sample_extinction(self, time_s, x, y):
        return 1.0 if y == 0.0 else 0.0


class _FedFrom:
    """0.6 FED/min from *t_on* on, none before."""

    def __init__(self, t_on):
        self.t_on = t_on

    def sample_fed_rate(self, time_s, x, y):
        return 0.6 if time_s >= self.t_on else 0.0


# ── optical depth and the extinction mean ────────────────────────────────


def test_uniform_k_over_12_m_gives_tau_at_tau_max():
    """K = 0.5 /m over 12 m is tau = 6.0, the shipped tau_max, to the bit."""
    rc = _measure(_corridor(12.0), 0.5)
    assert rc.path_length_m == 12.0
    assert rc.k_ave_route == 0.5
    assert rc.tau_route == 6.0
    assert rc.tau_route == RouteCostConfig().tau_max


def test_tau_is_k_ave_times_length_not_k_alone():
    assert _measure(_corridor(20.0), 0.3).tau_route == pytest.approx(
        0.3 * 20.0, rel=1e-12
    )


def test_length_weighted_mean_of_10_m_at_1_and_30_m_at_0_is_a_quarter():
    """Unweighted the same two segment means give 0.5."""
    assert _length_weighted_mean([(1.0, 10.0), (0.0, 30.0)], []) == 0.25


def test_length_weighted_mean_falls_back_to_the_degenerate_samples():
    assert _length_weighted_mean([], [0.2, 0.4]) == pytest.approx(0.3, rel=1e-12)
    assert _length_weighted_mean([], []) == 0.0
    assert _length_weighted_mean([(0.7, 5.0)], [9.0]) == 0.7


def test_polyline_mean_weights_each_segment_by_its_length():
    """10 m at K = 1 (both ends), then 30 m from K = 1 to K = 0.

    With one sample per end the second segment's mean is 0.5, so the
    polyline mean is (10 x 1 + 30 x 0.5) / 40 = 0.625; unweighted it is 0.75.
    """
    waypoints = [(0.0, 0.0), (10.0, 0.0), (10.0, 30.0)]
    k = integrated_extinction_along_polyline(waypoints, 0.0, _Step(), step_m=100.0)
    assert k == pytest.approx(0.625, rel=1e-12)


# ── when the agent reaches a point ───────────────────────────────────────


@pytest.mark.parametrize(
    ("horizon_s", "anticipate", "expected"),
    [
        (math.inf, True, 15.0),  # 13 m at 1.3 m/s is 10 s after t = 5 s
        (10.0, True, 15.0),  # a horizon of exactly that walk caps nothing
        (6.0, True, 11.0),  # a shorter horizon caps the foresight at 6 s
        (math.inf, False, 5.0),  # without anticipation the decision time
    ],
)
def test_arrival_time_is_walk_over_speed_capped_by_the_horizon(
    horizon_s, anticipate, expected
):
    config = RouteCostConfig(
        base_speed_m_per_s=1.3,
        foresight_horizon_s=horizon_s,
        anticipate=anticipate,
    )
    assert _arrival_time(5.0, 13.0, config) == pytest.approx(expected, rel=1e-12)


def test_foresight_clock_adds_the_walked_offset_of_a_piece():
    """t0 = 2 s at 2 m/s: 4 m on is 4 s; a piece starting 6 m on, 7 s."""
    clock = _ForesightClock(2.0, 2.0, 100.0, 0.0, math.inf)
    assert clock.at(4.0) == 4.0
    assert clock.shifted(6.0).at(4.0) == 7.0
    assert clock.shifted(6.0).shifted(2.0).at(0.0) == 6.0  # 8 m on


def test_foresight_clock_stops_at_the_horizon_and_the_last_frame():
    config = RouteCostConfig(base_speed_m_per_s=2.0, foresight_horizon_s=3.0)
    horizon = _foresight_clock(2.0, 0.0, config, math.inf, None)
    assert horizon.at(100.0) == 3.0
    ended = _foresight_clock(2.0, 0.0, config, 2.5, None)
    assert ended.at(100.0) == 2.5
    d = np.array([0.0, 1.0, 100.0])
    assert ended.at_many(d).tolist() == [ended.at(x) for x in d]
    assert ended.at_many(d).tolist() == [2.0, 2.5, 2.5]


def test_foresight_is_held_at_the_last_frame_but_not_before_the_decision():
    assert _cap_at_fds_end(5.0, 12.0, 10.0, None) == 10.0
    assert _cap_at_fds_end(5.0, 8.0, 10.0, None) == 8.0
    assert _cap_at_fds_end(5.0, 10.0, 10.0, None) == 10.0
    # A decision past the last frame keeps its own time and what lies ahead.
    assert _cap_at_fds_end(20.0, 25.0, 10.0, None) == 20.0
    assert _cap_at_fds_end(20.0, 15.0, 10.0, None) == 15.0


def test_fds_end_is_the_earliest_last_frame_of_the_samplers():
    class Ends:
        def __init__(self, end_time_s):
            self.end_time_s = end_time_s

    late, early, synthetic = Ends(30.0), Ends(20.0), ConstantExtinctionField(0.0)
    assert _fds_end(synthetic, None) == (math.inf, None)
    assert _fds_end(late, synthetic, early) == (20.0, early)
    assert _fds_end(early, late) == (20.0, early)


# ── the dose taken over a walk ───────────────────────────────────────────


def test_a_rate_of_0_6_per_min_over_100_s_adds_one_fed():
    assert _dose(0.6, 100.0) == pytest.approx(1.0, rel=1e-12)
    assert _dose(0.0, math.inf) == 0.0


def test_segment_dose_is_the_rate_at_the_arrival_time_over_the_walk():
    """10 m at 0.1 m/s is 100 s; 0.6 /min from t = 50 s on adds 1.0.

    Reached at 60 s the rate is on; read at the decision time (0 s) it is off.
    """
    graph = _corridor(10.0)
    config = RouteCostConfig(base_speed_m_per_s=0.1)
    field = ConstantExtinctionField(0.0)
    fed = _FedFrom(50.0)
    arrived = evaluate_segment(
        graph, "D0", "E0", 0.0, field, fed, config, arrival_time_s=60.0
    )
    assert arrived.travel_time_s == pytest.approx(100.0, rel=1e-12)
    assert arrived.fed_growth == pytest.approx(1.0, rel=1e-12)
    assert arrived.arrival_time_s == 60.0
    decided = evaluate_segment(graph, "D0", "E0", 0.0, field, fed, config)
    assert decided.arrival_time_s == 0.0
    assert decided.fed_growth == 0.0


# ── the speed the router assumes in smoke ────────────────────────────────


def test_router_speed_uses_the_smoke_speed_factor_at_the_mean_k():
    """K = 2 /m: Lund factor 1 - 0.057 x 2 / 0.706, as the walking model uses.

    The router reuses the smoke-speed coefficients; the same K through
    ``SmokeSpeedModel`` gives the same factor, and 10 m is walked at
    1.3 m/s times it.
    """
    factor = 1.0 - 0.057 * 2.0 / 0.706
    assert factor == pytest.approx(0.8385269, rel=1e-6)
    seg = evaluate_segment(
        _corridor(10.0),
        "D0",
        "E0",
        0.0,
        ConstantExtinctionField(2.0),
        None,
        RouteCostConfig(),
    )
    _, model_factor = SmokeSpeedModel(
        ConstantExtinctionField(2.0), SmokeSpeedConfig()
    ).sample(0.0, 0.0, 0.0)
    assert model_factor == pytest.approx(factor, rel=1e-12)
    assert seg.speed_factor == pytest.approx(factor, rel=1e-12)
    assert seg.travel_time_s == pytest.approx(10.0 / (1.3 * factor), rel=1e-12)
    assert _leg_travel_time(10.0, 2.0, RouteCostConfig()) == pytest.approx(
        (factor, 10.0 / (1.3 * factor)), rel=1e-12
    )


def test_router_speed_is_clamped_at_the_smoke_speed_minimum():
    sf, travel = _leg_travel_time(10.0, 20.0, RouteCostConfig())
    assert sf == 0.1
    assert travel == pytest.approx(10.0 / (1.3 * 0.1), rel=1e-12)


def test_router_coefficients_are_the_smoke_speed_ones():
    config, model = RouteCostConfig(), SmokeSpeedConfig()
    assert (config.alpha, config.beta, config.min_speed_factor) == (
        model.alpha,
        model.beta,
        model.min_speed_factor,
    )


# ── thresholds hit exactly ───────────────────────────────────────────────


def test_a_segment_at_the_visibility_threshold_is_not_visible():
    """K = 0.5 /m on a 0.5 threshold: visible needs K strictly below it."""
    graph = _corridor(10.0)
    config = RouteCostConfig(visibility_extinction_threshold=0.5)

    def visible(k):
        field = ConstantExtinctionField(k)
        return evaluate_segment(graph, "D0", "E0", 0.0, field, None, config).visible

    assert visible(0.5) is False
    assert visible(0.4999) is True


def test_a_route_at_the_fed_threshold_is_not_in_violation():
    """FED exactly 1 is the limit, not over it; the violation is strict."""
    graph = _corridor(10.0)
    config = RouteCostConfig(fed_rejection_threshold=1.0)
    at_limit = _measure(graph, 0.0, config, current_fed=1.0)
    over = _measure(graph, 0.0, config, current_fed=1.0 + 1e-9)
    assert at_limit.fed_max_route == 1.0
    assert "fed" not in at_limit.violation_kinds
    assert "fed" in over.violation_kinds
