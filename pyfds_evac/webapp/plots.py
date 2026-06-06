"""Build interactive Plotly figures from a finished scenario run.

Figures are produced with the Plotly Python API and embedded as HTML
fragments (Plotly.js is loaded once from CDN in the page head). Each builder
is defensive: missing data yields a small "no data" figure rather than an
error, because smoke/FED/route histories only exist when the matching model
was active.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import plotly.graph_objects as go
from fasthtml.common import NotStr

# Qualitative exit palette led by clay, tuned to read on the cream ground.
_PALETTE = [
    "#cc785c",
    "#3f8f57",
    "#3b6fb0",
    "#d19a2e",
    "#7e5b9a",
    "#2e8b8b",
    "#c23b2e",
    "#9a6a3a",
]


_GRID = "rgba(20,20,19,0.06)"
_ZERO = "rgba(20,20,19,0.14)"
_FG = "#4a473f"


def figure_html(fig: go.Figure, div_id: str) -> Any:
    """Embed a Plotly figure as an HTML fragment (no bundled Plotly.js).

    Applies the Warm Paper Lab light template so charts match the GUI's cream
    ground (transparent background, warm ink, hue-shifted grid).
    """
    fig.update_layout(
        margin=dict(l=52, r=22, t=30, b=46),
        template="plotly_white",
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
    fig.add_annotation(text=message, showarrow=False, font=dict(size=14, color="#777"))
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


def trajectories_figure(result: Any, scenario: Any) -> go.Figure:
    """Agent paths coloured by assigned exit, over walkable area and exits."""
    if not result.sqlite_file or not Path(result.sqlite_file).exists():
        return _empty("Trajectory data unavailable.")

    import pedpy

    sqlite = Path(result.sqlite_file)
    traj = pedpy.load_trajectory_from_jupedsim_sqlite(trajectory_file=sqlite)
    walkable = pedpy.load_walkable_area_from_jupedsim_sqlite(trajectory_file=sqlite)

    fig = go.Figure()

    # Walkable area outline.
    try:
        wx, wy = walkable.polygon.exterior.xy
        fig.add_trace(
            go.Scatter(
                x=list(wx),
                y=list(wy),
                fill="toself",
                mode="lines",
                line=dict(color="#c9bfa6", width=1),
                fillcolor="rgba(20,20,19,0.035)",
                name="walkable",
                hoverinfo="skip",
                showlegend=False,
            )
        )
    except Exception:
        pass

    agent_exit = _agent_exit_map(result.route_cost_history)
    exits = sorted(set(agent_exit.values()))
    color_of = {ex: _PALETTE[i % len(_PALETTE)] for i, ex in enumerate(exits)}

    data = traj.data
    # One trace per exit group (paths separated by None) keeps the plot light.
    groups: Dict[str, Dict[str, list]] = {}
    for agent_id, agent_data in data.sort_values("frame").groupby("id"):
        exit_id = agent_exit.get(agent_id, "unassigned")
        g = groups.setdefault(exit_id, {"x": [], "y": []})
        g["x"].extend(list(agent_data["x"]) + [None])
        g["y"].extend(list(agent_data["y"]) + [None])

    for exit_id, g in groups.items():
        # SVG Scatter (not Scattergl) so trajectories render without WebGL.
        # Faint: the moving dots are the focus, the paths are context.
        fig.add_trace(
            go.Scatter(
                x=g["x"],
                y=g["y"],
                mode="lines",
                line=dict(color=color_of.get(exit_id, "#b9b09a"), width=1),
                name=exit_id.replace("_", " "),
                opacity=0.28,
                hoverinfo="skip",
            )
        )

    # Exit polygons from the scenario config.
    for i, (exit_id, edata) in enumerate((scenario.raw.get("exits") or {}).items()):
        coords = edata.get("coordinates") or []
        if not coords:
            continue
        ex = [c[0] for c in coords] + [coords[0][0]]
        ey = [c[1] for c in coords] + [coords[0][1]]
        fig.add_trace(
            go.Scatter(
                x=ex,
                y=ey,
                fill="toself",
                mode="lines",
                line=dict(
                    color=color_of.get(exit_id, _PALETTE[i % len(_PALETTE)]), width=2
                ),
                fillcolor="rgba(204,120,92,0.16)",
                name=f"{exit_id.replace('_', ' ')} (exit)",
                hoverinfo="skip",
            )
        )

    # ── Animated playback: agent dots over time ──
    # A FIXED agent array (NaN where an agent is not present) keeps marker
    # indices aligned across frames so Plotly can tween positions smoothly;
    # ~120 frames keeps motion fine-grained but the payload light (only x/y
    # change per frame — colour lives on the base trace).
    frames_all = sorted(data["frame"].unique())
    dot_idx = len(fig.data)
    fps = float(getattr(traj, "frame_rate", 0) or 1.0)

    if len(frames_all) >= 2:
        agent_ids = sorted(int(a) for a in data["id"].unique())
        colors = [color_of.get(agent_exit.get(a, ""), "#cc785c") for a in agent_ids]
        nan = float("nan")
        by_frame = {f: g for f, g in data.groupby("frame")}

        def _xy(frame_no):
            sub = by_frame[frame_no]
            pos = {int(i): (x, y) for i, x, y in zip(sub["id"], sub["x"], sub["y"])}
            xs = [pos.get(a, (nan, nan))[0] for a in agent_ids]
            ys = [pos.get(a, (nan, nan))[1] for a in agent_ids]
            return xs, ys

        step = max(1, len(frames_all) // 120)
        sampled = frames_all[::step]
        x0, y0 = _xy(sampled[0])
        fig.add_trace(
            go.Scatter(
                x=x0,
                y=y0,
                mode="markers",
                marker=dict(
                    size=7,
                    color=colors,
                    line=dict(width=0.5, color="rgba(20,20,19,0.35)"),
                ),
                name="agents",
                hoverinfo="skip",
            )
        )
        fig.frames = [
            go.Frame(
                data=[go.Scatter(x=_xy(f)[0], y=_xy(f)[1])],
                name=str(f),
                traces=[dot_idx],
            )
            for f in sampled
        ]
        play = dict(
            frame=dict(duration=60, redraw=False),
            fromcurrent=True,
            transition=dict(duration=60, easing="linear"),
        )
        fig.update_layout(
            updatemenus=[
                dict(
                    type="buttons",
                    direction="left",
                    x=0,
                    y=1.10,
                    xanchor="left",
                    showactive=False,
                    pad=dict(t=0, r=8),
                    buttons=[
                        dict(label="▶ play", method="animate", args=[None, play]),
                        dict(
                            label="❚❚ pause",
                            method="animate",
                            args=[
                                [None],
                                dict(mode="immediate", frame=dict(duration=0)),
                            ],
                        ),
                    ],
                )
            ],
            sliders=[
                dict(
                    active=0,
                    x=0.13,
                    len=0.87,
                    pad=dict(t=2, b=0),
                    currentvalue=dict(prefix="t = ", suffix=" s", font=dict(size=11)),
                    steps=[
                        dict(
                            label=f"{f / fps:.0f}",
                            method="animate",
                            args=[
                                [str(f)],
                                dict(
                                    mode="immediate",
                                    frame=dict(duration=0, redraw=False),
                                    transition=dict(duration=0),
                                ),
                            ],
                        )
                        for f in sampled
                    ],
                )
            ],
        )

    fig.update_layout(xaxis_title="x (m)", yaxis_title="y (m)")
    fig.update_yaxes(scaleanchor="x", scaleratio=1)
    return fig


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
        line_color="#d2722b",
        annotation_text="incapacitation (0.3)",
    )
    fig.add_hline(
        y=1.0, line_dash="dot", line_color="#c23b2e", annotation_text="untenable (1.0)"
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
