"""Sign legibility, step by step: one sign of a real FDS run, and the algorithm.

Left, sign B of ``assets/t_junction`` (``config_full.json``) at one time of
the FDS run ``fire_2MW_PVC``. The legible cells, the mean extinction
coefficient along each sight line, the capped visibility, the view-angle
factor, the concealment and the distance are all read from the VisMap that
pyFDS-Evac builds for a run (``_build_vismap``: fdsvismap with C = 3, the
30 m reading distance, view angle and obstructions). V is the product of
those arrays, as in ``get_sign_vismap``, and the script asserts that it
reproduces the legible cells. The time is fixed by a rule before plotting: the first map time at
which sign B's legible area is below half its clear-air area (t = 0). The
three marked cells are picked by rule on the corridor axis and in the stem,
and the script asserts the class it labels each one with.

Right, the steps the left panel is made of, with the equation numbers of
Börger, Belt and Arnold (2024).

The extinction slices of the run are tracked in
``scripts/figures/data/t_junction_fire_2MW_PVC_extinction`` (see its
README), outside ``assets/`` so no tool takes them for a full run of the
scenario, and the script runs without arguments. ``--fds-dir`` takes another copy of the run.
Run from the repository root::

    uv run python scripts/figures/sign_legibility_steps.py

Writes ``site/static/images/wayfinding/sign_legibility_steps.png``.
"""

import argparse
import json
import re
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns
from matplotlib.colors import ListedColormap
from matplotlib.lines import Line2D
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Patch, Rectangle
from shapely import wkt

from pyfds_evac.core.fdsreader_adapter import open_fds_simulation
from pyfds_evac.core.visibility import (
    _build_vismap,
    _extinction_slice_index,
    extract_sign_descriptors,
)

ROOT = Path(__file__).resolve().parents[2]
ASSET = ROOT / "assets" / "t_junction"
OUT = ROOT / "site" / "static" / "images" / "wayfinding"

# Palette shared with sign_rotation.py: one meaning, one colour, one style.
LEGIBLE_C = "#4575b4"  # sign legible: solid sight line, filled marker
HIDDEN_C = "#d73027"  # sign not legible: dashed sight line, hollow marker
REGION = "#fee090"  # cells that read the sign: yellow fill
SIGN = "#c89b00"  # sign plate and facing arrow
WALL = "dimgrey"
INK = "#252525"

NODE = "exit_B_right"
SLICE_HEIGHT_M = 1.6  # pyFDS-Evac default; the nearest slice is used
TIME_STEP_S = 10.0


def fire_box(fds_file):
    """XB (x0, x1, y0, y1) of the VENT with SURF_ID='FIRE' in the FDS deck."""
    for line in Path(fds_file).read_text().splitlines():
        if "&VENT" in line and "'FIRE'" in line:
            xb = re.search(r"XB=([^/]*?),\s*SURF", line).group(1)
            return [float(v) for v in xb.split(",")[:4]]
    raise SystemExit("no FIRE vent in the deck")


def extinction_slice(fds_dir, time):
    """K on the slice the VisMap reads, its height, and the cell centres."""
    sim = open_fds_simulation(str(fds_dir))
    slc = sim.slices[_extinction_slice_index(str(fds_dir), SLICE_HEIGHT_M)]
    data, coords = slc.to_global(masked=True, fill=np.nan, return_coordinates=True)
    frame = data[slc.get_nearest_timestep(time)]
    return frame, coords["x"], coords["y"], float(slc.extent.z_start)


def cell(xs, ys, x, y):
    """Row and column of the grid cell nearest (x, y)."""
    return int(np.argmin(np.abs(ys - y))), int(np.argmin(np.abs(xs - x)))


def box(ax, y, h, text, fc, x0=0.03, w=0.8):
    ax.add_patch(
        FancyBboxPatch(
            (x0, y - h / 2),
            w,
            h,
            boxstyle="round,pad=0.006,rounding_size=0.015",
            fc=fc,
            ec="lightgrey",
            lw=0.9,
        )
    )
    ax.text(
        x0 + w / 2,
        y,
        text,
        ha="center",
        va="center",
        fontsize=8.6,
        color=INK,
        linespacing=1.35,
    )


