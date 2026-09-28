# /// script
# requires-python = ">=3.11"
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
"""Figures for the verification test "Heat dose in a uniform room".

Three sealed 30 x 30 m rooms are started by FDS at 100, 150 and 200 C
(assets ``fed_incap_heat_<T>c``). 100 agents walk a loop of four corner
checkpoints and never leave. The expected heat dose is a hand calculation
that uses no pyFDS-Evac code: the script reads the TEMPERATURE slice at
z = 1.5 m with fdsreader, looks up the value at each agent's recorded
position (nearest slice node, nearest slice time) and sums SFPE Eq. 63.44

    FED_HEAT = sum [ T^3.4 / 5e7 ] * dt      (T in C, dt in min)

over the agent's own update times. FDS does not hold the prescribed
temperature exactly (it settles about 1 % lower within the first minute), so
the closed form at the nominal temperature, 60 * 5e7 / T^3.4 s, is shown for
reference only.

Checks: the temperature each agent recorded equals the slice value; its
heat FED equals the hand sum; in the deterministic run it stops at the first
update where the hand sum reaches 1; in the probabilistic run (150 C only)
the fraction stopped follows Phi(ln FED(t) / 0.94) within the KS 95 % band.

Run from the repository root::

    uv run python scripts/verification/heat_room_figures.py --data DIR

``DIR`` holds ``fed_incap_heat_<T>c/`` for T in 100, 150, 200, each with
``fds/`` (FDS output) and ``evac/deterministic/`` (``fed_history.csv``);
``fed_incap_heat_150c`` also has ``evac/probabilistic/``. A missing
temperature is skipped. Writes ``heat_room_*.png`` and ``heat_room.gif`` to
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
TEMPS = (100, 150, 200)
Z = 1.5
SIGMA = 0.94

AGENT = "#969696"  # pyFDS-Evac agents: thin grey solid lines
HAND = "#4575b4"  # hand calculation from the slice: blue dashed line
NOMINAL = "#fc8d59"  # closed form at the deck temperature: orange dotted
SIM = "#d73027"  # simulated stop: red crosses
TEMP_COLOURS = {100: "#fdbf6f", 150: "#fc8d59", 200: "#d73027"}
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


def t_nominal(temp_c):
    """Seconds to FED = 1 at a constant temperature, SFPE Eq. 63.44."""
    return 60.0 * 5e7 / temp_c**3.4


def phi(x):
    """Standard normal CDF, element-wise."""
    return 0.5 * (1.0 + np.vectorize(math.erf)(np.asarray(x) / math.sqrt(2.0)))


def temperature_slice(fds_dir):
    """Return (times, xs, ys, T[t, x, y], seam gap) of the TEMPERATURE slice at Z.

    The seam gap is the largest difference between two meshes at a node they
    share, the only place where "the slice value at a point" is ambiguous.
    """
    sim = fdsreader.Simulation(str(fds_dir))
    for sl in sim.slices:
        if sl.quantity.name != "TEMPERATURE" or sl.orientation != 3:
            continue
        if abs(sl.extent.z_start - Z) > 1e-6:
            continue
        data = sl.to_global(masked=False, fill=np.nan)
        coords = sl.get_coordinates()
        return (
            np.asarray(sl.times, dtype=float),
            np.asarray(coords["x"], dtype=float),
            np.asarray(coords["y"], dtype=float),
            data,
            seam_gap(sl, np.asarray(coords["x"]), np.asarray(coords["y"])),
        )
    raise ValueError(f"no TEMPERATURE slice at z = {Z} m in {fds_dir}")


def seam_gap(sl, xs, ys):
    """Largest |difference| between meshes at shared slice nodes, all times."""
    lo = np.full((len(sl.times), xs.size, ys.size), np.inf)
    hi = np.full_like(lo, -np.inf)
    for sub in sl.subslices:
        e = sub.extent
        i0 = int(np.argmin(np.abs(xs - e.x_start)))
        j0 = int(np.argmin(np.abs(ys - e.y_start)))
        ni, nj = sub.data.shape[1:]
        view = (slice(None), slice(i0, i0 + ni), slice(j0, j0 + nj))
        lo[view] = np.minimum(lo[view], sub.data)
        hi[view] = np.maximum(hi[view], sub.data)
    return float(np.max(hi - lo))


def load_history(path):
    """Read a ``fed_history.csv`` and coerce the incapacitation flag to bool."""
    hist = pd.read_csv(path, low_memory=False)
    hist["incapacitated"] = hist["incapacitated"].astype(str).str.lower() == "true"
    return hist.sort_values(["agent_id", "time_s"]).reset_index(drop=True)


def hand_dose(hist, times, xs, ys, temp):
    """Add the slice temperature and hand-summed heat FED to each history row."""
    t = hist["time_s"].to_numpy()
    ti = np.abs(times[None, :] - t[:, None]).argmin(axis=1)
    ii = np.abs(xs[None, :] - hist["x"].to_numpy()[:, None]).argmin(axis=1)
    jj = np.abs(ys[None, :] - hist["y"].to_numpy()[:, None]).argmin(axis=1)
    hist["t_slice"] = temp[ti, ii, jj]
    dt_min = hist.groupby("agent_id")["time_s"].diff().fillna(0.0) / 60.0
    hist["fed_hand"] = (
        (hist["t_slice"] ** 3.4 / 5e7 * dt_min).groupby(hist["agent_id"]).cumsum()
    )
    rec = hist["temperature_celsius"] ** 3.4 / 5e7 * dt_min
    hist["fed_from_recorded_t"] = rec.groupby(hist["agent_id"]).cumsum()
    return hist


def first_time(hist, mask):
    """First ``time_s`` per agent at which ``mask`` holds (NaN if never)."""
    ids = np.sort(hist["agent_id"].unique())
    hit = hist[mask].groupby("agent_id")["time_s"].min()
    return hit.reindex(ids).to_numpy(dtype=float)


def room_mean_dose(times, temp, t_end):
    """Hand FED from the room-mean slice temperature, on 1 s steps to t_end."""
    mean = np.nanmean(temp, axis=(1, 2))
    grid = np.arange(0.0, t_end + 1e-9, 1.0)
    t_at = mean[np.abs(times[None, :] - grid[:, None]).argmin(axis=1)]
    rate = t_at**3.4 / 5e7 / 60.0
    fed = np.concatenate([[0.0], np.cumsum(rate[1:] * np.diff(grid))])
    return grid, fed


def ks_distance(t_inc, n, t_end, model_at):
    """Sup |F_n - F| on [0, t_end], F_n counting over all n agents."""
    hit = np.sort(t_inc[np.isfinite(t_inc)])
    model = model_at(hit)
    above = np.arange(1, hit.size + 1) / n - model
    below = model - np.arange(0, hit.size) / n
    tail = float(model_at(np.array([t_end]))[0]) - hit.size / n
    return float(max(above.max(initial=0), below.max(initial=0), abs(tail)))


def style_axes(ax, frame=True):
    """Apply the house tick, grid and frame conventions to one axes."""
    ax.tick_params(axis="both", which="both", length=0, labelcolor="dimgrey")
    ax.grid(False)
    sns.despine(ax=ax, left=True, bottom=True)
    if frame:
        ax.patch.set_edgecolor("lightgrey")
        ax.patch.set_linewidth(0.8)


def _bbox(stage):
    """Lower-left and upper-right corners of a polygon stage in config.json."""
    pts = np.asarray(stage["coordinates"], dtype=float)
    return pts.min(axis=0), pts.max(axis=0)


def draw_plan(ax, room, cfg, show_labels):
    """Draw walls, spawn area, checkpoint loop and exit on a plan view."""
    xs, ys = room.exterior.xy
    ax.plot(xs, ys, color=WALL, lw=1.6, zorder=3)
    (x0, y0), (x1, y1) = _bbox(cfg["distributions"]["jps-distributions_0"])
    ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fc=SPAWN, ec="none", alpha=0.25))
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


def plot_setup(out, room, cfg, case):
    """Plan view of the room over the 150 C slice at 1.5 m, late in the run."""
    times, xs, ys, temp = case["times"], case["xs"], case["ys"], case["temp"]
    k = int(np.argmin(np.abs(times - 500.0)))
    field = temp[k]
    fig, ax = plt.subplots(figsize=(6.4, 5.6), dpi=150)
    mesh = ax.pcolormesh(
        xs,
        ys,
        field.T,
        cmap="Oranges",
        vmin=np.nanmin(field) - 0.3,
        vmax=np.nanmax(field) + 0.3,
        shading="nearest",
        alpha=0.55,
        zorder=0,
        rasterized=True,
    )
    draw_plan(ax, room, cfg, show_labels=True)
    late = temp[times > 60.0]
    ax.text(
        15.0,
        15.0,
        f"TEMPERATURE slice at z = {Z:g} m, t = {times[k]:.0f} s\n"
        f"deck: 150 °C; FDS after 60 s: {np.nanmin(late):.1f}–"
        f"{np.nanmax(late):.1f} °C",
        ha="center",
        va="center",
        fontsize=8.5,
        color=TEXT,
        bbox=dict(fc="white", ec="none", alpha=0.85, pad=3),
        zorder=5,
    )
    cbar = fig.colorbar(mesh, ax=ax, fraction=0.04, pad=0.03)
    cbar.set_label("gas temperature [°C]", color=TEXT)
    cbar.ax.tick_params(length=0, labelcolor="dimgrey")
    cbar.outline.set_visible(False)
    handles = [
        Line2D([0], [0], color=WALL, lw=1.6, label="wall"),
        Patch(fc=SPAWN, alpha=0.25, label="spawn area (100 agents)"),
        Patch(fc="none", ec=CHECKPOINT, hatch="////", label="checkpoint loop"),
        Patch(fc=EXIT, ec=EXIT, label="exit (not used)"),
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
    fig.savefig(out / "heat_room_setup.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def plot_temperature(out, cases):
    """Room temperature at 1.5 m against time: mean, spread, deck value."""
    fig, ax = plt.subplots(figsize=(7.0, 4.2), dpi=150)
    for temp_c, case in cases.items():
        times, temp = case["times"], case["temp"]
        rel_mean = np.nanmean(temp, axis=(1, 2)) / temp_c * 100.0
        rel_lo = np.nanmin(temp, axis=(1, 2)) / temp_c * 100.0
        rel_hi = np.nanmax(temp, axis=(1, 2)) / temp_c * 100.0
        colour = TEMP_COLOURS[temp_c]
        ax.fill_between(times, rel_lo, rel_hi, color=colour, alpha=0.25, lw=0)
        ax.plot(times, rel_mean, color=colour, lw=1.4, label=f"{temp_c} °C deck")
        ax.text(
            1005,
            rel_mean[-1],
            f"{temp_c} °C: {rel_mean[-1] * temp_c / 100:.1f} °C",
            fontsize=8,
            color=TEXT,
            va="center",
        )
    ax.axhline(100.0, color="lightgrey", lw=0.8, ls="--", zorder=1)
    ax.text(
        210,
        100.03,
        "prescribed by &INIT",
        ha="left",
        va="bottom",
        fontsize=8,
        color=TEXT,
    )
    ax.text(
        210,
        99.85,
        "FDS settles about 1 % below it within a minute, then holds.\n"
        "Band: spread over the 61 × 61 slice nodes. The hand\n"
        "calculation uses these slice values, not the deck value.",
        fontsize=8.5,
        color=TEXT,
        va="top",
    )
    ax.set_xlim(0.0, 1000.0)
    ax.set_xlabel("time [s]", color=TEXT)
    ax.set_ylabel("T / T_deck at 1.5 m [%]", color=TEXT)
    ax.legend(loc="lower left", fontsize=8, **LEGEND)
    style_axes(ax)
    fig.savefig(out / "heat_room_temperature.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def plot_fed(out, case, temp_c):
    """Agents' heat FED against the hand calculation, deterministic run."""
    det = case["det"]
    t_det = case["t_det"]
    t_max = float(np.nanmax(t_det)) * 1.4
    view = det[det["time_s"] <= t_max]
    fig, (ax, axr) = plt.subplots(
        2,
        1,
        figsize=(7.0, 5.6),
        dpi=150,
        sharex=True,
        gridspec_kw=dict(height_ratios=[3.0, 1.3], hspace=0.08),
    )
    segs, resid = [], []
    for _, g in view.groupby("agent_id"):
        t = g["time_s"].to_numpy()
        segs.append(np.column_stack([t, g["heat_fed_cumulative"].to_numpy()]))
        resid.append(
            np.column_stack([t, (g["heat_fed_cumulative"] - g["fed_hand"]).to_numpy()])
        )
    ax.add_collection(LineCollection(segs, colors=AGENT, lw=0.6, alpha=0.5))
    grid, fed_mean = room_mean_dose(case["times"], case["temp"], t_max)
    ax.plot(grid, fed_mean, color=HAND, lw=1.8, ls="--", zorder=4)
    t_nom = t_nominal(temp_c)
    ax.plot(grid, grid / t_nom, color=NOMINAL, lw=1.2, ls=":", zorder=3)
    ax.axhline(1.0, color="lightgrey", lw=0.8, zorder=1)
    t_stop = float(np.nanmedian(t_det))
    ax.axvline(t_stop, color=SIM, lw=1.0, ls="-.", zorder=2)
    ax.text(
        t_stop + 2,
        0.08,
        f"all {t_det.size} agents stop\nat t = {t_stop:.0f} s",
        fontsize=8.5,
        color=TEXT,
    )
    ax.text(
        t_nom - 2,
        1.04,
        f"{t_nom:.1f} s at a steady {temp_c} °C",
        ha="right",
        fontsize=8,
        color=TEXT,
    )
    handles = [
        Line2D([0], [0], color=AGENT, lw=1.0, label="100 agents (deterministic run)"),
        Line2D(
            [0], [0], color=HAND, lw=1.8, ls="--", label="hand sum, room-mean slice T"
        ),
        Line2D(
            [0], [0], color=NOMINAL, lw=1.2, ls=":", label=f"closed form at {temp_c} °C"
        ),
        Line2D([0], [0], color=SIM, lw=1.0, ls="-.", label="deterministic stop"),
    ]
    ax.legend(handles=handles, loc="upper left", fontsize=8, **LEGEND)
    ax.set_xlim(0.0, t_max)
    ax.set_ylim(0.0, float(view["heat_fed_cumulative"].max()) * 1.08)
    ax.set_ylabel("heat FED [-]", color=TEXT)

    axr.add_collection(LineCollection(resid, colors=AGENT, lw=0.6, alpha=0.6))
    axr.axhline(0.0, color="lightgrey", lw=0.8, zorder=1)
    res = float(case["dose_resid"])
    lim = max(res, 1e-12) * 1.6
    axr.set_ylim(-lim, lim)
    axr.text(
        0.02,
        0.08,
        f"per agent, against the hand sum at its own position: "
        f"|FED − hand| ≤ {res:.1e}",
        transform=axr.transAxes,
        fontsize=8,
        color=TEXT,
    )
    axr.ticklabel_format(axis="y", style="sci", scilimits=(-2, 2))
    axr.yaxis.get_offset_text().set_color(TEXT)
    axr.yaxis.get_offset_text().set_fontsize(8)
    axr.set_ylabel("FED − hand", color=TEXT)
    axr.set_xlabel("time [s]", color=TEXT)
    for a in (ax, axr):
        style_axes(a)
    fig.savefig(out / "heat_room_fed.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def plot_scaling(out, cases):
    """Time to FED = 1 against temperature: closed form, hand sum, simulation."""
    fig, ax = plt.subplots(figsize=(6.4, 4.4), dpi=150)
    temps = np.linspace(90.0, 215.0, 100)
    ax.plot(
        temps,
        t_nominal(temps),
        color=NOMINAL,
        lw=1.2,
        ls=":",
        label="closed form 60·5e7 / T^3.4 at the deck T",
    )
    for temp_c, case in cases.items():
        t_eff = case["t_eff"]
        ax.plot(
            temp_c,
            t_nominal(temp_c),
            ls="none",
            marker="D",
            ms=5,
            color=NOMINAL,
        )
        ax.plot(
            t_eff,
            case["t_hand_cross"],
            ls="none",
            marker="o",
            ms=9,
            mfc="white",
            mec=HAND,
            mew=1.4,
        )
        ax.plot(
            t_eff,
            float(np.nanmedian(case["t_det"])),
            ls="none",
            marker="x",
            ms=7,
            color=SIM,
            mew=1.6,
        )
        ax.annotate(
            f"{temp_c} °C deck: stop at {np.nanmedian(case['t_det']):.0f} s\n"
            f"(closed form {t_nominal(temp_c):.1f} s)",
            (t_eff, case["t_hand_cross"]),
            xytext=(12, 6),
            textcoords="offset points",
            fontsize=8,
            color=TEXT,
        )
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xticks([100, 125, 150, 175, 200])
    ax.set_xticklabels(["100", "125", "150", "175", "200"])
    ax.set_yticks([30, 60, 120, 240, 480])
    ax.set_yticklabels(["30", "60", "120", "240", "480"])
    ax.minorticks_off()
    ax.set_xlim(90.0, 270.0)
    ax.set_xlabel(
        "temperature [°C] (log): deck ◆, T^3.4-mean of the slice ○", color=TEXT
    )
    ax.set_ylabel("time to heat FED = 1 [s] (log)", color=TEXT)
    handles = [
        Line2D(
            [0],
            [0],
            color=NOMINAL,
            lw=1.2,
            ls=":",
            marker="D",
            ms=5,
            label="60·5e7 / T^3.4 (◆ at the deck T)",
        ),
        Line2D(
            [0],
            [0],
            ls="none",
            marker="o",
            mfc="white",
            mec=HAND,
            mew=1.4,
            label="hand sum from the slice",
        ),
        Line2D(
            [0],
            [0],
            ls="none",
            marker="x",
            color=SIM,
            mew=1.6,
            label="pyFDS-Evac, all 100 agents",
        ),
    ]
    ax.legend(handles=handles, loc="lower left", fontsize=8, **LEGEND)
    style_axes(ax)
    fig.savefig(out / "heat_room_scaling.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def plot_incapacitation(out, case):
    """Empirical CDF of heat incapacitation times against the log-normal."""
    t_inc, n, t_end = case["t_prob"], case["n"], case["t_end"]
    grid, fed = case["grid"], case["fed_mean"]
    band = 1.36 / math.sqrt(n)
    fig, ax = plt.subplots(figsize=(7.0, 4.4), dpi=150)
    t_show = min(t_end, 1000.0)
    keep = (grid > 0) & (grid <= t_show)
    model = phi(np.log(fed[keep]) / SIGMA)
    ax.fill_between(
        grid[keep],
        np.clip(model - band, 0, 1),
        np.clip(model + band, 0, 1),
        color=HAND,
        alpha=0.15,
        lw=0,
    )
    ax.plot(grid[keep], model, color=HAND, lw=1.8, ls="--", zorder=3)
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
    t_det = float(np.nanmedian(case["t_det"]))
    ax.axvline(t_det, color=SIM, lw=1.2, ls="-.", zorder=2)
    ax.text(
        t_det * 0.95,
        0.80,
        f"deterministic run:\nall {n} agents at {t_det:.0f} s",
        ha="right",
        va="top",
        fontsize=8.5,
        color=TEXT,
    )
    ax.text(
        0.02,
        0.97,
        f"KS distance D = {case['d_ks']:.3f} < {band:.3f} = 1.36/√{n}\n"
        f"{k} of {n} stopped by {t_end:.0f} s",
        transform=ax.transAxes,
        va="top",
        fontsize=8.5,
        color=TEXT,
    )
    handles = [
        Line2D([0], [0], color="#1f253f", lw=1.4, label="probabilistic run (n = 100)"),
        Line2D(
            [0],
            [0],
            color=HAND,
            lw=1.8,
            ls="--",
            label=f"Φ(ln FED_hand(t) / {SIGMA})",
        ),
        Patch(fc=HAND, alpha=0.15, label="KS 95 % band"),
        Line2D([0], [0], color=SIM, lw=1.2, ls="-.", label="deterministic"),
    ]
    ax.legend(handles=handles, loc="lower right", fontsize=8, **LEGEND)
    ax.set_xscale("log")
    ax.set_xlim(10.0, t_show)
    ax.set_ylim(0.0, 1.0)
    ax.set_xlabel("time [s] (log)", color=TEXT)
    ax.set_ylabel("fraction incapacitated [-]", color=TEXT)
    style_axes(ax)
    fig.savefig(out / "heat_room_incapacitation.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def render_gif(out, hist, room, cfg, n, t_last, step_s, fps, hold):
    """Plan-view animation of the deterministic run, coloured by heat FED."""
    times = np.sort(hist["time_s"].unique())
    picks = times[np.searchsorted(times, np.arange(0.0, t_last + 1e-9, step_s))]
    by_time = dict(tuple(hist[hist["time_s"].isin(picks)].groupby("time_s")))

    fig, ax = plt.subplots(figsize=(6.6, 5.6), dpi=100)
    draw_plan(ax, room, cfg, show_labels=False)
    cmap = sns.color_palette("YlOrRd", as_cmap=True)
    walk = ax.scatter(
        [], [], c=[], cmap=cmap, vmin=0.0, vmax=1.0, s=26, ec="dimgrey", lw=0.4
    )
    down = ax.scatter([], [], marker="x", color="black", s=30, lw=1.4, zorder=6)
    cbar = fig.colorbar(walk, ax=ax, fraction=0.04, pad=0.03)
    cbar.set_label("heat FED [-]", color=TEXT)
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
                label="incapacitated (heat)",
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
    with writer.saving(fig, out / "heat_room.gif", dpi=100):
        for tp in list(picks) + [picks[-1]] * hold:
            g = by_time[tp]
            up = g[~g["incapacitated"]]
            dn = g[g["incapacitated"]]
            walk.set_offsets(up[["x", "y"]].to_numpy().reshape(-1, 2))
            walk.set_array(up["heat_fed_cumulative"].to_numpy())
            down.set_offsets(dn[["x", "y"]].to_numpy().reshape(-1, 2))
            clock.set_text(f"t = {tp:.0f} s   (150 °C room)")
            count.set_text(f"incapacitated: {len(dn)} / {n}")
            writer.grab_frame()
    plt.close(fig)
    return len(picks) + hold


def analyse(case_dir, temp_c):
    """Read one temperature's FDS slice and runs; return the numbers to check."""
    times, xs, ys, temp, gap = temperature_slice(case_dir / "fds")
    case = dict(times=times, xs=xs, ys=ys, temp=temp, seam_gap=gap)
    det = hand_dose(
        load_history(case_dir / "evac" / "deterministic" / "fed_history.csv"),
        times,
        xs,
        ys,
        temp,
    )
    heat_cause = det["incapacitation_cause"].astype(str) == "heat"
    case["det"] = det
    case["t_det"] = first_time(det, det["incapacitated"])
    case["t_hand"] = first_time(det, det["fed_hand"] >= 1.0)
    case["t_hand_cross"] = float(np.nanmedian(case["t_hand"]))
    case["all_heat"] = bool(heat_cause[det["incapacitated"]].all())
    case["t_resid"] = float(np.abs(det["temperature_celsius"] - det["t_slice"]).max())
    case["dose_resid"] = float(
        np.abs(det["heat_fed_cumulative"] - det["fed_hand"]).max()
    )
    case["sum_resid"] = float(
        np.abs(det["heat_fed_cumulative"] - det["fed_from_recorded_t"]).max()
    )
    # FED(t) at the median stop, as a T^3.4-weighted mean temperature.
    before = det[det["time_s"] <= case["t_hand_cross"]]
    case["t_eff"] = float((before["t_slice"] ** 3.4).mean() ** (1 / 3.4))
    late = temp[times > 60.0]
    case["t_late"] = (float(np.nanmin(late)), float(np.nanmax(late)))
    dt = np.diff(np.sort(det["time_s"].unique()))
    case["dt"] = (float(dt.min()), float(dt.max()))
    case["n"] = int(det["agent_id"].nunique())
    case["t_end"] = float(det["time_s"].max())

    prob_path = case_dir / "evac" / "probabilistic" / "fed_history.csv"
    if prob_path.exists():
        prob = load_history(prob_path)
        case["t_prob"] = first_time(prob, prob["incapacitated"])
        grid, fed_mean = room_mean_dose(times, temp, case["t_end"])
        case["grid"], case["fed_mean"] = grid, fed_mean

        def model_at(t):
            fed_t = np.interp(t, grid, fed_mean)
            return phi(np.log(np.maximum(fed_t, 1e-300)) / SIGMA)

        case["d_ks"] = ks_distance(case["t_prob"], case["n"], case["t_end"], model_at)
        case["f_end"] = float(model_at(np.array([case["t_end"]]))[0])
    return case


def report(temp_c, case):
    """Print the numbers quoted on the verification page."""
    lo, hi = case["t_late"]
    t_det = case["t_det"]
    print(f"--- {temp_c} C ---")
    print(f"slice T after 60 s: {lo:.2f}-{hi:.2f} C; seam gap {case['seam_gap']:.2e} K")
    print(f"FED update spacing {case['dt'][0]:.3f}-{case['dt'][1]:.3f} s")
    print(f"closed form at {temp_c} C: {t_nominal(temp_c):.2f} s")
    print(
        f"hand sum reaches 1 at {np.nanmin(case['t_hand']):.0f}-"
        f"{np.nanmax(case['t_hand']):.0f} s; T_eff = {case['t_eff']:.2f} C"
    )
    print(
        f"deterministic: {np.isfinite(t_det).sum()}/{t_det.size} stopped at "
        f"{np.nanmin(t_det):.0f}-{np.nanmax(t_det):.0f} s; "
        f"max |t_stop - t_hand| = {np.nanmax(np.abs(t_det - case['t_hand'])):.1f} s; "
        f"cause all heat: {case['all_heat']}"
    )
    print(
        f"1. max |T_agent - T_slice| = {case['t_resid']:.2e} K "
        f"<= seam gap {case['seam_gap']:.2e}: {case['t_resid'] <= case['seam_gap']}"
    )
    print(
        f"2. max |FED - hand(recorded T)| = {case['sum_resid']:.2e} <= 1e-9: "
        f"{case['sum_resid'] <= 1e-9}; end to end, "
        f"max |FED - hand(slice)| = {case['dose_resid']:.2e}"
    )
    print(
        f"3. deterministic stop at the hand crossing: "
        f"{bool(np.all(t_det == case['t_hand'])) and case['all_heat']}"
    )
    if "t_prob" in case:
        k = np.isfinite(case["t_prob"]).sum()
        print(
            f"probabilistic: {k}/{case['n']} stopped by {case['t_end']:.0f} s "
            f"(model {case['f_end']:.3f}); KS D = {case['d_ks']:.4f}, "
            f"band {1.36 / math.sqrt(case['n']):.4f}"
        )


def main():
    """Compute the hand calculation, compare it with the runs, draw the figures.

    Parameters
    ----------
    --data : path
        Directory holding ``fed_incap_heat_<T>c/`` for T in 100, 150, 200.

    Saves
    -----
    site/static/images/verification/heat_room_setup.png
        Plan view over the 150 C TEMPERATURE slice at 1.5 m.
    site/static/images/verification/heat_room_temperature.png
        Slice temperature against time for the three decks.
    site/static/images/verification/heat_room_fed.png
        Heat FED against time at 150 C, with residuals.
    site/static/images/verification/heat_room_scaling.png
        Time to FED = 1 against temperature.
    site/static/images/verification/heat_room_incapacitation.png
        Probabilistic stop times against the log-normal, 150 C.
    site/static/images/verification/heat_room.gif
        Animation of the deterministic 150 C run.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--data",
        type=Path,
        required=True,
        help="directory with fed_incap_heat_<T>c/{fds,evac}/",
    )
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    # --- Style Setup ---
    sns.set_theme(font_scale=1.0, style="whitegrid", font="DejaVu Sans")

    # --- Data ---
    cases = {}
    for temp_c in TEMPS:
        case_dir = args.data / f"fed_incap_heat_{temp_c}c"
        if not (case_dir / "evac" / "deterministic" / "fed_history.csv").exists():
            print(f"skip {temp_c} C: no {case_dir}/evac/deterministic")
            continue
        cases[temp_c] = analyse(case_dir, temp_c)
        report(temp_c, cases[temp_c])
    main_case = cases[150]

    # --- Plot ---
    scenario = ROOT / "assets" / "fed_incap_heat_150c"
    room = wkt.loads((scenario / "geometry.wkt").read_text())
    cfg = json.loads((scenario / "config.json").read_text())
    plot_setup(OUT, room, cfg, main_case)
    plot_temperature(OUT, cases)
    plot_fed(OUT, main_case, 150)
    plot_scaling(OUT, cases)
    if "t_prob" in main_case:
        plot_incapacitation(OUT, main_case)
    frames = render_gif(
        OUT,
        main_case["det"],
        room,
        cfg,
        main_case["n"],
        t_last=float(np.nanmax(main_case["t_det"])) + 25.0,
        step_s=1.0,
        fps=10,
        hold=15,
    )
    size = (OUT / "heat_room.gif").stat().st_size / 1e6
    print(f"heat_room.gif: {frames} frames, {size:.2f} MB")


if __name__ == "__main__":
    main()
