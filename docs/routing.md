# Smoke-aware routing

> Part of [pyFDS-Evac](../README.md).

The pyFDS-Evac routing system implements dynamic, smoke-aware path
planning. Agents evaluate candidate routes against the current hazard
fields and periodically reroute as conditions change. Costs are
recomputed at each reevaluation tick, so the chosen path adapts as
conditions evolve.

> **Which model is running.** Two cost models exist, selected per deck
> with `routing.cost_model`. The **default is `"gate"`**: the route's
> optical depth `K_ave * L` decides which exits stay available and
> orders the survivors, with travel time as tie-break. The historical
> `"additive"` model, in which smoke is a toll per metre, is still
> available. This page covers the machinery both share; the
> gate itself is documented in
> [route-cost-gate.md](route-cost-gate.md).

> **Note:** The cost model supports both smoke and FED (toxic gas)
> terms. FED-based route cost is active when a `fed_model` is
> provided to `run_scenario`; otherwise `fed_rate_sampler` is `None`
> and only smoke influences route ranking.

## Stage graph

Routes are evaluated on a `StageGraph` -- a directed weighted graph
where nodes represent stages (distributions, checkpoints, exits).
The graph is built once at simulation start from the scenario
configuration.

```python
from pyfds_evac.core.route_graph import StageGraph

graph = StageGraph.from_scenario(
    direct_steering_info=stage_info,   # stage_id -> {polygon, stage_type}
    transitions=transitions,           # [{from, to}, ...]
    distributions=distributions,       # optional spawn areas
    walkable_polygon=walkable_polygon, # optional Shapely Polygon
)
```

### Graph construction without a journey

When a scenario defines no `transitions`, the stage graph wires itself by
stage type: spawn areas and crossings reach every crossing and every exit,
exits are terminal, and nothing points back at a spawn area. Crossings
therefore participate in cost-driven routing without a hand-authored journey.
In clear air the direct spawn-to-exit edge is cheapest, so agents take the
nearest exit and crossings sit inert; smoke can make a route through a
crossing cheaper.

Explicit `transitions` remain authoritative and skip this path entirely.

### Edge geometry

Edges carry a polyline that follows the corridor geometry computed
by JuPedSim's `RoutingEngine` at graph construction time. Smoke
and FED are sampled along this polyline, not along a straight
centroid-to-centroid ray. Edge weight is the polyline arc length.

When no walkable polygon is provided (e.g. in unit tests), edges
fall back to a straight centroid-to-centroid ray.

### Shortest-path queries

The graph provides Dijkstra-based shortest-path queries to find
reachable exits. When dynamic weights are provided, Dijkstra uses
smoke/FED-adjusted costs instead of static arc lengths:

```python
# All reachable exits with costs and paths
paths = graph.shortest_paths_to_exits(source="dist_1")

# Nearest exit only
result = graph.shortest_exit(source="dist_1")
if result:
    exit_id, cost, path = result
```

## Route cost evaluation

Each candidate route is scored by evaluating its segments (edges)
against current smoke conditions. The cost model combines path
length and smoke exposure (FED terms are supported but not currently
active — see note above).

### Segment evaluation

For each segment (edge between two stages), the system performs
the following steps:

1. Sample the extinction coefficient K along the edge polyline
   using the Beer-Lambert path-integrated mean
   ([Boerger et al. 2024](../materials/waypoint_based_visibility.pdf),
   Eq. 8-9).
2. Compute the smoke-adjusted speed factor from the mean K using
   the [smoke-speed model](smoke-speed-model.md).
3. Estimate the travel time from the segment length and reduced
   speed.
4. Optionally, estimate the FED growth along the segment from the
   FED rate at the polyline midpoint (by arc length) and the
   estimated travel time. (Active only when a `fed_model` is
   provided; otherwise `fed_rate_sampler` is `None`.)

### Line-of-sight extinction

The mean extinction along a segment is computed by sampling K at
uniform intervals along the edge polyline:

```
sigma_bar = (1 / |P|) * sum(K_p)
```

where `|P|` is the number of sample points and `K_p` is the
extinction at each point. The sample spacing is controlled by
`sampling_step_m` (default 2.0 m). This is the discrete form of
[Boerger et al. (2024)](../materials/waypoint_based_visibility.pdf),
Eq. 8-9.

### Arrival-time pricing

