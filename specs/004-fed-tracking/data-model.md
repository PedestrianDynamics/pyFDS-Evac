# FED Tracking: Data Model

**Feature**: FED Tracking  
**Branch**: 004-fed-tracking  
**Created**: 2026-03-23

---

## Overview

This document defines the data models for the pyfdsevac exposure tracking module.

---

## Core Entities

### PedestrianFEDTrack

Cumulative FED exposure record for a pedestrian over time.

**Fields**:
| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| pedestrian_id | str | Unique pedestrian identifier | Non-empty string |
| timestamp | float | Simulation time step | ≥ 0 |
| position | Tuple[float, float] | (x, y) pedestrian coordinates | Finite values |
| cumulative_FED | float | Total FED accumulated | ≥ 0 |
| fed_rate | float | FED accumulation rate (per time step) | ≥ 0 |
| smoke_concentration | float | Local smoke concentration | ≥ 0 |

**Validation Rules**:
- cumulative_FED must be monotonically non-decreasing
- fed_rate computed from smoke_concentration and time delta

**State Transitions**: N/A (immutable data object)

---

### DoorFEDMetrics

FED and smoke metrics recorded when pedestrian evaluates door candidate.

**Fields**:
| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| pedestrian_id | str | ID of pedestrian evaluating door | Non-empty string |
| door_id | str | Door candidate identifier | Non-empty string |
| FED_max_Door | float | Peak FED at door location | ≥ 0 |
| K_ave_Door | float | Average extinction coefficient | ≥ 0 |
| is_visible | bool | Visibility classification | True if K < 0.5 |
| evaluation_timestamp | float | Time of door evaluation | ≥ 0 |

**Validation Rules**:
- FED_max_Door represents peak exposure at door
- is_visible = True if K_ave_Door < 0.5 (visibility threshold)

**State Transitions**: N/A (immutable data object)

---

### FEDAccumulationEvent

Event recording FED increase with smoke context.

**Fields**:
| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| pedestrian_id | str | ID of pedestrian | Non-empty string |
| timestamp_start | float | Time interval start | ≥ 0 |
| timestamp_end | float | Time interval end | ≥ timestamp_start |
| FED_increment | float | FED increase during interval | ≥ 0 |
| smoke_concentration_avg | float | Average smoke level | ≥ 0 |
| dwell_time | float | Time spent in smoke | ≥ 0 |

**Validation Rules**:
- FED_increment computed from smoke_concentration_avg × dwell_time
- time interval must be contiguous with previous events

**State Transitions**: N/A (immutable data object)

---

### ExposureDiagnostic

Aggregated FED exposure history and peak metrics for pedestrian.

**Fields**:
| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| pedestrian_id | str | ID of pedestrian | Non-empty string |
| total_exposure_time | float | Cumulative time in smoke | ≥ 0 |
| peak_FED | float | Maximum FED recorded | ≥ 0 |
| peak_FED_timestamp | float | Time of peak exposure | ≥ 0 |
| FED_trajectory | List[Tuple[float, float]] | (timestamp, FED) pairs | Sorted by timestamp |
| door_evaluations | List[DoorFEDMetrics] | All door candidate metrics | Non-empty list |

**Validation Rules**:
- FED_trajectory must be sorted by timestamp
- peak_FED must match maximum value in trajectory
- door_evaluations includes all doors evaluated during simulation

**State Transitions**: N/A (immutable data object)

---

## Data Flow

```
FDS Smoke Data (input)
    ↓
Pedestrian Position Tracking
    ↓
PedestrianFEDTrack (per time step)
    ↓
DoorFEDMetrics (at door evaluation)
    ↓
FEDAccumulationEvent (recorded)
    ↓
ExposureDiagnostic (aggregated)
    ↓
Output: JSON for analysis
```