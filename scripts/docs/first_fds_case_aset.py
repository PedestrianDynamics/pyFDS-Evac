"""ASET against exit time for the "A crowd in a real fire" page.

For every agent of the T-junction fire run, compares the first time a
tenability limit is reached at the agent's own position with its exit time.
It also samples the same limits at fixed points and on a grid (a person
standing still from ignition), and computes when the signs of each route stop
being visible (fdsvismap). Nothing here changes the engine: the per-agent
values come from the run's output files, the fields from ``ExtinctionField``
and ``FdsFedField``, the sign maps from fdsvismap.

Make the fire run first, as on the page (``RUNS`` any output directory,
``FDS`` the FDS output directory)::

    uv run python run.py --scenario assets/t_junction --fds-dir FDS \\
        --output-sqlite RUNS/tj_fire.sqlite \\
        --output-smoke-history RUNS/tj_fire_smoke.csv \\
        --output-fed-history RUNS/tj_fire_fed.csv \\
        --output-route-history RUNS/tj_fire_routes.csv

then, with the fdsvismap version that has the ASET functions (it only reads
the FDS fields here; do not run simulations in this environment)::

    uv run --with git+https://github.com/FireDynamics/fdsvismap@31dc0b6 \\
        python scripts/docs/first_fds_case_aset.py --data FDS --runs RUNS

Prints every number the page quotes and writes
``site/static/images/first-fds-case/aset_*.png`` and the slider frames
``site/static/images/first-fds-case/signs/t*.webp``.
"""

import argparse
import json
import math
import sqlite3
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib.colors import BoundaryNorm, ListedColormap
from matplotlib.lines import Line2D
from matplotlib.patches import Patch, Polygon, Rectangle
from shapely import contains_xy, wkt

from pyfds_evac import (
    DefaultFedConfig,
    DefaultFedModel,
    ExtinctionField,
    FdsFedField,
    SmokeSpeedConfig,
)
from pyfds_evac.core.fed import default_fic

ROOT = Path(__file__).resolve().parents[2]
ASSET = ROOT / "assets" / "t_junction"
OUT = ROOT / "site" / "static" / "images" / "first-fds-case"

TEXT = "dimgrey"
WALL = "dimgrey"
EXIT = "#33a02c"
FIRE = "#bd0c0c"
SIGN = "#c89b00"
JIN_SIGN_K = (0.3, 1.8)  # Jin's lit-sign data, see Fundamentals > Visibility
OUT_COLOUR = "#4575b4"
INSIDE = "#969696"
NEVER = "#f3e3b5"  # map cells that do not fail within the run
MARKS = {  # criterion -> colour, marker, label on the figures
    "K 0.3": ("#4575b4", "o", "K ≥ 0.3 1/m (10 m, C = 3)"),
    "ISO FEC 0.3": ("#d73027", "D", "ISO FEC ≥ 0.3 (HCl ≥ 300 ppm)"),
    "FED 0.3": ("#1a1a1a", "s", "FED ≥ 0.3 (FDS+Evac form)"),
}
FPS = 10.0
T_END = 300.0
T_CSV_END = 299.0  # last second the per-agent histories record
SLICE_Z = 2.0
BURNER = (24.0, 10.5, 2.0, 1.0)

# HCl is the only irritant of this deck (asserted in ``records``), so
# HCl [ppm] = F_FIC,HCl * FIC with the SFPE denominator the engine uses.
F_FIC_HCL_PPM = 900.0
CT_HCL_PPM_MIN = 114000.0  # Purser lethal dose, the FLD_irr term of the FED
K_10M = 3.0 / 10.0  # 10 m with C = 3 (Jin, reflecting sign; FDS default)

# Criterion -> test on a table with columns k, hcl, co, fed.
CRITERIA = {
    "K 0.3": lambda d: d.k >= K_10M,
    "FIC_imp 1": lambda d: d.hcl >= 200.0,  # Purser escape impairment
    "ISO FEC 0.3": lambda d: d.hcl >= 300.0,
    "SFPE FIC 1": lambda d: d.hcl >= 900.0,
    "ISO FEC 1": lambda d: d.hcl >= 1000.0,
    "CO 2700": lambda d: d.co >= 2700.0,  # EA short exposure
    "FED 0.3": lambda d: d.fed >= 0.3,
    "FED 1": lambda d: d.fed >= 1.0,
}
SENSITIVITY_K = (0.23, 0.6, 0.8, 1.0)