With `anticipate` (default `true`, and **independent of `cost_model`**),
each segment is priced at the time the agent would reach it rather than
the time it decides:

```
arrival_time = now + min(walked_so_far / base_speed_m_per_s,
                         foresight_horizon_s)
```

The unimpeded `base_speed_m_per_s` is used, not the smoke-reduced speed.
`foresight_horizon_s` defaults to infinity.

### Composite cost

The composite is the additive model's ranking number. It is still
computed and reported under the gate, where it does not rank:

```
composite = effective_length * (1 + w_smoke * K_ave) + w_fed * FED_max
```

where:

- `effective_length` is the route length measured from the agent's own
  position when one is supplied, otherwise the node-to-node path length
- `K_ave` is the length-weighted average extinction along the route
- `FED_max` is the projected cumulative FED at route completion
- `w_smoke` and `w_fed` are configurable weights

Exposure on the part of the first segment the agent has already walked
is credited out of `K_ave` and `FED_max`, because it is already carried
in `current_fed`.

### What each model ranks on

Both models write a single `rank_cost` field, which ordering, the
exit-switch anchor and the same-exit path test all read:

| model | `rank_cost` | sort key |
|---|---|---|
| `"gate"` | `travel_time_s + w_queue * queue_time_s` | `(rejected, tier, tau, rank_cost, hops)` |
| `"additive"` | `composite_cost` | `(rejected, tier, 0.0, rank_cost, hops)` |

Under the gate the route's optical depth `tau = K_ave * L` leads the sort and
`rank_cost` breaks ties; under the additive model the `tau` slot is a constant
and `rank_cost` decides alone. The `tau` in the key is scaled by
`current_exit_discount` (0.9) for the exit the agent already heads for.

