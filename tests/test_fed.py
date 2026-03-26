import math
from pathlib import Path
from types import SimpleNamespace

import matplotlib.pyplot as plt
import numpy as np
import pytest

try:
    from fdsreader import Simulation
except ModuleNotFoundError:
    Simulation = None

from src.core.fed import (
    DefaultFedConfig,
    DefaultFedInputs,
    DefaultFedModel,
    FdsFedField,
    _cn_fed_rate_per_minute,
    _co_fed_rate_per_minute,
    _co_percent_to_ppm,
    _hyperventilation_factor,
    _irritant_fld_rate_per_minute,
    _nox_fed_rate_per_minute,
    _o2_hypoxia_rate_per_minute,
    accumulate_default_fed,
    default_fed_rate_per_minute,
    time_to_fed_threshold_s,
)
from src.core import load_scenario, run_scenario


HASPEL_DIR = Path("fds_data/haspel")


CONSTANT_EXPOSURE_CASES = {
    "co_only": DefaultFedInputs(
        co_volume_fraction_percent=0.10,
        co2_volume_fraction_percent=0.0,
        o2_volume_fraction_percent=20.9,
    ),
    "co_with_co2": DefaultFedInputs(
        co_volume_fraction_percent=0.10,
        co2_volume_fraction_percent=5.0,
        o2_volume_fraction_percent=20.9,
    ),
    "hypoxia_only": DefaultFedInputs(
        co_volume_fraction_percent=0.0,
        co2_volume_fraction_percent=0.0,
        o2_volume_fraction_percent=12.0,
    ),
    "combined": DefaultFedInputs(
        co_volume_fraction_percent=0.10,
        co2_volume_fraction_percent=5.0,
        o2_volume_fraction_percent=12.0,
    ),
}


def _integrate_constant_exposure(
    inputs: DefaultFedInputs,
    *,
    dt_s: float = 1.0,
    threshold: float = 1.0,
    max_time_s: float = 7200.0,
):
    """Numerically integrate FED under constant exposure using the runtime update rule."""
    fed = 0.0
    time_s = 0.0
    history = [(time_s, fed)]
    while fed < threshold and time_s < max_time_s:
        fed = accumulate_default_fed(inputs, duration_s=dt_s, initial_fed=fed)
        time_s += dt_s
        history.append((time_s, fed))
    return history


@pytest.mark.parametrize(
    ("case_name", "inputs"),
    list(CONSTANT_EXPOSURE_CASES.items()),
)
def test_constant_exposure_step_integration_matches_threshold_time(case_name, inputs):
    del case_name
    analytic_time_s = time_to_fed_threshold_s(inputs, threshold=1.0)
    assert analytic_time_s > 0.0
    assert math.isfinite(analytic_time_s)

    history = _integrate_constant_exposure(
        inputs,
        dt_s=1.0,
        threshold=1.0,
        max_time_s=max(7200.0, analytic_time_s + 1.0),
    )
    times_s = [time_s for time_s, _ in history]
    fed_values = [fed for _, fed in history]

    assert fed_values == sorted(fed_values)
    assert times_s[-1] >= analytic_time_s
    assert times_s[-1] - analytic_time_s <= 1.0
    assert fed_values[-2] < 1.0 <= fed_values[-1]


@pytest.mark.parametrize(
    ("case_name", "inputs"),
    list(CONSTANT_EXPOSURE_CASES.items()),
)
def test_constant_exposure_accumulation_matches_closed_form(case_name, inputs):
    del case_name
    rate_per_min = default_fed_rate_per_minute(inputs)
    assert rate_per_min > 0.0

    for duration_s in (1.0, 10.0, 60.0, 300.0):
        expected = rate_per_min * duration_s / 60.0
        assert accumulate_default_fed(inputs, duration_s=duration_s) == pytest.approx(
            expected,
            rel=1e-12,
            abs=1e-12,
        )


def test_default_fed_rate_is_zero_in_clear_air():
    rate = default_fed_rate_per_minute(DefaultFedInputs())
    assert rate < 1e-5
    assert time_to_fed_threshold_s(DefaultFedInputs()) > 1.0e7


# ---------------------------------------------------------------------------
# Closed-form rate validation for each ISO 13571 term
# ---------------------------------------------------------------------------


