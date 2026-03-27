# Demo scenario: smoke-blocked T-corridor

This scenario demonstrates all three pyFDS-Evac model features:
speed reduction, FED incapacitation, and dynamic rerouting.

## Geometry

A T-shaped corridor where agents spawn in a dead-end branch and must
walk through the fire zone to reach either exit.

```
  Exit A ←─── 20 m ───┬─── 10 m ───→ Exit B
  (left)               │ fire          (right)
                       │ at junction
                  ┌────┴────┐
                  │  agents  │  6 m wide
                  │  spawn   │  10 m deep
                  └─────────┘
```

- Horizontal corridor: 30 m x 3 m (y = 10 to 13)
- Vertical branch: 6 m x 10 m (x = 17 to 23, y = 0 to 10)
- Exit A at x = 0 (20 m from junction)
- Exit B at x = 30 (10 m from junction)
- 50 agents spawn in the branch at t = 0

## Fire setup (demo.fds)

A 1 MW PVC-cable fire at the junction produces heavy soot and toxic
gases. The fire ramps up over 60 seconds.

| Property | Value |
|----------|-------|
| Fuel | PVC cable (C2H3Cl) |
| Peak HRR | 1 MW (500 kW/m^2 x 2 m^2) |
| Soot yield | 0.172 |
| CO yield | 0.063 |
| HCN yield | 0.006 |
| HCl yield | 0.48 |
| Ramp-up | 0 to 100% over 60 s |
| Ceiling height | 3 m |
| Grid | 0.25 m (120 x 52 x 12 cells) |

## FDS slice outputs

Horizontal slices at z = 2 m (head height):

| Slice quantity | Used by |
|----------------|---------|
| Extinction coefficient | Smoke-speed model |
| Carbon monoxide volume fraction | FED (CO narcosis) |
| Carbon dioxide volume fraction | FED (hyperventilation factor) |
| Oxygen volume fraction | FED (hypoxia) |
| Hydrogen cyanide volume fraction | FED (CN narcosis) |
| Hydrogen chloride volume fraction | FED (irritant) |
| Visibility | Smokeview visualization only |

## Why all three features are exercised

**Speed reduction.** Agents approaching the junction encounter
increasing extinction, reducing their walking speed via the
Frantzich-Nilsson correlation.

**FED incapacitation.** The 6 m branch narrows to a 3 m corridor,
creating a bottleneck at the junction. Agents queuing in heavy smoke
accumulate CO, HCN, and HCl exposure. The high HCl yield from PVC
drives the irritant term, while CO and O2 depletion contribute to
narcosis. Some agents reach FED = 1.0 and become incapacitated.

**Rerouting.** Exit B is initially closer (10 m vs 20 m), so agents
prefer it. As smoke builds and drifts right, the route cost to Exit B
increases and agents switch to Exit A.

## Running

1. Run the FDS simulation:

```bash
fds assets/demo/demo.fds
```

2. Run the evacuation:

```bash
uv run python run.py \
  --scenario assets/demo \
  --fds-dir assets/demo \
  --enable-rerouting \
  --reroute-interval 5 \
  --output-smoke-history smoke.csv \
  --output-fed-history fed.csv \
  --output-route-history routes.csv
```
