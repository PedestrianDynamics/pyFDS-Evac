"""Hand-computed values of four rerouting golden cases (#810).

The goldens under ``tests/golden/rank_routes`` and
``tests/golden/evaluate_and_reroute`` are snapshots of the code's own output
(``regression-only`` in ``tests/golden/README.md``): they show that a value
changed, not that it is right. For the cases below the value follows from
the case's inputs in a few lines of arithmetic, written out in each test, so
these tests are independent verification of the documented cost terms. They
do not replace the goldens.

Shared inputs, from ``test_rerouting_golden``: the star graph has its spawn
at (0, 0), the west exit at (-20, 0) and the east exit at (40, 0); both cost
configurations walk at ``base_speed_m_per_s = 1.0``; the additive one keeps
the default FED weight ``w_fed = 10``. Every case is in clear air unless it
says otherwise, so a walk of L metres takes L seconds. ``rank_routes``
returns unrounded floats, compared to float precision; ``_evaluate``
rounds its costs to 4 decimals as the goldens do, so those are compared to
half a unit in the last stored digit. The last test changes the speed and
the weights from 1 so that each factor of the FED and queue terms shows.
"""

from __future__ import annotations

import math

import pytest
import test_rerouting_golden as golden

from pyfds_evac.core.route_graph import rank_routes

FLOAT = 1e-9
ROUNDING = 5e-5
W_FED = 10.0
WEST_M, EAST_M = 20.0, 40.0


def _rank(name: str) -> tuple[dict, list[str]]:
    return _rank_case(golden.RANK_CASES[name])


def _rank_case(case: golden.RankCase) -> tuple[dict, list[str]]:
    ranked = rank_routes(
        case.graph(),
        case.source,
        case.time_s,
        case.current_fed,
        case.extinction,
        case.fed,
        case.config,
        exit_counts=case.exit_counts,
        cognitive_map=case.cognitive_map() if case.cognitive_map else None,
        agent_position=case.agent_position,
        current_exit=case.current_exit,
    )
    return {rc.exit_id: rc for rc in ranked}, [rc.exit_id for rc in ranked]


def test_route_fed_is_the_rate_times_the_walk_in_minutes():
    """``additive_fed_refuses``: west arm FED rate 4.0 /min, current FED 0.2.

    FED on a route = current FED + rate x walk time / 60 (rate per minute,
    time in seconds); composite cost = length + w_fed x route FED.
    West: 0.2 + 4.0 x 20 / 60 = 1.5333, cost 20 + 10 x 1.5333 = 35.3333.
    East has no FED rate: 0.2, cost 40 + 10 x 0.2 = 42.0.
    """
    routes, _ = _rank("additive_fed_refuses")
    west_fed = 0.2 + 4.0 * WEST_M / 60.0
    assert routes["west"].fed_max_route == pytest.approx(west_fed, abs=FLOAT)
    assert routes["west"].composite_cost == pytest.approx(
        WEST_M + W_FED * west_fed, abs=FLOAT
    )
    assert routes["east"].fed_max_route == pytest.approx(0.2, abs=FLOAT)
    assert routes["east"].composite_cost == pytest.approx(
        EAST_M + W_FED * 0.2, abs=FLOAT
    )


def test_fed_on_both_arms_scales_with_each_walk():
    """``additive_fed_fallback``: both arms at 4.0 /min, current FED 0.2.

    East: 0.2 + 4.0 x 40 / 60 = 2.8667, cost 40 + 10 x 2.8667 = 68.6667.
    """
    routes, _ = _rank("additive_fed_fallback")
    east_fed = 0.2 + 4.0 * EAST_M / 60.0
    assert routes["east"].fed_max_route == pytest.approx(east_fed, abs=FLOAT)
    assert routes["east"].composite_cost == pytest.approx(
        EAST_M + W_FED * east_fed, abs=FLOAT
    )


