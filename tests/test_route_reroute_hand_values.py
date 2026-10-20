"""Hand values for the reroute schedule and the evaluation guards (#816).

``should_reevaluate`` is exact arithmetic on binary-representable times:
an agent evaluates at its offset, then every ``interval`` after its last
evaluation, and an interval of zero or less turns rerouting off. Boundary
values are exactly reached (0.5, 1.0, 1.5 are exact in binary).
"""

from __future__ import annotations

import pytest

from pyfds_evac.core.route_graph import AgentRouteState, should_reevaluate


def _state(last: float, offset: float = 0.0) -> AgentRouteState:
    return AgentRouteState(last_eval_time_s=last, eval_offset_s=offset)


class TestShouldReevaluate:
    def test_interval_exactly_elapsed_reevaluates(self):
        # 1.0 + 0.5 = 1.5 exactly.
        assert should_reevaluate(1.5, _state(last=1.0), 0.5) is True

    def test_just_short_of_the_interval_waits(self):
        assert should_reevaluate(1.4375, _state(last=1.0), 0.5) is False

    def test_offset_exactly_reached_evaluates_the_first_time(self):
        state = _state(last=float("-inf"), offset=0.75)
        assert should_reevaluate(0.75, state, 0.5) is True

    def test_before_the_offset_waits(self):
        state = _state(last=float("-inf"), offset=0.75)
        assert should_reevaluate(0.5, state, 0.5) is False

    def test_first_evaluation_ignores_the_interval(self):
        # Never evaluated: the offset alone decides, not offset + interval.
        state = _state(last=float("-inf"), offset=0.25)
        assert should_reevaluate(0.25, state, 100.0) is True

    @pytest.mark.parametrize("last", [float("-inf"), 0.0, 1.0])
    def test_zero_interval_never_reevaluates(self, last):
        state = _state(last=last, offset=0.0)
        assert should_reevaluate(5.0, state, 0.0) is False

    def test_negative_interval_never_reevaluates(self):
        assert should_reevaluate(5.0, _state(last=0.0), -1.0) is False
