# /// script
# requires-python = ">=3.11"
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
1 / f. The movement model's start-up is such a term: an occupant that relaxes
to its desired speed with time constant tau loses tau in both runs, which moves
the ratio by -tau (1 - f) / t_clear. Each egress time is also a whole number
of time steps dt. The pass band is (2 tau (1 - f) + 2 dt) / t_clear.

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
# Social force model relaxation time in assets/ISO-table21/config.json.
TAU = 0.5
V0 = 1.25
KS = (0.5, 1.0, 3.0, 7.5, 10.0)
V0S = (1.0, 0.75, 0.5, 0.25)
# Tolerance allowed by the pytest tests, quoted for comparison only.
TEST_TOL = 0.08

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


def air_density(y_o2, y_soot, t_c=20.0, p=101325.0):
    """Ideal-gas density of the deck's mixture (N2 background, O2, soot)."""
    w = {"N2": 28.0134, "O2": 31.9988, "C": 12.0107}
    y_n2 = 1.0 - y_o2 - y_soot
    w_mix = 1.0 / (y_n2 / w["N2"] + y_o2 / w["O2"] + y_soot / w["C"])
    return p * w_mix * 1e-3 / (8.3144626 * (273.15 + t_c))


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
    t_end = float(re.search(r"Simulation finished in ([\d.]+) s", log).group(1))
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
    """Walking speed over the middle 40 m, fitted to x(t)."""
    mid = traj[(traj["x"] > -20.0) & (traj["x"] < 20.0)]
    return float(np.polyfit(mid["t"], mid["x"], 1)[0])


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


