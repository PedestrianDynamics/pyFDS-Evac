---
title: "FDS slice sampling"
weight: 18
aliases: [/docs/fds-sampling/, /docs/using/fds-sampling/]
---

How pyFDS-Evac reads FDS slice data at an agent's position: the sampler, how
a slice is chosen by height, and how the models use it. For the slices a
deck must write, see [What your FDS case must provide](fds-case-requirements.md).

The `SliceFieldSampler` class in `pyfds_evac/core/fds_sampling.py` provides
nearest-neighbor spatial and temporal lookup on horizontal FDS slice
files. It's the shared pyFDS-Evac data-access layer used by both the
smoke-speed model (extinction coefficient) and the FED model (gas
concentrations).

## How it works

`SliceFieldSampler` wraps a single `fdsreader` slice object and
exposes a `sample(time_s, x, y)` method that returns the scalar value
at the nearest slice value position and the nearest timestep. The
value positions depend on how FDS wrote the slice ([FDS User Guide](https://github.com/firemodels/fds/blob/c9da70d7a/Manuals/FDS_User_Guide/FDS_User_Guide.tex), `&SLCF`):

- **Node-centred** (the FDS default): one value per mesh node, which
  FDS averages from the cells around that node. The sampler reads the
  nearest node.
- **Cell-centred** (`CELL_CENTERED=T` on the `&SLCF` line): one value
  per cell, without averaging. The sampler reads the nearest cell
  centre, the midpoint of the cell's two nodes, so stretched grids are
  handled.

A query exactly halfway between two positions reads the lower index.

Internally it:

1. Finds the subslice whose bounding box covers the queried `(x, y)`
   point (one subslice per FDS mesh the slice intersects).
2. Resolves the nearest timestep index via binary search
   (`get_nearest_timestep`).
3. Finds the nearest value position along the x and y axes, from the
   mesh nodes inside the subslice extent (midpoints of those nodes for
   cell-centred slices).
4. Returns `subslice.data[t_index, i_index, j_index]`.

### Past the end of the FDS output

The nearest timestep of a time past the last slice frame is the last
frame, so without a check a run longer than the FDS run would walk its
agents through frozen smoke. `sample` therefore raises `FdsHorizonError`
(a `ValueError`) when `time_s` is more than one slice output interval
(the largest spacing between frames; FDS clips the final frame at
`T_END`, so the last spacing can be shorter) past the last frame. The
message names the quantity, the requested time and the last FDS time.
The extinction, gas FED and heat FED fields pass this error on instead
of treating it as an out-of-domain point. `VisibilityModel` raises for a
query past its last vismap time point, which is the first vismap step at
or after the FDS end.

`build_run_kwargs` checks the whole run at setup: a scenario
`max_simulation_time` more than one output interval past the last frame
of any slice in `--fds-dir` with at least two frames stops the run
before it starts. Every such slice in the case counts, including slices
the run does not read, and the check applies even when all agents would
leave before `T_END`.

`--allow-fds-horizon-hold` (`allow_horizon_hold=True` in Python) turns
the setup check into a logged warning and holds the last frame in the
samplers, logging one warning per sampler the first time it happens.

### Outside the FDS slices

A point is inside a slice when a subslice covers it; the subslice extents
are closed intervals, so a point on the outer mesh face is inside. Outside
every subslice, `sample` raises `ValueError`, and each model turns that into
ambient air and clear sight:

| Quantity | Value outside | Warning |
|---|---|---|
| Extinction *K* (speed, route cost) | 0 1/m, speed factor 1 | one, at the first sample outside |
| Gases (CO, CO₂, O₂, optional species) | CO 0 %, CO₂ 0 % (the atmospheric 0.04 % is not used), O₂ 20.9 %, every optional species 0 ppm; FED rate 0 | none |
| Heat, `TEMPERATURE` | 20 °C; the default clothed law then gives 1.2 × 10⁻⁴ /min | none |
| Heat, `INTEGRATED INTENSITY` | *U* and *q* NaN in the FED history, rate 0 | one, at the first sample outside |
| Sign visibility (agent off the vismap grid) | clear air: legible when the sign is within its reading distance, measured from the agent | none |

A route edge prices the part outside as clear air: an edge wholly outside
has optical depth τ = 0, and the outside samples of a partly covered edge
count as *K* = 0 in its mean. The sign case is described on
[Wayfinding](/models/wayfinding.md#off-the-fds-grid).

[FDS+Evac](https://github.com/firemodels/fds/tree/c9da70d7a/Source) reads
smoke, gases and heat the same way. At initialisation it marks every evacuation-grid cell outside every
fire mesh (`IMESH = 0`,
[`evac.f90:6328–6363`](https://github.com/firemodels/fds/blob/c9da70d7a/Source/evac.f90#L6328-L6363)).
Those cells keep zero soot and zero FED, the ambient temperature `TMPA` and
zero radiant flux
([`evac.f90:7250–7272`](https://github.com/firemodels/fds/blob/c9da70d7a/Source/evac.f90#L7250-L7272)).
Sign sight from outside differs: along the line from such an agent,
FDS+Evac still tests walls and averages the smoke of the cells inside the
fire meshes, while pyFDS-Evac tests only the distance ([Wayfinding › Limitations](/models/wayfinding.md#limitations)).

**Partial gas coverage stops the run.** When some loaded gas slices cover a
point and others do not, the gas FED raises `ValueError` and names the
point, the time and the missing quantities
([#427](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/427)). The
heat FED does the same for its `TEMPERATURE` and `INTEGRATED INTENSITY`
slices. The check runs when an agent reaches such a point, not at setup.

**Setup report.** Before the first step, `run_scenario` compares the
scenario with the slices of every sampled quantity. The domain is the area
that every quantity covers. The report gives the walkable area outside
(m² and share), each exit, checkpoint and spawn area outside (m²), each
sign outside, and each route edge outside (m). It is logged once and
stored as `fds_coverage` in `metrics` and in the
[run manifest](outputs.md#run-manifest). For a T-junction whose west
corridor extends 12 m past the FDS mesh, the log reads:

```
FDS coverage: outside the FDS slices (CARBON DIOXIDE VOLUME FRACTION, CARBON
MONOXIDE VOLUME FRACTION, HYDROGEN CHLORIDE VOLUME FRACTION, OXYGEN VOLUME
FRACTION, SOOT EXTINCTION COEFFICIENT), agents read ambient air and clear
sight: walkable area 36.00 m² (19.4 %); exit exit_A_left 3.00 m²;
distribution jps-distributions_out 6.00 m²; sign exit_A_left; edge
jps-checkpoints_0 -> exit_A_left 11.50 m; ...
```

**Flag and count.** Each smoke and FED history row carries `in_fds_domain`,
`False` where the agent stood outside
([Outputs](outputs.md#smoke-history)). At the end, the run logs the number
of agents, samples and agent-seconds outside, stored as
`metrics["fds_outside"]`:

```
Outside the FDS domain: 8 agent(s), 56 sample(s), about 56.0 agent-seconds
of ambient air and clear sight.
```

These two are the signal to check. The first-sample warning of *K* fires
once per run, often at t = 0 for a route sample, and says nothing about
agents later. The route-cost history does not record the length outside
per row ([#431](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/431)).

**Strict option.** `--require-fds-coverage` (`require_fds_coverage=True` on
`run_scenario`, `ExtinctionField`, `FdsFedField`, `FdsHeatField` and
`VisibilityModel`) turns both checks into errors. The run stops at setup
when the report finds anything outside. When a sign also lies off the
vismap grid, the visibility model stops the run while it is built, and
that error names only the signs. Any smoke, FED, heat or sign-visibility sample outside
raises `FdsDomainError`, which names the quantity, the position and the
time. The horizon error of the previous section takes precedence.

### Performance caches

Three caches reduce per-call overhead on hot paths (for example, sampling
along a line of sight where all points share the same timestep and
typically the same subslice):

- **Last-hit subslice cache** -- the most recently matched subslice is
  checked first before falling back to a linear scan. Consecutive
  sample points along a ray almost always hit the same subslice.
- **Timestep cache** -- when `time_s` hasn't changed since the last
  call, the cached `t_index` is reused, skipping the binary search.
- **Axis cache** -- the x and y value positions of each subslice are
  computed once and reused.

## Loading a sampler

Use `load_slice_sampler()` to load a single FDS quantity:

```python
from pyfds_evac.core.fds_sampling import load_slice_sampler

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
    slice_height_m=1.6,  # default of run.py, FDS+Evac HUMAN_SMOKE_HEIGHT
)
```

If only one slice matches the quantity, `slice_height_m` has no effect.
Without `slice_height_m`, `load_slice_sampler` takes the first horizontal
slice in declaration order. The model factories (`ExtinctionField.from_fds`,
`FdsFedField.from_fds`, `FdsHeatField.from_fds`) default to 1.6 m.

The rule lives in `select_horizontal_slice`: vertical slices are
skipped, the slice whose z is nearest `slice_height_m` wins, and a
warning is logged when it is more than 0.5 m away. The visibility model
applies the same function to the extinction slice it hands to fdsvismap.

From the command line the height is `--smoke-slice-height`, 1.6 m by
default (the FDS+Evac `HUMAN_SMOKE_HEIGHT`). The value is an absolute z in
the FDS domain, so it equals the height above the floor where the floor is
at z = 0. C/VM2 and the Engineers Australia note evaluate tenability at
2.0 m ([ASET and RSET](/fundamentals/aset-rset.md)). For a check against
them, run with `--smoke-slice-height 2.0` and write the slices at that
height in the FDS deck (`&SLCF PBZ=2.0`); otherwise the run reads the
nearest slice and warns only when it is more than 0.5 m away
([Silent failure modes](fds-case-requirements.md#silent-failure-modes)).

### Sharing a `Simulation` instance

Parsing an FDS case directory is expensive. When you need both
extinction and FED fields from the same case, load the `Simulation`
once and pass it to both factory methods:

```python
from fdsreader import Simulation
from pyfds_evac.core.smoke_speed import ExtinctionField
from pyfds_evac.core.fed import FdsFedField

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
from pyfds_evac.core.smoke_speed import (
    ExtinctionField,
    SmokeSpeedConfig,
    SmokeSpeedModel,
)

field = ExtinctionField.from_fds("path/to/fds_case")  # slice nearest 1.6 m
model = SmokeSpeedModel(field, SmokeSpeedConfig())
extinction, speed_factor = model.sample(time_s=30.0, x=5.0, y=1.0)
```

`sample` returns the pair (*K*, speed factor); `model.speed_factor(...)`
returns the factor alone. On the tracked `assets/iso_table21_coupled/fds` at
(5, 1) it gives *K* = 0.99550 1/m and a factor of 0.919626.

If a queried point falls outside the FDS domain, `sample_extinction`
returns `0.0` (clear air) and logs a warning on the first occurrence. With
`require_fds_coverage=True` it raises `FdsDomainError` instead; see
[Outside the FDS slices](#outside-the-fds-slices).

### FED model

`FdsFedField` creates one `SliceFieldSampler` per gas species (CO,
CO2, O2, and optionally HCN, NO, NO2, HCl, HBr, HF, SO2, acrolein,
formaldehyde):

```python
from pyfds_evac.core.fed import DefaultFedConfig, DefaultFedModel, FdsFedField

fed_field = FdsFedField.from_fds("path/to/fds_case")  # slices nearest 1.6 m
model = DefaultFedModel(fed_field, DefaultFedConfig())
inputs = model.sample_inputs(time_s=30.0, x=5.0, y=3.0)
```

Each gas is read from its own slice nearest the height, so CO and CO₂ can
come from different heights when the deck declares them at different heights.

### Heat model

`FdsHeatField` reads the `TEMPERATURE` slice nearest the height (1.6 m by
default). With `integrated_intensity=True`, used by
`--heat-radiant-source integrated-intensity`, it also reads the
`INTEGRATED INTENSITY` slice; the two must lie at the same z, or the call
stops with a `ValueError` that names both heights. The layer regime
(`--heat-regime layer`) reads a second `TEMPERATURE` slice at
`--heat-layer-height`.

### Line-of-sight extinction

The `integrated_extinction_along_los()` function in
`pyfds_evac/core/route_graph.py` computes the Beer-Lambert path-integrated
mean extinction coefficient between two points. It samples at uniform
intervals along the ray and returns the arithmetic mean:

```python
from pyfds_evac.core.route_graph import integrated_extinction_along_los

k_mean = integrated_extinction_along_los(
    x_from=1.0, y_from=2.0,
    x_to=10.0, y_to=2.0,
    time_s=30.0,
    extinction_sampler=field,
    step_m=2.0,
)
```

This is the discrete form of
[Boerger et al. (2024)](https://doi.org/10.1016/j.firesaf.2024.104269),
Eq. 8-9, and is used internally by the route-cost evaluator for
smoke-aware [routing](routing.md).

## Next steps

- [FDS case requirements](fds-case-requirements.md) -- the `&SLCF` lines a
  case must declare, and the failure modes when they're missing.
- [Smoke-speed model](/models/smoke-speed.md) -- how extinction drives
  agent speed reduction.
- [Smoke-aware routing](routing.md) -- how extinction and FED drive
  dynamic route selection.
