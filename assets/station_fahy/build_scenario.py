#!/usr/bin/env python3
"""Build the Fahy Table 2 scenario on the hand-drawn Station geometry.

    .venv/bin/python assets/station_fahy/build_scenario.py

Stage 1 of the validation in
``docs/archive/superpowers/specs/2026-08-05-station-validation-design.md``: clear air,
no FDS. It tests whether the *familiarity gradient* plus the rule that everyone
entered through the front door reproduces the front-door pull Fahy measured.

What Stage 1 can and cannot show
--------------------------------
In clear air a familiarity model and a nearest-exit model agree on the
dance-floor row -- that row only separates them once the fire intervenes, which
is Stage 2. Stage 1's discriminator is the aggregate front-door share: Fahy
found at least 53 % of survivors tried or used the front door out of four
available, which a nearest-exit model has no reason to produce.

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
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from shapely import wkt as W
from shapely.geometry import Polygon, box

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

V0 = 1.3
RADIUS = 0.15

# The doorway at the north-east corner of the main bar. Two freehand strokes in
# the drawing -- a 0.15 m lip on the bar (ring 5) and a hook on the partition
# behind it (ring 6) -- happen to pass within 0.40 m of each other, narrower
# than two 0.15 m-radius bodies, so counterflow there deadlocks and those agents
# never evacuate (issue #103). No dimension backs either stroke, so the drawing
# stays as traced and the deck clips them here: 0.40 m -> 0.93 m.
DOORWAY_CLIPS = (
    (5, box(-3.60, 0.35, -2.45, 1.00)),
    (6, box(-3.70, 0.00, -3.00, 1.149)),
)


def widen_bar_doorway(walkable: Polygon) -> Polygon:
    """Cut :data:`DOORWAY_CLIPS` out of the obstacles they narrow."""
    rings = list(walkable.interiors)
    for index, clip in DOORWAY_CLIPS:
        rings[index] = largest_part(Polygon(rings[index]).difference(clip)).exterior
    return Polygon(walkable.exterior, rings)


def largest_part(poly):
    if poly.geom_type == "MultiPolygon":
        return max(poly.geoms, key=lambda p: p.area)
    return poly


def apportion(total: int, shares: list[float]) -> list[int]:
    """Largest-remainder apportionment, so the parts sum to *total* exactly."""
    raw = [total * s for s in shares]
    out = [int(x) for x in raw]
    for i in sorted(range(len(raw)), key=lambda i: raw[i] - out[i], reverse=True):
        if sum(out) >= total:
            break
        out[i] += 1
    return out


def build() -> tuple[dict, Polygon]:
    walkable = widen_bar_doorway(W.loads((SOURCE / "geometry.wkt").read_text()))
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
                    "radius_distribution": "constant",
                    "v0_distribution": "constant",
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
    for exit_id, exit_cfg in cfg["exits"].items():
        c = Polygon(exit_cfg["coordinates"]).centroid
        exit_cfg["sign"] = {"x": c.x, "y": c.y, "alpha": None, "c": SIGN_C[exit_id]}
    sim = cfg["config"]["simulation_settings"]["simulationParams"]
    sim["model_type"] = "WarpDriverModel"
    sim["max_simulation_time"] = 600.0
    # The library default is 0 -- congestion-aware routing is opt-in, because
    # the queue term (w_queue * base_speed_m_per_s * N / exit capacity; no
    # relation to this file's per-agent V0) scales with the population and no
    # constant suits every deck. 0.03 is this deck's calibration: it reproduces Fahy's 52.9 %
    # front-door share at this crowd of 333 and nowhere else. See
    # scripts/sweep_queue_weight.py and docs/routing.md.
    cfg["routing"] = dict(cfg.get("routing") or {}, w_queue=0.03)
    return cfg, walkable


def main() -> int:
    cfg, walkable = build()
    total = sum(d["parameters"]["number"] for d in cfg["distributions"].values())
    (HERE / "config.json").write_text(json.dumps(cfg, indent=2))
    (HERE / "geometry.wkt").write_text(walkable.wkt + "\n")

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
