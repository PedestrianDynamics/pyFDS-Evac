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

over the agent's own update times. Eq. 63.44 is ISO 13571:2012 Eq. (10),
the law of ``--heat-clothing unclothed``, with which the runs are made; the
default law, ISO Eq. (9), is not checked here. The decks set TMPA to the prescribed
temperature, so FDS holds the room at the deck value and the closed form
60 * 5e7 / T^3.4 s at that value is the expected time to FED = 1.

Checks: the temperature each agent recorded equals the slice value; its
heat FED equals the hand sum of its recorded temperature to round-off and the
hand sum on the slice within the bound the mesh seams allow; in the
deterministic run it stops at the first update where the hand sum reaches 1; in the probabilistic runs (150 C only),
pooled over all seeds, the fraction stopped follows Phi(ln FED(t) / 0.94)
within the KS 95 % band of the pooled agent count.

Run from the repository root::

    uv run python scripts/verification/heat_room_figures.py --data DIR

``DIR`` holds ``fed_incap_heat_<T>c/`` for T in 100, 150, 200, each with
``fds/`` (FDS output) and ``evac/deterministic/`` (``fed_history.csv``);
``fed_incap_heat_150c`` also has ``evac/probabilistic_seeds/<seed>/``. A missing
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
SPAWN = "#762a83"  # purple, outside the temperature and FED colour maps
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
    """Return (times, xs, ys, T[t, x, y], seam gap, shared) of the slice at Z.

    The seam gap is the largest difference between two meshes at a node they
    share, the only place where "the slice value at a point" is ambiguous.
    ``shared[i, j]`` is True at such nodes.
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
            *seam_gap(sl, np.asarray(coords["x"]), np.asarray(coords["y"])),
        )
    raise ValueError(f"no TEMPERATURE slice at z = {Z} m in {fds_dir}")


def seam_gap(sl, xs, ys):
    """Largest |difference| between meshes at shared nodes, and the node mask."""
    lo = np.full((len(sl.times), xs.size, ys.size), np.inf)
    hi = np.full_like(lo, -np.inf)
    count = np.zeros((xs.size, ys.size), dtype=int)
    for sub in sl.subslices:
        e = sub.extent
        i0 = int(np.argmin(np.abs(xs - e.x_start)))
        j0 = int(np.argmin(np.abs(ys - e.y_start)))
        ni, nj = sub.data.shape[1:]
        view = (slice(None), slice(i0, i0 + ni), slice(j0, j0 + nj))
        lo[view] = np.minimum(lo[view], sub.data)
        hi[view] = np.maximum(hi[view], sub.data)
        count[view[1:]] += 1
    return float(np.max(hi - lo)), count > 1


def load_history(path):
    """Read a ``fed_history.csv`` and coerce the incapacitation flag to bool."""
    hist = pd.read_csv(path, low_memory=False)
    hist["incapacitated"] = hist["incapacitated"].astype(str).str.lower() == "true"
    return hist.sort_values(["agent_id", "time_s"]).reset_index(drop=True)


def hand_dose(hist, times, xs, ys, temp, shared, gap):
    """Add the slice temperature and hand-summed heat FED to each history row.

    ``seam_bound`` is the largest FED difference the mesh seams allow: at a
    shared node the agent may read the other mesh, up to ``gap`` K away, and
    d(rate)/rate = 3.4 dT/T, so each such update adds at most
    3.4 * gap / T * rate * dt.
    """
    t = hist["time_s"].to_numpy()
    ti = np.abs(times[None, :] - t[:, None]).argmin(axis=1)
    ii = np.abs(xs[None, :] - hist["x"].to_numpy()[:, None]).argmin(axis=1)
    jj = np.abs(ys[None, :] - hist["y"].to_numpy()[:, None]).argmin(axis=1)
    hist["t_slice"] = temp[ti, ii, jj]
    dt_min = hist.groupby("agent_id")["time_s"].diff().fillna(0.0) / 60.0
    hist["fed_hand"] = (
        (hist["t_slice"] ** 3.4 / 5e7 * dt_min).groupby(hist["agent_id"]).cumsum()
    )
    step = hist["t_slice"] ** 3.4 / 5e7 * dt_min
    at_seam = shared[ii, jj]
    hist["at_seam"] = at_seam
    hist["seam_bound"] = (
        (3.4 * gap / hist["t_slice"] * step * at_seam)
        .groupby(hist["agent_id"])
        .cumsum()
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


def ks_p_value(d, n):
    """Asymptotic Kolmogorov p-value of distance d for n samples."""
    lam = d * math.sqrt(n)
    return float(
        2.0
        * sum(
            (-1) ** (k - 1) * math.exp(-2.0 * k * k * lam * lam) for k in range(1, 101)
        )
    )


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
    ax.add_patch(
        Rectangle(
            (x0, y0), x1 - x0, y1 - y0, fc="none", ec=SPAWN, lw=1.2, ls="--", zorder=2
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
        Patch(fc="none", ec=SPAWN, ls="--", label="spawn area (100 agents)"),
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
    """Room temperature at 1.5 m against time: deviation from the deck value."""
    fig, ax = plt.subplots(figsize=(7.0, 4.2), dpi=150)
    worst = 0.0
    for temp_c, case in cases.items():
        times, temp = case["times"], case["temp"]
        dev = (temp - temp_c) * 1e3
        lo, hi = np.nanmin(dev, axis=(1, 2)), np.nanmax(dev, axis=(1, 2))
        worst = max(worst, float(np.nanmax(np.abs(dev))))
        colour = TEMP_COLOURS[temp_c]
        ax.fill_between(times, lo, hi, color=colour, alpha=0.25, lw=0)
        ax.plot(
            times,
            np.nanmean(dev, axis=(1, 2)),
            color=colour,
            lw=1.4,
            label=f"{temp_c} °C deck",
        )
    ax.axhline(0.0, color="lightgrey", lw=0.8, ls="--", zorder=1)
    ax.text(
        0.98,
        0.95,
        f"max |T − T_deck| over all 61 × 61 slice nodes: {worst:.2f} mK\n"
        "line: room mean; band: spread over the slice nodes",
        transform=ax.transAxes,
        ha="right",
        va="top",
        fontsize=8.5,
        color=TEXT,
    )
    ax.set_xlim(0.0, 1000.0)
    ax.set_ylim(-1.6 * worst, 1.6 * worst)
    ax.set_xlabel("time [s]", color=TEXT)
    ax.set_ylabel("T − T_deck at 1.5 m [mK]", color=TEXT)
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
    ax.plot(t_nom, 1.0, ls="none", marker="D", ms=5, color=NOMINAL, zorder=5)
    ax.annotate(
        f"{t_nom:.1f} s at a steady {temp_c} °C",
        (t_nom, 1.0),
        xytext=(-10, -90),
        textcoords="offset points",
        ha="right",
        fontsize=8,
        color=TEXT,
        arrowprops=dict(arrowstyle="-", color="lightgrey", lw=0.8),
    )
    ax.text(
        t_stop + 2,
        0.62,
        f"gap to the closed form: {t_stop - t_nom:+.1f} s\n"
        "the dose is checked every 1 s",
        fontsize=8,
        color=TEXT,
        va="top",
    )
    handles = [
        Line2D([0], [0], color=AGENT, lw=1.0, label="100 agents (deterministic run)"),
        Line2D(
            [0],
            [0],
            color=HAND,
            lw=1.8,
            ls="--",
            label="hand sum at the room-mean slice T\n(per-agent sums: lower panel)",
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

    scale = 10.0 ** math.floor(math.log10(max(float(case["dose_resid"]), 1e-300)))
    resid = [np.column_stack([r[:, 0], r[:, 1] / scale]) for r in resid]
    axr.add_collection(LineCollection(resid, colors=AGENT, lw=0.6, alpha=0.6))
    axr.axhline(0.0, color="lightgrey", lw=0.8, zorder=1)
    res = float(case["dose_resid"])
    lim = max(res, 1e-12) / scale * 1.6
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
    exp = int(round(math.log10(scale)))
    axr.set_ylabel(f"FED − hand\n[×$10^{{{exp}}}$]", color=TEXT)
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
    )
    for temp_c, case in cases.items():
        t_eff = case["t_eff"]
        ax.plot(
            temp_c,
            t_nominal(temp_c),
            ls="none",
            marker="D",
            ms=4,
            color=NOMINAL,
            zorder=5,
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
    ax.set_xlabel("temperature T [°C] (log)", color=TEXT)
    ax.set_ylabel("time to heat FED = 1 [s] (log)", color=TEXT)
    handles = [
        Line2D(
            [0],
            [0],
            color=NOMINAL,
            lw=1.2,
            ls=":",
            marker="D",
            ms=4,
            label=r"closed form $t^* = 60\cdot 5\times10^{7}/T^{3.4}$, ◆ at the deck T",
        ),
        Line2D(
            [0],
            [0],
            ls="none",
            marker="o",
            mfc="white",
            mec=HAND,
            mew=1.4,
            label=r"hand sum from the slice, at its $T^{3.4}$-mean",
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
    t_inc, t_end = case["t_prob"], case["t_end"]
    n = t_inc.size
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
    for run in case["t_runs"]:
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
    t_det = float(np.nanmedian(case["t_det"]))
    ax.axvline(t_det, color=SIM, lw=1.2, ls="-.", zorder=2)
    ax.text(
        t_det * 0.95,
        0.80,
        f"deterministic run:\nall {case['n']} agents at {t_det:.0f} s",
        ha="right",
        va="top",
        fontsize=8.5,
        color=TEXT,
    )
    ax.text(
        0.02,
        0.97,
        f"pooled KS distance D = {case['d_ks']:.3f} "
        f"{'≤' if case['d_ks'] <= band else '>'} {band:.3f} = 1.36/√{n}"
        f",\np = {case['p_ks']:.2f}; {k} of {n} stopped by {t_end:.0f} s; "
        f"{len(case['t_runs'])} seeds pooled",
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
            label=f"probabilistic, {len(case['t_runs'])} seeds pooled (n = {n})",
        ),
        Line2D([0], [0], color=AGENT, lw=0.6, label="one seed each"),
        Line2D(
            [0],
            [0],
            color=HAND,
            lw=1.8,
            ls="--",
            label=f"Φ(ln FED_hand(t) / {SIGMA})",
        ),
        Patch(fc=HAND, alpha=0.15, label=f"KS 95 % band, n = {n}"),
        Line2D([0], [0], color=SIM, lw=1.2, ls="-.", label="deterministic"),
    ]
    ax.legend(handles=handles, loc="lower right", fontsize=8, **LEGEND)
    ax.set_xscale("log")
    ax.set_xlim(1.0, t_show)
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
    caption = ax.text(
        15.0,
        15.0,
        "",
        ha="center",
        va="center",
        fontsize=10,
        color=TEXT,
        bbox=dict(fc="white", ec="lightgrey", alpha=0.9, pad=5),
        zorder=7,
    )
    caption.set_visible(False)
    t_all = float(hist.loc[hist["incapacitated"], "time_s"].min())
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
        for idx, tp in enumerate(list(picks) + [picks[-1]] * hold):
            g = by_time[tp]
            up = g[~g["incapacitated"]]
            dn = g[g["incapacitated"]]
            walk.set_offsets(up[["x", "y"]].to_numpy().reshape(-1, 2))
            walk.set_array(up["heat_fed_cumulative"].to_numpy())
            down.set_offsets(dn[["x", "y"]].to_numpy().reshape(-1, 2))
            clock.set_text(f"t = {tp:.0f} s   (150 °C room)")
            count.set_text(f"incapacitated: {len(dn)} / {n}")
            if idx >= len(picks):
                caption.set_text(f"all {n} stopped\nat {t_all:.0f} s: heat FED ≥ 1")
                caption.set_visible(True)
            writer.grab_frame()
    plt.close(fig)
    return len(picks) + hold


def analyse(case_dir, temp_c):
    """Read one temperature's FDS slice and runs; return the numbers to check."""
    times, xs, ys, temp, gap, shared = temperature_slice(case_dir / "fds")
    case = dict(times=times, xs=xs, ys=ys, temp=temp, seam_gap=gap)
    det = hand_dose(
        load_history(case_dir / "evac" / "deterministic" / "fed_history.csv"),
        times,
        xs,
        ys,
        temp,
        shared,
        gap,
    )
    heat_cause = det["incapacitation_cause"].astype(str) == "heat"
    case["det"] = det
    case["t_det"] = first_time(det, det["incapacitated"])
    case["t_hand"] = first_time(det, det["fed_hand"] >= 1.0)
    case["t_hand_cross"] = float(np.nanmedian(case["t_hand"]))
    case["all_heat"] = bool(heat_cause[det["incapacitated"]].all())
    dtemp = np.abs(det["temperature_celsius"] - det["t_slice"])
    case["t_resid"] = float(dtemp.max())
    case["t_resid_off_seam"] = float(dtemp[~det["at_seam"]].max())
    case["t_resid_seam"] = float(dtemp[det["at_seam"]].to_numpy().max(initial=0.0))
    case["dose_resid"] = float(
        np.abs(det["heat_fed_cumulative"] - det["fed_hand"]).max()
    )
    case["sum_resid"] = float(
        np.abs(det["heat_fed_cumulative"] - det["fed_from_recorded_t"]).max()
    )
    # Two recursive sums of n positive terms each round by <= n * eps * FED.
    n_upd = det.groupby("agent_id").size().max()
    case["roundoff"] = float(
        2 * n_upd * np.finfo(float).eps * det["heat_fed_cumulative"].max()
    )
    excess = np.abs(det["heat_fed_cumulative"] - det["fed_hand"]) - (
        det["seam_bound"] + case["roundoff"]
    )
    case["dose_ok"] = bool((excess <= 0).all())
    case["seam_bound_max"] = float(det["seam_bound"].max())
    # Margins around the stop: the hand FED one update before and at the stop
    # must be further from 1 than the seam bound, or the stop could move.
    t_h = pd.Series(case["t_hand"], index=np.sort(det["agent_id"].unique()))
    stop_t = det["agent_id"].map(t_h)
    before_stop = det[det["time_s"] == stop_t - 1.0]
    at_stop = det[det["time_s"] == stop_t]
    case["margin_below"] = float(1.0 - before_stop["fed_hand"].max())
    case["margin_above"] = float(at_stop["fed_hand"].min() - 1.0)
    case["seam_at_stop"] = float(at_stop["seam_bound"].max())
    case["seam_rows_to_stop"] = int(
        det[det["time_s"] <= stop_t].groupby("agent_id")["at_seam"].sum().max()
    )
    # FED(t) at the median stop, as a T^3.4-weighted mean temperature.
    before = det[det["time_s"] <= case["t_hand_cross"]]
    case["t_eff"] = float((before["t_slice"] ** 3.4).mean() ** (1 / 3.4))
    case["t_star_eff"] = t_nominal(case["t_eff"])
    case["drop_pct"] = float((1.0 - np.nanmean(temp[times > 60.0]) / temp_c) * 100)
    # Last slice time at which the room mean still falls by more than 0.01 K.
    mean = np.nanmean(temp, axis=(1, 2))
    falling = np.diff(mean) < -0.01
    case["t_fall_end"] = float(times[1:][falling].max()) if falling.any() else 0.0
    late = temp[times > 60.0]
    case["t_late"] = (float(np.nanmin(late)), float(np.nanmax(late)))
    dt = np.diff(np.sort(det["time_s"].unique()))
    case["dt"] = (float(dt.min()), float(dt.max()))
    case["n"] = int(det["agent_id"].nunique())
    case["t_end"] = float(det["time_s"].max())

    seeds_dir = case_dir / "evac" / "probabilistic_seeds"
    if seeds_dir.exists():
        runs = {}
        for d in sorted(seeds_dir.iterdir(), key=lambda d: int(d.name)):
            prob = load_history(d / "fed_history.csv")
            runs[int(d.name)] = first_time(prob, prob["incapacitated"])
        case["t_runs"] = list(runs.values())
        case["t_prob"] = np.concatenate(case["t_runs"])
        grid, fed_mean = room_mean_dose(times, temp, case["t_end"])
        case["grid"], case["fed_mean"] = grid, fed_mean

        def model_at(t):
            fed_t = np.interp(t, grid, fed_mean)
            return phi(np.log(np.maximum(fed_t, 1e-300)) / SIGMA)

        n_pool = case["t_prob"].size
        case["d_ks"] = ks_distance(case["t_prob"], n_pool, case["t_end"], model_at)
        case["p_ks"] = ks_p_value(case["d_ks"], n_pool)
        case["d_seed"] = {
            s: ks_distance(t, t.size, case["t_end"], model_at) for s, t in runs.items()
        }
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
        f"room mean after 60 s is {case['drop_pct']:.2f} % below the deck; "
        f"T_eff = {case['t_eff']:.2f} C, closed form at T_eff "
        f"{case['t_star_eff']:.2f} s"
    )
    print(
        f"hand sum first >= 1 at update {np.nanmin(case['t_hand']):.0f}-"
        f"{np.nanmax(case['t_hand']):.0f} s; margins: 1 - FED_hand before = "
        f"{case['margin_below']:.2e}, FED_hand at stop - 1 = "
        f"{case['margin_above']:.2e}"
    )
    print(
        f"deterministic: {np.isfinite(t_det).sum()}/{t_det.size} stopped at "
        f"{np.nanmin(t_det):.0f}-{np.nanmax(t_det):.0f} s; "
        f"max |t_stop - t_hand| = {np.nanmax(np.abs(t_det - case['t_hand'])):.1f} s; "
        f"cause all heat: {case['all_heat']}"
    )
    print(
        f"room mean falls by > 0.01 K per slice step until {case['t_fall_end']:.0f} s"
    )
    print(
        f"1. max |T_agent - T_slice| off shared nodes = "
        f"{case['t_resid_off_seam']:.2e} K <= 1e-10: "
        f"{case['t_resid_off_seam'] <= 1e-10}; at shared nodes "
        f"{case['t_resid_seam']:.2e} K <= seam gap {case['seam_gap']:.2e}: "
        f"{case['t_resid_seam'] <= case['seam_gap']}"
    )
    print(
        f"2. max |FED - hand(recorded T)| = {case['sum_resid']:.2e} <= "
        f"round-off {case['roundoff']:.2e}: "
        f"{case['sum_resid'] <= case['roundoff']}; end to end, "
        f"max |FED - hand(slice)| = {case['dose_resid']:.2e} within the seam "
        f"bound (max {case['seam_bound_max']:.2e}) per row: {case['dose_ok']}"
    )
    print(
        f"3. seam bound up to the stop <= "
        f"{case['seam_at_stop']:.2e} (max {case['seam_rows_to_stop']} seam "
        f"updates per agent); stop fixed: "
        f"{case['seam_at_stop'] < min(case['margin_below'], case['margin_above'])}; "
        f"deterministic stop at the hand crossing: "
        f"{bool(np.all(t_det == case['t_hand'])) and case['all_heat']}"
    )
    if "t_prob" in case:
        for (s, d), t in zip(case["d_seed"].items(), case["t_runs"]):
            print(
                f"seed {s}: {np.isfinite(t).sum()}/{t.size} stopped, KS D = {d:.4f} "
                f"(band {1.36 / math.sqrt(t.size):.4f}, p = {ks_p_value(d, t.size):.3f})"
            )
        ds = np.array(list(case["d_seed"].values()))
        b1 = 1.36 / math.sqrt(case["t_runs"][0].size)
        print(
            f"per-seed D: min {ds.min():.4f}, median {np.median(ds):.4f}, "
            f"max {ds.max():.4f}; {(ds > b1).sum()} of {ds.size} above {b1:.4f}"
        )
        n_pool = case["t_prob"].size
        k = np.isfinite(case["t_prob"]).sum()
        band = 1.36 / math.sqrt(n_pool)
        print(
            f"probabilistic, {len(ds)} seeds pooled: {k}/{n_pool} stopped by "
            f"{case['t_end']:.0f} s (model {case['f_end']:.3f}); "
            f"KS D = {case['d_ks']:.4f}, band {band:.4f}, p = {case['p_ks']:.3f}; "
            f"passes: {case['d_ks'] <= band}"
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
