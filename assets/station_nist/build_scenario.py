#!/usr/bin/env python3
"""Build the Fahy Table 2 scenario on the NIST-derived Station geometry.

    .venv/bin/python assets/station_nist/build_scenario.py          # write
    .venv/bin/python assets/station_nist/build_scenario.py --tables # print

Station-derived geometry (provenance unverified, #377).

The walkable area is extracted from the NIST deck by
``assets/station/extract_walkable.py``, as ``assets/station/geometry.wkt`` is but
without the baseboards and toe kicks. The areas, the Fahy table, the
familiarity classes and every agent parameter are *imported* from
``assets/station_fahy`` -- nothing is copied -- so the two decks differ only in
the geometry, the exits and the checkpoints.

What this script adds to the extraction, each recorded in the README:

* the extraction itself leaves out baseboards and toe kicks (``IGNORED_LAYERS``);
* a translation hand frame -> NIST frame (:data:`TRANSLATION`);
* the gap table: every opening under 0.9 m is classified (deck door, trim-framed
  doorway, fixture clearance or slit); doors and fixtures that are the only
  access are set to the 0.9 m clearance floor, the rest is sealed
  (:func:`classify_gaps`, :func:`apply_gap_table`);
* the areas, clipped to the walkable area in ``PRIORITY`` order, without the
  bar service wells;
* exits just inside each deck door, and checkpoints at the doorways.

``simplify_doors.py`` is deliberately not run on this geometry: it would widen
the fixture passages that are only closed here, and cut the front door to its
own rule. Its gap finder is reused.
"""

from __future__ import annotations

import importlib.util
import json
import math
import sys
from pathlib import Path

import shapely
from shapely import affinity
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union

HERE = Path(__file__).parent
ASSETS = HERE.parent
NIST = ASSETS / "station"
FAHY = ASSETS / "station_fahy"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# Fahy's builder puts its own directory on sys.path, which makes ``areas``,
# ``fahy_table2`` and ``simplify_doors`` importable below.
FB = _load("station_fahy_build", FAHY / "build_scenario.py")
import areas  # noqa: E402
import fahy_table2 as F  # noqa: E402
import simplify_doors as SD  # noqa: E402

EX = _load("station_extract_walkable", NIST / "extract_walkable.py")

# Hand frame -> NIST frame, translation only. Chamfer fit of the hand building
# interior to the NIST walkable boundary: median residual 0.07 m, p90 0.40 m.
# A similarity fit (rotation -0.21 deg, scale 0.992) is a reported sensitivity.
TRANSLATION = (3.635, -8.366)

