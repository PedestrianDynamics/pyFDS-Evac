"""Route choice in smoke after Schröder et al. (2015): geometry and fire figures.

Geometry after B. Schröder, D. Haensel, M. Chraibi, L. Arnold, A. Seyfried,
E. Andresen, "Knowledge- and perception-based route choice modelling in case
of fire", Proc. 6th Int. Symp. Human Behaviour in Fire (2015), pp. 327-338,
Fig. 6 (p. 335), https://juser.fz-juelich.de/record/255940. No data from
the authors is used, and no figure of the paper is redrawn: the smoke target
below is our reading of Fig. 6c in words, fixed before any FDS run was
scored.

``DATA`` is the study folder with the finished FDS runs of the nine fire
variants ``a0NN_<fuel>_hNN/`` (decks from
``assets/schroeder2015_route/make_decks.py``). Run from the repository
root::

    uv run python scripts/docs/schroeder2015_fire_figures.py --data DATA

It prints the geometry, fire, pre-movement and fire-choice numbers of the
page as Markdown tables and writes ``geometry.png``, ``fire_field.png``,
``p0b_sweep.png`` and ``p0b_hall_diag.png`` to
``site/static/images/studies/schroeder2015/``.

Fire choice (P0b). The 2.8 m extinction slice at 165 s is scored against
five regions, each inset by one 0.2 m cell; the region score is the share of
nodes meeting the condition and the variant score S is the mean of the
five. Room 3 K >= 2.3, upper corridor K >= 2.3, lower corridor K <= 0.23,
lower hall 0.7 <= K <= 1.4, upper hall K <= 0.23 (1/m). Hall diagnosis,
post hoc: the flow direction is inferred from the order in which the device
trees first exceed K = 0.23 1/m; no flux is measured.
"""

import argparse
import importlib.util
import math
import re
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import fdsreader
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib.colors import BoundaryNorm
from matplotlib.patches import Rectangle
from scipy import stats
from shapely import box, unary_union

fdsreader.settings.ENABLE_CACHING = False

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "assets" / "schroeder2015_route"
OUT = ROOT / "site" / "static" / "images" / "studies" / "schroeder2015"
P1_FIRES = ["a047_pvc_h40", "a047_pvc_h35", "a012_pvc_h30"]
VARIANTS = [
    "a047_pvc_h30",
    "a047_pvc_h35",
    "a047_pvc_h40",
    "a047_pur_h30",
    "a047_pur_h40",
    "a012_pvc_h30",
    "a012_pvc_h40",
    "a012_pur_h30",
    "a012_pur_h40",
]
# name: (x0, x1, y0, y1) before the inset, condition (lo, hi) in 1/m
REGIONS = {
    "Room 3": ((0.2, 10.6, 24.2, 31.0), (2.3, np.inf)),
    "Upper corridor": ((-5.0, 0.0, 24.2, 35.0), (2.3, np.inf)),
    "Lower corridor": ((-5.0, 0.0, -10.0, 0.0), (0.0, 0.23)),
    "Room 1 lower": ((0.2, 10.6, 0.0, 12.0), (0.7, 1.4)),
    "Room 1 upper": ((0.2, 10.6, 12.0, 24.0), (0.0, 0.23)),
}
SHORT = dict(zip(REGIONS, ("R3", "UC", "LC", "1L", "1U")))
REGION_EDGE = {
    "Room 3": ("#d73027", "-"),
    "Upper corridor": ("#d73027", "--"),
    "Lower corridor": ("#4575b4", "-"),
    "Room 1 lower": ("#fc8d59", "-"),
    "Room 1 upper": ("#4575b4", "--"),
}
INSET = 0.2
T_SNAP, T_WIN = 165.0, (160.0, 170.0)
K_ON = 0.23
LEVELS = [0, 0.23, 0.7, 1.4, 2.3, 1e3]
LEGEND = dict(
    frameon=True,
    facecolor="white",
    framealpha=0.8,
    edgecolor="lightgrey",
    labelcolor="dimgrey",
)
HALL_TREES = {
    "doorB_h": 21.7,
    "hall_hi": 18.1,
    "hall_mid": 12.1,
    "hall_lo": 6.1,
    "doorA_h": 1.7,
}