LOCATIONS = {
    "exit B": (29.0, 11.5),
    "junction": (18.5, 11.5),
    "left corridor": (10.0, 11.5),
    "spawn centre": (20.0, 4.5),
    "branch mouth": (20.0, 9.0),
    "exit A": (1.0, 11.5),
}
# Routes of the scenario (spawn -> junction -> exit) and the signs on them.
ROUTES = {
    "to A": ([(20, 4.5), (20, 9), (18.5, 11.5), (1, 11.5)], "exit_A_left"),
    "to B": ([(20, 4.5), (20, 9), (20, 11.5), (29, 11.5)], "exit_B_right"),
}
JUNCTION_SIGN = "jps-checkpoints_0"
MAX_VIS_M = 30.0
SLIDER_TIMES = np.arange(0, 301, 10)


def _style(ax, grid_axis=None):
    if grid_axis is None:
        ax.grid(False)
    else:
        ax.grid(alpha=0.7, linewidth=1, axis=grid_axis)
    ax.tick_params(axis="both", which="both", length=0, labelcolor=TEXT)
    sns.despine(ax=ax, left=True, bottom=True)


def _legend(target, **kwargs):
    return target.legend(
        frameon=True,
        facecolor="white",
        framealpha=0.8,
        edgecolor="lightgrey",
        labelcolor=TEXT,
        **kwargs,
    )


def _save(fig, name, **kwargs):
    path = OUT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor="white", **kwargs)
    plt.close(fig)
    print(f"wrote {path.relative_to(ROOT)}")


def _plan(ax, walkable, config):
    ax.add_patch(
        Polygon(np.asarray(walkable.exterior.coords), fc="none", ec=WALL, lw=1.2)
    )
    for spec in config["exits"].values():
        xy = np.asarray(spec["coordinates"])
        ax.add_patch(Polygon(xy, fc=EXIT, ec="none", alpha=0.85, zorder=3))
    x, y, w, d = BURNER
    ax.add_patch(Rectangle((x, y), w, d, fc="none", ec=FIRE, lw=1.4, zorder=4))
    ax.set_aspect("equal")
    ax.set_xlim(-0.3, 30.3)
    ax.set_ylim(-0.3, 13.3)
    ax.set_xticks([])
    ax.set_yticks([])


# --- Run outputs ---


def agents(sqlite_path):
    """Spawn and exit time per agent; exit is NaN when censored.

    An agent counts as out only if it left before 299 s, the last second the
    per-agent histories record. The agent that leaves at 299.0 s is therefore
    censored with those still inside at 300 s.
    """
    with sqlite3.connect(sqlite_path) as con:
        fps = float(
            con.execute("select value from metadata where key = 'fps'").fetchone()[0]
        )
        df = pd.read_sql(
            "select id, min(frame) as first, max(frame) as last "
            "from trajectory_data group by id",
            con,
        )
        tracks = pd.read_sql("select frame, id, pos_x, pos_y from trajectory_data", con)
    assert fps == FPS
    last_s = df["last"].to_numpy() / FPS
    people = pd.DataFrame(
        {
            "spawn": df["first"].to_numpy() / FPS,
            "last": last_s,
            "exit": np.where(last_s < T_CSV_END, last_s, np.nan),
        },
        index=pd.Index(df["id"], name="agent_id"),
    )
    return people, tracks


