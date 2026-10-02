# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "fdsreader",
#     "matplotlib",
#     "numpy",
#     "pandas",
#     "pillow",
#     "seaborn",
#     "shapely",
# ]
# ///
"""Figures for the verification test "CO dose in a uniform room" (2000 ppm).

A 30 x 30 m room is filled with 2000 ppm CO by FDS (CHID
``demo_homogeneous_CO_2000ppm``). 100 agents walk a loop of four corner
checkpoints and never leave, so each one breathes the same air for the whole
run. The expected dose is a hand calculation that uses no pyFDS-Evac code:

    r  = 2.764e-5 C^1.036            [1/min], C in ppm
    HV = exp(0.1903 C_CO2 + 2.0004) / 7.1,   C_CO2 in %
    FED(t) = r HV t / 60,   t* = 60 / (r HV)   [s]

with the O2 term zero above 20 % O2. C, C_CO2 and O2 are read from the FDS
slices at z = 1.5 m. The deterministic run stops every agent at FED >= 1, so
all incapacitation times must lie within one FED update of t*. The
probabilistic runs draw one threshold per agent from a log-normal with median
1 and sigma 0.94; since FED is linear in t, the fraction incapacitated by t
is Phi(ln(t / t*) / 0.94). The runs of all seeds are pooled, and the pooled
fraction is checked against the KS 95 % band 1.36 / sqrt(n), n the pooled
agent count; the distance of each seed alone is printed as a spread.

Run from the repository root::

    uv run python scripts/verification/co_room_figures.py --data DIR

``DIR`` holds ``fds/`` (FDS output), ``evac/deterministic/`` and
``evac/probabilistic_seeds/<seed>/`` (``fed_history.csv``); the animation
shows the lowest seed. Writes ``co_room_setup.png``, ``co_room_fed.png``,
``co_room_incapacitation.png`` and ``co_room.gif`` to
``site/static/images/verification/``.
"""

import argparse
import json
import math
from pathlib import Path

import fdsreader
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib.animation import PillowWriter
from matplotlib.collections import LineCollection
from matplotlib.lines import Line2D
from matplotlib.patches import FancyArrowPatch, Patch, Rectangle
from shapely import wkt

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "site" / "static" / "images" / "verification"
SCENARIO = ROOT / "assets" / "fed_incap_co_2000ppm"
CHID = "demo_homogeneous_CO_2000ppm"
SIGMA = 0.94

# One meaning, one colour, one style across the four figures.
AGENT = "#969696"  # pyFDS-Evac agents: thin grey solid lines
HAND = "#4575b4"  # hand calculation: blue dashed line
FDS = "#d73027"  # FDS FED device: red open circles
DETERMINISTIC = "#d73027"  # deterministic incapacitation: red dash-dot line
WALL = "dimgrey"
EXIT = "#33a02c"
CHECKPOINT = "#324465"
SPAWN = "#fc8d59"
TEXT = "dimgrey"
LEGEND = dict(
    frameon=True,
    facecolor="white",
    framealpha=0.8,
    edgecolor="lightgrey",
    labelcolor="dimgrey",
)


def slice_at(sim, quantity, z):
    """Return the whole (time, x, y) array of a horizontal slice at height z."""
    for sl in sim.slices:
        if sl.quantity.name != quantity or sl.orientation != 3:
            continue
        if abs(sl.extent.z_start - z) < 1e-6:
            return sl, sl.to_global(masked=False, fill=np.nan)
    raise ValueError(f"no {quantity} slice at z = {z} m")


def phi(x):
    """Standard normal CDF, element-wise."""
    return 0.5 * (1.0 + np.vectorize(math.erf)(np.asarray(x) / math.sqrt(2.0)))


def first_incapacitation(hist):
    """First ``time_s`` at which each agent is incapacitated (NaN if never)."""
    ids = np.sort(hist["agent_id"].unique())
    hit = hist[hist["incapacitated"]].groupby("agent_id")["time_s"].min()
    return hit.reindex(ids).to_numpy(dtype=float)


