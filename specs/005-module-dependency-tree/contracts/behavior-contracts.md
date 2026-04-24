# Behavior Module Contracts

## Speed Module

```python
class SpeedCalculator:
    """Computes speed factor from extinction or soot-derived extinction."""
    
    def __init__(self, sampler: Sampler):
        ...
    
    def compute_speed_factor(self, time: float, x: float, y: float, z: float) -> float:
        """Compute speed factor at position."""
        ...
    
    @property
    def mandatory_inputs(self) -> List[str]:
        """Return list of mandatory quantities."""
        return ["extinction"]
    
    @property
    def optional_inputs(self) -> List[str]:
        """Return list of optional quantities."""
        return ["soot"]
```

### Contract

- **Input**: Sampler with extinction or soot
- **Output**: Speed factor (0.0 to 1.0)
- **Failure**: If extinction missing, fail immediately

## Routing Module

```python
class RoutePlanner:
    """Computes door/path fire summaries and chooses targets."""
    
    def __init__(self, sampler: Sampler, routing_engine: RoutingEngine):
        ...
    
    def compute_path_fire_summary(self, path: List[Tuple[float, float]]) -> dict:
        """Compute fire conditions along a path."""
        ...
    
    def choose_next_waypoint(self, current_pos: Tuple[float, float], 
                             available_waypoints: List[Tuple[float, float]]) -> int:
        """Select next waypoint based on fire conditions."""
        ...
    
    @property
    def mandatory_inputs(self) -> List[str]:
        return ["extinction", "visibility"]
```

### Contract

- **Input**: Sampler with extinction + visibility, routing engine
- **Output**: Next waypoint index
- **Visibility**: Uses sampler for local visibility along paths

## FED Module

```python
class FEDAccumulator:
    """Accumulates FED-equivalent field and cumulative FED per agent."""
    
    def __init__(self, sampler: Sampler):
        ...
    
    def compute_local_fed(self, time: float, x: float, y: float, z: float) -> float:
        """Compute local FED rate at position."""
        ...
    
    def accumulate_fed(self, agent_id: int, fed_rate: float, dt: float):
        """Accumulate FED for an agent."""
        ...
    
    def get_cumulative_fed(self, agent_id: int) -> float:
        """Return total accumulated FED for agent."""
        ...
    
    @property
    def mandatory_inputs(self) -> List[str]:
        return ["co", "co2", "hcn", "temperature"]
    
    @property
    def optional_inputs(self) -> List[str]:
        return ["hcl", "radiation"]
```

### Contract

- **Input**: Sampler with gas fields
- **Output**: FED rate and cumulative FED per agent
- **Fallback**: If gas fields missing, disable FED with warning
