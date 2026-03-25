# Quickstart: Smoke-Speed Model

## Prerequisites

- Python 3.11+
- `jupedsim`, `fdsvismap`, `numpy` installed
- FDS simulation data directory with visibility output

## Installation

```bash
# Clone repository
git clone https://github.com/PedestrianDynamics/fds-evac.git
cd fds-evac

# Install dependencies
pip install -r requirements.txt

# Add pyfdsevac to Python path
export PYTHONPATH=$(pwd):$PYTHONPATH
```

## Basic Usage

### Python API

```python
from pathlib import Path
import jupedsim as jps
from src.core import ConstantExtinctionField, SmokeSpeedConfig, SmokeSpeedModel, load_scenario, run_scenario

scenario = load_scenario("assets/ISO-table21")
smoke_model = SmokeSpeedModel(
    ConstantExtinctionField(1.0),
    SmokeSpeedConfig(fds_dir=".", update_interval_s=0.1),
)
result = run_scenario(scenario, seed=420, smoke_speed_model=smoke_model)

print(f"Evacuation time: {result.evacuation_time:.1f}s")
print(f"Smoke samples: {len(result.smoke_history or [])}")
```

### CLI

```bash
# Run smoke-speed simulation with default config
python -m pyfdsevac.cli.main \
    --sim-dir fds_data \
    --output output_smoke.sqlite \
    --visibility-threshold 50.0 \
    --max-speed 1.0 \
    --interpolation-method nearest \
    --num-agents 100

# With custom interpolation (higher quality)
python -m pyfdsevac.cli.main \
    --sim-dir fds_data \
    --output output_smoke.sqlite \
    --visibility-threshold 50.0 \
    --max-speed 1.0 \
    --interpolation-method bilinear \
    --num-agents 100
```

## Key Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `visibility_threshold` | 50.0 | Clarity percentage below which speed reduction begins |
| `max_speed` | 1.0 | Maximum agent speed (m/s) |
| `visibility_range` | 2.0 | Exponential decay rate for speed calculation |
| `interpolation_method` | `nearest` | Spatial interpolation: `nearest`, `bilinear`, `bicubic` |
| `update_interval` | 1.0 | Seconds between speed updates |

## Interpolation Methods

| Method | Speed | Quality | Use Case |
|--------|-------|---------|----------|
| `nearest` | Fastest | Basic | Real-time simulations, many agents |
| `bilinear` | Medium | Good | Balanced accuracy/speed |
| `bicubic` | Slowest | Best | High-fidelity visualization |

**Performance target**: 1000 agents update in <100ms per time step (SC-002).

## Output Files

### Trajectory File (SQLite)

Extended with smoke-speed columns:

```sql
SELECT agent_id, time, x, y, speed_factor, visibility_at_position
FROM trajectory
WHERE agent_id = 42
ORDER BY time;
```

| Column | Type | Description |
|--------|------|-------------|
| `agent_id` | INTEGER | Agent identifier |
| `time` | REAL | Simulation time (seconds) |
| `x`, `y` | REAL | Agent position |
| `speed_factor` | REAL | Normalized speed (0-1) |
| `visibility_at_position` | REAL | Clarity percentage (0-100) |

### Telemetry Output (JSON)

```json
{
    "simulation_id": "uuid",
    "telemetry": {
        "boundary_warnings": 12,
        "speed_clamping_events": 45,
        "interpolation_failures": 0
    }
}
```

## Common Workflows

### Workflow 1: Compare Smoke vs No-Smoke

```python
# Run baseline (no smoke)
result_baseline = run_simulation(
    config=base_config,  # Without smoke-speed
    trajectory_file="baseline.sqlite"
)

# Run with smoke
result_smoke = run_smoke_simulation(
    config=smoke_config,
    trajectory_file="smoke.sqlite"
)

# Compare evacuation times
print(f"Baseline: {result_baseline.evacuation_time:.1f}s")
print(f"With smoke: {result_smoke.evacuation_time:.1f}s")
print(f"Delay: {result_smoke.evacuation_time - result_baseline.evacuation_time:.1f}s")
```

### Workflow 2: Sensitivity Analysis

```python
# Test different visibility thresholds
for threshold in [30.0, 50.0, 70.0]:
    config = SmokeSpeedConfig(
        visibility_threshold=threshold,
        max_speed=1.0,
        simulation_id=f"threshold_{threshold}"
    )
    result = run_smoke_simulation(config=config, ...)
    print(f"Threshold {threshold}%: evacuation = {result.evacuation_time:.1f}s")
```

### Workflow 3: Export to CSV

```python
import sqlite3
import pandas as pd

# Load trajectories from SQLite
conn = sqlite3.connect("output_smoke.sqlite")
df = pd.read_sql_query(
    "SELECT * FROM trajectory ORDER BY agent_id, time",
    conn
)

# Export to CSV
df.to_csv("trajectories.csv", index=False)
```

## Validation

### Check Visibility Map

```python
# Verify percentage clarity range
for grid in visibility_map.grids:
    assert grid.grid.min() >= 0, "Visibility below 0%"
    assert grid.grid.max() <= 100, "Visibility above 100%"
```

### Verify Speed Bounds

```python
# Speed should always be in [0, max_speed]
for speed_factor in speed_history:
    assert 0 <= speed_factor <= 1, "Speed factor out of bounds"
```

## Troubleshooting

### Error: "Visibility values outside [0, 100]"

**Cause**: FDS data not converted to percentage clarity.

**Fix**: Check FDS simulation parameters; ensure visibility output is normalized.

### Error: "Performance target missed"

**Cause**: Interpolation too slow for agent count.

**Fix**: Use `InterpolationMethod.NEAREST` (default) or reduce agent count.

### Error: "Interpolation failure"

**Cause**: Agent outside visibility map bounds.

**Fix**: Ensure agent positions within FDS grid extent; check simulation geometry.

## Next Steps

1. Review `specs/001-smoke-speed-model/research.md` for technical details
2. Check `specs/001-smoke-speed-model/data-model.md` for data structures
3. Run integration tests: `pytest tests/integration/test_smoke_speed_integration.py`
4. Contribute to `tasks.md` for implementation tasks