def test_queue_is_the_crowd_over_the_exit_capacity():
    """``additive_queue``: 40 agents at west, none at east, ``w_queue = 1``.

    Queue time = N / capacity = 40 / 1.3 = 30.7692 s (default exit capacity
    1.3 agents/s); composite adds w_queue x v0 x queue time, so west costs
    20 + 1.0 x 1.0 x 30.7692 = 50.7692 and loses to east at 40.
    """
    routes, order = _rank("additive_queue")
    queue_s = 40 / 1.3
    assert routes["west"].queue_time_s == pytest.approx(queue_s, abs=FLOAT)
    assert routes["west"].composite_cost == pytest.approx(
        WEST_M + 1.0 * 1.0 * queue_s, abs=FLOAT
    )
    assert routes["east"].queue_time_s == 0.0
    assert order == ["east", "west"]


def test_tau_counts_only_the_walk_still_ahead():
    """``gate_agent_position``: agent at (-8, 0), west arm extinction 0.2 /m.

    tau = K x remaining length. West has 20 - 8 = 12 m left, all in the
    west arm: tau = 0.2 x 12 = 2.4, and with ``w_smoke = w_fed = 0`` the
    composite cost is the remaining length, 12. East walks back 8 m and
    then 40 m: cost 48.
    """
    routes, _ = _rank("gate_agent_position")
    assert routes["west"].tau_route == pytest.approx(0.2 * 12.0, abs=FLOAT)
    assert routes["west"].composite_cost == pytest.approx(12.0, abs=FLOAT)
    assert routes["east"].composite_cost == pytest.approx(8.0 + EAST_M, abs=FLOAT)


@pytest.mark.parametrize("name", ["better_path_ten_percent", "better_path_additive"])
def test_a_shorter_same_exit_path_is_priced_by_its_length(name):
    """Diamond D0 (0, 0), C0 (0, 10), C1 (0, 30), E0 (20, 10), clear air.

    The agent walks D0-C1-E0: 30 + sqrt(20^2 + 20^2) = 58.2843 m. The other
    path D0-C0-E0 is 10 + 20 = 30 m, so it switches to it.
    """
    switch = golden._evaluate(golden.REROUTE_CASES[name])["switch"]
    assert switch["reason"] == "better_path"
    assert switch["old_cost"] == pytest.approx(30.0 + math.hypot(20, 20), abs=ROUNDING)
    assert switch["new_cost"] == pytest.approx(10.0 + 20.0, abs=ROUNDING)


def test_fed_and_queue_scale_with_speed_and_weights():
    """Star, v0 = 1.3 m/s, ``w_fed = 2``, ``w_queue = 3``, west FED rate
    4.0 /min, current FED 0.2, 40 agents at west.

    West walk: 20 / 1.3 = 15.3846 s, so FED = 0.2 + 4.0 x 15.3846 / 60 =
    1.2256. Queue: 40 / 1.3 = 30.7692 s, priced as 3 x 1.3 x 30.7692 = 120 m.
    Composite: 20 + 2 x 1.2256 + 120 = 142.4513.
    """
    case = golden.RankCase(
        golden._star2,
        golden._additive(base_speed_m_per_s=1.3, w_fed=2.0, w_queue=3.0),
        fed=golden.ArmFed({"west": 4.0}),
        current_fed=0.2,
        exit_counts={"west": 40, "east": 0},
    )
    routes, _ = _rank_case(case)
    west_fed = 0.2 + 4.0 * (WEST_M / 1.3) / 60.0
    queue_s = 40 / 1.3
    assert routes["west"].fed_max_route == pytest.approx(west_fed, abs=FLOAT)
    assert routes["west"].queue_time_s == pytest.approx(queue_s, abs=FLOAT)
    assert routes["west"].composite_cost == pytest.approx(
        WEST_M + 2.0 * west_fed + 3.0 * 1.3 * queue_s, abs=FLOAT
    )
