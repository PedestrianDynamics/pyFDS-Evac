"""Agents-and-smoke animations for the two study pages.

The same picture as "The run, animated" on "A crowd in a real fire"
(``scripts/docs/first_fds_case_figures.py``): the FDS extinction field as the
background and the agents as dots. It reuses the helpers of
``scripts/animate_agents_smoke.py`` and a 40-colour GIF palette pass. The
FDS output and the runs are not in the repository; both commands read them
from ``--data`` and ``--runs``.

The Schröder room (``docs/study-schroeder2020.md``), one GIF per door layout,
capped exit, pre-movement 0, arm U. ``DATA`` and ``RUNS`` are the folders of
``scripts/docs/schroeder_room_maps.py``, after it has run::

    uv run --with "pedpy>=1.5.1" python scripts/docs/study_animations.py \\
        schroeder --data DATA --runs RUNS

The background is K at 2.0 m from the same slices as the maps. An agent is
drawn as a red cross while it stands in a 0.6 m cell whose ASET
(K ≥ 0.23 1/m, ∃ rule) has passed, and as a blue dot otherwise. The dashed
outline marks the cells with DIFF < 0 on the page's map (maximum RSET over
the 10 seeds); the animation shows one seed, the one whose room empties at
the median time.

With and without the fire (``docs/howto-with-without-fire.md``): arms U and
R, pre-movement 30 s, one seed. ``DATA`` is the ``fire_2MW_PVC`` output and
``RUNS`` the folder of ``scripts/docs/fire_blind_vs_coupled.py``::

    uv run python scripts/docs/study_animations.py \\
        fire-blind --data DATA --runs RUNS

The seed is the one whose last R agent leaves at the median time. Agents are
coloured and sized by their speed factor, as on "A crowd in a real fire".

Writes GIFs to ``site/static/images/studies/schroeder2020/`` and
``site/static/images/fire-blind/``. Needs ``ffmpeg`` for the palette pass.
"""

import argparse
import json
import shutil
import subprocess
import sys
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
from shapely import box, unary_union, wkt

sys.path.insert(0, str(Path(__file__).resolve().parent))
import first_fds_case_figures as ffc  # noqa: E402
import schroeder_room_maps as maps  # noqa: E402

from pyfds_evac import ExtinctionField  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
TEXT = "dimgrey"
FAIL = "#d73027"  # DIFF < 0 and agents past ASET: one meaning, one colour
CLEAR = "#4575b4"
HALO = [patheffects.withStroke(linewidth=3.0, foreground="white")]
STEP_S, FPS = 1.0, 8  # 8 s of simulation per second of GIF


def write_gif(fig, update, times, final):
    """Render with Pillow, then reduce to 64 colours with ffmpeg."""
    final.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        raw = Path(tmp) / "raw.gif"
        anim = animation.FuncAnimation(fig, update, frames=times, blit=False)
        anim.save(str(raw), writer=animation.PillowWriter(fps=FPS), dpi=100)
        plt.close(fig)
        if shutil.which("ffmpeg") is None:
            shutil.copy(raw, final)
        else:
            palette = (
                "split[a][b];[a]palettegen=max_colors=40[p];"
                "[b][p]paletteuse=dither=none:diff_mode=rectangle"
            )
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-loglevel",
                    "error",
                    "-i",
                    str(raw),
                    "-vf",
                    palette,
                    str(final),
                ],
                check=True,
            )
    print(
        f"wrote {final.relative_to(ROOT)} ({final.stat().st_size / 1e6:.1f} MB, {len(times)} frames)"
    )


def colourbar(fig, mappable, slot, label, ticks):
    cb = fig.colorbar(mappable, cax=fig.add_subplot(slot), orientation="horizontal")
    cb.set_label(label, color=TEXT)
    cb.set_ticks(ticks, labels=[f"{t:g}" for t in ticks])
    cb.ax.minorticks_off()
    cb.ax.tick_params(length=0, labelcolor=TEXT)
    cb.outline.set_visible(False)
    return cb


def median_seed(values):
    """The seed whose value is closest to the median; the lower seed on a tie."""
    med = float(np.median(list(values.values())))
    return min(values, key=lambda s: (abs(values[s] - med), s)), med


# --- The Schröder room -------------------------------------------------------


