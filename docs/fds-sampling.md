# FDS slice sampling

> Part of [pyFDS-Evac](../README.md).

The `SliceFieldSampler` class in `src/core/fds_sampling.py` provides
nearest-neighbor spatial and temporal lookup on horizontal FDS slice
files. It's the shared pyFDS-Evac data-access layer used by both the
smoke-speed model (extinction coefficient) and the FED model (gas
concentrations).

## How it works

`SliceFieldSampler` wraps a single `fdsreader` slice object and
exposes a `sample(time_s, x, y)` method that returns the scalar value
at the nearest grid cell and timestep.

Internally it:

1. Finds the subslice whose bounding box covers the queried `(x, y)`
   point (one subslice per FDS mesh the slice intersects).
2. Resolves the nearest timestep index via binary search
   (`get_nearest_timestep`).
3. Computes the nearest cell indices along the x and y axes.
4. Returns `subslice.data[t_index, i_index, j_index]`.

### Performance caches

Two caches reduce per-call overhead on hot paths (for example, sampling
along a line of sight where all points share the same timestep and
typically the same subslice):

- **Last-hit subslice cache** -- the most recently matched subslice is
  checked first before falling back to a linear scan. Consecutive
  sample points along a ray almost always hit the same subslice.
- **Timestep cache** -- when `time_s` hasn't changed since the last
  call, the cached `t_index` is reused, skipping the binary search.

## Loading a sampler

Use `load_slice_sampler()` to load a single FDS quantity:

```python
from src.core.fds_sampling import load_slice_sampler

sampler = load_slice_sampler(
    "path/to/fds_case",
    "SOOT EXTINCTION COEFFICIENT",
)
value = sampler.sample(time_s=30.0, x=5.0, y=3.0)
```

### Selecting a slice height

When an FDS case contains multiple horizontal slices for the same
quantity at different heights, pass `slice_height_m` to select the
closest one:

```python
sampler = load_slice_sampler(
    "path/to/fds_case",
    "SOOT EXTINCTION COEFFICIENT",
    slice_height_m=2.0,
)
```

If only one slice matches the quantity, `slice_height_m` has no effect.

### Sharing a `Simulation` instance

Parsing an FDS case directory is expensive. When you need both
extinction and FED fields from the same case, load the `Simulation`
once and pass it to both factory methods:

```python
from fdsreader import Simulation
from src.core.smoke_speed import ExtinctionField
from src.core.fed import FdsFedField

sim = Simulation("path/to/fds_case")
extinction = ExtinctionField.from_fds("path/to/fds_case", simulation=sim)
fed_field = FdsFedField.from_fds("path/to/fds_case", simulation=sim)
```

All three factory functions (`load_slice_sampler`,
`ExtinctionField.from_fds`, `FdsFedField.from_fds`) accept an optional
`simulation` keyword argument. When omitted, each creates its own
`Simulation` instance internally.

## Integration with models

### Smoke-speed model

`ExtinctionField` wraps a `SliceFieldSampler` for the
`SOOT EXTINCTION COEFFICIENT` quantity and exposes
`sample_extinction(time_s, x, y)`:

```python
from src.core.smoke_speed import ExtinctionField, SmokeSpeedModel

field = ExtinctionField.from_fds("path/to/fds_case", slice_height_m=2.0)
model = SmokeSpeedModel(field, config)
speed_factor = model.sample(time_s=30.0, x=5.0, y=3.0)
```

If a queried point falls outside the FDS domain, `sample_extinction`
returns `0.0` (clear air) and logs a warning on the first occurrence.

### FED model

`FdsFedField` creates one `SliceFieldSampler` per gas species (CO,
CO2, O2, and optionally HCN, NO, NO2, HCl, HBr, HF, SO2, acrolein,
formaldehyde):

```python
from src.core.fed import FdsFedField, DefaultFedModel

fed_field = FdsFedField.from_fds("path/to/fds_case")
model = DefaultFedModel(fed_field)
inputs = model.sample_inputs(time_s=30.0, x=5.0, y=3.0)
```

### Line-of-sight extinction

The `integrated_extinction_along_los()` function in
`src/core/route_graph.py` computes the Beer-Lambert path-integrated
mean extinction coefficient between two points. It samples at uniform
intervals along the ray and returns the arithmetic mean:

```python
from src.core.route_graph import integrated_extinction_along_los

k_mean = integrated_extinction_along_los(
    x_from=1.0, y_from=2.0,
    x_to=10.0, y_to=2.0,
    time_s=30.0,
    extinction_sampler=field,
    step_m=2.0,
)
```

This is the discrete form of Boerger et al. (2024), Eq. 8-9, and is
used internally by the route-cost evaluator for smoke-aware rerouting.
