#!/usr/bin/env python3
"""Plot how w_smoke reprices the two T-junction routes.

Shows the crossover: the near exit is cheaper on distance alone, and stays
cheaper under *uniform* smoke at any weight, but asymmetric smoke on its arm
overtakes it. The gap between the two panels is the point -- smoke only shifts
the choice when it is unevenly distributed.

Usage:
    .venv/bin/python scripts/generate_smoke_weight_sweep.py [-o OUT.png]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

sys.path.insert(0, "tests")
from test_rerouting_smoke_sweep import (  # noqa: E402
    FAR_EXIT,
    NEAR_EXIT,
    SmokeOnTheNearArm,
    UniformSmoke,
    _costs,
    _graph,
)


def main(out_path: Path) -> None:
    graph = _graph()
    weights = [w / 20.0 for w in range(0, 61)]

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.4), sharey=True)
    for ax, field, title in (
        (axes[0], SmokeOnTheNearArm(), "smoke on the near exit's arm"),
        (axes[1], UniformSmoke(4.0), "uniform smoke everywhere"),
    ):
        near = [_costs(graph, field, w)[NEAR_EXIT] for w in weights]
        far = [_costs(graph, field, w)[FAR_EXIT] for w in weights]
        ax.plot(weights, near, label=f"{NEAR_EXIT} (10 m)", color="#d62728", lw=2)
        ax.plot(weights, far, label=f"{FAR_EXIT} (20 m)", color="#2b7bba", lw=2)
        crossover = next((w for w, n, f in zip(weights, near, far) if n > f), None)
        if crossover is not None:
            ax.axvline(crossover, ls="--", color="#666", lw=1)
            ax.annotate(
                f"flips at w_smoke = {crossover:.2f}",
                xy=(crossover, ax.get_ylim()[1] * 0.5),
                xytext=(crossover + 0.3, ax.get_ylim()[1] * 0.55),
                fontsize=9,
            )
        else:
            ax.text(
                0.5,
                0.9,
                "never flips",
                transform=ax.transAxes,
                ha="center",
                fontsize=10,
                color="#666",
            )
        ax.set_title(title, fontsize=10)
        ax.set_xlabel("w_smoke")
        ax.legend(fontsize=8, frameon=False)
    axes[0].set_ylabel("composite route cost")
    fig.suptitle(
        "Smoke shifts the exit choice only when it is asymmetric\n"
        "assets/t_junction: the near exit is 10 m from the junction, the far one 20 m",
        fontsize=11,
    )
    fig.tight_layout(rect=(0.0, 0.0, 1.0, 0.90))
    fig.savefig(out_path, dpi=140)
    print(f"Wrote: {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-o", "--out", default="assets/t_junction/smoke_weight_sweep.png"
    )
    main(Path(parser.parse_args().out))
