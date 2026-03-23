# Route Decision Logic Contracts

## Overview

This document defines the interface contracts for the `pyfdsevac/routing` module.

## Public API

### DoorCandidate Data Contract

**Purpose**: Represent a door candidate with computed fire metrics

**Fields**:
- `door_id: str` - Unique identifier for the door
- `position: Tuple[float, float]` - (x, y) coordinates of door
- `K_ave_Door: float` - Average extinction coefficient (m²/m), range [0, ∞)
- `FED_max_Door: float` - Maximum cumulative FED (Fractional Effective Dose), range [0, ∞)
- `is_visible: bool` - True if K < 0.5 m²/m, False otherwise
- `connectivity: List[str]` - List of door IDs reachable from this door

**Validation Rules**:
- K_ave_Door ≥ 0
- FED_max_Door ≥ 0
- is_visible = True iff K_ave_Door < 0.5

**State Transitions**:
- N/A (immutable data object)

---

### FireSummary Data Contract

**Purpose**: Aggregate metrics for a door/path

**Fields**:
- `door_id: str` - Door identifier
- `K_ave_Door: float` - Average extinction coefficient
- `FED_max_Door: float` - Maximum FED
- `is_visible: bool` - Visibility classification
- `visibility_rating: str` - One of: "visible", "smoke-impacted", "non-visible"

**Validation Rules**:
- visibility_rating = "visible" if K_ave_Door < 0.5
- visibility_rating = "smoke-impacted" if 0.5 ≤ K_ave_Door < 1.0
- visibility_rating = "non-visible" if K_ave_Door ≥ 1.0

---

### RouteDecision Data Contract

**Purpose**: Record of pedestrian route choice

**Fields**:
- `pedestrian_id: str` - ID of pedestrian making decision
- `timestamp: float` - Simulation time of decision
- `origin_candidate: str` - Door ID from which decision was made
- `destination_candidate: str` - Door ID selected as destination
- `selection_rationale: str` - Explanation (e.g., "lowest_K_ave", "fallback")

**Validation Rules**:
- origin_candidate ≠ destination_candidate (must be different doors)
- timestamp ≥ 0
- selection_rationale must be one of defined rationale values

---

### RouteSwitchEvent Data Contract

**Purpose**: Event logging for route changes

**Fields**:
- `pedestrian_id: str` - ID of pedestrian switching routes
- `timestamp: float` - Time of route switch
- `origin_candidate: str` - Door ID being left
- `destination_candidate: str` - Door ID being selected
- `K_ave_before: float` - Average K of original path
- `K_ave_after: float` - Average K of new path
- `FED_max_before: float` - Max FED of original path
- `FED_max_after: float` - Max FED of new path

**Validation Rules**:
- All K_ave values ≥ 0
- All FED_max values ≥ 0
- timestamp ≥ 0

---

## Interface Contracts

### RouteEvaluator Interface

**Purpose**: Evaluate door candidates and select optimal route

**Methods**:

```python
def evaluate_candidates(
    candidates: List[DoorCandidate],
    current_door: str,
    smoke_threshold: float = 0.5,
    fed_threshold: float = 1.0
) -> Tuple[str, str]:
    """
    Evaluate door candidates and return optimal destination and rationale.
    
    Args:
        candidates: List of door candidates with fire metrics
        current_door: Current door ID pedestrian is at
        smoke_threshold: K value above which path is considered unsafe (default: 0.5)
        fed_threshold: FED value above which candidate is rejected (default: 1.0)
    
    Returns:
        Tuple of (destination_door_id, selection_rationale)
    
    Raises:
        ValueError: If no valid candidates remain after filtering
    """
```

**Preconditions**:
- candidates list is non-empty
- current_door exists in candidate list or is valid starting point
- thresholds are non-negative

**Postconditions**:
- Returns door_id that passes threshold checks
- Rationale explains selection logic
- Raises error if all candidates fail thresholds (fallback required)

---

### RouteManager Interface

**Purpose**: Manage pedestrian route selection and switching

**Methods**:

```python
def register_route_switch(
    pedestrian_id: str,
    timestamp: float,
    origin: str,
    destination: str,
    K_ave_before: float,
    K_ave_after: float,
    FED_max_before: float,
    FED_max_after: float
) -> RouteSwitchEvent:
    """
    Record a route switch event.
    
    Args:
        pedestrian_id: ID of pedestrian changing routes
        timestamp: Simulation time of switch
        origin: Door ID being left
        destination: Door ID being selected
        K_ave_before/after: Average extinction coefficients
        FED_max_before/after: Maximum FED values
    
    Returns:
        RouteSwitchEvent object with recorded data
    """
```

```python
def get_fallback_destination(
    current_door: str,
    candidates: List[DoorCandidate]
) -> str:
    """
    Get nearest safe exit when all candidates fail thresholds.
    
    Args:
        current_door: Current door ID
        candidates: All available door candidates
    
    Returns:
        Door ID of nearest physically reachable exit
    
    Raises:
        RuntimeError: If no reachable exit exists
    """
```

**Preconditions**:
- All door IDs reference valid doors in routing graph
- Timestamps are monotonically increasing per pedestrian

**Postconditions**:
- Route switches logged for audit trail
- Fallback returns valid door ID or raises error

---

## Error Conditions

| Error | Condition | Handling |
|-------|-----------|----------|
| ValueError | No valid candidates after FED threshold filtering | Use fallback behavior |
| RuntimeError | No reachable exit in fallback | Log fatal error, stop simulation |
| AssertionError | Invalid door connectivity graph | Log error, suggest graph validation |

---

## Data Flow

```
FDS Smoke Data → DoorCandidate Metrics → RouteEvaluator
                                              ↓
                                        RouteDecision
                                              ↓
                                        RouteSwitchEvent
                                              ↓
                                          Logging
```