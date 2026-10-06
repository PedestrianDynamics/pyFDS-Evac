"""Start a pyFDS-Evac scenario from an FDS deck.

:func:`import_fds_deck` reads one ``.fds`` file and returns the scenario
``config.json`` content, the walkable WKT and an :class:`ImportReport`; the
run model is untouched (``load_scenario`` reads the written directory as any
other scenario).

- *Legacy* decks (FDS+Evac: an evacuation ``&MESH`` or any evacuation
  namelist) map ``&EXIT``/``&DOOR`` to exits and ``&EVAC``/``&EVHO``/
  ``&ENTR``/``&PERS`` to spawn areas, on one floor.
- *Modern* decks get exits from ``SURF_ID='OPEN'`` vents on the exterior of
  the mesh union within the walking band, plus any ``--exit``; spawn areas
  fill each walkable component that has an exit, with a flagged placeholder
  of 100 agents unless ``agents`` is given.

Everything stays in the FDS frame. The output is deterministic: sorted keys,
coordinates rounded to 1e-6 m, IDs from the deck or ``<group>_<n>``.

The model contract (mapping table, rules, maintainer decisions) is the
import task record; this module imports neither JuPedSim nor fdsreader.
"""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any

from shapely import wkt as shapely_wkt
from shapely.geometry import LineString, Point, box

from .fds_deck import FdsDeck, NamelistRecord, parse_fds_deck
from .fds_import_geometry import (
    ExitLine,
    exit_strip,
    ior_normal,
    largest_remainder,
    polygons_of,
    ring_coordinates,
    rounded,
    union,
)
from .fds_import_legacy import (
    LegacyContext,
    dropped_groups,
    legacy_exits,
    legacy_spawns,
)
from .fds_import_legacy import floor_index as _floor_index
from .fds_import_people import HUMAN_SMOKE_HEIGHT_M
from .fds_import_report import (
    Floor,
    ImportedExit,
    ImportedSpawn,
    ImportReport,
    ReportItem,
)
from .fds_sampling import _SLICE_HEIGHT_TOLERANCE_M
from .walkable_provider import (
    FloorSpec,
    WalkableProvider,
    WalkableResult,
    script_walkable,
)

__all__ = [
    "FdsImportError",
    "ImportResult",
    "import_fds_deck",
    "parse_fds_deck",
]

#: Evacuation namelists that make a deck legacy (FDS+Evac).
EVAC_GROUPS = frozenset(
    {"EVAC", "EXIT", "PERS", "DOOR", "ENTR", "CORR", "EVHO", "EVSS", "STRS", "EDEV"}
)
#: Default exit strip depth [m] (rule E1).
EXIT_DEPTH_M = 0.5
#: Agents written for a modern deck without ``agents`` (flagged placeholder).
PLACEHOLDER_AGENTS = 100
#: Above this density [persons/m2] a spawn area is flagged (FDS+Evac Guide).
PACKING_LIMIT_PER_M2 = 4.0
#: Walking band above the floor for a modern deck [m] (the script's default).
MODERN_BAND_M = (0.1, 1.8)
#: ``&TIME T_END`` when the deck has none [s].
DEFAULT_MAX_TIME_S = 300.0
#: An OPEN vent wider than this is flagged as a possible open boundary [m].
WIDE_OPENING_M = 5.0
#: Slices pyFDS-Evac reads: (QUANTITY, SPEC_ID).
NEEDED_SLICES = (
    ("EXTINCTION COEFFICIENT", None),
    ("VOLUME FRACTION", "CARBON MONOXIDE"),
    ("VOLUME FRACTION", "CARBON DIOXIDE"),
    ("VOLUME FRACTION", "OXYGEN"),
    ("TEMPERATURE", None),
)
_FACES = ("XMIN", "XMAX", "YMIN", "YMAX", "ZMIN", "ZMAX")


class FdsImportError(ValueError):
    """The deck cannot be imported; nothing is written."""


@dataclass
class ImportResult:
    """The scenario files of one import and its report."""

    raw: dict[str, Any]
    walkable_wkt: str
    report: ImportReport
    deck_path: Path

    def run_command(self, out_dir: str | Path) -> str:
        command = f"pyfds-evac --scenario {out_dir}"
        fds_dir = self.report.recommendations.get("fds_dir")
        return command + (f" --fds-dir {fds_dir}" if fds_dir else "")

    def write(self, out_dir: str | Path) -> Path:
        """Write ``config.json``, ``geometry.wkt`` and ``import_report.json``."""
        target = Path(out_dir)
        target.mkdir(parents=True, exist_ok=True)
        self.report.recommendations["run_command"] = self.run_command(out_dir)
        _dump(target / "config.json", self.raw)
        (target / "geometry.wkt").write_text(self.walkable_wkt + "\n", encoding="utf-8")
        _dump(target / "import_report.json", self.report.to_dict())
        return target


