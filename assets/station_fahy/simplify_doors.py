#!/usr/bin/env python3
"""Open every doorway in the traced Station geometry, the way egress models do.

    .venv/bin/python assets/station_fahy/simplify_doors.py in.wkt out.wkt

The drawing traces door leaves and jambs stroke by stroke, so its openings carry
the freehand error of two strokes rather than of one: passages come out anywhere
between 0.04 m and the drawn width. Two failure modes follow. Openings under
~0.2 m are not doors at all but strokes that failed to meet -- they leave a slit
an agent can never use and a spurious passage in the navigation mesh. Openings
between that and a body width admit one agent and deadlock two: the 0.40 m gap
at the north-east corner of the main bar stalled three agents for a full 600 s
run (issue #103).

Neither is a property of the building. The Station's doors were ordinary doors,
and an evacuation model assumes them wide open at their clear width -- the same
simplification Fahy, Proulx & Flynn and the NIST reconstruction make. So this
script sets every passage to at least ``TARGET`` and seals what is narrower than
``SEAL``, leaving anything already wider untouched.

The front entrance is the one opening the plan dimensions (2.0 m / 6.6 ft, the
pair of doors patrons entered by), so it is set to that figure explicitly rather
than to the generic minimum.
"""

from __future__ import annotations

import math
import sys

from shapely import wkt as W
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union
from shapely.strtree import STRtree

# Widths in metres.
SEAL = 0.20  # below this an opening is a tracing slit, not a door
TARGET = 0.90  # one leaf, wide open
DEPTH = 1.20  # cut deeper than any wall, so the throat opens along its length
SLIVER = 0.03  # obstacle fragments this small are cutting debris

# The front entrance is a vestibule, and the drawing traces only its outer
# opening: patrons passed the exterior double doors, crossed a ticket area, and
# went through a single interior door into the club. NIST NCSTAR 2 Vol. 1
# Table 7-6 dimensions both -- 1727 mm clear at the double doors, 914 mm at the
# interior door, which is the limiting element at 180 persons of code capacity:
# "the rate of egress ... was limited initially by the single doorway inside the
# vestibule, not the double doors visible from the outside". It was in this
# vestibule that the crowd-crush formed inside 90 s. Restoring the interior door
# is what keeps the front entrance from being the widest way out of the deck.
# The blocks below are wall, added after the doorways are opened: they narrow
# the traced outer opening to its clear width and close the inner end of the
# vestibule down to one door.
VESTIBULE_WALLS = (
    box(-1.25, -9.10, -1.108, -8.74),  # outer doors, west jamb
    box(0.619, -9.10, 0.76, -8.74),  # outer doors, east jamb
    box(-1.20, -5.60, -0.702, -5.40),  # interior door, west leaf
    box(0.212, -5.60, 0.70, -5.40),  # interior door, east leaf
)


def find_passages(walkable: Polygon, max_width: float) -> list[tuple]:
    """Every gap narrower than *max_width* between two facing walls.

    Returned as ``(width, point_a, point_b, midpoint)``, narrowest first and one
    entry per opening: a doorway shows up as a run of near-equal chords, so only
    the narrowest within 1.2 m survives.
    """
    rings = [walkable.exterior, *walkable.interiors]
    points, tags = _sample_rings(rings)
    tree = STRtree(points)
    found = []
    for i, p in enumerate(points):
        j = _closest_facing(walkable, tree, points, tags, rings, i, max_width)
        if j is not None:
            found.append((p.distance(points[j]), p, points[j]))
    return _dedupe(sorted(found, key=lambda t: t[0]))


def _sample_rings(rings) -> tuple[list[Point], list[tuple[int, float]]]:
    points, tags = [], []
    for index, ring in enumerate(rings):
        length = ring.length
        count = max(8, int(length / 0.07))
        for step in range(count):
            position = length * step / count
            points.append(ring.interpolate(position))
            tags.append((index, position))
    return points, tags


def _closest_facing(walkable, tree, points, tags, rings, i, max_width) -> int | None:
    """Index of the nearest boundary point across open floor from ``points[i]``."""
    best = None
    for j in tree.query(points[i].buffer(max_width)):
        if j <= i or _same_stretch_of_wall(tags, rings, i, j):
            continue
        span = LineString([points[i], points[j]])
        if span.length > max_width or not span.within(walkable.buffer(1e-9)):
            continue
        if best is None or span.length < best[1]:
            best = (j, span.length)
    return None if best is None else best[0]