def records(runs):
    """Per agent and second: K, HCl, CO, FED and speed factor."""
    fed = pd.read_csv(runs / "tj_fire_fed.csv")
    smoke = pd.read_csv(runs / "tj_fire_smoke.csv")
    # HCl is the only irritant: no HCN or NOx, and the Purser FLD_irr term
    # equals the FIC term on every row, so no HF, SO2, acrolein or
    # formaldehyde either. HBr shares both denominators with HCl, so this
    # check cannot exclude it; the deck has no bromine species.
    assert (fed[["hcn_ppm", "no_ppm", "no2_ppm"]].to_numpy() == 0).all()
    hcl = F_FIC_HCL_PPM * fed.fic
    assert np.allclose(hcl, CT_HCL_PPM_MIN * fed.fld_rate_per_min, atol=1e-6)
    merged = fed.assign(hcl=hcl).merge(
        smoke[["time_s", "agent_id", "extinction_per_m"]],
        on=["time_s", "agent_id"],
        validate="one_to_one",
    )
    return pd.DataFrame(
        {
            "time_s": merged.time_s,
            "agent_id": merged.agent_id,
            "k": merged.extinction_per_m,
            "hcl": merged.hcl,
            "co": 1e4 * merged.co_percent,
            "fed": merged.fed_cumulative,
            "speed_factor": merged.speed_factor,
            "temperature": merged.temperature_celsius,
        }
    )


def first_crossings(rec, people, criteria):
    """First time [s] each agent meets each criterion while inside."""
    rec = rec.join(people["exit"], on="agent_id")
    rec = rec[~(rec.time_s > rec["exit"])]
    out = pd.DataFrame(index=people.index)
    for key, test in criteria.items():
        out[key] = rec[test(rec)].groupby("agent_id").time_s.min()
    return out


# --- FDS fields ---


def _check_slice_height(fds_dir):
    from fdsreader import Simulation

    sim = Simulation(str(fds_dir))
    for quantity in (
        "SOOT EXTINCTION COEFFICIENT",
        "HYDROGEN CHLORIDE VOLUME FRACTION",
        "CARBON MONOXIDE VOLUME FRACTION",
    ):
        heights = {s.extent.z_start for s in sim.slices.filter_by_quantity(quantity)}
        assert heights == {SLICE_Z}, (quantity, heights)
    return sim


def _series(k_field, fed_model, x, y, times):
    """K, HCl, CO and the dose of someone standing at (x, y) from t = 0."""
    rows, fed = [], 0.0
    for t in times:
        inputs, rate = fed_model.sample_rate(t, x, y)
        rows.append(
            {
                "k": k_field.sample_extinction(t, x, y),
                "hcl": F_FIC_HCL_PPM * default_fic(inputs),
                "co": 1e4 * inputs.co_volume_fraction_percent,
                "fed": fed,
            }
        )
        fed += rate / 60.0
    return pd.DataFrame(rows, index=times)


def _first(d, test):
    hit = test(d)
    return d.index[hit].min() if hit.any() else np.nan


def location_aset(k_field, fed_model, criteria):
    """First time each criterion is met at each fixed point, from ignition."""
    times = np.arange(0.0, T_END + 0.5, 1.0)
    table = {}
    for name, (x, y) in LOCATIONS.items():
        d = _series(k_field, fed_model, x, y, times)
        table[name] = {key: _first(d, test) for key, test in criteria.items()}
    return pd.DataFrame(table).T


def grid_aset(k_field, fed_field, walkable, cell=0.5):
    """Earliest of K >= 0.3 and ISO FEC >= 0.3 on a grid, from ignition."""
    xs = np.arange(cell / 2, 30.0, cell)
    ys = np.arange(cell / 2, 13.0, cell)
    gx, gy = np.meshgrid(xs, ys)
    inside = contains_xy(walkable, gx, gy)
    aset = np.full(gx.shape, np.nan)
    aset[inside] = np.inf
    for t in np.arange(0.0, T_END + 0.5, 1.0):
        rows, cols = np.nonzero(np.isinf(aset))
        for j, i in zip(rows, cols, strict=True):
            x, y = gx[j, i], gy[j, i]
            hcl = fed_field.sample_inputs(t, x, y).hcl_ppm
            if k_field.sample_extinction(t, x, y) >= K_10M or hcl >= 300.0:
                aset[j, i] = t
    return xs, ys, aset, cell


# --- Sign visibility (fdsvismap) ---


def sign_vismap(fds_dir, config):
    from fdsvismap import VisMap

    vis = VisMap()
    vis.read_fds_data(str(fds_dir), fds_slc_height=SLICE_Z)
    vis.set_time_points(np.arange(0.0, T_END + 0.5, 1.0).tolist())
    vis.set_visibility_bounds(0.0, MAX_VIS_M)
    signs = {**config["exits"], **config["checkpoints"]}
    for name, spec in signs.items():
        s = spec["sign"]
        vis.add_sign(name, s["x"], s["y"], s["c"], s["alpha"])
    for route, (points, exit_sign) in ROUTES.items():
        vis.add_route(route, points, signs=[JUNCTION_SIGN, exit_sign])
    vis.compute_all()
    return vis


