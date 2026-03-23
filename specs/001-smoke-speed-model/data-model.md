# Data Model: Smoke-Speed Model

## Overview

This document defines the structured data contracts for the smoke-speed model. All public functions accept and return these dataclasses or Pydantic models (Python 3.11+).

## High-Level Entities

### SmokeSpeedConfig

Configuration parameters for smoke-speed computation. All metrics MUST be tagged with simulation ID, agent ID, and time step for traceability.

```python
@dataclass
class SmokeSpeedConfig:
    """Configuration for smoke-speed model."""
    visibility_threshold: float  # c0: percentage clarity threshold (0-100), default 50.0
    max_speed: float  # v0: maximum agent speed (m/s), default 1.0
    visibility_range: float  # range parameter for exponential decay, default 2.0
    interpolation_method: InterpolationMethod  # nearest/bilinear/bicubic, default NEAREST
    update_interval: float  # seconds between speed updates, default 1.0
    simulation_id: str  # Unique identifier for this simulation run
```

**Validation rules**:
- `visibility_threshold` ∈ [0, 100]
- `max_speed` > 0
- `visibility_range` > 0
- `update_interval` > 0

**Relationships**:
- Consumed by: `VisibilitySampler`, `SpeedModel`, `TelemetryCollector`
- Created by: CLI or runtime configuration loader
- Used by: `AgentUpdater`, `SimulationRunner`

---

### VisibilityMap

Time-series collection of smoke visibility measurements across a spatial domain, stored as percentage clarity values (0-100%).

```python
@dataclass
class VisibilityGrid:
    """Single time-step visibility grid."""
    time: float  # seconds
    grid: np.ndarray  # 3D array [x, y, z] of visibility percentages (0-100)
    origin: Tuple[float, float, float]  # (x, y, z) corner of grid
    cell_size: Tuple[float, float, float]  # (dx, dy, dz) grid resolution

@dataclass
class VisibilityMap:
    """Time-series of visibility grids."""
    grids: List[VisibilityGrid]  # Sorted by time
    interpolation_method: InterpolationMethod  # Default method for sampling
    
    def sample(self, time: float, x: float, y: float, z: float = 0) -> float:
        """Sample visibility at arbitrary position and time via configured interpolation."""
```

**Validation rules**:
- `grids` sorted ascending by `time`
- All grids have identical spatial dimensions
- All visibility values ∈ [0, 100]

**Relationships**:
- Consumed by: `VisibilitySampler`, `TemporalInterpolator`
- Created by: `FdsLoader` (from FDS files)
- Used by: `AgentUpdater` → `VisibilitySampler`

---

### SpeedFactor

Normalized value between 0 and 1 representing the multiplier applied to an agent's maximum speed based on local smoke visibility.

```python
@dataclass
class SpeedFactor:
    """Computed speed factor for an agent at a specific time."""
    agent_id: int
    time: float
    factor: float  # 0-1 normalized speed factor
    visibility_at_position: float  # percentage clarity (0-100) at agent position
    raw_visibility: float  # raw FDS visibility before conversion
    
    @property
    def speed(self, max_speed: float) -> float:
        """Compute actual speed given maximum speed."""
        return self.factor * max_speed
```

**Validation rules**:
- `factor` ∈ [0, 1]
- `visibility_at_position` ∈ [0, 100]

**Relationships**:
- Consumed by: `TrajectoryWriter`, analysis tools
- Created by: `SpeedModel`
- Used by: `AgentUpdater` (to set `agent.model.desiredSpeed`)

---

### AgentFireState

Tracking state for smoke-affected agents during simulation.

```python
@dataclass
class AgentFireState:
    """Per-agent smoke exposure state."""
    agent_id: int
    last_speed_update: float  # time of last speed computation
    speed_history: List[SpeedFactor]  # time-series of speed factors
    min_visibility_seen: float  # minimum visibility encountered (0-100)
    max_visibility_seen: float  # maximum visibility encountered (0-100)
```

**Relationships**:
- Consumed by: `SimulationRunner` (state management)
- Created by: `SimulationRunner` on agent creation
- Used by: telemetry for exposure analysis

---

### TelemetryEvent

Structured metric event for boundary warnings, speed clamping, and interpolation failures.

