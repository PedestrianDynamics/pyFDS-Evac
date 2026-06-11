"""S1 -- corridor FED lethality: does the FED -> incapacitation coupling fire.

Tier A already pins the FED equation to machine precision; this scenario
verifies the *wiring* inside the real run loop: a constant CO atmosphere is
sampled at each agent's live position, cumulative FED advances every tick, and
crossing the threshold pins the agent's speed to zero.

Three arms, per the harness contract:

- **control** (``fed_model=None``)   -> no incapacitation, agents evacuate.
- **treatment** (CO on, deterministic threshold) -> every agent collapses at the
  closed-form ``t* = 60 * D / rate(CO)``, within one FED update interval.
- **dose-response** (``slow``)        -> probabilistic thresholds reproduce the
  log-normal population endpoint: ~half the population incapacitated when
  cumulative FED reaches the median threshold.

The CO level and corridor length are chosen so ``t* < free-walk egress`` -- the
non-vacuous inequality is asserted, not assumed (else the treatment arm would be
indistinguishable from the control).
"""

from __future__ import annotations

import pytest

from pyfds_evac.core.fed import TenabilityConfig
from pyfds_evac.core.scenario import run_scenario

from harness import (
    CorridorSpec,
    corridor_scenario,
    deterministic_tenability,
    first_incapacitation_times,
    make_fed_model,
    time_to_incapacitation_s,
    uniform,
)

# 6 % CO -> t* ~ 23.4 s, comfortably inside the 40 s free-walk egress.
CO_PPM = 60_000.0
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


def _co_fed_model():
    return make_fed_model(
        co_volume_fraction=uniform(CO_PPM * 1e-6),
        co2_volume_fraction=uniform(0.0),
        o2_volume_fraction=uniform(0.209),
        update_interval_s=UPDATE_INTERVAL_S,
    )


def test_tstar_is_inside_egress_window():
    """Design invariant: the agent must still be in the field at t*."""
    spec = _spec()
    tstar = time_to_incapacitation_s(CO_PPM)
    assert tstar < spec.free_walk_egress_s, (
        f"t*={tstar:.1f}s exceeds free-walk egress "
        f"{spec.free_walk_egress_s:.1f}s -- the lethality test would be vacuous."
    )


def test_geometry_sanity_agents_evacuate_with_no_fed():
    """Sanity: with no FED model agents can traverse the corridor and exit."""
    spec = _spec()
    result = run_scenario(corridor_scenario(spec), seed=spec.seed)
    try:
        assert result.fed_history is None
        assert result.metrics["agents_evacuated"] > 0
        assert result.metrics["agents_remaining"] == 0
    finally:
        result.cleanup()


def test_null_field_control_no_accumulation():
    """Behavioral F0: FED model present but zero toxicant -> zero accumulation.

    This is the discriminating control -- it drives the *same* accumulation
    wiring as the treatment with a null input, so it catches spurious FED drift
    (e.g. the O2 ambient-drift class the model guards against in fed.py) that the
    geometry sanity arm (``fed_model=None``) cannot see.
    """
    spec = _spec()
    null_fed = make_fed_model(
        co_volume_fraction=uniform(0.0),
        co2_volume_fraction=uniform(0.0),
        o2_volume_fraction=uniform(0.209),  # ambient O2, hypoxia gated off
        update_interval_s=UPDATE_INTERVAL_S,
    )
    result = run_scenario(
        corridor_scenario(spec),
        seed=spec.seed,
        fed_model=null_fed,
        tenability_config=deterministic_tenability(),
    )
    try:
        assert result.fed_history is not None
        assert result.metrics["fed_history_samples"] > 0  # wiring did run
        assert result.metrics["fed_max"] == 0.0, (
            f"null toxicant should not accumulate FED, got {result.metrics['fed_max']}"
        )
        assert first_incapacitation_times(result) == {}
    finally:
        result.cleanup()


