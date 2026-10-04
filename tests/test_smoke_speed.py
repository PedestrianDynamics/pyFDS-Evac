import math
from pathlib import Path

import matplotlib.pyplot as plt
import pytest

from pyfds_evac.core import (
    ConstantExtinctionField,
    SmokeSpeedConfig,
    SmokeSpeedModel,
    extinction_from_soot_density,
    load_scenario,
    run_scenario,
    speed_from_soot_density,
)
from pyfds_evac.core.smoke_speed import (
    speed_factor_from_extinction,
    speed_factor_from_extinction_fridolf,
)


def _run_iso_constant_extinction(extinction_per_m: float, v0: float | None = None):
    scenario = load_scenario("assets/ISO-table21")
    if v0 is not None:
        for distribution in scenario.raw["distributions"].values():
            distribution["parameters"]["v0"] = v0
    # A slower occupant needs proportionally longer, on top of the smoke factor.
    stretch = 1.0 if v0 is None else 1.25 / v0
    baseline = scenario.copy()
    baseline.set_max_time(450.0 * stretch)
    baseline = run_scenario(baseline, seed=420)
    smoke_scenario = scenario.copy()
    smoke_scenario.set_max_time(
        450.0 * stretch / max(0.1, speed_factor_from_extinction(extinction_per_m))
    )
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


# Fridolf et al. (2018), method 3: w = min(w_free, max(0.2, w_free - 0.34 (3 - V)))
# with V = C / K and C = 3. Rows: V [m] -> w [m/s] at w_free = 1.19 and 1.35.
FRIDOLF_VISIBILITIES = (0.5, 1.0, 2.0, 3.0, 4.0, 5.0, math.inf)
FRIDOLF_TABLE = {
    1.19: (0.340, 0.510, 0.850, 1.190, 1.190, 1.190, 1.190),
    1.35: (0.500, 0.670, 1.010, 1.350, 1.350, 1.350, 1.350),
}
# (w_free, V, w) at the paper's w_free values (methods 1-3), computed from its
# equation; 1.2 -> 0.86 m/s at 2 m is the worked example of Fridolf et al. 2019.
FRIDOLF_PAPER_POINTS = (
    (1.35, 0.0, 0.33),
    (1.35, 2.0, 1.01),
    (1.0, 2.0, 0.66),
    (1.0, 1.0, 0.32),
    (1.0, 0.5, 0.2),
    (1.0, 0.0, 0.2),
    (1.2, 2.0, 0.86),
)


def _extinction(visibility_m: float, c: float = 3.0) -> float:
    return 0.0 if math.isinf(visibility_m) else c / visibility_m


