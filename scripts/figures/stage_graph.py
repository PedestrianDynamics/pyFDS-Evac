"""Stage-graph figure: smoke is sampled along the walked polyline.

Plan view of a non-convex room with a prescribed toy extinction field (no
simulation). The straight agent-to-exit line cuts through a wall; the walked
polyline is sampled every ``RouteCostConfig.sampling_step_m`` and each sample
is coloured by the extinction K at the time the agent would reach it at
``RouteCostConfig.base_speed_m_per_s``. ``draw_spacetime`` draws the same route
in space-time; it is not used in the rendered figure.

Run from the repository root::

    .venv/bin/python scripts/figures/stage_graph.py

Writes ``site/static/images/concepts/stage_graph.png``.
"""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import Rectangle

try:
    import seaborn as sns
except ImportError:  # seaborn only sets the theme; fall back to rcParams
    sns = None

from pyfds_evac import RouteCostConfig

OUT = Path(__file__).resolve().parents[2] / "site" / "static" / "images" / "concepts"
ROUTING = RouteCostConfig()

# Shared palette of the concept figures: one meaning, one colour, one style.
SMOKE = LinearSegmentedColormap.from_list("smoke", ["#f7f7f7", "#9a9a9a", "#2b2b2b"])
CHOSEN = "#4575b4"  # chosen / walked route: solid line
REFUSED = "#d73027"  # refused route: dashed line, hatched bar
OPTION = "#969696"  # candidate neither chosen nor refused
KNOWN = "#324465"  # stage in the map: filled marker
UNKNOWN = "#bdbdbd"  # stage not in the map: hollow marker, dashed edge
LEGIBLE = "#fee090"  # legible sign: yellow fill with a gold outline
LEGIBLE_EDGE = "#c89b00"
EXIT = "#33a02c"  # exit door
AGENT = "#1a1a1a"  # agent: star marker
WALL = "dimgrey"
FLOOR = "#f7f7f7"
TEXT = "dimgrey"
LABEL_BOX = dict(fc="white", ec="none", alpha=0.85, pad=1.5)


def smoke_field(x, y, t):
    """Toy extinction field: a plume in the corridor that grows with time."""
    cx, cy = 7.0, 1.6
    r2 = (x - cx) ** 2 + 0.6 * (y - cy) ** 2
    return 1.6 * (0.35 + 0.65 * t / 40.0) * np.exp(-r2 / 6.0)


def route_points(ds=ROUTING.sampling_step_m):
    """Walked polyline from agent to exit, sampled as the router samples it.

    Each straight piece gets ``max(2, ceil(length / ds) + 1)`` evenly spaced
    samples including both ends, so the spacing never exceeds ds.
    """
    verts = np.array([[1.2, 4.2], [2.6, 3.0], [3.6, 1.4], [9.6, 1.4], [9.6, 5.5]])
    seg = np.diff(verts, axis=0)
    lens = np.hypot(seg[:, 0], seg[:, 1])
    s_knots = np.concatenate([[0.0], np.cumsum(lens)])
    pieces = [
        np.linspace(s_knots[i], s_knots[i + 1], max(2, int(np.ceil(length / ds)) + 1))
        for i, length in enumerate(lens)
    ]
    s = np.concatenate(pieces)
    x = np.interp(s, s_knots, verts[:, 0])
    y = np.interp(s, s_knots, verts[:, 1])
    return verts, s, x, y


