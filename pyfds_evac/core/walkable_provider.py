"""Walkable-area providers for the FDS deck importer.

The importer needs the space an occupant can walk on, in FDS (x, y) metres.
How that polygon is made is a dependency behind one interface::

    provider(deck: FdsDeck, floor: FloorSpec) -> WalkableResult

Exit and spawn construction use only the resulting polygon and the deck
records, so a better provider (or a hand-drawn ``--walkable`` WKT) changes
nothing else.

The default provider, :func:`deck_walkable`, reads the deck through the
in-repo namelist parser (multi-line records, ``MULT_ID``), so it works from
an installed wheel:

- the domain is the union of the floor's mesh footprints (the evacuation
  meshes of an FDS+Evac deck, source ``derived:evac-mesh``; otherwise the
  fire meshes, ``derived:deck``), and its edge is a wall (the FDS default
  ``INERT`` boundary);
- solids are the floor's ``&OBST`` footprints minus its ``&HOLE``
  footprints; a zero-thickness record is widened by
  :data:`HALF_CELL_M` on each side;
- with the floor's meshes given, every ``&OBST`` and ``&HOLE`` is first put
  on the mesh gridlines with FDS's rules (:func:`snap_footprints`), so the
  area is the one FDS computes, not the one the written ``XB`` suggests;
- free parts of :data:`MIN_PART_M2` or less are dropped, and interior rings
  smaller than that are filled (grid noise, not obstacles).

It returns every free component. Which components are kept (those holding a
spawn area) is decided by the importer, which knows the spawns and exits.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from .fds_deck import FdsDeck, NamelistRecord
from .fds_import_geometry import fill_small_rings, polygons_of, union, widened_box

#: Half-width given to a zero-thickness ``&OBST``/``&HOLE`` on each side [m].
HALF_CELL_M = 0.05
#: Free parts and interior rings of this area or less are dropped/filled [m2].
MIN_PART_M2 = 0.25


class WalkableError(ValueError):
    """The walkable area could not be derived; the message says what to do."""


@dataclass(frozen=True)
class FloorSpec:
    """The floor the importer asks a provider for.

    ``z_band`` is absolute [m]; ``domain`` is the union of the selected
    evacuation meshes (legacy deck) or of the fire meshes (modern deck);
    ``obstructions`` and ``holes`` are the ``&OBST`` and ``&HOLE`` records
    that apply to this floor (z band, ``EVACUATION`` and ``MESH_ID``
    honoured). ``meshes`` are the floor's ``&MESH`` records, the grid the
    records are snapped to (none: taken as written); ``thicken`` is
    ``&MISC THICKEN_OBSTRUCTIONS``.
    """

    z_floor: float
    z_band: tuple[float, float]
    domain: Any
    evac_mesh_ids: tuple[str, ...] | None = None
    obstructions: tuple[NamelistRecord, ...] = ()
    holes: tuple[NamelistRecord, ...] = ()
    meshes: tuple[NamelistRecord, ...] = ()
    thicken: bool = False


@dataclass(frozen=True)
class WalkableResult:
    """A provider's polygon and its diagnostics.

    ``notes`` are report items ``(status, level, group, message, record)``
    for the importer to add; ``snap`` summarises the grid snapping
    (``None`` when no mesh was given).
    """

    polygon: Any
    diagnostics: list[str] = field(default_factory=list)
    source: str = "derived"
    notes: list[tuple[str, str, str, str, NamelistRecord | None]] = field(
        default_factory=list
    )
    snap: dict | None = None


WalkableProvider = Callable[[FdsDeck, FloorSpec], WalkableResult]


def footprint(record: NamelistRecord) -> Any:
    """Plan footprint of *record*'s ``XB``, a zero-thickness axis widened."""
    x0, x1, y0, y1 = record.box6()[:4]
    return widened_box(x0, x1, y0, y1, HALF_CELL_M)


#: Tolerance of coordinate comparisons on the grid [m].
_GRID_TOL = 1e-9
#: FDS collapses a bound pair closer than this share of a cell onto one line.
_COLLAPSE_CELLS = 0.25

_STRETCHED = "stretched grid (&TRNX/&TRNY)"


