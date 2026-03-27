# Smoke-aware routing

> Part of [pyFDS-Evac](../README.md).

The pyFDS-Evac routing system implements dynamic, smoke-aware path
planning. Agents evaluate candidate routes based on smoke exposure
and periodically reroute to lower-cost paths as conditions change.

> **Note:** The cost model also supports a FED (toxic gas dose)
> component, but the simulation loop currently passes
> `fed_rate_sampler=None`, so FED does not influence route ranking
> at runtime. The descriptions below note where FED terms exist in
> the cost model but are inactive.

## Stage graph

Routes are evaluated on a `StageGraph` -- a directed weighted graph
where nodes represent stages (distributions, checkpoints, exits) and
edge weights are Euclidean distances between stage centroids. The graph
is built once at simulation start from the scenario configuration.

```python
from pyfds_evac.core.route_graph import StageGraph

graph = StageGraph.from_scenario(
    direct_steering_info=stage_info,   # stage_id -> {polygon, stage_type}
    transitions=transitions,           # [{from, to}, ...]
    distributions=distributions,       # optional spawn areas
)
```

### Shortest-path queries

The graph provides Dijkstra-based shortest-path queries to find
reachable exits:

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
against current smoke conditions. The cost model combines path length
and smoke exposure (plus an inactive FED term — see note above).

### Segment evaluation

For each segment (edge between two stages), the system performs
the following steps:

1. Sample the extinction coefficient K along the line of sight
   between stage centroids using the Beer-Lambert path-integrated
   mean
   ([Boerger et al. 2024](../materials/waypoint_based_visibility.pdf),
   Eq. 8-9).
2. Compute the smoke-adjusted speed factor from the mean K using
   the [smoke-speed model](smoke-speed-model.md).
3. Estimate the travel time from the segment length and reduced
   speed.
4. Optionally, estimate the FED growth along the segment from the
   FED rate at the midpoint and the estimated travel time.
   *(Currently inactive: `fed_rate_sampler` is `None` at runtime,
   so `fed_growth` is always 0.)*

### Line-of-sight extinction

The mean extinction along a segment is computed by sampling K at
uniform intervals along the centroid-to-centroid ray:

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
    fed_rejection_threshold=1.0,          # reject if FED_max exceeds
    visibility_extinction_threshold=0.5,  # K threshold for visibility
    sampling_step_m=2.0,                  # ray sample spacing
    base_speed_m_per_s=1.3,               # clear-air walking speed
    alpha=0.706,                          # speed-law coefficient
    beta=-0.057,                          # speed-law coefficient
    min_speed_factor=0.1,                 # speed factor floor
)
```

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
   ├─ Dijkstra → one shortest path per reachable exit
   ├─ evaluate_route on each path (composite cost + rejection flags)
   │   (only the geometrically shortest path to each exit is scored;
   │    alternative paths to the same exit are not enumerated)
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
| `length_m`      | `float` | Euclidean segment length                |
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
