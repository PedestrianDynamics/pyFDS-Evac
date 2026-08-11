"""Geometry helpers shared by the routing and visibility layers."""

from __future__ import annotations

import logging

_logger = logging.getLogger(__name__)


def node_position(polygon) -> tuple[float, float]:
    """The point that stands for a stage, guaranteed to lie inside it.

    Stages are polygons but every layer needs a single point for them: the
    route graph measures edge lengths between these points, and the
    visibility layer puts a node's default sign at one.  The obvious choice,
    the area centroid, is wrong for a non-convex polygon -- an L, a C, or a
    room wrapping around an obstruction -- where the area-weighted average
    lands in the concavity, off the shape entirely.

    A point that is not on the walkable floor breaks both callers:

    * routing asks the navmesh for a path from it, the navmesh rejects it as
      inaccessible, and the edge falls back to a straight ray whose length
      ignores every wall in between (four Station spawn areas hit this, and
      their route costs were straight-line distances);
    * visibility puts the node's sign inside a wall, where no agent can ever
      read it, so a discovery agent never learns that node exists.

    Both layers must also agree, or a node is routed to one point and seen
    from another.  Hence one helper, used by both.

    The centroid is kept whenever it is already interior, so node positions
    are unchanged for every well-behaved polygon and no calibration resting
    on them shifts silently.  ``representative_point`` is used only where the
    centroid is unusable: it is always interior, though not always central.
    """
    centroid = polygon.centroid
    try:
        if polygon.contains(centroid):
            return float(centroid.x), float(centroid.y)
        interior = polygon.representative_point()
    except Exception as exc:
        # A self-intersecting or degenerate polygon can refuse both queries.
        # The centroid is then no worse than aborting, and the stage setup
        # skips unusable polygons anyway.
        _logger.warning("Cannot place a node inside %s: %s", polygon.geom_type, exc)
        return float(centroid.x), float(centroid.y)
    _logger.debug(
        "Centroid of a %s lies outside it; using an interior point", polygon.geom_type
    )
    return float(interior.x), float(interior.y)
