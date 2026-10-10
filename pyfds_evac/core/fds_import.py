"""Start a pyFDS-Evac scenario from an FDS deck.

:func:`import_fds_deck` reads one ``.fds`` file and returns the scenario
``config.json`` content, the walkable WKT and an :class:`ImportReport`; the
run model is untouched (``load_scenario`` reads the written directory as any
other scenario).

- *Legacy* decks (FDS+Evac: a ``&MESH`` with ``EVACUATION=.TRUE.``) map ``&EXIT``/``&DOOR`` to exits and ``&EVAC``/``&EVHO``/
  ``&ENTR``/``&PERS`` to spawn areas, on one floor.
- *Modern* decks get exits from ``SURF_ID='OPEN'`` vents on the exterior of
  the mesh union within the walking band, plus any ``--exit``; spawn areas
  fill each walkable component that has an exit, with a flagged placeholder
  of 100 agents unless ``agents`` is given. An ``&EVHO`` there is cut out
  of the derived walkable area; the other evacuation namelists are reported
  and ignored.

Everything stays in the FDS frame. The output is deterministic: sorted keys,
coordinates rounded to 1e-6 m, IDs from the deck or ``<group>_<n>``.

The model contract (mapping table, rules, maintainer decisions) is the
import task record; this module imports neither JuPedSim nor fdsreader.
"""

from __future__ import annotations

import itertools
import json
import math
import os
import shutil
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path
from typing import Any

from shapely import wkt as shapely_wkt
from shapely.geometry import LineString, Point, box

from .fds_deck import FdsDeck, NamelistRecord, parse_fds_deck
from .fds_import_geometry import (
    MIN_EXIT_WIDTH_M,
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
    ZERO_WIDTH,
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
from .fds_import_slices import SliceCheck, check_slices
from .walkable_provider import (
    FloorSpec,
    WalkableProvider,
    WalkableResult,
    deck_walkable,
    footprint,
)

__all__ = [
    "FdsImportError",
    "ImportResult",
    "check_fds_deck",
    "import_fds_deck",
    "parse_fds_deck",
]

#: FDS+Evac namelists; on a plain deck only ``&EVHO`` is applied.
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
    #: The spawn areas as built, kept in memory for the terminal summary.
    spawns: list[ImportedSpawn] = field(default_factory=list)

    def run_command(self, out_dir: str | Path) -> str:
        command = f"pyfds-evac --scenario {out_dir}"
        fds_dir = self.report.recommendations.get("fds_dir")
        return command + (f" --fds-dir {fds_dir}" if fds_dir else "")

    def write(self, out_dir: str | Path) -> Path:
        """Write ``config.json``, ``geometry.wkt`` and ``import_report.json``.

        The files are written into a temporary folder next to *out_dir* and
        then moved in, so a failed write leaves no partial file behind.
        """
        target = Path(out_dir)
        self.report.recommendations["run_command"] = self.run_command(out_dir)
        target.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=f".{target.name}.", dir=target.parent))
        try:
            self._write_files(staging)
            _move_into(staging, target)
        finally:
            shutil.rmtree(staging, ignore_errors=True)
        return target

    def _write_files(self, folder: Path) -> None:
        _dump(folder / "config.json", self.raw)
        (folder / "geometry.wkt").write_text(self.walkable_wkt + "\n", encoding="utf-8")
        _dump(folder / "import_report.json", self.report.to_dict())


_OUTPUT_FILES = ("config.json", "geometry.wkt", "import_report.json")


def check_output_folder(out_dir: str | Path, *, force: bool = False) -> None:
    """Refuse to overwrite a scenario the importer did not write.

    A folder with a ``config.json`` but no ``import_report.json`` holds an
    authored scenario (decks sit next to theirs in ``assets/``); importing
    over it would replace its journeys, routing and parameters. A folder
    the importer made may be re-imported. *force* skips the check.
    """
    target = Path(out_dir)
    if force or not (target / "config.json").exists():
        return
    if (target / "import_report.json").exists():
        return
    raise FdsImportError(
        f"{target} holds a config.json that the importer did not write "
        "(no import_report.json); importing would replace it. Choose another "
        "-o folder, or pass --force to overwrite it"
    )


