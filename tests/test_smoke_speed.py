from pathlib import Path

import matplotlib.pyplot as plt
import pytest

from src.core import (
    ConstantExtinctionField,
    SmokeSpeedConfig,
    SmokeSpeedModel,
    extinction_from_soot_density,
    load_scenario,
    run_scenario,
    speed_from_soot_density,
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


def test_soot_density_conversion_matches_fds_evac_default():
    assert extinction_from_soot_density(500.0) == pytest.approx(4.35)
    assert extinction_from_soot_density(1000.0) == pytest.approx(8.7)
    assert extinction_from_soot_density(1500.0) == pytest.approx(13.05)


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
        observed_factors = {
            round(row["speed_factor"], 6) for row in smoke.smoke_history
        }
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


def test_smoke_updates_do_not_release_agents_during_premovement():
    scenario = load_scenario("assets/ISO-table21")
    for distribution in scenario.raw["distributions"].values():
        params = distribution["parameters"]
        params["use_premovement"] = True
        params["premovement_distribution"] = "uniform"
        params["premovement_param_a"] = 30.0
        params["premovement_param_b"] = 30.0
    scenario.set_max_time(2.0)

    smoke_model = SmokeSpeedModel(
        ConstantExtinctionField(1.0),
        SmokeSpeedConfig(
            fds_dir=".",
            update_interval_s=0.1,
        ),
    )
    result = run_scenario(scenario, seed=420, smoke_speed_model=smoke_model)

    try:
        assert result.smoke_history
        positions_by_agent = {}
        for row in result.smoke_history:
            positions_by_agent.setdefault(int(row["agent_id"]), set()).add(
                (round(float(row["x"]), 6), round(float(row["y"]), 6))
            )
            assert float(row["base_speed"]) > 0.0

        assert positions_by_agent
        assert all(len(positions) == 1 for positions in positions_by_agent.values())
    finally:
        result.cleanup()


def test_fds_evac_guide_smoke_density_points_match_theory():
    base_speed = 1.5
    soot_densities = [0.0, 500.0, 1000.0, 1500.0]
    expected_speeds = [
        1.5,
        1.5 * (1.0 + (-0.057 / 0.706) * 4.35),
        1.5 * (1.0 + (-0.057 / 0.706) * 8.7),
        0.15,
    ]

    observed = [
        speed_from_soot_density(base_speed, soot_density, min_speed_factor=0.1)
        for soot_density in soot_densities
    ]

    assert observed == pytest.approx(expected_speeds, rel=1e-9)


def test_fds_evac_guide_smoke_density_plot_is_generated(tmp_path: Path):
    base_speed = 1.5
    soot_points = [0.0, 500.0, 1000.0, 1500.0]
    theory_x = list(range(0, 2201, 25))
    theory_y = [
        speed_from_soot_density(base_speed, soot_density, min_speed_factor=0.1)
        for soot_density in theory_x
    ]
    model_y = [
        speed_from_soot_density(base_speed, soot_density, min_speed_factor=0.1)
        for soot_density in soot_points
    ]
    extinction_points = [extinction_from_soot_density(value) for value in soot_points]

    output = tmp_path / "smoke-density-vs-speed.png"
    fig, ax = plt.subplots(figsize=(9, 6))
    ax.plot(theory_x, theory_y, color="black", linewidth=2, label="Theory")
    ax.scatter(
        soot_points,
        model_y,
        color="red",
        edgecolors="black",
        s=70,
        label="pyFDS-Evac",
        zorder=3,
    )
    ax.set_xlabel("Soot density (mg/m$^3$)")
    ax.set_ylabel("Speed (m/s)")
    ax.set_ylim(0.0, 1.6)
    ax.grid(True, alpha=0.3)
    top = ax.twiny()
    top.set_xlim(ax.get_xlim())
    top.set_xticks(soot_points)
    top.set_xticklabels(
        [f"{value:.2f}".rstrip("0").rstrip(".") for value in extinction_points]
    )
    top.set_xlabel("Extinction coefficient (1/m)")
    ax.legend(loc="best")
    fig.tight_layout()
    fig.savefig(output, dpi=150, bbox_inches="tight")
    plt.close(fig)

    assert output.exists()
    assert output.stat().st_size > 0