class TestCoFedRate:
    """Verify CO FED rate against guide Eq. 13: 2.764e-5 * C_CO^1.036 [1/min]."""

    def test_known_value(self):
        co_ppm = _co_percent_to_ppm(0.10)  # 1000 ppm
        rate = _co_fed_rate_per_minute(co_ppm)
        expected = 2.764e-5 * (1000.0**1.036)
        assert rate == pytest.approx(expected, rel=1e-10)

    def test_zero(self):
        assert _co_fed_rate_per_minute(0.0) == 0.0

    def test_negative(self):
        assert _co_fed_rate_per_minute(-10.0) == 0.0


class TestCnFedRate:
    """Verify CN FED rate against guide Eq. 14-15.

    C_CN = max(0, C_HCN - C_NO2).
    Rate = exp(C_CN / 43) / 220 - 0.0045.
    """

    def test_known_value(self):
        hcn, no2 = 150.0, 20.0
        c_cn = hcn - no2  # 130 ppm
        expected = math.exp(c_cn / 43.0) / 220.0 - 0.0045
        rate = _cn_fed_rate_per_minute(hcn, no2)
        assert rate == pytest.approx(expected, rel=1e-10)

    def test_no2_exceeds_hcn(self):
        """NO2 protective effect zeroes the CN term when NO2 >= HCN."""
        assert _cn_fed_rate_per_minute(50.0, 100.0) == 0.0

    def test_zero_hcn(self):
        assert _cn_fed_rate_per_minute(0.0, 0.0) == 0.0

    def test_small_cn_yields_nonnegative(self):
        """When C_CN is small, exp(C_CN/43)/220 < 0.0045 → rate clamped to 0."""
        assert _cn_fed_rate_per_minute(1.0, 0.0) >= 0.0


class TestNoxFedRate:
    """Verify NOx FED rate against guide Eq. 16: C_NOx / 1500 [1/min]."""

    def test_known_value(self):
        no, no2 = 50.0, 20.0
        expected = (no + no2) / 1500.0
        rate = _nox_fed_rate_per_minute(no, no2)
        assert rate == pytest.approx(expected, rel=1e-10)

    def test_zero(self):
        assert _nox_fed_rate_per_minute(0.0, 0.0) == 0.0

    def test_no_only(self):
        assert _nox_fed_rate_per_minute(75.0, 0.0) == pytest.approx(75.0 / 1500.0)

    def test_no2_only(self):
        assert _nox_fed_rate_per_minute(0.0, 30.0) == pytest.approx(30.0 / 1500.0)


class TestIrritantFldRate:
    """Verify irritant FLD rate against guide Eq. 17 with Table 2 Ct values."""

    def test_single_species_hcl(self):
        inputs = DefaultFedInputs(hcl_ppm=1140.0)  # 1140 / 114000 = 0.01
        assert _irritant_fld_rate_per_minute(inputs) == pytest.approx(0.01, rel=1e-10)

    def test_single_species_no2(self):
        inputs = DefaultFedInputs(no2_ppm=19.0)  # 19 / 1900 = 0.01
        assert _irritant_fld_rate_per_minute(inputs) == pytest.approx(0.01, rel=1e-10)

    def test_single_species_acrolein(self):
        inputs = DefaultFedInputs(acrolein_ppm=45.0)  # 45 / 4500 = 0.01
        assert _irritant_fld_rate_per_minute(inputs) == pytest.approx(0.01, rel=1e-10)

    def test_all_irritants(self):
        inputs = DefaultFedInputs(
            hcl_ppm=114.0,
            hbr_ppm=114.0,
            hf_ppm=87.0,
            so2_ppm=12.0,
            no2_ppm=19.0,
            acrolein_ppm=45.0,
            formaldehyde_ppm=225.0,
        )
        expected = (
            114.0 / 114000.0
            + 114.0 / 114000.0
            + 87.0 / 87000.0
            + 12.0 / 12000.0
            + 19.0 / 1900.0
            + 45.0 / 4500.0
            + 225.0 / 22500.0
        )
        assert _irritant_fld_rate_per_minute(inputs) == pytest.approx(
            expected, rel=1e-10
        )

    def test_zero(self):
        assert _irritant_fld_rate_per_minute(DefaultFedInputs()) == 0.0


