# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "fdsreader>=1.11.7,<1.12",
#     "matplotlib",
#     "numpy",
#     "pandas",
#     "pillow",
#     "seaborn",
# ]
# ///
"""Figures for the verification page "ISO 20414 Test 19: incapacitation by toxic gases".

ISO 20414 Table 22: one occupant, held at the centre of a 10 x 10 x 3 m room
by a pre-evacuation time above 1e7 s, breathes a constant gas mixture. The
time at which its FED reaches 1 must equal a hand calculation. Four mixtures,
from Fig. 8 of the FDS+Evac guide, separate the three terms:

    a  CO2 2 %,    CO 0.1 %, O2 15 %   all three terms
    b  CO2 0,      CO 0,     O2 12 %   O2 alone
    c  CO2 0,      CO 0.1 %, O2 21 %   CO alone
    d  CO2 3.43 %, CO 0.1 %, O2 21 %   CO with the CO2 factor

The hand calculation uses no pyFDS-Evac code (FDS form, t in minutes):

    r_CO  = 2.764e-5 C_CO^1.036           C_CO in ppm
    HV    = exp(0.1903 C_CO2 + 2.0004)/7.1 if C_CO2 > 0, else 1   (C_CO2 in %)
    r_O2  = 1 / exp(8.13 - 0.54 (20.9 - C_O2)) if C_O2 < 20 %, else 0
    t*    = 60 / (r_CO HV + r_O2)   [s]

with the concentrations read from the FDS slices. FDS's own FED device at the
occupant is the second, independent reference.

Run from the repository root::

    uv run python scripts/verification/iso_test19_figures.py --data DIR

``DIR`` holds ``fds/{a,b,c,d}/`` (FDS output with ``_devc.csv``) and
``evac/{a,b,c,d}/fed_history.csv``. Writes ``iso_test19_setup.png``,
``iso_test19_terms.png``, ``iso_test19_fed.png``, ``iso_test19_crossing.png``
and ``iso_test19.gif`` to ``site/static/images/verification/``.
"""

import argparse
import math
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from _fdsreader_open import open_fds_case
from matplotlib.animation import PillowWriter
from matplotlib.lines import Line2D
from matplotlib.patches import Patch, Rectangle

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "site" / "static" / "images" / "verification"
CASES = "abcd"
# Prescribed volume fractions in %, Fig. 8 of the FDS+Evac guide.
PRESCRIBED = {
    "a": {"co2": 2.00, "co": 0.10, "o2": 15.0, "label": "all three terms"},
    "b": {"co2": 0.00, "co": 0.00, "o2": 12.0, "label": "O₂ alone"},
    "c": {"co2": 0.00, "co": 0.10, "o2": 21.0, "label": "CO alone"},
    "d": {"co2": 3.43, "co": 0.10, "o2": 21.0, "label": "CO + CO₂ factor"},
}
ROOM = (0.0, 0.0, 10.0, 10.0)
SPAWN = (4.4, 4.4, 5.6, 5.6)
EXIT_BOX = (9.0, 9.0, 9.8, 9.8)
DEVICE = (5.0, 5.0)
# FDS's CO coefficient (func.f90, light work) against the guide's 2.764e-5.
FDS_CO_COEF = 2.7641667e-5
CONC_TOL = 1e-4
FED_TOL = 1e-9
FDS_TOL = 1e-6

SIM = "#1f253f"  # pyFDS-Evac occupant: dark solid line, filled dot
HAND = "#4575b4"  # hand calculation: blue dashed line
FDS = "#d73027"  # FDS FED device: red open circles
TERM_CO = "#90c1c6"
TERM_CO2 = "#446485"
TERM_O2 = "#fc8d59"
WALL = "dimgrey"
EXIT = "#33a02c"
SPAWN_C = "#fee090"
TEXT = "dimgrey"
LEGEND = dict(
    frameon=True,
    facecolor="white",
    framealpha=0.8,
    edgecolor="lightgrey",
    labelcolor="dimgrey",
)


