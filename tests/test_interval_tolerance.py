"""Tests for cadence check interval tolerance (#927).

Cadence checks of the form `t - last >= interval` must absorb float
rounding of simulation time advancing in steps of dt.
"""

from __future__ import annotations

import pytest

from pyfds_evac.core.deadlock import _TIME_EPS_S
from pyfds_evac.core.plan_view import FrameRecorder
from pyfds_evac.core.route_graph import AgentRouteState, should_reevaluate
from pyfds_evac.core.time_step import TIME_EPS_S


def test_time_eps_constant():
    assert TIME_EPS_S == 1e-9
    assert _TIME_EPS_S == TIME_EPS_S


@pytest.mark.parametrize(
    ("dt", "interval", "total_s", "expected_count"),
    [
        (0.01, 0.1, 300.0, 3000),
        (0.01, 0.2, 300.0, 1500),
        (0.05, 0.1, 300.0, 3000),
        (0.01, 0.5, 300.0, 600),
        (0.05, 0.5, 300.0, 600),
    ],
)
def test_should_reevaluate_float_cadence(dt, interval, total_s, expected_count):
    """Float stepping with dt must not miss steps when t is a multiple of dt."""
    state = AgentRouteState(last_eval_time_s=0.0, eval_offset_s=0.0)
    t = 0.0
    eval_count = 0
    steps = int(round(total_s / dt))
    for _ in range(steps):
        t += dt
        if should_reevaluate(t, state, interval):
            eval_count += 1
            state = AgentRouteState(last_eval_time_s=t, eval_offset_s=0.0)
    assert eval_count == expected_count


def test_frame_recorder_due_float_cadence():
    """FrameRecorder._due by simulated time does not miss steps at dt=0.01 and min_sim_s=0.1."""

    class DummySim:
        def __init__(self):
            self._t = 0.0

        def elapsed_time(self):
            return self._t

    sim = DummySim()
    # High max_hz wall-clock limit so only simulated time governs.
    recorder = FrameRecorder(lambda e: None, max_hz=1e-9, min_sim_s=0.1)
    recorder._last = 0.0
    recorder._last_sim = 0.0

    due_count = 0
    for _ in range(300):
        sim._t += 0.01
        if recorder._due(now=0.0, simulation=sim):
            due_count += 1
            recorder._last_sim = sim._t
    assert due_count == 30
