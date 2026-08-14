"""The gate model always leaves the agent somewhere to go.

`rank_routes` guarantees that at least one route comes back un-rejected: when
every route fails, it un-rejects the least-bad one so the caller always has a
target. `_apply_exit_death` then drops the exits this agent has already found
impassable -- and that filter can remove exactly the route the guarantee was
resting on. If the remaining list is handed back untouched, every entry in it is
rejected, `evaluate_and_reroute` reads that as "no route", and the agent skips
the tick still walking toward an exit it has condemned.

So the invariant these tests hold is narrow and load-bearing: whatever
`_apply_exit_death` returns, its head is a route the agent may take.

The rest of the gate model is not covered here. Its sight criterion saturates in
both reference fires -- t_junction/fire_2MW_PVC has median route K of 10.7 /m,
i.e. Jin sight of 0.28 m -- so the fallback exercised below is what decides
almost every switch in practice, which is why it is the part pinned first.
"""

from __future__ import annotations

from dataclasses import replace

from pyfds_evac.core.route_graph import (
    AgentRouteState,
    RouteCost,
    RouteCostConfig,
    _apply_exit_death,
)


def _route(exit_id: str, *, rejected: bool, k_max: float, travel_s: float) -> RouteCost:
    return RouteCost(
        exit_id=exit_id,
        path=["spawn", exit_id],
        path_length_m=travel_s,
        k_ave_route=k_max,
        travel_time_s=travel_s,
        fed_max_route=0.0,
        composite_cost=travel_s,
        rejected=rejected,
        rejection_reason=f"sight 1.0 m < {travel_s:.1f} m" if rejected else None,
        k_max_route=k_max,
        feasible=not rejected,
        segments=[],
    )


def _config() -> RouteCostConfig:
    return RouteCostConfig(cost_model="gate")


class TestHeadIsAlwaysUsable:
    def test_survivors_are_kept_when_one_is_passable(self):
        state = AgentRouteState(current_exit="A", current_path=[])
        ranked = [
            _route("A", rejected=False, k_max=0.1, travel_s=10.0),
            _route("B", rejected=True, k_max=5.0, travel_s=20.0),
        ]
        out = _apply_exit_death(ranked, state, _config())

        assert state.dead_exits == {"B"}
        assert [rc.exit_id for rc in out] == ["A"]
        assert not out[0].rejected

    def test_all_survivors_rejected_still_yields_a_target(self):
        """The case that used to stall a tick.

        Not every rejection is a death: `rank_routes` also refuses a route whose
        signs are all unreadable, which leaves ``rejected`` set but ``feasible``
        untouched, so the exit survives. B died on an earlier tick, and once its
        route is filtered out the only survivor is one of those -- rejected, but
        alive. Handing that back untouched made `evaluate_and_reroute` read "no
        route" and skip the tick.
        """
        state = AgentRouteState(current_exit="A", current_path=[])
        state.dead_exits.add("B")
        unreadable = replace(
            _route("A", rejected=True, k_max=0.5, travel_s=10.0),
            rejection_reason="all segments non-visible",
            feasible=True,
        )
        ranked = [
            replace(
                _route("B", rejected=False, k_max=0.1, travel_s=20.0),
                rejection_reason="fallback: no route passes (sight 1.0 m < 20.0 m)",
            ),
            unreadable,
        ]
        out = _apply_exit_death(ranked, state, _config())

        assert [rc.exit_id for rc in out] == ["A"]
        assert not out[0].rejected
        assert state.dead_exits == {"B"}

    def test_every_exit_dead_falls_back_to_the_least_smoky(self):
        state = AgentRouteState(current_exit=None, current_path=[])
        ranked = [
            _route("A", rejected=True, k_max=5.0, travel_s=10.0),
            _route("B", rejected=True, k_max=1.0, travel_s=40.0),
        ]
        out = _apply_exit_death(ranked, state, _config())

        assert state.dead_exits == {"A", "B"}
        assert out[0].exit_id == "B"  # farther, but its worst stretch is milder
        assert not out[0].rejected
        assert "every exit dead" in (out[0].rejection_reason or "")

    def test_a_fallback_route_never_kills_its_own_exit(self):
        """rank_routes' un-rejection is not evidence the exit is passable."""
        state = AgentRouteState(current_exit="A", current_path=[])
        ranked = [
            replace(
                _route("A", rejected=False, k_max=5.0, travel_s=10.0),
                rejection_reason="fallback: no route passes (sight 1.0 m < 10.0 m)",
            ),
        ]
        _apply_exit_death(ranked, state, _config())

        assert state.dead_exits == set()
