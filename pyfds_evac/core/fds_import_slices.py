"""Deck-only check of the FDS output a pyFDS-Evac run reads (#604).

:func:`check_slices` reads the ``&SLCF``, ``&TIME``, ``&DUMP`` and ``&REAC``
records of a parsed deck and says, before FDS runs, whether the run will
find what its default mechanisms need. It never opens FDS output.

The rules copy the runtime's, they do not redefine them:

- A slice is used when it is horizontal (``PBZ``, or ``XB`` with z0 == z1
  and neither x nor y collapsed: fdsreader tests x, then y, then z);
  among those, the one nearest the requested height wins and declaration
  order breaks ties, as :func:`fds_sampling.select_horizontal_slice`. The
  z ranked is the one the run ranks: fdsreader's extent of the slice FDS
  writes (#687). See :func:`_on_grid`. Past
  ``_SLICE_HEIGHT_TOLERANCE_M`` the runtime warns; so does the check.
- Smoke speed and sign legibility read ``SOOT EXTINCTION COEFFICIENT``: deck
  ``QUANTITY='EXTINCTION COEFFICIENT'`` with no ``SPEC_ID`` or
  ``SPEC_ID='SOOT'`` (FDS User Guide 6.9.1, Sec. 22.10.5, note 5: simple
  chemistry names its smoke ``SOOT``). FED reads CO, CO2 and O2 volume
  fractions, all three or none. Without them the run warns and switches the
  mechanism off; here that is a failed (``✗``) item.
- Heat slices, the output interval and the ``&REAC`` yields are reported,
  never failed: ``init`` cannot know the run's heat flags.
- Without ``&TIME T_END`` FDS stops at its default of 1 s (User Guide 6.9.1,
  Sec. 6.2.1), while ``init`` writes ``max_simulation_time`` 300 s.

A horizontal slice FDS culls is left out, as if the deck did not declare
it, and named in :attr:`SliceCheck.dropped`: its z outside every fire
mesh, or its ``MESH_NUMBER`` naming a mesh that does not hold z or no
fire mesh (``READ_SLCF``, read.f90 of FDS-6.10.1-2291-gcc0ee9ee7e, lines
15806 and 15854-15898). See :func:`_culled`.

A deck with ``&TRNZ`` (a stretched z grid) keeps the deck's z: the
stretched nodes are not computed here. The cull still applies, since
``&TRNZ`` moves the nodes, not the mesh bounds ``ZS`` and ``ZF``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from typing import Any

from pyfds_evac.config.parameters import SMOKE_UPDATE_INTERVAL_S

from .fds_deck import FdsDeck, FdsDeckError, NamelistRecord
from .fds_import_geometry import rounded
from .fds_sampling import _SLICE_HEIGHT_TOLERANCE_M
from .fed import HEAT_SLICE_Z_TOLERANCE_M, FdsFedField

#: FDS ``&TIME T_END`` default [s] (User Guide 6.9.1, Sec. 6.2.1).
FDS_DEFAULT_T_END_S = 1.0
#: FDS ``&DUMP NFRAMES`` default (User Guide 6.9.1, Sec. 22.1).
FDS_DEFAULT_NFRAMES = 1000

#: The FED gate: (line label, SPEC_ID).
FED_GASES = (
    ("CO", "CARBON MONOXIDE"),
    ("CO2", "CARBON DIOXIDE"),
    ("O2", "OXYGEN"),
)
#: Optional FED gases, as the SPEC_ID of their volume-fraction slice.
OPTIONAL_GASES = tuple(
    label.removesuffix(" VOLUME FRACTION") for _, label in FdsFedField._OPTIONAL_SPECIES
)
EXTINCTION = "EXTINCTION COEFFICIENT"
VOLUME_FRACTION = "VOLUME FRACTION"
#: Extinction ``SPEC_ID`` values read as ``SOOT EXTINCTION COEFFICIENT``.
SOOT_SPEC_IDS = (None, "SOOT")

FAILED = ("missing", "vertical_only")
MARKS = {"ok": "✓", "missing": "✗", "vertical_only": "✗", "far": "!"}
GRID_NOTE = "z on the mesh grid, where FDS writes the slice"
#: The note when ``&TRNZ`` stretches the grid and the deck's z is ranked.
DECK_Z_NOTE = "deck z: &TRNZ stretches the grid, FDS moves a slice onto it"


@dataclass
class SliceItem:
    """One line of the check; :meth:`to_dict` is its report entry."""

    key: str
    label: str
    status: str
    required: bool
    message: str
    z_requested: float | None = None
    nearest_pbz: float | None = None
    orientation_found: str | None = None
    fix: str | None = None
    level: str = "info"

    @property
    def failed(self) -> bool:
        return self.required and self.status in FAILED

    @property
    def ok(self) -> bool:
        """A slice item: a horizontal slice within the height tolerance.

        Any other item: neither failed nor a warning.
        """
        if self.z_requested is None:
            return not self.failed and self.level != "warning"
        if self.nearest_pbz is None:
            return False
        return abs(self.nearest_pbz - self.z_requested) <= _SLICE_HEIGHT_TOLERANCE_M

    @property
    def mark(self) -> str:
        if self.status in MARKS:
            return MARKS[self.status]
        return "!" if self.level == "warning" else "·"

    def line(self) -> str:
        fix = f"; fix: {self.fix}" if self.fix else ""
        return f"{self.mark} {self.label:<12}{self.message}{fix}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "required": self.required,
            "level": self.level,
            "message": self.message,
            "z_requested": self.z_requested,
            "nearest_pbz": self.nearest_pbz,
            "ok": self.ok,
            "orientation_found": self.orientation_found,
            "fix": self.fix,
        }


@dataclass
class SliceCheck:
    """The result of :func:`check_slices`."""

    height: float
    items: list[SliceItem] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    grid_note: str = GRID_NOTE
    #: Slices FDS culls: ``line``, ``quantity``, ``spec_id``, ``z``, ``reason``.
    dropped: list[dict[str, Any]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(item.failed for item in self.items)

    @property
    def failed(self) -> list[SliceItem]:
        return [item for item in self.items if item.failed]

    def lines(self, compact: bool = False) -> list[str]:
        """The printed block; *compact* leaves out the plain info lines."""
        shown = [i for i in self.items if not compact or i.mark != "·"]
        out = [f"FDS output check at z = {self.height:g} m ({self.grid_note}):"]
        out += [f"  {item.line()}" for item in shown]
        out += [f"  {note}" for note in self.notes]
        if compact and not self.ok:
            out.append(
                "  The scenario is still written; the ✗ lines say what the run "
                "will lack. Details: pyfds-evac init DECK --check"
            )
        return out

    def to_dict(self) -> dict[str, Any]:
        return {item.key: item.to_dict() for item in self.items}


@dataclass(frozen=True)
class _Slice:
    record: NamelistRecord
    orientation: str  # horizontal, vertical or volume
    z: float | None
    deck_z: float | None = None
    culled: str | None = None  # why FDS writes no such slice


def check_slices(deck: FdsDeck, height: float) -> SliceCheck:
    """Check *deck* for the slices a run at *height* reads; see the module."""
    meshes = _fire_meshes(deck)
    stretched = bool(deck.group("TRNZ"))
    placed = [
        _on_grid(s, meshes, stretched) for s in map(_slice, deck.group("SLCF")) if s
    ]
    slices = [s for s in placed if s.culled is None]
    note = DECK_Z_NOTE if stretched else GRID_NOTE
    check = SliceCheck(height, grid_note=note)
    check.dropped = [_dropped(s) for s in placed if s.culled is not None]
    check.notes += [_dropped_note(d) for d in check.dropped]
    check.items.append(_extinction(deck, slices, height))
    gases = [_gas(slices, label, spec, height) for label, spec in FED_GASES]
    check.items += gases
    if any(g.failed for g in gases):
        check.notes.append(
            "FED needs CO, CO2 and O2 slices together; without all three the "
            "run has no toxic FED"
        )
    check.items.append(_optional_gases(slices, height))
    check.items.append(_heat(slices, "TEMPERATURE", height))
    check.items.append(_intensity(slices, height))
    check.items.append(_t_end(deck))
    check.items.append(_dt_slcf(deck))
    check.items += _yields(deck, slices)
    return check


# --- slice records ---------------------------------------------------------------


def _slice(record: NamelistRecord) -> _Slice | None:
    """Orientation and z of an ``&SLCF``; None for evacuation or unplaced ones."""
    if _safe(record.flag, "EVACUATION", False):
        return None
    pbz = _number(record, "PBZ")
    if pbz is not None:
        return _Slice(record, "horizontal", pbz)
    if record.has("PBX") or record.has("PBY"):
        return _Slice(record, "vertical", None)
    xb = _safe(record.xb)
    if xb is None:
        return None
    x0, x1, y0, y1, z0, z1 = xb
    # fdsreader's order: a collapsed x or y makes the slice vertical even
    # when z is collapsed too (a line), and the runtime then skips it.
    if x0 == x1 or y0 == y1:
        return _Slice(record, "vertical", None)
    if z0 == z1:
        return _Slice(record, "horizontal", z0)
    return _Slice(record, "volume", None)


#: FDS ``READ_SLCF`` tolerance of the cell-centred cell search [m].
_FDS_CELL_TOL_M = 1e-10


def _fire_meshes(deck: FdsDeck) -> list[tuple[int, NamelistRecord]]:
    """(FDS mesh number, mesh) of the fire meshes.

    The number counts evacuation meshes too, as FDS numbers ``&MESH``
    records (after ``MULT``); the evacuation meshes are left out (#687).
    """
    meshes = enumerate(deck.group("MESH"), start=1)
    return [(n, m) for n, m in meshes if not _safe(m.flag, "EVACUATION", False)]


def _on_grid(
    item: _Slice, meshes: list[tuple[int, NamelistRecord]], stretched: bool
) -> _Slice:
    """*item* at the z the run ranks it on, the deck's z kept in ``deck_z``.

    FDS writes the slice in each mesh it cuts, or only in ``MESH_NUMBER``,
    as the grid node index K (``READ_SLCF``, read.f90). fdsreader 1.11
    takes z from node K of each mesh and, for a horizontal slice, the
    lowest of them (``Slice.__init__``, slcf/slice.py ~273), which the run
    ranks (:func:`fds_sampling._slice_z_mid`). A slice FDS culls comes
    back with ``culled`` set; on a *stretched* (``&TRNZ``) grid, or when
    no holding mesh has a readable ``IJK``, the deck's z is kept.
    """
    if item.orientation != "horizontal" or item.z is None:
        return item
    number = _number(item.record, "MESH_NUMBER")
    xy = None if item.record.has("PBZ") else _safe(item.record.xb)
    named = [m for n, m in meshes if number is None or n == number]
    reason = _culled(item.z, xy, number, named, bool(meshes))
    if reason is not None:
        return replace(item, deck_z=item.z, culled=reason)
    if stretched:
        return replace(item, deck_z=item.z)
    centred = bool(_safe(item.record.flag, "CELL_CENTERED", False))
    zs = [_node_z(mesh, item.z, xy, centred) for mesh in named]
    found = [z for z in zs if z is not None]
    if not found:
        return replace(item, deck_z=item.z)
    return replace(item, z=rounded(min(found)), deck_z=item.z)


def _culled(
    z: float, xy, number: float | None, named: list[NamelistRecord], any_mesh: bool
) -> str | None:
    """Why FDS writes no horizontal slice at *z*; None when it writes one.

    ``READ_SLCF`` (read.f90 6.10) reads a slice in mesh NM only when
    ``MESH_NUMBER`` is NM, its default (line 15806), and culls it there
    when z lies outside ZS..ZF or the clipped x-y extent is empty (lines
    15870-15898). None, never a cull, when the deck has no fire mesh or a
    named mesh has no readable ``XB``: the check cannot judge then.
    """
    if not any_mesh:
        return None
    if not named:
        return f"MESH_NUMBER {number:g} names no fire &MESH"
    holds = [_holds(mesh, z, xy) for mesh in named]
    if None in holds or any(holds):
        return None
    if number is not None:
        return f"&MESH {number:g} (MESH_NUMBER) does not hold it"
    return "outside every fire &MESH"


def _holds(mesh: NamelistRecord, z: float, xy) -> bool | None:
    """Whether FDS keeps a horizontal slice at *z* in *mesh*; None if unknown.

    Inclusive in z (``XB(5)>ZF .OR. XB(6)<ZS`` culls), exclusive in x and
    y (``XB(1)>=XF .OR. XB(2)<=XS ...``), read.f90 lines 15885-15888. The
    1e-9 m in z absorbs rounding in ``MULT``-expanded mesh bounds.
    """
    xb = _safe(mesh.xb)
    if xb is None:
        return None
    x0, x1, y0, y1, z0, z1 = xb
    if z < z0 - 1e-9 or z > z1 + 1e-9:
        return False
    if xy is not None and (xy[1] <= x0 or xy[0] >= x1 or xy[3] <= y0 or xy[2] >= y1):
        return False
    return True


def _node_z(mesh: NamelistRecord, z: float, xy, centred: bool) -> float | None:
    """z of the node K that FDS writes for *z* in *mesh*; None if not known.

    None when *mesh* does not hold the slice (:func:`_holds`) or has no
    readable ``IJK``. Uniform grid of ``IJK``/``XB``. A node slice:
    K = NINT((z - ZS)/DZ), halves up. A cell-centred one: the last cell K
    whose centre is within DZ/2 + 1e-10 m of z, written as its upper node.
    """
    ijk = mesh.values("IJK")
    xb = _safe(mesh.xb)
    if xb is None or len(ijk) != 3 or not isinstance(ijk[2], int) or ijk[2] <= 0:
        return None
    if not _holds(mesh, z, xy):
        return None
    x0, x1, y0, y1, z0, z1 = xb
    dz = (z1 - z0) / ijk[2]
    if not centred:
        return float(z0 + math.floor((z - z0) / dz + 0.5) * dz)
    cells = [
        k
        for k in range(1, ijk[2] + 1)
        if abs(z - (z0 + (k - 0.5) * dz)) < 0.5 * dz + _FDS_CELL_TOL_M
    ]
    return float(z0 + cells[-1] * dz) if cells else None


def _dropped(item: _Slice) -> dict[str, Any]:
    return {
        "line": item.record.line,
        "quantity": _quantity(item.record),
        "spec_id": _spec(item.record),
        "z": item.deck_z,
        "reason": item.culled,
    }


def _dropped_note(entry: dict[str, Any]) -> str:
    spec = f", SPEC_ID {entry['spec_id']}" if entry["spec_id"] else ""
    return (
        f"dropped &SLCF line {entry['line']} ({entry['quantity']}{spec}, "
        f"z {entry['z']:g} m): {entry['reason']}, so FDS writes no such slice"
    )


def _safe(method, *args):
    try:
        return method(*args)
    except FdsDeckError:
        return None


def _number(record: NamelistRecord | None, key: str) -> float | None:
    return None if record is None else _safe(record.number, key)


def _quantity(record: NamelistRecord) -> str:
    return str(record.text("QUANTITY", "")).strip().upper()


def _spec(record: NamelistRecord) -> str | None:
    value = record.text("SPEC_ID")
    return None if value is None else value.strip().upper()


def _matching(slices, quantity: str, specs: tuple) -> list[_Slice]:
    return [
        s
        for s in slices
        if _quantity(s.record) == quantity and _spec(s.record) in specs
    ]


def _nearest(matches: list[_Slice], height: float) -> _Slice | None:
    """The runtime rule: nearest horizontal z, first declared on a tie."""
    horizontal = [s for s in matches if s.orientation == "horizontal"]
    if not horizontal:
        return None
    return min(horizontal, key=lambda s: abs(_z(s) - height))


def _deck_z(item: _Slice) -> str:
    """``deck z ..., `` when the deck puts *item* off the grid."""
    if item.deck_z is None or item.deck_z == item.z:
        return ""
    return f"deck z {item.deck_z:g} m, "


def _z(item: _Slice) -> float:
    return item.z if item.z is not None else float("nan")


def _orientation(matches: list[_Slice]) -> str | None:
    if any(s.orientation == "horizontal" for s in matches):
        return "horizontal"
    kinds = sorted({s.orientation for s in matches})
    return "/".join(kinds) if kinds else None


# --- required slices -------------------------------------------------------------


def _required(key, label, matches, height, fix, extra="") -> SliceItem:
    chosen = _nearest(matches, height)
    orientation = _orientation(matches)
    item = SliceItem(key, label, "ok", True, "", height, orientation_found=orientation)
    if chosen is None:
        found = "none" if not matches else f"{orientation} only, the run reads none"
        item.status = "missing" if not matches else "vertical_only"
        item.message = f"{found} (requested z {height:g} m){extra}"
        item.fix = fix
        item.level = "error"
        return item
    z = _z(chosen)
    item.nearest_pbz = z
    item.message = (
        f"z {z:g} m ({_deck_z(chosen)}requested {height:g} m, "
        f"line {chosen.record.line})"
    )
    if abs(z - height) > _SLICE_HEIGHT_TOLERANCE_M:
        item.status = "far"
        item.level = "warning"
        item.message += (
            f", {abs(z - height):.2f} m away: the run reads it there and warns"
        )
        item.fix = fix
    return item


def _slcf(height: float, quantity: str, spec: str | None = None) -> str:
    spec_text = f", SPEC_ID='{spec}'" if spec else ""
    return f"add &SLCF PBZ={height:g}, QUANTITY='{quantity}'{spec_text} /"


def _extinction(deck: FdsDeck, slices, height: float) -> SliceItem:
    matches = _matching(slices, EXTINCTION, SOOT_SPEC_IDS)
    extra = _extinction_traps(slices) if not _nearest(matches, height) else ""
    item = _required(
        EXTINCTION,
        "Extinction",
        matches,
        height,
        _slcf(height, EXTINCTION),
        extra,
    )
    if not item.failed:
        item.message += "; smoke speed and sign legibility read it"
    else:
        item.message += "; the run has no smoke slowdown and no smoke on signs"
    return item


def _extinction_traps(slices) -> str:
    """Slices that look like the extinction coefficient but are not read."""
    notes = []
    if any(_quantity(s.record) == "EXTINCTION" for s in slices):
        notes.append(
            "QUANTITY='EXTINCTION' is FDS's combustion-suppression flag, "
            "not the extinction coefficient"
        )
    other = sorted(
        {
            str(_spec(s.record))
            for s in slices
            if _quantity(s.record) == EXTINCTION
            and _spec(s.record) not in SOOT_SPEC_IDS
        }
    )
    if other:
        notes.append(
            f"EXTINCTION COEFFICIENT with SPEC_ID {', '.join(other)} is not "
            "the soot one the run reads"
        )
    if any(_quantity(s.record) == "VISIBILITY" for s in slices):
        notes.append("VISIBILITY is no substitute")
    return "".join(f"; {n}" for n in notes)


def _gas(slices, label: str, spec: str, height: float) -> SliceItem:
    matches = _matching(slices, VOLUME_FRACTION, (spec,))
    return _required(
        f"{VOLUME_FRACTION} {spec}",
        label,
        matches,
        height,
        _slcf(height, VOLUME_FRACTION, spec),
    )


# --- reported only ---------------------------------------------------------------


def _optional_gases(slices, height: float) -> SliceItem:
    found = []
    for spec in OPTIONAL_GASES:
        chosen = _nearest(_matching(slices, VOLUME_FRACTION, (spec,)), height)
        if chosen is not None:
            found.append(f"{spec} z {_z(chosen):g} m")
    text = ", ".join(found) if found else "none"
    return SliceItem(
        "optional FED gases",
        "Other gases",
        "info",
        False,
        f"{text} (FED adds the ones present)",
    )


def _horizontal_z(matches: list[_Slice]) -> list[float]:
    return sorted({_z(s) for s in matches if s.orientation == "horizontal"})


def _by_quantity(slices, quantity: str) -> list[_Slice]:
    return [s for s in slices if _quantity(s.record) == quantity]


def _heat(slices, quantity: str, height: float) -> SliceItem:
    matches = _by_quantity(slices, quantity)
    chosen = _nearest(matches, height)
    return SliceItem(
        quantity,
        "Temperature",
        "info",
        False,
        f"{_z_list(matches)}; needed for --enable-heat-fed or --heat-regime layer",
        height,
        None if chosen is None else _z(chosen),
        _orientation(matches),
    )


def _z_list(matches: list[_Slice]) -> str:
    zs = _horizontal_z(matches)
    if zs:
        return "z " + ", ".join(f"{z:g}" for z in zs) + " m"
    return "none" if not matches else f"{_orientation(matches)} only"


def _intensity(slices, height: float) -> SliceItem:
    quantity = "INTEGRATED INTENSITY"
    matches = _by_quantity(slices, quantity)
    chosen = _nearest(matches, height)
    item = SliceItem(
        quantity,
        "Intensity",
        "info",
        False,
        f"{_z_list(matches)}; needed for --heat-radiant-source integrated-intensity",
        height,
        None if chosen is None else _z(chosen),
        _orientation(matches),
    )
    temperature = _horizontal_z(_by_quantity(slices, "TEMPERATURE"))
    lonely = [
        z
        for z in _horizontal_z(matches)
        if not any(abs(z - t) <= HEAT_SLICE_Z_TOLERANCE_M for t in temperature)
    ]
    if lonely:
        item.level = "warning"
        item.message += (
            f"; no TEMPERATURE slice at z {', '.join(f'{z:g}' for z in lonely)} m"
        )
        item.fix = _slcf(lonely[0], "TEMPERATURE")
    return item


def _t_end(deck: FdsDeck) -> SliceItem:
    t_end = _number(deck.first("TIME"), "T_END")
    if t_end is None:
        return SliceItem(
            "T_END",
            "T_END",
            "missing",
            True,
            f"none: FDS stops at its default T_END of {FDS_DEFAULT_T_END_S:g} s, "
            "and init writes max_simulation_time 300 s, past the FDS output",
            fix="add &TIME T_END=<seconds the evacuation needs> /",
            level="error",
        )
    return SliceItem(
        "T_END",
        "T_END",
        "ok",
        True,
        f"{t_end:g} s; init writes max_simulation_time {t_end:g} s",
    )


def _dt_slcf(deck: FdsDeck) -> SliceItem:
    dump = deck.first("DUMP")
    dt = _number(dump, "DT_SLCF")
    source = "&DUMP DT_SLCF"
    if dt is None:
        time = deck.first("TIME")
        t_end = _number(time, "T_END")
        t_begin = _number(time, "T_BEGIN") or 0.0
        nframes = _number(dump, "NFRAMES") or FDS_DEFAULT_NFRAMES
        dt = ((t_end if t_end is not None else FDS_DEFAULT_T_END_S) - t_begin) / nframes
        source = f"(T_END - T_BEGIN)/NFRAMES, NFRAMES {nframes:g}"
    item = SliceItem("DT_SLCF", "DT_SLCF", "info", False, f"{dt:g} s ({source})")
    if dt > SMOKE_UPDATE_INTERVAL_S:
        item.level = "warning"
        item.message += (
            f", coarser than the run's smoke update interval of "
            f"{SMOKE_UPDATE_INTERVAL_S:g} s"
        )
        item.fix = f"set &DUMP DT_SLCF={SMOKE_UPDATE_INTERVAL_S:g} /"
    return item


def _yields(deck: FdsDeck, slices) -> list[SliceItem]:
    """Simple-chemistry yields of the gases a declared slice shows.

    Only decks whose every ``&REAC`` is simple chemistry: one with
    ``SPEC_ID_NU`` sets its products explicitly, and without ``&REAC`` the
    source of the species is not known from the deck.
    """
    reacs = deck.group("REAC")
    if not reacs or any(r.has("SPEC_ID_NU") for r in reacs):
        return []
    declared = (
        ("SOOT_YIELD", _matching(slices, EXTINCTION, SOOT_SPEC_IDS), "extinction"),
        ("CO_YIELD", _matching(slices, VOLUME_FRACTION, ("CARBON MONOXIDE",)), "CO"),
    )
    return [
        SliceItem(
            f"&REAC {key}",
            key,
            "info",
            False,
            f"absent or 0 in &REAC: the {what} slice gets nothing from combustion",
            fix=f"set &REAC {key} to the fuel's yield",
            level="warning",
        )
        for key, matches, what in declared
        if matches and not any((_number(r, key) or 0.0) > 0 for r in reacs)
    ]
