# Route-Decision Logic Quickstart

**Feature**: Route-Decision Logic  
**Branch**: 003-route-decision  
**Created**: 2026-03-23

---

## Overview

This guide helps developers get started with the route-decision logic module.

---

## Prerequisites

- Python 3.10+
- pyfdsevac package installed
- FDS smoke data files
- JuPedSim routing graph

---

## Quick Start

### 1. Import the module

```python
from pyfdsevac.routing import DoorCandidate, RouteEvaluator, RouteManager
```

### 2. Create door candidates

```python
from pyfdsevac.routing import DoorCandidate

candidate = DoorCandidate(
    door_id="door_001",
    position=(5.0, 10.0),
    K_ave_Door=0.3,  # Visible (K < 0.5)
    FED_max_Door=0.8,  # Below threshold (1.0)
    is_visible=True,
    connectivity=["door_002", "door_003"]
)
```

### 3. Evaluate route candidates

```python
from pyfdsevac.routing import RouteEvaluator

evaluator = RouteEvaluator()

# Evaluate candidates
destination, rationale = evaluator.evaluate_candidates(
    candidates=[candidate1, candidate2, candidate3],
    current_door="current_door_id",
    smoke_threshold=0.5,
    fed_threshold=1.0
)

print(f"Selected: {destination}, Reason: {rationale}")
```

### 4. Record route switches

```python
from pyfdsevac.routing import RouteManager

manager = RouteManager()

event = manager.register_route_switch(
    pedestrian_id="ped_001",
    timestamp=120.5,
    origin="door_001",
    destination="door_002",
    K_ave_before=0.8,
    K_ave_after=0.3,
    FED_max_before=1.5,
    FED_max_after=0.7
)

print(f"Route switch recorded: {event}")
```

---

## Key Concepts

### Visibility Classification

- **Visible**: K < 0.5 m²/m (≥ 2m visual range)
- **Smoke-impacted**: 0.5 ≤ K < 1.0 m²/m
- **Non-visible**: K ≥ 1.0 m²/m

### Thresholds

- **FED_max_Door**: 1.0 FED (per ISO 13571) - candidates exceeding are rejected
- **Smoke threshold**: K = 0.5 m²/m - triggers reroute

---

## Example: Full Workflow

```python
from pyfdsevac.routing import DoorCandidate, RouteEvaluator, RouteManager

# Load door candidates (from FDS data)
candidates = [
    DoorCandidate("door_001", (5.0, 10.0), 0.3, 0.8, True, ["door_002"]),
    DoorCandidate("door_002", (8.0, 12.0), 0.7, 1.2, False, ["door_003"]),
    DoorCandidate("door_003", (10.0, 15.0), 0.2, 0.5, True, []),
]

# Evaluate
evaluator = RouteEvaluator()
destination, rationale = evaluator.evaluate_candidates(
    candidates=candidates,
    current_door="entry_door"
)

# Record
manager = RouteManager()
event = manager.register_route_switch(
    pedestrian_id="ped_001",
    timestamp=100.0,
    origin="entry_door",
    destination=destination,
    K_ave_before=0.0,  # Unknown before selection
    K_ave_after=evaluator.get_candidate_metrics(destination).K_ave_Door,
    FED_max_before=0.0,
    FED_max_after=evaluator.get_candidate_metrics(destination).FED_max_Door
)
```

---

## Troubleshooting

### Error: "No valid candidates after filtering"

**Cause**: All candidates exceed FED threshold (1.0)

**Solution**: Use fallback behavior:
```python
fallback = manager.get_fallback_destination(current_door, candidates)
```

### Error: "K value negative"

**Cause**: Invalid smoke data

**Solution**: Validate FDS data before processing

---

## Next Steps

- Read `contracts/interface.md` for detailed API specifications
- Check `tests/` for usage examples
- See `cli/routing.py` for command-line interface