# Baseboards (A-WDWK-BAY, z <= 0.111 m, some at z 0.15-0.26 m) and toe kicks
# (A-CASE-TOEA, z <= 0.10 m) are 0.1 m proud of a wall or counter. They are
# left out of the extraction: they narrowed doorways and casework gaps that a
# person walks through (README, "Gap table").
IGNORED_LAYERS = ("A-WDWK-BAY", "A-CASE-TOEA")
# Every opening agents use is at least this wide (README, "Clearance floor").
# WarpDriver (JuPedSim 1.4.2) does not pass agents of radius up to 0.23 m
# through narrower openings (jupedsim#1719).
CLEAR_FLOOR = 0.90
CLEAR_CHECK = CLEAR_FLOOR - 0.001  # the gap finder samples the boundary at 7 cm
SLIT = 0.20  # m, a chord below this is a tracing slit, never a door
# A non-door narrower than the largest agent (radius cap 0.23 m) is not a
# passage for this population: the navigation mesh routes through it and the
# agents jam, so it is sealed (README, "Gap table").
IMPASSABLE_BELOW = 0.46
DOOR_LEAF_REACH = 0.5  # m, a deck door leaf this close makes the gap a door
TRIM_REACH = 0.03  # m, a chord end this close to door trim is on a jamb
THIN_FEATURE = 0.09  # m, CAD debris: obstacle teeth and floor slivers below this
MAX_ROUNDS = 8
USED_FLOOR_MIN = 0.314  # m2, one agent's floor (2.5 pi r^2 at r = 0.20 m)
FRONT_INTERIOR_DOOR = (3.44, -14.38)
FRONT_INTERIOR_CLEAR = 0.91  # m, NCSTAR 914 mm; leaves at x 2.97 and 3.88
FRONT_DOOR_LINE_Y = -14.36
# Bar service wells hold no agents. The main-bar well is cut off by its sealed
# slits; the rear-bar well behind the L-shaped counter is named here.
SERVICE_WELLS = (box(1.75, -4.0, 4.85, -1.5),)
# Floor in use that the build cuts off on purpose: a point inside it, the largest
# area it may have (m2) and why. Any other cut-off floor in use, or a larger part
# around one of these points, stops the build (:func:`_check_cut_off`).
CUT_OFF = {
    (-1.84, -11.54): (
        12.0,
        "main-bar service well, behind the 0.39 m gap at (0.68, -10.37)",
    ),
    (2.83, -11.98): (0.6, "0.5 m2 niche behind the 0.30 m gap at (3.39, -11.74)"),
}
# Extracted floor with no opening to the main floor that overlaps floor in use:
# a point inside it, its largest area (m2) and what it is. Any other such floor
# stops the build (:func:`_check_isolated`).
ISOLATED = {
    (-12.38, -1.41): (3.1, "closed room west of the dart room"),
    (-6.07, -15.32): (0.4, "enclosed 0.36 m2 pocket in the main-bar rectangle"),
}

# The same rectangles as the hand deck, Rear bar / dart room included (#380).
RECTS = areas.RECTS

# The deck's exterior doors, which the extraction keeps shut: (exit id, x or y
# of the door line, span along it, which wall). Each exit is a strip just inside.
EXIT_DEPTH = 0.4
EXIT_DOORS = {
    # FRONT DOOR, x 2.44-4.34 at the vestibule's outer end (y -17.11 inside)
    "jps-exits_0": ("y", -17.11, (2.44, 4.34), +1),
    # Main bar side exit door, x -5.97 inside, y -13.51..-12.51
    "jps-exits_1": ("x", -5.97, (-13.51, -12.51), +1),
    # Kitchen exit door, x -5.97 inside, y -8.61..-7.61
    "jps-exits_2": ("x", -5.97, (-8.61, -7.61), +1),
    # Platform exit door, x 17.66 (jamb markers at y -11.39 and -12.38)
    "jps-exits_3": ("x", 17.66, (-12.38, -11.39), -1),
}

# Checkpoints keep Fahy's roles. The three that stand at a door are placed on
# the NIST doorway; the rest follow the translation. (x, y, radius)
CHECKPOINT_AT = {
    "jps-checkpoints_3": (3.39, -16.60, 0.35),  # outer end of the vestibule
    "jps-checkpoints_4": (-5.50, -13.01, 0.35),  # main bar side door
    "jps-checkpoints_5": (-5.50, -8.11, 0.35),  # kitchen side door
    "jps-checkpoints_6": (3.38, -14.97, 0.35),  # vestibule, south of the door
}


def translate(geom):
    return affinity.translate(geom, *TRANSLATION)


def largest(geom):
    parts = [p for p in getattr(geom, "geoms", [geom]) if p.geom_type == "Polygon"]
    return max(parts, key=lambda p: p.area) if parts else None


# ---- the gap table --------------------------------------------------------


class _Floor:
    """A walkable polygon that buffers itself once.

    ``simplify_doors.find_passages`` buffers the polygon by 1e-9 m for every
    candidate pair, which takes minutes on a regularised floor. The proxy hands
    back one buffered copy.
    """

    def __init__(self, polygon: Polygon):
        self.exterior = polygon.exterior
        self.interiors = polygon.interiors
        self._buffered = polygon.buffer(1e-9)

    def buffer(self, distance: float):
        return self._buffered


def find_passages(walkable: Polygon, max_width: float) -> list[tuple]:
    """``simplify_doors.find_passages`` on a floor buffered once."""
    return SD.find_passages(_Floor(walkable), max_width)