def style_axes(ax, frame=True):
    """Apply the house tick, grid and frame conventions to one axes."""
    ax.tick_params(axis="both", which="both", length=0, labelcolor="dimgrey")
    ax.grid(False)
    sns.despine(ax=ax, left=True, bottom=True)
    if frame:
        ax.patch.set_edgecolor("lightgrey")
        ax.patch.set_linewidth(0.8)


def read_gas(fds_dir):
    """Volume fractions (CO ppm, CO2 %, O2 %) and their spread over the slices."""
    sim = open_fds_case(str(fds_dir))
    names = {
        "CARBON MONOXIDE VOLUME FRACTION": ("co_ppm", 1e6),
        "CARBON DIOXIDE VOLUME FRACTION": ("co2", 100.0),
        "OXYGEN VOLUME FRACTION": ("o2", 100.0),
    }
    gas, spread, z = {}, 0.0, set()
    for sl in sim.slices:
        if sl.quantity.name not in names or sl.orientation != 3:
            continue
        key, scale = names[sl.quantity.name]
        data = sl.to_global(masked=False, fill=np.nan) * scale
        gas[key] = float(np.nanmean(data))
        spread = max(spread, float(np.nanmax(data) - np.nanmin(data)))
        z.add(round(sl.extent.z_start, 3))
        gas["n_times"] = data.shape[0]
    gas["spread"] = spread
    gas["z"] = sorted(z)
    return gas


def hand_rates(gas):
    """Per-term FED rates in 1/min, FDS form, without pyFDS-Evac code."""
    c = gas["co_ppm"]
    r_co = 2.764e-5 * c**1.036 if c > 0 else 0.0
    hv = math.exp(0.1903 * gas["co2"] + 2.0004) / 7.1 if gas["co2"] > 0 else 1.0
    r_o2 = 1.0 / math.exp(8.13 - 0.54 * (20.9 - gas["o2"])) if gas["o2"] < 20 else 0.0
    return {"r_co": r_co, "hv": hv, "r_o2": r_o2, "total": r_co * hv + r_o2}


def fds_crossing(devc):
    """Time at which FDS's FED device reaches 1, linear between rows."""
    return float(np.interp(1.0, devc["FED_occupant"], devc["Time"]))


def check_occupant_gas(case, hist, gas):
    """Assert the gas in fed_history.csv equals the FDS slice value."""
    pairs = (
        ("co_percent", 1e4, "co_ppm"),
        ("co2_percent", 1.0, "co2"),
        ("o2_percent", 1.0, "o2"),
    )
    for column, scale, key in pairs:
        seen = hist[column].to_numpy() * scale
        ref = gas[key]
        if ref == 0.0:
            assert np.all(seen == 0.0), f"{case}: {column} not 0"
            continue
        dev = float(np.abs(seen / ref - 1.0).max())
        assert dev <= CONC_TOL, f"{case}: {column} off the slice by {dev:.1e}"


def o2_gate_shift(case, gas, t_star):
    """Print how far t* would move if the O2 < 20 % gate were missing."""
    if gas["o2"] < 20:
        return
    r = hand_rates(gas)
    r_o2 = 1.0 / math.exp(8.13 - 0.54 * (20.9 - gas["o2"]))
    shift = t_star - 60.0 / (r["total"] + r_o2)
    print(f"     without the O2 gate: {r_o2:.2e} /min more, t* {shift:.1f} s earlier")


def first_true(hist, column):
    """First time_s where a boolean column is true, or NaN."""
    rows = hist[hist[column]]
    return float(rows["time_s"].iloc[0]) if len(rows) else float("nan")


def load_history(path):
    """Read fed_history.csv and derive the crossing and incapacitation flags."""
    hist = pd.read_csv(path).sort_values("time_s").reset_index(drop=True)
    hist["incapacitated"] = hist["incapacitated"].astype(str).str.lower() == "true"
    hist["crossed"] = hist["fed_cumulative"] >= 1.0
    return hist


