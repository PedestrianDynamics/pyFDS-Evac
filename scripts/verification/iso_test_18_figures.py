# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "fdsreader",
#     "matplotlib",
#     "numpy",
#     "pandas",
#     "pillow",
#     "seaborn",
# ]
# ///
"""Figures for the verification page "ISO 20414 Test 18: walking speed in smoke".

One occupant walks the ISO corridor (100 x 2 m, 1 m exit) once in clear air
and once under a constant extinction coefficient K. The expected result is a
hand calculation that uses no pyFDS-Evac code:

    f(K) = min(1, max(0.1, 1 + beta K / alpha)),  alpha = 0.706, beta = -0.057
    t_smoke / t_clear = 1 / f(K)

For the FDS-coupled case K is not an input: it is read from the FDS slice at
1.5 m with fdsreader and compared with what the deck prescribes,
K = 8700 m2/kg x rho x Y_soot, rho from the ideal-gas law at 20 C.

The ratio differs from 1 / f(K) only through time that does not scale with
1 / f, such as the movement model's start-up. A smoky run at speed f v0 is a
clear run at desired speed f v0, so the expected egress time comes from the
clear runs alone: fit t = L / v0 + a to the five clear runs of the v0 sweep
and predict t_pred = L / (f v0) + a. The tolerance is the fit's largest
residual plus two time steps dt. The collision-free model in the FDS case has
no inertia (a = 0), so there t_pred = t_clear / f within (1 + 1 / f) dt.

Run from the repository root::

    uv run python scripts/verification/iso_test_18_figures.py --data DIR

``DIR`` holds ``fds/`` (the coupled FDS output) and ``evac/<run>/`` with
``run.sqlite``, ``smoke_history.csv`` (smoke runs) and ``run.log`` for the runs
``clear``, ``K0.5``, ``K1``, ``K3``, ``K7.5``, ``K10``, ``v0_<v>_clear`` and
``v0_<v>_K1`` for v = 1.0, 0.75, 0.5, 0.25, ``coupled_clear`` and
``coupled_fds``. Writes ``iso18_setup.png``, ``iso18_speed_factor.png``,
``iso18_ratio.png`` and ``iso18.gif`` to ``site/static/images/verification/``.
"""

import argparse
import json
import re
import sqlite3
from pathlib import Path

import fdsreader
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib.animation import PillowWriter
from matplotlib.lines import Line2D
from matplotlib.patches import Patch, Rectangle

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "site" / "static" / "images" / "verification"
ISO = ROOT / "assets" / "ISO-table21"
COUPLED = ROOT / "assets" / "iso_table21_coupled"

# The default law, as documented in Models > Smoke-speed (FDS+Evac values).
ALPHA = 0.706
BETA = -0.057
F_MIN = 0.1
# FDS: K = MASS_EXTINCTION_COEFFICIENT x soot density, default 8700 m2/kg.
MASS_EXTINCTION = 8700.0
# Simulation time step: each egress time is a whole number of steps.
DT = 0.01
# Frantzich and Nilsson's lit-tunnel data cover this K range (Fundamentals).
K_DATA = (1.9, 7.4)
# Constants for FDS's hydrostatic density drop and the dry-air reference
# behind the deck's 1.2041 kg/m3.
G = 9.80665
W_DRY_AIR = 28.9647
V0 = 1.25
KS = (0.5, 1.0, 3.0, 7.5, 10.0)
V0S = (1.0, 0.75, 0.5, 0.25)

# One meaning, one colour, one marker across the figures.
LAW = "#4575b4"  # hand calculation: blue line
K_SWEEP = "#1f253f"  # constant-K runs at v0 = 1.25 m/s: dark circles
V0_SWEEP = "#fc8d59"  # v0 sweep at K = 1: orange triangles
FDS = "#d73027"  # K read from FDS: red diamonds
WALL = "dimgrey"
EXIT = "#33a02c"
SPAWN = "#fc8d59"
TEXT = "dimgrey"
LEGEND = dict(
    frameon=True,
    facecolor="white",
    framealpha=0.8,
    edgecolor="lightgrey",
    labelcolor="dimgrey",
)


def speed_factor(k):
    """The default (Lund) law, written out by hand."""
    return min(1.0, max(F_MIN, 1.0 + BETA * k / ALPHA))


def molar_mass(y_o2, y_soot):
    """Molar mass [g/mol] of the deck's mixture (N2 background, O2, soot)."""
    w = {"N2": 28.0134, "O2": 31.9988, "C": 12.0107}
    y_n2 = 1.0 - y_o2 - y_soot
    return 1.0 / (y_n2 / w["N2"] + y_o2 / w["O2"] + y_soot / w["C"])


