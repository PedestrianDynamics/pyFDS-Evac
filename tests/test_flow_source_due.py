"""The spawn loop and the position snapshot share one flow-source test (#747).

The spawn loop tries a flow source at the simulated time ``k * dt`` (how
JuPedSim computes ``elapsed_time``) when ``_flow_source_due`` holds. The
snapshot of the positions that attempt reads is taken one step before, at
``(k - 1) * dt + dt``, with the test widened by ``dt / 2``. Whenever the
loop would try a source, the snapshot must have been taken.

In floating point ``(k - 1) * dt + dt`` differs from ``k * dt`` at some
steps: at k = 7 and 10 it is below (0.07, 0.1), at k = 6 and 15 above
(0.06, 0.15). Windows that open or close exactly there need the margin.
"""

from __future__ import annotations

import itertools

import pytest

from pyfds_evac.core.scenario import _flow_source_due, _flow_spawn_due

DT = 0.01
STEPS = 700
# (start, end) on and off the step grid, and opening or closing where the
# snapshot time falls below or above the step time.
WINDOWS = [
    (0.0, 1.0),
    (0.5, 2.5),
    (0.123, 1.777),
    (1.0 / 3.0, 2.0 / 3.0 + 1.0),
    (0.07, 1.07),
    (0.1, 0.15),
    (0.0, 0.06),
]
NUMBERS = [1, 3, 7]


def _due(flow, frequency, number, counter, time_s):
    """The spawn loop's test, written out: agents still to enter, the
    window open (both ends inclusive) and the next spawn reached."""
    next_spawn = flow["start_time"] + counter * frequency
    return (
        counter < number
        and flow["start_time"] <= time_s <= flow["end_time"]
        and time_s >= next_spawn
    )


def _sources():
    for (start, end), number in itertools.product(WINDOWS, NUMBERS):
        flow = {"start_time": start, "end_time": end}
        yield flow, (end - start) / number, number


@pytest.mark.parametrize(("flow", "frequency", "number"), list(_sources()))
def test_the_snapshot_is_taken_whenever_the_loop_tries_a_source(
    flow, frequency, number
):
    tried = 0
    for counter in range(number + 1):
        for k in range(1, STEPS):
            due = _flow_source_due(flow, frequency, number, counter, k * DT)
            assert due is _due(flow, frequency, number, counter, k * DT), (counter, k)
            if not due:
                continue
            tried += 1
            snapshot_time = (k - 1) * DT + DT
            assert _flow_spawn_due(
                [flow], [[frequency, 1]], [number], [counter], snapshot_time, DT
            ), (counter, k)
    assert tried > 0


@pytest.mark.parametrize(
    ("counter", "time_s", "due"),
    [
        (0, 0.49, False),  # before the window
        (0, 0.5, True),  # the window opens
        (1, 0.99, False),  # before the next spawn
        (1, 1.0, True),  # the next spawn
        (1, 2.5, True),  # the window closes, inclusive
        (1, 2.51, False),  # after the window
        (4, 1.5, False),  # every agent entered
    ],
)
def test_a_source_is_due_from_its_next_spawn_to_its_window_end(counter, time_s, due):
    flow = {"start_time": 0.5, "end_time": 2.5}
    assert _flow_source_due(flow, 0.5, 4, counter, time_s) is due
