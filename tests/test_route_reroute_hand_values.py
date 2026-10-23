"""Hand values for the reroute schedule and the evaluation guards (#816).

``should_reevaluate`` is exact arithmetic on binary-representable times:
an agent evaluates at its offset, then every ``interval`` after its last
evaluation, and an interval of zero or less turns rerouting off. Boundary
values are exactly reached (0.5, 1.0, 1.5 are exact in binary).
"""

from __future__ import annotations

import math

import pytest
import test_rerouting_golden as golden

from pyfds_evac.core.route_graph import (
    AgentRouteState,
    RerouteConfig,
    evaluate_and_reroute,
    should_reevaluate,
)
from pyfds_evac.core.smoke_speed import ConstantExtinctionField


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


class TestEvaluateAndReroute:
    """The guards of ``evaluate_and_reroute`` on stars of exits.

    ``golden._star`` puts the spawn at the origin and each exit at the given
    distance; with ``base_speed_m_per_s = 1`` a route of L metres takes L s.
    """

    @staticmethod
    def _evaluate(
        graph, config, extinction, current_exit, origin="spawn", target="east"
    ):
        wait_info = golden._wait_info(graph, origin, target)
        route_state = AgentRouteState(current_exit=current_exit)
        switch = evaluate_and_reroute(
            agent_id=1,
            wait_info=wait_info,
            route_state=route_state,
            graph=graph,
            current_time_s=5.0,
            current_fed=0.0,
            extinction_sampler=extinction,
            fed_rate_sampler=None,
            config=RerouteConfig(cost_config=config),
        )
        return switch, route_state

    def test_a_chosen_exit_stamps_the_evaluation(self):
        """West at 10 m takes 10 s, east at 30 m takes 30 s. 10 < 0.9 x 30,
        so the agent leaves east for west, and the evaluation is stamped."""
        graph = golden._star({"west": 10.0, "east": 30.0})
        switch, state = self._evaluate(
            graph, golden._gate(), ConstantExtinctionField(0.0), "east"
        )
        assert (switch.old_exit, switch.new_exit) == ("east", "west")
        assert state.current_exit == "west"
        assert state.last_eval_time_s == 5.0

    def test_no_reachable_exit_stamps_and_decides_nothing(self):
        """D0 leads to C0 and no exit: nothing is ranked. Without a cognitive
        map there is nothing to explore, so no switch; the stamp still holds
        the agent back for the interval."""
        graph = golden._dead_end()
        switch, state = self._evaluate(
            graph,
            golden._gate(),
            ConstantExtinctionField(0.0),
            None,
            origin="D0",
            target="C0",
        )
        assert switch is None
        assert state.last_eval_time_s == 5.0

    def test_a_refused_route_the_scan_lands_on_is_not_taken_or_stamped(self):
        """Arms west 10, east 30, north 50 m at K = 0.75, 0.3, 0.12 /m:
        tau = 7.5, 9.0 and 6.0, with tau_max = 6.0. West and east are
        refused, north is feasible. The agent is on east. With the deadband
        margin 6.0 x 0.5 = 3.0, north is cleaner than east by exactly 3.0,
        not clearly, and slower, so the anchor refuses it. West is cleaner
        by 1.5, inside the margin, and 10 < 0.9 x 30 s, so the scan lands on
        west. West is refused: no switch, and the evaluation is not stamped,
        so the agent re-evaluates at the next check."""
        graph = golden._star3()
        switch, state = self._evaluate(
            graph,
            golden._gate(tau_deadband=0.5),
            golden.ArmField({"west": 0.75, "east": 0.3, "north": 0.12}),
            "east",
        )
        assert switch is None
        assert state.current_exit == "east"
        assert state.current_path == []
        assert state.last_eval_time_s == -math.inf