def _load(name):
    """Import a module of assets/schroeder2015_route; the generators import
    ``geometry`` by its bare name, so it is registered under that name."""
    path = ASSETS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def md_table(header, rows):
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    print("\n".join(lines) + "\n")


def heading(text):
    print(f"\n### {text}\n")


def style(ax):
    ax.grid(False)
    ax.tick_params(axis="both", which="both", length=0, labelcolor="dimgrey")
    ax.patch.set_edgecolor("lightgrey")
    ax.patch.set_linewidth(0.8)


def save(fig, name):
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / f"{name}.png", dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"wrote {OUT / name}.png")


# --- Setup numbers -----------------------------------------------------------


def report_setup(geo, decks):
    heading("Geometry")
    rooms = unary_union([box(*geo.CORRIDOR), box(*geo.HALL), box(*geo.ROOM3)]).area
    x0, y0, x1, y1 = geo.CORRIDOR
    meshed = (x1 - x0) * (y1 - y0) + geo.HALL[2] * geo.ROOM3[3]
    md_table(
        ["Quantity", "Value"],
        [
            ["floor meshed in FDS", f"{meshed:.0f} m²"],
            ["floor inside the walls (corridor, hall, Room 3)", f"{rooms:.0f} m²"],
            ["walkable area", f"{geo.walkable().area:.0f} m²"],
            ["hall interior width", f"{geo.HALL[2] - geo.HALL[0]:.1f} m"],
        ],
    )
    heading("Fire")
    rows = []
    for name in P1_FIRES:
        v = decks.variants()[name]
        _, dz = decks.meshes(0.2, v["h"])
        tau = math.sqrt(decks.Q_MAX / v["alpha"])
        rows.append(
            [
                name,
                v["alpha"],
                v["fuel"],
                v["h"],
                f"{decks.Q_MAX:.0f} kW",
                f"{tau:.1f} s",
                f"{dz:.4f} m",
            ]
        )
    md_table(["Fire", "α [kW/s²]", "fuel", "H [m]", "cap", "TAU_Q", "dz"], rows)


def report_premovement():
    """Each supported family with mean 120 s, SD 60 s against N(120, 60) cut at 0."""
    heading("Pre-movement families against N(120, 60) s truncated at 0")
    ref = stats.truncnorm(-2.0, np.inf, loc=120, scale=60)
    families = {
        "weibull a = 135.49, b = 2.101": stats.weibull_min(2.101, scale=135.49),
        "gamma a = 4, b = 30": stats.gamma(4, scale=30),
        "uniform a = 16.1, b = 223.9": stats.uniform(16.1, 223.9 - 16.1),
        "lognormal a = 4.676, b = 0.472": stats.lognorm(0.472, scale=np.exp(4.676)),
    }
    below = stats.norm(120, 60).cdf(0)
    print(f"N(120, 60) s below 0 s: {100 * below:.1f} %\n")
    t = np.linspace(0, 1500, 300001)
    dt = t[1] - t[0]
    rows = []
    for name, d in families.items():
        diff = np.abs(d.cdf(t) - ref.cdf(t))
        rows.append(
            [
                name,
                f"{d.mean():.1f} / {d.std():.1f}",
                f"{diff.max():.3f}",
                f"{diff.sum() * dt:.1f}",
                f"{d.ppf(0.99):.0f}",
                f"{d.sf(300):.3f}",
            ]
        )
    rows.append(["reference", "", "", "", f"{ref.ppf(0.99):.0f}", f"{ref.sf(300):.3f}"])
    md_table(
        [
            "Family",
            "mean / SD [s]",
            "KS distance",
            "W1 [s]",
            "99th pct [s]",
            "P(t > 300 s)",
        ],
        rows,
    )


# --- FDS fields --------------------------------------------------------------


def ext_slices(sim):
    sl = [
        s
        for s in sim.slices
        if s.quantity.name == "SOOT EXTINCTION COEFFICIENT" and s.orientation == 3
    ]
    return sorted(sl, key=lambda s: s.extent.z_start)


