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

    assert default_fed_rate_per_minute(co_with_co2) > default_fed_rate_per_minute(co_only)
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
        assert all(
            (curr - prev) >= 0.5 - 1e-9
            for prev, curr in zip(times, times[1:])
        )
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
        ax.step(runtime_times, runtime_fed, where="post", linewidth=2, label="Runtime FED")
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