def _move_into(staging: Path, target: Path) -> None:
    """Rename the staged folder to *target*, or each file into an existing one."""
    if not target.exists():
        staging.rename(target)
        return
    for name in _OUTPUT_FILES:
        os.replace(staging / name, target / name)


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
    on_slice_check: Callable[[SliceCheck], None] | None = None,
) -> ImportResult:
    """Import the FDS deck at *path*; see the module docstring.

    ``walkable_wkt`` (WKT text) skips derivation; otherwise
    ``derive_walkable`` (default: :func:`deck_walkable`) makes the polygon,
    and only its components holding a spawn area are kept (see
    :func:`_select_components`). ``exits`` are extra exit lines
    ``(x0, y0, x1, y1[, ior])``. Raises :class:`FdsImportError` (or the
    parser's/provider's ``ValueError``) when nothing can be written.

    The slice check (:func:`check_fds_deck`) runs once the floor is chosen,
    before the walkable step, at the height written to ``config.json``; its
    result goes to ``recommendations`` and to *on_slice_check*, so a caller
    has it even when a later step raises. It never changes what is written.
    """
    _check_options(exit_depth, agents)
    deck_path = Path(path)
    deck = parse_fds_deck(deck_path)
    opts = _Options(floor, floor_z, z_band, exit_depth, agents, exits)
    kind = _classify(deck)
    report = ImportReport(deck=deck_path.name, chid=deck.chid, kind=kind)
    _parser_items(deck, report)
    provider = derive_walkable or deck_walkable
    floors, chosen, height = _deck_floor(deck, kind, opts, report)
    check = check_slices(deck, rounded(height))
    report.recommendations["slices"] = check.to_dict()
    report.recommendations["slice_check_ok"] = check.ok
    if on_slice_check is not None:
        on_slice_check(check)
    build = _import_legacy if kind == "legacy" else _import_modern
    return build(deck, deck_path, opts, report, walkable_wkt, provider, floors, chosen)


def check_fds_deck(
    path: str | Path,
    *,
    floor: str | None = None,
    floor_z: float | None = None,
    z_band: tuple[float, float] | None = None,
    smoke_slice_height: float | None = None,
) -> SliceCheck:
    """Check the deck at *path* for the FDS output a run reads; write nothing.

    The floor is chosen as :func:`import_fds_deck` chooses it, and the
    height is the ``smoke_slice_height`` it would write unless
    *smoke_slice_height* (absolute z [m]) is given. Raises like
    :func:`import_fds_deck` when the deck or its floor cannot be read.
    """
    deck_path = Path(path)
    deck = parse_fds_deck(deck_path)
    opts = _Options(floor, floor_z, z_band, EXIT_DEPTH_M, None, ())
    kind = _classify(deck)
    scratch = ImportReport(deck=deck_path.name, chid=deck.chid, kind=kind)
    if smoke_slice_height is not None and not math.isfinite(smoke_slice_height):
        raise FdsImportError(
            f"smoke slice height must be a finite number of metres, "
            f"got {smoke_slice_height}"
        )
    _, _, height = _deck_floor(deck, kind, opts, scratch)
    if smoke_slice_height is not None:
        height = smoke_slice_height
    return check_slices(deck, rounded(height))


def _deck_floor(deck, kind: str, opts, report) -> tuple[list[Floor], Floor, float]:
    """The floors, the chosen one and the smoke slice height above it.

    Legacy: the evacuation floors (else the fire meshes' floor), picked
    with ``--floor``, at the last ``HUMAN_SMOKE_HEIGHT``. Modern: the
    floor at ``--floor-z`` or the lowest mesh, at 1.6 m.
    """
    if kind != "legacy":
        floor = _modern_floor(deck, opts, report)
        return [floor], floor, floor.z_floor + HUMAN_SMOKE_HEIGHT_M
    floors = _evac_floors(deck, report)
    if not floors:
        report.add(
            "A",
            "warning",
            "MESH",
            "evacuation namelists but no evacuation "
            "mesh: the floor is taken from the fire meshes",
        )
        floors = [_modern_floor(deck, opts, report)]
    floor = _choose_floor(floors, opts.floor)
    return floors, floor, floor.z_floor + _human_smoke_height(deck)


def _check_options(depth: float, agents: int | None) -> None:
    if not (math.isfinite(depth) and depth > 0):
        raise FdsImportError(
            f"exit depth must be a positive number of metres, got {depth}"
        )
    if agents is not None and agents < 0:
        raise FdsImportError(f"agents must be >= 0, got {agents}")


