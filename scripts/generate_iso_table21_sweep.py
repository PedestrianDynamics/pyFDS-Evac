"""Generate the ISO 20414 Table 21 verification figure.

Both axes the standard asks for, and the residual against the tolerance.

A plot of expected-versus-observed alone is not checkable: two curves lying on
top of each other tell you they agree, not by how much. The residual panels show
the error and draw the 8 % band the tests assert, so a reader can see the margin
rather than take it on trust.

ISO 20414 Table 21 asks the test be repeated over "different combinations of
unimpeded walking speeds ... and constant extinction coefficients". The left
column sweeps extinction at 1.25 m/s; the right sweeps speed at k = 1.0/m,
where the expected ratio is constant because the factor multiplies v0.
"""

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import seaborn as sns

from pyfds_evac.core import (
    ConstantExtinctionField,
    SmokeSpeedConfig,
    SmokeSpeedModel,
    load_scenario,
    run_scenario,
)
from pyfds_evac.core.smoke_speed import speed_factor_from_extinction


def _build_parser() -> argparse.ArgumentParser:
    """Build the command-line interface for the sweep plot generator."""
    parser = argparse.ArgumentParser(
        description="Generate the ISO Table 21 sweep plot."
    )
    parser.add_argument(
        "--output",
        default="artifacts/iso-table21-sweep.png",
        help="Output PNG path",
    )
    return parser


def _run_iso_constant_extinction(extinction_per_m: float, v0: float | None = None):
    """Run the baseline and constant-extinction ISO Table 21 scenarios."""
    scenario = load_scenario("assets/ISO-table21")
    if v0 is not None:
        for distribution in scenario.raw["distributions"].values():
            distribution["parameters"]["v0"] = v0
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


