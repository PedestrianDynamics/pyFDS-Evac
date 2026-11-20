"""A deadlock does not end a run while a stuck agent's dose is still rising (#988).

Geometry: a 0.6 m wide corridor. A 0.2 m hot patch (5000 C) at x = 3.0 to 3.2
incapacitates the first agent that walks into it; it then stands in the
corridor and the second agent stops behind it, outside the patch. The
detector fires 100 s after that. Elsewhere the air is at ``COOL_C``: at
172 C the heat dose of the stuck agent reaches its threshold about 210 s into
the run (ISO 13571 Eq. 9), at 0 C it never rises.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "verification"))
from harness import (  # noqa: E402
    CorridorSpec,
    corridor_scenario,
    deterministic_heat_tenability,
    make_heat_model,
)

from pyfds_evac.core.scenario import (  # noqa: E402
    _agents_with_rising_dose,
    run_scenario,
)

COOL_C = 172.0
HOT_PATCH_C = 5000.0
DEADLOCK_END_S = 103.0


def _run(cool_c: float):
    spec = CorridorSpec(
        length_m=12.0, width_m=0.6, num_agents=2, seed=42, max_simulation_time=500.0
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

    def field(_t, x, _y):
        return HOT_PATCH_C if 3.0 <= x <= 3.2 else cool_c

    return run_scenario(
        scenario,
        seed=spec.seed,
        heat_fed_model=make_heat_model(field, update_interval_s=0.1),
        tenability_config=deterministic_heat_tenability(),
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


def test_a_zero_dose_rate_still_ends_the_run_as_a_deadlock():
    result = _run(0.0)
    try:
        deadlock = result.metrics["deadlock"]
        assert deadlock["ended_run"] is True
        assert result.end_reason == "deadlock"
        assert result.evacuation_time == pytest.approx(DEADLOCK_END_S, abs=1.0)
        assert result.evacuation_time == pytest.approx(deadlock["since_s"] + 100.0)
    finally:
        result.cleanup()


@pytest.mark.parametrize(
    ("rates", "expected"),
    [
        ({}, []),
        ({1: 0.0, 2: 0.0}, []),
        ({1: 0.0, 2: 0.01}, [2]),
        ({3: 5.0}, []),
    ],
    ids=["no-rate-yet", "all-zero", "one-rising", "other-agent"],
)
def test_only_stuck_agents_with_a_positive_rate_count(rates, expected):
    stuck = {1: (0.0, 0.0), 2: (1.0, 0.0)}
    assert _agents_with_rising_dose(stuck, rates) == expected
