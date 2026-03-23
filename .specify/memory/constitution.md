<!-- 
Sync Impact Report
==================
Version change: initial → v1.0.0

Modified principles:
  - N/A (initial creation)

Added sections:
  - I. Package-First Architecture
  - II. CLI-Driven Development
  - III. Test-First Implementation
  - IV. Integration Testing Discipline
  - V. Structured Data Contracts
  - Governance

Removed sections:
  - N/A

Templates requiring updates:
  ⚠ .specify/templates/plan-template.md (pending review for constitution alignment)
  ⚠ .specify/templates/spec-template.md (pending review for constitution alignment)
  ⚠ .specify/templates/tasks-template.md (pending review for constitution alignment)
  ⚠ .specify/templates/commands/*.md (pending review for generic agent references)

Follow-up TODOs:
  - TODO(RATIFICATION_DATE): Set actual project ratification date (currently placeholder)
-->

# Constitution: pyfdsevac Project

**Version**: 1.0.0  
**Ratification Date**: [TODO(RATIFICATION_DATE): Set actual project adoption date]  
**Last Amended**: 2026-03-23

---

## Preamble

This constitution establishes the governing principles for the `pyfdsevac` project, a pedestrian evacuation simulation framework integrating fire dynamics (FDS) data with JuPedSim pedestrian modeling. These principles guide all architectural decisions, code contributions, and project evolution.

---

## I. Package-First Architecture

**All new functionality MUST be organized as submodules of the `pyfdsevac/` Python package.**

### Rules

- **I.1**: New features MUST be implemented in `pyfdsevac/` subdirectories (`io`, `fields`, `behavior`, `runtime`, `interfaces`, `cli`).
- **I.2**: The `pyfdsevac/` package MUST be importable as a standalone library (`import pyfdsevac`).
- **I.3**: Script-centric code in `src/` MAY exist temporarily for backward compatibility but MUST NOT receive new feature development.
- **I.4**: Public API exports MUST be explicitly defined in `pyfdsevac/__init__.py`.

### Rationale

Package-first architecture enables clean separation of concerns, testable modules, and stable public interfaces. It prevents the accumulation of monolithic scripts and ensures long-term maintainability.

---

## II. CLI-Driven Development

**All public functionality MUST be accessible and demonstrable via command-line interface before considering internal API stability.**

### Rules

- **II.1**: Every major feature MUST have a corresponding CLI subcommand (e.g., `pyfdsevac run-smoke`, `pyfdsevac run-routing`).
- **II.2**: CLI entrypoints MUST use `argparse` with explicit argument definitions.
- **II.3**: CLI output MUST be structured (JSON) for machine consumption, with human-readable alternatives.
- **II.4**: CLI validation MUST fail fast with clear error messages for invalid inputs.

### Rationale

CLI-first development ensures interface stability, enables automated testing via shell scripts, and provides immediate user value before backend integration.

---

## III. Test-First Implementation (NON-NEGOTIABLE)

**Test code MUST be written and FAIL before implementation code is created.**

### Rules

- **III.1**: Every public function MUST have corresponding contract tests in `tests/contract/`.
- **III.2**: Unit tests MUST cover edge cases and boundary conditions in `tests/unit/`.
- **III.3**: Integration tests MUST validate module interactions in `tests/integration/`.
- **III.4**: Test tasks MUST appear in `tasks.md` BEFORE implementation tasks for each user story.
- **III.5**: No pull request merges without passing all tests.

### Rationale

Test-first implementation (TDD) ensures code correctness, documents expected behavior, and prevents regressions. This is NON-NEGOTIABLE for safety-critical simulation code.

---

## IV. Integration Testing Discipline

**Integration tests MUST validate module interactions, not just isolated unit behavior.**

### Rules

- **IV.1**: Integration tests MUST cover `fields` ↔ `behavior` ↔ `runtime` module interactions.
- **IV.2**: Integration tests MUST validate smoke-speed ↔ JuPedSim integration.
- **IV.3**: Integration tests MUST use real FDS data files or deterministic mocks.
- **IV.4**: Integration tests MUST verify end-to-end workflows (CLI → runtime → output).

### Rationale

Module integration is where most bugs occur in scientific simulations. Integration testing discipline ensures components work together correctly before deployment.

---

## V. Structured Data Contracts

**All public functions MUST accept and return dataclasses (Pydantic models where Python 3.11+ features required).**

### Rules

- **V.1**: Every public function signature MUST use dataclasses for complex parameters.
- **V.2**: Dataclasses MUST be defined in `pyfdsevac/data_models.py` or module-specific `data_models.py`.
- **V.3**: All dataclasses MUST include validation rules (type hints, default values, ranges).
- **V.4**: Public APIs MUST document data contract guarantees (e.g., "returns normalized factor in [0,1]").

### Rationale

Structured data contracts prevent runtime errors, enable IDE autocomplete, and serve as living documentation for API consumers.

---

## Governance

### Amendment Procedure

1. Propose amendment via pull request to `.specify/memory/constitution.md`.
2. Update `Last Amended` date and increment `CONSTITUTION_VERSION`.
3. Run `sync-constitution` command to validate template alignment.
4. Merge after team review and approval.

### Versioning Policy

- **MAJOR**: Backward incompatible governance changes (principle removals, fundamental redefinitions).
- **MINOR**: New principles added or existing principles materially expanded.
- **PATCH**: Clarifications, wording improvements, typo fixes.

### Compliance Review

- All pull requests MUST include a "Constitution Check" section verifying alignment.
- Violations MUST be explicitly justified with override approval.
- Annual review of constitution relevance and principle effectiveness.

---

## Acknowledgments

This constitution draws from best practices in scientific computing, software architecture, and safety-critical systems development.
