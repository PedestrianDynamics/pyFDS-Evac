# Feature Specification: FED Tracking

**Feature Branch**: `004-fed-tracking`  
**Created**: 2026-03-23  
**Status**: Draft  
**Input**: FED Tracking: Track cumulative Fractional Effective Dose exposure per pedestrian, integrate with routing decisions, record FED_max_Door and K_ave_Door metrics per door candidate, implement smoke exposure diagnostics

## Clarifications

### Session 2026-03-23

- **FED threshold for route rejection**: 1.0 FED (ISO 13571 standard for safe exposure limit)
- **Smoke visibility threshold**: K = 0.5 m²/m (approximately 2m visual range)
- **Route-switch timing target**: 5 seconds as target performance metric

## User Scenarios & Testing

### User Story 1 - Smoke Exposure Monitoring During Evacuation (Priority: P1)

Pedestrians moving through smoke-filled environments need real-time tracking of their cumulative smoke exposure to avoid dangerous conditions. The system must track each pedestrian's exposure over time, provide route recommendations based on exposure metrics, and record detailed diagnostics for post-evacuation analysis.

**Why this priority**: Cumulative smoke exposure directly impacts pedestrian safety and survival probability; accurate tracking enables informed routing decisions and emergency response planning.

**Independent Test**: Run deterministic tests verifying FED accumulation rate, route-switching triggers, and FED_max_Door recording at door candidates.

**Acceptance Scenarios**:

  1. Pedestrian's cumulative FED increases proportionally to smoke concentration along path
  2. When pedestrian approaches door, system records FED_max_Door and K_ave_Door metrics for that candidate
  3. Route-switch occurs when accumulated FED exceeds threshold or visibility drops below minimum
  4. All exposure events recorded with timestamps for forensic analysis

---

## Requirements

### Functional Requirements

- **FR-001**: Track cumulative Fractional Effective Dose exposure per pedestrian over simulation time
- **FR-002**: Record FED_max_Door (maximum FED at door) for each door candidate evaluated during routing
- **FR-003**: Record K_ave_Door (average extinction coefficient) for each door candidate
- **FR-004**: Compute FED accumulation rate based on local smoke concentration and pedestrian dwell time
- **FR-005**: Integrate FED metrics with routing decisions to reject candidates exceeding exposure thresholds
- **FR-006**: Record pedestrian trajectory with cumulative FED values at each time step
- **FR-007**: Generate smoke exposure diagnostics including FED accumulation history and peak exposure events

### Observability Requirements

- **OR-001**: Log all FED_max_Door and K_ave_Door values for each door candidate evaluation
- **OR-002**: Record pedestrian FED accumulation history with timestamps for forensic analysis
- **OR-003**: Record route-switch events triggered by FED threshold violations

### Key Entities

- **PedestrianFEDTrack**: Cumulative FED exposure record with timestamps, position, and accumulation rate
- **DoorFEDMetrics**: FED_max_Door and K_ave_Door metrics recorded when pedestrian evaluates door candidate
- **FEDAccumulationEvent**: Event recording FED increase with smoke concentration and time interval
- **ExposureDiagnostic**: Aggregated FED exposure history and peak exposure metrics for pedestrian

## Success Criteria

### Measurable Outcomes

- **SC-001**: FED accumulation tracked with <5% error compared to reference smoke concentration integration
- **SC-002**: Door FED metrics recorded with 100% accuracy for all candidate evaluations
- **SC-003**: Route-switch decisions based on FED thresholds execute within 5 seconds of threshold detection
- **SC-004**: FED accumulation history recorded with <100ms latency per time step

### Validation Metrics

- FED accumulation accuracy: Percentage deviation from reference smoke exposure integration
- Door metric coverage: Percentage of door candidates with recorded FED_max_Door and K_ave_Door
- Route-switch latency: Time from FED threshold detection to routing decision update
- Diagnostic completeness: Percentage of exposure events recorded in final diagnostics

## Assumptions

- Smoke concentration data is available per pedestrian position at each simulation time step
- FED accumulation follows ISO 13571 standard: FED = ∫(CO₂ concentration × time) dt + ∫(CO concentration × time) dt
- Door candidates are evaluated at specific points (pedestrian reaches door location)
- Smoke concentration is interpolated from grid to pedestrian position using standard methods
- FED thresholds for route rejection align with safety standards (1.0 FED = life-threatening exposure)
- Pedestrian dwell time at door is short enough that FED_max_Door approximates peak exposure