def load_history(path):
    """Read a ``fed_history.csv`` and coerce the incapacitation flag to bool."""
    hist = pd.read_csv(path)
    hist["incapacitated"] = hist["incapacitated"].astype(str).str.lower() == "true"
    return hist.sort_values(["agent_id", "time_s"]).reset_index(drop=True)


def style_axes(ax, frame=True):
    """Apply the house tick, grid and frame conventions to one axes."""
    ax.tick_params(axis="both", which="both", length=0, labelcolor="dimgrey")
    ax.grid(False)
    sns.despine(ax=ax, left=True, bottom=True)
    if frame:
        ax.patch.set_edgecolor("lightgrey")
        ax.patch.set_linewidth(0.8)


def draw_plan(ax, room, cfg, show_labels):
    """Draw walls, spawn area, checkpoint loop and exit on a plan view."""
    xs, ys = room.exterior.xy
    ax.plot(xs, ys, color=WALL, lw=1.6, zorder=3)
    (x0, y0), (x1, y1) = _bbox(cfg["distributions"]["jps-distributions_0"])
    ax.add_patch(
        Rectangle(
            (x0, y0),
            x1 - x0,
            y1 - y0,
            fc=SPAWN,
            ec="none",
            alpha=0.25,
            zorder=1,
        )
    )
    loop = []
    for name in ("cp_NE_1", "cp_NW_1", "cp_SW_1", "cp_SE_1"):
        (cx0, cy0), (cx1, cy1) = _bbox(cfg["checkpoints"][name])
        ax.add_patch(
            Rectangle(
                (cx0, cy0),
                cx1 - cx0,
                cy1 - cy0,
                fc="none",
                ec=CHECKPOINT,
                lw=1.0,
                hatch="////",
                alpha=0.8,
                zorder=2,
            )
        )
        loop.append(((cx0 + cx1) / 2, (cy0 + cy1) / 2, name[3:5]))
    for (xa, ya, _), (xb, yb, _) in zip(loop, loop[1:] + loop[:1]):
        ax.add_patch(
            FancyArrowPatch(
                (xa, ya),
                (xb, yb),
                arrowstyle="-|>",
                mutation_scale=12,
                color=CHECKPOINT,
                lw=0.9,
                shrinkA=18,
                shrinkB=18,
                zorder=3,
            )
        )
    (ex0, ey0), (ex1, ey1) = _bbox(cfg["exits"]["exit_A_left"])
    ax.add_patch(
        Rectangle((ex0, ey0), ex1 - ex0, ey1 - ey0, fc=EXIT, ec=EXIT, zorder=4)
    )
    if show_labels:
        for x, y, label in loop:
            dy = 2.9 if y > 15 else -2.9
            ax.text(x, y + dy, label, ha="center", va="center", fontsize=8, color=TEXT)
    ax.set_xlim(-1.0, 31.0)
    ax.set_ylim(-1.0, 31.0)
    ax.set_aspect("equal")


def _bbox(stage):
    """Lower-left and upper-right corners of a polygon stage in config.json."""
    pts = np.asarray(stage["coordinates"], dtype=float)
    return pts.min(axis=0), pts.max(axis=0)


