---
title: "Terminal UI"
weight: 10
aliases: [/docs/terminal-ui/]
---

`pyfds-evac-tui` is an optional front end that runs in a terminal. You pick a
scenario and an FDS folder, set the options, check the effective
configuration, run, and read the results, all in six steps. It works in an
SSH session on a remote machine, with no port forwarding.

The terminal UI runs the same model, with the same defaults, as the
`pyfds-evac` command. It sets the same options and calls the same run path:
`stream_run` → `build_run_kwargs` → `run_scenario` → `apply_outputs`. For a
form in the browser, with charts and a trajectory replay, see the
[Web GUI](web-gui.md).

{{< callout type="warning" >}}
**The run stops when the terminal closes.** A closed window or a dropped SSH
session ends the run, and it leaves no trajectory and no CSV files. For long
runs, start the terminal UI inside `tmux` or `screen`, or use `pyfds-evac`
from the command line. See [When the terminal closes](#when-the-terminal-closes).
{{< /callout >}}

## Install and start

Install the `tui` extra. It adds [Textual](https://textual.textualize.io/)
(`textual>=8.2`). The terminal UI needs Python 3.12 to 3.14, like the
package.

```bash
pip install "pyfds-evac[tui]"
```

In a [source checkout](install.md#install-from-the-repository), use uv:

```bash
uv sync --extra tui
uv run pyfds-evac-tui
```

Without the extra, the command stops with the line below. `pyfds-evac-tui
--help` works without the extra.

```text
pyfds-evac-tui needs the TUI extra, which is not installed (missing module '…'). Install it with: pip install 'pyfds-evac[tui]'
```

### Start it in a folder with `assets/`

The terminal UI reads its examples from `./assets` and writes runs under
`./results`, where `./` is the folder you start it in. The package ships no
scenarios. Unpack the example zip of the [Quickstart](quickstart.md) and start
inside the unpacked folder, as for the
[Web GUI](web-gui.md#where-the-gui-reads-and-writes):

```bash
cd pyfds-evac-quickstart
pyfds-evac-tui
```

{{< checkpoint title="The terminal UI started" >}}
The top line shows the six steps, `1` to `6`. The **Examples** tab lists
`ISO-table21`. If it says "No assets/ folder here …", you started in another
folder: quit with `ctrl+q`, `cd` into the unpacked folder, and start again.
{{< /checkpoint >}}

- **Results folder.** Runs go to `./results`, or to `$PYFDS_EVAC_RESULTS_DIR`
  when it is set. The terminal UI has no upload folder: it opens scenario
  files where they are.
- **Terminal size.** The minimum is 80 × 24 characters. A smaller terminal
  shows "Terminal is W×H; the TUI needs 80×24. Resize, or zoom out. A run
  continues meanwhile." At 120 × 35 or larger, the Run and Results steps show
  the plan view beside the progress bars. In a smaller terminal, `v` opens
  the plan full screen.

{{< details title="Themes" closed="true" >}}
Two themes ship: `evac-dark` and `solarized-light`. The only command-line
option is `--theme {evac-dark,solarized-light}`. The theme is chosen in this
order:

1. `--theme`;
2. the environment variable `PYFDS_EVAC_TUI_THEME`;
3. the last theme used, stored in `recent.json` (see
   [Reproduce a run](#reproduce-a-run));
4. `evac-dark`.

An invalid `PYFDS_EVAC_TUI_THEME` stops the start with
`PYFDS_EVAC_TUI_THEME='x' is not a theme; choose from evac-dark, solarized-light`.
To switch while the terminal UI runs, open the command palette (`ctrl+k`) and
choose "Theme: evac dark" or "Theme: Solarized Light". The choice is
remembered.
{{< /details >}}

## Run a scenario

The first run uses `ISO-table21` from the Quickstart zip, in clear air: one
agent walks a corridor 100 m long to the exit.

1. **Scenario.** On a first start the **Examples** tab is open, with
   `ISO-table21` first. Press `Enter`. The terminal UI moves to the FDS step.
   After earlier runs the **Recent** tab opens instead: press `shift+tab`,
   `→` and `tab` to reach Examples, then `Enter`.
2. **FDS.** `ISO-table21` has no fire. Press `Enter` on **No FDS (clear
   air)**. The terminal UI moves to Configure.
3. **Configure.** Leave the defaults. Press `ctrl+n` to go to Review.
4. **Review.** It reads "✓ Ready to run". Press `ctrl+r`.
5. **Run.** The bars fill while the run goes on. The terminal UI moves to
   Results when the run ends.

{{< checkpoint title="The run finished" >}}
At 80 columns, Results starts with these lines:

```text
✓ Complete: all agents evacuated   exit 0
  Evacuation time 79.2 s   Evacuated 1 of 1 agents
  Incapacitated: not modelled in this run
```

This run has no dose model, so incapacitation is not modelled. From 100
columns on, the last line joins the line above it.

The run folder is `results/ISO-table21/deterministic/seed420/<UTC start>`. It
holds `ISO-table21.sqlite`, `ISO-table21.manifest.json`, the route, route-cost
and exit history CSVs, and `bundle/`.
{{< /checkpoint >}}

The sections below describe each step. The screenshots of the Scenario and
Configure steps are the terminal UI's snapshot tests, so they change when the
screens change. The others come from a real run of `assets/t_junction` with
the `fire_2MW_PVC` FDS output and seed 42; that FDS output was produced
separately and is not in the repository.

### The step bar

The top line marks each step with a glyph and a word, so it reads without
colour:

| Mark | Meaning |
|---|---|
| `✓` | done |
| `!` | errors |
| `⟳` | running |
| `✎` | settings changed since the run |
| `◐` (Results) | incomplete |
| `■` (Results) | cancelled |
| `✗` (Results) | failed, or the run stopped without a result |

### 1 Scenario

{{< terminal-figure src="tui-snapshots/test_snapshot_scenario[evac-dark].raw" min-width="40rem" max-width="46rem"
  alt="The Scenario step at 80 by 24 characters in the evac-dark theme. Three tabs: Recent, Examples and Open file; Examples is open. A filter box, then a list of examples: ISO-table21 marked deck only, iso_table21_coupled marked FDS output found, t_junction marked deck only, and its config variants indented below it. Under the list, the info line for ISO-table21: 1 agent, 1 exit, max time 300 s, seed 420."
  caption="The Scenario step (snapshot test `test_snapshot_scenario`, 80 × 24)." >}}

Three tabs choose the scenario:

- **Recent** lists the last 10 pairs of scenario and FDS folder, each with its
  last status and date. Entries whose scenario or FDS folder is gone come
  last, dimmed, and say which: "scenario missing", "FDS folder missing", or
  both. When two rows would read alike, a short part of the scenario's
  folder tells them apart. `Enter` restores the scenario and the FDS folder
  and jumps to Review. It restores no other setting
  ([#534](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/534)). If
  the scenario is gone, `Enter` stays on the Scenario step and says how to
  recover. If only the FDS folder is gone, `Enter` loads the scenario and
  opens the FDS step to choose another folder or none. `Delete` removes the highlighted
  entry from the list; nothing is removed automatically. Recent opens at
  start only when one of its entries can be used.
- **Examples** lists every folder in `./assets` that has a `config.json`, with
  its `config_*.json` variants, and a filter box. Each row says "FDS output
  found" or "deck only".
- **Open file** takes a `.json`, a `.zip`, or a folder with `config.json`.
  It browses as the FDS step does, starting in the folder you started the
  terminal UI in: the list shows the folders and the `.json` and `.zip`
  files, marks scenarios as **scenario** (a `.json` or `.zip` file, or a
  folder with a JSON and a WKT file), and offers `..` to go up. `Enter` or a
  click on a scenario opens it; on any other folder it goes into it. Typing
  a path filters the list; `Tab` completes and `↓` goes to the list.

The info line shows the number of agents and exits, the maximum time and the
seed.

### 2 FDS

{{< terminal-figure src="images/tui/tui-fds.svg"
  alt="The FDS step at 120 by 35 characters. The FDS output folder field holds /Users/Shared/pyfds-evac-demo/assets/t_junction/fire_2MW_PVC. Below it, two choices: Found FDS output assets/t_junction/fire_2MW_PVC, and No FDS (clear air). The inventory line reads: check mark extinction, check mark co, check mark co2, check mark o2, cross temperature, cross integrated_intensity. The next line reads: FDS output ends at 300.0 s; scenario runs to 300.0 s, with a check mark."
  caption="The FDS step with the `fire_2MW_PVC` output of `assets/t_junction`." >}}

- The step suggests the folders with a `.smv` file up to 2 levels below the
  scenario and below the start folder. You can also type a path, or choose
  **No FDS (clear air)**.
- Typing a path browses folders, as Emacs `dired` does. The list shows the
  subfolders of the typed folder that match the typed name as `fzf` does
  (`fvs` finds `fic_vs_fed_speed`; names that start with it come first),
  marks those
  with a `.smv` file as **FDS output**, and offers `..` to go up. `Enter` (or
  a click) on an FDS output folder chooses it; on any other folder it goes
  into it. `Tab` completes the name as far as it is unique, as a shell does;
  `↓` goes to the list; `~` is the home folder. Hidden folders show when the
  typed name starts with a dot. Typing while the list has the focus goes to
  the path box, so the list narrows and `↑`/`↓`/`Enter` still pick.
- Choosing a folder reads its inventory in a separate process. The step shows
  ✓ or ✗ for extinction, CO, CO2, O2, temperature and integrated intensity,
  and the end time of the FDS output against the scenario's time limit.
- For a "deck only" example, the step says to run FDS first or to continue
  without fire. [What your FDS case must provide](fds-case-requirements.md)
  lists the slices a run reads.

### 3 Configure

{{< terminal-figure src="tui-snapshots/test_snapshot_configure[evac-dark].raw" min-width="40rem" max-width="46rem"
  alt="The Configure step at 80 by 24 characters for ISO-table21 without FDS. The Scenario and run section is open: the derived output folder ending in ISO-table21/deterministic/seed420/20261003T120000Z, fixed until a setting changes; a Seed field, not set, with its help text; Advanced (1) collapsed. The FDS input and smoke section is open: the FDS folder reads none, no fire input; smoke update interval, smoke slice height and two other fields are marked inactive. Collapsed sections follow: Toxic gas (FED/FIC), Heat (off), Routing, Visibility and signs, ASET/RSET tools. The summary line at the bottom reads L2, smoke off, gas off, heat off, FIC off, reroute 1 s, vis off, valid."
  caption="The Configure step (snapshot test `test_snapshot_configure`, 80 × 24)." >}}

The options are grouped in the sections of `pyfds-evac --help`: Scenario &
run, FDS input & smoke, Toxic gas (FED/FIC), Heat, Routing, Visibility &
signs, ASET/RSET tools, and Outputs.

- The step offers 40 options: every run option of `pyfds-evac` except
  `--cleanup`, `--export-only`, `--inspect-fds` and `--print-summary`.
  `--show-config` is not a run option; the Review step shows its report.
- Each section shows its common options, then the others under
  "Advanced (*n*)".
- The output paths are not fields. They follow from the **Output folder** at
  the top: the Outputs section lists them, see
  [Outputs and folders](#outputs-and-folders).
- An option that has no effect with the current settings is greyed out, with
  the reason. `Enter` on it goes to the setting that enables it.
- `?` or `F1` shows the option's help, its flag, its default, its Python API
  default, its FDS+Evac counterpart, its unit and a link to its docs page,
  followed by the list of keys.
- `ctrl+f` finds a setting. The palette (`ctrl+k`) has "Reset all settings",
  which asks first, and "Toggle advanced in all sections".
- The summary line at the bottom shows the review level, the active models,
  and "✓ valid" or the number of errors.

### 4 Review

{{< terminal-figure src="images/tui/tui-review.svg"
  alt="The Review step at 120 by 35 characters. The header reads Ready to run, Level 2. Inputs: the scenario /Users/Shared/pyfds-evac-demo/assets/t_junction, the FDS folder ending in fire_2MW_PVC, ends 300.0 s; seed 42 from the scenario; time limit 300 s; the output folder. Models: smoke_speed on, FDS extinction at 1.6 m every 1.0 s; gas_fed on, CO, CO2, O2; heat_fed off, needs --enable-heat-fed; tenability on; rerouting on every 1.0 s; visibility on, smoke-aware, 3 signs; smoke_blind, replay_exits, fds_horizon_hold and fds_coverage_required off. Changed settings none, no effect none, warnings none. At the bottom, the command box starting with pyfds-evac --scenario /Users/Shared/pyfds-evac-demo/assets/t_junction --output-sqlite and the run folder."
  caption="The Review step for the `fire_2MW_PVC` run. The paths are those of the folder the screenshot was taken in." >}}

Review shows the effective configuration: the same report as
`pyfds-evac --show-config`, described in
[Checking a configuration before the run](usage.md#checking-a-configuration-before-the-run).
At the bottom is the `pyfds-evac` command for these settings.

- Errors are listed first. `Enter` on an error goes to its field. A run with
  errors cannot start.
- **Level 2** means the FDS folder was inspected. **Level 1** means it was not,
  because the inspection failed or is still running. Then the checks that need
  the FDS slices are not shown yet. Level 1 does not mean the configuration is
  wrong. The palette entry "Inspect FDS folder" tries again, and a failed
  inspection still allows the run.
- `c` copies the command, `s` writes `command.sh` and `run.py` into the planned
  run folder, and `p` shows the equivalent Python. See
  [Reproduce a run](#reproduce-a-run).

### 5 Run

{{< terminal-figure src="images/tui/tui-run.svg"
  alt="The Run step at 120 by 35 characters during the fire run. The phase line reads Running, with the phases initialising, FDS inspection, visibility, running, writing outputs, done. The status line reads sim 56.0 of 300 s, wall 0:03, evacuated 12 of 200 planned (6 %), incapacitated 0, not spawned 171; one warning. On the left, the plan view of the T-junction: walls, the exits A_left with 10 and B_right with 2 evacuated, three signs as diamonds, agents as dots. On the right, the Evacuated and Simulated time bars and the evacuated sparkline. Below the plan, the time scrubber, the smoke legend with bins 0.1, 0.5, 1, 3 and 10 per metre, FDS slice z = 2.0 m, frame t = 56 s, the glyph legend, and the note The run stops if this terminal closes; use tmux or screen for long runs. The run log fills the bottom."
  caption="The Run step about 56 s into the `fire_2MW_PVC` run (seed 42), wide layout." >}}

The run happens in a separate process. You can move between steps; the run
goes on. Only one run happens at a time: `ctrl+r` during a run says "A run is
in progress (run #*N*)".

- The phase line shows initialising → FDS inspection → visibility → running →
  writing outputs → done.
- The status line shows the simulated time against the limit, the wall time,
  "evacuated *e* of *t* planned", the incapacitated agents (only when the
  run models incapacitation), the agents not yet spawned, and the number of
  warnings (`w` lists them).
- During the run, *t* counts the **planned** agents, including flow agents that
  have not spawned yet. Results counts the agents **that entered**. In the
  screenshots, the run shows "of 200 planned" and Results "of 150 that
  entered", because 50 agents had not spawned when the time limit was reached
  ([#279](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/279)).
- `x` or `ctrl+c` cancels, after a confirmation. See [Cancel a run](#cancel-a-run).
- `v`, `w` and `l` open the plan, the warnings and the log full screen.

### 6 Results

{{< terminal-figure src="images/tui/tui-results.svg"
  alt="The Results step at 120 by 35 characters after the fire run. The first line reads Incomplete: time limit reached, 80 agents inside, 50 not spawned, exit 2. Then: Simulated time (limit reached) 300.0 s, Evacuated 70 of 150 that entered, Incapacitated 0; a bar for 70 of 150; the summary line; run 1, t_junction, seed 42, wall 0:13. On the left, the plan replayed at 60 s with its scrubber. On the right, one warning, the per-exit counts at the end of the run, exit_A_left 10 and exit_B_right 60, and the evacuated-over-time sparkline. At the bottom, the output files with their sizes: bundle, the smoke, FED, route, route-cost and exit history CSVs, t_junction.sqlite, t_junction.manifest.json and child.log."
  caption="Results of the `fire_2MW_PVC` run, with the plan replayed at 60 s." >}}

The outcome comes first, in the same words as the Web GUI:

| Outcome line | Exit status |
|---|---|
| "Complete: all agents evacuated" | 0 |
| "Incomplete: time limit reached, *k* agents inside[, *m* not spawned]" | 2 |
| "Run failed: …"; "(during setup; the run was not started)" when the run failed before it started | 1 |
| "Cancelled at sim *t* s", or "Cancelled before the first progress sample" | none |
| "The run stopped without a result (process exit *N*)" | none |

The exit statuses are those of `pyfds-evac`; see
[Exit status](usage.md#exit-status). Then follow the time, "Evacuated *e*
of *n* agents" ("… that entered" when flow agents had not spawned), and
"Incapacitated *j*" when the run models incapacitation or "Incapacitated:
not modelled in this run" when it does not. Below 100 columns the
incapacitated part goes on a line of its own.
[Results](web-gui.md#results) on the Web GUI page says when a run models
incapacitation. After that come the run line (run number, scenario, seed
used, wall time), the warnings, the per-exit counts at the end of the run,
the evacuated-over-time sparkline (wide layout only), and the output files
with their sizes.

- `←` and `→` replay the stored plan frames 1 s at a time, `shift+←` and
  `shift+→` 10 s at a time. Replay works only after the run has ended.
- `y` copies the path of the highlighted file. `t` shows the traceback or the
  end of `child.log`.
- `c` and `s` give the command and the script of this run; see
  [Reproduce a run](#reproduce-a-run).
- `e` goes back to Configure, `n` starts a new scenario.

**Settings changed.** If you edit the settings after a run so that they
differ from the run's, Results reads "✎ Previous settings. Settings changed
since run #*N*. These results show that run's settings, not the current ones.
Run again …". The output paths are left out of this comparison; a typed
output folder is included. The idea is the same as in the Web GUI; see
[Settings changed](web-gui.md#settings-changed).

## Keys

| Where | Key | Action |
|---|---|---|
| everywhere | `ctrl+k` | command palette: themes, go to step, Inspect FDS folder, Copy command, Save command and script, Show Python, Reset all settings, Toggle advanced, Open docs page |
| everywhere | `ctrl+q` | quit; during a run it asks "A run is in progress. Quit and cancel it?" |
| FDS to Results | `ctrl+p` | previous step, keeping all values; the footer names it. From Run it goes to Review and the run continues; from Results it goes to Configure. `Esc` does the same, but tmux's `escape-time` can delay it |
| everywhere | `?` or `F1` | the list of keys; on a Configure field, the field's help first. `?` is never typed into a text box |
| Scenario, FDS, Configure | `ctrl+n` | next step (from Configure: to Review) |
| Configure, Review, Results | `ctrl+r` | run. With warnings, outside Review, it asks "r Run anyway / Esc Review"; on Review it runs at once |
| Configure | `↑` / `↓` | previous / next option, also out of a text box or a closed dropdown; `Enter` flips a switch, opens a dropdown or a section, and on an inactive option goes to the setting that enables it |
| Configure | `ctrl+f` | find a setting |
| Review | `c` | copy the command to the clipboard (OSC 52) |
| Review | `s` | write `command.sh` and `run.py` into the planned run folder, before any run |
| Review | `p` | show the equivalent Python of the current settings |
| Review, during a run | `ctrl+n` | back to the Run step |
| Run | `x` or `ctrl+c` | cancel, after a confirmation |
| Run | `v` / `w` / `l` | full-screen plan / warnings / log |
| Results | `c` | open "Command and Python for run #*N*", built from the run's settings; `c` in the dialog copies |
| Results | `s` | write `command.sh` and `run.py` of the run into the run folder, replacing a save from Review |
| Results | `Enter` | preview the highlighted output file: the first 40 lines of a text file, the tables and row counts of a SQLite file, the files of a folder. In the dialog `y` copies the path and `o` opens the file in the system app (macOS `open`, Linux `xdg-open`; not over SSH) |
| Results | `y` | copy the path of the highlighted output file |
| Results | `e` / `n` / `t` / `w` | change settings (Configure) / new scenario / traceback or end of `child.log` / warnings |
| Results, full plan | `←` / `→`, `shift+←` / `shift+→` | replay the plan frames by 1 s / 10 s, after the run has ended |
| Run, Results | `v` | full-screen plan (`Esc` back) |

The keys avoid common terminal conflicts: there is no `ctrl+s` (XOFF) and no
`ctrl+a` or `ctrl+b` (the `screen` and `tmux` prefixes). `ctrl+n` and `ctrl+p`
are next and previous, as in Emacs and tmux. The palette is on `ctrl+k`,
not Textual's default `ctrl+p`, so in a text box `ctrl+k` does not delete to
the end of the line.

The footer shows the keys of the current step on the left and, on every
step and in the full-screen plan, a fixed group on the right:
`^q quit  ? keys  ^k palette`. On a narrow terminal the step keys are cut
first; the fixed group stays visible at 80 columns. The labels are words, so
they read the same with `NO_COLOR` or `TERM=dumb`.

## Outputs and folders

Each run gets its own folder, under the same rules as in the Web GUI:
`<results folder>/<scenario>/<mode>/seed<seed>/<UTC start>`, or
`<typed folder>/<UTC start>`, with `-2`, `-3`, … added when the folder exists.
[Output folders](web-gui.md#output-folders) on the Web GUI page gives the
rules in full. Configure shows the planned folder under **Output folder**; it
stays the same until a setting changes.

The files are named after the scenario:

| File | Written |
|---|---|
| `<name>.sqlite` | always: the trajectory |
| `<name>.manifest.json` | always: the run manifest, beside the trajectory |
| `<name>_smoke_history.csv` | when a smoke model ran |
| `<name>_fed_history.csv` | when the gas FED or the heat FED ran |
| `<name>_route_history.csv` | when rerouting is on (the default) |
| `<name>_route_cost_history.csv` | when rerouting is on |
| `<name>_exit_history.csv` | always |
| `bundle/` | always: the scenario for the app |
| `child.log` | always; listed in Results only when it is not empty |
| `command.sh`, `run.py` | when you press `s` |

[Outputs](outputs.md) describes each model output column by column. Results
lists the files as the run reports them, with their names and sizes; the
labels of the Web GUI are not shared yet
([#550](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/550)).

## Reproduce a run

Three records describe a run:

- **The run manifest** `<name>.manifest.json` holds the effective configuration
  under `configuration`. `configuration.command` is the full `pyfds-evac …`
  command. See [Run manifest](outputs.md#run-manifest).
- **`command.sh`** is one line: the shortest `pyfds-evac` command, with
  absolute paths. It includes the `--output-*` and `--export-app-bundle` flags,
  which point at the run's own folder. **Running it again overwrites that
  run's files.** Edit the paths first, or use `run.py`.
- **`run.py`** is the same standalone script as the Web GUI's
  [Show the run as Python](web-gui.md#show-the-run-as-python), with the header
  "Generated by pyfds-evac-tui." It writes into `<run folder>/python_output`,
  so it never overwrites the run. Saved from Results, it carries the seed the
  run used, also when that seed came from the scenario.

`s` on Review saves the scripts of the current settings before a run. `c` and
`s` on Results use the settings the run had.

The terminal UI cannot reopen a run's settings yet
([#534](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/534)). Recent
restores only the scenario and the FDS folder.

{{< details title="Where the Recent list is stored" closed="true" >}}
The Recent list is `$XDG_CONFIG_HOME/pyfds-evac/recent.json`, or
`~/.config/pyfds-evac/recent.json` when `XDG_CONFIG_HOME` is not set, on
every operating system. It holds the last 10 runs and the theme. If the file
cannot be read or written, the terminal UI ignores it.
{{< /details >}}

## The plan view

{{< terminal-figure src="images/tui/tui-plan-solarized.svg" min-width="40rem" max-width="46rem"
  alt="The full-screen plan at 80 by 24 characters in the Solarized Light theme, replaying the fire run at 60 s. The T-junction fills the screen: the horizontal corridor at the top with two signs at its ends and one near the junction, the vertical corridor below with agents as dots. The exits are labelled A_left with 10 and B_right with 2 evacuated. Below: the scrubber at 60.0 s of the 300 s limit, the smoke legend for K in 1/m with bins 0.1, 0.5, 1, 3 and 10, FDS slice z = 2.0 m, frame t = 60 s, the glyph legend, and the replay keys."
  caption="The full-screen plan (`v`) at 80 × 24 in the Solarized Light theme, replaying the `fire_2MW_PVC` run at 60 s." >}}

The plan view is a coarse preview of the run. The trajectory SQLite and the
CSV files are the results. It draws:

- walls, and the exits with their evacuated counts;
- signs (`◆`), agents (`•`; `●` for two or more in a cell; `x` incapacitated);
- the smoke as the extinction coefficient K in fixed bins at 0.1, 0.5, 1, 3
  and 10 1/m, the same for every run. The Web GUI replay uses the same bins
  and the same slice rule, so the two front ends draw smoke by the same rule.

The legend states the FDS slice height and the FDS frame time the run read.
That height is the slice actually read, the one nearest to the smoke slice
height: in the screenshots the slice is at 2.0 m, while the setting is the
default 1.6 m. See [Selecting a slice height](fds-sampling.md#selecting-a-slice-height).
The run manifest does not record the slice height yet
([#592](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/592));
see [Run manifest](outputs.md#run-manifest).

Without plan data, or with `TERM=dumb`, the region reads "plan not available".

{{< details title="How often the plan is updated" closed="true" >}}
The run sends a plan frame when 1/*f* wall seconds have passed or when 1
simulated second has passed, whichever comes first. A smoke grid is sent
whenever the FDS frame changes. *f* is 5 per second, 2 when `SSH_CONNECTION`
is set, and 1 when `PYFDS_EVAC_TUI_REDUCED_MOTION` is set.

On a fast run the simulated-second rule decides: on `t_junction` about 90
frames come per wall second. The Run screen redraws at most 10 times per wall
second. So the two variables only lower the wall-time rule; they do not limit
the plan to 1 or 2 updates per second.

All frames stay in memory for the replay, so a very long run uses more
memory. Tests show that recording the frames does not change the results.
{{< /details >}}

## How a run is executed

Each run is a separate `spawn` child process that runs the same code as
`pyfds-evac`. A test runs the same scenario through the terminal UI and
through `pyfds-evac` with the command the terminal UI shows. The two give
identical `trajectory_data` rows, the same set of CSV files with
byte-identical contents, and the same exit status. The test uses `ISO-table21`
with seed 7, without fire, so it compares the route, route-cost and exit
histories; it does not cover a fire scenario.

- **`child.log`.** The child's standard output and error go to
  `<run folder>/child.log`: Python warnings, output of the native libraries,
  and the `--debug` lines. Nothing prints over the screen.
- **Temporary files.** The child gets a private temporary folder, removed
  when the child ends, whatever the outcome. If the terminal UI itself was
  killed, its folder (`pyfds-evac-run-<pid>-…`) stays behind until the next
  start of the terminal UI removes it.
- **A crashed run.** When the child ends without a result, Results reads "The
  run stopped without a result (process exit *N*)", and `t` shows the last 20
  lines of `child.log`.

### Cancel a run

1. `x` or `ctrl+c` asks "Cancel run? Files already written are kept."
2. The run stops at its next progress sample, or between two phases. The
   status reads "Cancelling… (waiting for the current phase: …)".
3. If no result comes within 10 s, the terminal UI terminates the process,
   and kills it 3 s later.

This automatic stop never happens while the outputs are being written,
because those writes are not atomic. A cancel pressed during "writing outputs"
is not acted on: the run finishes, and Results shows Complete or Incomplete,
not Cancelled.

Pressing cancel again asks "Stop the process now?". `y` terminates the process
at once, **also** during "writing outputs", and so does `ctrl+q` with "Quit and
cancel". Both can leave a partial file.

A cancelled run has no exit code. Results reads "■ Cancelled at sim *t* s",
or "■ Cancelled before the first progress sample" when no progress sample
had arrived, with "; the process was stopped" when it was terminated. A run cancelled
before the writing phase writes no trajectory and no CSV files: only
`child.log` remains, and `command.sh` and `run.py` if you saved them.

### When the terminal closes

The run stops. On a hang-up (SIGHUP), or when its parent process is gone, the
child stops at its next progress sample, as on a cancel. Outputs are written
only at the end of a run, so a closed terminal or a dropped SSH session leaves
**no trajectory and no CSV files**: only `child.log`, and `command.sh` and
`run.py` if you saved them. Start the run again.

- The Run step says "The run stops if this terminal closes; use tmux or screen
  for long runs."
- For long runs, start the terminal UI inside `tmux` or `screen`. Or use
  `pyfds-evac` from the command line, with Slurm on a cluster.
- A run cannot be detached or reattached
  ([#530](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/530)).
- A child that is still starting when the terminal UI is killed can run to
  its end ([#555](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/555)).

## SSH, terminals and accessibility

- **Copy** (`c`, `y`) uses the OSC 52 escape sequence only, so the terminal
  must support it. It does not work in macOS Terminal (see
  [`App.copy_to_clipboard`](https://textual.textualize.io/api/app/#textual.app.App.copy_to_clipboard)).
  Under `tmux` it needs `set -g set-clipboard on`. When it fails, nothing is
  copied and no error appears. The message reads "Sent to clipboard (OSC 52).
  If nothing was copied, select the command above or press s." Over SSH, the
  reliable ways are the command shown on Review and the files that `s` writes.
- **Over SSH** (`SSH_CONNECTION` set), the wall-time rule for plan frames
  drops to 2 per second. The screen still redraws up to 10 times per second.
- **Colours.** The themes need a truecolor terminal. With 256 or 16 colours,
  each theme colour is rounded to the nearest one the terminal has, so
  `solarized-light` turns yellow, grey and pink. The terminal UI then says at
  start "This terminal shows 256 colours, so the theme colours are
  approximate." It decides from `COLORTERM` and `TERM`, as
  [Rich](https://rich.readthedocs.io/en/stable/console.html#color-systems)
  does. To get truecolor:
  - set `COLORTERM=truecolor` when the terminal supports it. SSH does not
    forward `COLORTERM`, so set it on the server, for example in `~/.bashrc`;
  - in `tmux` 3.2 or later, add `set -g default-terminal "tmux-256color"` and
    `set -as terminal-features ",*:RGB"` to `~/.tmux.conf`, then restart the
    tmux server (`tmux kill-server`).
- **`NO_COLOR`** (any non-empty value) gives Textual's monochrome rendering.
  The plan then draws the smoke bins with the shade glyphs `░ ▒ ▓ █`, and
  agents and states keep their glyphs. `NO_COLOR` is the only way to get the
  shade glyphs.
- **`PYFDS_EVAC_TUI_REDUCED_MOTION`** only lowers the wall-time rule for plan
  frames, to 1 per second. It does not stop the motion; see
  [How often the plan is updated](#the-plan-view).
- **Glyphs.** `• ● ◆ ◐ ✓ ✗` have an ambiguous East Asian width. In a CJK locale
  a terminal may draw them two cells wide. There is no ASCII fallback.
- **Platforms.** The terminal UI tests, including the snapshots, run in CI on
  Ubuntu with Python 3.12, 3.13 and 3.14. It was developed on macOS. Windows
  is not tested. Windows has no SIGHUP, so there the run stops on a closed
  terminal only through the check of the parent process.

## Web GUI and terminal UI

The output folders, the outcome wording, "Settings changed" and the Python
script are shared and described on the [Web GUI](web-gui.md) page. The
differences:

| | Web GUI | Terminal UI |
|---|---|---|
| Runs in | a background thread of the server | a child process; its output goes to `child.log` |
| Closing the window or the terminal | the server keeps the run going | the run stops |
| Scenario input | `./assets` picker; uploads saved in `./uploads` | `./assets` examples, Recent, or a file, zip or folder opened where it is |
| Options offered | the GUI form (several heat and visibility options under "Other", [#311](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/311), [#270](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/270)) | 40 options: every run option except `--cleanup`, `--export-only`, `--inspect-fds`, `--print-summary` |
| Effective configuration before the run | — | Review (the `--show-config` report) |
| Results | charts, trajectory replay, FED panel | outcome, per-exit counts, sparkline, plan replay in 1 s steps, file list |
| Results-only mode | yes | no |
| Over SSH | needs port forwarding (`--host`, `--port`) | runs in the SSH session |

## Limits

- No reopening of a run's settings, and no `--config` file
  ([#534](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/534)).
- No stored run records, no reattaching, and no Slurm submission from the
  terminal UI ([#530](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/530)).
- A child that is still starting when the terminal UI is killed can run to its
  end; its temporary folder is removed at the next start
  ([#555](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/555)).
- The output files have no labels shared with the Web GUI and the command
  line; Results shows the file names
  ([#550](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/550)).
- The run counts planned agents; Results counts the agents that entered
  ([#279](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/279)).
- All replay frames are held in memory.
- No results-only mode, no charts and no trajectory replay. Open the SQLite in
  the Web GUI or in [fds-viewer](https://github.com/PedestrianDynamics/fds-viewer).

Error messages of the terminal UI, with their fixes, are on
[Troubleshooting](troubleshooting.md#terminal-ui).

{{< details title="Where this is in the code" closed="true" >}}
- `pyfds_evac/tui/runner.py`, `ProcessRunner`, `child_entry`, `frame_rate`, `sweep_temp_dirs`: the child process, the frame rate and the temporary folders.
- `pyfds_evac/tui/app.py`, `EvacTui`, `results_text`, `result_files`: the steps, the outcome lines and the file list.
- `pyfds_evac/tui/model.py`, `Recent`, `save_command`, `list_examples`: Recent, `command.sh` and `run.py`, and the Examples tab.
- `pyfds_evac/config/frontend.py`, `output_paths`, `results_root`, `run_outcome`: the files, the results folder and the outcome wording, shared with the Web GUI.
- `pyfds_evac/config/effective.py`, `cli_command`: the command in `command.sh`.
- `pyfds_evac/core/run_stream.py`, `stream_run`: the run, as `pyfds-evac` makes it.
- `tests/test_tui.py`, `test_a20_tui_run_equals_cli`: the equivalence test with `pyfds-evac`.
{{< /details >}}
