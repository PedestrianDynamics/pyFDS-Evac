# 012 — Component verification suite

## Problem

pyFDS-Evac couples several independent sub-models — smoke-speed reduction,
FED toxicity, the vismap visibility gate, cognitive maps, route cost and
dynamic rerouting, and pre-movement sampling. To date these have only been
exercised together, inside the demo scenario. When a coupled run produces a
surprising egress time we cannot tell *which* term is responsible, and one
component can be wrong in a way that another silently compensates for.

This spec defines a verification suite that exercises **each mechanism in
isolation against a hand-computable reference** before any integrated run.
The distinction is deliberate: this is **verification** ("are the equations
solved correctly"), for which analytical ground truth exists, and is
separate from the behavioural **validation** of human decision-making, which
is only partially achievable on ethical grounds (drills, post-incident data,
VR) and is out of scope here.

The design directly avoids the failure mode of Cheong et al. (FEMTC 2020,
*Coupling of Evacuation and Fire Modelling Through Soot Level Analysis*),
whose headline "different evacuation dynamic" rested on a single
deterministic run of 30 agents in which the reported exit-split change
corresponded to one agent, with no replication and no sensitivity analysis.
Every stochastic element here is verified by ensemble plus fixed-seed
determinism, and every deterministic transform against a closed form.

## References

- **Börger et al. (vismap / FDSVisMap)** — path-integrated Beer-Lambert
  extinction, Lambertian cosine correction, Bresenham occlusion, required
  visibility from geometry. (`materials/waypoint_based_visibility_summary.md`)
- **Fridolf et al. (2016, 2019)** — walking speed in smoke, `v ∝ V/(V+2)`.
- **Frantzich & Nilsson (2003) / Lund** — linear `factor = 1 + βK/α`.
- **Jin (1970)** — `V = C/K`.
- **ISO 13571 / SFPE** — FED toxicity model (`pyfds_evac/core/fed.py`).

## Principle

Each test isolates one mechanism, feeds a controlled input whose output is
known in closed form, and asserts within a stated tolerance. Two tiers:

- **Tier A — pure-function verification.** The model function is fed a
  synthetic field (a numpy array) constructed so the answer is exact. No
  FDS run is involved; results are deterministic to machine precision.
- **Tier B — pipeline verification on real FDS output.** A small FDS case
  produces genuine smoke and gas fields. Ground truth is the **closed-form
  transform applied to the actually-sampled field**, asserted cell-by-cell:
  `model(field) == reference(field)`. The field need not be known a priori —
  only the transformation must match. Tier B confirms that the FDS readers,
  slice selection, and coordinate handling are correct on real data.

Tolerances: Tier A exact or `1e-9`; Tier B closed-form match to `1e-6` on
the sampled value, and spatial boundaries (e.g. a visibility threshold
contour) within one grid cell, with the discretisation error documented.

## Tier A — manufactured fields

Construct these as arrays shaped like an FDS slice `(ny, nx)` and inject
them directly into the model functions (bypassing `read_fds_data` /
`SliceFieldSampler`):

| ID | Field | Closed-form property it pins |
|----|-------|------------------------------|
| **F0** | `K = 0` everywhere | Null: every speed factor = 1, `V = max_vis`, FED = 0, all signs visible. Any deviation is a bug. |
| **F1** | `K = K₀` (uniform) | Mean-along-ray = `K₀` independent of path → decouples the LOS operator from the field. `V = c/K₀`, speed factor, route cost all exact. |
| **F2** | `K(x) = a·x` (linear ramp) | Mean of a linear field along a ray equals its **midpoint** value. The single test that proves the LOS operator is a path *mean*, not local sampling or max. |
| **F3** | `K = K_hi` in a thin band, 0 elsewhere | max-vs-mean discrimination; smoke occlusion vs geometric occlusion. |
| **F4** | two halves, `K=0` left / `K=K₀` right | Exit-choice and route-cost selection prefer the clear side. |

## Component test matrix

### 1. Smoke-speed reduction (`core/smoke_speed.py`)

- **A1.1** F1, Lund: assert `factor == 1 + β·K₀/α` exactly (α=0.706,
  β=−0.057). Choose `K₀=0.706 ⇒ factor=0.943`.
- **A1.2** F1, Fridolf: `V=c/K₀`, assert `factor == V/(V+2)` exactly.
- **A1.3** Clamp edges: `K=0 ⇒ 1.0`; large `K` ⇒ `min_speed_factor` (Lund)
  vs `→0` (Fridolf, no hard clamp) — verify the two laws differ as
  documented.
- **A1.4 (key)** F2, route cost: ray from `x=0` to `x=L`; assert sampled
  mean-K `== a·L/2`. This is the test that distinguishes the pipeline from
  the FEMTC max-soot heuristic.
- **B1.1** Real fire field: for a sample of cells, assert
  `smoke_factor(K_cell) == reference(K_cell)` to `1e-6`.

### 2. FED toxicity and tenability (`core/fed.py`)

The total FED rate is `(co + cn + nox + fld)·hv_co2 + o2` (`FedComponents.
total_rate_per_min`). The CO₂ hyperventilation multiplier `hv_co2 =
exp(0.1903·CO₂% + 2.0004)/7.1` is **≥ 1.04 even at CO₂ = 0** and cannot be
omitted from any reference value.

- **A2.1** Constant CO = 1000 ppm, CO₂ = 0, O₂ = 20.9 %, T = 30 min. CO rate
  (Eq. 13) = `2.764e-5 · 1000^1.036 ≈ 0.03543`/min; `hv_co2(0) ≈ 1.0411`;
  O₂ term = 0 (gated at 19.5 %). Closed form
  `FED = 0.03543 · 1.0411 · 30 ≈ 1.107`. Assert to `1e-3` against the exact
  expression, **not** the CO-only value.
- **A2.2** Additivity: constant CO + HCN ⇒ FED equals
  `(co_rate + cn_rate)·hv_co2·T` from the two closed forms.
- **A2.3** O₂ hypoxia gate (19.5 %): at O₂ ≥ 19.5 % the term is exactly 0
  (`_o2_hypoxia_rate_per_minute` early-return); just below, it follows
  `1/(60·exp(8.13−0.54·(20.9−O₂)))` with no blow-up. Sweep across the
  boundary and assert both branches.
- **A2.4** FIC (`default_fic`): constant irritant mix ⇒
  `FIC = Σ C_i/F_FIC,i` exactly (instantaneous, not integrated).
- **A2.5** FIC speed reduction: `v_final = v_frantzich · max(fic_min_factor,
  1 − fic_alpha·FIC)` (α=0.7, floor=0.3). Assert the closed form and the
  clamp at high FIC.
- **A2.6 (ensemble, anti-FEMTC)** Probabilistic incapacitation threshold
  `D = fed_threshold·exp(σ·Z), Z~N(0,1)`, σ=0.94: draw a large population
  and assert the median ≈ `fed_threshold` and the cumulative fraction
  incapacitated at FED = 0.3 / 1 / 3 reproduces the documented ≈ 10/50/88 %
  bands. Deterministic mode returns `fed_threshold` for every agent.
- **A2.7** Monotonicity in each toxicant; determinism under a fixed seed.
- **B2.1** Real fire field: assert accumulated FED equals the closed form
  integrated over the **sampled** CO/CO₂/O₂ trajectory along an agent path.

### 3. vismap / visibility (`core/visibility.py` + fdsvismap)

These tests target the two risks identified in review — the x/y array
orientation (masked by square geometry) and the untested `alpha` convention.

- **B3.1 (axis order — highest value)** Non-square room (G1, 8×4 m), one
  sign at a known asymmetric side-wall position, near-clear air. Compute
  the set of cells that should see it (within `max_vis`, within the
  view-angle cone, unobstructed) and compare the boolean map. A transpose
  bug fails here but not on the square demo.
- **B3.2 (required-visibility boundary)** Use a genuinely uniform field
  (G3 prescribed soot, or an injected F1 array through the real library) so
  `V=c/K₀=R` is constant — the contour is not clean on the turbulent fire
  field. Cells at distance `d<R` are visible, `d>R` not; assert the contour
  at `d=c/K₀` within ±1 cell.
- **B3.3 (alpha / view angle)** Sign facing +x. A cell directly in front is
  visible; a cell directly behind is **not**, even in clear air. Pins the
  convention documented in `visibility.py:209-213` against the library's
  `cosθ` formula (`FDSVisMap.py:335-342`). Note: current unit tests mock
  `_build_vismap`, so this path is presently uncovered.
- **B3.4 (geometric occlusion)** Insert an `OBST` wall (G4) between the
  sign and part of the floor; cells behind it are not visible regardless of
  smoke — isolates Bresenham occlusion from extinction.

### 4. Cognitive map (`core/cognitive_map.py`)

- **A4.1** `full`: `known_nodes == all graph nodes` at `t=0`.
- **A4.2** `discovery` + all-visible stub: known set at spawn = spawn +
  visible neighbours; after stepping to an adjacent node, the newly-visible
  signs are added; converges to the full reachable set.
- **A4.3** `discovery` + nothing-visible stub: known = `{spawn}` only; no
  expansion until a sign becomes visible — couples cleanly to B3.
- Use a deterministic `VisibilityModel` stub so the map logic is tested
  independently of fdsvismap.

### 5. Route graph + rerouting (`core/route_graph.py`, dynamic routing)

- **B5.1** Two-zone case (G2): smoke on the shorter path raises its cost
  above the longer clear path; assert the agent selects the long path, from
  `mean_K · length` (or the configured cost function).
- **B5.2** Reroute latency: a path is occluded at `t₁`; the agent reroutes
  at the next tick `≥ t₁`; assert latency `≤ reroute_interval`.
- **B5.3** Congestion: load one edge; cost rises; flow splits — deterministic
  given seed and placement.
- **B5.4** A rejected route appears in the route-cost CSV with its rejection
  reason (existing behaviour).

### 6. Pre-movement (`core/premovement_distributions.py`)

- **A6.1** Sample `N=1e5`: sample mean → `a·b`, variance → `a·b²` (Gamma)
  within Monte-Carlo error; KS test vs `scipy.stats.gamma`.
- **A6.2 (anti-FEMTC)** Fixed seed → bit-identical array. Determinism is the
  property a single uncontrolled run lacks.
- **A6.3** Edge cases: `n=0`, `n=1`.

## Integration ladder

Add one mechanism at a time, all others held at identity/off, so a
discrepancy localises to the term just added:

1. speed-only (F1 / G1) — egress time = `path_length / (v₀ · factor)`.
2. + FED (constant gas / G1) — egress time unchanged, FED to closed form.
3. + vismap gating (G2) — the occluded exit is rejected.
4. + cognitive map (discovery) — staff (`full`) and visitor (`discovery`)
   diverge predictably.
5. + rerouting — blocked-path latency holds.
6. Full demo scenario — every term now has a known-good reference.

## Stochastic discipline

Any RNG-driven element (pre-movement, agent placement) is reported as an
**ensemble of ≥ 30 seeds** with a confidence interval, **and** asserted
bit-identical under a fixed seed. A single-run difference is never reported
as an effect.

---

## FDS cases

The decks below are **illustrative and not yet executed** (no FDS in the
authoring session); yields and HRR are tunable to hit a target K range, and
each should be run once and the written quantities confirmed before its
slice fixture is frozen for CI.

All cases write a slice at the analysis height with the quantities the
pipeline canonicalises (`core/fds_inventory.py`): `SOOT EXTINCTION
COEFFICIENT` (vismap + speed), and `CARBON MONOXIDE / CARBON DIOXIDE /
OXYGEN VOLUME FRACTION` (FED). Analysis height matches
`VisibilityModel(slice_height_m=2.0)`; if the modelling convention moves to
the NFPA 502 B.3 head height of 2.5 m, change `PBZ` and `slice_height_m`
together.

Resolution note: the suite uses `dx = 0.10 m`. For a ~200 kW burner the
characteristic diameter `D* ≈ 0.5 m`, giving `D*/dx ≈ 5` — adequate to
**verify the coupling code** on a real smoke field, but coarse for
**validating fire dynamics**; refine to `dx = 0.05 m` near the burner if the
fire field itself is under test.

### G1 — non-square fire room (primary Tier-B case)

8 m (x) × 4 m (y) × 3 m (z), two exits on the short (x) walls, burner
off-centre so the field is asymmetric in both axes (this is what makes B3.1
able to catch a transpose). Sign for exit A on the south wall facing north.

```
Plan view (x right, y up), 8 m x 4 m:

 y=4 +----------[signB ▲180]----------+
     |                                |
 ExitA]      ⊡burner(2.25,1.25)       [ExitB     <- doorways at y=1.5..2.5
 x=0  |                                |  x=8
 y=0 +----------[signA ▲0]------------+
            sign at (4.0, 0.2/3.8)
```

```
&HEAD CHID='verif_G1', TITLE='Non-square room, single burner' /
&MESH IJK=80,40,30, XB=0.0,8.0, 0.0,4.0, 0.0,3.0 /
&TIME T_END=120.0 /
&MISC TMPA=20.0 /

&REAC FUEL='PROPANE', SOOT_YIELD=0.06, CO_YIELD=0.01 /   ! yields tune the K and CO range

! Off-centre burner ≈ 200 kW (0.5 x 0.5 m at 800 kW/m2)
&OBST XB=2.0,2.5, 1.0,1.5, 0.0,0.4, SURF_IDS='BURNER','INERT','INERT' /
&SURF ID='BURNER', HRRPUA=800.0, COLOR='RED', RAMP_Q='qramp' /
&RAMP ID='qramp', T=0.0,  F=0.0 /
&RAMP ID='qramp', T=10.0, F=1.0 /
&RAMP ID='qramp', T=120.0,F=1.0 /

! Two doorway exits: localized OPEN vents on the boundary planes.
! (The mesh perimeter is solid by default; these patches are the doorways.)
&VENT XB=0.0,0.0, 1.5,2.5, 0.0,2.0, SURF_ID='OPEN' /   ! Exit A (west, x=0)
&VENT XB=8.0,8.0, 1.5,2.5, 0.0,2.0, SURF_ID='OPEN' /   ! Exit B (east, x=8)

! Analysis slice at 2.0 m: extinction + FED species
&SLCF PBZ=2.0, QUANTITY='SOOT EXTINCTION COEFFICIENT' /
&SLCF PBZ=2.0, QUANTITY='VISIBILITY' /
&SLCF PBZ=2.0, QUANTITY='VOLUME FRACTION', SPEC_ID='CARBON MONOXIDE' /
&SLCF PBZ=2.0, QUANTITY='VOLUME FRACTION', SPEC_ID='CARBON DIOXIDE' /
&SLCF PBZ=2.0, QUANTITY='VOLUME FRACTION', SPEC_ID='OXYGEN' /

&DUMP DT_SLCF=2.0, DT_DEVC=1.0 /
&TAIL /
```

Scenario-JSON sign descriptor to pair with it (exit A sign on south wall,
facing north — `alpha` per the `visibility.py` convention):

```json
"exits": {
  "A": { "x": 0.0, "y": 2.0, "sign": { "x": 4.0, "y": 0.2, "alpha": 0, "c": 3 } },
  "B": { "x": 8.0, "y": 2.0, "sign": { "x": 4.0, "y": 3.8, "alpha": 180, "c": 3 } }
}
```

### G2 — two-zone (exit choice / rerouting)

Two 5×4 rooms joined by a 1 m doorway; fire in room A so room B and its exit
stay tenable. Drives B5.1–B5.4.

```
Plan view, 10 m x 4 m, partition at x=5 with a 1 m doorway:

 ExitA]  ⊡fire    | doorway |        [ExitB
 x=0     room A   |  y≈1.5  | room B  x=10
         (smoky)  | ..2.5   | (clear)
              partition x=5
```

```
&HEAD CHID='verif_G2', TITLE='Two-zone, fire in room A' /
&MESH IJK=100,40,30, XB=0.0,10.0, 0.0,4.0, 0.0,3.0 /
&TIME T_END=180.0 /
&REAC FUEL='PROPANE', SOOT_YIELD=0.08, CO_YIELD=0.012 /

! Partition wall at x=5 with a 1 m doorway
&OBST XB=5.0,5.1, 0.0,1.5, 0.0,3.0 /
&OBST XB=5.0,5.1, 2.5,4.0, 0.0,3.0 /

! Burner in room A (~250 kW)
&OBST XB=1.5,2.0, 1.5,2.0, 0.0,0.4, SURF_IDS='BURNER','INERT','INERT' /
&SURF ID='BURNER', HRRPUA=1000.0, COLOR='RED', RAMP_Q='qramp' /
&RAMP ID='qramp', T=0.0,F=0.0 / &RAMP ID='qramp', T=10.0,F=1.0 / &RAMP ID='qramp', T=180.0,F=1.0 /

! Exit A in room A (smoky), Exit B in room B (clear) — boundary doorways
&VENT XB=0.0,0.0,  1.5,2.5, 0.0,2.0, SURF_ID='OPEN' /   ! Exit A (west)
&VENT XB=10.0,10.0,1.5,2.5, 0.0,2.0, SURF_ID='OPEN' /   ! Exit B (east)

&SLCF PBZ=2.0, QUANTITY='SOOT EXTINCTION COEFFICIENT' /
&SLCF PBZ=2.0, QUANTITY='VOLUME FRACTION', SPEC_ID='CARBON MONOXIDE' /
&SLCF PBZ=2.0, QUANTITY='VOLUME FRACTION', SPEC_ID='CARBON DIOXIDE' /
&SLCF PBZ=2.0, QUANTITY='VOLUME FRACTION', SPEC_ID='OXYGEN' /
&DUMP DT_SLCF=2.0 /
&TAIL /
```

### G4 — geometric occlusion (B3.4)

G1 plus a free-standing partial wall between the exit-A sign and part of the
floor; cells in its shadow must read not-visible independent of smoke.

```
! add to the G1 deck:
&OBST XB=3.8,4.2, 1.0,3.0, 0.0,2.4, COLOR='GRAY' /   ! occluder in front of sign A
```

### G3 — prescribed uniform smoke (optional pure-field check)

A no-fire box with a uniform soot mass fraction set via `&INIT`, giving a
near-uniform extinction field as an extra cross-check of the reader and the
`V=c/K` path against `K = K_m · ρ_soot` (FDS default `K_m = 8700 m²/kg`).
Treat its numbers as version-dependent — the exact-analytic uniform/linear
tests live in Tier A, which does not depend on FDS internals.

```
&HEAD CHID='verif_G3', TITLE='Uniform prescribed soot, no fire' /
&MESH IJK=40,40,30, XB=0.0,4.0, 0.0,4.0, 0.0,3.0 /
&TIME T_END=10.0 /
&REAC FUEL='PROPANE', SOOT_YIELD=0.05 /          ! defines the SOOT species
&INIT XB=0.0,4.0, 0.0,4.0, 0.0,3.0, MASS_FRACTION(1)=1.0E-4, SPEC_ID(1)='SOOT' /
&SLCF PBZ=2.0, QUANTITY='SOOT EXTINCTION COEFFICIENT' /
&SLCF PBZ=2.0, QUANTITY='VISIBILITY' /
&DUMP DT_SLCF=1.0 /
&TAIL /
```

Expected order of magnitude: `ρ_air ≈ 1.2 kg/m³`, `Y_soot = 1e-4 ⇒
ρ_soot ≈ 1.2e-4 kg/m³ ⇒ K ≈ 8700·1.2e-4 ≈ 1.04 /m ⇒ V = 3/1.04 ≈ 2.9 m`.
Confirm against the value FDS actually writes before asserting on it.

## Deliverables

1. `tests/verification/fields.py` — F0–F4 array constructors.
2. `tests/verification/test_*.py` — one file per component, Tier A asserts.
3. `fds_cases/verif_G1,G2,G3,G4/` — decks above + a tiny pre-computed slice
   fixture per case so Tier B runs in CI without invoking FDS.
4. `tests/verification/test_pipeline_ladder.py` — the six-step ladder.

## Order of work

Write **B3.1 (non-square axis order)** and **A1.4 (F2 midpoint)** first:
they target the two concrete risks already identified (the transpose masked
by square geometry, and the path-mean operator that separates this work from
the FEMTC max-soot approach). The remaining Tier-A tests follow, then the
Tier-B fixtures, then the ladder.
