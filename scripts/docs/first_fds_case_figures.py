"""Figures for the "A crowd in a fire" page: the T-junction with a 2 MW PVC fire.

The figures come from two runs of ``assets/t_junction`` (``config.json``,
discovery agents, seed 42), one in clear air and one against the FDS output of
``assets/t_junction/t_junction.fds``. Make the runs from the repository root,
with ``FDS`` the FDS output directory and ``RUNS`` any output directory::

    uv run python run.py --scenario assets/t_junction \\
        --output-sqlite RUNS/tj_clear.sqlite
    uv run python run.py --scenario assets/t_junction --fds-dir FDS \\
        --output-sqlite RUNS/tj_fire.sqlite \\
        --output-smoke-history RUNS/tj_fire_smoke.csv \\
        --output-fed-history RUNS/tj_fire_fed.csv \\
        --output-route-history RUNS/tj_fire_routes.csv

then::

    uv run python scripts/docs/first_fds_case_figures.py --data FDS --runs RUNS

Writes ``site/static/images/first-fds-case/*.png`` and ``agents_smoke.gif``. The
GIF needs ``ffmpeg`` on the PATH for its palette pass.
"""

import argparse
import importlib.util
import json
import shutil
import sqlite3
import subprocess
import tempfile
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib import animation, patheffects
from matplotlib.colors import LogNorm, Normalize
from matplotlib.lines import Line2D
from matplotlib.patches import FancyArrowPatch, Patch, Polygon, Rectangle
from shapely import wkt

from pyfds_evac import ExtinctionField

ROOT = Path(__file__).resolve().parents[2]
ASSET = ROOT / "assets" / "t_junction"
OUT = ROOT / "site" / "static" / "images" / "first-fds-case"

# Shared palette of the concept figures: one meaning, one colour, one style.
EXIT = "#33a02c"  # exit door
WALL = "dimgrey"
FLOOR = "#f7f7f7"
TEXT = "dimgrey"
FIRE = "#bd0c0c"
SIGN = "#c89b00"
EXIT_A = "#4575b4"  # left exit: blue, solid
EXIT_B = "#fc8d59"  # right exit: orange, dashed
INSIDE = "#969696"  # still inside at 300 s: grey, dotted
CLEAR = "#4575b4"
FIRE_RUN = "#d73027"
FPS = 10.0  # trajectory frames per second
T_END = 300.0
BURNER = (24.0, 10.5, 2.0, 1.0)  # x, y, width, depth of the FDS burner vent
HALO = [patheffects.withStroke(linewidth=2.5, foreground="white")]


def _animator():
    """The helpers of ``scripts/animate_agents_smoke.py``, loaded by path."""
    path = ROOT / "scripts" / "animate_agents_smoke.py"
    spec = importlib.util.spec_from_file_location("animate_agents_smoke", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _style(ax):
    ax.grid(False)
    ax.tick_params(axis="both", which="both", length=0, labelcolor=TEXT)
    sns.despine(ax=ax, left=True, bottom=True)


def _save(fig, name):
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / name, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"wrote {OUT / name}")


def _plan(ax, walkable, config, labels=True):
    """Walls, exits and burner of the T, drawn once for every plan view."""
    ax.add_patch(
        Polygon(np.asarray(walkable.exterior.coords), fc="none", ec=WALL, lw=1.4)
    )
    for name, spec in config["exits"].items():
        xy = np.asarray(spec["coordinates"])
        ax.add_patch(Polygon(xy, fc=EXIT, ec="none", alpha=0.85, zorder=3))
        if labels:
            x = xy[:, 0].mean()
            side = "A" if x < 15 else "B"
            ax.annotate(
                f"exit {side}",
                (x, 13.0),
                xytext=(0, 5),
                textcoords="offset points",
                ha="center",
                va="bottom",
                color=EXIT,
                fontweight="bold",
            )
    x, y, w, d = BURNER
    ax.add_patch(Rectangle((x, y), w, d, fc=FIRE, ec="none", zorder=3))
    ax.set_aspect("equal")
    ax.set_xlim(-0.5, 30.5)
    ax.set_ylim(-0.5, 13.5)