def _dump(path: Path, data: dict[str, Any]) -> None:
    text = json.dumps(data, indent=2, sort_keys=True, allow_nan=False)
    path.write_text(text + "\n", encoding="utf-8")


@dataclass
class _Options:
    floor: str | None
    floor_z: float | None
    z_band: tuple[float, float] | None
    depth: float
    agents: int | None
    exits: Sequence[Sequence[float]]


def import_fds_deck(
    path: str | Path,
    *,
    floor: str | None = None,
    floor_z: float | None = None,
    z_band: tuple[float, float] | None = None,
    walkable_wkt: str | None = None,
    derive_walkable: WalkableProvider | None = None,
    agents: int | None = None,
    exits: Sequence[Sequence[float]] = (),
    exit_depth: float = EXIT_DEPTH_M,
    layer_rules: str = "none",
) -> ImportResult:
    """Import the FDS deck at *path*; see the module docstring.

    ``walkable_wkt`` (WKT text) skips derivation; otherwise
    ``derive_walkable`` (default: the walkable script with *layer_rules*)
    makes the polygon. ``exits`` are extra exit lines
    ``(x0, y0, x1, y1[, ior])``. Raises :class:`FdsImportError` (or the
    parser's/provider's ``ValueError``) when nothing can be written.
    """
    _check_options(exit_depth, agents)
    deck_path = Path(path)
    deck = parse_fds_deck(deck_path)
    opts = _Options(floor, floor_z, z_band, exit_depth, agents, exits)
    kind = _classify(deck)
    report = ImportReport(deck=deck_path.name, chid=deck.chid, kind=kind)
    _parser_items(deck, report)
    provider = derive_walkable or partial(script_walkable, layer_rules=layer_rules)
    build = _import_legacy if kind == "legacy" else _import_modern
    return build(deck, deck_path, opts, report, walkable_wkt, provider)


def _check_options(depth: float, agents: int | None) -> None:
    if not (math.isfinite(depth) and depth > 0):
        raise FdsImportError(
            f"exit depth must be a positive number of metres, got {depth}"
        )
    if agents is not None and agents < 0:
        raise FdsImportError(f"agents must be >= 0, got {agents}")


def _classify(deck: FdsDeck) -> str:
    evac_mesh = any(m.flag("EVACUATION", False) for m in deck.group("MESH"))
    evac_records = any(r.group in EVAC_GROUPS for r in deck.records)
    return "legacy" if evac_mesh or evac_records else "modern"


def _parser_items(deck: FdsDeck, report: ImportReport) -> None:
    for issue in deck.issues:
        report.items.append(
            ReportItem(
                issue.status,
                "warning",
                issue.group,
                issue.id,
                issue.line,
                issue.message,
            )
        )


# --- floors ------------------------------------------------------------------


def _mesh_box(mesh: NamelistRecord):
    x0, x1, y0, y1 = mesh.box6()[:4]
    return box(x0, y0, x1, y1)


def _mesh_dx(mesh: NamelistRecord) -> float | None:
    ijk = mesh.values("IJK")
    if len(ijk) != 3:
        return None
    x0, x1, y0, y1 = mesh.box6()[:4]
    return min((x1 - x0) / float(ijk[0]), (y1 - y0) / float(ijk[1]))


def _min_dx(meshes) -> float | None:
    values = [d for d in (_mesh_dx(m) for m in meshes) if d]
    return min(values) if values else None


def _meshes(deck: FdsDeck, evacuation: bool) -> list[NamelistRecord]:
    meshes = [m for m in deck.group("MESH") if m.xb() is not None]
    return [m for m in meshes if bool(m.flag("EVACUATION", False)) == evacuation]


def _evac_floors(deck: FdsDeck, report: ImportReport) -> list[Floor]:
    """Main evacuation meshes grouped by overlapping z; lowest z_floor first."""
    evac = _meshes(deck, evacuation=True)
    main = [m for m in evac if m.flag("EVAC_HUMANS", False)] or evac
    groups: list[list[NamelistRecord]] = []
    for mesh in sorted(main, key=lambda m: (m.box6()[4], m.line)):
        _place_in_group(groups, mesh)
    floors = [_floor_of(g, report) for g in groups]
    return sorted(floors, key=lambda f: (f.z_floor, f.slab))