def k_slice(fds_dir):
    """Times and K (t, ny, nx) of the z = 2.0 m slice, as the maps read it."""
    import fdsreader

    sim = fdsreader.Simulation(str(fds_dir))
    sl = next(
        s
        for s in sim.slices
        if s.quantity.name == maps.QUANTITIES["K"]
        and s.orientation == 3
        and abs((s.extent.z_start + s.extent.z_end) / 2 - maps.Z) < 0.06
    )
    data, coords = sl.to_global(return_coordinates=True)
    xs, ys = coords["x"], coords["y"]
    extent = (float(xs[0]), float(xs[-1]), float(ys[0]), float(ys[-1]))
    return np.asarray(sl.times), np.transpose(data, (0, 2, 1)), extent


def fail_outline(diff, grid):
    """Union of the DIFF < 0 cells, as shapely geometry."""
    cells = [
        box(
            grid.x_edges[i],
            grid.y_edges[j],
            min(grid.x_edges[i + 1], 30.0),
            min(grid.y_edges[j + 1], 10.0),
        )
        for j, i in zip(*np.nonzero(np.nan_to_num(diff, nan=0.0) < 0))
    ]
    return unary_union(cells)


def pooled_diff(runs, v, fds, walkable, grid, aset):
    """The page's DIFF map of one version, and the median-time seed."""
    rsets, last = [], {}
    for seed in maps.SEEDS:
        df = maps.trajectory(maps.run_dir(runs, v, fds, seed))
        rsets.append(maps.pedpy_rset(df, walkable, grid))
        last[seed] = df.frame.max() / maps.FPS
    m = maps.measures(aset, maps.pool(rsets, "max"), grid)
    seed, med = median_seed(last)
    print(
        f"- {v.layout} {v.name}: min DIFF {m['min']:.0f} s, area DIFF < 0 "
        f"{m['area']:.1f} m²; seed {seed} empties at {last[seed]:.1f} s (median {med:.1f} s)"
    )
    return m, seed, last[seed]


def room_axes(walkable, exits, outline):
    sns.set_theme(font_scale=0.9, style="whitegrid", font="DejaVu Sans")
    fig = plt.figure(figsize=(7.2, 3.6), layout="constrained")
    gs = fig.add_gridspec(2, 2, height_ratios=(1.0, 0.06))
    ax = fig.add_subplot(gs[0, :])
    maps._plan(ax, walkable, exits)
    for geom in getattr(outline, "geoms", [outline]):
        ax.plot(
            *geom.exterior.xy, color=FAIL, lw=1.6, ls="--", zorder=6, path_effects=HALO
        )
    return fig, gs, ax


def draw_room_legend(ax):
    handles = [
        Line2D(
            [],
            [],
            ls="",
            marker="o",
            mfc=CLEAR,
            mec="white",
            ms=6,
            label="agent, cell still below the limit",
        ),
        Line2D(
            [],
            [],
            ls="",
            marker="X",
            mfc=FAIL,
            mec="white",
            ms=8,
            label="agent in a cell past its ASET",
        ),
        Line2D(
            [], [], color=FAIL, ls="--", lw=1.6, label="DIFF < 0 on the map (10 seeds)"
        ),
    ]
    ax.legend(
        handles=handles,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.02),
        ncols=3,
        fontsize=7,
        frameon=True,
        facecolor="white",
        framealpha=0.8,
        edgecolor="lightgrey",
        labelcolor=TEXT,
        handletextpad=0.3,
        columnspacing=1.0,
    )


def agent_states(df, frame, aset, grid, t):
    pts = df[df.frame == frame]
    xy = pts[["x", "y"]].to_numpy()
    i = np.clip(
        np.searchsorted(grid.x_edges, xy[:, 0], side="right") - 1, 0, grid.shape[1] - 1
    )
    j = np.clip(
        np.searchsorted(grid.y_edges, xy[:, 1], side="right") - 1, 0, grid.shape[0] - 1
    )
    past = np.nan_to_num(aset[j, i], nan=np.inf) <= t
    return xy, past


