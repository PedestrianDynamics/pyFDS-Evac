"""Where each Fahy Table 2 area sits in the hand-drawn Station geometry.

Anchors that are **ground truth**, not interpretation:

* obstacle 7 = the stage, obstacle 5 = the main bar (from the author of the
  drawing);
* the dance floor is the east end of the big central hall (likewise);
* the four doors, whose identity was settled by fitting the NIST deck's door
  positions against the drawing's exits -- 0.76 m RMSE for
  front/main-bar/kitchen/platform versus 4.16 m for the main-bar/kitchen swap.

Everything else here is *derived* from those anchors and is the part a reviewer
should push on. Each area is a rectangle clipped to the building interior, so a
boundary that clips away to nothing is a placement error rather than a silent
shrink -- :func:`build` refuses to continue when an area cannot hold its
occupants.

Frame note: the exits were deliberately pushed outside the building so agents
keep walking after leaving, which makes the outdoor apron walkable too. Areas
are therefore clipped to :func:`building_interior` and not to the walkable area:
clipped to the latter, six of these twelve rectangles reached past a wall and
started about a quarter of the crowd in the open air.

The rectangles below are anchored on the dimensions Fahy's floor plan prints,
which the drawing reproduces to a few centimetres: 24.2 m across the front
elevation, an 8.5 m main bar frontage running west from the entrance doors, a
10.9 x 4.6 m sunroom east of them, and a 16.5 x 9.8 m club behind. Rooms the
plan names but Table 2 has no row for -- storage, office, rest rooms, kitchen --
are left empty, as they are in Tawil's reconstruction.
"""

from __future__ import annotations

from shapely.geometry import Polygon, box
from shapely.ops import unary_union

# name -> (x0, y0, x1, y1) in the drawing's frame.
RECTS: dict[str, tuple[float, float, float, float]] = {
    # --- the club, 16.5 x 9.8 m, split west-to-east by distance from the stage ---
    "Near stage or on dance floor": (5.0, -4.3, 12.0, 3.0),
    "Behind dance floor": (-2.0, -4.3, 5.0, 3.0),
    "Center stage-side": (-2.0, 3.0, 5.0, 5.3),
    "Stage": (5.0, 3.0, 12.0, 5.3),
    "Back wall platform": (12.0, -3.0, 14.6, 3.0),
    # --- around the bars ---
    "Main bar": (-9.9, -8.8, -1.5, -1.0),
    "Between bars": (-9.9, 1.5, -2.0, 5.3),
    # the west wing, split front-to-back: the dart room end abuts the club, the
    # hallway runs behind it to the storage rooms
    "Rear bar / dart room": (-13.5, 1.5, -8.0, 6.5),
    "Back hallway": (-13.5, 6.5, -8.0, 9.5),
    # --- the front of house ---
    "Entryway": (-1.5, -8.8, 1.7, -5.6),
    "Sunroom": (1.7, -8.8, 11.7, -4.3),
    # --- stage end: the dressing room and the lobby off the platform door ---
    "Near stage door": (11.7, -8.8, 16.6, -3.0),
}


def largest_part(geom):
    """The biggest polygon of *geom*, which may already be a single one."""
    if geom.geom_type != "MultiPolygon":
        return geom
    return max(geom.geoms, key=lambda part: part.area)


def building_interior(walkable):
    """The walkable area inside the building, apron excluded.

    The walls are traced as separate strokes rather than one envelope, so the
    outline is recovered by growing them until the doorways close, taking the
    outer boundary of that single connected network, and shrinking back.
    """
    pad = 0.6
    walls = unary_union([Polygon(r) for r in walkable.interiors])
    network = largest_part(walls.buffer(pad))
    return walkable.intersection(largest_part(Polygon(network.exterior).buffer(-pad)))


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
    """Clip every area to the building interior, resolving overlaps by priority.

    Overlapping spawn areas would let one agent be attributed to two rows,
    which quietly corrupts the origin->exit matrix this asset exists to measure.
    """
    indoors = building_interior(walkable)
    order = list(PRIORITY) + [n for n in RECTS if n not in PRIORITY]
    out: dict = {}
    claimed = None
    for name in order:
        poly = box(*RECTS[name]).intersection(indoors)
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