def main() -> int:
    """Generate and save the ISO Table 21 extinction sweep figure."""
    args = _build_parser().parse_args()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    tolerance = 0.08

    extinctions = [0.5, 1.0, 3.0, 7.5, 10.0]
    speeds = [1.25, 1.0, 0.75, 0.5, 0.25]

    k_rows = []
    for extinction_per_m in extinctions:
        baseline, smoke = _run_iso_constant_extinction(extinction_per_m)
        try:
            factor = speed_factor_from_extinction(extinction_per_m)
            k_rows.append(
                {
                    "x": extinction_per_m,
                    "observed": smoke.evacuation_time,
                    "expected": baseline.evacuation_time / factor,
                    "ratio": smoke.evacuation_time / baseline.evacuation_time,
                    "expected_ratio": 1.0 / factor,
                }
            )
        finally:
            smoke.cleanup()
            baseline.cleanup()

    v_rows = []
    expected_ratio_at_k1 = 1.0 / speed_factor_from_extinction(1.0)
    for v0 in speeds:
        baseline, smoke = _run_iso_constant_extinction(1.0, v0=v0)
        try:
            v_rows.append(
                {
                    "x": v0,
                    "ratio": smoke.evacuation_time / baseline.evacuation_time,
                    "expected_ratio": expected_ratio_at_k1,
                }
            )
        finally:
            smoke.cleanup()
            baseline.cleanup()

    def residual_pct(rows):
        return [100.0 * (r["ratio"] / r["expected_ratio"] - 1.0) for r in rows]

    sns.set_theme(font_scale=1.0, style="whitegrid", font="DejaVu Sans")
    expected_colour = "#1f253f"
    observed_colour = "#d73027"
    band_colour = "#33a02c"
    legend_style = dict(
        frameon=True,
        facecolor="white",
        framealpha=0.8,
        edgecolor="lightgrey",
        labelcolor="dimgrey",
        fontsize=8,
    )

    fig, axes = plt.subplots(2, 2, figsize=(12, 7), height_ratios=[2, 1], dpi=150)

    ax = axes[0][0]
    ax.plot(
        [r["x"] for r in k_rows],
        [r["expected"] for r in k_rows],
        "--",
        color=expected_colour,
        linewidth=2,
        label="Expected (hand calculation)",
        zorder=3,
    )
    ax.scatter(
        [r["x"] for r in k_rows],
        [r["observed"] for r in k_rows],
        color=observed_colour,
        edgecolors="white",
        linewidths=0.8,
        s=60,
        label="Observed (simulation)",
        zorder=4,
    )
    ax.set_ylabel("Evacuation time [s]", color="dimgrey")
    ax.set_title(
        r"$\bf{(a)}$ Extinction sweep at $v_0$ = 1.25 m/s", loc="left", fontsize=11
    )
    ax.legend(loc="upper left", **legend_style)

    ax = axes[1][0]
    ax.axhspan(
        -100 * tolerance,
        100 * tolerance,
        color=band_colour,
        alpha=0.12,
        label=f"tolerance the test asserts (+/-{tolerance:.0%})",
    )
    ax.axhline(0.0, color="grey", linewidth=0.8)
    ax.plot(
        [r["x"] for r in k_rows],
        residual_pct(k_rows),
        "o-",
        color=observed_colour,
        markeredgecolor="white",
    )
    ax.set_xlabel("Extinction K [1/m]", color="dimgrey")
    ax.set_ylabel("time-ratio error [%]", color="dimgrey")
    ax.set_ylim(-100 * tolerance * 1.6, 100 * tolerance * 1.6)
    ax.set_title(r"$\bf{(c)}$ Residual, extinction sweep", loc="left", fontsize=11)
    ax.legend(loc="upper right", **legend_style)

    ax = axes[0][1]
    ax.axhline(
        expected_ratio_at_k1,
        linestyle="--",
        color=expected_colour,
        linewidth=2,
        label="Expected ratio (independent of $v_0$)",
        zorder=3,
    )
    ax.scatter(
        [r["x"] for r in v_rows],
        [r["ratio"] for r in v_rows],
        color=observed_colour,
        edgecolors="white",
        linewidths=0.8,
        s=60,
        label="Observed ratio",
        zorder=4,
    )
    ax.set_ylabel("$t_{smoke}$ / $t_{clear}$  [-]", color="dimgrey")
    # Pin the scale to the tolerance. Left to autoscale, matplotlib zooms to the
    # spread of near-identical values and adds an offset, so points agreeing to
    # 0,06 % look wildly scattered -- the opposite of what the panel shows.
    ax.set_ylim(
        expected_ratio_at_k1 * (1 - 2 * tolerance),
        expected_ratio_at_k1 * (1 + 2 * tolerance),
    )
    ax.axhspan(
        expected_ratio_at_k1 * (1 - tolerance),
        expected_ratio_at_k1 * (1 + tolerance),
        color=band_colour,
        alpha=0.12,
    )
    ax.set_title(
        r"$\bf{(b)}$ Walking-speed sweep at K = 1.0/m", loc="left", fontsize=11
    )
    ax.legend(loc="best", **legend_style)

    ax = axes[1][1]
    ax.axhspan(-100 * tolerance, 100 * tolerance, color=band_colour, alpha=0.12)
    ax.axhline(0.0, color="grey", linewidth=0.8)
    ax.plot(
        [r["x"] for r in v_rows],
        residual_pct(v_rows),
        "o-",
        color=observed_colour,
        markeredgecolor="white",
    )
    ax.set_xlabel("Unimpeded walking speed $v_0$ [m/s]", color="dimgrey")
    ax.set_ylabel("time-ratio error [%]", color="dimgrey")
    ax.set_ylim(-100 * tolerance * 1.6, 100 * tolerance * 1.6)
    ax.set_title(r"$\bf{(d)}$ Residual, walking-speed sweep", loc="left", fontsize=11)

    for ax in axes.flat:
        ax.tick_params(axis="both", which="both", length=0, labelcolor="dimgrey")
        ax.patch.set_edgecolor("lightgrey")
        ax.patch.set_linewidth(0.8)
    sns.despine(left=True, bottom=True)

    worst = max(abs(v) for v in residual_pct(k_rows) + residual_pct(v_rows))
    fig.suptitle(
        "ISO 20414 Table 21 - reduced visibility vs walking speed",
        color="dimgrey",
    )
    fig.tight_layout(rect=(0.0, 0.03, 1.0, 1.0))
    verdict = "inside" if worst <= 100 * tolerance else "outside"
    fig.text(
        0.99,
        0.01,
        f"worst time-ratio error {worst:.2f} %, {verdict} the "
        f"{tolerance:.0%} tolerance",
        ha="right",
        va="bottom",
        fontsize=9,
        color="dimgrey",
        style="italic",
    )
    fig.savefig(output, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"worst time-ratio error: {worst:.2f} % (tolerance {tolerance:.0%})")
    print(output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