def draw_plan(ax, verts, s, x, y, v0=ROUTING.base_speed_m_per_s):
    """Top panel: bee-line through the wall vs the walked polyline."""
    ax.add_patch(Rectangle((0, 0), 11, 5.6, fc=FLOOR, ec=WALL, lw=1.6, zorder=0))
    # internal wall separating the entrance hall from the corridor
    ax.add_patch(Rectangle((3.0, 2.4), 6.0, 0.25, fc=WALL, ec="none", zorder=3))
    ax.add_patch(Rectangle((3.0, 2.4), 0.25, 3.2, fc=WALL, ec="none", zorder=3))

    # smoke field at the departure time
    gx, gy = np.meshgrid(np.linspace(0, 11, 220), np.linspace(0, 5.6, 120))
    ax.contourf(
        gx,
        gy,
        smoke_field(gx, gy, 0.0),
        levels=8,
        cmap=SMOKE,
        vmin=0,
        vmax=1.6,
        alpha=0.75,
        zorder=1,
    )

    # straight sight line: agent -> exit, crossing the wall
    ax.plot(
        [verts[0, 0], verts[-1, 0]],
        [verts[0, 1], verts[-1, 1]],
        color=OPTION,
        lw=1.6,
        ls="--",
        zorder=4,
    )
    ax.text(
        6.2,
        4.15,
        "straight line: samples\nsmoke through the wall",
        color=TEXT,
        fontsize=8.2,
        ha="center",
        va="bottom",
        zorder=6,
        bbox=LABEL_BOX,
    )

    # walked polyline sampled every Delta s, coloured by K at arrival time
    k = smoke_field(x, y, s / v0)
    ax.plot(verts[:, 0], verts[:, 1], color=CHOSEN, lw=2.4, zorder=4)
    sc = ax.scatter(
        x,
        y,
        c=k,
        cmap=SMOKE,
        vmin=0,
        vmax=1.6,
        s=38,
        edgecolors=CHOSEN,
        linewidths=1.1,
        zorder=5,
    )
    ax.text(
        6.4,
        0.2,
        rf"walked polyline, $\Delta s \leq {ROUTING.sampling_step_m:g}$ m,"
        "\n"
        r"$\bar K_{uv}$ = mean of the samples",
        color=TEXT,
        fontsize=8.2,
        ha="center",
        va="bottom",
        zorder=6,
        bbox=LABEL_BOX,
    )

    # stage-graph nodes
    ax.scatter([2.6, 9.6], [3.0, 1.4], s=80, fc=KNOWN, ec="white", lw=1.4, zorder=6)
    ax.text(
        2.35, 2.75, "node $u$", fontsize=8, color=TEXT, ha="right", va="top", zorder=6
    )
    ax.text(
        9.6, 1.05, "node $v$", fontsize=8, color=TEXT, ha="center", va="top", zorder=6
    )
    ax.add_patch(Rectangle((9.2, 5.5), 0.8, 0.2, fc=EXIT, ec="none", zorder=6))
    ax.text(9.05, 5.35, "exit", fontsize=8, color=TEXT, ha="right", va="top", zorder=6)

    # agent and its walkable distance to the first node
    ax.scatter(
        [verts[0, 0]],
        [verts[0, 1]],
        marker="*",
        s=200,
        fc=AGENT,
        ec="white",
        lw=0.8,
        zorder=7,
    )
    ax.text(
        verts[0, 0] - 0.15,
        verts[0, 1] + 0.3,
        "agent",
        fontsize=8.5,
        color=TEXT,
        ha="left",
        va="bottom",
        zorder=7,
    )
    ax.annotate(
        "",
        xy=(2.45, 2.85),
        xytext=(1.05, 4.05),
        arrowprops=dict(
            arrowstyle="<->", color=TEXT, lw=1.0, connectionstyle="arc3,rad=0.35"
        ),
        zorder=6,
    )
    ax.text(
        1.35, 3.1, "$d_W$", fontsize=9, color=TEXT, ha="center", va="center", zorder=6
    )

    ax.set_xlim(-0.2, 11.2)
    ax.set_ylim(-0.2, 5.9)
    ax.set_aspect("equal")
    # a floor plan has no data axes: grid, ticks and frame add nothing
    ax.axis("off")
    ax.set_title(
        "Plan view: cost is integrated along the walk, not the sight line",
        fontsize=10,
        loc="left",
        pad=4,
    )
    return sc