def extracted_floor() -> Polygon:
    """The NIST extraction without baseboards and toe kicks (:data:`IGNORED_LAYERS`)."""
    walkable, *_ = EX.extract(
        NIST / "Station210_clean.fds", 0.1, 1.8, 0.05, 0.25, IGNORED_LAYERS
    )
    return walkable


def _door_leaves() -> list[tuple[str, float, float]]:
    _, obstructions = EX.parse_deck(NIST / "Station210_clean.fds")
    return [
        (name, (x0 + x1) / 2, (y0 + y1) / 2)
        for name, x0, x1, y0, y1, z0, z1 in obstructions
        if z1 >= 0.1 and z0 <= 1.8 and EX.is_door(name)
    ]


def _trim_footprint():
    """The door and window trim (``A-WDWK-TRIM``) as one footprint."""
    _, obstructions = EX.parse_deck(NIST / "Station210_clean.fds")
    return unary_union(
        [
            EX.footprint(x0, x1, y0, y1, 0.05)
            for name, x0, x1, y0, y1, z0, z1 in obstructions
            if name.startswith("A-WDWK-TRIM") and z1 >= 0.1 and z0 <= 1.8
        ]
    )


def classify_gaps(walkable: Polygon) -> list[dict]:
    """Every opening narrower than :data:`CLEAR_CHECK`, classified once.

    ``door``     a deck door leaf within 0.5 m, or trim (``A-WDWK-TRIM``) on both
                 jambs: set to :data:`CLEAR_FLOOR` (NCSTAR door widths are
                 0.81-0.91 m); the front interior door is 0.91 m (NCSTAR 914 mm);
    ``sealed``   narrower than the cap diameter and not a door: closed;
    ``fixture``  furniture or casework clearance, 0.46 m or wider. Whether it is
                 sealed or widened depends on the floor around it and is decided
                 by :func:`apply_gap_table`. A chord under 0.2 m is never a door.
    """
    leaves = _door_leaves()
    trim = _trim_footprint()
    rows = []
    for width, a, b, mid in sorted(
        find_passages(walkable, CLEAR_CHECK), key=lambda p: (p[3].x, p[3].y)
    ):
        if _is_front_door(mid) and front_door_width(walkable) >= CLEAR_FLOOR:
            continue
        distance, name = min(
            (math.hypot(mid.x - x, mid.y - y), n) for n, x, y in leaves
        )
        basis = ""
        if distance <= DOOR_LEAF_REACH:
            basis = "leaf"
        elif a.distance(trim) <= TRIM_REACH and b.distance(trim) <= TRIM_REACH:
            basis = "trim"
        if width < SLIT:
            cls, final, basis = "sealed", 0.0, "slit"
        elif basis:
            cls, final = "door", _door_clear_width(mid)
        elif width < IMPASSABLE_BELOW:
            cls, final, basis = "sealed", 0.0, "slit"
        else:
            cls, final = "fixture", 0.0
        rows.append(
            {
                "x": round(mid.x, 2),
                "y": round(mid.y, 2),
                "extracted": round(width, 2),
                "class": cls,
                "basis": basis,
                "final": final,
                "leaf": name if basis == "leaf" else "",
                "a": a,
                "b": b,
            }
        )
    return rows


def _is_front_door(mid: Point) -> bool:
    x, y = FRONT_INTERIOR_DOOR
    return math.hypot(mid.x - x, mid.y - y) < 0.5


def front_door_width(walkable: Polygon) -> float:
    """The front interior door measured along its line, y -14.36, between the leaves.

    The gap finder samples the boundary and can read this door a few
    millimetres short; the cut along the door line is the width that counts.
    """
    cut = LineString([(2.0, FRONT_DOOR_LINE_Y), (5.0, FRONT_DOOR_LINE_Y)])
    runs = walkable.intersection(cut)
    inside = [r for r in getattr(runs, "geoms", [runs]) if 2.5 < r.centroid.x < 4.3]
    return inside[0].length if len(inside) == 1 else 0.0