def room_gif(fire, df, aset, m, grid, walkable, exits, name, title):
    times_k, k, extent = fire
    t_end = STEP_S * np.ceil(df.frame.max() / maps.FPS / STEP_S) + 2 * STEP_S
    times = np.arange(0.0, t_end + 1e-9, STEP_S)
    fig, gs, ax = room_axes(walkable, exits, fail_outline(m["diff"], grid))
    im = ax.imshow(
        k[0],
        origin="lower",
        extent=extent,
        cmap=maps_smoke(),
        norm=LogNorm(0.02, 2.0),
        interpolation="nearest",
        zorder=0,
    )
    clear = ax.scatter(
        [], [], s=22, c=CLEAR, edgecolors="white", linewidths=0.5, zorder=7
    )
    past = ax.scatter(
        [], [], s=46, c=FAIL, marker="X", edgecolors="white", linewidths=0.5, zorder=8
    )
    cb = colourbar(fig, im, gs[1, 0], "K at 2.0 m [1/m], log scale", (0.05, 0.23, 1))
    cb.ax.axvline(0.23, color=FAIL, lw=1.5)
    draw_room_legend(ax)
    fig.add_subplot(gs[1, 1]).set_axis_off()
    head = ax.set_title("", loc="left", color=TEXT, fontsize=9)

    def update(t):
        im.set_data(k[np.abs(times_k - t).argmin()])
        xy, now = agent_states(df, int(round(t * maps.FPS)), aset, grid, t)
        clear.set_offsets(xy[~now] if len(xy) else np.empty((0, 2)))
        past.set_offsets(xy[now] if len(xy) else np.empty((0, 2)))
        head.set_text(
            f"{title}   t = {t:5.1f} s   {len(xy):3d} inside, "
            f"{int(now.sum()):3d} past ASET   ({STEP_S * FPS:g}x real time)"
        )
        return im, clear, past, head

    write_gif(fig, update, times, maps.OUT / name)


def maps_smoke():
    anim = ffc._animator()
    return anim._masked_cmap(anim.SMOKE)


def report_states(df, aset, grid, layout):
    """When agents stand in cells past their ASET, as the caption quotes it."""
    rows = []
    for t in np.arange(0.0, df.frame.max() / maps.FPS + 1e-9, STEP_S):
        xy, past = agent_states(df, int(round(t * maps.FPS)), aset, grid, t)
        west = int((past & (xy[:, 0] < 15.0)).sum()) if len(xy) else 0
        rows.append((t, len(xy), int(past.sum()), west))
    first = next((r for r in rows if r[2] > 0), None)
    peak = max(rows, key=lambda r: r[2])
    rest = [r for r in rows if r[1] > 0]
    all_from = next(
        (r[0] for i, r in enumerate(rest) if all(q[1] == q[2] for q in rest[i:])),
        None,
    )
    print(
        f"- {layout}: first agent past ASET at {first[0]:.0f} s; every agent inside "
        f"past ASET from {'never' if all_from is None else f'{all_from:.0f} s'}; last past ASET at {max(r[0] for r in rows if r[2] > 0):.0f} s; peak {peak[2]} at {peak[0]:.0f} s; "
        f"past-ASET agent-frames west of x = 15 m: {sum(r[3] for r in rows)} of "
        f"{sum(r[2] for r in rows)}"
    )


def schroeder(data, runs):
    walkable, exits = maps.load_layouts(data)
    grids = {k: maps.make_grid(w) for k, w in walkable.items()}
    versions = {v.layout: v for v in maps.VERSIONS if v.name == "capped_pre0"}
    for layout, doors in (("1door", "one door"), ("2door", "two doors")):
        fds = maps.LAYOUT_FDS[layout][0]
        fire = maps.fire_fields(data / fds, runs / "cache")
        aset = maps.cell_aset(fire.node["K 0.23"], fire, grids[layout])
        v = versions[layout]
        m, seed, _ = pooled_diff(runs, v, fds, walkable[layout], grids[layout], aset)
        df = maps.trajectory(maps.run_dir(runs, v, fds, seed))
        report_states(df, aset, grids[layout], layout)
        room_gif(
            k_slice(data / fds),
            df,
            aset,
            m,
            grids[layout],
            walkable[layout],
            exits[layout],
            f"agents_smoke_{layout}.gif",
            f"{doors}, seed {seed}",
        )


# --- With and without the fire -------------------------------------------------


def median_r_seed(runs, pre):
    summary = pd.read_csv(runs / "summary_runs.csv")
    rows = summary[(summary.arm == "R") & (summary.pre == pre)]
    seed, med = median_seed(dict(zip(rows.seed, rows.rset_last)))
    both = summary[(summary.pre == pre) & (summary.seed == seed)].set_index("arm")
    for arm in ("U", "R"):
        r = both.loc[arm]
        print(
            f"- {arm}: last out {r.rset_last:.1f} s, exit A {r.exit_A}, exit B {r.exit_B}"
        )
    print(
        f"- pre {pre} s: seed {seed}, R last out {rows.set_index('seed').rset_last[seed]:.1f} s "
        f"(median {med:.1f} s)"
    )
    return seed


