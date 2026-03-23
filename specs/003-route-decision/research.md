# Route-Decision Logic Research

**Feature**: Route-Decision Logic  
**Branch**: 003-route-decision  
**Created**: 2026-03-23  
**Last Updated**: 2026-03-23

---

## Research Tasks Completed

### 1. FDS+Evac Target Selection Algorithm

**Source**: [evac.f90:16300](https://github.com/tmp/evac.f90)

**Decision**: Target selection uses weighted ranking of door candidates based on:
- Average extinction coefficient (K_ave)
- Maximum FED (Fractional Effective Dose)
- Distance from current position
- Visibility classification

**Rationale**: The algorithm computes a "cost" for each candidate and selects the minimum-cost path. The cost function is:
```
cost = w_K * K_ave + w_FED * FED_max + w_dist * distance
```
where weights are tuned for pedestrian behavior realism.

**Alternatives considered**:
- Simple K_ave minimization (rejected: doesn't account for FED exposure)
- Greedy nearest-door selection (rejected: ignores fire exposure)

---

### 2. JuPedSim Dynamic Route API

**Decision**: Use JuPedSim's `change_target()` method to modify pedestrian destinations during simulation.

**Rationale**: The method accepts new door ID and immediately updates pedestrian routing graph traversal. Requires:
- Pedestrian must be at door node (not en route)
- New target must be in routing graph
- Simulation must be paused during modification

**Alternatives considered**:
- Full pedestrian restart (rejected: too expensive computationally)
- Route cache invalidation (rejected: complex state management)

---

### 3. Smoke Data Interpolation

**Decision**: Use spatial interpolation from FDS grid to door positions, then temporal interpolation for time-varying metrics.

**Rationale**: 
- **Spatial**: Bilinear interpolation from surrounding grid points
- **Temporal**: Linear interpolation between time steps
- Door-specific K and FED computed as volume averages over door area

**Formula**:
```
K_door(t) = mean(interpolate_spatial(K_grid(t')))
FED_door(t) = max(integrate(FED_rate(t''), t'' from 0 to t))
```

**Alternatives considered**:
- Single-point nearest neighbor (rejected: inaccurate for large doors)
- Full path integration (rejected: too computationally expensive)

---

### 4. Route-Switch Timing

**Decision**: Target latency < 5 seconds from smoke detection to route change.

**Rationale**: 
- 5 seconds is human perception threshold for reaction time
- Simulation time steps typically 0.1-1.0 seconds
- Must complete within current simulation cycle to avoid inconsistent states

**Implementation**:
```python
if current_time - last_route_switch_time < 5.0:
    check_smoke_threshold()
    if threshold_violated:
        select_new_route()
```

**Alternatives considered**:
- Immediate reaction (rejected: unrealistic for human behavior)
- Fixed delay (rejected: doesn't adapt to smoke growth rate)

---

## Dependencies Verified

### pyfdsevac.fields
✅ Provides FDS smoke data access
- `get_K_at_position(position, time)` - extinction coefficient
- `get_FED_at_position(position)` - cumulative FED

### pyfdsevac.runtime
✅ Provides pedestrian simulation interface
- `get_pedestrian_position(ped_id)` - current location
- `get_route_graph()` - door connectivity graph

### Existing Routing Graph
✅ Data structure available
- `doors` - dict of door IDs to positions
- `connectivity` - adjacency list of door connections

---

## Integration Patterns Established

### Data Flow
```
FDS Output (HRR,Smoke) 
    ↓ fields module
DoorCandidate Metrics
    ↓ routing module
RouteEvaluator → RouteDecision
    ↓ runtime module
RouteSwitchEvent → Logging
```

### Error Handling
- All threshold violations logged with door ID and metrics
- Fallback behavior triggered when all candidates fail
- Fatal errors logged with simulation state snapshot

---

## Open Questions

None - all research tasks completed successfully.

---

## References

1. [evac.f90 source](https://github.com/tmp/evac.f90) - FDS+Evac routing algorithm
2. ISO 13571 - Fire safety engineering — Assessment of fire safety in buildings
3. JuPedSim documentation - Dynamic route modification API