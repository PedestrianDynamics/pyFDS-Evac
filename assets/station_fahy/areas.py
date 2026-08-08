"""Where each Fahy Table 2 area sits in the hand-drawn Station geometry.

Anchors that are **ground truth**, not interpretation:

* obstacle 7 = the stage, obstacle 5 = the main bar (from the author of the
  drawing);
* the dance floor is the east end of the big central hall (likewise);
* the four doors, whose identity was settled by fitting the NIST deck's door
  positions against the drawing's exits -- 0.76 m RMSE for
  front/main-bar/kitchen/platform versus 4.16 m for the main-bar/kitchen swap.

Everything else here is *derived* from those anchors and is the part a reviewer
should push on. Each area is a rectangle clipped to the walkable geometry, so a
boundary that clips away to nothing is a placement error rather than a silent
shrink -- :func:`build` refuses to continue when an area cannot hold its
occupants.

Frame note: the drawing does not share the deck's origin, and the exits were
deliberately pushed outside the building so agents keep walking after leaving.
No transform between the two frames is used anywhere, on purpose: a similarity
fit through those displaced doors has pairwise scale ratios spanning 1.15-1.37,
so it cannot carry deck coordinates into this frame.
"""

from __future__ import annotations

from shapely.geometry import box

# name -> (x0, y0, x1, y1) in the drawing's frame.
RECTS: dict[str, tuple[float, float, float, float]] = {
    # --- the central hall, split west-to-east by distance from the stage ---
    "Near stage or on dance floor": (7.5, -8.0, 15.8, 5.0),
    "Behind dance floor": (0.0, -8.0, 7.5, 5.0),
    "Between bars": (-9.0, -8.0, 0.0, -1.0),
    "Center stage-side": (0.0, 5.0, 7.5, 8.0),
    # --- around the bars ---
    "Main bar": (-10.5, -1.0, -2.5, 1.0),
    "Rear bar / dart room": (-15.5, 4.0, -8.0, 9.0),
    # --- the front of house ---
    "Entryway": (-3.0, -10.2, 3.0, -8.0),
    "Sunroom": (-9.0, -10.2, -3.0, -8.0),
    "Back hallway": (-15.8, -9.5, -10.5, -2.0),
    # --- stage end ---
    "Stage": (10.0, 5.0, 15.8, 8.0),
    "Near stage door": (13.0, -9.5, 16.4, -4.0),
    "Back wall platform": (4.0, 8.5, 15.8, 11.5),
}


# Specific places win over the broad hall areas where the rectangles overlap:
# somebody standing by the stage door is "near the stage door", not "on the
# dance floor". Anything not listed keeps whatever is left.
PRIORITY = (
    "Near stage door",
    "Stage",
    "Entryway",
    "Sunroom",
    "Main bar",
    "Back wall platform",
)


def polygons(walkable):
    """Clip every area to the walkable geometry, resolving overlaps by priority.

    Overlapping spawn areas would let one agent be attributed to two rows,
    which quietly corrupts the origin->exit matrix this asset exists to measure.
    """
    from shapely.ops import unary_union

    order = list(PRIORITY) + [n for n in RECTS if n not in PRIORITY]
    out: dict = {}
    claimed = None
    for name in order:
        poly = box(*RECTS[name]).intersection(walkable)
        if claimed is not None:
            poly = poly.difference(claimed)
        out[name] = poly
        claimed = poly if claimed is None else unary_union([claimed, poly])
    return {n: out[n] for n in RECTS}


def capacity_report(walkable, counts, radius=0.15, packing=2.5):
    """Area needed per agent is generous on purpose.

    A disc of radius r occupies pi*r^2, but agents cannot be placed touching --
    JuPedSim rejects overlapping seeds -- so *packing* multiplies the bare disc
    area. At r=0.15 that is about 0.18 m2 per agent.
    """
    import math

    per_agent = packing * math.pi * radius**2
    rows = []
    for name, poly in polygons(walkable).items():
        need = counts.get(name, 0) * per_agent
        rows.append((name, counts.get(name, 0), poly.area, need, poly.area >= need))
    return rows, per_agent