# --- Numbers the page quotes ---


def _counts(people, cross, key):
    out = people["exit"].notna()
    c = cross[key]
    hit = c.notna()
    beyond = (people["exit"] - c)[out & hit]
    return {
        "reach": int(hit.sum()),
        "first": c.min(),
        "out_clear": int((out & ~hit).sum()),
        "out_after": int((out & hit).sum()),
        "inside_hit": int((~out & hit).sum()),
        "beyond_median": beyond.median(),
        "beyond_max": beyond.max(),
    }


def report(people, tracks, rec, cross, loc, vis):
    out = people["exit"].notna()
    travel = (people["exit"] - people.spawn)[out]
    print(f"agents {len(people)}, spawned last at {people.spawn.max():.0f} s")
    print(
        f"trajectory: {int((people['last'] < T_END).sum())} left before 300 s, "
        f"last exit {people['last'][people['last'] < T_END].max():.1f} s"
    )
    print(
        f"counted out (exit < {T_CSV_END:.0f} s) {out.sum()}, censored {(~out).sum()}"
    )
    print(f"travel time median {travel.median():.1f} s, max {travel.max():.1f} s")
    print(f"temperature column: {sorted(rec.temperature.unique())}")

    print(
        "\nper agent | reach | first | out, never | out after | inside, "
        "reached | beyond: median max"
    )
    for key in CRITERIA:
        c = _counts(people, cross, key)
        print(
            f"  {key:12s} {c['reach']:4d} {c['first']:5.0f} {c['out_clear']:4d} "
            f"{c['out_after']:4d} {c['inside_hit']:4d}      "
            f"{c['beyond_median']:5.0f} {c['beyond_max']:5.0f}"
        )
    fed03 = cross["FED 0.3"].dropna()
    print(
        f"FED 0.3 crossings {fed03.min():.0f}-{fed03.max():.0f} s; "
        f"max FED {rec.fed.max():.3f}; max HCl {rec.hcl.max():.0f} ppm "
        f"(FIC {rec.hcl.max() / F_FIC_HCL_PPM:.1f}); max CO {rec.co.max():.0f} ppm"
    )
    at_fed = rec.merge(fed03.rename("t0"), left_on="agent_id", right_index=True)
    at_fed = at_fed[at_fed.time_s == at_fed.t0]
    print(
        f"FIC of those agents when FED reached 0.3: "
        f"{(at_fed.hcl / F_FIC_HCL_PPM).min():.1f}-"
        f"{(at_fed.hcl / F_FIC_HCL_PPM).max():.1f}"
    )
    late = people.spawn[people.spawn > loc["K 0.3"].max()]
    print(
        f"agents spawned after the last location crossed K 0.3 "
        f"({loc['K 0.3'].max():.0f} s): {len(late)}"
    )

    sens = {f"K {k}": (lambda d, k=k: d.k >= k) for k in SENSITIVITY_K}
    sens_cross = first_crossings(rec, people, sens)
    for k in SENSITIVITY_K:
        c = sens_cross[f"K {k}"]
        diff = (c - cross["K 0.3"]).dropna()
        print(
            f"K {k}: reach {c.notna().sum()}, out after "
            f"{(out & c.notna()).sum()}, changed {(diff != 0).sum()}, "
            f"max shift {diff.abs().max():.0f} s"
        )

    floor_k = lund_floor_k()
    inside_k = rec.k
    after = rec.merge(cross["K 0.3"].rename("t0"), left_on="agent_id", right_index=True)
    after = after[after.time_s >= after.t0]
    print(
        f"\nK per agent-second: median {inside_k.median():.1f}, "
        f"p90 {inside_k.quantile(0.9):.1f}, max {inside_k.max():.1f} 1/m"
    )
    print(
        f"K per agent-second after the agent's own 0.3 crossing: median "
        f"{after.k.median():.1f} 1/m (visibility {3 / after.k.median():.2f} m)"
    )
    print(
        f"agent-seconds at the speed floor {(rec.speed_factor <= 0.1 + 1e-9).mean():.1%}; "
        f"lund reaches the floor at K = {floor_k:.2f} 1/m; "
        f"above 7.4: {(rec.k > 7.4).mean():.1%}; "
        f"above 1.27: {(rec.k > 1.27).mean():.1%}; "
        f"below 0.1 (not in the histogram): {(rec.k < 0.1).sum()} of {len(rec)}"
    )

    print("\nlocation ASET [s from ignition], z = 2.0 m (nan: not in 300 s)")
    print(loc.to_string(float_format=lambda v: f"{v:.0f}"))

    print(
        "\nsign visibility along each route (fdsvismap, c from config.json, "
        f"max_vis {MAX_VIS_M:g} m)"
    )
    for route in ROUTES:
        a = vis.get_route_aset(route)
        print(
            f"  {route}: {len(a)} points, first loss {a.min():.0f} s, "
            f"median {np.median(a):.0f} s, last {a.max():.0f} s"
        )
    spawn = LOCATIONS["spawn centre"]
    lost = [
        t
        for t in vis.vismap_time_points
        if not vis.get_agg_vismap(t)[_cell(vis, *spawn)]
    ]
    print(f"  spawn centre loses sight of every sign at {min(lost):.0f} s")