def _door_clear_width(mid: Point) -> float:
    return FRONT_INTERIOR_CLEAR if _is_front_door(mid) else CLEAR_FLOOR


def _front_door_row() -> dict:
    """The front interior door between its leaves, x 2.97 and 3.88."""
    a, b = Point(2.97, FRONT_DOOR_LINE_Y), Point(3.88, FRONT_DOOR_LINE_Y)
    return {
        "pass": 0,
        "x": round((a.x + b.x) / 2, 2),
        "y": FRONT_DOOR_LINE_Y,
        "extracted": round(front_door_width(extracted_floor()), 2),
        "class": "door",
        "basis": "leaf",
        "final": FRONT_INTERIOR_CLEAR,
        "leaf": "A-DOOR-STND-1",
        "a": a,
        "b": b,
    }


def apply_gap_table(walkable: Polygon, rows: list[dict], reach: float = 0.25):
    """Widen the doors, seal the slits, and settle each fixture clearance.

    A fixture clearance under :data:`CLEAR_FLOOR` is sealed unless that cuts off
    floor an agent uses (:func:`_used_floor`); then it is the only access, so it
    is widened to :data:`CLEAR_FLOOR` and counts as a door. *reach* is the depth
    of the cut across a wall; :func:`final_walkable` raises it when a door
    stays narrow.
    """
    for row in rows:
        if row["class"] == "door":
            walkable = _set_door_width(walkable, row, reach)
    before = walkable
    for row in rows:
        if row["class"] == "sealed":
            walkable = _seal(walkable, Point(row["x"], row["y"]))
    walkable = largest(walkable)  # sealing leaves the cut-off floor as other parts
    _check_cut_off(before, walkable)
    for row in rows:
        if row["class"] == "fixture":
            walkable = _settle_fixture(walkable, row, reach)
    return walkable


def _unrecorded(parts, recorded: dict) -> list[tuple]:
    """Parts overlapping floor in use that no *recorded* entry covers.

    A part counts when it overlaps more than one agent's floor; smaller parts
    count together once their sum does, so many small losses cannot pass.
    """
    used = _used_floor()
    found, small = [], 0.0
    for part in parts:
        overlap = part.intersection(used).area
        if overlap <= USED_FLOOR_MIN:
            small += overlap
            continue
        if any(
            part.area <= most and part.buffer(1e-6).contains(Point(p))
            for p, (most, _) in recorded.items()
        ):
            continue
        c = part.representative_point()
        found.append((round(c.x, 2), round(c.y, 2), round(part.area, 2)))
    if small > USED_FLOOR_MIN:
        found.append(("small parts", round(small, 2)))
    return found


def _check_cut_off(before: Polygon, kept: Polygon) -> None:
    """Stop if a step cut off more than one agent's floor in use, unless recorded.

    Regularising and sealing a slit keep the largest part without the
    only-access check of a fixture clearance, so floor an area relies on could
    otherwise vanish with the smaller parts.
    """
    lost = before.difference(kept)
    unrecorded = _unrecorded(getattr(lost, "geoms", [lost]), CUT_OFF)
    if unrecorded:
        raise SystemExit(
            f"sealing cuts off floor in use at {unrecorded}: make the gap a door "
            "or record the floor in CUT_OFF"
        )


def _settle_fixture(walkable: Polygon, row: dict, reach: float) -> Polygon:
    closed = _close(walkable, row)
    cut = walkable.difference(closed).difference(_patch_of(row))
    if cut.intersection(_used_floor()).area <= USED_FLOOR_MIN:
        row["class"], row["basis"], row["final"] = "sealed", "fixture", 0.0
        return closed
    row["class"], row["basis"], row["final"] = "fixture", "only access", CLEAR_FLOOR
    return _set_door_width(walkable, row, reach)


def _patch_of(row: dict) -> Polygon:
    a, b = row["a"], row["b"]
    mid = Point((a.x + b.x) / 2, (a.y + b.y) / 2)
    return SD._patch(mid, a, b, a.distance(b) + 0.20, 0.30)


