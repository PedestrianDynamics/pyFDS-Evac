"""The arithmetic of the flow set-up checks, at their boundaries (#836).

``_percentage_count``, ``_check_flow_rate`` and ``_schedule_window`` decide
how many agents a flow adds and whether the deck is accepted. The runs of
``test_flow_schedule_run`` and ``test_spawn_placement`` use values far from
a boundary; here each is called with values chosen so that its operator,
its floor or its tolerance decides the outcome. Every expected value is
worked out in the test, not read from the code.
"""

from __future__ import annotations

import pytest
from shapely.geometry import box

from pyfds_evac.core.agent_params import SpawnConfigError
from pyfds_evac.core.simulation_init import (
    _check_flow_rate,
    _percentage_count,
    _schedule_window,
)


@pytest.mark.parametrize(
    ("percentage", "expected"),
    [(10, 6), (50, 31), (90, 56), (1, 1)],
)
def test_percentage_count_floors_the_share_of_the_capacity(percentage, expected):
    """100 m2 at radius 0.5 m: the capacity estimate is floor(100 / (pi 0.25) / 2)
    = floor(63.66) = 63 agents. The share is floored, not rounded or raised:
    10 % of 63 is 6.3 -> 6, 50 % is 31.5 -> 31 (rounding gives 32), 90 % is
    56.7 -> 56 (rounding gives 57). 1 % is 0.63, which still places one."""
    params = {"radius": 0.5, "percentage": percentage}
    assert _percentage_count(params, box(0, 0, 10, 10)) == expected


def test_percentage_count_places_at_least_one_agent():
    """1 m2 at radius 0.5 m: capacity max(1, floor(1.27 / 2)) = 1; 50 % of 1
    is 0.5, floored to 0 and raised to 1."""
    params = {"radius": 0.5, "percentage": 50}
    assert _percentage_count(params, box(0, 0, 1, 1)) == 1


def test_a_flow_rate_equal_to_the_capacity_is_accepted():
    """4 agents over 2 s is exactly 2 agents/s, the capacity of 2: not above it."""
    _check_flow_rate("d", 4, 2.0, 2)


def test_a_flow_rate_above_the_capacity_is_refused():
    """5 agents over 2 s is 2.5 agents/s against a capacity of 2."""
    with pytest.raises(
        SpawnConfigError,
        match=r"flow rate of 2\.5 agents/s exceeds area capacity of 2 agents",
    ):
        _check_flow_rate("d", 5, 2.0, 2)


def test_a_window_of_exactly_one_step_per_agent_is_accepted():
    """4 agents at one per 0.25 s need 1 s (exact in binary): [0, 1] holds them."""
    entry = {"flow_start_time": 0.0, "flow_end_time": 1.0, "number": 4}
    assert _schedule_window(entry, "d", 0.25) == (0.0, 1.0)


def test_a_window_short_by_rounding_is_accepted():
    """3 agents at one per 0.1 s need 3 * 0.1 = 0.30000000000000004 s in
    floating point, while the window [0, 0.3] is exactly 0.3 s long; the
    1e-9 s tolerance accepts it."""
    entry = {"flow_start_time": 0.0, "flow_end_time": 0.3, "number": 3}
    assert _schedule_window(entry, "d", 0.1) == (0.0, 0.3)


def test_a_window_short_by_more_than_the_tolerance_is_refused():
    """The same window 1e-7 s shorter is a real shortfall, far above 1e-9 s."""
    entry = {"flow_start_time": 0.0, "flow_end_time": 0.3 - 1e-7, "number": 3}
    with pytest.raises(SpawnConfigError, match="too short for 3 agents"):
        _schedule_window(entry, "d", 0.1)
