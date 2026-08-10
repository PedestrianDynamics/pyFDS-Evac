# API Contracts: Smoke-Speed Model

## Overview

This document defines the public API contracts for the smoke-speed model. All functions MUST accept and return the dataclasses defined in `data-model.md`.

## Public Module Interface

### pyfdsevac.interfaces.api

Main entry point for smoke-speed model functionality.

```python
# pyfdsevac/interfaces/api.py

def run_smoke_simulation(
    sim_dir: str,
    config: SmokeSpeedConfig,
    walkable_area: Any,  # JuPedSim WalkableArea
    exits: List[Any],  # List of exit polygons
    spawning_areas: List[Any],  # List of spawning area polygons
    trajectory_file: str,
) -> SimulationResult:
    """
    Run a complete smoke-speed simulation.
    
    Args:
        sim_dir: Directory containing FDS simulation data
        config: SmokeSpeedConfig with all required parameters
        walkable_area: JuPedSim WalkableArea for agent movement
        exits: List of exit polygons
        spawning_areas: List of spawning area polygons
        trajectory_file: Path to output trajectory file
        
    Returns:
        SimulationResult with statistics and telemetry
        
    Raises:
        FileNotFoundError: If FDS data not found in sim_dir
        ValueError: If config validation fails
    """
    ...

def load_visibility_map(
    sim_dir: str,
    waypoints: List[Tuple[float, float, float]],
    times: List[float],
    interpolation_method: InterpolationMethod = InterpolationMethod.NEAREST,
) -> VisibilityMap:
    """
    Load FDS visibility data and create VisibilityMap.
    
    Args:
        sim_dir: Directory containing FDS simulation data
        waypoints: List of (waypoint_id, x, y) tuples
        times: List of time points for visibility computation
        interpolation_method: Default interpolation method for sampling
        
    Returns:
        VisibilityMap with percentage clarity values (0-100)
        
    Raises:
        FileNotFoundError: If FDS data not found
    """
    ...
```

**Contract guarantees**:
- `run_smoke_simulation()` always returns `SimulationResult` (never raises unhandled exceptions)
- `load_visibility_map()` validates all inputs before processing
- Both functions are idempotent (same inputs → same outputs)

---

## CLI Contract

### pyfdsevac.cli.main

Command-line interface using `argparse`.

```bash
# Run smoke-speed simulation
python -m pyfdsevac.cli.main \
    --sim-dir /path/to/fds/data \
    --output /path/to/output.sqlite \
    --visibility-threshold 50.0 \
    --max-speed 1.0 \
    --interpolation-method nearest \
    --num-agents 100

# Output format: JSON (structured)
{
    "simulation_id": "uuid",
    "num_agents": 100,
    "duration_seconds": 245.3,
    "telemetry": {
        "boundary_warnings": 12,
        "speed_clamping_events": 45,
        "interpolation_failures": 0
    }
}
```

**CLI flags**:
```python
parser = argparse.ArgumentParser(description="Run smoke-speed simulation")

# Required
parser.add_argument("--sim-dir", required=True, help="FDS simulation directory")
parser.add_argument("--output", required=True, help="Output trajectory file")

# Configuration
parser.add_argument("--visibility-threshold", type=float, default=50.0,
                    help="Visibility threshold (0-100%) for speed reduction")
parser.add_argument("--max-speed", type=float, default=1.0,
                    help="Maximum agent speed (m/s)")
parser.add_argument("--interpolation-method", 
                    choices=["nearest", "bilinear", "bicubic"],
                    default="nearest",
                    help="Spatial interpolation method")
parser.add_argument("--num-agents", type=int, default=40,
                    help="Number of agents to simulate")

# Output options
parser.add_argument("--telemetry-output", 
                    help="Telemetry output file (JSON)")
```

---

## Integration Contracts

### fields/sampler ↔ behavior/speed_model

