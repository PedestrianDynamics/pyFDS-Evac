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
import seaborn as sns
from matplotlib.colors import LinearSegmentedColormap
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
    ("co", "CO", "#d73027"),
    ("cn", "HCN/CN", "#fc8d59"),
    ("nox", "NOx", "#fee090"),
    ("fld", "Irritants (FLD)", "#4575b4"),
    ("o2", "O2 hypoxia", "#bdbdbd"),
)
_STACK_HATCHES = ("", "//", "..", "xx", "\\\\")

_THRESHOLD_COLOUR = "#d73027"
_CUBEHELIX = LinearSegmentedColormap.from_list(
    "cubehelix6", sns.cubehelix_palette(6, rot=-0.25, light=0.7)
)
_LEGEND_STYLE = dict(
    frameon=True,
    facecolor="white",
    framealpha=0.8,
    edgecolor="lightgrey",
    labelcolor="dimgrey",
)


def _set_style() -> None:
    """Apply the house plot theme."""
    sns.set_theme(font_scale=1.0, style="whitegrid", font="DejaVu Sans")


def _finish_axes(*axes) -> None:
    """Soften ticks, frame each panel and drop the spines."""
    for ax in axes:
        ax.tick_params(axis="both", which="both", length=0, labelcolor="dimgrey")
        ax.patch.set_edgecolor("lightgrey")
        ax.patch.set_linewidth(0.8)
        sns.despine(ax=ax, left=True, bottom=True)


def _style_colorbar(cbar, label: str) -> None:
    """Label a colorbar in the house style."""
    cbar.set_label(label, color="dimgrey")
    cbar.outline.set_visible(False)
    cbar.ax.tick_params(length=0, labelcolor="dimgrey")


def _note(ax, text: str) -> None:
    """Write an insight annotation above the top-right corner of *ax*."""
    ax.text(
        1.0,
        1.01,
        text,
        transform=ax.transAxes,
        ha="right",
        va="bottom",
        fontsize=9,
        color="dimgrey",
        style="italic",
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
    _set_style()
    palette = [_CUBEHELIX(i / max(n_agents - 1, 1)) for i in range(n_agents)]
    if show_rate:
        fig, (ax_fed, ax_rate) = plt.subplots(
            2, 1, sharex=True, figsize=(9, 6), constrained_layout=True
        )
    else:
        fig, ax_fed = plt.subplots(figsize=(9, 4), constrained_layout=True)
        ax_rate = None

    for i, agent_id in enumerate(sorted(by_agent)):
        series = by_agent[agent_id]
        color = palette[i]
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
        color=_THRESHOLD_COLOUR,
        linestyle="--",
        linewidth=1.0,
        label=f"threshold={threshold}",
    )
    ax_fed.set_ylabel("Cumulative FED", color="dimgrey")
    ax_fed.set_title(title, loc="left", pad=7, color="dimgrey")
    if n_agents <= 12:
        ax_fed.legend(loc="upper left", fontsize=8, **_LEGEND_STYLE)

    crossings = [
        next(t for t, f in zip(s["t"], s["fed"]) if f >= threshold)
        for s in by_agent.values()
        if s["fed"] and max(s["fed"]) >= threshold
    ]
    _highlight_lead(ax_fed, by_agent, threshold, palette)
    if crossings:
        _note(
            ax_fed,
            f"{len(crossings)} of {n_agents} agents reach FED {threshold:g}, "
            f"the first at {min(crossings):.0f} s",
        )
    else:
        peak = max(max(s["fed"], default=0.0) for s in by_agent.values())
        _note(
            ax_fed,
            f"none of {n_agents} agents reaches FED {threshold:g} (peak {peak:.2g})",
        )

    if ax_rate is not None:
        ax_rate.set_ylabel("FED rate (1/min)", color="dimgrey")
        ax_rate.set_xlabel("time (s)", color="dimgrey")
        _finish_axes(ax_fed, ax_rate)
    else:
        ax_fed.set_xlabel("time (s)", color="dimgrey")
        _finish_axes(ax_fed)

    return fig


