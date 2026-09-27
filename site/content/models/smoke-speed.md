---
title: "Smoke-speed model"
weight: 1
math: true
---

> [!NOTE]
> This page is the specification of the smoke-speed model. For worked cases on
> the assets (runs, figures, numbers), see [Speed in practice](/docs/smoke-speed-model.md).

Based on: [Walking speed in smoke](/fundamentals/walking-speed.md) and [Extinction coefficient](/fundamentals/extinction.md).

Symbols follow the [notation table](/docs/concepts.md#notation). The Python
API (extinction sources, `SmokeSpeedModel`, conversion helpers) is in
[docs/smoke-speed-model.md](/docs/smoke-speed-model.md).

## Coded form

The model turns the extinction coefficient *K* [1/m] at the agent's position
into a speed factor *f* [-], selected by `SmokeSpeedConfig.speed_law`
(`pyfds_evac/core/smoke_speed.py`). A non-finite or negative *K* is read as 0.

- **`"lund"` (default)**, `speed_factor_from_extinction`:

  $$
  f(K) = \min\!\left(1,\ \max\!\left(f_{\min},\ 1 + \frac{\beta}{\alpha}K\right)\right).
  $$

- **`"fridolf"`**, `speed_factor_from_extinction_fridolf`: the law of
  Fridolf et al. (2018), method 3, with \(V = C/K\) [m] and the agent's
  smoke-free speed \(v_0\) [m/s],

  $$
  w = \min\!\left(v_0,\ \max\!\left(0.2,\ v_0 - 0.34\,(3 - V)\right)\right),
  \qquad f = \frac{w}{v_0}, \qquad f(0) = 1.
  $$

  The reduction is additive, 0.34 m/s per metre of visibility below 3 m, and
  the floor is an absolute 0.2 m/s, not a fraction of \(v_0\). Above 3 m the
  speed is unchanged. The paper gives no *C*; pyFDS-Evac uses *C* = 3, as FDS
  does. Until [#146](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/146)
  this option computed \(V/(V+2)\), a law with no known source.

## Parameters

Fields of `SmokeSpeedConfig`, with the defaults in the code. `run.py` and the
web GUI set only the last two (`--smoke-update-interval`,
`--smoke-slice-height`); the speed law and its coefficients need a
`SmokeSpeedConfig` built in Python (see the
[parameter split](/docs/concepts.md#the-parameter-split)).

| Field | Default | Unit | Meaning |
|---|---|---|---|
| `speed_law` | `"lund"` | - | `"lund"` or `"fridolf"` |
| `alpha` | `0.706` | m/s | \(\alpha\), `lund` only |
| `beta` | `-0.057` | m²/s | \(\beta\), `lund` only |
| `min_speed_factor` | `0.1` | - | \(f_{\min}\), `lund` only |
| `visibility_factor_c` | `3.0` | - | *C*, `fridolf` only |
| `fridolf_slope` | `0.34` | m/s per m | Speed drop per metre of visibility, `fridolf` only |
| `fridolf_visibility_threshold_m` | `3.0` | m | Visibility below which speed drops, `fridolf` only |
| `fridolf_min_speed_m_per_s` | `0.2` | m/s | Absolute speed floor, `fridolf` only |
| `update_interval_s` | `1.0` | s | Time between samples of *K* for each agent |
| `slice_height_m` | `1.6` | m | Height of the FDS slice that is read ([FDS+Evac](https://github.com/firemodels/fds/tree/c9da70d7a/Source) `HUMAN_SMOKE_HEIGHT`; the previous default was 2.0) |

The routing block has its own copy of `alpha`, `beta` and `min_speed_factor`,
used only to price routes; see the [routing model](/models/routing.md#parameters).

## Where it acts in the time step

Every `update_interval_s` (`--smoke-update-interval` in `run.py`),
`run_scenario` samples *K* at each agent's position and stores *f* as the
agent's smoke factor. The agent's desired speed is then
\(v_0 \cdot f \cdot g(\mathrm{FIC})\) (`direct_steering_runtime.py:186`–`190`),
where \(g\) is the irritant factor of the [FED model](/models/fed.md).

![Speed factor v/v0 against extinction coefficient K for the Frantzich–Nilsson law and for the fridolf option at v0 = 1.25 m/s with C = 3 and C = 8](/images/concepts/speed_laws.png)

*Speed factor \(v/v_0\) [-] against extinction coefficient K [1/m]. Solid dark
blue: Frantzich–Nilsson with the default constants, floor 0.1 reached at
K = 11.1 m⁻¹. The `fridolf` option (Fridolf et al. 2018) at
\(v_0\) = 1.25 m/s with \(V = C/K\): red dashed for C = 3, orange dash-dotted
for C = 8. The arrow marks the largest gap between Frantzich–Nilsson and C = 3.
Script: `scripts/figures/speed_laws.py`.*

Background: the [Concepts](/docs/concepts.md) page
and the talk [*A Modular Workflow for Visibility-Aware Evacuation Modelling*](https://pedestriandynamics.org/pyFDS-Evac/talks/visibility-seminar-2026/).

For real FDS output, `fdsreader` provides the local extinction field
via `SliceFieldSampler`. For verification cases such as ISO 20414:2020 Test 18 (Table 21),
the runner can also apply a constant extinction coefficient directly.

## FDS data access

All FDS slice data is read through a single library:

- **`fdsreader`** — reads raw FDS slice quantities with nearest-neighbor
  spatial and temporal lookup via `SliceFieldSampler`
  (`pyfds_evac/core/fds_sampling.py`)
- Used by both the smoke-speed model (extinction `K [1/m]`) and the FED
  model (CO, CO2, O2, and optional irritant gases)
- When a scenario needs both extinction and FED fields from the same FDS
  case, pass a shared `fdsreader.Simulation` instance to avoid parsing
  the directory twice (see [FDS sampling API](/docs/fds-sampling.md))

Runs of the ISO 20414 Test 18 (Table 21) corridor, with a constant extinction
coefficient and with FDS output, the plotting scripts and the verification
figures are on [Speed in practice](/docs/smoke-speed-model.md#runs-on-the-assets).

## Deviations from the literature

The published laws are on [Walking speed in smoke](/fundamentals/walking-speed.md).
The code departs from them as follows.

- **Fractional, not absolute.** The linear law is applied as a factor of each
  agent's own \(v_0\) (`smoke_speed.py:234`), the FDS+Evac normalisation of an
  absolute regression. It divides by the intercept \(\alpha\), an
  extrapolation to *K* = 0, not a measured free walking speed.
- **Floor.** \(f_{\min}\) is FDS+Evac's convention, not a measured minimum;
  Ronchi et al. (2013) put the minimum speed in both the Jin and the
  Frantzich–Nilsson data at about 0.3–0.4 m/s.
- **Range and spread.** The law is evaluated at every *K*, including below the
  tunnel data, and uses only the mean coefficients, not their standard
  deviations.
- **The `fridolf` option.** Fridolf et al. (2018) state visibility, not *K*,
  and give no *C*; the code uses *C* = 3 by default. Their 2019 fit used
  *A* = 2 for reflecting signs (see
  [Walking speed in smoke](/fundamentals/walking-speed.md)). \(v_0\) is each
  agent's own free speed, as in their method 3, not the truncated normal
  distribution (mean 1.35 m/s, SD 0.25 m/s, 0.85–1.85 m/s) that method 3
  draws it from.
- **Irritancy counted twice.** Frantzich and Nilsson's smoke contained acetic
  acid, so \(f(K)\) already includes irritant slowing, and multiplying by
  \(g(\mathrm{FIC})\) partly counts irritancy twice. SFPE Eq. 63.14 adds the
  two losses instead
  ([#153](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/153),
  [#147](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/147)).
- **Combination with irritants.** \(g(\mathrm{FIC})\) multiplies \(f\); see the
  [FED page](/models/fed.md#deviations-from-the-literature).