def _close(walkable: Polygon, row: dict) -> Polygon:
    """Wall in the opening across its chord, keeping the larger floor."""
    return largest(walkable.difference(_patch_of(row)))


def _used_floor():
    """Floor an agent stands on or walks to: areas, exit strips, checkpoints.

    The service wells (:data:`SERVICE_WELLS`) hold no agents and are not used.
    """
    base = json.loads((FAHY / "source" / "config.json").read_text())
    parts = [translate(box(*r)) for r in RECTS.values()]
    parts = [unary_union(parts).difference(unary_union(SERVICE_WELLS))]
    for axis, line, (lo, hi), side in EXIT_DOORS.values():
        a, b = sorted((line, line + side * EXIT_DEPTH))
        parts.append(box(lo, a, hi, b) if axis == "y" else box(a, lo, b, hi))
    for cp_id, cp in base["checkpoints"].items():
        x, y, radius = _checkpoint_at(cp_id, cp)
        parts.append(Point(x, y).buffer(radius))
    return unary_union(parts)


def _set_door_width(walkable: Polygon, row: dict, reach: float = 0.25) -> Polygon:
    """Cut the opening to the clear width, or wall it in down to that width."""
    a, b = row["a"], row["b"]
    mx, my = (a.x + b.x) / 2, (a.y + b.y) / 2
    # Axis aligned: the sampled chord ends are not exactly opposite, and a
    # tilted patch leaves slivers along the jambs.
    along_x = abs(b.x - a.x) >= abs(b.y - a.y)
    half = row["final"] / 2
    if not along_x:
        flipped = affinity.affine_transform(walkable, [0, -1, 1, 0, 0, 0])
        fixed = _set_door_width_x(flipped, (-my, mx), half, reach)
        return affinity.affine_transform(fixed, [0, 1, -1, 0, 0, 0])
    return _set_door_width_x(walkable, (mx, my), half, reach)


def _set_door_width_x(
    walkable: Polygon, mid: tuple[float, float], half: float, reach: float
):
    mx, my = mid
    walkable = walkable.union(box(mx - half, my - reach, mx + half, my + reach))
    for side in (-1, 1):
        plane = mx + side * half
        for jamb in (0.14, 0.11, 0.08, 0.05, 0.02):
            run = _wall_run(walkable, plane + side * jamb, my)
            if run is None:
                continue
            x0, x1 = sorted((plane, plane + side * jamb))
            walkable = walkable.difference(box(x0, run[0], x1, run[1]))
            break
    return walkable


def _wall_run(walkable, x: float, y: float) -> tuple[float, float] | None:
    """The stretch of wall through (*x*, *y*) along y, or None in open floor."""
    probe = LineString([(x, y - 1.0), (x, y + 1.0)])
    wall = probe.difference(walkable)
    for run in getattr(wall, "geoms", [wall]):
        lo, hi = run.bounds[1], run.bounds[3]
        if lo <= y <= hi and hi - lo < 0.6:
            return lo, hi
    return None


def _seal(
    walkable, centre: Point, reach: float = 1.0, open_by: float = IMPASSABLE_BELOW / 2
):
    """Remove the floor narrower than the cap diameter within *reach* of *centre*."""
    opened = walkable.buffer(-open_by, join_style=2).buffer(open_by, join_style=2)
    local = centre.buffer(reach)
    return walkable.difference(local.difference(opened))


def regularise(walkable: Polygon, reach: float = THIN_FEATURE / 2) -> Polygon:
    """Remove obstacle teeth and floor slivers thinner than :data:`THIN_FEATURE`.

    The CAD trim around doors and wall ends leaves teeth a few millimetres to
    a few centimetres thick, and slits of floor between them. An agent pushed
    against such a corner lands inside it and JuPedSim stops the run with
    "outside of accessible area". Closing by half the feature size and then
    opening by a third of that, with mitred corners, removes both and moves no
    wall that is thicker.
    """
    closed = walkable.buffer(reach, join_style=2).buffer(-reach, join_style=2)
    opened = closed.buffer(-reach / 3, join_style=2).buffer(reach / 3, join_style=2)
    kept = largest(opened)
    _check_cut_off(walkable, kept)
    return kept


