# l_corridor — a route-choice asset whose two routes are *differently* smoky

## Why this asset exists

`assets/t_junction` is the repository's other route-choice deck, and it cannot
discriminate between route-choice models. Its 2 MW PVC-cable fire saturates the
extinction field over the whole corridor: sampling `SOOT EXTINCTION COEFFICIENT`
at z = 2 m along both arms of the T at t = 300 s gives

| t_junction arm | median K [1/m] | Jin sighting distance S = 3/K |
|---|---|---|
| A (left, 20 m) | 11.23 | 0.27 m |
| B (right, 10 m) | 8.52 | 0.35 m |

At a sighting distance of roughly 30 cm *every* route is refused. That measures
lethality, not route choice: a model that always picks the short route and a
model that weighs smoke heavily produce the same answer, because both routes are
impassable. To tell route-choice models apart you need a fire that makes one
route bad and leaves the other one walkable.

This deck does that. It is deliberately a 1 MW propane fire with a
well-ventilated soot yield rather than a 2 MW PVC fire, so K stays in the range
where 3/K is a meaningful sighting distance on one route and still walkable on
the other.

## Geometry

A flat, single-level L (`geometry.wkt`), all corridors 3 m wide:

```
POLYGON ((0 0, 30 0, 30 3, 13 3, 13 25, 45 25, 45 28, 10 28, 10 3, 0 3, 0 0))
```

| Part | Extent |
|---|---|
| bottom corridor | x ∈ [0, 30], y ∈ [0, 3] |
| vertical leg | x ∈ [10, 13], y ∈ [3, 25] |
| top corridor | x ∈ [10, 45], y ∈ [25, 28] |
| **Exit A (near)** | OPEN vent at x = 0, on the bottom corridor |
| **Exit B (far)** | OPEN vent at x = 45, on the top corridor |
| spawn | x ∈ [13.8, 16.2], y ∈ [0.3, 2.7] — east of the junction |

Route lengths from the junction square (x ∈ [10, 13], y ∈ [0, 3]), which is the
shared prefix of both routes:

| Route | Path | Length |
|---|---|---|
| near | junction → west along the bottom corridor → exit A | ≈ 11 m |
| far | junction → north up the leg → east along the top corridor → exit B | ≈ 58 m |

Distance alone therefore always prefers the near route, by more than 5×. Only a
smoke-aware cost can flip the choice, which is the point.

## The fire

1 MW propane (`SOOT_YIELD=0.06`, `CO_YIELD=0.01`) on a 1 × 1 m burner at
**(5.0, 1.5)** — on the *near* route, between exit A and the junction. The ramp
reaches full output at 45 s and holds to the end of the 400 s run, because the
asset needs a sustained contrast window rather than a transient one.

Placement is the whole design. Reaching exit A means walking past the fire, so
the near route smokes immediately and hard. The far route leads away from the
fire, up the leg and east, and degrades only as the ceiling layer spreads over
~60 m of corridor.

## Measured contrast

```bash
.venv/bin/python assets/l_corridor/measure_contrast.py \
  "<sciebo>/fds-evac-data/l_corridor/fire_1MW_west"
```

`measure_contrast.py` samples the z = 2 m extinction slice every 0.5 m along each
route, through `pyfds_evac.core.fds_sampling` — the same path the smoke-speed
model uses, so these are the numbers the router sees. The shared junction square
is excluded from both polylines: it enters both costs identically and cannot
discriminate.

Acceptance: at least 60 s where the far route's worst K is below half the near
route's *and* the near route's sighting distance S = 3/K is under 10 m.

|  t [s] | near mean K | near p90 K | near worst K | near S=3/K | far mean K | far p90 K | far worst K | far S=3/K | far/near worst | window |
|--------|-------------|------------|--------------|------------|------------|-----------|-------------|-----------|----------------|--------|
|      0 |       0.000 |      0.000 |        0.000 |        inf |      0.000 |     0.000 |       0.000 |       inf |            inf |      - |
|     30 |       0.187 |      1.192 |        2.118 |       1.42 |      0.000 |     0.000 |       0.000 |   6606.82 |           0.00 |    YES |
|     60 |       0.340 |      1.801 |        3.517 |       0.85 |      0.011 |     0.007 |       0.236 |     12.70 |           0.07 |    YES |
|     90 |       0.648 |      1.358 |        2.293 |       1.31 |      0.148 |     0.289 |       0.454 |      6.60 |           0.20 |    YES |
|    120 |       0.666 |      1.428 |        1.514 |       1.98 |      0.303 |     0.509 |       0.634 |      4.73 |           0.42 |    YES |
|    150 |       0.631 |      0.854 |        1.422 |       2.11 |      0.342 |     0.555 |       0.641 |      4.68 |           0.45 |    YES |
|    180 |       0.803 |      1.042 |        2.956 |       1.02 |      0.372 |     0.611 |       0.875 |      3.43 |           0.30 |    YES |
|    210 |       0.701 |      1.509 |        2.579 |       1.16 |      0.402 |     0.654 |       0.786 |      3.82 |           0.30 |    YES |
|    240 |       0.730 |      1.560 |        2.275 |       1.32 |      0.424 |     0.675 |       0.724 |      4.15 |           0.32 |    YES |
|    270 |       0.591 |      1.322 |        1.401 |       2.14 |      0.444 |     0.719 |       0.910 |      3.30 |           0.65 |      - |
|    300 |       0.799 |      1.661 |        2.508 |       1.20 |      0.468 |     0.771 |       0.807 |      3.72 |           0.32 |    YES |
|    330 |       0.595 |      1.222 |        1.263 |       2.38 |      0.469 |     0.720 |       0.899 |      3.34 |           0.71 |      - |
|    360 |       0.700 |      1.113 |        1.390 |       2.16 |      0.485 |     0.749 |       0.901 |      3.33 |           0.65 |      - |
|    390 |       0.826 |      2.049 |        2.142 |       1.40 |      0.506 |     0.770 |       0.916 |      3.27 |           0.43 |    YES |

