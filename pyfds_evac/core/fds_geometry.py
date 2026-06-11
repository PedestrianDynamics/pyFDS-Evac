"""Derive a JuPedSim walkable-area WKT directly from an FDS case.

Authoring the FDS deck and the JuPedSim ``geometry.wkt`` independently lets the
two geometries silently diverge (offset origin, swapped x/y, a wall in one but
not the other) -- see GitHub issue #26.  Generating the WKT *from* the FDS
``&MESH``/``&OBST`` geometry makes them share one coordinate frame by
construction, eliminating that class of mismatch.

Approach (2-D projection at the walking height):

1. Domain footprint = union of every mesh's ``(x, y)`` rectangle.
2. Wall footprint = union of every obstruction that spans the walking-height
   band, projected to ``(x, y)``.  FDS thin walls have **zero** 2-D thickness
   (``x_start == x_end`` or ``y_start == y_end``); they are buffered to
   ``wall_thickness`` so they register as barriers rather than vanishing.
3. Walkable area = domain minus walls.

The two modelling choices are explicit parameters: ``walk_height_band`` (which
obstructions count as walls -- a full-height wall does, an overhead beam does
not) and ``wall_thickness`` (the width given to zero-thickness FDS walls).

Known limitation (prototype): this uses each obstruction's *bounding box*
(``obst.bounding_box``).  When a wall and its doorway are a single ``&OBST`` id,
or a doorway is cut with ``&HOLE``, the bounding box spans the gap and wrongly
seals the passage -- yielding a disconnected ``MultiPolygon``.  The production
fix is per-cell occupancy via ``mesh.get_obstruction_mask(times)`` at the
walking height, polygonised into the void footprint (issue #26).
"""

from __future__ import annotations

from shapely.geometry import MultiPolygon, Polygon, box
from shapely.ops import unary_union

try:
    from fdsreader import Simulation
except ModuleNotFoundError:  # pragma: no cover - exercised only without fdsreader
    Simulation = None


def _extent_xy_box(extent) -> Polygon:
    """Project an fdsreader ``Extent`` to its ``(x, y)`` rectangle."""
    return box(extent.x_start, extent.y_start, extent.x_end, extent.y_end)


def _wall_footprint(extent, wall_thickness: float) -> Polygon | None:
    """Return the 2-D footprint of one obstruction, or ``None`` if degenerate.

    Zero-thickness FDS walls (a line in plan view) are buffered to
    ``wall_thickness`` with flat caps so they become thin barriers.
    """
    dx = extent.x_end - extent.x_start
    dy = extent.y_end - extent.y_start
    if dx > 0 and dy > 0:
        return _extent_xy_box(extent)
    if dx == 0 and dy == 0:
        return None  # a point obstruction has no wall in plan view
    # A line: buffer it to a thin rectangle along its run.
    half = wall_thickness / 2.0
    return _extent_xy_box(extent).buffer(half, cap_style="flat")


def _spans_height(extent, low: float, high: float) -> bool:
    """True if the obstruction's z-range overlaps the walking band [low, high]."""
    return extent.z_start < high and extent.z_end > low


def walkable_polygon_from_fds(
    fds_dir: str,
    *,
    walk_height_band: tuple[float, float] = (0.0, 1.8),
    wall_thickness: float = 0.2,
    simulation=None,
):
    """Build the JuPedSim walkable area as a Shapely polygon from FDS geometry.

    Parameters
    ----------
    walk_height_band:
        ``(low, high)`` in metres.  Only obstructions whose z-range overlaps
        this band are treated as walls, so overhead obstructions are ignored.
    wall_thickness:
        Width assigned to zero-thickness FDS walls so they become barriers.

    Returns a ``Polygon`` (or ``MultiPolygon`` if walls disconnect the domain).
    """
    if simulation is not None:
        sim = simulation
    elif Simulation is not None:
        sim = Simulation(str(fds_dir))
    else:  # pragma: no cover
        raise ModuleNotFoundError("fdsreader is required to read FDS geometry.")

    low, high = walk_height_band
    domain = unary_union([_extent_xy_box(m.extent) for m in sim.meshes])

    walls = [
        footprint
        for ob in sim.obstructions
        if _spans_height(ob.bounding_box, low, high)
        for footprint in (_wall_footprint(ob.bounding_box, wall_thickness),)
        if footprint is not None
    ]
    if not walls:
        return domain

    walkable = domain.difference(unary_union(walls))
    if not walkable.is_valid:
        walkable = walkable.buffer(0)
    return walkable


def largest_polygon(geometry) -> Polygon:
    """Return the largest connected component (JuPedSim needs one polygon)."""
    if isinstance(geometry, MultiPolygon):
        return max(geometry.geoms, key=lambda g: g.area)
    return geometry


def walkable_wkt_from_fds(
    fds_dir: str,
    *,
    walk_height_band: tuple[float, float] = (0.0, 1.8),
    wall_thickness: float = 0.2,
    keep_largest: bool = True,
    simplify_tolerance: float = 0.0,
    simulation=None,
) -> str:
    """Return the walkable area as a WKT ``POLYGON`` string in the FDS frame."""
    walkable = walkable_polygon_from_fds(
        fds_dir,
        walk_height_band=walk_height_band,
        wall_thickness=wall_thickness,
        simulation=simulation,
    )
    if keep_largest:
        walkable = largest_polygon(walkable)
    if simplify_tolerance > 0:
        walkable = walkable.simplify(simplify_tolerance, preserve_topology=True)
    return walkable.wkt


if __name__ == "__main__":  # pragma: no cover
    import argparse

    parser = argparse.ArgumentParser(description="Derive a walkable WKT from FDS.")
    parser.add_argument("fds_dir", help="FDS case directory (containing the .smv)")
    parser.add_argument("--walk-low", type=float, default=0.0)
    parser.add_argument("--walk-high", type=float, default=1.8)
    parser.add_argument("--wall-thickness", type=float, default=0.2)
    args = parser.parse_args()
    print(
        walkable_wkt_from_fds(
            args.fds_dir,
            walk_height_band=(args.walk_low, args.walk_high),
            wall_thickness=args.wall_thickness,
        )
    )
