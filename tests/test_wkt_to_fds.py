"""Tests for generating an FDS geometry deck from a walkable-area WKT.

The core invariant is the round-trip: the generated ``&OBST`` walls must be the
exact complement of the walkable area, so no wall ever covers walkable space and
the whole walkable boundary is enclosed.
"""

from __future__ import annotations

import numpy as np
from shapely.geometry import Point

from pyfds_evac.core.wkt_to_fds import _load_walkable, _obst_boxes, wkt_to_fds

# An L-shaped room with a doorway gap, exterior-only.
L_ROOM_WKT = "POLYGON ((0 0, 6 0, 6 4, 10 4, 10 10, 0 10, 0 0))"
# A square room with a square obstacle (hole) in the middle.
HOLE_WKT = "POLYGON ((0 0, 10 0, 10 10, 0 10, 0 0), (4 4, 6 4, 6 6, 4 6, 4 4))"


def _covered(boxes, x, y) -> bool:
    return any(x0 < x < x1 and y0 < y < y1 for (x0, x1, y0, y1) in boxes)


def test_walls_never_cover_walkable_interior():
    """No generated OBST may contain a point inside the walkable area."""
    walk = _load_walkable(L_ROOM_WKT)
    boxes, _ = _obst_boxes(walk, 0.25, 1)
    minx, miny, maxx, maxy = walk.bounds
    rng = np.random.RandomState(0)
    checked = 0
    while checked < 2000:
        x, y = rng.uniform(minx, maxx), rng.uniform(miny, maxy)
        if not walk.contains(Point(x, y)):
            continue
        checked += 1
        assert not _covered(boxes, x, y), (
            f"wall covers walkable point ({x:.2f}, {y:.2f})"
        )


def test_obstacle_hole_becomes_solid():
    """A hole in the walkable polygon must be filled by wall OBSTs."""
    walk = _load_walkable(HOLE_WKT)
    boxes, _ = _obst_boxes(walk, 0.25, 1)
    # Centre of the hole (5, 5) is non-walkable -> must be covered by a wall.
    assert _covered(boxes, 5.0, 5.0)
    # A point in the open room is walkable -> must not be covered.
    assert not _covered(boxes, 1.0, 1.0)


def test_mesh_encloses_walkable_with_margin():
    """The mesh extent must contain the walkable bounds plus the wall margin."""
    walk = _load_walkable(L_ROOM_WKT)
    _, (mx0, my0, mx1, my1, ni, nj) = _obst_boxes(walk, 0.25, 1)
    bx0, by0, bx1, by1 = walk.bounds
    assert mx0 < bx0 and my0 < by0 and mx1 > bx1 and my1 > by1
    assert ni > 0 and nj > 0


def test_deck_has_required_sections_and_slices():
    """The full deck runs end-to-end: mesh, walls, fire, and the canonical slices."""
    deck = wkt_to_fds(L_ROOM_WKT, chid="t")
    assert "&HEAD CHID='t'" in deck
    assert "&MESH IJK=" in deck
    assert "&OBST XB=" in deck
    assert "&TAIL /" in deck
    for quantity in (
        "SOOT EXTINCTION COEFFICIENT",
        "CARBON MONOXIDE",
        "CARBON DIOXIDE",
        "OXYGEN",
    ):
        assert quantity in deck


def test_geometry_only_omits_fire():
    """``include_fire=False`` yields walls without a burner or slices."""
    deck = wkt_to_fds(L_ROOM_WKT, include_fire=False)
    assert "&OBST XB=" in deck
    assert "BURNER" not in deck
    assert "SLCF" not in deck