def test_treatment_arm_incapacitates_at_closed_form_tstar():
    """Constant CO collapses every agent at t*, within one FED update tick."""
    spec = _spec()
    tstar = time_to_incapacitation_s(CO_PPM)
    result = run_scenario(
        corridor_scenario(spec),
        seed=spec.seed,
        fed_model=_co_fed_model(),
        tenability_config=deterministic_tenability(),
    )
    try:
        incap = first_incapacitation_times(result)
        # Every agent collapses (none escape before t*).
        assert len(incap) == spec.num_agents, (
            f"expected all {spec.num_agents} agents incapacitated, got {len(incap)}"
        )
        # Uniform field => position-independent => one shared collapse time.
        assert len(set(incap.values())) == 1, (
            f"uniform field should give a single t*, got {sorted(set(incap.values()))}"
        )
        observed = next(iter(incap.values()))
        # Detection lags by at most one update interval (crossing is caught at
        # the next FED tick); it can never precede t*.
        assert tstar - 0.5 <= observed <= tstar + UPDATE_INTERVAL_S + 0.5, (
            f"observed t*={observed:.1f}s vs closed-form {tstar:.1f}s "
            f"(update interval {UPDATE_INTERVAL_S}s)"
        )
        # None evacuate -- collapse precedes the exit.
        assert result.metrics["agents_remaining"] == spec.num_agents
    finally:
        result.cleanup()


@pytest.mark.slow
def test_probabilistic_population_endpoint_is_lognormal_median():
    """Population endpoint: ~half incapacitated at the median threshold.

    Probabilistic mode draws each agent's threshold from a log-normal with
    median ``fed_threshold``.  Sampled at the time cumulative FED reaches that
    median (``t*`` for D=1), the incapacitated fraction must sit near 50 % --
    the anti-FEMTC claim that a single deterministic run cannot make.  A single
    large population stands in for a 30-seed ensemble here; the incap RNG is
    seeded from the run seed (scenario.py), so the fraction is reproducible, not
    a single uncontrolled draw.
    """
    spec = CorridorSpec(
        length_m=60.0,  # longer: keep the large population in-field through t*
        width_m=6.0,
        num_agents=120,
        v0=1.0,
        seed=7,
        max_simulation_time=60.0,
    )
    tstar = time_to_incapacitation_s(CO_PPM, fed_threshold=1.0)
    tenability = TenabilityConfig(
        enable_fic_speed=False,
        enable_incapacitation=True,
        fed_threshold=1.0,
        incapacitation_mode="probabilistic",
        susceptibility_sigma=0.94,
    )
    result = run_scenario(
        corridor_scenario(spec),
        seed=spec.seed,
        fed_model=_co_fed_model(),
        tenability_config=tenability,
    )
    try:
        incap = first_incapacitation_times(result)
        # Fraction collapsed by the moment cumulative FED crosses the median.
        window = tstar + UPDATE_INTERVAL_S
        collapsed_by_median = sum(1 for t in incap.values() if t <= window)
        fraction = collapsed_by_median / spec.num_agents
        assert 0.35 <= fraction <= 0.65, (
            f"log-normal median band: expected ~50% incapacitated by t*+dt, "
            f"got {fraction:.0%} ({collapsed_by_median}/{spec.num_agents})"
        )
    finally:
        result.cleanup()


@pytest.mark.slow
def test_probabilistic_run_is_reproducible_under_fixed_seed():
    """Anti-FEMTC determinism: same seed yields the same collapse-time *multiset*.

    Note the invariant is the multiset, not the per-agent mapping: JuPedSim's
    integration is not bit-reproducible run-to-run (the agent-id <-> outcome
    assignment shuffles even with ``fed_model=None``), so trajectory-level
    determinism is unattainable with this engine.  What *is* reproducible -- and
    what the anti-FEMTC discipline actually needs -- is the aggregate endpoint:
    the same seed produces the same distribution of collapse times.
    """
    spec = CorridorSpec(
        length_m=40.0,
        width_m=4.0,
        num_agents=20,
        v0=1.0,
        seed=11,
        max_simulation_time=60.0,
    )
    tenability = TenabilityConfig(
        enable_fic_speed=False,
        enable_incapacitation=True,
        fed_threshold=1.0,
        incapacitation_mode="probabilistic",
        susceptibility_sigma=0.94,
    )

    def _collapse_times():
        result = run_scenario(
            corridor_scenario(spec),
            seed=spec.seed,
            fed_model=_co_fed_model(),
            tenability_config=tenability,
        )
        try:
            return sorted(first_incapacitation_times(result).values())
        finally:
            result.cleanup()

    assert _collapse_times() == _collapse_times()
