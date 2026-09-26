---
title: "Smoke-speed model"
weight: 1
math: true
---

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

- **`"fridolf"`**, `speed_factor_from_extinction_fridolf`: with
  \(V = C/K\) [m],

  $$
  f(K) = \frac{V}{V + 2~\mathrm{m}}, \qquad f(0) = 1,
  $$

  with no floor. Its attribution to Fridolf et al. (2019) is unverified, and
  the paper's own law differs; see
  [Walking speed in smoke](/fundamentals/walking-speed.md) and
  [#146](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/146).

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
| `update_interval_s` | `1.0` | s | Time between samples of *K* for each agent |
| `slice_height_m` | `2.0` | m | Height of the FDS slice that is read |

The routing block has its own copy of `alpha`, `beta` and `min_speed_factor`,
used only to price routes; see the [routing model](/models/routing.md#parameters).

## Where it acts in the time step

Every `update_interval_s` (`--smoke-update-interval` in `run.py`),
`run_scenario` samples *K* at each agent's position and stores *f* as the
agent's smoke factor. The agent's desired speed is then
\(v_0 \cdot f \cdot g(\mathrm{FIC})\) (`direct_steering_runtime.py:186`–`190`),
where \(g\) is the irritant factor of the [FED model](/models/fed.md).

![Speed factor v/v0 against extinction coefficient K for the Frantzich–Nilsson law and for the fridolf option V/(V+2) with C = 3 and C = 8](/images/concepts/speed_laws.png)

*Speed factor \(v/v_0\) [-] against extinction coefficient K [1/m]. Solid blue:
Frantzich–Nilsson with the default constants, floor 0.1 reached at K = 11.1 m⁻¹.
Orange: the `fridolf` option, \(V/(V+2)\) with \(V = C/K\), for C = 3 (solid)
and C = 8 (dashed).
Script: `scripts/figures/speed_laws.py`.*

Background: the [Concepts](/docs/concepts.md) page
and the talk [*A Modular Workflow for Visibility-Aware Evacuation Modelling*](https://pedestriandynamics.org/pyFDS-Evac/talks/visibility-seminar-2026/)
([PDF](https://pedestriandynamics.org/pyFDS-Evac/talks/pyFDS-Evac_visibility_seminar_2026.pdf)).

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

Run the ISO 20414 Test 18 (Table 21) corridor with a constant extinction coefficient:

```bash
uv run run.py \
  --scenario assets/ISO-table21 \
  --constant-extinction 1.0 \
  --smoke-update-interval 0.1 \
  --output-smoke-history /tmp/iso-table21-smoke-history.csv \
  --cleanup
```

Run the smoke-speed model against FDS results read through `fdsreader`. The
repository ships the deck, not its output — the slices are 4.2 MB and the full
run 54 MB — so run FDS once first:

```bash
mkdir -p /tmp/iso21 && cd /tmp/iso21 \
  && fds /path/to/assets/ISO-table21/ISO-table21.fds && cd -   # ~8 min

uv run run.py \
  --scenario assets/ISO-table21 \
  --fds-dir /tmp/iso21 \
  --smoke-update-interval 0.1 \
  --output-smoke-history /tmp/iso-table21-fds-smoke-history.csv \
  --cleanup
```

Inspect the FDS quantities available through `fdsreader`:

```bash
uv run run.py --inspect-fds --fds-dir /tmp/iso21 --scenario assets/ISO-table21
```

For a case where the coupling is exercised without running FDS yourself, see
[`assets/iso_table22_coupled`](https://github.com/PedestrianDynamics/pyFDS-Evac/blob/main/assets/iso_table22_coupled/README.md): its output
is committed (136 kB) and a test reads it on every CI run.

Plot smoke-speed history for a single agent:

```bash
uv run python scripts/plot_smoke_history.py \
  --input /tmp/iso-table21-smoke-history.csv \
  --output /tmp/iso-table21-smoke-history.png \
  --agent-id 1
```

Plot aggregate smoke-speed history:

```bash
uv run python scripts/plot_smoke_history.py \
  --input /tmp/iso-table21-smoke-history.csv \
  --output /tmp/iso-table21-smoke-history-aggregate.png
```

Generate a stable ISO 20414 Test 18 (Table 21) sweep artifact under `artifacts/`:

```bash
uv run python scripts/generate_iso_table21_sweep.py
```

Figure: ![ISO 20414 Test 18 (Table 21) sweep](/artifacts/iso-table21-sweep.png)

Generate the FDS+Evac smoke-density vs speed verification plot:

```bash
uv run python scripts/generate_smoke_density_speed_plot.py
```

Figure: ![soot_density vs speed](/artifacts/smoke-density-vs-speed.png)

## Deviations from the literature

The published laws are on [Walking speed in smoke](/fundamentals/walking-speed.md).
The code departs from them as follows.

- **Fractional, not absolute.** The linear law is applied as a factor of each
  agent's own \(v_0\) (`smoke_speed.py:227`), the FDS+Evac normalisation of an
  absolute regression. It divides by the intercept \(\alpha\), an
  extrapolation to *K* = 0, not a measured free walking speed.
- **Floor.** \(f_{\min}\) is FDS+Evac's convention, not a measured minimum;
  Ronchi et al. (2013) put the minimum speed in both the Jin and the
  Frantzich–Nilsson data at about 0.3–0.4 m/s.
- **Range and spread.** The law is evaluated at every *K*, including below the
  tunnel data, and uses only the mean coefficients, not their standard
  deviations.
- **The `fridolf` option.** \(V/(V+2)\) (`smoke_speed.py:261`) is not the law
  of Fridolf et al. (2019), whose own law differs (see
  [Walking speed in smoke](/fundamentals/walking-speed.md)); the attribution
  is unverified ([#146](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/146)). Fridolf et al. fitted with *A* = 2 for reflecting
  signs, while the code uses *C* = 3 by default.
- **Irritancy counted twice.** Frantzich and Nilsson's smoke contained acetic
  acid, so \(f(K)\) already includes irritant slowing, and multiplying by
  \(g(\mathrm{FIC})\) partly counts irritancy twice. SFPE Eq. 63.14 adds the
  two losses instead
  ([#153](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/153),
  [#147](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/147)).
- **Combination with irritants.** \(g(\mathrm{FIC})\) multiplies \(f\); see the
  [FED page](/models/fed.md#deviations-from-the-literature).
