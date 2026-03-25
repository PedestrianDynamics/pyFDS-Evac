"""Generate the ISO Table 21 extinction sweep verification plot."""

import argparse
from pathlib import Path

import matplotlib.pyplot as plt

from src.core import (
    ConstantExtinctionField,
    SmokeSpeedConfig,
    SmokeSpeedModel,
    load_scenario,
    run_scenario,
)
from src.core.smoke_speed import speed_factor_from_extinction


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


def _run_iso_constant_extinction(extinction_per_m: float):
    """Run the baseline and constant-extinction ISO Table 21 scenarios."""
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


def main() -> int:
    """Generate and save the ISO Table 21 extinction sweep figure."""
    args = _build_parser().parse_args()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    extinctions = [0.5, 1.0, 3.0, 7.5, 10.0]
    results = []

    for extinction_per_m in extinctions:
        baseline, smoke = _run_iso_constant_extinction(extinction_per_m)
        try:
            expected_factor = speed_factor_from_extinction(extinction_per_m)
            results.append(
                {
                    "extinction_per_m": extinction_per_m,
                    "observed_time_s": smoke.evacuation_time,
                    "expected_time_s": baseline.evacuation_time / expected_factor,
                }
            )
        finally:
            smoke.cleanup()
            baseline.cleanup()

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
    print(output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
