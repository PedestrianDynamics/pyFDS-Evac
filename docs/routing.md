# Smoke-aware routing

> Part of [pyFDS-Evac](../README.md).

The pyFDS-Evac routing system implements dynamic, smoke-aware path
planning. Agents evaluate candidate routes based on smoke exposure
and periodically reroute to lower-cost paths as conditions change.
Route costs are recomputed from current hazard fields at each
reevaluation tick, so the chosen path adapts as conditions evolve.

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

### Composite cost

The full route cost combines all segments:

```
composite = path_length * (1 + w_smoke * K_ave) + w_fed * FED_max
```

where:

- `K_ave` is the length-weighted average extinction along the route
- `FED_max` is the projected cumulative FED at route completion
- `w_smoke` and `w_fed` are configurable weights

### Route rejection

A route is rejected under either of these conditions:

- `FED_max` exceeds `fed_rejection_threshold` (default 1.0) —
  evaluated per route inside `evaluate_route`
- **All** of its segments have K ≥ `visibility_extinction_threshold`
  **and** at least one other route has at least one visible segment —
  evaluated as a second pass in `rank_routes` after all routes are scored

The second condition means a smoky-but-short route is only rejected
when a cleaner alternative exists. If every route is fully obscured,
none are visibility-rejected.

If all routes end up rejected (by either condition), the lowest-cost
rejected route is un-rejected as a fallback so the agent always has
a path.

### Configuration

`RouteCostConfig` controls all cost evaluation parameters:

```python
from pyfds_evac.core.route_graph import RouteCostConfig

config = RouteCostConfig(
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

### Congestion-aware routing

When `w_queue > 0`, an exit-congestion term is added to the
composite cost:

```
queue_distance = base_speed_m_per_s * N_exit / capacity
composite = path_length * (1 + w_smoke * K_ave)
          + w_fed * FED_max
          + w_queue * queue_distance
```

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

#### Why it is opt-in, and what 0.03 means

The term is `w_queue * v0 * N / c` with `N` a **global** tally of every agent
targeting the exit. With the default `v0` and capacity the penalty is simply
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
the deck it was calibrated on — `assets/station_fahy` sets `w_queue = 0.03` in
its own `routing` block. Issue #89 tracks replacing the global `N` with a queue
the agent can perceive, which would remove the scale dependence.

#### Provenance of the Station's 0.03

Calibrated, not conventional. `scripts/sweep_queue_weight.py` sweeps the
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
`w_queue * v0 * N / c` with `N` a global tally, so its magnitude
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
   ├─ Dijkstra with dynamic weights → one minimum-cost path per reachable exit
   │   (only the single lowest-cost path to each exit under these weights
   │    is evaluated; alternative paths to the same exit are not enumerated)
   ├─ evaluate_route on each path (composite cost + rejection flags)
   ├─ visibility rejection pass
   │   └─ if ≥1 route has any visible segment:
   │       mark routes where ALL segments are non-visible as rejected
   ├─ sort: non-rejected first (by composite cost), rejected last
   └─ if all rejected → un-reject least-cost route as fallback

3. Pick best = ranked[0]
   └─ if best is hard-rejected (not a fallback) → skip (return None)

4. Compare best.exit_id to agent's current exit
   ├─ same exit → update cached path silently, return None
   └─ different exit → reroute_agent(wait_info, best.path)
       ├─ rewrite path_choices deterministically along new path
       ├─ retarget agent to first unvisited stage in new path
       └─ return RouteSwitch record
```

### When a switch is triggered

A switch is recorded when **all three** conditions hold:

1. The agent's reevaluation tick fires (staggered offset + interval).
2. `rank_routes` finds a best route that is not hard-rejected.
3. That best route leads to a **different exit** than the current one.

No switch is recorded when:

- The agent has not yet reached its offset time.
- The source node is missing from the graph (e.g., agent is in a stage not included in the routing graph).
- All routes are hard-rejected (FED ≥ threshold and no visible fallback).
- The best route leads to the same exit (path may still be updated).

### Route switch reasons

Each `RouteSwitch` record includes a `reason` field:

| Reason          | Condition                                                        |
|-----------------|------------------------------------------------------------------|
| `initial`       | Agent had no previous exit assignment                            |
| `smoke_reroute` | Best route is a different exit (lower composite cost)            |
| `fallback`      | Best route was un-rejected as fallback (all routes rejected)     |

### Segment caching

Route evaluation supports an optional `cached_segments` dictionary.
When provided, segment costs are cached by `(source, target)` key and
reused across route evaluations within the same timestep. This avoids
redundant extinction sampling when multiple candidate routes share
segments.

```python
cache: dict[tuple[str, str], SegmentCost] = {}
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
| `visible`       | `bool`  | Whether K is below visibility threshold |

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
| `composite_cost`   | `float`             | Final cost used for ranking       |
| `segments`         | `list[SegmentCost]` | Per-segment breakdowns            |
| `queue_time_s`     | `float`             | Estimated queueing time at exit   |
| `rejected`         | `bool`              | Whether route was rejected        |
| `rejection_reason` | `str \| None`       | Reason for rejection              |

## References

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
