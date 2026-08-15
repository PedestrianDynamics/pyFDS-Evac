# Gate-model review: consolidated findings

Five independent reviews of `feat/smoke-gate-routing` @ `ba586d3`
(architect, correctness, scientist, writer, scenario tester).

**Sections A-E are the reviews as delivered, at that commit.** Read them for the
argument, not for the current code: several findings have since been fixed, and
[section F](#f-status-after-the-rework) carries the dispositions. For what the
shipped model does now, read [route-cost-gate.md](route-cost-gate.md).

---

## Verdict

**The gate does almost no work in real fires, and the least-K fallback is the
model that actually runs.** Measured on `assets/t_junction` + `fire_2MW_PVC`:
239 of 33 008 route evaluations feasible (0.7 %), **zero feasible after ~60 s**;
26 of 27 exit switches decided by the fallback, 1 by the gate. `sign_contrast_c=8`
barely moves it (490/33 044), so this is not a calibration artefact of `c = 3`.
In world100 the fallback share rises from 16 % to 88 % as the hall fills.

With `c = 3` and `fraction = 0.5`, a 20 m walk needs `K <= 0.3 /m`. Both real
fires exceed that within ~60 s. Everything downstream — banding, hysteresis,
monotone death — is then governed by a rule (`sort by k_max`) that no plan
section designed and no reference code uses.

---

## A0. Discriminating experiment: aggregation is NOT the cause

Hypothesis: the saturation is an artefact of using worst-case `k_max` over a
whole bending polyline instead of FDS+Evac's `K_ave` along one sight line.
Recomputed offline from the tester's own route-cost CSVs (no rerun):

| criterion | t_junction feasible | world100 feasible |
|---|---|---|
| shipped (`c/k_max` vs `0.5*L`) | 239 / 33 008 = **0.72 %** | 951 / 13 572 = **7.0 %** |
| faithful (`K_ave * L < 2c = 6`) | **1.04 %** | **8.7 %** |

**Hypothesis refuted.** The aggregation barely moves it, because t_junction is
optically opaque: median route `k_ave = 10.7 /m`, i.e. Jin sight **0.28 m**;
agent-experienced K reaches 12-14 /m and `speed_factor` sits on its 0.1 floor
from t = 120 s. Every Jin-based criterion — ours, `K_ave`, per-leg, or
FDS+Evac's own absolute 0.03 /m — says impassable. The saturation is physics.

**Consequences.**
1. `t_junction` + `fire_2MW_PVC` is **not a routing benchmark**. It is a
   lethality scenario: ~35/150 evacuate under *both* models, and the agents are
   blind and crawling. It cannot discriminate route-choice models and should not
   be used to validate one.
2. `world100` + `fire_4p5MW` **is** the valid test bed, and there the gate does
   real work: 56 % feasible in 0-30 s, 28 % in 30-60 s, and the 0-40 s cohort
   legitimately refuses the near E2 because E2 lies toward the fire at (2, 11).
3. Honest scope claim: **the gate discriminates while the space is partially
   tenable; the fallback governs once it is not.** That makes the fallback's
   quality a deliverable, not a safety net — so B2 is the highest-priority
   defect, ahead of B1.

## A. Design-level, needs a decision

**A1. The gate re-introduces the length penalty the plan set out to remove.**
`needed = 0.5 * effective_length` (`route_graph.py:1101`) paired with route-wide
`k_max` (`:1050`): a 60 m clean detour needs `K <= 0.1 /m` *everywhere*, a 25 m
route tolerates 0.24 /m. Long routes are held to a strictly harder standard —
the exact pathology the plan's opening diagnoses. *(scientist, architect,
correctness — all three independently.)*

**A2. Provenance is inverted.** In `materials/evac.f90` the door gate is an
**absolute** threshold, `K_ave < ABS(FED_DOOR_CRIT)` = 0.03 /m (`:1459`,
`:5260`), minimising time. The `0.5*d` rule is FDS+Evac's **tier-4 last resort**
(`:16455`), reached only when no smoke-free door exists — and it uses `K_ave`
along the **straight, occlusion-blocked bee line** (`See_door`, `:15343`), which
makes `S > 0.5*d` equivalent to optical depth tau < 6 along a real sight line.
Our `k_max` over a polyline that bends round corners has no such reading.
The comment at `:1095` is wrong; so is the commit message.

