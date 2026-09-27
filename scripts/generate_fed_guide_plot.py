"""Generate the stationary FED guide verification plot."""

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns

from pyfds_evac.core.fed import DefaultFedInputs, accumulate_default_fed


def _build_parser() -> argparse.ArgumentParser:
    """Build the command-line interface for the FED plot generator."""
    parser = argparse.ArgumentParser(
        description="Generate the FDS+Evac stationary FED verification plot."
    )
    parser.add_argument(
        "--output",
        default="artifacts/fed-guide-stationary-cases.png",
        help="Output PNG path",
    )
    return parser


def _guide_stationary_cases():
    """Return the guide's stationary gas cases keyed by plot label."""
    return {
        "Combined (2, 0.1, 15)%": DefaultFedInputs(0.1, 2.0, 15.0),
        "O2 Only (0, 0, 12)%": DefaultFedInputs(0.0, 0.0, 12.0),
        "CO Only (0, 0.1, 21)%": DefaultFedInputs(0.1, 0.0, 21.0),
        "CO2-Enhanced (3.43, 0.1, 21)%": DefaultFedInputs(0.1, 3.43, 21.0),
    }


def main() -> int:
    """Generate and save the guide-style stationary FED figure."""
    args = _build_parser().parse_args()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    times_s = np.linspace(0.0, 100.0, 101)
    sns.set_theme(font_scale=1.0, style="whitegrid", font="DejaVu Sans")
    colours = ["#d73027", "#fc8d59", "#4575b4", "#1f253f"]
    styles = ["-", "--", "-.", ":"]
    fig, ax = plt.subplots(figsize=(9, 6), dpi=150)
    finals = {}
    for (label, inputs), colour, style in zip(
        _guide_stationary_cases().items(), colours, styles
    ):
        fed_curve = [accumulate_default_fed(inputs, duration_s=t) for t in times_s]
        finals[label] = fed_curve[-1]
        ax.plot(
            times_s, fed_curve, linewidth=2, color=colour, linestyle=style, label=label
        )

    co_only = finals["CO Only (0, 0.1, 21)%"]
    co2_boost = finals["CO2-Enhanced (3.43, 0.1, 21)%"]
    ax.text(
        0.98,
        0.02,
        f"3.43 % CO2 multiplies the CO-only dose by {co2_boost / co_only:.1f} "
        f"(FED {co2_boost:.3f} vs {co_only:.3f} at {times_s[-1]:.0f} s)",
        transform=ax.transAxes,
        ha="right",
        va="bottom",
        fontsize=9,
        color="dimgrey",
        style="italic",
    )
    ax.set_xlabel("Time [s]", color="dimgrey")
    ax.set_ylabel("FED Index [-]", color="dimgrey")
    ax.set_title(
        "FDS+Evac stationary FED verification cases",
        loc="left",
        pad=7,
        color="dimgrey",
    )
    ax.legend(
        loc="upper left",
        frameon=True,
        facecolor="white",
        framealpha=0.8,
        edgecolor="lightgrey",
        labelcolor="dimgrey",
    )
    ax.tick_params(axis="both", which="both", length=0, labelcolor="dimgrey")
    ax.patch.set_edgecolor("lightgrey")
    ax.patch.set_linewidth(0.8)
    sns.despine(left=True, bottom=True)
    fig.tight_layout()
    fig.savefig(output, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
