"""Build interactive Plotly figures from a finished scenario run.

Figures are produced with the Plotly Python API and embedded as HTML
fragments (Plotly.js is loaded once from CDN in the page head). Each builder
is defensive: missing data yields a small "no data" figure rather than an
error, because smoke/FED/route histories only exist when the matching model
was active.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

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

    Applies the Warm Paper Lab light template so charts match the GUI's cream
    ground (transparent background, warm ink, hue-shifted grid).
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
    fig.add_annotation(text=message, showarrow=False, font=dict(size=14, color="#b2a9a3"))
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return fig


def _agent_exit_map(
    route_cost_history: Optional[List[Dict[str, Any]]],
) -> Dict[int, str]:
    """Map agent_id -> last chosen exit (route_rank == 1) for colouring."""
    if not route_cost_history:
        return {}
    df = pd.DataFrame(route_cost_history)
    if "route_rank" not in df or "current_exit" not in df:
        return {}
    chosen = df[df["route_rank"] == 1].sort_values("time_s")
    last = chosen.groupby("agent_id").last()
    return last["current_exit"].to_dict()


def fed_figure(result: Any) -> go.Figure:
    """Cumulative FED over time (mean and max across agents)."""
    rows = result.fed_history
    if not rows:
        return _empty("No FED history (load an FDS field with a FED model).")
    df = pd.DataFrame(rows)
    if "fed_cumulative" not in df or "time_s" not in df:
        return _empty("FED history is missing expected columns.")
    agg = df.groupby("time_s")["fed_cumulative"].agg(["mean", "max"]).reset_index()
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(x=agg["time_s"], y=agg["max"], mode="lines", name="max FED")
    )
    fig.add_trace(
        go.Scatter(x=agg["time_s"], y=agg["mean"], mode="lines", name="mean FED")
    )
    fig.add_hline(
        y=0.3,
        line_dash="dot",
        line_color="#ffb020",
        annotation_text="incapacitation (0.3)",
    )
    fig.add_hline(
        y=1.0, line_dash="dot", line_color="#e01e37", annotation_text="untenable (1.0)"
    )
    fig.update_layout(xaxis_title="time (s)", yaxis_title="cumulative FED")
    return fig


def smoke_figure(result: Any) -> go.Figure:
    """Mean speed factor and extinction over time."""
    rows = result.smoke_history
    if not rows:
        return _empty("No smoke history (provide --fds-dir or --constant-extinction).")
    df = pd.DataFrame(rows)
    agg = (
        df.groupby("time_s")
        .agg(
            speed_factor=("speed_factor", "mean"),
            extinction=("extinction_per_m", "mean"),
        )
        .reset_index()
    )
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
            name="mean K [1/m]",
            yaxis="y2",
        )
    )
    fig.update_layout(
        xaxis_title="time (s)",
        yaxis_title="speed factor",
        yaxis2=dict(title="extinction K [1/m]", overlaying="y", side="right"),
    )
    return fig


def route_cost_figure(result: Any) -> go.Figure:
    """Mean composite cost of the chosen route over time."""
    rows = result.route_cost_history
    if not rows:
        return _empty("No route-cost history (enable rerouting).")
    df = pd.DataFrame(rows)
    if "route_rank" not in df or "composite_cost" not in df:
        return _empty("Route-cost history is missing expected columns.")
    chosen = df[df["route_rank"] == 1]
    agg = chosen.groupby("time_s")["composite_cost"].mean().reset_index()
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=agg["time_s"],
            y=agg["composite_cost"],
            mode="lines",
            name="mean chosen-route cost",
        )
    )
    fig.update_layout(xaxis_title="time (s)", yaxis_title="composite cost")
    return fig
