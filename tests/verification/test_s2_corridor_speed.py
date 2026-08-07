"""S2 -- corridor smoke-speed: does the extinction -> speed-factor coupling fire.

The mirror of S1: a uniform, *sub-lethal* extinction field (no FED model, so
nobody is incapacitated) should slow agents by exactly the speed law's factor
and leave everyone able to evacuate.

Two assertion layers:

- **Wiring (exact).**  Each ``smoke_history`` row records the factor the model
  applied at the agent's position; under a uniform field it must equal the
  closed-form factor, the sampled extinction must equal ``K0``, and the applied
  ``desired_speed`` must equal ``base_speed * factor``.  This is exact and
  position-independent, so it is robust to JuPedSim's run-to-run nondeterminism
  (see project memory: only aggregate invariants are reproducible).
- **Behavioral (aggregate).**  Total egress time scales as ``1 / factor`` versus
  the no-smoke control -- asserted as a ratio with tolerance, never bit-equality.

The Lund (linear, clamped) and Fridolf (V/(V+2)) laws give materially different
factors for the same ``K0``; the divergence is asserted so a silent law mix-up
cannot pass.
"""

from __future__ import annotations

import pytest
from harness import (
    CorridorSpec,
    corridor_scenario,
    fridolf_speed_factor,
    lund_speed_factor,
    make_smoke_model,
    uniform,
)

from pyfds_evac.core.scenario import run_scenario

# K0 = 2 /m: sub-lethal haze. Lund -> 0.839, Fridolf -> 0.429 (clear divergence).
K0 = 2.0


def _spec() -> CorridorSpec:
    return CorridorSpec(
        length_m=30.0,
        width_m=4.0,
        num_agents=5,
        v0=1.0,
        seed=42,
        max_simulation_time=120.0,
    )


def _assert_uniform_factor(smoke_history, expected_factor: float):
    """Every logged row applied the closed-form factor at the sampled K0."""
    assert smoke_history, "smoke model produced no history rows"
    for row in smoke_history:
        assert row["extinction_per_m"] == pytest.approx(K0, abs=1e-9)
        assert row["speed_factor"] == pytest.approx(expected_factor, rel=1e-9)
        assert row["desired_speed"] == pytest.approx(
            row["base_speed"] * row["speed_factor"], rel=1e-9
        )


def test_lund_factor_applied_exactly():
    """Uniform K0 + Lund law: every agent is slowed by the closed-form factor."""
    spec = _spec()
    result = run_scenario(
        corridor_scenario(spec),
        seed=spec.seed,
        smoke_speed_model=make_smoke_model(uniform(K0), speed_law="lund"),
    )
    try:
        _assert_uniform_factor(result.smoke_history, lund_speed_factor(K0))
    finally:
        result.cleanup()


def test_fridolf_factor_applied_exactly():
    """Uniform K0 + Fridolf law: factor matches V/(V+2) with V = c/K0."""
    spec = _spec()
    result = run_scenario(
        corridor_scenario(spec),
        seed=spec.seed,
        smoke_speed_model=make_smoke_model(uniform(K0), speed_law="fridolf"),
    )
    try:
        _assert_uniform_factor(result.smoke_history, fridolf_speed_factor(K0))
    finally:
        result.cleanup()


def test_laws_diverge_at_same_extinction():
    """Lund and Fridolf must give materially different factors for one K0.

    Guards against a silent speed-law mix-up: if the two laws collapsed to the
    same value the per-law tests would both pass on the wrong implementation.
    """
    assert abs(lund_speed_factor(K0) - fridolf_speed_factor(K0)) > 0.2


def test_null_field_control_no_slowdown():
    """Behavioral F0: K = 0 everywhere -> factor == 1, no speed change.

    Drives the same smoke-update wiring as the treatment with a null field, so
    a bug that perturbs speed even in clear air is caught here.
    """
    spec = _spec()
    result = run_scenario(
        corridor_scenario(spec),
        seed=spec.seed,
        smoke_speed_model=make_smoke_model(uniform(0.0), speed_law="lund"),
    )
    try:
        history = result.smoke_history
        assert history, "smoke model produced no history rows"
        for row in history:
            assert row["speed_factor"] == pytest.approx(1.0, rel=1e-9)
            assert row["desired_speed"] == pytest.approx(row["base_speed"], rel=1e-9)
    finally:
        result.cleanup()


def test_egress_slows_by_inverse_factor():
    """Aggregate behaviour: egress time scales as 1/factor vs the clear control.

    Low congestion (few agents, wide corridor) so egress is speed-limited, not
    flow-limited.  Asserted as a tolerant ratio -- bit-equality is unavailable
    because the underlying run is not deterministic at trajectory level.
    """
    spec = _spec()
    factor = lund_speed_factor(K0)

    control = run_scenario(corridor_scenario(spec), seed=spec.seed)
    treatment = run_scenario(
        corridor_scenario(spec),
        seed=spec.seed,
        smoke_speed_model=make_smoke_model(uniform(K0), speed_law="lund"),
    )
    try:
        evac_control = control.metrics["evacuation_time"]
        evac_treatment = treatment.metrics["evacuation_time"]
        # Both fully evacuate: the haze is sub-lethal, no incapacitation path.
        assert control.metrics["agents_remaining"] == 0
        assert treatment.metrics["agents_remaining"] == 0
        # Strictly slower, and close to the 1/factor prediction.
        assert evac_treatment > evac_control
        assert evac_treatment / evac_control == pytest.approx(1.0 / factor, rel=0.08)
    finally:
        control.cleanup()
        treatment.cleanup()