def _same_stretch_of_wall(tags, rings, i, j) -> bool:
    """True when both points sit on one wall, where a chord means a corner."""
    ring_i, along_i = tags[i]
    ring_j, along_j = tags[j]
    if ring_i != ring_j:
        return False
    length = rings[ring_i].length
    gap = abs(along_i - along_j)
    return min(gap, length - gap) < 2.0


def _dedupe(passages: list[tuple]) -> list[tuple]:
    kept = []
    for width, a, b in passages:
        middle = Point((a.x + b.x) / 2, (a.y + b.y) / 2)
        if any(middle.distance(k[3]) < 1.2 for k in kept):
            continue
        kept.append((width, a, b, middle))
    return kept


def _patch(middle: Point, a: Point, b: Point, length: float, depth: float) -> Polygon:
    """A rectangle spanning the opening, *depth* deep through the wall."""
    norm = math.hypot(b.x - a.x, b.y - a.y)
    ux, uy = (b.x - a.x) / norm, (b.y - a.y) / norm
    hx, hy = ux * length / 2, uy * length / 2
    px, py = -uy * depth / 2, ux * depth / 2
    return Polygon(
        [
            (middle.x - hx - px, middle.y - hy - py),
            (middle.x + hx - px, middle.y + hy - py),
            (middle.x + hx + px, middle.y + hy + py),
            (middle.x - hx + px, middle.y - hy + py),
        ]
    )


def _rebuild(walkable: Polygon, obstacles: list[Polygon]) -> Polygon:
    kept = [o for o in obstacles if o.area > SLIVER]
    return Polygon(walkable.exterior, [o.exterior for o in kept])


def add_walls(walkable: Polygon, patches: list[Polygon]) -> Polygon:
    """Merge *patches* into the obstacles, so they become wall."""
    if not patches:
        return walkable
    merged = unary_union([Polygon(r) for r in walkable.interiors] + patches)
    parts = list(merged.geoms) if merged.geom_type == "MultiPolygon" else [merged]
    return _rebuild(walkable, parts)


def seal(walkable: Polygon, passages: list[tuple]) -> Polygon:
    """Close the gaps left where two wall strokes failed to meet."""
    patches = [_patch(m, a, b, w + 0.30, 0.30) for w, a, b, m in passages if w < SEAL]
    return add_walls(walkable, patches)


def widen(walkable: Polygon, patches: list[Polygon]) -> Polygon:
    """Cut *patches* out of whichever obstacles they overlap."""
    if not patches:
        return walkable
    cut = unary_union(patches)
    opened = []
    for obstacle in (Polygon(r) for r in walkable.interiors):
        remainder = obstacle.difference(cut)
        if remainder.is_empty:
            continue
        opened.extend(
            list(remainder.geoms)
            if remainder.geom_type == "MultiPolygon"
            else [remainder]
        )
    return _rebuild(walkable, opened)


def open_doors(walkable: Polygon, rounds: int = 5) -> Polygon:
    """Seal the slits, then widen until nothing is under :data:`TARGET`.

    Widening is iterative because a doorway is a throat, not a point: opening it
    at its narrowest chord can leave the next chord along the wall still tight.
    """
    walkable = seal(walkable, find_passages(walkable, 1.05))
    for _ in range(rounds):
        passages = find_passages(walkable, TARGET - 0.005)
        if not passages:
            # The vestibule goes in last: both its doors are wider than TARGET,
            # so widening leaves them alone, but building it first would not.
            return add_walls(walkable, list(VESTIBULE_WALLS))
        walkable = widen(
            walkable,
            [_patch(m, a, b, TARGET + 0.03, DEPTH) for _, a, b, m in passages],
        )
    raise SystemExit(f"still below {TARGET} m after {rounds} rounds")


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        raise SystemExit(__doc__)
    source = W.loads(open(argv[1]).read())
    opened = open_doors(source)
    if not opened.is_valid:
        raise SystemExit("result is not a valid polygon")
    open(argv[2], "w").write(opened.wkt + "\n")
    print(
        f"walkable {source.area:.2f} -> {opened.area:.2f} m2, "
        f"{len(opened.interiors)} obstacles"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
