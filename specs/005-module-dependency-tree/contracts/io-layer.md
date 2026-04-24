# IO Layer Contracts

**Feature**: Module Dependency Tree  
**Branch**: `005-module-dependency-tree`  
**Date**: 2026-03-24

## Purpose

Define interfaces between the IO layer and the fields layer.

## FdsSource API

```python
class FdsSource:
    """Loads raw FDS quantities using fdsreader library."""
    
    def __init__(self, simulation_path: str):
        ...
    
    def get_quantity(self, quantity_name: str) -> List[FireField]:
        ...
    
    def available_quantities(self) -> List[str]:
        ...
    
    def get_grid_info(self) -> dict:
        ...
    
    def get_time_steps(self) -> List[float]:
        ...
```

### Contract

- **Input**: Valid FDS simulation directory path
- **Output**: List of FireField objects with aligned time steps
- **Error Handling**: Explicit errors for missing quantities (no guessing)

## VisibilitySource API

```python
class VisibilitySource:
    """Loads visibility-specific data using fdsvismap library."""
    
    def __init__(self, simulation_path: str, pickle_path: Optional[str] = None):
        ...
    
    def get_visibility(self, time: float, x: float, y: float, z: float) -> float:
        ...
    
    def get_time_aggregated_visibility(self) -> np.ndarray:
        ...
    
    def get_waypoint_visibility(self, waypoints: List[Tuple[float, float]]) -> List[List[float]]:
        ...
```

### Contract

- **Input**: Valid FDS simulation directory, optional pickle cache
- **Output**: Visibility values at queried points
- **Error Handling**: Explicit errors for out-of-bounds requests

## Catalog API

```python
class Catalog:
    """Registry of available fire quantities from all IO sources."""
    
    def __init__(self, fds_source: FdsSource, visibility_source: VisibilitySource):
        ...
    
    def get_available_quantities(self) -> Dict[str, FireQuantity]:
        ...
    
    def has_quantity(self, name: str) -> bool:
        ...
    
    def get_source(self, quantity_name: str) -> str:
        ...
    
    def get_support_level(self) -> str:
        ...
```

### Contract

- **Input**: Two IO sources
- **Output**: Unified view of all available quantities
- **Support Levels**: minimal, recommended, full
