"""Generate geometry.wkt from a hand-sketched layout.

Sketch (reproduced from the user's drawing): a rectangular room with —
  - a horizontal partition near the top, with a single 1.2 m door on the
    right leading up into a top-right exit alcove (red = exit)
  - a LEFT divider that hangs from that partition and stops partway down,
    leaving the bottom open (no door — just an open gap, as drawn)
  - a RIGHT divider that runs the full height, floor to partition, with
    one 1.2 m doorway — this is the start room's west wall
  - a pocket wall in the bottom-left, with a 1.2 m door
  - past that door, a FLOATING L-shaped wall (an island, touching
    nothing): 1.2 m clear of the pocket wall on one end, 1.2 m clear of
    divider A on the other — agents pass above or below it, not through
    a door cut into it
  - the spawn zone (green = start) against the right wall, behind the
    right divider's doorway

Built as: outer interior rectangle MINUS wall-bar rectangles, where each
wall bar is split into two segments to leave a DOOR_W-wide gap at its
door position (same technique real architectural doors use — not the
overlapping-rooms trick from discovery_test, so gaps are exact widths).

Edit WALL_THICKNESS / DOOR_W / the *_Y / *_X constants below and re-run to
reshape. Coordinates are in metres, matching the scale of
assets/social_force (wall thickness 0.1 m there too).
"""

from pathlib import Path

from shapely.geometry import Polygon, box
from shapely.ops import unary_union

HERE = Path(__file__).parent

# ── tunables ─────────────────────────────────────────────────────────────
WALL_THICKNESS = 0.1     # matches assets/social_force/geometry.wkt — NOT scaled
DOOR_W = 1.2              # required entrance width — NOT scaled

# Domain shrunk ~30% from the first draft (28x26 -> 20x18) for more
# realistic room proportions relative to a 1.2 m door. Wall thickness and
# door width stay fixed above; only room/corridor extents scale down.
DOMAIN = (0.0, 0.0, 20.0, 18.0)   # xmin, ymin, xmax, ymax (outer wall centreline)

# Partition 1: horizontal wall separating the top exit alcove from the
# main room. One door on the right leads up into the alcove.
PART1_Y = 13.0
PART1_DOOR_X = (17.0, 17.0 + DOOR_W)

# Left divider (A): hangs from the partition and stops short of the
# floor, matching the sketch — that line stops partway down, leaving the
# bottom open (no door needed, it's just an open gap).
DIV_A_X = 7.0
DIV_A_Y_RANGE = (4.5, PART1_Y)

# Right divider (B): a single continuous wall from the partition all the
# way down to the floor — this is the sketch's other line, which runs
# the full height, not a short stub. It's the west wall of the start
# room, with one 1.2 m doorway (the one you flagged).
DIV_B_X = 13.0
DIV_B_Y_RANGE = (0.0, PART1_Y)
DIV_B_DOOR_Y = (1.0, 1.0 + DOOR_W)

# Bottom-left pocket wall (touches the west wall) + a separate FLOATING
# L-shaped wall (island, touching nothing): a horizontal foot picking up
# right after the pocket door, then a vertical riser reaching up toward
# divider A. It has open clearance on both ends instead of a door cut
# into its own body: 1.2 m to the pocket wall on one side (the door),
# 1.2 m to divider A on the other (the gap above the riser).
POCKET_Y = 1.9
POCKET_WALL_A_X = (0.0, 2.9)
POCKET_DOOR_X = (2.9, 2.9 + DOOR_W)          # 1.2 m clearance, bottom end

FLOATING_FOOT_X = (POCKET_DOOR_X[1], 7.0)     # horizontal foot, right after the door
FLOATING_WALL_X = 7.0                         # riser x, aligned under divider A
FLOATING_RISER_Y = (2.0, DIV_A_Y_RANGE[0] - DOOR_W)   # top end: 1.2 m below divider A

# Start (green) and exit (red) zones.
START_RECT = (14.0, 0.8, 18.5, 2.8)          # start room, right of divider B
EXIT_RECT = (17.0, 15.8, 18.8, 17.4)         # top-right alcove


