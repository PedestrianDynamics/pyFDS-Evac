---
title: "Pathfinder's FED cases"
linkTitle: "Pathfinder FED"
weight: 16
math: true
aliases: [/docs/testing-pathfinder-fed/, /models/verification/testing-pathfinder-fed/]
---

| | |
|---|---|
| **Component** | Gas FED ([Models › FED](/models/fed.md)) |
| **Level** | Equation, coupled, and FDS case |
| **Asset** | `assets/pathfinder_fed_stationary` (FDS deck, scenario); test `tests/verification/test_pathfinder_fed.py` |
| **Expected value from** | Pathfinder's hand calculation (moving occupant) and FDS's own `FED` device (stationary occupant) |
| **Status** | passes: moving occupant to 1 × 10⁻⁴ (equation) and 1.0 × 10⁻³ (run loop); stationary occupant within 0.1 % at the end of a 119 s run, 1.3 % at 60 s ([#208](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/208)) |

## What is tested

Pathfinder 2025-1 verifies its FED with two cases (its V&V page, Special
features, FED), for a model that has the same three-gas form as pyFDS-Evac's:
CO, the CO₂ hyperventilation factor and the O₂ term of Purser's FED (its
technical reference, FED). This page runs both cases here:

1. a **moving occupant** through three prescribed gas mixtures, and
2. a **stationary occupant** in a fire, against FDS's own `FED` device.

Both are verification: does the code evaluate the published equations on the
gas it reads? Neither says that the equations predict human tolerance.

Pathfinder states no numeric tolerance for either case ("satisfactory"; its
differences are 1.9 % and 3 %), so the tolerances below are this project's,
declared before each run.

## Moving occupant

**Pathfinder's case.** Three regions separated by thin walls hold 100 %, 75 %
and 50 % combustion products by mass, the rest air. Table 1 of its page gives
the mass fractions:

| Species | Combustion products | Air |
|---|---|---|
| CO₂ | 0.010000 | 0.000592 |
| CO | 0.001000 | 0.000000 |
| N₂ | 0.839000 | 0.763018 |
| O₂ | 0.150000 | 0.231164 |
| H₂O | 0.000000 | 0.005226 |

The occupant starts on the left at 0.25 m/s; the distance to the exit is
30 m. Hand calculation: FED = **0.07896**. Pathfinder: 0.07745 (1.9 % lower).

**Two things the page does not give, and what is assumed here.**

- *Region lengths.* They are shown only in a figure. Three equal 10 m regions
  are assumed (40 s in each); this reproduces 0.07896. This is an inference.
  It is not a published value.
- *Mass to volume.* The conversion is not stated. Ideal-gas mole fractions
  are used, with molar masses from the standard atomic weights (CO₂ 44.0095,
  CO 28.0101, N₂ 28.0134, O₂ 31.9988, H₂O 18.01528 g/mol).

**Gas in each region** (volume percent, ideal gas) and the FED rate of
pyFDS-Evac's own functions:

| Products | CO₂ % | CO % | O₂ % | CO rate (1/min) | HV<sub>CO₂</sub> | O₂ rate (1/min) | total rate (1/min) | dose in 40 s |
|---|---|---|---|---|---|---|---|---|
| 100 % | 0.6511 | 0.1023 | 13.4315 | 0.036287 | 1.17845 | 0.016622 | 0.059384 | 0.03959 |
| 75 % | 0.4984 | 0.0768 | 15.2632 | 0.026962 | 1.14471 | 0.006182 | 0.037045 | 0.02470 |
| 50 % | 0.3455 | 0.0512 | 17.0985 | 0.017732 | 1.11188 | 0.002295 | 0.022010 | 0.01467 |

The total is **0.07896** (0.078959), the hand value.

### Equation level

The test sums the three doses with `default_fed_components`. **Pass
criterion: |FED − 0.07896| ≤ 1 × 10⁻⁴.** Result: 0.078959. The test also
pins the mass-to-volume numbers above to 1 × 10⁻⁴ percent.

**The O₂ term is active in all three regions.** O₂ is 13.4, 15.3 and 17.1 %:
below the 20 % gate of pyFDS-Evac (and FDS), and below Pathfinder's 19.5 %.
The term contributes 0.0167 of the 0.0790 dose (21 %); without it the sum is
0.0622. So Pathfinder's hand value includes it, and the choice between 19.5 %
and 20 % does not matter in this case: the test runs both, with the same result
(`--o2-threshold-percent 19.5`).

**Sensitivity to the unpublished lengths.** A 1 m shift between regions
changes the result by 1.3 to 3.2 %:

| Lengths (m) | FED | Against 0.07896 |
|---|---|---|
| 10 / 10 / 10 (assumed) | 0.07896 | 0 |
| 9 / 10 / 11 | 0.07647 | −3.2 % |
| 10 / 9 / 11 | 0.07796 | −1.3 % |
| 11 / 10 / 9 | 0.08145 | +3.2 % |

Pathfinder's 0.07745 lies in this range, but the lengths cannot be recovered
from it.

### Through the run loop

One agent at 0.25 m/s walks a 30 m corridor (`corridor_scenario` of the
verification harness), spawned in a 0.4 m-wide polygon, to an exit whose near
edge is 30 m from the polygon centre. The gas field is synthetic: the three
mixtures above, in regions 10 m long from the spawn centre. The FED update
interval is 1 s.

**Predeclared tolerance.** The run loop adds `rate(x at t_k) × (t_k − t_{k−1})`
at each update, a right-endpoint rule, and the last update is before the agent
leaves. Because the rate falls from region to region, the result is below the
hand value by at most one update's dose at the highest-rate region:
1 s × 0.059384 /min / 60 = 9.9 × 10⁻⁴. **Pass criterion:**
|FED − 0.07896| ≤ 9.9 × 10⁻⁴ + 10⁻⁵, and FED ≤ 0.07896.

**Result.** 0.077970 at the last update (119 s, x = 30.96 m), 9.9 × 10⁻⁴
below the hand value, which is the bound itself: the agent's last interval
and the two region boundaries each fall just short of a whole update. The
agent walks at 0.25 m/s to within 5 × 10⁻³ m/s between updates.

## Stationary occupant

**Pathfinder's case.** An FDS fire; devices at 1.6459 m measure CO₂, CO and
O₂, and FDS computes the FED. FDS device 0.0467, Pathfinder 0.0455 (3 %),
which Pathfinder attributes to the 0.5 s PLOT3D output interval. Its FDS
files are not published.

**This repository's case.** `assets/pathfinder_fed_stationary`: a 4 × 4 × 3 m
room with 0.2 m cells, a 0.4 × 0.4 m propane burner of 200 kW (CO yield 0.2,
soot yield 0.05, 10 s ramp-up), and a 1 m wide, 1 m high opening in the +x
wall. The smoke layer stops its descent near the soffit, below the 1.7 m of
the devices. Room, burner and yields are assumptions of this deck, not
sourced values. FDS output slices (CO, CO₂, O₂ volume fraction and soot
extinction) at 1.7 m, every 0.5 s. Devices at (3.05, 3.05, 1.7) m, in the same
plane: FDS's `FED` and the three gas volume fractions. One agent stands in a
0.22 m square around the point with a pre-movement of 1000 s, so it does not
move in the 120 s run.

FDS 6.10.1 (`FDS-6.10.1-0-g12efa16-release`), one process, 62 s wall time on
macOS. Output in `fds-evac-data/pathfinder_fed_stationary/` (not in the
repository). Rerun with `fds pathfinder_fed_stationary.fds`.

**Predeclared, before the first FDS run.** pyFDS-Evac's cumulative FED
against FDS's `FED` device at the same time: relative difference ≤ 5 % at
the last update before 120 s (119 s), ≤ 10 % at 60 and 90 s; the FDS dose at
120 s at least 0.05, so the comparison is not vacuous. The gas pyFDS-Evac
reads (CO and CO₂ volume percent) against the FDS gas devices: ≤ 5 % at 60, 90
and 119 s. Why these bands: Pathfinder's own difference is 3 %, from a 0.5 s
output interval; here the slice interval is also 0.5 s and the FED update is
1 s, a right-endpoint rule that overstates a rising dose by about
*p*·Δ*t*/(2*t*) for a dose growing as *t*<sup>*p*</sup>, at most 2.5 % at 120 s
and 5 % at 60 s for *p* = 3; the slice is read at its nearest node and the
device sits in the cell around the point (0.2 m cells), with the agent up to
0.11 m from the device. A miss is a result: the bands are not changed to pass.

The first deck had 100 kW and reached an FDS dose of only 0.0446 at 120 s,
below the 0.05 minimum, so it was replaced by the 200 kW deck above before any
comparison with pyFDS-Evac. Nothing else was changed.

**Result.** FDS's device reaches 0.1055 at 120 s. pyFDS-Evac updates every
second and stands at 0.1039 at 119 s, against 0.1038 for FDS at 119 s.

| *t* (s) | FDS `FED` | pyFDS-Evac | difference | CO, slice / device | CO₂, slice / device |
|---|---|---|---|---|---|
| 20 | 0.00115 | 0.00120 | +4.5 % | 0.989 | 0.991 |
| 40 | 0.00892 | 0.00909 | +1.9 % | 0.998 | 0.998 |
| 60 | 0.02381 | 0.02411 | +1.3 % | 1.008 | 1.008 |
| 90 | 0.05827 | 0.05856 | +0.5 % | 0.994 | 0.994 |
| 119 | 0.10379 | 0.10392 | +0.1 % | 0.999 | 0.999 |

The sign and size follow the right-endpoint estimate: largest where the dose
is small and growing fastest, and the O₂ read from the slice is within 0.02
percentage points of the device throughout. **Pass.**

## Differences from Pathfinder

These are documented differences, not tests:

- **O₂ threshold.** Pathfinder's is set by the user and defaults to 19.5 %
  (OSHA). Ours is 20 % (the FDS guard; `--o2-threshold-percent 19.5` sets
  Pathfinder's). In the moving case the choice does not matter (O₂ is below
  both everywhere).
- **Sampling height.** Pathfinder samples at 0.9 × the occupant's height
  *above the occupant's location*, from PLOT3D data interpolated in space and
  time. pyFDS-Evac reads the horizontal slice nearest an absolute height
  (`--smoke-slice-height`, default 1.6 m; 1.7 m in this deck, the only
  slice), at the nearest node. The device height of Pathfinder's case is
  1.6459 m.
- **Outside the FDS mesh.** Pathfinder pauses FED accumulation; pyFDS-Evac
  reads ambient air, which gives the same result under the 20 % threshold (no
  term).
- **FED does not act on the occupant in Pathfinder**, according to its
  documentation: "these values have no impact on movement" (How-to › FED
  integration). It reports FED as an exposure measure. In pyFDS-Evac the dose
  can incapacitate an agent (`--fed-threshold`; opt out with
  `--disable-tenability`), so the agent stops where Pathfinder's keeps
  walking. Pathfinder is closed source: this is what its 2025-1 documentation
  says, not verified in code. Smoke still slows Pathfinder's occupants through
  visibility.
- **Mass to volume and region lengths** (moving case): assumptions above.

## Run it yourself

```bash
uv run pytest tests/verification/test_pathfinder_fed.py
```

The stationary test needs the FDS output and is skipped without it
(`external_data`). It reads `fds-evac-data/pathfinder_fed_stationary/`, or the
folder in `PATHFINDER_FED_DATA`. To make it, run FDS on the deck:

```bash
mkdir run && cp assets/pathfinder_fed_stationary/pathfinder_fed_stationary.fds run/
cd run && fds pathfinder_fed_stationary.fds
```

Sources: Pathfinder 2025-1, V&V › Special features › FED and Technical
reference › FED (Thunderhead Engineering); How-to › FED integration.
