<!-- Sync Impact Report -->
<!-- Version change: 0.0.0 → 1.0.0 -->
<!-- Modified principles: N/A (initial ratification) -->
<!-- Added sections: Core Principles (5 principles), Implementation Constraints, Governance -->
<!-- Removed sections: N/A -->
<!-- Templates requiring updates: ✅ .specify/templates/plan-template.md (Constitution Check section aligns) -->
<!--         ✅ .specify/templates/spec-template.md (requirements alignment) -->
<!--         ✅ .specify/templates/tasks-template.md (phase structure reflects principles) -->
<!-- Follow-up TODOs: None -->

# pyfdsevac Constitution

## Core Principles

### I. Package-First Architecture

All new functionality MUST be organized under the `pyfdsevac/` package namespace. The project MUST NOT remain script-centric; every feature must contribute to a stable, importable package structure.

**Rules:**
- New code MUST live in `pyfdsevac/` submodules (`io`, `fields`, `behavior`, `runtime`, `interfaces`, `cli`)
- Temporary script entrypoints are allowed ONLY during migration; they MUST be replaced by proper package interfaces
- Public API contracts (`interfaces` module) MUST be defined and stabilized before implementation
- Test code MUST mirror the package structure under `tests/`

**Rationale:** A clean package layout enables independent testing, clear ownership, and smooth evolution from prototype to production. It prevents technical debt from accumulating in ad-hoc scripts.

### II. CLI-Driven Development

Every library and module MUST expose functionality via a command-line interface. The CLI protocol MUST use stdin/arguments for input and stdout for structured output; errors MUST go to stderr.

**Rules:**
- Each submodule MUST provide a CLI entrypoint that accepts parameters via arguments or flags
- CLI output MUST support both human-readable and JSON formats
- Testing CLI behavior MUST be possible without importing Python modules
- CLI interfaces SHOULD be generated from the same contracts used by the Python API

**Rationale:** CLI-first design enforces decoupling, makes debugging trivial, and enables composability with shell tools and other processes.

### III. Test-First Implementation (NON-NEGOTIABLE)

Test-driven development is mandatory. Tests MUST be written, approved by reviewer, and confirmed failing BEFORE any implementation begins.

**Rules:**
- Every user story MUST have associated test tasks listed in tasks.md before implementation starts
- Contract tests MUST verify interface contracts before integration work
- Red-Green-Refactor cycle MUST be strictly observed: red tests → green implementation → refactor
- Test files MUST be named and organized to match the production module structure

**Rationale:** Test-first practice catches design flaws early, documents intended behavior, and prevents regression. The NON-NEGOTIABLE status means no implementation may proceed without this step.

### IV. Integration Testing Discipline

Integration tests are required for all contract boundaries and inter-module interactions.

**Focus areas:**
- New library contract tests between modules (`io` ↔ `fields`, `behavior` ↔ `runtime`)
- Contract changes to `interfaces` module must include integration validation
- Smoke-speed model integration with JuPedSim runtime
- Route-decision integration with behavior and FED tracking

**Rules:**
- Integration tests MUST use real data files or mocked external dependencies
- Tests MUST verify end-to-end workflows, not just individual functions
- CI MUST run integration tests before merging

**Rationale:** Integration tests catch mismatches between module interfaces that unit tests cannot detect, ensuring the system works as a cohesive whole.

### V. Structured Data Contracts

All modules MUST define and enforce explicit data contracts using structured types. No ad-hoc dictionaries or ambiguous data passing.

**Rules:**
- All public functions MUST accept and return well-typed dataclasses or Pydantic models
- Data contracts (`FireConfig`, `SimulationConfig`, `SimulationResult`, `AgentFireState`, `FireFieldFrame`, `FireFieldSeries`) MUST be versioned and documented
- Input validation MUST happen at module boundaries
- Serialization (JSON, etc.) MUST be explicit and testable

**Rationale:** Explicit contracts enable independent development, reliable testing, and prevent runtime surprises from malformed data.

## Implementation Constraints

### Technology Stack

- **Language**: Python 3.11+
- **Core dependencies**: `fdsvismap` for FDS data loading, JuPedSim for simulation engine
- **Testing**: pytest for unit and integration tests
- **Data modeling**: Pydantic or standard library `dataclasses`
- **CLI framework**: `argparse` or `click` (standard library preferred)

### Quality Gates

- All code MUST pass linting and type checking before merge
- Test coverage MUST be measured and reported
- Breaking changes to public contracts require version bump and migration plan

## Development Workflow

### Code Review Requirements

- All PRs MUST reference the relevant user story from spec.md
- Constitution compliance MUST be verified in review checklist
- CLI interfaces MUST be tested manually before merge
- Integration tests MUST demonstrate full workflow before merge

### Versioning Policy

- Version format: MAJOR.MINOR.PATCH
- MAJOR: Breaking changes to public contracts or CLI interface
- MINOR: New features that are backward-compatible
- PATCH: Bug fixes, non-semantic improvements

## Governance

This constitution supersedes all other development practices in the pyfdsevac project. Amendments require:

1. **Proposal**: Document the proposed change with rationale
2. **Review**: Evaluate impact on existing code, templates, and workflows
3. **Approval**: Team consensus or designated maintainer approval
4. **Migration**: Create tasks for updating existing code if needed
5. **Version bump**: Increment CONSTITUTION_VERSION per semver rules

**Compliance Review**: All pull requests MUST include a Constitution Check section in their implementation plan. Violations MUST be justified in the Complexity Tracking table with simpler alternative rejected reasons.

**Version**: 1.0.0 | **Ratified**: 2026-03-23 | **Last Amended**: 2026-03-23