def _place_in_group(groups: list[list[NamelistRecord]], mesh: NamelistRecord) -> None:
    z0, z1 = mesh.box6()[4:]
    for group in groups:
        if any(z0 <= m.box6()[5] and z1 >= m.box6()[4] for m in group):
            group.append(mesh)
            return
    groups.append([mesh])


def _floor_of(meshes: list[NamelistRecord], report: ImportReport) -> Floor:
    meshes = sorted(meshes, key=lambda m: m.line)
    levels = [
        (m.box6()[4] + m.box6()[5]) / 2 - m.num("EVAC_Z_OFFSET", 1.0) for m in meshes
    ]
    if max(levels) - min(levels) > 1e-9:
        report.add(
            "A",
            "warning",
            "MESH",
            f"evacuation meshes of one floor give "
            f"floor levels {sorted(set(levels))}; the lowest is used",
            meshes[0],
        )
    slab = (min(m.box6()[4] for m in meshes), max(m.box6()[5] for m in meshes))
    name = meshes[0].id or f"MESH_{meshes[0].line}"
    return Floor(name, tuple(meshes), min(levels), slab, _min_dx(meshes))


def _choose_floor(floors: list[Floor], wanted: str | None) -> Floor:
    if wanted is None:
        return floors[0]
    for floor in floors:
        if wanted in {m.id for m in floor.meshes}:
            return floor
    ids = sorted(m.id for f in floors for m in f.meshes if m.id)
    raise FdsImportError(f"--floor {wanted!r} names no evacuation mesh; known: {ids}")


def _modern_floor(deck: FdsDeck, opts: _Options) -> Floor:
    meshes = _meshes(deck, evacuation=False) or _meshes(deck, evacuation=True)
    if not meshes:
        raise FdsImportError("the deck has no &MESH with XB; nothing to import")
    z_floor = (
        opts.floor_z if opts.floor_z is not None else min(m.box6()[4] for m in meshes)
    )
    slab = (z_floor + MODERN_BAND_M[0], z_floor + MODERN_BAND_M[1])
    return Floor(
        "lowest" if opts.floor_z is None else "floor_z",
        tuple(meshes),
        z_floor,
        slab,
        _min_dx(meshes),
    )


def _floor_obstructions(deck: FdsDeck, floor: Floor, band, legacy: bool):
    """``&OBST`` records of this floor: ``EVACUATION`` and ``MESH_ID`` honoured."""
    mesh_ids = {m.id for m in floor.meshes}
    out = []
    for record in deck.group("OBST"):
        if _obst_applies(record, mesh_ids, band, legacy):
            out.append(record)
    return tuple(out)


def _obst_applies(record: NamelistRecord, mesh_ids, band, legacy: bool) -> bool:
    evacuation = record.flag("EVACUATION")
    if evacuation is (not legacy):
        return False
    mesh_id = record.text("MESH_ID")
    if mesh_id is not None and mesh_id not in mesh_ids:
        return False
    xb = record.xb()
    return xb is not None and xb[5] >= band[0] and xb[4] <= band[1]


# --- walkable ----------------------------------------------------------------


def _walkable(deck, floor_spec: FloorSpec, user_wkt, provider, report) -> Any:
    if user_wkt is not None:
        result = WalkableResult(_load_wkt(user_wkt), [], "user")
    else:
        result = provider(deck, floor_spec)
    polygon = result.polygon
    if polygon is None or polygon.is_empty or not polygon.is_valid or polygon.area <= 0:
        raise FdsImportError(
            f"the walkable area ({result.source}) is empty or invalid; no scenario written"
        )
    if polygon.geom_type not in ("Polygon", "MultiPolygon"):
        raise FdsImportError(
            f"the walkable area is a {polygon.geom_type}, not a polygon"
        )
    parts = polygons_of(polygon)
    report.walkable = {
        "source": result.source,
        "area_m2": rounded(polygon.area),
        "components": len(parts),
        "holes": sum(len(p.interiors) for p in parts),
        "diagnostics": list(result.diagnostics),
    }
    return polygon


def _load_wkt(text: str):
    try:
        return shapely_wkt.loads(text)
    except Exception as exc:  # shapely raises its own GEOSException types
        raise FdsImportError(f"cannot read the walkable WKT: {exc}") from exc