def main():
    """Read sign B's legibility at one time and draw it next to the algorithm.

    Parameters
    ----------
    --fds-dir : t_junction FDS output (fire_2MW_PVC); default: the tracked
        extinction slices in scripts/figures/data/.

    Saves
    -----
    site/static/images/wayfinding/sign_legibility_steps.png
    """
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--fds-dir",
        default=Path(__file__).parent / "data" / "t_junction_fire_2MW_PVC_extinction",
        type=Path,
    )
    args = ap.parse_args()

    # --- Data ---
    signs = extract_sign_descriptors(
        json.loads((ASSET / "config_full.json").read_text())
    )
    walls = wkt.loads((ASSET / "geometry.wkt").read_text())
    fire = fire_box(ASSET / "t_junction.fds")
    vis = _build_vismap(str(args.fds_dir), signs, TIME_STEP_S, SLICE_HEIGHT_M)
    wp = list(signs).index(NODE)
    sign = signs[NODE]
    xs, ys = np.asarray(vis.all_x_coords), np.asarray(vis.all_y_coords)
    times = np.asarray(vis.vismap_time_points, float)
    cell_area = float(np.diff(xs).mean() * np.diff(ys).mean())

    area = np.array([vis.get_sign_vismap(wp, t).sum() * cell_area for t in times])
    t = float(times[np.argmax(area < 0.5 * area[0])])
    assert t > 0, "sign B never drops below half its clear-air area"

    legible = vis.get_sign_vismap(wp, t)
    legible0 = vis.get_sign_vismap(wp, 0.0)
    unconcealed = vis.all_sign_non_concealed_cells_array_dict[wp].astype(bool)
    cos = vis.all_sign_angle_array_dict[wp]
    dist = vis.all_sign_distance_array_dict[wp]
    kbar = vis._get_mean_extco_array_at_time(wp, t)
    v_cap = vis._get_visibility_array(wp, t)
    v = cos * v_cap * unconcealed
    assert np.array_equal(legible, (v >= dist) & (v >= vis.min_vis)), (
        "V does not reproduce get_sign_vismap"
    )
    k_map, kx, ky, z_slice = extinction_slice(args.fds_dir, t)

    # P: the legible cell on the corridor axis farthest from the sign. Q: the
    # nearest cell that faces the sign (cos θ > 0.9), is not concealed and
    # whose capped visibility is already below L, so smoke decides it before
    # the angle applies. R: a cell in the stem.
    row = cell(xs, ys, 0, sign["y"])[0]
    p = (row, int(np.where(legible[row])[0].min()))
    smoked = (
        unconcealed & ~legible & (cos > 0.9) & (v_cap < dist) & (ys[:, None] >= 10.0)
    )
    assert smoked.any(), "no cell is lost to smoke alone"
    q = np.unravel_index(np.argmin(np.where(smoked, dist, np.inf)), dist.shape)
    r = cell(xs, ys, 20.0, 3.0)
    assert legible[p] and unconcealed[p], "P must be legible"
    assert not legible[q] and unconcealed[q] and cos[q] > 0, "Q must be smoked out"
    assert smoked[q] and v_cap[q] < dist[q], "Q must fail L <= min(C/K, Vmax)"
    assert not unconcealed[r] and not legible[r], "R must be concealed"
    print(
        f"t = {t:.0f} s, legible area {area[np.searchsorted(times, t)]:.1f} m² "
        f"of {area[0]:.1f} m² at t = 0, slice z = {z_slice} m"
    )

    # --- Style Setup ---
    sns.set_theme(font_scale=1.0, style="whitegrid", font="DejaVu Sans")
    fig = plt.figure(figsize=(14.5, 5.4), dpi=150)
    gs = fig.add_gridspec(
        2, 2, width_ratios=[1.6, 1], height_ratios=[1, 0.05], wspace=0.05, hspace=0.25
    )
    ax = fig.add_subplot(gs[0, 0])
    cax = fig.add_subplot(gs[1, 0])
    axf = fig.add_subplot(gs[:, 1])

    # --- Plot: one sign, one time ---
    smoke = ListedColormap(plt.cm.Greys(np.linspace(0.0, 0.8, 256)))
    mesh = ax.pcolormesh(
        kx,
        ky,
        np.ma.masked_invalid(k_map).T,
        cmap=smoke,
        vmin=0,
        # 90 % of corridor cells at t = 20 s are below 1 1/m; a wider scale
        # washes out the smoke between the fire and the sign that the sight
        # lines cross.
        vmax=1,
        shading="nearest",
        rasterized=True,
        zorder=0,
    )
    ax.contourf(
        xs,
        ys,
        legible.astype(float),
        levels=[0.5, 1.5],
        colors=[REGION],
        alpha=0.75,
        zorder=1,
    )
    ax.contour(
        xs,
        ys,
        legible.astype(float),
        levels=[0.5],
        colors=[SIGN],
        linewidths=1.0,
        zorder=2,
    )
    ax.contour(
        xs,
        ys,
        legible0.astype(float),
        levels=[0.5],
        colors=[WALL],
        linewidths=1.0,
        linestyles=":",
        zorder=2,
    )
    ax.plot(*walls.exterior.xy, color=WALL, lw=1.2, zorder=3)
    ax.add_patch(
        Rectangle(
            (fire[0], fire[2]),
            fire[1] - fire[0],
            fire[3] - fire[2],
            fc="black",
            ec="white",
            lw=0.6,
            zorder=4,
        )
    )
    ax.text(
        (fire[0] + fire[1]) / 2,
        (fire[2] + fire[3]) / 2,
        "fire",
        ha="center",
        va="center",
        fontsize=7.5,
        color="white",
        zorder=5,
    )

    sx, sy = sign["x"], sign["y"]
    ax.add_patch(
        Rectangle(
            (sx - 0.15, sy - 0.6), 0.3, 1.2, fc=SIGN, ec="white", lw=0.6, zorder=6
        )
    )
    a = np.deg2rad(sign["alpha"])
    ax.add_patch(
        FancyArrowPatch(
            (sx, sy),
            (sx + 2.2 * np.sin(a), sy + 2.2 * np.cos(a)),
            arrowstyle="-|>",
            mutation_scale=11,
            color=SIGN,
            lw=1.4,
            zorder=6,
        )
    )
    ax.text(
        sx - 0.2,
        13.35,
        f"sign B\nα = {sign['alpha']:.0f}°, C = {sign['c']:g}",
        ha="right",
        va="bottom",
        fontsize=8.3,
        color=INK,
    )

    marks = {
        "P": (p, LEGIBLE_C, "-", True),
        "Q": (q, HIDDEN_C, "--", False),
        "R": (r, HIDDEN_C, ":", False),
    }
    for key, (ij, colour, ls, filled) in marks.items():
        x, y = xs[ij[1]], ys[ij[0]]
        ax.plot([sx, x], [sy, y], color=colour, ls=ls, lw=1.5, zorder=7)
        ax.plot(
            x,
            y,
            "o",
            ms=7.5,
            mfc=colour if filled else "white",
            mec=colour,
            mew=1.6,
            zorder=8,
        )
        dy = -0.45 if key == "P" else 0.45
        ax.text(
            x + (0.5 if key == "P" else 0),
            y + dy,
            key,
            ha="center",
            va="top" if key == "P" else "bottom",
            fontsize=9.5,
            color=colour,
            fontweight="bold",
            zorder=8,
        )

    def numbers(ij):
        return (
            f"L = {dist[ij]:.1f} m,  K̄ = {kbar[ij]:.2f} 1/m\n"
            f"V = min({sign['c']:g}/K̄, 30) · cos θ = {v_cap[ij]:.1f} · {cos[ij]:.2f}"
            f" = {v[ij]:.1f} m\n"
        )

    notes = [
        ("P", LEGIBLE_C, numbers(p) + "L ≤ V  →  legible", (0.3, 9.0)),
        ("Q", HIDDEN_C, numbers(q) + "L > V  →  not legible (smoke)", (0.3, 6.1)),
        (
            "R",
            HIDDEN_C,
            f"L = {dist[r]:.1f} m\nthe sight line crosses a wall\n"
            "U = 0  →  not legible",
            (0.3, 3.2),
        ),
    ]
    for key, colour, text, (x, y) in notes:
        ax.text(
            x,
            y,
            f"{key}:  {text}",
            fontsize=8.2,
            color=INK,
            va="top",
            bbox=dict(
                fc="white", ec=colour, lw=0.8, alpha=0.92, boxstyle="round,pad=0.3"
            ),
            zorder=9,
        )

    ax.set_aspect("equal")
    ax.set_xlim(-0.3, 30.3)
    ax.set_ylim(-0.3, 15.2)
    ax.set_xlabel("x (m)", color="dimgrey")
    ax.set_ylabel("y (m)", color="dimgrey")
    ax.tick_params(axis="both", which="both", length=0, labelcolor="dimgrey")
    ax.grid(False)
    ax.set_title(
        f"(a) Sign B of t_junction (fire_2MW_PVC) at t = {t:.0f} s",
        loc="left",
        fontsize=11,
        color=INK,
    )
    ax.legend(
        handles=[
            Patch(fc=REGION, ec=SIGN, label="legible at this time"),
            Line2D([], [], color=WALL, ls=":", label="legible in clear air (t = 0)"),
            Line2D([], [], color=LEGIBLE_C, label="legible sight line"),
            Line2D([], [], color=HIDDEN_C, ls="--", label="not legible"),
        ],
        loc="upper left",
        bbox_to_anchor=(0.0, 1.0),
        ncol=4,
        fontsize=8,
        frameon=True,
        facecolor="white",
        framealpha=0.8,
        edgecolor="lightgrey",
        labelcolor="dimgrey",
    )
    cb = fig.colorbar(mesh, cax=cax, orientation="horizontal", extend="max")
    cb.outline.set_visible(False)
    cb.ax.tick_params(length=0, labelcolor="dimgrey", labelsize=8)
    cb.set_label(
        f"extinction coefficient K on the FDS slice at z = {z_slice:g} m (1/m)",
        color="dimgrey",
        fontsize=8.5,
    )

    # --- Plot: the algorithm ---
    axf.set_xlim(0, 1)
    axf.set_ylim(0, 1)
    axf.axis("off")
    axf.set_title("(b) The steps", loc="left", fontsize=11, color=INK)
    pre, test, use = "#f0f0f0", "#deebf7", "#fff7d6"
    steps = [
        (
            0.94,
            f"FDS slice: K(x, y, t), nearest to z = {SLICE_HEIGHT_M:g} m\n"
            f"(here z = {z_slice:g} m)",
            pre,
        ),
        (
            0.83,
            "per sign, cell and time: K̄ = mean K over the cells\n"
            "of the sight line cell → sign (Eq. 9, from Eq. 8)",
            test,
        ),
        (
            0.72,
            "Jin: V = C / K̄,  C = 3 (reflective sign, FDS default);\n"
            "C lumps luminance, size, contrast, ambient light",
            test,
        ),
        (0.625, "cap: V ← min(V, 30 m)", test),
        (
            0.53,
            "angle: V ← V · cos θ,  0 for θ ≥ 90°\n"
            "(sign as a Lambertian radiator, simplified)",
            test,
        ),
        (
            0.42,
            "V ← V · U (U = 0 behind a wall); legible ⇔ L ≤ V\n"
            "→ boolean map per sign and time",
            test,
        ),
        (0.30, "agent at its position: is the sign legible here?", use),
        (
            0.20,
            "discovery: the sign's node enters the agent's\n"
            "cognitive map; routes use the known graph only",
            use,
        ),
    ]
    h = 0.075
    for i, (y, text, fc) in enumerate(steps):
        box(axf, y, h if "\n" in text else 0.05, text, fc)
        if i:
            y_prev = steps[i - 1][0]
            h_prev = h if "\n" in steps[i - 1][1] else 0.05
            h_here = h if "\n" in text else 0.05
            axf.add_patch(
                FancyArrowPatch(
                    (0.43, y_prev - h_prev / 2 - 0.006),
                    (0.43, y + h_here / 2 + 0.006),
                    arrowstyle="-|>",
                    mutation_scale=10,
                    color="dimgrey",
                    lw=1.0,
                )
            )
    axf.plot([0.845] * 2, [0.83 + h / 2, 0.42 - h / 2], color=LEGIBLE_C, lw=1.5)
    axf.text(0.86, 0.625, "fdsvismap", fontsize=8.5, color=LEGIBLE_C, va="center")
    axf.plot([0.845] * 2, [0.30 + 0.025, 0.20 - h / 2], color=SIGN, lw=1.5)
    axf.text(0.86, 0.25, "pyFDS-Evac", fontsize=8.5, color=SIGN, va="center")
    axf.text(
        0.03,
        0.115,
        "Equation numbers: Börger, Belt and Arnold (2024). fdsvismap caps\n"
        "before the angle; their Eq. 10 caps after it. An agent with full\n"
        "familiarity knows every exit at t = 0 and does not use this test.",
        fontsize=8,
        color="dimgrey",
        va="top",
        style="italic",
    )

    sns.despine(fig=fig, left=True, bottom=True)

    # --- Save ---
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / "sign_legibility_steps.png", dpi=150, bbox_inches="tight")


if __name__ == "__main__":
    main()