def air_density(y_o2, y_soot, t_c=20.0, p=101325.0):
    """Ideal-gas density of the deck's mixture (N2 background, O2, soot)."""
    return p * molar_mass(y_o2, y_soot) * 1e-3 / (8.3144626 * (273.15 + t_c))


def deck_soot_fraction(deck):
    """The soot and O2 mass fractions of the single &INIT line in the deck."""
    y = re.findall(r"MASS_FRACTION\(\d\)=([0-9.Ee+-]+)", deck)
    return float(y[0]), float(y[1])


def read_slices(fds_dir):
    """Every horizontal K slice: {z: array (time, x, y)}, plus the times."""
    sim = fdsreader.Simulation(str(fds_dir))
    out, times = {}, None
    for sl in sim.slices:
        if sl.quantity.name != "SOOT EXTINCTION COEFFICIENT" or sl.orientation != 3:
            continue
        out[round(sl.extent.z_start, 3)] = sl.to_global(masked=False, fill=np.nan)
        times = sl.times
    return out, times


def load_run(data, name):
    """Egress time, trajectory and smoke history of one run."""
    run = data / "evac" / name
    log = (run / "run.log").read_text()
    t_end = float(
        re.search(
            r"Simulation (?:finished in|incomplete: time limit reached after) ([\d.]+) s",
            log,
        ).group(1)
    )
    con = sqlite3.connect(run / "run.sqlite")
    traj = pd.read_sql("select frame, pos_x as x, pos_y as y from trajectory_data", con)
    fps = float(
        con.execute("select value from metadata where key = 'fps'").fetchone()[0]
    )
    con.close()
    traj = traj.sort_values("frame").reset_index(drop=True)
    traj["t"] = traj["frame"] / fps
    smoke = None
    if (run / "smoke_history.csv").exists():
        smoke = pd.read_csv(run / "smoke_history.csv").dropna()
    return dict(t_end=t_end, traj=traj, smoke=smoke)


def steady_speed(traj):
    """Walking speed over the middle 40 m: path length over elapsed time."""
    mid = traj[(traj["x"] > -20.0) & (traj["x"] < 20.0)]
    path = np.hypot(np.diff(mid["x"]), np.diff(mid["y"])).sum()
    return float(path / (mid["t"].iloc[-1] - mid["t"].iloc[0]))


def style_axes(ax, frame=True):
    """Apply the house tick, grid and frame conventions to one axes."""
    ax.tick_params(axis="both", which="both", length=0, labelcolor="dimgrey")
    ax.grid(False)
    sns.despine(ax=ax, left=True, bottom=True)
    if frame:
        ax.patch.set_edgecolor("lightgrey")
        ax.patch.set_linewidth(0.8)


def bbox(stage):
    """Lower-left and upper-right corners of a polygon stage in config.json."""
    pts = np.asarray(stage["coordinates"], dtype=float)
    return pts.min(axis=0), pts.max(axis=0)


def draw_corridor(ax, cfg, spawn_style="fill"):
    """Walls, spawn box and exit of the ISO corridor."""
    ax.plot([-50, 50, 50, -50, -50], [-1, -1, 1, 1, -1], color=WALL, lw=1.4, zorder=3)
    (x0, y0), (x1, y1) = bbox(next(iter(cfg["distributions"].values())))
    if spawn_style == "fill":
        ax.add_patch(
            Rectangle((x0, y0), x1 - x0, y1 - y0, fc=SPAWN, ec="none", alpha=0.3)
        )
    (ex0, ey0), (ex1, ey1) = bbox(next(iter(cfg["exits"].values())))
    ax.add_patch(
        Rectangle((ex0, ey0), ex1 - ex0, ey1 - ey0, fc=EXIT, ec=EXIT, zorder=4)
    )


def mark_walk(ax, start, stop):
    """Start point and removal point of the occupant in the clear run."""
    ax.plot(*start, ls="none", marker="o", ms=5, color=K_SWEEP, zorder=6)
    ax.plot(*stop, ls="none", marker="x", ms=6, mew=1.4, color=K_SWEEP, zorder=6)