**A3. Plan step 1 was never implemented.** `visibility.py` and `run_config.py`
are untouched. fdsvismap's LOS integration was replaced by home-rolled
`c / k_max` after the concealment-masking finding — a substitution I did not
flag as a plan deviation at the time. Items A1, A2 and B5 all follow from it.

**A4. The 10 m band.** Numbers verified (C/VM2: 0.130 /m reflective, 0.347 /m
illuminated, both at V = 10 m). But 10 m is the *tenability limit* the ODs are
derived from, not the reverse; and it supports **one break at 10 m**, not a
uniform lattice. Bands are also unbounded above: K=1e-4 -> band 3000,
K=2e-4 -> band 1500, and `-band` outranks travel time, so an agent detours
arbitrarily far to avoid negligible smoke.

**A5. Anticipation with `foresight_horizon_s = inf`** gives the agent perfect
foresight of the FDS solution, and samples past the end of the data (the sampler
clamps to the last frame, `fds_sampling.py:64-83`). FDS+Evac's
`FED_max_Door * dist / Speed` is a different object: extrapolation from
*presently observable* conditions. Defensible as an upper bound; not FDS+Evac's
model, and not what the code comments claim.

---

## B. Bugs — unambiguous, fix regardless of the design decision

**B1. Monotonicity is violated.** `_apply_exit_death:1523` sorts `ranked`, not
`alive`, so the all-dead fallback can re-select an exit already in `dead_exits`.
Counterexample (tester, `c=8`): agent 12 goes A->B at t=23 s (A killed
`sight 8.8 m < 10.9 m`), then **B->A at t=24 s**.

**B2. Which exit an agent kills forever is decided by 1 Hz sampling noise.**
`rank_routes:1265` un-rejects the least-`k_max` route with a `fallback:` prefix;
`_apply_exit_death:1516` skips exactly that prefix — so each tick the *other*
exit dies permanently. Agent 41's fallback head alternates A/B second by second
(t=81 B, 82 A, 83 A, 86 B). Measured consequence: of 13 agents locked onto B,
**0 evacuated**; of 14 locked onto A, 2 did.

**B3. `dead_exits` cancels the gate's self-healing property.** `effective_length`
is *remaining* distance, so `needed` shrinks as the agent approaches — the same
haze that refuses an exit at 40 m accepts it at 2 m. That is the design.
Permanent death destroys it (`/tmp/proof2.py`): at t=1 the agent stands 1 m from
a door the model has just declared passable (`feasible=True`) and walks 60 m the
other way for the rest of the run.

**B4. Total death permanently swaps the objective.** Once every exit is dead,
ordering is `(k_max, travel_time)` forever — `dead_exits` never clears. After the
smoke fully clears, every route is `feasible=True` at max band and the agent is
still in the fallback branch, reason `every exit dead (None)` (`/tmp/proof6.py`).

**B5. `k_max` ignores `first_share` (`:1046`).** Every other aggregate is
share-weighted so smoke already walked isn't charged twice; `k_max` alone is not.
`/tmp/proof5.py`: agent past a wall of smoke with 20 m of clear air ahead —
`k_ave = 0.004` (correct) but `k_max = 1.0`, route refused. Systematic: only the
*current* route has a first leg partly behind the agent, so this penalises the
committed route and never its rivals — inverting `exit_switch_anchor`'s intent.

**B6. The anchor vetoes the whole band ordering.** `evaluate_and_reroute:1723`
decides switches on `best.composite_cost >= old_cost * exit_switch_anchor` — the
**additive** composite. `/tmp/proof4.py`: gate ranks the clear 25 m exit first,
anchor refuses, agent stays in the haze. Same defect at `:1706` for same-exit
paths. Clearer-but-longer is the *normal* gate case, so the headline feature may
never fire. Four sites needed a gate branch; one was written.

**B7. Dijkstra still routes additively (`:1164-1188`).** `w_smoke`/`w_fed` still
choose *which path* reaches each exit, at `time_s`, without anticipation. If an
exit has a short smoke-wall path and a longer clear one, Dijkstra returns the
wall, the gate refuses it, and `_apply_exit_death` permanently retires an exit
that had a passable path. (Tester: `w_smoke` is nonetheless *measured-neutral*
on t_junction — gate w_smoke=0 reproduced gate w_smoke=5 exactly.)

