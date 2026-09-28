"""Seeing a door (FDS+Evac) vs reading a sign (pyFDS-Evac), drawn side by side.

One 60 x 30 m hall, one exit in the west wall, one 3 x 8 m block in the
hall. The door centre and the sign are the same point, half a cell inside
the west wall, so the two panels differ only in the rule that decides
whether an agent at a cell knows the exit is there.

Left, FDS+Evac. ``Is_Visible_Door`` in ``evac.f90`` sees a door when the
segment from the agent to the door centre is not blocked: no range limit,
no contrast, no angle factor, no smoke. The left panel is a
re-implementation of that rule with shapely (a segment tested against the
block), not FDS+Evac itself.

Right, pyFDS-Evac. The legible cells come from the real model,
``VisibilityModel.clear_air(...).node_is_visible(...)``, with the default
30 m sign reading distance and an omni-directional sign (``alpha`` None,
C = 3) in clear air. Clear air makes C/K infinite, so the 30 m cap is the
whole range and the legible region is the disc minus the block's shadow.

The script asserts what the figure claims for its three agents and that the
two rules agree inside the disc, where only sight lines can differ.

Run from the repository root::

    uv run python scripts/figures/sign_range_fds_evac.py

Writes ``site/static/images/wayfinding/sign_range_fds_evac.png``.
"""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns
import shapely
from matplotlib.colors import ListedColormap
from matplotlib.lines import Line2D
from matplotlib.patches import Circle, Patch, Rectangle
from shapely.geometry import box

from pyfds_evac import VisibilityModel
from pyfds_evac.core.visibility import DEFAULT_MAX_SIGN_DISTANCE_M

OUT = Path(__file__).resolve().parents[2] / "site" / "static" / "images" / "wayfinding"

# Shared palette of the concept figures, plus the talk's plan-view colours.
CHOSEN = "#4575b4"  # target seen: solid sight line
REFUSED = "#d73027"  # target not seen: dashed sight line
LEGIBLE = "#fee090"  # cells that see the door / read the sign
LEGIBLE_EDGE = "#c89b00"
EXIT = "#33a02c"
AGENT = "#e66101"  # orange agent: filled if it sees the target, hollow if not
NAVY = "#1f2d5c"
WALL = "#4d4d4d"
FLOOR = "#ececec"
TEXT = "dimgrey"

L, W = 60.0, 30.0
BLOCK = (14.0, 18.0, 17.0, 26.0)  # x0, y0, x1, y1
CELL_M = 0.25
TARGET = (CELL_M, 15.0)  # door centre (FDS+Evac) = sign (pyFDS-Evac)
EXIT_HALF = 1.5
CAP = DEFAULT_MAX_SIGN_DISTANCE_M
# agent -> (position, FDS+Evac sees the door, pyFDS-Evac reads the sign)
AGENTS = {
    1: ((10.0, 8.0), True, True),
    2: ((45.0, 12.0), True, False),
    3: ((22.0, 22.0), False, False),
}
WHITE_BOX = dict(boxstyle="round,pad=0.25", fc="white", ec="none", alpha=0.9)


def fds_evac_sees_door(xy, obstacle):
    """Re-implementation of FDS+Evac's ``Is_Visible_Door``: an unblocked segment."""
    return not shapely.LineString([xy, TARGET]).intersects(obstacle)


def fds_evac_grid(xs, ys, obstacle):
    """Boolean grid (rows y, cols x) of the cells that see the door."""
    gx, gy = np.meshgrid(xs, ys)
    start = np.stack([gx.ravel(), gy.ravel()], axis=1)
    end = np.broadcast_to(TARGET, start.shape)
    lines = shapely.linestrings(np.stack([start, end], axis=1))
    return ~shapely.intersects(lines, obstacle).reshape(gx.shape)


