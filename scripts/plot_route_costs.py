"""Plot composite route cost vs time for each exit.

Usage:
    uv run python scripts/plot_route_costs.py route_costs.csv [routes.csv]
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns


def main(cost_csv: str, routes_csv: str | None = None) -> None:
    df = pd.read_csv(cost_csv)

    # Mean composite cost per (time, exit) across all agents
    mean_cost = df.groupby(["time_s", "exit_id"])["composite_cost"].mean().reset_index()

    exits = sorted(mean_cost["exit_id"].unique())
    colors = ["#d73027", "#4575b4", "#fc8d59", "#1f253f"]
    styles = ["-", "--", "-.", ":"]

    sns.set_theme(font_scale=1.0, style="whitegrid", font="DejaVu Sans")
    fig, ax = plt.subplots(figsize=(10, 5), dpi=150)

    for i, exit_id in enumerate(exits):
        sub = mean_cost[mean_cost["exit_id"] == exit_id].sort_values("time_s")
        label = exit_id.replace("_", " ")
        ax.plot(
            sub["time_s"],
            sub["composite_cost"],
            label=label,
            color=colors[i % len(colors)],
            linestyle=styles[i % len(styles)],
            lw=2,
        )

    # Overlay route switches if provided
    if routes_csv and Path(routes_csv).exists():
        switches = pd.read_csv(routes_csv)
        if not switches.empty:
            for _, row in switches.iterrows():
                ax.axvline(row["time_s"], color="gray", lw=0.6, alpha=0.2, zorder=1)
            # Legend entry for switches
            ax.axvline(
                -1, color="gray", lw=0.6, alpha=0.4, zorder=1, label="route switch"
            )

    overall = mean_cost.groupby("exit_id")["composite_cost"].mean()
    if len(overall) > 1:
        ranked = overall.sort_values()
        ax.text(
            1.0,
            1.01,
            f"{ranked.index[0].replace('_', ' ')} is cheapest on average "
            f"({ranked.iloc[0]:.1f} vs {ranked.iloc[1]:.1f} for "
            f"{ranked.index[1].replace('_', ' ')})",
            transform=ax.transAxes,
            ha="right",
            va="bottom",
            fontsize=9,
            color="dimgrey",
            style="italic",
        )

    ax.set_xlabel("Simulation time (s)", color="dimgrey")
    ax.set_ylabel("Mean composite cost", color="dimgrey")
    ax.set_title(
        "Route cost vs time (mean over active agents)",
        loc="left",
        pad=20,
        color="dimgrey",
    )
    ax.legend(
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

    out = Path(cost_csv).with_name("route_costs_plot.png")
    fig.tight_layout()
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print(f"Saved: {out}")
    plt.show()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    routes = sys.argv[2] if len(sys.argv) > 2 else None
    main(sys.argv[1], routes)
