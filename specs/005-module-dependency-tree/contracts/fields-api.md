# Fields Layer Contracts

## Sampler API

```python
class Sampler:
    """Uniform sampling interface for any fire quantity at (x, y, z, t)."""
    
    def __init__(self, catalog: Catalog):
        ...
    
    def get_quantity(self, quantity_name: str, time: float, x: float, y: float, z: float) -> float:
        """Sample a quantity at arbitrary coordinates.
        
        Args:
            quantity_name: Canonical name (extinction, co, etc.)
            time: Simulation time
            x, y, z: Spatial coordinates
            
        Returns:
            Interpolated value at (x, y, z, time)
            
        Raises:
            OutOfBoundsError: If coordinates outside grid
            MissingQuantityError: If quantity unavailable
        """
        ...
    
    def get_available_quantities(self) -> List[str]:
        """Return list of quantities available for sampling."""
        ...
```

### Contract

- **Input**: Any quantity name + (x, y, z, t) coordinates
- **Output**: Interpolated value at that point
- **Error Handling**: Explicit errors for unavailable quantities

## Alignment API

```python
class Alignment:
    """Maps FDS grid coordinates to scenario geometry."""
    
    def __init__(self, fds_grid: dict, scenario_geometry: WalkableArea):
        ...
    
    def map_to_fds(self, x: float, y: float, z: float) -> Tuple[int, int, int]:
        """Convert world coordinates to FDS grid indices."""
        ...
    
    def map_to_world(self, i: int, j: int, k: int) -> Tuple[float, float, float]:
        """Convert FDS grid indices to world coordinates."""
        ...
    
    def validate_overlap(self) -> bool:
        """Check if FDS grid and scenario geometry overlap."""
        ...
```

### Contract

- **Input**: World coordinates or FDS indices
- **Output**: Mapped coordinates
- **Validation**: Explicit errors if geometry doesn't overlap
