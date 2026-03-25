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

## Dependencies

- jupedsim
- pedpy
- fdsvismap
- plotly
- nbformat
