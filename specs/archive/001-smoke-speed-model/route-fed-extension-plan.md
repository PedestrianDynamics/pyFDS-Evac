# Route And FED Extension Plan

**Branch**: `001-smoke-speed-model`
**Date**: 2026-03-25
**Updated**: 2026-03-25

## Goal

Extend the existing smoke-speed and FED runtime with dynamic route reevaluation so agents prefer the shortest viable path to an exit, rerouting when smoke or toxic conditions degrade a route.

This plan treats `004-fed-tracking` and `003-route-decision` as requirement sources only. Implementation stays in the current `src/core` runtime.

## Design Principle

**Shortest path first, smoke-adjusted.**

Agents always target the shortest-path exit by default. When smoke or FED conditions degrade a route, the agent switches to the next-best viable route. This mirrors the real-world behavior observed in evacuations: people take the familiar/shortest route unless conditions force a change.

## Scope

- Build a stage graph from the existing journey/transition definitions.
- Default route selection: shortest path from agent position to an exit through the stage graph.
- Periodic reevaluation: score routes by smoke/FED conditions and switch when the current route becomes unviable.
- Record diagnostics for candidate evaluation and route switches.

## Definitions

`Stage Graph`
: A directed weighted graph where nodes are stages (distributions, checkpoints, exits) and edges are transitions. Edge weights represent Euclidean distance between stage centroids. Built once at simulation start from the journey/transition definitions already in `direct_steering_info` and `path_choices`.

`K_ave_Route`
: Average extinction coefficient `K` sampled along the planned path from the agent's current position through intermediate stages to an exit. Lower values mean better visibility.

`FED_max_Route`
: Projected cumulative FED when the agent reaches the exit via a candidate route. This is the agent's current cumulative FED plus the additional FED expected along the route. Candidates with `FED_max_Route > 1.0` are rejected by default.

`Route Cost`
: Composite score for ranking candidate routes: `cost = path_length * (1 + w_smoke * K_ave_Route) + w_fed * FED_max_Route`. Weights `w_smoke` and `w_fed` are configurable. The shortest clear-air route has the lowest cost.

## Runtime Inputs

Add route reevaluation settings alongside the existing smoke/FED runtime options:

- `route_reevaluation_interval_s`
  Default `10.0`. How often each agent reevaluates its route.
- `fed_rejection_threshold`
  Default `1.0`. Routes with projected `FED_max_Route` above this are rejected.
- `visibility_extinction_threshold`
  Default `0.5`. Per-segment K threshold for the "visible" flag.
- `route_sampling_step_m`
  Default `2.0`. Distance between smoke/FED samples along a candidate path.
- `w_smoke`
  Default `1.0`. Weight of smoke penalty in route cost.
- `w_fed`
  Default `10.0`. Weight of FED penalty in route cost.

These should be exposed first in `run.py`, then threaded into `run_scenario(...)`.

## Data Sources

### fdsvismap (primary for route visibility)

`fdsvismap.VisMap` provides the core visibility primitives used in the proof-of-concept notebook (`notebooks/fds-evac.ipynb`):

- **`vis.wp_is_visible(time, x, y, waypoint_id)`** — returns whether an agent at (x, y) can see waypoint `wp_id` through smoke at a given time. This is a line-of-sight check through the extinction field, not a simple distance threshold. This is the key primitive for route scoring.
- **`vis.get_local_visibility(time, x, y, c)`** — returns local visibility at a position. Used to compute cumulative visibility scores along a route.
- **`vis.get_distance_to_wp(x, y, waypoint_id)`** — Euclidean distance from agent to waypoint.
- **`vis.set_waypoint(x, y, c, alpha)`** — registers waypoints (stage centroids, exit points) for visibility queries. Must be called at setup time before `compute_all()`.
- **`vis.compute_all()`** — precomputes visibility for all registered waypoints at all configured time points. This is expensive but runs once.

The existing `ExtinctionField` in `src/core/smoke_speed.py` wraps `fdsvismap.VisMap` for per-agent extinction sampling (smoke-speed). For route evaluation, we additionally need the waypoint visibility API above.

### fdsreader (FED gas sampling)

- Use `fdsreader` via the existing `DefaultFedModel` in `src/core/fed.py` for FED-rate sampling and projected cumulative FED along routes.

