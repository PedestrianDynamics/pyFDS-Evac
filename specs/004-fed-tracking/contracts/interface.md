# FED Tracking: Interface Contracts

**Feature**: FED Tracking  
**Branch**: 004-fed-tracking  
**Created**: 2026-03-23

---

## Overview

This document defines the interface contracts for the pyfdsevac exposure tracking module.

---

## Module: exposure_tracker

### Public Functions

#### track_exposure(pedestrian_id, positions, smoke_concentrations, time_steps) → List[PedestrianFEDTrack]

Track cumulative FED exposure for a pedestrian over simulation time steps.

**Parameters**:
| Parameter | Type | Description |
|-----------|------|-------------|
| pedestrian_id | str | Unique pedestrian identifier |
| positions | List[Tuple[float, float]] | Pedestrian trajectory coordinates |
| smoke_concentrations | List[float] | Local smoke concentration per time step |
| time_steps | List[float] | Simulation time stamps |

**Returns**: List of PedestrianFEDTrack records

**Contract**:
- Input lists must be same length
- All values must be non-negative
- Returns FED trajectory with cumulative totals

---

#### record_door_metrics(pedestrian_id, door_id, FED_max, K_ave, timestamp) → DoorFEDMetrics

Record FED and smoke metrics for door candidate evaluation.

**Parameters**:
| Parameter | Type | Description |
|-----------|------|-------------|
| pedestrian_id | str | Pedestrian identifier |
| door_id | str | Door candidate identifier |
| FED_max | float | Peak FED at door location |
| K_ave | float | Average extinction coefficient |
| timestamp | float | Evaluation time |

**Returns**: DoorFEDMetrics record

**Contract**:
- FED_max and K_ave must be ≥ 0
- is_visible automatically computed from K_ave

---

#### compute_accumulation_event(pedestrian_id, start_time, end_time, smoke_concentration_avg, dwell_time) → FEDAccumulationEvent

Record FED accumulation over a time interval.

**Parameters**:
| Parameter | Type | Description |
|-----------|------|-------------|
| pedestrian_id | str | Pedestrian identifier |
| start_time | float | Interval start timestamp |
| end_time | float | Interval end timestamp |
| smoke_concentration_avg | float | Average smoke level |
| dwell_time | float | Time spent in smoke |

**Returns**: FEDAccumulationEvent record

**Contract**:
- FED_increment = smoke_concentration_avg × dwell_time (per ISO 13571)
- All time values ≥ 0

---

#### generate_diagnostic(pedestrian_id, fed_trajectory, door_evaluations) → ExposureDiagnostic

Generate aggregated exposure diagnostic for pedestrian.

**Parameters**:
| Parameter | Type | Description |
|-----------|------|-------------|
| pedestrian_id | str | Pedestrian identifier |
| fed_trajectory | List[PedestrianFEDTrack] | Full exposure history |
| door_evaluations | List[DoorFEDMetrics] | All door candidate metrics |

**Returns**: ExposureDiagnostic record

**Contract**:
- Trajectory sorted by timestamp
- Peak FED matches maximum in trajectory
- All door evaluations included

---

## Module: routing_integration

### Public Functions

#### evaluate_candidate_with_fed(candidate_metrics, fed_threshold) → bool

Determine if door candidate is acceptable based on FED threshold.

**Parameters**:
| Parameter | Type | Description |
|-----------|------|-------------|
| candidate_metrics | DoorFEDMetrics | Door evaluation metrics |
| fed_threshold | float | Maximum acceptable FED (default: 1.0) |

**Returns**: True if candidate passes threshold

**Contract**:
- Candidate rejected if FED_max_Door > fed_threshold
- Returns True for safe candidates

---

#### sort_candidates_by_fed(candidates, fed_threshold) → List[DoorFEDMetrics]

Sort door candidates by FED exposure with threshold filtering.

**Parameters**:
| Parameter | Type | Description |
|-----------|------|-------------|
| candidates | List[DoorFEDMetrics] | Door candidate metrics |
| fed_threshold | float | Maximum acceptable FED |

**Returns**: Sorted list (lowest FED first), filtered to acceptable candidates

**Contract**:
- Rejects candidates exceeding FED threshold
- Sorts remaining by FED_max_Door ascending
- At least one candidate required for routing to proceed

---

## Data Contracts

### Input Validation

- All FED values must be ≥ 0
- All K_ave values must be ≥ 0
- Time values must be monotonically increasing per pedestrian
- Position coordinates must be finite values

### Output Guarantees

- PedestrianFEDTrack cumulative_FED is monotonically non-decreasing
- DoorFEDMetrics is_visible computed from K_ave < 0.5 threshold
- ExposureDiagnostic includes complete door evaluation history
- All metrics are deterministic given same input data

---

## Error Conditions

| Condition | Error Type | Resolution |
|-----------|------------|------------|
| Mismatched input list lengths | ValueError | Validate inputs before calling |
| Negative FED or K_ave values | ValueError | Clamp to zero or log warning |
| Time not monotonically increasing | ValueError | Sort time steps before processing |
| Empty door candidates list | RuntimeError | Trigger fallback behavior |

---

## Version History

- **v1.0** (2026-03-23): Initial interface definition