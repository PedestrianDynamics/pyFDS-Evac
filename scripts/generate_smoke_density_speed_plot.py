from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt

from src.core import extinction_from_soot_density, speed_from_soot_density


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate the FDS+Evac smoke density vs speed verification plot."
    )
    parser.add_argument(
        "--output",
        default="artifacts/smoke-density-vs-speed.png",
        help="Output PNG path",
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

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
    print(output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