def draw_hall(ax, mask, xs, ys, inside_block, title, cap_style):
    """Floor, shaded cells, walls, block, exit and the 30 m circle."""
    ax.add_patch(Rectangle((0, 0), L, W, fc=FLOOR, ec="none", zorder=0))
    ax.imshow(
        np.where(mask & ~inside_block, 1.0, np.nan),
        origin="lower",
        extent=(0, L, 0, W),
        cmap=ListedColormap([LEGIBLE]),
        alpha=0.8,
        interpolation="nearest",
        zorder=1,
    )
    ax.contour(
        xs, ys, mask.astype(float), levels=[0.5], colors=LEGIBLE_EDGE, linewidths=0.9
    )
    hall = Rectangle((0, 0), L, W, fc="none", ec=WALL, lw=3.5, zorder=3)
    ax.add_patch(hall)
    x0, y0, x1, y1 = BLOCK
    ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fc=WALL, ec=WALL, zorder=3))
    ax.add_patch(
        Rectangle(
            (-0.6, TARGET[1] - EXIT_HALF),
            1.2,
            2 * EXIT_HALF,
            fc=EXIT,
            ec="none",
            zorder=4,
        )
    )
    ax.text(-1.2, TARGET[1], "exit", color=NAVY, fontsize=9, ha="right", va="center")
    ax.text(
        (x0 + x1) / 2,
        y1 + 1.0,
        "obstacle",
        color=NAVY,
        fontsize=8.5,
        ha="center",
        va="bottom",
        bbox=WHITE_BOX,
        zorder=6,
    )
    circle = Circle(TARGET, CAP, fill=False, zorder=4, **cap_style)
    ax.add_patch(circle)
    circle.set_clip_path(Rectangle((0, 0), L, W, transform=ax.transData))
    # navy frame around the plan, as in the talk
    ax.add_patch(
        Rectangle((-5.0, -2.0), L + 7.0, W + 4.0, fc="none", ec=NAVY, lw=0.8, zorder=0)
    )
    ax.set_xlim(-5.2, L + 2.2)
    ax.set_ylim(-2.2, W + 2.2)
    ax.set_aspect("equal")
    # a floor plan has no data axes: grid, ticks and frame add nothing
    ax.axis("off")
    ax.set_title(title, loc="left", color=NAVY, fontsize=11, fontweight="bold", pad=6)


def draw_agents(ax, verdicts):
    """Sight line to the target and a numbered marker for each agent."""
    for k, ((x, y), _, _) in AGENTS.items():
        seen = verdicts[k]
        ax.plot(
            [x, TARGET[0]],
            [y, TARGET[1]],
            color=CHOSEN if seen else REFUSED,
            ls="-" if seen else (0, (4, 2.5)),
            lw=1.8,
            zorder=5,
        )
        ax.plot(
            x,
            y,
            "o",
            ms=9,
            mfc=AGENT if seen else "white",
            mec=AGENT,
            mew=2.0,
            zorder=7,
        )
        ax.text(
            x + 1.2,
            y + 1.1,
            str(k),
            color=NAVY,
            fontsize=10,
            fontweight="bold",
            ha="left",
            va="bottom",
            bbox=WHITE_BOX,
            zorder=7,
        )


