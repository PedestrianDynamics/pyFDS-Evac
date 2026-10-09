"""Agents-and-smoke animations for the two study pages.

The same picture as "The run, animated" on "A crowd in a fire"
(``scripts/docs/first_fds_case_figures.py``): the FDS extinction field as the
background and the agents as dots. It reuses the helpers of
``scripts/animate_agents_smoke.py`` and a 40-colour GIF palette pass. The
FDS output and the runs are not in the repository; both commands read them
from ``--data`` and ``--runs``.

The Schröder room (``docs/study-schroeder2020.md``), one GIF per door layout,
capped exit, pre-movement 0, arm U. ``DATA`` and ``RUNS`` are the folders of
``scripts/docs/schroeder_room_maps.py``, after it has run::

    uv run --with "pedpy>=1.5.1" python scripts/docs/study_animations.py \\
        schroeder --data DATA --runs RUNS [--family rel|hrr060]

``--family`` follows the map script: ``rel`` (default) writes to
``schroeder2020/``, ``hrr060`` to its ``hrr060/`` subfolder.

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
coloured and sized by their speed factor, as on "A crowd in a fire".

Route choice in smoke after Schröder et al. (2015)
(``docs/study-schroeder2015.md``): the smoke-blind and gate arms side by side
on the main fire ``a047_pvc_h40``. ``DATA`` is the study folder of
``scripts/docs/schroeder2015_route.py``: the FDS output in
``DATA/a047_pvc_h40/`` and the runs in ``DATA/p1_a047_pvc_h40*/``::

    uv run python scripts/docs/study_animations.py schroeder2015 --data DATA

The background is K at 1.6 m, the slice of routing, walking speed and gas
dose. The seed is the gate seed whose door-A count is closest to the median.
Walking agents are coloured and sized by their speed factor; agents still in
pre-movement are drawn as open circles.

Writes GIFs to ``site/static/images/studies/schroeder2020/``,
``site/static/images/fire-blind/`` and
``site/static/images/studies/schroeder2015/``. Needs ``ffmpeg`` for the
palette pass. Needs ``ffmpeg`` for the palette pass.
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
from matplotlib.colors import BoundaryNorm, ListedColormap, LogNorm, Normalize
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


def write_gif(fig, update, times, final, fps=FPS, colours=40):
    """Render with Pillow, then reduce to *colours* colours with ffmpeg."""
    final.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        raw = Path(tmp) / "raw.gif"
        anim = animation.FuncAnimation(fig, update, frames=times, blit=False)
        anim.save(str(raw), writer=animation.PillowWriter(fps=fps), dpi=100)
        plt.close(fig)
        if shutil.which("ffmpeg") is None:
            shutil.copy(raw, final)
        else:
            palette = (
                f"split[a][b];[a]palettegen=max_colors={colours}[p];"
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


def k_slice(fds_dir, z=maps.Z):
    """Times and K (t, ny, nx) of the slice at z; 2.0 m is the height of the maps."""
    import fdsreader

    sim = fdsreader.Simulation(str(fds_dir))
    sl = next(
        s
        for s in sim.slices
        if s.quantity.name == maps.QUANTITIES["K"]
        and s.orientation == 3
        and abs((s.extent.z_start + s.extent.z_end) / 2 - z) < 0.06
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


# --- Route choice in smoke after Schröder et al. (2015) ------------------------

ROUTE_Z = 1.6  # m, the slice of routing, walking speed and gas dose
ROUTE_STEP_S, ROUTE_FPS = 2.0, 8  # 16 s of simulation per second of GIF
ROUTE_ARMS = {"sb": "(a) smoke-blind", "gate": "(b) gate"}
# Gate-arm events of seed 5, the seed the animation shows. Over the 10
# seeds: F via A at 47 s in all; every route refused from 130-134 s;
# fallback wave 151-155 s; E via door B at 152-156 s.
ROUTE_EVENTS = (
    (47.0, "47 s: F re-paths via door A;\nhalf the agents bound for F\nswitch to E"),
    (134.0, "134 s: first agents find\nevery route refused"),
    (152.0, "152 s: fallback wave,\nagents bound for E\nswitch to F"),
    (153.0, "153 s: E re-paths via door B,\nalready refused"),
)
WAIT = "black"  # open ring: filled dots are walking agents
# Few colour classes, so the 40-colour GIF palette keeps them all and the
# frames compress: K in log-spaced classes (0.23 1/m is the smoke limit of
# the tenability pages), speed factor in steps of 0.15.
ROUTE_K = (0.1, 0.23, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0)
ROUTE_SF = (0.1, 0.25, 0.4, 0.55, 0.7, 0.85, 1.0001)


def route_seed(route, runs):
    """The gate seed whose door-A count is closest to the median."""
    counts = {
        s: int((route.agents(runs / f"gate_s{s}.sqlite").door == "A").sum())
        for s in route.SEEDS
    }
    seed, med = median_seed(counts)
    print(
        f"- gate door-A counts {dict(sorted(counts.items()))}; "
        f"seed {seed} ({counts[seed]}, median {med:g})"
    )
    return seed


def report_route_arm(arm, ag, cap):
    """The numbers the page's caption quotes for one arm of the shown seed."""
    routes = (ag.door + ag.exit).value_counts().to_dict()
    b = ag[ag.door == "B"].t_door.sort_values()
    late = b[b >= 145.0]
    be = ag[(ag.door == "B") & (ag.exit == "E")].t_door
    walking = ag[~ag.evacuated]
    print(
        f"- {arm}: routes {routes}; at 146 s through door A "
        f"{int(((ag.door == 'A') & (ag.t_door <= 146.0)).sum())}; "
        f"door B before 145 s {int((b < 145.0).sum())} (last at "
        f"{b[b < 145.0].max():.1f} s), from 145 s "
        f"{len(late)} (first at {late.min():.1f} s); B->E door times "
        f"{be.min():.1f}-{be.max():.1f} s; last out {ag.t_out.max():.1f} s; "
        f"still inside at {cap:g} s: {len(walking)} (movement start "
        f"{walking.t_move.round(1).tolist()} s, exit {walking.exit.tolist()})"
    )