`rank_cost` is still what the exit-switch anchor and the same-exit path test
compare — a travel time under the gate. That the ordering and the anchor read
different quantities is a known defect; see
[route-cost-gate.md](route-cost-gate.md#known-limitations).

`tier` is 0 for every route unless `clean_extinction_threshold > 0` under the
gate, which is not the default; then a route whose smokiest leg is at or below
the threshold takes tier 0 and every other route takes tier 1. See
[the clean-exit tier](route-cost-gate.md#the-clean-exit-tier-off-by-default) for
what it does and why it ships off.

### Route rejection

A route is rejected under any of these conditions:

- `FED_max` exceeds `fed_rejection_threshold` (default 1.0) —
  evaluated per route inside `evaluate_route`. The threshold is
  asymmetric: a route to an exit that is *not* the agent's current one
  must come in under `fed_rejection_threshold * fed_return_margin`
  (0.9), so an agent flees a deadly exit at once but only switches onto
  a rival that is clearly safe.
- **Gate model only:** the route's optical depth `tau = K_ave * L_eff` exceeds
  `tau_max` (default 6). This test is asymmetric too: for an exit that is not
  the agent's current one the budget is `tau_max * tau_return_margin` (0.8), so
  switching needs a cleaner route than staying. `K_ave` is the length-weighted
  mean over the route's own polyline, and every exit is judged on it — see
  [route-cost-gate.md](route-cost-gate.md#optical-depth-what-it-measures-and-what-it-does-not).
  The rejection reason reads `tau 8.41 > 6.00 (K_ave 0.145 x 58.0 m)`.
- **Additive model only:** **all** of its segments have K ≥
  `visibility_extinction_threshold` **and** at least one other route has at
  least one visible segment — evaluated as a second pass in `rank_routes` after
  all routes are scored. This pass is skipped under the gate, where it was a
  second, hysteresis-free smoke criterion on top of the optical-depth test.

The last condition means a smoky-but-short route is only rejected
when a cleaner alternative exists. If every route is fully obscured,
none are visibility-rejected.

If all routes end up rejected, the least-bad one is un-rejected as a
fallback so the agent always has a path, and its reason is prefixed
`fallback: `. Under the gate the least-bad route is the one with the
lowest undiscounted `tau_route`, then the lowest `rank_cost`, with
`fallback_switch_margin` hysteresis on `k_max_route`; under the additive
model it is the lowest-composite route.

Rejections are never remembered. Each tick re-decides from the current
field, which is what lets the optical-depth criterion relax as an agent
closes on an exit — the distance in `tau` is the distance that remains.

### Configuration

`RouteCostConfig` controls all cost evaluation parameters. Every field
listed here is also readable from a scenario's `routing` block via
`RouteCostConfig.from_routing_params` — the full JSON key table is in
[route-cost-gate.md](route-cost-gate.md#configuration).

```python
from pyfds_evac.core.route_graph import RouteCostConfig

config = RouteCostConfig(
    cost_model="gate",                    # "gate" (default) or "additive"
    tau_max=6.0,                          # gate: optical depth budget K_ave * L
    tau_return_margin=0.8,                # gate: stricter budget for a rival exit
    current_exit_discount=0.9,            # gate: current exit's tau in the sort key
    tau_deadband=0.1,                     # gate: anchor deadband, as a fraction of tau_max
    clean_extinction_threshold=0.0,       # gate: clean-exit tier, 0 = off
    clean_exit_margin=0.1,                # gate: hysteresis on tier membership
    anticipate=True,                      # price segments at arrival time
    foresight_horizon_s=float("inf"),     # cap on anticipation (s)
    fallback_switch_margin=0.2,           # gate: all-refused hysteresis
    w_smoke=1.0,                          # smoke cost weight
    w_fed=10.0,                           # FED cost weight
    w_queue=0.0,                          # congestion weight (0 = off, the default)
    fed_rejection_threshold=1.0,          # reject if FED_max exceeds
    visibility_extinction_threshold=0.5,  # K threshold for visibility
    sampling_step_m=2.0,                  # ray sample spacing
    base_speed_m_per_s=1.3,               # clear-air walking speed
    alpha=0.706,                          # speed-law coefficient
    beta=-0.057,                          # speed-law coefficient
    min_speed_factor=0.1,                 # speed factor floor
    default_exit_capacity=1.3,            # fallback capacity (agents/s)
)
```

Two further fields exist on the dataclass but are **not** readable from
the `routing` block, so a scenario run always gets their defaults:
`fed_return_margin` (0.9) and `impassable_extinction_threshold` (3.0).

`w_smoke` and `w_fed` **no longer reach route choice under the gate.**
Since `0d9bf79` a gate run weights each Dijkstra edge by its own optical
depth, `k_avg * length` (plus a `1e-6 * length` floor that keeps a
clear-air graph from collapsing to all-zero weights). The composite is
still computed and reported; it does not rank, and it no longer picks
the path either. Under `"additive"` both weights are active as before.

### Congestion-aware routing

When `w_queue > 0`, an exit-congestion term enters the ranking. Under
the additive model it is converted to distance and added to the
composite:

```
queue_time     = N_exit / capacity
queue_distance = base_speed_m_per_s * queue_time
composite = path_length * (1 + w_smoke * K_ave)
          + w_fed * FED_max
          + w_queue * queue_distance
```

Under the gate the ranking number is a time, so the delay is added as a
time instead — `rank_cost = travel_time_s + w_queue * queue_time_s`.
Opting into congestion-aware routing therefore works under both models,
but `w_queue` is not the same quantity in the two: the additive form
carries the extra `base_speed_m_per_s` factor.

where:

- `N_exit` is the number of agents currently targeting that exit
- `capacity` is the exit's `capacity_agents_per_s` (default 1.3)
- `base_speed_m_per_s` converts queueing delay (seconds) into
  distance-equivalent cost (metres) so all terms share the same
  unit space

The queue term is applied at route-level ranking (Phase 3) only,
not in Dijkstra edge weights, because it is a per-exit constant
that cannot change which path is selected to a given exit.

**Congestion-aware routing is off by default** (`w_queue = 0`); set it in a
scenario's `routing` block to switch it on.

#### Why it is opt-in, and what 0.024 means

The term is `w_queue * v0 * N / c` with `N` a **global** tally of every agent
targeting the exit — where `v0` is the `base_speed_m_per_s` conversion constant
(not any agent's desired speed) and `c` is the exit's `capacity_agents_per_s`,
falling back to `default_exit_capacity`. With both at their 1.3 defaults the
penalty is simply
`w_queue * N` metres, so it grows without bound in the population while the
path-length differences it competes against are fixed by the geometry:

| N | `w_queue = 1.0` | `w_queue = 0.03` |
|---|---|---|
| 25 | 25 m | 0.8 m |
| 50 | 50 m | 1.5 m |
| 333 | 333 m | 10 m |

No constant is right at more than one crowd size. 1.0 puts 333 m on a door at
Station scale; the 0.03 that fixes that is inert in an ordinary room. So the
library ships no congestion weight at all, and the calibrated value lives with
the deck it was calibrated on. Issue #89 tracks replacing the global `N` with a
queue the agent can perceive, which would remove the scale dependence.

**`assets/station_fahy` currently ships `w_queue = 0.024`, not 0.03.** The 0.03
below was swept against a geometry whose doorways were narrower than the
building's; when the doorways were opened to their clear width the same sweep
scored 0.03 at 50.2 % and 0.024 at 53.0 % (seeds 420–422) against Fahy's 52.9 %.
The reasoning in this section is unchanged — only the fitted number moved.

**Two further caveats on that number.** The sweep was run under the additive
composite, where `w_queue` multiplies a *distance*
(`w_queue * base_speed_m_per_s * queue_time`). Under the default gate model it
multiplies a *time* (`w_queue * queue_time_s`, against travel time), which is a
different quantity, and no deck pins `cost_model` — so the Station deck now runs
under the gate with a weight fitted under the additive model. It has not been
re-swept there.

#### Provenance of the Station's queue weight

Calibrated, not conventional. The table below is the original sweep, which
selected 0.03; see the caveats above for why the deck now ships 0.024 and why
neither value has been re-fitted under the gate cost model.
`scripts/sweep_queue_weight.py` sweeps the
weight on `assets/station_fahy` with rerouting on, three seeds per
point, and scores each run with that asset's own `validate.py`. The
front-door share falls monotonically with `w_queue`:

| `w_queue` | front-door share | mean row deviation |
|---|---|---|
| 0 | 65.9 % | 18.2 % |
| **0.03** | **53.3 %** | **17.9 %** |
| 0.05 | 48.4 % | 18.0 % |
| 0.1 | 44.9 % | 18.9 % |
| 1.0 | 22.9 % | 21.8 % |

Fahy, Proulx & Flynn measured 52.9 % of door users at the front door,
so `w_queue = 0.03` reproduces the Station's aggregate exit split and
the previous default of `1.0` did not. The mean per-row deviation is
also lower, but it is nearly flat across 0.02–0.05 (17.1–18.0 %) while
the front-door share swings 58.1 % → 48.4 %, so the row structure
confirms that low weights beat 1.0 without discriminating 0.03 within
that band. The value is fixed by the aggregate target alone.

**This calibration holds at one crowd size.** The term is
`w_queue * v0 * N / c` (`v0`, `c` as above) with `N` a global tally, so its
magnitude
relative to the path-length differences it competes with grows linearly
with the population — 0.03 was fitted at the Station's 333 agents, and
a scenario an order of magnitude smaller wants a correspondingly larger
weight to express the same preference. That scale dependence is a
property of the global-`N` form rather than of this number; a queue an
agent could actually perceive would not have it.

Exit capacity can be configured per exit in the scenario config:

```json
{
  "exits": {
    "exit_1": {
      "capacity_agents_per_s": 2.5
    }
  }
}
```

When not specified, the default from
`RouteCostConfig.default_exit_capacity` (1.3 agents/s) is used.

This approach is inspired by the game-theoretic exit selection
model of Ehtamo et al. (2010), where each agent minimises
estimated evacuation time (queueing + walking). The staggered
reevaluation schedule provides natural convergence to Nash
equilibrium without explicit iteration.

## Dynamic rerouting

During simulation, agents periodically reevaluate their routes and
switch to lower-cost exits when conditions change.

### Reevaluation scheduling

Each agent has a personal time offset derived from its ID so that
not all agents reevaluate on the same timestep:

```
offset = (agent_id % steps_per_interval) * dt_s
```

An agent fires its **first** evaluation once `current_time >= offset`,
then fires again every `reevaluation_interval_s` thereafter. With a
10-second interval and 100 agents the load is spread uniformly across
the interval.

### Rerouting decision flow

`evaluate_and_reroute` runs once per agent per reevaluation tick:

```
1. Resolve source node
   ├─ use current_origin  (stage the agent is coming from)
   └─ fall back to current_target_stage
   → if source not in graph → skip (return None)

2. rank_routes(source, t, FED, K_field)
   ├─ evaluate all edges → dynamic costs from current smoke/FED
   │   (gate: k_avg * length + 1e-6 * length, the edge's own optical depth;
   │    additive: w_smoke / w_fed weighted composite)
   ├─ Dijkstra with dynamic weights → one minimum-cost path per reachable exit
   │   (only the single lowest-cost path to each exit under these weights
   │    is evaluated; alternative paths to the same exit are not enumerated)
   ├─ evaluate_route on each path
   │   ├─ FED rejection (asymmetric: x fed_return_margin for a non-current exit)
   │   └─ gate only: optical-depth rejection, reason "tau ...", every exit
   │       tested (asymmetric: budget x tau_return_margin for a non-current
   │       exit)
   ├─ visibility rejection pass (additive only)
   │   └─ if ≥1 route has any visible segment:
   │       mark routes where ALL segments are non-visible as rejected
   ├─ sort: non-rejected first, rejected last
   │   └─ gate     → (rejected, tier, tau x current_exit_discount, rank_cost, hops)
   │       additive → (rejected, tier, 0.0, rank_cost, hops)
   │       tier splits clean from smoky only when the gate runs with
   │       clean_extinction_threshold > 0 (not the default)
   └─ if all rejected → un-reject the least-bad route as fallback
       ├─ gate     → by (tau_route, rank_cost), held by fallback_switch_margin
       └─ additive → lowest composite

3. Pick best = ranked[0]
   └─ if best is hard-rejected (not a fallback) → skip (return None)

4. Compare best.exit_id to agent's current exit
   ├─ same exit → reroute only if the new path beats the path actually
   │   being walked by more than 10 % on rank_cost ("better_path"),
   │   else update the cached path silently and return None
   └─ different exit → exit-switch anchor, then reroute_agent(wait_info, best.path)
       ├─ candidates are tried in rank order; a promotion the anchor would
       │   refuse is skipped so it cannot hide the rest of the list
       ├─ anchor: adopt only if rank_cost < old_cost * exit_switch_anchor
       │   ├─ bypassed when the old exit is FED-lethal or impassably smoky
       │   └─ gate: bypassed when the rival is feasible, clearer in metres by
       │       the anchor margin, AND either a whole band clearer or clean
       │       while the current exit is not
       ├─ rewrite path_choices deterministically along new path
       ├─ retarget agent to first unvisited stage in new path
       └─ return RouteSwitch record
```

When `rank_routes` returns nothing at all — a discovery agent whose
known subgraph holds no exit — the agent is sent toward the nearest
unexplored frontier node instead of standing still (`explore`), or
patrols known nodes when its knowledge is exhausted (`wander`).

### When a switch is triggered

An exit switch is recorded when **all four** conditions hold:

1. The agent's reevaluation tick fires (staggered offset + interval).
2. `rank_routes` finds a best route that is not hard-rejected.
3. That best route leads to a **different exit** than the current one.
4. It clears the exit-switch anchor, or qualifies for one of the anchor
   bypasses (old exit FED-lethal or impassably smoky; or, under the gate, a
   feasible rival clearer in metres of sighting distance by the anchor margin
   *and* either a whole visibility band clearer or clean while the current exit
   is not).

No switch is recorded when:

- The agent has not yet reached its offset time.
- The source node is missing from the graph (e.g., agent is in a stage not included in the routing graph).
- All routes are hard-rejected and none was un-rejected as a fallback.
- The anchor holds the agent on its current exit.
- The best route leads to the same exit — though the path to it may
  still be rewritten, which is recorded as `better_path`.

### Route switch reasons

Each `RouteSwitch` record includes a `reason` field:

| Reason          | Condition                                                        |
|-----------------|------------------------------------------------------------------|
| `initial`       | Agent had no previous exit assignment                            |
| `smoke_reroute` | Best route is a different exit (lower `rank_cost`)               |
| `fallback`      | Best route was un-rejected as fallback (all routes rejected)     |
| `better_path`   | Same exit, but a path more than 10 % cheaper on `rank_cost`      |
| `explore`       | No exit known yet; heading to the nearest unexplored frontier    |
| `wander`        | Knowledge exhausted; patrolling known nodes                      |

### Segment caching

Route evaluation supports an optional `cached_segments` dictionary.
When provided, segment costs are cached by `(source, target)` key and
reused across route evaluations within the same timestep. This avoids
redundant extinction sampling when multiple candidate routes share
segments. Under `anticipate` the same edge on two routes is priced at
two different arrival times, so the key becomes
`(source, target, round(arrival_time_s))`. The re-measured first leg of
a position-aware route is deliberately not cached: it belongs to one
agent's position, and the cache is shared across agents in a pass.

```python
cache: dict[SegmentCacheKey, SegmentCost] = {}
ranked = rank_routes(
    graph, source, time_s, current_fed,
    extinction_sampler, fed_rate_sampler, config,
    cached_segments=cache,
)
```

## Data structures

The routing module uses two main data structures for cost reporting.

### `SegmentCost`

Cost breakdown for one edge of a route:

| Field           | Type    | Description                             |
|-----------------|---------|-----------------------------------------|
| `source`        | `str`   | Source stage ID                         |
| `target`        | `str`   | Target stage ID                         |
| `length_m`      | `float` | Segment length (polyline arc length)     |
| `k_avg`         | `float` | Mean extinction along the segment       |
| `speed_factor`  | `float` | Speed multiplier from smoke law         |
| `travel_time_s` | `float` | Estimated travel time                   |
| `fed_growth`    | `float` | Estimated FED increase                  |
| `visible`       | `bool`  | Whether `k_avg` is below `visibility_extinction_threshold` |
| `k_max`         | `float` | Worst extinction sampled on the segment |
| `arrival_time_s`| `float` | Time the segment was priced at (see anticipation) |

### `RouteCost`

Full cost evaluation for one candidate route:

| Field              | Type                | Description                       |
|--------------------|---------------------|-----------------------------------|
| `exit_id`          | `str`               | Target exit stage ID              |
| `path`             | `list[str]`         | Stage IDs from source to exit     |
| `path_length_m`    | `float`             | Total path length                 |
| `k_ave_route`      | `float`             | Length-weighted mean extinction    |
| `travel_time_s`    | `float`             | Total estimated travel time       |
| `fed_max_route`    | `float`             | Projected cumulative FED          |
| `composite_cost`   | `float`             | Additive cost; reported but not ranking under the gate |
| `rank_cost`        | `float`             | The number ordering, the anchor and the same-exit test read |
| `segments`         | `list[SegmentCost]` | Per-segment breakdowns            |
| `queue_time_s`     | `float`             | Estimated queueing time at exit   |
| `k_max_route`      | `float`             | Worst extinction anywhere on the route. Reported; used only by the all-refused fallback's switch margin |
| `tau_route`        | `float`             | Route optical depth `k_ave_route * effective_length` (gate). Refuses the route, orders the survivors, and orders the all-refused fallback |
| `k_leg_max`        | `float`             | Extinction of the route's smokiest leg, each leg taken as its own mean. Decides clean-exit membership |
| `clean`            | `bool`             | Whether `k_leg_max` is within the clean-exit limit. Always `False` at the default `clean_extinction_threshold = 0.0` |
| `feasible`         | `bool`              | Optical depth and dose both allow the route (gate) |
| `rejected`         | `bool`              | Whether route was rejected        |
| `rejection_reason` | `str \| None`       | Reason for rejection; `fallback: ` prefix when un-rejected |

`rank_cost`, `k_max_route`, `tau_route` and `feasible` are all
written to the route-cost CSV (`run.py --output-route-cost-history`), so the
gate's decisions can be audited from its own output.

## References

- [route-cost-gate.md](route-cost-gate.md) -- the gate model: the
  optical-depth criterion, the ordering, the fallback, the full `routing`
  key table, and known limitations.
- [gate-model-review-notes.md](gate-model-review-notes.md) -- provenance
  against `materials/evac.f90` and the open questions.
- [FDS+Evac Technical Reference and User's Guide](../materials/FDS+EVAC_Guide.pdf)
  -- Korhonen (2021). Speed-reduction law and smoke-interaction model
  (Section 3.4).
- [Boerger et al. (2024)](../materials/waypoint_based_visibility.pdf)
  -- Beer-Lambert integrated extinction along line of sight (Eq. 8-9),
  waypoint-based visibility maps. Fire Safety Journal 150:104269.
- [Schroder et al. (2020)](../materials/Schroder2020.pdf) --
  Waypoint-based visibility and evacuation modeling.
- [Ronchi et al. (2013)](../materials/Ronchi2013.pdf) -- FDS+Evac
  evacuation model validation and verification.
- Ehtamo, H., Heliövaara, S., Korhonen, T. & Hostikka, S. (2010).
  Game theoretic best-response dynamics for evacuees' exit selection.
  *Advances in Complex Systems*, 13(1), 113–134.
