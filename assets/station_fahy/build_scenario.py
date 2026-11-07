#!/usr/bin/env python3
"""Build the Fahy Table 2 scenario on the hand-drawn Station geometry.

    .venv/bin/python assets/station_fahy/build_scenario.py          # config.json
    .venv/bin/python assets/station_fahy/build_scenario.py --full   # + config_full.json

Stage 1 of the validation in
``docs/archive/superpowers/specs/2026-08-05-station-validation-design.md``: clear air,
no FDS. It tests whether the *familiarity gradient* plus the rule that everyone
entered through the front door reproduces the front-door pull Fahy measured.

What Stage 1 can and cannot show
--------------------------------
In clear air a familiarity model and a nearest-exit model agree on the
dance-floor row -- that row only separates them once the fire intervenes, which
is Stage 2. Stage 1's discriminator is the aggregate front-door share: at least
53 % of survivors tried or used the front door out of four available, which a
nearest-exit model has no reason to produce. The 53 % is derived, not stated
by Fahy, who writes "at least 50 percent": (127 used + 62 attempted)/355,
from "Exit Choice and Travel Paths". Time zero is first flame (NCSTAR 2,
Table 2-2), known to +-2 s.

Familiarity, from the paper rather than tuned
---------------------------------------------
``familiarity`` is the probability each exit is already in an agent's map.
Fahy reports visit frequency for 288 patrons; a *separate* sample of 82 reports
exit awareness, and the two corroborate each other:

    first visit      29.2 %   vs   aware of no alternates   29.3 %
    more than five   38.5 %   vs   aware of all or most     39.0 %

So first-timers get 0.0 and the >5-visit group 0.85, with the two middle groups
interpolated. No parameter here is fitted to the exit-usage data that Table 2
scores -- that would turn a validation into a calibration.

Note this supersedes the spec's prose ("~40 % occasional, ~20 % regulars"); the
published counts give 21.5 % and 38.5 %.

Every agent knows the front door regardless of class, via ``entrance``: every
patron entered that way, tickets collected and hands stamped. That single
empirically-grounded rule is the mechanism behind the crush.

``--full`` also writes ``config_full.json``: every distribution labelled by
``parameters.population`` (read by ``validate.py``), the 333 placed survivors
plus 22 unplaced survivors and 100 victims. Both extra groups are spread over
the areas in proportion to the placed survivors (largest remainder, as
:func:`apportion`), with the same familiarity classes and agent parameters:

    area                           placed unplaced  victim
    Stage                               4        0       1
    Near stage door                    17        1       5
    Near stage or on dance floor       75        5      23
    Back wall platform                 15        1       5
    Sunroom                            16        1       5
    Behind dance floor                 74        5      22
    Back hallway                       14        1       4
    Between bars                       29        2       9
    Rear bar / dart room               28        2       8
    Entryway                           17        1       5
    Main bar                           37        2      11
    Center stage-side                   7        1       2
    Total                             333       22     100

The front exit moved to the doorway. The hand-drawn polygon lay about 3 m
outside the front wall, so agents already outdoors at 86 s would have been
re-routed back in. Exit 0 only; no other exit, spawn, wall or radius changed.
Old polygon (``source/config.json``): x -1.544 .. 1.311, y -13.717 .. -11.951.
New polygon (:data:`FRONT_EXIT_POLYGON`): x -1.108 .. 0.619, y -9.50 .. -9.10
(outside face of the exterior double doors, 1.73 m clear). The sign, placed at
the exit centroid, moved with it from (-0.116, -12.834) to (-0.245, -9.300).

``source/geometry.wkt`` carries the drawing with its doorways already opened by
``simplify_doors.py``; re-trace the drawing and that script has to run again.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from shapely import wkt as W
from shapely.geometry import Point, Polygon, box

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

import areas  # noqa: E402
import fahy_table2 as F  # noqa: E402

SOURCE = HERE / "source"
FRONT_DOOR = "jps-exits_0"

# Unlit stage-door sign: six survivors noticed it unlit, one said there was no
# sign at all. Lit signs elsewhere. c is the sign's contrast constant.
SIGN_C = {
    "jps-exits_0": 8.0,  # front
    "jps-exits_1": 8.0,  # main bar, lit sign noticed by 2
    "jps-exits_2": 8.0,  # kitchen
    "jps-exits_3": 3.0,  # stage door, unlit
}

# (label, share of patrons, familiarity) -- see the module docstring.
CLASSES = (
    ("first_visit", 84 / 288, 0.00),
    ("second_visit", 31 / 288, 0.10),
    ("visits_3_to_5", 62 / 288, 0.33),
    ("regular", 111 / 288, 0.85),
)

# A population, not one repeated person. Uniform agents queue in perfect
# symmetry, and collision-free speed has no push or noise to break the arch that
# forms at a doorway, so a uniform crowd of them can stand at a door forever.
# Spreads are ordinary adult figures, not fitted to anything this deck scores.
V0 = 1.3
V0_STD = 0.2
# 0.20 m is an effective contact disc, not half a body width: adult shoulder
# breadth is 0.46-0.51 m (Weidmann 1993 sec. 2.32.1; Korhonen & Hostikka 2009,
# VTT WP 119, Table 1; ANSUR II via Dufour et al., arXiv:2508.19865). At the
# 0.15 m this deck used, three agents fit abreast in the 0.914 m interior door
# and the front entrance passed nearly 7 persons per metre-second, several
# times any measured door flow. The spread was narrowed from 0.02 m after the
# pilot: agents with r >= 0.24 m stalled alone at the ~0.9 m doors under
# WarpDriverModel (#908, jupedsim#1719). Chosen on run completion, not on any
# scored target. The cap is the mean + 3 sigma = 0.23 m.
RADIUS = 0.20
RADIUS_STD = 0.01

# config_full.json: Fahy's 355 survivors less the 333 placed, and the dead.
UNPLACED_TOTAL = 22
VICTIM_TOTAL = 100

# A checkpoint inside the vestibule, between the last node before the front
# door and the exit. Agents do not need it to find the doorway: JuPedSim
# (>= 1.4.2) walks them along the navigation mesh to their target, round
# walls, not in a straight line (#114, closed). It stays because the deck is
# calibrated with it (w_queue below).
VESTIBULE_CHECKPOINT = ("jps-checkpoints_6", (-0.25, -6.6), 0.35)

# The front exit sits on the outside face of the exterior double doors: x is the
# clear opening between the jambs (1.73 m, NCSTAR 2 Table 7-6: 1727 mm), y runs
# from the jamb ends (-9.10) 0.4 m outward. Agents leave the building at the
# doorway, so the exit is the doorway line, as the NIST deck has it. The strip
# touches no spawn area (areas are clipped to the building interior).
# Before, the polygon lay about 3 m outside the front wall:
#   x -1.544 .. 1.311, y -13.717 .. -11.951
# and the exit's sign (at the polygon centroid) moves with it, from
# (-0.116, -12.834) to (-0.245, -9.300).
FRONT_EXIT_POLYGON = box(-1.108, -9.50, 0.619, -9.10)


def largest_part(poly):
    # Clipping an area against the building can leave a collection whose stray
    # members are the lines where it grazed a wall; only the polygons can hold
    # agents.
    if poly.geom_type == "Polygon":
        return poly
    parts = [p for p in poly.geoms if p.geom_type == "Polygon"]
    return max(parts, key=lambda p: p.area) if parts else poly


def _check_front_exit(walkable, polys) -> None:
    """The front exit must be floor and clear of every spawn area."""
    if not FRONT_EXIT_POLYGON.within(walkable):
        raise SystemExit("front exit polygon is not inside the walkable area")
    for row, poly in polys.items():
        if poly.intersects(FRONT_EXIT_POLYGON):
            raise SystemExit(f"front exit polygon overlaps the spawn area {row!r}")


def _checkpoint(center: tuple[float, float], radius: float) -> dict:
    """A circular waypoint stage, in the shape the scenario schema expects."""
    circle = Point(*center).buffer(radius, quad_segs=8)
    return {
        "type": "polygon",
        "coordinates": [[round(x, 6), round(y, 6)] for x, y in circle.exterior.coords],
        "waiting_time": 0,
        "waiting_time_distribution": "constant",
        "waiting_time_std": 1,
        "enable_throughput_throttling": False,
        "max_throughput": 1,
        "speed_factor": 1,
        "shape": "circle",
        "center": list(center),
        "radius": radius,
    }


def apportion(total: int, shares: list[float]) -> list[int]:
    """Largest-remainder apportionment, so the parts sum to *total* exactly."""
    raw = [total * s for s in shares]
    out = [int(x) for x in raw]
    for i in sorted(range(len(raw)), key=lambda i: raw[i] - out[i], reverse=True):
        if sum(out) >= total:
            break
        out[i] += 1
    return out


def population_counts() -> dict[str, dict[str, int]]:
    """Per area, the agents of each population label in ``config_full.json``.

    The 22 survivors Fahy et al. could not place and the 100 victims are spread
    over the areas in proportion to the placed survivors (Spearpoint's rule for
    the unplaced), by largest-remainder apportionment.
    """
    placed = F.agents_per_row()
    shares = [n / sum(placed.values()) for n in placed.values()]
    unplaced = apportion(UNPLACED_TOTAL, shares)
    victim = apportion(VICTIM_TOTAL, shares)
    return {
        row: {"placed": placed[row], "unplaced": u, "victim": v}
        for row, u, v in zip(placed, unplaced, victim)
    }


def with_populations(cfg: dict) -> dict:
    """A copy of *cfg* with every distribution labelled by population.

    The unplaced and victim agents reuse the area polygon and the agent
    parameters of the area's placed distributions, and the same familiarity
    classes in the same shares.
    """
    full = json.loads(json.dumps(cfg))
    dists = full["distributions"]
    template: dict[str, dict] = {}
    for dist in dists.values():
        dist["parameters"]["population"] = "placed"
        template.setdefault(dist["parameters"]["fahy_row"], dist)
    index = len(dists)
    for row, counts in population_counts().items():
        for population in ("unplaced", "victim"):
            class_counts = apportion(counts[population], [c[1] for c in CLASSES])
            for (label, _, familiarity), n in zip(CLASSES, class_counts):
                if n == 0:
                    continue
                dist = json.loads(json.dumps(template[row]))
                dist["parameters"].update(
                    number=n,
                    familiarity=familiarity,
                    fahy_class=label,
                    population=population,
                )
                dists[f"jps-distributions_{index}"] = dist
                index += 1
    return full


def write_full(cfg: dict, directory: Path) -> None:
    """Write ``config_full.json`` next to ``config.json`` and print the counts."""
    full = with_populations(cfg)
    (directory / "config_full.json").write_text(json.dumps(full, indent=2))
    total = sum(d["parameters"]["number"] for d in full["distributions"].values())
    print(f"config_full.json: {total} agents")
    print(f"  {'area':30s} placed unplaced victim")
    for row, c in population_counts().items():
        print(f"  {row:30s} {c['placed']:6d} {c['unplaced']:8d} {c['victim']:6d}")


def build() -> tuple[dict, Polygon]:
    walkable = W.loads((SOURCE / "geometry.wkt").read_text())
    base = json.loads((SOURCE / "config.json").read_text())
    polys = areas.polygons(walkable)
    counts = F.agents_per_row()

    distributions: dict[str, dict] = {}
    index = 0
    for row, poly in polys.items():
        part = largest_part(poly)
        if part.is_empty:
            raise SystemExit(f"area {row!r} clipped away to nothing")
        coords = [[round(x, 3), round(y, 3)] for x, y in part.exterior.coords]
        for (label, share, familiarity), n in zip(
            CLASSES, apportion(counts[row], [c[1] for c in CLASSES])
        ):
            if n == 0:
                continue
            distributions[f"jps-distributions_{index}"] = {
                "type": "polygon",
                "coordinates": coords,
                "parameters": {
                    "number": n,
                    "radius": RADIUS,
                    "v0": V0,
                    "distribution_mode": "by_number",
                    "use_flow_spawning": False,
                    "use_premovement": False,
                    "radius_distribution": "gaussian",
                    "radius_std": RADIUS_STD,
                    "v0_distribution": "gaussian",
                    "v0_std": V0_STD,
                    "familiarity": familiarity,
                    "entrance": FRONT_DOOR,
                    # read by validate.py, not by the engine
                    "fahy_row": row,
                    "fahy_class": label,
                },
            }
            index += 1

    cfg = json.loads(json.dumps(base))
    cfg["distributions"] = distributions
    cfg["checkpoints"][VESTIBULE_CHECKPOINT[0]] = _checkpoint(*VESTIBULE_CHECKPOINT[1:])
    _check_front_exit(walkable, polys)
    cfg["exits"][FRONT_DOOR]["coordinates"] = [
        [round(x, 3), round(y, 3)] for x, y in FRONT_EXIT_POLYGON.exterior.coords
    ]
    for exit_id, exit_cfg in cfg["exits"].items():
        c = Polygon(exit_cfg["coordinates"]).centroid
        exit_cfg["sign"] = {"x": c.x, "y": c.y, "alpha": None, "c": SIGN_C[exit_id]}
    sim = cfg["config"]["simulation_settings"]["simulationParams"]
    # Collision-free speed is the model whose speed-density relation would limit
    # door flow, which is what these egress times need. It cannot be used yet:
    # under it a crowd deadlocks in the four-way crossing at jps-checkpoints_2
    # (#706), with or without the vestibule checkpoint. With seed 420, 100 of
    # 333 are left at the 600 s cap, 80 of them within 3 m of that checkpoint.
    sim["model_type"] = "WarpDriverModel"
    sim["max_simulation_time"] = 600.0
    # The library default is 0 -- congestion-aware routing is opt-in, because
    # the queue term (w_queue * base_speed_m_per_s * N / exit capacity; no
    # relation to this file's per-agent V0) scales with the population and no
    # constant suits every deck. 0.024 is this deck's calibration, fitted under
    # the additive model before 8bda7f7: 53.0 % front-door share over seeds
    # 420-422 against Fahy's 52.9 % (55.0 % at 0.02, 50.2 % at 0.03). At 0.5.0
    # the same sweep scores 34.8 %; the value has not been re-fitted. See
    # scripts/sweep_queue_weight.py and docs/routing.md.
    cfg["routing"] = dict(cfg.get("routing") or {}, w_queue=0.024)
    return cfg, walkable


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--full",
        action="store_true",
        help="also write config_full.json: 22 unplaced survivors and 100 victims",
    )
    args = ap.parse_args(argv)
    cfg, walkable = build()
    total = sum(d["parameters"]["number"] for d in cfg["distributions"].values())
    (HERE / "config.json").write_text(json.dumps(cfg, indent=2))
    (HERE / "geometry.wkt").write_text(walkable.wkt + "\n")
    if args.full:
        write_full(cfg, HERE)

    print(
        f"{len(cfg['distributions'])} distributions, {total} agents "
        f"(Fahy placeable: {F.total_agents()})"
    )
    by_class: dict[str, int] = {}
    for d in cfg["distributions"].values():
        by_class[d["parameters"]["fahy_class"]] = (
            by_class.get(d["parameters"]["fahy_class"], 0) + d["parameters"]["number"]
        )
    for label, share, familiarity in CLASSES:
        n = by_class.get(label, 0)
        print(
            f"  {label:14s} familiarity {familiarity:4.2f}  "
            f"{n:4d} agents {n / total:6.1%}  (Fahy {share:.1%})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
