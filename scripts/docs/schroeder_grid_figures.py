"""Grid figures of the Schröder room: the smoke layer and a same-grid perturbation.

Two figures for the Grid block of ``docs/study-schroeder2020.md``, from the
FDS runs only (no evacuation runs). ``DATA`` is the ``schroeder2020-room``
folder of ``scripts/docs/schroeder_room_maps.py``::

    uv run python scripts/docs/schroeder_grid_figures.py --data DATA

* ``grid_layer.png``: the smoke-layer interface at the three FDS device trees
  (from temperature, FDS User's Guide Eq. 22.25 on the tree, and from K), and
  the largest K at 2.0 m in the 0.6 m square around each tree, for the
  one-door 0.2 m and 0.1 m runs and the two-door run.
* ``grid_perturbation.png``: the K ≥ 0.23 1/m ASET map of the one-door room
  with HRRPUA raised by 0.1 % on the same 0.2 m grid (``hrr060_1door_pert``),
  against the change from the 0.2 m to the 0.1 m grid. The maps use the same
  cells, rule and slices as the page (``cell_aset`` of
  ``schroeder_room_maps.py``).

``--cache`` reuses the node first-crossing caches of the map script
(``RUNS/cache``); without it they are computed into a temporary folder.
Writes to ``site/static/images/studies/schroeder2020/``.
"""

import argparse
import logging
import re
import sys
import tempfile
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib.lines import Line2D
from shapely import wkt

sys.path.insert(0, str(Path(__file__).resolve().parent))
import schroeder_room_maps as maps  # noqa: E402

TEXT = maps.TEXT
LIMIT = 0.23  # 1/m, the page's headline criterion
LATE = 120.0  # s, the paper's fill time; "late" nodes exceed only after it
Z_TREE = np.linspace(0.2, 2.8, 14)  # the 14 points of every tree
TREES = (
    ("W", (5.1, 5.1), "about 6 m from the fire"),
    ("C", (15.1, 5.1), "mid-room"),
    ("E", (25.1, 8.9), "5 m from the door"),
)
PAL = sns.cubehelix_palette(6, rot=-0.25, light=0.7)
LAYER_RUNS = (  # FDS run, label, colour, line style, marker
    ("hrr060_1door", "1 door, 0.2 m", PAL[5], "-", "o"),
    ("hrr060_2door", "2 doors, 0.2 m", PAL[2], "--", "s"),
    ("hrr060_1door_dx010", "1 door, 0.1 m", "#d73027", "-", "D"),
)
T_SHOW = 300.0  # s shown on the layer figure; the room is empty by 125 s


# --- Smoke layer at the device trees ---------------------------------------


def layer_height(temp_k, z=Z_TREE, height=3.0):
    """FDS User's Guide Eq. 22.25 on one tree profile, ends held constant."""
    zz = np.concatenate([[0.0], z, [height]])
    tt = np.concatenate([[temp_k[0]], temp_k, [temp_k[-1]]])
    i1 = np.trapezoid(tt, zz)
    i2 = np.trapezoid(1.0 / tt, zz)
    tl = tt[0]
    return tl * (i1 * i2 - height**2) / (i1 + i2 * tl**2 - 2 * tl * height)


def k_level(prof, frac, z=Z_TREE):
    """Height where K falls below frac × its column maximum, from the ceiling."""
    thr = frac * prof.max()
    below = np.flatnonzero((prof[:-1] < thr) & (prof[1:] >= thr))
    if below.size == 0:
        return z[0]
    i = below[-1]
    return z[i] + (thr - prof[i]) / (prof[i + 1] - prof[i]) * (z[i + 1] - z[i])


def smooth(values):
    """10 s centred mean, as in the grid note."""
    return pd.Series(values).rolling(10, center=True, min_periods=5).mean()


def k_slice(fds_dir):
    """Times, x, y and K (t, ny, nx) of the z = 2.0 m slice."""
    import fdsreader

    logging.disable(logging.WARNING)
    sim = fdsreader.Simulation(str(fds_dir))
    sl = next(
        s
        for s in sim.slices
        if s.quantity.name == maps.QUANTITIES["K"]
        and s.orientation == 3
        and abs((s.extent.z_start + s.extent.z_end) / 2 - maps.Z) < 0.06
    )
    data, coords = sl.to_global(return_coordinates=True)
    logging.disable(logging.NOTSET)
    return np.asarray(sl.times), coords["x"], coords["y"], np.transpose(data, (0, 2, 1))


