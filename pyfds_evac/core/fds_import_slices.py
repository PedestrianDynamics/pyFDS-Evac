"""Deck-only check of the FDS output a pyFDS-Evac run reads (#604).

:func:`check_slices` reads the ``&SLCF``, ``&TIME``, ``&DUMP`` and ``&REAC``
records of a parsed deck and says, before FDS runs, whether the run will
find what its default mechanisms need. It never opens FDS output.

The rules copy the runtime's, they do not redefine them:

- A slice is used when it is horizontal (``PBZ``, or ``XB`` with z0 == z1
  and neither x nor y collapsed: fdsreader tests x, then y, then z);
  among those, the one nearest the requested height wins and declaration
  order breaks ties, as :func:`fds_sampling.select_horizontal_slice`. Past
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

The z printed is the deck's; FDS moves a slice to the nearest grid plane,
up to half a cell away.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pyfds_evac.config.parameters import SMOKE_UPDATE_INTERVAL_S

from .fds_deck import FdsDeck, FdsDeckError, NamelistRecord
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
GRID_NOTE = "deck z; FDS moves a slice to the grid, up to half a cell"


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

    @property
    def ok(self) -> bool:
        return not any(item.failed for item in self.items)

    @property
    def failed(self) -> list[SliceItem]:
        return [item for item in self.items if item.failed]

    def lines(self, compact: bool = False) -> list[str]:
        """The printed block; *compact* leaves out the plain info lines."""
        shown = [i for i in self.items if not compact or i.mark != "·"]
        out = [f"FDS output check at z = {self.height:g} m ({GRID_NOTE}):"]
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


def check_slices(deck: FdsDeck, height: float) -> SliceCheck:
    """Check *deck* for the slices a run at *height* reads; see the module."""
    slices = [s for s in map(_slice, deck.group("SLCF")) if s is not None]
    check = SliceCheck(height)
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
    item.message = f"z {z:g} m (requested {height:g} m, line {chosen.record.line})"
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
