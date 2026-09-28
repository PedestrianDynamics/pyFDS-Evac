"""Tier A verification tests for the ISO 13571 FED toxicity model.

Each reference value is rebuilt from raw formulae (math/random only) so the
tests verify ``pyfds_evac.core.fed`` against an independent computation rather
than echoing the module's own internals.  See specs/012-model-verification
SPEC.md section "2. FED toxicity and tenability".
"""

import math
import random

import pytest

from pyfds_evac.core.fed import (
    _FIC_COEFFS_PPM,
    DefaultFedInputs,
    TenabilityConfig,
    accumulate_default_fed,
    default_fed_rate_per_minute,
    default_fic,
    sample_incapacitation_threshold,
)


def _standard_normal_cdf(z: float) -> float:
    """Return the standard-normal CDF via the error function."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


# --- A2.1: CO-only accumulation with the CO2 hyperventilation factor --------


def test_a2_1_co_only_accumulation_and_hv_co2():
    inputs = DefaultFedInputs(
        co_volume_fraction_percent=0.1,  # 1000 ppm
        co2_volume_fraction_percent=0.0,
        o2_volume_fraction_percent=20.9,
    )

    # No CO2: the hyperventilation factor is 1, as in FDS (#194), and the
    # dose is the CO term alone.
    ref_co_rate = 2.764e-5 * (1000.0**1.036)
    co_only = ref_co_rate * (1800.0 / 60.0)
    assert co_only == pytest.approx(1.063, abs=1e-3)
    assert accumulate_default_fed(inputs, duration_s=1800.0) == pytest.approx(
        co_only, rel=1e-6
    )

    # 1 % CO2: the factor exp(0.1903 + 2.0004)/7.1 = 1.2594 scales the CO dose.
    with_co2 = DefaultFedInputs(
        co_volume_fraction_percent=0.1,
        co2_volume_fraction_percent=1.0,
        o2_volume_fraction_percent=20.9,
    )
    ref_hv = math.exp(0.1903 * 1.0 + 2.0004) / 7.1
    assert ref_hv == pytest.approx(1.2594, abs=1e-4)
    got = accumulate_default_fed(with_co2, duration_s=1800.0)
    assert got == pytest.approx(co_only * ref_hv, rel=1e-6)
    assert got != pytest.approx(co_only, rel=1e-3)


# --- A2.2: additivity of narcotic terms under the shared HV multiplier ------


def test_a2_2_co_and_hcn_terms_add_under_hv():
    inputs = DefaultFedInputs(
        co_volume_fraction_percent=0.05,  # 500 ppm
        hcn_ppm=80.0,
        no2_ppm=0.0,
        co2_volume_fraction_percent=1.0,
        o2_volume_fraction_percent=20.9,
    )

    co_ppm = 0.05 * 10000.0
    ref_co_rate = 2.764e-5 * (co_ppm**1.036)
    c_cn = max(0.0, 80.0 - 0.0)
    ref_cn_rate = math.exp(c_cn / 43.0) / 220.0 - 1.0 / 220.0
    ref_hv = math.exp(0.1903 * 1.0 + 2.0004) / 7.1
    ref_rate = (ref_co_rate + ref_cn_rate) * ref_hv

    assert default_fed_rate_per_minute(inputs) == pytest.approx(ref_rate, rel=1e-9)


# --- A2.3: O2 hypoxia gate at 20.0 % (FDS: X_O2 < 0.20) ---------------------


def test_a2_3_o2_gate_zero_at_and_above_threshold():
    for o2 in (20.0, 20.9):
        inputs = DefaultFedInputs(o2_volume_fraction_percent=o2)
        # All toxicants are 0, so the rate is purely the O2 contribution.
        assert default_fed_rate_per_minute(inputs) == 0.0


def test_a2_3_o2_gate_finite_just_below_threshold():
    inputs = DefaultFedInputs(o2_volume_fraction_percent=19.9)
    # Purser / FDS Tech Ref Eq. 18 gives t_incap directly in MINUTES, so the
    # per-minute rate is 1 / t_incap with no further conversion. This reference
    # previously carried a spurious 60x, matching the engine bug fixed in #35.
    ref_o2_rate = 1.0 / math.exp(8.13 - 0.54 * (20.9 - 19.9))

    got = default_fed_rate_per_minute(inputs)

    assert math.isfinite(got)
    assert got > 0.0
    assert got == pytest.approx(ref_o2_rate, rel=1e-9)


# --- A2.4: Fractional Irritant Concentration --------------------------------


def test_a2_4_fic_sums_concentration_over_coefficients():
    coeffs = dict(_FIC_COEFFS_PPM)
    inputs = DefaultFedInputs(hcl_ppm=90.0, so2_ppm=24.0)

    ref_fic = 90.0 / coeffs["hcl_ppm"] + 24.0 / coeffs["so2_ppm"]

    assert default_fic(inputs) == pytest.approx(ref_fic, rel=1e-9)


# --- A2.5: FIC-driven walking-speed reduction (closed form) -----------------


def test_a2_5_fic_speed_reduction_closed_form_and_clamp():
    alpha = 0.7
    floor = 0.3

    def speed_factor(fic: float) -> float:
        """Documented FIC speed factor: max(floor, 1 - alpha * FIC)."""
        return max(floor, 1.0 - alpha * fic)

    # The defaults the model applies (TenabilityConfig fic_alpha/fic_min_factor).
    cfg = TenabilityConfig()
    assert cfg.fic_alpha == alpha
    assert cfg.fic_min_factor == floor

    assert speed_factor(0.0) == pytest.approx(1.0)
    assert speed_factor(0.5) == pytest.approx(0.65)
    # Large FIC clamps to the floor rather than going negative.
    assert speed_factor(5.0) == pytest.approx(floor)

    v_frantzich = 1.2
    assert v_frantzich * speed_factor(0.5) == pytest.approx(0.78)


# --- A2.6: probabilistic incapacitation ensemble (anti-FEMTC) ---------------


def test_a2_6_probabilistic_incapacitation_reproduces_purser_bands():
    cfg = TenabilityConfig(incapacitation_mode="probabilistic")  # sigma 0.94
    rng = random.Random(12345)
    sigma = cfg.susceptibility_sigma

    n = 20000
    draws = [sample_incapacitation_threshold(cfg, rng) for _ in range(n)]

    for x in (0.3, 1.0, 3.0):
        empirical = sum(1 for d in draws if d <= x) / n
        expected = _standard_normal_cdf(math.log(x) / sigma)
        assert empirical == pytest.approx(expected, abs=0.03)

    draws.sort()
    median = draws[n // 2]
    assert median == pytest.approx(1.0, abs=0.05)


def test_a2_6_deterministic_mode_returns_threshold_exactly():
    cfg = TenabilityConfig(incapacitation_mode="deterministic")
    rng = random.Random(7)
    for _ in range(1000):
        assert sample_incapacitation_threshold(cfg, rng) == cfg.fed_threshold


# --- A2.7: determinism and monotonicity -------------------------------------


def test_a2_7_threshold_draws_are_seed_reproducible():
    cfg = TenabilityConfig(incapacitation_mode="probabilistic")
    first = [sample_incapacitation_threshold(cfg, random.Random(99)) for _ in range(50)]
    second = [
        sample_incapacitation_threshold(cfg, random.Random(99)) for _ in range(50)
    ]
    assert first == second


def test_a2_7_rate_is_pure_function():
    inputs = DefaultFedInputs(co_volume_fraction_percent=0.05, hcn_ppm=40.0)
    assert default_fed_rate_per_minute(inputs) == default_fed_rate_per_minute(inputs)


def test_a2_7_rate_strictly_increases_with_co():
    rates = [
        default_fed_rate_per_minute(DefaultFedInputs(co_volume_fraction_percent=c))
        for c in (0.01, 0.05, 0.1, 0.2)
    ]
    assert all(lo < hi for lo, hi in zip(rates, rates[1:]))


# --- A2.8: FDS verification case FED_FIC, "Asphyxiants" zone ----------------


def test_a2_8_fds_fed_fic_asphyxiants_zone_at_100_s():
    """Reproduce FDS Verification/Species/FED_FIC, device 'FED (Asphyxiants)'.

    The zone holds O2, CO2, CO, NO and HCN at constant mole fractions for
    100 s, with no NO2 and no irritants. FDS writes FED = 0.97403 at 100 s
    (FED_FIC.csv). This is the check that tells the CN forms apart: the
    FDS code form C_CN = C_HCN - (C_NO + C_NO2) gives 0.97401, the FDS+Evac
    guide's Eq. 15 form C_CN = C_HCN - C_NO2 gives 6.17 (#159).
    """
    inputs = DefaultFedInputs(
        o2_volume_fraction_percent=100.0 * 0.09021848,
        co2_volume_fraction_percent=100.0 * 0.01918864,
        co_volume_fraction_percent=2455.82e-4,
        no_ppm=134.87,
        hcn_ppm=265.33,
    )

    got = accumulate_default_fed(inputs, duration_s=100.0)

    assert got == pytest.approx(0.97403, abs=5e-5)
