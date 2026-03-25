"""Generate the stationary FED guide verification plot."""

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from src.core.fed import DefaultFedInputs, accumulate_default_fed


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
    print(output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
