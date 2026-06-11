"""Tier A verification tests for pre-movement time distributions.

Reference moments are rebuilt from the closed-form distribution formulae
(math/numpy only) so the tests verify ``pyfds_evac.core.premovement_distributions``
against an independent computation.  See specs/012-model-verification SPEC.md
section "6. Pre-movement".

Determinism (A6.2) is the property a single uncontrolled run lacks: fixed seed
must give bit-identical draws.
"""

import math

import numpy as np
import pytest

from pyfds_evac.core.premovement_distributions import (
    PREMOVEMENT_PRESETS,
    GammaDistribution,
    LognormalDistribution,
    UniformDistribution,
    WeibullDistribution,
    create_premovement_distribution,
)

# Large sample with a fixed seed keeps Monte-Carlo error well inside the
# tolerances below while remaining deterministic in CI.
N_MOMENTS = 100_000
MOMENT_SEED = 12345

# Closed-form parameters matching the module presets.
GAMMA_A, GAMMA_B = 1.291, 103.901
LOGNORMAL_A, LOGNORMAL_B = 4.586, 0.967
WEIBULL_A, WEIBULL_B = 139.285, 1.195
UNIFORM_A, UNIFORM_B = 0.0, 60.0


# --- A6.1: moment checks against closed-form references ----------------------


def test_a6_1_gamma_moments_match_closed_form():
    samples = GammaDistribution(a=GAMMA_A, b=GAMMA_B, seed=MOMENT_SEED).sample(
        N_MOMENTS
    )

    # numpy shape=a, scale=b -> mean = a*b, var = a*b^2.
    expected_mean = GAMMA_A * GAMMA_B
    expected_var = GAMMA_A * GAMMA_B**2

    assert samples.mean() == pytest.approx(expected_mean, rel=0.02)
    assert samples.var() == pytest.approx(expected_var, rel=0.02)


def test_a6_1_weibull_mean_matches_closed_form():
    samples = WeibullDistribution(a=WEIBULL_A, b=WEIBULL_B, seed=MOMENT_SEED).sample(
        N_MOMENTS
    )

    # a * Weibull(shape=b) -> mean = a * Gamma(1 + 1/b).
    expected_mean = WEIBULL_A * math.gamma(1.0 + 1.0 / WEIBULL_B)

    assert samples.mean() == pytest.approx(expected_mean, rel=0.02)


def test_a6_1_lognormal_mean_matches_closed_form():
    samples = LognormalDistribution(
        a=LOGNORMAL_A, b=LOGNORMAL_B, seed=MOMENT_SEED
    ).sample(N_MOMENTS)

    # lognormal(mean=a, sigma=b) -> mean = exp(a + b^2/2).
    expected_mean = math.exp(LOGNORMAL_A + LOGNORMAL_B**2 / 2.0)

    assert samples.mean() == pytest.approx(expected_mean, rel=0.03)


def test_a6_1_uniform_moments_match_closed_form():
    samples = UniformDistribution(a=UNIFORM_A, b=UNIFORM_B, seed=MOMENT_SEED).sample(
        N_MOMENTS
    )

    expected_mean = (UNIFORM_A + UNIFORM_B) / 2.0
    expected_var = (UNIFORM_B - UNIFORM_A) ** 2 / 12.0

    assert samples.mean() == pytest.approx(expected_mean, rel=0.02)
    assert samples.var() == pytest.approx(expected_var, rel=0.02)


def test_a6_1_ks_against_scipy_when_available():
    """Optional KS goodness-of-fit; skipped if scipy is not importable."""
    scipy = pytest.importorskip("scipy.stats")

    cases = [
        (
            GammaDistribution(a=GAMMA_A, b=GAMMA_B, seed=MOMENT_SEED),
            scipy.gamma(GAMMA_A, scale=GAMMA_B),
        ),
        (
            WeibullDistribution(a=WEIBULL_A, b=WEIBULL_B, seed=MOMENT_SEED),
            scipy.weibull_min(WEIBULL_B, scale=WEIBULL_A),
        ),
        (
            LognormalDistribution(a=LOGNORMAL_A, b=LOGNORMAL_B, seed=MOMENT_SEED),
            scipy.lognorm(LOGNORMAL_B, scale=math.exp(LOGNORMAL_A)),
        ),
        (
            UniformDistribution(a=UNIFORM_A, b=UNIFORM_B, seed=MOMENT_SEED),
            scipy.uniform(loc=UNIFORM_A, scale=UNIFORM_B - UNIFORM_A),
        ),
    ]

    for dist, frozen in cases:
        samples = dist.sample(N_MOMENTS)
        _, p_value = scipy.kstest(samples, frozen.cdf)
        assert p_value > 0.01


# --- A6.2: anti-FEMTC determinism -------------------------------------------


def test_a6_2_same_seed_is_bit_identical():
    first = GammaDistribution(seed=7).sample(1000)
    second = GammaDistribution(seed=7).sample(1000)

    assert np.array_equal(first, second)


def test_a6_2_different_seed_diverges():
    first = GammaDistribution(seed=7).sample(1000)
    other = GammaDistribution(seed=8).sample(1000)

    assert not np.array_equal(first, other)


def test_a6_2_factory_same_seed_is_bit_identical():
    params = PREMOVEMENT_PRESETS["gamma"]
    first = create_premovement_distribution("gamma", params, seed=7).sample(1000)
    second = create_premovement_distribution("gamma", params, seed=7).sample(1000)

    assert np.array_equal(first, second)


def test_a6_2_factory_different_seed_diverges():
    params = PREMOVEMENT_PRESETS["gamma"]
    first = create_premovement_distribution("gamma", params, seed=7).sample(1000)
    other = create_premovement_distribution("gamma", params, seed=8).sample(1000)

    assert not np.array_equal(first, other)


# --- A6.3: edge cases --------------------------------------------------------


def _all_distributions(seed):
    return [
        GammaDistribution(seed=seed),
        LognormalDistribution(seed=seed),
        WeibullDistribution(seed=seed),
        UniformDistribution(seed=seed),
    ]


def test_a6_3_sample_zero_returns_empty():
    for dist in _all_distributions(seed=3):
        samples = dist.sample(0)
        assert len(samples) == 0


def test_a6_3_sample_one_returns_length_one():
    for dist in _all_distributions(seed=3):
        samples = dist.sample(1)
        assert len(samples) == 1


def test_a6_3_samples_are_finite_and_non_negative():
    for dist in _all_distributions(seed=3):
        samples = dist.sample(1000)
        assert np.all(np.isfinite(samples))
        assert np.all(samples >= 0.0)


# --- A6.4: factory matches direct construction -------------------------------


def test_a6_4_factory_matches_direct_construction():
    from_factory = create_premovement_distribution(
        "gamma", PREMOVEMENT_PRESETS["gamma"], seed=1
    ).sample(1000)
    direct = GammaDistribution(a=GAMMA_A, b=GAMMA_B, seed=1).sample(1000)

    assert np.array_equal(from_factory, direct)


def test_a6_4_factory_unknown_type_raises_value_error():
    with pytest.raises(ValueError):
        create_premovement_distribution("not_a_distribution", {}, seed=1)
