"""S6 -- heat FED lethality (SFPE Handbook Eq. 63.44) and the OR incapacitation check.

Tier A already pins the heat FED equation to machine precision; this scenario
verifies the *wiring* the gas-FED suite (S1) can't exercise: gas and heat are
two independent cumulative doses (see ``fed.py``'s ``TenabilityConfig``
docstring), and an agent must collapse the instant *either* crosses its
threshold, recorded correctly in ``incapacitation_cause``.

Routing is not part of this scenario -- heat currently affects only
per-agent incapacitation, not route cost or rejection (that is still an open
design question, deferred pending further discussion).

Mirrors S1's corridor structure and temperature-scan style throughout.
"""

from __future__ import annotations

from harness import (
    CorridorSpec,
    corridor_scenario,
    deterministic_heat_tenability,
    first_incapacitation_causes,
    first_incapacitation_times,
    make_fed_model,
    make_heat_model,
    time_to_heat_incapacitation_s,
    time_to_incapacitation_s,
    uniform,
)

from pyfds_evac.core.fed import TenabilityConfig
from pyfds_evac.core.scenario import run_scenario

# 230 C -> t* ~ 28s (closed form), comfortably inside the 40s free-walk egress.
HEAT_TEMPERATURE_C = 230.0
UPDATE_INTERVAL_S = 1.0


def _spec() -> CorridorSpec:
    return CorridorSpec(
        length_m=40.0,
        width_m=4.0,
        num_agents=5,
        v0=1.0,
        seed=42,
        max_simulation_time=60.0,
    )


def _heat_model():
    return make_heat_model(
        temperature_celsius=uniform(HEAT_TEMPERATURE_C),
        update_interval_s=UPDATE_INTERVAL_S,
    )


def test_tstar_is_inside_egress_window():
    """Design invariant: the agent must still be in the field at t*."""
    spec = _spec()
    tstar = time_to_heat_incapacitation_s(HEAT_TEMPERATURE_C)
    assert tstar < spec.free_walk_egress_s, (
        f"t*={tstar:.1f}s exceeds free-walk egress "
        f"{spec.free_walk_egress_s:.1f}s -- the lethality test would be vacuous."
    )


def test_null_field_control_no_meaningful_accumulation():
    """Behavioral F0: heat model present but at ambient temperature.

    Unlike the gas null-field control (CO=0 gives an exact-zero rate via a
    deliberate hypoxia gate in fed.py), ambient temperature has no artificial
    floor on the heat FED rate -- Eq. 63.44 is merely self-limiting, by
    design (see fed.py's TenabilityConfig / SFPE Handbook Ch. 63, Eq. 63.44).
    So this control asserts the accumulated dose stays negligible over the
    run, not exactly zero -- the honest claim the model actually makes.
    """
    spec = _spec()
    null_heat = make_heat_model(
        temperature_celsius=uniform(20.0), update_interval_s=UPDATE_INTERVAL_S
    )
    result = run_scenario(
        corridor_scenario(spec),
        seed=spec.seed,
        heat_fed_model=null_heat,
        tenability_config=deterministic_heat_tenability(),
    )
    try:
        assert result.fed_history is not None
        assert result.metrics["heat_fed_history_samples"] > 0  # wiring did run
        assert result.metrics["heat_fed_max"] < 0.01, (
            "ambient temperature should accumulate negligible heat FED, got "
            f"{result.metrics['heat_fed_max']}"
        )
        assert first_incapacitation_causes(result) == {}
    finally:
        result.cleanup()


def test_treatment_arm_incapacitates_at_closed_form_tstar():
    """Constant hot temperature collapses every agent at t*, cause == 'heat'."""
    spec = _spec()
    tstar = time_to_heat_incapacitation_s(HEAT_TEMPERATURE_C)
    result = run_scenario(
        corridor_scenario(spec),
        seed=spec.seed,
        heat_fed_model=_heat_model(),
        tenability_config=deterministic_heat_tenability(),
    )
    try:
        incap = first_incapacitation_times(result)
        causes = first_incapacitation_causes(result)
        assert len(incap) == spec.num_agents, (
            f"expected all {spec.num_agents} agents incapacitated, got {len(incap)}"
        )
        assert len(set(incap.values())) == 1, (
            f"uniform field should give a single t*, got {sorted(set(incap.values()))}"
        )
        observed = next(iter(incap.values()))
        assert tstar - 0.5 <= observed <= tstar + UPDATE_INTERVAL_S + 0.5, (
            f"observed t*={observed:.1f}s vs closed-form {tstar:.1f}s "
            f"(update interval {UPDATE_INTERVAL_S}s)"
        )
        assert all(c == "heat" for c in causes.values()), (
            f"expected every collapse tagged 'heat', got {set(causes.values())}"
        )
        assert result.metrics["agents_remaining"] == spec.num_agents
    finally:
        result.cleanup()


# 20000 ppm -> t*_gas ~73s: slower than heat's ~28s, and past the 60s run
# window entirely, so the gas track cannot fire on its own within this test.
CO_PPM_SLOW = 20_000.0


def test_dual_track_or_condition_fires_on_the_faster_track():
    """Gas and heat run together; the OR must trip on whichever is faster.

    This is the one test exercising the actual merged incapacitation-check
    code path in scenario.py (gas_crossed / heat_crossed), not just a
    heat-only mirror of S1.
    """
    spec = _spec()
    tstar_heat = time_to_heat_incapacitation_s(HEAT_TEMPERATURE_C)
    tstar_gas = time_to_incapacitation_s(CO_PPM_SLOW)
    assert tstar_heat < tstar_gas, "test setup: heat must be the faster track"
    assert tstar_gas > spec.max_simulation_time, (
        "test setup: gas track must not fire within the run window either -- "
        "otherwise a passing test wouldn't prove the OR picked the faster one"
    )

    fed_model = make_fed_model(
        co_volume_fraction=uniform(CO_PPM_SLOW * 1e-6),
        co2_volume_fraction=uniform(0.0),
        o2_volume_fraction=uniform(0.209),
        update_interval_s=UPDATE_INTERVAL_S,
    )
    tenability = TenabilityConfig(
        enable_fic_speed=False,
        enable_incapacitation=True,
        fed_threshold=1.0,
        incapacitation_mode="deterministic",
        enable_heat_incapacitation=True,
        heat_fed_threshold=1.0,
        heat_incapacitation_mode="deterministic",
    )
    result = run_scenario(
        corridor_scenario(spec),
        seed=spec.seed,
        fed_model=fed_model,
        heat_fed_model=_heat_model(),
        tenability_config=tenability,
    )
    try:
        incap = first_incapacitation_times(result)
        causes = first_incapacitation_causes(result)
        assert len(incap) == spec.num_agents
        observed = next(iter(incap.values()))
        assert tstar_heat - 0.5 <= observed <= tstar_heat + UPDATE_INTERVAL_S + 0.5, (
            f"observed t*={observed:.1f}s should track the faster (heat) "
            f"closed form {tstar_heat:.1f}s, not the slower gas one "
            f"{tstar_gas:.1f}s"
        )
        assert all(c == "heat" for c in causes.values()), (
            f"expected the OR to fire on the faster (heat) track, got "
            f"{set(causes.values())}"
        )
    finally:
        result.cleanup()
