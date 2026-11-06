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
    default_fed_components,
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


def test_a2_6_probabilistic_incapacitation_reproduces_lognormal_bands():
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
    rng_first, rng_second = random.Random(99), random.Random(99)
    first = [sample_incapacitation_threshold(cfg, rng_first) for _ in range(50)]
    second = [sample_incapacitation_threshold(cfg, rng_second) for _ in range(50)]
    assert first == second
    assert len(set(first)) == len(first)


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


# --- A2.9: HCN term with NO and NO2 subtracted, clamped at zero -------------
#
# The FDS form (func.f90, function FED): C_CN = HCN - (NO + NO2) and
# rate = (exp(C_CN/43) - 1)/220. Reference values are rebuilt here from that
# form, not read from the module.


def test_a2_9_hcn_subtracts_no_and_no2():
    inputs = DefaultFedInputs(hcn_ppm=150.0, no_ppm=20.0, no2_ppm=10.0)
    ref_cn = (math.exp(120.0 / 43.0) - 1.0) / 220.0
    assert ref_cn == pytest.approx(0.06951, abs=1e-5)
    got = default_fed_components(inputs).cn_rate_per_min
    assert got == pytest.approx(ref_cn, rel=1e-9)


def test_a2_9_hcn_term_is_zero_when_nox_exceeds_hcn():
    inputs = DefaultFedInputs(hcn_ppm=20.0, no_ppm=30.0)
    parts = default_fed_components(inputs)
    assert parts.cn_rate_per_min == 0.0
    # NOx still enters its own term: 30 ppm / 1500 ppm.min.
    assert parts.nox_rate_per_min == pytest.approx(30.0 / 1500.0, rel=1e-12)


# --- A2.10: CO2 factor is exactly 1 at zero CO2, Eq. 70.34 above it ---------


def test_a2_10_co2_factor_one_at_zero_and_offset_above():
    assert default_fed_components(DefaultFedInputs()).hv_co2 == 1.0
    tiny = default_fed_components(
        DefaultFedInputs(co2_volume_fraction_percent=1e-9)
    ).hv_co2
    assert tiny == pytest.approx(math.exp(2.0004) / 7.1, rel=1e-6)
    assert tiny == pytest.approx(1.0411, abs=1e-4)
    six = default_fed_components(
        DefaultFedInputs(co2_volume_fraction_percent=6.0)
    ).hv_co2
    assert six == pytest.approx(math.exp(0.1903 * 6.0 + 2.0004) / 7.1, rel=1e-12)
    # No 70 L/min cap: at 25 L/min the cap would hold the factor at 2.8,
    # which Eq. 70.34 passes at about 5.2 % CO2.
    assert six > 2.8


# --- A2.11: O2 gate follows o2_threshold_percent ----------------------------


def test_a2_11_o2_gate_moves_with_threshold():
    just_below = DefaultFedInputs(o2_volume_fraction_percent=19.999)
    ref = 1.0 / math.exp(8.13 - 0.54 * (20.9 - 19.999))
    assert default_fed_rate_per_minute(just_below) == pytest.approx(ref, rel=1e-9)
    between = DefaultFedInputs(o2_volume_fraction_percent=19.7)
    assert default_fed_rate_per_minute(between) > 0.0
    assert default_fed_rate_per_minute(between, o2_threshold_percent=19.5) == 0.0
    assert (
        default_fed_rate_per_minute(
            DefaultFedInputs(o2_volume_fraction_percent=19.5), o2_threshold_percent=19.5
        )
        == 0.0
    )


# --- A2.12: mixed gases, CO2 multiplies every term except O2 ----------------


def test_a2_12_mixed_gas_co2_multiplies_all_but_o2():
    inputs = DefaultFedInputs(
        co_volume_fraction_percent=0.05,
        co2_volume_fraction_percent=3.0,
        o2_volume_fraction_percent=15.0,
        hcn_ppm=100.0,
        no_ppm=10.0,
        no2_ppm=20.0,
        hcl_ppm=500.0,
    )
    co = 2.764e-5 * 500.0**1.036
    cn = (math.exp(70.0 / 43.0) - 1.0) / 220.0
    nox = 30.0 / 1500.0
    fld = 500.0 / 114000.0 + 20.0 / 1900.0
    hv = math.exp(0.1903 * 3.0 + 2.0004) / 7.1
    o2 = 1.0 / math.exp(8.13 - 0.54 * (20.9 - 15.0))
    expected = (co + cn + nox + fld) * hv + o2
    got = default_fed_rate_per_minute(inputs)
    assert got == pytest.approx(expected, rel=1e-9)
    # Multiplying the O2 term too would give a different rate.
    assert got != pytest.approx((co + cn + nox + fld + o2) * hv, rel=1e-6)


# --- A2.13: seconds are converted to minutes once ---------------------------


def test_a2_13_accumulation_converts_seconds_to_minutes_once():
    inputs = DefaultFedInputs(co_volume_fraction_percent=0.1)  # 1000 ppm CO
    rate_per_min = 2.764e-5 * 1000.0**1.036
    assert accumulate_default_fed(inputs, duration_s=60.0) == pytest.approx(
        rate_per_min, rel=1e-9
    )
    stepped = 0.0
    for _ in range(60):
        stepped = accumulate_default_fed(inputs, duration_s=1.0, initial_fed=stepped)
    assert stepped == pytest.approx(rate_per_min, rel=1e-9)
    # The guide's extra factor 60 would give a dose 60 times smaller.
    assert stepped > 30.0 * rate_per_min / 60.0