def plot_setup(out, room, cfg, co_ppm, co_xy, co_min, co_max, n_times, z):
    """Figure 1: plan view of the room over the CO slice at 1.5 m."""
    fig, ax = plt.subplots(figsize=(6.4, 5.4), dpi=150)
    x, y = co_xy
    ax.pcolormesh(
        x,
        y,
        co_ppm.T,
        cmap="Greys",
        vmin=co_min - 5.0,
        vmax=co_max + 5.0,
        shading="nearest",
        alpha=0.35,
        zorder=0,
        rasterized=True,
    )
    draw_plan(ax, room, cfg, show_labels=True)
    ax.text(
        15.0,
        15.0,
        f"CO slice at z = {z:g} m (grey):\n{co_min:.2f} ppm in every cell"
        f"\nand all {n_times} slice times"
        f"\n(min = max = {co_max:.2f})",
        ha="center",
        va="center",
        fontsize=8.5,
        color=TEXT,
        bbox=dict(fc="white", ec="none", alpha=0.85, pad=3),
        zorder=5,
    )
    handles = [
        Line2D([0], [0], color=WALL, lw=1.6, label="wall"),
        Patch(fc=SPAWN, alpha=0.25, label="spawn area (100 agents)"),
        Patch(fc="none", ec=CHECKPOINT, hatch="////", label="checkpoint loop"),
        Patch(fc=EXIT, ec=EXIT, label="exit"),
    ]
    ax.legend(
        handles=handles,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.1),
        ncol=2,
        fontsize=8,
        **LEGEND,
    )
    ax.set_xlabel("x [m]", color=TEXT)
    ax.set_ylabel("y [m]", color=TEXT)
    style_axes(ax, frame=False)
    fig.savefig(out / "co_room_setup.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def plot_fed(out, det, devc, rate_s, t_star, t_cross_fds, resid_max):
    """Figure 2: agents' FED against the hand calculation and FDS's device."""
    fig, (ax, axr) = plt.subplots(
        2,
        1,
        figsize=(7.0, 5.6),
        dpi=150,
        sharex=True,
        gridspec_kw=dict(height_ratios=[3.0, 1.3], hspace=0.08),
    )
    t_end = float(det["time_s"].max())
    segs, resid = [], []
    for _, g in det.groupby("agent_id"):
        t = g["time_s"].to_numpy()
        fed = g["fed_cumulative"].to_numpy()
        segs.append(np.column_stack([t, fed]))
        resid.append(np.column_stack([t, fed - rate_s * t]))
    ax.add_collection(LineCollection(segs, colors=AGENT, lw=0.6, alpha=0.5))
    t = np.linspace(0.0, t_end, 201)
    ax.plot(t, rate_s * t, color=HAND, lw=1.8, ls="--", zorder=4)
    marks = np.unique([np.abs(devc["Time"] - m).idxmin() for m in range(0, 1001, 50)])
    ax.plot(
        devc["Time"].loc[marks],
        devc["FED_center"].loc[marks],
        ls="none",
        marker="o",
        ms=5,
        mfc="white",
        mec=FDS,
        mew=1.2,
        zorder=5,
    )
    ax.axhline(1.0, color="lightgrey", lw=0.8, zorder=1)
    for a in (ax, axr):
        a.axvline(t_star, color=TEXT, lw=0.8, ls=":", zorder=1)
    ax.text(
        t_star - 12,
        1.03,
        f"t* = {t_star:.1f} s",
        ha="right",
        fontsize=8.5,
        color=TEXT,
    )
    ax.text(
        0.02,
        0.97,
        f"Agents, FDS and the hand calculation agree:\n"
        f"FED = 1 at t* = {t_star:.1f} s (FDS device: {t_cross_fds:.1f} s);\n"
        f"max |FED_agent − FED_hand| = {resid_max:.1e}",
        transform=ax.transAxes,
        va="top",
        fontsize=8.5,
        color=TEXT,
    )
    handles = [
        Line2D([0], [0], color=AGENT, lw=1.0, label="100 agents (deterministic run)"),
        Line2D([0], [0], color=HAND, lw=1.8, ls="--", label="hand calculation"),
        Line2D(
            [0],
            [0],
            ls="none",
            marker="o",
            mfc="white",
            mec=FDS,
            mew=1.2,
            label="FDS device FED_center",
        ),
    ]
    ax.legend(
        handles=handles,
        loc="upper left",
        bbox_to_anchor=(0.0, 0.8),
        fontsize=8,
        **LEGEND,
    )
    ax.set_xlim(0.0, t_end)
    ax.set_ylim(0.0, rate_s * t_end * 1.05)
    ax.set_ylabel("FED [-]", color=TEXT)

    axr.add_collection(LineCollection(resid, colors=AGENT, lw=0.6, alpha=0.5))
    axr.plot(
        devc["Time"].loc[marks],
        devc["FED_center"].loc[marks] - rate_s * devc["Time"].loc[marks],
        ls="none",
        marker="o",
        ms=4,
        mfc="white",
        mec=FDS,
        mew=1.0,
    )
    axr.axhline(0.0, color="lightgrey", lw=0.8, zorder=1)
    fds_resid = devc["FED_center"].loc[marks] - rate_s * devc["Time"].loc[marks]
    lim = max(np.abs(fds_resid).max(), 1e-6) * 1.4
    axr.text(
        0.02,
        0.08,
        f"agents: |FED − hand| ≤ {resid_max:.1e} (on the zero line)",
        transform=axr.transAxes,
        fontsize=8,
        color=TEXT,
    )
    axr.set_ylim(-lim, lim)
    axr.ticklabel_format(axis="y", style="sci", scilimits=(-2, 2))
    axr.yaxis.get_offset_text().set_color(TEXT)
    axr.yaxis.get_offset_text().set_fontsize(8)
    axr.set_ylabel("FED − hand", color=TEXT)
    axr.set_xlabel("time [s]", color=TEXT)
    for a in (ax, axr):
        style_axes(a)
    fig.savefig(out / "co_room_fed.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def plot_incapacitation(out, t_runs, t_end, t_star, t_det, d_ks, band, p_ks):
    """Figure 3: pooled empirical CDF of incapacitation times against the log-normal."""
    t_inc = np.concatenate(t_runs)
    n = t_inc.size
    fig, ax = plt.subplots(figsize=(7.0, 4.4), dpi=150)
    t = np.linspace(1.0, t_end, 600)
    model = phi(np.log(t / t_star) / SIGMA)
    ax.fill_between(
        t,
        np.clip(model - band, 0, 1),
        np.clip(model + band, 0, 1),
        color=HAND,
        alpha=0.15,
        lw=0,
        zorder=1,
    )
    ax.plot(t, model, color=HAND, lw=1.8, ls="--", zorder=3)
    for run in t_runs:
        hit = np.sort(run[np.isfinite(run)])
        ax.step(
            np.concatenate([[0.0], hit, [t_end]]),
            np.concatenate([[0.0], np.arange(1, hit.size + 1), [hit.size]]) / run.size,
            where="post",
            color=AGENT,
            lw=0.6,
            alpha=0.6,
            zorder=2,
        )
    hit = np.sort(t_inc[np.isfinite(t_inc)])
    k = hit.size
    ax.step(
        np.concatenate([[0.0], hit, [t_end]]),
        np.concatenate([[0.0], np.arange(1, k + 1) / n, [k / n]]),
        where="post",
        color="#1f253f",
        lw=1.4,
        zorder=4,
    )
    ax.axvline(t_det, color=DETERMINISTIC, lw=1.2, ls="-.", zorder=2)
    ax.text(
        t_det - 10,
        0.72,
        f"deterministic run:\nall agents at {t_det:.0f} s",
        ha="right",
        va="top",
        fontsize=8.5,
        color=TEXT,
    )
    verdict = "inside the band" if d_ks <= band else "outside the band"
    sign = "≤" if d_ks <= band else ">"
    ax.text(
        0.02,
        0.97,
        f"pooled KS distance D = {d_ks:.3f} {sign} {band:.3f} = 1.36/√{n},\n"
        f"p = {p_ks:.2f}: {verdict};\n"
        f"{k} of {n} incapacitated by the end of the run ({t_end:.0f} s);\n"
        f"the rest are right-censored, as the model expects",
        transform=ax.transAxes,
        va="top",
        fontsize=8.5,
        color=TEXT,
    )
    handles = [
        Line2D(
            [0],
            [0],
            color="#1f253f",
            lw=1.4,
            label=f"probabilistic, {len(t_runs)} seeds pooled (n = {n})",
        ),
        Line2D([0], [0], color=AGENT, lw=0.6, label="one seed each"),
        Line2D(
            [0],
            [0],
            color=HAND,
            lw=1.8,
            ls="--",
            label=f"Φ(ln(t / t*) / {SIGMA}), t* = {t_star:.1f} s",
        ),
        Patch(fc=HAND, alpha=0.15, label=f"KS 95 % band, n = {n}"),
        Line2D([0], [0], color=DETERMINISTIC, lw=1.2, ls="-.", label="deterministic"),
    ]
    ax.legend(handles=handles, loc="lower right", fontsize=8, **LEGEND)
    ax.set_xlim(0.0, t_end)
    ax.set_ylim(0.0, 1.0)
    ax.set_xlabel("time [s]", color=TEXT)
    ax.set_ylabel("fraction incapacitated [-]", color=TEXT)
    style_axes(ax)
    fig.savefig(out / "co_room_incapacitation.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def render_gif(out, prob, room, cfg, n, step_s, fps):
    """Figure 4: plan-view animation of the probabilistic run, coloured by FED."""
    times = np.sort(prob["time_s"].unique())
    picks = times[np.searchsorted(times, np.arange(0.0, times[-1] + 1e-9, step_s))]
    by_time = dict(tuple(prob[prob["time_s"].isin(picks)].groupby("time_s")))

    fig, ax = plt.subplots(figsize=(6.6, 5.6), dpi=100)
    draw_plan(ax, room, cfg, show_labels=False)
    cmap = sns.color_palette("YlOrRd", as_cmap=True)
    walk = ax.scatter(
        [], [], c=[], cmap=cmap, vmin=0.0, vmax=1.3, s=26, ec="dimgrey", lw=0.4
    )
    down = ax.scatter([], [], marker="x", color="black", s=30, lw=1.4, zorder=6)
    cbar = fig.colorbar(walk, ax=ax, fraction=0.04, pad=0.03, extend="max")
    cbar.set_label("FED [-]", color=TEXT)
    cbar.ax.tick_params(length=0, labelcolor="dimgrey")
    cbar.outline.set_visible(False)
    clock = ax.text(0.5, 30.2, "", fontsize=10, color=TEXT, va="bottom")
    count = ax.text(30.0, 30.2, "", fontsize=10, color=TEXT, va="bottom", ha="right")
    ax.legend(
        handles=[
            Line2D(
                [0],
                [0],
                ls="none",
                marker="o",
                mfc="#fd8d3c",
                mec="dimgrey",
                label="walking",
            ),
            Line2D(
                [0],
                [0],
                ls="none",
                marker="x",
                color="black",
                mew=1.4,
                label="incapacitated",
            ),
        ],
        loc="upper center",
        bbox_to_anchor=(0.5, -0.06),
        ncol=2,
        fontsize=9,
        **LEGEND,
    )
    ax.set_xticks([])
    ax.set_yticks([])
    style_axes(ax, frame=False)
    fig.tight_layout()

    writer = PillowWriter(fps=fps)
    with writer.saving(fig, out / "co_room.gif", dpi=100):
        for tp in picks:
            g = by_time[tp]
            up = g[~g["incapacitated"]]
            dn = g[g["incapacitated"]]
            walk.set_offsets(up[["x", "y"]].to_numpy().reshape(-1, 2))
            walk.set_array(up["fed_cumulative"].to_numpy())
            down.set_offsets(dn[["x", "y"]].to_numpy().reshape(-1, 2))
            clock.set_text(f"t = {tp:.0f} s")
            count.set_text(f"incapacitated: {len(dn)} / {n}")
            writer.grab_frame()
    plt.close(fig)
    return len(picks)


def ks_p_value(d, n):
    """Asymptotic Kolmogorov p-value of distance d for n samples."""
    lam = d * math.sqrt(n)
    return float(
        2.0
        * sum(
            (-1) ** (k - 1) * math.exp(-2.0 * k * k * lam * lam) for k in range(1, 101)
        )
    )


def ks_distance(t_inc, n, t_end, t_star):
    """Sup |F_n - F| on [0, t_end], F_n counting over all n agents."""
    hit = np.sort(t_inc[np.isfinite(t_inc)])
    model = phi(np.log(hit / t_star) / SIGMA)
    above = np.arange(1, hit.size + 1) / n - model
    below = model - np.arange(0, hit.size) / n
    tail = phi(np.log(t_end / t_star) / SIGMA) - hit.size / n
    return float(max(above.max(initial=0), below.max(initial=0), abs(tail)))


def main():
    """Compute the hand calculation, compare it with both runs, draw the figures.

    Parameters
    ----------
    --data : path, optional
        Directory with ``fds/``, ``evac/deterministic/`` and
        ``evac/probabilistic_seeds/<seed>/``.

    Saves
    -----
    site/static/images/verification/co_room_setup.png
        150 dpi PNG, plan view over the CO slice at 1.5 m.
    site/static/images/verification/co_room_fed.png
        150 dpi PNG, FED against time with residuals.
    site/static/images/verification/co_room_incapacitation.png
        150 dpi PNG, pooled empirical CDF of incapacitation times with KS band.
    site/static/images/verification/co_room.gif
        Animation of the probabilistic run of the lowest seed.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--data",
        type=Path,
        required=True,
        help="directory with fds/, evac/deterministic/ and evac/probabilistic_seeds/",
    )
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    # --- Style Setup ---
    sns.set_theme(font_scale=1.0, style="whitegrid", font="DejaVu Sans")

    # --- Data: FDS ---
    z = 1.5
    sim = fdsreader.Simulation(str(args.data / "fds"))
    co_sl, co = slice_at(sim, "CARBON MONOXIDE VOLUME FRACTION", z)
    _, co2 = slice_at(sim, "CARBON DIOXIDE VOLUME FRACTION", z)
    _, o2 = slice_at(sim, "OXYGEN VOLUME FRACTION", z)
    c_ppm = float(np.nanmean(co)) * 1e6
    c_co2 = float(np.nanmean(co2)) * 100.0
    c_o2 = float(np.nanmean(o2)) * 100.0
    coords = co_sl.get_coordinates()
    devc = pd.read_csv(args.data / "fds" / f"{CHID}_devc.csv", header=1)

    # --- Hand calculation (no pyFDS-Evac code) ---
    rate = 2.764e-5 * c_ppm**1.036
    hv = math.exp(0.1903 * c_co2 + 2.0004) / 7.1
    o2_term = 0.0 if c_o2 > 20.0 else float("nan")
    rate_s = rate * hv / 60.0
    t_star = 1.0 / rate_s
    t_cross_fds = float(np.interp(1.0, devc["FED_center"], devc["Time"]))
    fds_resid = np.abs(devc["FED_center"] - rate_s * devc["Time"]).max()

    # --- Data: pyFDS-Evac runs ---
    det = load_history(args.data / "evac" / "deterministic" / "fed_history.csv")
    seed_dirs = sorted(
        (args.data / "evac" / "probabilistic_seeds").iterdir(),
        key=lambda d: int(d.name),
    )
    probs = {int(d.name): load_history(d / "fed_history.csv") for d in seed_dirs}
    prob = probs[min(probs)]
    dt = np.diff(np.sort(det["time_s"].unique()))
    t_det = first_incapacitation(det)
    t_runs = [first_incapacitation(h) for h in probs.values()]
    t_ends = {float(h["time_s"].max()) for h in probs.values()}
    t_end = min(t_ends)
    t_prob = np.concatenate(t_runs)
    t_prob[t_prob > t_end] = np.nan
    n = t_prob.size
    det_resid = np.abs(det["fed_cumulative"] - rate_s * det["time_s"])
    d_ks = ks_distance(t_prob, n, t_end, t_star)
    band = 1.36 / math.sqrt(n)
    p_ks = ks_p_value(d_ks, n)
    d_seed = {s: ks_distance(t, t.size, t_end, t_star) for s, t in zip(probs, t_runs)}

    print(
        f"CO    = {c_ppm:.4f} ppm (min {co.min() * 1e6:.4f}, max {co.max() * 1e6:.4f})"
    )
    print(f"CO2   = {c_co2:.6f} %, O2 = {c_o2:.4f} % (O2 term {o2_term:g})")
    print(f"HV    = {hv:.6f}")
    print(f"r     = {rate:.6e} 1/min, r*HV = {rate * hv:.6e} 1/min")
    print(f"t*    = {t_star:.2f} s")
    print(
        f"FDS FED_center = 1 at {t_cross_fds:.2f} s; max |FDS - hand| = {fds_resid:.2e}"
    )
    for label, hist in [("deterministic", det)] + [
        (f"probabilistic seed {s}", h) for s, h in probs.items()
    ]:
        dups = hist.duplicated(["time_s", "agent_id"]).sum()
        last = hist.groupby("agent_id")["time_s"].max()
        print(
            f"{label}: {hist['agent_id'].nunique()} agents, {len(hist)} rows, "
            f"{dups} duplicate rows, last row per agent {last.min():.2f}-"
            f"{last.max():.2f} s"
        )
    print(
        f"FED update spacing: {dt.min():.3f}-{dt.max():.3f} s (median {np.median(dt):.3f})"
    )
    print(
        f"deterministic incapacitation: {np.isfinite(t_det).sum()} / {t_det.size}, "
        f"t = {np.nanmin(t_det):.2f}-{np.nanmax(t_det):.2f} s, "
        f"t - t* = {np.nanmin(t_det) - t_star:+.2f} to {np.nanmax(t_det) - t_star:+.2f} s"
    )
    print(f"max |FED_agent - FED_hand| (deterministic) = {det_resid.max():.3e}")
    print(f"probabilistic run end times: {sorted(t_ends)} s")
    for s, t in zip(probs, t_runs):
        b = 1.36 / math.sqrt(t.size)
        print(
            f"seed {s}: {np.isfinite(t).sum()} / {t.size} incapacitated, "
            f"KS D = {d_seed[s]:.4f} (band {b:.4f}, p = {ks_p_value(d_seed[s], t.size):.3f})"
        )
    ds = np.array(list(d_seed.values()))
    b1 = 1.36 / math.sqrt(t_runs[0].size)
    print(
        f"per-seed D: min {ds.min():.4f}, median {np.median(ds):.4f}, "
        f"max {ds.max():.4f}; {(ds > b1).sum()} of {ds.size} above {b1:.4f}"
    )
    print(
        f"pooled ({len(t_runs)} seeds): {np.isfinite(t_prob).sum()} / {n} "
        f"incapacitated by {t_end:.0f} s "
        f"(model {phi(np.log(t_end / t_star) / SIGMA):.3f}); KS D = {d_ks:.4f}, "
        f"band {band:.4f}, p = {p_ks:.3f}; passes: {d_ks <= band}"
    )

    # --- Plot ---
    room = wkt.loads((SCENARIO / "geometry.wkt").read_text())
    cfg = json.loads((SCENARIO / "config.json").read_text())
    plot_setup(
        OUT,
        room,
        cfg,
        co[-1] * 1e6,
        (coords["x"], coords["y"]),
        float(co.min()) * 1e6,
        float(co.max()) * 1e6,
        co.shape[0],
        z,
    )
    plot_fed(OUT, det, devc, rate_s, t_star, t_cross_fds, float(det_resid.max()))
    plot_incapacitation(
        OUT, t_runs, t_end, t_star, float(np.nanmedian(t_det)), d_ks, band, p_ks
    )
    n_gif = prob["agent_id"].nunique()
    frames = render_gif(OUT, prob, room, cfg, n_gif, step_s=5.0, fps=12)
    size = (OUT / "co_room.gif").stat().st_size / 1e6
    print(f"co_room.gif: {frames} frames, {size:.2f} MB")


if __name__ == "__main__":
    main()
