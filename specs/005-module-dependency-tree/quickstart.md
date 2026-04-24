# Quickstart: Module Dependency Tree

## Test Scenarios

### Scenario 1: Minimal Support (Extinction Only)

**Setup**: FDS simulation with extinction coefficient only

**Expected Behavior**:
1. `Catalog` reports support level: "minimal"
2. `SpeedCalculator` works with extinction data
3. `RoutePlanner` derives visibility from extinction
4. `FEDAccumulator` disabled with warning
5. Simulation runs speed+routing only

**Test Cases**:
- [ ] Extinction missing → fail before first agent move
- [ ] Extinction present → speed updates work
- [ ] FED disabled → warning logged, no errors

---

### Scenario 2: Recommended Support (Extinction + Visibility)

**Setup**: FDS simulation with extinction + fdsvismap visibility

**Expected Behavior**:
1. `Catalog` reports support level: "recommended"
2. `SpeedCalculator` works
3. `RoutePlanner` uses fdsvismap for accurate visibility
4. Waypoint line-of-sight logic enabled

**Test Cases**:
- [ ] Visibility from fdsvismap → more accurate than derived
- [ ] Route planning uses true visibility data
- [ ] Line-of-sight waypoint logic enabled

---

### Scenario 3: Full Support (All Quantities)

**Setup**: FDS simulation with extinction, visibility, CO, CO2, HCN, temperature

**Expected Behavior**:
1. `Catalog` reports support level: "full"
2. All behavior modules fully functional
3. FED accumulation active
4. Speed, routing, and FED all running

**Test Cases**:
- [ ] All gas quantities present → FED active
- [ ] Full feature set enabled
- [ ] No warnings for missing data

---

### Scenario 4: Graceful Degradation

**Setup**: FDS simulation with extinction + CO2 only (missing CO, HCN)

**Expected Behavior**:
1. `Catalog` reports support level: "recommended" (not full)
2. Speed + routing work
3. FED disabled with warning
4. Simulation continues without FED

**Test Cases**:
- [ ] Missing gas quantities → FED disabled, not crashed
- [ ] Warning logged for missing FED inputs
- [ ] Speed + routing continue normally

---

### Scenario 5: Coordinate Alignment

**Setup**: FDS grid offset from scenario geometry

**Expected Behavior**:
1. `Alignment` maps world to FDS coordinates
2. Sampling uses correct grid indices
3. Bounds checking catches out-of-grid queries

**Test Cases**:
- [ ] Out-of-bounds query → clear error or warning
- [ ] Coordinate mapping accurate to grid resolution
- [ ] Missing overlap → fail with descriptive error

---

### Scenario 6: Mocked Behavior Testing

**Setup**: Behavior module with mocked sampler

**Expected Behavior**:
1. Sampler returns known test data
2. Behavior module computes correct output
3. No real FDS file access required

**Test Cases**:
- [ ] Mock sampler with known extinction → correct speed factor
- [ ] Mock sampler with known gas concentrations → correct FED rate
- [ ] Mock routing engine → correct waypoint selection
