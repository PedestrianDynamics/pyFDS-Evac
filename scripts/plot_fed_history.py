"""Plot per-agent FED history from ``run.py --output-fed-history``.

Default mode: one cumulative-FED line per agent (spaghetti plot).
``--stack AGENT_ID``: single-agent breakdown that stacks the per-species
contributions (CO, HCN/CN, NOx, irritants, O2), using the columns written
by the extended CSV.

Examples::

    uv run python scripts/plot_fed_history.py fed.csv
    uv run python scripts/plot_fed_history.py fed.csv --show-rate --output fed.png
    uv run python scripts/plot_fed_history.py fed.csv --stack 43 --output fed_43.png
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.figure import Figure

_COMPONENT_COLS = (
    "co_rate_per_min",
    "cn_rate_per_min",
    "nox_rate_per_min",
    "fld_rate_per_min",
    "o2_rate_per_min",
    "hv_co2",
)

_STACK_LABELS = (
    ("co", "CO", "#d35400"),
    ("cn", "HCN/CN", "#8e44ad"),
    ("nox", "NOx", "#16a085"),
    ("fld", "Irritants (FLD)", "#2980b9"),
    ("o2", "O2 hypoxia", "#7f8c8d"),
)


def _read_history(csv_path: Path) -> tuple[dict[int, dict[str, list[float]]], bool]:
    """Group FED rows by agent id and detect whether component columns exist."""
    by_agent: dict[int, dict[str, list[float]]] = {}
    has_components = False
    with csv_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = set(reader.fieldnames or [])
        has_components = all(col in fieldnames for col in _COMPONENT_COLS)
        has_speed = "desired_speed" in fieldnames
        for row in reader:
            agent_id = int(row["agent_id"])
            series = by_agent.setdefault(agent_id, {})
            series.setdefault("t", []).append(float(row["time_s"]))
            series.setdefault("fed", []).append(float(row["fed_cumulative"]))
            series.setdefault("rate", []).append(float(row["fed_rate_per_min"]))
            if has_components:
                for col in _COMPONENT_COLS:
                    series.setdefault(col, []).append(float(row[col]))
            if has_speed:
                series.setdefault("desired_speed", []).append(
                    float(row["desired_speed"])
                )
                series.setdefault("base_speed", []).append(float(row["base_speed"]))
    return by_agent, has_components


def _spaghetti_plot(
    by_agent: dict[int, dict[str, list[float]]],
    *,
    show_rate: bool,
    threshold: float,
    title: str,
) -> Figure:
    """Draw cumulative FED per agent; optionally overlay the rate panel."""
    n_agents = len(by_agent)
    cmap = plt.get_cmap("viridis", max(n_agents, 1))
    if show_rate:
        fig, (ax_fed, ax_rate) = plt.subplots(
            2, 1, sharex=True, figsize=(9, 6), constrained_layout=True
        )
    else:
        fig, ax_fed = plt.subplots(figsize=(9, 4), constrained_layout=True)
        ax_rate = None

    for i, agent_id in enumerate(sorted(by_agent)):
        series = by_agent[agent_id]
        color = cmap(i)
        ax_fed.plot(
            series["t"],
            series["fed"],
            color=color,
            linewidth=0.8,
            alpha=0.75,
            label=f"agent {agent_id}" if n_agents <= 12 else None,
        )
        if ax_rate is not None:
            ax_rate.plot(
                series["t"], series["rate"], color=color, linewidth=0.8, alpha=0.75
            )

    ax_fed.axhline(
        threshold,
        color="#c0392b",
        linestyle="--",
        linewidth=1.0,
        label=f"threshold={threshold}",
    )
    ax_fed.set_ylabel("Cumulative FED")
    ax_fed.set_title(title)
    ax_fed.grid(True, alpha=0.3)
    if n_agents <= 12:
        ax_fed.legend(loc="upper left", fontsize=8)
    else:
        ax_fed.text(
            0.99,
            0.02,
            f"{n_agents} agents",
            transform=ax_fed.transAxes,
            ha="right",
            va="bottom",
            fontsize=9,
        )

    if ax_rate is not None:
        ax_rate.set_ylabel("FED rate (1/min)")
        ax_rate.set_xlabel("time (s)")
        ax_rate.grid(True, alpha=0.3)
    else:
        ax_fed.set_xlabel("time (s)")

    return fig


def _effective_rates(series: dict[str, list[float]]) -> dict[str, list[float]]:
    """Return each term's post-HV contribution to the total rate (1/min).

    Narcotic terms (CO, CN, NOx, FLD) are multiplied by HV_CO2.  O2 hypoxia
    bypasses HV per ISO 13571, so it is reported as-is.
    """
    hv = series["hv_co2"]
    return {
        "co": [r * h for r, h in zip(series["co_rate_per_min"], hv)],
        "cn": [r * h for r, h in zip(series["cn_rate_per_min"], hv)],
        "nox": [r * h for r, h in zip(series["nox_rate_per_min"], hv)],
        "fld": [r * h for r, h in zip(series["fld_rate_per_min"], hv)],
        "o2": list(series["o2_rate_per_min"]),
    }


def _integrate_rates(
    t: list[float], rates: dict[str, list[float]]
) -> dict[str, list[float]]:
    """Integrate each rate series into cumulative FED (trapezoid rule)."""
    cumulative: dict[str, list[float]] = {}
    for key, series in rates.items():
        running = 0.0
        cum = [0.0]
        for i in range(1, len(t)):
            dt_min = max(0.0, t[i] - t[i - 1]) / 60.0
            running += 0.5 * (series[i] + series[i - 1]) * dt_min
            cum.append(running)
        cumulative[key] = cum
    return cumulative


def _stack_plot(
    series: dict[str, list[float]], *, agent_id: int, threshold: float, title: str
) -> Figure:
    """Stack per-species cumulative and rate contributions for one agent."""
    t = series["t"]
    rates = _effective_rates(series)
    cumulative = _integrate_rates(t, rates)

    keys = [key for key, _, _ in _STACK_LABELS]
    colors = [color for _, _, color in _STACK_LABELS]
    labels = [label for _, label, _ in _STACK_LABELS]

    fig, (ax_cum, ax_rate) = plt.subplots(
        2, 1, sharex=True, figsize=(9, 6.5), constrained_layout=True
    )

    ax_cum.stackplot(
        t,
        *[cumulative[k] for k in keys],
        labels=labels,
        colors=colors,
        alpha=0.85,
    )
    ax_cum.plot(t, series["fed"], color="black", linewidth=1.0, label="total (logged)")
    peak_fed = max(series["fed"]) if series["fed"] else 0.0
    if peak_fed >= 0.1 * threshold:
        ax_cum.axhline(
            threshold,
            color="#c0392b",
            linestyle="--",
            linewidth=1.0,
            label=f"threshold={threshold}",
        )
    ax_cum.set_ylabel(f"Cumulative FED  (peak={peak_fed:.2e})")
    ax_cum.set_title(title)
    ax_cum.legend(loc="upper left", fontsize=8)
    ax_cum.grid(True, alpha=0.3)

    ax_rate.stackplot(
        t, *[rates[k] for k in keys], labels=labels, colors=colors, alpha=0.85
    )
    ax_rate.set_ylabel("FED rate (1/min)")
    ax_rate.set_xlabel("time (s)")
    ax_rate.grid(True, alpha=0.3)

    fig.suptitle(f"Agent {agent_id}: FED breakdown", fontsize=11, y=1.02)
    return fig


def _speed_vs_fed_plot(
    by_agent: dict[int, dict[str, list[float]]],
    *,
    threshold: float,
    title: str,
) -> Figure:
    """Scatter desired speed vs cumulative FED, coloured by sample time."""
    all_fed: list[float] = []
    all_speed: list[float] = []
    all_t: list[float] = []
    for series in by_agent.values():
        all_fed.extend(series["fed"])
        all_speed.extend(series["desired_speed"])
        all_t.extend(series["t"])
    if not all_fed:
        raise SystemExit("No data to scatter.")

    fig, ax = plt.subplots(figsize=(8, 5), constrained_layout=True)
    sc = ax.scatter(all_fed, all_speed, c=all_t, s=6, alpha=0.5, cmap="viridis")
    ax.set_xlabel("Cumulative FED")
    ax.set_ylabel("Desired speed (m/s)")
    ax.set_title(title)
    ax.grid(True, alpha=0.3)
    ax.axvline(threshold, color="#c0392b", linestyle="--", linewidth=1.0)
    cb = fig.colorbar(sc, ax=ax)
    cb.set_label("time (s)")
    return fig


def _speed_and_fed_plot(
    series: dict[str, list[float]], *, agent_id: int, threshold: float, title: str
) -> Figure:
    """Per-agent time series with speed on the left axis and FED on the right."""
    fig, ax_speed = plt.subplots(figsize=(9, 4.5), constrained_layout=True)
    ax_speed.plot(
        series["t"],
        series["desired_speed"],
        color="#2980b9",
        linewidth=1.2,
        label="desired speed",
    )
    if "base_speed" in series:
        ax_speed.plot(
            series["t"],
            series["base_speed"],
            color="#2980b9",
            linewidth=0.8,
            linestyle=":",
            label="base (clear-air) speed",
        )
    ax_speed.set_xlabel("time (s)")
    ax_speed.set_ylabel("speed (m/s)", color="#2980b9")
    ax_speed.tick_params(axis="y", labelcolor="#2980b9")
    ax_speed.grid(True, alpha=0.3)

    ax_fed = ax_speed.twinx()
    ax_fed.plot(
        series["t"],
        series["fed"],
        color="#c0392b",
        linewidth=1.2,
        label="cumulative FED",
    )
    ax_fed.axhline(
        threshold,
        color="#c0392b",
        linestyle="--",
        linewidth=0.8,
        label=f"FED={threshold}",
    )
    ax_fed.set_ylabel("Cumulative FED", color="#c0392b")
    ax_fed.tick_params(axis="y", labelcolor="#c0392b")

    lines, labels = ax_speed.get_legend_handles_labels()
    lines2, labels2 = ax_fed.get_legend_handles_labels()
    ax_speed.legend(lines + lines2, labels + labels2, loc="upper right", fontsize=8)
    ax_speed.set_title(f"Agent {agent_id}: {title}")
    return fig


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", type=Path, help="FED history CSV from run.py")
    parser.add_argument(
        "--output",
        type=Path,
        help="Write the figure to this path instead of showing it",
    )
    parser.add_argument(
        "--show-rate", action="store_true", help="Add a second panel with FED rate"
    )
    parser.add_argument(
        "--stack",
        type=int,
        metavar="AGENT_ID",
        help="Plot a per-species stacked breakdown for one agent",
    )
    parser.add_argument(
        "--stack-all",
        type=Path,
        metavar="DIR",
        help="Write one per-species stacked plot per agent into DIR",
    )
    parser.add_argument(
        "--speed-vs-fed",
        action="store_true",
        help="Scatter desired speed vs cumulative FED across all agents, "
        "coloured by sample time. Requires the speed columns written by the "
        "updated pyfds_evac.",
    )
    parser.add_argument(
        "--speed-and-fed",
        type=int,
        metavar="AGENT_ID",
        help="Per-agent time series with speed (left axis) and FED (right axis).",
    )
    parser.add_argument(
        "--threshold", type=float, default=1.0, help="FED threshold line (default 1.0)"
    )
    parser.add_argument("--title", default="FED per agent")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    by_agent, has_components = _read_history(args.csv)
    if not by_agent:
        raise SystemExit(f"No rows found in {args.csv}")

    has_speed = "desired_speed" in next(iter(by_agent.values()))

    if args.speed_vs_fed:
        if not has_speed:
            raise SystemExit(
                f"{args.csv} lacks speed columns; re-run with the updated "
                "pyfds_evac to produce desired_speed/base_speed."
            )
        fig = _speed_vs_fed_plot(
            by_agent, threshold=args.threshold, title="Speed vs cumulative FED"
        )
    elif args.speed_and_fed is not None:
        if not has_speed:
            raise SystemExit(
                f"{args.csv} lacks speed columns; re-run with the updated "
                "pyfds_evac to produce desired_speed/base_speed."
            )
        if args.speed_and_fed not in by_agent:
            raise SystemExit(f"Agent {args.speed_and_fed} not found in {args.csv}")
        fig = _speed_and_fed_plot(
            by_agent[args.speed_and_fed],
            agent_id=args.speed_and_fed,
            threshold=args.threshold,
            title="speed & FED",
        )
    elif args.stack_all is not None:
        if not has_components:
            raise SystemExit(
                f"{args.csv} lacks component columns; re-run with the updated "
                "pyfds_evac to produce per-species breakdowns."
            )
        args.stack_all.mkdir(parents=True, exist_ok=True)
        for agent_id in sorted(by_agent):
            fig = _stack_plot(
                by_agent[agent_id],
                agent_id=agent_id,
                threshold=args.threshold,
                title=args.title,
            )
            out = args.stack_all / f"fed_agent_{agent_id:04d}.png"
            fig.savefig(out, dpi=120, bbox_inches="tight")
            plt.close(fig)
        print(f"Wrote {len(by_agent)} figures to {args.stack_all}")
        return 0

    elif args.stack is not None:
        if not has_components:
            raise SystemExit(
                f"{args.csv} lacks component columns; re-run with the updated "
                "pyfds_evac to produce per-species breakdowns."
            )
        if args.stack not in by_agent:
            raise SystemExit(f"Agent {args.stack} not found in {args.csv}")
        fig = _stack_plot(
            by_agent[args.stack],
            agent_id=args.stack,
            threshold=args.threshold,
            title=args.title,
        )
    else:
        fig = _spaghetti_plot(
            by_agent,
            show_rate=args.show_rate,
            threshold=args.threshold,
            title=args.title,
        )

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(args.output, dpi=150, bbox_inches="tight")
        print(f"Wrote {args.output}")
    else:
        plt.show()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