**B8. `feasible` conflates gate failure with every other rejection (`:1098`).**
An exit rejected for `"all segments non-visible"` — which `_must_flee_rejection`
deliberately treats as *not* a hazard — dies permanently. And FED rejection uses
the asymmetric deadband, so **whether an exit dies forever depends on whether it
was current that tick**: order-dependent irreversible state. A transient FED puff
kills an exit at the *stricter* rival threshold (`/tmp/proof3.py`).

**B9. A stalled tick.** `rank_routes` guarantees one un-rejected route;
`_apply_exit_death` filters that guarantee away, so `alive` can be non-empty and
entirely rejected. `evaluate_and_reroute:1652` then returns `None` — the agent
doesn't reroute and keeps walking toward a possibly-dead exit.

**B11. Clear-air equivalence — the property the plan says everything rests on —
is broken, in two independent ways.** (a) Bands are unbounded above: K=1e-4 gives
band 3000, K=2e-4 gives 1500, and `-band` outranks travel time, so two physically
clear routes are ordered by negligible smoke and an agent detours arbitrarily far.
Real FDS fields have faint nonzero K everywhere. (b) `gate` ranks on the *clamped*
`exposure_length` (`:955`) while `additive` uses unclamped `effective_length`
(`:1055`); they diverge by `max(0, remaining - first_length)` whenever a
candidate's first hop is behind the agent, so equivalence is exact only from the
spawn node. The scenario runs that appeared to confirm it used K = 0 exactly and
could not have failed; a unit test with `ConstantExtinctionField(0.0)` would have
the same defect. Any real check must use K = 1e-4.

**B10. Double-gating.** `visibility_extinction_threshold` (`:1223`) and
`impassable_extinction_threshold` (`:1305`) still apply under `gate`, contrary
to plan section 3.

---

## C. Verified clean (narrows the work)

- **Cache**: no stale read. 2- and 3-tuple keys are disjoint, `walked` accumulates
  from `path[0]` so keys are position-independent, dict resets per pass
  (`scenario.py:2054`). Costs: false type annotations in three signatures,
  Phase-1 writes are dead under anticipation, near-zero hit rate.
- **Infinities**: no `inf` arithmetic, no NaN path reachable.
- **`fallback_switch_margin` direction**: correct — but *usually unreachable*,
  because `rank_routes` un-rejects first, leaving `alive` non-empty.
- (**Clear air is NOT clean — moved to B11 below.** The scenario check ran with
  no `--fds-dir`, so K is exactly 0 and the check cannot fail.)
- **`c = 3`**: correct, confirmed independently by `evac.f90:5262` and Jin 1978.
  Note the duplicate constant: `smoke_speed.py:95` `visibility_factor_c = 3.0`.

---

## D. Scenario numbers

### t_junction (150 agents, 300 s)

| run | evac | exits (evacuated) | switches | B->A | A->B | reasons |
|---|---|---|---|---|---|---|
| additive s42 | 36 | A 15 / B 21 | 28 | 14 (t 3-76) | 14 (t 5-69) | 28 smoke_reroute |
| additive s1 | 35 | A 15 / B 20 | 26 | 13 | 13 | 26 smoke_reroute |
| **gate s42** | 30 | **A 30 / B 0** | 27 | 14 (t 2-255) | **13 (t 81-225)** | 1 smoke, **26 fallback** |
| **gate s1** | 32 | A 31 / B 1 | 27 | 14 | 13 | 1 smoke, 26 fallback |
| gate w_smoke=0 | 30 | A 30 / B 0 | 27 | 14 | 13 | identical to w_smoke=5 |
| gate c=8 | 30 | A 28 / B 2 | 31 | 15 | 16 | 4 smoke, 27 fallback |

**Prediction refuted.** No monotone B->A migration: 13 of 27 switches are A->B at
t = 81-225 s. Additive reproduces the reference baseline (35 switches / 35 out).
The number that separates the models is the exit split, not the churn.

### world100 four-exit, east spawn (E2 21.6 m, E3 28.2 m, E4 34.6 m, E1 52.5 m)

