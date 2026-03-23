# pyfdsevac: Route-Decision Logic

**Feature Branch**: `003-route-decision`  
**Status**: Phase 0 complete, ready for Phase 1 implementation

---

## Overview

The route-decision logic module implements pedestrian route selection during smoke-filled evacuation scenarios. It evaluates door candidates, computes fire exposure metrics, and guides pedestrians along safest available routes.

---

## Architecture

```
pyfdsevac/
├── routing/               # NEW: Route-decision logic module
│   ├── __init__.py        # Exports public API
│   ├── data_models.py     # DoorCandidate, FireSummary, RouteDecision, RouteSwitchEvent
│   ├── evaluator.py       # RouteEvaluator class (algorithm implementation)
│   ├── manager.py         # RouteManager class (state tracking)
│   └── cli.py             # CLI entrypoint (Phase 2)
└── __init__.py           # Update exports
```

---

## Phase 0: Research Complete

### Decision Summary

1. **Target Selection Algorithm**: Weighted cost function combining K_ave, FED_max, and distance
2. **JuPedSim Integration**: Use `change_target()` method for dynamic route modification
3. **Smoke Interpolation**: Spatial bilinear + temporal linear interpolation
4. **Route-Switch Timing**: <5s latency target

See `specs/003-route-decision/research.md` for full details.

---

## Phase 1: Implementation Tasks

### Phase 1.1: Data Models (TDD First)
- [ ] Write `tests/contract/test_door_candidate.py` (FAIL)
- [ ] Implement `pyfdsevac/routing/data_models.py`
- [ ] Write `tests/unit/test_fire_summary.py` (FAIL)
- [ ] Implement visibility rating logic

### Phase 1.2: Core Logic (TDD First)
- [ ] Write `tests/contract/test_route_evaluator.py` (FAIL)
- [ ] Implement `pyfdsevac/routing/evaluator.py`
- [ ] Write `tests/integration/test_fds_integration.py` (FAIL)
- [ ] Implement smoke data interpolation

### Phase 1.3: State Management (TDD First)
- [ ] Write `tests/contract/test_route_manager.py` (FAIL)
- [ ] Implement `pyfdsevac/routing/manager.py`
- [ ] Write `tests/integration/test_route_switch_events.py`

### Phase 1.4: Contracts & Quickstart
- [ ] Update `contracts/interface.md` with implementation details
- [ ] Update `quickstart.md` with code examples

### Phase 1.5: Agent Context Update
- [ ] Run `.specify/scripts/bash/update-agent-context.sh opencode`

---

## Phase 2: CLI & Testing

### Phase 2.1: CLI Implementation
- [ ] Implement `pyfdsevac routing` subcommand
- [ ] Add `--input` flag for FDS data path
- [ ] Add `--output` flag for event log JSON
- [ ] Add `--threshold` flags for smoke/FED thresholds

### Phase 2.2: End-to-End Tests
- [ ] Test smoke-free preferred path selection
- [ ] Test reroute under smoke
- [ ] Test candidate rejection under excessive smoke
- [ ] Test fallback behavior

---

## Constitution Check

| Principle | Status | Action |
|-----------|--------|--------|
| I. Package-First Architecture | ✅ PASS | New code in `pyfdsevac/routing/` |
| II. CLI-Driven Development | ⚠️ Phase 2 | CLI implementation in Phase 2 |
| III. Test-First Implementation | ⚠️ Phase 1 | Tests written before implementation |
| IV. Integration Testing | ⚠️ Phase 1 | Integration tests in Phase 1.2/1.3 |
| V. Structured Data Contracts | ✅ PASS | Dataclasses in `data_models.py` |

**Overall**: Compliance maintained with phased implementation.

---

## Dependencies

### Internal
- `pyfdsevac.fields` - FDS smoke data access
- `pyfdsevac.runtime` - Pedestrian simulation integration

### External
- JuPedSim (routing graph API)
- FDS output files (smoke data)

---

## Next Steps

1. **Phase 1.1**: Start with data models (TDD)
2. **Phase 1.2**: Implement evaluator with smoke interpolation
3. **Phase 1.3**: Add route manager for state tracking
4. **Phase 2**: Implement CLI and end-to-end tests

See `specs/003-route-decision/plan.md` for full implementation plan.