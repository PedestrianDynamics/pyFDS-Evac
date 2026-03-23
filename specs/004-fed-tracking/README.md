# FED Tracking: README

**Feature**: FED Tracking  
**Branch**: 004-fed-tracking  
**Created**: 2026-03-23  
**Status**: Phase 1 Planning Complete

---

## Overview

Track cumulative Fractional Effective Dose (FED) exposure per pedestrian during evacuation simulations. Records door-specific FED and smoke metrics, provides comprehensive exposure diagnostics, and integrates with routing decisions.

---

## Status

- ✅ Feature spec complete
- ✅ Constitution check complete
- ✅ Phase 0 research complete
- ✅ Phase 1 design complete (data-model, contracts, quickstart)
- ⏳ Phase 2 implementation pending
- ⏳ Phase 3 testing pending

---

## Documentation

| Document | Path | Description |
|----------|------|-------------|
| Feature Spec | [spec.md](./spec.md) | Feature requirements and acceptance criteria |
| Implementation Plan | [plan.md](./plan.md) | Implementation phases and tasks |
| Research | [research.md](./research.md) | Technical details and design decisions |
| Data Model | [data-model.md](./data-model.md) | Pydantic dataclasses |
| Contracts | [contracts/interface.md](./contracts/interface.md) | Public API contracts |
| Quickstart | [quickstart.md](./quickstart.md) | Developer onboarding guide |

---

## Key Features

- Track cumulative FED exposure per pedestrian over time
- Record door-specific FED_max_Door and K_ave_Door metrics
- Integrate with routing module for FED-based candidate rejection
- Generate comprehensive exposure diagnostics

---

## Technical Stack

- **JuPedSim**: Pedestrian simulation engine
- **FDS Smoke Data**: Fire dynamics simulator output
- **Python 3.10+**: Implementation language
- **Pydantic**: Data contracts

---

## Implementation Phases

### Phase 1 (Complete)
- [x] Generate research.md
- [x] Generate data-model.md
- [x] Generate contracts/
- [x] Generate quickstart.md

### Phase 2 (Pending)
- [ ] Implement data models
- [ ] Implement FED accumulation tracker
- [ ] Implement door metric recorder
- [ ] Implement trajectory recording
- [ ] Implement diagnostics generator

### Phase 3 (Pending)
- [ ] Write contract tests (TDD)
- [ ] Write unit tests
- [ ] Write integration tests
- [ ] Implement CLI subcommand
- [ ] Update documentation

---

## Constitution Compliance

| Principle | Status |
|-----------|--------|
| I. Package-First Architecture | ✅ PASS |
| II. CLI-Driven Development | ⚠️ Phase 2 |
| III. Test-First Implementation | ⚠️ Phase 3 |
| IV. Integration Testing | ⚠️ Phase 3 |
| V. Structured Data Contracts | ⚠️ Phase 2 |

---

## Next Steps

1. Run `/speckit.clarify` for additional clarification if needed
2. Run `/speckit.plan` to continue planning
3. Proceed to Phase 2 implementation after clarification complete