def _classify(deck: FdsDeck) -> str:
    evac_mesh = any(m.flag("EVACUATION", False) for m in deck.group("MESH"))
    return "legacy" if evac_mesh else "modern"


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


def _modern_floor(deck: FdsDeck, opts: _Options, report: ImportReport) -> Floor:
    """The floor of a deck without evacuation meshes.

    Only the meshes whose z range overlaps the walking band make up the
    floor; a mesh wholly above or below it (an upper storey) is left out
    and reported, so its footprint does not join the walkable area.
    """
    meshes = _meshes(deck, evacuation=False) or _meshes(deck, evacuation=True)
    if not meshes:
        raise FdsImportError("the deck has no &MESH with XB; nothing to import")
    z_floor = (
        opts.floor_z if opts.floor_z is not None else min(m.box6()[4] for m in meshes)
    )
    slab = (z_floor + MODERN_BAND_M[0], z_floor + MODERN_BAND_M[1])
    band = opts.z_band or slab
    on_floor = [m for m in meshes if _meets_band(m, band)]
    if not on_floor:
        raise FdsImportError(
            f"no &MESH reaches the walking band z = {band[0]:g}..{band[1]:g} m; "
            "pick the floor with --floor-z or the band with --z-band"
        )
    _meshes_off_floor(meshes, on_floor, band, report)
    return Floor(
        "lowest" if opts.floor_z is None else "floor_z",
        tuple(on_floor),
        z_floor,
        slab,
        _min_dx(on_floor),
    )


def _meets_band(mesh: NamelistRecord, band: tuple[float, float]) -> bool:
    z0, z1 = mesh.box6()[4:]
    return z0 < band[1] - 1e-9 and z1 > band[0] + 1e-9


def _meshes_off_floor(meshes, on_floor, band, report: ImportReport) -> None:
    for mesh in meshes:
        if mesh in on_floor:
            continue
        z0, z1 = mesh.box6()[4:]
        report.add(
            "A",
            "warning",
            "MESH",
            f"mesh at z = {z0:g}..{z1:g} m lies outside the walking band "
            f"z = {band[0]:g}..{band[1]:g} m: not part of the imported floor",
            mesh,
            id=mesh.id or f"MESH_{mesh.line}",
        )


def _floor_obstructions(
    deck: FdsDeck, floor: Floor, band, legacy: bool, group: str = "OBST"
):
    """*group* records of this floor: ``EVACUATION`` and ``MESH_ID`` honoured."""
    mesh_ids = {m.id for m in floor.meshes}
    out = []
    for record in deck.group(group):
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

#: Builds the exits and spawn areas of a floor on a walkable polygon.
StageBuilder = Callable[[Any, ImportReport], tuple[list, list]]


def _walkable_and_stages(
    deck, spec: FloorSpec, user_wkt, provider, report, build: StageBuilder
):
    """The walkable polygon with the exits and spawn areas built on it.

    A ``--walkable`` polygon is taken as given. A derived one keeps only the
    components that hold a spawn area (or, with none, an exit); the stages
    are then built again on the kept polygon, so strips and spawn pieces
    are clipped to it.
    """
    if user_wkt is not None:
        result = WalkableResult(_load_wkt(user_wkt), [], "user")
        walkable = _checked(result)
        _record_walkable(report, walkable, result)
        return (walkable, *build(walkable, report))
    result = provider(deck, spec)
    derived = _checked(result)
    if len(polygons_of(derived)) == 1:
        _record_walkable(report, derived, result, kept_by="single")
        return (derived, *build(derived, report))
    scratch = ImportReport(report.deck, report.chid, report.kind)
    exits, spawns = build(derived, scratch)
    kept, dropped, rule = _select_components(derived, exits, spawns)
    if not dropped:
        _record_walkable(report, derived, result, kept_by=rule)
        _note_all_kept(report, rule, len(kept))
        report.items.extend(scratch.items)
        return derived, exits, spawns
    walkable = union(kept)
    _record_walkable(report, walkable, result, kept_by=rule)
    _report_dropped(report, dropped, rule, exits)
    return (walkable, *build(walkable, report))


def _checked(result: WalkableResult):
    polygon = result.polygon
    if polygon is None or polygon.is_empty or not polygon.is_valid or polygon.area <= 0:
        raise FdsImportError(
            f"the walkable area ({result.source}) is empty or invalid; no scenario written"
        )
    if polygon.geom_type not in ("Polygon", "MultiPolygon"):
        raise FdsImportError(
            f"the walkable area is a {polygon.geom_type}, not a polygon"
        )
    return polygon