def final_walkable() -> tuple[Polygon, list[dict]]:
    """The extraction with every opening classified and settled.

    The gap finder keeps one chord per 1.2 m, so a narrow opening can hide a
    wider one next to it. Each round settles what the finder shows and looks
    again, until no opening is under :data:`CLEAR_CHECK`.
    """
    # Regularising widens the doors that the trim leaves 0.1 m thick; the front
    # interior door is set back to its deck width, between its leaves.
    front = _front_door_row()
    floor = _set_door_width(regularise(extracted_floor()), front)
    rows: list[dict] = [front]
    for round_ in range(MAX_ROUNDS):
        new = classify_gaps(floor)
        if not new:
            return floor, rows
        for row in new:
            row["pass"] = round_ + 1
        settled = apply_gap_table(floor, new, reach=0.25 * (round_ + 1))
        floor = largest(settled)
        _check_cut_off(settled, floor)
        rows += new
    left = [
        (round(m.x, 2), round(m.y, 2), round(w, 3))
        for w, _, _, m in find_passages(floor, CLEAR_CHECK)
    ]
    raise SystemExit(
        f"openings still under {CLEAR_CHECK} m after {MAX_ROUNDS} rounds: {left}"
    )


# ---- areas ----------------------------------------------------------------


def trapped_pockets(walkable: Polygon, radius: float = 0.23) -> Polygon | None:
    """Floor an agent of the radius cap cannot leave.

    Eroding by the cap radius splits off every pocket whose way out is narrower
    than a body; the pieces are grown back to the floor they stand on.
    """
    eroded = walkable.buffer(-radius)
    parts = sorted(getattr(eroded, "geoms", [eroded]), key=lambda g: -g.area)
    pockets = [p for p in parts[1:] if p.area > 0.5]
    if not pockets:
        return None
    return unary_union(pockets).buffer(radius).intersection(walkable)


def _check_isolated() -> None:
    """Stop if extracted floor with no opening to the main floor is in use.

    The extraction keeps the largest enclosed region; a room it leaves out
    must not hold an area, an exit strip or a checkpoint, unless recorded in
    :data:`ISOLATED`.
    """
    _, parts, _, domain, _ = EX.extract(
        NIST / "Station210_clean.fds", 0.1, 1.8, 0.05, 0.25, IGNORED_LAYERS
    )
    interior = sorted(
        (p for p in parts if not p.exterior.intersects(domain.boundary)),
        key=lambda p: -p.area,
    )
    unrecorded = _unrecorded(interior[1:], ISOLATED)
    if unrecorded:
        raise SystemExit(
            f"isolated floor in use at {unrecorded}: open it or record it in ISOLATED"
        )


def dropped_floor(walkable: Polygon, polys: dict[str, Polygon]) -> dict[str, float]:
    """Floor of each translated rectangle that no area keeps (m2).

    Service wells, trapped pockets and the smaller parts of a split rectangle;
    the README lists them and a test pins them, so a change shows.
    """
    kept = unary_union(list(polys.values()))
    return {
        name: translate(box(*RECTS[name])).intersection(walkable).difference(kept).area
        for name in polys
    }


def clip_areas(walkable: Polygon) -> dict[str, Polygon]:
    """Each Fahy rectangle, translated, clipped, one polygon, no overlaps."""
    pockets = trapped_pockets(walkable)
    floor = walkable if pockets is None else walkable.difference(pockets)
    floor = floor.difference(unary_union(SERVICE_WELLS))
    order = list(areas.PRIORITY) + [n for n in RECTS if n not in areas.PRIORITY]
    out: dict[str, Polygon] = {}
    claimed = None
    for name in order:
        poly = translate(box(*RECTS[name])).intersection(floor)
        if claimed is not None:
            poly = poly.difference(claimed)
        claimed = poly if claimed is None else unary_union([claimed, poly])
        part = largest(poly)
        if part is None:
            raise SystemExit(f"area {name!r} clipped away to nothing")
        out[name] = part
    return {n: out[n] for n in RECTS}