class TestHyperventilationFactor:
    """Verify HV_CO2 against guide Eq. 19: exp(0.1903*CO2 + 2.0004) / 7.1."""

    def test_zero_co2(self):
        expected = math.exp(2.0004) / 7.1
        assert _hyperventilation_factor(0.0) == pytest.approx(expected, rel=1e-10)

    def test_five_percent(self):
        expected = math.exp(0.1903 * 5.0 + 2.0004) / 7.1
        assert _hyperventilation_factor(5.0) == pytest.approx(expected, rel=1e-10)


class TestO2HypoxiaRate:
    """Verify O2 FED rate against guide Eq. 18."""

    def test_normal_air(self):
        rate = _o2_hypoxia_rate_per_minute(20.9)
        expected = 1.0 / (60.0 * math.exp(8.13 - 0.54 * 0.0))
        assert rate == pytest.approx(expected, rel=1e-10)

    def test_low_o2(self):
        rate = _o2_hypoxia_rate_per_minute(12.0)
        expected = 1.0 / (60.0 * math.exp(8.13 - 0.54 * (20.9 - 12.0)))
        assert rate == pytest.approx(expected, rel=1e-10)


class TestFullFormulaClosedForm:
    """Verify the full ISO 13571 formula matches hand-calculated composition."""

    def test_all_terms_active(self):
        inputs = DefaultFedInputs(
            co_volume_fraction_percent=0.05,
            co2_volume_fraction_percent=3.0,
            o2_volume_fraction_percent=15.0,
            hcn_ppm=80.0,
            no_ppm=30.0,
            no2_ppm=10.0,
            hcl_ppm=200.0,
            so2_ppm=50.0,
        )
        co_ppm = _co_percent_to_ppm(0.05)  # 500
        co_rate = 2.764e-5 * (co_ppm**1.036)
        c_cn = 80.0 - 10.0  # 70
        cn_rate = math.exp(c_cn / 43.0) / 220.0 - 0.0045
        nox_rate = (30.0 + 10.0) / 1500.0
        fld_irr = 200.0 / 114000.0 + 50.0 / 12000.0 + 10.0 / 1900.0
        hv = math.exp(0.1903 * 3.0 + 2.0004) / 7.1
        o2_rate = 1.0 / (60.0 * math.exp(8.13 - 0.54 * (20.9 - 15.0)))
        expected = (co_rate + cn_rate + nox_rate + fld_irr) * hv + o2_rate

        assert default_fed_rate_per_minute(inputs) == pytest.approx(expected, rel=1e-10)

    def test_only_required_species_reduces_to_three_term(self):
        """With no optional species, formula reduces to FED_CO * HV_CO2 + FED_O2."""
        inputs = DefaultFedInputs(
            co_volume_fraction_percent=0.10,
            co2_volume_fraction_percent=2.0,
            o2_volume_fraction_percent=18.0,
        )
        co_ppm = _co_percent_to_ppm(0.10)
        co_rate = 2.764e-5 * (co_ppm**1.036)
        hv = math.exp(0.1903 * 2.0 + 2.0004) / 7.1
        o2_rate = 1.0 / (60.0 * math.exp(8.13 - 0.54 * (20.9 - 18.0)))
        expected = co_rate * hv + o2_rate

        assert default_fed_rate_per_minute(inputs) == pytest.approx(expected, rel=1e-10)


# ---------------------------------------------------------------------------
# Constant-exposure threshold tests for new terms
# ---------------------------------------------------------------------------

NEW_TERM_CASES = {
    "cn_only": DefaultFedInputs(hcn_ppm=150.0),
    "nox_only": DefaultFedInputs(no_ppm=100.0, no2_ppm=50.0),
    "irritants_only": DefaultFedInputs(hcl_ppm=500.0, so2_ppm=200.0),
    "cn_nox_irritants": DefaultFedInputs(
        hcn_ppm=100.0,
        no_ppm=50.0,
        no2_ppm=20.0,
        hcl_ppm=200.0,
        acrolein_ppm=30.0,
    ),
}


