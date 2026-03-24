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

## Dependencies

- jupedsim
- pedpy
- fdsvismap
- plotly
- nbformat

