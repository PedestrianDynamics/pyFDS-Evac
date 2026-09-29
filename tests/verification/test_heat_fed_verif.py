"""Tier A verification tests for the SFPE Handbook heat (convective) FED model.

Source: Purser & McAllister (2016), SFPE Handbook 5th ed., Ch. 63,
doi:10.1007/978-1-4939-2565-0_63, book pp. 2382-2385. Expected values come
from the Handbook, not from ``pyfds_evac.core.fed``:

- A3.1-A3.4 evaluate Eq. 63.44 in the form printed on p. 2382, a *time* to
  incapacitation in minutes, ``t_Iconv = 5e7 * T**-3.4`` (T in deg C), and
  sum the dose as Eq. 63.48 does (``FED = sum dt / t_Iconv``). This checks
  the code against the printed equation; it cannot check that the equation
  predicts human tolerance. The code selects Eq. 63.44 with
  ``clothing="unclothed"`` (ISO 13571:2012 Eq. (10)); the default, ISO
  Eq. (9), is checked in ``tests/test_heat_iso_clothing.py`` and against the
  same tables in A3.12.
- A3.8-A3.11 compare with the Handbook's published numbers: Table 63.21
  (which reproduces Eq. 63.45, not Eq. 63.44), Table 63.20 (convective and
  radiant rows) and Table 63.17 (reported tolerance times).

Only the code under test is imported from ``pyfds_evac``; every reference
value is written out here with ``math`` alone.
"""

import math
import random
from dataclasses import replace

import pytest

from pyfds_evac.core.fed import (
    HeatFedInputs,
    TenabilityConfig,
    accumulate_default_heat_fed,
    default_heat_fed_rate_per_minute,
    sample_heat_incapacitation_threshold,
    time_to_heat_fed_threshold_s,
)

UNCLOTHED = "unclothed"


def _standard_normal_cdf(z: float) -> float:
    """Return the standard-normal CDF via the error function."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def _t_iconv_min(temperature_c: float) -> float:
    """Return Eq. 63.44 as printed (p. 2382): minutes to incapacitation."""
    return 5.0e7 * temperature_c ** (-3.4)


# --- A3.1: rate is the reciprocal of the printed Eq. 63.44 -----------------


def test_a3_1_rate_is_reciprocal_of_printed_time():
    """Eq. 63.48 accrues 1/t_Iconv per minute, with t_Iconv from Eq. 63.44."""
    for t in (20.0, 100.0, 120.0, 150.0, 200.0, 250.0):
        ref_rate = 1.0 / _t_iconv_min(t)
        got = default_heat_fed_rate_per_minute(
            HeatFedInputs(temperature_celsius=t), UNCLOTHED
        )
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

    SFPE Handbook Eq. 63.44 has no built-in validity cutoff -- a moderate exposure
    still accrues some dose, just slowly, self-limiting by the exponent alone.
    """
    rate_below = default_heat_fed_rate_per_minute(
        HeatFedInputs(temperature_celsius=80.0), UNCLOTHED
    )
    assert rate_below > 0.0
    assert rate_below == pytest.approx(1.0 / _t_iconv_min(80.0), rel=1e-9)


# --- A3.3: accumulation over a constant-exposure interval -------------------


def test_a3_3_accumulation_over_interval():
    inputs = HeatFedInputs(temperature_celsius=150.0)
    duration_s = 90.0
    ref_fed = (duration_s / 60.0) / _t_iconv_min(150.0)

    got = accumulate_default_heat_fed(inputs, duration_s=duration_s, clothing=UNCLOTHED)

    assert got == pytest.approx(ref_fed, rel=1e-9)


def test_a3_3_accumulation_adds_to_initial_dose():
    inputs = HeatFedInputs(temperature_celsius=150.0)
    got = accumulate_default_heat_fed(
        inputs, duration_s=60.0, initial_fed=0.4, clothing=UNCLOTHED
    )
    assert got == pytest.approx(0.4 + 1.0 / _t_iconv_min(150.0), rel=1e-9)


