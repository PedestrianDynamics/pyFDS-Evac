"""Pin the FED history columns shared by the gas and heat doses (#218).

Gas FED = 1 and heat FED = 1 are different endpoints, yet both set the same
``incapacitated`` flag and report through ``incapacitation_cause``. Whatever
naming #218 adds to tell the endpoints apart, these columns and their values
stay, so existing post-processing keeps working.
"""

from __future__ import annotations

from harness import (
    CorridorSpec,
    corridor_scenario,
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


def test_fed_history_keeps_shared_incapacitation_columns():
    """Both tracks on; every row has the kept columns and a known cause."""
    spec = CorridorSpec(
        length_m=40.0,
        width_m=4.0,
        num_agents=3,
        v0=1.0,
        seed=7,
        max_simulation_time=40.0,
    )
    result = run_scenario(
        corridor_scenario(spec),
        seed=spec.seed,
        fed_model=make_fed_model(
            co_volume_fraction=uniform(20_000e-6),
            co2_volume_fraction=uniform(0.0),
            o2_volume_fraction=uniform(0.209),
            update_interval_s=1.0,
        ),
        heat_fed_model=make_heat_model(
            temperature_celsius=uniform(230.0), update_interval_s=1.0
        ),
        tenability_config=TenabilityConfig(
            incapacitation_mode="deterministic",
            heat_incapacitation_mode="deterministic",
        ),
    )
    try:
        rows = result.fed_history
        assert rows, "no FED history rows"
        for row in rows:
            missing = KEPT_COLUMNS - row.keys()
            assert not missing, f"FED history lost columns {sorted(missing)}"
            assert row["incapacitation_cause"] in CAUSES
            assert bool(row["incapacitated"]) == (row["incapacitation_cause"] != "")
        assert {r["incapacitation_cause"] for r in rows} >= {"heat"}
    finally:
        result.cleanup()