def field(sl, t):
    g, c = sl.to_global(masked=True, fill=np.nan, return_coordinates=True)
    times = np.asarray(sl.times)
    i = int(np.argmin(np.abs(times - t)))
    return g, times, i, c["x"], c["y"], float(c["z"][0])


def region_mask(x, y, b):
    x0, x1, y0, y1 = b
    X, Y = np.meshgrid(x, y, indexing="ij")
    return (
        (X >= x0 + INSET - 1e-6)
        & (X <= x1 - INSET + 1e-6)
        & (Y >= y0 + INSET - 1e-6)
        & (Y <= y1 - INSET + 1e-6)
    )


def score(K, x, y):
    out = {}
    for name, (b, (lo, hi)) in REGIONS.items():
        v = K[region_mask(x, y, b)]
        v = v[np.isfinite(v)]
        out[f"{name} frac"] = float(np.mean((v >= lo) & (v <= hi)))
        out[f"{name} median"] = float(np.median(v))
    out["score"] = float(np.mean([out[f"{n} frac"] for n in REGIONS]))
    return out


def load_sweep(data):
    rows, snaps = [], {}
    for v in VARIANTS:
        sim = fdsreader.Simulation(str(data / v))
        for sl in ext_slices(sim):
            g, t, i, x, y, z = field(sl, T_SNAP)
            w = (t >= T_WIN[0]) & (t <= T_WIN[1])
            row = {"variant": v, "z": round(z, 2)}
            row |= {f"snap {k}": val for k, val in score(g[i], x, y).items()}
            row |= {
                f"win {k}": val for k, val in score(np.nanmean(g[w], 0), x, y).items()
            }
            rows.append(row)
            if z > 2.5:
                snaps[v] = (g[i], x, y, z)
    return pd.DataFrame(rows), snaps


def report_sweep(df):
    heading("Fire choice: score S at 2.8 m, 165 s")
    top = df[df.z > 2.5]
    rows = []
    for _, r in top.iterrows():
        rows.append(
            [
                r.variant,
                f"{r.z:.2f} m",
                f"{r['snap score']:.2f}",
                f"{r['win score']:.2f}",
                *[f"{r[f'snap {n} frac']:.2f}" for n in REGIONS],
                " / ".join(f"{r[f'snap {n} median']:.2g}" for n in list(REGIONS)[1:]),
            ]
        )
    md_table(
        [
            "Variant",
            "slice",
            "S (165 s)",
            "S (160–170 s)",
            *SHORT.values(),
            "median K UC / LC / 1L / 1U",
        ],
        rows,
    )
    null = np.mean([1, 0, 1, 0, 1])
    print(f"null field (Room 3 opaque, everything else clear): S = {null:.2f}")
    print("slice heights by ceiling:", sorted(set(zip(df.variant.str[-3:], df.z))))


# --- Hall diagnosis ----------------------------------------------------------


def tree_z(deck):
    m = re.search(
        r"K_hall_lo'.*XBP=[^,]+,[^,]+,[^,]+,[^,]+,([\d.]+),([\d.]+), POINTS=(\d+)",
        deck.read_text(),
    )
    return np.linspace(float(m[1]), float(m[2]), int(m[3]))


def devices(data, v):
    """Layer depth on the hall trees at 165 s and arrival times near 2.8 m."""
    z = tree_z(data / v / f"{v}.fds")
    H = float(v[-2:]) / 10
    d = pd.read_csv(data / v / f"{v}_devc.csv", skiprows=1)
    i = int(np.argmin(np.abs(d.Time.values - T_SNAP)))
    k28 = int(np.argmin(np.abs(z - 2.8)))
    rows = []
    for dev, y in HALL_TREES.items():
        K = np.array([d[f"K_{dev}-{k + 1}"].iloc[i] for k in range(len(z))])
        on = np.where(K > K_ON)[0]
        zi = z[on.min()] if on.size else H
        rows.append({"variant": v, "device": dev, "y": y, "depth": H - zi})
    arr = {}
    for dev in ("doorA_h", "doorA_c", "doorB_h", "doorB_c"):
        K = d[f"K_{dev}-{k28 + 1}"].values
        j = int(np.argmax(K > K_ON))
        arr[dev] = d.Time.values[j] if K[j] > K_ON else np.nan
    return rows, arr