def _signs(config):
    out = []
    for group in ("exits", "checkpoints"):
        for name, spec in config.get(group, {}).items():
            if "sign" in spec:
                out.append((name, spec["sign"]))
    return out


def fig_scenario(walkable, config):
    sns.set_theme(font_scale=1.0, style="whitegrid", font="DejaVu Sans")
    fig, ax = plt.subplots(figsize=(8.5, 4.4))
    ax.add_patch(
        Polygon(np.asarray(walkable.exterior.coords), fc=FLOOR, ec="none", zorder=0)
    )
    _plan(ax, walkable, config)
    spawn = np.asarray(config["distributions"]["jps-distributions_0"]["coordinates"])
    ax.add_patch(Polygon(spawn, fc="none", ec=TEXT, ls="--", lw=1.3, zorder=2))
    ax.annotate(
        "spawn area:\none agent every 2 s,\n150 in 300 s",
        (18.0, 4.5),
        xytext=(13.0, 4.5),
        ha="right",
        va="center",
        color=TEXT,
        fontsize=9,
        arrowprops={"arrowstyle": "-", "color": TEXT, "lw": 0.8},
    )
    check = np.asarray(config["checkpoints"]["jps-checkpoints_0"]["coordinates"])
    ax.add_patch(Polygon(check, fc="none", ec=TEXT, ls=":", lw=1.2, zorder=2))
    ax.annotate(
        "junction\n(waypoint)",
        (check[:, 0].mean(), 11.5),
        xytext=(-58, -14),
        textcoords="offset points",
        ha="center",
        color=TEXT,
        fontsize=9,
        arrowprops={"arrowstyle": "-", "color": TEXT, "lw": 0.8},
    )
    for _, sign in _signs(config):
        dx = 1.6 * np.sin(np.deg2rad(sign["alpha"]))
        dy = 1.6 * np.cos(np.deg2rad(sign["alpha"]))
        ax.plot(sign["x"], sign["y"], marker="D", ms=7, color=SIGN, zorder=5)
        ax.add_patch(
            FancyArrowPatch(
                (sign["x"], sign["y"]),
                (sign["x"] + dx, sign["y"] + dy),
                arrowstyle="-|>",
                mutation_scale=12,
                color=SIGN,
                lw=1.6,
                zorder=5,
            )
        )
    ax.annotate(
        "2 MW PVC fire\n(FDS burner)",
        (25.0, 10.5),
        xytext=(25.0, 6.2),
        ha="center",
        color=FIRE,
        fontsize=9,
        arrowprops={"arrowstyle": "-|>", "color": FIRE, "lw": 1.0},
    )
    ax.annotate(
        "20 m to exit A",
        (8.5, 11.5),
        ha="center",
        va="center",
        color=TEXT,
        fontsize=9,
    )
    ax.annotate(
        "10 m to exit B",
        (26.8, 12.35),
        ha="center",
        va="center",
        color=TEXT,
        fontsize=9,
    )
    handles = [
        Patch(fc=EXIT, label="exit"),
        Line2D(
            [],
            [],
            marker="D",
            color=SIGN,
            lw=1.6,
            label="sign (arrow: the way it faces)",
        ),
        Patch(fc=FIRE, label="burner"),
    ]
    ax.legend(
        handles=handles,
        loc="lower left",
        frameon=True,
        facecolor="white",
        framealpha=0.8,
        edgecolor="lightgrey",
        labelcolor=TEXT,
        fontsize=9,
    )
    ax.set_xlabel("x [m]", color=TEXT)
    ax.set_ylabel("y [m]", color=TEXT)
    _style(ax)
    _save(fig, "scenario.png")