def route_frames(fed):
    """Agents per FED sample time: x, y and the speed factor, NaN while waiting.

    The FED history writes a speed factor of 0 before an agent's pre-movement
    ends; the animation draws those agents as waiting instead.
    """
    d = pd.read_csv(
        fed, usecols=["time_s", "agent_id", "x", "y", "desired_speed", "speed_factor"]
    )
    d["sf"] = d.speed_factor.where(d.desired_speed > 0)
    return {round(t, 3): g[["x", "y", "sf"]].to_numpy() for t, g in d.groupby("time_s")}


def route_counts(ag, t):
    door = ag.door[ag.t_door <= t].value_counts()
    out = ag.exit[ag.t_out <= t].value_counts()
    inside = len(ag) - int(out.sum())
    return (
        f"through door A {door.get('A', 0):3d}, B {door.get('B', 0):3d}\n"
        f"out via exit E {out.get('E', 0):3d}, F {out.get('F', 0):3d}; "
        f"inside {inside:3d}"
    )


def route_smoke(anim):
    """The smoke ramp without its darkest fifth, so dots stay visible on it."""
    smoke = anim._masked_cmap(anim.SMOKE)
    cmap = ListedColormap(smoke(np.linspace(0.0, 0.8, len(ROUTE_K) - 1)))
    cmap.set_bad("white")
    return cmap


def route_plan(ax, geo, k0, extent, anim):
    im = ax.imshow(
        k0,
        origin="lower",
        extent=extent,
        cmap=route_smoke(anim),
        norm=BoundaryNorm(ROUTE_K, len(ROUTE_K) - 1),
        interpolation="nearest",
        zorder=0,
    )
    walk = geo.walkable()
    for ring in [walk.exterior, *walk.interiors]:
        ax.plot(*ring.xy, color=ffc.WALL, lw=1.0, zorder=2)
    x0, y0, x1, y1 = geo.ROOM3
    ax.plot([x0, x1, x1, x0, x0], [y0, y0, y1, y1, y0], color=ffc.WALL, lw=1.0)
    bx0, bx1, by0, by1 = geo.BURNER_XY
    ax.fill([bx0, bx1, bx1, bx0], [by0, by0, by1, by1], color=ffc.FIRE, zorder=3)
    for xy in (geo.exit_polygon("E"), geo.exit_polygon("F")):
        ax.fill(*np.asarray(xy).T, color=ffc.EXIT, zorder=3)
    labels = {
        "door A": (0.5, 1.6, "left", ffc.WALL),
        "door B": (0.5, 21.6, "left", ffc.WALL),
        "exit E": (-2.6, -11.0, "center", ffc.EXIT),
        "exit F": (-2.6, 36.0, "center", ffc.EXIT),
        "Room 3": (10.4, 30.3, "right", TEXT),
        "hall": (10.4, 23.3, "right", TEXT),
    }
    for text, (x, y, ha, col) in labels.items():
        ax.text(
            x,
            y,
            text,
            ha=ha,
            va="center",
            fontsize=7,
            color=col,
            fontweight="bold" if col != TEXT else "normal",
            path_effects=HALO,
            zorder=9,
        )
    ax.set_aspect("equal")
    ax.set_xlim(-5.6, 11.0)
    ax.set_ylim(-12.0, 37.0)
    ffc._style(ax)
    ax.set_xticks([])
    ax.set_yticks([])
    walking = ax.scatter(
        [],
        [],
        c=[],
        cmap=anim.SPEED_CMAP,
        norm=BoundaryNorm(ROUTE_SF, 256),
        edgecolors="white",
        linewidths=0.6,
        zorder=6,
    )
    waiting = ax.scatter(
        [], [], s=10, facecolors="none", edgecolors=WAIT, linewidths=0.8, zorder=5
    )
    return im, walking, waiting


