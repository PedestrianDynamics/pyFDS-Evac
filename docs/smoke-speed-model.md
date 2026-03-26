# Smoke-speed model

> Part of [pyFDS-Evac](../README.md).

The pyFDS-Evac smoke-speed model reduces walking speed based on local
smoke conditions. It uses the extinction coefficient K [1/m] as its
primary input and applies a linear speed-reduction law derived from
the original FDS+Evac / Frantzich-Nilsson (Lund) correlation.

## Speed-reduction law

The model computes a multiplicative speed factor from the local
extinction coefficient:

```
speed_factor(K) = 1 + beta * K / alpha
```

The factor is clamped to `[min_speed_factor, 1.0]`, so agents always
retain a minimum fraction of their clear-air speed. With the default
coefficients:

| Parameter          | Default | Description                         |
|--------------------|---------|-------------------------------------|
| `alpha`            | 0.706   | Normalization constant              |
| `beta`             | -0.057  | Slope (negative = speed decreases)  |
| `min_speed_factor` | 0.1     | Floor for the speed multiplier      |

The actual walking speed is:

```
v(K) = v0 * speed_factor(K)
```

where `v0` is the agent's clear-air speed.

## Extinction sources

The model accepts any object that implements the `ExtinctionSampler`
protocol (a `sample_extinction(time_s, x, y) -> float` method). Two
built-in implementations are provided:

- **`ExtinctionField`** -- reads the `SOOT EXTINCTION COEFFICIENT`
  quantity from FDS slice data via `fdsreader`. Use this for real FDS
  output.
- **`ConstantExtinctionField`** -- returns a fixed K value everywhere.
  Use this for deterministic verification cases such as ISO 20414
  Table 21.

### Loading from FDS data

```python
from src.core.smoke_speed import ExtinctionField, SmokeSpeedConfig

field = ExtinctionField.from_fds(
    "path/to/fds_case",
    slice_height_m=2.0,   # select the horizontal slice closest to 2 m
)
```

If a queried point falls outside the FDS domain, `sample_extinction`
returns `0.0` (clear air) and logs a warning on the first occurrence.

### Using a constant field

```python
from src.core.smoke_speed import ConstantExtinctionField

field = ConstantExtinctionField(extinction_per_m=1.0)
```

## Configuration

`SmokeSpeedConfig` bundles the model coefficients with runtime
settings:

```python
from src.core.smoke_speed import SmokeSpeedConfig

config = SmokeSpeedConfig(
    fds_dir="path/to/fds_case",
    update_interval_s=1.0,    # how often agents resample extinction
    slice_height_m=2.0,       # FDS slice height
    alpha=0.706,
    beta=-0.057,
    min_speed_factor=0.1,
)
```

The `update_interval_s` controls how frequently each agent queries the
extinction field during the simulation loop. A value of `1.0` means
one sample per agent per second of simulated time.

## Putting it together

```python
from src.core.smoke_speed import (
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

Two helper functions support the soot-density-based workflow used in
FDS+Evac:

- `extinction_from_soot_density(soot_density_mg_per_m3)` -- converts
  soot density to extinction using
  `K = K_m * rho_s * 1e-6`, where `K_m = 8700 m^2/kg` is the
  mass-specific extinction coefficient for red light at 633 nm.
- `speed_from_soot_density(base_speed, soot_density_mg_per_m3)` --
  computes the reduced walking speed directly from soot density.

## References

- Jin (1970-1978): empirical visibility-extinction correlation
  `V = C / sigma`
- Frantzich & Nilsson (Lund): linear speed-extinction relation used
  by FDS+Evac
- Ronchi et al. (2013): interpretation A3 comparison across
  evacuation tools
- Boerger et al. (2024), Fire Safety Journal 150:104269:
  Beer-Lambert integrated extinction along line of sight (Eq. 8-9)
