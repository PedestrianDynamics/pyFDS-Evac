# FED Tracking: Research

**Feature**: FED Tracking  
**Branch**: 004-fed-tracking  
**Created**: 2026-03-23

---

## Research Questions

### 1. FDS Smoke Data Interpolation

**Question**: How to compute pedestrian-specific exposure from FDS grid data?

**Approach**:
- Use inverse distance weighting (IDW) for smoke concentration interpolation
- Linear interpolation for time-varying smoke data between time steps
- Consider pedestrian size (finite volume) for high-gradient regions

**Decision**: Use IDW with power coefficient p=2 for smoke concentration, combined with temporal linear interpolation.

**Rationale**:
- IDW is computationally efficient and widely used in fire dynamics
- Power coefficient p=2 balances local vs. distant influence
- Linear temporal interpolation sufficient for typical time step sizes

**Alternatives considered**:
- Kriging interpolation: More accurate but computationally expensive
- Bilinear interpolation: Less accurate for irregular pedestrian paths
- Nearest neighbor: Too coarse for exposure calculation

---

### 2. FED Accumulation Formula

**Question**: How to implement ISO 13571 FED calculation?

**Approach**:
```
FED = FED_CO2 + FED_CO
where:
  FED_CO2 = ∫(CO₂ concentration / 10000) dt
  FED_CO = ∫(CO concentration / 1000) dt
```

**Decision**: Implement time-step integration using trapezoidal rule for better accuracy.

**Rationale**:
- Trapezoidal rule provides second-order accuracy
- Matches FDS time step output format
- Standard practice in fire exposure analysis

**Formula**:
```
FED_increment = 0.5 × (CO₂_prev/10000 + CO₂_curr/10000) × Δt
              + 0.5 × (CO_prev/1000 + CO_curr/1000) × Δt
```

**Alternatives considered**:
- Euler method (forward difference): Simpler but less accurate
- Simpson's rule: Requires evenly spaced time steps (not always true)
- Pre-computed FED from FDS: Not always available in output

---

### 3. JuPedSim Trajectory API

**Question**: How to record FED values at each simulation time step?

**Approach**:
- Hook into JuPedSim pedestrian step callback
- Access pedestrian state (position, velocity) per time step
- Query smoke field for local concentration at position

**Decision**: Use JuPedSim's pedestrian callback API to record FED per step.

**Rationale**:
- Callback API ensures per-step execution
- Minimal performance overhead
- Standard pattern for post-processing in simulation frameworks

**Implementation**:
```python
def step_callback(pedestrian):
    position = pedestrian.get_position()
    smoke_conc = smoke_field.interpolate(position)
    fed_increment = compute_fed_increment(smoke_conc, time_delta)
    return fed_increment
```

**Alternatives considered**:
- Post-simulation trajectory replay: Less accurate, requires storing full state
- Custom output module: Requires JuPedSim source modification
- External tracking: Complex synchronization with simulation

---

### 4. Integration with Routing Module

**Question**: How to pass FED metrics from tracking to routing module?

**Approach**:
- Routing module queries exposure tracker for door-specific metrics
- FED metrics cached per door candidate per pedestrian
- Integration via data contract (DoorFEDMetrics dataclass)

**Decision**: Use query-based integration where routing explicitly requests metrics.

**Rationale**:
- Loose coupling between modules
- Clear data contracts via Pydantic dataclasses
- Easy to test modules independently

**Interface**:
```python
# Routing requests metrics
door_metrics = exposure_tracker.get_door_metrics(
    pedestrian_id="ped_001",
    door_id="door_exit_A"
)

# Returns DoorFEDMetrics with FED_max_Door and K_ave_Door
```

**Alternatives considered**:
- Push-based events: More complex state management
- Shared memory cache: Risk of stale data
- Direct function calls: Tight coupling between modules

---

## Implementation Roadmap

### Phase 0: Smoke Interpolation
- [ ] Implement IDW smoke concentration interpolation
- [ ] Add temporal interpolation for time-varying data
- [ ] Test with FDS output files

### Phase 1: FED Accumulation
- [ ] Implement ISO 13571 FED formula
- [ ] Add trapezoidal integration
- [ ] Unit tests for FED computation

### Phase 2: Tracking Module
- [ ] Implement `track_exposure()` function
- [ ] Implement `record_door_metrics()` function
- [ ] Integrate with JuPedSim callback API

### Phase 3: Routing Integration
- [ ] Implement `evaluate_candidate_with_fed()`
- [ ] Implement `sort_candidates_by_fed()`
- [ ] Integration tests with routing module

---

## Performance Considerations

### Expected Performance

| Operation | Complexity | Notes |
|-----------|------------|-------|
| Smoke interpolation | O(n) per query | n = number of grid points |
| FED accumulation | O(t) per pedestrian | t = time steps |
| Door metrics | O(1) per door | Cached per pedestrian |
| Route evaluation | O(m log m) | m = number of door candidates |

### Optimization Strategies

1. **Spatial indexing**: Use k-d tree for smoke grid nearest-neighbor lookup
2. **Caching**: Cache door-specific metrics per pedestrian
3. **Vectorization**: Use NumPy for batch smoke interpolation
4. **Lazy loading**: Load FDS data on-demand, not at initialization

---

## Validation Strategy

### Unit Tests

- Test smoke interpolation against known values
- Verify FED accumulation formula with synthetic smoke profiles
- Validate door metrics computation

### Integration Tests

- End-to-end: FDS data → tracking → diagnostics
- Test routing module uses FED metrics correctly
- Verify CLI output format

### Accuracy Requirements

- Smoke interpolation: <5% error vs. reference
- FED accumulation: <2% error vs. analytical solution
- Door metrics: 100% coverage for all candidates

---

## References

1. ISO 13571:2000 - Fire safety engineering — Assessment of fire safety in buildings
2. FDS+Evac Documentation - Smoke data output format
3. JuPedSim API Documentation - Pedestrian simulation framework