def capacity_rows(polys: dict[str, Polygon], radius: float = FB.RADIUS):
    """(name, n, area, need at 1x, headroom) as :func:`areas.capacity_report`."""
    per_agent = 2.5 * math.pi * radius**2
    counts = F.agents_per_row()
    return [
        (n, counts[n], p.area, counts[n] * per_agent, p.area / (counts[n] * per_agent))
        for n, p in polys.items()
    ]


# ---- exits and checkpoints --------------------------------------------------


def exit_polygons(walkable: Polygon) -> dict[str, Polygon]:
    out = {}
    for exit_id, (axis, line, (lo, hi), side) in EXIT_DOORS.items():
        a, b = sorted((line, line + side * EXIT_DEPTH))
        strip = box(lo, a, hi, b) if axis == "y" else box(a, lo, b, hi)
        floor = strip.intersection(walkable)
        poly = largest(floor)
        if poly is None or poly.area < 0.5 * strip.area:
            raise SystemExit(f"{exit_id}: the strip at the door is not walkable")
        if floor.area - poly.area > 0.01:
            raise SystemExit(f"{exit_id}: the strip at the door is split")
        out[exit_id] = poly
    return out


def _checkpoint_at(cp_id: str, cp: dict) -> tuple[float, float, float]:
    if cp_id in CHECKPOINT_AT:
        return CHECKPOINT_AT[cp_id]
    x, y = cp["center"]
    return x + TRANSLATION[0], y + TRANSLATION[1], cp["radius"]


def checkpoints(base: dict, walkable: Polygon) -> dict[str, dict]:
    """Fahy's seven checkpoints, translated or placed at their doorway."""
    out = {}
    for cp_id, cp in base["checkpoints"].items():
        x, y = cp["center"]
        nx, ny, radius = _checkpoint_at(cp_id, cp)
        if not Point(nx, ny).buffer(radius).within(walkable):
            raise SystemExit(f"{cp_id} at ({nx:.2f}, {ny:.2f}) is not inside the floor")
        new = FB._checkpoint((round(nx, 3), round(ny, 3)), radius)
        sign = cp.get("sign")
        if sign:
            new["sign"] = {
                **sign,
                "x": sign["x"] + (nx - x),
                "y": sign["y"] + (ny - y),
            }
        out[cp_id] = new
    return out


# ---- the scenario -----------------------------------------------------------


