# Rerouting Oscillation — Cause, Fix, and the 0.9 Anchor

Why agents flip-flop between exits during dynamic rerouting, what the game-theory
literature says about it, and the fix we implemented. Code: `route_graph.py`.
FDS+Evac reference: `materials/evac.f90`. Theory: Ehtamo et al. (2010),
`materials/Ehtamo2010.pdf`.

## The symptom

Agents repeatedly switch their target exit back and forth during a run. It is worst
at short reroute intervals (e.g. 1 s), because the flip can recur on every
re-evaluation.

## The cause (in our code)

The exit-switch decision had **no hysteresis**. We already had an anti-thrash margin,
`_PATH_IMPROVEMENT_THRESHOLD = 0.95`, but it only guarded *same-exit* path swaps
(`route_graph.py`). The branch that switches to a *different* exit adopted any exit
that ranked cheapest, however marginally — so two near-tied exits swapped every tick.
A congestion feedback loop made it worse: switching to exit B raises B's queue cost,
which makes A look cheaper next round, which switches back.

## What the literature says (Ehtamo 2010)

- **Cost model** (their Eq. 6): an exit's estimated evacuation time is
  `moving_time + queuing_time = distance/speed + (closer agents heading there)/capacity`.
  It is a genuine game — your queue depends on everyone else's choice.
- **The game converges — under fixed positions.** Best-response reaches a Nash
  equilibrium with *both* parallel and round-robin update schedules (Thms 4.1, 4.2).
  Update order is not the key lever. (This corrects an earlier assumption that
  parallel updating "cycles forever" — it does not, for this game.)
- **Why a live sim still oscillates:** those proofs assume agents are stationary. In
  a run everyone is walking, so distances and congestion shift continuously and the
  equilibrium target keeps moving — naive best-response chases it.
- **The fix is an "anchoring parameter":** *"an agent may not be willing to react to
  such small differences."* Discount the current exit so a rival must be *clearly*,
  not marginally, better. Grounded behaviourally in Proulx (people stick to a chosen
  plan). Two forms — subtract seconds, or multiply the current cost by a factor in
  (0,1).
- **Re-evaluation frequency is not the problem.** Ehtamo's agents re-decide
  continuously and still settle. Fast re-evaluation is realistic (a person re-plans
  instantly); anchoring, not a slow timer, is what makes it stable.

## What FDS+Evac does (reference implementation)

- `FAC_DOOR_WAIT = 0.9` — the proportional anchor: the current door's estimated time
  is multiplied by 0.9 (looks 10% faster), applied to every comparison.
- `FAC_DOOR_OLD = 0.1` — current door stays "smoke-free" ~10× longer (extra stickiness).
- `TAU_CHANGE_DOOR = 1.0 s` — reconsider ~every 1 s, stochastically staggered.
- Uses round-robin updates + a Nash convergence check (`NASH_CLOSE_ENOUGH = 0.05`).

## The fix (implemented)

Added `RerouteConfig.exit_switch_anchor` (default **0.9**) and gated the exit-switch
branch in `evaluate_and_reroute` (`route_graph.py`): adopt a different exit only if

```
best.composite_cost < current_exit_cost · exit_switch_anchor
```

Important nuance (caught by `test_smoke_triggers_reroute`): **anchoring is skipped
when the current exit is rejected** (smoke-blocked or FED-lethal). Hysteresis must
never pin an agent to an exit that has become unsafe — fleeing to a costlier but
survivable exit must always be allowed. Anchoring is also skipped on the initial
choice, and when the old exit is no longer reachable/priced.

Real runs use 0.9: `run_config.py` builds `RerouteConfig` without overriding the
field. Locked in by `tests/test_route_graph.py::TestExitSwitchAnchor` (a ~5% gain is
blocked with the anchor, allowed with it disabled).

## Why 0.9 — honest accounting

**Grounded (the mechanism):** that there should be a hysteresis margin at all, as a
proportional factor in (0,1) — Ehtamo's anchoring parameter, Proulx's psychology.

**Not grounded (the value):** 0.9 is *not* calibrated. It is FDS+Evac's default
"patience factor" — a round number; the guide states it without justification and
Ehtamo never derives a value. Our previous same-exit 0.95 is equally arbitrary.

So the justification for 0.9 is **"matches the field-standard reference tool"**
(convention/precedent), which is real but weaker than a calibrated weight — and it is
labelled as such in the code comment.

**Why 0.9 rather than keeping 0.95:** the value change is minor and neither is
calibrated — the substantive fix is adding anchoring to the exit-switch branch *at
all*. Given we pick some default, 0.9 (a) matches the tool this field validates
against, so behaviour is directly comparable, and (b) is slightly stronger inertia
(10% vs 5% margin), i.e. more resistant to the oscillation we are killing.

**TODO for a real number:** a sensitivity sweep (à la Haghani 2018) — the smallest
margin that stops oscillation without making agents ignore genuinely better exits — is
the only path to a *calibrated* value rather than a borrowed one.

## Second fix — FED deadband (asymmetric hysteresis)