**VERDICT: contrast window 30–270 s (240 s long; the criterion asks for ≥ 60 s).**

**Do not read `near p90 K` as a percentile.** `route_stats` takes
`values[int(0.9 * n)]`, and the near route has only n = 20 samples, so index 18
of an ascending sort of 20 is the *second-largest* value. Three near-route
samples (x = 4.5, 5.0, 5.5) sit on the burner footprint, so both `near worst K`
and `near p90 K` are plume-centerline cells rather than corridor statistics. The
column is a genuine 90th percentile only on the far route (n = 113, index 101,
eleven values above it).

Because the near route's two headline columns are burner samples, the claim that
the route is *smoke-logged* rather than merely *crossed by a plume* has to be
checked away from the fire. Sampling the bottom corridor either side of the
burner, excluding it:

| t [s] | x 0.5–4.0 (exit side) median K → S | x 6.0–10.0 (junction side) median K → S |
|---|---|---|
|  60 | 0.102 → 29.5 m | 0.052 → 57.7 m |
| 120 | 0.276 → 10.9 m | 0.805 → 3.73 m |
| 180 | 0.508 → 5.91 m | 0.950 → 3.16 m |
| 240 | 0.425 → 7.06 m | 0.809 → 3.71 m |
| 300 | 0.438 → 6.84 m | 1.003 → 2.99 m |
| 390 | 0.454 → 6.61 m | 0.950 → 3.16 m |

Both halves of the near route are genuinely smoke-logged from ~120 s: an agent
walking from the junction to exit A spends the first 4 m at a sighting distance
around 3 m, passes the fire, and finishes at 6–7 m. That is the near route being
bad, not one hot cell. Meanwhile the far route settles around mean K ≈ 0.5 with
a worst case near 0.9 (S ≈ 3.3 m) — degraded but walkable, which is what makes
the choice non-trivial rather than merely fatal.

The three `-` rows after 270 s are the near route's worst K dipping during a lull
in plume puffing, not the far route catching up: the far route's mean K climbs
monotonically and slowly (0.30 → 0.51 over 120–390 s) while the near route's mean
stays roughly 1.6× higher throughout. The sustained discriminator is the gap in
mean K; the worst-case ratio is the noisier of the two.

The window is bounded above as well as below. The far route's worst-case sighting
distance drifts down toward the criterion's 3.0 m floor (3.43 → 3.27 m over
180–390 s) as the ceiling layer fills the top corridor. Extending `T_END` well
past 400 s would eventually fail the "far route still walkable" leg of the test —
the deck is sized for the 400 s run, not for an arbitrarily long one.

The window is reported as 30–270 s by the script's convention of ending a run at
the first failing sample; 240 s is the last sample verified good. Either reading
clears the 60 s requirement by a wide margin.

## `fire_1MW` — the negative control

`<sciebo>/fds-evac-data/l_corridor/fire_1MW/` is kept deliberately. It is the
same geometry with the burner at **(20, 1.5)**, east of the junction, and it
produces an **inverted** contrast — the far route is the smokier one from 90 s
onward:

|  t [s] | near worst K | near S | far worst K | far S | far/near |
|---|---|---|---|---|---|
|  60 | 0.181 | 16.5 m | 0.050 | 60.5 m | 0.27 |
|  90 | 0.259 | 11.6 m | 0.443 |  6.8 m | 1.71 |
| 120 | 0.454 |  6.6 m | 0.513 |  5.8 m | 1.13 |
| 180 | 0.351 |  8.5 m | 0.581 |  5.2 m | 1.65 |
| 300 | 0.401 |  7.5 m | 0.645 |  4.7 m | 1.61 |

The reason is geometric, not a modelling error. A fire at x = 20 is 7 m from the
vertical leg's entrance but 20 m from exit A, so the *far* route starts closer to
the fire than the near exit is, and it is a long branch in which smoke
accumulates; the near route runs west, away from the fire, and stays clear. Keep
this run as evidence that the asset's contrast depends on fire placement rather
than on the L-shape alone, and as a regression case: any change that makes
`fire_1MW` pass the acceptance criterion means the measurement has broken.

## Files

| Path | Purpose |
|---|---|
| `geometry.wkt` | walkable polygon |
| `config.json` | JuPedSim deck: spawn, both exits, junction/topcorner checkpoints, journey |
| `l_corridor.fds` | 8 corridor-hugging meshes (67k cells), both OPEN exits, burner, z = 2 m slices |
| `measure_contrast.py` | route sampling, table and verdict |

The meshes hug the three corridors rather than tiling the 45 × 28 m bounding
box: the L occupies 261 m² of 1260 m², so a bounding-box tiling spent 80% of its
cells inside solid rock. Because each mesh boundary *is* a corridor wall, no
`&OBST` is needed. Do not add the rasterised complement back — an `&OBST` that
only grazes a mesh face gets snapped to a one-cell sheet inside the mesh, which
here seals the vertical leg.

## Runs

| Directory | Fire | Result |
|---|---|---|
| `<sciebo>/fds-evac-data/l_corridor/fire_1MW_west/` | (5.0, 1.5) | **accepted**, 240 s window; 972 s wall clock on 8 MPI ranks |
| `<sciebo>/fds-evac-data/l_corridor/fire_1MW/` | (20.0, 1.5) | negative control, inverted contrast |
