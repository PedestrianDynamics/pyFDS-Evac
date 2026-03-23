# Implementation Plan: FED Tracking

**Feature Branch**: `004-fed-tracking`  
**Spec**: [spec.md](./spec.md)  
**Created**: 2026-03-23

---

## Technical Context

### Feature Summary
Track cumulative Fractional Effective Dose (FED) exposure per pedestrian during evacuation simulations. The system records FED accumulation over time, captures door-specific metrics (FED_max_Door, K_ave_Door) when pedestrians evaluate exit candidates, and integrates with routing decisions to reject paths with excessive smoke exposure. Provides comprehensive exposure diagnostics for post-evacuation analysis.

### Key Technologies
- **JuPedSim**: Pedestrian simulation engine for trajectory tracking
- **FDS Smoke Data**: Fire Dynamics Simulator output for extinction coefficient (K) and FED metrics
- **Python 3.10+**: Implementation language with Pydantic for data contracts
- **Smoke Interpolation**: Grid-to-pedestrian position interpolation for exposure computation

### Unknowns & Research Needs
1. FDS smoke data interpolation methods for pedestrian-specific exposure calculation
2. FED accumulation formula implementation (CO₂ and CO integration per ISO 13571)
3. JuPedSim API for trajectory recording with FED values at each time step
4. Integration with routing module for FED-based candidate rejection

### Dependencies
- pyfdsevac.fields module for smoke data access
- pyfdsevac.runtime module for pedestrian trajectory tracking
- Existing smoke analysis infrastructure for K and FED metrics

### Integrations
- Output: Pedestrian FED trajectory (per-time-step FED values with timestamps)
- Input: Door metrics (FED_max_Door, K_ave_Door) from smoke analysis
- Integration point: Route decision module uses FED metrics for candidate evaluation

---

## Constitution Check

| Principle | Status | Violation Justification |
|-----------|--------|------------------------|
| I. Package-First Architecture | ✅ PASS | New code in `pyfdsevac/fields/` subpackage for exposure tracking |
| II. CLI-Driven Development | ⚠️ PENDING | CLI subcommand `pyfdsevac run-fed-tracking` planned for Phase 2 |
| III. Test-First Implementation | ⚠️ PENDING | Tests must be written before implementation (per TDD rule) |
| IV. Integration Testing | ⚠️ PENDING | Integration tests needed for fields↔runtime↔routing interaction |
| V. Structured Data Contracts | ⚠️ PENDING | Dataclasses in `pyfdsevac/data_models.py` planned for Phase 1 |

**Overall**: Phase 0 research required to resolve unknowns before implementation can proceed.

---

## Phase 0: Outline & Research

### Research Tasks
1. **FDS Smoke Interpolation**: Determine method for computing pedestrian-specific exposure from FDS grid data
2. **FED Accumulation Formula**: Implement ISO 13571 standard integration (CO₂ + CO exposure)
3. **JuPedSim Trajectory API**: Document how to record FED values at each simulation time step
4. **Integration with Routing**: Establish how FED metrics flow from tracking to route decision module

### Deliverable
- `research.md` with all unknowns resolved

---

## Phase 1: Design & Contracts

### Deliverables
1. `data-model.md`: PedestrianFEDTrack, DoorFEDMetrics, FEDAccumulationEvent, ExposureDiagnostic dataclasses
2. `contracts/`: Interface contracts for FED tracking module
3. `quickstart.md`: Developer onboarding guide for exposure tracking

---

## Implementation Phases

### Phase 1
- [ ] Generate research.md (Phase 0 complete)
- [ ] Generate data-model.md
- [ ] Generate contracts/
- [ ] Generate quickstart.md
- [ ] Update agent context

### Phase 2
- [ ] Implement data models
- [ ] Implement FED accumulation tracker
- [ ] Implement door metric recorder (FED_max_Door, K_ave_Door)
- [ ] Implement trajectory recording with FED values
- [ ] Implement smoke exposure diagnostics generator

### Phase 3
- [ ] Write contract tests (TDD: tests first)
- [ ] Write unit tests for edge cases
- [ ] Write integration tests for module interactions
- [ ] Implement CLI subcommand
- [ ] Update documentation