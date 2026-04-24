# Feature Specification: Module Dependency Tree

**Feature Branch**: `005-module-dependency-tree`  
**Created**: 2026-03-24  
**Status**: Draft  
**Input**: User description: "Implement module dependency tree from issue #12"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Module Architecture (Priority: P1)

I want to reorganize the pyFDS-Evac codebase into a clean module structure with clear separation of concerns between IO operations, field processing, behavior logic, and runtime integration.

**Why this priority**: This is the foundation for all future development. Without proper module boundaries, adding new features or fixing bugs becomes increasingly difficult as the codebase grows.

**Independent Test**: Can be fully tested by verifying module imports follow dependency order (io → fields → behavior → runtime) and that each module exposes only its intended public API.

**Acceptance Scenarios**:

1. **Given** the repository exists with current prototype code, **When** I examine the module structure, **Then** I see exactly six modules: io, fields, behavior, runtime, interfaces, and cli
2. **Given** I have imported a module, **When** I check its dependencies, **Then** it only imports from modules lower in the dependency chain
3. **Given** a module tries to import from a module higher in the chain, **When** I run linting, **Then** it fails with a dependency violation error

---

### User Story 2 - IO Layer Abstraction (Priority: P1)

I want FDS data loading and visibility computation to be hidden behind consistent APIs so behavior modules don't care which library (fdsreader vs fdsvismap) is used.

**Why this priority**: The IO layer handles external dependencies and data formats. Changes to these libraries or adding new data sources should not require changes to behavior logic.

**Independent Test**: Can be fully tested by mocking the catalog API and verifying behavior modules work identically whether IO uses fdsreader, fdsvismap, or a new future library.

**Acceptance Scenarios**:

1. **Given** I have loaded FDS data from a file, **When** I request extinction or visibility data, **Then** the catalog returns it without exposing which underlying library provided it
2. **Given** a required FDS quantity is missing, **When** I attempt to load it, **Then** the system fails with an explicit error message rather than guessing or defaulting
3. **Given** I want to add a new data source, **When** I implement it behind the catalog API, **Then** existing behavior modules work without modification

---

### User Story 3 - Field Sampling Interface (Priority: P1)

I want a consistent interface for sampling any fire quantity at any spatial and temporal coordinate so behavior modules can focus on logic, not data access patterns.

**Why this priority**: Behavior modules (speed, routing, FED) all need to query fire conditions at agent positions. A unified sampling API eliminates duplication and ensures consistent error handling.

**Independent Test**: Can be fully tested by creating a mock sampler with known test data and verifying all behavior modules sample correctly at arbitrary (x, y, z, t) coordinates.

**Acceptance Scenarios**:

1. **Given** I have a sampler instance, **When** I call `get_quantity("extinction", time, x, y, z)`, **Then** it returns the extinction coefficient at that point
2. **Given** I sample a point outside the FDS grid, **When** I request data, **Then** it returns a clear error or warning rather than crashing
3. **Given** I request a quantity that is unavailable, **When** I call the sampler, **Then** it returns a specific error indicating which quantity is missing

---

### User Story 4 - Behavior Module Contracts (Priority: P1)

I want each behavior module to declare its mandatory and optional inputs so the system can run with partial data and provide clear warnings when features are disabled.

**Why this priority**: FDS simulations may not always produce all required quantities (e.g., missing gas concentrations). The system should gracefully degrade functionality rather than failing completely.

**Independent Test**: Can be fully tested by running with missing input files and verifying the system:
- Fails immediately if extinction is missing (speed/routing impossible)
- Runs speed+routing but disables FED with warning if gas fields missing
- Derives simple visibility from extinction when fdsvismap unavailable

**Acceptance Scenarios**:

1. **Given** extinction data is missing, **When** I start the simulation, **Then** it fails before any agents move with an explicit error about missing extinction
2. **Given** CO, CO2, and HCN files are missing, **When** I run with available extinction, **Then** speed updates work but FED tracking is disabled with a warning
3. **Given** fdsvismap pickle file is unavailable, **When** I request visibility data, **Then** the system derives local visibility from extinction and disables waypoint line-of-sight logic

---

### User Story 5 - Runtime Orchestration (Priority: P1)

I want a runtime session that orchestrates all modules (alignment, sampling, speed, routing, FED, JuPedSim adapter) without implementing any behavior logic itself.

**Why this priority**: The runtime layer needs to coordinate periodic updates from fire fields to agents. Mixing orchestration with logic makes testing and maintenance difficult.

**Independent Test**: Can be fully tested by mocking all behavior modules and verifying the runtime calls them in the correct order with correct data flows.

**Acceptance Scenarios**:

1. **Given** I start a simulation session, **When** each simulation tick completes, **Then** the runtime updates agent speeds, checks routing, and accumulates FED
2. **Given** I examine the runtime code, **When** I check its imports, **Then** it imports ONLY from the six canonical modules and no behavior logic itself
3. **Given** a warning occurs (e.g., missing data), **When** it happens, **Then** the runtime logs it without halting the simulation

---

### User Story 6 - v1 Quantity Contract (Priority: P2)

I want the FDS quantity requirements for v1 to be documented so users know what files their FDS simulations must export for minimal, recommended, and full support.

**Why this priority**: Users running FDS simulations need to know which outputs to enable. Clear documentation prevents confusion and ensures successful integration.

**Independent Test**: Can be fully tested by running example FDS cases with different quantity combinations and verifying the system reports correct support level.