def plot_setup(out, iso_cfg, cpl_cfg, start, stop):
    """Figure 1: the corridor, and both ends at true scale."""
    fig = plt.figure(figsize=(8.0, 5.0), dpi=150)
    gs = fig.add_gridspec(2, 2, height_ratios=[1.0, 1.25], hspace=0.55, wspace=0.12)
    ax = fig.add_subplot(gs[0, :])
    draw_corridor(ax, iso_cfg)
    (cx0, cy0), (cx1, cy1) = bbox(next(iter(cpl_cfg["distributions"].values())))
    ax.add_patch(
        Rectangle(
            (cx0, cy0), cx1 - cx0, cy1 - cy0, fc="none", ec=SPAWN, ls="--", lw=1.0
        )
    )
    ax.annotate(
        "",
        (-50, -2.1),
        (50, -2.1),
        arrowprops=dict(arrowstyle="<->", color=TEXT, lw=0.8),
        annotation_clip=False,
    )
    ax.text(0, -2.4, "corridor 100 m", ha="center", va="top", fontsize=8.5, color=TEXT)
    mark_walk(ax, start, stop)
    ax.annotate(
        "",
        (start[0], 0.45),
        (stop[0], 0.45),
        arrowprops=dict(arrowstyle="<->", color=K_SWEEP, lw=0.8),
    )
    ax.text(
        0,
        0.2,
        f"walked ≈ {stop[0] - start[0]:.1f} m: start (●) to removal (×)",
        ha="center",
        va="top",
        fontsize=8.5,
        color=TEXT,
    )
    ax.set_xlim(-52, 52)
    ax.set_ylim(-3.2, 1.6)
    ax.set_yticks([-1, 0, 1])
    ax.set_title(
        r"$\bf{(a)}$" + "  ISO corridor, 100 × 2 m (width not to scale)",
        loc="left",
        fontsize=10,
        color=TEXT,
    )
    ax.set_xlabel("x [m]", color=TEXT, fontsize=9)
    ax.set_ylabel("y [m]", color=TEXT, fontsize=9)
    style_axes(ax, frame=False)
    ax.tick_params(labelsize=8.5)

    ends = (
        ("(b)", "spawn end, true scale", (-50.5, -45.5)),
        ("(c)", "exit end", (45.5, 50.5)),
    )
    for i, (tag, title, xlim) in enumerate(ends):
        a = fig.add_subplot(gs[1, i])
        draw_corridor(a, iso_cfg)
        a.add_patch(
            Rectangle(
                (cx0, cy0), cx1 - cx0, cy1 - cy0, fc="none", ec=SPAWN, ls="--", lw=1.0
            )
        )
        a.set_xlim(*xlim)
        a.set_ylim(-1.4, 1.4)
        a.set_aspect("equal")
        a.set_title(
            r"$\bf{" + tag + "}$  " + title, loc="left", fontsize=10, color=TEXT
        )
        a.set_xlabel("x [m]", color=TEXT, fontsize=9)
        style_axes(a, frame=False)
        a.tick_params(labelsize=8.5)
        mark_walk(a, start, stop)
        if i == 1:
            a.tick_params(labelleft=False)
            a.text(
                49.46,
                0.72,
                "exit zone\n1 × 0.92 m",
                ha="center",
                va="bottom",
                fontsize=8,
                color=TEXT,
            )
    handles = [
        Line2D([0], [0], color=WALL, lw=1.4, label="wall"),
        Patch(fc=SPAWN, alpha=0.3, label="spawn box, constant-K runs"),
        Patch(fc="none", ec=SPAWN, ls="--", label="spawn box, FDS-coupled runs"),
        Patch(fc=EXIT, ec=EXIT, label="exit zone"),
        Line2D([0], [0], ls="none", marker="o", ms=5, color=K_SWEEP, label="start"),
        Line2D(
            [0],
            [0],
            ls="none",
            marker="x",
            ms=6,
            mew=1.4,
            color=K_SWEEP,
            label="removed",
        ),
    ]
    fig.legend(
        handles=handles,
        loc="lower center",
        bbox_to_anchor=(0.5, -0.1),
        ncol=4,
        fontsize=8,
        **LEGEND,
    )
    fig.savefig(out / "iso18_setup.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def plot_speed_factor(out, rows):
    """Figure 2: the law f(K) with the recorded and the walked factors."""
    fig, ax = plt.subplots(figsize=(7.0, 4.4), dpi=150)
    k = np.linspace(0.0, 13.0, 400)
    law = np.array([speed_factor(v) for v in k])
    inside = (k >= K_DATA[0]) & (k <= K_DATA[1])
    ax.plot(k, np.where(inside, law, np.nan), color=LAW, lw=1.8, zorder=2)
    ax.plot(k, law, color=LAW, lw=1.4, ls="--", zorder=1)
    ax.axvspan(*K_DATA, color=LAW, alpha=0.07, lw=0, zorder=0)
    ax.text(
        np.mean(K_DATA),
        1.03,
        f"tunnel data, K = {K_DATA[0]}–{K_DATA[1]} /m",
        ha="center",
        va="top",
        fontsize=8,
        color=TEXT,
    )
    k_clamp = (F_MIN - 1.0) * ALPHA / BETA
    ax.axvline(k_clamp, color="lightgrey", lw=0.8, ls=":", zorder=1)
    ax.text(
        k_clamp - 0.15,
        0.62,
        f"FDS+Evac floor f = {F_MIN}\nfrom K = {k_clamp:.2f} /m\n(not reached here)",
        ha="right",
        va="top",
        fontsize=8,
        color=TEXT,
    )
    groups = (
        ("constant K", K_SWEEP, "o"),
        ("v0 sweep", V0_SWEEP, "^"),
        ("FDS", FDS, "D"),
    )
    for group, colour, marker in groups:
        sel = [r for r in rows if r["group"] == group]
        kk = [r["K"] for r in sel]
        ax.plot(
            kk,
            [r["f_recorded"] for r in sel],
            ls="none",
            marker=marker,
            ms=9,
            mfc="none",
            mec=colour,
            mew=1.3,
            zorder=4,
        )
        ax.plot(
            kk,
            [r["f_walked"] for r in sel],
            ls="none",
            marker="+",
            ms=9,
            color=colour,
            mew=1.3,
            zorder=5,
        )
    dev_rec = max(
        abs(r["f_recorded"] - r["f_hand"]) for r in rows if r["group"] != "FDS"
    )
    dev_walk = max(abs(r["f_walked"] / r["f_hand"] - 1.0) for r in rows)
    ax.text(
        5.0,
        0.9,
        "Every point lies on the law:\n"
        f"recorded factor − hand f:  max {dev_rec:.1e}\n"
        "(FDS case: inside the slice's own spread)\n"
        f"walked speed / (f v₀) − 1:  max {dev_walk:.1e}",
        fontsize=8.5,
        color=TEXT,
        va="top",
    )
    handles = [
        Line2D(
            [0],
            [0],
            color=LAW,
            lw=1.8,
            label=r"$f(K) = 1 + \beta K/\alpha$, hand calculation (dashed: no data)",
        ),
        Line2D(
            [0],
            [0],
            ls="none",
            marker="o",
            mfc="none",
            mec=K_SWEEP,
            mew=1.3,
            label="constant K, v₀ = 1.25 m/s",
        ),
        Line2D(
            [0],
            [0],
            ls="none",
            marker="^",
            mfc="none",
            mec=V0_SWEEP,
            mew=1.3,
            label="K = 1, v₀ = 1.0 … 0.25 m/s",
        ),
        Line2D(
            [0],
            [0],
            ls="none",
            marker="D",
            mfc="none",
            mec=FDS,
            mew=1.3,
            label="K read from FDS",
        ),
        Line2D(
            [0],
            [0],
            ls="none",
            marker="+",
            color="dimgrey",
            mew=1.3,
            label="open marker: recorded factor;  + walked speed / v₀",
        ),
    ]
    ax.legend(handles=handles, loc="lower left", fontsize=7.5, **LEGEND)
    ax.set_xlim(0.0, 13.0)
    ax.set_ylim(0.0, 1.05)
    ax.set_xlabel(r"extinction coefficient $K$ [1/m]", color=TEXT)
    ax.set_ylabel(r"speed factor $f$ [-]", color=TEXT)
    style_axes(ax)
    fig.savefig(out / "iso18_speed_factor.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def run_label(r):
    """Short axis label of one smoke run."""
    if r["group"] == "constant K":
        return f"K = {r['K']:g}"
    if r["group"] == "v0 sweep":
        return f"v₀ = {r['v0']:g}"
    return "FDS"


def plot_ratio(out, rows, fit):
    """Figure 3: time ratio against 1/f, and each egress time against t_pred."""
    fig, (ax, axr) = plt.subplots(
        1,
        2,
        figsize=(9.6, 4.2),
        dpi=150,
        gridspec_kw=dict(wspace=0.3, width_ratios=[1.0, 1.25]),
    )
    x = np.linspace(1.0, 5.5, 50)
    ax.plot(x, x, color=LAW, lw=1.8, zorder=2)
    markers = {
        "constant K": (K_SWEEP, "o"),
        "v0 sweep": (V0_SWEEP, "^"),
        "FDS": (FDS, "D"),
    }
    for i, r in enumerate(rows):
        colour, marker = markers[r["group"]]
        style = dict(ls="none", marker=marker, ms=8, mfc="none", mec=colour, mew=1.3)
        ax.plot(1.0 / r["f_hand"], r["ratio"], zorder=4, **style)
        diff = 1000 * (r["t_smoke"] - r["t_pred"])
        tol = 1000 * r["t_tol"]
        axr.plot([i, i], [-tol, tol], color=colour, lw=6, alpha=0.18, zorder=1)
        axr.plot(i, diff, zorder=4, **style)
    ax.text(
        1.1,
        4.9,
        "egress-time ratio = 1 / f(K)\n(ISO's expected result)",
        fontsize=8.5,
        color=TEXT,
        va="top",
    )
    for r in rows:
        if r["group"] == "constant K" and r["K"] > 2:
            ax.text(
                1.0 / r["f_hand"] + 0.12,
                r["ratio"] - 0.1,
                f"K = {r['K']:g}",
                fontsize=7.5,
                color=TEXT,
                va="top",
            )
    ax.annotate(
        "K = 0.5 and 1 /m,\nv₀ sweep and FDS case",
        (1.09, 1.09),
        (1.1, 3.6),
        fontsize=7.5,
        color=TEXT,
        arrowprops=dict(arrowstyle="-", color="lightgrey", lw=0.8),
    )
    ax.set_xlim(0.9, 5.6)
    ax.set_ylim(0.9, 5.6)
    ax.set_xlabel(r"expected $1/f(K)$ [-]", color=TEXT)
    ax.set_ylabel(r"simulated $t_\mathrm{smoke}/t_\mathrm{clear}$ [-]", color=TEXT)
    ax.set_title(r"$\bf{(a)}$" + "  time ratio", loc="left", fontsize=10, color=TEXT)

    axr.axhline(0.0, color=LAW, lw=1.2, zorder=2)
    axr.set_xticks(range(len(rows)))
    axr.set_xticklabels([run_label(r) for r in rows], rotation=45, ha="right")
    axr.tick_params(axis="x", labelsize=8)
    axr.text(
        -0.3,
        44,
        f"expected: clear-run fit t = L/v₀ + a, L = {fit['L']:.2f} m, "
        f"a = {fit['a']:.2f} s\n"
        f"bars: tolerance ± {1000 * (fit['r_max'] + 2 * DT):.0f} ms "
        f"(FDS case: ± {1000 * rows[-1]['t_tol']:.0f} ms, a = 0)",
        fontsize=8,
        color=TEXT,
        va="top",
    )
    worst = max(rows, key=lambda r: abs(r["t_smoke"] - r["t_pred"]) / r["t_tol"])
    axr.annotate(
        f"largest: {1000 * (worst['t_smoke'] - worst['t_pred']):+.0f} ms "
        f"on {worst['t_smoke']:.0f} s",
        (rows.index(worst), 1000 * (worst["t_smoke"] - worst["t_pred"])),
        (1.5, -40),
        fontsize=8,
        color=TEXT,
        arrowprops=dict(arrowstyle="-", color="lightgrey", lw=0.8),
    )
    axr.set_xlim(-0.6, len(rows) - 0.4)
    axr.set_ylim(-48, 48)
    axr.set_ylabel(r"$t_\mathrm{smoke} - t_\mathrm{pred}$ [ms]", color=TEXT)
    axr.set_title(
        r"$\bf{(b)}$" + "  egress time against expected",
        loc="left",
        fontsize=10,
        color=TEXT,
    )
    handles = [
        Line2D(
            [0],
            [0],
            ls="none",
            marker="o",
            mfc="none",
            mec=K_SWEEP,
            mew=1.3,
            label="constant K, v₀ = 1.25 m/s",
        ),
        Line2D(
            [0],
            [0],
            ls="none",
            marker="^",
            mfc="none",
            mec=V0_SWEEP,
            mew=1.3,
            label="K = 1, v₀ = 1.0 … 0.25 m/s",
        ),
        Line2D(
            [0],
            [0],
            ls="none",
            marker="D",
            mfc="none",
            mec=FDS,
            mew=1.3,
            label="K read from FDS",
        ),
    ]
    ax.legend(handles=handles, loc="lower right", fontsize=7.5, **LEGEND)
    for a in (ax, axr):
        style_axes(a)
    fig.savefig(out / "iso18_ratio.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def render_gif(out, runs, labels, iso_cfg, step_s, fps, hold_s=2.0):
    """Figure 4: stacked corridors, the occupant coloured by its speed.

    Each run carries ``K`` (tints the corridor grey) and ``t_pred`` (the
    expected egress time shown once the occupant is out).
    """
    t_max = max(r["t_end"] for r in runs)
    frames = np.arange(0.0, t_max + step_s, step_s)
    n = len(runs)
    fig, axes = plt.subplots(n, 1, figsize=(6.6, 0.62 * n + 1.1), dpi=100, sharex=True)
    cmap = sns.color_palette("viridis", as_cmap=True)
    dots, trails, notes = [], [], []
    for ax, run, label in zip(axes, runs, labels):
        grey = 1.0 - 0.45 * run["K"] / max(KS)
        ax.add_patch(
            Rectangle((-50, -1), 100, 2, fc=(grey, grey, grey), ec="none", zorder=0)
        )
        draw_corridor(ax, iso_cfg)
        ax.set_xlim(-51, 51)
        ax.set_ylim(-1.3, 1.3)
        ax.set_yticks([])
        ax.text(-49.5, 1.25, label, fontsize=8.5, color=TEXT, va="bottom")
        (trail,) = ax.plot([], [], color="lightgrey", lw=1.2, zorder=2)
        dot = ax.scatter(
            [],
            [],
            c=[],
            cmap=cmap,
            vmin=0.0,
            vmax=1.3,
            s=40,
            ec="dimgrey",
            lw=0.5,
            zorder=5,
        )
        note = ax.text(
            49.5, 1.25, "", fontsize=8.5, color=TEXT, va="bottom", ha="right"
        )
        dots.append(dot)
        trails.append(trail)
        notes.append(note)
        style_axes(ax, frame=False)
        t = run["traj"]["t"].to_numpy()
        run["speed"] = np.gradient(run["traj"]["x"].to_numpy(), t)
    axes[-1].set_xlabel("x [m]  (corridor width stretched)", color=TEXT, fontsize=8.5)
    cbar = fig.colorbar(dots[0], ax=axes, fraction=0.03, pad=0.02)
    cbar.set_label("walking speed [m/s]", color=TEXT, fontsize=8.5)
    cbar.ax.tick_params(length=0, labelcolor="dimgrey", labelsize=8)
    cbar.outline.set_visible(False)
    clock = fig.text(0.02, 0.985, "", fontsize=10, color=TEXT, va="top")
    count = fig.text(0.86, 0.985, "", fontsize=10, color=TEXT, va="top", ha="right")

    writer = PillowWriter(fps=fps)
    with writer.saving(fig, out / "iso18.gif", dpi=100):
        for tf in frames:
            done = 0
            for run, dot, trail, note in zip(runs, dots, trails, notes):
                traj = run["traj"]
                i = int(np.searchsorted(traj["t"].to_numpy(), tf, side="right")) - 1
                if tf >= run["t_end"]:
                    done += 1
                    dot.set_offsets(np.empty((0, 2)))
                    note.set_text(
                        f"out at {run['t_end']:.2f} s, expected {run['t_pred']:.2f} s"
                    )
                    trail.set_data(traj["x"], traj["y"])
                    continue
                dot.set_offsets([[traj["x"].iloc[i], traj["y"].iloc[i]]])
                dot.set_array(np.array([run["speed"][i]]))
                trail.set_data(traj["x"].iloc[: i + 1], traj["y"].iloc[: i + 1])
                note.set_text(f"{run['speed'][i]:.2f} m/s")
            clock.set_text(f"t = {tf:5.0f} s")
            count.set_text(f"out: {done} / {n}")
            writer.grab_frame()
        hold = int(hold_s * fps)
        for _ in range(hold):
            writer.grab_frame()
    plt.close(fig)
    return len(frames) + hold


def fit_clear(data):
    """Fit t = L / v0 + a to the five clear runs of the v0 sweep."""
    names = {V0: "clear", **{v: f"v0_{v:g}_clear" for v in V0S}}
    v0 = np.array(list(names))
    t = np.array([load_run(data, n)["t_end"] for n in names.values()])
    length, a = np.polyfit(1.0 / v0, t, 1)
    resid = t - (length / v0 + a)
    return dict(L=float(length), a=float(a), r_max=float(np.abs(resid).max()))


def build_rows(data, k_fds, fit):
    """Expected against simulated, one row per smoke run."""
    specs = [(f"K{k:g}", "clear", k, V0, "constant K") for k in KS]
    specs += [(f"v0_{v:g}_K1", f"v0_{v:g}_clear", 1.0, v, "v0 sweep") for v in V0S]
    specs += [("coupled_fds", "coupled_clear", k_fds, V0, "FDS")]
    rows = []
    for smoke_name, clear_name, k, v0, group in specs:
        smoke = load_run(data, smoke_name)
        clear = load_run(data, clear_name)
        f_hand = speed_factor(k)
        recorded = smoke["smoke"]["speed_factor"].to_numpy()
        ratio = smoke["t_end"] / clear["t_end"]
        if group == "FDS":
            # Collision-free model: no inertia, so t = L / v exactly.
            t_pred = clear["t_end"] / f_hand
            t_tol = (1.0 + 1.0 / f_hand) * DT
        else:
            t_pred = fit["L"] / (f_hand * v0) + fit["a"]
            t_tol = fit["r_max"] + 2 * DT
        rows.append(
            dict(
                name=smoke_name,
                group=group,
                K=k,
                v0=v0,
                f_hand=f_hand,
                f_recorded=float(recorded[np.argmax(np.abs(recorded - f_hand))]),
                f_walked=steady_speed(smoke["traj"]) / v0,
                t_clear=clear["t_end"],
                t_smoke=smoke["t_end"],
                t_pred=t_pred,
                t_tol=t_tol,
                ratio=ratio,
                rel_err=ratio * f_hand - 1.0,
                k_recorded=(
                    float(smoke["smoke"]["extinction_per_m"].min()),
                    float(smoke["smoke"]["extinction_per_m"].max()),
                ),
            )
        )
    return rows


def check_criteria(rows, fds_checks):
    """The page's pass criteria; returns one line per failed check."""
    fails = [f"FDS case: {name}" for name, ok in fds_checks.items() if not ok]
    for r in rows:
        if r["group"] != "FDS" and abs(r["f_recorded"] - r["f_hand"]) > 1e-12:
            fails.append(f"{r['name']}: recorded factor differs from f(K)")
        if abs(r["f_walked"] / r["f_hand"] - 1.0) > 1e-5:
            fails.append(f"{r['name']}: walked speed differs from f v0")
        if abs(r["t_smoke"] - r["t_pred"]) > r["t_tol"]:
            fails.append(f"{r['name']}: egress time outside the tolerance")
    return fails


def main():
    """Compute the hand calculation, compare it with the runs, draw the figures.

    Parameters
    ----------
    --data : path
        Directory with ``fds/`` and ``evac/<run>/``.

    Saves
    -----
    site/static/images/verification/iso18_setup.png
    site/static/images/verification/iso18_speed_factor.png
    site/static/images/verification/iso18_ratio.png
    site/static/images/verification/iso18.gif
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--data", type=Path, required=True, help="directory with fds/ and evac/<run>/"
    )
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    # --- Style Setup ---
    sns.set_theme(font_scale=1.0, style="whitegrid", font="DejaVu Sans")

    # --- Data: FDS, and what the deck prescribes ---
    k_slices, times = read_slices(args.data / "fds")
    deck = (COUPLED / "iso_table21_coupled.fds").read_text()
    y_soot, y_o2 = deck_soot_fraction(deck)
    rho = air_density(y_o2, y_soot)
    k_deck = MASS_EXTINCTION * rho * y_soot
    w_mix = molar_mass(y_o2, y_soot)
    print(
        f"deck: Y_soot = {y_soot:.6e}, Y_O2 = {y_o2}, W = {w_mix:.3f} g/mol "
        f"(dry air {W_DRY_AIR}: {w_mix / W_DRY_AIR - 1:+.2%}), "
        f"rho = {rho:.5f} kg/m3 -> K = {k_deck:.5f} /m"
    )
    k_range = {}
    for z, arr in sorted(k_slices.items()):
        k_range[z] = (float(np.nanmin(arr)), float(np.nanmax(arr)))
        hydro = rho * G * z / 101325.0
        mid = 0.5 * sum(k_range[z])
        print(
            f"K slice z = {z:g} m: {k_range[z][0]:.7f}-{k_range[z][1]:.7f} /m "
            f"over {arr.shape[0]} times {[round(float(t), 1) for t in times]}; "
            f"1 - slice/deck = {1 - mid / k_deck:.2e}, rho g z / p = {hydro:.2e}"
        )
    z_agent = min(k_slices, key=lambda z: abs(z - 1.6))
    k_fds = float(np.nanmean(k_slices[z_agent]))

    # --- Data: pyFDS-Evac runs against the hand calculation ---
    fit = fit_clear(args.data)
    print(
        f"t = L / v0 + a over the 5 clear runs: L = {fit['L']:.3f} m, "
        f"a = {fit['a']:.3f} s, largest residual {fit['r_max']:.4f} s"
    )
    rows = build_rows(args.data, k_fds, fit)
    print(
        f"{'run':12s} {'K':>7s} {'v0':>5s} {'f hand':>9s} {'t_clear':>8s} "
        f"{'t_smoke':>8s} {'t_pred':>8s} {'diff':>7s} {'tol':>6s} {'1/f':>8s} "
        f"{'ratio':>8s} {'err %':>7s} {'f rec-hand':>10s} {'walk/fv0-1':>10s}"
    )
    for r in rows:
        print(
            f"{r['name']:12s} {r['K']:7.4f} {r['v0']:5.2f} {r['f_hand']:9.6f} "
            f"{r['t_clear']:8.2f} {r['t_smoke']:8.2f} {r['t_pred']:8.3f} "
            f"{r['t_smoke'] - r['t_pred']:+7.4f} {r['t_tol']:6.4f} "
            f"{1 / r['f_hand']:8.5f} {r['ratio']:8.5f} {100 * r['rel_err']:+7.3f} "
            f"{r['f_recorded'] - r['f_hand']:+10.1e} "
            f"{r['f_walked'] / r['f_hand'] - 1:+10.1e}"
        )
    cpl = next(r for r in rows if r["group"] == "FDS")
    k_lo, k_hi = k_range[z_agent]
    z_other = [z for z in k_range if z != z_agent]
    smoke = load_run(args.data, "coupled_fds")["smoke"]
    k_rec = smoke["extinction_per_m"]
    fds_checks = {
        f"recorded K inside the {z_agent:g} m slice": k_rec.between(k_lo, k_hi).all(),
        "recorded factor inside f of that range": smoke["speed_factor"]
        .between(speed_factor(k_hi), speed_factor(k_lo))
        .all(),
    }
    for z in z_other:
        fds_checks[f"recorded K outside the {z:g} m slice"] = not (
            k_rec.between(*k_range[z]).any()
        )
    print(
        f"coupled run recorded K = {cpl['k_recorded'][0]:.7f}-{cpl['k_recorded'][1]:.7f}"
    )
    for name, ok in fds_checks.items():
        print(f"  {name}: {bool(ok)}")
    fails = check_criteria(rows, fds_checks)
    print("pass criteria:", "all met" if not fails else "FAILED")
    for line in fails:
        print("  " + line)

    # --- Plot ---
    iso_cfg = json.loads((ISO / "config.json").read_text())
    cpl_cfg = json.loads((COUPLED / "config.json").read_text())
    clear = load_run(args.data, "clear")
    traj = clear["traj"]
    last = traj.iloc[-1]
    start = (float(traj["x"].iloc[0]), float(traj["y"].iloc[0]))
    stop = (
        float(last["x"]) + V0 * (clear["t_end"] - float(last["t"])),
        float(last["y"]),
    )
    print(
        f"clear run: start x = {start[0]:.2f} m, removed at x = {stop[0]:.2f} m, "
        f"walked {stop[0] - start[0]:.2f} m"
    )
    plot_setup(OUT, iso_cfg, cpl_cfg, start, stop)
    plot_speed_factor(OUT, rows)
    plot_ratio(OUT, rows, fit)
    gif_names = ("clear", "K1", "K3", "K7.5", "K10")
    gif_runs = [load_run(args.data, name) for name in gif_names]
    by_name = {r["name"]: r for r in rows}
    for name, run in zip(gif_names, gif_runs):
        run["K"] = by_name[name]["K"] if name in by_name else 0.0
        run["t_pred"] = (
            by_name[name]["t_pred"] if name in by_name else fit["L"] / V0 + fit["a"]
        )
    labels = ["clear air"] + [
        f"K = {k:g} /m,  f = {speed_factor(k):.3f}" for k in (1.0, 3.0, 7.5, 10.0)
    ]
    frames = render_gif(OUT, gif_runs, labels, iso_cfg, step_s=2.0, fps=20)
    size = (OUT / "iso18.gif").stat().st_size / 1e6
    print(f"iso18.gif: {frames} frames, {size:.2f} MB")
    if fails:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