@dataclass(frozen=True)
class SnappedBox:
    """One record's plan box on one mesh's gridlines.

    ``box`` is ``(x0, x1, y0, y1)``; ``flat_x``/``flat_y`` mark a box FDS
    put on a single gridline in that direction; ``shift_m`` is the largest
    move of a bound in x or y from the record clipped to the mesh.
    """

    record: NamelistRecord
    box: tuple[float, float, float, float]
    flat_x: bool
    flat_y: bool
    shift_m: float


@dataclass(frozen=True)
class _Axis:
    """A uniform mesh axis: ``cells`` cells between ``start`` and ``end``."""

    start: float
    end: float
    cells: int

    @property
    def step(self) -> float:
        return (self.end - self.start) / self.cells

    def scaled(self, x: float) -> float:
        return (x - self.start) * (1.0 / self.step)

    def index(self, x: float) -> int:
        """FDS ``NINT`` of the cell coordinate of *x* (clipped, so >= 0)."""
        return math.floor(self.scaled(x) + 0.5)

    def coord(self, i: int) -> float:
        return round(self.start + i * self.step, 9)


def _mesh_axes(mesh: NamelistRecord) -> tuple[_Axis, _Axis, _Axis] | None:
    ijk = mesh.values("IJK")
    if not mesh.has("XB") or len(ijk) != 3 or min(ijk) < 1:
        return None
    x0, x1, y0, y1, z0, z1 = mesh.box6()
    cells = (int(v) for v in ijk)
    return tuple(  # type: ignore[return-value]
        _Axis(lo, hi, n) for (lo, hi), n in zip(((x0, x1), (y0, y1), (z0, z1)), cells)
    )


def _snap_axis(
    axis: _Axis, lo: float, hi: float, thicken: bool, side_start: float
) -> tuple[int, int]:
    """Cell indices of the clipped range ``lo..hi``: FDS ``READ_OBST``.

    Which gridline a collapsed pair lands on is FDS's own test, which
    compares metres with cell indices (``GINV`` is the identity on a
    uniform grid) and, in y, subtracts the x start: ``side_start`` is the
    start FDS subtracts from the lower bound.
    """
    i1, i2 = axis.index(lo), axis.index(hi)
    if thicken:
        if i1 == i2:
            i1 = int(axis.scaled(0.5 * (lo + hi)))
            i2 = min(i1 + 1, axis.cells)
        return i1, i2
    if (hi - lo) >= _COLLAPSE_CELLS * axis.step or i1 == i2:
        return i1, i2
    if (lo - side_start) - i1 < i2 - (hi - axis.start):
        return i1, i1
    return i2, i2


def _thicken_dirs(record: NamelistRecord, axes, thicken: bool) -> list[bool]:
    """Per axis: thickening applies unless the midpoint lies outside the mesh."""
    flag = record.flag("THICKEN")
    wanted = thicken if flag is None else flag
    box6 = record.box6()
    return [
        wanted and 2 * a.start <= box6[2 * k] + box6[2 * k + 1] <= 2 * a.end
        for k, a in enumerate(axes)
    ]


def _touches_face(spans, clipped) -> bool:
    """The record only touches this mesh's face in x or y: the neighbour owns it."""
    return any(
        hi - lo > _GRID_TOL and chi - clo <= _GRID_TOL
        for (lo, hi), (clo, chi) in zip(spans[:2], clipped[:2])
    )