def arrival_map(data, v):
    sim = fdsreader.Simulation(str(data / v))
    sl = ext_slices(sim)[-1]
    g, c = sl.to_global(masked=True, fill=np.nan, return_coordinates=True)
    t = np.asarray(sl.times)
    hit = np.nan_to_num(g) > K_ON
    first = np.where(hit.any(axis=0), t[np.argmax(hit, axis=0)], np.nan)
    first[np.isnan(g[0])] = np.nan
    return first, g[int(np.argmin(np.abs(t - T_SNAP)))], c["x"], c["y"]


def report_hall(depth, arr):
    heading("Hall diagnosis (post hoc, arrival order)")
    lead_a = (arr.doorA_c - arr.doorA_h).dropna()
    lead_b = arr.doorB_c - arr.doorB_h
    fast = depth[depth.variant.str.startswith("a047_pvc")]
    near_c = fast[fast.device.isin(["doorB_h", "hall_hi", "hall_mid"])].depth
    a_end = fast[fast.device == "doorA_h"].depth
    md_table(
        ["Quantity", "Value"],
        [
            [
                "door A: hall side reached first",
                f"{int((lead_a > 0).sum())} of {len(arr)} variants, "
                f"{lead_a.min():.0f}–{lead_a.max():.0f} s earlier",
            ],
            [
                "door B: hall side reached first",
                f"{int((lead_b > 0).sum())} of {len(arr)}",
            ],
            [
                "layer depth at 165 s, PVC α 0.047, from C to mid-hall",
                f"{near_c.min():.1f}–{near_c.max():.1f} m",
            ],
            [
                "layer depth at 165 s, PVC α 0.047, at the A end",
                f"{a_end.min():.1f}–{a_end.max():.1f} m",
            ],
        ],
    )


# --- Figures -----------------------------------------------------------------


def draw_outline(ax, geo, color="black"):
    w = geo.walkable()
    for ring in [w.exterior, *w.interiors]:
        ax.plot(*ring.xy, color=color, lw=0.7)
    x0, y0, x1, y1 = geo.ROOM3
    ax.plot([x0, x1, x1, x0], [y0, y0, y1, y1], color=color, lw=0.7)


def draw_regions(ax):
    for name, (b, _) in REGIONS.items():
        x0, x1, y0, y1 = b
        ec, ls = REGION_EDGE[name]
        ax.add_patch(
            Rectangle(
                (x0 + INSET, y0 + INSET),
                x1 - x0 - 2 * INSET,
                y1 - y0 - 2 * INSET,
                fill=False,
                ec=ec,
                ls=ls,
                lw=1.4,
            )
        )


def region_handles():
    labels = ["K ≥ 2.3", "K ≥ 2.3", "K ≤ 0.23", "0.7 ≤ K ≤ 1.4", "K ≤ 0.23"]
    return [
        plt.Line2D(
            [],
            [],
            color=REGION_EDGE[n][0],
            ls=REGION_EDGE[n][1],
            lw=1.4,
            label=f"{n}: {lab}",
        )
        for n, lab in zip(REGIONS, labels)
    ]


def colorbar_bins(fig, pm, cax):
    """Colour bar with one label per K bin, the top bin open-ended."""
    cb = fig.colorbar(pm, cax=cax)
    centres = [0.5 * (a + b) for a, b in zip(LEVELS[:-1], LEVELS[1:])]
    cb.set_ticks(centres, labels=["< 0.23", "0.23–0.7", "0.7–1.4", "1.4–2.3", "> 2.3"])
    cb.ax.minorticks_off()
    cb.outline.set_edgecolor("lightgrey")
    return cb