| cohort | additive | gate |
|---|---|---|
| 0-40 | E2 9, E3 11 | E3 14, E4 6 |
| 40-80 | E3 17, E2 1, E4 2 | E4 18, E3 2 |
| 80-120 | E2 20 | E4 20 |
| 120-160 | E2 20 | E4 20 |
| 160-200 | E2 20 | E4 16, E2 4 |
| 200-240 | E2 19 | E4 17, E2 2 |
| **totals** | **E2 89, E3 28, E4 2** | **E4 97, E3 16, E2 6** |
| RSET last / median | 253.6 / 136.8 s | 269.7 / 147.6 s |

Two regimes: **0-40 s** the gate is genuinely unsaturated (rank-1 fallback
55/336) and the band ordering legitimately refuses the near E2, which lies toward
the fire at (2, 11). **>=80 s** all four exits are refused and E4's dominance is
the least-K fallback, not the gate.

---

## E. Testing and documentation debt

- `tests/test_route_gate.py` **does not exist**; `test_rerouting_smoke_sweep.py:5`
  points at it. The new default ships with zero coverage. 215 routing tests pass
  *because* the suite cannot see the new default.
- A clear-air test using `ConstantExtinctionField(0.0)` **would pass while the
  invariant is false** — it must use K = 1e-4 to be a real check.
- **`"additive"` alone does not restore old behaviour**: `anticipate` is
  independent of `cost_model` and defaults true. Migration needs
  `{"cost_model": "additive", "anticipate": false}` — so the two test files I
  "pinned" are not actually pinned.
- **Clear-air equivalence has a fourth hole**: `gate` ranks on the *clamped*
  `exposure_length` (`:955`), `additive` on unclamped `effective_length`
  (`:1055`); they diverge by `max(0, remaining - first_length)` whenever a
  candidate's first hop is behind the agent. Exact only from the spawn node —
  and `station_fahy`'s 52-53 % front-door share is the exposed calibration.
- **No deck pins `cost_model`**: `assets/t_junction` and `assets/fed_incap_co_*`
  silently switched models on this commit.
- Stalest docs: `docs/routing.md:112-165`, `docs/model-comparison.md:136-162`,
  `docs/rerouting-oscillation-notes.md:144-173`,
  `docs/routing-and-signs-notes.md:51-99`, `README.md:351-355,506-513`.
  Paper: `eq:composite` referenced at ~16 sites incl. the parameter table
  `main.tex:1230-1257`.
- Config: `cost_model` is an unvalidated free string — a typo silently yields
  additive in all three places at once.
- Diagnostics: `k_max_route`, `min_visibility_m`, `band`, `feasible` are not
  written to the route-cost CSV; there is no `dead_exits` trace at all. The gate
  model is currently undiagnosable from its own output.
