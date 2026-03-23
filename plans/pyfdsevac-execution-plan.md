# `pyfdsevac` Execution Plan From Current Prototype

## Summary
Evolve the current repo into a real `pyfdsevac` package in place, using the existing prototype code only as seed material. The first vertical slice is a local CLI-driven fire-aware run that loads FDS data, runs JuPedSim with smoke-based speed updates, and emits structured outputs. Route switching and FED tracking follow in later phases, but all new work should be organized under the target package layout from day one so the backend can later become a thin adapter.

## Implementation Changes
- Replace the current script-centric shape with a package layout rooted at `pyfdsevac/`, while keeping a thin temporary compatibility entrypoint if needed during migration.
- Move current responsibilities into stable modules:
  - `pyfdsevac/io`: FDS loading wrapper over `fdsvismap`, scenario loading, result writing.
  - `pyfdsevac/fields`: fire field models, sampling, coordinate alignment, door/path summaries.
  - `pyfdsevac/behavior`: smoke-speed model first, then routing and FED.
  - `pyfdsevac/runtime`: JuPedSim adapter, session loop, runner.
  - `pyfdsevac/interfaces`: stable Python API for external callers.
  - `pyfdsevac/cli`: command entrypoints.
- Treat current code as follows:
  - `src/fdstooling.py` becomes the initial basis for `io/fds_source.py` plus `fields/sampler.py`.
  - `src/jpstooling.py` becomes the initial basis for `runtime/jupedsim_adapter.py` and `behavior/speed.py`; routing logic stays but is isolated behind behavior/runtime boundaries.
  - `src/config.py` is replaced by explicit config/data models instead of a mutable object with embedded paths and geometry defaults.
  - `main.py` is decomposed; plotting/debug code is removed from the runtime path and kept only as optional tooling later.
- Define the first stable public interfaces early and keep them unchanged across phases:
  - `run_simulation(scenario, simulation_config, fire_config, fds_results_path) -> SimulationResult`
  - `load_fire_fields(fds_results_path, fire_config) -> FireFieldSeries`
- Phase order:
  1. Package skeleton, config/result models, and API contracts.
  2. FDS ingestion plus generic field sampling and coordinate alignment.
  3. JuPedSim runtime adapter and session loop.
  4. First vertical slice: smoke-speed updates only, exposed through CLI.
  5. Route-decision module with door/path summaries and route-switch events.
  6. FED accumulation and output history.
  7. Backend adapter that calls `pyfdsevac.interfaces`.
- First CLI milestone must support:
  - loading a normalized scenario file
  - loading FDS results offline
  - running JuPedSim with periodic fire updates
  - writing trajectories, speed-factor history, warnings, and diagnostics
- Explicit public data contracts to introduce:
  - `FireConfig`
  - `SimulationConfig`
  - `SimulationResult`
  - `AgentFireState`
  - `FireFieldFrame` / `FireFieldSeries`

## Test Plan
- Unit tests for:
  - FDS field discovery and failure handling
  - coordinate alignment and out-of-bounds behavior
  - field sampling by `(x, y, z, t)`
  - smoke-speed factor computation, bounds, and repeated-update stability
- Integration tests for:
  - CLI end-to-end run from scenario + FDS inputs to structured outputs
  - JuPedSim runtime session with periodic fire updates
  - later backend adapter calling the exact same `interfaces.run_simulation(...)` path
- Validation scenarios to add after the first CLI slice:
  - smoke-free baseline
  - smoke-induced slowdown without rerouting
  - rerouting when secondary path is safer
  - FED accumulation sanity checks
  - source-derived spot checks against FDS+Evac behavior

## Assumptions
- This repo is the implementation starting point; no separate repo split in v1.
- First shipped milestone is CLI-first, not backend-first.
- v1 scope is speed change, route change, and FED tracking; incapacitation stays out of scope.
- FDS results are consumed offline through `fdsvismap`.
- JuPedSim remains the simulation engine and is wrapped only inside `pyfdsevac/runtime`.
- Current prototype files are not preserved as public API; they are migration input only.