**Acceptance Scenarios**:

1. **Given** I run an FDS case with extinction only, **When** I load it into pyFDS-Evac, **Then** the system reports "minimal support: speed updates available"
2. **Given** I run an FDS case with extinction and visibility maps, **When** I load it, **Then** the system reports "recommended support: speed, routing, visibility-based waypoints"
3. **Given** I run an FDS case with extinction, visibility, and gas concentrations, **When** I load it, **Then** the system reports "full support: all features enabled"

---

### Edge Cases

- What happens when FDS output files exist but are corrupted or incomplete?
- How does the system handle cases where the geometry in the FDS file doesn't match the JuPedSim scenario geometry?
- What happens when time indices between FDS outputs and simulation ticks don't align?
- How does the system handle cases where agents are positioned outside the FDS grid boundaries?

## Requirements *(mandatory)*

### Functional Requirements

#### Module Structure

- **FR-001**: The codebase MUST be organized into exactly six canonical modules: `pyfdsevac/io`, `pyfdsevac/fields`, `pyfdsevac/behavior`, `pyfdsevac/runtime`, `pyfdsevac/interfaces`, and `pyfdsevac/cli`
- **FR-002**: Each module MUST import ONLY from modules lower in the dependency chain (io has no dependencies, fields imports from io, behavior imports from fields, runtime imports from all above)
- **FR-003**: The module dependency order MUST be enforced by linting tools with clear error messages when violated

#### IO Layer

- **FR-004**: `pyfdsevac/io/fds_source.py` MUST use `fdsreader` to load raw FDS quantities
- **FR-005**: `pyfdsevac/io/visibility_source.py` MUST use `fdsvismap` for visibility-specific computations
- **FR-006**: Both IO modules MUST hide their underlying libraries behind the `pyfdsevac/fields/catalog.py` API
- **FR-007**: IO modules MUST explicitly report which quantities are missing rather than guessing or inferring defaults
- **FR-008**: When a required FDS quantity is missing, the system MUST fail with an explicit error message before simulation starts

#### Field Abstraction

- **FR-009**: `pyfdsevac/fields/catalog.py` MUST provide a single source of truth for "what fire quantities are available for this case"
- **FR-010**: `pyfdsevac/fields/catalog.py` MUST expose canonical field names: extinction, soot, temperature, CO, CO2, HCN, HCl, and optional radiation-related outputs
- **FR-011**: `pyfdsevac/fields/sampler.py` MUST provide a uniform sampling API that accepts `(x, y, z, t)` coordinates for any quantity
- **FR-012**: `pyfdsevac/fields/alignment.py` MUST align FDS coordinates with scenario geometry and validate overlap assumptions
- **FR-013**: When sampling a point outside the FDS grid, the system MUST return a clear error or warning

#### Behavior Modules

- **FR-014**: `pyfdsevac/behavior/speed.py` MUST compute speed factor from extinction or soot-derived extinction
- **FR-015**: `pyfdsevac/behavior/routing.py` MUST compute door/path fire summaries and choose targets using FDS+Evac-inspired logic
- **FR-016**: `pyfdsevac/behavior/fed.py` MUST produce local FED-equivalent field and accumulate cumulative FED per agent
- **FR-017**: Each behavior module MUST declare its mandatory inputs for v1 functionality

#### Runtime

- **FR-018**: `pyfdsevac/runtime/session.py` MUST orchestrate the simulation loop using only public APIs from alignment, sampler, speed, routing, fed, and jupedsim_adapter
- **FR-019**: `pyfdsevac/runtime/session.py` MUST log warnings when optional quantities are missing or derived
- **FR-020**: `pyfdsevac/runtime/session.py` MUST NOT implement any behavior logic (speed calculation, routing decisions, FED accumulation)

#### v1 Quantity Contract

- **FR-021**: The system MUST document the minimum FDS quantities required for v1: extinction coefficient or enough soot data to derive it
- **FR-022**: The system MUST document gas quantities required for full FED v1: CO, CO2, HCN, temperature, and either O2 directly or documented derivation strategy
- **FR-023**: The system MUST report support level ("minimal", "recommended", "full") when loading FDS results

### Key Entities

- **FireQuantity**: A named fire-related quantity (extinction, soot, temperature, CO, CO2, HCN, HCl, radiation) with canonical name and metadata
- **FireField**: A spatial and temporal field representing a fire quantity at specific simulation time
- **Sampler**: An abstraction that provides access to fire fields at arbitrary (x, y, z, t) coordinates
- **Catalog**: A registry of available fire quantities and their sources
- **SimulationResult**: Structured output including agent trajectories, speed history, FED history, and warnings

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The module dependency tree has exactly six modules with no circular dependencies (verified by linting)
- **SC-002**: All behavior modules can be tested with mocked sampler data without accessing real FDS files
- **SC-003**: The system completes v1 speed+routing with minimal FDS quantities (extinction only) in under 5 minutes for a 100-agent simulation
- **SC-004**: The system reports correct support level ("minimal"/"recommended"/"full") for FDS cases with different quantity combinations
- **SC-005**: When extinction is missing, the system fails immediately before any agents move (within first simulation tick)

### Business Outcomes

- **SC-006**: New developers can understand the codebase structure in under 30 minutes by examining module boundaries
- **SC-007**: Adding a new data source (beyond fdsreader/fdsvismap) requires changes to only one IO module, not behavior modules