def _wall_bar(x0, x1, y0, y1, gap=None):
    """Return wall segments for a horizontal-or-vertical bar, split by *gap*.

    ``gap`` is (lo, hi) along the bar's long axis where a door removes
    material. Horizontal bars (y0==y1's thickness band) split along x;
    vertical bars split along y.
    """
    horizontal = (x1 - x0) > (y1 - y0)
    if gap is None:
        return [box(x0, y0, x1, y1)]
    lo, hi = gap
    segs = []
    if horizontal:
        if lo > x0:
            segs.append(box(x0, y0, lo, y1))
        if hi < x1:
            segs.append(box(hi, y0, x1, y1))
    else:
        if lo > y0:
            segs.append(box(x0, y0, x1, lo))
        if hi < y1:
            segs.append(box(x0, hi, x1, y1))
    return segs


def build():
    xmin, ymin, xmax, ymax = DOMAIN
    t = WALL_THICKNESS
    interior = box(xmin + t, ymin + t, xmax - t, ymax - t)

    walls = []
    # Partition 1 (horizontal), door on the right.
    walls += _wall_bar(xmin + t, xmax - t, PART1_Y, PART1_Y + t, gap=PART1_DOOR_X)
    # Divider A, upper part hangs from the partition, no gap.
    a0, a1 = DIV_A_Y_RANGE
    walls += _wall_bar(DIV_A_X, DIV_A_X + t, a0, a1)
    # Divider B — full-height wall, one 1.2 m doorway into the start room.
    b0, b1 = DIV_B_Y_RANGE
    walls += _wall_bar(DIV_B_X, DIV_B_X + t, b0, b1, gap=DIV_B_DOOR_Y)
    # Bottom-left pocket wall (touches the west wall).
    walls.append(box(xmin, POCKET_Y, POCKET_WALL_A_X[1], POCKET_Y + t))
    # Floating L-shaped wall (island): horizontal foot + vertical riser,
    # 1.2 m clear of the pocket wall on one end and 1.2 m clear of
    # divider A on the other.
    f0, f1 = FLOATING_FOOT_X
    walls.append(box(f0, POCKET_Y, f1, POCKET_Y + t))
    r0, r1 = FLOATING_RISER_Y
    walls.append(box(FLOATING_WALL_X, r0, FLOATING_WALL_X + t, r1))

    floor = interior.difference(unary_union(walls))
    if floor.geom_type != "Polygon":
        raise SystemExit(
            f"Floor split into {floor.geom_type} — a wall fully disconnects "
            f"a region (check the *_Y_RANGE / gap constants)."
        )

    (HERE / "geometry.wkt").write_text(floor.wkt + "\n", encoding="utf-8")

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.patches import Polygon as MplPoly

        fig, ax = plt.subplots(figsize=(9, 8.4))
        xs, ys = floor.exterior.xy
        ax.add_patch(MplPoly(list(zip(xs, ys)), facecolor="#dfe3ea", edgecolor="#333", lw=1.2))
        for interior_ring in floor.interiors:
            ix, iy = interior_ring.xy
            ax.add_patch(MplPoly(list(zip(ix, iy)), facecolor="#333"))
        sx0, sy0, sx1, sy1 = START_RECT
        ax.add_patch(MplPoly([(sx0, sy0), (sx1, sy0), (sx1, sy1), (sx0, sy1)],
                              facecolor="none", edgecolor="#16a34a", lw=2.5))
        ex0, ey0, ex1, ey1 = EXIT_RECT
        ax.add_patch(MplPoly([(ex0, ey0), (ex1, ey0), (ex1, ey1), (ex0, ey1)],
                              facecolor="none", edgecolor="#dc2626", lw=2.5))
        ax.set_aspect("equal")
        ax.set_xlim(xmin - 1, xmax + 1)
        ax.set_ylim(ymin - 1, ymax + 1)
        ax.set_title("social_force_sketch walkable area (green=start, red=exit)")
        ax.grid(alpha=0.3)
        fig.tight_layout()
        fig.savefig(HERE / "layout_preview.png", dpi=100)
        print("wrote geometry.wkt and layout_preview.png")
    except ImportError:
        print("wrote geometry.wkt (matplotlib not available for preview)")

    return floor


if __name__ == "__main__":
    build()