def _record_walkable(report, polygon, result: WalkableResult, kept_by=None) -> None:
    parts = polygons_of(polygon)
    report.walkable = {
        "source": result.source,
        "area_m2": rounded(polygon.area),
        "components": len(parts),
        "holes": sum(len(p.interiors) for p in parts),
        "diagnostics": list(result.diagnostics),
    }
    if kept_by is not None:
        report.walkable["kept_by"] = kept_by
        report.walkable["components_dropped"] = []


def _select_components(walkable, exits, spawns) -> tuple[list, list, str]:
    """Components holding a spawn area; without any, those holding an exit.

    Exits given with ``--exit`` always keep their component. With neither a
    spawn area nor an exit, every component is kept (rule ``"all"``).
    """
    parts = polygons_of(walkable)
    user = [e.polygon for e in exits if e.source == "X3"]
    anchors, rule = [s.polygon for s in spawns], "spawn"
    if not anchors:
        anchors, rule = [e.polygon for e in exits], "exit"
    if not anchors:
        return parts, [], "all"
    anchors += user
    kept = [p for p in parts if any(_overlaps(p, a) for a in anchors)]
    if not kept:
        return parts, [], "all"
    return kept, [p for p in parts if not any(p is k for k in kept)], rule


def _overlaps(component, shape) -> bool:
    return bool(component.intersection(shape).area > 1e-9)


def _note_all_kept(report, rule: str, count: int) -> None:
    if rule != "all":
        return
    report.add(
        "A",
        "info",
        "walkable",
        f"no spawn area and no exit to choose the walkable components by: "
        f"all {count} kept",
        id="components",
    )


def _report_dropped(report, dropped, rule: str, exits) -> None:
    what = "spawn area" if rule == "spawn" else "spawn area or exit"
    for index, part in enumerate(dropped, 1):
        inside = sorted(e.id for e in exits if _overlaps(part, e.polygon))
        x0, y0, x1, y1 = part.bounds
        report.walkable["components_dropped"].append(
            {
                "area_m2": rounded(part.area),
                "bounds": [rounded(v) for v in (x0, y0, x1, y1)],
                "reason": f"no {what} in it",
                "exits": inside,
            }
        )
        also = f"; its exits are dropped with it: {', '.join(inside)}" if inside else ""
        report.add(
            "A",
            "warning",
            "walkable",
            f"walkable component of {part.area:.3f} m2 at x {x0:g}..{x1:g}, "
            f"y {y0:g}..{y1:g} dropped: no {what} in it{also}",
            id=f"component_{index}",
        )


def _load_wkt(text: str):
    try:
        return shapely_wkt.loads(text)
    except Exception as exc:  # shapely raises its own GEOSException types
        raise FdsImportError(f"cannot read the walkable WKT: {exc}") from exc


# --- legacy ------------------------------------------------------------------


def _import_legacy(
    deck, deck_path, opts, report, user_wkt, provider, floors, floor
) -> ImportResult:
    if opts.agents is not None:
        report.add(
            "D",
            "warning",
            "--agents",
            "ignored for an FDS+Evac deck: the &EVAC records set the numbers",
            id="agents",
        )
    band = opts.z_band or floor.slab
    domain = union([_mesh_box(m) for m in floor.meshes])
    _touching_meshes(floor, report)
    spec = FloorSpec(
        floor.z_floor,
        band,
        domain,
        tuple(m.id or "" for m in floor.meshes),
        _floor_obstructions(deck, floor, band, legacy=True),
        _floor_obstructions(deck, floor, band, legacy=True, group="HOLE"),
    )
    tol = max(floor.dx or 0.0, 0.05)
    build = partial(_legacy_stages, deck, floor, floors, opts, tol)
    walkable, exits, spawns = _walkable_and_stages(
        deck, spec, user_wkt, provider, report, build
    )
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


def _touching_meshes(floor: Floor, report: ImportReport) -> None:
    """Warn when two evacuation meshes of the floor touch or overlap.

    FDS+Evac keeps each main evacuation mesh sealed (agents cross only
    through a ``&DOOR``); the walkable area is the union of the footprints,
    so their shared edge is open here.
    """
    pairs = itertools.combinations(floor.meshes, 2)
    for first, second in pairs:
        if not _mesh_box(first).intersects(_mesh_box(second)):
            continue
        report.add(
            "A",
            "warning",
            "MESH",
            f"evacuation meshes {first.label} and {second.label} touch: "
            "the walkable area joins them, so their shared edge is open; "
            "FDS+Evac keeps it a wall",
            first,
        )