def schroeder2015(data):
    """Smoke-blind and gate side by side, main fire, the median gate seed."""
    import schroeder2015_route as route  # also turns off fdsreader caching

    geo = route._geometry()
    anim = ffc._animator()
    runs = route.run_dir(data, route.MAIN)
    seed = route_seed(route, runs)
    times_k, k, extent = k_slice(data / route.MAIN, z=ROUTE_Z)
    arms = {}
    for arm in ROUTE_ARMS:
        ag = route.agents(
            runs / f"{arm}_s{seed}.sqlite", runs / f"{arm}_s{seed}_exit.csv"
        )
        report_route_arm(arm, ag, route.CAP)
        arms[arm] = (ag, route_frames(runs / f"{arm}_s{seed}_fed.csv.gz"))
    times = np.arange(0.0, route.CAP, ROUTE_STEP_S)  # FED history ends at 399 s

    sns.set_theme(font_scale=0.9, style="whitegrid", font="DejaVu Sans")
    fig = plt.figure(figsize=(6.4, 8.6), layout="constrained")
    gs = fig.add_gridspec(2, 2, height_ratios=(1.0, 0.025))
    panels = {}
    for col, (arm, label) in enumerate(ROUTE_ARMS.items()):
        ax = fig.add_subplot(gs[0, col])
        panels[arm] = (
            *route_plan(ax, geo, k[0], extent, anim),
            ax.set_title("", loc="left", color=TEXT, fontsize=8.5),
            label,
        )
    im0, walk0 = panels["sb"][0], panels["sb"][1]
    walk0.set_array(np.array([1.0]))
    colourbar(fig, im0, gs[1, 0], f"K at {ROUTE_Z:g} m [1/m]", ROUTE_K[1:-1])
    colourbar(
        fig, walk0, gs[1, 1], "speed factor (bigger dot = slower)", (0.1, 0.4, 0.7, 1.0)
    )
    walk0.set_array(np.array([]))
    fig.axes[0].legend(
        handles=[
            Line2D(
                [],
                [],
                ls="",
                marker="o",
                mfc="none",
                mec=WAIT,
                ms=4,
                label="waiting (pre-movement)",
            ),
            Line2D(
                [],
                [],
                ls="",
                marker="o",
                mfc=plt.get_cmap(anim.SPEED_CMAP)(1.0),
                mec="white",
                ms=5,
                label="walking",
            ),
        ],
        loc="lower right",
        bbox_to_anchor=(1.0, 0.03),
        fontsize=7,
        frameon=True,
        facecolor="white",
        framealpha=0.9,
        edgecolor="lightgrey",
        labelcolor=TEXT,
        handletextpad=0.3,
    )
    event = fig.axes[1].text(
        10.8,
        -5.0,
        "",
        ha="right",
        va="center",
        fontsize=7,
        color=TEXT,
        path_effects=HALO,
        zorder=9,
    )
    head = fig.suptitle("", x=0.01, ha="left", color=TEXT, fontsize=9)

    def update(t):
        im_k = k[np.abs(times_k - t).argmin()]
        waiting_n = 0
        for arm, (im, walking, waiting, title, label) in panels.items():
            ag, frames = arms[arm]
            pts = frames.get(round(t, 3), np.empty((0, 3)))
            wait = np.isnan(pts[:, 2])
            waiting_n = int(wait.sum())
            sf = pts[~wait, 2]
            im.set_data(im_k)
            walking.set_offsets(pts[~wait, :2])
            walking.set_array(sf)
            walking.set_sizes(12.0 * (1.0 + 2.0 * np.clip((1.0 - sf) / 0.9, 0, 1)))
            waiting.set_offsets(pts[wait, :2])
            title.set_text(f"{label}\n{route_counts(ag, t)}")
        done = [text for t0, text in ROUTE_EVENTS if t >= t0]
        event.set_text("gate:\n" + "\n".join(done) if done else "")
        head.set_text(
            f"main fire {route.MAIN}, seed {seed}, {ROUTE_STEP_S * ROUTE_FPS:g}x real time\n"
            f"t = {t:5.0f} s   waiting: {waiting_n:3d} (same agents, starts and "
            "start times in both arms)"
        )
        return head

    write_gif(
        fig,
        update,
        times,
        route.OUT / "agents_smoke_gate.gif",
        fps=ROUTE_FPS,
        colours=64,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("study", choices=("schroeder", "fire-blind", "schroeder2015"))
    parser.add_argument(
        "--data",
        type=Path,
        required=True,
        help="FDS output folder; schroeder2015: the study folder",
    )
    parser.add_argument(
        "--runs", type=Path, help="the study's run folder (not for schroeder2015)"
    )
    parser.add_argument(
        "--family",
        choices=tuple(maps.FAMILIES),
        default="rel",
        help="schroeder only: FDS runs, rel (default) or hrr060",
    )
    opts = parser.parse_args()
    if opts.study == "schroeder2015":
        schroeder2015(opts.data.resolve())
        return
    if opts.runs is None:
        parser.error(f"{opts.study} needs --runs")
    if opts.study == "schroeder":
        maps.use_family(opts.family)
        schroeder(opts.data.resolve(), opts.runs.resolve())
        return
    fire_blind(opts.data.resolve(), opts.runs.resolve())


if __name__ == "__main__":
    main()