After the anchor, the demo still flip-flopped. Route-cost logs showed the residual
was **FED-flicker, not visibility**: a route's predicted dose sitting right on the
1.0 incapacitation threshold and wobbling across it every second (e.g. agent 119's
exit B: 0.94 → 1.07 → 0.94 …), rejecting/un-rejecting the exit each tick.

Naive stickiness (make the current exit's FED threshold more lenient, à la FDS+Evac
`FAC_DOOR_OLD`) would be **unsafe here** — `FAC_DOOR_OLD` only applies to *non-lethal*
smoke, never lethal conditions. Making the FED threshold sticky would glue agents to a
route the model predicts will incapacitate them.

Safe fix — an **asymmetric deadband (Schmitt trigger)**, `RouteCostConfig.fed_return_margin`
(default 0.9):
- The agent's **current exit** keeps the full threshold (1.0) — it still flees the
  instant predicted dose crosses incapacitation. Safety unchanged.
- A **different exit** is only accepted as a switch target if its dose is below
  `1.0 × 0.9 = 0.9` — clearly safe, not merely back under threshold.

So leaving a bad exit stays instant; *returning* to one requires clear margin, which
stops the flip-back. `current_exit` is threaded through `rank_routes → evaluate_route`
so the rejection knows which exit is the agent's own. Locked in by
`test_fed_deadband_asymmetric` and `test_fed_deadband_still_flees_over_threshold`.

