# Feature Specification: Route-Decision Logic

**Feature Branch**: `003-route-decision`  
**Created**: 2026-03-23  
**Status**: Clarified  
**Input**: Model door candidates from scenario exits/routing graph. Implement door/path fire summaries: K_ave_Door, FED_max_Door, visible/non-visible classification. Implement FDS+Evac-style target selection ordering from evac.f90. Add route-switch events and diagnostics. Add deterministic tests covering: smoke-free preferred path, reroute under smoke, candidate rejection under excessive smoke, fallback behavior when all candidates are poor.

## Clarifications

### Session 2026-03-23

**FED_max_Door Threshold**: 1.0 FED (per ISO 13571 standard) - cumulative exposure limit before route rejection required

**Smoke Concentration Threshold**: K = 0.5 m²/m (approximately 2m visual range) - triggers reroute when current path exceeds this value

**Route-Switch Timing**: 5 seconds target latency from smoke detection to route change implementation

## User Scenarios & Testing

### User Story 1 - Pedestrian Route Selection in Smoke-Filled Environments (Priority: P1)

Pedestrians must select safe exit routes during evacuation when visibility is impaired by smoke. The system should evaluate multiple door/path candidates, compute fire exposure metrics, and guide pedestrians along the safest available routes while providing visibility into routing decisions.

**Why this priority**: Life safety depends on accurate route decisions during evacuation; incorrect choices can significantly increase travel time or expose pedestrians to hazardous conditions.

**Independent Test**: Run deterministic test suite covering smoke-free preferred path, reroute under smoke, candidate rejection under excessive smoke, and fallback scenarios.

**Acceptance Scenarios**:

  1. In smoke-free environment, pedestrian selects path with lowest K_ave_Door (average extinction coefficient)
  2. When smoke increases on preferred path, pedestrian reroutes to alternative candidate with acceptable metrics
  3. When a door candidate exceeds FED_max_Door threshold, it is rejected from consideration
  4. When all candidates are poor, pedestrian falls back to nearest safe exit

---

## Requirements

### Functional Requirements

- **FR-001**: Model door candidates from scenario exits and routing graph connectivity
- **FR-002**: Compute door/path fire summaries including K_ave_Door, FED_max_Door, and visible/non-visible classification
- **FR-003**: Implement FDS+Evac-style target selection ordering based on fire exposure metrics
- **FR-004**: Record route-switch events with timestamps, origin candidate, and destination candidate
- **FR-005**: Generate diagnostics for route selection including candidate metrics and rejection reasons
- **FR-006**: Select smoke-free preferred path when all candidates have acceptable metrics
- **FR-007**: Reroute pedestrian when smoke concentration exceeds threshold on current path
- **FR-008**: Reject door candidates where FED_max_Door exceeds fire exposure threshold
- **FR-009**: Implement fallback behavior when all candidate doors have excessive smoke exposure

### Observability Requirements

- **OR-001**: Log all route-switch events with candidate metrics for post-evacuation analysis
- **OR-002**: Record rejection reasons for each candidate (FED threshold exceeded, visibility below minimum, etc.)

### Key Entities

- **DoorCandidate**: Door node with computed fire metrics (K_ave_Door, FED_max_Door, visibility classification)
- **RouteDecision**: Record of pedestrian choice including timestamp, origin, destination, and selection rationale
- **RouteSwitchEvent**: Event recording when pedestrian changes destination with metrics before/after switch
- **FireSummary**: Aggregated metrics for door/path including K_ave_Door, FED_max_Door, visible flag

## Success Criteria

### Measurable Outcomes

- **SC-001**: Pedestrians select optimal routes in smoke-free conditions with >95% accuracy based on K_ave_Door ranking
- **SC-002**: Route-switch events occur within 5 seconds (target latency) of smoke threshold violation detection
- **SC-003**: FED_max_Door threshold correctly rejects >99% of candidates exceeding safe exposure limits
- **SC-004**: Fallback behavior successfully guides pedestrians to exit when all primary candidates are unavailable

### Validation Metrics

- Route selection accuracy: Percentage of simulations where pedestrians reach nearest safe exit
- Average route-switch latency: Time from smoke detection to route change implementation
- Candidate rejection rate: Percentage of door candidates rejected due to FED/visibility thresholds
- Fallback success rate: Percentage of high-smoke scenarios where fallback mechanism guides pedestrians to safety

## Assumptions

- Fire exposure metrics (K_ave_Door, FED_max_Door) are computed by downstream smoke analysis modules
- Routing graph provides door connectivity information (which doors lead to which other doors/areas)
- Smoke concentration data is available per door/path at each simulation time step
- FED_max_Door threshold: 1.0 FED (per ISO 13571) - candidates exceeding this are rejected
- Smoke concentration threshold: K = 0.5 m²/m (approximately 2m visual range) - triggers reroute
- Visibility classification: K < 0.5 m²/m = visible, K ≥ 0.5 m²/m = non-visible
- Pedestrians can immediately reroute upon detecting smoke threshold violation (5s target latency)
- Fallback behavior selects nearest physically reachable exit when all routed candidates fail