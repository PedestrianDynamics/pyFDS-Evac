#!/usr/bin/env python3
"""Reconstruct The Station nightclub floor plan.

Traced from the dimensioned plan of the venue (the version annotated with the
four exit doors), cross-checked against NIST NCSTAR 2 Vol. I where they overlap.

Coordinate system
    x runs west-to-east along the front facade, y runs from the front facade
    (y = 0, FRONT on the plan) toward the REAR.  Origin is the south-west corner
    of the main building, so the western storage wing has negative x.

Dimension provenance
    Constants are marked "plan" when read directly off the drawing, "chain" when
    derived from a dimension chain that closes, and "approx" where the drawing is
    ambiguous.  Two chains close exactly and anchor everything else:

      * West wall of the main bar room:  3.7 + 0.9 + 3.0 = 7.6, the labelled
        height.  This fixes the main bar side exit door at 0.9 m wide, 3.7 m
        north of the front corner.
      * Overall widths:  32.8 (top) - 26.5 (front) = 6.3 m of western wing.

    The 0.9 m door width independently reproduces NCSTAR Table 7-6's *measured*
    914 mm clear width for the side doors.  That is a real cross-check between
    two separate sources, not a restatement of one.

Status
    First-pass rectilinear reconstruction, NOT yet verified against the drawing
    by eye.  Run with --preview and compare before trusting it.  The horseshoe
    bar is squared off, and canted walls at the alcove and the western wing are
    approximated by rectangles.
"""

from pathlib import Path

from shapely.geometry import box
from shapely.ops import unary_union

HERE = Path(__file__).parent

FRONT_WIDTH = 26.5  # plan
TOP_WIDTH = 32.8  # plan
DEPTH = 20.9  # plan
WEST_WING = TOP_WIDTH - FRONT_WIDTH  # chain: 6.3

DOOR_W = 0.9  # plan; matches NCSTAR Table 7-6's 914 mm

# ── Rooms, (x_min, y_min, x_max, y_max) ──────────────────────────────
ROOMS = {
    # Front range, west to east
    "main_bar_room": (0.0, 0.0, 8.5, 7.6),  # 7.6 chain; 8.5 approx
    "entry_hall": (8.5, 0.0, 11.0, 2.8),  # 2.8 plan
    "ticket_area": (8.5, 2.8, 11.0, 7.6),  # approx
    "sunroom": (11.0, 0.0, 22.0, 5.0),  # 5 plan (east side)
    "dressing_room": (22.0, 0.0, 24.4, 4.9),  # 2.4 x 4.9 plan
    # Assembly range
    "main_floor": (11.0, 5.0, 19.0, 12.3),  # circulation
    "dance_floor": (13.5, 5.0, 19.0, 12.3),  # 7.3 deep, plan
    "raised_platform": (19.0, 5.0, 22.6, 12.3),  # 3.6 x 7.3 plan
    "alcove": (22.6, 5.0, 25.0, 8.0),  # 2.4 x 3 plan; lower corner carries the door
    "raised_dining": (11.0, 12.3, 19.0, 14.4),  # 2.1 deep, plan
    # Back of house
    "kitchen": (0.0, 7.6, 7.3, 9.9),  # 7.3 x 2.3 plan
    "rear_bar_dart": (0.0, 9.9, 11.0, 14.4),  # approx
    "back_hallway": (7.3, 14.4, 11.0, 16.5),  # approx
    "restroom_a": (11.0, 14.4, 14.0, 17.4),  # 3 x 3 plan
    "restroom_b": (11.0, 17.4, 14.0, 20.4),  # 3 x 3 plan
    "office": (5.0, 16.5, 11.0, 20.9),  # approx, within the 11.9 top block
    "side_bar": (14.0, 14.4, 17.7, 17.4),  # 3.7 plan
    "rear_area": (14.0, 14.4, 22.0, 17.0),  # approx
    "storage_west": (-WEST_WING, 8.0, 0.0, 15.2),  # 6.1 x 7.2 plan
}

