# 014 — Public API and run manifest

## Problem

The documentation (spec 013) needs a small, stable surface to describe.
Four gaps block it:

- `import pyfds_evac` exposes nothing. Users have to know the internal
  module that defines each class.
- A synthetic run with `ConstantExtinctionField` still has to pass a
  fake `fds_dir` to `SmokeSpeedConfig` and `DefaultFedConfig`.
- The `scenario.py` docstring shows an import path (`core.scenario`)
  that does not exist.
- A run leaves no record of the code, inputs and FDS build that produced
  it. An ensemble cannot be traced or reproduced afterwards.

## Changes

1. **Lazy re-exports.** `pyfds_evac/__init__.py` resolves its public names
   through a PEP 562 `__getattr__` and lists them in `__all__` and
   `__dir__`. The names are `load_scenario`, `run_scenario`,
   `build_run_kwargs`, `Scenario`, `ScenarioResult`, `ProgressEvent`,
   `SmokeSpeedModel`, `SmokeSpeedConfig`, `ExtinctionField`,
   `ConstantExtinctionField`, `DefaultFedModel`, `DefaultFedConfig`,
   `FdsFedField`, `DefaultHeatFedModel`, `FdsHeatField`,
   `TenabilityConfig`, `RerouteConfig`, `RouteCostConfig` and
   `VisibilityModel`. Eager imports are ruled out: `pyfds_evac.core`
   pulls in pandas and matplotlib and costs 1–2.5 s, while a bare
   `import pyfds_evac` stays under a millisecond. The first attribute
   access pays the full import.
2. **`fds_dir` defaults to `None`** in `SmokeSpeedConfig` and
   `DefaultFedConfig`. It is the first field and every other field has a
   default, so no field moves and positional calls keep working. No model
   reads `config.fds_dir`; the FDS path reaches the fields through
   `from_fds(...)`.
3. **Docstring** in `scenario.py` imports from `pyfds_evac.core.scenario`.
4. **Run manifest** (`pyfds_evac/core/manifest.py`). `run_scenario` writes
   `<trajectory stem>.manifest.json` next to the trajectory SQLite file
   and exposes its path as `ScenarioResult.manifest_file`, next to
   `sqlite_file`. `ScenarioResult.cleanup()` deletes both. The manifest
   records:
   - `versions`: pyfds-evac, jupedsim, fdsreader and fdsvismap from
     `importlib.metadata` (`null` if not installed);
   - `uv_lock_sha256`: the sha256 of the `uv.lock` in the pyfds-evac
     checkout, found by walking up from the package source directory to
     a `pyproject.toml` with `name = "pyfds-evac"`. Another project's
     lock is never hashed; an installed wheel records `null`;
   - `git_commit` and `git_dirty`: `git rev-parse HEAD` and whether
     `git status --porcelain --untracked-files=no` is non-empty in that
     checkout, with a 2 s timeout (`null` without git or a checkout);
   - `seed` and `scenario_path`;
   - `fds_dir`: the first FDS directory the smoke, FED or heat model
     reads. `ExtinctionField.from_fds`, `FdsFedField.from_fds` and
     `FdsHeatField.from_fds` store it as `field.fds_dir`, which wins over
     `config.fds_dir`; a `ConstantExtinctionField` model is skipped.
     `fds_version` is the line after `FDSVERSION` in that directory's
     `.smv` (`null` without a case);
   - `created_utc`: an ISO 8601 UTC timestamp.

   Writing the manifest never fails a finished run: an `OSError` or
   `ValueError` is logged as a warning and `manifest_file` is `None`.
   `run.py --output-sqlite` copies the manifest to
   `<output stem>.manifest.json` beside the copied trajectory, before
   `--cleanup` deletes the temporary one.

   The name carries the trajectory stem because the default trajectory
   is a temporary file in a shared directory. A fixed `manifest.json`
   there would be overwritten by concurrent runs.

## Tests

- `tests/test_public_api.py`: every exported name resolves to its
  defining module; an unknown name raises `AttributeError`; `dir()` lists
  the exports; a bare import in a fresh interpreter loads neither pandas,
  matplotlib nor `pyfds_evac.core`; both configs default `fds_dir` to
  `None`; `SmokeSpeedModel(ConstantExtinctionField(k), SmokeSpeedConfig())`
  samples.
- `tests/test_manifest.py`: `FDSVERSION` parsing on a fake `.smv`, and
  the missing-block, missing-directory and missing-`.smv` cases;
  `fds_dir` selection across models; `uv.lock` lookup walking upwards;
  `fds_dir` taken from `from_fds` on the tracked `iso_table21_coupled`
  case, preferred over the config; `uv.lock` accepted only beside a
  pyfds-evac `pyproject.toml`; git fields outside a repository; all
  manifest fields; a 2 s `run_scenario` on `assets/ISO-table21` with a
  constant field, which writes the manifest and removes it on cleanup; a
  failing `write_manifest` (`OSError`, `ValueError`) that still returns
  the run; `run.py` copying the manifest beside `--output-sqlite` under
  `--cleanup`.

## Non-goals

- Changing `pyfds_evac.core`, which stays eager, or its `__all__`.
- Exporting `load_slice_sampler`. It returns a `SliceFieldSampler`, which
  fills no `run_scenario` keyword.
- Recording the full scenario JSON, the CLI options or the host in the
  manifest.
- Making aggregate results bit-reproducible. The manifest records inputs;
  it does not guarantee identical trajectories.