# --- legacy ------------------------------------------------------------------


def _import_legacy(deck, deck_path, opts, report, user_wkt, provider) -> ImportResult:
    floors = _evac_floors(deck, report)
    if not floors:
        report.add(
            "A",
            "warning",
            "MESH",
            "evacuation namelists but no evacuation "
            "mesh: the floor is taken from the fire meshes",
        )
        floors = [_modern_floor(deck, opts)]
    floor = _choose_floor(floors, opts.floor)
    band = opts.z_band or floor.slab
    domain = union([_mesh_box(m) for m in floor.meshes])
    spec = FloorSpec(
        floor.z_floor,
        band,
        domain,
        tuple(m.id or "" for m in floor.meshes),
        _floor_obstructions(deck, floor, band, legacy=True),
    )
    walkable = _walkable(deck, spec, user_wkt, provider, report)
    tol = max(floor.dx or 0.0, 0.05)
    time = deck.first("TIME")
    ctx = LegacyContext(
        deck,
        floor,
        floors,
        walkable,
        opts.depth,
        tol,
        report,
        t_begin=time.num("T_BEGIN", 0.0) if time else 0.0,
        t_end=time.number("T_END") if time else None,
    )
    exits = _unique(legacy_exits(ctx) + _user_exits(opts, walkable, report), "EXIT")
    spawns = _unique_spawns(legacy_spawns(ctx, [e.id for e in exits]))
    dropped_groups(deck, report)
    _floors_not_imported(deck, floors, floor, report)
    height = floor.z_floor + _human_smoke_height(deck)
    return _finish(
        deck,
        deck_path,
        report,
        floor,
        band,
        domain,
        tol,
        walkable,
        exits,
        spawns,
        height,
    )


def _human_smoke_height(deck: FdsDeck) -> float:
    """The last ``HUMAN_SMOKE_HEIGHT`` read wins, as in FDS+Evac."""
    values = [
        v
        for p in deck.group("PERS")
        if (v := p.number("HUMAN_SMOKE_HEIGHT")) is not None
    ]
    return values[-1] if values else HUMAN_SMOKE_HEIGHT_M


def _floors_not_imported(deck, floors, chosen, report) -> None:
    for index, floor in enumerate(floors):
        if floor is chosen:
            continue
        records = [r for r in deck.records if _floor_index(r, floors) == index]
        evac = [r for r in records if r.group == "EVAC"]
        agents = sum(int(r.num("NUMBER_INITIAL_PERSONS", 0) or 0) for r in evac)
        entry = {
            "id": floor.id,
            "z_floor": rounded(floor.z_floor),
            "agents": agents,
            "evac": len(evac),
            "exit": sum(r.group == "EXIT" for r in records),
            "door": sum(r.group == "DOOR" for r in records),
        }
        report.floors_not_imported.append(entry)
        report.add(
            "D",
            "warning",
            "MESH",
            f"floor {floor.id!r} (z_floor "
            f"{floor.z_floor:g} m) not imported: {agents} agents dropped; "
            "pick it with --floor",
            id=floor.id,
        )


# --- modern ------------------------------------------------------------------


def _import_modern(deck, deck_path, opts, report, user_wkt, provider) -> ImportResult:
    floor = _modern_floor(deck, opts)
    band = opts.z_band or floor.slab
    domain = union([_mesh_box(m) for m in floor.meshes])
    spec = FloorSpec(
        floor.z_floor,
        band,
        domain,
        None,
        _floor_obstructions(deck, floor, band, legacy=False),
    )
    walkable = _walkable(deck, spec, user_wkt, provider, report)
    tol = max(floor.dx or 0.0, 0.05)
    exits = _vent_exits(deck, floor, band, domain, walkable, opts.depth, report)
    exits = _unique(exits + _user_exits(opts, walkable, report), "EXIT")
    spawns = _modern_spawns(walkable, exits, opts.agents, report)
    _upper_floor_warnings(deck, floor, domain, report)
    return _finish(
        deck,
        deck_path,
        report,
        floor,
        band,
        domain,
        tol,
        walkable,
        exits,
        spawns,
        floor.z_floor + HUMAN_SMOKE_HEIGHT_M,
    )