def fig_geometry(geo):
    pal = sns.color_palette("colorblind")
    fig, ax = plt.subplots(figsize=(7.5, 9.5))
    w = geo.walkable()
    ax.fill(*w.exterior.xy, color="#e8eef4", zorder=1, label="walkable (pyFDS-Evac)")
    ax.plot(*w.exterior.xy, color=pal[0], lw=1.2, zorder=3)
    for hole in w.interiors:
        ax.fill(*hole.xy, color="dimgrey", zorder=3)
    x0, y0, x1, y1 = geo.ROOM3
    ax.add_patch(
        Rectangle(
            (x0, y0),
            x1 - x0,
            y1 - y0,
            fc="none",
            ec="grey",
            hatch="///",
            lw=0.8,
            zorder=2,
            label="Room 3 (FDS only, not walkable)",
        )
    )
    ax.add_patch(Rectangle((0, 0), geo.WALL, y1, fc="dimgrey", ec="none", zorder=2))
    ax.add_patch(
        Rectangle(
            (0, y0 - geo.WALL),
            geo.HALL[2],
            geo.WALL,
            fc="dimgrey",
            ec="none",
            zorder=2,
            label="wall 0.2 m (FDS)",
        )
    )
    ax.add_patch(
        Rectangle(
            (geo.DOOR_C[0], y0 - geo.WALL),
            geo.DOOR_C[1] - geo.DOOR_C[0],
            geo.WALL,
            fc="white",
            ec="none",
            zorder=3,
        )
    )
    ax.add_patch(
        Rectangle(
            (0, geo.DOOR_D[0]),
            geo.WALL,
            geo.DOOR_D[1] - geo.DOOR_D[0],
            fc="white",
            ec="none",
            zorder=3,
        )
    )
    bx0, bx1, by0, by1 = geo.BURNER_XY
    ax.add_patch(
        Rectangle(
            (bx0, by0),
            bx1 - bx0,
            by1 - by0,
            fc="#d73027",
            ec="none",
            zorder=3,
            label="burner 3 × 2 m",
        )
    )
    ax.plot(
        *zip(*geo.spawn_area()),
        color=pal[4],
        lw=1.2,
        ls=":",
        zorder=3,
        label="start area, 200 agents",
    )
    for name in ("A", "B"):
        ax.fill(*zip(*geo.door_checkpoint(name)), color=pal[1], zorder=4)
    ax.fill([], [], color=pal[1], label="waypoints at doors A, B")
    for name in ("E", "F"):
        ax.fill(*zip(*geo.exit_polygon(name)), color=pal[2], zorder=4)
    ax.fill([], [], color=pal[2], label="exits E, F")
    for k, (sx0, sy0, sx1, sy1) in enumerate(geo.SOURCE.values()):
        ax.add_patch(
            Rectangle(
                (sx0, sy0),
                sx1 - sx0,
                sy1 - sy0,
                fc="none",
                ec="black",
                ls="--",
                lw=1,
                zorder=5,
                label="source outline, digitised ±0.5–1 m" if k == 0 else None,
            )
        )
    labels = {
        "Room 1 (hall)": (5.4, 12),
        "Room 2\n(corridor)": (-2.5, 12),
        "Room 3": (8.8, 30.2),
        "A": (0.9, 1.6),
        "B": (0.9, 21.6),
        "C": (5.4, 23.3),
        "D": (-0.6, 27.6),
        "E": (-0.8, -9.4),
        "F": (-0.8, 34.4),
    }
    for text, (x, y) in labels.items():
        ax.text(
            x, y, text, ha="center", va="center", fontsize=9, color="black", zorder=6
        )
    ax.set_aspect("equal")
    ax.set_xlim(-6, 11.5)
    ax.set_ylim(-11, 36)
    ax.set_xlabel("x [m]", color="dimgrey")
    ax.set_ylabel("y [m]", color="dimgrey")
    style(ax)
    sns.despine(left=True, bottom=True)
    ax.legend(loc="center left", bbox_to_anchor=(1.02, 0.5), fontsize=8.5, **LEGEND)
    save(fig, "geometry")


