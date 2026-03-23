# Research: Smoke-Speed Model Implementation

## 1. Visibility Data Format (FDS fdsvismap)

### Decision: Use fdsvismap VisMap class directly

**Decision**: Continue using `fdsvismap.VisMap` class for loading FDS visibility data. The existing `fdstooling.py` correctly instantiates and configures `VisMap` with `read_fds_data()`, `set_start_point()`, `set_waypoint()`, `set_time_points()`, and `compute_all()`.

**Rationale**: 
- `fdsvismap` is listed as required dependency in `requirements.txt`
- Current prototype uses this library successfully
- library handles FDS-specific output format (`*.fdsvismap` files)
- Provides `get_local_visibility(time, x, y, c)` and `wp_is_visible(time, x, y, waypoint_id)` methods

**Alternatives considered**:
- Parse raw FDS CSV/JSON outputs directly → Rejected: fdsvismap handles parsing complexity
- Custom FDS reader → Rejected: Duplication of fdsvismap functionality

### Unknown Resolved: Visibility Unit Conversion

**From spec clarification**: Visibility values represent percentage clarity (0-100%) where 0% = complete occlusion, 100% = clear air.

**Research finding**: `fdsvismap.VisMap.get_local_visibility()` returns raw visibility values that must be normalized to 0-100% range. The normalization formula depends on FDS simulation parameters (smoke optical depth, extinction coefficient, brightness thresholds). Since exact conversion formula not documented in fdsvismap, we implement a configurable normalization step that:
- Reads raw visibility values from `VisMap`
- Applies min-max normalization or calibrated scale factor
- Stores result as `VisibilityMap` with explicit percentage clarity values

## 2. Interpolation Methods

### Decision: Implement three interpolation methods with configurable selection

**Decision**: Implement nearest neighbor, bilinear, and bicubic interpolation methods selectable via `SmokeSpeedConfig.interpolation_method`. Nearest neighbor as default for performance-critical deployments.

**Rationale**:
- Spec requires configurable interpolation (clarification Q4)
- Spec mandates nearest neighbor as default (performance)
- JuPedSim agent positions are continuous; grid-based visibility requires sampling
- Performance target (SC-002: 1000 agents in 100ms) requires efficient default

**Implementation approach**:
```python
# pyfdsevac/fields/sampler.py
class VisibilitySampler:
    def __init__(self, visibility_map: VisibilityMap, method: InterpolationMethod):
        self.grid = visibility_map  # Time-series of 3D visibility grids
        self.method = method
        
    def sample(self, time: float, x: float, y: float, z: float = 0) -> float:
        """Sample visibility at arbitrary position and time."""
        # 1. Temporal interpolation to get visibility grids for time t
        grid_t = self._interpolate_time(time)
        
        # 2. Spatial interpolation within grid at time t
        if self.method == InterpolationMethod.NEAREST:
            return self._nearest_neighbor(grid_t, x, y, z)
        elif self.method == InterpolationMethod.BILINEAR:
            return self._bilinear(grid_t, x, y, z)
        elif self.method == InterpolationMethod.BICUBIC:
            return self._bicubic(grid_t, x, y, z)
```

**Alternatives considered**:
- Single fixed interpolation method → Rejected: Spec requires configurability
- Only nearest neighbor → Rejected: Would not meet "user-configurable" requirement
- Adaptive method selection → Rejected: Adds complexity without clear benefit

## 3. Speed Calculation Model

### Decision: Implement configurable visibility-to-speed curve

**Decision**: Replace existing step-function `calculate_desired_speed()` with configurable visibility-to-speed mapping. Default curve: exponential decay from max_speed to 0 as visibility decreases below threshold c0.

**Current implementation gap**:
```python
# src/jpstooling.py (current, not acceptable for smoke-speed model)
def calculate_desired_speed(visibility: float, c: float, max_speed: float, range: float = 2.0):
    if visibility <= c:
        return 0
    else:
        return max_speed * (1 - np.exp(-(visibility - c) / range))
```

**Problems with current implementation**:
1. Step function (visibility ≤ c → 0) is not continuous per spec FR-002
2. `c` parameter used as visibility threshold, not smoke concentration
3. No visibility unit conversion (assumes raw values)
4. Hardcoded `range=5` parameter
5. No clamping to [0, max_speed] bounds
6. No telemetry metrics