# --- A3.4: closed-form time to threshold ------------------------------------


def test_a3_4_time_to_threshold_matches_closed_form():
    inputs = HeatFedInputs(temperature_celsius=150.0)
    ref_t_s = _t_iconv_min(150.0) * 60.0

    got = time_to_heat_fed_threshold_s(inputs, threshold=1.0, clothing=UNCLOTHED)

    assert got == pytest.approx(ref_t_s, rel=1e-9)


def test_a3_4_time_to_threshold_is_infinite_at_ambient_zero_rate():
    inputs = HeatFedInputs(temperature_celsius=0.0)
    assert time_to_heat_fed_threshold_s(inputs, threshold=1.0) == math.inf


def test_a3_4_time_to_threshold_is_zero_when_already_met():
    inputs = HeatFedInputs(temperature_celsius=150.0)
    assert time_to_heat_fed_threshold_s(inputs, threshold=1.0, initial_fed=1.0) == 0.0


# --- A3.5: probabilistic heat incapacitation ensemble -----------------------


def test_a3_5_probabilistic_heat_threshold_reproduces_lognormal_bands():
    cfg = TenabilityConfig(heat_incapacitation_mode="probabilistic")
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
        # One threshold for gas and heat (ISO 13571:2012 §5.4).
        assert sample_heat_incapacitation_threshold(cfg, rng) == cfg.fed_threshold


