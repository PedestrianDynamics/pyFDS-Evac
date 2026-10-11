"""A run ends once it is empty and no flow window can still spawn (#742).

Four agents of radius 0.2 m fill a 1.2 m square and stand for 2 s; a flow
of five into the square, open from 0 to 1 s, finds no free position. The
standing agents then walk out. With nothing left to enter, the run stops
when the last of them leaves, long before its 60 s limit, and is reported
as incomplete with ``end_reason`` ``"flows_closed"``.
"""

from __future__ import annotations

import pytest
from shapely.geometry import box
from test_flow_spawn_spacing import D1, _run_recording_gaps, _scenario_with_flow

LIMIT_S = 60.0


def test_a_run_ends_when_it_empties_after_its_flow_windows_closed(monkeypatch):
    scenario = _scenario_with_flow(
        "CollisionFreeSpeedModel",
        box(1.0, 1.0, 2.2, 2.2),
        (4, 0.2),
        (5, 0.2),
        1.0,
        LIMIT_S,
        premovement_s=2.0,
    )
    # Seed 1 leaves one standing agent at the exit edge until the limit.
    _, result, out = _run_recording_gaps(monkeypatch, scenario, 2)
    assert result.evacuation_time < LIMIT_S
    assert result.agents_remaining == 0
    assert result.agents_not_spawned == 5
    assert result.success is False
    assert result.status == "incomplete"
    assert result.end_reason == "flows_closed"
    assert any(
        line.startswith(f"Flow spawning: '{D1}' found no free position")
        and line.endswith("5 of its 5 agents did not enter")
        for line in out.splitlines()
    )


@pytest.mark.parametrize(
    ("counter", "time_s", "can_spawn"),
    [
        (0, 0.0, True),  # the window has not opened yet
        (2, 3.0, True),  # deferring inside the window
        (2, 5.0, True),  # the window closes, inclusive
        (2, 5.01, False),  # the window has closed
        (4, 3.0, False),  # every agent entered
    ],
)
def test_a_source_can_spawn_until_its_window_closes(counter, time_s, can_spawn):
    from pyfds_evac.core.scenario import _flow_can_spawn

    flow = {"start_time": 1.0, "end_time": 5.0}
    assert _flow_can_spawn([flow], [4], [counter], time_s) is can_spawn


def test_any_source_still_open_keeps_the_run_going():
    from pyfds_evac.core.scenario import _flow_can_spawn

    closed = {"start_time": 0.0, "end_time": 1.0}
    later = {"start_time": 10.0, "end_time": 20.0}
    assert _flow_can_spawn([closed, later], [3, 3], [0, 0], 5.0)
    assert not _flow_can_spawn([closed, later], [3, 3], [0, 3], 5.0)
