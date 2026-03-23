# Feature Specification: Smoke-Speed Model

**Feature Branch**: `001-smoke-speed-model`  
**Created**: 2026-03-23  
**Status**: Draft  
**Input**: User description: "Add smoke-speed model"

## Clarifications

### Session 2026-03-23

- Q: For SC-002 performance target (1000 agents in 100ms), what's the acceptable fallback when performance isn't met? → A: Simplify interpolation — if performance target not met, reduce interpolation complexity
- Q: For FR-007 missing data fallback, what's the priority behavior when visibility data is missing? → A: Interpolate from adjacent data points — system MUST use spatial and temporal interpolation to estimate visibility from adjacent grid points when data is missing for specific regions or time steps
- Q: What unit system should be used for visibility values? → A: Percentage clarity (0-100%) — visibility values represent clarity percentage where 0% = complete occlusion, 100% = clear air
- Q: How should visibility be interpolated for agents between grid points? → A: User-configurable — interpolation method (nearest neighbor, bilinear, bicubic) MUST be configurable in SmokeSpeedConfig with nearest neighbor as default for performance-critical deployments
- Q: What log level should boundary warnings use? → A: Metric/telemetry only — boundary warnings and speed clamping events MUST be exported as telemetry metrics rather than log entries

## User Scenarios & Testing

### User Story 1 - Compute smoke-affected agent speed (Priority: P1)

A simulation operator loads FDS fire simulation results and runs pedestrian evacuation with smoke-induced speed reduction. The system calculates each agent's desired speed based on local smoke visibility and emits updated trajectories with speed-history data.

**Why this priority**: This is the foundational smoke-speed model that enables realistic fire-evacuation simulation. Without it, agents move at constant maximum speed regardless of smoke conditions. This MVP delivers immediate value by incorporating smoke visibility effects on movement.

**Independent Test**: Can be fully tested by loading a precomputed FDS visibility map, running simulation with smoke-speed enabled, and verifying agents slow down in low-visibility zones while maintaining expected evacuation times. Delivers a complete smoke-aware simulation workflow.

**Acceptance Scenarios**:

  1. **Given** a valid FDS simulation directory with smoke data, **When** the simulation loads visibility fields, **Then** the system converts visibility values to percentage clarity (0-100%) format and reads all time-step smoke visibility values without errors
  2. **Given** an agent in a smoke-affected region with visibility below threshold (percentage clarity < c0), **When** speed is computed, **Then** the agent's desired speed is reduced proportionally to smoke density
  3. **Given** an agent in clear air with visibility above threshold (percentage clarity >= c0), **When** speed is computed, **Then** the agent moves at or near maximum speed
4. **Given** smoke visibility changes over time, **When** the simulation advances, **Then** agent speeds update accordingly for each time step

---

### User Story 2 - Validate smoke-speed boundaries (Priority: P2)

The system ensures smoke-speed calculations never produce physically impossible speeds (negative or excessively high) and exports boundary warning metrics when visibility data is out of expected range.

**Why this priority**: Safety and reliability. Invalid speeds break simulation integrity and can cause agents to teleport or stop entirely. Boundary validation prevents cascading errors while providing diagnostic information.

**Independent Test**: Can be tested independently by feeding extreme or corrupted visibility values and verifying speed outputs stay within reasonable bounds (0 to max_speed) with appropriate metrics exported.

**Acceptance Scenarios**:

  1. **Given** visibility value of zero (complete smoke occlusion, 0% clarity), **When** speed is computed, **Then** agent desired speed is exactly zero
  2. **Given** visibility value of 100% (clear air), **When** speed is computed, **Then** agent desired speed equals configured maximum speed
  3. **Given** visibility data contains NaN, negative, or out-of-range (>100%) values, **When** speed is computed, **Then** system exports boundary warning metrics and clamps values to 0-100% range before processing

---

### User Story 3 - Output speed-factor history (Priority: P3)

The simulation produces structured output files containing agent trajectories with speed-factor time-series, enabling post-simulation analysis of smoke exposure effects.

**Why this priority**: Analysis and validation. Operators need to verify smoke-speed effects occurred as expected and analyze patterns. This is critical for model validation but not required for first working iteration.

**Independent Test**: Can be tested by running a short smoke-speed simulation and verifying the output trajectory file contains additional columns or attributes tracking speed factors per agent per time step.

**Acceptance Scenarios**:

1. **Given** a completed simulation with smoke-speed model active, **When** trajectories are written, **Then** each agent's path includes speed-factor values at each recorded time step
2. **Given** speed-factor data, **When** an operator loads trajectories for analysis, **Then** they can correlate speed reductions with smoke visibility percentage (0-100%) at agent positions
3. **Given** speed-factor history, **When** export is requested, **Then** data can be saved in standard formats (CSV, SQLite with extended schema)

---

### Edge Cases

- What happens when FDS visibility data is missing for certain time steps or spatial regions?
- How does the system handle agents positioned outside the defined visibility map bounds?
- What occurs when smoke visibility oscillates rapidly between time steps?
- How are initial agent speeds handled during the pre-movement phase before smoke effects apply?

## Requirements

### Functional Requirements