def _cell(vis, x, y):
    j = int(np.argmin(np.abs(vis.all_y_coords - y)))
    i = int(np.argmin(np.abs(vis.all_x_coords - x)))
    return j, i


def lund_floor_k():
    """K at which the default 'lund' speed law reaches its floor."""
    cfg = SmokeSpeedConfig()
    return (cfg.min_speed_factor - 1.0) * cfg.alpha / cfg.beta


# --- Figures ---


def _aset_cmap():
    bounds = [0, 20, 30, 40, 50, 60, 90, 300, 301]  # last bin: not by 300 s
    colours = sns.cubehelix_palette(len(bounds) - 2, rot=-0.25, light=0.9, dark=0.15)[
        ::-1
    ] + [NEVER]
    return ListedColormap(colours), BoundaryNorm(bounds, len(bounds) - 1), bounds


def fig_map(walkable, config, grid, loc, vis):
    """Where and when each point of the T fails: tenability, sign visibility."""
    xs, ys, aset, cell = grid
    cmap, norm, bounds = _aset_cmap()
    sns.set_theme(font_scale=1.0, style="whitegrid", font="DejaVu Sans")
    fig, (top, bottom) = plt.subplots(2, 1, figsize=(8.5, 8.2), layout="constrained")
    extent = (0, 30, 0, 13)
    shown = np.where(np.isinf(aset), T_END, aset)
    im = top.imshow(
        shown,
        origin="lower",
        extent=extent,
        cmap=cmap,
        norm=norm,
        interpolation="nearest",
    )
    _plan(top, walkable, config)
    for name, (x, y) in LOCATIONS.items():
        t = np.nanmin([loc.loc[name, "K 0.3"], loc.loc[name, "ISO FEC 0.3"]])
        top.plot(x, y, marker="o", ms=5, mfc="white", mec="black", zorder=5)
        dy = -1.1 if y > 10 else 0.0
        dx = 1.4 if y <= 10 else 0.0
        if name == "exit A":
            dx, dy = 1.6, -1.1
        top.annotate(
            f"{t:.0f} s",
            (x + dx, y + dy),
            ha="center",
            va="center",
            fontsize=9,
            fontweight="semibold",
            color="black",
            bbox={
                "boxstyle": "round,pad=0.15",
                "fc": "white",
                "ec": "none",
                "alpha": 0.85,
            },
            zorder=6,
        )
    top.set_title(
        "(a) tenability: first time K ≥ 0.3 1/m or HCl ≥ 300 ppm "
        "(ISO FEC 0.3),\nsomeone standing there from ignition",
        loc="left",
        color=TEXT,
        fontsize=10,
    )

    sign_aset = vis.get_aset_map().astype(float)
    ever = np.zeros_like(sign_aset, dtype=bool)
    for t in (0.0, 1.0, 2.0):
        ever |= vis.get_agg_vismap(t)
    vx, vy = vis.all_x_coords, vis.all_y_coords
    gx, gy = np.meshgrid(vx, vy)
    solid = ~contains_xy(walkable, gx, gy)
    shown = np.ma.masked_where(solid | ~ever, sign_aset)
    x0, x1, y0, y1 = vis._get_domain_extent()
    bottom.imshow(
        shown,
        origin="lower",
        extent=(x0, x1, y0, y1),
        cmap=cmap,
        norm=norm,
        interpolation="nearest",
    )
    blind = ~solid & ~ever
    if blind.any():
        bottom.contourf(
            vx,
            vy,
            blind.astype(float),
            levels=[0.5, 1.5],
            colors="none",
            hatches=["///"],
        )
    _plan(bottom, walkable, config)
    signs = {**config["exits"], **config["checkpoints"]}
    for spec in signs.values():
        s = spec["sign"]
        bottom.plot(
            s["x"], s["y"], marker="D", ms=7, color=SIGN, mec="black", mew=0.6, zorder=6
        )
    for route, (points, _) in ROUTES.items():
        p = np.asarray(points)
        a = vis.get_route_aset(route)
        bottom.plot(
            p[:, 0],
            p[:, 1],
            color="black",
            lw=1.0,
            ls="-" if route == "to A" else "--",
            zorder=5,
        )
        bottom.annotate(
            f"route {route[-1]}: signs lost at\n"
            f"{a.min():.0f}-{a.max():.0f} s, median {np.median(a):.0f} s",
            (4.0 if route == "to A" else 26.0, 7.5),
            ha="center",
            color=TEXT,
            fontsize=9,
        )
    bottom.set_title(
        "(b) wayfinding, not tenability: first time no sign can be "
        "seen (fdsvismap, all three signs)",
        loc="left",
        color=TEXT,
        fontsize=10,
    )
    cb = fig.colorbar(
        im,
        ax=(top, bottom),
        orientation="horizontal",
        fraction=0.04,
        pad=0.02,
        aspect=40,
    )
    cb.set_ticks(
        [*bounds[:-2], 300.5], labels=[str(b) for b in bounds[:-2]] + ["not by 300"]
    )
    cb.set_label("time since ignition [s]", color=TEXT)
    cb.ax.tick_params(length=0, labelcolor=TEXT)
    for spine in cb.ax.spines.values():
        spine.set_visible(False)
    handles = [
        Line2D([], [], marker="D", ls="", color=SIGN, mec="black", label="sign"),
        Line2D([], [], color="black", ls="-", label="route A"),
        Line2D([], [], color="black", ls="--", label="route B"),
        Patch(fc="none", ec=FIRE, lw=1.4, label="burner"),
    ]
    _legend(bottom, handles=handles, loc="lower left", fontsize=8, ncols=1)
    for ax in (top, bottom):
        _style(ax)
    _save(fig, "aset_map.png")