- Operational: `--vis-cache` is a **no-op for `familiarity: full`/`1.0` decks`**;
  dropping it turned a 10+ min world100 precompute into a ~5 min run.

---

# F. Status after the rework

Monotone death was dropped and the gate kept self-healing (`e441b03`), then the
fallback was banded and the anchor bypass narrowed (`f6eede0`), then the band
left the ordering and sight moved from the route's worst sample to its mean
(`cea33ce`).

| finding | status |
|---|---|
| B3 permanent death cancels self-healing | **fixed** -- `dead_exits` and `_apply_exit_death` removed; refusal is never remembered |
| B4 total death permanently swaps the objective | **fixed** with B3 |
| B1 monotonicity violated in the all-dead branch | **moot** -- there is no death to be monotone about |
| B2 which exit dies is decided by 1 Hz noise | **moot** with B3 |
| B9 stalled tick | **fixed** (`ca49e45`) |
| B5 `k_max` ignores `first_share` | **fixed** -- the first segment is resampled from the agent's position, outside the shared cache |
| B6 anchor vetoes the band ordering | **fixed** -- one `rank_cost` read by ordering, anchor and the same-exit test; a band-clearer *feasible* rival bypasses the anchor |
| A2 provenance comment inverted | **fixed** (`ca49e45`) |
| annotations, test pins, red test on main | **fixed** (`ca49e45`) |
| A3 fdsvismap LOS never wired in | **reversed** (`b16e900`) -- the LOS reading is wired in and reported, but it no longer gates. It is defined only where a sign resolves, so selecting it per exit let sign geometry decide which exits were tested: on `l_corridor` the far exit lies around two corners, was never sight-tested, and the diversion vanished (84/16 became 100/0); on `world100` one exit was tested 43 times and fell back 2095. Every exit is now gated on `c / K_ave` over its own polyline |
| A1/A2 gate penalises long routes; aggregation unfaithful | **partly addressed** -- since `cea33ce` the criterion averages K, so worst-case K no longer refuses anything (it survives only in the fallback switch margin), and with the mean the test is exactly an optical depth `K_ave * L <= 2c` -- the same form `See_door` computes. What remains is the distance: it compares against the whole bending route, so it holds long routes to a stricter standard. The rejection reason always names `sight (path)` |
| A2 absolute 0.03 /m criterion absent | **available, off** (`2ee36d4`, `45e146f`) -- shipped as `clean_extinction_threshold`, defaulting to 0. Measured on `l_corridor` over five seeds it moved the far-exit share not at all (15-22 with, 15-17 without) while median RSET rose 17 % and monotonicity went from 0 returns to 34-38 agents per run. Note also that FDS+Evac's tier 1 is a hard filter, whereas ours falls through to time when empty |
| B7 Dijkstra still routes additively | **open** |
| B8 `feasible` conflates gate failure with every rejection | **open**, but no longer irreversible |
| B11 clear-air equivalence at small nonzero K | **addressed** (`cea33ce`) -- bands saturate at 3 classes and no longer order feasible routes, so the term that diverged at small nonzero K is out of the sort. Not re-measured at K = 1e-4; the K = 0 result stands (world100 7712 rows, t_junction 4030 rows) |
| A4 uniform band lattice | **moot for ordering** (`cea33ce`) -- the lattice still exists but only orders the all-refused fallback |
| A? sight read from the route's worst sample | **fixed** (`cea33ce`) -- `min_visibility_m` is now `c / k_ave`. `k_max_route` is reported and drives the fallback switch margin only |
| B10 double-gating on the extinction thresholds | **open** -- still three smoke gates under the gate model |
| E: gate diagnostics missing from the CSV | **fixed** (`cea33ce`) -- `rank_cost`, `k_max_route`, `min_visibility_m`, `band`, `feasible` are written |
| monotonicity (returns to abandoned exits) | **open** -- 182 returns across 26 agents became 38 across 12 on world100. The requirement is zero |
| E: `tests/test_route_gate.py` missing | **fixed** -- the file exists and covers the gate |
| E: stale docs | **fixed** -- the model reference is now [route-cost-gate.md](route-cost-gate.md); `routing.md`, `model-comparison.md`, `routing-and-signs-notes.md`, `rerouting-oscillation-notes.md` and `usage.md` were brought in line with it. The paper is not done. |

## Removing the band: the prediction and the measurement

The review predicted that taking the visibility band out of the ordering would
collapse `l_corridor`'s far-exit share toward 0/100 — that the band, not the
sight gate, was producing the diversion the deck was built to show.

**Measured, the split held at 84/16 against additive's 100/0**, produced by the
sight gate itself. The prediction is refuted; record it as a prediction, not as
a property of the model. The re-run is not in
`<sciebo>/fds-evac-data/l_corridor/evac/`, whose CSVs are the `b3babc0` run;
the measurement is reported in `cea33ce`'s commit message.

What the band removal did fix is churn: 223 switches and 182 returns to
abandoned exits across 26 agents on world100 became 59 and 38 across 12. The
requirement is zero, so this stays open.

## Still open after `cea33ce`

- **B7** `w_smoke` and `w_fed` weight the Phase-1 Dijkstra edge costs under the
  gate, so two objectives are stacked: smoke prices the path, then gates the
  exit.
- **B10** `visibility_extinction_threshold` (0.5 /m) and
  `impassable_extinction_threshold` (3.0 /m) both still fire under the gate.
  With the sight criterion that is three smoke gates, not one.
- **A5** anticipation advances the clock at the unimpeded `base_speed_m_per_s`
  while a smoke-slowed agent walks at as little as 0.1x it, so the field is
  sampled systematically too early — and furthest ahead where the smoke is
  thickest. `foresight_horizon_s = inf` is perfect foresight of the FDS
  solution.
- **Uncalibrated hysteresis, now five constants:** `exit_switch_anchor` (0.9),
  `fallback_switch_margin` (0.2), `fed_return_margin` (0.9),
  `sight_return_margin` (1.25), `_PATH_IMPROVEMENT_THRESHOLD` (10 %).
- **Monotonicity:** 38 returns across 12 agents on world100.
- **The dose veto never fires on the fires we have.** `fed_max_route` peaks at
  0.0016 on `l_corridor`'s `fire_1MW_west` (counted over 3498 route-cost rows)
  against a threshold of 1.0. On these decks the gate is wayfinding, not hazard
  avoidance.

## Fallback tie-break: nearest, not farthest

The original brainstorm specified "the smallest k wins; the same k, the farthest
wins". The first half is implemented (banded -- see B-list above); the second is
**not**, deliberately, and the user confirmed nearest on 2026-08-14.

Farthest-wins is what produced the measured inversion: agent 99 sent to a 51 m
exit over a 22 m one on 2.0 m of sight against 1.8 m. Once ties are banded rather
than exact, they are common rather than measure-zero, so the tie-break decides
real cases and "farthest" systematically sends agents the long way round inside
a band. A deliberate move-away-from-the-fire rule would be a different
mechanism -- distance from the fire, not route length -- and is not implemented.

## What t_junction is for now

Not routing. Its 2 MW PVC fire drives route K to 10.7 /m and refuses everything.
Keep it as a lethality / speed-collapse case and use `assets/l_corridor` (near
exit smokes first, long way round stays clean) for route-choice questions.

## Reading the sight line from fdsvismap

`VisMap._get_visibility_array` computes `wp.c / mean_extco_array`, i.e. Jin's
relation with `K_ave` averaged along the obstruction-aware sight line. That is
the same quantity FDS+Evac's `See_door` returns, which is what makes
`S > 0.5 * d` a statement about optical depth (`tau < 2c`) rather than a
worst-case sample compared against a whole bending route.

Three properties had to be handled:

* **the 30 m cap** -- applied inside the array build, so `set_visibility_bounds`
  is called *before* `compute_all`, raised to the domain diagonal. This is what
  made the first attempt at using fdsvismap unusable: a 68 m route compared
  against a number that can never exceed 30 m fails wherever it stands.
* **masked zeros** -- the returned value is the sight line multiplied by the
  sign's readable half-plane and by obstructions, so `0.0` means "concealed",
  "standing behind the sign" or "smoked out", indistinguishably. Only the last
  is a passability statement, so `visibility_to_node` returns `None` instead and
  the caller falls back to the polyline criterion. A hidden sign is not a wall.
* **the eye position** -- the sight query needs a point to look from, but
  `agent_position` also re-measures every route from that point. They are
  separate parameters (`los_position`) because passing the spawn node as
  `agent_position` silently re-ranked routes whose edges carry waypoints, and
  broke a reroute-latency check.

**Owed upstream:** `_vis_metre_array` mirrors the mask product from the public
`get_visibility_to_wp` in order to vectorise it. fdsvismap should expose
`get_visibility_array(waypoint_id, time)` and the pin be updated; until then
that function is the one place duplicating library internals.

## Correction: the clean-exit tier was measured with the wrong hysteresis

`clean_exit_margin` had two defaults -- `0.1` on the dataclass and `0.8` in
`from_routing_params` -- and every deck-driven run took the second. So the
eight-seed refutation recorded in `45e146f` ran with a hysteresis band of
`0.03/0.8 - 0.03` = **0.0075 /m** rather than the intended
`0.03/0.1 - 0.03` = **0.27 /m**, a factor of 36. The commit message argues the
tier fails because that band is narrower than the median per-tick drift in a
leg mean (0.0072 /m). At the intended margin the band is twice the *p90* drift,
so that explanation was an artefact of the bug and not a property of the design.

Re-measured on l_corridor with the defaults reconciled, three seeds:

| seed | tier on (near/far) | off | switches on/off | violations on/off |
|---|---|---|---|---|
| 1 | 84/16 | 84/16 | 42 / 4 | 7 agents / 0 |
| 2 | 84/16 | 85/15 | 56 / 5 | 19 agents / 0 |
| 3 | 88/12 | 88/12 | 48 / 8 | 10 agents / 0 |

**The conclusion survives, the numbers and the mechanism do not.** The far-exit
share is unchanged by the tier at either margin, so it still does not redirect
anyone -- the prediction of 25-40 is refuted at the intended setting too. But
monotonicity costs 3-8 agents per run, not the 34-38 quoted, and the cause is
not simply a band narrower than the noise. Tier membership is binary, so a
crossing swaps which objective is in force rather than reordering a list, and a
wider deadband delays that without removing it.

The tier stays off by default. Anyone re-opening the question should start from
these numbers, not from `45e146f`'s.

## Ruling: the gate is an exposure criterion, not a visibility one

The shipped test is `c / K_ave_route >= 0.5 * L_remaining`, i.e.

    tau = K_ave * L <= 2c = 6

an **optical depth along the walked route**. That is a real physical quantity --
`tau = integral K ds = kappa_m * integral rho_s ds` is the soot column the agent
passes through, proportional to inhaled dose up to the nearly constant speed
factor. It is computable for every exit and independent of sign placement, which
is why it replaced the line-of-sight form.

It is **not** a sighting distance. Jin's `S = c/K` is contrast attenuation along
a straight, unobstructed line between a sign and its background. Integrate K
along a route that turns ninety degrees twice and the result is not a sighting
distance of anything -- you cannot see around a corner. `See_door` shares the
form `tau <= 2c` only because its path is a bee line and its `d` a bee-line
distance; on a straight corridor the two coincide, on l_corridor's far route
they do not.

Three consequences.

1. **The names are false.** `min_visibility_m`, `_sighting_distance`,
   `sight_distance_fraction`, `sign_contrast_c`, and the reason string
   `sight (path) X m < Y m` all assert visibility, and none of it measures
   visibility. They should become route optical depth `tau` and a budget
   `tau_max`. **Done at `0d9bf79`.**
2. **The FDS+Evac provenance is weakened, not gone.** *(Corrected after
   re-reading `evac.f90`.)* The **threshold** is citable: FDS+Evac's tier-4 test
   computes `L2_tmp = d * 0.5 / (3.0 / K_ave_Door)` and strikes the door out at
   `L2_tmp >= 1.0` (`:16458`, `:16463`), which is exactly `K_ave * d > 6`. What does
   not carry over is the **quantity** — `K_ave_Door` is a mean along `See_door`'s
   straight sight line, with an L1 distance for doors with no resolved sight line
   (`:16460`) — nor the **scope**: the test sits in a last-resort branch,
   loops only over known-or-visible doors, and strikes doors out permanently
   (`:16464-16465`). So the paper may say the gate is *inspired by* FDS+Evac's
   tier-4 visibility door rule and inherits its threshold with a citation; it may
   not say it implements it, and 6 is still uncalibrated as an exposure budget.

   The same re-read supplies provenance for the hysteresis added at `9f55f6e`:
   `FAC_DOOR_OLD2 = 0.9` (`:1507`) discounts the current door's `L2_tmp` at
   `:16290` and `:16467`, and at `:16467` that `L2_tmp` **is** `tau/6`. So
   `current_exit_discount = 0.9` discounts the same quantity in the same place.
   The shipped code comment instead cites `FAC_DOOR_WAIT` at `evac.f90:1503`;
   `FAC_DOOR_WAIT` is at `:1505` and discounts travel time, not smoke.
3. **A1 is retired rather than open.** Scaling the threshold with route length
   was a defect for a visibility criterion and is correct for an exposure one: a
   longer walk through the same haze does expose you more.

`c = 3` is Jin's constant for **light-reflecting sign legibility** -- the
contrast at which a subject can recognise a sign -- and it is not a statement
about whether a person can walk somewhere. Frantzich and Nilsson's subjects
walked at K = 7-8 /m, where Jin gives S = 0.4 m: people walk where they
demonstrably cannot read signs. Under the gate the constant now sets the
exposure budget directly, `tau_max = 2c`, so `c = 8` is a 2.7x looser gate than
`c = 3`. The earlier finding that `sign_contrast_c = 8` "barely moves it" was
measured on t_junction, which is optically saturated at K ~ 10.7 /m and cannot
discriminate anything; it is not evidence that `c` is inert where the gate works.

Jin and `c = 3` belong to the cognitive map, where the sign-legibility semantics
are correct and the constant is properly sourced. **Done at `0d9bf79`:** the gate
now carries `tau_max = 6.0` as its own constant, `sign_contrast_c` is gone, and
the docs declare it uncalibrated. Calibrating it against a soot-dose or
FED-equivalent limit remains open.

## Why the clean-exit tier cannot work here, structurally

The hysteresis protects the wrong crossing. Entering the clean set is guarded by
the 10x `FAC_DOOR_OLD` deadband; **returning is not a tier crossing at all**.
Once the near exit re-enters the set both routes are clean, the tier ties, both
bands sit at saturation, and the decision falls through to a plain time
comparison that the nearer exit wins immediately. That is why a wider margin
delays the oscillation without removing it.

FDS+Evac's tier is stable because refusal is **remembered**:
`Is_Visible_Door(i) = .FALSE.` and `Is_Known_Door(i) = .FALSE.`
(`evac.f90:16464-16465`) are permanent within the run. pyFDS-Evac removed that
memory at `e441b03`, deliberately, because permanent death destroyed the gate's
self-healing property (B3). **The tier cannot be had without the memory.** That
is a structural incompatibility, not a tuning failure, and it is a better reason
to keep the tier off than any seed count.

Scope limit: l_corridor has no persistent clean alternative, so it cannot refute
clean-preference in general. What is established is narrower and sufficient --
this implementation is unstable, and the instability is intrinsic to a
memoryless lexicographic tier.

## Under the gate, no hazard bypasses the anchor

`_must_flee_rejection` matches `reason.startswith("FED")` or `"visible" in
reason`. The gate's only rejection reason is `tau ...` (was `sight (path) ...`),
and `visibility_extinction_threshold` no longer fires under the gate, so the
`"visible"` branch is unreachable there and `impassable_extinction_threshold` is
dead code under the default model. The only surviving flee path is FED, which on
these fires never fires (`max fed_max_route = 0.0016` against a threshold of
1.0). This is defensible if the gate is genuinely not a hazard statement, which
per the ruling above it is not -- but it should be stated rather than left as
vestigial code implying a protection that does not exist.

**Status: documented, not fixed.** Stated in
[route-cost-gate.md](route-cost-gate.md#known-limitations), in the README, and in
[rerouting-oscillation-notes.md](rerouting-oscillation-notes.md). Renaming the
reason string to `tau` at `0d9bf79` did not change the disposition; it made the
`"visible"` branch unreachable by a second route.

## Open after `9f55f6e`: the ordering and the anchor are in different currencies

`rank_routes` orders feasible routes by `tau`; `_anchor_allows` compares
`rank_cost`, a travel time. The two can disagree, and an agent then oscillates
between what each prefers. Measured on l_corridor: 51 returns to abandoned exits
at `0d9bf79`, 34 at `9f55f6e` once the current exit's `tau` was discounted.
world100 is unaffected -- 39 agents to the far clean exit, 9 switches, no
returns.

Two attempts made it worse and should not be repeated:

- **`tau` as the anchor's currency**: 51 returns became 90. `tau` is zero in
  clear air, so `candidate.tau < old.tau * 0.9` degenerates to `0 < 0` and the
  anchor stops discriminating. It is also why `rank_cost` must stay a time: a
  `tau` anchor would let no agent switch in clear air, and `w_queue` would count
  for nothing exactly where decks calibrate it.
- **A ratio-only bypass**: 109 returns. Adding the absolute floor
  `old.tau - candidate.tau > 0.1 * tau_max` took it to 51.
- **Making that deadband symmetric** (`25a6f8f`): 34 returns before, 34 after.
  The asymmetry was real -- leaving an exit had to clear a margin in `tau` while
  returning fell straight through to the time comparison, which the nearer exit
  wins unconditionally -- and fixing it changed nothing measurable.

**That null result reframes the finding.** Of l_corridor's 34 returns, 29 have
the returned-to route cleaner by more than the deadband (median 0.95 of optical
depth against a margin of 0.6). They are the ordering correctly following a
field that reversed, not an oscillation any constant could damp. What is open is
therefore not the mixed currency but a modelling question: **should a memoryless
model follow a reversing field?** FDS+Evac's answer is memory -- a door struck
out at `evac.f90:16463` stays struck out (`:16464-16465`) -- and pyFDS-Evac
removed that at `e441b03` on purpose, because permanent death destroyed the
gate's self-healing property (B3). The two cannot both be had as the code
stands. This belongs in the PR discussion.
