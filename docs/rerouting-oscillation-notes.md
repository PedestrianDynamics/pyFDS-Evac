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

## Third source — congestion overshoot (NOT fixed; documented follow-up)

The remaining oscillation is the **crowd sloshing** feedback loop: many agents
re-evaluate against the same congestion snapshot, all switch to the momentarily-cheaper
exit, overshoot its congestion, and swing back next tick. This is Ehtamo's
parallel-best-response overshoot, made permanent by agents moving (the equilibrium
target keeps shifting).

FDS+Evac's answer: at each decision point it iterates the exit choice to a **Nash
equilibrium** — sweep all agents, update each door's crowd count immediately after each
picks, repeat until <5% still change (`NASH_CLOSE_ENOUGH = 0.05`) — *before* anyone
moves. Ours updates `exit_counts` sequentially already, but does only **one pass per
tick** instead of iterating to convergence, so the crowd takes many ticks to settle
(and, with movement, may never fully settle).

**Decision: not building this now.** Rationale:
- Much of the residual is legitimate (agents genuinely bouncing between two
  marginal-dose exits in a deadly scenario).
- All the bad numbers are at an unrealistic **1 s** interval; a realistic 5 s interval
  lets the crowd spread between re-evaluations and slosh far less — free mitigation.
- The full Nash-iteration loop is expensive (N sweeps/tick) and fiddly
  (convergence caps, determinism, movement coupling) — high risk for a partly-cosmetic
  gain.

**Reach for it only if metrics show mis-allocation** (waves of everyone piling on one
exit inflating egress time), not just a busy-looking viewer. Cheaper mitigations to try
first: raise the reroute interval to ~5 s; randomise re-evaluation order + 2 sweeps;
or cap how many agents may switch *to* one exit per tick (anti-herding throttle).

## Bottom line

- **Bug 1:** exit switches had no inertia → **fix:** `exit_switch_anchor` (0.9),
  bypassed when the current exit is unsafe.
- **Bug 2:** FED-flicker at the dose threshold → **fix:** asymmetric `fed_return_margin`
  (0.9) deadband — flee at 1.0, return only below 0.9; never weakens safety.
- **Residual:** congestion overshoot — documented, deferred; fix only if it distorts
  metrics.
- **Values (0.9):** match FDS+Evac — defensible by precedent, *not* calibrated; a
  sensitivity sweep is the path to real numbers.
- **Frequency is not the culprit:** instant re-evaluation is realistic; hysteresis is
  what makes it stable.
