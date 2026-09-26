"""Exposure-gate figure: refuse on optical depth, then order the survivors.

Top: plan view with three candidate routes from one agent to three exits,
sampled along the walked polylines and coloured by extinction K. The field is
a prescribed toy plume, not a simulation. Bottom: the gate. Each route's
optical depth tau = K_bar * L is drawn as a bar against the budgets from
``RouteCostConfig`` (``tau_max`` for the current exit, ``tau_return_margin *
tau_max`` for any other exit); the refused route is hatched, and the survivors
are ranked by tau first and travel time second, so the long clean route wins.
Travel time is priced as the code prices it: ``base_speed_m_per_s`` times the
Frantzich-Nilsson factor at the route-mean K, with the ``routing`` coefficients.

Run from the repository root::

    .venv/bin/python scripts/figures/exposure_gate.py

Writes ``site/static/images/concepts/exposure_gate.png``.
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

from pyfds_evac import (
    ConstantExtinctionField,
    RouteCostConfig,
    SmokeSpeedConfig,
    SmokeSpeedModel,
)

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
TAU_MAX = ROUTING.tau_max
MU = ROUTING.tau_return_margin

ROUTES = {
    "A": dict(verts=[[1.5, 3.5], [4.5, 5.2], [8.0, 5.2], [8.0, 6.8]], style="-"),
    "B": dict(verts=[[1.5, 3.5], [2.5, 1.0], [10.5, 1.0], [11.8, 2.0]], style="-"),
    "C": dict(verts=[[1.5, 3.5], [6.0, 3.6], [11.8, 4.2]], style="-"),
}


def smoke_field(x, y):
    """Toy extinction field: one plume in the middle of the hall.

    The peak is set so that route C exceeds tau_max outright: it is refused
    at the initial choice, where every exit is held to tau_max, and not only
    as a rival exit.
    """
    r2 = (x - 7.0) ** 2 + 0.9 * (y - 4.0) ** 2
    return 1.6 * np.exp(-r2 / 5.0)


def resample(verts, ds=ROUTING.sampling_step_m / 4):
    """Resample a polyline every ds metres; return s, x, y and its length."""
    verts = np.asarray(verts, dtype=float)
    seg = np.diff(verts, axis=0)
    knots = np.concatenate([[0.0], np.cumsum(np.hypot(seg[:, 0], seg[:, 1]))])
    s = np.arange(0.0, knots[-1] + 1e-9, ds)
    return (
        s,
        np.interp(s, knots, verts[:, 0]),
        np.interp(s, knots, verts[:, 1]),
        knots[-1],
    )


def route_speed(kbar):
    """Speed [m/s] the router assumes on a route with mean extinction kbar."""
    config = SmokeSpeedConfig(
        alpha=ROUTING.alpha,
        beta=ROUTING.beta,
        min_speed_factor=ROUTING.min_speed_factor,
    )
    factor = SmokeSpeedModel(ConstantExtinctionField(kbar), config).speed_factor(
        0.0, 0.0, 0.0
    )
    return ROUTING.base_speed_m_per_s * factor


def route_metrics():
    """tau, travel time and sample data per route."""
    out = {}
    for name, r in ROUTES.items():
        s, x, y, length = resample(r["verts"])
        k = smoke_field(x, y)
        kbar = float(k.mean())
        out[name] = dict(
            s=s,
            x=x,
            y=y,
            k=k,
            L=length,
            kbar=kbar,
            tau=kbar * length,
            time=length / route_speed(kbar),
        )
    return out


def gate_ranks(metrics):
    """Rank of each route that passes the rival-exit budget, by tau then time."""
    survivors = sorted(
        (n for n in metrics if metrics[n]["tau"] <= TAU_MAX * MU),
        key=lambda n: (metrics[n]["tau"], metrics[n]["time"]),
    )
    return {n: i + 1 for i, n in enumerate(survivors)}


def route_style(rank):
    """Colour and line style of a route: chosen, other survivor, or refused."""
    if rank is None:
        return REFUSED, "--"
    return (CHOSEN, "-") if rank == 1 else (OPTION, "-")


def draw_plan(ax, metrics):
    """Left panel: agent, plume, three walked routes to three exits."""
    ax.add_patch(Rectangle((0, 0), 12.5, 7.2, fc=FLOOR, ec=WALL, lw=1.6, zorder=0))
    gx, gy = np.meshgrid(np.linspace(0, 12.5, 250), np.linspace(0, 7.2, 150))
    ax.contourf(
        gx,
        gy,
        smoke_field(gx, gy),
        levels=8,
        cmap=SMOKE,
        vmin=0,
        vmax=1.6,
        alpha=0.75,
        zorder=1,
    )

    sc = None
    rank = gate_ranks(metrics)
    for name, m in metrics.items():
        color, ls = route_style(rank.get(name))
        ax.plot(m["x"], m["y"], color=color, lw=2.2, ls=ls, zorder=4)
        sc = ax.scatter(
            m["x"],
            m["y"],
            c=m["k"],
            cmap=SMOKE,
            vmin=0,
            vmax=1.6,
            s=22,
            edgecolors=color,
            linewidths=1.0,
            zorder=5,
        )

    # exits and route labels
    exits = {
        "A": ((7.6, 7.05), (8.9, 6.45)),
        "B": ((12.4, 1.6), (11.2, 2.15)),
        "C": ((12.4, 3.8), (11.2, 4.55)),
    }
    for name, (rect, lab) in exits.items():
        w, h = (0.8, 0.2) if name == "A" else (0.2, 0.8)
        ax.add_patch(Rectangle(rect, w, h, fc=EXIT, ec="none", zorder=6))
        ax.text(
            *lab,
            f"exit {name}",
            fontsize=9,
            fontweight="bold",
            color=TEXT,
            ha="center",
            va="center",
            zorder=7,
            bbox=LABEL_BOX,
        )

    ax.scatter([1.5], [3.5], marker="*", s=220, fc=AGENT, ec="white", lw=0.8, zorder=7)
    ax.text(
        1.5,
        3.95,
        "agent",
        fontsize=8.5,
        color=TEXT,
        ha="center",
        va="bottom",
        zorder=7,
    )

    ax.set_xlim(-0.2, 12.9)
    ax.set_ylim(-0.2, 7.5)
    ax.set_aspect("equal")
    # a floor plan has no data axes: grid, ticks and frame add nothing
    ax.axis("off")
    ax.set_title(
        r"$\bf{(a)}$  Three candidate routes, smoke sampled along each walk",
        fontsize=10,
        loc="left",
        pad=4,
    )
    return sc


def draw_gate(ax, metrics):
    """Right panel: tau bars against the budget, refused route hatched, survivors ranked."""
    names = list(metrics)
    ypos = np.arange(len(names))[::-1]
    budget_other = MU * TAU_MAX

    ax.axvspan(budget_other, TAU_MAX, color=OPTION, alpha=0.12, zorder=0)
    ax.axvline(TAU_MAX, color=TEXT, lw=1.4, zorder=1)
    ax.axvline(budget_other, color=TEXT, lw=1.2, ls="--", zorder=1)
    ax.axvline(0, color="lightgrey", lw=0.8, zorder=1)
    # threshold captions sit above the bars, so no bar label can run into them
    ax.text(
        TAU_MAX + 0.12,
        2.95,
        rf"$\tau_{{\max}} = {TAU_MAX:g}$" + "\ncurrent exit",
        color=TEXT,
        fontsize=8,
        ha="left",
        va="bottom",
    )
    ax.text(
        budget_other - 0.12,
        2.95,
        rf"${MU:g}\,\tau_{{\max}} = {budget_other:g}$" + "\nany other exit",
        color=TEXT,
        fontsize=8,
        ha="right",
        va="bottom",
    )

    rank = gate_ranks(metrics)

    for y, name in zip(ypos, names):
        m = metrics[name]
        refused = name not in rank
        color, _ = route_style(rank.get(name))
        ax.barh(
            y,
            m["tau"],
            height=0.55,
            color="white" if refused else color,
            edgecolor=color,
            hatch="////" if refused else None,
            lw=1.2,
            zorder=2,
        )
        label = (
            "refused" if refused else f"rank {rank[name]}   ({m['time']:.0f} s walk)"
        )
        if refused:
            # past the red line, never on it
            ax.text(
                max(m["tau"], TAU_MAX) + 0.15,
                y,
                label,
                fontsize=8.5,
                va="center",
                ha="left",
                color=REFUSED,
                fontweight="bold",
            )
        elif m["tau"] > 2.5:
            # long bar: label inside, clear of the budget lines
            ax.text(
                0.15,
                y,
                label,
                fontsize=8.5,
                va="center",
                ha="left",
                color="white",
                fontweight="bold",
            )
        else:
            ax.text(
                m["tau"] + 0.15,
                y,
                label,
                fontsize=8.5,
                va="center",
                ha="left",
                color=color,
                fontweight="bold",
            )

    ax.set_yticks(ypos)
    ax.set_yticklabels([f"route {n}" for n in names], fontsize=9)
    ax.set_xlim(0, 9.5)
    ax.set_ylim(-0.5, 3.75)
    ax.set_xlabel(
        r"optical depth along the walk  $\tau_k = \bar K_k\, L_k$",
        fontsize=8.5,
        color=TEXT,
    )
    ax.tick_params(axis="both", which="both", length=0, labelcolor=TEXT)
    ax.tick_params(axis="x", labelsize=7.5)
    # value labels carry the numbers; the zero line anchors the bars
    ax.grid(False)
    ax.set_title(
        r"$\bf{(b)}$  Gate: refuse above the budget, then sort by $\tau$, then by time",
        fontsize=10,
        loc="left",
        pad=4,
    )


def main():
    """Render the exposure-gate figure.

    Saves
    -----
    site/static/images/concepts/exposure_gate.png
    """
    if sns is not None:
        sns.set_theme(font_scale=1.0, style="whitegrid", font="DejaVu Sans")
    else:
        plt.rcParams["font.family"] = "DejaVu Sans"

    metrics = route_metrics()
    for n, m in metrics.items():
        print(
            f"route {n}: L={m['L']:.1f} m  Kbar={m['kbar']:.2f}  tau={m['tau']:.2f}  t={m['time']:.0f} s"
        )

    fig, (ax_plan, ax_gate) = plt.subplots(
        2,
        1,
        figsize=(6.6, 7.0),
        dpi=150,
        gridspec_kw=dict(height_ratios=[1.0, 0.72], hspace=0.3),
    )
    sc = draw_plan(ax_plan, metrics)
    draw_gate(ax_gate, metrics)

    cbar = fig.colorbar(sc, ax=ax_plan, fraction=0.04, pad=0.02)
    cbar.set_label(r"extinction $K_p$ [m$^{-1}$]", fontsize=8.5, color=TEXT)
    cbar.ax.tick_params(labelsize=7.5, length=0, labelcolor=TEXT)
    cbar.ax.grid(False)
    cbar.outline.set_visible(False)
    if sns is not None:
        sns.despine(fig=fig, left=True, bottom=True)

    rank = gate_ranks(metrics)
    best = min(rank, key=rank.get)
    shortest = min(metrics, key=lambda n: metrics[n]["L"])
    longest = max(metrics, key=lambda n: metrics[n]["L"])
    note = (
        f"Route {best} wins with the least smoke, "
        rf"$\tau$ = {metrics[best]['tau']:.1f}, "
        f"over {metrics[best]['L']:.1f} m"
    )
    if best == longest:
        note += f", the longest walk (route {shortest}: {metrics[shortest]['L']:.1f} m)"
    ax_gate.text(
        0.0,
        -0.22,
        note,
        transform=ax_gate.transAxes,
        ha="left",
        va="top",
        fontsize=8.5,
        color=TEXT,
        style="italic",
    )

    out = OUT
    out.mkdir(parents=True, exist_ok=True)
    fig.savefig(out / "exposure_gate.png", dpi=150, bbox_inches="tight")


if __name__ == "__main__":
    main()