# Horseshoe main bar, squared off. NCSTAR Fig. 7-3 gives 12.7 m2 for it.
MAIN_BAR_COUNTER = (1.9, 1.5, 6.5, 5.8)  # 4.6 x 4.3 plan

# (wall axis, fixed coordinate, centre along the wall, width, outward normal)
DOORS = {
    "main_bar_side": ("x", 0.0, 3.7 + DOOR_W / 2, DOOR_W, -1),  # chain
    "kitchen_side": ("x", 0.0, 8.75, DOOR_W, -1),  # approx
    "platform_side": ("x", 25.0, 5.0 + DOOR_W / 2, DOOR_W, +1),  # 5 plan
    "front_entrance": ("y", 0.0, 9.75, DOOR_W, -1),  # between the 2.0/2.1 dims
}


def _strip(axis, fixed, centre, width, outward, depth=1.6):
    half = width / 2.0
    if axis == "y":
        lo, hi = sorted((fixed, fixed + outward * depth))
        return box(centre - half, lo, centre + half, hi)
    lo, hi = sorted((fixed, fixed + outward * depth))
    return box(lo, centre - half, hi, centre + half)


def build_walkable():
    parts = [box(*bounds) for bounds in ROOMS.values()]
    parts += [_strip(*spec) for spec in DOORS.values()]
    walkable = unary_union(parts).difference(box(*MAIN_BAR_COUNTER))
    if walkable.geom_type != "Polygon":
        raise SystemExit(
            f"walkable area is {walkable.geom_type}: some room is disconnected"
        )
    return walkable


def preview(walkable):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon as MplPoly

    fig, ax = plt.subplots(figsize=(11, 9))
    xs, ys = walkable.exterior.xy
    ax.add_patch(MplPoly(list(zip(xs, ys)), fc="#dfe7f0", ec="#20313f", lw=1.6))
    for ring in walkable.interiors:
        ix, iy = ring.xy
        ax.add_patch(MplPoly(list(zip(ix, iy)), fc="#20313f"))
    for name, bounds in ROOMS.items():
        ax.text(
            (bounds[0] + bounds[2]) / 2,
            (bounds[1] + bounds[3]) / 2,
            name.replace("_", "\n"),
            fontsize=6,
            ha="center",
            va="center",
        )
    for name, (axis, fixed, centre, _w, _o) in DOORS.items():
        x, y = (fixed, centre) if axis == "x" else (centre, fixed)
        ax.plot(x, y, "o", ms=9, mfc="#d62728", mec="k", zorder=5)
        ax.annotate(name, (x, y), textcoords="offset points", xytext=(8, 6), fontsize=7)
    ax.set_aspect("equal")
    ax.set_xlabel("x [m]   west -> east along the front facade")
    ax.set_ylabel("y [m]   front -> rear")
    ax.set_title(
        f"The Station, reconstructed: {walkable.area:.0f} m2 walkable "
        "(NCSTAR footprint 412 m2)",
        fontsize=10,
    )
    ax.grid(alpha=0.25)
    fig.tight_layout()
    out = HERE / "layout_preview.png"
    fig.savefig(out, dpi=140)
    print(f"Wrote: {out}")


def build(make_preview: bool = False):
    walkable = build_walkable()
    (HERE / "geometry.wkt").write_text(walkable.wkt + "\n", encoding="utf-8")
    print(f"Walkable area : {walkable.area:7.1f} m2   (NCSTAR footprint 412 m2)")
    print(f"Bounding box  : {tuple(round(v, 1) for v in walkable.bounds)}")
    print(f"Expected      : x in [{-WEST_WING}, {FRONT_WIDTH}], y in [0.0, {DEPTH}]")
    if make_preview:
        preview(walkable)
    return walkable


if __name__ == "__main__":
    import sys

    build(make_preview="--preview" in sys.argv)
