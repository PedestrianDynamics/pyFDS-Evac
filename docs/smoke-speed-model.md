---
title: "Smoke-speed model"
weight: 9
---

> Part of [pyFDS-Evac](../README.md).

The pyFDS-Evac smoke-speed model reduces agent walking speed based on
local smoke conditions. It takes the extinction coefficient K [1/m] as
its primary input and applies one of two speed-reduction laws, selected
via `SmokeSpeedConfig.speed_law`.

## Speed-reduction laws

`speed_law="lund"` (default) applies the linear Frantzich–Nilsson law in the
FDS+Evac fractional form, clamped to `[min_speed_factor, 1.0]`;
`speed_law="fridolf"` applies `V / (V + 2)` through the sighting distance
`V = C / K`, with no floor. Its attribution to Fridolf et al. (2019) is
unverified: the paper's own law differs
([#146](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/146)). In both cases the
agent walks at `v0 * speed_factor(K)`, where `v0` is its clear-air speed.

The coded equations, the `SmokeSpeedConfig` defaults and the departures from
the literature are on the [smoke-speed model](/models/smoke-speed.md) page;
the published laws are on
[Walking speed in smoke](/fundamentals/walking-speed.md).

## Extinction sources

The model accepts any object that implements the `ExtinctionSampler`
protocol (a `sample_extinction(time_s, x, y) -> float` method). Two
built-in implementations are available:

- **`ExtinctionField`** -- reads the `SOOT EXTINCTION COEFFICIENT`
  quantity from FDS slice data via `fdsreader`. Use this for real FDS
  output.
- **`ConstantExtinctionField`** -- returns a fixed K value everywhere.
  Use this for deterministic verification cases such as ISO 20414
  Table 21.

### Loading from FDS data

To load extinction data from an FDS case directory:

```python
from pyfds_evac.core.smoke_speed import ExtinctionField

field = ExtinctionField.from_fds(
    "path/to/fds_case",
    slice_height_m=2.0,   # select the horizontal slice closest to 2 m
)
```

If a queried point falls outside the FDS domain, `sample_extinction`
returns `0.0` (clear air) and logs a warning on the first occurrence.

### Using a constant field

To use a uniform extinction value for verification:

```python
from pyfds_evac.core.smoke_speed import ConstantExtinctionField

field = ConstantExtinctionField(extinction_per_m=1.0)
```

## Configuration

`SmokeSpeedConfig` bundles the model coefficients with runtime
settings:

```python
from pyfds_evac.core.smoke_speed import SmokeSpeedConfig

config = SmokeSpeedConfig(
    fds_dir="path/to/fds_case",
    update_interval_s=1.0,    # how often agents resample extinction
    slice_height_m=2.0,       # FDS slice height
    speed_law="lund",         # or "fridolf"
)
```

The law coefficients (`alpha`, `beta`, `min_speed_factor`,
`visibility_factor_c`) are further fields; their defaults are listed on the
[smoke-speed model](/models/smoke-speed.md#parameters) page.

The `update_interval_s` field controls how frequently each agent
queries the extinction field during the simulation loop. A value of
`1.0` means one sample per agent per second of simulated time.

## Putting it together

To create a full smoke-speed model and query it:

```python
from pyfds_evac.core.smoke_speed import (
    ExtinctionField,
    SmokeSpeedConfig,
    SmokeSpeedModel,
)

field = ExtinctionField.from_fds(config.fds_dir)
model = SmokeSpeedModel(field, config)

# Query at a specific point and time
extinction_K, speed_factor = model.sample(time_s=30.0, x=5.0, y=3.0)

# Or get just the factor
factor = model.speed_factor(time_s=30.0, x=5.0, y=3.0)
```

## Conversion utilities

Two helper functions support the soot-density-based workflow from the
original FDS+Evac guide:

- `extinction_from_soot_density(soot_density_mg_per_m3)` -- converts
  soot density to extinction using `K = K_m * rho_s * 1e-6`, where `K_m`
  (`mass_extinction_coefficient_m2_per_kg`, default 8700 m²/kg) is the FDS
  default mass-specific extinction coefficient (see
  [Extinction coefficient](/fundamentals/extinction.md)).
- `speed_from_soot_density(base_speed, soot_density_mg_per_m3)` --
  computes the reduced walking speed directly from soot density.

## References

- [Smoke-speed model](/models/smoke-speed.md): coded form, defaults and
  deviations from the literature.
- [Walking speed in smoke](/fundamentals/walking-speed.md) and
  [Extinction coefficient](/fundamentals/extinction.md): the published laws
  and their sources.
- [evac.f90](../materials/evac.f90) -- Original FDS+Evac Fortran
  source for cross-referencing implementation details.