def fig_fire(field, walkable, config, anim):
    times = (20, 30, 45, 90)
    cell = 0.25
    xs = np.arange(0.0, 30.0 + cell, cell)
    ys = np.arange(0.0, 13.0 + cell, cell)
    outside = anim._outside_mask(walkable, xs, ys)
    grids = [anim._field_grid(field, t, xs, ys, outside) for t in times]
    sns.set_theme(font_scale=1.0, style="whitegrid", font="DejaVu Sans")
    fig, axes = plt.subplots(2, 2, figsize=(9.5, 5.2), layout="constrained")
    for ax, t, grid in zip(axes.ravel(), times, grids, strict=True):
        im = ax.imshow(
            grid,
            origin="lower",
            extent=(0, 30, 0, 13),
            cmap=anim._masked_cmap(anim.SMOKE),
            norm=LogNorm(0.1, 30.0),
            interpolation="bilinear",
            zorder=0,
        )
        with np.errstate(invalid="ignore"):
            ax.contour(
                xs,
                ys,
                np.ma.masked_invalid(grid),
                levels=[1.0],
                colors=[FIRE],
                linewidths=1.0,
                linestyles="--",
            )
        _plan(ax, walkable, config, labels=False)
        corridor = grid[(ys >= 10) & (ys <= 13)][:, (xs >= 1) & (xs <= 29)]
        share = np.mean(corridor[~np.isnan(corridor)] >= 1.0)
        ax.set_title(
            f"t = {t} s   ({share:.0%} of the corridor below 3 m visibility)",
            loc="left",
            color=TEXT,
            fontsize=10,
        )
        _style(ax)
        ax.set_xticks([0, 10, 20, 30])
        ax.set_yticks([0, 10])
    cb = fig.colorbar(im, ax=axes, fraction=0.03, pad=0.02, extend="both")
    cb.set_label("extinction K [1/m]  (visibility S = 3/K)", color=TEXT)
    ticks = (0.1, 0.3, 1.0, 3.0, 10.0, 30.0)
    cb.set_ticks(ticks, labels=[f"{k:g}  ({3 / k:g} m)" for k in ticks])
    cb.ax.minorticks_off()
    cb.ax.tick_params(length=0, labelcolor=TEXT)
    cb.outline.set_visible(False)
    cb.ax.axhline(1.0, color=FIRE, ls="--", lw=1.2)
    _save(fig, "fire.png")


def _tracks(sqlite_path):
    with sqlite3.connect(sqlite_path) as con:
        df = pd.read_sql("select frame, id, pos_x, pos_y from trajectory_data", con)
    return df.sort_values(["id", "frame"])


def _outcomes(tracks):
    """Per agent: spawn time, last time, and the exit it left by (or inside)."""
    last_frame = tracks.frame.max()
    g = tracks.groupby("id")
    out = pd.DataFrame(
        {
            "spawn_s": g.frame.min() / FPS,
            "last_s": g.frame.max() / FPS,
            "x": g.pos_x.last(),
        }
    )
    left = g.frame.max() < last_frame
    out["exit"] = np.where(~left, "inside", np.where(out.x < 15, "A", "B"))
    return out


def fig_trajectories(walkable, config, runs):
    style = {"A": (EXIT_A, "-"), "B": (EXIT_B, "--"), "inside": (INSIDE, ":")}
    sns.set_theme(font_scale=1.0, style="whitegrid", font="DejaVu Sans")
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.4), layout="constrained")
    for ax, (label, path) in zip(axes, runs.items(), strict=True):
        tracks = _tracks(path)
        outcome = _outcomes(tracks)
        for agent, track in tracks.groupby("id"):
            colour, ls = style[outcome.loc[agent, "exit"]]
            ax.plot(track.pos_x, track.pos_y, color=colour, ls=ls, lw=0.7, alpha=0.6)
        _plan(ax, walkable, config, labels=False)
        counts = outcome.exit.value_counts()
        ax.set_title(
            f"{label}: {counts.get('A', 0)} exit A, {counts.get('B', 0)} exit B, "
            f"{counts.get('inside', 0)} inside",
            loc="left",
            color=TEXT,
            fontsize=10,
        )
        _style(ax)
    handles = [
        Line2D([], [], color=c, ls=ls, label=name)
        for name, (c, ls) in {
            "left by exit A": style["A"],
            "left by exit B": style["B"],
            "inside at 300 s": style["inside"],
        }.items()
    ]
    fig.legend(
        handles=handles,
        loc="outside lower center",
        ncols=3,
        frameon=True,
        facecolor="white",
        framealpha=0.8,
        edgecolor="lightgrey",
        labelcolor=TEXT,
    )
    _save(fig, "trajectories.png")


