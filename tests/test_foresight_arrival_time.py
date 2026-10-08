"""Route foresight reads every sample when the agent reaches it (#650).

With ``anticipate`` on, an extinction sample at a point p of a measured route
is read at ``t_dec + min(s(p) / v0, H)``, where ``s(p)`` is the walk from the
agent's position to p: the walk to the next node, then the node legs. Reading
each leg at its start instead made the cost jump when the agent passed a
node, because the first leg starts where the agent stands and was read at the
decision time.

The graph is ``_linear`` of the golden tests: D0 (0, 0) -> C0 (10, 0) -> E0
(20, 0), no routing engine (straight walks), 2 m sampling steps, v0 = 1.3 m/s.
Smoke K = 0.8 /m stands at x >= 11 m from t = 5 s on.
"""

from __future__ import annotations

import math

import pytest
import test_rerouting_golden as golden

from pyfds_evac.core.route_graph import RouteCostConfig, evaluate_route

_GATE = RouteCostConfig(cost_model="gate")
_SMOKE = golden.LateSmoke(k=0.8, x_min=11.0, t_on=5.0)


def _tau(path, position, config=_GATE, time_s=0.0, cache=None):
    return evaluate_route(
        golden._linear(),
        path,
        time_s,
        0.0,
        _SMOKE,
        None,
        config,
        cached_segments=cache,
        agent_position=position,
    ).tau_route


def test_single_leg_reads_each_point_when_it_is_reached():
    """From C0 the samples at 12..20 m are reached after the 5 s onset.

    Samples at 0, 2, ..., 10 m from C0; those at 8 and 10 m (x 18, 20) are
    reached at 6.15 s and 7.69 s, x >= 11 holds from 2 m on but the onset
    only from 6.5 m on: tau = 0.8 x 2/6 x 10 m. Read at the decision time
    the whole leg was clear, tau 0.
    """
    assert _tau(["C0", "E0"], (10.0, 0.0)) == pytest.approx(0.8 * 2 / 6 * 10, 1e-12)


def test_tau_is_continuous_across_a_node():
    """An agent 0.1 m before and 0.1 m past C0 sees nearly the same route.

    Reading each leg at its start, the route jumped from 6.67 to 0 here.
    """
    before = _tau(["D0", "C0", "E0"], (9.9, 0.0))
    after = _tau(["C0", "E0"], (10.1, 0.0))
    assert before == pytest.approx(2.6666666666666665, rel=1e-12)
    assert after == pytest.approx(2.64, rel=1e-12)
    assert abs(after - before) <= _SMOKE.k * 0.2


def test_without_anticipation_every_sample_is_at_the_decision_time():
    config = RouteCostConfig(cost_model="gate", anticipate=False)
    assert _tau(["C0", "E0"], (10.0, 0.0), config) == 0.0


def test_horizon_caps_every_sample():
    config = RouteCostConfig(cost_model="gate", foresight_horizon_s=3.0)
    assert _tau(["C0", "E0"], (10.0, 0.0), config) == 0.0


def test_without_a_position_the_walk_counts_from_the_first_node():
    assert _tau(["D0", "C0", "E0"], None) == pytest.approx(6.666666666666666, 1e-12)


def test_cache_is_not_shared_across_decision_times_under_a_horizon():
    """A cache passed across decision times stays exact.

    A run clears its cache at every decision time, but the API accepts one
    across several. Decided at 2.1 s and 2.3 s with H = 3 s, the leg
    C0 -> E0 starts in the same whole second (5.1 s, 5.3 s), and every
    sample is capped at 5.1 s and 5.3 s: smoke switched on at 5.2 s lies
    within the second foresight only. A shared entry would hand it the
    first agent's clear leg.
    """
    config = RouteCostConfig(cost_model="gate", foresight_horizon_s=3.0)
    smoke = golden.LateSmoke(k=0.8, x_min=11.0, t_on=5.2)

    def tau(time_s, cache):
        return evaluate_route(
            golden._linear(),
            ["D0", "C0", "E0"],
            time_s,
            0.0,
            smoke,
            None,
            config,
            cached_segments=cache,
        ).tau_route

    shared: dict = {}
    assert tau(2.1, shared) == 0.0
    assert tau(2.3, shared) == tau(2.3, {}) > 0.0