### Existing runtime state

- Reuse the existing per-agent FED state already maintained in `src/core/scenario.py`.

### Setup requirement

At simulation start, register stage centroids and exit centroids as `fdsvismap` waypoints so that `wp_is_visible()` queries are available during route reevaluation. This matches the notebook pattern where waypoints are registered via `vis.set_waypoint()` before `vis.compute_all()`.

## JuPedSim Integration

The notebook proof-of-concept (`notebooks/fds-evac.ipynb`) demonstrates two key JuPedSim APIs for dynamic routing:

- **`jps.RoutingEngine(walkable_polygon)`** — computes geometric waypoint paths through the walkable area. Call `routing.compute_waypoints(agent_position, exit_centroid)` to get the path to each candidate exit.
- **`simulation.switch_agent_journey(agent_id, journey_id, stage_id)`** — switches an agent to a different journey/exit at runtime. This is how the notebook implements rerouting.

For the production path with direct steering, the equivalent is updating `agent_wait_info` to retarget the agent's stage sequence. Both mechanisms should be supported: `switch_agent_journey` for simple multi-exit cases and direct-steering retargeting for multi-stage routes through checkpoints.

The `RoutingEngine` should be created once at simulation start alongside the stage graph.

## Stage Graph Construction

Build the graph once at simulation start from existing data:

1. **Nodes**: every key in `direct_steering_info` (exits, checkpoints, zones, distributions).
2. **Edges**: from `path_choices` (already built by `build_agent_path_state`) and from the `transitions` list in the scenario JSON.
3. **Edge weight**: Euclidean distance between polygon centroids of the two stages.
4. **Exit nodes**: stages whose `stage_type == "exit"`.

The graph is static (topology does not change). Only the smoke/FED cost overlay changes over time.

### Shortest Path Baseline

At agent spawn, compute the shortest path (by Euclidean edge weight) from the agent's current stage to each reachable exit using Dijkstra. Assign the agent to the shortest-path exit. This replaces the current uniform-random or single-journey-based assignment for agents that have multiple reachable exits.

### Smoke-Adjusted Rerouting

At each reevaluation interval:

1. For each reachable exit, compute the route cost through the stage graph.
2. Route cost is the sum of edge costs, where each edge cost = `segment_length * (1 + w_smoke * K_avg_segment)`.
3. Add `w_fed * FED_max_Route` to the total.
4. Reject routes where `FED_max_Route > fed_rejection_threshold`.
5. Pick the lowest-cost surviving route.
6. If the winner differs from the current route, switch.

## Candidate Evaluation

Two complementary approaches, used together:

### Waypoint Visibility Scoring (from notebook proof-of-concept)

For each candidate route (agent → stages → exit):

1. Use `jps.RoutingEngine.compute_waypoints(agent_position, exit_centroid)` to get the geometric path.
2. Map path waypoints to the nearest registered `fdsvismap` waypoints (stage centroids).
3. For each waypoint on the path, call `vis.wp_is_visible(time, agent_x, agent_y, wp_id)` to check line-of-sight through smoke.
4. For visible waypoints, accumulate `vis.get_local_visibility(time, wp_x, wp_y, c)`.
5. The route's **visibility score** is the sum of local visibility at visible waypoints. Higher is better.

This is the same approach validated in `notebooks/fds-evac.ipynb`.

### Extinction and FED Sampling (for quantitative cost)

For each edge (stage A → stage B) in a candidate route:

1. Sample extinction `K` at `route_sampling_step_m` intervals along the centroid-to-centroid line.
2. Compute `K_avg_segment` as the mean of samples.
3. Estimate travel time as `segment_length / (v0 * speed_factor_from_extinction(K_avg_segment))`.
4. Estimate FED growth as `fed_rate_at_midpoint * travel_time_s`.

Sum across all edges to get `K_ave_Route`, total travel time, and `FED_max_Route`.

### Combined Scoring

The visibility score from `fdsvismap` and the extinction/FED cost are combined:
- `wp_is_visible` determines whether a route segment is passable (binary).
- `K_ave_Route` and `FED_max_Route` provide quantitative ranking among passable routes.
- A route where key waypoints are not visible through smoke is penalized even if average K is moderate (smoke may be concentrated at critical chokepoints).

