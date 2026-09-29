"""Pin the FED history columns shared by the gas and heat doses (#218).

Gas FED = 1 and heat FED = 1 are different endpoints, yet both set the same
``incapacitated`` flag and report through ``incapacitation_cause``. Whatever
naming #218 adds to tell the endpoints apart, these columns and their values
stay, so existing post-processing keeps working.

Each case below fixes when each dose crosses its threshold, from the hand
formulas in ``harness`` (ISO Eq. (9) for heat, the guide's CO term for gas),
and checks the cause the run records: the dose that crossed first, both on
the same update, and a crossing by the other dose after the agent stopped,
which must not change the recorded cause.
"""

from __future__ import annotations

import math

import pytest
from harness import (
    CorridorSpec,
    co_fed_rate_per_min,
    corridor_scenario,
    heat_fed_rate_per_min,
    make_fed_model,
    make_heat_model,
    uniform,
)

from pyfds_evac.core.fed import TenabilityConfig
from pyfds_evac.core.scenario import run_scenario

KEPT_COLUMNS = {
    "fed_cumulative",
    "heat_fed_cumulative",
    "heat_fed_rate_per_min",
    "temperature_celsius",
    "incapacitated",
    "incapacitation_cause",
}
CAUSES = {"", "gas", "heat", "gas+heat"}

CO_PPM = 20_000.0
TEMPERATURE_C = 230.0
UPDATE_S = 1.0
RUN_S = 25.0
NEVER_S = 1e6

# (id, seconds for the gas dose to reach its threshold, same for heat,
#  expected cause). Crossing times sit mid-interval so the update on which a
# dose crosses is unambiguous.
_CASES = [
    ("gas-first", 5.5, NEVER_S, "gas"),
    ("heat-first", NEVER_S, 5.5, "heat"),
    ("same-update", 5.3, 5.7, "gas+heat"),
    ("heat-crosses-after-gas", 5.5, 15.5, "gas"),
    ("gas-crosses-after-heat", 15.5, 5.5, "heat"),
]


def _run(t_gas_s: float, t_heat_s: float):
    """Corridor with uniform CO and temperature; thresholds from hand rates."""
    fed_threshold = co_fed_rate_per_min(CO_PPM) * t_gas_s / 60.0
    heat_threshold = heat_fed_rate_per_min(TEMPERATURE_C) * t_heat_s / 60.0
    spec = CorridorSpec(
        length_m=40.0,
        width_m=4.0,
        num_agents=2,
        v0=1.0,
        seed=7,
        max_simulation_time=RUN_S,
    )
    result = run_scenario(
        corridor_scenario(spec),
        seed=spec.seed,
        fed_model=make_fed_model(
            co_volume_fraction=uniform(CO_PPM * 1e-6),
            co2_volume_fraction=uniform(0.0),
            o2_volume_fraction=uniform(0.209),
            update_interval_s=UPDATE_S,
        ),
        heat_fed_model=make_heat_model(
            temperature_celsius=uniform(TEMPERATURE_C), update_interval_s=UPDATE_S
        ),
        tenability_config=TenabilityConfig(
            incapacitation_mode="deterministic",
            fed_threshold=fed_threshold,
            heat_incapacitation_mode="deterministic",
            heat_fed_threshold=heat_threshold,
        ),
    )
    return result, fed_threshold, heat_threshold


def _rows_by_agent(rows):
    by_agent: dict[int, list[dict]] = {}
    for row in rows:
        by_agent.setdefault(row["agent_id"], []).append(row)
    for agent_rows in by_agent.values():
        agent_rows.sort(key=lambda r: r["time_s"])
    return by_agent


@pytest.mark.parametrize(
    ("t_gas_s", "t_heat_s", "expected_cause"),
    [pytest.param(g, h, c, id=i) for i, g, h, c in _CASES],
)
def test_incapacitation_cause_records_the_first_crossing(
    t_gas_s, t_heat_s, expected_cause
):
    """The recorded cause is the dose that crossed first, and it is kept."""
    result, fed_threshold, heat_threshold = _run(t_gas_s, t_heat_s)
    try:
        by_agent = _rows_by_agent(result.fed_history)
        assert by_agent, "no FED history rows"
        t_first = min(t_gas_s, t_heat_s)
        for agent_id, rows in by_agent.items():
            start = rows[0]["time_s"]
            for row in rows:
                missing = KEPT_COLUMNS - row.keys()
                assert not missing, f"FED history lost columns {sorted(missing)}"
                assert row["incapacitation_cause"] in CAUSES
                assert bool(row["incapacitated"]) == (row["incapacitation_cause"] != "")
            stopped = [r for r in rows if r["incapacitation_cause"]]
            assert stopped, f"agent {agent_id} never incapacitated"
            # Stopped on the first update at or after the earlier crossing.
            elapsed = stopped[0]["time_s"] - start
            assert math.ceil(t_first) - 0.5 <= elapsed <= math.ceil(t_first) + 0.5, (
                f"agent {agent_id} stopped after {elapsed} s, expected "
                f"{math.ceil(t_first)} s"
            )
            # Once recorded, the cause never changes.
            causes = {r["incapacitation_cause"] for r in stopped}
            assert causes == {expected_cause}, (agent_id, causes)
            # Rows before the stop carry no cause.
            before = rows[: rows.index(stopped[0])]
            assert all(r["incapacitation_cause"] == "" for r in before)
            # A later crossing by the other dose is reached but not recorded.
            if max(t_gas_s, t_heat_s) < RUN_S and expected_cause != "gas+heat":
                other = (
                    "heat_fed_cumulative"
                    if expected_cause == "gas"
                    else ("fed_cumulative")
                )
                threshold = (
                    heat_threshold if expected_cause == "gas" else (fed_threshold)
                )
                assert stopped[-1][other] >= threshold, (
                    f"agent {agent_id}: {other} never reached {threshold}; "
                    "the later crossing is not exercised"
                )
    finally:
        result.cleanup()
