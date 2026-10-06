"""FDS+Evac namelists (``&EXIT``, ``&DOOR``, ``&ENTR``, ``&EVAC``, ``&EVHO``,
``&PERS``) mapped to pyFDS-Evac exits and spawn areas.

The mapping table, its statuses and the rules (E1 exit strip, ``&EVHO``
split, ``&DOOR`` leading off the floor) are in the import task record; each
non-exact mapping leaves a report item.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from shapely.geometry import box

from . import fds_import_people as people
from .fds_deck import FdsDeck, NamelistRecord
from .fds_import_geometry import (
    ExitLine,
    exit_strip,
    ior_normal,
    largest_remainder,
    line_from_xb,
    polygons_of,
    split_holes,
    union,
)
from .fds_import_report import Floor, ImportedExit, ImportedSpawn, ImportReport

#: Keys each group maps; a trailing ``*`` is a prefix. Other keys are cosmetic
#: (:data:`COSMETIC`) or dropped with a report item.
HANDLED = {
    "EXIT": (
        "ID",
        "XB",
        "IOR",
        "MESH_ID",
        "XYZ",
        "TIME_OPEN",
        "TIME_CLOSE",
        "KNOWN_DOOR",
        "LOCKED_WHEN_CLOSED",
        "COUNT_ONLY",
    ),
    "DOOR": (
        "ID",
        "XB",
        "IOR",
        "MESH_ID",
        "XYZ",
        "TIME_OPEN",
        "TIME_CLOSE",
        "LOCKED_WHEN_CLOSED",
        "TO_NODE",
        "EXIT_SIGN",
    ),
    "ENTR": (
        "ID",
        "XB",
        "IOR",
        "MESH_ID",
        "MAX_FLOW",
        "MAX_HUMANS",
        "TIME_START",
        "TIME_STOP",
        "PERS_ID",
        "KNOWN_DOOR_NAMES",
        "KNOWN_DOOR_PROBS",
    ),
    "EVAC": (
        "ID",
        "XB",
        "NUMBER_INITIAL_PERSONS",
        "PERS_ID",
        "MESH_ID",
        "PRE_*",
        "DET_*",
        "KNOWN_DOOR_NAMES",
        "KNOWN_DOOR_PROBS",
    ),
    "EVHO": ("ID", "XB", "EVAC_ID", "PERS_ID", "MESH_ID"),
    "PERS": (
        "ID",
        "DEFAULT_PROPERTIES",
        "VELOCITY_DIST",
        "VEL_*",
        "PRE_*",
        "DET_*",
        "HUMAN_SMOKE_HEIGHT",
        "DIAMETER_DIST",
        "DIA_*",
    ),
}
COSMETIC = (
    "FYI",
    "COLOR",
    "RGB",
    "SHOW",
    "HEIGHT",
    "VENT_FFIELD",
    "ANGLE",
    "COLOR_METHOD",
    "OUTPUT_*",
    "AVATAR_*",
    "DEAD_*",
    "TITLE",
)
#: Groups that are dropped whole: single floor, no devices.
DROPPED_GROUPS = {
    "CORR": "corridor between floors; one floor is imported",
    "STRS": "stairs; one floor is imported",
    "EVSS": "incline; a speed_factor zone cannot express up/down",
    "EDEV": "evacuation device; no counterpart",
}


@dataclass
class LegacyContext:
    """What the legacy mapping needs."""

    deck: FdsDeck
    floor: Floor
    floors: list[Floor]
    walkable: Any
    depth: float
    tol: float
    report: ImportReport
    t_begin: float
    t_end: float | None
    known_exits: list[str] = field(default_factory=list)
    pers_cache: dict[str, dict[str, Any]] = field(default_factory=dict)

    def add(self, *args: Any, **kwargs: Any) -> None:
        self.report.add(*args, **kwargs)


def _matches(key: str, patterns: tuple[str, ...]) -> bool:
    return any(
        key == p or (p.endswith("*") and key.startswith(p[:-1])) for p in patterns
    )


def classify_keys(record: NamelistRecord, report: ImportReport) -> None:
    """One C item per cosmetic key, one D item per key with no counterpart."""
    handled = HANDLED.get(record.group, ())
    for key in record.params:
        if _matches(key, handled):
            continue
        if _matches(key, COSMETIC):
            report.add("C", "info", record.group, f"{key} ignored", record)
            continue
        report.add("D", "warning", record.group, f"{key} has no counterpart", record)


# --- floor membership ------------------------------------------------------


def floor_index(record: NamelistRecord, floors: list[Floor]) -> int | None:
    """The floor of *record*: by ``MESH_ID``, else by z overlap with a slab."""
    mesh_id = record.text("MESH_ID")
    if mesh_id is not None:
        return next(
            (i for i, f in enumerate(floors) if mesh_id in {m.id for m in f.meshes}),
            None,
        )
    z_range = _z_range(record)
    if z_range is None:
        return 0 if len(floors) == 1 else None
    lo, hi = z_range
    return next(
        (i for i, f in enumerate(floors) if lo <= f.slab[1] and hi >= f.slab[0]),
        None,
    )


def _z_range(record: NamelistRecord) -> tuple[float, float] | None:
    xb = record.xb()
    if xb is not None:
        return xb[4], xb[5]
    xyz = record.values("XYZ")
    if len(xyz) == 3:
        return float(xyz[2]), float(xyz[2])
    return None


def on_floor(ctx: LegacyContext, group: str) -> list[NamelistRecord]:
    """Records of *group* on the chosen floor; others are counted elsewhere."""
    chosen = ctx.floors.index(ctx.floor)
    out = []
    for record in ctx.deck.group(group):
        where = floor_index(record, ctx.floors)
        if where == chosen:
            out.append(record)
        elif where is None:
            ctx.add("D", "warning", group, "not on any evacuation mesh", record)
    return out


# --- exits -----------------------------------------------------------------


def legacy_exits(ctx: LegacyContext) -> list[ImportedExit]:
    """``&EXIT`` and ``&DOOR`` records of the floor as exit strips."""
    exits = [_exit_from(ctx, r) for r in on_floor(ctx, "EXIT")]
    exits += [_door_from(ctx, r) for r in on_floor(ctx, "DOOR")]
    return [e for e in exits if e is not None]


def _exit_from(ctx: LegacyContext, record: NamelistRecord) -> ImportedExit | None:
    classify_keys(record, ctx.report)
    if record.flag("COUNT_ONLY", False):
        ctx.add("D", "warning", "EXIT", "COUNT_ONLY counter: no counterpart", record)
        return None
    if record.flag("KNOWN_DOOR", False) and record.id is not None:
        ctx.known_exits.append(record.id)
    return _strip_exit(ctx, record, "&EXIT")


def _door_from(ctx: LegacyContext, record: NamelistRecord) -> ImportedExit | None:
    classify_keys(record, ctx.report)
    target = _node(ctx.deck, record.text("TO_NODE"))
    if target is not None and target.group == "ENTR" and _same_floor(ctx, target):
        ctx.add(
            "D",
            "warning",
            "DOOR",
            f"teleport to &ENTR {target.id!r} on the same "
            "floor dropped; check that no agent is trapped",
            record,
        )
        return None
    found = "" if target is not None else " (TO_NODE not found)"
    exit_ = _strip_exit(ctx, record, "&DOOR")
    if exit_ is None:
        return None
    exit_.role = "door"
    ctx.add(
        "A",
        "warning",
        "DOOR",
        f"leads off the floor to {record.text('TO_NODE')!r}"
        f"{found}: imported as an exit; agents leaving here are counted as "
        "evacuated",
        record,
    )
    return exit_


def _node(deck: FdsDeck, node_id: str | None) -> NamelistRecord | None:
    groups = ("ENTR", "CORR", "STRS", "EXIT", "DOOR")
    return next(
        (r for r in deck.records if r.group in groups and r.id == node_id), None
    )


def _same_floor(ctx: LegacyContext, record: NamelistRecord) -> bool:
    return floor_index(record, ctx.floors) == ctx.floors.index(ctx.floor)


def _strip_exit(ctx, record: NamelistRecord, source: str) -> ImportedExit | None:
    line = _exit_line(ctx, record, outward=True)
    if line is None:
        return None
    _check_reachable(ctx, record, line)
    strip = exit_strip(line, ctx.depth, ctx.walkable)
    if strip is None:
        distance = line.line.distance(ctx.walkable)
        ctx.add(
            "D",
            "error",
            record.group,
            "exit dropped: its strip on the room side "
            f"is empty or narrower than 0.1 m; the line is {distance:.3f} m from "
            "the walkable area",
            record,
        )
        return None
    exit_ = ImportedExit(
        record.id or "", strip, source, (line.x0, line.y0, line.x1, line.y1)
    )
    exit_.sign = _sign(ctx, record)
    _schedule(ctx, record, exit_)
    ctx.add(
        "S",
        "info",
        record.group,
        f"exit strip {strip.area:.6g} m2 (depth {ctx.depth:g} m on the room side)",
        record,
    )
    return exit_


def _exit_line(ctx, record: NamelistRecord, outward: bool) -> ExitLine | None:
    """The record's line with its normal into the room.

    ``&EXIT``/``&DOOR`` IOR points room -> exit (``outward``), ``&ENTR`` IOR
    points entry -> room. Without IOR the side with more walkable area wins.
    """
    ior = record.number("IOR")
    try:
        x0, y0, x1, y1 = line_from_xb(
            record.xb() or (), None if ior is None else int(ior)
        )
        nx, ny = ior_normal(int(ior)) if ior is not None else (0.0, 0.0)
    except ValueError as exc:
        ctx.add("D", "error", record.group, f"dropped: {exc}", record)
        return None
    if ior is None:
        return _guess_side(ctx, record, (x0, y0, x1, y1))
    normal = (-nx, -ny) if outward else (nx, ny)
    return ExitLine(x0, y0, x1, y1, normal)


def _guess_side(ctx, record, seg) -> ExitLine:
    x0, y0, x1, y1 = seg
    axis = (1.0, 0.0) if x0 == x1 else (0.0, 1.0)
    sides = [
        ExitLine(x0, y0, x1, y1, axis),
        ExitLine(x0, y0, x1, y1, (-axis[0], -axis[1])),
    ]
    areas = [_strip_area(s, ctx) for s in sides]
    chosen = sides[0] if areas[0] >= areas[1] else sides[1]
    ctx.add(
        "A",
        "warning",
        record.group,
        f"no IOR: room side taken as normal "
        f"{chosen.normal}, the side with more walkable area",
        record,
    )
    return chosen


def _strip_area(line: ExitLine, ctx) -> float:
    strip = exit_strip(line, ctx.depth, ctx.walkable)
    return 0.0 if strip is None else strip.area


def _check_reachable(ctx, record, line: ExitLine) -> None:
    distance = line.line.distance(ctx.walkable)
    if distance > ctx.tol:
        ctx.add(
            "A",
            "warning",
            record.group,
            f"walkable_suspect: exit line is "
            f"{distance:.3f} m from the walkable area (tolerance {ctx.tol:g} m)",
            record,
        )


def _sign(ctx, record: NamelistRecord) -> dict[str, float] | None:
    xyz = record.values("XYZ")
    if len(xyz) != 3:
        return None
    ctx.add(
        "A",
        "info",
        record.group,
        "XYZ -> omni-directional sign, c = 3 (FDS+Evac has no viewing-angle factor)",
        record,
    )
    return {"x": float(xyz[0]), "y": float(xyz[1]), "c": 3}


def _schedule(ctx, record: NamelistRecord, exit_: ImportedExit) -> None:
    opened, closed = record.number("TIME_OPEN"), record.number("TIME_CLOSE")
    if opened is None and closed is None:
        return
    if opened is not None and closed is not None and closed <= opened:
        ctx.add(
            "D",
            "warning",
            record.group,
            f"TIME_CLOSE {closed:g} <= TIME_OPEN {opened:g}: schedule dropped",
            record,
        )
        return
    exit_.open_from_s, exit_.closed_after_s = opened, closed
    locked = record.flag("LOCKED_WHEN_CLOSED", False)
    note = (
        ""
        if locked
        else (
            " FDS+Evac lets agents pass a closed exit unless "
            "LOCKED_WHEN_CLOSED; here nobody leaves while it is closed"
        )
    )
    ctx.add(
        "A",
        "info" if locked else "warning",
        record.group,
        f"schedule open_from_s={opened}, closed_after_s={closed}.{note}",
        record,
    )


# --- spawn areas -----------------------------------------------------------


def legacy_spawns(ctx: LegacyContext, exit_ids: list[str]) -> list[ImportedSpawn]:
    """``&EVAC`` (minus ``&EVHO``) and ``&ENTR`` records as spawn areas."""
    for record in ctx.deck.group("PERS"):
        _pers(ctx, record.id)
    evhos = on_floor(ctx, "EVHO")
    for record in evhos:
        classify_keys(record, ctx.report)
    spawns: list[ImportedSpawn] = []
    for record in on_floor(ctx, "EVAC"):
        spawns += _evac_spawns(ctx, record, evhos, exit_ids)
    for record in on_floor(ctx, "ENTR"):
        spawns += _entr_spawns(ctx, record, exit_ids)
    return spawns


def _pers(ctx: LegacyContext, pers_id: str | None) -> dict[str, Any]:
    """Speed keys of a ``&PERS``, computed once (its report items once too)."""
    if pers_id is None:
        return {}
    if pers_id in ctx.pers_cache:
        return ctx.pers_cache[pers_id]
    record = next((r for r in ctx.deck.group("PERS") if r.id == pers_id), None)
    if record is None:
        return {}
    classify_keys(record, ctx.report)
    people.body_size_note(record, ctx.add)
    try:
        speed = people.speed_parameters(record, ctx.add)
    except ValueError as exc:
        ctx.add("D", "warning", "PERS", f"speed not mapped: {exc}", record)
        speed = {}
    ctx.pers_cache[pers_id] = speed
    return speed


def _pers_record(ctx, record: NamelistRecord) -> NamelistRecord | None:
    pers_id = record.text("PERS_ID")
    if pers_id is None:
        return None
    found = next((r for r in ctx.deck.group("PERS") if r.id == pers_id), None)
    if found is None:
        raise ValueError(
            f"&{record.group} {record.label} (line {record.line}): "
            f"PERS_ID {pers_id!r} names no &PERS record"
        )
    return found


def _evac_spawns(ctx, record, evhos, exit_ids) -> list[ImportedSpawn]:
    classify_keys(record, ctx.report)
    number = int(record.num("NUMBER_INITIAL_PERSONS", 0) or 0)
    if number <= 0:
        ctx.add("D", "info", "EVAC", "NUMBER_INITIAL_PERSONS is 0: no agents", record)
        return []
    rect = box(*_rect(record))
    if not _inside_enough(ctx, record, rect):
        return []
    pers = _pers_record(ctx, record)
    params = _group_parameters(ctx, record, pers, exit_ids)
    params.update(_delay(ctx, pers, record))
    pieces = _minus_evho(ctx, record, rect, evhos)
    return _share(ctx, record, pieces, number, params)


def _rect(record: NamelistRecord) -> tuple[float, float, float, float]:
    x0, x1, y0, y1 = record.box6()[:4]
    return x0, y0, x1, y1


def _inside_enough(ctx, record, rect) -> bool:
    share = rect.intersection(ctx.walkable).area / rect.area if rect.area else 0.0
    if share < 0.05:
        ctx.add(
            "D",
            "error",
            record.group,
            f"walkable_suspect: only {share:.1%} of the "
            "area is walkable; group dropped",
            record,
        )
        return False
    if share < 0.5:
        ctx.add(
            "A",
            "warning",
            record.group,
            f"walkable_suspect: only {share:.1%} of the area is walkable",
            record,
        )
    return True


def _group_parameters(ctx, record, pers, exit_ids) -> dict[str, Any]:
    params = dict(_pers(ctx, pers.id if pers is not None else None))
    params.update(
        people.familiarity_parameters(
            record, exit_ids, ctx.known_exits, ctx.add, record.group
        )
    )
    return params


def _delay(ctx, pers, record) -> dict[str, Any]:
    try:
        return people.delay_parameters(pers, record, ctx.add, record.group)
    except ValueError as exc:
        ctx.add(
            "D",
            "warning",
            record.group,
            f"delay not mapped ({exc}); the loader default applies",
            record,
        )
        return {}


def _minus_evho(ctx, record, rect, evhos) -> list:
    holes = [e for e in evhos if _evho_applies(e, record)]
    if not holes:
        return [rect]
    shape = rect.difference(union([box(*_rect(h)) for h in holes]))
    pieces = [p for poly in polygons_of(shape) for p in split_holes(poly)]
    for hole in holes:
        ctx.add(
            "A",
            "info",
            "EVHO",
            f"subtracted from &EVAC {record.id!r}; spawn area "
            f"split into {len(pieces)} hole-free piece(s)",
            hole,
        )
    return pieces


def _evho_applies(evho: NamelistRecord, evac: NamelistRecord) -> bool:
    evac_id, pers_id = evho.text("EVAC_ID"), evho.text("PERS_ID")
    if evac_id is None and pers_id is None:
        return True
    return evac_id == evac.id or (
        pers_id is not None and pers_id == evac.text("PERS_ID")
    )


def _share(ctx, record, pieces, number, params) -> list[ImportedSpawn]:
    counts = largest_remainder(number, [p.area for p in pieces])
    base = record.id or f"{record.group}_{record.line}"
    out = []
    for index, (piece, count) in enumerate(zip(pieces, counts, strict=True), 1):
        if count == 0:
            continue
        name = base if len(pieces) == 1 else f"{base}_{index}"
        out.append(
            ImportedSpawn(
                name,
                piece,
                f"&{record.group}",
                {**params, "number": count},
                parent=(record.group, record.line),
            )
        )
    ctx.add("S", "info", record.group, f"{number} agents in {len(out)} area(s)", record)
    return out


def _entr_spawns(ctx, record, exit_ids) -> list[ImportedSpawn]:
    classify_keys(record, ctx.report)
    flow = record.num("MAX_FLOW", 0.0) or 0.0
    if flow <= 0:
        ctx.add(
            "D",
            "info",
            "ENTR",
            "MAX_FLOW is 0 (fed by a &DOOR or a ramp): no agents created here",
            record,
        )
        return []
    line = _exit_line(ctx, record, outward=False)
    strip = None if line is None else exit_strip(line, ctx.depth, ctx.walkable)
    if strip is None:
        ctx.add(
            "D",
            "error",
            "ENTR",
            "entry dropped: no walkable strip on its room side",
            record,
        )
        return []
    start, stop = _entry_window(ctx, record)
    number = _entry_number(ctx, record, flow, stop - start)
    pers = _pers_record(ctx, record)
    params = _group_parameters(ctx, record, pers, exit_ids)
    _no_entry_delay(ctx, pers, record)
    params.update(
        {
            "number": number,
            "use_flow_spawning": True,
            "flow_start_time": start,
            "flow_end_time": stop,
        }
    )
    ctx.add(
        "A",
        "info",
        "ENTR",
        f"flow spawning: {number} agents over [{start:g}, {stop:g}] s",
        record,
    )
    name = record.id or f"ENTR_{record.line}"
    return [ImportedSpawn(name, strip, "&ENTR", params, parent=("ENTR", record.line))]


def _entry_window(ctx, record) -> tuple[float, float]:
    start = record.num("TIME_START", ctx.t_begin)
    stop = record.number("TIME_STOP")
    if stop is None:
        stop = ctx.t_end if ctx.t_end is not None else 300.0
        ctx.add(
            "A",
            "warning",
            "ENTR",
            f"no TIME_STOP: the entry never stops in "
            f"FDS+Evac; flow ends at T_END = {stop:g} s",
            record,
        )
    return start, stop


def _entry_number(ctx, record, flow: float, duration: float) -> int:
    limit = record.number("MAX_HUMANS")
    number = int(limit) if limit is not None else round(flow * max(duration, 0.0))
    rate = number / duration if duration > 0 else 0.0
    if abs(rate - flow) > 1e-9:
        ctx.add(
            "A",
            "warning",
            "ENTR",
            f"{number} agents over {duration:g} s is "
            f"{rate:.4g} agents/s, not MAX_FLOW = {flow:g}",
            record,
        )
    return number


def _no_entry_delay(ctx, pers, record) -> None:
    has_delay = any(
        k.startswith(("PRE_", "DET_")) for k in (pers.params if pers else {})
    )
    if has_delay:
        ctx.add(
            "D",
            "warning",
            "ENTR",
            "flow-spawned agents start at once; the &PERS delay is not applied",
            record,
        )


def dropped_groups(deck: FdsDeck, report: ImportReport) -> None:
    """Items for whole groups with no counterpart, and ``&MISC EVACUATION_*``."""
    for record in deck.records:
        reason = DROPPED_GROUPS.get(record.group)
        if reason:
            report.add("D", "warning", record.group, reason, record)
    for record in deck.group("MISC"):
        for key in (k for k in record.params if k.startswith("EVAC")):
            report.add("C", "info", "MISC", f"{key} ignored", record)
