"""Generate an FDS geometry deck from a JuPedSim walkable-area WKT.

The reverse of deriving a WKT from FDS (which is underdetermined -- the FDS
domain holds the navigable space *and* sealed compartments, and geometry alone
cannot say which is walkable).  Going WKT -> FDS has no such ambiguity: the WKT
*is* the walkable space, so the FDS solid region is simply its complement within
the mesh.  Generating the fire domain from the designed walkable area guarantees
the two share one coordinate frame -- the geometry-consistency goal (issue #26),
solved from the authoritative side.

Pipeline:

1. Parse the WKT walkable polygon (exterior = boundary, holes = obstacles).
2. Size an ``&MESH`` to the walkable bounds plus a wall margin, at cell size dx.
3. ``solid = mesh_rectangle - walkable``, rasterised onto the dx grid.
4. Decompose the solid cells into axis-aligned ``&OBST`` boxes (greedy maximal
   rectangles, to keep the obstruction count low).
5. Optionally append a fire + slice template so the deck runs end-to-end and
   writes the exact slices pyFDS-Evac reads (extinction + CO/CO2/O2).

What it does *not* infer: the fire itself (HRR, fuel) and the analysis outputs
are physics choices, not geometry; the template provides sensible defaults you
are expected to edit.
"""

from __future__ import annotations

import logging
import math

import numpy as np
from shapely import wkt as _wkt
from shapely.geometry import box
from shapely.geometry.base import BaseGeometry
from shapely.prepared import prep

_logger = logging.getLogger(__name__)

# Slices pyFDS-Evac canonicalises (see core/fds_inventory.py).
_FED_SPECIES = ("CARBON MONOXIDE", "CARBON DIOXIDE", "OXYGEN")

# Preferred cell size when auto-sizing; refined finer only to resolve thin walls.
_DEFAULT_DX = 0.25
# Floor on the auto-sized cell: stops a stray near-duplicate coordinate (e.g. a
# 0.01 m modelling artifact) from forcing a runaway-fine mesh.
_MIN_DX = 0.1


def _min_feature_width(walkable: BaseGeometry) -> float:
    """Smallest axis-aligned gap between vertex coordinates (the thinnest wall).

    For rectilinear floor plans a 0.1 m wall shows up as adjacent coordinates
    0.1 m apart (e.g. 5.0 and 5.1).  Returns ``inf`` for a plain rectangle with
    no internal features.  Used to pick a ``dx`` fine enough to resolve walls.
    """
    polys = list(getattr(walkable, "geoms", [walkable]))
    xs: set[float] = set()
    ys: set[float] = set()
    for poly in polys:
        for ring in [poly.exterior, *poly.interiors]:
            for x, y in ring.coords:
                xs.add(round(x, 9))
                ys.add(round(y, 9))
    return min(_min_gap(xs), _min_gap(ys))


def _min_gap(values) -> float:
    """Smallest positive difference between consecutive sorted values."""
    ordered = sorted(values)
    gaps = [b - a for a, b in zip(ordered, ordered[1:]) if b - a > 1e-9]
    return min(gaps) if gaps else math.inf


def _coord_decimals(dx: float) -> int:
    """Decimals needed to print dx-aligned coordinates without rounding drift.

    Coordinates are multiples of ``dx``; a fixed ``%.2f`` would corrupt a
    non-centimetre ``dx`` (e.g. 0.025 or 0.104), shifting walls or collapsing
    thin ``&OBST`` boxes to zero width.
    """
    if dx <= 0 or not math.isfinite(dx):
        return 2
    return min(6, max(2, -math.floor(math.log10(dx)) + 2))


def _load_walkable(wkt_or_polygon) -> BaseGeometry:
    """Accept a WKT string or a Shapely geometry; return the walkable area."""
    if isinstance(wkt_or_polygon, BaseGeometry):
        geometry = wkt_or_polygon
    else:
        geometry = _wkt.loads(str(wkt_or_polygon))
    if geometry.is_empty:
        raise ValueError("Walkable WKT is empty.")
    return geometry


def _mesh_grid(walkable: BaseGeometry, dx: float, margin_cells: int):
    """Return mesh extent and cell counts snapped to the dx grid with a margin."""
    x0, y0, x1, y1 = walkable.bounds
    mx0 = (math.floor(x0 / dx) - margin_cells) * dx
    my0 = (math.floor(y0 / dx) - margin_cells) * dx
    mx1 = (math.ceil(x1 / dx) + margin_cells) * dx
    my1 = (math.ceil(y1 / dx) + margin_cells) * dx
    ni = round((mx1 - mx0) / dx)
    nj = round((my1 - my0) / dx)
    return mx0, my0, mx1, my1, ni, nj


