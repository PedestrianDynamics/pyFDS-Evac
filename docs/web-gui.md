---
title: "Web GUI"
weight: 9
---

An optional local web app that runs the same model as the `pyfds-evac`
command (`run.py`) behind a form: pick a scenario, set the options, run it,
watch the progress, and look at the results. It is for exploring a scenario;
for studies, scripts and the command line are easier to reproduce. To turn
a GUI run into a script, see [Show the run as Python](#show-the-run-as-python).
For a terminal or an SSH session, see [Terminal UI](terminal-ui.md).

## Install and launch

Install the `gui` extra and start the GUI from the folder that contains
`assets/` (see [Where the GUI reads and writes](#where-the-gui-reads-and-writes)):

```bash
pip install "pyfds-evac[gui]"
pyfds-evac-gui
```

Then open <http://127.0.0.1:5001>. The extra installs
[FastHTML](https://fastht.ml/) and its dependencies. On a screen narrower
than 900 px, such as a phone, the form sits above the results instead of
beside them.

`pyfds-evac-gui` listens on 127.0.0.1, so only this computer can open it.
`--host 0.0.0.0` makes it reachable from other computers on the network, with
a warning that says so, and `--port` sets the port (default: the `PORT`
environment variable, else 5001).
Without the extra, the command stops with:

```text
pyfds-evac-gui needs the GUI extra, which is not installed (missing module 'fasthtml'). Install it with: pip install 'pyfds-evac[gui]'
```

In a [source checkout](install.md#install-from-the-repository), install the
extra with uv and start the GUI with `app.py`:

```bash
uv sync --extra gui
uv run app.py
```

`uv run app.py` listens on 127.0.0.1, port 5001, and reloads when the code
changes; it takes `--host` and `--port` like `pyfds-evac-gui`.
`uv run pyfds-evac-gui` also works in a checkout: it does not reload.

### Where the GUI reads and writes

| Folder | Installed with pip | Source checkout |
|---|---|---|
| Scenarios in the picker | `./assets` | `<checkout>/assets` |
| Uploaded scenarios | `./uploads` | `<checkout>/uploads` |
| Results | `./results` | `<checkout>/results` |

`./` is the folder in which `pyfds-evac-gui` starts. In a checkout, the
folders sit in the checkout whatever folder the server starts in. The
environment variable `PYFDS_EVAC_RESULTS_DIR` overrides the results folder in
both cases. Nothing is written into the installed package.

The package ships no scenarios, so after a pip install the picker is empty
until there is an `assets/` folder. Unpack the example zip of a page, for
example the [Quickstart](quickstart.md), and start the GUI inside the
unpacked folder:

```bash
cd pyfds-evac-quickstart
pyfds-evac-gui
```

The picker then lists `ISO-table21`. You can also upload a scenario (its
config JSON and geometry WKT, or a `.zip`) in the **Core** group; it is saved
under `./uploads`. To make one, see
[Create a scenario](howto-create-scenario.md). The fire examples ship the FDS deck only; run FDS yourself
before the GUI has smoke to read.

## Run a scenario

The steps use `iso_table21_coupled`, a scenario tracked in the repository
together with its FDS output, so they need a
[source checkout](install.md#install-from-the-repository). One agent walks a
100 m corridor filled with smoke of about K = 1 1/m. The numbered markers in
the first screenshot show where each control is. Click a screenshot to open
it at full size.

[![The start screen. On the left, the Parameters panel with the Show equivalent Python button in its header, the open Core group with the scenario picker set to iso_table21_coupled, the Smoke group with fields labelled with units such as "Constant extinction (1/m)" and "Smoke update interval (s)", and the Run scenario and Results only buttons at the bottom. On the right, the left part of the empty results area. Numbered markers: 1 at the scenario picker, 2 at the Smoke group, 3 at Run scenario, 4 at the results area](/images/web-gui/overview.png "The start screen: 1 scenario picker, 2 parameter groups, 3 Run scenario, 4 results area.")](images/web-gui/overview.png)

{{% steps %}}

### Pick a scenario

In **Core**, choose `iso_table21_coupled` in the scenario picker (1). Leave
the seed blank to use the scenario's own `baseSeed`. To use your own
scenario, drop its config JSON and geometry WKT, or a `.zip` bundle, on the
upload box and click **Add to list**. To make one, see
[Create a scenario](howto-create-scenario.md).

### Set the options

Open **Smoke** (2) and enter `assets/iso_table21_coupled/fds` in **FDS dir**,
or pick the folder with **Browse…**. Leave the other fields at their
defaults. Every `run.py` option has a field, and labels show the unit where
the value has one, for example **Smoke slice height (m)**. Press **?** next
to a field to read its help text. The groups and their fields are listed
under [The form](#the-form).

[![The Parameters panel with Core collapsed. The Smoke group is open with FDS dir set to assets/iso_table21_coupled/fds, an empty "Constant extinction (1/m)" field, "Smoke update interval (s)" set to 1.0 and "Smoke slice height (m)" set to 1.6. Below it the FED & Tenability group is open with the Disable tenability switch off](/images/web-gui/configure.png "The Smoke group with the FDS folder filled in, and the start of the FED & Tenability group.")](images/web-gui/configure.png)

### Run it

Click **Run scenario** (3). The results area (4) turns into a progress card
and a console with the model's log. The card names the scenario and the run
number and shows agents evacuated, simulated time, wall-clock time and
percent done. **Cancel run** stops the run at its next step.

If a value is invalid, the run does not start. An alert above the results
area says "The run was not started." with the error, and your settings and
any results already shown are kept. The field is named in the message when
the error comes from that field's value, for example `Seed: …`; otherwise
the message is shown as it is, with the exception type under
**Technical details**.

[![A progress card titled "Running: Haspel" with the subtitle "run #2 · coupled FDS × JuPedSim step loop", at 25 percent, with a progress bar, the line "evacuated 75/300 · sim 105.3s · wall 44s · 25%" and a Cancel run button. Below it, the console lists the model's setup and rerouting log lines](/images/web-gui/running.png "A run in progress. The corridor case finishes in about a second, so this shows the larger Haspel scenario of the repository.")](images/web-gui/running.png)

### Look at the results

When the run ends, the results replace the progress card. A header names
the run (**Results**, the run number, scenario and start time) and holds
**Show Python for this run** and **Clear results**. Below it, the outcome
is stated in words, "Complete: all agents evacuated" here, followed by
tiles for the evacuation time, agents evacuated, agents remaining and the
seed used, and any warnings from the run.

[![The top of the results. A header reads "Results  run #1 · iso_table21_coupled · 2026-09-29T18:14:06+00:00" with the buttons Show Python for this run and Clear results, and the line "Starting a new run replaces these results in this view; the files on disk are kept." Below it, a check mark and "Complete: all agents evacuated", four tiles reading Evacuation time 85.0 s, Evacuated 1 / 1 agents, Remaining 0 agents and Seed used 420, and a Warning box, "1 warning for run #1", saying that FED is disabled for assets/iso_table21_coupled/fds because it has no CO, CO2 or O2 slices](/images/web-gui/results_header.png "The results header, the outcome and the FED warning of the corridor run.")](images/web-gui/results_header.png)

The screenshots of this run predate the exit rule of
[#349](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/349); the run
now ends after 85.3 s, as in the steps below
([#389](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/389)).

Further down, press play in
**Trajectories** to replay the run, or drag the time slider. Scroll over the
plan to zoom and drag to pan; **↺** resets the view. With an FDS folder set,
the extinction slice is drawn under the agents as a grey smoke layer;
**Smoke** switches it off.

[![The Trajectories panel at t = 41 s, zoomed in on the corridor. The corridor is drawn in grey, the FDS smoke layer, with one yellow agent in it. Below the plan: a play button, the time slider, a reset-view button, speed buttons 1×, 2×, 5×, 10× and 50×, a custom speed field, and the smoke toggle set to on](/images/web-gui/replay.png "The trajectory replay with the FDS smoke layer on, zoomed in on the agent.")](images/web-gui/replay.png)

The **Smoke** chart below the replay plots the mean speed factor and the mean
extinction coefficient *K* over time. Other charts, such as Cognitive map
growth, stay empty for this one-agent corridor.

[![A Plotly chart titled Smoke, with time from 0 to 85 s on the horizontal axis, the speed factor on the left axis between 0.9196262 and 0.9196266, and the extinction coefficient K on the right axis between 0.995502 and 0.995507 per metre. Both lines are flat until about 50 s and then vary in their last digits](/images/web-gui/smoke_chart.png "The Smoke chart of the same run. K is uniform at about 1 1/m, so the axes zoom in on changes in the sixth and seventh decimal places.")](images/web-gui/smoke_chart.png)

{{< checkpoint title="The run finished" >}}
The agent leaves the corridor after 85.3 s, and the run reports 1 of 1
agent evacuated. The **Warning** box says that FED is disabled: this deck
writes only the soot extinction slice, no CO, CO₂ or O₂, so the warning is
expected here. The same run from the command line,

```bash
uv run python run.py --scenario assets/iso_table21_coupled \
    --fds-dir assets/iso_table21_coupled/fds
```

ends with `Simulation finished in 85.30 s (1/1 evacuated).`
{{< /checkpoint >}}

### Keep the run as a script

Click **Show Python for this run** in the results header to get this run as
a standalone Python script. **Show equivalent Python**, in the Parameters
header, previews the current form settings instead. See
[Show the run as Python](#show-the-run-as-python).

{{% /steps %}}

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
| Output files | **Output folder**; the SQLite with its run manifest, the five CSVs and the scenario bundle (`<run folder>/bundle`) are written to the run's folder (see [Output folders](#output-folders)) |
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
`run.py` command. Invalid combinations (for example `--vis-cache` with rerouting off)
are rejected when the form is submitted, with the same message as `run.py`,
in the alert above the results area.

One run is active at a time. It runs on a background thread and streams its
progress to the page. **Run scenario** and **Results only** stay locked
while a run is active or cancelling. **Cancel run** stops the run at its
next step.

### Run states

When a run ends, the panel shows one of these states, each with a header
that names the run and its own buttons:

| State | Shown when | Buttons |
|---|---|---|
| Results | the run finished and its results are displayed | **Show Python for this run**, **Clear results** |
| Failed | the run raised an error; the message comes first | **Show configuration of this run**, **Clear** |
| Cancelled | you cancelled the run; no results were produced | **Show configuration of this run**, **Clear** |
| Results not displayed | the run finished, but its results view could not be built | **Show Python for this run**, **Clear** |
| Ended | another run started, possibly in another window | **Show current run** |

**Clear results** asks for confirmation first: "Clear the results of run #N
from this view? The files on disk are kept." **Clear** on a failed or
cancelled run does not ask. A reload of the page shows the state the server
holds, so results survive a refresh. The form itself returns to its
defaults, so the Settings changed banner appears until you set the run's
settings again.

The outcome line comes from the run's status, not from whether the run
raised an error. It reads "Complete: all agents evacuated" when every agent
has entered and left, and "Incomplete: time limit reached, *k* agents
inside" when the time limit stopped the run first. When flow agents were
still to enter, it adds ", *m* not spawned", a Not spawned tile appears, and
the Evacuated tile counts spawned agents only.

### Settings changed

After a run, editing the form so that it would configure a different run
shows a banner: "Settings changed since run #N. The results below show that
run's settings, not the form. Run again to get results for the current
settings." The results header gets a **Previous settings** tag. If the
edited form is invalid, the banner says that the settings cannot currently
be run, and why. The comparison uses the same resolution as a submitted run
and leaves the output paths out. Restoring the settings removes the banner.

### Output folders

Each run writes into a folder of its own, so no run overwrites another:

- **Output folder blank** (the default): the folder is derived as
  `<results root>/<scenario>/<mode>/seed<seed>/<start time>`, where *mode* is
  the incapacitation mode, *seed* the seed the run uses, and *start time* the
  run's UTC start time, for example `20260929T181031Z`.
- **Output folder typed:** the run writes into `<typed folder>/<start time>`.
  While a folder is typed, a note under the box shows the resolved path:
  "Each run writes into *folder*/&lt;start time&gt;/". A relative folder is
  taken under the results root.

The results root is the folder in the environment variable
`PYFDS_EVAC_RESULTS_DIR` when it is set, and otherwise the results folder of
[Where the GUI reads and writes](#where-the-gui-reads-and-writes). If a run's folder
already exists, `-2`, `-3`, … is added to its name.

## Results

- **Summary**: the outcome in words, tiles for time, evacuated, remaining
  and seed used, the peak gas and heat FED when the run reported them (with
  "Incapacitated: not reported by this version"), and the run's warnings.
- **Charts**: smoke over time and the growth of the cognitive maps. FED is
  shown live during a run.
- **Trajectory replay**: agents move between the stored trajectory samples,
  coloured by cumulative gas FED or by assigned exit, with play, pause, a
  scrub bar, speeds of 1×, 2×, 5×, 10× and 50× or a custom speed, and
  scroll-to-zoom and drag-to-pan. When the run has an `fds_dir`, the FDS
  extinction slice is drawn under the agents as a smoke layer that can be
  switched off. Without a FED model, for example when the FDS output has no
  CO, CO₂ or O₂ slices, agents are coloured by exit and the FED/exit
  switch is not shown. The replay colours by gas FED only, not by heat FED
  ([#232](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/232)).
- **FED panel**: under the replay, when the run has a FED model. It shows
  the highest gas FED of any agent on one continuous scale that runs to 1, or
  to the run's FED threshold if that is higher. A marker labelled
  "threshold" (deterministic mode) or "median threshold" (probabilistic
  mode) sits at the run's `fed_threshold`, read from the run's own settings,
  not the current form. Without a recorded threshold there is no marker.

The files the run writes are described on [Outputs](outputs.md).

## Show the run as Python

The GUI can write any configuration as a standalone Python script. Use it to
rerun a GUI run on another machine or to start a batch study from it, with
the settings and the seed traceable to the run. The script reproduces a
configuration; it does not validate the model. The GUI never executes it.

Two buttons open the code:

- **Show equivalent Python**, in the Parameters header: a preview of the
  current form settings. It is not a run.
- **Show Python for this run**, in the results header: the code of the most
  recent run, built from the settings frozen when it was submitted. On a
  failed or cancelled run the same button reads **Show configuration of this
  run**.

Both open a dialog with **Copy** and **Download .py**.

[![Dialog titled "Code for run #1 · blind_spawn_discovery" with its start time and a RUN #1 badge. Below it the line "Status: Complete: all agents evacuated (30/30), evacuation time 55.14 s", five notices on packages, files not included, paths, outputs and reproducibility, a collapsed "Details" line, and the start of the script: comment lines with the pyfds-evac version, git commit, run number, start time and scenario, followed by the imports](/images/web-gui/run_code_dialog.png "The run-code dialog for run #1 of blind_spawn_discovery.")](images/web-gui/run_code_dialog.png)

The screenshot predates the per-distribution seeds of
[#360](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/360); the
same run now ends as described in the steps below
([#384](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/384)).

### Save a run and run it again

1. In the scenario picker, choose the plain `blind_spawn_discovery` entry,
   not one of its `/ config_….json` variants, and run it with the default
   settings.
2. When the run has finished, click **Show Python for this run**. The dialog
   is titled "Code for run #1 · blind_spawn_discovery · *start time*" and
   reports "Status: Incomplete: time limit reached, 2 agents inside,
   simulated time 300.00 s".
3. Click **Download .py**. The file is named after the scenario, the run
   number and the run's UTC start time, for example
   `pyfds_evac_blind_spawn_discovery_run1_20260929T182009Z.py`.
4. Run it with the pyfds-evac version named in its header, installed the same
   way as the GUI, for example the repository's `uv` environment. The `gui`
   extra is not needed. From the folder that holds the script:

   ```bash
   uv run --project /path/to/pyFDS-Evac python pyfds_evac_blind_spawn_discovery_run1_20260929T182009Z.py
   ```

{{< checkpoint title="Script run completed" >}}
After the model's own progress and log lines, the script ends with
(pyfds-evac 0.1.0; path shortened):

```text
Simulation incomplete: time limit reached after 300.00 s (28/30 evacuated, 2 remaining).
Trajectory SQLite: /…/pyfds_evac_blind_spawn_discovery_run1_20260929T182009Z_output/trajectory.sqlite
```

The run is incomplete, so the script exits with status 2, as `run.py` does.
The folder `pyfds_evac_blind_spawn_discovery_run1_20260929T182009Z_output`, created in the
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
- **Results can differ from the GUI run, even with the same seed,** with
  other versions or on other platforms.
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
live form. The status line uses the wording of the results view:
"Complete: all agents evacuated (*n*/*N*), evacuation time *t* s",
"Incomplete: time limit reached, *k* agents inside[, *m* not spawned],
simulated time *t* s", failed, cancelled, or not recorded. The file is named
`pyfds_evac_<scenario>_run<N>_<start time>.py`, with the run's UTC start
time such as `20260929T182009Z`.

- **Failed and cancelled runs** still have code. The dialog is titled
  "Configuration of the failed run #N" or "Configuration of the cancelled
  run #N"; the button that opens it reads **Show configuration of this
  run**. The code stays until you click **Clear**.
- **Only the most recent run has code.** There is none while a run is in
  progress. After **Clear** (or **Clear results** for a finished run) or a
  new run, the old run's code is gone and its button disappears. A button
  left over in another tab opens a dialog titled "No recorded run". Run
  numbers restart at 1 with every GUI session, so file and folder names
  carry the start time as well.
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
   `pyfds_evac_<scenario>_run<N>_<start time>_output` or
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
# pyfds-evac 0.1.0, commit ba4ade3041930519187984ba052ca02f0add0485.
# Run #1, started 2026-09-29T18:20:09+00:00.
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
OUTPUT_DIR = pathlib.Path('pyfds_evac_blind_spawn_discovery_run1_20260929T182009Z_output')

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

- **Run code, the run reported the seed expected at submission:** that seed,
  with `# seed used by run #N`.
- **Run code, seed box left blank and no seed confirmed** (for example a
  failed or cancelled run): `None`, with
  `# seed not recorded for this run; None = the scenario's baseSeed`.
- **Run code, seed typed in but not confirmed** (for example a failed or
  cancelled run): the submitted value, with
  `# seed submitted; the seed used was not recorded`.
- **Preview, seed box blank:** `None`, with
  `# None = the scenario's baseSeed (<value>)`, for example `(1301)` for
  `blind_spawn_discovery`.
{{< /details >}}

{{< details title="What the script leaves out, and why" closed="true" >}}
- **The GUI's CSV histories and app bundle.** The smoke, FED, route,
  route-cost and exit histories and the bundle are written by `apply_outputs` in
  `pyfds_evac.cli`, which the exported script does not call yet. Their keys
  (`output_smoke_history`, `output_fed_history`, `output_route_history`,
  `output_route_cost_history`, `output_exit_history`, `output_sqlite`,
  `export_app_bundle`) are set
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
