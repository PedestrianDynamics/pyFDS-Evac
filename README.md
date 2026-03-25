[![fds-evac](https://github.com/PedestrianDynamics/fds-evac/actions/workflows/code-quality.yml/badge.svg)](https://github.com/PedestrianDynamics/fds-evac/actions/workflows/code-quality.yml)


# pyFDS-Evac

Fire Dynamics Simulator (FDS) evacuation modeling with visibility analysis.

## Installation

This project uses [uv](https://github.com/astral-sh/uv) for dependency management.

```bash
uv sync
```

## Development

Activate the virtual environment:

```bash
uv shell
```

Run the main script:

```bash
python main.py
```

Run a JSON-first scenario with the CLI runner:

```bash
uv run run.py --scenario assets/ISO-table21 --cleanup
```

## Smoke-Speed Model

The smoke-speed model uses extinction coefficient `K [1/m]` as the primary
input. For real FDS output, `fdsvismap` provides the local extinction field.
For verification cases such as ISO 20414 Table 21, the runner can also apply a
constant extinction coefficient directly.

### FDS Data Access Layers

The project uses two different FDS readers on purpose:

- `fdsvismap`
  - used for extinction / visibility-centric workflows
  - current use: smoke-speed (`K [1/m]`) and visibility-related logic
- `fdsreader`
  - used for generic raw FDS quantities
  - current use: Table 22 / FED inputs such as `CO`, `CO2`, and `O2`

Rule of thumb:

- use `fdsvismap` for smoke/visibility
- use `fdsreader` for gases and other hazard quantities

Run the ISO Table 21 corridor with a constant extinction coefficient:

```bash
uv run run.py \
  --scenario assets/ISO-table21 \
  --constant-extinction 1.0 \
  --smoke-update-interval 0.1 \
  --output-smoke-history /tmp/iso-table21-smoke-history.csv \
  --cleanup
```

Run the smoke-speed model against FDS results read through `fdsvismap`:

```bash
uv run run.py \
  --scenario assets/ISO-table21 \
  --fds-dir fds_data \
  --smoke-update-interval 0.1 \
  --output-smoke-history /tmp/iso-table21-fds-smoke-history.csv \
  --cleanup
```

Inspect the FDS quantities available through `fdsreader`:

```bash
uv run run.py --inspect-fds --fds-dir fds_data --scenario assets/ISO-table21
```

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

Generate a stable ISO Table 21 sweep artifact under `artifacts/`:

```bash
uv run python scripts/generate_iso_table21_sweep.py
```

Figure: ![ISO Table 21 sweep](artifacts/iso-table21-sweep.png)

Generate the FDS+Evac smoke-density vs speed verification plot:

```bash
uv run python scripts/generate_smoke_density_speed_plot.py
```

## Table 22 / FED

The current Table 22 implementation is a **partial implementation** of
Section `3.4 Fire and Human Interaction` from the FDS+Evac guide and the
corresponding FDS+Evac code path.

What is implemented now:

- `CO`
- `CO2` hyperventilation factor
- `O2` hypoxia

This default pathway is read from FDS slice outputs through `fdsreader`.

Verification status on this branch:

- equation-level constant-exposure checks for `CO`, `CO2`, and `O2` are covered in [tests/test_fed.py](tests/test_fed.py)
- an ISO Table 22 style stationary benchmark is covered with `assets/ISO-table22`, using one fixed occupant in a room and comparing the runtime `FED=1` crossing time against the analytical reference for the implemented default pathway
- this verification currently covers only the implemented default FED pathway (`CO`, `CO2`, `O2`), not the broader set of toxic/thermal terms mentioned in ISO Table 22

A plot is not required for the Table 22 pass/fail check. The verification criterion is agreement in time to reach `FED = 1`. We still generate a stable artifact because it improves inspection and reporting.

Generate the ISO Table 22 stationary FED verification figure:

```bash
uv run python scripts/generate_iso_table22_stationary_plot.py
```

Figure: ![ISO Table 22 stationary FED verification](artifacts/iso-table22-stationary-fed.png)

What is **not** implemented yet from the full Section 3.4 formulation:

- `HCN`
- `NOx`
- irritants / `FLD_irr`
- other Purser terms such as `HCl`, `HBr`, `HF`, `SO2`, `NO2`, `C3H4O`, `CH2O`
- incapacitation effects on agent motion
- broader fire-human interaction effects such as routing by FED risk, temperature, or radiation

The implemented default FED equation is:

$$
\mathrm{FED}_{\mathrm{total}} = \mathrm{FED}_{\mathrm{CO}} \cdot \mathrm{HV}_{\mathrm{CO_2}} + \mathrm{FED}_{\mathrm{O_2}}
$$

with:

$$
\mathrm{FED}_{\mathrm{CO}} = \int 2.764 \times 10^{-5} \, C_{\mathrm{CO}}(t)^{1.036} \, dt
$$

$$
\mathrm{HV}_{\mathrm{CO_2}} = \frac{\exp(0.1903 \, C_{\mathrm{CO_2}}(t) + 2.0004)}{7.1}
$$

$$
\mathrm{FED}_{\mathrm{O_2}} = \int \frac{dt}{60 \, \exp\left(8.13 - 0.54 \, (20.9 - C_{\mathrm{O_2}}(t))\right)}
$$

Units used by the implementation:

- $C_{\mathrm{CO}}$: ppm
- $C_{\mathrm{CO_2}}$: volume %
- $C_{\mathrm{O_2}}$: volume %
- $t$: minutes

FDS slice outputs are read as volume fractions and converted to volume percent before applying the equations.

Inspect which local FDS cases support the default FED path:

```bash
uv run python - <<'PY'
from src.core import inspect_fds_quantities, list_simulations
for path in list_simulations("fds_data"):
    inv = inspect_fds_quantities(path)
    print(path, inv.canonical_slice_names(), inv.supports_default_fed())
PY
```

In the bundled sample data:

- `fds_data/basic` supports smoke-speed inputs, but not default FED
- `fds_data/haspel` supports default FED (`CO`, `CO2`, `O2`)

Run a scenario with FED accumulation enabled from FDS data and export the FED history:

```bash
uv run run.py \
  --scenario assets/ISO-table21 \
  --fds-dir fds_data/haspel \
  --smoke-slice-height 2.1 \
  --smoke-update-interval 1.0 \
  --output-fed-history /tmp/iso-fed-history.csv \
  --cleanup
```

The FED history CSV contains:

- `time_s`
- `agent_id`
- `x`, `y`
- `co_percent`
- `co2_percent`
- `o2_percent`
- `fed_rate_per_min`
- `fed_cumulative`

Note:

- If the scenario lies outside the FDS domain, the current implementation falls back to ambient conditions instead of failing.
- `HCN`, `NOx`, irritants, and other Purser terms are not yet included in this first Table 22 slice.

## Dependencies

- jupedsim
- pedpy
- fdsvismap
- plotly
- nbformat