def _legacy_stages(deck, floor, floors, opts, tol, walkable, report):
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
    return exits, spawns


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


def _import_modern(
    deck, deck_path, opts, report, user_wkt, provider, floors, floor
) -> ImportResult:
    band = opts.z_band or floor.slab
    domain = union([_mesh_box(m) for m in floor.meshes])
    spec = FloorSpec(
        floor.z_floor,
        band,
        domain,
        None,
        _floor_obstructions(deck, floor, band, legacy=False),
        _floor_obstructions(deck, floor, band, legacy=False, group="HOLE"),
    )
    tol = max(floor.dx or 0.0, 0.05)
    evhos = _plain_evhos(deck, floor, band, user_wkt is not None, report)
    build = partial(_modern_stages, deck, floor, band, domain, opts)
    walkable, exits, spawns = _walkable_and_stages(
        deck, spec, user_wkt, _minus_evhos(provider, evhos, report), report, build
    )
    _upper_floor_warnings(deck, floor, domain, report)
    _plain_evac_records(deck, report)
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


def _plain_evhos(deck, floor, band, user_walkable: bool, report) -> list:
    """``&EVHO`` records to cut out of a plain deck's derived walkable area.

    One applies when its z range meets the floor up to the band top and
    its ``MESH_ID``, if given, names a mesh of the floor; with
    ``--walkable`` the polygon is taken as given and none applies. The
    skipped ones are reported here, the applied ones by :func:`_minus_evhos`.
    """
    mesh_ids = {m.id for m in floor.meshes}
    applied = []
    for record in deck.group("EVHO"):
        reason = _evho_skipped(record, floor.z_floor, band[1], mesh_ids)
        if reason is None and user_walkable:
            reason = "the --walkable polygon is taken as given"
        if reason is not None:
            report.add("D", "warning", "EVHO", f"ignored: {reason}", record)
            continue
        applied.append(record)
    return applied


def _evho_skipped(record, z_floor: float, z_top: float, mesh_ids) -> str | None:
    xb = record.xb()
    if xb is None:
        return "invalid, XB is missing"
    mesh_id = record.text("MESH_ID")
    if mesh_id is not None and mesh_id not in mesh_ids:
        return f"MESH_ID {mesh_id!r} is not a mesh of the imported floor"
    if xb[5] < z_floor - 1e-9 or xb[4] > z_top:
        return "not on the imported floor"
    return None


def _minus_evhos(
    provider: WalkableProvider, evhos: list, report: ImportReport
) -> WalkableProvider:
    """*provider* with the footprints of *evhos* cut out of its polygon.

    An ``&EVHO`` that does not overlap the polygon is reported as ignored;
    holes that leave nothing raise :class:`FdsImportError` naming them.
    """
    if not evhos:
        return provider

    def derive(deck: FdsDeck, spec: FloorSpec) -> WalkableResult:
        result = provider(deck, spec)
        if result.polygon is None:
            return result
        holes = [r for r in evhos if _evho_cuts(r, result.polygon, report)]
        if not holes:
            return result
        note = f"{len(holes)} &EVHO cut out"
        polygon = result.polygon.difference(union([footprint(r) for r in holes]))
        if polygon.is_empty or polygon.area <= 0:
            names = ", ".join(f"&EVHO {r.label} (line {r.line})" for r in holes)
            verb = "is" if len(holes) == 1 else "are"
            raise FdsImportError(
                f"the walkable area ({result.source}) is empty once {names} "
                f"{verb} cut out; no scenario written"
            )
        return WalkableResult(polygon, [*result.diagnostics, note], result.source)

    return derive


def _evho_cuts(record: NamelistRecord, polygon, report: ImportReport) -> bool:
    if footprint(record).intersection(polygon).area <= 0:
        report.add(
            "D",
            "warning",
            "EVHO",
            "ignored: outside the walkable area",
            record,
        )
        return False
    report.add("A", "info", "EVHO", "cut out of the walkable area (plain deck)", record)
    return True


