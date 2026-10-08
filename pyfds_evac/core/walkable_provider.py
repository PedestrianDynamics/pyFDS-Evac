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
- free parts of :data:`MIN_PART_M2` or less are dropped, and interior rings
  smaller than that are filled (grid noise, not obstacles).

It returns every free component. Which components are kept (those holding a
spawn area) is decided by the importer, which knows the spawns and exits.
"""

from __future__ import annotations

from collections.abc import Callable
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
    honoured).
    """

    z_floor: float
    z_band: tuple[float, float]
    domain: Any
    evac_mesh_ids: tuple[str, ...] | None = None
    obstructions: tuple[NamelistRecord, ...] = ()
    holes: tuple[NamelistRecord, ...] = ()


@dataclass(frozen=True)
class WalkableResult:
    """A provider's polygon and its diagnostics."""

    polygon: Any
    diagnostics: list[str] = field(default_factory=list)
    source: str = "derived"


WalkableProvider = Callable[[FdsDeck, FloorSpec], WalkableResult]


def footprint(record: NamelistRecord) -> Any:
    """Plan footprint of *record*'s ``XB``, a zero-thickness axis widened."""
    x0, x1, y0, y1 = record.box6()[:4]
    return widened_box(x0, x1, y0, y1, HALF_CELL_M)


def deck_walkable(deck: FdsDeck, floor: FloorSpec) -> WalkableResult:
    """Default provider: the floor's domain minus (``&OBST`` - ``&HOLE``)."""
    domain = floor.domain
    if domain is None or domain.is_empty:
        raise WalkableError(
            "deriving the walkable area failed: the floor has no mesh footprint; "
            "pass --walkable FILE.wkt"
        )
    solids = union([footprint(r) for r in floor.obstructions])
    if floor.holes:
        solids = solids.difference(union([footprint(r) for r in floor.holes]))
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
    return WalkableResult(polygon, diagnostics, source)
