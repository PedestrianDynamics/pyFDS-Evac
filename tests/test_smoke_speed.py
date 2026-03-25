from pathlib import Path

import matplotlib.pyplot as plt
import pytest

from src.core import (
    ConstantExtinctionField,
    SmokeSpeedConfig,
    SmokeSpeedModel,
    load_scenario,
    run_scenario,
)
from src.core.smoke_speed import speed_factor_from_extinction


def _run_iso_constant_extinction(extinction_per_m: float):
    scenario = load_scenario("assets/ISO-table21")
    baseline = run_scenario(scenario, seed=420)
    smoke_scenario = scenario.copy()
    if extinction_per_m >= 10.0:
        smoke_scenario.set_max_time(450.0)
    smoke_model = SmokeSpeedModel(
        ConstantExtinctionField(extinction_per_m),
        SmokeSpeedConfig(
            fds_dir=".",
            update_interval_s=0.1,
        ),
    )
    smoke = run_scenario(smoke_scenario, seed=420, smoke_speed_model=smoke_model)
    return baseline, smoke


def test_speed_factor_clear_air_is_one():
    assert speed_factor_from_extinction(0.0) == 1.0


def test_speed_factor_reduces_with_extinction():
    assert speed_factor_from_extinction(1.0) < 1.0
    assert speed_factor_from_extinction(3.0) < speed_factor_from_extinction(1.0)


def test_speed_factor_clamps_to_minimum():
    assert speed_factor_from_extinction(100.0, min_speed_factor=0.2) == 0.2


@pytest.mark.parametrize("extinction_per_m", [0.5, 1.0, 3.0, 7.5, 10.0])
def test_iso_table21_constant_extinction_matches_expected_time_ratio(extinction_per_m):
    baseline, smoke = _run_iso_constant_extinction(extinction_per_m)

    try:
        assert baseline.success
        assert smoke.success
        assert smoke.agents_remaining == 0
        assert smoke.smoke_history

        expected_factor = speed_factor_from_extinction(extinction_per_m)
        observed_ratio = smoke.evacuation_time / baseline.evacuation_time
        expected_ratio = 1.0 / expected_factor

        assert observed_ratio == pytest.approx(expected_ratio, rel=0.08)
        observed_factors = {round(row["speed_factor"], 6) for row in smoke.smoke_history}
        assert observed_factors == {round(expected_factor, 6)}
    finally:
        baseline.cleanup()
        smoke.cleanup()


def test_iso_table21_extinction_sweep_produces_plot(tmp_path: Path):
    extinctions = [0.5, 1.0, 3.0, 7.5, 10.0]
    results = []

    for extinction_per_m in extinctions:
        baseline, smoke = _run_iso_constant_extinction(extinction_per_m)
        try:
            expected_factor = speed_factor_from_extinction(extinction_per_m)
            results.append(
                {
                    "extinction_per_m": extinction_per_m,
                    "baseline_time_s": baseline.evacuation_time,
                    "observed_time_s": smoke.evacuation_time,
                    "expected_time_s": baseline.evacuation_time / expected_factor,
                }
            )
        finally:
            smoke.cleanup()
            baseline.cleanup()

    output = tmp_path / "iso-table21-sweep.png"
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(
        [item["extinction_per_m"] for item in results],
        [item["observed_time_s"] for item in results],
        marker="o",
        label="Observed evacuation time",
    )
    ax.plot(
        [item["extinction_per_m"] for item in results],
        [item["expected_time_s"] for item in results],
        marker="s",
        linestyle="--",
        label="Expected evacuation time",
    )
    ax.set_xlabel("Extinction K [1/m]")
    ax.set_ylabel("Evacuation time [s]")
    ax.set_title("ISO Table 21 extinction sweep")
    ax.legend(loc="best")
    fig.tight_layout()
    fig.savefig(output, dpi=150, bbox_inches="tight")
    plt.close(fig)

    assert output.exists()
    assert output.stat().st_size > 0