def _plain_evac_records(deck: FdsDeck, report: ImportReport) -> None:
    """FDS+Evac namelists other than ``&EVHO`` on a plain deck: ignored."""
    for record in deck.records:
        if record.group not in EVAC_GROUPS or record.group == "EVHO":
            continue
        report.add(
            "D",
            "warning",
            record.group,
            "ignored: the deck has no EVACUATION=.TRUE. mesh, "
            "so it is not an FDS+Evac deck",
            record,
        )


def _modern_stages(deck, floor, band, domain, opts, walkable, report):
    exits = _vent_exits(deck, floor, band, domain, walkable, opts.depth, report)
    exits = _unique(exits + _user_exits(opts, walkable, report), "EXIT")
    spawns = _modern_spawns(walkable, exits, opts.agents, report)
    return exits, spawns


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
    _fire_surfaces(deck, (floor.z_floor, band[1]), walkable, report)
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
    _check_capacity(report, walkable, spawns)
    raw = _raw(deck, report, exits, spawns, height)
    text = shapely_wkt.dumps(walkable, rounding_precision=6, trim=True)
    return ImportResult(raw, text, report, deck_path, spawns)


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


def _fire_surfaces(deck: FdsDeck, z_range, walkable, report) -> None:
    """Burning surfaces between the floor and the band top, in walkable space.

    Reported, not excluded: FDS+Evac does not exclude them either. The
    advice names a way the deck kind supports; ``&EVHO`` only where it
    applies, not under ``--walkable``.
    """
    if report.kind == "legacy":
        advice = ", as in FDS+Evac; exclude it with &EVHO or the spawn polygon"
    else:
        advice = (
            "; rerun init with --walkable FILE.wkt, a walkable area without it "
            "(agents then neither spawn nor walk on it), or, to keep it walkable, "
            "cut a notch around it from the edge of the spawn polygon in "
            "distributions.<id>.coordinates of config.json"
        )
        if report.walkable.get("source") != "user":
            advice += (
                ". An &EVHO over the surface, in a copy of the deck, also cuts "
                "it out of the walkable area"
            )
    burning = {s.id for s in deck.group("SURF") if _burns(s)}
    for record in deck.group("VENT") + deck.group("OBST"):
        if not _burning_surface(record, burning):
            continue
        x0, x1, y0, y1, z0, z1 = record.box6()
        overlap = box(x0, y0, x1, y1).intersection(walkable).area
        if overlap <= 0 or z1 < z_range[0] - 1e-9 or z0 > z_range[1]:
            continue
        report.add(
            "A",
            "info",
            record.group,
            f"fire surface over {overlap:.3f} m2 "
            f"of the walkable area: agents may spawn on it{advice}",
            record,
        )


def _burns(surf: NamelistRecord) -> bool:
    return (surf.number("HRRPUA") or 0.0) > 0 or surf.has("MLRPUA")


def _burning_surface(record: NamelistRecord, burning: set) -> bool:
    if record.xb() is None:
        return False
    surfs = [
        str(v) for k in ("SURF_ID", "SURF_IDS", "SURF_ID6") for v in record.values(k)
    ]
    return any(s in burning for s in surfs)


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
        "fds_evac_segment": exit_.fds_evac_segment,
    }


def _spawn_report(spawn: ImportedSpawn, walkable) -> dict[str, Any]:
    area = spawn.polygon.intersection(walkable).area
    number = spawn.parameters.get("number", 0)
    out = {
        "id": spawn.id,
        "source": spawn.source,
        "number": number,
        "area_m2": rounded(area),
        "density_per_m2": rounded(number / area) if area > 0 else None,
        "parameters_written": sorted(spawn.parameters),
        "loader_defaults": _loader_defaults(spawn.parameters),
        "placeholder": spawn.placeholder,
    }
    if spawn.expansion is not None:
        out["zero_width_expansion"] = spawn.expansion
    return out


#: What the loader applies to a spawn area that leaves a key out
#: (docs/scenario-json.md); listed so a reader sees every inferred value.
LOADER_DEFAULTS = {
    "v0": "1.25 m/s, constant",
    "radius": "0.2 m",
    "premovement": "constant 10 s (FDS+Evac PRE_MEAN), with a warning",
    "familiarity": "full",
}


def _loader_defaults(params: dict[str, Any]) -> dict[str, str]:
    written = {
        "v0": "v0" in params,
        "radius": "radius" in params,
        "premovement": "use_premovement" in params
        or bool(params.get("use_flow_spawning")),
        "familiarity": "familiarity" in params,
    }
    return {key: text for key, text in LOADER_DEFAULTS.items() if not written[key]}


