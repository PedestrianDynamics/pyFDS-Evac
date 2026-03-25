import math

import matplotlib.pyplot as plt
import numpy as np
import pytest
from fdsreader import Simulation

from src.core.fed import (
    DefaultFedModel,
    DefaultFedInputs,
    DefaultFedConfig,
    FdsFedField,
    accumulate_default_fed,
    default_fed_rate_per_minute,
    time_to_fed_threshold_s,
)
from src.core import load_scenario, run_scenario


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


def _find_haspel_peak_co_location():
    sim = Simulation("fds_data/haspel")
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
    peak = _find_haspel_peak_co_location()
    field = FdsFedField.from_fds("fds_data/haspel")
    model = DefaultFedModel(field, DefaultFedConfig(fds_dir="fds_data/haspel"))

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


class _ConstantFedModel:
    def __init__(self, rate_per_min=0.25):
        self.rate_per_min = float(rate_per_min)

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