@pytest.mark.parametrize(
    ("case_name", "inputs"),
    list(NEW_TERM_CASES.items()),
)
def test_new_term_threshold_time_matches_step_integration(case_name, inputs):
    del case_name
    analytic_time_s = time_to_fed_threshold_s(inputs, threshold=1.0)
    assert analytic_time_s > 0.0
    assert math.isfinite(analytic_time_s)

    history = _integrate_constant_exposure(
        inputs,
        dt_s=1.0,
        threshold=1.0,
        max_time_s=max(7200.0, analytic_time_s + 1.0),
    )
    times_s = [t for t, _ in history]
    fed_values = [f for _, f in history]

    assert fed_values == sorted(fed_values)
    assert times_s[-1] >= analytic_time_s
    assert times_s[-1] - analytic_time_s <= 1.0
    assert fed_values[-2] < 1.0 <= fed_values[-1]


def test_hcn_contributes_to_fed_rate():
    """Test that HCN (cyanide) contributes to FED rate via CN term."""
    base = DefaultFedInputs()
    with_hcn = DefaultFedInputs(hcn_ppm=100.0)
    rate_base = default_fed_rate_per_minute(base)
    rate_hcn = default_fed_rate_per_minute(with_hcn)
    assert rate_hcn > rate_base
    assert rate_hcn > 0.0


def test_no_ppm_contributes_to_fed_rate():
    """Test that NO contributes to FED rate via NOx term."""
    base = DefaultFedInputs()
    with_no = DefaultFedInputs(no_ppm=50.0)
    rate_base = default_fed_rate_per_minute(base)
    rate_no = default_fed_rate_per_minute(with_no)
    assert rate_no > rate_base
    assert rate_no > 0.0


def test_no2_ppm_contributes_to_fed_rate():
    """Test that NO2 contributes to FED rate via both CN and NOx terms."""
    base = DefaultFedInputs()
    with_no2 = DefaultFedInputs(no2_ppm=20.0)
    rate_base = default_fed_rate_per_minute(base)
    rate_no2 = default_fed_rate_per_minute(with_no2)
    assert rate_no2 > rate_base
    assert rate_no2 > 0.0


def test_hcl_ppm_contributes_to_fed_rate():
    """Test that HCl contributes to FED rate via irritant term."""
    base = DefaultFedInputs()
    with_hcl = DefaultFedInputs(hcl_ppm=100.0)
    rate_base = default_fed_rate_per_minute(base)
    rate_hcl = default_fed_rate_per_minute(with_hcl)
    assert rate_hcl > rate_base
    assert rate_hcl > 0.0


def test_hbr_ppm_contributes_to_fed_rate():
    """Test that HBr contributes to FED rate via irritant term."""
    base = DefaultFedInputs()
    with_hbr = DefaultFedInputs(hbr_ppm=100.0)
    rate_base = default_fed_rate_per_minute(base)
    rate_hbr = default_fed_rate_per_minute(with_hbr)
    assert rate_hbr > rate_base
    assert rate_hbr > 0.0


def test_hf_ppm_contributes_to_fed_rate():
    """Test that HF contributes to FED rate via irritant term."""
    base = DefaultFedInputs()
    with_hf = DefaultFedInputs(hf_ppm=50.0)
    rate_base = default_fed_rate_per_minute(base)
    rate_hf = default_fed_rate_per_minute(with_hf)
    assert rate_hf > rate_base
    assert rate_hf > 0.0


def test_so2_ppm_contributes_to_fed_rate():
    """Test that SO2 contributes to FED rate via irritant term."""
    base = DefaultFedInputs()
    with_so2 = DefaultFedInputs(so2_ppm=50.0)
    rate_base = default_fed_rate_per_minute(base)
    rate_so2 = default_fed_rate_per_minute(with_so2)
    assert rate_so2 > rate_base
    assert rate_so2 > 0.0


def test_acrolein_ppm_contributes_to_fed_rate():
    """Test that acrolein contributes to FED rate via irritant term."""
    base = DefaultFedInputs()
    with_acrolein = DefaultFedInputs(acrolein_ppm=50.0)
    rate_base = default_fed_rate_per_minute(base)
    rate_acrolein = default_fed_rate_per_minute(with_acrolein)
    assert rate_acrolein > rate_base
    assert rate_acrolein > 0.0


def test_formaldehyde_ppm_contributes_to_fed_rate():
    """Test that formaldehyde contributes to FED rate via irritant term."""
    base = DefaultFedInputs()
    with_formaldehyde = DefaultFedInputs(formaldehyde_ppm=100.0)
    rate_base = default_fed_rate_per_minute(base)
    rate_formaldehyde = default_fed_rate_per_minute(with_formaldehyde)
    assert rate_formaldehyde > rate_base
    assert rate_formaldehyde > 0.0