def _recommend(deck, deck_path, report, walkable, exits, height) -> None:
    rec = report.recommendations
    rec["smoke_slice_height"] = rounded(height)
    rec["coverage"] = _coverage(deck, walkable, exits)
    rec["fds_meshes"] = len(_meshes(deck, evacuation=False))
    smv = deck_path.parent / f"{deck.chid}.smv" if deck.chid else None
    found = smv is not None and smv.is_file()
    rec["fds_output_found"] = str(smv) if found else None
    use = found and report.kind == "modern"
    rec["fds_dir"] = str(deck_path.parent) if use else None
    if found and not use:
        rec["fds_dir_note"] = (
            "it is FDS+Evac output, and pyFDS-Evac reads only the output of "
            "a fire-only run; fdsreader is not verified on FDS+Evac output"
        )


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
            "no exit found"
            + _flow_field_note(report)
            + ": add exits in JuPedSim Web or with --exit x0,y0,x1,y1[,ior]"
        )
    if not any(s.parameters.get("number", 0) > 0 for s in spawns):
        report.not_runnable.append("no agents to place" + _zero_width_note(report))


def _flow_field_note(report) -> str:
    """Name decks whose every dropped exit is narrower than the minimum."""
    drops = [
        i.message
        for i in report.items
        if i.group in ("EXIT", "DOOR") and i.message.startswith("exit dropped")
    ]
    if not drops or not all("below the minimum exit width" in m for m in drops):
        return ""
    return (
        f" (every &EXIT is narrower than the minimum exit width "
        f"{MIN_EXIT_WIDTH_M:g} m: the deck uses its exits only as flow-field "
        "targets, which pyFDS-Evac does not model)"
    )


def _zero_width_note(report) -> str:
    count = sum(
        i.group == "EVAC" and i.level == "error" and i.message.startswith(ZERO_WIDTH)
        for i in report.items
    )
    if not count:
        return ""
    return (
        f": {count} &EVAC record(s) have a {ZERO_WIDTH} (a point or a line), "
        "with no area to place agents in"
    )


#: Loader default agent radius [m] (docs/scenario-json.md).
DEFAULT_RADIUS_M = 0.2


def spawn_capacity(area: float, max_radius: float) -> int:
    """Agents the runtime admits in a spawn area of *area* m2.

    The same packing estimate as ``simulation_init._estimate_max_capacity``
    (half the area over a disc of *max_radius*, at least 0.1 m); the
    runtime refuses to start when a spawn area asks for more. Kept here so
    the importer does not import JuPedSim; a test pins the two together.
    It is high in thin or small areas and low in large ones; see there.
    """
    radius = max(max_radius, 0.1)
    return max(1, math.floor(area / (math.pi * radius * radius) * 0.5))


def _max_radius(params: dict[str, Any]) -> float:
    """As ``simulation_init._get_max_agent_radius``."""
    radius = float(params.get("radius", DEFAULT_RADIUS_M))
    if params.get("radius_distribution") == "gaussian" and params.get("radius_std"):
        return min(radius + 3 * float(params["radius_std"]), 1.0)
    return radius


def _check_capacity(report, walkable, spawns) -> None:
    """Not runnable when a spawn area asks for more agents than the run admits.

    Like the runtime, areas are clipped to the walkable polygon and the
    groups that share one polygon are counted together; flow spawning is
    left out. The deck is not changed.
    """
    groups: dict[str, list[ImportedSpawn]] = {}
    for spawn in spawns:
        if spawn.parameters.get("use_flow_spawning"):
            continue
        area = spawn.polygon.intersection(walkable)
        groups.setdefault(area.wkt, []).append(spawn)
    for members in groups.values():
        area = members[0].polygon.intersection(walkable).area
        total = sum(int(m.parameters.get("number", 0)) for m in members)
        radius = max(_max_radius(m.parameters) for m in members)
        capacity = spawn_capacity(area, radius)
        if total <= capacity:
            continue
        hint = (
            "lower NUMBER_INITIAL_PERSONS or enlarge the &EVAC area"
            if report.kind == "legacy"
            else "pass --agents N with a smaller N, or enlarge the walkable area"
        )
        names = ", ".join(m.id for m in members)
        report.not_runnable.append(
            f"spawn area {names} ({area:.3f} m2) holds about {capacity} agents "
            f"of radius {radius:g} m, but {total} are requested: {hint}"
        )


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