def tree_series(dev, sl, tree, where):
    """Interface heights and the cell K near one tree, NaN where unstratified."""
    temp = dev[[f"T_tree_{tree}-{i}" for i in range(1, 15)]].to_numpy() + 273.15
    kk = dev[[f"K_tree_{tree}-{i}" for i in range(1, 15)]].to_numpy()
    strat = (temp[:, -1] - temp[:, 0] > 1.0) & (kk[:, -1] > 0.1)
    z_t = [layer_height(t) if s else np.nan for t, s in zip(temp, strat)]
    z_k = {
        f: [k_level(k, f) if s else np.nan for k, s in zip(kk, strat)]
        for f in (0.5, 0.1)
    }
    t, xs, ys, k = sl
    bx = np.abs(xs - where[0]) <= maps.CELL / 2 + 1e-3
    by = np.abs(ys - where[1]) <= maps.CELL / 2 + 1e-3
    kbox = k[:, by][:, :, bx].max(axis=(1, 2))
    return {
        "t_dev": dev["Time"].to_numpy(),
        "z_t": smooth(z_t),
        "z_k50": smooth(z_k[0.5]),
        "z_k10": smooth(z_k[0.1]),
        "t_k": t,
        "k": kbox,
    }


def first_crossing(t, k):
    hit = np.flatnonzero(k >= LIMIT)
    return (t[hit[0]], LIMIT) if hit.size else None


def below_gap(t, k):
    """First interval after the first crossing where K is back below LIMIT."""
    hit = np.flatnonzero(k >= LIMIT)
    if hit.size == 0:
        return None
    drop = np.flatnonzero((k < LIMIT) & (np.arange(k.size) > hit[0]))
    if drop.size == 0:
        return None
    back = np.flatnonzero((k >= LIMIT) & (np.arange(k.size) > drop[0]))
    return t[drop[0]], (t[back[0]] if back.size else None)


def layer_report(label, tree, s):
    """One line of the numbers the page quotes for one run and tree."""
    hit = first_crossing(s["t_k"], s["k"])
    first = f"{hit[0]:.0f} s" if hit else "not by the end"
    z_t = np.asarray(s["z_t"])
    above = np.flatnonzero(np.nan_to_num(z_t, nan=-1.0) >= 2.0)
    until = f"{s['t_dev'][above[-1]]:.0f} s" if above.size else "never"
    gap = below_gap(s["t_k"], s["k"])
    gap_txt = (
        "none"
        if gap is None
        else f"{gap[0]:.0f} s to {'the end' if gap[1] is None else f'{gap[1]:.0f} s'}"
    )
    return (
        f"- {label}, tree {tree}: first K ≥ {LIMIT} at 2.0 m {first}; back below "
        f"the limit {gap_txt}; T interface last at or above 2.0 m at {until}"
    )


def draw_tree(axes, s, style):
    _, label, colour, ls, marker = style
    axes[0].plot(s["t_dev"], s["z_t"], color=colour, ls=ls, lw=1.6, label=label)
    axes[1].plot(s["t_dev"], s["z_k50"], color=colour, ls=ls, lw=1.6)
    axes[1].plot(s["t_dev"], s["z_k10"], color=colour, ls=ls, lw=0.8, alpha=0.7)
    axes[2].plot(s["t_k"], s["k"], color=colour, ls=ls, lw=1.0)
    hit = first_crossing(s["t_k"], s["k"])
    if hit:
        axes[2].plot(*hit, marker=marker, color=colour, ms=8, mec="white", zorder=5)
    return hit