def fig_agents(people, cross):
    """One bar per agent from spawn to exit, with the first crossings on it."""
    order = people.sort_values("spawn").index
    sns.set_theme(font_scale=1.0, style="whitegrid", font="DejaVu Sans")
    fig, ax = plt.subplots(figsize=(8.0, 9.0), layout="constrained")
    for row, agent in enumerate(order):
        spawn, gone = people.loc[agent, ["spawn", "exit"]]
        end = gone if not np.isnan(gone) else T_CSV_END
        colour = OUT_COLOUR if not np.isnan(gone) else INSIDE
        ax.plot(
            [spawn, end],
            [row, row],
            color=colour,
            lw=1.6,
            solid_capstyle="butt",
            zorder=1,
            alpha=0.55,
        )
        k = cross.loc[agent, "K 0.3"]
        if not np.isnan(k):
            ax.plot(
                [k, end],
                [row, row],
                color=colour,
                lw=1.6,
                solid_capstyle="butt",
                zorder=2,
            )
        if np.isnan(gone):
            ax.plot(T_CSV_END, row, marker=">", ms=3, color=INSIDE, zorder=2)
    sizes = {"K 0.3": 10, "ISO FEC 0.3": 22, "FED 0.3": 14}
    for key, (colour, marker, label) in MARKS.items():
        rows = np.arange(len(order))
        t = cross.loc[order, key].to_numpy()
        ax.scatter(
            t,
            rows,
            marker=marker,
            s=sizes[key],
            color=colour,
            lw=0,
            zorder=4 if key == "K 0.3" else 3,
            label=label,
        )
    ax.annotate(
        "from about 50 s, agents spawn\ninto smoke past the visibility\nlimit; HCl ≥ 300 ppm within 3 s",
        (150, 70),
        xytext=(185, 40),
        color=TEXT,
        fontsize=9,
        arrowprops={"arrowstyle": "-", "color": TEXT, "lw": 0.8},
    )
    n_out = people["exit"].notna().sum()
    ax.annotate(
        f"{n_out} counted out\n(exit before 299 s)",
        (60, 8),
        color=OUT_COLOUR,
        fontsize=9,
        fontweight="semibold",
    )
    ax.annotate(
        f"{len(people) - n_out} still inside at 299 s\n(censored)",
        (15, 125),
        color=TEXT,
        fontsize=9,
        fontweight="semibold",
    )
    ax.set_xlim(0, T_END + 6)
    ax.set_ylim(len(order), -1)
    ax.set_yticks([0, 49, 99, 149], ["1", "50", "100", "150"])
    ax.set_xlabel("time since ignition [s]", color=TEXT)
    ax.set_ylabel("agent, in order of spawning", color=TEXT)
    _style(ax, "x")
    handles = [
        Line2D(
            [],
            [],
            color=OUT_COLOUR,
            lw=1.6,
            alpha=0.55,
            label="got out: before K ≥ 0.3",
        ),
        Line2D([], [], color=OUT_COLOUR, lw=1.6, label="got out: after K ≥ 0.3"),
        Line2D(
            [], [], color=INSIDE, lw=1.6, marker=">", ms=4, label="censored at 299 s"
        ),
    ] + [
        Line2D([], [], marker=m, ls="", color=c, label=f"first {lab}")
        for c, m, lab in MARKS.values()
    ]
    _legend(fig, handles=handles, loc="outside lower center", ncols=2, fontsize=9)
    _save(fig, "aset_agents.png")


