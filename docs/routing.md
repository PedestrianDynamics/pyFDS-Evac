# Smoke-aware routing

> Part of [pyFDS-Evac](../README.md).

The pyFDS-Evac routing system implements dynamic, smoke-aware path
planning. Agents evaluate candidate routes based on smoke exposure and
toxic gas dose, and periodically reroute to lower-cost paths as
conditions change.

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
against current smoke conditions. The cost model combines three
factors: path length, smoke exposure, and toxic gas dose.

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

- `FED_max` exceeds `fed_rejection_threshold` (default 1.0)
- All segments are non-visible (K above
  `visibility_extinction_threshold`) while another route has
  visibility

If all routes are rejected, the least-bad route is un-rejected as a
fallback so the agent always has a path.

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

Reevaluation is staggered across agents to spread computational cost.
Each agent receives a time offset computed from its ID:

```python
from pyfds_evac.core.route_graph import compute_eval_offset

offset = compute_eval_offset(agent_id=42, interval_s=10.0, dt_s=0.01)
```

An agent reevaluates when `current_time - last_eval_time >= interval`.
With a 10-second interval and 100 agents, roughly 10 agents
reevaluate per second.

### Rerouting flow

The `evaluate_and_reroute` function handles the full rerouting cycle
for one agent:

1. Determine the agent's current position in the stage graph.
2. Rank all routes from that position using `rank_routes`.
3. If the best route leads to a different exit, reroute the agent
   by updating its path choices and target stage.
4. Return a `RouteSwitch` record for diagnostics, or `None` if no
   switch occurred.

```python
from pyfds_evac.core.route_graph import (
    evaluate_and_reroute,
    RerouteConfig,
    AgentRouteState,
)

reroute_config = RerouteConfig(
    reevaluation_interval_s=10.0,
    cost_config=cost_config,
)

switch = evaluate_and_reroute(
    agent_id=42,
    wait_info=agent_wait_info,
    route_state=agent_route_state,
    graph=graph,
    current_time_s=30.0,
    current_fed=0.3,
    extinction_sampler=extinction_field,
    fed_rate_sampler=fed_model,
    config=reroute_config,
)
```

### Route switch reasons

Each `RouteSwitch` record includes a `reason` field:

| Reason           | Description                                |
|------------------|--------------------------------------------|
| `initial`        | First route assignment (no previous exit)  |
| `smoke_reroute`  | Switched to a lower-cost exit due to smoke |
| `fallback`       | All routes rejected; using least-bad option|

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