**Contract**: `VisibilitySampler.sample()` returns visibility percentage (0-100), which `SpeedModel.visibility_to_speed()` consumes.

```python
# fields/sampler.py
class VisibilitySampler:
    def sample(self, time: float, x: float, y: float, z: float = 0) -> float:
        """Sample visibility at position, return percentage clarity (0-100)."""
        ...

# behavior/speed_model.py  
def visibility_to_speed(visibility_pct: float, config: SmokeSpeedConfig) -> float:
    """Convert percentage clarity to speed (m/s)."""
    ...
```

**Validation**: `visibility_pct` ∈ [0, 100] guaranteed by `VisibilitySampler`

---

### behavior/speed_model ↔ runtime/agent_updater

**Contract**: `SpeedModel` returns speed in [0, max_speed], which `AgentUpdater` applies to agents.

```python
# behavior/speed_model.py
@dataclass
class SpeedFactor:
    factor: float  # 0-1 normalized
    visibility_at_position: float  # 0-100 percentage
    
# runtime/agent_updater.py
class AgentUpdater:
    def update_agent_speed(self, agent: jps.Agent, speed_factor: SpeedFactor, config: SmokeSpeedConfig):
        """Apply speed factor to agent, clamp to [0, max_speed]."""
        speed = speed_factor.factor * config.max_speed
        agent.model.desiredSpeed = float(np.clip(speed, 0.0, config.max_speed))
```

**Validation**: `speed_factor.factor` ∈ [0, 1], final speed clamped to [0, max_speed]

---

### runtime/agent_updater ↔ runtime/simulation_runner

**Contract**: `AgentUpdater` provides per-agent speed updates, `SimulationRunner` orchestrates loop.

```python
# runtime/simulation_runner.py
class SimulationRunner:
    def __init__(self, config: SmokeSpeedConfig, agent_updater: AgentUpdater):
        self.config = config
        self.agent_updater = agent_updater
        
    def run(self, simulation: jps.Simulation) -> SimulationResult:
        """Run simulation loop, calling agent_updater per time step."""
        while simulation.elapsed_time() < self.config.max_time:
            # ... iteration logic ...
            self.agent_updater.update_all(simulation, time)
```

---

## Error Handling Contracts

### Input Validation

All public functions MUST validate inputs before processing and raise `ValueError` for invalid inputs:

```python
def validate_smoke_config(config: SmokeSpeedConfig) -> List[str]:
    """Return list of validation errors (empty if valid)."""
    errors = []
    if not (0 <= config.visibility_threshold <= 100):
        errors.append("visibility_threshold must be 0-100")
    if config.max_speed <= 0:
        errors.append("max_speed must be > 0")
    if config.visibility_range <= 0:
        errors.append("visibility_range must be > 0")
    return errors
```

### Telemetry Events

All telemetry events MUST include required tags:

```python
@dataclass
class TelemetryEvent:
    event_type: TelemetryEventType
    simulation_id: str  # Required
    agent_id: int  # Required
    time_step: float  # Required
    value: float  # Required
    details: Dict[str, Any]  # Optional, event-specific
```

---

## Performance Contracts

### SC-002: Performance Target

```python
# Contract: 1000 agents speed update in <100ms
def test_performance_target():
    config = SmokeSpeedConfig(num_agents=1000, interpolation_method=InterpolationMethod.NEAREST)
    start = time.perf_counter()
    run_simulation(config)
    elapsed_ms = (time.perf_counter() - start) * 1000
    assert elapsed_ms < 100.0, f"Performance missed: {elapsed_ms:.1f}ms"
```

**Fallback**: If target not met, reduce interpolation complexity (nearest neighbor default).

---

## Versioning

API contracts are versioned per semver:
- **MAJOR**: Breaking changes to data structures or function signatures
- **MINOR**: New optional parameters, new functions
- **PATCH**: Bug fixes, performance improvements

**Current version**: v1.0.0 (initial release)