def fig_fire_field(data, geo):
    cmap = plt.get_cmap("Greys", len(LEVELS) - 1)
    norm = BoundaryNorm(LEVELS, cmap.N)
    fig, axes = plt.subplots(2, 3, figsize=(11, 15.5), sharex=True, sharey=True)
    for j, v in enumerate(P1_FIRES):
        sim = fdsreader.Simulation(str(data / v))
        sl = ext_slices(sim)
        for row, (zn, t) in enumerate([(2.8, 165.0), (1.6, 145.0)]):
            ax = axes[row][j]
            s = min(sl, key=lambda s: abs(s.extent.z_start - zn))
            g, times, i, x, y, z = field(s, t)
            pm = ax.pcolormesh(
                x, y, g[i].T, cmap=cmap, norm=norm, shading="nearest", rasterized=True
            )
            draw_outline(ax, geo, color="#4575b4")
            if row == 0:
                draw_regions(ax)
            label = "(main fire)" if j == 0 else ""
            ax.set_title(
                f"({'abcdef'[3 * row + j]}) {v} {label}\nK at {z:.2f} m, "
                f"{times[i]:.0f} s",
                loc="left",
                fontsize=10,
                color="dimgrey",
            )
            ax.set_aspect("equal")
            ax.set_xlim(-5.4, 11)
            ax.set_ylim(-10.4, 35.4)
            style(ax)
            if row == 1:
                ax.set_xlabel("x [m]", color="dimgrey")
            if j == 0:
                ax.set_ylabel("y [m]", color="dimgrey")
    for lab, (x, y) in {"A": (0.5, 1.6), "B": (0.5, 21.6), "C": (5.4, 23.0)}.items():
        for ax in axes.flat:
            ax.text(
                x,
                y,
                lab,
                color="#4575b4",
                fontsize=9,
                weight="semibold",
                ha="left",
                va="center",
            )
    sns.despine(left=True, bottom=True)
    fig.tight_layout(rect=(0, 0.06, 0.9, 1))
    cax = fig.add_axes([0.915, 0.35, 0.015, 0.3])
    cb = colorbar_bins(fig, pm, cax)
    cb.set_label("soot extinction K [1/m]", color="dimgrey")
    cb.ax.tick_params(length=0, labelcolor="dimgrey")
    fig.legend(
        handles=region_handles(),
        loc="lower center",
        ncol=3,
        fontsize=8.5,
        title="scoring regions of the fire choice (top row)",
        title_fontsize=8.5,
        **LEGEND,
    )
    save(fig, "fire_field")


def fig_sweep(df, snaps):
    top = df[df.z > 2.5].set_index("variant")
    cmap = plt.get_cmap("Greys", len(LEVELS) - 1)
    norm = BoundaryNorm(LEVELS, cmap.N)
    fig, axes = plt.subplots(3, 3, figsize=(11, 16.5), sharex=True, sharey=True)
    for i, v in enumerate(VARIANTS):
        ax = axes.flat[i]
        K, x, y, z = snaps[v]
        pm = ax.pcolormesh(
            x, y, K.T, cmap=cmap, norm=norm, shading="nearest", rasterized=True
        )
        draw_regions(ax)
        r = top.loc[v]
        fr = " ".join(f"{SHORT[n]} {r[f'snap {n} frac']:.2f}" for n in REGIONS)
        ax.set_title(
            f"({chr(97 + i)}) {v}  S = {r['snap score']:.2f}\n{fr}",
            loc="left",
            fontsize=9,
            color="black" if v != "a047_pvc_h40" else "#bd0c0c",
        )
        ax.set_aspect("equal")
        ax.set_xlim(-5.2, 10.8)
        ax.set_ylim(-10.2, 35.2)
        style(ax)
        if i % 3 == 0:
            ax.set_ylabel("y [m]", color="dimgrey")
        if i >= 6:
            ax.set_xlabel("x [m]", color="dimgrey")
    sns.despine(left=True, bottom=True)
    fig.tight_layout(rect=(0, 0.05, 0.9, 1))
    cax = fig.add_axes([0.915, 0.35, 0.015, 0.3])
    cb = colorbar_bins(fig, pm, cax)
    cb.set_label("soot extinction K at 2.8 m, 165 s [1/m]", color="dimgrey")
    cb.ax.tick_params(length=0, labelcolor="dimgrey")
    fig.legend(
        handles=region_handles(), loc="lower center", ncol=3, fontsize=8.5, **LEGEND
    )
    save(fig, "p0b_sweep")


