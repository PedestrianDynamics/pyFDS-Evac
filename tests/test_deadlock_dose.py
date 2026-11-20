"""A deadlock does not end a run while a stuck agent's dose is still rising (#988).

Geometry: a 0.6 m wide corridor. A 0.2 m hot patch (5000 C) at x = 3.0 to 3.2
incapacitates the first agent that walks into it; it then stands in the
corridor and the second agent stops behind it, outside the patch. The
detector fires 100 s after that. Elsewhere the air is at ``COOL_C``: at
172 C the heat dose of the stuck agent reaches its threshold about 210 s into
the run (ISO 13571 Eq. 9), at 0 C it never rises.
"""

import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "verification"))
from harness import (  # noqa: E402
    CorridorSpec,
    corridor_scenario,
    deterministic_heat_tenability,
    make_fed_model,
    make_heat_model,
    uniform,
)

from pyfds_evac.core.fed import TenabilityConfig  # noqa: E402
from pyfds_evac.core.scenario import (  # noqa: E402
    _agents_reaching_threshold,
    _threshold_reach_s,
    run_scenario,
)

COOL_C = 172.0
HOT_PATCH_C = 5000.0
DEADLOCK_END_S = 103.0


def _run_models(t_max_s, tenability, *, heat_model=None, fed_model=None):
    spec = CorridorSpec(
        length_m=12.0, width_m=0.6, num_agents=2, seed=42, max_simulation_time=t_max_s
    )
    scenario = corridor_scenario(spec)
    scenario.raw["exits"]["exit_far"]["coordinates"] = [
        [11, 0.05],
        [12, 0.05],
        [12, 0.55],
        [11, 0.55],
        [11, 0.05],
    ]
    scenario.raw["distributions"]["spawn_near"]["coordinates"] = [
        [1, 0.05],
        [2.5, 0.05],
        [2.5, 0.55],
        [1, 0.55],
        [1, 0.05],
    ]

    return run_scenario(
        scenario,
        seed=spec.seed,
        heat_fed_model=heat_model,
        fed_model=fed_model,
        tenability_config=tenability,
    )


def _in_patch(x):
    return 3.0 <= x <= 3.2


def _run(cool_c: float, t_max_s: float = 500.0, tenability=None):
    def field(_t, x, _y):
        return HOT_PATCH_C if _in_patch(x) else cool_c

    return _run_models(
        t_max_s,
        tenability or deterministic_heat_tenability(),
        heat_model=make_heat_model(field, update_interval_s=0.1),
    )


def _run_gas(t_max_s: float):
    """Heat boxes the agents in; the stuck one has only a gas dose.

    The hot patch incapacitates the first agent by heat. Elsewhere the air
    is at 20 C and carries 4000 ppm CO (about 0.15 FED/min), so the stuck
    agent reaches the gas threshold of 1.0 at about 400 s.
    """

    def heat(_t, x, _y):
        return HOT_PATCH_C if _in_patch(x) else 20.0

    fed_model = make_fed_model(
        co_volume_fraction=uniform(4000e-6),
        co2_volume_fraction=uniform(0.0),
        o2_volume_fraction=uniform(0.209),
        update_interval_s=0.1,
    )
    tenability = TenabilityConfig(
        enable_fic_speed=False,
        enable_incapacitation=True,
        fed_threshold=1.0,
        incapacitation_mode="deterministic",
        enable_heat_incapacitation=True,
        heat_fed_threshold=50.0,
        heat_incapacitation_mode="deterministic",
    )
    return _run_models(
        t_max_s,
        tenability,
        heat_model=make_heat_model(heat, update_interval_s=0.1),
        fed_model=fed_model,
    )


def test_a_rising_dose_keeps_the_run_going_past_the_deadlock(caplog):
    with caplog.at_level("WARNING", logger="pyfds_evac.core.scenario"):
        result = _run(COOL_C)
    try:
        deadlock = result.metrics["deadlock"]
        assert deadlock["ended_run"] is False
        assert deadlock["agents"] == 1
        assert result.end_reason == "all_mobile_left"
        assert result.evacuation_time > DEADLOCK_END_S + 50.0
        assert result.agents_incapacitated == 2
        logged = [r.getMessage() for r in caplog.records if "Deadlock" in r.message]
        assert len(logged) == 1
        assert "continues" in logged[0]
        assert "dose of 1 stuck agent" in logged[0]
    finally:
        result.cleanup()