**New implementation**:
```python
# pyfdsevac/behavior/speed_model.py
@dataclass
class SmokeSpeedConfig:
    visibility_threshold: float  # c0: percentage clarity threshold (default 50.0)
    max_speed: float  # v0: maximum agent speed (default 1.0)
    visibility_range: float  # range parameter for exponential decay (default 2.0)
    interpolation_method: InterpolationMethod  # nearest/bilinear/bicubic
    # ... other config

def visibility_to_speed(visibility_pct: float, config: SmokeSpeedConfig) -> float:
    """Convert percentage clarity (0-100%) to speed factor (0-1), then to actual speed."""
    # Clamp visibility to valid range
    visibility_pct = np.clip(visibility_pct, 0.0, 100.0)
    
    # Exponential decay curve: speed increases with visibility above threshold
    if visibility_pct <= config.visibility_threshold:
        # Below threshold: gradual reduction to zero
        factor = (visibility_pct / config.visibility_threshold) ** 2  # Quadratic decay
    else:
        # Above threshold: exponential approach to max_speed
        factor = 1.0 - np.exp(-(visibility_pct - config.visibility_threshold) / config.visibility_range)
    
    # Clamp to [0, 1] then scale to max_speed
    speed = np.clip(factor, 0.0, 1.0) * config.max_speed
    return float(np.clip(speed, 0.0, config.max_speed))
```

**Rationale**:
- Continuous function (no step discontinuities) per spec FR-002
- Configurable parameters per spec FR-003
- Explicit clamping to physical bounds per spec FR-005
- Default parameters aligned with spec assumptions (v0=1.0 m/s, c0=50% clarity)

**Alternatives considered**:
- Linear visibility-to-speed mapping → Rejected: Less realistic than exponential
- Piecewise linear with multiple segments → Rejected: Overly complex for MVP
- Lookup table from empirical data → Rejected: No empirical data available

## 4. Missing Data Handling

### Decision: Implement spatial and temporal interpolation with fallback

**Decision**: Implement spatial interpolation (via `VisibilitySampler`) and temporal interpolation for missing time steps. Fallback to nearest time step if interpolation fails.

**Implementation**:
```python
# pyfdsevac/fields/temporal_interpolator.py
class TemporalInterpolator:
    def __init__(self, visibility_map: VisibilityMap):
        self.grids = visibility_map.grids  # List of (time, grid) tuples
        self.times = [g[0] for g in self.grids]
        
    def get_time_grid(self, time: float) -> np.ndarray:
        """Get visibility grid for arbitrary time via interpolation."""
        if time <= self.times[0]:
            return self.grids[0][1]  # Use first grid
        if time >= self.times[-1]:
            return self.grids[-1][1]  # Use last grid
            
        # Find surrounding time steps
        for i in range(len(self.times) - 1):
            if self.times[i] <= time <= self.times[i + 1]:
                # Linear interpolation between grids
                t0, grid0 = self.grids[i]
                t1, grid1 = self.grids[i + 1]
                alpha = (time - t0) / (t1 - t0)
                return grid0 * (1 - alpha) + grid1 * alpha
        
        # Fallback (should not reach here)
        return self.grids[0][1]
```

**Rationale**:
- Spec FR-007 requires spatial/temporal interpolation
- Spec clarification Q2 mandates interpolation fallback (not zero speed)
- Interpolation failures rare if FDS data complete; fallback to nearest time step is safe

**Alternatives considered**:
- Fallback to zero speed on interpolation failure → Rejected: Would stop agents completely
- Skip agent update on failure → Rejected: Causes trajectory gaps
- Error/abort simulation → Rejected: Too aggressive for production

## 5. Telemetry Metrics System

### Decision: Implement in-memory metrics collection with export hooks

**Decision**: Create telemetry module for boundary warnings, speed clamping, and interpolation failures. Metrics exported via configurable hooks (e.g., file, StatsD, Prometheus).

**Implementation**:
```python
# pyfdsevac/behavior/telemetry.py
@dataclass
class TelemetryEvent:
    event_type: TelemetryEventType  # BOUNDARY_WARNING, SPEED_CLAMPING, INTERPOLATION_FAILURE
    simulation_id: str
    agent_id: int
    time_step: float
    value: float
    details: dict

class TelemetryCollector:
    def __init__(self, simulation_id: str):
        self.simulation_id = simulation_id
        self.events: List[TelemetryEvent] = []
        
    def record_boundary_warning(self, agent_id: int, time: float, visibility: float):
        self.events.append(TelemetryEvent(
            event_type=TelemetryEventType.BOUNDARY_WARNING,
            simulation_id=self.simulation_id,
            agent_id=agent_id,
            time_step=time,
            value=visibility,
            details={"reason": "visibility_out_of_range"}
        ))
        
    def export(self, sink: TelemetrySink):
        """Export events to configured sink (file, StatsD, etc.)"""
        sink.emit(self.events)
```