def _vent_exits(deck, floor, band, domain, walkable, depth, report):
    """Tier X1: ``SURF_ID='OPEN'`` vents on the exterior within the band."""
    exits = []
    for index, vent in enumerate(deck.group("VENT"), 1):
        if str(vent.text("SURF_ID", "")).upper() != "OPEN":
            continue
        name = vent.id or f"vent_{index}"
        for plane in _vent_planes(vent, floor.meshes, domain):
            exits += _plane_exits(
                vent, name, plane, band, domain, walkable, depth, report
            )
    return exits


def _vent_planes(vent: NamelistRecord, meshes, domain) -> list[tuple]:
    """The vent's XB, or the faces its MB/DB names."""
    if vent.xb() is not None:
        return [vent.box6()]
    if vent.has("DB"):
        bounds = domain.bounds
        z = (min(m.box6()[4] for m in meshes), max(m.box6()[5] for m in meshes))
        return [
            _face(
                vent.text("DB") or "", (bounds[0], bounds[2], bounds[1], bounds[3], *z)
            )
        ]
    if vent.has("MB"):
        return [_face(vent.text("MB") or "", m.box6()) for m in meshes]
    return []


def _face(name: str, xb: tuple) -> tuple:
    face = str(name).upper()
    if face not in _FACES:
        raise FdsImportError(f"unknown vent face {name!r}")
    x0, x1, y0, y1, z0, z1 = xb
    axis, high = _FACES.index(face) // 2, _FACES.index(face) % 2
    planes = {
        0: (x1, x1, y0, y1, z0, z1) if high else (x0, x0, y0, y1, z0, z1),
        1: (x0, x1, y1, y1, z0, z1) if high else (x0, x1, y0, y0, z0, z1),
        2: (x0, x1, y0, y1, z1, z1) if high else (x0, x1, y0, y1, z0, z0),
    }
    return planes[axis]


def _plane_exits(vent, name, xb, band, domain, walkable, depth, report) -> list:
    x0, x1, y0, y1, z0, z1 = xb
    if z1 - z0 < 1e-9:
        report.add("D", "info", "VENT", "horizontal OPEN vent: not an exit", vent)
        return []
    if not (z1 >= band[0] and z0 <= band[1]):
        report.add(
            "D",
            "info",
            "VENT",
            f"OPEN vent at z {z0:g}..{z1:g} m is outside the "
            f"walking band {band[0]:g}..{band[1]:g} m: not an exit",
            vent,
        )
        return []
    if abs(x1 - x0) > 1e-9 and abs(y1 - y0) > 1e-9:
        report.add(
            "D", "warning", "VENT", "OPEN vent is not a plane: not an exit", vent
        )
        return []
    segment = LineString([(x0, y0), (x1, y1)]).intersection(domain.boundary)
    pieces = [g for g in _lines_of(segment) if g.length > 1e-9]
    if not pieces:
        report.add(
            "D",
            "info",
            "VENT",
            "OPEN vent between meshes, not on the exterior of the domain: not an exit",
            vent,
        )
        return []
    return [
        e
        for e in (
            _vent_exit(vent, name, p, domain, walkable, depth, report) for p in pieces
        )
        if e is not None
    ]


def _lines_of(geometry) -> list[LineString]:
    if geometry.is_empty:
        return []
    if isinstance(geometry, LineString):
        return [geometry]
    return [g for g in getattr(geometry, "geoms", []) if isinstance(g, LineString)]


def _vent_exit(vent, name, piece: LineString, domain, walkable, depth, report):
    (ax, ay), (bx, by) = piece.coords[0], piece.coords[-1]
    normal = _inward_normal(piece, domain)
    if normal is None:
        return None
    line = ExitLine(ax, ay, bx, by, normal)
    strip = exit_strip(line, depth, walkable)
    if strip is None:
        report.add(
            "D",
            "warning",
            "VENT",
            f"OPEN vent {name!r}: its strip does not reach "
            f"the walkable area ({line.line.distance(walkable):.3f} m away)",
            vent,
        )
        return None
    _flag_wide(vent, line, domain, report)
    mx, my = (
        (ax + bx) / 2 + normal[0] * depth / 2,
        (ay + by) / 2 + normal[1] * depth / 2,
    )
    report.add(
        "S", "info", "VENT", f"OPEN vent on the exterior -> exit {name!r} (X1)", vent
    )
    return ImportedExit(
        name,
        strip,
        "X1",
        (ax, ay, bx, by),
        sign={"x": rounded(mx), "y": rounded(my), "c": 3},
    )