Result: agent 119 went 4 switches → 0. But aggregate demo oscillation only dropped
modestly (≈33 → 30 reversals), because the deadband only targets FED-flicker (~half
the demo's reversals); the rest is congestion overshoot (below).

## Third source — visibility rejection bypasses the anchor (the real demo cause)

This is what actually flip-flopped the demo, at both 1 s and 5 s. Found by
instrumenting a real run (`--output-route-history` + route-cost history) rather than
guessing — the earlier congestion/sign theories below turned out not to be the trigger.

### The evidence

In the demo route-cost log, at t=75 s agent 21's committed exit (B) is the **cheaper**
one yet gets rejected, and the agent flees to the costlier A:

```
exit_A_left   rank 1  cost 41.78  rejected=False
exit_B_right  rank 2  cost 41.36  rejected=True  reason="all segments non-visible"
```

Across the run, **14 switches move an agent to an equal-or-more-expensive exit**
(e.g. agent 28: 53.83 → 55.04). Under the anchor a switch needs `new < old × 0.9`, so a
switch to a costlier exit can only happen when the current exit is **rejected** — which
**bypasses the anchor** (`route_graph.py`, by design: an agent must be free to flee an
*unsafe* exit). `fed_max ≈ 0.002` and `queue = 0` on these rows, so it is neither FED nor
congestion: it is the **K_vis fallback** rejecting a route whose segments are all below
the `visibility_extinction_threshold` (0.5).

### Why the binary rejection is wrong here

The rejected routes carry only **mild** smoke — k_ave 0.505–0.942, barely over the 0.5
threshold — while a genuinely impassable route (test fixture) is k_ave 8.0. The binary
`all segments non-visible` flag can't tell light haze from a wall of smoke, and smoke is
**already** in the route cost via `w_smoke · k_ave`. So a route in light haze is
double-counted: costed *and* hard-rejected, and the rejection bypasses the anchor →
unguarded U-turn every time the haze crosses the threshold.

### The fix — `_must_flee_rejection` (graded rejection)

The anchor is bypassed **only** for a genuine hazard the agent must flee:

- **FED-lethal** (`FED_max > threshold`), or
- **impassably dense smoke** — route k_ave above `impassable_extinction_threshold`
  (default 3.0, ~1 m visibility, `S ≈ C/K`).

A *mild* visibility rejection (light haze, or an unreadable sign on an otherwise clear
route) is left subject to the anchor: the smoke is in the cost, so the agent stays on its
cheaper committed exit instead of U-turning. Verified against the demo log: **14/14
mild-smoke flips prevented, all 27 genuine cost-driven switches kept, 0 FED/dense-smoke
flees affected**. Locked in by `test_mild_smoke_does_not_flee_current_exit` (mild → stay)
and `test_smoke_triggers_reroute` (dense k_ave 8.0 → still reroutes).

`impassable_extinction_threshold` is not calibrated — it is chosen to sit above the mild
haze that caused the flip-flop (≤ ~0.9) and below genuine walls of smoke; a sensitivity
sweep is the path to a real value.

## Fourth source — position-blind routing (the deepest cause)

With the rejection-bypass fixed (above), a residual remained: agents walking **back and
forth** between near-tied exits, and — more tellingly — an agent standing **1 m from an
exit walking away from it** to a far one. The route-cost log showed the smoking gun: every
route was priced with `source = jps-checkpoints_0`, i.e. **distances from the upstream
junction, not from where the agent actually was.** Agent 35 at t=86 sat 1.1 m from exit B
yet was charged "B = 11 m, A = 18 m" (both junction-relative) and routed to A, 28 m away;
at t=102, 11 m into its walk toward A, it was *still* charged "A = 18 m from the junction",
so B looked cheaper and it reversed. Every agent in the corridor was priced **as if it
were standing at the junction**, regardless of how far it had walked — which is exactly why
they walk past exits and reverse mid-corridor.

The `B→A→B→A` churn was a *symptom* of this: fixed-node costs swing with the smoke field
and nothing credits the distance already covered, so agents chase the momentarily-cheaper
exit forever.

**Fix — position-aware cost (Haensel 2014 "path-integrated distance").** `evaluate_route`
now takes `agent_position` and `current_target` and measures distance from the agent's
actual position:
- **Continuing toward the current target** → charge only the *remaining* distance from the
  agent to that node (credit progress), replacing the first node-to-node segment.
- **A route diverging from that heading** → add the *backtrack* from the agent's position to
  the branch node before the graph distance.

Verified against agent 35's real trajectory: t=86 becomes B = 11 vs A = 121 → **stays at B**
(no walking away); t=102 becomes A = 77 vs B = 137 → **stays at A** (no reversal). Without
`agent_position` it falls back to the geometric node path length (backward compatible).
Locked in by `tests/test_route_graph.py::TestPositionAwareRouting`.

**Why this replaced anti-backtracking.** A first prototype for the churn added a stricter
`reversal_anchor` + `previous_exit` "don't undo your last switch" rule. It worked, but
position-aware cost is the *root* fix: commitment now emerges from geometry itself —
backtracking is free near the junction (agent hasn't committed) and expensive once it's
down a corridor — which is more principled than a fixed reversal margin, and it also fixes
the "walk away from the exit you're next to" case that anti-backtracking never addressed.
So the anti-backtracking heuristic was **reverted** as redundant; the base
`exit_switch_anchor` (0.9) still damps genuine near-ties at the junction.

## Analysed but NOT shipped (deferred; no demonstrated need)

Two mechanisms were prototyped while hunting this bug, then reverted once the demo data
showed neither was the cause. Kept here so they are cheap to resurrect **with a test
grounded in a scenario that actually exhibits them**:

- **Congestion overshoot / distance-gated queue (Ehtamo Eq. 6).** The queue term counts
  *all* agents heading to an exit, not just those closer than you; a far-field crowd
  shift can then swing every agent's cost. Real, but the demo's `queue = 0` — not its
  problem. Fix would be a per-exit sorted-distance snapshot and `bisect_left(..., my_dist)`.
  The full FDS+Evac answer is Nash-iterating exit choice to convergence each tick before
  anyone moves (`NASH_CLOSE_ENOUGH = 0.05`) — expensive; only worth it if metrics show
  mis-allocation (waves piling on one exit), not a busy-looking viewer.
- **Sign-visibility proximity override.** With `--vis-cache`, fdsvismap's `view_angle`
  check can drop a sign at close range (steep angle), rejecting an exit the agent has all
  but reached. But the standard demo runs **without** `--vis-cache`, so `vis_model` is
  `None` and this path is inert — and `_must_flee_rejection` above already keeps a
  sign rejection subject to the anchor. Revisit only for sign-driven (`--vis-cache`) runs.

**A longer reroute interval is not a fix.** The demo flip-flopped at 5 s too — the loop is
algorithmic (a rejection bypassing hysteresis), not a frequency artefact, and a slower
timer is *less* behaviourally realistic, not more.

## Bottom line

- **Bug 1:** exit switches had no inertia → **fix:** `exit_switch_anchor` (0.9),
  bypassed when the current exit is genuinely unsafe.
- **Bug 2:** FED-flicker at the dose threshold → **fix:** asymmetric `fed_return_margin`
  (0.9) deadband — flee at 1.0, return only below 0.9; never weakens safety.
- **Bug 3 (the demo cause):** *any* visibility rejection of the current exit bypassed the
  anchor, so mild smoke (k_ave ~0.5–0.9) tripping the binary 0.5 threshold flipped agents
  onto costlier exits → **fix:** `_must_flee_rejection` — only FED-lethal or impassably
  dense smoke (`impassable_extinction_threshold`, 3.0) bypasses the anchor; mild haze is a
  soft cost. Proven on the demo log: 14/14 flips fixed, 27 real switches kept.
- **Bug 4 (deepest cause):** routes were priced from the upstream junction node, ignoring
  where the agent actually was — so an agent 1 m from an exit walked away from it and
  reversed mid-corridor → **fix:** position-aware cost (Haensel path-integrated distance,
  `agent_position` + `current_target`) — credit progress toward the current target, charge
  backtracking to reach a divergent route. Commitment now emerges from geometry.
- **Deferred / reverted:** congestion distance-gating, the sign proximity override, and the
  anti-backtracking `reversal_anchor` heuristic — all analysed, none the root cause;
  reverted in favour of the fixes above. Resurrect with a data-grounded test if a scenario
  ever needs them.
- **Values (0.9 / 3.0):** *not* calibrated; sensitivity sweeps are the path to real numbers.
- **Frequency is not the culprit:** instant re-evaluation is realistic; a longer interval
  hides oscillation without fixing it. Correct rejection semantics + hysteresis are what
  make it stable — confirmed when 5 s still oscillated but graded rejection did not.