def test_combined_all_isolates_contribute():
    """Test combined exposure with all new ISO 13571 species."""
    inputs = DefaultFedInputs(
        co_volume_fraction_percent=0.1,
        co2_volume_fraction_percent=5.0,
        o2_volume_fraction_percent=20.9,
        hcn_ppm=100.0,
        no_ppm=50.0,
        no2_ppm=20.0,
        hcl_ppm=100.0,
        hbr_ppm=100.0,
        hf_ppm=50.0,
        so2_ppm=50.0,
        acrolein_ppm=50.0,
        formaldehyde_ppm=100.0,
    )
    rate = default_fed_rate_per_minute(inputs)
    assert rate > 0.0
    analytic_time = time_to_fed_threshold_s(inputs, threshold=1.0)
    assert analytic_time > 0.0
    assert analytic_time < 1000.0

    accumulated = accumulate_default_fed(inputs, duration_s=60.0)
    assert accumulated > 0.0
    expected = rate * 1.0
    assert accumulated == pytest.approx(expected, rel=1e-10)


@pytest.mark.parametrize(
    ("inputs", "expected_dominant_term"),
    [
        (DefaultFedInputs(0.1, 2.0, 15.0), "combined"),
        (DefaultFedInputs(0.0, 0.0, 12.0), "o2"),
        (DefaultFedInputs(0.1, 0.0, 21.0), "co"),
        (DefaultFedInputs(0.1, 3.43, 21.0), "co2_hv"),
    ],
)
def test_fds_evac_guide_stationary_fed_cases_reach_fed_one_consistently(
    inputs, expected_dominant_term
):
    analytic_time_s = time_to_fed_threshold_s(inputs)

    assert analytic_time_s > 0.0
    assert math.isfinite(analytic_time_s)

    fed_at_threshold = accumulate_default_fed(inputs, duration_s=analytic_time_s)
    fed_before_threshold = accumulate_default_fed(
        inputs, duration_s=max(0.0, analytic_time_s - 1.0)
    )

    assert fed_at_threshold == pytest.approx(1.0, rel=1e-9)
    assert fed_before_threshold < 1.0

    if expected_dominant_term == "combined":
        assert analytic_time_s < time_to_fed_threshold_s(
            DefaultFedInputs(0.1, 0.0, 15.0)
        )
    elif expected_dominant_term == "o2":
        assert analytic_time_s < time_to_fed_threshold_s(DefaultFedInputs())
        assert analytic_time_s > 10000.0
    elif expected_dominant_term == "co":
        assert analytic_time_s > 1000.0
    elif expected_dominant_term == "co2_hv":
        assert analytic_time_s < time_to_fed_threshold_s(
            DefaultFedInputs(0.1, 0.0, 21.0)
        )


def test_co2_accelerates_co_fed_under_constant_exposure():
    co_only = CONSTANT_EXPOSURE_CASES["co_only"]
    co_with_co2 = CONSTANT_EXPOSURE_CASES["co_with_co2"]

    assert default_fed_rate_per_minute(co_with_co2) > default_fed_rate_per_minute(
        co_only
    )
    assert time_to_fed_threshold_s(co_with_co2) < time_to_fed_threshold_s(co_only)


def test_combined_constant_exposure_reaches_threshold_fastest():
    combined = CONSTANT_EXPOSURE_CASES["combined"]

    threshold_times = {
        name: time_to_fed_threshold_s(inputs)
        for name, inputs in CONSTANT_EXPOSURE_CASES.items()
    }

    assert threshold_times["co_with_co2"] < threshold_times["co_only"]
    assert threshold_times["combined"] < threshold_times["co_only"]
    assert threshold_times["combined"] < threshold_times["co_with_co2"]
    assert threshold_times["combined"] < threshold_times["hypoxia_only"]
    assert default_fed_rate_per_minute(combined) == pytest.approx(
        max(
            default_fed_rate_per_minute(inputs)
            for inputs in CONSTANT_EXPOSURE_CASES.values()
        )
    )