def _inward_normal(piece: LineString, domain) -> tuple[float, float] | None:
    (ax, ay), (bx, by) = piece.coords[0], piece.coords[-1]
    axis = (1.0, 0.0) if abs(ax - bx) < 1e-9 else (0.0, 1.0)
    mid = ((ax + bx) / 2, (ay + by) / 2)
    for sign in (1.0, -1.0):
        probe = Point(mid[0] + sign * axis[0] * 1e-4, mid[1] + sign * axis[1] * 1e-4)
        if domain.contains(probe):
            return (sign * axis[0], sign * axis[1])
    return None


def _flag_wide(vent, line: ExitLine, domain, report) -> None:
    minx, miny, maxx, maxy = domain.bounds
    face = (maxy - miny) if line.normal[0] else (maxx - minx)
    if line.width > WIDE_OPENING_M or line.width >= 0.8 * face:
        report.add(
            "A",
            "warning",
            "VENT",
            f"wide opening ({line.width:g} m): may be an open boundary, not a door",
            vent,
        )


def _user_exits(opts: _Options, walkable, report) -> list[ImportedExit]:
    """Tier X3: ``--exit x0,y0,x1,y1[,ior]``."""
    out = []
    for index, spec in enumerate(opts.exits, 1):
        out.append(
            _user_exit(
                index, tuple(float(v) for v in spec), walkable, opts.depth, report
            )
        )
    return out


def _user_exit(index, spec, walkable, depth, report) -> ImportedExit:
    if len(spec) not in (4, 5):
        raise FdsImportError(f"--exit needs x0,y0,x1,y1[,ior], got {spec}")
    x0, y0, x1, y1 = spec[:4]
    if abs(x0 - x1) > 1e-9 and abs(y0 - y1) > 1e-9:
        raise FdsImportError(f"--exit {spec}: the line must be parallel to x or y")
    lines = _candidate_lines((x0, y0, x1, y1), spec[4] if len(spec) == 5 else None)
    strips = [
        (strip, line)
        for line in lines
        if (strip := exit_strip(line, depth, walkable)) is not None
    ]
    if not strips:
        raise FdsImportError(f"--exit {spec}: no walkable strip next to the line")
    strip, line = max(strips, key=lambda pair: pair[0].area)
    name = f"user_exit_{index}"
    report.add(
        "S", "info", "--exit", f"exit {name!r} from the command line (X3)", id=name
    )
    return ImportedExit(name, strip, "X3", (x0, y0, x1, y1))


def _candidate_lines(seg, ior) -> list[ExitLine]:
    x0, y0, x1, y1 = seg
    if ior is not None:
        nx, ny = ior_normal(int(ior))
        return [ExitLine(x0, y0, x1, y1, (-nx, -ny))]
    axis = (1.0, 0.0) if abs(x0 - x1) < 1e-9 else (0.0, 1.0)
    return [
        ExitLine(x0, y0, x1, y1, axis),
        ExitLine(x0, y0, x1, y1, (-axis[0], -axis[1])),
    ]


def _modern_spawns(walkable, exits, agents, report) -> list[ImportedSpawn]:
    strips = union([e.polygon for e in exits]) if exits else None
    pieces = []
    for index, component in enumerate(polygons_of(walkable)):
        pieces += _component_pieces(index, component, exits, strips, report)
    placeholder = agents is None
    total = PLACEHOLDER_AGENTS if placeholder else agents
    counts = largest_remainder(total, [p.area for p in pieces])
    if placeholder and pieces:
        report.add(
            "A",
            "warning",
            "spawn",
            f"placeholder: {total} agents; the deck has "
            "no occupant count and no neutral occupant density exists. Pass "
            "--agents N",
            id="placeholder",
        )
    return [
        ImportedSpawn(f"spawn_{i}", piece, "inferred", {"number": n}, placeholder)
        for i, (piece, n) in enumerate(zip(pieces, counts, strict=True), 1)
        if n > 0
    ]


def _component_pieces(index, component, exits, strips, report) -> list:
    if not any(e.polygon.intersection(component).area > 0 for e in exits):
        report.add(
            "A",
            "warning",
            "spawn",
            f"walkable component {index} "
            f"({component.area:.3f} m2) has no exit: no agents placed there",
            id=f"component_{index}",
        )
        return []
    rest = component if strips is None else component.difference(strips)
    return polygons_of(rest)