def tj_panel(ax, field_grid, walkable, config, anim, label):
    im = ax.imshow(
        field_grid,
        origin="lower",
        extent=(0, 30, 0, 13),
        cmap=anim._masked_cmap(anim.SMOKE),
        norm=LogNorm(0.1, 30.0),
        interpolation="bilinear",
        zorder=0,
    )
    ffc._plan(ax, walkable, config, labels=False)
    for x, name in ((0.5, "exit A"), (29.5, "exit B")):
        ax.annotate(
            name,
            (x, 9.6),
            ha="center",
            va="top",
            color=ffc.EXIT,
            fontweight="bold",
            path_effects=[patheffects.withStroke(linewidth=2.5, foreground="white")],
        )
    ffc._style(ax)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_title(label, loc="left", color=TEXT, fontsize=9)
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
    return im, scat


def fire_blind(data, runs, pre=30):
    anim = ffc._animator()
    seed = median_r_seed(runs, pre)
    folder = runs / f"pre{pre:02d}" / f"seed{seed:02d}"
    walkable = wkt.loads((ffc.ASSET / "geometry.wkt").read_text())
    config = json.loads((ffc.ASSET / f"config_initial_pre{pre}.json").read_text())
    field = ExtinctionField.from_fds(str(data))
    arms = {
        "U": anim._read_history(folder / "U_smoke.csv"),
        "R": anim._read_history(folder / "R_smoke.csv"),
    }
    t_end = max(t for tr in arms["R"].values() for t, *_ in tr)
    times = np.arange(0.0, STEP_S * np.ceil(t_end / STEP_S) + 1e-9, STEP_S)
    cell = 0.5
    xs = np.arange(0.0, 30.0 + cell, cell)
    ys = np.arange(0.0, 13.0 + cell, cell)
    outside = anim._outside_mask(walkable, xs, ys)
    sns.set_theme(font_scale=0.9, style="whitegrid", font="DejaVu Sans")
    fig = plt.figure(figsize=(6.6, 6.6), layout="constrained")
    gs = fig.add_gridspec(3, 2, height_ratios=(1.0, 1.0, 0.06))
    labels = {
        "U": "U: smoke-blind, free speed, fire-free route",
        "R": "R: smoke slows the agents and enters the route choice",
    }
    first = anim._field_grid(field, 0.0, xs, ys, outside)
    panels = {
        arm: tj_panel(
            fig.add_subplot(gs[row, :]), first, walkable, config, anim, labels[arm]
        )
        for row, arm in enumerate(("U", "R"))
    }
    colourbar(fig, panels["U"][0], gs[2, 0], "smoke K [1/m], log scale", (0.1, 1, 10))
    colourbar(
        fig,
        panels["U"][1],
        gs[2, 1],
        "speed factor (bigger dot = slower)",
        (0.1, 0.5, 1.0),
    )
    head = fig.suptitle("", x=0.01, ha="left", color=TEXT, fontsize=10)

    def update(t):
        grid = anim._field_grid(field, t, xs, ys, outside)
        counts = []
        for arm, (im, scat) in panels.items():
            im.set_data(grid)
            pts = anim._agents_at(arms[arm], t)
            xy = np.array([[x, y] for x, y, _ in pts]) if pts else np.empty((0, 2))
            sf = np.array([s for _, _, s in pts])
            scat.set_offsets(xy)
            scat.set_array(sf)
            scat.set_sizes(18.0 * (1.0 + 2.0 * np.clip((1.0 - sf) / 0.9, 0, 1)))
            counts.append(f"{arm} {len(pts):3d}")
        wait = "   (everyone still waiting)" if t < pre else ""
        head.set_text(
            f"pre-movement {pre} s, seed {seed}, {STEP_S * FPS:g}x real time\n"
            f"t = {t:5.1f} s   inside: {', '.join(counts)}{wait}"
        )
        return head

    write_gif(
        fig,
        update,
        times,
        ffc.ROOT
        / "site"
        / "static"
        / "images"
        / "fire-blind"
        / "agents_smoke_u_vs_r.gif",
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("study", choices=("schroeder", "fire-blind"))
    parser.add_argument("--data", type=Path, required=True, help="FDS output folder")
    parser.add_argument(
        "--runs", type=Path, required=True, help="the study's run folder"
    )
    opts = parser.parse_args()
    if opts.study == "schroeder":
        schroeder(opts.data.resolve(), opts.runs.resolve())
        return
    fire_blind(opts.data.resolve(), opts.runs.resolve())


if __name__ == "__main__":
    main()
