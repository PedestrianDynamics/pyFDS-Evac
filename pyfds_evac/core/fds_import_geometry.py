"""Plane geometry for the FDS deck importer (shapely only).

All coordinates stay in the FDS frame: no translation, rotation or scaling.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from shapely.geometry import LineString, MultiPolygon, Polygon, box
from shapely.ops import split, unary_union

#: Exit strips narrower than this along the exit line are dropped [m].
MIN_EXIT_WIDTH_M = 0.1
_EPS = 1e-9


@dataclass(frozen=True)
class ExitLine:
    """An axis-aligned exit line with the unit normal into the room."""

    x0: float
    y0: float
    x1: float
    y1: float
    normal: tuple[float, float]

    @property
    def line(self) -> LineString:
        return LineString([(self.x0, self.y0), (self.x1, self.y1)])

    @property
    def width(self) -> float:
        return math.hypot(self.x1 - self.x0, self.y1 - self.y0)


def ior_normal(ior: int) -> tuple[float, float]:
    """Unit vector along ``IOR`` (±1 x, ±2 y)."""
    axis = abs(int(ior))
    if axis not in (1, 2):
        raise ValueError(f"IOR must be ±1 or ±2 for a vertical exit, got {ior}")
    sign = 1.0 if ior > 0 else -1.0
    return (sign, 0.0) if axis == 1 else (0.0, sign)


def line_from_xb(xb: tuple, ior: int | None) -> tuple[float, float, float, float]:
    """The plan segment of a vertical plane ``XB``; ValueError if not a plane."""
    x0, x1, y0, y1 = xb[:4]
    flat_x, flat_y = abs(x1 - x0) < _EPS, abs(y1 - y0) < _EPS
    if ior is not None and abs(int(ior)) == 1 and not flat_x:
        raise ValueError(f"IOR={ior} needs x0 == x1 in XB, got {x0:g}..{x1:g}")
    if ior is not None and abs(int(ior)) == 2 and not flat_y:
        raise ValueError(f"IOR={ior} needs y0 == y1 in XB, got {y0:g}..{y1:g}")
    if flat_x == flat_y:
        raise ValueError(f"XB is not a vertical plane: {xb[:4]}")
    return (x0, y0, x0, y1) if flat_x else (x0, y0, x1, y0)


def strip_box(line: ExitLine, depth: float) -> Polygon:
    """Rectangle on *line* extended *depth* along its normal."""
    nx, ny = line.normal
    xs = (line.x0, line.x1, line.x0 + nx * depth, line.x1 + nx * depth)
    ys = (line.y0, line.y1, line.y0 + ny * depth, line.y1 + ny * depth)
    return box(min(xs), min(ys), max(xs), max(ys))


def exit_strip(line: ExitLine, depth: float, walkable) -> Polygon | None:
    """Rule E1: the strip on the room side, clipped to the walkable area.

    Returns the largest piece, or None when the strip is empty or narrower
    than :data:`MIN_EXIT_WIDTH_M` along the line.
    """
    piece = largest_polygon(strip_box(line, depth).intersection(walkable))
    if piece is None or piece.area <= _EPS:
        return None
    if _width_along(piece, line) < MIN_EXIT_WIDTH_M:
        return None
    return piece


def _width_along(piece: Polygon, line: ExitLine) -> float:
    minx, miny, maxx, maxy = piece.bounds
    return maxy - miny if abs(line.normal[0]) > 0 else maxx - minx


def largest_polygon(geometry) -> Polygon | None:
    """The largest polygon of *geometry*, or None if it has no area."""
    polygons = polygons_of(geometry)
    return max(polygons, key=lambda p: p.area) if polygons else None


def polygons_of(geometry) -> list[Polygon]:
    """The polygons of any shapely geometry, largest first, ties by bounds."""
    if geometry is None or geometry.is_empty:
        return []
    if isinstance(geometry, Polygon):
        return [geometry]
    parts = [g for part in getattr(geometry, "geoms", []) for g in polygons_of(part)]
    return sorted(parts, key=lambda p: (-p.area, p.bounds))


def split_holes(polygon: Polygon) -> list[Polygon]:
    """Split *polygon* into hole-free pieces with vertical cuts.

    Each cut runs through the centre of a hole, which turns that hole into
    two notches; the union of the pieces is *polygon*.
    """
    pending, done = [polygon], []
    while pending:
        piece = pending.pop()
        if not piece.interiors:
            done.append(piece)
            continue
        pending.extend(_cut_at_hole(piece))
    return sorted(done, key=lambda p: p.bounds)


def _cut_at_hole(piece: Polygon) -> list[Polygon]:
    hole = Polygon(piece.interiors[0])
    x = hole.centroid.x
    _, miny, _, maxy = piece.bounds
    cutter = LineString([(x, miny - 1.0), (x, maxy + 1.0)])
    return polygons_of(split(piece, cutter))


def largest_remainder(total: int, weights: list[float]) -> list[int]:
    """Share *total* by *weights*; the parts sum to *total* exactly.

    Ties in the remainder go to the earlier entry.
    """
    weight_sum = sum(weights)
    if total <= 0 or weight_sum <= 0:
        return [0] * len(weights)
    quotas = [total * w / weight_sum for w in weights]
    shares = [math.floor(q) for q in quotas]
    order = sorted(range(len(weights)), key=lambda i: (-(quotas[i] - shares[i]), i))
    for index in order[: total - sum(shares)]:
        shares[index] += 1
    return shares


def ring_coordinates(polygon: Polygon) -> list[list[float]]:
    """Exterior ring of *polygon*, closed, rounded to 1e-6 m."""
    return [[rounded(x), rounded(y)] for x, y in polygon.exterior.coords]


def rounded(value: float) -> float:
    """Round to 1e-6 and turn -0.0 into 0.0, for byte-stable output."""
    return round(float(value), 6) + 0.0


def union(polygons: list) -> Polygon | MultiPolygon:
    return unary_union(polygons)