def _snap_in_mesh(record, axes, *, hole: bool, thicken: bool, evac_z: bool):
    """``(SnappedBox | None, dropped)`` of *record* on one mesh's grid.

    FDS+Evac stretches an evacuation obstruction to the mesh's full height
    (*evac_z*), so z never collapses there.
    """
    box6 = record.box6()
    spans = [(box6[2 * k], box6[2 * k + 1]) for k in range(3)]
    if evac_z and not hole:
        spans[2] = (axes[2].start, axes[2].end)
    if any(hi < a.start or lo > a.end for a, (lo, hi) in zip(axes, spans)):
        return None, False
    clipped = [(max(lo, a.start), min(hi, a.end)) for a, (lo, hi) in zip(axes, spans)]
    if _touches_face(spans, clipped):
        return None, False
    dirs = [False] * 3 if hole else _thicken_dirs(record, axes, thicken)
    used = 2 if hole else 3
    sides = [axes[0].start, axes[0].start, axes[2].start]
    idx = [_snap_axis(axes[k], *clipped[k], dirs[k], sides[k]) for k in range(used)]
    flat = [i1 == i2 for i1, i2 in idx]
    if not hole and sum(flat) >= 2:
        return None, True
    xs = [axes[k].coord(i) for k in range(2) for i in idx[k]]
    shift = max(abs(xs[n] - clipped[n // 2][n % 2]) for n in range(4))
    return SnappedBox(
        record, (xs[0], xs[1], xs[2], xs[3]), flat[0], flat[1], shift
    ), False


@dataclass(frozen=True)
class _RecordSnap:
    record: NamelistRecord
    boxes: list[SnappedBox]
    dropped: bool


def _snap_each(
    records, grids, *, hole: bool, thicken: bool, evac_z: bool = False
) -> list[_RecordSnap]:
    out = []
    for record in records:
        boxes, dropped = [], False
        for axes in grids:
            snapped, gone = _snap_in_mesh(
                record, axes, hole=hole, thicken=thicken, evac_z=evac_z
            )
            boxes.extend([snapped] if snapped else [])
            dropped = dropped or gone
        out.append(_RecordSnap(record, boxes, dropped and not boxes))
    return out


def snap_footprints(
    records: Iterable[NamelistRecord],
    meshes: Iterable[NamelistRecord],
    *,
    hole: bool,
    thicken: bool,
    evac_z: bool = False,
) -> list[SnappedBox]:
    """The plan boxes of *records* on the gridlines of each mesh they overlap.

    Rules of FDS ``READ_OBST`` (``hole=False``): clip to the mesh, ``NINT``
    per bound, ``THICKEN`` (the record's flag, else *thicken*) or the
    quarter-cell collapse; an obstruction that collapses in two axes gives
    no box. ``READ_HOLE`` (``hole=True``): clip and ``NINT`` only. Meshes
    without ``XB`` and ``IJK`` are ignored. *evac_z*: the records are on
    evacuation meshes, where FDS+Evac gives an obstruction the mesh's z.
    """
    grids = [g for g in map(_mesh_axes, meshes) if g is not None]
    snaps = _snap_each(records, grids, hole=hole, thicken=thicken, evac_z=evac_z)
    return [box for snap in snaps for box in snap.boxes]


def snap_segment(
    mesh: NamelistRecord, x0: float, y0: float, x1: float, y1: float
) -> tuple[float, float, float, float] | None:
    """A plan segment moved onto *mesh*'s gridlines: FDS+Evac ``READ_EXIT``.

    Each bound is clipped to the mesh and rounded with ``NINT`` to a
    gridline, as for ``&EXIT``, ``&DOOR`` and ``&ENTR``. None when the mesh
    has no ``XB`` and ``IJK``.
    """
    grid = _mesh_axes(mesh)
    if grid is None:
        return None
    ax, ay = grid[0], grid[1]

    def snap(axis: _Axis, v: float) -> float:
        return axis.coord(axis.index(min(max(v, axis.start), axis.end)))

    return snap(ax, x0), snap(ay, y0), snap(ax, x1), snap(ay, y1)


def _label(record: NamelistRecord) -> str:
    return f"{record.label} (line {record.line})"


def _written_flat(record: NamelistRecord) -> tuple[bool, bool]:
    x0, x1, y0, y1 = record.box6()[:4]
    return x1 - x0 < _GRID_TOL, y1 - y0 < _GRID_TOL


def _written_overlap(wall: NamelistRecord, hole: NamelistRecord) -> bool:
    """``READ_HOLE``'s test on the written bounds of the wall and the hole.

    After the index test, FDS skips a wall whose intersection with the hole
    ends at the hole's lower bound or starts at its upper bound in x or y,
    so a hole that only touches the wall, or has no width, never cuts.
    """
    w, h = wall.box6(), hole.box6()
    for k in (0, 2):
        lo, hi = max(h[k], w[k]), min(h[k + 1], w[k + 1])
        if hi <= h[k] or lo >= h[k + 1]:
            return False
    return True


def _flat_cut_box(ob: SnappedBox, hole: SnappedBox):
    """The box of *hole* that cuts the one-gridline wall *ob*, or ``None``.

    A hole that is flat in a direction cuts only a wall on the same
    gridline; otherwise the hole is widened across the wall's flat
    direction, so a gridline inside the hole's snapped range is cut.
    """
    if not _written_overlap(ob.record, hole.record):
        return None
    hx0, hx1, hy0, hy1 = hole.box
    if hole.flat_x and not (ob.flat_x and abs(hx0 - ob.box[0]) < _GRID_TOL):
        return None
    if hole.flat_y and not (ob.flat_y and abs(hy0 - ob.box[2]) < _GRID_TOL):
        return None
    pad = HALF_CELL_M + _GRID_TOL
    if ob.flat_x and not hole.flat_x:
        hx0, hx1 = hx0 - pad, hx1 + pad
    if ob.flat_y and not hole.flat_y:
        hy0, hy1 = hy0 - pad, hy1 + pad
    return widened_box(hx0, hx1, hy0, hy1, HALF_CELL_M)


def _wall_piece(ob: SnappedBox, holes: list[SnappedBox], cutting: set[int]):
    """Footprint of one snapped box; a one-gridline wall is cut by the holes."""
    piece = widened_box(*ob.box, HALF_CELL_M)
    if not (ob.flat_x or ob.flat_y):
        return piece
    for n, hole in enumerate(holes):
        cut = _flat_cut_box(ob, hole)
        if cut is not None and piece.intersection(cut).area > 0:
            cutting.add(n)
            piece = piece.difference(cut)
    return piece


def _snapped_solids(obsts: list[_RecordSnap], holes: list[SnappedBox], cutting):
    """Solids of the snapped obstructions minus the holes that cut them."""
    solids = [
        union([_wall_piece(ob, holes, cutting) for ob in snap.boxes]).simplify(0)
        for snap in obsts
        if snap.boxes
    ]
    thick = [
        widened_box(*h.box, HALF_CELL_M) for h in holes if not (h.flat_x or h.flat_y)
    ]
    merged = union(solids)
    return merged.difference(union(thick)) if thick else merged


def _written_solids(floor: FloorSpec):
    solids = union([footprint(r) for r in floor.obstructions])
    if floor.holes:
        solids = solids.difference(union([footprint(r) for r in floor.holes]))
    return solids


@dataclass
class _FloorSnap:
    """What snapping found; ``solids`` is ``None`` when the floor is as written."""

    solids: Any = None
    notes: list = field(default_factory=list)
    summary: dict | None = None


def _closed_holes(holes: list[_RecordSnap], cutting: set[int], floor, flat) -> list:
    """Holes snapped to a gridline that cut nothing, over a written obstruction."""
    written = union([footprint(r) for r in floor.obstructions])
    closed = []
    for snap in holes:
        mine = [b for b in snap.boxes if id(b) in flat]
        if not mine or len(mine) < len(snap.boxes):
            continue
        if any(id(b) in cutting for b in mine):
            continue
        if footprint(snap.record).intersection(written).area > 0:
            closed.append(snap.record)
    return closed


def _gridline_pairs(obsts: list[_RecordSnap]) -> list[NamelistRecord]:
    """The later record of each pair of separate walls on one gridline."""
    lines: dict[tuple, list[tuple[NamelistRecord, float, float]]] = {}
    later: list[NamelistRecord] = []
    for snap in obsts:
        for b in snap.boxes:
            key, lo, hi = _line_of(b)
            if key is None:
                continue
            clash = any(
                r is not snap.record
                and min(hi, h) - max(lo, start) > _GRID_TOL
                and not footprint(r).intersects(footprint(snap.record))
                for r, start, h in lines.get(key, [])
            )
            if clash and snap.record not in later:
                later.append(snap.record)
            lines.setdefault(key, []).append((snap.record, lo, hi))
    return later


def _line_of(b: SnappedBox):
    if b.flat_x:
        return ("x", b.box[0]), b.box[2], b.box[3]
    if b.flat_y:
        return ("y", b.box[2]), b.box[0], b.box[1]
    return None, 0.0, 0.0


def _collapsed(snap: _RecordSnap) -> bool:
    """A box FDS put on one gridline although the record is not zero-width."""
    wx, wy = _written_flat(snap.record)
    return any((b.flat_x and not wx) or (b.flat_y and not wy) for b in snap.boxes)


def _snap_notes(obsts, holes_closed, dropped, max_shift):
    notes = [
        (
            "A",
            "warning",
            "OBST",
            "thinner than its mesh cell in plan: FDS puts it on one gridline",
            s.record,
        )
        for s in obsts
        if _collapsed(s)
    ]
    notes += [
        (
            "A",
            "warning",
            "OBST",
            "smaller than half a cell in two directions: FDS drops it",
            s.record,
        )
        for s in dropped
    ]
    notes += [
        ("A", "warning", "HOLE", "snaps to no cell: the opening stays closed in FDS", r)
        for r in holes_closed
    ]
    notes += [
        ("A", "warning", "OBST", "lands on the same gridline as another &OBST", r)
        for r in _gridline_pairs(obsts)
    ]
    if max_shift > _GRID_TOL:
        notes.append(
            (
                "S",
                "info",
                "walkable",
                f"obstructions moved onto the FDS grid by up to {max_shift:.3f} m",
                None,
            )
        )
    return notes


def _snap_floor(deck: FdsDeck, floor: FloorSpec) -> _FloorSnap:
    grids = [g for g in map(_mesh_axes, floor.meshes) if g is not None]
    if not grids:
        return _FloorSnap()
    if deck.group("TRNX") or deck.group("TRNY"):
        note = (
            "A",
            "warning",
            "walkable",
            f"{_STRETCHED}: obstructions taken as written",
            None,
        )
        return _FloorSnap(None, [note], {"skipped": _STRETCHED})
    obsts = _snap_each(
        floor.obstructions,
        grids,
        hole=False,
        thicken=floor.thicken,
        evac_z=floor.evac_mesh_ids is not None,
    )
    holes = _snap_each(floor.holes, grids, hole=True, thicken=False)
    boxes = [b for s in (*obsts, *holes) for b in s.boxes]
    worst = max(boxes, key=lambda b: b.shift_m, default=None)
    max_shift = worst.shift_m if worst is not None else 0.0
    dropped = [s for s in obsts if s.dropped]
    summary = {
        "max_shift_m": round(max_shift, 6),
        "record": _label(worst.record) if worst and max_shift > _GRID_TOL else None,
        "dropped": len(dropped),
        "holes_closed": 0,
    }
    if max_shift <= _GRID_TOL and not dropped:
        return _FloorSnap(None, [], summary)
    hole_boxes = [b for s in holes for b in s.boxes]
    cutting: set[int] = set()
    solids = _snapped_solids(obsts, hole_boxes, cutting)
    flat = {id(b) for b in hole_boxes if b.flat_x or b.flat_y}
    cutting_ids = {id(hole_boxes[n]) for n in cutting}
    closed = _closed_holes(holes, cutting_ids, floor, flat)
    summary["holes_closed"] = len(closed)
    return _FloorSnap(solids, _snap_notes(obsts, closed, dropped, max_shift), summary)


def deck_walkable(deck: FdsDeck, floor: FloorSpec) -> WalkableResult:
    """Default provider: the floor's domain minus (``&OBST`` - ``&HOLE``)."""
    domain = floor.domain
    if domain is None or domain.is_empty:
        raise WalkableError(
            "deriving the walkable area failed: the floor has no mesh footprint; "
            "pass --walkable FILE.wkt"
        )
    snap = _snap_floor(deck, floor)
    solids = _written_solids(floor) if snap.solids is None else snap.solids
    pieces = polygons_of(domain.difference(solids))
    parts = [p for p in pieces if p.area > MIN_PART_M2]
    small = len(pieces) - len(parts)
    filled_parts = [fill_small_rings(p, MIN_PART_M2) for p in parts]
    filled = sum(
        len(p.interiors) - len(f.interiors)
        for p, f in zip(parts, filled_parts, strict=True)
    )
    polygon = union(filled_parts)
    lo, hi = floor.z_band
    legacy = floor.evac_mesh_ids is not None
    diagnostics = [
        f"domain {domain.area:.3f} m2: union of the floor's "
        f"{'evacuation ' if legacy else ''}meshes, its edge a wall",
        f"{len(floor.obstructions)} &OBST minus {len(floor.holes)} &HOLE "
        f"in z=[{lo:g}, {hi:g}] m",
        f"{len(parts)} free component(s); {small} part(s) of "
        f"<= {MIN_PART_M2:g} m2 dropped, {filled} hole(s) below it filled",
    ]
    source = "derived:evac-mesh" if legacy else "derived:deck"
    return WalkableResult(polygon, diagnostics, source, snap.notes, snap.summary)