def main():
    """Compute both visibility grids and render the comparison.

    Saves
    -----
    site/static/images/wayfinding/sign_range_fds_evac.png
    """
    # --- Data ---
    obstacle = box(*BLOCK)
    walkable = box(0.0, 0.0, L, W).difference(obstacle)
    signs = {"exit": {"x": TARGET[0], "y": TARGET[1], "alpha": None, "c": 3}}
    vis = VisibilityModel.clear_air(walkable, signs, cell_size_m=CELL_M)

    xs = np.arange(CELL_M / 2, L, CELL_M)
    ys = np.arange(CELL_M / 2, W, CELL_M)
    gx, gy = np.meshgrid(xs, ys)
    inside_block = shapely.contains_xy(obstacle, gx, gy)
    fds = fds_evac_grid(xs, ys, obstacle)
    pyfds = np.array([[vis.node_is_visible(0.0, x, y, "exit") for x in xs] for y in ys])

    dist = np.hypot(gx - TARGET[0], gy - TARGET[1])
    assert not (pyfds & (dist > CAP)).any(), "a sign is legible beyond the cap"
    disc = (dist < CAP - CELL_M) & ~inside_block
    agree = np.mean(fds[disc] == pyfds[disc])
    print(f"inside {CAP:.0f} m, FDS+Evac rule and model agree on {agree:.1%} of cells")
    assert agree > 0.98, "inside the disc the two rules should differ only at edges"

    fds_seen, pyfds_seen = {}, {}
    for k, (xy, fds_claim, pyfds_claim) in AGENTS.items():
        fds_seen[k] = fds_evac_sees_door(xy, obstacle)
        pyfds_seen[k] = vis.node_is_visible(0.0, *xy, "exit")
        d = np.hypot(xy[0] - TARGET[0], xy[1] - TARGET[1])
        print(
            f"agent {k} at {xy}, {d:.1f} m: FDS+Evac sees={fds_seen[k]}, "
            f"pyFDS-Evac reads={pyfds_seen[k]}"
        )
        assert fds_seen[k] == fds_claim, f"agent {k}: FDS+Evac verdict"
        assert pyfds_seen[k] == pyfds_claim, f"agent {k}: pyFDS-Evac verdict"
    d2 = np.hypot(AGENTS[2][0][0] - TARGET[0], AGENTS[2][0][1] - TARGET[1])

    # --- Style Setup ---
    sns.set_theme(font_scale=1.0, style="whitegrid", font="DejaVu Sans")
    fig, (ax0, ax1) = plt.subplots(
        1, 2, figsize=(13.0, 3.7), dpi=150, gridspec_kw=dict(wspace=0.04)
    )

    # --- Plot ---
    draw_hall(
        ax0,
        fds,
        xs,
        ys,
        inside_block,
        "FDS+Evac: a door is seen at any distance",
        dict(ec=NAVY, lw=1.0, ls=(0, (2, 3)), alpha=0.35),
    )
    ax0.text(
        44.0,
        26.5,
        "obstacle's shadow",
        color=NAVY,
        fontsize=8.5,
        ha="center",
        va="center",
        bbox=WHITE_BOX,
        zorder=6,
    )
    draw_agents(ax0, fds_seen)

    draw_hall(
        ax1,
        pyfds,
        xs,
        ys,
        inside_block,
        f"pyFDS-Evac: a sign is read within {CAP:.0f} m",
        dict(ec=NAVY, lw=2.0, ls=(0, (6, 3))),
    )
    ang = np.deg2rad(-24.0)
    ax1.text(
        TARGET[0] + CAP * np.cos(ang) + 1.0,
        TARGET[1] + CAP * np.sin(ang),
        f"{CAP:.0f} m reading distance",
        color=NAVY,
        fontsize=9,
        ha="left",
        va="center",
        bbox=WHITE_BOX,
        zorder=6,
    )
    draw_agents(ax1, pyfds_seen)
    ax1.annotate(
        f"Agent 2, {d2:.0f} m away, clear view:\n"
        "FDS+Evac sees the door,\npyFDS-Evac cannot read the sign",
        xy=AGENTS[2][0],
        xytext=(45.5, 23.5),
        color=TEXT,
        fontsize=8.5,
        ha="center",
        va="center",
        bbox=WHITE_BOX,
        arrowprops=dict(arrowstyle="-", color=TEXT, lw=0.8, shrinkB=7),
        zorder=8,
    )

    handles = [
        Patch(fc=LEGIBLE, ec=LEGIBLE_EDGE, alpha=0.8, lw=0.9),
        Line2D([], [], color=CHOSEN, lw=1.8, marker="o", ms=8, mfc=AGENT, mec=AGENT),
        Line2D(
            [],
            [],
            color=REFUSED,
            lw=1.8,
            ls=(0, (4, 2.5)),
            marker="o",
            ms=8,
            mfc="white",
            mec=AGENT,
            mew=2.0,
        ),
    ]
    fig.legend(
        handles=handles,
        labels=[
            "cells that see the door (left) / read the sign (right), clear air",
            "agent sees the target: solid sight line, filled marker",
            "agent does not: dashed sight line, hollow marker",
        ],
        loc="lower center",
        bbox_to_anchor=(0.5, 0.04),
        ncol=3,
        fontsize=8,
        frameon=True,
        facecolor="white",
        framealpha=0.8,
        edgecolor="lightgrey",
        labelcolor="dimgrey",
    )
    sns.despine(fig=fig, left=True, bottom=True)

    # --- Save ---
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / "sign_range_fds_evac.png", dpi=150, bbox_inches="tight")


if __name__ == "__main__":
    main()