def _find_haspel_peak_co_location():
    sim = Simulation(str(HASPEL_DIR))
    co_slice = sim.slices.filter_by_quantity("CARBON MONOXIDE VOLUME FRACTION")[0]
    best = None
    for subslice in co_slice.subslices:
        flat_index = int(subslice.data.argmax())
        peak = float(subslice.data.reshape(-1)[flat_index])
        if best is not None and peak <= best["value"]:
            continue
        t_idx, i_idx, j_idx = map(
            int, np.unravel_index(flat_index, subslice.data.shape)
        )
        dx = (subslice.extent.x_end - subslice.extent.x_start) / subslice.shape[0]
        dy = (subslice.extent.y_end - subslice.extent.y_start) / subslice.shape[1]
        best = {
            "value": peak,
            "time_s": float(co_slice.times[t_idx]),
            "x": float(subslice.extent.x_start + (i_idx + 0.5) * dx),
            "y": float(subslice.extent.y_start + (j_idx + 0.5) * dy),
        }
    return best


def test_fdsreader_stationary_haspel_sampling_drives_positive_fed():
    if Simulation is None:
        pytest.skip("fdsreader is not installed in this environment.")
    if not HASPEL_DIR.exists():
        pytest.skip("Local haspel FDS fixture is not available in this checkout.")

    peak = _find_haspel_peak_co_location()
    field = FdsFedField.from_fds(str(HASPEL_DIR))
    model = DefaultFedModel(field, DefaultFedConfig(fds_dir=str(HASPEL_DIR)))

    inputs, rate_per_min = model.sample_rate(peak["time_s"], peak["x"], peak["y"])
    _, _, cumulative = model.advance(
        peak["time_s"] + 60.0,
        peak["x"],
        peak["y"],
        dt_s=60.0,
        current_fed=0.0,
    )

    assert inputs.co_volume_fraction_percent > 0.0
    assert inputs.co2_volume_fraction_percent >= 0.0
    assert inputs.o2_volume_fraction_percent > 0.0
    assert rate_per_min > 0.0
    assert cumulative > 0.0


class _ConstantInputsFedModel:
    def __init__(self, inputs: DefaultFedInputs):
        self.inputs = inputs

    def advance(self, time_s, x, y, *, dt_s, current_fed):
        del time_s, x, y
        rate_per_min = default_fed_rate_per_minute(self.inputs)
        updated = accumulate_default_fed(
            self.inputs,
            duration_s=dt_s,
            initial_fed=current_fed,
        )
        return self.inputs, rate_per_min, updated


def test_iso_table22_stationary_runtime_matches_analytic_threshold_time():
    inputs = CONSTANT_EXPOSURE_CASES["combined"]
    analytic_time_s = time_to_fed_threshold_s(inputs, threshold=1.0)

    scenario = load_scenario("assets/ISO-table22")
    dist_params = scenario.raw["distributions"]["jps-distributions_0"]["parameters"]
    dist_params["use_premovement"] = False
    dist_params["v0"] = 0.0
    scenario.set_max_time(math.ceil(analytic_time_s) + 1.0)

    result = run_scenario(
        scenario,
        seed=420,
        fed_model=_ConstantInputsFedModel(inputs),
    )

    try:
        assert result.fed_history
        crossing_row = next(
            row for row in result.fed_history if row["fed_cumulative"] >= 1.0
        )
        crossing_time_s = float(crossing_row["time_s"])

        assert abs(crossing_time_s - analytic_time_s) <= result.metrics["dt"]
        assert result.metrics["fed_max"] >= 1.0
        assert result.metrics["agents_remaining"] == 1
        assert result.metrics["all_evacuated"] is False
    finally:
        result.cleanup()


class _ConstantFedModel:
    def __init__(self, rate_per_min=0.25, update_interval_s=0.0):
        self.rate_per_min = float(rate_per_min)
        self.config = SimpleNamespace(update_interval_s=float(update_interval_s))

    def advance(self, time_s, x, y, *, dt_s, current_fed):
        inputs = DefaultFedInputs(0.1, 2.0, 15.0)
        updated = float(current_fed) + self.rate_per_min * max(0.0, float(dt_s)) / 60.0
        return inputs, self.rate_per_min, updated


def test_run_scenario_records_cumulative_fed_history():
    scenario = load_scenario("assets/ISO-table21")
    result = run_scenario(
        scenario,
        seed=420,
        fed_model=_ConstantFedModel(rate_per_min=0.5),
    )

    try:
        assert result.success
        assert result.fed_history
        assert result.metrics["fed_history_samples"] == len(result.fed_history)
        assert result.metrics["fed_max"] > 0.0

        cumulative_values = [row["fed_cumulative"] for row in result.fed_history]
        assert cumulative_values[-1] > cumulative_values[0]
        assert cumulative_values == sorted(cumulative_values)
    finally:
        result.cleanup()


