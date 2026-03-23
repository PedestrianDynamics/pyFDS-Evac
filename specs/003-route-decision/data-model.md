# Route-Decision Logic: Data Model

**Feature**: Route-Decision Logic  
**Branch**: 003-route-decision  
**Created**: 2026-03-23

---

## Overview

This document defines the data models for the pyfdsevac routing module.

---

## Core Entities

### DoorCandidate

Represents a door candidate with computed fire metrics.

**Fields**:
| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| door_id | str | Unique door identifier | Non-empty string |
| position | Tuple[float, float] | (x, y) door coordinates | Finite values |
| K_ave_Door | float | Average extinction coefficient (m²/m) | ≥ 0 |
| FED_max_Door | float | Maximum cumulative FED | ≥ 0 |
| is_visible | bool | Visibility classification | True if K < 0.5 |
| connectivity | List[str] | Reachable door IDs | List of valid door IDs |

**State Transitions**: N/A (immutable data object)

---

### FireSummary

Aggregated metrics for a door/path.

**Fields**:
| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| door_id | str | Door identifier | Non-empty string |
| K_ave_Door | float | Average extinction coefficient | ≥ 0 |
| FED_max_Door | float | Maximum FED | ≥ 0 |
| is_visible | bool | Visibility classification | True if K < 0.5 |
| visibility_rating | str | Smoke level classification | "visible", "smoke-impacted", or "non-visible" |

**Validation Rules**:
- visibility_rating = "visible" if K_ave_Door < 0.5
- visibility_rating = "smoke-impacted" if 0.5 ≤ K_ave_Door < 1.0
- visibility_rating = "non-visible" if K_ave_Door ≥ 1.0

**State Transitions**: N/A (immutable data object)

---

### RouteDecision

Record of pedestrian route choice.

**Fields**:
| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| pedestrian_id | str | ID of pedestrian | Non-empty string |
| timestamp | float | Simulation time | ≥ 0 |
| origin_candidate | str | Origin door ID | Must exist in routing graph |
| destination_candidate | str | Selected destination | Must exist in routing graph |
| selection_rationale | str | Decision explanation | "lowest_K_ave", "lowest_FED", "fallback" |

**Validation Rules**:
- origin_candidate ≠ destination_candidate
- selection_rationale must be one of defined values

**State Transitions**: N/A (immutable data object)

---

### RouteSwitchEvent

Event logging for route changes.

**Fields**:
| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| pedestrian_id | str | ID of pedestrian | Non-empty string |
| timestamp | float | Time of switch | ≥ 0 |
| origin_candidate | str | Door being left | Must exist in routing graph |
| destination_candidate | str | Door being selected | Must exist in routing graph |
| K_ave_before | float | K of original path | ≥ 0 |
| K_ave_after | float | K of new path | ≥ 0 |
| FED_max_before | float | Max FED of original path | ≥ 0 |
| FED_max_after | float | Max FED of new path | ≥ 0 |

**Validation Rules**:
- timestamp must be monotonically increasing per pedestrian
- All K_ave and FED_max values ≥ 0

**State Transitions**: N/A (immutable data object)

---

## Data Flow

```
FDS Smoke Data (input)
    ↓
DoorCandidate Metrics (computed)
    ↓
RouteEvaluator (process)
    ↓
RouteDecision (record)
    ↓
RouteSwitchEvent (logged)
    ↓
Output: JSON for analysis
```