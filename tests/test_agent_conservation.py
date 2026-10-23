"""Every configured agent is accounted for at the end of a run (#836).

A table of small runs on the synthetic room of ``test_run_outcome``, each
with the counts worked out from the deck and the 1.3 m/s walking speed. The
exit is 5.8 m or more from the spawn area (x up to 4 m, exit at x = 9.8 m),
so within 4 s nobody leaves, and within 60 s everybody does.

``total_agents`` counts the agents that entered; the evacuated ones are
those that entered and left, so ``total = evacuated + remaining``, and with
the flow agents that never entered, ``total + not_spawned`` is the number
the deck configured.
"""

from __future__ import annotations

import pytest
from test_flow_schedule_run import _run, _scheduled, _window, _without_journeys
from test_run_outcome import ENOUGH_S, NUM_AGENTS, TOO_SHORT_S, _scenario

FLOW = {
    "use_flow_spawning": True,
    "flow_start_time": 0,
    "flow_end_time": 6,
}


def _flow(max_time_s, **extra):
    return _scenario(max_time_s, **{**FLOW, **extra})


# build, configured, evacuated, remaining, not_spawned
CASES = {
    "by-number-completed": (lambda: _scenario(ENOUGH_S), NUM_AGENTS, 6, 0, 0),
    "by-number-time-limit": (lambda: _scenario(TOO_SHORT_S), NUM_AGENTS, 0, 6, 0),
    "flow-completed": (lambda: _flow(ENOUGH_S), NUM_AGENTS, 6, 0, 0),
    "flow-without-journeys": (
        lambda: _without_journeys(_flow(ENOUGH_S)),
        NUM_AGENTS,
        6,
        0,
        0,
    ),
    # One agent every 10 s, so only the one of t = 0 is in at 1 s.
    "flow-time-limit": (
        lambda: _flow(TOO_SHORT_S, flow_end_time=60),
        NUM_AGENTS,
        0,
        1,
        5,
    ),
    # 4 agents at t = 0 and 6 over [1, 5] s.
    "initial-and-scheduled-completed": (
        lambda: _scheduled([_window(1, 5, 6)], initial=4),
        10,
        10,
        0,
        0,
    ),
    # 10 agents over [2, 12] s: the ones of 2 s and 3 s are in at 4 s.
    "schedule-time-limit": (
        lambda: _scheduled([_window(2, 12, 10)], max_time_s=4.0),
        10,
        0,
        2,
        8,
    ),
}


@pytest.mark.parametrize("case", CASES, ids=list(CASES))
def test_every_configured_agent_is_accounted_for(case):
    build, configured, evacuated, remaining, not_spawned = CASES[case]
    result = _run(build())
    try:
        assert (
            result.agents_evacuated,
            result.agents_remaining,
            result.agents_not_spawned,
        ) == (evacuated, remaining, not_spawned)
        assert result.total_agents == result.agents_evacuated + result.agents_remaining
        assert result.total_agents + result.agents_not_spawned == configured
    finally:
        result.cleanup()