def _solid_mask(walkable, mx0, my0, ni, nj, dx) -> np.ndarray:
    """Boolean grid: True where a cell shares no area with the walkable area.

    A cell is walkable if it *overlaps* the walkable polygon (positive
    intersection area), not merely if its centre is inside.  Centre-sampling
    would seal a cell whose centre lands in a wall even though part of the cell
    is walkable, silently deleting narrow or off-grid passages; overlap keeps
    them open (a wall never covers a positive-area walkable region) at the cost
    of walls thinning by up to one cell -- the safe direction for an egress
    domain (never seal a corridor).
    """
    prepared = prep(walkable)
    solid = np.ones((ni, nj), dtype=bool)
    for i in range(ni):
        x0 = mx0 + i * dx
        for j in range(nj):
            y0 = my0 + j * dx
            cell = box(x0, y0, x0 + dx, y0 + dx)
            if not prepared.intersects(cell):
                continue  # fully outside walkable -> solid (fast path)
            if prepared.contains(cell):
                solid[i, j] = False  # fully inside -> walkable (fast path)
            elif walkable.intersection(cell).area > 1e-12:
                solid[i, j] = False  # boundary cell with real overlap (slow path)
    return solid


def _greedy_rectangles(solid: np.ndarray):
    """Decompose solid cells into axis-aligned rectangles (i0, i1, j0, j1).

    Greedy maximal rectangles: from each unused solid cell, grow as wide as the
    contiguous solid run, then as tall as every column in that span stays solid
    and unused.  Far fewer boxes than one-per-cell, valid for FDS ``&OBST``.
    """
    ni, nj = solid.shape
    used = np.zeros_like(solid)
    rects = []
    for i in range(ni):
        for j in range(nj):
            if not solid[i, j] or used[i, j]:
                continue
            width = 0
            while i + width < ni and solid[i + width, j] and not used[i + width, j]:
                width += 1
            height = 1
            while j + height < nj and _row_free(solid, used, i, width, j + height):
                height += 1
            used[i : i + width, j : j + height] = True
            rects.append((i, i + width, j, j + height))
    return rects


def _row_free(solid, used, i, width, j) -> bool:
    """True if cells [i:i+width] in column j are all solid and unused."""
    return bool(np.all(solid[i : i + width, j]) and not np.any(used[i : i + width, j]))


def _obst_boxes(walkable, dx, margin_cells):
    """Return wall ``&OBST`` boxes (x0, x1, y0, y1) plus mesh metadata."""
    mx0, my0, mx1, my1, ni, nj = _mesh_grid(walkable, dx, margin_cells)
    solid = _solid_mask(walkable, mx0, my0, ni, nj, dx)
    boxes = [
        (mx0 + i0 * dx, mx0 + i1 * dx, my0 + j0 * dx, my0 + j1 * dx)
        for (i0, i1, j0, j1) in _greedy_rectangles(solid)
    ]
    return boxes, (mx0, my0, mx1, my1, ni, nj)


def _fire_and_slices(walkable, slice_height_m, hrrpua, burner_size_m, z_max, nd) -> str:
    """A burner at the walkable centroid plus the slices pyFDS-Evac reads."""
    c = walkable.representative_point()
    half = burner_size_m / 2.0
    burner_top = min(0.4, z_max)  # keep the burner inside a shallow mesh
    lines = [
        "! --- fire (edit to taste; not derived from geometry) ---",
        "&REAC FUEL='PROPANE', SOOT_YIELD=0.06, CO_YIELD=0.01 /",
        f"&OBST XB={c.x - half:.{nd}f},{c.x + half:.{nd}f},{c.y - half:.{nd}f},"
        f"{c.y + half:.{nd}f},0.0,{burner_top}, SURF_IDS='BURNER','INERT','INERT' /",
        f"&SURF ID='BURNER', HRRPUA={hrrpua:.1f}, COLOR='RED', RAMP_Q='qramp' /",
        "&RAMP ID='qramp', T=0.0, F=0.0 /",
        "&RAMP ID='qramp', T=10.0, F=1.0 /",
        "",
        f"! --- analysis slices at z={slice_height_m} m (pyFDS-Evac quantities) ---",
        f"&SLCF PBZ={slice_height_m}, QUANTITY='SOOT EXTINCTION COEFFICIENT' /",
    ]
    for spec in _FED_SPECIES:
        lines.append(
            f"&SLCF PBZ={slice_height_m}, QUANTITY='VOLUME FRACTION', SPEC_ID='{spec}' /"
        )
    lines.append("&DUMP DT_SLCF=2.0 /")
    return "\n".join(lines)