def test_run_scenario_throttles_fed_history_to_update_interval():
    scenario = load_scenario("assets/ISO-table22")
    dist_params = scenario.raw["distributions"]["jps-distributions_0"]["parameters"]
    dist_params["use_premovement"] = False
    dist_params["v0"] = 0.0
    scenario.set_max_time(2.1)

    result = run_scenario(
        scenario,
        seed=420,
        fed_model=_ConstantFedModel(rate_per_min=0.5, update_interval_s=0.5),
    )

    try:
        assert result.fed_history
        times = [row["time_s"] for row in result.fed_history]
        assert times[0] == pytest.approx(0.0)
        assert all((curr - prev) >= 0.5 - 1e-9 for prev, curr in zip(times, times[1:]))
        assert len(times) <= 6
    finally:
        result.cleanup()


def _guide_stationary_cases():
    return {
        "Combined (2, 0.1, 15)%": DefaultFedInputs(0.1, 2.0, 15.0),
        "O2 Only (0, 0, 12)%": DefaultFedInputs(0.0, 0.0, 12.0),
        "CO Only (0, 0.1, 21)%": DefaultFedInputs(0.1, 0.0, 21.0),
        "CO2-Enhanced (3.43, 0.1, 21)%": DefaultFedInputs(0.1, 3.43, 21.0),
    }


def test_fds_evac_guide_stationary_cases_produce_plot(tmp_path):
    times_s = np.linspace(0.0, 100.0, 101)
    output = tmp_path / "fed-guide-stationary-cases.png"

    fig, ax = plt.subplots(figsize=(9, 6))
    for label, inputs in _guide_stationary_cases().items():
        fed_curve = [accumulate_default_fed(inputs, duration_s=t) for t in times_s]
        ax.plot(times_s, fed_curve, linewidth=2, label=label)

    ax.set_xlabel("Time [s]")
    ax.set_ylabel("FED Index [-]")
    ax.set_title("FDS+Evac stationary FED verification cases")
    ax.legend(loc="best")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(output, dpi=150, bbox_inches="tight")
    plt.close(fig)

    assert output.exists()
    assert output.stat().st_size > 0


def test_iso_table22_stationary_runtime_produces_plot(tmp_path: Path):
    inputs = CONSTANT_EXPOSURE_CASES["combined"]
    analytic_time_s = time_to_fed_threshold_s(inputs, threshold=1.0)

    scenario = load_scenario("assets/ISO-table22")
    dist_params = scenario.raw["distributions"]["jps-distributions_0"]["parameters"]
    dist_params["use_premovement"] = False
    dist_params["v0"] = 0.0
    scenario.set_max_time(math.ceil(analytic_time_s) + 1.0)

    result = run_scenario(
        scenario,
        seed=420,
        fed_model=_ConstantInputsFedModel(inputs),
    )

    try:
        runtime_times = [row["time_s"] for row in result.fed_history]
        runtime_fed = [row["fed_cumulative"] for row in result.fed_history]
        theory_times = np.linspace(0.0, runtime_times[-1], 400)
        theory_fed = [
            accumulate_default_fed(inputs, duration_s=float(t)) for t in theory_times
        ]

        output = tmp_path / "iso-table22-stationary-fed.png"
        fig, ax = plt.subplots(figsize=(8, 5))
        ax.plot(theory_times, theory_fed, linewidth=2, label="Analytical FED")
        ax.step(
            runtime_times, runtime_fed, where="post", linewidth=2, label="Runtime FED"
        )
        ax.axhline(1.0, color="black", linestyle=":", linewidth=1.5, label="FED = 1")
        ax.set_xlabel("Time [s]")
        ax.set_ylabel("FED Index [-]")
        ax.set_title("ISO Table 22 stationary FED verification")
        ax.legend(loc="best")
        fig.tight_layout()
        fig.savefig(output, dpi=150, bbox_inches="tight")
        plt.close(fig)

        assert output.exists()
        assert output.stat().st_size > 0
    finally:
        result.cleanup()
