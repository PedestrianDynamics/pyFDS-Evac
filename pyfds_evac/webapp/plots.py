"""Build interactive Plotly figures from a finished scenario run.

Figures are produced with the Plotly Python API and embedded as HTML
fragments (Plotly.js is loaded once from CDN in the page head). Each builder
is defensive: missing data yields a small "no data" figure rather than an
error, because smoke/FED/route histories only exist when the matching model
was active.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import plotly.graph_objects as go
from fasthtml.common import NotStr

# Qualitative exit palette led by clay, tuned to read on the cream ground.
_PALETTE = [
    "#f4c430",
    "#ff6a1a",
    "#e01e37",
    "#ffb020",
    "#e8590c",
    "#c81d4e",
    "#ff8a3d",
    "#9a6a3a",
]


_GRID = "rgba(255,255,255,0.06)"
_ZERO = "rgba(255,255,255,0.16)"
_FG = "#b2a9a3"


def figure_html(fig: go.Figure, div_id: str) -> Any:
    """Embed a Plotly figure as an HTML fragment (no bundled Plotly.js).

    Both backgrounds are transparent, so the figure sits on whichever ground
    the page is currently painting and only the ink has to follow the theme.
    The values below are the dark defaults; Plotly bakes them in at render
    time and resolves no CSS variables, so ``theme.py``'s switch re-applies
    the font and grid colours with ``Plotly.relayout`` after a flip.

    ``colorway`` is deliberately *not* re-applied: the exit palette is drawn
    from the heat ramp, which is identical in both themes.
    """
    fig.update_layout(
        margin=dict(l=52, r=22, t=30, b=46),
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="IBM Plex Mono, ui-monospace, monospace", color=_FG, size=12),
        colorway=_PALETTE,
        height=460,
        legend=dict(bgcolor="rgba(0,0,0,0)"),
    )
    fig.update_xaxes(gridcolor=_GRID, zerolinecolor=_ZERO, linecolor=_GRID)
    fig.update_yaxes(gridcolor=_GRID, zerolinecolor=_ZERO, linecolor=_GRID)
    html = fig.to_html(full_html=False, include_plotlyjs=False, div_id=div_id)
    return NotStr(html)


def _empty(message: str) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(
        text=message, showarrow=False, font=dict(size=14, color="#b2a9a3")
    )
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return fig


def _agent_exit_map(
    route_cost_history: list[dict[str, Any]] | None,
) -> dict[int, str]:
    """Map agent_id -> last chosen exit (route_rank == 1) for colouring."""
    if not route_cost_history:
        return {}
    df = pd.DataFrame(route_cost_history)
    if "route_rank" not in df or "current_exit" not in df:
        return {}
    chosen = df[df["route_rank"] == 1].sort_values("time_s")
    last = chosen.groupby("agent_id").last()
    return last["current_exit"].to_dict()


#: What the smoke chart's means are taken over: ``smoke_history`` holds a row
#: only for agents in the simulation and not incapacitated (#321).
SMOKE_CAPTION = (
    "Mean over the agents still in the simulation and not incapacitated, "
    "at each smoke update."
)
# Lowest top of the K axis [1/m], so a near-clear field is not magnified.
_K_AXIS_FLOOR = 1.0


def _smoke_means(rows: list[dict[str, Any]]) -> pd.DataFrame:
    """Mean speed factor and K per smoke update time."""
    return (
        pd.DataFrame(rows)
        .groupby("time_s")
        .agg(
            speed_factor=("speed_factor", "mean"),
            extinction=("extinction_per_m", "mean"),
        )
        .reset_index()
    )


def _end_time(result: Any) -> float | None:
    end = getattr(result, "evacuation_time", None)
    return float(end) if end else None


def smoke_figure(result: Any) -> go.Figure:
    """Mean speed factor and extinction over time, on fixed axes.

    Speed factor 0-1; K from 0 to max(1.1 x the highest mean, 1 1/m); time
    from 0 to the run's simulated end, so a series that stops early shows
    as stopping and a constant field reads as constant.
    """
    rows = result.smoke_history
    if not rows:
        return _empty("No smoke history (provide --fds-dir or --constant-extinction).")
    agg = _smoke_means(rows)
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=agg["time_s"],
            y=agg["speed_factor"],
            mode="lines",
            name="mean speed factor",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=agg["time_s"],
            y=agg["extinction"],
            mode="lines",
            name="mean K",
            line=dict(dash="dash"),
            yaxis="y2",
        )
    )
    k_top = max(1.1 * float(agg["extinction"].max()), _K_AXIS_FLOOR)
    end = _end_time(result) or float(agg["time_s"].max())
    fig.update_layout(
        xaxis=dict(title="Simulated time (s)", range=[0.0, end]),
        yaxis=dict(title="Speed factor (–)", range=[0.0, 1.0]),
        yaxis2=dict(
            title="Extinction coefficient K (1/m)",
            overlaying="y",
            side="right",
            range=[0.0, k_top],
        ),
    )
    return fig


def smoke_summary(result: Any, update_interval_s: float | None) -> list[str]:
    """Numbers behind the smoke chart, also its text alternative.

    Plain statistics of the plotted means: their ranges and time span, a
    note when the series ends before the run, and the samples read outside
    the FDS domain (ambient air), which are in the mean (#594).
    """
    rows = result.smoke_history
    if not rows:
        return []
    agg = _smoke_means(rows)
    t0, t1 = float(agg["time_s"].min()), float(agg["time_s"].max())
    sf, k = agg["speed_factor"], agg["extinction"]
    lines = [
        f"Mean speed factor: {sf.min():.3f} to {sf.max():.3f} · "
        f"Mean K: {k.min():.3g} to {k.max():.3g} 1/m · "
        f"from {t0:.1f} s to {t1:.1f} s, {len(agg)} smoke updates"
    ]
    end = _end_time(result)
    if end is not None and t1 < end - (update_interval_s or 0.0):
        lines.append(
            f"No agent in the simulation and not incapacitated after {t1:.1f} s."
        )
    outside = sum(1 for r in rows if r.get("in_fds_domain") is False)
    if outside:
        lines.append(
            f"Includes {outside} samples outside the FDS domain (ambient air)."
        )
    return lines


def cognitive_map_grew(result: Any) -> bool:
    """True when some agent's cognitive map grew after it was first recorded.

    ``cognitive_map_history`` adds a row only when an agent's map changes, so
    a second row for the same agent is a growth event. Agents that know the
    whole graph from the start (no discovery) have one row each.
    """
    rows = result.cognitive_map_history or []
    seen: set[Any] = set()
    for row in rows:
        aid = row.get("agent_id")
        if aid in seen:
            return True
        seen.add(aid)
    return False


def cognitive_map_figure(result: Any) -> go.Figure:
    """Mean known nodes/edges per agent over time (discovery-mode learning).

    ``cognitive_map_history`` has one row per agent per growth event (map
    size only ever increases, see scenario.py), so agents that stop growing
    simply stop producing rows. Forward-filling each agent's node/edge count
    onto the union of event times before averaging keeps agents who learned
    everything early from vanishing out of the mean.
    """
    rows = result.cognitive_map_history
    if not rows:
        return _empty("No cognitive-map history (run had no routing stage graph).")
    df = pd.DataFrame(rows)
    if "known_nodes" not in df or "known_edges" not in df:
        return _empty("Cognitive-map history is missing expected columns.")
    df["n_nodes"] = df["known_nodes"].apply(len)
    df["n_edges"] = df["known_edges"].apply(len)

    def _mean_over_time(col: str) -> pd.Series:
        wide = df.pivot_table(
            index="time_s", columns="agent_id", values=col, aggfunc="last"
        )
        return wide.sort_index().ffill().mean(axis=1)

    nodes = _mean_over_time("n_nodes")
    edges = _mean_over_time("n_edges")
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(x=nodes.index, y=nodes.values, mode="lines", name="mean known nodes")
    )
    fig.add_trace(
        go.Scatter(
            x=edges.index,
            y=edges.values,
            mode="lines",
            name="mean known edges",
            yaxis="y2",
        )
    )
    fig.update_layout(
        xaxis_title="time (s)",
        yaxis_title="known nodes",
        yaxis2=dict(title="known edges", overlaying="y", side="right"),
    )
    return fig
