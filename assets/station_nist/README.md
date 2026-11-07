# Station, Fahy Table 2 on the NIST-derived geometry

**Station-derived geometry (provenance unverified).** The walkable area comes
from `assets/station/Station210_clean.fds`; where that deck came from, and what
was dropped or changed relative to NCSTAR Appendix L2.2, is not documented yet
(#377).

The same 333 survivors, familiarity classes and agent parameters as
[`station_fahy`](../station_fahy/), on the NIST geometry instead of the
hand-drawn one. Nothing is copied: `build_scenario.py` imports the areas
(`areas.RECTS`, `PRIORITY`), the Fahy table and the classes from `station_fahy`.
`station_fahy` is unchanged.

```bash
.venv/bin/python assets/station_nist/build_scenario.py            # config.json, geometry.wkt
.venv/bin/python assets/station_nist/build_scenario.py --tables   # the tables below
.venv/bin/python assets/station_nist/plot_overlay.py              # overlay.png
.venv/bin/python run.py --scenario assets/station_nist --seed 4
```

![overlay](overlay.png)

## Status

Clear-air runs on seeds 4-23 place all 333 agents but **none ends by
evacuation**: 15 stop in a deadlock report (3-6 agents left), 3 reach the 600 s
cap (6-7 left) and 2 (seeds 7 and 23) stop with JuPedSim's "outside of
accessible area" at (16.03, -13.52) and (-5.14, -6.53). Acceptance item 2 is
not met; see "Open: stalls at narrow passages".

## Frame

Translation only, hand frame to NIST frame: **(+3.635, -8.366) m**. A chamfer
fit of the hand building interior to the NIST walkable boundary gives a median
residual of 0.07 m and a 90th percentile of 0.40 m. A similarity fit (rotation
-0.21 deg, scale 0.992) is a reported sensitivity and is not used.

### Landmark residuals

Hand-drawn landmark translated into the NIST frame, against the NIST deck.
Gate: each at most 0.5 m or listed with a reason.

| landmark | hand + T | NIST | residual | |
|---|---|---|---|---|
| building x min | -12.36 | -12.21 | 0.16 | ok |
| building y min (front wall) | -17.33 | -17.72 | 0.38 | ok |
| building y max | 3.35 | 3.34 | 0.01 | ok |
| building x max | 20.13 | 17.76 | 2.37 | over: the hand interior includes the lobby outside the platform door, which the NIST extraction keeps shut |
| door (-11.18, -4.37) | (-11.34, -4.27) | | 0.19 | ok |
| door (-9.93, -1.20) | (-9.92, -1.26) | | 0.06 | ok |
| door (-2.20, -0.47) | (-2.23, -0.50) | | 0.04 | ok |
| door (4.88, -0.70) | (4.85, -0.66) | | 0.05 | ok |
| door (4.92, 1.50) | (4.84, 1.47) | | 0.09 | ok |
| front interior door (3.44, -14.38) | (3.39, -13.79) | | 0.59 | over: the hand drawing places the interior door 0.6 m north; the deck's leaves at y -14.36 are the reference |
| door (16.04, -12.98) | (16.47, -13.35) | | 0.57 | over: the drawing has one opening where the deck has two (16.04 and 17.31) |
| door (17.31, -12.98) | (16.47, -13.35) | | 0.92 | over: same opening |
| door 5i (-5.81, -1.91) | none within 1.5 m | | n/a | over: the drawing's opening was not traced |
| door (-4.96, 1.63) | none within 1.5 m | | n/a | over: not traced |
| doorway (2.32, -13.27) | nearest (3.39, -13.79) | | 1.19 | over: not traced as a separate opening |
| main bar counter, bounding box | y -14.34..-7.90, x -7.2..1.31 | y -14.22..-9.46, x -4.19..0.94 | south edge 0.12, east edge 0.37 | the drawing's outline (hand obstacle 1) also encloses the service aisle north of the counter |
| stage (drawing obstacle 7) | not identified | | | the drawing's obstacle numbers are not in the repository |

## Gap table

Every opening under 0.9 m in the extraction (24 of them), classified once from
the extraction, before any run. `extracted` is the chord found by
`simplify_doors.find_passages`; the extractor widens the thin jamb markers by
0.05 m per side, so a doorway loses 0.10 m.

- **door**: a deck door leaf (`A-DOOR-STND-1`, `door 5i`) within 0.5 m, or the
  trimmed doorway at (2.32, -13.27). Restored to the extracted chord plus 0.10 m
  (the deck's clear width). The front interior door is set to **0.91 m**
  (NCSTAR 914 mm; deck leaves at x 2.97 and 3.88).
- **fixture**: casework or a wall opening without a leaf. Left as extracted.
- **sealed**: narrower than the cap diameter, 0.46 m (radius 0.20 + 3 x 0.01,
  times two). M2 sealed only slits under 0.2 m; the first ten-seed run on that
  rule left agents stuck at the 0.27, 0.30 and 0.39 m openings, so the
  threshold is the diameter an agent needs. This is a deviation from M2.

`simplify_doors.py` is not run on this geometry.

| x | y | extracted | class | final | deck door leaf |
|---|---|---|---|---|---|
| -11.18 | -4.37 | 0.71 | door | 0.81 | A-DOOR-STND-1 |
| -9.93 | -1.20 | 0.71 | door | 0.81 | A-DOOR-STND-1 |
| -5.81 | -1.91 | 0.70 | door | 0.80 | door 5i |
| -5.62 | -6.64 | 0.49 | fixture | 0.49 |  |
| -4.96 | 1.63 | 0.53 | door | 0.63 | A-DOOR-STND-1 |
| -3.41 | 1.85 | 0.71 | fixture | 0.71 |  |
| -2.20 | -0.47 | 0.58 | door | 0.68 | A-DOOR-STND-1 |
| -0.40 | -0.61 | 0.61 | fixture | 0.61 |  |
| 0.74 | -10.37 | 0.39 | sealed | sealed |  |
| 0.94 | -7.56 | 0.52 | fixture | 0.52 |  |
| 2.09 | -2.69 | 0.60 | fixture | 0.60 |  |
| 2.32 | -13.27 | 0.71 | door | 0.81 |  |
| 2.49 | -4.43 | 0.52 | fixture | 0.52 |  |
| 3.44 | -14.38 | 0.85 | door | 0.91 | A-DOOR-STND-1 |
| 3.44 | -11.71 | 0.30 | sealed | sealed |  |
| 4.88 | -0.70 | 0.68 | door | 0.78 | A-DOOR-STND-1 |
| 4.92 | 1.50 | 0.71 | door | 0.81 | A-DOOR-STND-1 |
| 6.73 | -4.82 | 0.03 | sealed | sealed |  |
| 14.36 | -4.79 | 0.05 | sealed | sealed |  |
| 14.38 | -3.07 | 0.61 | fixture | 0.61 |  |
| 14.79 | -12.04 | 0.69 | fixture | 0.69 |  |
| 14.92 | -10.27 | 0.27 | sealed | sealed |  |
| 16.04 | -12.98 | 0.66 | door | 0.76 | A-DOOR-STND-1 |
| 17.31 | -12.98 | 0.44 | door | 0.54 | A-DOOR-STND-1 |

## Areas

Each `RECTS` box translated, clipped to the walkable area in `PRIORITY` order,
largest part kept. Capacity is the repo's `areas.capacity_report` rule: 2.5 x
pi x r^2 per agent at r = 0.20 m. Headroom is area over need.

| area | n | m2 | need 1x | headroom |
|---|---|---|---|---|
| Near stage or on dance floor | 75 | 43.3 | 23.6 | 1.84 |
| Behind dance floor | 74 | 46.6 | 23.2 | 2.01 |
| Center stage-side | 7 | 9.1 | 2.2 | 4.14 |
| Stage | 4 | 15.2 | 1.3 | 12.06 |
| Back wall platform | 15 | 9.5 | 4.7 | 2.01 |
| Main bar | 37 | 39.7 | 11.6 | 3.41 |
| Between bars | 29 | 27.7 | 9.1 | 3.04 |
| Rear bar / dart room | 28 | 12.8 | 8.8 | 1.46 |
| Back hallway | 14 | 8.2 | 4.4 | 1.86 |
| Entryway | 17 | 9.6 | 5.3 | 1.79 |
| Sunroom | 16 | 37.7 | 5.0 | 7.51 |
| Near stage door | 17 | 12.5 | 5.3 | 2.35 |


Recorded choices:

- **Main bar**: the extra 11.2 m2 the NIST clip adds over the hand clip is the
  bartender well inside the horseshoe counter (`A-CASE-CNTR-1`, `A-CASE-CABN-1`
  and the full-height wall at y -9.51), reached only through a 0.39 m opening.
  It is not bar floor. The opening is sealed, so the well is not walkable.
- **Rear bar / dart room**: east edge -8.0 (the Fahy plan), not the -6.0 of the
  hand deck (#380). The largest part is 12.8 m2 (13.9 m2 over three parts).
- **Entryway**: the ticket-area part, x 4.5-6.8, unclipped. The vestibule part
  (x 2.1-4.3, 8.1 m2) is the alternative. Agents in the ticket area reach the
  front exit only through the 0.91 m interior door at y -14.36
  (`tests/test_station_nist.py`).
- **Near stage strip** at x 14.5-15.6 is dropped (a second part of 5.2 m2); the
  back-wall platform handrail is passable (`assets/station/README.md`).
- Under the 2x gate of the contract (2 x n x 0.314 m2) four areas fall short
  (Near stage or on dance floor, Rear bar / dart room, Back hallway, Entryway);
  the maintainer chose the 1x rule.

## Exits and checkpoints

Exit ids and order are Fahy's: `jps-exits_0` front, `_1` main bar side door,
`_2` kitchen side door, `_3` platform door. Each exit is a 0.4 m strip just
inside the deck door at its width: front x 2.44-4.34 at y -17.11, side doors
y -13.51..-12.51 and -8.61..-7.61 at x -5.97, platform door y -12.38..-11.39 at
x 17.66. `SIGN_C` (the stage door unlit, c = 3) and `entrance` (the front door)
carry over.

Checkpoints are not decoration without journeys. With no journeys and no
transitions the route graph wires every spawn area to every checkpoint and exit
(`route_graph._wire_by_type`), checkpoints block the links that pass through
them, and a vision-less run reveals a node's neighbours on arrival. Dropping
them would change routing, so all seven stay, with Fahy's roles and signs:

| checkpoint | role | hand frame | NIST frame |
|---|---|---|---|
| `_0`, `_1` | either side of door 5i, dart room hallway | (-8.59, 6.34), (-8.95, 5.59) | (-4.96, -2.03), (-5.32, -2.78) |
| `_2` | hall crossing | (0.85, -3.56) | (4.49, -11.93) |
| `_3` | outer end of the front vestibule | (-0.33, -9.15) | (3.39, -16.60) |
| `_4` | main bar side door | (-9.18, -4.64) | (-5.50, -13.01) |
| `_5` | kitchen side door | (-9.32, 0.12) | (-5.50, -8.11) |
| `_6` | vestibule, south of the interior door | (-0.25, -6.60) | (3.38, -14.97) |

## Routing

`w_queue = 0`, the library default, is primary here. 0.024 is the hand-deck
fit of `station_fahy` (53 % front-door share over three seeds, fitted before
the additive model; not re-fitted) and is the labelled sensitivity on this
deck: `cfg["routing"] = {"w_queue": 0.024}`.

## Geometry regularisation (workaround record)

`build_scenario.regularise` closes and opens the extracted polygon by 0.045 m
with mitred corners before the gap table is applied.

- **Reason**: the CAD trim around door jambs and wall ends leaves teeth and
  floor slivers 5 mm to 5 cm wide. An agent pushed against one lands inside it
  and JuPedSim stops with "Point (...) is outside of accessible area". On the
  unmodified extraction that ended 12 of 20 runs within two minutes, most at the front
  interior door.
- **Affected versions**: jupedsim 1.4.2 with WarpDriverModel.
- **Upstream issue**: none yet.
- **Regression test**: `tests/test_station_nist.py::test_the_files_are_what_the_build_script_writes`
  pins the regularised file; the ten-seed run is the behavioural check.
- **Removal condition**: JuPedSim tolerates agents against sub-centimetre
  corners, or the extractor stops emitting the trim.

## Open: stalls at narrow passages

With the gap table above, seeds 4-23 leave 1-7 agents at four passages that
are narrower than 0.65 m and were classified `fixture`: the casework at
(2.49, -4.43) and (2.09, -2.69), and the wall openings at (-5.62, -6.64) and
(0.94, -7.56) in front of the kitchen door. Opening those four and two more to
0.9 m as a diagnostic still leaves 1-5 agents stuck at (2.3, -3.5), (3.1, -3.5)
and near the platform door. Radius and `w_queue` were not touched.
