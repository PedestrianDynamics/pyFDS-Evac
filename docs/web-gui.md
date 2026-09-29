---
title: "Web GUI"
weight: 9
---

An optional local web app that runs the same model as `run.py` behind a form:
pick a scenario, set the options, run it, watch the progress, and look at the
results. It is for exploring a scenario; for studies, scripts and `run.py`
are easier to reproduce.

## Install and launch

```bash
uv sync --extra gui
uv run app.py
```

Then open <http://localhost:5001>. The extra installs
[FastHTML](https://fastht.ml/) and its dependencies.

## The form

The form is built from the `run.py` parser, so every option has a field.
Choice fields with no parser default show "default": for `heat_clothing` that
means clothed, ISO 13571 Eq. (9), and a blank `heat_fed_threshold` follows
`fed_threshold`
([#311](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/311)). The fields are grouped:

| Group | Fields |
|---|---|
| Core | scenario (pick or upload), seed |
| Smoke | `fds_dir` (with a folder browser), `constant_extinction`, `smoke_update_interval`, `smoke_slice_height` |
| FED & Tenability | `disable_tenability`, `incapacitation_mode`, `susceptibility_sigma`, `enable_fic_speed`, `fic_alpha`, `fic_min_factor`, `fed_threshold`, `o2_threshold_percent`, `enable_heat_fed`, `heat_incapacitation_mode`, `heat_susceptibility_sigma`, `heat_clothing`, `heat_fed_threshold` |
| Rerouting | `enable_rerouting`, `reroute_interval` |
| Visibility | `vis_cache` |
| Output files | an output folder; the SQLite, the four CSVs and the scenario bundle (`<folder>/bundle`) are written there |
| Other (collapsed) | every remaining option: `clear_air_visibility`, `no_visibility`, `vis_cell_size`, `max_sign_distance`, and the heat options `heat_endpoint`, `heat_fed_method`, `heat_emissivity`, `heat_convective_coefficient`, `heat_skin_temperature`, `heat_radiant_source`, `heat_u_factor`, `heat_regime`, `heat_layer_height`, `heat_view_factor`, `heat_layer_emissivity` |

Four `run.py` options have no field: `--print-summary`, `--export-only`,
`--inspect-fds` and `--cleanup`. Options with a fixed set of values are
dropdowns. The option meanings and defaults are on [Usage](usage.md).

The flags under "Other" are not yet next to the group they belong to
([#311](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/311),
[#270](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/270)).

## Runs

The GUI calls the same `run_scenario()` as the command line, through the same
option builder (`build_run_kwargs` in `pyfds_evac/core/run_config.py`), so a
run configured in the browser is identical to the equivalent `run.py`
command. Invalid combinations (for example `--vis-cache` with rerouting off)
are rejected when the form is submitted, with the same message as `run.py`.

One run is active at a time. It runs on a background thread and streams its
progress to the page. Cancelling stops the run at its next step.

## Results

- **Charts**: smoke over time and the growth of the cognitive maps. FED is
  shown live during a run.
- **Trajectory replay**: agents move between the stored trajectory samples,
  coloured by cumulative gas FED or by assigned exit, with play, pause, a
  scrub bar and ¼×–4× speed. When the run has an `fds_dir`, the FDS
  extinction slice is drawn under the agents as a smoke layer that can be
  switched off. The replay colours by gas FED only, not by heat FED
  ([#232](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/232)).

The files the run writes are described on [Outputs](outputs.md).