def _first_crossing(series: dict[str, list[float]], threshold: float) -> float | None:
    """Time the agent's cumulative FED first reaches *threshold*, if ever."""
    return next((t for t, f in zip(series["t"], series["fed"]) if f >= threshold), None)


def _highlight_lead(ax, by_agent, threshold: float, palette) -> None:
    """Redraw the agent that crosses first (or peaks highest) bold and label it.

    Agents share one line style, so the extreme one is picked out by width
    and a direct label rather than by colour alone.
    """
    ids = sorted(by_agent)
    crossings = {a: _first_crossing(by_agent[a], threshold) for a in ids}
    crossed = [a for a in ids if crossings[a] is not None]
    if crossed:
        lead = min(crossed, key=crossings.get)
        text = f"agent {lead}: first to FED {threshold:g} ({crossings[lead]:.0f} s)"
    else:
        lead = max(ids, key=lambda a: max(by_agent[a]["fed"], default=0.0))
        text = f"agent {lead}: highest FED"
    series = by_agent[lead]
    if not series["fed"]:
        return
    ax.plot(series["t"], series["fed"], color=palette[ids.index(lead)], linewidth=2.2)
    anchor = (series["t"][-1], series["fed"][-1])
    offset, align = (-8, 10), "right"
    if crossings[lead] is not None:
        anchor = (crossings[lead], threshold)
        offset, align = (8, -10), "left"
        ax.plot(*anchor, "o", color="#1f253f", ms=5, zorder=5)
    ax.annotate(
        text,
        xy=anchor,
        xytext=offset,
        textcoords="offset points",
        ha=align,
        va="center",
        fontsize=8,
        color="dimgrey",
    )


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

    _set_style()
    fig, (ax_cum, ax_rate) = plt.subplots(
        2, 1, sharex=True, figsize=(9, 6.5), constrained_layout=True
    )

    ax_cum.stackplot(
        t,
        *[cumulative[k] for k in keys],
        labels=labels,
        colors=colors,
        hatch=list(_STACK_HATCHES),
        edgecolor="white",
        linewidth=0.3,
        alpha=0.85,
    )
    ax_cum.plot(
        t,
        series["fed"],
        color="#1f253f",
        linewidth=1.0,
        label="total (logged)",
    )
    peak_fed = max(series["fed"]) if series["fed"] else 0.0
    if peak_fed >= 0.1 * threshold:
        ax_cum.axhline(
            threshold,
            color=_THRESHOLD_COLOUR,
            linestyle="--",
            linewidth=1.0,
            label=f"threshold={threshold}",
        )
    ax_cum.set_ylabel(f"Cumulative FED  (peak={peak_fed:.2e})", color="dimgrey")
    ax_cum.set_title(title, loc="left", pad=7, color="dimgrey")
    ax_cum.legend(loc="upper left", fontsize=8, **_LEGEND_STYLE)

    finals = {k: cumulative[k][-1] if cumulative[k] else 0.0 for k in keys}
    dose = sum(finals.values())
    if dose > 0.0:
        lead = max(finals, key=finals.get)
        lead_label = dict(zip(keys, labels))[lead]
        _note(
            ax_cum,
            f"{lead_label} gives {finals[lead] / dose:.0%} of the dose "
            f"by {t[-1]:.0f} s",
        )

    ax_rate.stackplot(
        t,
        *[rates[k] for k in keys],
        labels=labels,
        colors=colors,
        hatch=list(_STACK_HATCHES),
        edgecolor="white",
        linewidth=0.3,
        alpha=0.85,
    )
    ax_rate.set_ylabel("FED rate (1/min)", color="dimgrey")
    ax_rate.set_xlabel("time (s)", color="dimgrey")
    _finish_axes(ax_cum, ax_rate)

    fig.suptitle(f"Agent {agent_id}: FED breakdown", fontsize=11, color="dimgrey")
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

    _set_style()
    fig, ax = plt.subplots(figsize=(8, 5), constrained_layout=True)
    cmap = _CUBEHELIX
    sc = ax.scatter(
        all_fed, all_speed, c=all_t, s=6, alpha=0.5, cmap=cmap, edgecolors="none"
    )
    ax.set_xlabel("Cumulative FED", color="dimgrey")
    ax.set_ylabel("Desired speed (m/s)", color="dimgrey")
    ax.set_title(title, loc="left", pad=7, color="dimgrey")
    ax.axvline(threshold, color=_THRESHOLD_COLOUR, linestyle="--", linewidth=1.0)
    ax.text(
        threshold,
        1.0,
        f" FED = {threshold:g}",
        transform=ax.get_xaxis_transform(),
        ha="left",
        va="top",
        fontsize=9,
        color="dimgrey",
    )
    past = [v for f, v in zip(all_fed, all_speed) if f >= threshold]
    if past:
        _note(
            ax,
            f"past FED {threshold:g}: {len(past) / len(all_fed):.0%} of samples, "
            f"mean speed {sum(past) / len(past):.2f} m/s",
        )
    else:
        i_peak = max(range(len(all_fed)), key=all_fed.__getitem__)
        _note(
            ax,
            f"peak FED {all_fed[i_peak]:.2g} at {all_t[i_peak]:.0f} s "
            f"(threshold {threshold:g} not reached)",
        )
    _finish_axes(ax)
    cb = fig.colorbar(sc, ax=ax)
    cb.solids.set_alpha(1.0)
    _style_colorbar(cb, "time (s)")
    return fig