def draw_spacetime(ax, s, x, y, v0=ROUTING.base_speed_m_per_s, period=1.0, t0=6.0):
    """Bottom panel: samples at t + s/v0 on a growing smoke field."""
    s_max = s[-1]
    ss, tt = np.meshgrid(np.linspace(0, s_max, 240), np.linspace(0, 40, 160))
    xs = np.interp(ss, s, x)
    ys = np.interp(ss, s, y)
    ax.contourf(
        ss,
        tt,
        smoke_field(xs, ys, tt),
        levels=8,
        cmap=SMOKE,
        vmin=0,
        vmax=1.6,
        alpha=0.75,
        zorder=1,
    )

    # world line of the agent leaving at t0, and the samples on it
    ax.plot([0, s_max], [t0, t0 + s_max / v0], color=CHOSEN, lw=2.0, zorder=4)
    ax.scatter(
        s,
        t0 + s / v0,
        c=smoke_field(x, y, t0 + s / v0),
        cmap=SMOKE,
        vmin=0,
        vmax=1.6,
        s=22,
        edgecolors=CHOSEN,
        linewidths=0.5,
        zorder=5,
    )
    ax.text(
        s_max * 0.55,
        t0 + s_max * 0.55 / v0 + 4.5,
        r"sampled at $t + \ell_{uv}/v_0$",
        color=CHOSEN,
        fontsize=8.5,
        ha="center",
        va="bottom",
        rotation=0,
        zorder=6,
        bbox=dict(fc="white", ec="none", alpha=0.85, pad=1.5),
    )
    # naive alternative: everything sampled at the decision time
    ax.plot([0, s_max], [t0, t0], color=REFUSED, lw=1.4, ls="--", zorder=4)
    ax.text(
        s_max * 0.25,
        t0 - 1.0,
        "frozen field at $t$",
        color=REFUSED,
        fontsize=8,
        ha="center",
        va="top",
        zorder=6,
    )

    # reevaluation ticks every T seconds on the agent's own clock
    for k in range(0, 8):
        tk = t0 + k * period * 3  # 3 s spacing keeps the ticks legible
        ax.plot([0.1, 0.45], [tk, tk], color=TEXT, lw=1.6, zorder=6)
    ax.text(
        0.7,
        t0 + 7 * 3 * period * 0.62,
        "re-decide\nevery $T$",
        color=TEXT,
        fontsize=8,
        ha="left",
        va="center",
        zorder=6,
    )

    ax.set_xlim(0, s_max)
    ax.set_ylim(0, 40)
    ax.set_xlabel("arc length $s$ along the route [m]", fontsize=8.5, color=TEXT)
    ax.set_ylabel("time [s]", fontsize=8.5, color=TEXT)
    ax.tick_params(labelsize=7.5, length=0, labelcolor=TEXT)
    ax.grid(False)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.set_title(
        "Space-time: each segment is priced when the agent gets there",
        fontsize=9.5,
        color=CHOSEN,
        loc="left",
        pad=4,
    )


def main():
    """Render the stage-graph figure.

    Saves
    -----
    site/static/images/concepts/stage_graph.png
    """
    if sns is not None:
        sns.set_theme(font_scale=1.0, style="whitegrid", font="DejaVu Sans")
    else:
        plt.rcParams["font.family"] = "DejaVu Sans"

    verts, s, x, y = route_points()
    # Plan view only. The space-time panel (draw_spacetime) is kept for the
    # paper; on the slide it cost more explanation than it earned.
    fig, ax_plan = plt.subplots(figsize=(6.6, 3.6), dpi=150)
    sc = draw_plan(ax_plan, verts, s, x, y)

    cbar = fig.colorbar(sc, ax=ax_plan, fraction=0.035, pad=0.03)
    cbar.set_label(
        r"extinction $K_p$ at the sample [m$^{-1}$]", fontsize=8.5, color=TEXT
    )
    cbar.ax.tick_params(labelsize=7.5, length=0, labelcolor=TEXT)
    cbar.ax.grid(False)
    cbar.outline.set_visible(False)
    if sns is not None:
        sns.despine(fig=fig, left=True, bottom=True)

    k = sc.get_array()
    ax_plan.text(
        0.0,
        -0.03,
        f"Walked route: {s[-1]:.1f} m in {len(s)} samples; "
        rf"peak $K_p$ = {k.max():.2f} m$^{{-1}}$ where it passes the plume",
        transform=ax_plan.transAxes,
        ha="left",
        va="top",
        fontsize=8.5,
        color=TEXT,
        style="italic",
    )

    out = OUT
    out.mkdir(parents=True, exist_ok=True)
    fig.savefig(out / "stage_graph.png", dpi=150, bbox_inches="tight")


if __name__ == "__main__":
    main()