class TestFridolfSpeedFactor:
    """Fridolf et al. (2018) additive speed-visibility law with absolute floor."""

    def test_clear_air_is_one(self):
        assert speed_factor_from_extinction_fridolf(0.0) == 1.0

    @pytest.mark.parametrize("v0", sorted(FRIDOLF_TABLE))
    def test_table_matches_paper(self, v0):
        for visibility, w in zip(FRIDOLF_VISIBILITIES, FRIDOLF_TABLE[v0]):
            factor = speed_factor_from_extinction_fridolf(
                _extinction(visibility), visibility_factor_c=3.0, free_speed_m_per_s=v0
            )
            assert v0 * factor == pytest.approx(w, rel=1e-12)

    @pytest.mark.parametrize(("v0", "visibility", "w"), FRIDOLF_PAPER_POINTS)
    def test_paper_points(self, v0, visibility, w):
        # V = 0 is approached with a very large K.
        k = 1e12 if visibility == 0.0 else _extinction(visibility)
        factor = speed_factor_from_extinction_fridolf(k, free_speed_m_per_s=v0)
        assert v0 * factor == pytest.approx(w, rel=1e-9)

    @pytest.mark.parametrize("visibility", [3.0, 4.0, 10.0])
    def test_no_slowing_at_or_above_3_m(self, visibility):
        """The discriminating case: V/(V+2) gave < 1 here."""
        cfg = SmokeSpeedConfig(fds_dir=".", speed_law="fridolf")
        model = SmokeSpeedModel(ConstantExtinctionField(_extinction(visibility)), cfg)
        _, factor = model.sample(0.0, 0.0, 0.0)
        assert factor == 1.0

    @pytest.mark.parametrize(("v0", "visibility"), [(1.19, 0.05), (1.0, 0.5)])
    def test_floor_is_absolute(self, v0, visibility):
        # w_free - 0.34 (3 - V) < 0.2 here, so w is the 0.2 m/s floor, not 0.2 v0.
        factor = speed_factor_from_extinction_fridolf(
            _extinction(visibility), free_speed_m_per_s=v0
        )
        assert v0 * factor == pytest.approx(0.2, rel=1e-12)

    @pytest.mark.parametrize("k", [math.nan, math.inf, -1.0])
    def test_non_finite_or_negative_k_is_clear_air(self, k):
        # Same convention as the Lund law.
        assert speed_factor_from_extinction_fridolf(k, free_speed_m_per_s=1.19) == 1.0
        assert speed_factor_from_extinction(k) == 1.0

    @pytest.mark.parametrize("v0", [0.1, 0.15, 0.2])
    def test_floor_never_raises_speed_above_v0(self, v0):
        for k in (0.5, 3.0, 6.0, 1e6):
            factor = speed_factor_from_extinction_fridolf(k, free_speed_m_per_s=v0)
            assert factor == 1.0
            assert v0 * factor <= v0

    def test_zero_free_speed_returns_one(self):
        assert speed_factor_from_extinction_fridolf(6.0, free_speed_m_per_s=0.0) == 1.0

    def test_constants_from_config(self):
        cfg = SmokeSpeedConfig()
        assert cfg.fridolf_slope == 0.34
        assert cfg.fridolf_visibility_threshold_m == 3.0
        assert cfg.fridolf_min_speed_m_per_s == 0.2

    @pytest.mark.parametrize("v0", [0.5, 1.0, 1.19, 1.35, 1.85])
    def test_factor_is_non_increasing_in_extinction(self, v0):
        ks = [0.0, 0.1, 0.5, 1.0, 1.2, 1.5, 2.0, 3.0, 6.0, 10.0, 60.0, 1e6]
        factors = [
            speed_factor_from_extinction_fridolf(k, free_speed_m_per_s=v0) for k in ks
        ]
        assert all(a >= b for a, b in zip(factors, factors[1:]))
        assert factors[-1] < factors[0]

    @pytest.mark.parametrize("c", [0.0, -3.0, math.nan, math.inf])
    def test_invalid_visibility_factor_is_rejected(self, c):
        with pytest.raises(ValueError, match="visibility_factor_c"):
            speed_factor_from_extinction_fridolf(1.0, visibility_factor_c=c)

    def test_larger_c_gives_higher_factor(self):
        # Higher C means better visibility at the same K
        f_c3 = speed_factor_from_extinction_fridolf(3.0, visibility_factor_c=3.0)
        f_c8 = speed_factor_from_extinction_fridolf(3.0, visibility_factor_c=8.0)
        assert f_c8 > f_c3


