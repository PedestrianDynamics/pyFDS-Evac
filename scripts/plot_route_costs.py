"""Plot composite route cost vs time for each exit.

Usage:
    uv run python scripts/plot_route_costs.py route_costs.csv [routes.csv]
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


def main(cost_csv: str, routes_csv: str | None = None) -> None:
    df = pd.read_csv(cost_csv)

    # Mean composite cost per (time, exit) across all agents
    mean_cost = df.groupby(["time_s", "exit_id"])["composite_cost"].mean().reset_index()

    exits = sorted(mean_cost["exit_id"].unique())
    colors = ["tab:blue", "tab:orange", "tab:green", "tab:red"]

    fig, ax = plt.subplots(figsize=(10, 5))

    for i, exit_id in enumerate(exits):
        sub = mean_cost[mean_cost["exit_id"] == exit_id].sort_values("time_s")
        label = exit_id.replace("_", " ")
        ax.plot(
            sub["time_s"],
            sub["composite_cost"],
            label=label,
            color=colors[i % len(colors)],
            lw=2,
        )

    # Overlay route switches if provided
    if routes_csv and Path(routes_csv).exists():
        switches = pd.read_csv(routes_csv)
        if not switches.empty:
            for _, row in switches.iterrows():
                ax.axvline(row["time_s"], color="gray", lw=0.6, alpha=0.4)
            # Legend entry for switches
            ax.axvline(-1, color="gray", lw=0.6, alpha=0.4, label="route switch")

    ax.set_xlabel("Simulation time (s)")
    ax.set_ylabel("Mean composite cost")
    ax.set_title("Route cost vs time (mean over active agents)")
    ax.legend()
    ax.grid(True, alpha=0.3)

    out = Path(cost_csv).with_name("route_costs_plot.png")
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    print(f"Saved: {out}")
    plt.show()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    routes = sys.argv[2] if len(sys.argv) > 2 else None
    main(sys.argv[1], routes)