def test_a3_5_gas_and_heat_threshold_draws_are_independent():
    """The two tracks draw from independent streams, one per agent.

    The engine seeds them separately -- ``seed ^ 0x5EED1`` for gas and
    ``seed ^ 0x5EED2`` for heat (``scenario.py``) -- so the test mirrors that
    rather than drawing both from one generator. Drawing 200 of each from a
    single shared ``Random`` and asserting the lists differ is true of any
    generator, including one where the heat sampler is the gas sampler, so it
    would not catch the defect it names.

    Independence is checked where it matters: correlation across a population,
    with each agent's two draws taken from its own two streams.
    """
    import math

    from pyfds_evac.core.fed import sample_incapacitation_threshold

    cfg = TenabilityConfig(
        incapacitation_mode="probabilistic", heat_incapacitation_mode="probabilistic"
    )
    n = 1000
    gas = [
        sample_incapacitation_threshold(cfg, random.Random(i ^ 0x5EED1))
        for i in range(n)
    ]
    heat = [
        sample_heat_incapacitation_threshold(cfg, random.Random(i ^ 0x5EED2))
        for i in range(n)
    ]

    # Log-space, because the draws are log-normal and the correlation of the
    # underlying normals is what "independent stream" actually means.
    lg = [math.log(x) for x in gas]
    lh = [math.log(x) for x in heat]
    mg, mh = sum(lg) / n, sum(lh) / n
    cov = sum((a - mg) * (b - mh) for a, b in zip(lg, lh)) / n
    sg = (sum((a - mg) ** 2 for a in lg) / n) ** 0.5
    sh = (sum((b - mh) ** 2 for b in lh) / n) ** 0.5
    r = cov / (sg * sh)

    assert abs(r) < 0.15, f"gas and heat draws are correlated: r={r:.3f}"

    # Independent streams are only half of it. The heat sampler must also read
    # the *heat* configuration: aliasing it to the gas sampler leaves the
    # streams as independent as ever, so correlation alone cannot catch that.
    # Separate the two medians by 5x and check which one the draws land on.
    split = replace(cfg, fed_threshold=1.0, heat_fed_threshold=5.0)
    heat_split = sorted(
        sample_heat_incapacitation_threshold(split, random.Random(i ^ 0x5EED2))
        for i in range(n)
    )
    median = heat_split[n // 2]
    assert 4.0 < median < 6.25, (
        f"heat draws have median {median:.2f}, expected ~5.0 -- the sampler is "
        "reading fed_threshold rather than heat_fed_threshold"
    )


# --- A3.6: determinism and monotonicity -------------------------------------


def test_a3_6_threshold_draws_are_seed_reproducible():
    cfg = TenabilityConfig(heat_incapacitation_mode="probabilistic")
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


# --- A3.8: Table 63.21 is Eq. 63.45, not Eq. 63.44 --------------------------
#
# Table 63.21 (p. 2385) sums the dose of the armchair room burn minute by
# minute. Its caption says "Calculated According to Equation 63.44", but the
# printed rates are those of Eq. 63.45 (p. 2382, tolerance time, mid
# humidity), the law of ``--heat-endpoint tolerance``. These tests keep the
# table as the independent reference for it, and record that Eq. 63.44 does
# not reproduce it.

TABLE_63_21_TEMP_C = (20.0, 65.0, 125.0, 220.0, 405.0, 405.0)
TABLE_63_21_RATE = (0.0, 0.02, 0.19, 1.57, 15.55, 15.55)
# Printed from minute 3 on; minutes 1 and 2 are blank in the table.
TABLE_63_21_CUMULATIVE = {3: 0.21, 4: 1.78, 5: 17.33, 6: 32.88}


def _t_tol_min(temperature_c: float) -> float:
    """Return Eq. 63.45 as printed (p. 2382): tolerance time in minutes."""
    return 2.0e31 * temperature_c ** (-16.963) + 4.0e8 * temperature_c ** (-3.7561)


def test_a3_8_eq_63_45_reproduces_table_63_21_rates():
    """Each printed rate is 1/t_tol rounded to two decimals (+-0.005)."""
    for temp, printed in zip(TABLE_63_21_TEMP_C, TABLE_63_21_RATE):
        assert 1.0 / _t_tol_min(temp) == pytest.approx(printed, abs=0.005), temp


def test_a3_8_table_63_21_cumulative_row_sums_the_rounded_rates():
    """The printed cumulative row is the running sum of the printed rates.

    Against the unrounded Eq. 63.45 sum, the n-th entry may differ by up to
    n rounding steps of 0.005 each: 0.21 is 0.02 + 0.19, whereas the exact
    sum to minute 3 is 0.2035.
    """
    rounded_total = 0.0
    exact_total = 0.0
    for minute, (temp, printed) in enumerate(
        zip(TABLE_63_21_TEMP_C, TABLE_63_21_RATE), start=1
    ):
        rounded_total += printed
        exact_total += 1.0 / _t_tol_min(temp)
        if minute not in TABLE_63_21_CUMULATIVE:
            continue
        expected = TABLE_63_21_CUMULATIVE[minute]
        assert rounded_total == pytest.approx(expected, abs=1e-9), minute
        assert exact_total == pytest.approx(expected, abs=minute * 0.005), minute


def test_a3_8_table_63_21_first_crossing_in_fourth_minute():
    """The Handbook text: incapacitation (FED = 1) "during the fourth minute"."""
    total = 0.0
    crossing_minute = None
    for minute, temp in enumerate(TABLE_63_21_TEMP_C, start=1):
        total += 1.0 / _t_tol_min(temp)
        if total >= 1.0:
            crossing_minute = minute
            break
    assert crossing_minute == 4


def test_a3_8_eq_63_44_does_not_reproduce_table_63_21():
    """Records the caption mismatch: Eq. 63.44 gives 0.03/0.27/1.84/14.67.

    Both the printed Eq. 63.44 and the implemented rate miss every non-zero
    printed rate by more than the table's rounding, so the table is not an
    oracle for the law in use today.
    """
    for temp, printed in zip(TABLE_63_21_TEMP_C[1:5], TABLE_63_21_RATE[1:5]):
        assert abs(1.0 / _t_iconv_min(temp) - printed) > 0.005, temp
        got = default_heat_fed_rate_per_minute(
            HeatFedInputs(temperature_celsius=temp), UNCLOTHED
        )
        assert abs(got - printed) > 0.005, temp


# --- A3.9: Table 63.20 convective rows --------------------------------------
#
# Table 63.20 (p. 2383) gives tolerance times in whole minutes for air below
# 10 % water vapour. Each entry is read as the interval [t - 0.5, t + 0.5]
# min. The Handbook says Eq. 63.44 is "somewhat overconservative at the
# low-temperature end" and "somewhat nonconservative" at higher temperatures
# (p. 2382). Eq. 63.44 gives 7.9 / 4.3 / 2.5 / 1.6 / 1.1 min.

TABLE_63_20_CONVECTIVE_MIN = {100.0: 12, 120.0: 7, 140.0: 4, 160.0: 2, 180.0: 1}


def test_a3_9_eq_63_44_not_longer_than_table_63_20():
    """Eq. 63.44 never gives a longer time than the table's rounding allows."""
    for temp, tabulated in TABLE_63_20_CONVECTIVE_MIN.items():
        t44 = _t_iconv_min(temp)
        assert t44 <= tabulated + 0.5, (temp, t44, tabulated)
        rate = default_heat_fed_rate_per_minute(
            HeatFedInputs(temperature_celsius=temp), UNCLOTHED
        )
        assert 1.0 / rate <= tabulated + 0.5, (temp, 1.0 / rate, tabulated)


def test_a3_9_eq_63_44_is_overconservative_at_the_low_end():
    """At 100-140 C Eq. 63.44 is below the table's interval (shorter time)."""
    for temp in (100.0, 120.0, 140.0):
        tabulated = TABLE_63_20_CONVECTIVE_MIN[temp]
        rate = default_heat_fed_rate_per_minute(
            HeatFedInputs(temperature_celsius=temp), UNCLOTHED
        )
        assert 1.0 / rate < tabulated - 0.5, (temp, 1.0 / rate, tabulated)


def test_a3_9_eq_63_44_within_factor_two_of_table_63_20():
    """Gross-error band: Eq. 63.44 time within a factor 2 of every row.

    The factor 2 is a stated choice, not a sourced tolerance. The Handbook
    says only "somewhat" over- or nonconservative; the observed ratios are
    0.61 to 1.07. The band catches a wrong exponent or unit, not a refit.
    """
    for temp, tabulated in TABLE_63_20_CONVECTIVE_MIN.items():
        rate = default_heat_fed_rate_per_minute(
            HeatFedInputs(temperature_celsius=temp), UNCLOTHED
        )
        assert 0.5 <= (1.0 / rate) / tabulated <= 2.0, temp


# --- A3.10: Table 63.17 reported tolerance times ----------------------------


def test_a3_10_eq_63_44_not_longer_than_reported_dry_air_tolerance():
    """Eq. 63.44 never exceeds a time humans were reported to tolerate.

    Table 63.17 (p. 2375), dry-air rows: the points A-D "added for
    comparison" to Fig. 63.28, whose curves Eq. 63.44 is derived from. The
    subjects were clothed (205 C: "bare headed, protected") and tolerated
    these times, so a naked-skin law should not predict longer; the check is
    one-sided and needs no chosen tolerance. The humid-air row is
    outside Eq. 63.44's < 10 % water-vapour scope and is left out.
    """
    reported = {110.0: 25.0, 180.0: 3.0, 205.0: 4.0, 126.0: 7.0}
    for temp, tolerated_min in reported.items():
        rate = default_heat_fed_rate_per_minute(
            HeatFedInputs(temperature_celsius=temp), UNCLOTHED
        )
        assert 1.0 / rate <= tolerated_min, (temp, 1.0 / rate, tolerated_min)


# --- A3.11: radiant references for the total-flux dose -----------------------
#
# These tests fix the published numbers a radiant term must reproduce and
# check that Eq. 63.43 as printed does; they call no pyFDS-Evac code. The
# total-flux method (#223) is checked against the same Table 63.20 rows in
# tests/test_heat_total_flux.py.


def _t_irad_min(flux_kw_m2: float, dose: float) -> float:
    """Return Eq. 63.43 as printed (p. 2382): t = r / q**1.33 in minutes."""
    return dose / flux_kw_m2**1.33


def test_a3_11_eq_63_43_reproduces_table_63_20_radiant_rows():
    """2.5 kW/m2 -> 30 s and 10 kW/m2 -> 4 s, within the issue's +-30 % band.

    r = 1.33 (kW/m2)^4/3 min, which the Handbook proposes as the tolerance
    threshold (p. 2382); Table 63.20 lists tenability limits. Eq. 63.43 gives
    23.6 s and 3.7 s. The row "< 2.5 kW/m2 -> > 5 min" is a threshold, not a
    value of Eq. 63.43, and is not checked.
    """
    for flux, tabulated_s in ((2.5, 30.0), (10.0, 4.0)):
        t_s = 60.0 * _t_irad_min(flux, dose=1.33)
        assert t_s == pytest.approx(tabulated_s, rel=0.30), flux


def test_a3_11_hot_layer_anchor_200c_is_about_2_5_kw_m2():
    """A 200 C layer radiates about 2.5 kW/m2 to a person below (p. 2382).

    Black-body layer (emissivity 1) and a full view of it, net flux to a
    surface at 20 or 35 C: 2.42 and 2.33 kW/m2. Emissivity, view factor,
    surface temperature and the +-10 % band are assumptions: the Handbook
    says only "approximately".
    """
    sigma = 5.67e-8  # W m^-2 K^-4, as printed with Eq. 63.49
    t_layer_k = 200.0 + 273.15
    for t_surface_c in (20.0, 35.0):
        t_surface_k = t_surface_c + 273.15
        q = sigma * (t_layer_k**4 - t_surface_k**4) / 1000.0
        assert q == pytest.approx(2.5, rel=0.10), t_surface_c


# --- A3.12: ISO 13571:2012 Eq. (9), the default law, against the tables ----
#
# ISO 13571:2012 §8.3.2, fully clothed: t_Iconv = 4.1e8 * T**-3.61 min. The
# Handbook's tables are not stated to be for clothed subjects; these tests
# record where the default law lies relative to them, not a pass band.


def _t_iso_9_min(temperature_c: float) -> float:
    """Return ISO 13571:2012 Eq. (9): minutes, fully clothed."""
    return 4.1e8 * temperature_c ** (-3.61)


def test_a3_12_default_law_is_iso_eq_9():
    for temp in TABLE_63_20_CONVECTIVE_MIN:
        rate = default_heat_fed_rate_per_minute(HeatFedInputs(temperature_celsius=temp))
        assert 1.0 / rate == pytest.approx(_t_iso_9_min(temp), rel=1e-12)


def test_a3_12_eq_9_is_1_8_to_3_times_table_63_20():
    """Eq. (9) gives 24.7 / 12.8 / 7.3 / 4.5 / 3.0 min against 12/7/4/2/1."""
    ratios = [
        _t_iso_9_min(temp) / tabulated
        for temp, tabulated in TABLE_63_20_CONVECTIVE_MIN.items()
    ]
    assert min(ratios) == pytest.approx(1.83, abs=0.01)
    assert max(ratios) == pytest.approx(2.96, abs=0.01)
    assert all(
        t > tabulated + 0.5
        for t, tabulated in zip(
            map(_t_iso_9_min, TABLE_63_20_CONVECTIVE_MIN),
            TABLE_63_20_CONVECTIVE_MIN.values(),
        )
    )


def test_a3_12_eq_9_against_table_63_17_dry_air_rows():
    """Eq. (9) is longer than the reported 7 min at 126 C (10.7 min).

    At 110, 180 and 205 C it stays at or below the reported times
    (17.5 against 25, 2.96 against 3, 1.85 against 4 min).
    """
    reported = {110.0: 25.0, 180.0: 3.0, 205.0: 4.0, 126.0: 7.0}
    longer = {t for t, tol in reported.items() if _t_iso_9_min(t) > tol}
    assert longer == {126.0}
    assert _t_iso_9_min(126.0) == pytest.approx(10.73, abs=0.01)