```python
from enum import Enum

class TelemetryEventType(Enum):
    BOUNDARY_WARNING = "boundary_warning"  # visibility out of range
    SPEED_CLAMPING = "speed_clamping"  # speed adjusted to bounds
    INTERPOLATION_FAILURE = "interpolation_failure"  # interpolation could not estimate

@dataclass
class TelemetryEvent:
    """Structured telemetry event."""
    event_type: TelemetryEventType
    simulation_id: str
    agent_id: int
    time_step: float
    value: float  # raw value triggering event
    details: Dict[str, Any]  # event-specific metadata
```

**Example events**:
```python
# Visibility out of range (e.g., -5% or 150%)
TelemetryEvent(
    event_type=TelemetryEventType.BOUNDARY_WARNING,
    simulation_id="sim_001",
    agent_id=42,
    time_step=123.45,
    value=-5.0,
    details={"reason": "visibility_negative"}
)

# Speed clamped to max_speed
TelemetryEvent(
    event_type=TelemetryEventType.SPEED_CLAMPING,
    simulation_id="sim_001",
    agent_id=42,
    time_step=123.45,
    value=1.2,  # computed speed exceeded max_speed
    details={"clamped_to": 1.0, "reason": "exceeded_max_speed"}
)
```

**Relationships**:
- Consumed by: `TelemetryCollector`, export sinks
- Created by: `TelemetryCollector` (via `record_*` methods)
- Used by: telemetry sinks (file, StatsD, Prometheus)

---

### InterpolationMethod

Enum for interpolation methods (configurable per spec FR-003).

```python
from enum import Enum

class InterpolationMethod(Enum):
    NEAREST = "nearest"  # Nearest neighbor (fastest, default)
    BILINEAR = "bilinear"  # Bilinear interpolation
    BICUBIC = "bicubic"  # Bicubic interpolation (highest quality)
```

**Relationships**:
- Referenced by: `SmokeSpeedConfig`, `VisibilityMap`
- Used by: `VisibilitySampler` to select interpolation algorithm

---

## Data Flow

```
FDS Files (fdsvismap)
    ↓
FdsLoader.read_fds_data()
    ↓
VisibilityMap (percentage clarity 0-100%)
    ↓
VisibilitySampler.sample(time, x, y)
    ↓
Visibility at position (float 0-100)
    ↓
SpeedModel.visibility_to_speed(visibility, config)
    ↓
SpeedFactor (factor 0-1)
    ↓
AgentUpdater.update(agent, speed_factor)
    ↓
agent.model.desiredSpeed = speed_factor * config.max_speed
```

## Serialization

### JSON (for API exchange)

```python
# VisibilityMap serialization
{
    "grids": [
        {
            "time": 0.0,
            "grid": [[...]],  # Base64 encoded numpy array
            "origin": [0.0, 0.0, 0.0],
            "cell_size": [0.5, 0.5, 0.5]
        }
    ],
    "interpolation_method": "nearest"
}

# SpeedFactor serialization
{
    "agent_id": 42,
    "time": 123.45,
    "factor": 0.65,
    "visibility_at_position": 32.5,
    "raw_visibility": 0.45
}
```

### SQLite (for trajectory storage)

```sql
-- Extension to jupedsim trajectory table
ALTER TABLE trajectory ADD COLUMN speed_factor REAL;
ALTER TABLE trajectory ADD COLUMN visibility_at_position REAL;
ALTER TABLE trajectory ADD COLUMN raw_visibility REAL;

-- Telemetry events table
CREATE TABLE telemetry_events (
    id INTEGER PRIMARY KEY,
    simulation_id TEXT NOT NULL,
    agent_id INTEGER NOT NULL,
    time_step REAL NOT NULL,
    event_type TEXT NOT NULL,
    value REAL NOT NULL,
    details TEXT  -- JSON blob
);
```

## Validation Utility

```python
# pyfdsevac/data_models.py
def validate_visibility_map(vm: VisibilityMap) -> List[str]:
    """Validate VisibilityMap, return list of error messages (empty if valid)."""
    errors = []
    
    if not vm.grids:
        errors.append("VisibilityMap has no grids")
        return errors
    
    # Check sorted time
    times = [g.time for g in vm.grids]
    if times != sorted(times):
        errors.append("VisibilityGrids not sorted by time")
    
    # Check visibility ranges
    for i, grid in enumerate(vm.grids):
        if grid.grid.min() < 0 or grid.grid.max() > 100:
            errors.append(f"Grid {i} has visibility values outside [0, 100]")
    
    return errors
```
