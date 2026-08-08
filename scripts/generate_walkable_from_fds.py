#!/usr/bin/env python3
"""Derive a JuPedSim walkable area from the obstructions in an FDS deck.

An FDS deck describes solids; JuPedSim wants the space between them. This
subtracts every obstruction that blocks an upright occupant from the mesh
footprint, keeps the interior, and writes it as WKT.

Two things about the FDS format cost real time if you get them wrong:

``XB`` is ``x0,x1,y0,y1,z0,z1``
    Pairs by axis, not corner-then-corner. Reading it the obvious way turns a
    0.1 m wall into a 900 m² rectangle, and every layer then appears to cover
    most of the domain.

Obstructions may be zero-thickness
    A wall with ``x0 == x1`` is a legitimate FDS thin obstruction. ``box()`` on
    it is degenerate and ``buffer()`` of the invalid result yields garbage that
    unions into hundreds of square metres. The degenerate axis has to be
    widened explicitly, by half a grid cell.

What blocks and what does not is decided by the CAD layer name each ``&OBST``
carries as a trailing comment (``A-WALL-MAIN``, ``A-CASE-CABN``, ...). Only
horizontal finishes -- floors, ceilings, carpet, stair treads -- are treated as
free. Bars, counters, handrails, platforms and fixtures are obstacles, and come
out as holes in the polygon.

Door leaves are **not** obstacles. JuPedSim has no door concept: a doorway is
absence of wall, and whether an opening is usable is expressed by the exit
stages placed later, not by the geometry.

Usage:
    .venv/bin/python scripts/generate_walkable_from_fds.py DECK.fds -o out.wkt \
        [--z-band 0.1 1.8] [--min-hole 0.25] [--plot out.png]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from shapely.geometry import Polygon, box
from shapely.ops import unary_union

# Layers that never obstruct an upright occupant: horizontal surfaces you stand
# on rather than walk into. Stair treads and risers belong here -- a staircase is
# walkable -- as do the platform tops.
#
# Platform rims and handrails are here too, and that is a modelling decision
# rather than an observation. A handrail is a real barrier at 0.15-1.06 m, and
# leaving it solid cuts the raised platform off entirely: 374.7 m2 walkable with
# 37 m2 of platform unreachable. But a 2-D walkable area cannot represent the
# stair opening in a railing, or the level change the railing exists to guard,
# so the choice is between a platform nobody can leave and a platform edge that
# can be crossed anywhere. Occupants demonstrably stood on the Station's back
# wall platform and got off it, so an unreachable platform is the worse error.
#
# The consequence, stated so it is not discovered later: agents may cross the
# platform edge at any point, not only at the stairs the plan shows.
# Matched case-insensitively, like OPENINGS: this deck writes both "CARPET"
# (10 obstructions) and "carpet" (9), and a case-sensitive test silently blocks
# whichever casing is not listed.
HORIZONTAL_FINISHES = (
    "a-flor",
    "a-ceil",
    "a-strs-tred",
    "a-risr",
    "carpet",
    "a-plat-rim",
    "a-hral",
)
# Door leaves are openings, not walls -- see the module docstring. Matched on a
# *substring*, case-insensitively, because a hand-edited deck names doors both
# ways: the Station model carries the CAD layer "A-DOOR-STND-1" alongside
# free-text "door 5i", "back door qqq" and "FRONT DOOR". A prefix rule caught
# only the former and left an interior door sealing a whole wing.
OPENINGS = ("door",)

# Everything else blocks. The judgement calls, and why they fall this way for
# the Station deck (run with --report to re-check on any other deck):
#
#   A-PLAT-RIM   0.9 m2   platform *edges*, not their surfaces; blocking them
#                         outlines a platform without sealing it
#   A-HRAL-*     3.7 m2   handrails, balusters, newel posts -- you cannot walk
#                         through a railing
#   A-FIXT-MAIN  5.4 m2   fixtures at 0.6-2.2 m, mostly wall-mounted and so
#                         already inside a wall footprint
#   A-WDWK-TRIM  5.9 m2   mouldings, likewise mounted on walls
#
# 16 m2 of 312 between them, so the classification is not load-bearing for the
# area -- but --report makes it checkable rather than a matter of trust.

_XB = re.compile(r"XB\s*=\s*([-\d.eE+]+(?:\s*,\s*[-\d.eE+]+){5})")
_BAR = re.compile(r"(XBAR0|XBAR|YBAR0|YBAR|ZBAR0|ZBAR)\s*=\s*([-\d.eE+]+)")


def parse_deck(path: Path):
    """Return (mesh footprints, [(layer_name, x0, x1, y0, y1, z0, z1), ...])."""
    meshes: list[Polygon] = []
    obstructions: list[tuple[str, float, float, float, float, float, float]] = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if line.startswith("&PDIM"):  # FDS 4 domain; &MESH in FDS 5+
            g = dict(_BAR.findall(line))
            meshes.append(
                box(
                    float(g["XBAR0"]),
                    float(g["YBAR0"]),
                    float(g["XBAR"]),
                    float(g["YBAR"]),
                )
            )
        elif line.startswith("&MESH"):
            m = _XB.search(line)
            if m:
                v = [float(t) for t in m.group(1).split(",")]
                meshes.append(box(v[0], v[2], v[1], v[3]))
        elif line.startswith("&OBST"):
            m = _XB.search(line)
            if m is None:
                continue
            v = [float(t) for t in m.group(1).split(",")]
            name = line.split("/")[-1].strip() or "?"
            obstructions.append((name, *v))
    return meshes, obstructions


def blocks(name: str) -> bool:
    lowered = name.lower()
    if any(p in lowered for p in OPENINGS):
        return False
    return not any(p in lowered for p in HORIZONTAL_FINISHES)


def footprint(x0: float, x1: float, y0: float, y1: float, half_cell: float):
    """Plan footprint, giving a zero-thickness obstruction real substance."""
    lo_x, hi_x = sorted((x0, x1))
    lo_y, hi_y = sorted((y0, y1))
    if hi_x - lo_x < 1e-9:
        lo_x, hi_x = lo_x - half_cell, hi_x + half_cell
    if hi_y - lo_y < 1e-9:
        lo_y, hi_y = lo_y - half_cell, hi_y + half_cell
    return box(lo_x, lo_y, hi_x, hi_y)


def drop_small_holes(polygon: Polygon, min_area: float) -> Polygon:
    """Fill interior rings below *min_area*, which are grid noise, not obstacles."""
    keep = [r for r in polygon.interiors if Polygon(r).area >= min_area]
    if len(keep) == len(polygon.interiors):
        return polygon
    return Polygon(polygon.exterior, keep)


def is_door(name: str) -> bool:
    return any(p in name.lower() for p in OPENINGS)


def exterior_doors(domain, walls, doors, tolerance: float = 0.15) -> set[int]:
    """Indices of the doors that lead outdoors rather than between rooms.

    Both must be told apart, and neither name nor CAD layer distinguishes them.
    An *interior* door has to open, or a single leaf seals a whole wing off from
    the rest of the building. An *exterior* door has to stay shut, or the
    walkable area leaks out of the envelope and swallows the site around it --
    which is precisely what happens if every door is opened: the interior stops
    being the largest enclosed region and the extraction collapses.

    The test is positional, not nominal: seal every door, find the outdoors as
    the free region touching the mesh edge, and call a door exterior when it
    fronts onto that region.
    """
    sealed = domain.difference(unary_union(walls + [d for _, d in doors]))
    outside = [
        part
        for part in getattr(sealed, "geoms", [sealed])
        if part.exterior.intersects(domain.boundary)
    ]
    if not outside:
        return set()
    outdoors = unary_union(outside)
    return {
        index
        for index, (_, shape) in enumerate(doors)
        if shape.buffer(tolerance).intersects(outdoors)
    }


def extract(deck: Path, z_lo: float, z_hi: float, half_cell: float, min_hole: float):
    meshes, obstructions = parse_deck(deck)
    if not meshes:
        raise SystemExit(f"{deck}: no &PDIM or &MESH found; is this an FDS deck?")

    in_band = [
        (name, footprint(x0, x1, y0, y1, half_cell))
        for name, x0, x1, y0, y1, z0, z1 in obstructions
        if z1 >= z_lo and z0 <= z_hi and not is_door(name)
    ]
    walls = [shape for name, shape in in_band if blocks(name)]
    doors = [
        (name, footprint(x0, x1, y0, y1, half_cell))
        for name, x0, x1, y0, y1, z0, z1 in obstructions
        if z1 >= z_lo and z0 <= z_hi and is_door(name)
    ]

    domain = unary_union(meshes)
    outer = exterior_doors(domain, walls, doors)
    solids = walls + [shape for index, (_, shape) in enumerate(doors) if index in outer]
    free = domain.difference(unary_union(solids))
    _report_doors = (len(doors), len(outer))
    parts = sorted(getattr(free, "geoms", [free]), key=lambda g: -g.area)

    # The mesh extends past the building, so the free space splits into the
    # interior and the outdoors around it. The interior is the part that does
    # not touch the domain boundary; the outdoors necessarily does.
    edge = domain.boundary
    interior = [p for p in parts if not p.exterior.intersects(edge)]
    if not interior:
        raise SystemExit(
            "every free region touches the domain edge, so the interior cannot "
            "be told from the outdoors -- check the z band and the layer rules"
        )
    walkable = drop_small_holes(interior[0], min_hole)
    return walkable, parts, len(solids), domain, _report_doors


def layer_report(deck: Path, z_lo: float, z_hi: float, half_cell: float):
    """Per-layer blocked footprint, so the classification can be audited."""
    from collections import defaultdict

    _, obstructions = parse_deck(deck)
    grouped: dict[tuple[str, bool], list] = defaultdict(list)
    spans: dict[str, list[float]] = {}
    for name, x0, x1, y0, y1, z0, z1 in obstructions:
        layer = name.rstrip("0123456789").strip() or "?"
        span = spans.setdefault(layer, [z0, z1])
        span[0], span[1] = min(span[0], z0), max(span[1], z1)
        if z1 < z_lo or z0 > z_hi:
            continue
        grouped[(layer, blocks(name))].append(footprint(x0, x1, y0, y1, half_cell))

    rows = [
        (unary_union(v).area, layer, blocking, len(v))
        for (layer, blocking), v in grouped.items()
    ]
    print(f"\n{'layer':26s} {'n':>5s} {'footprint':>12s}  {'z range':>14s}  verdict")
    for area, layer, blocking, count in sorted(rows, reverse=True):
        lo, hi = spans[layer]
        verdict = "blocks" if blocking else "free"
        print(f"{layer:26s} {count:5d} {area:9.1f} m2  {lo:6.2f}..{hi:5.2f}  {verdict}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("deck", type=Path)
    parser.add_argument("-o", "--out", type=Path, required=True)
    parser.add_argument(
        "--z-band",
        nargs=2,
        type=float,
        default=(0.1, 1.8),
        metavar=("LO", "HI"),
        help="height band an upright occupant occupies (default 0.1 1.8)",
    )
    parser.add_argument(
        "--half-cell",
        type=float,
        default=0.05,
        help="half the grid spacing, used to widen zero-thickness obstructions",
    )
    parser.add_argument(
        "--min-hole",
        type=float,
        default=0.25,
        help="interior rings smaller than this (m2) are grid noise and are filled",
    )
    parser.add_argument("--plot", type=Path, default=None)
    parser.add_argument(
        "--report",
        action="store_true",
        help="print the per-layer blocked footprint and blocking verdict",
    )
    args = parser.parse_args()

    walkable, parts, n_solids, domain, doors = extract(
        args.deck, args.z_band[0], args.z_band[1], args.half_cell, args.min_hole
    )

    print(
        f"{args.deck.name}: {n_solids} blocking obstructions in "
        f"z=[{args.z_band[0]}, {args.z_band[1]}]"
    )
    print(f"  domain      {domain.area:8.1f} m2")
    print(
        f"  doors       {doors[0]} in band; {doors[1]} front onto the outdoors "
        f"and stay shut, {doors[0] - doors[1]} interior ones open"
    )
    print(f"  free space  {len(parts)} regions; interior kept")
    print(
        f"  walkable    {walkable.area:8.1f} m2  with {len(walkable.interiors)} holes"
    )
    print(f"  valid: {walkable.is_valid}")

    if args.report:
        layer_report(args.deck, args.z_band[0], args.z_band[1], args.half_cell)

    args.out.write_text(walkable.wkt + "\n", encoding="utf-8")
    print(f"\nWrote {args.out}")

    if args.plot:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt  # noqa: E402
        from matplotlib.patches import PathPatch
        from matplotlib.path import Path as MplPath

        # Draw the polygon as a single path with the holes as reversed subpaths,
        # not as a filled exterior with the holes painted over. Filling the
        # exterior ring alone also fills every concavity -- which once made a
        # bar that *is* excluded look as though it were part of the floor.
        vertices, codes = [], []
        for ring, reverse in [(walkable.exterior, False)] + [
            (r, True) for r in walkable.interiors
        ]:
            coords = list(ring.coords)[::-1] if reverse else list(ring.coords)
            vertices.extend(coords)
            codes.extend(
                [MplPath.MOVETO]
                + [MplPath.LINETO] * (len(coords) - 2)
                + [MplPath.CLOSEPOLY]
            )
        ax_path = MplPath(vertices, codes)
        fig, ax = plt.subplots(figsize=(11, 8))
        ax.add_patch(
            PathPatch(ax_path, facecolor="#2b7bba", alpha=0.5, edgecolor="#1f4e79")
        )
        for ring in walkable.interiors:
            ax.plot(*ring.xy, color="#d94801", lw=1.0)
        bounds = walkable.bounds
        ax.set_xlim(bounds[0] - 1, bounds[2] + 1)
        ax.set_ylim(bounds[1] - 1, bounds[3] + 1)
        ax.set_aspect("equal")
        ax.set_title(
            f"{args.deck.stem}: walkable {walkable.area:.0f} m2, "
            f"{len(walkable.interiors)} obstacles"
        )
        fig.tight_layout()
        fig.savefig(args.plot, dpi=130)
        print(f"Wrote {args.plot}")


if __name__ == "__main__":
    sys.exit(main())