def draw_room(ax, pos, labels):
    """Walls, spawn box, unused exit and the occupant on a plan view."""
    x0, y0, x1, y1 = ROOM
    ax.plot([x0, x1, x1, x0, x0], [y0, y0, y1, y1, y0], color=WALL, lw=1.6)
    sx0, sy0, sx1, sy1 = SPAWN
    ax.add_patch(
        Rectangle((sx0, sy0), sx1 - sx0, sy1 - sy0, fc=SPAWN_C, ec="none", alpha=0.6)
    )
    ex0, ey0, ex1, ey1 = EXIT_BOX
    ax.add_patch(
        Rectangle(
            (ex0, ey0), ex1 - ex0, ey1 - ey0, fc="none", ec=EXIT, hatch="////", lw=1.0
        )
    )
    if labels:
        ax.plot(*pos, "o", ms=9, mfc=SIM, mec="white", zorder=5)
        ax.plot(*DEVICE, "+", ms=11, mew=1.6, color=FDS, zorder=6)
    ax.set_xlim(-0.6, 10.6)
    ax.set_ylim(-0.6, 10.6)
    ax.set_aspect("equal")


def plot_setup(out, pos, z_slice):
    """Figure 1: plan of the ISO room with occupant, FED device and exit."""
    fig, ax = plt.subplots(figsize=(5.6, 5.2), dpi=150)
    ax.add_patch(Rectangle((0, 0), 10, 10, fc="#f0f0f0", ec="none", zorder=0))
    draw_room(ax, pos, labels=True)
    ax.annotate(
        f"occupant at ({pos[0]:.2f}, {pos[1]:.2f}) m,\n"
        "held by a pre-evacuation time > 10⁷ s",
        xy=pos,
        xytext=(0.5, 2.2),
        fontsize=8.5,
        color=TEXT,
        arrowprops=dict(arrowstyle="-", color=TEXT, lw=0.8),
    )
    ax.annotate(
        "FDS FED device at (5, 5, 1.6) m",
        xy=DEVICE,
        xytext=(4.6, 7.6),
        fontsize=8.5,
        color=TEXT,
        arrowprops=dict(arrowstyle="-", color=TEXT, lw=0.8),
    )
    ax.text(
        9.4,
        8.6,
        "exit, never reached",
        ha="right",
        va="top",
        fontsize=8.5,
        color=TEXT,
    )
    ax.text(
        5.0,
        0.5,
        f"Gas slices at z = {z_slice:g} m: uniform, constant, one mixture per case",
        ha="center",
        fontsize=8.5,
        color=TEXT,
    )
    handles = [
        Line2D([0], [0], color=WALL, lw=1.6, label="wall (10 × 10 m, 3 m high)"),
        Patch(fc=SPAWN_C, alpha=0.6, label="spawn area"),
        Line2D(
            [0],
            [0],
            ls="none",
            marker="o",
            mfc=SIM,
            mec="white",
            ms=8,
            label="occupant",
        ),
        Line2D(
            [0],
            [0],
            ls="none",
            marker="+",
            color=FDS,
            mew=1.6,
            ms=10,
            label="FDS FED device",
        ),
        Patch(fc="none", ec=EXIT, hatch="////", label="exit"),
    ]
    ax.legend(
        handles=handles,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.1),
        ncol=3,
        fontsize=8,
        **LEGEND,
    )
    ax.set_xlabel("x [m]", color=TEXT)
    ax.set_ylabel("y [m]", color=TEXT)
    style_axes(ax, frame=False)
    fig.savefig(out / "iso_test19_setup.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def plot_terms(out, rates, t_star):
    """Figure 2: expected FED rate per case, split into its three terms."""
    fig, ax = plt.subplots(figsize=(7.0, 3.4), dpi=150)
    ys = np.arange(len(CASES))[::-1]
    for y, case in zip(ys, CASES):
        r = rates[case]
        co = r["r_co"]
        co2 = r["r_co"] * (r["hv"] - 1.0)
        o2 = r["r_o2"]
        left = 0.0
        for width, color, hatch in (
            (co, TERM_CO, ""),
            (co2, TERM_CO2, "////"),
            (o2, TERM_O2, "...."),
        ):
            if width > 0:
                ax.barh(
                    y,
                    width,
                    left=left,
                    height=0.6,
                    color=color,
                    hatch=hatch,
                    ec="white",
                    lw=0.6,
                )
            left += width
        ax.text(
            left + 0.001,
            y,
            f"{r['total']:.5f} /min → t* = {t_star[case]:.1f} s",
            va="center",
            fontsize=8.5,
            color=TEXT,
        )
    ax.set_yticks(ys)
    ax.set_yticklabels([f"{c}: {PRESCRIBED[c]['label']}" for c in CASES])
    ax.set_xlim(0.0, 0.135)
    ax.set_xlabel("expected FED rate [1/min]", color=TEXT)
    ax.text(
        0.134,
        ys[2],
        "c and d share the CO;\nd is twice as fast because\nof the CO₂ factor (HV = 2.0)",
        ha="right",
        va="center",
        fontsize=8.5,
        color=TEXT,
    )
    handles = [
        Patch(fc=TERM_CO, label="CO: r_CO"),
        Patch(fc=TERM_CO2, hatch="////", ec="white", label="CO₂ factor: r_CO (HV − 1)"),
        Patch(fc=TERM_O2, hatch="....", ec="white", label="O₂: r_O2"),
    ]
    ax.legend(
        handles=handles,
        loc="upper center",
        bbox_to_anchor=(0.45, -0.22),
        ncol=3,
        fontsize=8,
        **LEGEND,
    )
    style_axes(ax)
    fig.savefig(out / "iso_test19_terms.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def draw_zoom(ax, h, d, rate_s, t_star, t_sim):
    """Inset over t* +- 2 s: the 1 s update grid decides the stop time."""
    ins = ax.inset_axes((0.07, 0.45, 0.42, 0.39))
    t0, t1 = t_star - 2.0, t_star + 2.0
    for tu in np.arange(math.ceil(t0), t1 + 1e-9):
        ins.axvline(tu, color="lightgrey", lw=0.6, zorder=0)
    ins.axhline(1.0, color="lightgrey", lw=0.8, zorder=0)
    t = np.linspace(t0, t1, 3)
    ins.plot(t, rate_s * t, color=HAND, lw=1.8, ls="--", zorder=2)
    win = h[(h["time_s"] >= t0 - 1) & (h["time_s"] <= t1 + 1)]
    ins.plot(
        win["time_s"],
        win["fed_cumulative"],
        color=SIM,
        lw=1.2,
        drawstyle="steps-post",
        zorder=3,
    )
    dw = d[(d["Time"] >= t0 - 1) & (d["Time"] <= t1 + 1)]
    ins.plot(
        dw["Time"], dw["FED_occupant"], "o", ms=3.5, mfc="white", mec=FDS, zorder=4
    )
    fed_stop = float(win.loc[win["time_s"] == t_sim, "fed_cumulative"].iloc[0])
    ins.plot(t_sim, fed_stop, "x", color="black", ms=6, mew=1.4, zorder=5)
    ins.annotate(
        f"stop +{t_sim - t_star:.2f} s",
        xy=(t_sim, fed_stop),
        xytext=(t0 + 0.15, 1.0014),
        fontsize=7,
        color=TEXT,
        arrowprops=dict(arrowstyle="-", color=TEXT, lw=0.6),
    )
    ins.set_xlim(t0, t1)
    ins.set_ylim(0.998, 1.002)
    ins.set_xticks([t_star])
    ins.set_xticklabels(["t*"], fontsize=6.5)
    ins.set_yticks([0.998, 1.0, 1.002])
    ins.set_yticklabels(["0.998", "1", "1.002"], fontsize=6.5)
    ins.tick_params(length=0, labelcolor=TEXT, pad=1)
    ins.set_facecolor("white")
    for sp in ins.spines.values():
        sp.set_visible(True)
        sp.set_color("lightgrey")
        sp.set_linewidth(0.8)


def plot_fed(out, hists, devcs, rates, t_star, t_sim):
    """Figure 3: FED(t) per case against the hand line and FDS's device."""
    fig, axes = plt.subplots(2, 2, figsize=(8.0, 6.0), dpi=150, sharey=True)
    for ax, case in zip(axes.flat, CASES):
        h, d = hists[case], devcs[case]
        rate_s = rates[case]["total"] / 60.0
        t_end = float(h["time_s"].max())
        t = np.linspace(0.0, t_end, 101)
        ax.plot(t, rate_s * t, color=HAND, lw=2.4, ls="--", zorder=3)
        ax.plot(h["time_s"], h["fed_cumulative"], color=SIM, lw=1.0, zorder=4)
        step = max(1, len(d) // 14)
        ax.plot(
            d["Time"].iloc[::step],
            d["FED_occupant"].iloc[::step],
            ls="none",
            marker="o",
            ms=5,
            mfc="white",
            mec=FDS,
            mew=1.1,
            zorder=5,
        )
        ax.axhline(1.0, color="lightgrey", lw=0.8, zorder=1)
        ax.axvline(t_star[case], color=TEXT, lw=0.8, ls=":", zorder=1)
        ax.plot(t_sim[case], 1.0, marker="x", color="black", ms=8, mew=1.6, zorder=6)
        ax.text(
            t_star[case] - 0.03 * t_end,
            1.08,
            f"t* = {t_star[case]:.1f} s\nstop at {t_sim[case]:.0f} s",
            ha="right",
            va="bottom",
            fontsize=8,
            color=TEXT,
        )
        gas = PRESCRIBED[case]
        ax.set_title(
            f"{case}: CO₂ {gas['co2']:g} %, CO {gas['co']:g} %, O₂ {gas['o2']:g} %",
            fontsize=9.5,
            color=TEXT,
        )
        resid = np.abs(h["fed_cumulative"] - rate_s * h["time_s"]).max()
        ax.text(
            0.03,
            0.95,
            f"|FED − hand| ≤ {max(resid, 1e-16):.0e}",
            transform=ax.transAxes,
            va="top",
            fontsize=8,
            color=TEXT,
        )
        ax.set_xlim(0.0, t_end)
        ax.set_ylim(0.0, 1.45)
        style_axes(ax)
        draw_zoom(ax, h, d, rate_s, t_star[case], t_sim[case])
    for ax in axes[1]:
        ax.set_xlabel("time [s]", color=TEXT)
    for ax in axes[:, 0]:
        ax.set_ylabel("FED [-]", color=TEXT)
    handles = [
        Line2D([0], [0], color=SIM, lw=1.0, label="pyFDS-Evac occupant"),
        Line2D([0], [0], color=HAND, lw=2.4, ls="--", label="hand calculation"),
        Line2D(
            [0],
            [0],
            ls="none",
            marker="o",
            mfc="white",
            mec=FDS,
            mew=1.1,
            label="FDS FED device",
        ),
        Line2D(
            [0],
            [0],
            ls="none",
            marker="x",
            color="black",
            mew=1.6,
            label="incapacitated",
        ),
        Line2D(
            [0], [0], color="lightgrey", lw=1.0, label="inset (t* ± 2 s): FED update"
        ),
    ]
    fig.legend(
        handles=handles,
        loc="lower center",
        bbox_to_anchor=(0.5, -0.04),
        ncol=3,
        fontsize=8,
        **LEGEND,
    )
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    fig.savefig(out / "iso_test19_fed.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def plot_crossing(out, t_star, t_sim, t_fds, dt):
    """Figure 4: simulated and FDS crossing times minus the hand calculation."""
    fig, ax = plt.subplots(figsize=(7.0, 3.4), dpi=150)
    ys = np.arange(len(CASES))[::-1]
    ax.axvspan(0.0, dt, color=SIM, alpha=0.12, lw=0, zorder=0)
    ax.axvline(0.0, color=HAND, lw=1.4, ls="--", zorder=1)
    for y, case in zip(ys, CASES):
        ds = t_sim[case] - t_star[case]
        df = t_fds[case] - t_star[case]
        ax.plot([df, ds], [y, y], color="lightgrey", lw=1.0, zorder=2)
        ax.plot(ds, y, "o", ms=8, color=SIM, zorder=4)
        ax.plot(df, y, "o", ms=8, mfc="white", mec=FDS, mew=1.3, zorder=4)
        ax.text(
            max(ds, dt) + 0.05,
            y,
            f"+{ds:.2f} s",
            va="center",
            fontsize=8.5,
            color=TEXT,
        )
        ax.text(
            df - 0.05,
            y,
            f"{df:+.2f} s",
            ha="right",
            va="center",
            fontsize=8,
            color=FDS,
        )
    ax.text(
        dt / 2,
        ys[0] + 0.45,
        f"pyFDS-Evac pass band [0, Δt = {dt:g} s)",
        ha="center",
        va="center",
        fontsize=8.5,
        color=TEXT,
    )
    ax.set_yticks(ys)
    ax.set_yticklabels([f"{c}: t* = {t_star[c]:.1f} s" for c in CASES])
    ax.set_ylim(-1.5, len(CASES) - 0.2)
    ax.set_xlim(-0.6, 1.8)
    ax.set_xlabel("crossing time − hand calculation t* [s]", color=TEXT)
    ax.text(
        0.99,
        0.03,
        "Each stop is the first FED update after t*.\n"
        "FDS is judged by criterion 4: its early 0.1 s\n"
        "is its larger CO coefficient.",
        transform=ax.transAxes,
        ha="right",
        va="bottom",
        fontsize=8.5,
        color=TEXT,
    )
    handles = [
        Line2D([0], [0], ls="none", marker="o", color=SIM, label="pyFDS-Evac stop"),
        Line2D(
            [0],
            [0],
            ls="none",
            marker="o",
            mfc="white",
            mec=FDS,
            mew=1.3,
            label="FDS FED device",
        ),
        Line2D([0], [0], color=HAND, ls="--", label="hand calculation"),
    ]
    ax.legend(
        handles=handles,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.22),
        ncol=3,
        fontsize=8,
        **LEGEND,
    )
    style_axes(ax)
    fig.savefig(out / "iso_test19_crossing.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def render_gif(out, hists, t_sim, step_s, fps):
    """Figure 5: the four cases side by side, occupant coloured by FED."""
    t_max = max(float(h["time_s"].max()) for h in hists.values())
    frames = np.arange(0.0, t_max + 1e-9, step_s)
    cmap = sns.color_palette("YlOrRd", as_cmap=True)
    fed_max = 1.2
    fig, axes = plt.subplots(2, 2, figsize=(6.6, 6.4), dpi=100)
    fig.subplots_adjust(
        left=0.01, right=0.87, bottom=0.005, top=0.885, wspace=0.04, hspace=0.09
    )
    artists = {}
    for ax, case in zip(axes.flat, CASES):
        draw_room(ax, None, labels=False)
        ax.set_xlim(-0.2, 10.2)
        ax.set_ylim(-0.2, 10.2)
        gas = PRESCRIBED[case]
        ax.set_title(
            f"{case}: CO₂ {gas['co2']:g} %, CO {gas['co']:g} %, O₂ {gas['o2']:g} %",
            fontsize=9,
            color=TEXT,
            pad=3,
        )
        dot = ax.scatter(
            [], [], c=[], cmap=cmap, vmin=0.0, vmax=fed_max, s=260, ec=WALL
        )
        cross = ax.scatter([], [], marker="x", color="black", s=180, lw=2.2, zorder=6)
        ax.add_patch(Rectangle((1.0, 1.0), 8.0, 0.7, fc="white", ec="lightgrey"))
        bar = Rectangle((1.0, 1.0), 0.0, 0.7, ec="none")
        ax.add_patch(bar)
        ax.text(4.3, 2.0, "FED", ha="center", fontsize=8, color=TEXT)
        for v in (0.0, 1.0):
            xv = 1.0 + 8.0 * v / fed_max
            ax.plot([xv] * 2, [0.8, 1.9], color="black", lw=1.0)
            ax.text(xv, 2.0, f"{v:g}", ha="center", fontsize=8, color=TEXT)
        label = ax.text(
            5.0, 7.4, "", ha="center", va="bottom", fontsize=9.5, color=TEXT
        )
        ax.set_xticks([])
        ax.set_yticks([])
        style_axes(ax, frame=False)
        artists[case] = (dot, cross, bar, label)
    cax = fig.add_axes((0.89, 0.12, 0.025, 0.66))
    cb = fig.colorbar(
        plt.cm.ScalarMappable(norm=plt.Normalize(0.0, fed_max), cmap=cmap), cax=cax
    )
    cb.set_ticks([0.0, 0.5, 1.0])
    cb.set_label("FED [-]", color=TEXT, fontsize=9)
    cb.ax.tick_params(length=0, labelcolor=TEXT, labelsize=8)
    cb.outline.set_edgecolor("lightgrey")
    clock = fig.text(0.44, 0.955, "", ha="center", fontsize=12, color=TEXT)
    count = fig.text(0.44, 0.925, "", ha="center", fontsize=9.5, color=TEXT)

    writer = PillowWriter(fps=fps)
    with writer.saving(fig, out / "iso_test19.gif", dpi=100):
        for tf in frames:
            down = 0
            for case in CASES:
                h = hists[case]
                i = min(np.searchsorted(h["time_s"].to_numpy(), tf), len(h) - 1)
                row = h.iloc[i]
                fed = float(row["fed_cumulative"])
                stopped = bool(row["incapacitated"])
                down += stopped
                dot, cross, bar, label = artists[case]
                dot.set_offsets([[row["x"], row["y"]]])
                dot.set_array(np.array([fed]))
                cross.set_offsets(
                    [[row["x"], row["y"]]] if stopped else np.empty((0, 2))
                )
                bar.set_width(8.0 * min(fed, fed_max) / fed_max)
                bar.set_facecolor(cmap(min(fed, fed_max) / fed_max))
                state = f"stopped at {t_sim[case]:.0f} s" if stopped else "standing"
                label.set_text(f"FED = {fed:.2f}\n{state}")
            clock.set_text(f"t = {tf:.0f} s")
            count.set_text(f"incapacitated: {down} / 4 occupants (× = FED ≥ 1)")
            writer.grab_frame()
        for _ in range(fps * 2):
            writer.grab_frame()
    plt.close(fig)
    return len(frames)


def main():
    """Compute the hand calculation, compare it with the runs, draw the figures.

    Parameters
    ----------
    --data : path
        Directory with ``fds/{a,b,c,d}/`` and ``evac/{a,b,c,d}/``.

    Saves
    -----
    site/static/images/verification/iso_test19_setup.png
        Plan of the ISO room.
    site/static/images/verification/iso_test19_terms.png
        Expected FED rate per case, by term.
    site/static/images/verification/iso_test19_fed.png
        FED against time per case, with the hand line and FDS's device.
    site/static/images/verification/iso_test19_crossing.png
        Crossing time minus the hand calculation, with the pass band.
    site/static/images/verification/iso_test19.gif
        The four cases side by side.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--data",
        type=Path,
        required=True,
        help="directory with fds/{a,b,c,d}/ and evac/{a,b,c,d}/",
    )
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    # --- Style Setup ---
    sns.set_theme(font_scale=1.0, style="whitegrid", font="DejaVu Sans")

    # --- Data and checks ---
    rates, t_star, t_sim, t_inc, t_fds, hists, devcs = {}, {}, {}, {}, {}, {}, {}
    z_slice, dts = set(), set()
    print(
        "case  CO[ppm]    CO2[%]    O2[%]  max|dX/X|  r_hand[/min]  "
        "|r_sim/r_hand-1|  max|FED-hand|  t*[s]  t_FDS[s]  t_sim[s]  moved"
    )
    for case in CASES:
        gas = read_gas(args.data / "fds" / case)
        z_slice.update(gas["z"])
        spec = PRESCRIBED[case]
        rel = []
        for key, value in (("co_ppm", spec["co"] * 1e4), ("co2", spec["co2"])):
            rel.append(abs(gas[key] - value) / value if value else abs(gas[key]))
        rel.append(abs(gas["o2"] - spec["o2"]) / spec["o2"])
        rates[case] = hand_rates(gas)
        rate_s = rates[case]["total"] / 60.0
        t_star[case] = 1.0 / rate_s

        devc = pd.read_csv(
            args.data / "fds" / case / f"iso_table22_{case}_devc.csv", header=1
        )
        devcs[case] = devc
        t_fds[case] = fds_crossing(devc)

        h = load_history(args.data / "evac" / case / "fed_history.csv")
        hists[case] = h
        dts.update(np.round(np.diff(h["time_s"]), 6))
        t_sim[case] = first_true(h, "crossed")
        t_inc[case] = first_true(h, "incapacitated")
        r_sim = float(h["fed_rate_per_min"].iloc[0])
        resid = float(np.abs(h["fed_cumulative"] - rate_s * h["time_s"]).max())
        moved = float(np.hypot(h["x"] - h["x"].iloc[0], h["y"] - h["y"].iloc[0]).max())
        print(
            f"{case:4s} {gas['co_ppm']:9.3f} {gas['co2']:8.5f} {gas['o2']:8.5f} "
            f"{max(rel):9.1e}  {rates[case]['total']:.6e}  "
            f"{abs(r_sim / rates[case]['total'] - 1):15.1e}  {resid:12.1e}  "
            f"{t_star[case]:6.2f}  {t_fds[case]:8.2f}  {t_sim[case]:8.2f}  {moved:.1e}"
        )
        # FDS's CO coefficient is larger by FDS_CO_COEF / 2.764e-5; that alone
        # shortens its crossing by this fraction of t*.
        co_share = rates[case]["r_co"] * rates[case]["hv"] / rates[case]["total"]
        fds_shift = 1.0 - 1.0 / (1.0 + (FDS_CO_COEF / 2.764e-5 - 1.0) * co_share)
        print(
            f"     spread over slice cells and times {gas['spread']:.1e}; "
            f"HV {rates[case]['hv']:.5f}; stop at {t_inc[case]:.2f} s; "
            f"FDS early by {(t_star[case] - t_fds[case]) / t_star[case]:.2e} "
            f"of t* (coefficient alone: {fds_shift:.2e}, remainder "
            f"{(t_star[case] * (1 - fds_shift) - t_fds[case]) / t_star[case]:.1e})"
        )
        remainder = (t_star[case] * (1 - fds_shift) - t_fds[case]) / t_star[case]
        # Criterion 1: the FDS slice equals the deck, and the occupant sees it.
        assert max(rel) <= CONC_TOL, f"{case}: slice differs from the deck"
        check_occupant_gas(case, h, gas)
        # Criterion 2: FED is the hand rate times time, to round-off.
        assert resid <= FED_TOL, f"{case}: FED off the hand line by {resid:.1e}"
        # Criterion 4: FDS agrees once its CO coefficient is accounted for.
        assert abs(remainder) <= FDS_TOL, f"{case}: FDS off by {remainder:.1e} t*"
        # Criterion 5: the occupant stays put and does not evacuate.
        assert moved == 0.0, f"{case}: occupant moved {moved:.2e} m"
        o2_gate_shift(case, gas, t_star[case])
    dt = max(dts)
    print(f"slice heights {sorted(z_slice)} m; FED history spacing {sorted(dts)} s")
    for case in CASES:
        # Criterion 3: the stop is the first update at or after t*.
        ok = t_star[case] <= t_sim[case] < t_star[case] + dt
        same = t_inc[case] == t_sim[case]
        print(f"{case}: t* <= t_sim < t* + {dt:g}: {ok}; stop == crossing: {same}")
        assert ok and same, f"{case}: crossing or stop outside [t*, t* + dt)"
    print("all pass criteria hold")

    # --- Plot ---
    pos = (float(hists["a"]["x"].iloc[0]), float(hists["a"]["y"].iloc[0]))
    plot_setup(OUT, pos, min(z_slice))
    plot_terms(OUT, rates, t_star)
    plot_fed(OUT, hists, devcs, rates, t_star, t_sim)
    plot_crossing(OUT, t_star, t_sim, t_fds, dt)
    frames = render_gif(OUT, hists, t_sim, step_s=10.0, fps=12)
    size = (OUT / "iso_test19.gif").stat().st_size / 1e6
    print(f"iso_test19.gif: {frames} frames, {size:.2f} MB")


if __name__ == "__main__":
    main()