def fig_evacuated(runs):
    sns.set_theme(font_scale=1.0, style="whitegrid", font="DejaVu Sans")
    fig, ax = plt.subplots(figsize=(7.5, 4.0))
    t = np.arange(0.0, T_END + 0.1, 1.0)
    first = None
    for (label, path), colour, ls in zip(
        runs.items(), (CLEAR, FIRE_RUN), ("-", "--"), strict=True
    ):
        outcome = _outcomes(_tracks(path))
        gone = np.sort(outcome.last_s[outcome.exit != "inside"].to_numpy())
        n = np.searchsorted(gone, t, side="right")
        ax.step(t, n, where="post", color=colour, ls=ls, lw=2.0, label=label)
        ax.annotate(
            f"{n[-1]}",
            (T_END, n[-1]),
            xytext=(6, 0),
            textcoords="offset points",
            va="center",
            color=colour,
            fontweight="bold",
        )
        first = outcome if first is None else first
    spawned = np.searchsorted(np.sort(first.spawn_s.to_numpy()), t, side="right")
    ax.plot(t, spawned, color=INSIDE, lw=1.2, ls=":", label="agents spawned")
    ax.annotate(
        "in the fire, half\nare still inside\nat 300 s",
        (255, 86),
        ha="center",
        va="center",
        color=TEXT,
        fontsize=9,
    )
    ax.set_xlim(0, T_END)
    ax.set_ylim(0, 160)
    ax.set_xlabel("time [s]", color=TEXT)
    ax.set_ylabel("agents evacuated", color=TEXT)
    ax.grid(alpha=0.7, linewidth=1, axis="y")
    ax.tick_params(axis="both", which="both", length=0, labelcolor=TEXT)
    sns.despine(ax=ax, left=True, bottom=True)
    ax.legend(
        loc="upper left",
        frameon=True,
        facecolor="white",
        framealpha=0.8,
        edgecolor="lightgrey",
        labelcolor=TEXT,
    )
    _save(fig, "evacuated.png")


def fig_exposure(fed_csv):
    fed = pd.read_csv(
        fed_csv, usecols=["time_s", "agent_id", "fed_cumulative", "speed_factor"]
    )
    sns.set_theme(font_scale=1.0, style="whitegrid", font="DejaVu Sans")
    fig, (top, bottom) = plt.subplots(
        2, 1, figsize=(7.5, 6.0), sharex=True, layout="constrained"
    )
    for _, agent in fed.groupby("agent_id"):
        top.plot(agent.time_s, agent.fed_cumulative, color=INSIDE, lw=0.6, alpha=0.5)
    worst_id = fed.loc[fed.fed_cumulative.idxmax(), "agent_id"]
    worst = fed[fed.agent_id == worst_id]
    top.plot(worst.time_s, worst.fed_cumulative, color=FIRE_RUN, lw=2.0)
    top.annotate(
        f"highest dose: FED {worst.fed_cumulative.max():.2f}",
        (worst.time_s.iloc[-1], worst.fed_cumulative.iloc[-1]),
        xytext=(-10, 12),
        textcoords="offset points",
        ha="right",
        color=FIRE_RUN,
        fontsize=9,
    )
    top.axhline(1.0, color=TEXT, lw=1.0, ls="--")
    top.annotate(
        "incapacitation at FED = 1 (nobody reaches it)",
        (5, 1.0),
        xytext=(0, 4),
        textcoords="offset points",
        color=TEXT,
        fontsize=9,
    )
    top.set_ylim(0, 1.1)
    top.set_ylabel("FED, one line per agent", color=TEXT)

    band = fed.groupby("time_s").speed_factor.describe(percentiles=[0.1, 0.5, 0.9])
    bottom.fill_between(
        band.index,
        band["10%"],
        band["90%"],
        color=FIRE_RUN,
        alpha=0.2,
        lw=0,
        label="middle 80 %",
    )
    bottom.plot(band.index, band["50%"], color=FIRE_RUN, lw=2.0, label="median")
    bottom.plot(
        band.index, band["10%"], color=FIRE_RUN, lw=0.8, ls=":", label="slowest 10 %"
    )
    bottom.axhline(0.1, color=TEXT, lw=1.0, ls="--")
    bottom.annotate(
        "floor 0.1 (min_speed_factor)",
        (5, 0.1),
        xytext=(0, 4),
        textcoords="offset points",
        color=TEXT,
        fontsize=9,
    )
    bottom.set_ylim(0, 1.05)
    bottom.set_xlim(0, T_END)
    bottom.set_ylabel("speed factor of agents inside", color=TEXT)
    bottom.set_xlabel("time [s]", color=TEXT)
    bottom.legend(
        loc="upper right",
        frameon=True,
        facecolor="white",
        framealpha=0.8,
        edgecolor="lightgrey",
        labelcolor=TEXT,
    )
    for ax in (top, bottom):
        ax.grid(alpha=0.7, linewidth=1, axis="y")
        ax.tick_params(axis="both", which="both", length=0, labelcolor=TEXT)
        sns.despine(ax=ax, left=True, bottom=True)
    _save(fig, "exposure.png")