@pytest.mark.parametrize(
    ("cool_c", "t_max_s"),
    [(20.0, 500.0), (0.0, 500.0), (COOL_C, 150.0)],
    ids=["cool-air", "zero-rate", "threshold-after-time-limit"],
)
def test_a_dose_that_cannot_reach_its_threshold_ends_the_run_as_a_deadlock(
    cool_c, t_max_s
):
    result = _run(cool_c, t_max_s)
    try:
        deadlock = result.metrics["deadlock"]
        assert deadlock["ended_run"] is True
        assert result.end_reason == "deadlock"
        assert result.evacuation_time == pytest.approx(DEADLOCK_END_S, abs=1.0)
        assert result.evacuation_time == pytest.approx(deadlock["since_s"] + 100.0)
    finally:
        result.cleanup()


@pytest.mark.parametrize(
    ("now_s", "cumulative", "rate", "threshold", "expected"),
    [
        (100.0, 0.5, 0.0, 1.0, math.inf),
        (100.0, 0.5, 0.3, 1.0, 200.0),
        (100.0, 1.2, 0.3, 1.0, 100.0),
    ],
    ids=["zero-rate", "half-dose-left", "already-over"],
)
def test_threshold_reach_time_follows_the_rate(
    now_s, cumulative, rate, threshold, expected
):
    assert _threshold_reach_s(now_s, cumulative, rate, threshold) == pytest.approx(
        expected
    )


@pytest.mark.parametrize(
    ("t_max_s", "expected"),
    [(199.9, []), (200.0, [2]), (300.0, [2])],
    ids=["just-short", "exactly-at-limit", "ample"],
)
def test_only_stuck_agents_that_reach_their_threshold_by_the_limit_count(
    t_max_s, expected
):
    stuck = {1: (0.0, 0.0), 2: (1.0, 0.0)}
    reach = {1: math.inf, 2: 200.0, 3: 10.0}
    assert _agents_reaching_threshold(stuck, reach, t_max_s) == expected


def test_a_heat_threshold_above_the_reach_ends_the_run_as_a_deadlock():
    """The heat track uses the heat threshold, not the gas one (#988).

    At 172 C the dose reaches 1.0 at about 210 s but 3.0 only after the
    500 s limit; the gas threshold of 1.0 would let the run continue.
    """
    tenability = TenabilityConfig(
        enable_fic_speed=False,
        enable_incapacitation=False,
        fed_threshold=1.0,
        enable_heat_incapacitation=True,
        heat_fed_threshold=3.0,
        heat_incapacitation_mode="deterministic",
    )
    result = _run(COOL_C, 500.0, tenability)
    try:
        assert result.end_reason == "deadlock"
        assert result.metrics["deadlock"]["ended_run"] is True
    finally:
        result.cleanup()


def test_a_heat_threshold_below_the_gas_one_still_continues():
    tenability = TenabilityConfig(
        enable_fic_speed=False,
        enable_incapacitation=False,
        fed_threshold=50.0,
        enable_heat_incapacitation=True,
        heat_fed_threshold=1.0,
        heat_incapacitation_mode="deterministic",
    )
    result = _run(COOL_C, 500.0, tenability)
    try:
        assert result.end_reason == "all_mobile_left"
        assert result.metrics["deadlock"]["ended_run"] is False
    finally:
        result.cleanup()


def test_a_gas_dose_that_reaches_its_threshold_keeps_the_run_going():
    result = _run_gas(500.0)
    try:
        assert result.end_reason == "all_mobile_left"
        assert result.metrics["deadlock"]["ended_run"] is False
        assert result.agents_incapacitated == 2
    finally:
        result.cleanup()


def test_a_gas_dose_that_misses_the_time_limit_ends_the_run_as_a_deadlock():
    result = _run_gas(300.0)
    try:
        assert result.end_reason == "deadlock"
        assert result.metrics["deadlock"]["ended_run"] is True
    finally:
        result.cleanup()
