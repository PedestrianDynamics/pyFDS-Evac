---
title: "Dynamic route rerouting"
weight: 3
math: true
---

See [docs/routing.md](/docs/routing.md) for the full routing model,
cost formulas, and API reference, and
[docs/routing-and-signs-notes.md](/docs/routing-and-signs-notes.md) for
working notes on exit choice and where the exit-choice research papers
disagree with each other.

Background: the ideas behind this model are explained on the [Concepts](/docs/concepts.md) page
and in the talk [*A Modular Workflow for Visibility-Aware Evacuation Modelling*](https://pedestriandynamics.org/pyFDS-Evac/talks/visibility-seminar-2026/)
([PDF](https://pedestriandynamics.org/pyFDS-Evac/talks/pyFDS-Evac_visibility_seminar_2026.pdf)).

## How smoke enters route choice

Two models, selected per deck with `routing.cost_model`.

**`"gate"` (default).** One quantity does the whole of the smoke reasoning: the
route's **optical depth**

```
tau = K_ave * L
```

the soot column the agent walks through, with `K_ave` the mean extinction along
the route polyline and `L` the distance still to walk. On this page `tau` is
always this dimensionless optical depth, not the relaxation time τ of
FDS+Evac's movement model. A route is refused when
`tau` exceeds `tau_max` (default 6), Dijkstra weights every edge by its own
`tau`, and `tau` orders the routes that survive, with travel time breaking ties.
Path choice and exit choice are therefore one objective. In clear air every
`tau` is zero, nothing is refused, and the model reduces to nearest-exit.

![Top: plan view with three routes from one agent to exits A, B and C around a smoke plume. Bottom: bar chart of optical depth per route against the budgets 4.8 and 6](/images/concepts/exposure_gate.png)

*Schematic with a prescribed toy plume, not a simulation. Top: three candidate
routes, sampled along each walk and coloured by extinction K [1/m]. Bottom:
optical depth `tau` [-] per route against `tau_max` = 6 (current exit and
initial choice) and 0.8 `tau_max` = 4.8 (any other exit). Route C is refused;
route B ranks first although it is the longest walk.
Script: `scripts/figures/exposure_gate.py`.*

`tau` is an **exposure** statement, not a sighting distance. The criterion grew
out of one -- `c / K_ave >= 0.5 * L` rearranges to `K_ave * L <= 2c`, which is
`tau <= 6` at Jin's `c = 3` -- and FDS+Evac's tier-4 door rule is exactly
`tau > 6` (`evac.f90:16458, :16463`). But Jin's `S = c / K` is contrast along a
straight unobstructed line to a sign; integrating `K` around two corners
measures what you walk through, not what you can see. The two coincide only on a
straight corridor, and `tau_max` is **not calibrated** against a soot-dose or
FED-equivalent limit. Jin's constant keeps its proper meaning in the cognitive
map, where sign legibility is the question being asked.

Refusals are **not remembered**. The criterion is relative to the distance still
to walk, so it relaxes on approach: smoke that refuses a door at 40 m accepts it
at 2 m. When every route is refused the agent still has to move, so it takes the
one with least smoke to walk through and holds it unless a rival's worst stretch
is clearly milder (`fallback_switch_margin`). Churn is held down by the
exit-switch anchor, by a stricter budget for a rival exit
(`tau_return_margin`, 0.8), and by a discount on the current exit's `tau` in the
sort (`current_exit_discount`, 0.9, FDS+Evac's `FAC_DOOR_OLD2`).

**Measured, with the limitation stated.** Ranking on `tau` sends 39 of
`world100`'s agents to the far clean exit, with 9 switches and no agent
returning to an exit it abandoned -- the outcome the model exists to produce.
On `l_corridor` agents oscillate: 34 returns to abandoned exits across 14
agents and 55 switches, with a far-exit share of about 18. The cause is **not**
a currency mismatch between the `tau` ordering and the anchor's time
fallthrough: 29 of the 34 returns go to a route cleaner by more than the
deadband, and 31 fall in `t = 40-60 s` where the two routes' `tau` genuinely
cross over. The model is following a field that reverses, and no constant damps
that -- what is missing is commitment
([#124](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/124)).
See [docs/route-cost-gate.md](/docs/route-cost-gate.md#known-limitations).

**This is a departure from FDS+Evac, not a reproduction of it.** The threshold
`tau > 6` is borrowed with a citation; the *place* it is used is not. In the
reference's first three tiers the rank is a time or distance norm and smoke is
only a boolean admission test (`evac.f90:16265, :16354, :16401`), so smoke can
move a door between tiers but cannot reorder candidates. It ranks on smoke only
in the tier-4 last resort, over known-or-visible doors, on a bee line, with
permanent strike-out. Here `tau` is the ordering everywhere, with no memory.
On `l_corridor` that diverts 18 of 100 agents where the reference criterion
would send essentially everyone to the near exit -- a prediction reasoned from
`evac.f90`, not a measured run of it. A `L/d` geometric bias (1.41 near against
1.27 far on that deck) tilts the criterion about 11 % further in the same
direction. Both are written up in
[docs/route-cost-gate.md](/docs/route-cost-gate.md#the-diversion-is-a-departure-from-fdsevac-not-a-reproduction-of-it).

An optional **clean-exit tier** (`clean_extinction_threshold`, **off by
default**) prefers exits below an absolute smoke criterion outright, however
far. It is FDS+Evac's primary door rule, and measured on both reference decks it
did not redirect anyone while costing monotonicity -- see
[docs/gate-model-review-notes.md](/docs/gate-model-review-notes.md).

Each segment is priced at the time the agent would *arrive* there (`anticipate`,
`foresight_horizon_s`), using unimpeded speed.

**`"additive"`.** The original model: smoke is a toll per metre walked,
`effective_length * (1 + w_smoke * k_ave) + w_fed * fed_max`. Both terms scale
with route length, so a long clean detour pays for its length twice and can
never win -- which is why the gate exists. Pin it with
`{"cost_model": "additive", "anticipate": false}`; `anticipate` is independent
of the model, so the pin needs both.

**FIC does not route** under either model. It drives the Purser slowdown and
incapacitation only. FIC and the optical-depth gate are driven by the same
smoke, so routing on both would double-count.

**What this model does not do.** It is not hazard avoidance. On the fires
measured here the dose veto never comes close to firing -- the largest projected
FED over a whole `l_corridor` run is 0.0016 against a threshold of 1.0 -- and
`impassable_extinction_threshold` cannot fire under the gate at all, because it
is reached only from a rejection reason containing `"visible"` and the gate's
only reason string starts `tau`. So no smoke rejection bypasses the exit-switch
anchor at any density. What the gate does is exposure-gated wayfinding.

The model reference is [docs/route-cost-gate.md](/docs/route-cost-gate.md);
provenance and the open questions are in
[docs/gate-model-review-notes.md](/docs/gate-model-review-notes.md).
`assets/l_corridor` is the deck the model is judged on -- a near exit behind the
fire and a clean 58 m way round -- and its results are in the sciebo case folder.

## Components

- **StageGraph**: Dijkstra-based shortest-path routing on a graph of
  stages (distributions, checkpoints, exits)
- **Route cost evaluation**: Samples extinction (K) along candidate paths
  to compute smoke exposure. When a `fed_model` is provided, projected FED
  vetoes routes under both models and enters the ranking only under
  `"additive"`
- **Dynamic rerouting**: Agents recompute routes at configurable intervals,
  selecting lower-exposure paths when available
- **Cognitive-map history**: `run_scenario(collect_cognitive_map_history=True)`
  records what each agent knows, every time it changes — see
  [docs/testing-familiarity.md](/docs/testing-familiarity.md) and
  `scripts/animate_cognitive_map.py`
- **Discovery-world generator**: `scripts/generate_discovery_world.py` produces
  random test decks (open room, convex obstacles, signed checkpoints, exits
  optionally hidden from the spawn) for exercising discovery routing; the same
  decks drive the invariant tests in `tests/test_generated_worlds.py`
- **Congestion-aware routing**: Optional exit-congestion term (`w_queue`), **off
  by default** — it scales with a global agent count, so no constant suits every
  scenario. `assets/station_fahy` opts in at 0.024, calibrated against Fahy
  Table 2 — see [docs/routing.md](/docs/routing.md#why-it-is-opt-in-and-what-0024-means)
  and `scripts/sweep_queue_weight.py`
- **Throughput throttling**: Optional exit flux limiting via
  `enable_throughput_throttling` and `max_throughput` in scenario config

## Usage

See [docs/usage.md](/docs/usage.md) for the full rerouting CLI
(`--enable-rerouting`, `--reroute-interval`, `--output-route-history`,
`--output-route-cost-history`, `--vis-cache`) and the plotting scripts
that consume the generated route-cost CSVs.
