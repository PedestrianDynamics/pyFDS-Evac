# Data Model: Module Dependency Tree

**Feature**: Module Dependency Tree  
**Branch**: `005-module-dependency-tree`  
**Date**: 2026-03-24

## Entities

### FireQuantity

Represents a named fire-related quantity with metadata.

**Fields**:
- `name`: str - Canonical name (extinction, soot, temperature, CO, CO2, HCN, HCl, radiation)
- `unit`: str - Physical unit (1/m, kg/m³, K, %, etc.)
- `required_for`: List[str] - Behavior modules that require this (e.g., ["speed", "fed"])
- `source_type`: str - Where it comes from (fdsreader, fdsvismap, derived)

**Validation Rules**:
- `name` must be one of the canonical names
- `required_for` cannot be empty
- `source_type` must be one of: "fdsreader", "fdsvismap", "derived"

**State Transitions**: N/A (immutable definition)

---

### FireField

Represents a spatial and temporal field for a fire quantity at a specific simulation time.

**Fields**:
- `quantity`: FireQuantity - The quantity type
- `time`: float - Simulation time in seconds
- `data`: np.ndarray - 3D array (x, y, z) of values
- `coordinates`: dict - Grid metadata (x_coords, y_coords, z_coords arrays)

**Validation Rules**:
- `time` must be >= 0
- `data` shape must match coordinates dimensions
- All coordinate arrays must be monotonically increasing

**State Transitions**: N/A (immutable snapshot)

---

### Catalog

Registry of all available fire quantities for a loaded FDS case.

**Fields**:
- `available`: Dict[str, FireQuantity] - Map of quantity name to definition
- `sources`: Dict[str, str] - Map of quantity name to source module
- `support_level`: str - "minimal", "recommended", or "full"

**Validation Rules**:
- `support_level` must be one of: "minimal", "recommended", "full"
- Each quantity in `available` must have an entry in `sources`

**State Transitions**:
1. `empty` → `minimal`: extinction quantity available
2. `minimal` → `recommended`: visibility quantity added
3. `recommended` → `full`: all gas quantities (CO, CO2, HCN, temperature) added

---

### Sampler

Abstraction for querying fire fields at arbitrary coordinates.

**Fields**:
- `catalog`: Catalog - Available quantities registry
- `fields`: Dict[str, List[FireField]] - Time-series fields per quantity

**Validation Rules**:
- Sampler must have at least one quantity in catalog
- All fields must be aligned to same spatial grid

**State Transitions**: N/A (configured once, read-only after)

---

### SimulationResult

Structured output from a complete simulation run.

**Fields**:
- `trajectories`: List[AgentTrajectory] - Agent positions over time
- `speed_history`: Dict[int, List[float]] - Speed per agent per tick
- `fed_history`: Dict[int, List[float]] - Cumulative FED per agent per tick
- `warnings`: List[str] - All warnings generated during simulation
- `metadata`: dict - Simulation parameters (seed, duration, tick rate)

**Validation Rules**:
- All agent IDs in histories must match trajectories
- Time steps must be consistent across all histories
- No duplicate warnings

**State Transitions**: N/A (immutable result)

---

### AgentTrajectory

Path of a single agent through the simulation.

**Fields**:
- `agent_id`: int - Unique identifier
- `positions`: List[Tuple[float, float, float]] - (x, y, z) coordinates per tick
- `exit_time`: Optional[float] - Time when agent reached exit (if applicable)

**Validation Rules**:
- `agent_id` must be positive
- All positions must be within walkable area bounds
- `exit_time` must be >= simulation start time if present

**State Transitions**: N/A (immutable record)

---

## Relationships

| Entity | Relationship | Cardinality |
|--------|-------------|-------------|
| Catalog | contains | FireQuantity (1:N) |
| Sampler | uses | Catalog (1:1) |
| Sampler | contains | FireField (1:N per quantity) |
| SimulationResult | contains | AgentTrajectory (1:N) |
| SimulationResult | contains | speed_history (1:1 per agent) |
| SimulationResult | contains | fed_history (1:1 per agent) |
| BehaviorModule | requires | FireQuantity (M:N) |

## Key Dependencies

- **io layer** → creates FireFields from raw FDS data
- **fields layer** → builds Catalog and Sampler from FireFields
- **behavior layer** → consumes Sampler to query FireFields
- **runtime layer** → aggregates results into SimulationResult
