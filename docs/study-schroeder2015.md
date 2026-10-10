---
title: "Route choice in smoke after Schröder et al. (2015)"
linkTitle: "Route choice in smoke (Schröder et al. 2015)"
weight: 2
---

Schröder et al. (2015) let agents in an assembly hall choose between two
doors and two exits while smoke from a fire in a neighbouring room spreads.
We build their geometry, add our own growing fire, and run pyFDS-Evac's own
smoke-aware routing on it with 200 agents and 10 seeds per case:

- **Exit and door shares.** How the default `gate` router and the
  `additive` router change them in a growing fire, against a smoke-blind
  crowd.
- **Door choice by movement start.** Why, under `gate`, the door an agent
  takes depends mainly on when it starts moving.
- **What the router sees.** It reads the smoke along the whole route at
  1.6 m, including smoke that will arrive later. Schröder's sensor reads the
  smoke present in the agent's room along straight lines at 2.8 m. This
  difference in perception scope is
  [#125](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/125).

{{< example-files-link "study-schroeder2015" >}}

{{< callout type="info" >}}
The geometry follows Schröder et al. (2015), Fig. 6 (p. 335), which is the
same case as Schröder (2017), Fig. 3.9. The paper does not publish its
fire, so the fire is ours. pyFDS-Evac implements neither Schröder's smoke
sensor (Eqs. 4–5) nor his risk tolerance; the
[routing model page](/models/routing.md#deviations-from-the-literature)
describes them. The scripts `scripts/docs/schroeder2015_route.py` and
`scripts/docs/schroeder2015_fire_figures.py` print every number and draw
every figure on this page; `scripts/docs/study_animations.py` draws the
animation. The page reports research software applied to
one scenario and gives no design or safety verdict.
{{< /callout >}}

## The result in brief

Main fire `a047_pvc_h40`, mean of 10 seeds. The no-fire and smoke-blind
arms are identical, so the smoke-blind arm is the reference:

| Arm | Exit-E share | ΔE against smoke-blind (95 % CI) | Door split |
|---|---|---|---|
| no fire = smoke-blind | 0.520 | 0 | boundary at y = 12.54 ± 0.13 m (per seed) |
| `gate` | **0.689** | +0.169 (+0.128, +0.209) | no boundary in metres; Δy > 0 in 10 of 10 seeds (post hoc sign test, p = 0.002) |
| `additive` | 0.447 | −0.074 (−0.088, −0.059) | **Δy = −0.90 m (−1.16, −0.64)**; a valid boundary in 10 of 10 seeds |

Δy is the boundary minus the clear-air boundary of the same seed. A
positive Δy moves the boundary toward door B, so more agents use door A.
A change in the E share counts if it exceeds 2 × SD of the smoke-blind
shares, 0.048.

- **Gate sends more agents through door A to exit E** than clear air does:
  E share 0.689 against 0.520, in 10 of 10 seeds.
- **(Post hoc) Gate's door choice follows mainly when an agent starts
  moving.** The door-B share is 0.04 for agents starting at 30–120 s and
  0.83 for those starting at 150–300 s. In clear air it is about 0.5 throughout.
- **The cause is a hall-wide re-path at 45 s and a wave of fallbacks
  peaking at 151–155 s.** The path search reads the smoke present at decision time,
  while the route's τ reads the smoke each point will have when the agent
  gets there. From 134–136 s every route is refused for the first agents,
  and the fallback sends most of them to door B and exit F.
- **Additive shifts the split by −0.90 m** (95 % CI −1.16, −0.64) on the
  main fire. Its shift depends on the fire: −0.90 m on the main fire,
  +0.25 m on `a047_pvc_h35` (95 % CI −0.00 to +0.50, not resolved) and
  +1.25 m on `a012_pvc_h30`.
- **Heat and the 400 s cap.** Heat entered neither routing nor
  tenability. Up to 7 late-starting agents per run were still walking at
  400 s.

## The building

![Plan of the case. A corridor, Room 2, 5 m wide runs from y = −10 to 35 m with exit E at the bottom and exit F at the top. To its right the hall, Room 1, 10.4 m wide and 24 m long, connects to the corridor through door A at y ≈ 1.6 m and door B at y ≈ 21.6 m, both marked as orange waypoints. Above the hall, Room 3 is hatched as FDS-only and holds a red 3 × 2 m burner; doors C (to the hall) and D (to the corridor) are gaps in its walls. A dotted line marks the start area of the 200 agents. Dashed black rectangles show the digitised outline of the source, within ±0.5–1 m of ours.](/images/studies/schroeder2015/geometry.png)

Tags: **[P]** published in the paper, **[D]** digitised from Schröder et
al. (2015), Figs. 2–3 and 6 (±0.5–1 m), **[A]** assumed here.

| Item | Value | Tag |
|---|---|---|
| Room 1, hall | x 0–10.5, y 0–24 m; interior x 0.2–10.6 m (10.4 m, on the 0.2 m grid) | [D] / [A] |
| Room 2, corridor | x −5–0, y −10–35 m; exits E (bottom) and F (top), 2 m wide at x −3.6 to −1.6 m | [D] / [A] |
| Room 3 | y 24–31 m; x not given in the source, taken as the hall's width | [D] / [A] |
| Doors | all 2 m wide. A at y 0.6–2.6, B at y 20.6–22.6, D at y 26.6–28.6, C at x 4.4–6.4 m; snapped to the 0.2 m grid; 2 m high in FDS | [P] width / [A] |
| Floor | 554 m² meshed in FDS; 545 m² inside the walls; 471 m² walkable | computed |

**Departures from the source.**

- Room 3 and doors C and D are not walkable and not in the stage graph.
  They stand in for Schröder's room-to-corridor sensor. In FDS, C and D are
  open.
- Doors A and B are waypoints, E and F are exits. Each exit has a 0.8 m
  deep passage, so agents enter it before they are removed
  ([#349](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/349)).
- The waypoint split is 50/50 at A and at B, because the engine needs an
  explicit split where a waypoint has two exits. Route ranking picks each
  agent's exit. In clear air nobody crosses over: only A→E and B→F occur.
- Agents start uniformly in the hall, 0.3 m from the walls. Model CFSM,
  radius 0.15 m, familiarity `full`.
- FDS 6.10.1 is used. Schröder used FDS 6.1.2.

## The fire

The paper publishes no fire: burner, heat release rate, fuel, soot yield,
grid, ceiling height and end time are all unstated. Our fire was set from
design-fire practice before any routing run. One of nine variants was then
chosen against a smoke target, also before any routing run.

| Item | Main fire `a047_pvc_h40` | `a047_pvc_h35` | `a012_pvc_h30` | Source |
|---|---|---|---|---|
| Growth | t², α = 0.047 kW/s² (fast) | same | α = 0.012 kW/s² (medium) | SFPE Handbook, 6th ed., Ch. 3, Table 3.5 |
| Cap | 1.5 MW: HRRPUA 250 kW/m² on a 3 × 2 m burner centred in Room 3 (x 4–7, y 26.6–28.6 m) | same | same | HRRPUA after DIN EN 1991-1-2/NA, via Schröder (2017), p. 74; cap [A] |
| Cap reached at | 178.6 s | 178.6 s | 353.6 s | computed (`TAU_Q`) |
| Fuel | PVC: soot yield 0.172, CO yield 0.063 kg/kg, ΔH<sub>c</sub> 16,400 kJ/kg | same | same | FDS User's Guide PVC example, on which Schröder (2017), Table 4.5, p. 75, is based |
| Ceiling | 4.0 m | 3.5 m | 3.0 m | [A]; the paper extracts smoke up to 3.0 m (Table 2, p. 334), so its ceiling is above 3 m |
| Grid, time | 0.2 m (dz 0.1944 m at 3.5 m), 480 s, slices every 1 s | same | same | [A] |

Smoke is written at 1.6 m (routing, walking speed and gas dose), and at
2.0 and 2.8 m for comparison. With the 3.5 m ceiling FDS places these at
1.56, 1.94 and 2.72 m; pyFDS-Evac takes the nearest slice and logs the
height mismatch. Runtime with 6 MPI processes: 90 min (`a047_pvc_h40`),
99 min (`a047_pvc_h35`), 61 min (`a012_pvc_h30`).

### How the main fire was chosen

![Six plan views of soot extinction K. Top row, the 2.8 m slice at 165 s for the three fires, with the five scoring regions drawn. Main fire a047_pvc_h40: Room 3 and the upper corridor black, the lower hall grey (0.7 to 2.3 per metre), the upper hall mostly light (below 0.7), and the corridor toward E grey. a047_pvc_h35: almost everything black. a012_pvc_h30: the upper hall darker than the lower hall, the lower corridor clear. Bottom row, the 1.6 m slice at 145 s: the hall is clear except a grey band along the end wall at door A in the two fast fires and a dark patch at door C; Room 3 is black.](/images/studies/schroeder2015/fire_field.png)

1. **The target was fixed first.** It is our reading of the paper's
   Fig. 6c (p. 335, the 2.8 m extraction at 165 s, printed without a colour
   scale): Room 3 and the upper corridor opaque (K ≥ 2.3 1/m), the lower
   corridor clear (K ≤ 0.23), the lower hall at K 0.7–1.4, the upper hall
   clear (K ≤ 0.23 [A]).
2. **Nine runs on the 0.2 m grid**: α ∈ {0.012, 0.047} × {PVC, PUR} ×
   ceiling ∈ {3.0, 4.0} m, plus the central case `a047_pvc_h35`. Each is
   scored by S, the mean over five regions of the share of nodes that meet
   the target.
3. **No automatic pick was plausible.** The best score, 0.60 for
   `a012_pvc_h30`, equals that of a field with smoke only in Room 3. No
   variant beats that null field. `a012_pvc_h30` also reverses the hall
   pattern: median K 2.0 1/m in the upper hall against 0.99 in the lower.
4. **Smoke enters the hall through door C** and piles up at the far, door-A
   end (details below). Whether the 2.8 m slice shows the lower hall darker
   depends on how far below the ceiling it sits.
5. **The maintainer chose `a047_pvc_h40` by visual match to Fig. 6c.** It is
   the only variant with the lower hall darker than the upper (median K 1.5
   against 0.51 1/m) and an opaque upper corridor (87 % of nodes). It
   differs from Fig. 6c in four ways: the corridor toward E is smokier
   (median K 0.94 against ≤ 0.23); the lower hall is patchier and darker;
   some smoke sits at the top of the hall near C; and its score is 0.48
   against the best 0.60.

The comparison fires are `a012_pvc_h30` (best score, reversed hall
pattern) and `a047_pvc_h35` (the central design fire, smoke almost
everywhere). The fire was chosen against the smoke target only; no route
outcome was known.

{{< details title="The scores of all nine variants" closed="true" >}}

![Nine plan views of K on the 2.8 m slice at 165 s, one per variant, each with the five scoring regions and the region scores in its title. Fast PVC fires with 3.0 and 3.5 m ceilings are black almost everywhere. a047_pvc_h40, highlighted, shows the lower hall grey and the upper hall light. Slow fires leave the lower corridor clear; a012_pvc_h30 has the upper hall darker than the lower. The PUR fires with a 4.0 m ceiling are light almost everywhere.](/images/studies/schroeder2015/p0b_sweep.png)

| Variant | S (165 s) | S (160–170 s) | Room 3 | Upper corridor | Lower corridor | Lower hall | Upper hall | Median K: upper corridor / lower corridor / lower hall / upper hall |
|---|---|---|---|---|---|---|---|---|
| a047_pvc_h30 | 0.40 | 0.40 | 1.00 | 1.00 | 0.00 | 0.00 | 0.00 | 8.4 / 4.2 / 4.9 / 6.7 |
| a047_pvc_h35 | 0.40 | 0.40 | 1.00 | 0.98 | 0.00 | 0.00 | 0.00 | 4.7 / 1.6 / 2.8 / 2.4 |
| **a047_pvc_h40** | **0.48** | 0.46 | 1.00 | 0.87 | 0.08 | 0.40 | 0.08 | 3.5 / 0.94 / 1.5 / 0.51 |
| a047_pur_h30 | 0.41 | 0.38 | 1.00 | 0.59 | 0.00 | 0.49 | 0.00 | 2.4 / 1.3 / 1.4 / 1.9 |
| a047_pur_h40 | 0.40 | 0.41 | 1.00 | 0.02 | 0.30 | 0.09 | 0.62 | 0.97 / 0.28 / 0.44 / 0.2 |
| a012_pvc_h30 | 0.60 | 0.62 | 1.00 | 0.43 | 1.00 | 0.59 | 0.00 | 2.3 / 0 / 0.99 / 2 |
| a012_pvc_h40 | 0.55 | 0.55 | 1.00 | 0.02 | 1.00 | 0.00 | 0.73 | 0.4 / 0 / 0.0066 / 0.14 |
| a012_pur_h30 | 0.24 | 0.23 | 0.19 | 0.00 | 1.00 | 0.00 | 0.00 | 0.64 / 0 / 0.26 / 0.55 |
| a012_pur_h40 | 0.39 | 0.39 | 0.00 | 0.00 | 1.00 | 0.00 | 0.95 | 0.087 / 0 / 0.0012 / 0.04 |

Region columns are the share of nodes meeting the target; K is in 1/m.
Regions are inset by one cell; the corridor beside the hall is not scored.
PUR: soot yield 0.056, CO yield 0.122 kg/kg, ΔH<sub>c</sub> 18,770 kJ/kg
(Schröder 2017, Table 4.4 and p. 74). The score uses one LES frame; the
thresholds are a reading of a greyscale image.

{{< /details >}}

{{< details title="Where the smoke enters the hall (post hoc)" closed="true" >}}

![Six panels. (a) to (c): maps of the first time K exceeds 0.23 per metre on the 2.8 m slice for three variants; the smoke front starts at door C at the top of the hall and moves toward y = 0. (d) Layer depth at 165 s along the hall: for the fast PVC fires about 1.1 to 1.3 m near C and mid-hall and 2.7 to 3.3 m at the door-A end. (e) K along the hall axis at 2.8 m against the two hall targets. (f) Time smoke reaches the hall side of doors A and B against the corridor side; most points lie above the diagonal, so the hall side is reached first.](/images/studies/schroeder2015/p0b_hall_diag.png)

The decks have no velocity output and no device in door C, so the flow
direction is inferred from the order in which the device trees first exceed
K = 0.23 1/m. No flux is measured.

- **Entry through door C.** On the 2.8 m slice the front starts at C and
  moves toward y = 0.
- **Doors A and B are outlets.** The hall side of door A is reached 7–20 s
  before the corridor side in 9 of 9 variants; door B shows the same order
  in 8 of 9.
- **Pile-up at the A end.** For the fast PVC fires at 165 s the layer is
  1.1–1.3 m deep from C to mid-hall and 2.7–3.3 m deep at the A end.
- So the upper/lower pattern at 2.8 m depends on the slice depth below the
  ceiling (H − 2.8 m) against the depth of the jet near C. With a 4.0 m
  ceiling and α = 0.047 the slice lies just below the jet near C and inside
  the pile-up at the A end.

{{< /details >}}

## The crowd and the routers

- **200 agents** in the hall [P], placed uniformly at t = 0 [A].
- **Walking speed** v₀ ~ N(1.0, 0.2) m/s [P], clipped by the engine to
  0.1–5.0 m/s.
- **Pre-movement** with mean 120 s and SD 60 s [P]: Weibull, scale
  135.49 s, shape 2.101. The source uses N(120, 60) s, which pyFDS-Evac
  does not offer.
- **Four arms, seeds 1–10 each:** no fire; smoke-blind (`--smoke-blind`);
  `gate`; `additive` with `w_smoke` 1.0, the engine default. The cost model
  is set explicitly in each scenario; at the time a misspelt name selected
  the additive model
  ([#305](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/305)).
- **Routing settings:** `anticipate: true`, `foresight_horizon_s` at its
  default (no limit), `base_speed_m_per_s` 1.0. Routes are re-evaluated
  every 1 s, also during pre-movement.
- **Smoke height** 1.6 m for routing, speed and gas dose. Schröder's
  example extracts at 2.8 m.
- **Tenability:** gas FED on, heat FED off (both engine defaults).
- **Horizon:** 400 s against the FDS end of 480 s.

The [routing model](/models/routing.md) and
[the gate in detail](/docs/route-cost-gate.md) explain each setting.

{{< details title="Which pre-movement distribution" closed="true" >}}

pyFDS-Evac offers gamma, lognormal, Weibull, uniform and constant
pre-movement (`pyfds_evac/core/premovement_distributions.py`). N(120, 60) s
puts 2.3 % of agents below 0 s, so the reference is N(120, 60) truncated at
0. Each family is matched to mean 120 s and SD 60 s:

| Family (engine parameters a, b) | KS distance | W1 [s] | 99th percentile [s] | P(t > 300 s) |
|---|---|---|---|---|
| **Weibull 135.49, 2.101** | **0.056** | **6.1** | 280 | 0.005 |
| gamma 4, 30 | 0.079 | 9.1 | 301 | 0.010 |
| uniform 16.1, 223.9 | 0.076 | 9.4 | 222 | 0.000 |
| lognormal 4.676, 0.472 | 0.105 | 12.6 | 322 | 0.015 |
| reference, N(120, 60) truncated at 0 | | | 260 | 0.001 |

Set both `premovement_param_a` and `premovement_param_b`. With only one
set, the engine silently uses its preset.

{{< /details >}}

## Results

### Exit shares and flows

![Four panels of cumulative agents against time on the main fire, mean of 10 seeds with a min–max band. Door A: gate rises fastest and ends at 145, smoke-blind 104, additive 96. Door B: gate stays at about 6 until 160 s, then rises to 55; smoke-blind 96, additive 104. Exit E: gate 137, smoke-blind 104, additive 88. Exit F: gate stays at about 6 until 170 s, then rises to 61; smoke-blind 96, additive 109.](/images/studies/schroeder2015/p1_counts.png)

| Fire | Arm | E share | ΔE against smoke-blind (95 % CI) | Doors A / B | Routes AE / AF / BE / BF |
|---|---|---|---|---|---|
| a047_pvc_h40 | smoke-blind | 0.520 | 0 | 104 / 96 | 104.0 / 0.0 / 0.0 / 96.0 |
| a047_pvc_h40 | gate | 0.689 | +0.169 (+0.128, +0.209) | 145 / 55 | 137.4 / 7.6 / 0.2 / 54.6 |
| a047_pvc_h40 | additive | 0.447 | −0.074 (−0.088, −0.059) | 96 / 104 | 89.2 / 7.0 / 0.0 / 103.6 |
| a047_pvc_h35 | gate | 0.777 | +0.257 (+0.235, +0.279) | 155 / 45 | 155.1 / 0.0 / 0.2 / 44.4 |
| a047_pvc_h35 | additive | 0.532 | +0.012 (+0.002, +0.021) | 106 / 94 | 106.2 / 0.0 / 0.0 / 93.5 |
| a012_pvc_h30 | gate | 0.918 | +0.398 (+0.373, +0.423) | 183 / 17 | 183.2 / 0.0 / 0.3 / 16.4 |
| a012_pvc_h30 | additive | 0.574 | +0.054 (+0.044, +0.064) | 115 / 85 | 114.7 / 0.0 / 0.0 / 85.2 |

Mean of 10 seeds. The smoke-blind arm is the same on every fire.

### Door choice follows movement start (gate)

![Post hoc measure. Six panels against movement start in 30 s bins, mean and 95 % CI over 10 seeds. Top row, share via door B; bottom row, share via exit E; one column per fire. Dotted lines mark the gate medians over 10 seeds of three events: F re-paths via door A, the first pass with every route refused (labelled "all refused"), and E re-paths via door B. Main fire: under gate, the door-B share is about 0.4 for starts before 30 s, below 0.1 for starts at 30–150 s, and 0.75 to 0.9 for starts at 150–300 s; markers at 45, 135 and 158 s. In clear air it stays near 0.5. Additive follows clear air until about 150 s and then rises to 0.6 to 0.9. a047_pvc_h35 looks much the same, with markers at 44, 128 and 172 s. a012_pvc_h30: gate sends almost nobody through B for starts at 60–210 s and everyone to E; for later starts the door-B share rises to 0.35–0.6; markers at 57, 173 and 225 s.](/images/studies/schroeder2015/p1_door_by_start.png)

This measure was added after the first results were seen (post hoc). Under
`gate`, an agent's door is predicted better by when it starts moving
than by where it starts: area under the ROC curve 0.86 against 0.66, and
McFadden R² 0.30 against 0.05 (0.38 for both together). Position still
matters a little. Under `additive`, start position stays the better predictor (AUC 0.96).

{{< details title="Door predictors for all fires" closed="true" >}}

| Fire | Arm | AUC start y | AUC start time | R² start y | R² start time | R² both |
|---|---|---|---|---|---|---|
| a047_pvc_h40 | no fire | 1.00 | 0.50 | 0.99 | 0.00 | 0.99 |
| a047_pvc_h40 | gate | 0.66 | 0.86 | 0.05 | 0.30 | 0.38 |
| a047_pvc_h40 | additive | 0.96 | 0.58 | 0.64 | 0.02 | 0.71 |
| a047_pvc_h35 | gate | 0.78 | 0.77 | 0.17 | 0.17 | 0.38 |
| a047_pvc_h35 | additive | 0.98 | 0.54 | 0.73 | 0.01 | 0.76 |
| a012_pvc_h30 | gate | 0.81 | 0.45 | 0.17 | 0.00 | 0.18 |
| a012_pvc_h30 | additive | 0.99 | 0.44 | 0.79 | 0.00 | 0.82 |

Logistic models of door B, seeds pooled. An AUC below 0.5 means later
starters use door B less.

{{< /details >}}

### Smoke-blind and gate, animated

![Animation of the main fire, seed 3, at 16 times real time, smoke-blind on the left and gate on the right. Both show the corridor with exits E at the bottom and F at the top, the hall with doors A and B on its left wall, and Room 3 with the red burner above the hall. Grey smoke fills Room 3, spreads into the upper corridor, and from about 145 s lies at the door-A end of the hall; by 398 s the whole plan is dark grey. Open black rings are agents still waiting; filled dots walk. On the left, agents from the lower hall walk to door A and exit E, those from the upper hall to door B and exit F. On the right, after 45 s almost every agent that starts walking goes to door A, also from the upper hall; at 148 s door A counts 86 against 60 on the left. From about 149 s the later starters go to door B instead, and on to F through the smoky upper corridor, where their dots grow and turn orange and red. A text box at the lower right of the gate panel lists the events at 45, 135, 152 and 164 s as they happen. At the end the left panel shows door A 105, door B 95, and the right door A 147, door B 53, with nobody inside](/images/studies/schroeder2015/agents_smoke_gate.gif)

*Main fire `a047_pvc_h40`, seed 3, 0–398 s at 16 times real time. Left
smoke-blind, right `gate`; both arms have the same agents, start positions
and start times. Seed 3 has 147 agents through door A under `gate`, the
median of the 10 seeds. Background: K at 1.6 m, the slice that routing,
walking speed and gas dose use. Open rings: agents in pre-movement. Dots:
walking agents, coloured and sized by their speed factor. Regenerated by
`scripts/docs/study_animations.py`.*

What to watch for:

- **45–145 s.** Under `gate` almost every agent that starts walking heads for
  door A, also from the upper hall. Smoke-blind splits the hall at about
  y = 12.5 m. By 146 s, 83 agents have passed door A under `gate` against
  57 for smoke-blind.
- **From 134 s.** The first agents find every route refused, as smoke at
  1.6 m reaches the door-A end of the hall. Under `gate`, 10 agents pass
  door B before 145 s (the last at 70.6 s) and 43 from 149.1 s on. Those
  43 all go to F through the smoky upper corridor, where their dots grow
  and turn red.
- **The end.** Smoke-blind's last agent leaves at 303.4 s, gate's at
  362.9 s. In this seed nobody is inside at 400 s in either arm.

The route figure below shows the 2.8 m slice for comparison with the
paper. The animation shows 1.6 m, the slice that routing and walking
speed use.

### Why: a hall-wide re-path and a fallback wave

Five facts of the `gate` code explain the pattern
(`pyfds_evac/core/route_graph.py`):

- The path search weights each edge by `k_avg·L + 1e-6·L`
  (`GatePolicy.edge_weight`), so length only breaks ties: any trace of
  smoke on the shorter path sends the search onto a smoke-free path of any
  length.
- The search starts where the agent stands
  ([#451](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/451)):
  the walk to each door is the first leg, charged the smoke on that walk.
  The smoke in the hall is nearly uniform at these times, so almost every
  hall agent gets the same door for a given exit: from 50 to 144 s, 97–99 %
  of the hall agents' first-ranked routes are A→E, in every seed.
- The search uses the smoke present at decision time
  (`_generate_candidates`). The τ of each candidate is read point by point
  at the time the agent would reach that point, counted from where the
  agent stands (`_measure_route`,
  [#650](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/650)); see
  [the routing model](/models/routing.md#how-smoke-enters-route-choice).
- Routes are ranked by τ first (`GatePolicy.order_key`). An exit switch
  needs the rival's τ to be lower by more than 6 × 0.1 = 0.6 (`_tau_band`).
  A route is refused above τ = 6 for the current exit and 4.8 for a rival
  exit (`RouteCostConfig`). τ = 6 comes from the original
  [FDS+Evac](https://github.com/firemodels/fds/tree/c9da70d7a/Source).
- **Two refused routes:** the lower τ decides, with a 20 % margin; a switch
  straight back is blocked for 10 s
  ([#458](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/458)).

The 45 s re-path happens at the same second in all 10 seeds; the later
events vary by a few seconds between seeds:

| Time | Event |
|---|---|
| **45 s** | Exit F re-paths via door A. Trace smoke on hall→B→F (router τ 0.08) makes the smoke-free path via A win, at 45.1 m against 24.5 m. E via A (23.5 m) is now more than 10 % shorter in time than F via A, so agents bound for F switch to E (`_clears_exit_anchor`): 819 exit changes at 45 s over 10 seeds, and 28 more at 74–80 s, all logged `shorter_path` ([#92](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/92)). No route was refused. |
| 45–134 s | Almost every hall agent heads for A→E. 0.2 B→E agents per seed pass door B, at 71–87 s. Between 72 and 150 s, 6.1 exit changes per seed are logged `smoke_reroute`. |
| **134–136 s** | Every route is refused for the first hall agents: A→E's τ, read at the time they would reach each point, passes 6 as smoke piles up at the door-A end. The fallback keeps the current route until a rival's τ is more than 20 % lower. |
| **from 150 s** | Fallback wave: 307 of the 666 fallback switches over 10 seeds fall in 151–155 s. A→E→B→F 284, B→E→B→F 185, A→E→A→F 141, A→F→A→E 50, B→F→A→E 5, B→E→A→F 1; in all 666 the new route has the lower τ. |
| **156–164 s** | Exit E re-paths via door B, but B→E is already refused (router τ 22–31, median per pass, at 158–163 s), so almost nobody turns from A to B→E. Same-exit re-paths (`better_path`) number 8.3 per seed, at 136–168 s. |

Per seed, 30–47 exit changes return to an exit the agent had left earlier,
none within 2 s of leaving it. Between two refused routes the 20 % margin and
the 10 s return lockout apply. A fallback switch X→Y is followed by a switch
Y→X of the same agent 56 times in 10 seeds (median 34 s later). Route smoke
is read once per grid cell since [#653](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/653) (0.5.0), and the returns
remain with it.

![Three panels of route optical depth τ as the router computed it, gate arm, agents in the hall, 10 seeds, median and interquartile range per 5 s, on a log scale with lines at τ = 6 and 4.8. Main fire: B→F rises to about 0.1–0.3 at 30–45 s and disappears, replaced by A→F at about 0.7, which rises to about 2 by 110 s; a few agents rank B→E (below 0.05, 90–125 s) from where they stand. A→E stays near 0 until about 130 s, then rises steeply and crosses 6 at about 140 s. B→E, ranked by the few agents near door B, rises with it and crosses 6 just before A→E. When the hall re-paths E via door B at 156–164 s, B→E is already above τ 20. Afterwards every route lies above 6 and rises to about 100–250 by 300 s. The comparison fires show the same steps at other times: on a012_pvc_h30 A→E stays at 0 until about 145 s and passes 6 near 185 s.](/images/studies/schroeder2015/p1_tau.png)

τ is read point by point at the time the agent would reach each point. A
route appears only while the path search offers it for its exit to at
least one agent.

**The pre-registered mechanism was refuted; its direction held.** Before
the runs we predicted that B→E would carry more τ than A→E and so move the
boundary toward door B. The boundary did move toward B, and from 130 s B→E
does carry more τ than A→E (τ figure), but that comparison does not move
the agents: almost nobody takes B→E (0.2 per seed). The shift toward door A
comes from the 45 s re-path of exit F, and the later door-B users reach F
by the fallback.

{{< details title="Reroutes per seed, main fire" closed="true" >}}

| Arm | Switches | Agents | By reason |
|---|---|---|---|
| gate | 165.8 | 118.2 | 84.8 `shorter_path`, 66.6 `fallback`, 8.3 `better_path` (same exit, new path), 6.1 `smoke_reroute` |
| additive | 53.3 | 36.3 | 42.6 `smoke_reroute`, 10.7 `shorter_path` |

Mean per seed. Since 0.5.0 each exit change is labelled by its cause
([#92](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/92)).

{{< /details >}}

### The additive boundary

![Two panels. (a) Share via door B against start y on the main fire, 2 m bins: in clear air a step from 0 to 1 at y = 12.56 m; additive a smooth curve crossing 0.5 at 11.62 m; gate dots between 0.06 and 0.47 with no fit. (b) Boundary shift per seed with mean and 95 % CI for smoke-blind (all zero) and additive: −0.90 m on the main fire, +0.25 m on a047_pvc_h35 with a CI that reaches zero, +1.25 m on a012_pvc_h30. A note says gate is not drawn, with Δy > 0 in 10/10 seeds on each fire.](/images/studies/schroeder2015/p1_boundary.png)

Under `gate`, door B is not a monotone function of start y, so a boundary
fitted in metres is not meaningful: its CI lies inside the hall in none of
the 10 seeds on the main fire. Gate is therefore reported by its E share, its
sign count and the door share by start. Under `additive` every seed has a
valid boundary; the shift is −0.90 m (−1.16, −0.64) on the main fire.
Additive charges length in both path and exit ranking and keeps the
spatial split.

### The comparison fires

| Fire | Gate ΔE | Gate sign count | Gate re-path times | Additive Δy (95 % CI) | Additive ΔE |
|---|---|---|---|---|---|
| a047_pvc_h40 (main) | +0.169 | Δy > 0 in 10 of 10; valid boundary in 0 | 45 / 156–164 s; every route refused from 134–136 s | −0.90 m (−1.16, −0.64); 10 of 10 negative | −0.074 |
| a047_pvc_h35 | +0.257 | 10 of 10; valid in 4 | 44 / 156–199 s; every route refused from 127–129 s | +0.25 m (−0.00, +0.50); 9 of 10 positive | +0.012, below 0.048 |
| a012_pvc_h30 | +0.398 | 10 of 10; valid in 0 | F via A 57 s; every route refused from 172–176 s; E via B 221–276 s | +1.25 m (+0.90, +1.59); 10 of 10 positive | +0.054 |

- `a047_pvc_h35` repeats the main-fire order of events: F via A at 44 s,
  every route refused from 127–129 s, E via B at 156–199 s.
- `a012_pvc_h30` reaches the gate's sign by another route. Most agents
  take A→E (E share 0.918). Of its 16.7 door-B users per seed, 55 %
  started before the 57 s re-path; the fallback, from 172–176 s, sends
  later starters to door B before E re-paths via B at 221–276 s. Start
  time does not predict door B (AUC 0.45).
- `h35` and `h40` differ only in ceiling height. The evidence is two growth
  rates and three smoke fields, not three independent fires.
- Additive's shift depends on the fire and is not resolved on
  `a047_pvc_h35`. Its mechanism was not analysed.

{{< details title="Routes of one seed, main fire" closed="true" >}}

![Three plan views of seed 1 on the main fire, trajectories coloured by door and exit, over the 2.8 m smoke slice at 165 s in grey. Smoke-blind: everyone below about y = 12.5 m walks to A and E, everyone above to B and F (AE 114, BF 86). Gate: most agents, including many from the upper hall, walk to A and E; a later group walks to B and F (AE 139, AF 9, BF 52). Additive: the split lies lower in the hall (AE 103, AF 6, BF 91).](/images/studies/schroeder2015/p1_routes_a047_pvc_h40.png)

The background is the 2.8 m slice at 165 s, for display only. Routing used
the 1.6 m slice.

{{< /details >}}

## How far to trust the numbers

- **Pre-registration.** The criteria were fixed before the boundary and
  E-share statistics were computed. This is stated, but cannot be checked.
  The E-share threshold (0.048) was set after the seed-1 exit counts were
  seen (114, 137 and 99 via E for smoke-blind, gate and additive, in the first runs), and
  those counts already gave its sign. The sign test, the door share by
  start, the predictor table and the boundary validity count are post hoc.
- **Clear air.** The no-fire arm reproduces the earlier clear-air runs
  exactly, and smoke-blind runs are identical to no fire on all three
  fires. Start positions are the same in every arm, so the comparisons are
  paired by seed. The deck's radius is 0.15 m, so [#408](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/408) (stage reach from
  the agent's own radius, 0.5.0) could have moved these arms; it did not. The clear-air boundary, 12.54 m per seed (12.56 m
  pooled), lies −0.05 m from the shortest-path boundary at 12.60 m. Before
  the fix of [#350](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/350)
  and [#401](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/401)
  the difference was +1.50 m. The clear-air slope comes from perfectly
  separated data and is not an estimate.
- **Still walking at 400 s.** No run raised the FDS horizon error
  ([#356](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/356)),
  but the 400 s cap leaves some agents walking:

  | Fire | gate, per run (total in 10 runs) | additive |
  |---|---|---|
  | a047_pvc_h40 | 0–3 (21) | 0–4 (22) |
  | a047_pvc_h35 | 0–7 (37) | 0–7 (36) |
  | a012_pvc_h30 | 0–1 (3) | 0–1 (2) |

  They are late starters (median movement start 286 s; 115 of 121 at 250 s
  or later) walking at a speed factor of 0.10. None is stalled: each
  walked at least 0.47 m in the last 30 s.
- **Gas.** The largest gas FED of any agent in any run is 0.069; nobody is
  incapacitated by gas.
- **Heat.** Heat FED was off in all 90 fire-arm runs, so heat entered
  neither routing nor tenability, and "nobody incapacitated" covers gas
  only. A post hoc estimate samples the FDS temperature at 1.6 m at the
  agents' positions every 1 s. On the main fire, agents meet up to 168 °C,
  and 25 (gate) and 23 (additive) per run on average go above 60 °C. The convective dose peaks
  at 0.042 clothed and 0.12 unclothed, with the constants of
  `pyfds_evac/core/fed.py`. The unclothed law is Purser and McAllister
  (2026), Eq. 70.42, p. 2318; it is somewhat unconservative at higher
  temperatures, so the unclothed dose at 168 °C may be underestimated. The
  clothed constants have not been checked against ISO 13571. Radiant heat
  was not assessed.
- **One LES realisation per fire**, on the 0.2 m grid only.

## What this does not show

- The study uses the geometry of Schröder et al. (2015) with our own fire,
  crowd and router. Their results are neither reproduced, calibrated nor
  validated.
- The sensor settings behind the paper's route patterns (Fig. 6d,
  extraction height, grid, time step and f<sub>risk</sub>) are unpublished,
  so its route choice cannot be set against ours. The counts of its Fig. 7
  are one sensitivity sample.
- pyFDS-Evac has neither Schröder's sensor (Eq. 4), his edge factor
  (Eq. 5), f<sub>risk</sub>, nor his obstruction test
  ([routing model](/models/routing.md#deviations-from-the-literature)).
- The router reads the smoke along the whole route at 1.6 m, including
  smoke that will arrive later. Agents could not see that smoke
  ([#125](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/125)).
- The gate's τ = 6 comes from FDS+Evac. Schröder's factor 2 and
  f<sub>risk</sub> are chosen, not fitted (p. 332). The page ranks neither
  rule above the other.
- The door-choice pattern is a property of the model: a lexicographic τ
  rule with present-time path search from each agent's position. No occupant
  behaviour was observed.
- The gate split has no boundary in metres. It is reported by its E share,
  its sign count and the door share by start.
- The predicted direction held; the pre-registered mechanism did not.

## Reproduce

{{< example-files "study-schroeder2015" >}}

The inputs are in `assets/schroeder2015_route/`. Run every command from
the repository root, or from the unpacked zip with `python` instead of
`uv run python`. `DATA` is a folder outside the repository.

1. **FDS**, 6 MPI processes per deck:

   ```bash
   for F in a047_pvc_h40 a047_pvc_h35 a012_pvc_h30; do
     mkdir -p "$DATA/$F" && cp assets/schroeder2015_route/$F/$F.fds "$DATA/$F/"
     (cd "$DATA/$F" && mpiexec -n 6 fds $F.fds)
   done
   ```

2. **Evacuation**, four arms on the main fire and three on each comparison
   fire, seeds 1–10. One seed of each arm on the main fire:

   ```bash
   C=assets/schroeder2015_route/evac
   uv run python run.py --scenario $C/config_gate.json --seed 1                                    # no fire
   uv run python run.py --scenario $C/config_gate.json --seed 1 --fds-dir "$DATA/a047_pvc_h40" --smoke-blind
   uv run python run.py --scenario $C/config_gate.json --seed 1 --fds-dir "$DATA/a047_pvc_h40"     # gate
   uv run python run.py --scenario $C/config_additive.json --seed 1 --fds-dir "$DATA/a047_pvc_h40" # additive
   ```

   `assets/schroeder2015_route/run_p1.sh` runs every seed and adds
   `--output-route-history`, `--output-exit-history`,
   `--output-fed-history` and `--output-route-cost-history`. A run with
   agents still walking at the 400 s cap is incomplete, and `run.py` exits
   with status 2 ([Exit status](usage.md#exit-status)); the script counts
   such a run as done. It exits non-zero if any run fails. For all seeds at once:

   ```bash
   PY="uv run python" bash assets/schroeder2015_route/run_p1.sh \
       "$DATA/a047_pvc_h40" "$DATA/p1_a047_pvc_h40" 6 --with-nofire
   PY="uv run python" bash assets/schroeder2015_route/run_p1.sh \
       "$DATA/a047_pvc_h35" "$DATA/p1_a047_pvc_h35" 6
   PY="uv run python" bash assets/schroeder2015_route/run_p1.sh \
       "$DATA/a012_pvc_h30" "$DATA/p1_a012_pvc_h30" 6
   ```

   Each run takes about 25–40 s.

3. **Numbers and figures:**

   ```bash
   uv run python scripts/docs/schroeder2015_route.py --data "$DATA"
   ```

   It prints every evacuation number on this page as Markdown tables,
   then this summary, then writes the figures:

   ```text
   main fire, exit-E share: no fire 0.520, gate 0.689, additive 0.447
   main fire, additive dy: -0.90 m (-1.16, -0.64)
   main fire, gate door-B share: 0.04 for starts 30-120 s, 0.83 for starts 150-300 s
   ```

4. **Animation** of smoke-blind and gate, about 1 min. It needs
   `ffmpeg` for the colour reduction; without it the GIF is larger:

   ```bash
   uv run python scripts/docs/study_animations.py schroeder2015 --data "$DATA"
   ```

   It prints the seed and the numbers of the caption, then writes the GIF:

   ```text
   - gate door-A counts {1: 148, 2: 137, 3: 147, 4: 154, 5: 143, 6: 145, 7: 150, 8: 131, 9: 147, 10: 148}; seed 3 (147, median 147)
   wrote site/static/images/studies/schroeder2015/agents_smoke_gate.gif (2.1 MB, 200 frames)
   ```

5. **Fire choice**, optional: it needs all nine fires. Write the decks with
   `uv run python assets/schroeder2015_route/make_decks.py "$DATA"`, run
   each with FDS as in step 1 (about 6 h for the six further decks), then
   `uv run python scripts/docs/schroeder2015_fire_figures.py --data "$DATA"`.

**Provenance.** The evacuation runs on this page were made on main at
`c619a046` by steps 2–4 above (seeds 1–10, Python 3.13.4), run by hand from
a clean checkout; each run's manifest records the commit with
`git_dirty: false` and `agent_seeding: spawn-key-blake2b-v2`. The no-fire
and smoke-blind arms give the same numbers as the earlier runs of
`9c820e0f`, `2a94a8da` and `828ae8c3`. The FDS
runs used `FDS-6.10.1-0-g12efa16-release`.

## Limits and open issues

**The scenario and the fire.**

- One 0.2 m grid; a 0.1 m check waits until the case is frozen.
- One LES realisation per fire; the fire choice scores one frame.
- The fire is ours, and its differences from Fig. 6c are listed above. Two
  one-factor tests are deferred, possibly to a later run on JURECA: door C
  closed, and a 4.6 m ceiling.
- Heat FED was off; radiant heat was not assessed
  ([#81](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/81)).
- Up to 7 agents per run are still walking at 400 s.

**Engine behaviour seen here.**

- The path search uses present-time smoke
  ([routing model](/models/routing.md#how-smoke-enters-route-choice)).
- One path per exit
  ([#185](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/185)).
- Perception scope
  ([#125](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/125)).
- Anticipation horizon
  ([#356](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/356)).

**Open design questions.**

1. Present-time path search against anticipated τ: the τ of a route is
   read at the agent's arrival time at each point
   ([#650](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/650)),
   the path search at decision time.
2. The 1e-6·L length floor lets the path search react to τ of order 1e-4;
   [the gate page](/docs/route-cost-gate.md) discusses the floor.

**Not done yet.** A dose-aware or perceived-smoke arm for the late B→F
route through the opaque upper corridor.

The paper's unpublished inputs (its fire deck, the settings behind Fig. 6d,
later code versions of the factor 2) are not used. The study uses published
sources only.

## Sources

{{< details title="Sources" closed="true" >}}

- Schröder, B., Haensel, D., Chraibi, M., Arnold, L., Seyfried, A., &
  Andresen, E. (2015). Knowledge- and perception-based route choice
  modelling in case of fire. *Proceedings of the 6th International
  Symposium on Human Behaviour in Fire*, Cambridge, UK, 28–30 September
  2015, pp. 327–338. Interscience Communications. ISBN
  978-0-9933933-0-3.
  [juser.fz-juelich.de/record/255940](https://juser.fz-juelich.de/record/255940).
  Room 3 and the fire in it p. 329; the 2.80 m extraction height p. 330;
  Eq. 4 p. 331; Eq. 5, the factor 2 and f<sub>risk</sub> p. 332; Table 2
  p. 334; Fig. 6 p. 335; doors 2 m wide and the hall's smoke "lower as well
  as more homogenous and delayed" than the corridor toward F p. 336.
- Schröder, B. (2017). *Multivariate methods for life safety analysis in
  case of fire*. Dissertation, Bergische Universität Wuppertal (2016).
  Schriften des Forschungszentrums Jülich, IAS Series 34. ISBN
  978-3-95806-254-2.
  [urn:nbn:de:0001-2017081810](https://nbn-resolving.org/urn:nbn:de:0001-2017081810).
  Fire in Room 3 p. 55; Fig. 3.9 p. 57; HRRPUA p. 74; Table 4.4 p. 74;
  Table 4.5 p. 75.
- Fleischmann, C., & Wade, C. (2026). Fire scenarios. *SFPE Handbook of
  Fire Protection Engineering*, 6th ed., Ch. 3, Table 3.5.
  [doi:10.1007/978-3-031-59212-6_3](https://doi.org/10.1007/978-3-031-59212-6_3)
- DIN EN 1991-1-2/NA, for the HRRPUA of 250 kW/m², through Schröder (2017),
  p. 74. Paraphrased.
- McGrattan, K. et al. *Fire Dynamics Simulator User's Guide*, sixth
  edition, NIST SP 1019, section "Fuels not compatible with simple
  chemistry" (PVC example).
- Purser, D. A., & McAllister, J. L. (2026). Assessment of hazards to
  occupants from smoke, toxic gases, and heat. *SFPE Handbook of Fire
  Protection Engineering*, 6th ed., Ch. 70, Eq. 70.42, p. 2318 (the
  running text refers to it as Eq. 70.38).
  [doi:10.1007/978-3-031-59212-6_70](https://doi.org/10.1007/978-3-031-59212-6_70)
- The original [FDS+Evac](https://github.com/firemodels/fds/tree/c9da70d7a/Source),
  for τ = 6.
- Code: `pyfds_evac/core/route_graph.py` (`GatePolicy.edge_weight`,
  `GatePolicy.order_key`, `_tau_band`, `_generate_candidates`,
  `_measure_route`, `_clears_exit_anchor`, `_decide_exit_change`,
  `RouteCostConfig`), `pyfds_evac/core/premovement_distributions.py`,
  `pyfds_evac/core/fed.py`.

{{< /details >}}

## What next

- [Routing model](/models/routing.md): how pyFDS-Evac prices routes in
  smoke.
- [The gate in detail](/docs/route-cost-gate.md).
- [Wayfinding](/models/wayfinding.md): what agents know and see.
- [ASET-RSET maps after Schröder et al. (2020)](study-schroeder2020.md).
- [Design fires](/fundamentals/design-fires.md).
- Perception scope:
  [#125](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/125).

pyFDS-Evac is research software, provided without warranty.