def _upper_floor_warnings(deck, floor: Floor, domain, report) -> None:
    """A horizontal solid covering half the footprint above head height."""
    z_max = max(m.box6()[5] for m in floor.meshes)
    tops: dict[float, list] = {}
    for record in deck.group("OBST"):
        xb = record.xb()
        if xb is None or not (floor.z_floor + 2.0 < xb[5] < z_max):
            continue
        tops.setdefault(round(xb[5], 6), []).append(box(xb[0], xb[2], xb[1], xb[3]))
    for z_top, boxes in sorted(tops.items()):
        if union(boxes).intersection(domain).area >= 0.5 * domain.area:
            report.add(
                "A",
                "warning",
                "OBST",
                f"possible upper floor at z = {z_top:g} m, not imported",
                id=f"z={z_top:g}",
            )


# --- checks, settings, output ------------------------------------------------


def _unique(exits: list[ImportedExit], group: str) -> list[ImportedExit]:
    used: set[str] = set()
    for index, exit_ in enumerate(exits, 1):
        base = exit_.id or f"{group}_{index}"
        name, n = base, 1
        while name in used:
            n += 1
            name = f"{base}_{n}"
        exit_.id = name
        used.add(name)
    return exits


def _unique_spawns(spawns: list[ImportedSpawn]) -> list[ImportedSpawn]:
    used: set[str] = set()
    for spawn in spawns:
        name, n = spawn.id, 1
        while name in used:
            n += 1
            name = f"{spawn.id}_{n}"
        spawn.id = name
        used.add(name)
    return spawns


def _finish(
    deck, deck_path, report, floor, band, domain, tol, walkable, exits, spawns, height
) -> ImportResult:
    _check_connectivity(walkable, exits, spawns, report)
    _check_extent(walkable, domain, tol, report)
    _check_density(walkable, spawns, report)
    report.floor = {
        "id": floor.id,
        "z_floor": rounded(floor.z_floor),
        "z_band": [rounded(band[0]), rounded(band[1])],
        "meshes": [m.id for m in floor.meshes],
    }
    report.exits = [_exit_report(e) for e in exits]
    report.distributions = [_spawn_report(s, walkable) for s in spawns]
    _recommend(deck, deck_path, report, walkable, exits, height)
    _runnable(report, exits, spawns)
    raw = _raw(deck, report, exits, spawns, height)
    text = shapely_wkt.dumps(walkable, rounding_precision=6, trim=True)
    return ImportResult(raw, text, report, deck_path)


def _check_connectivity(walkable, exits, spawns, report) -> None:
    components = polygons_of(walkable)
    with_exit = [
        any(e.polygon.intersection(c).area > 0 for e in exits) for c in components
    ]
    for spawn in spawns:
        hit = [
            i
            for i, c in enumerate(components)
            if spawn.polygon.intersection(c).area > 0
        ]
        if hit and not any(with_exit[i] for i in hit):
            report.add(
                "A",
                "warning",
                "spawn",
                f"walkable_suspect: agents in component {hit[0]} cannot reach any exit",
                id=spawn.id,
            )


def _check_extent(walkable, domain, tol, report) -> None:
    ratio = walkable.area / domain.area if domain.area else 0.0
    if not 0.05 <= ratio <= 1.0 + 1e-9:
        report.add(
            "A",
            "warning",
            "walkable",
            f"walkable_suspect: walkable area is {ratio:.1%} of the domain",
            id="extent",
        )
    if not walkable.within(domain.buffer(tol)):
        report.add(
            "A",
            "warning",
            "walkable",
            "walkable_suspect: the polygon reaches "
            f"more than {tol:g} m beyond the selected domain",
            id="domain_edge",
        )


def _check_density(walkable, spawns, report) -> None:
    for spawn in spawns:
        area = spawn.polygon.intersection(walkable).area
        number = spawn.parameters.get("number", 0)
        if spawn.parameters.get("use_flow_spawning") or area <= 0:
            continue
        if number / area > PACKING_LIMIT_PER_M2:
            report.add(
                "A",
                "warning",
                "spawn",
                f"{number} agents on {area:.3f} m2 is "
                f"{number / area:.2f} /m2, above the packing limit of about "
                f"{PACKING_LIMIT_PER_M2:g} /m2",
                id=spawn.id,
            )


def _exit_report(exit_: ImportedExit) -> dict[str, Any]:
    return {
        "id": exit_.id,
        "source": exit_.source,
        "role": exit_.role,
        "segment": [rounded(v) for v in exit_.segment],
        "strip_area_m2": rounded(exit_.polygon.area),
        "sign": exit_.sign,
        "open_from_s": exit_.open_from_s,
        "closed_after_s": exit_.closed_after_s,
    }


