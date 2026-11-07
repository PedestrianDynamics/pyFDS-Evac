#!/usr/bin/env python3
"""Build the Fahy Table 2 scenario on the NIST-derived Station geometry.

    .venv/bin/python assets/station_nist/build_scenario.py          # write
    .venv/bin/python assets/station_nist/build_scenario.py --tables # print

Station-derived geometry (provenance unverified, #377).

The walkable area is ``assets/station/geometry.wkt``, extracted from the NIST
deck by ``assets/station/extract_walkable.py``. The areas, the Fahy table, the
familiarity classes and every agent parameter are *imported* from
``assets/station_fahy`` -- nothing is copied -- so the two decks differ only in
the geometry, the exits and the checkpoints.

What this script adds to the extraction, each recorded in the README:

* a translation hand frame -> NIST frame (:data:`TRANSLATION`);
* the gap table: every opening under 0.9 m in the extraction is classified once
  (deck door, trimmed doorway, fixture or sealed) and the doors are restored to
  the deck's clear width, the openings no agent fits through sealed (:func:`classify_gaps`);
* the areas, clipped to the walkable area in ``PRIORITY`` order;
* exits just inside each deck door, and checkpoints at the doorways.

``simplify_doors.py`` is deliberately not run on this geometry: it would raise
every opening to 0.9 m, including the fixtures.
"""

from __future__ import annotations

import importlib.util
import json
import math
import sys
from pathlib import Path

import shapely
from shapely import affinity
from shapely import wkt as W
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

# An opening narrower than the largest agent (radius cap 0.23 m) is not a
# passage for this population: the navigation mesh routes through it and the
# agents jam. M2 seals only the slits under 0.2 m; the first ten-seed run on
# that rule left agents stuck at the 0.27, 0.30 and 0.39 m openings, so the
# threshold is the cap diameter (README, "Gap table").
IMPASSABLE_BELOW = 0.46
CLEAR_BELOW = 0.90  # m, the gap table covers every opening under this
HALF_CELL_LOSS = 0.10  # m, two jambs widened by the extractor's 0.05 m each
DOOR_LEAF_REACH = 0.5  # m, a deck door leaf this close makes the gap a door
THIN_FEATURE = 0.09  # m, CAD debris: obstacle teeth and floor slivers below this
FRONT_INTERIOR_DOOR = (3.44, -14.38)
FRONT_INTERIOR_CLEAR = 0.91  # m, NCSTAR 914 mm; leaves at x 2.97 and 3.88

# The Rear bar / dart room east edge is the Fahy plan's -8.0, not the -6.0 of
# the hand deck (#380): on the NIST geometry -8.0 holds 28 agents (README).
RECTS = {**areas.RECTS, "Rear bar / dart room": (-13.5, 0.5, -8.0, 7.5)}

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


def _door_leaves() -> list[tuple[str, float, float]]:
    _, obstructions = EX.parse_deck(NIST / "Station210_clean.fds")
    return [
        (name, (x0 + x1) / 2, (y0 + y1) / 2)
        for name, x0, x1, y0, y1, z0, z1 in obstructions
        if z1 >= 0.1 and z0 <= 1.8 and EX.is_door(name)
    ]


def classify_gaps(walkable: Polygon) -> list[dict]:
    """Every opening narrower than 0.9 m, classified once (M2).

    ``door``     a deck door leaf within 0.5 m: restored to the deck clear width
                 (the extracted chord plus the 0.10 m the extractor took, and
                 the NCSTAR 0.91 m at the front interior door);
    ``fixture``  furniture or fixture clearance: left as extracted;
    ``sealed``   narrower than the cap diameter: closed (a slit under 0.2 m in M2).
    """
    leaves = _door_leaves()
    rows = []
    for width, a, b, mid in sorted(
        SD.find_passages(walkable, CLEAR_BELOW), key=lambda p: (p[3].x, p[3].y)
    ):
        distance, name = min(
            (math.hypot(mid.x - x, mid.y - y), n) for n, x, y in leaves
        )
        if distance <= DOOR_LEAF_REACH or _is_trimmed_doorway(mid):
            cls = "door"
            final = round(width + HALF_CELL_LOSS, 2)
            if (
                math.hypot(
                    mid.x - FRONT_INTERIOR_DOOR[0], mid.y - FRONT_INTERIOR_DOOR[1]
                )
                < 0.5
            ):
                final = FRONT_INTERIOR_CLEAR
        elif width < IMPASSABLE_BELOW:
            cls, final = "sealed", 0.0
        else:
            cls, final = "fixture", round(width, 2)
        rows.append(
            {
                "x": round(mid.x, 2),
                "y": round(mid.y, 2),
                "extracted": round(width, 2),
                "class": cls,
                "final": final,
                "leaf": name if distance <= DOOR_LEAF_REACH else "",
                "a": a,
                "b": b,
            }
        )
    return rows