def fig_exits(runs):
    rows = []
    for label, path in runs.items():
        counts = _outcomes(_tracks(path)).exit.value_counts()
        rows.append([counts.get(k, 0) for k in ("A", "B", "inside")])
    data = np.asarray(rows)
    sns.set_theme(font_scale=1.0, style="whitegrid", font="DejaVu Sans")
    fig, ax = plt.subplots(figsize=(7.5, 2.4))
    labels = list(runs)
    left = np.zeros(len(labels))
    parts = (
        ("exit A (20 m)", EXIT_A, ""),
        ("exit B (10 m)", EXIT_B, "//"),
        ("inside at 300 s", INSIDE, ".."),
    )
    for col, (name, colour, hatch) in enumerate(parts):
        ax.barh(
            labels,
            data[:, col],
            left=left,
            color=colour,
            hatch=hatch,
            edgecolor="white",
            label=name,
        )
        for i, v in enumerate(data[:, col]):
            if v >= 6:
                ax.text(
                    left[i] + v / 2,
                    i,
                    str(v),
                    ha="center",
                    va="center",
                    color="white",
                    fontweight="bold",
                    path_effects=[
                        patheffects.withStroke(linewidth=2, foreground="#555555")
                    ],
                )
        left += data[:, col]
    ax.invert_yaxis()
    ax.set_xlim(0, 150)
    ax.set_xlabel("agents", color=TEXT)
    ax.grid(False)
    ax.tick_params(axis="both", which="both", length=0, labelcolor=TEXT)
    sns.despine(ax=ax, left=True, bottom=True)
    ax.legend(
        loc="upper center",
        bbox_to_anchor=(0.5, -0.35),
        ncols=3,
        frameon=True,
        facecolor="white",
        framealpha=0.8,
        edgecolor="lightgrey",
        labelcolor=TEXT,
    )
    _save(fig, "exits.png")


