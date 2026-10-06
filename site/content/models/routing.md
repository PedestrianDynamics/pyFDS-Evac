---
title: "Dynamic route rerouting"
weight: 4
math: true
---

> [!NOTE]
> This page is the specification of the routing model. For worked cases on the
> assets (runs, figures, numbers), see [Routing in practice](/docs/routing.md)
> and [Gate model in practice](/docs/route-cost-gate.md).

Based on: [Extinction coefficient](/fundamentals/extinction.md), [Visibility through smoke](/fundamentals/visibility.md) and [Exit choice and familiarity](/fundamentals/exit-choice.md).

See [docs/routing.md](/docs/routing.md) for the routing machinery,
cost formulas, and API reference, and
[docs/routing-and-signs-notes.md](/docs/routing-and-signs-notes.md) for
working notes on exit choice and where the exit-choice research papers
disagree with each other.

Symbols follow the [notation table](/docs/concepts.md#notation).

Background: the [Concepts](/docs/concepts.md) page and the talk [*A Modular Workflow for Visibility-Aware Evacuation Modelling*](https://pedestriandynamics.org/pyFDS-Evac/talks/visibility-seminar-2026/).

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
[FDS+Evac](https://github.com/firemodels/fds/tree/c9da70d7a/Source)'s movement model. A route is refused when
`tau` exceeds `tau_max` (see [Parameters](#parameters)), Dijkstra weights every edge by its own
`tau`, and `tau` orders the routes that survive, with travel time breaking ties.
Path choice and exit choice are therefore one objective. In clear air every
`tau` is zero, nothing is refused, and routes order by travel time (the
Dijkstra tie-break is 1e-6 × length), which is nearest-exit; this equivalence
has not been re-measured since routes were first ordered on `tau`
([Known limitations](/docs/route-cost-gate.md#known-limitations)).

![Top: plan view with three routes from one agent to exits A, B and C around a smoke plume. Bottom: bar chart of optical depth per route against the budgets 4.8 and 6](/images/concepts/exposure_gate.png)

*Schematic with a prescribed toy plume, not a simulation. Top: three candidate
routes, sampled along each walk, the samples shaded by extinction K [1/m]. Bottom:
optical depth `tau` [-] per route against `tau_max` = 6 (current exit and
initial choice) and 0.8 `tau_max` = 4.8 (any other exit). Route C is refused;
route B ranks first although it is the longest walk.
Script: `scripts/figures/exposure_gate.py`.*

`tau` is an **exposure** statement, not a sighting distance; where its budget
comes from is under [Deviations from the literature](#deviations-from-the-literature).

Refusals are **not remembered**. The criterion is relative to the distance still
to walk, so it relaxes on approach: smoke that refuses a door at 40 m accepts it
at 2 m. When every route is refused the agent still has to move, so it takes the
one with least smoke to walk through and holds it unless a rival's `tau` is
clearly lower (`fallback_switch_margin`). Churn is held down by the
exit-switch anchor, by a stricter budget for a rival exit
(`tau_return_margin`), and by a discount on the current exit's `tau` in the
sort (`current_exit_discount`, FDS+Evac's `FAC_DOOR_OLD2`).

**Measured, with the limitation stated.** Ranking on `tau` sends `world100`'s
agents to the far clean exit without returns, while on `l_corridor` agents
return to exits they abandoned, following a field that reverses; what is
missing is commitment
([#124](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/124)). The
counts are in [docs/route-cost-gate.md](/docs/route-cost-gate.md#churn-protection)
and [Known limitations](/docs/route-cost-gate.md#known-limitations).

**This is a departure from FDS+Evac, not a reproduction of it.** The threshold
`tau > 6` is borrowed with a citation; the *place* it is used is not. In the
reference's first three tiers the rank is a time or distance norm and smoke is
only a boolean admission test (`evac.f90:16601, :16690, :16737`), so smoke can
move a door between tiers but cannot reorder candidates. It ranks on smoke only
in the tier-4 last resort, over known-or-visible doors, on a bee line, with a
strike-out that lasts one call (`evac.f90:16800-16801`, reset at `:16170-16171`).
Its only lasting smoke memory is a weak mark on a lone agent's previous
target once `K_ave >= 0.3 /m` (`:16628-16637`), described in
[docs/model-comparison.md](/docs/model-comparison.md#the-smoke-criteria-on-a-door). Here `tau` is the
ordering everywhere, with no memory.
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

**Every exit is priced from the agent's position.** Dijkstra starts where the
agent stands. Its first legs are the walks from the agent to each successor of
its origin node, the node it last left, and to the node it is heading for.
Each walk goes through the walkable area and is weighted by the smoke on that
walk; all other edges are weighted by the smoke present at decision time
(`_generate_candidates`, `_first_hops`). The search never routes back through
the origin node, so every path starts at the agent and its first node is one
of those successors or the current target. A walk that passes the origin on
its way to a successor is still priced, on the smoke along it.

The first leg of each route is then measured on that walk: its mean
extinction, length and travel time enter `K_ave`, `tau` and the travel time,
so the agent pays for the smoke ahead of it and none of the smoke behind it
(`_measure_route`). The agent's current exit is also measured on the path it
is walking. If that path orders ahead of the searched one, it becomes the
current exit's entry, so the current exit is never ranked behind the path the
agent walks (`rank_routes`, `current_path`). Without a position, or when the
source is an exit, the search starts at the source node
(`_search_from_position`).

[FDS+Evac](https://github.com/firemodels/fds/blob/c9da70d7a/Source/evac.f90#L16096-L16955)
(`Change_Target_Door`) also evaluates every door, the current one included,
from the agent's position (`x1_old = xx`, `:16178`): smoke on the straight
sight line to the door (`See_door`, `:16486`) and the Euclidean distance
(`:16593`, `:16606`). It has no graph, so the walked path through the stage
graph is a pyFDS-Evac extension.

Anticipation (`anticipate`, `foresight_horizon_s`) applies only to the path
the search returns for each exit: each edge of that path is sampled at the
time the agent would reach the edge's start, using unimpeded speed, and
`tau`, travel time and projected FED are measured from those samples
(`_measure_route`).

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

The gate at work, with its evidence, is in [docs/route-cost-gate.md](/docs/route-cost-gate.md);
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

## Parameters

Defaults in the code, as a scenario's `routing` block reads them
(`RouteCostConfig.from_routing_params`, `pyfds_evac/core/route_graph.py`).
This is the complete list of keys. Which keys act under which cost model is
tabulated in [docs/route-cost-gate.md](/docs/route-cost-gate.md#configuration).

| `routing` key | Default | Meaning |
|---|---|---|
| `cost_model` | `"gate"` | `"gate"` or `"additive"`, matched exactly; any other value raises `ValueError` |
| `tau_max` | `6.0` | Budget \(\tau_{\max}\) on the optical depth of a route |
| `tau_return_margin` | `0.8` | A rival exit must come in under `tau_max` times this |
| `current_exit_discount` | `0.9` | Factor on the current exit's `tau` in the sort |
| `tau_deadband` | `0.1` | Anchor deadband, as a fraction of `tau_max` |
| `clean_extinction_threshold` | `0.0` (off) | Extinction [1/m] of the smokiest leg at or below which an exit is in the clean tier |
| `clean_exit_margin` | `0.1` | Hysteresis: the current exit stays clean up to `clean_extinction_threshold` / `clean_exit_margin` (FDS+Evac `FAC_DOOR_OLD`) |
| `fed_rejection_threshold` | `1.0` | Projected FED above which a route is refused |
| `anticipate` | `true` | Measure the path to each exit edge by edge at the agent's arrival time; the path search uses the smoke at decision time |
| `foresight_horizon_s` | `inf` | How far ahead [s] anticipation reads the FDS record |
| `fallback_switch_margin` | `0.2` | Between two refused routes, a rival's `tau` must be this fraction below the current exit's; differences up to 1e-9 are ties, which hold. Before 0.4.0 it compared worst extinction `k_max_route` ([#458](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/458)) |
| `w_smoke` | `1.0` | Smoke weight; additive model only, inert under the gate |
| `w_fed` | `10.0` | Dose weight; additive model only, inert under the gate |
| `w_queue` | `0.0` | Weight on queue time in the ranking cost (off) |
| `visibility_extinction_threshold` | `0.5` | Extinction [1/m] above which a segment counts as not visible; additive model only |
| `sampling_step_m` | `2.0` | \(\Delta s\), spacing of smoke samples along a polyline [m] |
| `base_speed_m_per_s` | `1.3` | Router's clear-air speed [m/s], not the agent's \(v_0\) |
| `alpha` | `0.706` | Router's copy of \(\alpha\) [m/s], for travel time only |
| `beta` | `-0.057` | Router's copy of \(\beta\) [m²/s], for travel time only |
| `min_speed_factor` | `0.1` | Router's copy of \(f_{\min}\), for travel time only |
| `default_exit_capacity` | `1.3` | Exit capacity [agents/s] for queue time, when an exit sets no `capacity_agents_per_s` |

Fixed constants, which no `routing` key can set:

| Constant | Value | Meaning |
|---|---|---|
| `RerouteConfig.exit_switch_anchor` | `0.9` | A rival exit needs `rank_cost` below this fraction of the current exit's |
| `RouteCostConfig.fed_return_margin` | `0.9` | A rival exit is refused above this fraction of `fed_rejection_threshold` |
| `RouteCostConfig.impassable_extinction_threshold` | `3.0` | Route-average *K* [1/m] above which a visibility rejection must be fled; never reached under the gate |
| `_PATH_IMPROVEMENT_THRESHOLD` | `0.9` | A new path to the same exit needs `rank_cost` below this fraction of the walked path's |

The router always uses the linear speed law, whatever `SmokeSpeedConfig`
the agents walk with. Each agent re-decides every
`RerouteConfig.reevaluation_interval_s`:

| Where the run starts | Re-decision interval |
|---|---|
| `RerouteConfig()` built in Python | `10.0` s |
| `run.py --reroute-interval` | `1.0` s |

The other defaults that differ between `run_scenario()` and `run.py` are
listed in [Python API and command line](/docs/usage.md#python-api-and-command-line).

### Assumptions

| Value | Source |
|---|---|
| `tau_max` = 6 | FDS+Evac tier-4 door rule, \(\bar K d \le 6\) (`evac.f90:16794`, `:16799`), used here as an exposure budget; not calibrated (see [Deviations](#deviations-from-the-literature)) |
| `current_exit_discount` = 0.9 | FDS+Evac `FAC_DOOR_OLD2` |
| `clean_exit_margin` = 0.1 | FDS+Evac `FAC_DOOR_OLD` |
| `exit_switch_anchor` = 0.9, `_PATH_IMPROVEMENT_THRESHOLD` = 0.9 | value of FDS+Evac `FAC_DOOR_WAIT`, applied to a different cost; not calibrated |
| `tau_return_margin`, `tau_deadband`, `fallback_switch_margin`, `fed_return_margin`, `impassable_extinction_threshold`, `visibility_extinction_threshold`, `w_smoke`, `w_fed` | pyFDS-Evac assumptions, not calibrated |
| `w_queue` = 0 | off; `assets/station_fahy` sets 0.024, calibrated against Fahy Table 2 ([routing in practice](/docs/routing.md#why-it-is-opt-in-and-what-0024-means)) |
| `base_speed_m_per_s` = 1.3, `default_exit_capacity` = 1.3 | pyFDS-Evac assumptions |

`evac.f90` line numbers on this page refer to the copy in `materials/evac.f90`,
FDS commit [c9da70d7a](https://github.com/firemodels/fds/blob/c9da70d7a/Source/evac.f90).

## Switching rule

At each re-decision the candidates ranked above the agent's current exit are
tried in order, and the first one the **exit-switch anchor** accepts is
taken. Under the gate, two `tau` values at most `EPS_TAU` = 1e-9 apart rank
as equal (after the current-exit discount), so travel time orders them;
neighbouring ties chain into one group (`taus_tie`, `_order_routes`). The anchor (`_AnchoredPolicy.anchor_allows`) decides in this order:

1. No current route: accept.
2. **Must flee** (`_must_flee_rejection`): the current route is refused for its
   projected FED, or for visibility with a route-average *K* above
   `impassable_extinction_threshold`. Accept, whatever the cost.
3. **Two refused routes** (both `feasible` false, which includes a route the
   fallback re-admitted): the candidate is accepted only if its `tau` is below
   the current route's × (1 − `fallback_switch_margin`) and the two differ by
   more than `EPS_TAU` (`_fallback_rival_wins`). Neither travel time nor
   `k_max_route` decides, so the agent is not held on a route with three times
   the smoke because it is quicker, and a tie (both `tau` 0 included) holds.
   The fallback order uses the same rule
   ([#458](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/458)).
4. Otherwise the cost model decides (`improvement`):
   - **Gate** (`GatePolicy.improvement`): a clean candidate leaves a dirty
     exit; an infeasible candidate needs `rank_cost` below
     `exit_switch_anchor` × the current one; a feasible candidate whose `tau`
     is lower by more than `tau_max` × `tau_deadband` (0.6 by default) is
     accepted, one higher by more than that is refused, and a tie inside the
     band falls through to the same `rank_cost` ratio.
   - **Additive** (`AdditivePolicy.improvement`): only the top-ranked route is
     tried, and it needs `rank_cost` below `exit_switch_anchor` × the current
     one.

Under the gate, the `tau` test overwrites the rejection reason after the FED
test sets it, so a route that is both FED-lethal and over `tau_max` loses the
must-flee bypass
([#128](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/128)).

A new path to the **same** exit is taken when its `rank_cost` is below
`_PATH_IMPROVEMENT_THRESHOLD` × the walked path's, or when the walked path is
refused and the new one is not (reason `better_path`). When every route is
refused, the least-smoky one is un-refused as a fallback. The full decision
table is in [Routing in practice](/docs/routing.md#rerouting-decision-flow).

### Code structure

For maintainers, one re-decision runs through: `_measure_route` (samples the
smoke and dose along a candidate) → `policy_for(config)`, which returns the
`GatePolicy` or `AdditivePolicy` that supplies `edge_weight`, `feasibility`,
`rank_cost`, `order_key` and `improvement` → `rank_routes` and
`_apply_fallback` → `evaluate_and_reroute`, which returns the switch records
written to the route history.

## How agents are steered

pyFDS-Evac decides where each agent goes, and JuPedSim moves the agent there.
The link between the two is JuPedSim's **direct-steering stage**: an agent on
such a stage walks towards the point stored in its `target`, and the caller
sets that point. JuPedSim 1.4.2 is the locked version (`uv.lock`;
`pyproject.toml` requires `jupedsim>=1.4.2`).

### What each side does

JuPedSim, inside `simulation.iterate()`:

- computes the next waypoint from the agent's position to its target on the
  navigation mesh of the walkable area, every step
  ([`TacticalDecisionSystem.hpp`](https://github.com/PedestrianDynamics/jupedsim/blob/v1.4.2/libsimulator/src/TacticalDecisionSystem.hpp));
- moves the agent towards that waypoint with the operational model set in
  the deck (`model_type`; `CollisionFreeSpeedModel` when unset).

pyFDS-Evac, in Python, in the main loop of `run_scenario` (`scenario.py`):

- sets an agent's target when the agent starts a new stage or changes exit
  (`direct_steering_runtime.py`, `assign_agent_target`);
- reads every agent's position each step and tests whether the agent has
  reached its stage (`direct_steering_runtime.py`, `reached_stage`). An exit
  is reached when the agent's centre is inside the exit polygon or within
  `EXIT_REACH_TOLERANCE_M` = 0.03 m of it. A checkpoint or waypoint is reached
  within the agent radius plus `TARGET_REACH_MARGIN_M` = 0.5 m of its target
  point;
- applies checkpoint waiting times, throughput caps, exit schedules and zone
  speed factors;
- removes an agent that reaches an exit with
  `simulation.mark_agent_for_removal`.

### Which agents are steered directly

- **Deck without journeys** (no `journeys` and no `transitions`, or no
  `distributions`). Every exit gets a direct-steering stage, and all agents
  share one journey made of a single direct-steering stage
  (`simulation_init.py`, `_initialize_with_fallback`). This is the default
  mechanism.
- **Deck with journeys.** An exit without throughput throttling becomes a
  native JuPedSim exit stage (`add_exit_stage`); a throttled exit becomes a
  direct-steering stage (`simulation_init.py`, `_add_stages`). Every exit is
  also kept in pyFDS-Evac's direct-steering table, so routed agents can be
  sent to it. JuPedSim accepts a direct-steering stage only as the sole stage
  of a journey. An agent whose journey contains a checkpoint or an exit from
  that table, which is every journey that ends at an exit, is therefore placed
  on the shared direct-steering journey, and pyFDS-Evac walks it through the
  journey's stages.
- **Distribution without a journey, in a deck with journeys.** Its agents get
  a JuPedSim journey to the nearest exit (`simulation_init.py`,
  `find_nearest_exit_journey`). At an unthrottled exit, JuPedSim removes them
  itself. A throttled exit is a direct-steering stage, so pyFDS-Evac steers
  these agents to it and removes them there under its cap
  ([#434](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/434)). A
  deck in which such an exit also has a schedule (`open_from_s` or
  `closed_after_s`) is refused at start.

### Why direct steering

The routing and wayfinding models need a target per agent that can change
during the run:

- Each agent re-evaluates its route at a fixed interval, every 1.0 s with
  `run.py` (`--reroute-interval`; `RerouteConfig.reevaluation_interval_s` is
  10 s when the config is built directly). Two agents in the same room can
  pick different exits, and an agent can switch exit mid-way.
- Each agent ranks only the routes on its own cognitive map
  ([Wayfinding](/models/wayfinding.md)).
- Exits open and close on a schedule
  ([#396](https://github.com/PedestrianDynamics/pyFDS-Evac/pull/396)).
- Exits and checkpoints can cap their throughput, and checkpoints can hold
  agents for a waiting time.
- Zone speed factors are applied per agent in the same pass.

A JuPedSim journey is a stage graph shared by every agent assigned to it. Its
transitions follow fixed rules (fixed, round robin, least targeted) set when
the journey is built, and they do not read smoke or an agent's knowledge.

[FDS+Evac](https://github.com/firemodels/fds/tree/c9da70d7a/Source) also
picks each agent's target itself. Each agent walks along the flow field of its
own target door (`FIND_PREFERRED_DIRECTION`,
[`evac.f90:11403–11404`](https://github.com/firemodels/fds/blob/c9da70d7a/Source/evac.f90#L11403-L11404)).
At random times, on average every `TAU_CHANGE_DOOR` = 1.0 s
([`:1531`](https://github.com/firemodels/fds/blob/c9da70d7a/Source/evac.f90#L1531),
[`:7998`](https://github.com/firemodels/fds/blob/c9da70d7a/Source/evac.f90#L7998)),
the agent calls `CHANGE_TARGET_DOOR` to choose its door again.

### Cost

Direct steering moves per-agent work out of JuPedSim's C++ core into Python.
Each step, pyFDS-Evac iterates over the agents through JuPedSim's Python API,
reads positions, tests stages and updates speeds. With native journeys, stage
reaching and removal run inside `simulation.iterate()`.

In two small clear-air runs, the per-step steering pass took about four times
as long as `simulation.iterate()`:

| Case | Steering pass | `iterate()` | Rest of loop |
|---|---|---|---|
| `familiarity_test_no_journey`: 20 agents, no journeys, 3489 steps | 79–80 % | 19–20 % | 1–2 % |
| `t_junction`: 200 agents flow-spawned over 400 s, deck with journeys (steered directly), 30000 steps | 76–78 % | 18–20 % | 4–5 % |

Shares are of the wall time of the main loop. The largest part of the steering pass is
pyFDS-Evac's own geometry: the exit test builds a shapely point per agent per
step. The cost of the same runs with native JuPedSim journeys is not measured.
These agent counts are small, so the shares can differ at higher density.

{{< details title="How the shares were measured" closed="true" >}}

- Commit `4f859bf5`, jupedsim 1.4.2, Python 3.12, Apple M3 Pro (12 cores),
  macOS 27.0.
- `run_scenario(load_scenario("assets/<case>"), seed=1)`: no smoke, no rerouting,
  JuPedSim's default time step of 0.01 s.
- Timers (`time.perf_counter`) around the main loop of `run_scenario` and
  around the steering pass (the block that runs when the direct-steering
  table is not empty, up to the cognitive-map history), in a local,
  uncommitted copy of `scenario.py`; `jupedsim.Simulation.iterate` wrapped
  with the same timer. "Rest of loop" is spawning and the other per-step
  passes.
- Four runs of each case; the table gives the range.
- `familiarity_test_no_journey` uses `SocialForceModel` and `t_junction`
  uses `CollisionFreeSpeedModel`, as set in their decks.
- `familiarity_test_no_journey` ends when every agent is out, at 34.9 s.
  `t_junction` stops at its 300 s limit with 143 of 200 agents out.
- A `cProfile` run of `t_junction` attributes the largest part of the
  steering pass to `reached_stage` → `distance_to_polygon` (shapely `Point`
  construction and distance), more than to JuPedSim's agent iterator.

{{< /details >}}

### What this means for correctness

Stage reaching, removal at exits, waiting times, throughput caps and exit
schedules are pyFDS-Evac code, so their tests live in this repository:

- [`tests/test_exit_door_width.py`](https://github.com/PedestrianDynamics/pyFDS-Evac/blob/main/tests/test_exit_door_width.py):
  agents leave only through the exit polygon, and the flow scales with the
  door width
  ([#349](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/349)).
- [`tests/test_thin_exit.py`](https://github.com/PedestrianDynamics/pyFDS-Evac/blob/main/tests/test_thin_exit.py):
  agents held a few centimetres short of a thin exit still count as out,
  and agents beside the door do not
  ([#401](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/401)).
- [`tests/test_scheduled_exits.py`](https://github.com/PedestrianDynamics/pyFDS-Evac/blob/main/tests/test_scheduled_exits.py):
  a closed exit removes nobody, and agents heading for it reroute
  ([#396](https://github.com/PedestrianDynamics/pyFDS-Evac/pull/396)).

- [`tests/test_throttled_exit_without_journey.py`](https://github.com/PedestrianDynamics/pyFDS-Evac/blob/main/tests/test_throttled_exit_without_journey.py):
  agents without a journey whose nearest exit is throttled reach that exit
  and leave it at the cap spacing
  ([#434](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/434)).

Exit throughput throttling has no general test yet
([#355](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/355)).

## Limitations

- Switching can oscillate where two routes cross in cost
  ([#124](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/124)).
  Pricing the first leg on the walk makes this more frequent near a smoky
  door, because a short walk follows the field from one second to the next.
  On the `l_corridor_gate` reference deck, switches went from 28 to 58 and
  exit reversals from 16 to 40, 28 of them within 2 s. Each switch follows
  the switching rule on correct prices.
- Routes are priced with smoke the agent cannot perceive, including stretches
  it has never seen
  ([#125](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/125)).
- Under the gate a FED-lethal route over `tau_max` loses the must-flee bypass
  ([#128](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/128)).
- One path is priced per exit
  ([#185](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/185)).
- The path to each exit is chosen on the smoke at decision time.
  Anticipation applies only to that path, edge by edge at the arrival time at
  the edge's start (`_generate_candidates`, `_measure_route`). Under
  `anticipate`, the search ranks on decision-time smoke, so its path can
  carry a higher `tau` on arrival than another path to the same exit.
- The search never offers "walk back to the origin node, then on". When that
  is the only way round the smoke, the direct walk is priced on its own smoke.
- The first-leg FED is a share of the first segment's FED growth, in
  proportion to the walk's length and at most the whole segment; the dose on
  the walk itself is not sampled. Anticipated arrival times are counted from
  the origin node along the whole first segment (`_measure_route`, `_arrival_time`;
  [#171](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/171), open).
- The ordering treats `tau` differences up to 1e-9 as ties, so round-off no
  longer decides it
  ([#452](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/452)).
  The anchor treats a difference within `tau_max` × `tau_deadband` as a tie,
  but a real difference inside that band still keeps the current exit ranked
  first, and the anchor is then never consulted
  ([#187](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/187), open).
- The queue term counts agents globally, not those an agent can perceive
  ([#89](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/89)).
- Heat does not enter route choice
  ([#81](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/81)).
- The smoke terms are the same for every familiarity setting
  ([#362](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/362)).
- `impassable_extinction_threshold` (3.0 1/m) is a modelling assumption
  with no empirical source; the field surveys give only self-estimated
  visibility at turn-back
  ([#371](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/371)).
- For discovery agents, the order of tied routes depends on
  `PYTHONHASHSEED` ([#199](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/199)).
- Anticipation assumes unimpeded speed and, by default, perfect foresight of
  the finished FDS record.

The measurements behind these are in
[Gate model in practice › Known limitations](/docs/route-cost-gate.md#known-limitations).

## Verification

- S4 T-junction
  ([`tests/verification/test_s4_tjunction_reroute.py`](https://github.com/PedestrianDynamics/pyFDS-Evac/blob/main/tests/verification/test_s4_tjunction_reroute.py)):
  agents leave a smoke-blocked exit for the clear one.
- Golden rerouting
  ([`tests/test_rerouting_golden.py`](https://github.com/PedestrianDynamics/pyFDS-Evac/blob/main/tests/test_rerouting_golden.py)):
  a regression check that decisions do not change unnoticed, not a
  verification against an independent value.

See the [Verification](/verification/_index.md) index for their status.

## Usage

See [docs/usage.md](/docs/usage.md) for the full rerouting CLI
(`--enable-rerouting`, `--reroute-interval`, `--output-route-history`,
`--output-route-cost-history`, `--vis-cache`) and the plotting scripts
that consume the generated route-cost CSVs.

## Deviations from the literature

The published laws are on [Visibility through smoke](/fundamentals/visibility.md)
and [Exit choice and familiarity](/fundamentals/exit-choice.md).

- **Where the budget comes from.** FDS+Evac's tier-4 door rule requires the
  visibility of a reflective sign at the door, \(3/\bar K\), to be at least half
  the distance *d* to the door, which rearranges to \(\bar K d \le 6\)
  (`evac.f90:16794`, `:16799`). That is the default `tau_max`
  (`route_graph.py`, `RouteCostConfig.tau_max`). Jin's law describes a straight line of sight to a
  sign in uniform smoke; here the same number bounds the integral of *K* along
  a walked polyline, which measures exposure, not sight. The two agree only
  on a straight corridor, and the budget has not been calibrated against a
  smoke-exposure or FED limit. The line-level comparison with `evac.f90` is in
  [docs/route-cost-gate.md](/docs/route-cost-gate.md#where-the-6-comes-from).
- **Exit choice.** Routes are ranked on optical depth and travel time.
  Familiarity and social influence, which the exit-choice literature finds
  significant, enter only through the cognitive map, not through the route
  cost, and herding is not modelled.
- **Smoke in a cognitive-map router, earlier work.** Schröder et al. (2015)
  priced routes by smoke in the cognitive-map router of JuPedSim. They
  integrate the FDS optical density *D* along the straight line of sight
  from the agent to each exit available to the agent, and weight the integral
  by the maximum *D* on that line over the maximum on all such lines
  (Eq. 4, p. 331). A door whose line of sight is obstructed is excluded
  from the smoke edge-factor calculation. The smoke raises the edge weight
  by the factor \(1 + 2 f_{\mathrm{smoke}} (1 - f_{\mathrm{risk}})\)
  (Eq. 5, p. 332), where the factor 2 and the individual risk tolerance
  \(f_{\mathrm{risk}}\) are chosen, not fitted to data (p. 332); the authors call the model a
  proof of concept. *D* is read at an extraction height in the upper layer
  (2.80 m in their example, p. 330; varied over 2–3 m, Table 2, p. 334),
  and the sensor does not evaluate visibility (p. 330). The
  height is an artificial parameter and the most influential one in their
  sensitivity study (p. 337). pyFDS-Evac differs: it integrates *K* along
  the walked route polyline, not a line of sight, and samples smoke the
  agent cannot perceive
  ([#125](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/125)). It
  implements neither Eq. 4, Eq. 5, \(f_{\mathrm{risk}}\) nor the
  obstruction test.
  [Route choice in smoke after Schröder et al. (2015)](/docs/study-schroeder2015.md)
  runs pyFDS-Evac's own routing on their geometry.

## Sources

- Schröder, B., Haensel, D., Chraibi, M., Arnold, L., Seyfried, A., &
  Andresen, E. (2015). *Knowledge- and perception-based route choice
  modelling in case of fire*. Proceedings of the 6th International
  Symposium on Human Behaviour in Fire, Cambridge, UK, 28–30 September
  2015, pp. 327–338. Interscience Communications. ISBN
  978-0-9933933-0-3. No DOI;
  [juser.fz-juelich.de/record/255940](https://juser.fz-juelich.de/record/255940).