def _speed_and_fed_plot(
    series: dict[str, list[float]], *, agent_id: int, threshold: float, title: str
) -> Figure:
    """Per-agent time series with speed on the left axis and FED on the right."""
    speed_colour = "#4575b4"
    _set_style()
    fig, ax_speed = plt.subplots(figsize=(9, 4.5), constrained_layout=True)
    ax_speed.plot(
        series["t"],
        series["desired_speed"],
        color=speed_colour,
        linewidth=1.2,
        label="desired speed",
    )
    if "base_speed" in series:
        ax_speed.plot(
            series["t"],
            series["base_speed"],
            color=speed_colour,
            linewidth=0.8,
            linestyle=":",
            label="base (clear-air) speed",
        )
    ax_speed.set_xlabel("time (s)", color="dimgrey")
    ax_speed.set_ylabel("speed (m/s)", color=speed_colour)

    ax_fed = ax_speed.twinx()
    ax_fed.grid(False)
    ax_fed.plot(
        series["t"],
        series["fed"],
        color=_THRESHOLD_COLOUR,
        linewidth=1.2,
        linestyle="-.",
        label="cumulative FED",
    )
    ax_fed.axhline(
        threshold,
        color=_THRESHOLD_COLOUR,
        linestyle="--",
        linewidth=0.8,
        label=f"FED={threshold}",
    )
    ax_fed.set_ylabel("Cumulative FED", color=_THRESHOLD_COLOUR)

    lines, labels = ax_speed.get_legend_handles_labels()
    lines2, labels2 = ax_fed.get_legend_handles_labels()
    ax_speed.legend(
        lines + lines2,
        labels + labels2,
        loc="upper right",
        fontsize=8,
        **_LEGEND_STYLE,
    )
    ax_speed.set_title(f"Agent {agent_id}: {title}", loc="left", pad=7, color="dimgrey")
    crossing = next(
        (t for t, f in zip(series["t"], series["fed"]) if f >= threshold), None
    )
    if crossing is not None:
        speed_at = series["desired_speed"][series["t"].index(crossing)]
        _note(
            ax_speed,
            f"FED {threshold:g} at {crossing:.0f} s, desired speed then "
            f"{speed_at:.2f} m/s",
        )
    elif series["fed"]:
        i_peak = max(range(len(series["fed"])), key=series["fed"].__getitem__)
        _note(
            ax_speed,
            f"peak FED {series['fed'][i_peak]:.2g} at {series['t'][i_peak]:.0f} s "
            f"(threshold {threshold:g} not reached)",
        )
    _finish_axes(ax_speed)
    ax_fed.tick_params(axis="both", which="both", length=0, labelcolor="dimgrey")
    sns.despine(ax=ax_fed, left=True, bottom=True, right=True)
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