def fig_hall(data, depth, arr, fields):
    group = {
        "a047_pvc": "#d73027",
        "a047_pur": "#fc8d59",
        "a012_pvc": "#4575b4",
        "a012_pur": "#90c1c6",
    }
    dash = {"h30": ":", "h35": "-.", "h40": "-"}
    mark = {"h30": "o", "h35": "s", "h40": "^"}
    fig = plt.figure(figsize=(14, 13))
    gs = fig.add_gridspec(2, 3, height_ratios=[1.5, 1], wspace=0.28, hspace=0.25)
    cmap = plt.get_cmap("rocket_r")
    maps = ["a047_pvc_h30", "a047_pvc_h40", "a012_pvc_h30"]
    for i, v in enumerate(maps):
        ax = fig.add_subplot(gs[0, i])
        first, _, x, y = fields[v]
        pm = ax.pcolormesh(
            x,
            y,
            first.T,
            cmap=cmap,
            vmin=0,
            vmax=200,
            shading="nearest",
            rasterized=True,
        )
        ax.contour(
            x,
            y,
            np.nan_to_num(first.T, nan=999),
            levels=[60, 100, 140, 165],
            colors="white",
            linewidths=0.6,
        )
        for lab, (xt, yt) in {
            "C": (5.4, 25.0),
            "A": (-0.9, 1.6),
            "B": (-0.9, 21.6),
            "D": (-0.9, 27.6),
        }.items():
            ax.text(
                xt,
                yt,
                lab,
                color="#4575b4",
                fontsize=10,
                weight="semibold",
                ha="center",
                va="center",
            )
        ax.set_aspect("equal")
        ax.set_xlim(-5.2, 10.8)
        ax.set_ylim(-10.2, 35.2)
        ax.set_title(
            f"({'abc'[i]}) {v}",
            loc="left",
            fontsize=10,
            color="dimgrey",
        )
        ax.set_xlabel("x [m]", color="dimgrey")
        if i == 0:
            ax.set_ylabel("y [m]", color="dimgrey")
        style(ax)
    cb = fig.colorbar(pm, ax=ax, fraction=0.05, pad=0.03, extend="max")
    cb.set_label(
        "first time K > 0.23 1/m at 2.8 m [s]\n(white lines 60, 100, 140, 165 s)",
        color="dimgrey",
    )
    cb.ax.tick_params(length=0, labelcolor="dimgrey")

    ax_d = fig.add_subplot(gs[1, 0])
    for v, g in depth.groupby("variant", sort=False):
        h = v[-3:]
        ax_d.plot(
            g.y, g.depth, color=group[v[:8]], ls=dash[h], marker=mark[h], ms=5, lw=1.4
        )
    ax_d.set_xlabel("y in the hall [m] (C end at 24, A end at 0)", color="dimgrey")
    ax_d.set_ylabel("layer depth at 165 s [m]", color="dimgrey")
    ax_d.set_title(
        "(d) the layer is deepest at the A end",
        loc="left",
        fontsize=10,
        color="dimgrey",
    )
    ax_d.invert_xaxis()

    ax_e = fig.add_subplot(gs[1, 1])
    for v in VARIANTS:
        _, K, x, y = fields[v]
        ix = int(np.argmin(np.abs(x - 5.5)))
        m = (y > 0.2) & (y < 23.8)
        ax_e.plot(y[m], K[ix, m], color=group[v[:8]], ls=dash[v[-3:]], lw=1.4)
    ax_e.fill_between([0, 12], 0.7, 1.4, color="#fc8d59", alpha=0.25, lw=0)
    ax_e.fill_between([12, 24], 0, 0.23, color="#4575b4", alpha=0.25, lw=0)
    ax_e.text(
        6,
        1.5,
        "target lower hall",
        fontsize=8,
        color="dimgrey",
        ha="center",
        bbox=dict(fc="white", ec="none", alpha=0.8, pad=1),
    )
    ax_e.text(
        18,
        0.3,
        "target upper hall",
        fontsize=8,
        color="dimgrey",
        ha="center",
        bbox=dict(fc="white", ec="none", alpha=0.8, pad=1),
    )
    ax_e.set_yscale("symlog", linthresh=0.5)
    ax_e.set_xlabel("y on the hall axis x = 5.5 m [m]", color="dimgrey")
    ax_e.set_ylabel("K at 2.8 m, 165 s [1/m]", color="dimgrey")
    ax_e.set_title(
        "(e) hall axis against the target", loc="left", fontsize=10, color="dimgrey"
    )
    ax_e.invert_xaxis()

    ax_f = fig.add_subplot(gs[1, 2])
    for v in VARIANTS:
        a = arr.loc[v]
        c, h = group[v[:8]], v[-3:]
        ax_f.scatter(
            a.doorA_h,
            a.doorA_c,
            color=c,
            marker=mark[h],
            s=40,
            edgecolors="white",
            linewidths=0.6,
            zorder=3,
        )
        ax_f.scatter(
            a.doorB_h,
            a.doorB_c,
            facecolors="none",
            edgecolors=c,
            marker=mark[h],
            s=40,
            linewidths=1.2,
            zorder=3,
        )
    lim = [50, 230]
    ax_f.plot(lim, lim, color="dimgrey", lw=0.8)
    ax_f.text(
        100,
        205,
        "above the line:\nhall side first",
        fontsize=8,
        color="dimgrey",
        ha="center",
    )
    ax_f.set_xlim(lim)
    ax_f.set_ylim(lim)
    ax_f.set_xlabel("smoke on the hall side, x = 1.1 m [s]", color="dimgrey")
    ax_f.set_ylabel("smoke on the corridor side, x = −0.9 m [s]", color="dimgrey")
    ax_f.set_title(
        "(f) doors A (filled) and B (open), about 2.8 m",
        loc="left",
        fontsize=10,
        color="dimgrey",
    )
    for ax in (ax_d, ax_e, ax_f):
        style(ax)
    sns.despine(left=True, bottom=True)
    handles = [
        plt.Line2D(
            [],
            [],
            color=c,
            lw=2,
            label=k.replace("_", " ")
            .upper()
            .replace("A047", "α 0.047")
            .replace("A012", "α 0.012"),
        )
        for k, c in group.items()
    ]
    handles += [
        plt.Line2D(
            [],
            [],
            color="dimgrey",
            ls=dash[h],
            marker=mark[h],
            lw=1.2,
            label=f"H {h[1]}.{h[2]} m",
        )
        for h in dash
    ]
    fig.legend(
        handles=handles,
        loc="lower center",
        ncol=7,
        fontsize=8.5,
        bbox_to_anchor=(0.5, 0.0),
        **LEGEND,
    )
    save(fig, "p0b_hall_diag")


def main():
    """Print the page's geometry and fire numbers and write its fire figures.

    Parameters
    ----------
    --data : the schroeder2015-route study folder.

    Saves
    -----
    site/static/images/studies/schroeder2015/{geometry,fire_field,p0b_sweep,
    p0b_hall_diag}.png
    """
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--data", type=Path, required=True)
    args = parser.parse_args()
    data = args.data.resolve()
    geo, decks = _load("geometry"), _load("make_decks")

    # --- Data ---
    report_setup(geo, decks)
    report_premovement()
    df, snaps = load_sweep(data)
    report_sweep(df)
    rows, arrivals, fields = [], {}, {}
    for v in VARIANTS:
        r, a = devices(data, v)
        rows += r
        arrivals[v] = a
        fields[v] = arrival_map(data, v)
    depth = pd.DataFrame(rows)
    arr = pd.DataFrame(arrivals).T
    report_hall(depth, arr)

    # --- Plot ---
    sns.set_theme(font_scale=1.0, style="whitegrid", font="DejaVu Sans")
    fig_geometry(geo)
    fig_fire_field(data, geo)
    fig_sweep(df, snaps)
    fig_hall(data, depth, arr, fields)


if __name__ == "__main__":
    main()
