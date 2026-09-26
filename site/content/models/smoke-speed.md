---
title: "Smoke-speed model"
weight: 1
math: true
---

See [docs/smoke-speed-model.md](/docs/smoke-speed-model.md) for the full
model description, configuration, and API reference.

The smoke-speed model uses extinction coefficient `K [1/m]` as the primary
input. Two speed laws are available, selected via `SmokeSpeedConfig.speed_law`:

| `speed_law` | Model | Reference |
|-------------|-------|-----------|
| `"lund"` (default) | Linear: `speed_factor = 1 + β·K/α`, clamped to `[min_speed_factor, 1]` | Frantzich & Nilsson / FDS+Evac |
| `"fridolf"` | Non-linear: `speed_factor = V / (V + 2)` where `V = C / K` (Jin) | Fridolf et al. (2019) |

The Fridolf law is empirically validated against individual walking-speed
measurements in smoke-filled tunnels and naturally asymptotes to zero without
a hard clamp. Select it with `SmokeSpeedConfig(speed_law="fridolf")`;
`visibility_factor_c` controls the Jin constant (default `3` for reflective
signs, `8` for light-emitting signs).

![Speed factor v/v0 against extinction coefficient K for the Frantzich–Nilsson law and for Fridolf's law with C = 3 and C = 8](/images/concepts/speed_laws.png)

*Speed factor \(v/v_0\) [-] against extinction coefficient K [1/m]. Solid blue:
Frantzich–Nilsson with the default constants, floor 0.1 reached at K = 11.1 m⁻¹.
Orange: Fridolf et al. (2019) with C = 3 (solid) and C = 8 (dashed).
Script: `scripts/figures/speed_laws.py`.*

Background: the ideas behind this model are explained on the [Concepts](/docs/concepts.md) page
and in the talk [*A Modular Workflow for Visibility-Aware Evacuation Modelling*](https://pedestriandynamics.org/pyFDS-Evac/talks/visibility-seminar-2026/)
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
