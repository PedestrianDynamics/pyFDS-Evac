"""Tier A verification tests for the ISO TS 13571 heat (convective) FED model.

Each reference value is rebuilt from raw formulae (math/random only) so the
tests verify ``pyfds_evac.core.fed``'s heat FED symbols against an independent
computation rather than echoing the module's own internals.  See
specs/012-model-verification SPEC.md section "2. FED toxicity and tenability"
for the sibling gas-FED suite this mirrors (``test_fed_verif.py``).

Formula under test, ISO TS 13571 eq. 5 (not in the FDS+Evac guide, unlike the
gas terms -- see the paper quoted in ``pyfds_evac/core/fed.py``):

    rate [1/min] = T[deg C] ** 3.4 / 5e7
"""

import math
import random

import pytest

from pyfds_evac.core.fed import (
    HeatFedInputs,
    TenabilityConfig,
    accumulate_default_heat_fed,
    default_heat_fed_rate_per_minute,
    sample_heat_incapacitation_threshold,
    time_to_heat_fed_threshold_s,
)


def _standard_normal_cdf(z: float) -> float:
    """Return the standard-normal CDF via the error function."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


# --- A3.1: rate matches the closed form -------------------------------------


def test_a3_1_rate_matches_closed_form():
    for t in (20.0, 100.0, 120.0, 150.0, 200.0, 250.0):
        ref_rate = t**3.4 / 5e7
        got = default_heat_fed_rate_per_minute(HeatFedInputs(temperature_celsius=t))
        assert got == pytest.approx(ref_rate, rel=1e-9)


# --- A3.2: domain guard, not a 120C floor -----------------------------------


def test_a3_2_rate_is_zero_only_at_or_below_zero_degrees():
    assert (
        default_heat_fed_rate_per_minute(HeatFedInputs(temperature_celsius=0.0)) == 0.0
    )
    assert (
        default_heat_fed_rate_per_minute(HeatFedInputs(temperature_celsius=-10.0))
        == 0.0
    )
    assert not math.isfinite(float("nan"))
    assert (
        default_heat_fed_rate_per_minute(
            HeatFedInputs(temperature_celsius=float("nan"))
        )
        == 0.0
    )


def test_a3_2_rate_is_nonzero_and_small_at_moderate_temperature():
    """Confirms there is deliberately NO artificial floor anywhere above 0C.

    ISO TS 13571 eq. 5 has no built-in validity cutoff -- a moderate exposure
    still accrues some dose, just slowly, self-limiting by the exponent alone.
    """
    rate_below = default_heat_fed_rate_per_minute(
        HeatFedInputs(temperature_celsius=80.0)
    )
    assert rate_below > 0.0
    assert rate_below == pytest.approx(80.0**3.4 / 5e7, rel=1e-9)


# --- A3.3: accumulation over a constant-exposure interval -------------------


def test_a3_3_accumulation_over_interval():
    inputs = HeatFedInputs(temperature_celsius=150.0)
    ref_rate = 150.0**3.4 / 5e7
    duration_s = 90.0
    ref_fed = ref_rate * (duration_s / 60.0)

    got = accumulate_default_heat_fed(inputs, duration_s=duration_s)

    assert got == pytest.approx(ref_fed, rel=1e-9)


def test_a3_3_accumulation_adds_to_initial_dose():
    inputs = HeatFedInputs(temperature_celsius=150.0)
    got = accumulate_default_heat_fed(inputs, duration_s=60.0, initial_fed=0.4)
    ref_rate = 150.0**3.4 / 5e7
    assert got == pytest.approx(0.4 + ref_rate, rel=1e-9)


# --- A3.4: closed-form time to threshold ------------------------------------


def test_a3_4_time_to_threshold_matches_closed_form():
    inputs = HeatFedInputs(temperature_celsius=150.0)
    ref_rate = 150.0**3.4 / 5e7
    ref_t_s = (1.0 / ref_rate) * 60.0

    got = time_to_heat_fed_threshold_s(inputs, threshold=1.0)

    assert got == pytest.approx(ref_t_s, rel=1e-9)


def test_a3_4_time_to_threshold_is_infinite_at_ambient_zero_rate():
    inputs = HeatFedInputs(temperature_celsius=0.0)
    assert time_to_heat_fed_threshold_s(inputs, threshold=1.0) == math.inf


def test_a3_4_time_to_threshold_is_zero_when_already_met():
    inputs = HeatFedInputs(temperature_celsius=150.0)
    assert time_to_heat_fed_threshold_s(inputs, threshold=1.0, initial_fed=1.0) == 0.0


# --- A3.5: probabilistic heat incapacitation ensemble -----------------------


def test_a3_5_probabilistic_heat_threshold_reproduces_lognormal_bands():
    cfg = TenabilityConfig()  # heat_fed_threshold=1.0, heat_susceptibility_sigma=0.94
    rng = random.Random(24680)
    sigma = cfg.heat_susceptibility_sigma

    n = 20000
    draws = [sample_heat_incapacitation_threshold(cfg, rng) for _ in range(n)]

    for x in (0.3, 1.0, 3.0):
        empirical = sum(1 for d in draws if d <= x) / n
        expected = _standard_normal_cdf(math.log(x) / sigma)
        assert empirical == pytest.approx(expected, abs=0.03)

    draws.sort()
    median = draws[n // 2]
    assert median == pytest.approx(1.0, abs=0.05)


def test_a3_5_deterministic_heat_mode_returns_threshold_exactly():
    cfg = TenabilityConfig(heat_incapacitation_mode="deterministic")
    rng = random.Random(7)
    for _ in range(1000):
        assert sample_heat_incapacitation_threshold(cfg, rng) == cfg.heat_fed_threshold


def test_a3_5_gas_and_heat_threshold_draws_are_independent():
    """Locks in that the two tracks draw independently, not from a shared stream.

    Regression guard: if a future refactor accidentally shares one RNG call
    between the gas and heat draws, the two sequences would become
    correlated (e.g. identical after a fixed seed) instead of independent.
    """
    from pyfds_evac.core.fed import sample_incapacitation_threshold

    cfg = TenabilityConfig()
    rng = random.Random(555)
    gas_draws = [sample_incapacitation_threshold(cfg, rng) for _ in range(200)]
    heat_draws = [sample_heat_incapacitation_threshold(cfg, rng) for _ in range(200)]
    assert gas_draws != heat_draws


# --- A3.6: determinism and monotonicity -------------------------------------


def test_a3_6_threshold_draws_are_seed_reproducible():
    cfg = TenabilityConfig()
    first = [
        sample_heat_incapacitation_threshold(cfg, random.Random(99)) for _ in range(50)
    ]
    second = [
        sample_heat_incapacitation_threshold(cfg, random.Random(99)) for _ in range(50)
    ]
    assert first == second


def test_a3_6_rate_is_pure_function():
    inputs = HeatFedInputs(temperature_celsius=130.0)
    assert default_heat_fed_rate_per_minute(inputs) == default_heat_fed_rate_per_minute(
        inputs
    )


def test_a3_6_rate_strictly_increases_with_temperature():
    rates = [
        default_heat_fed_rate_per_minute(HeatFedInputs(temperature_celsius=t))
        for t in (50.0, 100.0, 150.0, 200.0, 250.0)
    ]
    assert all(lo < hi for lo, hi in zip(rates, rates[1:]))


# --- A3.7: heat FED is not folded into the gas FED sum ----------------------


def test_a3_7_heat_fed_has_no_effect_on_gas_fed_total():
    """Locks in the core physics constraint: heat is a separate dose track.

    A hot-temperature HeatFedInputs must not change default_fed_rate_per_minute
    (the gas total) at all -- the two dataclasses and rate functions are
    fully decoupled, not merely by convention but because HeatFedInputs is
    never passed into any gas-rate function's signature.
    """
    from pyfds_evac.core.fed import DefaultFedInputs, default_fed_rate_per_minute

    gas_inputs = DefaultFedInputs(co_volume_fraction_percent=0.1)
    baseline = default_fed_rate_per_minute(gas_inputs)

    # There is no code path by which HeatFedInputs(temperature_celsius=300)
    # could influence this call -- the two rate functions take disjoint
    # input types. Re-assert the gas rate is unchanged after computing a
    # large heat rate alongside it, as a readable regression guard.
    _ = default_heat_fed_rate_per_minute(HeatFedInputs(temperature_celsius=300.0))
    assert default_fed_rate_per_minute(gas_inputs) == baseline
