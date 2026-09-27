"""Sign rotation: how the sign's bearing decides whether it is legible.

One agent stands 6 m in front of one sign in a 6 x 10 m room filled with a
uniform smoke layer (K = 0.3 1/m). The sign stays where it is and turns away
from the agent, its bearing alpha going from 0 (facing the agent) to past 90
(turned away). Every number on the frame comes from pyFDS-Evac's own
visibility model (``VisibilityModel.clear_air``, i.e. fdsvismap): the
effective visibility ``cos(alpha) * min(C / K, Vmax)`` is
``visibility_to_node``, the distance is ``distance_to_node`` and the agent's
state is ``node_is_visible``. Nothing is recomputed here.

Run from the repository root::

    uv run python scripts/figures/sign_rotation.py

Writes ``site/static/images/wayfinding/sign_rotation.gif``.
"""

import contextlib
import io
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns
from matplotlib.animation import PillowWriter
from matplotlib.colors import ListedColormap
from matplotlib.patches import FancyArrowPatch, Rectangle
from shapely.geometry import box

from pyfds_evac import VisibilityModel

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "site" / "static" / "images" / "wayfinding"

# Palette shared with sign_bearing.py: one meaning, one colour, one style.
LEGIBLE_C = "#4575b4"  # sign legible: solid sight line, filled agent
HIDDEN_C = "#d73027"  # sign not legible: dashed sight line, hollow agent
REGION = "#fee090"  # cells that read the sign: yellow fill
SIGN = "#c89b00"  # sign plate and facing arrow
WALL = "dimgrey"
FLOOR = "#f7f7f7"
TEXT = "dimgrey"

ROOM_W, ROOM_L = 6.0, 10.0
CELL_M = 0.25
EXTINCTION = 0.3  # uniform smoke, 1/m
C_SIGN = 3.0  # reflective sign
# Both points sit on cell centres, so the model's cell-centre distance is 6 m.
SIGN_XY = (3.125, 1.125)
AGENT_XY = (3.125, 7.125)
# 1.5 degree steps keep every frame off the analytic crossing near 53.13 deg.
ALPHAS = np.arange(0.0, 111.0, 1.5)
FPS = 12
HOLD_START, HOLD_FLIP, HOLD_END = 12, 8, 18  # frames


def sweep():
    """Query the model once per bearing; return per-bearing state."""
    signs = {
        f"a{i}": dict(x=SIGN_XY[0], y=SIGN_XY[1], alpha=float(a), c=C_SIGN)
        for i, a in enumerate(ALPHAS)
    }
    # fdsvismap prints progress and divides by zero at the sign's own cell.
    with contextlib.redirect_stdout(io.StringIO()), np.errstate(invalid="ignore"):
        vis = VisibilityModel.clear_air(
            box(0, 0, ROOM_W, ROOM_L),
            signs,
            cell_size_m=CELL_M,
            extinction_per_m=EXTINCTION,
        )
    xs = np.arange(CELL_M / 2, ROOM_W, CELL_M)
    ys = np.arange(CELL_M / 2, ROOM_L, CELL_M)
    nodes = list(signs)
    legible = [vis.node_is_visible(0.0, *AGENT_XY, n) for n in nodes]
    # None means the sign faces away (a masked zero): nothing is readable.
    metres = [vis.visibility_to_node(0.0, *AGENT_XY, n) or 0.0 for n in nodes]
    regions = [
        np.array([[vis.node_is_visible(0.0, x, y, n) for x in xs] for y in ys])
        for n in nodes
    ]
    dist = vis.distance_to_node(*AGENT_XY, nodes[0])
    # The model's own ceiling (the domain diagonal); read once, never recomputed.
    v_max = float(vis._vis.max_vis)
    return np.array(legible), np.array(metres), regions, dist, v_max


def check(legible, metres, dist, v_max):
    """Assert one clean flip that agrees with the numbers shown; return it."""
    flip = int(np.argmin(legible))
    assert legible[0] and not legible[flip], "the sign never stops being legible"
    assert legible[:flip].all() and not legible[flip:].any(), "more than one flip"
    assert metres[flip - 1] >= dist > metres[flip], "number and state disagree"
    assert not legible[ALPHAS >= 90].any(), "legible from behind the sign"
    assert metres[0] < v_max, "Vmax binds: the rotation would not be the cause"
    assert 0.3 < flip / len(ALPHAS) < 0.7, "flip is not mid-animation"
    return flip