def _spawn_report(spawn: ImportedSpawn, walkable) -> dict[str, Any]:
    area = spawn.polygon.intersection(walkable).area
    number = spawn.parameters.get("number", 0)
    return {
        "id": spawn.id,
        "source": spawn.source,
        "number": number,
        "area_m2": rounded(area),
        "density_per_m2": rounded(number / area) if area > 0 else None,
        "parameters_written": sorted(spawn.parameters),
        "placeholder": spawn.placeholder,
    }


def _recommend(deck, deck_path, report, walkable, exits, height) -> None:
    rec = report.recommendations
    rec["smoke_slice_height"] = rounded(height)
    rec["slices"] = _slice_availability(deck, height)
    rec["coverage"] = _coverage(deck, walkable, exits)
    smv = deck_path.parent / f"{deck.chid}.smv" if deck.chid else None
    found = smv is not None and smv.is_file()
    rec["fds_output_found"] = str(smv) if found else None
    use = found and report.kind == "modern"
    rec["fds_dir"] = str(deck_path.parent) if use else None
    if found and not use:
        rec["fds_dir_note"] = (
            "FDS+Evac output found but not used: reading it with "
            "fdsreader is not verified; add --fds-dir to try"
        )


def _slice_availability(deck: FdsDeck, height: float) -> dict[str, Any]:
    out = {}
    for quantity, spec in NEEDED_SLICES:
        heights = [
            z
            for s in deck.group("SLCF")
            if _slice_matches(s, quantity, spec) and (z := s.number("PBZ")) is not None
        ]
        nearest = min(heights, key=lambda z: abs(z - height)) if heights else None
        ok = nearest is not None and abs(nearest - height) <= _SLICE_HEIGHT_TOLERANCE_M
        out[quantity if spec is None else f"{quantity} {spec}"] = {
            "nearest_pbz": nearest,
            "ok": ok,
        }
    return out


def _slice_matches(record: NamelistRecord, quantity: str, spec: str | None) -> bool:
    if str(record.text("QUANTITY", "")).upper() != quantity:
        return False
    return spec is None or str(record.text("SPEC_ID", "")).upper() == spec


def _coverage(deck: FdsDeck, walkable, exits) -> dict[str, Any]:
    fire = [_mesh_box(m) for m in _meshes(deck, evacuation=False)]
    if not fire:
        return {"fire_meshes": 0}
    fire_union = union(fire)
    outside = walkable.difference(fire_union).area
    exits_out = sorted(
        e.id for e in exits if not e.polygon.within(fire_union.buffer(1e-9))
    )
    return {
        "fire_meshes": len(fire),
        "walkable_outside_m2": rounded(outside),
        "exits_outside": exits_out,
    }


def _runnable(report, exits, spawns) -> None:
    if not exits:
        report.not_runnable.append(
            "no exit found: add exits in JuPedSim Web or with --exit x0,y0,x1,y1[,ior]"
        )
    if not any(s.parameters.get("number", 0) > 0 for s in spawns):
        report.not_runnable.append("no agents to place")


def _raw(deck, report, exits, spawns, height) -> dict[str, Any]:
    time = deck.first("TIME")
    t_end = time.number("T_END") if time else None
    if t_end is None:
        report.add(
            "A",
            "info",
            "TIME",
            f"no T_END: max_simulation_time {DEFAULT_MAX_TIME_S:g} s",
            id="T_END",
        )
    params = {
        "max_simulation_time": t_end if t_end is not None else DEFAULT_MAX_TIME_S,
        "smoke_slice_height": rounded(height),
    }
    return {
        "config": {"simulation_settings": {"simulationParams": params}},
        "exits": {e.id: _exit_json(e) for e in exits},
        "distributions": {s.id: _spawn_json(s) for s in spawns},
        "journeys": [],
        "transitions": [],
    }


def _exit_json(exit_: ImportedExit) -> dict[str, Any]:
    out: dict[str, Any] = {
        "type": "polygon",
        "coordinates": ring_coordinates(exit_.polygon),
    }
    if exit_.sign is not None:
        out["sign"] = exit_.sign
    if exit_.open_from_s is not None:
        out["open_from_s"] = exit_.open_from_s
    if exit_.closed_after_s is not None:
        out["closed_after_s"] = exit_.closed_after_s
    return out


def _spawn_json(spawn: ImportedSpawn) -> dict[str, Any]:
    return {
        "type": "polygon",
        "coordinates": ring_coordinates(spawn.polygon),
        "parameters": spawn.parameters,
    }