- **FR-001**: System MUST load smoke visibility data from FDS simulation results stored in the configured simulation directory; visibility values MUST be converted to percentage clarity (0-100%) format for internal processing
- **FR-002**: System MUST compute agent desired speed as a continuous function of local smoke visibility, ensuring monotonic reduction from max_speed to zero as visibility decreases
- **FR-003**: System MUST provide configurable parameters for visibility threshold (c0), speed adjustment range, interpolation method selection (nearest neighbor, bilinear, bicubic), and visibility unit conversion (if FDS provides non-percentage units) that control the visibility-to-speed mapping function
- **FR-004**: System MUST update agent speeds at regular time intervals during simulation, using visibility data corresponding to the current simulation time
- **FR-005**: System MUST clamp computed speeds to valid physical bounds (0 ≤ speed ≤ max_speed) and export boundary warning metrics for visibility values that exceed valid range (outside 0-100%) before speed computation
- **FR-006**: System MUST output agent trajectories with speed-factor time-series data, either as extended attributes or separate history files
- **FR-007**: System MUST handle missing or corrupted visibility data gracefully using spatial and temporal interpolation to estimate visibility from adjacent grid points; fallback to zero speed only when interpolation fails completely

### Observability Requirements

- **OR-001**: System MUST export boundary warning metrics when visibility inputs exceed valid range (outside 0-100%) before speed computation
- **OR-002**: System MUST export speed clamping metrics when computed speeds are adjusted to stay within physical bounds (0 to max_speed)
- **OR-003**: System MUST export interpolation failure metrics when spatial/temporal interpolation cannot estimate visibility from adjacent data points

### Key Entities

- **SmokeVisibility**: Represents smoke density at a specific location and time, derived from FDS simulation output. Contains spatial coordinates (x, y, z), time stamp, and visibility value as percentage clarity (0-100%). Used to look up local smoke conditions for speed calculation. 0% = complete occlusion (zero visibility), 100% = clear air (maximum visibility).

- **SpeedFactor**: A normalized value between 0 and 1 representing the multiplier applied to an agent's maximum speed based on local smoke visibility. A factor of 0 means agent cannot move (complete occlusion), 1 means agent moves at full speed (clear air).

- **VisibilityMap**: A time-series collection of smoke visibility measurements across a spatial domain, stored as percentage clarity values (0-100%). Provides efficient spatial and temporal interpolation to compute visibility at arbitrary agent positions and simulation times. Interpolation method MUST be configurable (nearest neighbor, bilinear, bicubic) in SmokeSpeedConfig with nearest neighbor as default for performance-critical deployments.

- **SmokeSpeedConfig**: Configuration parameters controlling smoke-speed behavior: visibility threshold (c0), maximum speed (v0), visibility range parameter for exponential decay, update frequency during simulation, and interpolation method selection (nearest neighbor, bilinear, bicubic with nearest neighbor as default). Configurable via configuration file or runtime API. All metrics MUST be tagged with simulation ID, agent ID, and time step for traceability.

## Success Criteria

### Measurable Outcomes

- **SC-001**: Agents in smoke-affected regions (visibility < c0 threshold, where c0 is a percentage clarity value) achieve 50% lower average speed compared to clear-air agents
- **SC-002**: Smoke-speed model completes speed computation for 1000 agents within 100ms per time step on standard hardware; if target not met, interpolation complexity MUST be reduced (e.g., switch from bicubic to bilinear or nearest neighbor)
- **SC-003**: Speed calculations produce valid physical bounds (0 to max_speed) for 100% of agent updates during smoke simulation; visibility inputs MUST be validated and clamped to 0-100% range
- **SC-004**: Trajectory output files include speed-factor data with less than 5% missing values for agents that remain in the simulation domain
- **SC-005**: System delivers smoke-speed simulation results within 2x the runtime of the baseline (non-smoke) simulation on identical hardware
- **SC-006**: Boundary warnings and speed clamping events are exported as telemetry metrics with at least 95% delivery reliability

### Validation Metrics

- Smoke-speed correlation: Speed reduction factor should correlate positively with smoke visibility percentage (0-100%, higher clarity → higher speed)
- Boundary compliance: 0% visibility must produce zero speed; 100% visibility must produce max speed
- Temporal consistency: Speed updates should not cause discontinuous agent motion artifacts

## Assumptions

- FDS smoke visibility data follows standard fdsvismap output format with spatial grids and time series; values MUST be converted to percentage clarity (0-100%) for internal processing
- Smoke visibility effects dominate other factors in speed computation (crowd pressure, terrain, etc. are simplified or handled by underlying JuPedSim model)
- Smoke concentration correlates inversely with visibility (higher smoke = lower percentage clarity)
- Standard human walking speed (1.0 m/s default) is appropriate max_speed baseline for evacuation scenarios
- Visibility thresholds (c0=50%) are derived from industry standards for safe navigation in smoke (50% clarity threshold)
- JuPedSim social force model accepts dynamic speed updates without stability issues
- Smoke data is available at uniform time intervals matching simulation time step
- Telemetry metrics are collected and exported through standard metrics pipeline (e.g., Prometheus, StatsD, or similar)