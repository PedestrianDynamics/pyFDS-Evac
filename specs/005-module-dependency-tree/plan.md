# Implementation Plan: Module Dependency Tree

**Branch**: `005-module-dependency-tree` | **Date**: 2026-03-24 | **Spec**: [spec.md](./spec.md)  
**Input**: Feature specification from `/specs/005-module-dependency-tree/spec.md`

## Summary

Reorganize the pyFDS-Evac codebase into a clean six-module architecture with strict dependency order: `io` → `fields` → `behavior` → `runtime`, plus `interfaces` and `cli`. This establishes a maintainable foundation where IO layers are abstracted from business logic, field sampling is unified, and behavior modules declare clear input contracts for graceful degradation.

## Technical Context

**Language/Version**: Python 3.11+  
**Primary Dependencies**: fdsreader, fdsvismap, jupedsim, pedpy, shapely  
**Storage**: SQLite (trajectory output), pickle files (visibility maps)  
**Testing**: pytest (behavior modules with mocked samplers)  
**Target Platform**: Linux/MacOS desktop
**Project Type**: library/cli  
**Performance Goals**: Complete v1 speed+routing with 100 agents in under 5 minutes  
**Constraints**: <200ms p95 per simulation tick, graceful degradation with partial data  
**Scale/Scope**: Six canonical modules, ~10-20 files total, 1000-5000 LOC

## Constitution Check

**GATE: Module Architecture** ✅ PASS  
- Six canonical modules: `io`, `fields`, `behavior`, `runtime`, `interfaces`, `cli`  
- Dependency order enforced: io (no deps) → fields (io) → behavior (fields) → runtime (all)

**GATE: IO Layer Separation** ✅ PASS  
- `fds_source.py` uses fdsreader only, hides behind catalog API  
- `visibility_source.py` uses fdsvismap only, hides behind catalog API  
- Both report missing data explicitly, no guessing

**GATE: Field Abstraction** ✅ PASS  
- `catalog.py`: single source of truth for available quantities  
- `sampler.py`: uniform `(x, y, z, t)` sampling API  
- Clear errors for unavailable quantities

**GATE: Behavior Module Contracts** ✅ PASS  
- `speed.py`: requires extinction OR soot-derived extinction  
- `routing.py`: requires extinction/visibility  
- `fed.py`: requires CO, CO2, HCN, temperature  
- Each declares mandatory inputs for fallback policies

**GATE: Runtime Integration** ✅ PASS  
- `session.py`: orchestrates only, uses public APIs from all modules  
- No behavior logic implemented in runtime  
- Logs warnings for missing/derived quantities

**GATE: v1 Scope & Fallback Policy** ✅ PASS  
- Minimal: extinction only → speed updates  
- Recommended: extinction + visibility → speed + routing  
- Full: all quantities → all features  
- Missing extinction → fail immediately  
- Missing gas fields → speed+routing only, warn on FED disable

**Status**: All constitutional principles satisfied. No violations requiring justification.

## Project Structure

### Documentation (this feature)

```text
specs/005-module-dependency-tree/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
pyfdsevac/
├── io/
│   ├── __init__.py
│   ├── fds_source.py       # Load FDS quantities via fdsreader
│   └── visibility_source.py # Load visibility via fdsvismap
├── fields/
│   ├── __init__.py
│   ├── catalog.py          # Available quantities registry
│   ├── sampler.py          # Uniform sampling API
│   └── alignment.py        # Geometry coordinate mapping
├── behavior/
│   ├── __init__.py
│   ├── speed.py            # Speed factor from extinction
│   ├── routing.py          # Door/path fire summaries
│   └── fed.py              # FED accumulation
├── runtime/
│   ├── __init__.py
│   ├── jupedsim_adapter.py # JuPedSim integration
│   └── session.py          # Simulation loop orchestration
├── interfaces/
│   ├── __init__.py
│   └── api.py              # Public API contracts
└── cli/
    ├── __init__.py
    └── main.py             # CLI entry point

tests/
├── io/
├── fields/
├── behavior/
├── runtime/
└── integration/

main.py                     # Update to use pyfdsevac runtime
```

**Structure Decision**: Single-project structure (option 1). The codebase is a Python library with CLI interface, not a web/mobile app. All modules live under `pyfdsevac/` package with clear dependency boundaries. Tests mirror the source structure for isolation.

## Complexity Tracking

No violations. This refactor aligns with all constitutional principles.