def frame_order(flip):
    """Sweep indices with holds at the start, on the flip and at the end."""
    idx = list(range(len(ALPHAS)))
    return (
        [0] * HOLD_START
        + idx[:flip]
        + [flip] * HOLD_FLIP
        + idx[flip:]
        + [idx[-1]] * HOLD_END
    )


def draw_room(ax, region, alpha, ok):
    """Floor plan: legible cells, the rotated sign, the agent, the sight line."""
    ax.clear()
    ax.add_patch(Rectangle((0, 0), ROOM_W, ROOM_L, fc=FLOOR, ec="none", zorder=0))
    ax.imshow(
        np.where(region, 1.0, np.nan),
        origin="lower",
        extent=(0, ROOM_W, 0, ROOM_L),
        cmap=ListedColormap([REGION]),
        alpha=0.7,
        interpolation="nearest",
        zorder=1,
    )
    ax.add_patch(
        Rectangle((0, 0), ROOM_W, ROOM_L, fc="none", ec=WALL, lw=1.4, zorder=2)
    )
    # fdsvismap's readable normal is (sin a, cos a): a = 0 faces +y.
    normal = np.array([np.sin(np.deg2rad(alpha)), np.cos(np.deg2rad(alpha))])
    plate = np.array([normal[1], -normal[0]]) * 0.6
    sx, sy = SIGN_XY
    ax.plot(
        [sx - plate[0], sx + plate[0]],
        [sy - plate[1], sy + plate[1]],
        color=SIGN,
        lw=5,
        solid_capstyle="butt",
        zorder=5,
    )
    ax.add_patch(
        FancyArrowPatch(
            SIGN_XY,
            (sx + 1.3 * normal[0], sy + 1.3 * normal[1]),
            arrowstyle="-|>",
            mutation_scale=12,
            color=SIGN,
            lw=1.8,
            zorder=5,
        )
    )
    ax.text(sx - 0.9, sy - 0.55, "sign", fontsize=8, color=TEXT, ha="right")
    colour = LEGIBLE_C if ok else HIDDEN_C
    ax.plot(
        [AGENT_XY[0], sx],
        [AGENT_XY[1], sy],
        color=colour,
        lw=1.8,
        ls="-" if ok else (0, (4, 3)),
        zorder=4,
    )
    ax.plot(
        *AGENT_XY,
        marker="o",
        ms=11,
        mew=2.2,
        mec=colour,
        mfc=colour if ok else "white",
        zorder=6,
    )
    ax.text(
        AGENT_XY[0] + 0.45,
        AGENT_XY[1] + 0.35,
        "agent",
        fontsize=8,
        color=TEXT,
        ha="left",
    )
    ax.set_xlim(-0.2, ROOM_W + 0.2)
    ax.set_ylim(-0.2, ROOM_L + 0.2)
    ax.set_aspect("equal")
    # a floor plan has no data axes: grid, ticks and frame add nothing
    ax.axis("off")