## Ranking Rules

1. Reject routes where `FED_max_Route > fed_rejection_threshold`.
2. Reject routes where all segments are non-visible (`K > visibility_extinction_threshold`) when a visible route exists.
3. Among survivors, rank by `Route Cost` (lowest wins).
4. Break ties with fewer intermediate stages (simpler path preferred).

Fallback:
- If all routes are rejected, select the least-bad physically reachable route and log the fallback reason.

## Performance Strategy

Route reevaluation is the most expensive new operation. Budget: must not more than double the per-iteration overhead.

### First iteration: centroid-to-centroid sampling

- Sample smoke/FED only along straight lines between stage centroids, not along actual walked paths.
- Use `route_sampling_step_m = 2.0` (coarse) to limit sample count.
- Reevaluate every `route_reevaluation_interval_s` (default 10s = every 1000 iterations at dt=0.01), not every step.
- Stagger reevaluation across agents: agent reevaluates at `t = offset + n * interval` where `offset = (agent_id % interval_steps) * dt`. This spreads the cost across iterations.
- Cache route costs per edge per reevaluation epoch. Since smoke changes slowly relative to agent movement, edge costs computed for one agent can be reused for other agents evaluating the same edge in the same epoch.

### Performance limits (first iteration)

For N agents, M exits, P edges per route, S samples per edge:
- Per reevaluation: `M * P * S` extinction samples per agent.
- With caching: `total_edges * S` samples per epoch (shared across agents).
- Example: 30 agents, 3 exits, 5 edges/route, 10 samples/edge = 150 samples/epoch (cached), not 4500.

## Implementation Slices

### Phase 1: Stabilize Smoke/FED Runtime ✅ (done)

- Smoke-speed interaction with direct steering fixed: smoke is a multiplicative factor on top of checkpoint/stage speed changes.
- FED update throttling using `DefaultFedConfig.update_interval_s` is wired.
- Performance optimized: skip `update_checkpoint_speed` when no speed zones exist.

### Phase 2: Stage Graph, Routing Engine, and Shortest-Path Baseline

- Build the stage graph from `direct_steering_info` and transitions at simulation start.
- Create `jps.RoutingEngine(walkable_polygon)` at simulation start.
- Register stage centroids and exit centroids as `fdsvismap` waypoints via `vis.set_waypoint()`. Call `vis.compute_all()` after registration so `wp_is_visible()` is available at runtime.
- Implement Dijkstra shortest path from each distribution to each reachable exit.
- Assign agents to shortest-path exit at spawn (replace uniform-random fallback).
- Add `src/core/route_graph.py` with `StageGraph` class.
- Unit tests with known geometries verifying shortest path selection.

### Phase 3: Route Evaluation Primitives

- Add a route cost function that accepts agent position, candidate route (list of stages), current time, and current cumulative FED.
- Sample extinction along centroid-to-centroid segments.
- Compute `K_ave_Route`, estimated travel time, `FED_max_Route`, and composite `Route Cost`.
- Add edge cost caching with epoch invalidation.
- Deterministic unit tests using `ConstantExtinctionField`.

### Phase 4: Dynamic Rerouting

- Add reevaluation scheduling with agent-staggered offsets.
- At each reevaluation: score all reachable exits, apply ranking/rejection, switch if winner changed.
- Update `agent_wait_info` to retarget to the new exit's stage sequence.
- Record route-switch events: `(time, agent_id, old_exit, new_exit, old_cost, new_cost, reason)`.

### Phase 5: Diagnostics and Output

- Add per-candidate evaluation records (all scored routes, not just winner).
- Add route-switch history CSV output (`--output-route-history`).
- Add summary metrics: switch count, rejection count, fallback count per agent.

## Suggested Code Locations

- `src/core/route_graph.py` *(new)*
  Stage graph construction, Dijkstra, route cost evaluation, edge cost caching.
- `src/core/scenario.py`
  Main simulation loop: reevaluation scheduling, route-switch execution, diagnostics.
- `src/core/direct_steering_runtime.py`
  Target update when route switches: retarget `agent_wait_info` to new stage sequence.