def test_fallback_deck_tau_does_not_collapse_past_a_node():
    """tj_full_gate_fallback with anticipation, the 7-9 s flip of #650.

    Both arms fill and never clear, so no route's optical depth may drop from
    above 1 to below 0.1 between two evaluations of one agent. Reading the
    first leg at the decision time, route A fell from 72 to 0 when agents
    passed the checkpoint, and they switched to it and back.
    """
    from dataclasses import replace

    deck = replace(golden.DECKS["tj_full_gate_fallback"], anticipate=True)
    rows: list[dict] = []
    real_run = golden.run_scenario

    def keep(*args, **kwargs):
        result = real_run(*args, **kwargs)
        rows.extend(result.route_cost_history or [])
        return result

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(golden, "run_scenario", keep)
        golden._run_deck(deck)
    assert rows
    last: dict[tuple, float] = {}
    collapses = []
    for row in rows:
        key = (row["agent_id"], row["exit_id"])
        tau = float(row["tau_route"])
        if last.get(key, 0.0) > 1.0 and tau < 0.1:
            collapses.append((row["time_s"], *key, last[key], tau))
        last[key] = tau
    assert collapses == []


class _FramedSmoke:
    """K = 3 /m at x >= 18 m from the 7 s frame on; 1 s frames, ties later."""

    def sample_extinction(self, time_s: float, x: float, y: float) -> float:
        del y
        frame = math.floor(time_s + 0.5)
        return 3.0 if x >= 18.0 and frame >= 7 else 0.0


@pytest.mark.parametrize("order", [(9.87, 9.48), (9.48, 9.87)])
def test_shared_cache_matches_fresh_for_agents_in_one_second(order):
    """Two agents reach C0 0.1 s and 0.4 s after deciding (codex F1, #650).

    Their samples at x = 18 m fall 6.25 s and 6.55 s after the decision,
    frames 6 and 7, so the first route is feasible (tau 5) and the second is
    refused (tau 10). A segment cache keyed on the whole second of the
    leg's start handed the second agent the first one's measurement.
    """

    def route(x, cache):
        return evaluate_route(
            golden._linear(),
            ["D0", "C0", "E0"],
            0.0,
            0.0,
            _FramedSmoke(),
            None,
            _GATE,
            cached_segments=cache,
            agent_position=(x, 0.0),
        )

    expected = {9.87: (5.0, True), 9.48: (10.0, False)}
    shared: dict = {}
    for x in order:
        fresh = route(x, {})
        cached = route(x, shared)
        assert (fresh.tau_route, fresh.feasible) == pytest.approx(expected[x])
        assert cached == fresh


def test_bent_first_leg_reads_each_piece_from_its_own_distance():
    """The clock of a polyline runs on across its vertices.

    A 3 m + 4 m walk at 2 m/s decided at 2 s reaches the vertex at 3.5 s and
    its end at 5.5 s; every point is read at 2 + s / 2.
    """
    from pyfds_evac.core.route_graph import _ForesightClock, _polyline_stats

    times: list[tuple[float, float, float]] = []

    class _Recording:
        def sample_extinction(self, time_s, x, y):
            times.append((time_s, x, y))
            return 0.0

    clock = _ForesightClock(
        t0=2.0,
        speed=2.0,
        horizon_end_s=math.inf,
        decision_time_s=2.0,
        end_s=math.inf,
    )
    _polyline_stats([(0.0, 0.0), (3.0, 0.0), (3.0, 4.0)], 2.0, _Recording(), 2.0, clock)
    assert times
    for time_s, x, y in times:
        walked = x + y  # along the L: 3 m east, then north
        assert time_s == pytest.approx(2.0 + walked / 2.0, abs=1e-12)
    assert max(t for t, _, _ in times) == pytest.approx(5.5, abs=1e-12)


def test_cache_keys_on_the_foresight_limit_for_one_start_time():
    """Two decisions reach C0 at the same instant with different caps (C4a).

    Decided at 0 s from x = 6 m and at 1 s from x = 8 m at 2 m/s, both reach
    C0 at exactly 2.0 s, but H = 3 s caps their samples at 3.0 s and 4.0 s:
    smoke switched on at 3.5 s lies within the second foresight only. The
    start time alone would hand the second the first one's clear leg.
    """
    config = RouteCostConfig(
        cost_model="gate", base_speed_m_per_s=2.0, foresight_horizon_s=3.0
    )
    smoke = golden.LateSmoke(k=0.8, x_min=11.0, t_on=3.5)

    def route(time_s, x, cache):
        return evaluate_route(
            golden._linear(),
            ["D0", "C0", "E0"],
            time_s,
            0.0,
            smoke,
            None,
            config,
            cached_segments=cache,
            agent_position=(x, 0.0),
        )

    shared: dict = {}
    first = route(0.0, 6.0, shared)
    second = route(1.0, 8.0, shared)
    assert first.segments[1].arrival_time_s == second.segments[1].arrival_time_s
    assert first.tau_route == 0.0
    assert second == route(1.0, 8.0, {})
    assert second.tau_route > 0.0
