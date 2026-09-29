---
title: "Web GUI"
weight: 9
---

An optional local web app that runs the same model as `run.py` behind a form:
pick a scenario, set the options, run it, watch the progress, and look at the
results. It is for exploring a scenario; for studies, scripts and `run.py`
are easier to reproduce. To turn a GUI run into a script, see
[Show the run as Python](#show-the-run-as-python).

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
| Core | scenario (pick or upload), seed; a blank seed uses the scenario's `baseSeed`, as `run.py` does, and 42 if the scenario sets none ([Usage](usage.md)) |
| Smoke | `fds_dir` (with a folder browser), `constant_extinction`, `smoke_update_interval`, `smoke_slice_height` |
| FED & Tenability | `disable_tenability`, `incapacitation_mode`, `susceptibility_sigma`, `enable_fic_speed`, `fic_alpha`, `fic_min_factor`, `fed_threshold`, `o2_threshold_percent`, `enable_heat_fed`, `heat_incapacitation_mode`, `heat_susceptibility_sigma`, `heat_clothing`, `heat_fed_threshold` |
| Rerouting | `enable_rerouting`, `reroute_interval` |
| Visibility | `vis_cache`; blank means no cache |
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
run configured in the browser gets the same options as the equivalent
`run.py` command. The results can still differ: a second run in the same GUI
session can differ from a fresh `run.py` run with the same seed
([#198](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/198)). Invalid combinations (for example `--vis-cache` with rerouting off)
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

## Show the run as Python

The GUI can write any configuration as a standalone Python script. Use it to
rerun a GUI run on another machine or to start a batch study from it, with
the settings and the seed traceable to the run. The script reproduces a
configuration; it does not validate the model. The GUI never executes it.

Two buttons open the code:

- **Show equivalent Python**, in the Parameters header: a preview of the
  current form settings. It is not a run.
- **Show Python for this run**, in the results bar and in the message of a
  failed or cancelled run: the code of the most recent run, built from the
  settings frozen when it was submitted.

Both open a dialog with **Copy** and **Download .py**.

![Dialog titled "Code for run #1 · blind_spawn_discovery" with its start time and a RUN #1 badge. Below it the line "Status: finished (30/30 evacuated)", five notices on packages, files not included, paths, outputs and reproducibility, a collapsed "Details" line, and the start of the script: comment lines with the pyfds-evac version, git commit, run number, start time and scenario, followed by the imports](/images/web-gui/run_code_dialog.png)

### Save a run and run it again

1. Run the `blind_spawn_discovery` scenario with the default settings.
2. When the run has finished, click **Show Python for this run**. The dialog
   is titled "Code for run #1 · blind_spawn_discovery · *start time*" and
   reports "Status: finished (30/30 evacuated)".
3. Click **Download .py**. The file is named
   `pyfds_evac_blind_spawn_discovery_run1.py`.
4. Run it with the pyfds-evac version named in its header, installed the same
   way as the GUI, for example the repository's `uv` environment. The `gui`
   extra is not needed. From the folder that holds the script:

   ```bash
   uv run --project /path/to/pyFDS-Evac python pyfds_evac_blind_spawn_discovery_run1.py
   ```

{{< checkpoint title="Script run completed" >}}
After the model's own progress and log lines, the script ends with
(pyfds-evac 0.1.0 at commit `cb236e1`; path shortened):

```text
Simulation finished in 55.14 s (30/30 evacuated).
Trajectory SQLite: /…/pyfds_evac_blind_spawn_discovery_run1_output/trajectory.sqlite
```

The folder `pyfds_evac_blind_spawn_discovery_run1_output`, created in the
folder you ran the script from, holds `trajectory.sqlite` and
`trajectory.manifest.json`.
{{< /checkpoint >}}

On another machine, copy the scenario folder and the FDS results as well: the
script contains code only. Then edit the `PATHS` block at the top of the
script. A scenario uploaded into the GUI lives in the GUI's own uploads folder
and will not exist elsewhere.

### What to keep in mind

- **The snapshot stores settings, not inputs.** It keeps the option values and
  the scenario path, not the scenario JSON, the FDS results or the visibility
  cache. The script reloads them from disk, so after an edit to the scenario
  or the FDS folder the code for run #N no longer reproduces run #N.
- **Results can differ from the GUI run, even with the same seed.** Repeated
  runs in one GUI process are affected
  ([#198](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/198)), and
  other versions or platforms can also change results. For an exact
  comparison, compare the first run of a fresh process on each side.
- **Outputs.** The script writes to a new `OUTPUT_DIR` and does not overwrite
  the GUI run's files. It does read the same `VIS_CACHE` file, and the cache
  key includes the resolved FDS directory (`_make_meta` in
  `pyfds_evac/core/visibility.py`), so a changed `FDS_DIR` or setting makes
  the script rebuild the map and rewrite that file.
- **Fewer output files.** The script writes the trajectory SQLite and its
  manifest, not the GUI's CSV histories or app bundle
  ([#328](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/328)).

### Preview and run code

**Preview.** The form is resolved exactly as a submitted run would be. If the
settings are invalid, the dialog shows the same error message as `run.py`,
with a **Details** disclosure, and no code; **Copy** and **Download .py** are
disabled. The file is named `pyfds_evac_<scenario>_preview.py`.

**Run code.** It is built only from the run's frozen snapshot, never from the
live form. The status line uses the `run.py` wording: finished (*n*/*N*
evacuated), stopped after *t* s (*k* remaining), failed, cancelled, or not
recorded. The file is named `pyfds_evac_<scenario>_run<N>.py`.

- **Failed and cancelled runs** still have code. The dialog is titled
  "Configuration of the failed run #N" or "Configuration of the cancelled
  run #N". A cancelled run keeps its code until **Clear results**.
- **Only the most recent run has code.** There is none while a run is in
  progress. After **Clear results** or a new run, the old run's code is gone
  and the dialog shows "No recorded run". Run numbers are not unique across
  GUI sessions
  ([#319](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/319)).
- **Changed form.** If the current form no longer resolves to the run's
  options, a note says that the code reproduces the run, not the form, and
  suggests Preview. Output paths are left out of this comparison.

{{< details title="What the script contains" closed="true" >}}
The script has six parts, in this order. The excerpt is the run from
[Save a run and run it again](#save-a-run-and-run-it-again), trimmed where
marked.

1. **Header.** The pyfds-evac version and git commit, with
   "(with uncommitted changes)" when the checkout was dirty; the commit alone
   then does not identify the code. Then "Run #N, started *UTC time*" or
   "Preview", the scenario name, and the notices shown in the dialog.
2. **`PATHS`.** `SCENARIO`, `FDS_DIR` and `VIS_CACHE` are absolute paths on
   the machine that ran the GUI. `OUTPUT_DIR` is a new relative folder,
   `pyfds_evac_<scenario>_run<N>_output` or
   `pyfds_evac_<scenario>_preview_output`, resolved against the folder the
   script is launched from.
3. **`OPTIONS`.** Every resolved option, one per line, exactly as the GUI
   hands it to `build_run_kwargs`.
4. **The run.** A `Namespace` is rebuilt from `OPTIONS` and `PATHS`; the
   script then calls `load_scenario`, `build_run_kwargs`
   (`pyfds_evac/core/run_config.py`) and `run_scenario`. There is no second
   option mapping, so the script cannot drift from the GUI.
5. **After the run.** A finished or stopped message. The trajectory SQLite is
   copied to `OUTPUT_DIR/trajectory.sqlite` with its manifest, and
   `result.cleanup()` removes the temporary copies `run_scenario` wrote.
6. **CLI-only keys.** `cleanup`, `export_only`, `inspect_fds` and
   `print_summary` appear in `OPTIONS`, but `build_run_kwargs` ignores them.
   `'cleanup': False` next to `result.cleanup()` is expected, not a bug.

```python
# Generated by the pyFDS-Evac GUI.
# pyfds-evac 0.1.0, commit cb236e14dc607960fe646b091fe30c17f3737660.
# Run #1, started 2026-09-29T16:03:41+00:00.
# Scenario: blind_spawn_discovery
# ... notices ...

import argparse
import pathlib
import shutil

from pyfds_evac.core import load_scenario, run_scenario
from pyfds_evac.core.manifest import manifest_path_for
from pyfds_evac.core.run_config import build_run_kwargs

# PATHS: from the computer that ran the GUI. Edit them on another machine.
SCENARIO = '/.../pyFDS-Evac/assets/blind_spawn_discovery'  # path shortened
FDS_DIR = None
VIS_CACHE = None
# A new folder: the script never overwrites the GUI run's files.
OUTPUT_DIR = pathlib.Path('pyfds_evac_blind_spawn_discovery_run1_output')

# Settings: the resolved configuration the GUI passes to build_run_kwargs.
OPTIONS = {
    'seed': 1301,  # seed used by run #1
    'cleanup': False,
    'clear_air_visibility': False,
    'collect_route_cost_history': True,
    # ... remaining options, sorted by name ...
    'output_sqlite': None,
    'print_summary': False,
    # ...
}

opts = argparse.Namespace(
    **OPTIONS,
    scenario=SCENARIO,
    fds_dir=FDS_DIR,
    vis_cache=VIS_CACHE,
)

scenario = load_scenario(SCENARIO)
run_kwargs = build_run_kwargs(scenario, opts, log=print)
result = run_scenario(scenario, **run_kwargs)

# ... finished / stopped message, then copy the trajectory SQLite
# and its manifest to OUTPUT_DIR ...
result.cleanup()  # remove the temporary copies run_scenario wrote
```
{{< /details >}}

{{< details title="How the seed is written" closed="true" >}}
The `seed` line in `OPTIONS` carries a comment that says where its value
comes from. `None` means the scenario's `baseSeed`, which is 42 when the
scenario sets none ([Usage](usage.md)).

| Case | Value | Comment |
|---|---|---|
| Run code; the run reported the seed expected at submission | that seed | `# seed used by run #N` |
| Run code; seed box left blank and no seed confirmed (for example a failed or cancelled run) | `None` | `# seed not recorded for this run; None = the scenario's baseSeed` |
| Run code; seed typed in but not confirmed (for example a failed or cancelled run) | the submitted value | `# seed submitted; the seed used was not recorded` |
| Preview; seed box blank | `None` | `# None = the scenario's baseSeed (<value>)`, for example `(1301)` for `blind_spawn_discovery` |
{{< /details >}}

{{< details title="What the script leaves out, and why" closed="true" >}}
- **The GUI's CSV histories and app bundle.** The smoke, FED, route and
  route-cost histories and the bundle are written by `apply_outputs`, which
  lives in `run.py`, outside the installed package. Their keys
  (`output_smoke_history`, `output_fed_history`, `output_route_history`,
  `output_route_cost_history`, `output_sqlite`, `export_app_bundle`) are set
  to `None`
  ([#328](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/328)).
  Route-cost history collection stays on (`collect_route_cost_history`), as
  in the GUI.
- **The GUI's progress callback.** It only drives the GUI's live view. The
  model's own progress lines are still printed.
{{< /details >}}

{{< details title="Evidence: the equivalence test" closed="true" >}}
`test_exported_script_reproduces_the_gui_run` in
`tests/test_webapp.py` runs a GUI run and its exported script in two fresh
interpreters, so each is the first run of its process. For one scenario,
`blind_spawn_discovery` (`baseSeed` 1301), the two match on total, evacuated
and remaining agents, evacuation time and seed. It covers that scenario only.
{{< /details >}}