class TestSmokeSpeedModelFridolf:
    """SmokeSpeedModel dispatches to Fridolf when speed_law='fridolf'."""

    def test_fridolf_law_uses_free_speed(self):
        # V = 2 m: w = 1.19 - 0.34 = 0.85 m/s.
        field = ConstantExtinctionField(1.5)
        cfg = SmokeSpeedConfig(
            fds_dir=".", speed_law="fridolf", visibility_factor_c=3.0
        )
        model = SmokeSpeedModel(field, cfg)
        _, factor = model.sample(0.0, 0.0, 0.0, free_speed_m_per_s=1.19)
        assert 1.19 * factor == pytest.approx(0.85, rel=1e-12)

    def test_fridolf_without_free_speed_is_method_1(self):
        # No v0 given: w_free = 1 m/s (method 1), so w = 0.66 m/s at V = 2 m.
        field = ConstantExtinctionField(1.5)
        cfg = SmokeSpeedConfig(fds_dir=".", speed_law="fridolf")
        _, factor = SmokeSpeedModel(field, cfg).sample(0.0, 0.0, 0.0)
        assert factor == pytest.approx(0.66, rel=1e-12)

    def test_lund_ignores_free_speed(self):
        cfg = SmokeSpeedConfig(fds_dir=".")
        model = SmokeSpeedModel(ConstantExtinctionField(1.0), cfg)
        _, f1 = model.sample(0.0, 0.0, 0.0, free_speed_m_per_s=1.19)
        _, f2 = model.sample(0.0, 0.0, 0.0)
        assert f1 == f2 == speed_factor_from_extinction(1.0)

    def test_three_argument_sample_override_still_works(self):
        """A subclass whose sample() predates free_speed_m_per_s keeps working."""

        class LegacyModel(SmokeSpeedModel):
            def sample(self, time_s, x, y):
                return 1.0, 0.5

        model = LegacyModel(ConstantExtinctionField(1.0), SmokeSpeedConfig())
        assert model.speed_factor(0.0, 0.0, 0.0) == 0.5
        assert model.speed_factor(0.0, 0.0, 0.0, free_speed_m_per_s=1.19) == 0.5

    @pytest.mark.parametrize("law", ["Fridolf", "LUND", "", " lund", None])
    def test_unknown_speed_law_is_rejected(self, law):
        """An unknown speed_law raises instead of running lund (#305)."""
        with pytest.raises(ValueError, match=r"Unknown speed_law"):
            SmokeSpeedConfig(fds_dir=".", speed_law=law)

    @pytest.mark.parametrize("law", ["lund", "fridolf"])
    def test_known_speed_law_is_accepted(self, law):
        assert SmokeSpeedConfig(fds_dir=".", speed_law=law).speed_law == law

    def test_sample_rejects_a_mutated_speed_law(self):
        """The issue's case: 'Fridolf' gave the lund 0.8385, not 0.592."""
        cfg = SmokeSpeedConfig(fds_dir=".")
        cfg.speed_law = "Fridolf"
        model = SmokeSpeedModel(ConstantExtinctionField(2.0), cfg)
        with pytest.raises(ValueError, match=r"Unknown speed_law 'Fridolf'"):
            model.sample(0.0, 0.0, 0.0, free_speed_m_per_s=1.25)

    def test_lund_law_used_by_default(self):
        field = ConstantExtinctionField(0.0)
        cfg = SmokeSpeedConfig(fds_dir=".")
        model = SmokeSpeedModel(field, cfg)
        _, factor = model.sample(0.0, 0.0, 0.0)
        assert factor == pytest.approx(1.0)


def test_run_scenario_accepts_three_argument_sample():
    """run_scenario must not pass free_speed_m_per_s to a sample() without it."""

    class LegacyModel(SmokeSpeedModel):
        def sample(self, time_s, x, y):
            return 1.0, 0.5

    scenario = load_scenario("assets/ISO-table21")
    scenario.set_max_time(3.0)
    model = LegacyModel(ConstantExtinctionField(1.0), SmokeSpeedConfig(fds_dir="."))
    result = run_scenario(scenario, seed=420, smoke_speed_model=model)
    try:
        assert result.smoke_history
        assert all(row["speed_factor"] == 0.5 for row in result.smoke_history)
    finally:
        result.cleanup()


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


@pytest.mark.parametrize("v0", [1.0, 0.75, 0.5, 0.25])
def test_iso_table21_holds_across_unimpeded_walking_speeds(v0):
    """ISO 20414 Table 21 asks for both axes, not just extinction.

    "different combinations of unimpeded walking speeds ... and constant
    extinction coefficients need to be tested. Examples of such values can be
    1,0 m/s, 0,75 m/s, 0,5 m/s, and 0,25 m/s for the unimpeded walking speeds."

    This is a null test by construction: the smoke factor multiplies ``v0``, so
    the time *ratio* must not depend on ``v0`` at all. That is exactly why it is
    worth running -- it fails if a clamp is applied to an absolute speed rather
    than to the factor, which is the shape of defect the FIC speed factor turned
    out to have.
    """
    baseline, smoke = _run_iso_constant_extinction(1.0, v0=v0)

    try:
        assert baseline.success and smoke.success
        assert smoke.agents_remaining == 0

        expected_factor = speed_factor_from_extinction(1.0)
        observed_ratio = smoke.evacuation_time / baseline.evacuation_time
        assert observed_ratio == pytest.approx(1.0 / expected_factor, rel=0.08)
        observed = {round(row["speed_factor"], 6) for row in smoke.smoke_history}
        assert observed == {round(expected_factor, 6)}, (
            "the factor must not depend on the unimpeded speed"
        )
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


def test_smoke_updates_record_base_speed_during_premovement():
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
        for row in result.smoke_history:
            assert float(row["base_speed"]) > 0.0
            assert float(row["desired_speed"]) < float(row["base_speed"])
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
