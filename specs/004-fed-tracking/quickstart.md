# FED Tracking: Quickstart

**Feature**: FED Tracking  
**Branch**: 004-fed-tracking  
**Created**: 2026-03-23

---

## Overview

This quickstart guide helps developers get up to speed with the FED tracking module.

---

## Key Concepts

### What is FED?

Fractional Effective Dose (FED) is a standardized measure of smoke exposure that combines the effects of carbon dioxide (CO₂) and carbon monoxide (CO) on human physiology. FED accumulates over time based on smoke concentration:

```
FED = ∫(CO₂ concentration × time) dt + ∫(CO concentration × time) dt
```

**ISO 13571 Thresholds**:
- FED < 1.0: Safe for evacuation
- FED = 1.0: Life-threatening exposure (evacuation timeout)
- FED > 1.0: Survival probability decreases

### Module Organization

```
pyfdsevac/
├── exposure/
│   ├── __init__.py          # Public API exports
│   ├── tracker.py           # Core tracking functions
│   ├── metrics.py           # Door-specific metrics
│   └── diagnostics.py       # Aggregate analysis
├── data_models.py           # Pydantic dataclasses
└── __init__.py              # Package exports
```

---

## Quick Start Examples

### Example 1: Track Pedestrian Exposure

```python
from pyfdsevac.exposure.tracker import track_exposure

# Pedestrian trajectory and smoke data
positions = [(0.0, 0.0), (1.5, 2.0), (3.0, 4.5)]
smoke_concentrations = [0.1, 0.3, 0.5]
time_steps = [0.0, 1.0, 2.0]

# Track FED exposure
fed_tracks = track_exposure(
    pedestrian_id="ped_001",
    positions=positions,
    smoke_concentrations=smoke_concentrations,
    time_steps=time_steps
)

# Result: List[PedestrianFEDTrack] with cumulative FED values
```

### Example 2: Record Door Metrics

```python
from pyfdsevac.exposure.metrics import record_door_metrics

# Pedestrian evaluates a door candidate
door_metrics = record_door_metrics(
    pedestrian_id="ped_001",
    door_id="door_exit_A",
    FED_max=0.8,
    K_ave=0.3,
    timestamp=2.5
)

# door_metrics.is_visible == True (K_ave < 0.5)
```

### Example 3: Generate Exposure Diagnostic

```python
from pyfdsevac.exposure.diagnostics import generate_diagnostic

# Compile all exposure data for pedestrian
diagnostic = generate_diagnostic(
    pedestrian_id="ped_001",
    fed_trajectory=fed_tracks,
    door_evaluations=door_metrics_list
)

# diagnostic includes:
# - peak_FED, total_exposure_time
# - Complete FED trajectory
# - All door evaluation metrics
```

### Example 4: Route Candidate Evaluation

```python
from pyfdsevac.exposure.routing_integration import evaluate_candidate_with_fed

# Check if door candidate passes FED threshold
is_acceptable = evaluate_candidate_with_fed(
    candidate_metrics=door_metrics,
    fed_threshold=1.0  # ISO 13571 safe limit
)

# Returns True if FED_max_Door <= 1.0
```

---

## Data Model Reference

### PedestrianFEDTrack

Track cumulative exposure per time step:
- `pedestrian_id`: Unique identifier
- `timestamp`: Simulation time
- `cumulative_FED`: Total FED at this time
- `fed_rate`: FED increase this step
- `smoke_concentration`: Local smoke level

### DoorFEDMetrics

Metrics when pedestrian evaluates a door:
- `FED_max_Door`: Peak FED at door
- `K_ave_Door`: Average extinction coefficient
- `is_visible`: True if K < 0.5

### ExposureDiagnostic

Aggregate analysis for pedestrian:
- `peak_FED`: Maximum exposure recorded
- `FED_trajectory`: Complete time-series data
- `door_evaluations`: All candidate metrics

---

## CLI Usage

Once implemented (Phase 2):

```bash
# Run FED tracking analysis
pyfdsevac run-fed-tracking --scenario <path> --output <path>

# Generate exposure diagnostics
pyfdsevac export-diagnostics --pedestrian <id> --output <path>
```

---

## Testing

Tests are organized by contract type:

```
tests/
├── contract/              # Contract tests (TDD first)
│   ├── test_tracker.py
│   ├── test_metrics.py
│   └── test_diagnostics.py
├── unit/                  # Unit tests for edge cases
│   └── test_exposure_edge_cases.py
└── integration/           # Module interaction tests
    └── test_routing_integration.py
```

Run tests:
```bash
pytest tests/contract/      # Contract tests
pytest tests/unit/          # Unit tests
pytest tests/integration/   # Integration tests
```

---

## Integration Points

### With Routing Module

The exposure tracking module provides door metrics to the routing module:

```
exposure.tracker.track_exposure()
    ↓
exposure.metrics.record_door_metrics()
    ↓
routing.evaluator.evaluate_candidate()
    ↓
routing.decider.sort_candidates_by_fed()
```

### With Runtime Module

Pedestrian trajectories are recorded by runtime and consumed by exposure tracking:

```
runtime.simulate()
    ↓
exposure.tracker.track_exposure()
    ↓
exposure.diagnostics.generate_diagnostic()
```

---

## Best Practices

1. **Always validate smoke data** before calling tracking functions
2. **Record door metrics** at the exact time pedestrian evaluates candidate
3. **Use FED threshold of 1.0** per ISO 13571 for routing decisions
4. **Log exposure diagnostics** for post-evacuation analysis
5. **Test edge cases**: empty trajectories, zero smoke, high smoke

---

## Troubleshooting

### Issue: "Time not monotonically increasing"

**Solution**: Sort time steps before calling `track_exposure()`

### Issue: "Negative FED value"

**Solution**: Check smoke concentration input - must be ≥ 0

### Issue: "Empty door candidates"

**Solution**: Verify routing graph connectivity or trigger fallback behavior

---

## Next Steps

1. Read `research.md` for technical details
2. Run `pytest tests/contract/` to verify contracts
3. Implement CLI subcommand per Phase 2