def _is_trimmed_doorway(mid: Point) -> bool:
    """The x 2.3 opening between the main bar and the front of house.

    The deck frames it with trim at y -13.67 and -12.86 and draws no leaf.
    """
    return abs(mid.x - 2.32) < 0.2 and abs(mid.y + 13.27) < 0.2


def apply_gap_table(walkable: Polygon, rows: list[dict]) -> Polygon:
    """Set each door to its clear width and seal what no agent fits through."""
    for row in rows:
        if row["class"] == "door":
            walkable = _set_door_width(walkable, row)
    for row in rows:
        if row["class"] == "sealed":
            walkable = _seal(walkable, Point(row["x"], row["y"]))
    return walkable


def _set_door_width(walkable: Polygon, row: dict) -> Polygon:
    """Cut the opening to the clear width, or wall it in down to that width."""
    a, b = row["a"], row["b"]
    mx, my = (a.x + b.x) / 2, (a.y + b.y) / 2
    # Axis aligned: the sampled chord ends are not exactly opposite, and a
    # tilted patch leaves slivers along the jambs.
    along_x = abs(b.x - a.x) >= abs(b.y - a.y)
    half = row["final"] / 2
    if not along_x:
        flipped = affinity.affine_transform(walkable, [0, -1, 1, 0, 0, 0])
        fixed = _set_door_width_x(flipped, (-my, mx), half)
        return affinity.affine_transform(fixed, [0, 1, -1, 0, 0, 0])
    return _set_door_width_x(walkable, (mx, my), half)


def _set_door_width_x(walkable: Polygon, mid: tuple[float, float], half: float):
    mx, my = mid
    walkable = walkable.union(box(mx - half, my - 0.25, mx + half, my + 0.25))
    for side in (-1, 1):
        plane = mx + side * half
        for reach in (0.14, 0.11, 0.08, 0.05, 0.02):
            run = _wall_run(walkable, plane + side * reach, my)
            if run is None:
                continue
            x0, x1 = sorted((plane, plane + side * reach))
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
    "outside of accessible area". Closing then opening by half the feature
    size, with mitred corners, removes both and moves no wall that is thicker.
    """
    closed = walkable.buffer(reach, join_style=2).buffer(-reach, join_style=2)
    opened = closed.buffer(-reach / 3, join_style=2).buffer(reach / 3, join_style=2)
    return largest(opened)


def final_walkable() -> tuple[Polygon, list[dict]]:
    extracted = W.loads((NIST / "geometry.wkt").read_text())
    rows = classify_gaps(extracted)
    return largest(apply_gap_table(regularise(extracted), rows)), rows


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


def clip_areas(walkable: Polygon) -> dict[str, Polygon]:
    """Each Fahy rectangle, translated, clipped, one polygon, no overlaps."""
    pockets = trapped_pockets(walkable)
    floor = walkable if pockets is None else walkable.difference(pockets)
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
        poly = largest(strip.intersection(walkable))
        if poly is None or poly.area < 0.5 * strip.area:
            raise SystemExit(f"{exit_id}: the strip at the door is not walkable")
        out[exit_id] = poly
    return out


def checkpoints(base: dict, walkable: Polygon) -> dict[str, dict]:
    """Fahy's seven checkpoints, translated or placed at their doorway."""
    out = {}
    for cp_id, cp in base["checkpoints"].items():
        x, y = cp["center"]
        radius = cp["radius"]
        if cp_id in CHECKPOINT_AT:
            nx, ny, radius = CHECKPOINT_AT[cp_id]
        else:
            nx, ny = x + TRANSLATION[0], y + TRANSLATION[1]
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
    polys = clip_areas(walkable)
    counts = F.agents_per_row()

    distributions: dict[str, dict] = {}
    index = 0
    for row, poly in polys.items():
        # set_precision keeps the ring valid where plain rounding to 1 mm
        # would pinch it into a bow tie
        coords = [
            [round(x, 3), round(y, 3)]
            for x, y in largest(shapely.set_precision(poly, 1e-3)).exterior.coords
        ]
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


def tables(rows: list[dict], polys: dict[str, Polygon]) -> str:
    lines = [
        "| x | y | extracted | class | final | deck door leaf |",
        "|---|---|---|---|---|---|",
    ]
    for r in rows:
        final = "sealed" if r["class"] == "sealed" else f"{r['final']:.2f}"
        lines.append(
            f"| {r['x']:.2f} | {r['y']:.2f} | {r['extracted']:.2f} | {r['class']} "
            f"| {final} | {r['leaf']} |"
        )
    lines += ["", "| area | n | m2 | need 1x | headroom |", "|---|---|---|---|---|"]
    for name, n, area, need, head in capacity_rows(polys):
        lines.append(f"| {name} | {n} | {area:.1f} | {need:.1f} | {head:.2f} |")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    cfg, walkable, info = build()
    if "--tables" in argv:
        print(tables(info["rows"], info["polys"]))
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