def resolve_dx(walkable: BaseGeometry, dx: float | None) -> float:
    """Choose a cell size that resolves the thinnest wall.

    ``dx=None`` auto-sizes to ``min(_DEFAULT_DX, thinnest_wall)`` so a coarse fire
    grid is used unless walls demand finer.  An explicit ``dx`` coarser than the
    thinnest wall is honoured but warned about: walls thinner than ``dx`` are
    silently dropped (cells are kept walkable on any overlap).
    """
    min_feat = _min_feature_width(walkable)
    if dx is None:
        if math.isinf(min_feat):
            return _DEFAULT_DX
        if min_feat < _MIN_DX - 1e-9:
            _logger.warning(
                "thinnest feature %.3g m is below the %.3g m floor; walls thinner "
                "than %.3g m may not resolve.",
                min_feat,
                _MIN_DX,
                _MIN_DX,
            )
        return max(min(_DEFAULT_DX, min_feat), _MIN_DX)
    if math.isfinite(min_feat) and dx > min_feat + 1e-9:
        _logger.warning(
            "dx=%.3g m is coarser than the thinnest wall (%.3g m); walls thinner "
            "than dx are dropped. Pass dx<=%.3g (or dx=None to auto-size).",
            dx,
            min_feat,
            min_feat,
        )
    return dx


def wkt_to_fds(
    wkt_or_polygon,
    *,
    dx: float | None = None,
    z_max: float = 3.0,
    chid: str = "from_wkt",
    margin_cells: int = 1,
    include_fire: bool = True,
    slice_height_m: float = 2.0,
    hrrpua: float = 800.0,
    burner_size_m: float = 0.5,
    t_end: float = 120.0,
) -> str:
    """Return an FDS input deck whose walkable void matches the given WKT.

    ``dx=None`` (default) auto-sizes the cell to resolve the thinnest wall; an
    explicit ``dx`` coarser than that is warned about (thin walls drop).  With
    ``include_fire`` (default) a burner and the pyFDS-Evac analysis slices
    (extinction + CO/CO2/O2) are appended so the deck runs end-to-end; set it
    False for a geometry-only deck (``&MESH`` + ``&OBST`` walls).
    """
    if include_fire and slice_height_m >= z_max:
        raise ValueError(
            f"slice_height_m ({slice_height_m} m) must be below z_max ({z_max} m); "
            "the analysis slice would lie outside the mesh."
        )
    walkable = _load_walkable(wkt_or_polygon)
    dx = resolve_dx(walkable, dx)
    boxes, (mx0, my0, mx1, my1, ni, nj) = _obst_boxes(walkable, dx, margin_cells)
    nk = max(1, round(z_max / dx))
    nd = _coord_decimals(dx)

    lines = [
        f"&HEAD CHID='{chid}', TITLE='Generated from JuPedSim walkable WKT' /",
        f"&MESH IJK={ni},{nj},{nk}, XB={mx0:.{nd}f},{mx1:.{nd}f},"
        f"{my0:.{nd}f},{my1:.{nd}f},0.0,{z_max} /",
        f"&TIME T_END={t_end} /",
        "&MISC TMPA=20.0 /",
        "",
        f"! --- walls: complement of the walkable area ({len(boxes)} OBSTs) ---",
    ]
    for x0, x1, y0, y1 in boxes:
        lines.append(
            f"&OBST XB={x0:.{nd}f},{x1:.{nd}f},{y0:.{nd}f},{y1:.{nd}f},0.0,{z_max} /"
        )
    if include_fire:
        lines += [
            "",
            _fire_and_slices(
                walkable, slice_height_m, hrrpua, burner_size_m, z_max, nd
            ),
        ]
    lines += ["", "&TAIL /", ""]
    return "\n".join(lines)


if __name__ == "__main__":  # pragma: no cover
    import argparse
    import pathlib

    parser = argparse.ArgumentParser(
        description="Generate an FDS deck from a walkable WKT."
    )
    parser.add_argument("wkt_file", help="File containing a POLYGON/MULTIPOLYGON WKT")
    parser.add_argument(
        "--dx",
        type=float,
        default=None,
        help="cell size (default: auto from thinnest wall)",
    )
    parser.add_argument("--z-max", type=float, default=3.0)
    parser.add_argument("--chid", default="from_wkt")
    parser.add_argument("--geometry-only", action="store_true")
    args = parser.parse_args()
    text = pathlib.Path(args.wkt_file).read_text(encoding="utf-8").strip()
    print(
        wkt_to_fds(
            text,
            dx=args.dx,
            z_max=args.z_max,
            chid=args.chid,
            include_fire=not args.geometry_only,
        )
    )
