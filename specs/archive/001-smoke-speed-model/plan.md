# Implementation Plan: Smoke-Speed Model

**Branch**: `001-smoke-speed-model` | **Date**: 2026-03-23 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/001-smoke-speed-model/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

Implement a smoke-speed model that computes pedestrian agent desired speeds based on local smoke visibility from FDS fire simulation data. The model converts FDS visibility to percentage clarity (0-100%), applies configurable visibility-to-speed mapping with interpolation methods, enforces physical speed bounds (0 to max_speed), and outputs agent trajectories with speed-factor time-series data. Critical gaps in current codebase: no `SmokeSpeedConfig` class, no percentage clarity conversion, no speed clamping with telemetry, no speed-factor output.

## Technical Context

**Language/Version**: Python 3.11+  
**Primary Dependencies**: `jupedsim` (simulation engine), `fdsvismap` (FDS data loading), `numpy` (numerical operations), `scipy` (interpolation)  
**Storage**: SQLite trajectories (enhanced with speed-factor columns)  
**Testing**: pytest (unit, contract, integration)  
**Target Platform**: Linux/MacOS simulation runtime  
**Project Type**: Scientific simulation library  
**Performance Goals**: 1000 agents speed update in <100ms per time step  
**Constraints**: <2x baseline (non-smoke) simulation runtime  
**Scale/Scope**: 10-1000 agents, 300-1000s simulation duration

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

✅ **I. Package-First Architecture**: New code in `pyfdsevac/` submodules (`io`, `fields`, `behavior`, `runtime`, `interfaces`, `cli`)  
✅ **II. CLI-Driven Development**: CLI entrypoint at `pyfdsevac/cli/main.py` using `argparse`  
✅ **III. Test-First Implementation (NON-NEGOTIABLE)**: Test tasks in `tasks.md` before implementation; contract → unit → integration progression  
✅ **IV. Integration Testing Discipline**: Integration tests for `fields` ↔ `behavior` ↔ `runtime` modules, smoke-speed ↔ JuPedSim  
✅ **V. Structured Data Contracts**: Pydantic dataclasses for `SmokeSpeedConfig`, `VisibilityMap`, `SpeedFactor`, `AgentFireState`

**Gates Passed**: All 5 constitution principles align with planned structure.

## Project Structure

### Documentation (this feature)

```text
specs/001-smoke-speed-model/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
pyfdsevac/                             # NEW: Main package
├── __init__.py                        # Package init with public API exports
├── data_models.py                     # Data models: SmokeSpeedConfig, VisibilityMap, SpeedFactor
├── io/                                # NEW: I/O operations
│   ├── __init__.py
│   ├── fds_loader.py                  # FDS visibility data loader
│   └── trajectory_writer.py           # Enhanced trajectory writer with speed-factor
├── fields/                            # NEW: Field sampling and interpolation
│   ├── __init__.py
│   ├── sampler.py                     # Spatial interpolation (nearest/bilinear/bicubic)
│   ├── temporal_interpolator.py       # Temporal interpolation for missing time steps
│   └── converter.py                   # FDS raw values → percentage clarity
├── behavior/                          # NEW: Agent behavior logic
│   ├── __init__.py
│   ├── speed_model.py                 # Smoke-speed computation with configurable curves
│   └── telemetry.py                   # Metrics collection
├── runtime/                           # NEW: JuPedSim integration
│   ├── __init__.py
│   ├── simulation_runner.py           # Simulation loop orchestration
│   └── agent_updater.py               # Per-agent speed updates
├── interfaces/                        # NEW: Public API
│   ├── __init__.py
│   └── api.py                         # Public functions: run_simulation(), load_fire_fields()
└── cli/                               # NEW: Command-line interface
    ├── __init__.py
    └── main.py                        # CLI entrypoint

tests/                                 # NEW: Test suite
├── contract/                          # Contract tests
├── integration/                       # Integration tests
└── unit/                              # Unit tests

src/                                   # EXISTING: Keep for backward compatibility
├── config.py
├── jpstooling.py
├── fdstooling.py
├── main.py
└── ploting.py
```

**Structure Decision**: pyfdsevac/ package-first architecture selected to replace script-centric src/ approach. New smoke-speed functionality lives in `pyfdsevac/` submodules (`io`, `fields`, `behavior`, `runtime`, `interfaces`, `cli`) following Constitution Principle I. Existing src/ files kept for backward compatibility during migration.

## Complexity Tracking

No Constitution violations detected. All requirements satisfied by new pyfdsevac/ package structure.
