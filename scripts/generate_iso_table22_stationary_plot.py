"""Generate the ISO Table 22 stationary FED verification plot."""

import argparse
import math
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from pyfds_evac.core import load_scenario, run_scenario
from pyfds_evac.core.fed import (
    DefaultFedInputs,
    accumulate_default_fed,
    default_fed_rate_per_minute,
    time_to_fed_threshold_s,
)


class _ConstantInputsFedModel:
    """Drive the runtime with constant gas inputs for stationary verification."""

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


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate the ISO Table 22 stationary FED verification plot."
    )
    parser.add_argument(
        "--output",
        default="artifacts/iso-table22-stationary-fed.png",
        help="Output PNG path",
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    inputs = DefaultFedInputs(
        co_volume_fraction_percent=0.10,
        co2_volume_fraction_percent=5.0,
        o2_volume_fraction_percent=12.0,
    )
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
        crossing_time_s = next(
            row["time_s"] for row in result.fed_history if row["fed_cumulative"] >= 1.0
        )

        theory_times = np.linspace(0.0, runtime_times[-1], 400)
        theory_fed = [
            accumulate_default_fed(inputs, duration_s=float(t)) for t in theory_times
        ]

        residual = [
            f - accumulate_default_fed(inputs, duration_s=float(t))
            for t, f in zip(runtime_times, runtime_fed)
        ]
        dt = result.metrics["dt"]

        fig, (ax, ax_r) = plt.subplots(
            2, 1, figsize=(8, 6.5), height_ratios=[3, 1], sharex=True
        )
        ax.plot(
            theory_times,
            theory_fed,
            color="tab:blue",
            linestyle="--",
            linewidth=3,
            label="Analytical FED",
            zorder=3,
        )
        ax.step(
            runtime_times,
            runtime_fed,
            where="post",
            color="tab:orange",
            linewidth=2,
            alpha=0.9,
            label="Runtime FED",
            zorder=2,
        )
        ax.plot(
            runtime_times[:: max(1, len(runtime_times) // 12)],
            runtime_fed[:: max(1, len(runtime_fed) // 12)],
            linestyle="None",
            marker="o",
            markersize=4,
            color="tab:orange",
            zorder=4,
            label="Runtime samples",
        )
        ax.axhline(1.0, color="black", linestyle=":", linewidth=1.5, label="FED = 1")
        ax.axvline(
            analytic_time_s,
            color="tab:green",
            linestyle="--",
            linewidth=1.5,
            label="Analytical threshold time",
        )
        ax.axvline(
            crossing_time_s,
            color="tab:red",
            linestyle="--",
            linewidth=1.5,
            label="Runtime threshold time",
        )
        ax.set_ylabel("FED Index [-]")
        ax.set_title(
            "ISO 20414 Table 22 - stationary FED verification\n"
            f"analytical FED=1 at {analytic_time_s:.1f} s, "
            f"runtime at {crossing_time_s:.1f} s "
            f"(difference {abs(crossing_time_s - analytic_time_s):.2f} s, "
            f"one timestep = {dt:g} s)"
        )
        ax.legend(loc="upper left", fontsize=8)
        ax.grid(alpha=0.25)

        # The two threshold lines coincide, which is the result -- but drawn
        # alone they look like one series is missing, so state both numerically
        # in the title above and show the error here instead.
        ax_r.axhspan(
            -dt,
            dt,
            color="tab:green",
            alpha=0.12,
            label=f"one timestep (+/-{dt:g} s worth of dose)",
        )
        ax_r.axhline(0.0, color="grey", linewidth=0.8)
        ax_r.plot(runtime_times, residual, color="tab:orange")
        ax_r.set_xlabel("Time [s]")
        ax_r.set_ylabel("runtime - analytical\nFED [-]")
        ax_r.legend(loc="best", fontsize=8)
        ax_r.grid(alpha=0.25)

        worst = max(abs(v) for v in residual)
        print(
            f"worst FED residual: {worst:.2e}  (crossing differs by "
            f"{abs(crossing_time_s - analytic_time_s):.2f} s, dt = {dt:g} s)"
        )
        fig.tight_layout()
        fig.savefig(output, dpi=150, bbox_inches="tight")
        plt.close(fig)
    finally:
        result.cleanup()

    print(output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