def gif_agents(field, walkable, config, smoke_csv, anim):
    tracks = anim._read_history(Path(smoke_csv))
    cell = 0.5
    xs = np.arange(0.0, 30.0 + cell, cell)
    ys = np.arange(0.0, 13.0 + cell, cell)
    outside = anim._outside_mask(walkable, xs, ys)
    step_s, fps = 2.0, 8  # 16 s of simulation per second of GIF
    times = np.arange(0.0, T_END + 0.1, step_s)
    sns.set_theme(font_scale=0.9, style="whitegrid", font="DejaVu Sans")
    fig = plt.figure(figsize=(6.6, 3.8), layout="constrained")
    grid = fig.add_gridspec(2, 2, height_ratios=(1.0, 0.05))
    ax = fig.add_subplot(grid[0, :])
    im = ax.imshow(
        anim._field_grid(field, 0.0, xs, ys, outside),
        origin="lower",
        extent=(0, 30, 0, 13),
        cmap=anim._masked_cmap(anim.SMOKE),
        norm=LogNorm(0.1, 30.0),
        interpolation="bilinear",
        zorder=0,
    )
    _plan(ax, walkable, config, labels=False)
    for x, name in ((0.5, "exit A"), (29.5, "exit B")):
        ax.annotate(
            name, (x, 9.6), ha="center", va="top", color=EXIT, fontweight="bold"
        )
    _style(ax)
    ax.set_xticks([])
    ax.set_yticks([])
    scat = ax.scatter(
        [],
        [],
        c=[],
        cmap=anim.SPEED_CMAP,
        norm=Normalize(0.1, 1.0),
        edgecolors="white",
        linewidths=0.5,
        zorder=4,
    )
    bars = (
        (im, grid[1, 0], "smoke K [1/m], log scale", (0.1, 1, 10)),
        (scat, grid[1, 1], "speed factor (bigger dot = slower)", (0.1, 0.5, 1.0)),
    )
    for mappable, slot, label, ticks in bars:
        cb = fig.colorbar(mappable, cax=fig.add_subplot(slot), orientation="horizontal")
        cb.set_label(label, color=TEXT)
        cb.set_ticks(ticks, labels=[f"{t:g}" for t in ticks])
        cb.ax.minorticks_off()
        cb.ax.tick_params(length=0, labelcolor=TEXT)
        cb.outline.set_visible(False)
    title = ax.set_title("", loc="left", color=TEXT, fontsize=10)

    def update(t):
        im.set_data(anim._field_grid(field, t, xs, ys, outside))
        pts = anim._agents_at(tracks, t)
        xy = np.array([[x, y] for x, y, _ in pts]) if pts else np.empty((0, 2))
        factors = np.array([sf for _, _, sf in pts])
        scat.set_offsets(xy)
        scat.set_array(factors)
        scat.set_sizes(18.0 * (1.0 + 2.0 * np.clip((1.0 - factors) / 0.9, 0, 1)))
        title.set_text(
            f"t = {t:5.1f} s   {len(pts)} agents inside   ({step_s * fps:g}x real time)"
        )
        return im, scat, title

    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        raw = Path(tmp) / "raw.gif"
        anim_obj = animation.FuncAnimation(fig, update, frames=times, blit=False)
        anim_obj.save(str(raw), writer=animation.PillowWriter(fps=fps), dpi=100)
        plt.close(fig)
        final = OUT / "agents_smoke.gif"
        if shutil.which("ffmpeg") is None:
            shutil.copy(raw, final)
        else:
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-loglevel",
                    "error",
                    "-i",
                    str(raw),
                    "-vf",
                    "split[a][b];[a]palettegen=max_colors=64[p];[b][p]paletteuse=dither=bayer",
                    str(final),
                ],
                check=True,
            )
    print(f"wrote {final} ({final.stat().st_size / 1e6:.1f} MB)")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data", required=True, help="FDS output directory")
    parser.add_argument("--runs", required=True, type=Path, help="run outputs")
    parser.add_argument("--no-gif", action="store_true", help="skip the animation")
    args = parser.parse_args()

    walkable = wkt.loads((ASSET / "geometry.wkt").read_text())
    config = json.loads((ASSET / "config.json").read_text())
    anim = _animator()
    # The deck writes slices at z = 2.0 m only; the 1.6 m default resolves to it.
    field = ExtinctionField.from_fds(args.data)
    runs = {
        "clear air": args.runs / "tj_clear.sqlite",
        "2 MW fire": args.runs / "tj_fire.sqlite",
    }

    fig_scenario(walkable, config)
    fig_fire(field, walkable, config, anim)
    fig_trajectories(walkable, config, runs)
    fig_evacuated(runs)
    fig_exposure(args.runs / "tj_fire_fed.csv")
    fig_exits(runs)
    if not args.no_gif:
        gif_agents(field, walkable, config, args.runs / "tj_fire_smoke.csv", anim)


if __name__ == "__main__":
    main()