def style_layer_axes(axes, k_top):
    for ax in axes[:2].flat:
        ax.axhspan(1.9, 2.1, color="lightgrey", alpha=0.5, lw=0, zorder=0)
        ax.set_ylim(0.0, 3.0)
    for ax in axes[2]:
        ax.axhline(LIMIT, color=TEXT, lw=0.8, ls=":")
        ax.set_ylim(0.0, k_top)
        ax.set_yticks([0, LIMIT, 0.5, 1.0, 1.5, 2.0][: 2 + int(k_top // 0.5)])
        ax.set_xlabel("time since ignition [s]", color=TEXT)
    for ax in axes.flat:
        ax.set_xlim(0, T_SHOW)
        ax.grid(False)
        ax.tick_params(axis="both", which="both", length=0, labelcolor=TEXT)
    sns.despine(left=True, bottom=True)
    for ax in axes.flat:
        ax.patch.set_edgecolor("lightgrey")
        ax.patch.set_linewidth(0.8)
    axes[0, 0].set_ylabel("interface from T [m]\n(FDS UG Eq. 22.25)", color=TEXT)
    axes[1, 0].set_ylabel("interface from K [m]\n50 % (thick), 10 % (thin)", color=TEXT)
    axes[2, 0].set_ylabel(
        "max K at 2.0 m in the 0.6 m\nsquare around the tree [1/m]", color=TEXT
    )


def fig_layer(data):
    sns.set_theme(font_scale=1.0, style="whitegrid", font="DejaVu Sans")
    fig, axes = plt.subplots(
        3, 3, figsize=(14, 10.5), sharex=True, layout="constrained"
    )
    k_top = 0.0
    lines = []
    for style in LAYER_RUNS:
        dev = pd.read_csv(data / style[0] / f"{style[0]}_devc.csv", skiprows=1)
        sl = k_slice(data / style[0])
        for col, (tree, where, _) in enumerate(TREES):
            s = tree_series(dev, sl, tree, where)
            keep = s["t_k"] <= T_SHOW
            k_top = max(k_top, float(np.percentile(s["k"][keep], 95)))
            draw_tree(axes[:, col], s, style)
            lines.append(layer_report(style[1], tree, s))
    for col, (tree, where, note) in enumerate(TREES):
        maps._title(axes[0, col], "abc"[col], f"tree {tree} at {where} m, {note}")
    style_layer_axes(axes, min(2.0, 0.5 * np.ceil(k_top / 0.5)))
    axes[0, 0].annotate(
        "the 2.0 m slice lies in this band\n(cell centres 1.9 and 2.1 m, 0.2 m grid)",
        (200, 2.0),
        xytext=(120, 0.35),
        color=TEXT,
        fontsize=9,
        arrowprops={"arrowstyle": "-", "color": "lightgrey"},
    )
    handles = [
        Line2D([], [], color=c, ls=ls, marker=m, mec="white", label=lab)
        for _, lab, c, ls, m in LAYER_RUNS
    ]
    handles.append(
        Line2D(
            [], [], color=TEXT, ls=":", lw=0.8, label=f"K = {LIMIT} 1/m (ASET limit)"
        )
    )
    maps._legend(axes[0, 2], handles=handles, loc="upper right", fontsize=8)
    maps._stamp(
        fig,
        "Tree points every 0.2 m on both grids. Interface only where the tree is "
        "stratified (T(2.8 m) − T(0.2 m) > 1 K and K(2.8 m) > 0.1 1/m), 10 s centred "
        "mean; Eq. 22.25 evaluated on the tree, not the FDS LAYER HEIGHT device. "
        "Markers: first K ≥ 0.23 1/m.",
    )
    maps._save(fig, "grid_layer.png")
    print("\n".join(lines))


# --- Same-grid perturbation --------------------------------------------------


def hrrpua(fds_dir):
    deck = (fds_dir / f"{fds_dir.name}.fds").read_text()
    return float(re.search(r"ID='FIRE', HRRPUA=([\d.]+)", deck).group(1))


def late_nodes(fire, step):
    """Node coordinates with ASET > LATE s, on the 0.2 m node lattice."""
    node = fire.node["K 0.23"][::step, ::step]
    jj, ii = np.nonzero(np.isfinite(node) & (node > LATE))
    return fire.xs[::step][ii], fire.ys[::step][jj]


def diff_panel(ax, grid, walkable, exits, d, letter, text):
    lim = 60
    im = maps._mesh(ax, grid, np.clip(d, -lim, lim), cmap="RdBu", vmin=-lim, vmax=lim)
    maps._hatch(ax, grid, np.abs(d) > 30, "///")
    maps._plan(ax, walkable, exits)
    big = np.nanmean(np.abs(d[np.isfinite(d)]) > 30)
    maps._title(
        ax,
        letter,
        f"{text}\nmean |Δ| {np.nanmean(np.abs(d)):.1f} s, |Δ| > 30 s in "
        f"{big:.1%} of cells, max |Δ| {np.nanmax(np.abs(d)):.0f} s",
    )
    return im


def late_panel(ax, fires, walkable, exits):
    styles = (
        ("fine", "0.1 m grid (every 2nd node)", "s", "#bdbdbd", 12, 2),
        ("base", "0.2 m grid", "o", maps.CAPPED, 26, 1),
        ("pert", "0.2 m grid, +0.1 % HRRPUA", "x", maps.UNCAPPED, 26, 1),
    )
    for key, label, marker, colour, size, step in styles:
        x, y = late_nodes(fires[key], step)
        ax.scatter(
            x,
            y,
            marker=marker,
            c=colour,
            s=size,
            lw=1.0,
            zorder=6,
            label=f"{label}: {x.size} nodes",
        )
    maps._plan(ax, walkable, exits)
    maps._title(ax, "c", f"nodes first exceeding K ≥ {LIMIT} 1/m after {LATE:.0f} s")
    maps._legend(ax, loc="lower right", fontsize=8)


def ecdf_panel(ax, pairs):
    for d, label, colour, ls in pairs:
        v = np.sort(np.abs(d[np.isfinite(d)]))
        ax.plot(
            v,
            np.arange(1, v.size + 1) / v.size,
            color=colour,
            ls=ls,
            lw=1.8,
            label=label,
        )
    ax.axvline(30, color="lightgrey", lw=0.8, zorder=0)
    ax.set_xscale("symlog", linthresh=1)
    ax.set_xlim(0, 300)
    ax.set_ylim(0, 1.02)
    ax.set_xlabel("|Δ ASET| per map cell [s]", color=TEXT, fontsize=9)
    ax.set_ylabel("share of cells", color=TEXT, fontsize=9)
    ax.grid(False)
    ax.tick_params(axis="both", which="both", length=0, labelcolor=TEXT, labelsize=8)
    sns.despine(ax=ax, left=True, bottom=True)
    ax.patch.set_edgecolor("lightgrey")
    ax.patch.set_linewidth(0.8)
    maps._title(ax, "d", "cells within a given |Δ|; grey line at 30 s")
    maps._legend(ax, loc="lower right", fontsize=8)


def fig_perturbation(data, cache):
    walkable = wkt.loads((data / "hrr060_1door" / "geometry.wkt").read_text())
    exits = maps.load_layouts(data)[1]["1door"]
    grid = maps.make_grid(walkable)
    runs = {
        "base": "hrr060_1door",
        "pert": "hrr060_1door_pert",
        "fine": "hrr060_1door_dx010",
    }
    fires = {k: maps.fire_fields(data / v, cache) for k, v in runs.items()}
    aset = {k: maps.cell_aset(f.node["K 0.23"], f, grid) for k, f in fires.items()}
    q0, q1 = hrrpua(data / runs["base"]), hrrpua(data / runs["pert"])
    d_pert = aset["pert"] - aset["base"]
    d_grid = aset["fine"] - aset["base"]
    fig, axes = maps._panel_grid(2, (13, 6.8))
    im = diff_panel(
        axes[0],
        grid,
        walkable,
        exits,
        d_pert,
        "a",
        f"same 0.2 m grid, HRRPUA {q1:g} minus {q0:g} kW/m² (+{q1 / q0 - 1:.1%})",
    )
    diff_panel(axes[1], grid, walkable, exits, d_grid, "b", "0.1 m minus 0.2 m grid")
    late_panel(axes[2], fires, walkable, exits)
    ecdf_panel(
        axes[3],
        (
            (d_pert, "+0.1 % HRRPUA, same grid", maps.UNCAPPED, "-"),
            (d_grid, "0.1 m against 0.2 m grid", maps.CAPPED, "--"),
        ),
    )
    cb = fig.colorbar(
        im, ax=axes[:2], location="bottom", shrink=0.6, aspect=50, extend="both"
    )
    cb.set_label(
        "Δ ASET [s], red = earlier than the 0.2 m base; hatched: |Δ| > 30 s", color=TEXT
    )
    cb.ax.tick_params(length=0, labelcolor=TEXT)
    cb.outline.set_visible(False)
    maps._suptitle(
        fig,
        "One door, K ≥ 0.23 1/m at 2.0 m: a tiny change of the fire "
        "moves ASET far less than the grid does",
    )
    maps._stamp(
        fig,
        "∃ rule, 0.6 m cells, slices every ~1 s, clock from ignition. "
        "Late nodes on the 0.2 m node lattice. Burner red, exit green.",
    )
    maps._save(fig, "grid_perturbation.png")
    for key, d in (("+0.1 % HRRPUA", d_pert), ("0.1 m grid", d_grid)):
        ok = np.abs(d[np.isfinite(d)])
        print(
            f"- {key}: mean |Δ| {ok.mean():.1f} s, 90th pct {np.percentile(ok, 90):.0f} s,"
            f" |Δ| > 30 s in {np.mean(ok > 30):.1%} ({int((ok > 30).sum())} cells),"
            f" max {ok.max():.0f} s"
        )
    for key, step in (("base", 1), ("pert", 1), ("fine", 2)):
        x, _ = late_nodes(fires[key], step)
        print(
            f"- late nodes (> {LATE:.0f} s), {key}: {x.size}, x from {x.min():.1f}"
            f" to {x.max():.1f} m"
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--data", type=Path, required=True, help="schroeder2020-room folder"
    )
    parser.add_argument(
        "--cache", type=Path, help="map-script cache folder (RUNS/cache)"
    )
    opts = parser.parse_args()
    data = opts.data.resolve()
    fig_layer(data)
    if opts.cache:
        fig_perturbation(data, opts.cache.resolve())
        return
    with tempfile.TemporaryDirectory() as tmp:
        fig_perturbation(data, Path(tmp))


if __name__ == "__main__":
    main()