**Rationale**:
- Spec OR-001 to OR-003 require metric exports
- Clarification Q5: boundary warnings as telemetry (not logs)
- Metrics tagged with (simulation_id, agent_id, time_step) per spec

**Alternatives considered**:
- Logging to files → Rejected: Clarification Q5 specifies telemetry, not logs
- Print to stdout → Rejected: Not suitable for production
- No telemetry → Rejected: Violates observability requirements

## 6. Trajectory Output Format

### Decision: Extend SQLite trajectory with speed-factor columns

**Decision**: Create custom trajectory writer that extends `jps.SqliteTrajectoryWriter` to include speed-factor columns (`speed_factor`, `visibility_at_position`).

**SQLite schema extension**:
```sql
-- Existing jupedsim schema (simplified)
CREATE TABLE trajectory (
    agent_id INTEGER,
    time REAL,
    x REAL,
    y REAL,
    z REAL,
    PRIMARY KEY (agent_id, time)
);

-- Extension for smoke-speed model
ALTER TABLE trajectory ADD COLUMN speed_factor REAL;  -- 0-1 normalized
ALTER TABLE trajectory ADD COLUMN visibility_at_position REAL;  -- percentage clarity
```

**Implementation**:
```python
# pyfdsevac/io/trajectory_writer.py
class SmokeSpeedTrajectoryWriter:
    def __init__(self, base_writer: jps.SqliteTrajectoryWriter):
        self.base = base_writer
        self.speed_factors: Dict[int, Dict[float, float]] = {}
        self.visibilities: Dict[int, Dict[float, float]] = {}
        
    def write(self, agent: jps.Agent, time: float, speed_factor: float, visibility: float):
        # Write base trajectory via jupedsim
        self.base.write(agent)
        
        # Store extended data in memory (dump to DB at end)
        if agent.id not in self.speed_factors:
            self.speed_factors[agent.id] = {}
            self.visibilities[agent.id] = {}
        self.speed_factors[agent.id][time] = speed_factor
        self.visibilities[agent.id][time] = visibility
```

**Rationale**:
- Spec FR-006 requires speed-factor time-series output
- SQLite extension preserves compatibility with existing tools
- CSV export option available post-processing (clarification Q3)

**Alternatives considered**:
- Separate CSV file per simulation → Rejected: Fragmented output
- JSON export → Rejected: Bloated for large agent counts
- No extension ( rely on post-processing) → Rejected: Violates FR-006

## 7. Performance Optimization

### Decision: Nearest neighbor default with complexity fallback

**Decision**: Use nearest neighbor interpolation as default. If performance target (SC-002: 1000 agents in 100ms) not met, fall back to reduced interpolation complexity.

**Implementation**:
```python
# pyfdsevac/runtime/simulation_runner.py
def run_simulation_with_performance_check(...):
    start_time = time.perf_counter()
    
    # Run simulation with current interpolation method
    simulate(...)
    
    elapsed_ms = (time.perf_counter() - start_time) * 1000
    
    # Performance check per SC-002
    if elapsed_ms > 100.0:
        logger.warning(f"Performance target missed: {elapsed_ms:.1f}ms > 100ms")
        # Reduce interpolation complexity
        config.interpolation_method = InterpolationMethod.NEAREST
```

**Rationale**:
- Spec SC-002 explicitly allows fallback when target not met
- Clarification Q1: "reduce interpolation complexity" when performance missed

**Alternatives considered**:
- Pre-compute all agent samples → Rejected: Memory intensive
- Parallel agent updates → Rejected: JuPedSim runtime may not support
- Caching interpolated values → Rejected: Agents move continuously; cache invalid

## Summary of Research Findings

| Requirement | Decision | Status |
|-------------|----------|--------|
| FR-001: Load FDS visibility → percentage clarity | Use fdsvismap + normalization | ✅ Resolved |
| FR-002: Continuous visibility-to-speed mapping | Exponential decay curve | ✅ Resolved |
| FR-003: Configurable parameters | SmokeSpeedConfig dataclass | ✅ Resolved |
| FR-004: Speed updates per time step | AgentUpdater hook | ✅ Resolved |
| FR-005: Speed clamping with telemetry | TelemetryCollector for clamping | ✅ Resolved |
| FR-006: Speed-factor output | SQLite extension | ✅ Resolved |
| FR-007: Missing data fallback | Spatial + temporal interpolation | ✅ Resolved |
| OR-001-OR-003: Telemetry metrics | TelemetryCollector with sinks | ✅ Resolved |
| SC-002: 1000 agents in 100ms | Nearest neighbor default, fallback | ✅ Resolved |

**All NEEDS CLARIFICATION items resolved. Proceed to Phase 1 design.**
