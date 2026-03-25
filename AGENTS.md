# fds-evac Development Guidelines

Auto-generated from all feature plans. Last updated: 2026-03-23

## Active Technologies

- Python 3.11+ + `jupedsim` (simulation engine), `fdsvismap` (FDS data loading), `numpy` (numerical operations), `scipy` (interpolation) (001-smoke-speed-model)
- `pyfdsevac/` package for smoke-speed model implementation

## Project Structure

```text
pyfdsevac/          # NEW: Main package (smoke-speed model)
├── __init__.py
├── data_models.py
├── io/
├── fields/
├── behavior/
├── runtime/
├── interfaces/
└── cli/

src/                # EXISTING: Keep for backward compatibility
tests/
```

## Commands

uv run pytest
uv run ruff check .

## Code Style

Python 3.11+: Follow standard conventions with pyfdsevac/ package-first architecture

## Recent Changes

- 001-smoke-speed-model: Added Python 3.11+ + `jupedsim` (simulation engine), `fdsvismap` (FDS data loading), `numpy` (numerical operations), `scipy` (interpolation), `pyfdsevac/` package structure

<!-- MANUAL ADDITIONS START -->
<!-- MANUAL ADDITIONS END -->