- `src/core/smoke_speed.py`
  Extinction sampling reused for route edge costs.
- `src/core/fed.py`
  FED projection reused for route FED estimates.
- `run.py`
  CLI parameters and CSV export wiring.

## Testing Plan

- Unit tests for `StageGraph` construction and Dijkstra correctness.
- Unit tests for route cost computation with constant extinction and constant FED.
- Integration tests for:
  - smoke-free scenario: agents pick shortest-path exit,
  - reroute under smoke: agent switches to longer but clearer exit,
  - FED rejection: route with `FED_max_Route > 1.0` is rejected,
  - fallback: all routes bad, agent picks least-bad.
- Regression tests:
  - smoke-speed and direct-steering speed modifiers combine correctly,
  - FED history sampling obeys configured update interval,
  - HC scenario (30 agents, 3 exits) completes without performance regression.

## Limitations (First Iteration)

These are known simplifications. Each is a candidate for improvement in a second stage.

1. **Centroid-to-centroid paths only.** Route cost is computed along straight lines between stage centroids, not along the actual walked path through the geometry. This underestimates path length in complex geometries with corridors and corners.

2. **No geometric path planning.** The stage graph uses Euclidean distance, not navigable distance. Two stages separated by a wall will have a low Euclidean edge weight despite being far apart via walkable paths. This requires the scenario to define stages that are geometrically reachable from their neighbors.

3. **Line-of-sight via fdsvismap waypoints only.** `fdsvismap`'s `wp_is_visible()` provides line-of-sight checks, but only for pre-registered waypoints (stage centroids). Visibility to arbitrary points (e.g., other agents, arbitrary doors) requires additional waypoint registration at setup time. FDS+Evac performs continuous visibility checks; our model checks only at registered waypoints during reevaluation intervals.

4. **No agent-type differentiation.** FDS+Evac has conservative, active, herding, and follower agent types with different exit-selection strategies. Our model treats all agents identically.

5. **Static graph topology.** The stage graph is built once. If doors are dynamically blocked, the graph does not update. (Edge costs do update via smoke, but topological changes like a door closing are not modeled.)

6. **No crowd density in route cost.** Congestion at exits is not factored into route selection. A shorter route to a crowded exit may be worse than a longer route to an empty one.

7. **Coarse FED projection.** FED growth is estimated using the midpoint FED rate for each segment, assuming constant exposure. In reality, FED rate changes as the agent moves through varying gas concentrations.

8. **No hysteresis / switching penalty.** Agents may oscillate between two similarly-scored routes. A switching cooldown or hysteresis band should be added if oscillation is observed.

## Second Stage Improvements

Items to address after the first iteration is validated:

- **Navigable distance via JuPedSim routing mesh.** Replace Euclidean edge weights with actual walkable distances computed from the simulation geometry. This is the most impactful improvement for complex floor plans.
- **Continuous line-of-sight visibility.** Extend beyond waypoint-based `wp_is_visible()` to support visibility checks to arbitrary points (other agents, dynamic obstacles), closer to FDS+Evac's continuous visibility model.
- **Crowd-aware routing.** Factor exit congestion (queue length, flow rate) into route cost. Requires sampling agent density near exits.
- **Agent types.** Implement conservative/active/herding/follower differentiation per FDS+Evac section 3.5.
- **Switching hysteresis.** Add a cooldown period or cost margin before allowing a route switch, to prevent oscillation.
- **Adaptive reevaluation interval.** Shorten the interval when smoke conditions are changing rapidly (high dK/dt), lengthen when stable.
- **Multi-floor routing.** Extend the stage graph to support vertical connections (stairs, elevators) for multi-story buildings.
- **Smoke blocking.** Mark graph edges as blocked when extinction exceeds a high threshold for a sustained period, effectively removing the route.

## Assumptions

- A 10-second default reevaluation interval is acceptable for the first implementation.
- Centroid-to-centroid sampling is a reasonable approximation when stages are placed at navigable waypoints.
- The existing `direct_steering_info` and `path_choices` structures contain enough information to build the stage graph without additional user input.
- Direct steering is the preferred execution layer for multi-stage dynamic routing.
- Smoke fields change slowly enough that edge cost caching per reevaluation epoch is valid.
