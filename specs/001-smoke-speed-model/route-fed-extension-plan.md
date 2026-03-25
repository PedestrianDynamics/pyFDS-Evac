# Route And FED Extension Plan

**Branch**: `001-smoke-speed-model`  
**Date**: 2026-03-25

## Goal

Extend the existing smoke-speed and FED runtime on this branch with dynamic route reevaluation, door-level smoke/FED summaries, and route-switch events.

This plan treats `004-fed-tracking` and `003-route-decision` as requirement sources only. Implementation stays in the current `src/core` runtime.

## Scope

- Add periodic route reevaluation with a configurable interval.
- Compute candidate route summaries for exits and intermediate stages.
- Reject unsafe candidates using projected smoke/FED thresholds.
- Switch route targets dynamically during the run.
- Record diagnostics for candidate evaluation and route switches.

## Definitions

`K_ave_Door`
: Average extinction coefficient `K` sampled along the planned path from the agent's current position to a door candidate. Lower values mean better visibility and lower smoke burden.

`FED_max_Door`
: Projected cumulative FED when the agent reaches a door candidate. This is the agent's current cumulative FED plus the additional FED expected along the candidate path. Candidates with `FED_max_Door > 1.0` are rejected by default.

## Runtime Inputs

Add route reevaluation settings alongside the existing smoke/FED runtime options:

- `route_reevaluation_interval_s`
  Default `10.0`.
- `fed_rejection_threshold`
  Default `1.0`.
- `visibility_extinction_threshold`
  Default `0.5`.
- `route_sampling_step_m`
  Distance between smoke/FED samples along a candidate path.

These should be exposed first in `run.py`, then threaded into `run_scenario(...)`.

## Data Sources

- Use `fdsvismap` via the existing `ExtinctionField` in `src/core/smoke_speed.py` for extinction sampling and `K_ave_Door`.
- Use `fdsreader` via the existing `DefaultFedModel` in `src/core/fed.py` for FED-rate sampling and projected cumulative FED.
- Reuse the existing per-agent FED state already maintained in `src/core/scenario.py`.

## JuPedSim Strategy

Use the same core idea as the notebook proof of concept in `notebooks/fds-evac.ipynb`:

- ask the routing layer for the currently planned route to each candidate,
- compare route quality across candidates,
- switch the agent when a better route appears.

For the production path, prefer direct steering for execution:

- treat exits and intermediate stages as route candidates,
- reevaluate at a fixed interval and at stage boundaries,
- update the next target stage instead of relying only on static journey definitions.

Journey switching remains useful as a fallback for simple multi-exit cases, but direct steering should be the main integration point for multi-stage smoke-aware routing.

## Candidate Evaluation

For each agent at reevaluation time:

1. Enumerate reachable candidate routes.
2. Build the planned waypoint path to each candidate.
3. Sample extinction `K` along the path.
4. Sample FED inputs along the same path and estimate FED growth over travel time.
5. Compute:
   - `K_ave_Door`
   - `FED_max_Door`
   - `visible` flag based on `K < 0.5`
   - rejection reasons
6. Reject candidates that fail thresholds unless all candidates fail.
7. Rank remaining candidates and switch if the winner changed.

## Ranking Rules

Initial ranking policy:

1. reject `FED_max_Door > fed_rejection_threshold`
2. reject candidates with sustained non-visible path conditions when an acceptable visible path exists
3. among survivors, prefer lower `FED_max_Door`
4. break ties with lower `K_ave_Door`
5. break remaining ties with shorter path length / travel time

Fallback:

- If all candidates are poor, select the least bad physically reachable candidate and log the fallback reason.

## Implementation Slices

### Phase 1: Stabilize Smoke/FED Runtime

- Fix smoke-speed interaction with direct steering so smoke remains a multiplicative factor on top of checkpoint/stage speed changes.
- Add FED update throttling using `DefaultFedConfig.update_interval_s`.
- Keep these changes separate from route-switch logic so the baseline runtime is trustworthy.

This phase is directly informed by the PR review comments in review `#3994051570` and follow-up review `#4006348208`, especially the notes about smoke-speed being overwritten by `update_checkpoint_speed()` and FED sampling running every simulation iteration.

### Phase 2: Route Evaluation Primitives

- Add a route summary helper that accepts agent position, candidate path, current time, and current cumulative FED.
- Compute path length, travel-time estimate, `K_ave_Door`, and projected `FED_max_Door`.
- Add deterministic unit tests using constant extinction / constant FED fixtures.

### Phase 3: Dynamic Routing

- Add reevaluation scheduling via `route_reevaluation_interval_s`.
- Integrate candidate ranking into direct-steering target updates.
- Support route switching at stage boundaries and periodic checks.
- Record route-switch events with old candidate, new candidate, and metrics.

### Phase 4: Diagnostics

- Add per-candidate evaluation records.
- Add route-switch history output.
- Add summary metrics such as candidate rejection counts, switch counts, and fallback count.

## Suggested Code Locations

- `src/core/scenario.py`
  Main simulation loop, agent FED state, reevaluation timing, diagnostics.
- `src/core/direct_steering_runtime.py`
  Direct-steering target updates and route-switch integration.
- `src/core/smoke_speed.py`
  Extinction sampling reused for path summaries.
- `src/core/fed.py`
  FED projection reused for path summaries.
- `run.py`
  CLI parameters and export wiring.

## Testing Plan

- Unit tests for candidate summary math with constant extinction and constant FED models.
- Integration tests for:
  - smoke-free preferred route,
  - reroute under smoke,
  - candidate rejection when `FED_max_Door > 1.0`,
  - fallback when all candidates are poor.
- Regression test that smoke-speed and direct-steering speed modifiers combine correctly.
- Regression test that FED history sampling obeys configured update interval.

## Non-Goals For First Iteration

- Perfect continuous replanning on every simulation step.
- Complex interpolation upgrades beyond the current field samplers.
- Full replacement of journey-based routing everywhere in the runtime.

## Assumptions

- A 10 second default reevaluation interval is acceptable for the first implementation.
- `FED_max_Door` is interpreted as projected cumulative FED along the path to a candidate, not only at the final door coordinate.
- Direct steering is the preferred execution layer for multi-stage dynamic routing.