def draw_curve(ax, i, legible, metres, dist, flip):
    """Effective visibility against bearing, traced up to the current frame."""
    ax.clear()
    ax.grid(False)
    ax.axhline(dist, color=TEXT, lw=1.0, ls=":", zorder=1)
    ax.text(112, dist, f"distance\n{dist:.1f} m", fontsize=8, color=TEXT, va="center")
    seen = min(i, flip - 1) + 1
    ax.plot(ALPHAS[:seen], metres[:seen], color=LEGIBLE_C, lw=2.2, zorder=3)
    if i >= flip:
        ax.plot(
            ALPHAS[flip - 1 : i + 1],
            metres[flip - 1 : i + 1],
            color=HIDDEN_C,
            lw=2.2,
            ls=(0, (4, 3)),
            zorder=3,
        )
    ax.plot(ALPHAS[i:], metres[i:], color="lightgrey", lw=1.0, zorder=2)
    ok = legible[i]
    colour = LEGIBLE_C if ok else HIDDEN_C
    ax.plot(
        ALPHAS[i],
        metres[i],
        marker="o",
        ms=8,
        mew=2,
        mec=colour,
        mfc=colour if ok else "white",
        zorder=4,
    )
    ax.set_xlim(-3, 111)
    ax.set_ylim(-0.4, metres.max() * 1.45)
    ax.set_yticks([0, 2, 4, 6, 8, 10])
    ax.set_xticks([0, 30, 60, 90])
    ax.set_xticklabels(["0°", "30°", "60°", "90°"])
    ax.set_xlabel("sign bearing α (0° = facing the agent)", fontsize=9, color=TEXT)
    ax.set_ylabel("effective visibility (m)", fontsize=9, color=TEXT)
    ax.tick_params(axis="both", which="both", length=0, labelcolor=TEXT)
    ax.text(
        0.98,
        0.97,
        f"α = {ALPHAS[i]:5.1f}°\n"
        f"visibility {metres[i]:4.1f} m\n"
        f"{'≥' if ok else '<'} distance {dist:3.1f} m",
        transform=ax.transAxes,
        ha="right",
        va="top",
        fontsize=11,
        color=colour,
        fontweight="semibold",
        family="DejaVu Sans Mono",
    )
    ax.text(
        0.98,
        0.66,
        "sign legible" if ok else "sign not legible",
        transform=ax.transAxes,
        ha="right",
        va="top",
        fontsize=10,
        color="white",
        fontweight="bold",
        bbox=dict(boxstyle="round,pad=0.3", fc=colour, ec="none"),
    )


def main():
    """Sweep the sign's bearing through the model and animate it.

    Saves
    -----
    site/static/images/wayfinding/sign_rotation.gif
    """
    legible, metres, regions, dist, v_max = sweep()
    flip = check(legible, metres, dist, v_max)
    print(
        f"distance {dist:.2f} m, K {EXTINCTION} 1/m, C {C_SIGN}, "
        f"C/K {metres[0]:.2f} m, Vmax {v_max:.2f} m; legible up to "
        f"{ALPHAS[flip - 1]:.1f} deg ({metres[flip - 1]:.2f} m), "
        f"not from {ALPHAS[flip]:.1f} deg ({metres[flip]:.2f} m)"
    )

    # --- Style Setup ---
    sns.set_theme(font_scale=1.0, style="whitegrid", font="DejaVu Sans")
    fig, (ax_room, ax_curve) = plt.subplots(
        1,
        2,
        figsize=(7.2, 4.0),
        dpi=100,
        gridspec_kw=dict(width_ratios=[1, 1.7], wspace=0.15),
    )
    fig.subplots_adjust(left=0.02, right=0.9, top=0.8, bottom=0.14)
    fig.text(
        0.02,
        0.95,
        "Turning a sign away shortens how far it can be read",
        fontsize=12,
        color="#333333",
        ha="left",
        va="top",
    )
    fig.text(
        0.02,
        0.89,
        rf"Uniform smoke $\bar{{K}}$ = {EXTINCTION} 1/m, reflective sign "
        rf"C = {C_SIGN:.0f}: C/$\bar{{K}}$ = {metres[0]:.0f} m "
        f"(cap Vmax = {v_max:.1f} m), agent {dist:.0f} m away.\n"
        rf"The sign stays legible while cos α · C/$\bar{{K}}$ ≥ {dist:.0f} m, "
        f"so it is lost by α = {ALPHAS[flip]:.0f}°, long before it turns sideways.",
        fontsize=8,
        color=TEXT,
        ha="left",
        va="top",
    )
    # shaded-region key, fixed across frames
    fig.text(
        0.02,
        0.06,
        "yellow cells: positions from which the model reads the sign",
        fontsize=7.5,
        color=TEXT,
        ha="left",
        bbox=dict(fc=REGION, ec="none", alpha=0.7, pad=2),
    )

    def render(i):
        draw_room(ax_room, regions[i], ALPHAS[i], legible[i])
        draw_curve(ax_curve, i, legible, metres, dist, flip)
        sns.despine(ax=ax_curve, left=True, bottom=True)

    # --- Save ---
    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / "sign_rotation.gif"
    writer = PillowWriter(fps=FPS)
    with writer.saving(fig, out, dpi=100):
        for i in frame_order(flip):
            render(i)
            writer.grab_frame()
    n = len(frame_order(flip))
    print(f"wrote {out} ({n} frames, {n / FPS:.1f} s)")


if __name__ == "__main__":
    main()