def plot_setup(out, iso_cfg, cpl_cfg, k_slices, k_deck):
    """Figure 1: the corridor, both ends at true scale, and the FDS slices."""
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
    ax.text(0, -2.4, "100 m", ha="center", va="top", fontsize=8.5, color=TEXT)
    ax.text(
        0,
        0,
        "one occupant walks to the exit;  v₀ = 1.25 m/s;  K constant everywhere",
        ha="center",
        va="center",
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
        if i == 1:
            a.tick_params(labelleft=False)
            a.text(
                49.46,
                0.72,
                "exit\n1 m",
                ha="center",
                va="bottom",
                fontsize=8,
                color=TEXT,
            )
    zs = sorted(k_slices)
    k_text = ",  ".join(
        f"{np.nanmin(k_slices[z]):.5f}–{np.nanmax(k_slices[z]):.5f} /m at z = {z:g} m"
        for z in zs
    )
    fig.text(
        0.5,
        -0.02,
        f"FDS-coupled case: K read from the slices, {k_text};  "
        f"the deck prescribes {k_deck:.5f} /m",
        ha="center",
        fontsize=8,
        color=TEXT,
    )
    handles = [
        Line2D([0], [0], color=WALL, lw=1.4, label="wall"),
        Patch(fc=SPAWN, alpha=0.3, label="spawn box, constant-K runs"),
        Patch(fc="none", ec=SPAWN, ls="--", label="spawn box, FDS-coupled runs"),
        Patch(fc=EXIT, ec=EXIT, label="exit"),
    ]
    fig.legend(
        handles=handles,
        loc="lower center",
        bbox_to_anchor=(0.5, -0.12),
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
    ax.plot(k, [speed_factor(v) for v in k], color=LAW, lw=1.8, zorder=2)
    k_clamp = (F_MIN - 1.0) * ALPHA / BETA
    ax.axvline(k_clamp, color="lightgrey", lw=0.8, ls=":", zorder=1)
    ax.text(
        k_clamp - 0.15,
        0.62,
        f"floor f = {F_MIN}\nfrom K = {k_clamp:.2f} /m\n(not reached here)",
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
        0.93,
        "Every point lies on the law:\n"
        f"recorded factor − hand f:  ≤ {max(dev_rec, 1e-17):.0e}\n"
        "(FDS case: inside the slice's own spread)\n"
        f"walked speed / (f v₀) − 1:  ≤ {dev_walk:.0e}",
        fontsize=8.5,
        color=TEXT,
        va="top",
    )
    handles = [
        Line2D([0], [0], color=LAW, lw=1.8, label="f(K) = 1 + βK/α, hand calculation"),
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
    ax.set_xlabel("extinction coefficient K [1/m]", color=TEXT)
    ax.set_ylabel("speed factor f [-]", color=TEXT)
    style_axes(ax)
    fig.savefig(out / "iso18_speed_factor.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def plot_ratio(out, rows):
    """Figure 3: time ratio against 1/f, and its relative error with the band."""
    fig, (ax, axr) = plt.subplots(
        1, 2, figsize=(9.0, 4.0), dpi=150, gridspec_kw=dict(wspace=0.28)
    )
    x = np.linspace(1.0, 5.5, 50)
    ax.plot(x, x, color=LAW, lw=1.8, zorder=2)
    markers = {
        "constant K": (K_SWEEP, "o"),
        "v0 sweep": (V0_SWEEP, "^"),
        "FDS": (FDS, "D"),
    }
    for r in rows:
        colour, marker = markers[r["group"]]
        for a, y in ((ax, r["ratio"]), (axr, 100 * r["rel_err"])):
            a.plot(
                1.0 / r["f_hand"],
                y,
                ls="none",
                marker=marker,
                ms=8,
                mfc="none",
                mec=colour,
                mew=1.3,
                zorder=4,
            )
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
    ax.set_xlabel("expected 1 / f(K) [-]", color=TEXT)
    ax.set_ylabel("simulated t_smoke / t_clear [-]", color=TEXT)
    ax.set_title(r"$\bf{(a)}$" + "  time ratio", loc="left", fontsize=10, color=TEXT)

    # The band: relative error <= 2 tau (1 - f) / t_clear, at v0 = 1.25 m/s.
    t_clear = next(r["t_clear"] for r in rows if r["name"] == "K1")
    fx = np.linspace(0.18, 1.0, 200)
    band = 100 * (2 * TAU * (1 - fx) + 2 * 0.01) / t_clear
    axr.fill_between(1 / fx, -band, band, color=LAW, alpha=0.15, lw=0, zorder=1)
    axr.axhline(0.0, color=LAW, lw=1.2, zorder=2)
    axr.text(
        1.1,
        -1.15,
        f"band at v₀ = 1.25 m/s: ± (2τ(1 − f) + 2Δt) / t_clear\n"
        f"with τ = {TAU} s and Δt = 0.01 s",
        fontsize=8,
        color=TEXT,
        va="bottom",
    )
    worst = max(rows, key=lambda r: abs(r["rel_err"]) / r["tol"])
    axr.annotate(
        f"largest: {100 * worst['rel_err']:+.2f} %\n(band {100 * worst['tol']:.2f} %;"
        f" pytest allows {100 * TEST_TOL:.0f} %)",
        (1.0 / worst["f_hand"], 100 * worst["rel_err"]),
        (2.6, 0.55),
        fontsize=8,
        color=TEXT,
        arrowprops=dict(arrowstyle="-", color="lightgrey", lw=0.8),
    )
    axr.set_xlim(0.9, 5.6)
    axr.set_ylim(-1.2, 1.2)
    axr.set_xlabel("expected 1 / f(K) [-]", color=TEXT)
    axr.set_ylabel("(simulated − expected) / expected [%]", color=TEXT)
    axr.set_title(
        r"$\bf{(b)}$" + "  relative error", loc="left", fontsize=10, color=TEXT
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


def render_gif(out, runs, labels, iso_cfg, step_s, fps):
    """Figure 4: stacked corridors, the occupant coloured by its speed."""
    t_max = max(r["t_end"] for r in runs)
    frames = np.arange(0.0, t_max + step_s, step_s)
    n = len(runs)
    fig, axes = plt.subplots(n, 1, figsize=(6.6, 0.62 * n + 1.1), dpi=100, sharex=True)
    cmap = sns.color_palette("viridis", as_cmap=True)
    dots, trails, notes = [], [], []
    for ax, run, label in zip(axes, runs, labels):
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
                    note.set_text(f"out at {run['t_end']:.1f} s")
                    trail.set_data(traj["x"], traj["y"])
                    continue
                dot.set_offsets([[traj["x"].iloc[i], traj["y"].iloc[i]]])
                dot.set_array(np.array([run["speed"][i]]))
                trail.set_data(traj["x"].iloc[: i + 1], traj["y"].iloc[: i + 1])
                note.set_text(f"{run['speed'][i]:.2f} m/s")
            clock.set_text(f"t = {tf:5.0f} s")
            count.set_text(f"out: {done} / {n}")
            writer.grab_frame()
    plt.close(fig)
    return len(frames)


def build_rows(data, k_fds):
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
        # The coupled runs use the collision-free model, which has no inertia.
        tau = TAU if group != "FDS" else 0.0
        dt = 0.05 if group == "FDS" else 0.01
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
                ratio=ratio,
                rel_err=ratio * f_hand - 1.0,
                tol=(2 * tau * (1 - f_hand) + 2 * dt) / clear["t_end"],
                k_recorded=(
                    float(smoke["smoke"]["extinction_per_m"].min()),
                    float(smoke["smoke"]["extinction_per_m"].max()),
                ),
            )
        )
    return rows


def check_criteria(rows, fds_inside):
    """The page's pass criteria; returns one line per failed check."""
    fails = []
    if not fds_inside:
        fails.append("FDS case: recorded K or factor outside the slice's range")
    for r in rows:
        if r["group"] != "FDS" and abs(r["f_recorded"] - r["f_hand"]) > 1e-12:
            fails.append(f"{r['name']}: recorded factor differs from f(K)")
        if abs(r["f_walked"] / r["f_hand"] - 1.0) > 1e-5:
            fails.append(f"{r['name']}: walked speed differs from f v0")
        if abs(r["rel_err"]) > r["tol"]:
            fails.append(f"{r['name']}: time ratio outside the band")
    return fails


def fit_start_up(rows):
    """Fit t = L / v + a to the clear run and the constant-K runs at 1.25 m/s."""
    sel = [r for r in rows if r["group"] == "constant K"]
    inv_v = [1.0 / V0] + [1.0 / (r["f_hand"] * V0) for r in sel]
    t = [sel[0]["t_clear"]] + [r["t_smoke"] for r in sel]
    length, a = np.polyfit(inv_v, t, 1)
    resid = np.asarray(t) - (length * np.asarray(inv_v) + a)
    return length, a, float(np.abs(resid).max())


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
    z_agent = min(k_slices, key=lambda z: abs(z - 1.6))
    k_fds = float(np.nanmean(k_slices[z_agent]))
    for z, arr in sorted(k_slices.items()):
        print(
            f"K slice z = {z:g} m: {np.nanmin(arr):.7f}-{np.nanmax(arr):.7f} /m "
            f"over {arr.shape[0]} times {[round(float(t), 1) for t in times]}"
        )
    print(
        f"deck: Y_soot = {y_soot:.6e}, rho = {rho:.5f} kg/m3 -> K = {k_deck:.5f} /m; "
        f"slice at {z_agent:g} m / deck - 1 = {k_fds / k_deck - 1:+.2e}"
    )

    # --- Data: pyFDS-Evac runs against the hand calculation ---
    rows = build_rows(args.data, k_fds)
    print(
        f"{'run':12s} {'K':>7s} {'v0':>5s} {'f hand':>9s} {'t_clear':>8s} "
        f"{'t_smoke':>8s} {'1/f':>8s} {'ratio':>8s} {'err %':>7s} {'band %':>7s} "
        f"{'f rec-hand':>10s} {'walk/fv0-1':>10s}"
    )
    for r in rows:
        print(
            f"{r['name']:12s} {r['K']:7.4f} {r['v0']:5.2f} {r['f_hand']:9.6f} "
            f"{r['t_clear']:8.2f} {r['t_smoke']:8.2f} {1 / r['f_hand']:8.5f} "
            f"{r['ratio']:8.5f} {100 * r['rel_err']:+7.3f} {100 * r['tol']:7.3f} "
            f"{r['f_recorded'] - r['f_hand']:+10.1e} "
            f"{r['f_walked'] / r['f_hand'] - 1:+10.1e}"
        )
    length, a, resid = fit_start_up(rows)
    print(
        f"t = L / v + a over the 6 runs at v0 = 1.25 m/s: L = {length:.2f} m, "
        f"a = {a:.3f} s, largest residual {resid:.3f} s"
    )
    cpl = next(r for r in rows if r["group"] == "FDS")
    k_lo = float(np.nanmin(k_slices[z_agent]))
    k_hi = float(np.nanmax(k_slices[z_agent]))
    smoke = load_run(args.data, "coupled_fds")["smoke"]
    inside = (
        smoke["extinction_per_m"].between(k_lo, k_hi).all()
        and smoke["speed_factor"].between(speed_factor(k_hi), speed_factor(k_lo)).all()
    )
    print(
        f"coupled run recorded K = {cpl['k_recorded'][0]:.7f}-{cpl['k_recorded'][1]:.7f}; "
        f"K and factor inside the slice's spread: {inside}"
    )
    fails = check_criteria(rows, inside)
    print("pass criteria:", "all met" if not fails else "FAILED")
    for line in fails:
        print("  " + line)

    # --- Plot ---
    iso_cfg = json.loads((ISO / "config.json").read_text())
    cpl_cfg = json.loads((COUPLED / "config.json").read_text())
    plot_setup(OUT, iso_cfg, cpl_cfg, k_slices, k_deck)
    plot_speed_factor(OUT, rows)
    plot_ratio(OUT, rows)
    gif_names = ("clear", "K1", "K3", "K7.5", "K10")
    gif_runs = [load_run(args.data, name) for name in gif_names]
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