def fig_extinction(rec):
    """K met per agent-second against the ranges the speed laws rest on."""
    floor_k = lund_floor_k()
    k = rec.k[rec.k >= 0.1]
    sns.set_theme(font_scale=1.0, style="whitegrid", font="DejaVu Sans")
    fig, ax = plt.subplots(figsize=(8.0, 3.8))
    bins = np.logspace(-1, np.log10(60), 50)
    ax.hist(k, bins=bins, color=INSIDE, edgecolor="white", lw=0.4)
    ax.set_xscale("log")
    ymax = ax.get_ylim()[1] * 1.15
    ax.set_ylim(0, ymax)
    ax.axvspan(*JIN_SIGN_K, facecolor=SIGN, alpha=0.18, lw=0, zorder=0)
    ax.annotate(
        "Jin sign\nvisibility\n0.3-1.8",
        (math.sqrt(JIN_SIGN_K[0] * JIN_SIGN_K[1]), ymax * 0.5),
        ha="center",
        va="top",
        color=TEXT,
        fontsize=9,
    )
    for (lo, hi), name, hatch in (
        ((0.30, 1.27), "Purser fit\nto Jin\n0.30-1.27", "//"),
        ((1.9, 7.4), "Frantzich-\nNilsson\n1.9-7.4", "\\\\"),
    ):
        ax.axvspan(
            lo, hi, facecolor="none", hatch=hatch, edgecolor="#4575b4", lw=0, alpha=0.5
        )
        ax.annotate(
            name,
            (math.sqrt(lo * hi), ymax * 0.97),
            ha="center",
            va="top",
            color=TEXT,
            fontsize=9,
        )
    ax.axvline(floor_k, color=FIRE, ls="--", lw=1.2)
    share = (rec.speed_factor <= 0.1 + 1e-9).mean()
    ax.annotate(
        f"speed floor 0.1\nfrom K = {floor_k:.1f}:\n{share:.0%} of all\nagent-seconds",
        (floor_k / 1.15, ymax * 0.45),
        color=FIRE,
        fontsize=9,
        va="center",
        ha="right",
        bbox={"boxstyle": "round,pad=0.2", "fc": "white", "ec": "none"},
    )
    ax.set_xlabel("extinction coefficient K at the agent [1/m], log scale", color=TEXT)
    ax.set_ylabel("agent-seconds", color=TEXT)
    ax.set_xlim(0.1, 60)
    _style(ax, "y")
    _save(fig, "aset_extinction.png")