def build() -> tuple[dict, Polygon, dict]:
    walkable, rows = final_walkable()
    base = json.loads((FAHY / "source" / "config.json").read_text())
    _check_isolated()
    polys = clip_areas(walkable)
    counts = F.agents_per_row()

    distributions: dict[str, dict] = {}
    index = 0
    for row, poly in polys.items():
        # set_precision keeps the ring valid where plain rounding to 1 mm
        # would pinch it into a bow tie
        snapped = largest(shapely.set_precision(poly, 1e-3))
        if abs(poly.area - snapped.area) > 0.01 or snapped.interiors:
            raise SystemExit(f"area {row!r} changes when written to 1 mm")
        coords = [[round(x, 3), round(y, 3)] for x, y in snapped.exterior.coords]
        for (label, share, familiarity), n in zip(
            FB.CLASSES, FB.apportion(counts[row], [c[1] for c in FB.CLASSES])
        ):
            if n == 0:
                continue
            distributions[f"jps-distributions_{index}"] = {
                "type": "polygon",
                "coordinates": coords,
                "parameters": {
                    "number": n,
                    "radius": FB.RADIUS,
                    "v0": FB.V0,
                    "distribution_mode": "by_number",
                    "use_flow_spawning": False,
                    "use_premovement": False,
                    "radius_distribution": "gaussian",
                    "radius_std": FB.RADIUS_STD,
                    "v0_distribution": "gaussian",
                    "v0_std": FB.V0_STD,
                    "familiarity": familiarity,
                    "entrance": FB.FRONT_DOOR,
                    "fahy_row": row,
                    "fahy_class": label,
                },
            }
            index += 1

    exits = {}
    for exit_id, poly in exit_polygons(walkable).items():
        c = poly.centroid
        exits[exit_id] = {
            "type": "polygon",
            "coordinates": [
                [round(x, 3), round(y, 3)] for x, y in poly.exterior.coords
            ],
            "enable_throughput_throttling": False,
            "max_throughput": 0,
            "sign": {"x": c.x, "y": c.y, "alpha": None, "c": FB.SIGN_C[exit_id]},
        }

    cfg = {
        "project_version": base["project_version"],
        "config": json.loads(json.dumps(base["config"])),
        "exits": exits,
        "distributions": distributions,
        "checkpoints": checkpoints(base, walkable),
        "zones": {},
        "journeys": [],
        "transitions": [],
        "obstacles": {},
        "journeys_v2": [],
    }
    sim = cfg["config"]["simulation_settings"]["simulationParams"]
    sim["model_type"] = "WarpDriverModel"
    sim["max_simulation_time"] = 600.0
    # The library default, stated: this deck's primary run has no congestion
    # term. 0.024 is the hand-deck Fahy fit (station_fahy) and is the labelled
    # sensitivity here, not the primary setting (M4).
    cfg["routing"] = {"w_queue": 0.0}
    return cfg, walkable, {"rows": rows, "polys": polys}


def measured_widths(walkable: Polygon, rows: list[dict]) -> list[float | None]:
    """The narrowest chord of the final floor within 0.7 m of each table row.

    The front interior door is the cut along its line (:func:`front_door_width`).
    None for a closed opening, or one wider than 1.6 m.
    """
    passages = find_passages(walkable, 1.6)
    out: list[float | None] = []
    for row in rows:
        if row["class"] == "sealed":
            out.append(None)
        elif _is_front_door(Point(row["x"], row["y"])):
            out.append(front_door_width(walkable))
        else:
            near = [
                w
                for w, _, _, m in passages
                if math.hypot(m.x - row["x"], m.y - row["y"]) < 0.7
            ]
            out.append(min(near) if near else None)
    return out


def tables(rows: list[dict], polys: dict[str, Polygon], walkable: Polygon) -> str:
    lines = [
        "| pass | x | y | extracted | class | basis | final | measured |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r, got in zip(rows, measured_widths(walkable, rows)):
        final = "sealed" if r["class"] == "sealed" else f"{r['final']:.2f}"
        shown = (
            "sealed"
            if r["class"] == "sealed"
            else "over 1.6"
            if got is None
            else f"{got:.3f}"
        )
        basis = r["leaf"] or r["basis"]
        lines.append(
            f"| {r['pass']} | {r['x']:.2f} | {r['y']:.2f} | {r['extracted']:.2f} | {r['class']} "
            f"| {basis} | {final} | {shown} |"
        )
    lines += [
        "",
        "| area | n | m2 | need 1x | headroom | dropped m2 |",
        "|---|---|---|---|---|---|",
    ]
    dropped = dropped_floor(walkable, polys)
    for name, n, area, need, head in capacity_rows(polys):
        lines.append(
            f"| {name} | {n} | {area:.1f} | {need:.1f} | {head:.2f} | {dropped[name]:.1f} |"
        )
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    cfg, walkable, info = build()
    if "--tables" in argv:
        print(tables(info["rows"], info["polys"], walkable))
        return 0
    total = sum(d["parameters"]["number"] for d in cfg["distributions"].values())
    (HERE / "config.json").write_text(json.dumps(cfg, indent=2))
    (HERE / "geometry.wkt").write_text(walkable.wkt + "\n")
    print(
        f"{len(cfg['distributions'])} distributions, {total} agents "
        f"(Fahy placeable: {F.total_agents()}), walkable {walkable.area:.1f} m2"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
