# Implementation Plan: Route-Decision Logic

**Feature Branch**: `003-route-decision`  
**Spec**: [spec.md](./spec.md)  
**Created**: 2026-03-23

---

## Technical Context

### Feature Summary
Implement pedestrian route decision logic during smoke-filled evacuation scenarios. The system evaluates door candidates, computes fire exposure metrics (K_ave_Door, FED_max_Door), and guides pedestrians along safest available routes with fallback behavior when all candidates are compromised.

### Key Technologies
- **JuPedSim**: Pedestrian simulation engine for route modeling
- **FDS Smoke Data**: Fire Dynamics Simulator output for extinction coefficient (K) and FED metrics
- **Routing Graph**: Graph representation of door connectivity and pedestrian paths
- **Python 3.10+**: Implementation language with Pydantic for data contracts

### Unknowns & Research Needs
1. FDS+Evac evac.f90 target selection algorithm details (line 16300 reference)
2. JuPedSim API for dynamic route modification during simulation
3. Smoke data interpolation between time steps for door-specific metrics
4. Performance expectations for route-switch decision latency (<5s target)

### Dependencies
- pyfdsevac.fields module for smoke data access
- pyfdsevac.runtime module for pedestrian simulation integration
- Existing routing graph data structures

### Integrations
- Output: Route switch events (JSON format for logging)
- Input: Door candidate metrics from smoke analysis modules
- Integration point: Pedestrian behavior module needs route decision interface

---

## Constitution Check

| Principle | Status | Violation Justification |
|-----------|--------|------------------------|
| I. Package-First Architecture | ✅ PASS | New code in `pyfdsevac/routing/` subpackage |
| II. CLI-Driven Development | ⚠️ PENDING | CLI subcommand `pyfdsevac run-routing` planned for Phase 2 |
| III. Test-First Implementation | ⚠️ PENDING | Tests must be written before implementation (per TDD rule) |
| IV. Integration Testing | ⚠️ PENDING | Integration tests needed for fields↔routing↔runtime interaction |
| V. Structured Data Contracts | ⚠️ PENDING | Dataclasses in `pyfdsevac/data_models.py` planned for Phase 1 |

**Overall**: Phase 0 research required to resolve unknowns before implementation can proceed.

---

## Phase 0: Outline & Research

### Research Tasks
1. **FDS+Evac Target Selection Algorithm**: Examine evac.f90 to understand candidate ordering logic
2. **JuPedSim Dynamic Route API**: Document how to modify pedestrian destinations during simulation
3. **Smoke Data Interpolation**: Determine method for computing door-specific K and FED values from FDS grid data
4. **Route-Switch Timing**: Establish performance benchmarks for decision latency (<5s target)

### Deliverable
- `research.md` with all unknowns resolved

---

## Phase 1: Design & Contracts

### Deliverables
1. `data-model.md`: DoorCandidate, RouteDecision, RouteSwitchEvent, FireSummary dataclasses
2. `contracts/`: Interface contracts for routing module
3. `quickstart.md`: Developer onboarding guide for routing module

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
- [ ] Implement door candidate modeler
- [ ] Implement fire summary computation
- [ ] Implement target selection ordering
- [ ] Implement route-switch event logging
- [ ] Implement fallback behavior

### Phase 3
- [ ] Write contract tests (TDD: tests first)
- [ ] Write unit tests for edge cases
- [ ] Write integration tests for module interactions
- [ ] Implement CLI subcommand
- [ ] Update documentation