def slider_frames(vis, walkable, config, tracks):
    """Sign visibility per route at 0, 10, ..., 300 s, with the agents."""
    vx, vy = vis.all_x_coords, vis.all_y_coords
    gx, gy = np.meshgrid(vx, vy)
    solid = ~contains_xy(walkable, gx, gy)
    x0, x1, y0, y1 = vis._get_domain_extent()
    cmap = ListedColormap(["#d9d9d9", "#74add1"])
    sns.set_theme(font_scale=0.9, style="whitegrid", font="DejaVu Sans")
    for t in SLIDER_TIMES:
        fig, axes = plt.subplots(2, 1, figsize=(6.0, 5.6), layout="constrained")
        here = tracks[tracks.frame == int(round(t * FPS))]
        for ax, route in zip(axes, ROUTES, strict=True):
            seen = vis.get_agg_vismap(float(t), route).astype(float)
            ax.imshow(
                np.ma.masked_where(solid, seen),
                origin="lower",
                extent=(x0, x1, y0, y1),
                cmap=cmap,
                vmin=0,
                vmax=1,
                interpolation="nearest",
            )
            _plan(ax, walkable, config)
            for name in (JUNCTION_SIGN, ROUTES[route][1]):
                spec = {**config["exits"], **config["checkpoints"]}[name]["sign"]
                ax.plot(
                    spec["x"],
                    spec["y"],
                    marker="D",
                    ms=6,
                    color=SIGN,
                    mec="black",
                    mew=0.6,
                    zorder=6,
                )
            ax.scatter(here.pos_x, here.pos_y, s=7, color="black", lw=0, zorder=7)
            share = seen[~solid].mean()
            ax.set_title(
                f"signs of route {route[-1]}: seen from {share:.0%} of the floor",
                loc="left",
                color=TEXT,
                fontsize=12,
            )
            _style(ax)
        fig.suptitle(
            f"t = {t:.0f} s after ignition, {len(here)} agents inside",
            x=0.01,
            ha="left",
            color=TEXT,
            fontsize=13,
        )
        handles = [
            Patch(fc="#74add1", label="a sign of the route is visible"),
            Patch(fc="#d9d9d9", label="no sign of the route visible"),
            Line2D([], [], marker="D", ls="", color=SIGN, mec="black", label="sign"),
            Line2D(
                [], [], marker="o", ls="", color="black", ms=4, label="agent (seed 42)"
            ),
        ]
        _legend(fig, handles=handles, loc="outside lower center", ncols=2, fontsize=11)
        _save(fig, f"signs/t{t:03.0f}.webp", pil_kwargs={"quality": 70, "method": 6})


def main():
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--data", required=True, type=Path, help="FDS output directory")
    parser.add_argument("--runs", required=True, type=Path, help="run outputs")
    args = parser.parse_args()

    walkable = wkt.loads((ASSET / "geometry.wkt").read_text())
    config = json.loads((ASSET / "config.json").read_text())
    sim = _check_slice_height(args.data)
    people, tracks = agents(args.runs / "tj_fire.sqlite")
    rec = records(args.runs)
    cross = first_crossings(rec, people, CRITERIA)
    # The deck writes slices at z = 2.0 m only; the 1.6 m default resolves to it.
    k_field = ExtinctionField.from_fds(str(args.data), simulation=sim)
    fed_field = FdsFedField.from_fds(str(args.data), simulation=sim)
    fed_model = DefaultFedModel(fed_field, DefaultFedConfig())
    loc = location_aset(k_field, fed_model, CRITERIA | {"K 1.0": lambda d: d.k >= 1.0})
    vis = sign_vismap(args.data, config)
    report(people, tracks, rec, cross, loc, vis)

    grid = grid_aset(k_field, fed_field, walkable)
    fig_map(walkable, config, grid, loc, vis)
    fig_agents(people, cross)
    fig_extinction(rec)
    slider_frames(vis, walkable, config, tracks)


if __name__ == "__main__":
    main()
