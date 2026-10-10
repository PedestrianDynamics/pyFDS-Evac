---
title: "Troubleshooting"
weight: 11
---

Find the message you see, then its cause and fix. Errors stop the run;
warnings let it continue, often with part of the model switched off, so read
them. The deck-side causes (missing slices, `&REAC` yields) are explained on
[What your FDS case must provide](fds-case-requirements.md).

## Errors

Command-line errors start with the name of the command you ran:
`pyfds-evac:` for the installed command, `run.py:` in a source checkout, and
`__main__.py:` for `python -m pyfds_evac` on Python 3.12 and 3.13.

| Message | Cause | Fix |
|---|---|---|
| `OSError: No simulations were found in the directory: DIR` | `--fds-dir` points at a directory without FDS output, for example one holding only the `.fds` deck. | Point it at the directory with the `.smv` file of a finished FDS run. |
| `ValueError: --inspect-fds requires --fds-dir` | `--inspect-fds` has nothing to inspect. | Add `--fds-dir`. |
| `ValueError: --vis-cache requires --enable-rerouting` | `--vis-cache` with `--no-enable-rerouting`. | Drop one of the two; rerouting is on by default. |
| `ValueError: --clear-air-visibility contradicts --fds-dir: …` | Clear-air sight on a deck with a fire. | Drop `--clear-air-visibility`; with `--fds-dir` the smoke decides what agents see. |
| `ValueError: --no-visibility and --clear-air-visibility conflict` | Both flags given. | Keep one. |
| `ValueError: --heat-regime layer needs --heat-fed-method total-flux` | The layer regime is part of the total-flux method. | Add `--heat-fed-method total-flux`. |
| `ValueError: --heat-regime layer needs --heat-layer-height` (or `--heat-view-factor`, `--heat-layer-emissivity`) | These three have no default. | Set all three; see [Models › Heat](/models/heat.md). |
| `ValueError: --heat-radiant-source integrated-intensity needs --heat-fed-method total-flux.` | As above, for the radiant source. | Add `--heat-fed-method total-flux`. |
| `ValueError: --heat-radiant-source integrated-intensity needs --heat-u-factor in [0.25, 1]; there is no default.` | *f* has no default. | Set `--heat-u-factor`. |
| `ValueError: DIR has no INTEGRATED INTENSITY slice. …` | The deck writes no `INTEGRATED INTENSITY` slice. | Add `&SLCF QUANTITY='INTEGRATED INTENSITY'` at the slice height and rerun FDS. |
| `pyfds-evac: error: argument --heat-u-factor: must be in [0.25, 1.0], got …` | *f* outside its range. | Use a value in [0.25, 1]. |
| `pyfds-evac: error: Distribution '…': requested N agents but area can hold at most ~C. …` | A spawn area asks for more agents than the run's capacity estimate. Also printed by `--export-only`. | Lower `number`, or enlarge the polygon in `distributions.<id>.coordinates`. |
| `pyfds-evac: error: Distribution '…': could not place the N requested agents (Only K of N  could be placed. …). The capacity estimate ~C is an upper bound. …` | The count is within the estimate, but JuPedSim cannot place every agent, for example in a narrow area. | As above. |
| `pyfds-evac: error: Distribution '…': JuPedSim could not add an agent to the simulation (…).` | JuPedSim refused an agent at a position the sampler gave, for example for an unknown journey or stage or a model parameter it rejects. | Read JuPedSim's message in the parentheses; the spawn area is not too small. |
| `ValueError: Unknown routing cost_model '…'; expected one of ('gate', 'additive')` | `routing.cost_model` in the scenario JSON is not one of the two names. The match is exact and case-sensitive: `"Gate"` fails. Raised with rerouting on or off. | Write `"gate"` or `"additive"`, or drop the key for `"gate"`; see [Scenario JSON](scenario-json.md#route-choice-routing). |
| `ValueError: Distribution '…' sets desired_speed=… and v0=…; desired_speed is an alias of v0, set one of them` (or the same for `desired_speed_distribution` and `v0_distribution`, `desired_speed_std` and `v0_std`) | A spawn area sets an alias and its `v0*` key to different values. | Set one of the two, or give both the same value; see [Scenario JSON](scenario-json.md#spawn-areas-distributionsidparameters). |
| `ValueError: Unknown speed_law '…'; expected one of ('lund', 'fridolf')` | Python only: a `SmokeSpeedConfig` built with another `speed_law`. No command-line option or JSON key sets it. | Use `"lund"` or `"fridolf"`, in lower case. |
| `pyfds-evac-gui needs the GUI extra, which is not installed (missing module '…'). Install it with: pip install 'pyfds-evac[gui]'` | `pyfds-evac-gui` without the `gui` extra. | Run `pip install "pyfds-evac[gui]"`, or `uv sync --extra gui` in a source checkout. |
| `pyfds-evac-tui needs the TUI extra, which is not installed (missing module '…'). Install it with: pip install 'pyfds-evac[tui]'` | `pyfds-evac-tui` without the `tui` extra. | Run `pip install "pyfds-evac[tui]"`, or `uv sync --extra tui` in a source checkout. |
| `IndexError: No slice with quantity '…' found in DIR` | A direct library call (`FdsFedField.from_fds`, `ExtinctionField.from_fds`, `load_slice_sampler`) on a case without that slice. `run.py` warns instead. | Add the slice to the deck, or check the case with `--inspect-fds` first. |

The `cost_model` and alias errors appear when the run starts, after the FDS
output is read. `--show-config` prints `Errors: none` for such a deck
([#571](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/571)).

### `pyfds-evac init`

| Command | Status | Meaning |
|---|---|---|
| `pyfds-evac init DECK.fds` | 0 | the scenario is written and runnable |
| | 3 | written, but not runnable (no exit, no agents, too many agents for a spawn area), or runnable with an input dropped at error level |
| | 1 | nothing written: the deck cannot be read, an argument is wrong, or `-o` holds a scenario the importer did not write |
| `pyfds-evac init DECK.fds --check` | 0 | the deck has the extinction-coefficient, CO, CO2 and O2 slices and `&TIME T_END` |
| | 3 | at least one of them is missing (a ✗ line names it and gives the `&SLCF` line to add) |
| | 1 | the deck cannot be read, the floor cannot be chosen, or an argument is wrong |

A plain `init` prints the same slice check, but its exit status ignores it.
Each message, its cause and its fix are in
[Usage › Messages and what to do](usage.md#messages-and-what-to-do).

## Warnings that change the result

| Message starts with | What happened | Fix |
|---|---|---|
| `FED is disabled for DIR: it has no CO slice …` | No gas FED: the result has no FED at all, not zero FED ([#137](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/137)). | Add the CO, CO₂ and O₂ slices and the `&REAC` yields. |
| `Heat FED is disabled for DIR: it has no TEMPERATURE slice.` | `--enable-heat-fed` on a case without temperature. | Add `&SLCF QUANTITY='TEMPERATURE'`. |
| `Smoke speed reduction is disabled for DIR: …` | No extinction slice; agents walk at clear-air speed. | Add the `SOOT EXTINCTION COEFFICIENT` slice, or pass `--constant-extinction`. |
| `Visibility falls back to clear air for DIR: …` | No extinction slice for sign legibility. | As above. |
| `Requested a '…' slice at z=… m but the nearest available … is at z=… m` | No slice within 0.5 m of `--smoke-slice-height`; the run reads another height. | Add slices at 1.6 m, or set `--smoke-slice-height` to a height the deck has. A slice within 0.5 m is used without a warning ([#165](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/165)). |
| `--heat-… has no effect without --enable-heat-fed.` | A heat option without the heat dose. | Add `--enable-heat-fed`, or drop the option. |
| `--heat-fed-threshold … departs from ISO 13571:2012 …` | A separate heat threshold is set. | Intended if you set it; the manifest records it. |
| `Distribution '…' sets no pre-movement; using the FDS+Evac default, a constant 10 s.` | The spawn area has no pre-movement keys. | Set `use_premovement` and the `premovement_*` keys ([Scenario JSON](scenario-json.md)). |
| `pyfds-evac: warning: import_report.json marks this scenario not runnable` | `pyfds-evac init` wrote the folder as not runnable and lists why. The run goes on, since the folder may have been fixed by hand after `init`; a stale cause can still stop it later. | Fix what the reasons name and import again, or edit the folder by hand ([Start from an FDS deck](start-from-fds-deck.md)). |

## Harmless log lines

- `WARNING:root:Module csv: [Errno 2] No such file or directory: …_hrr.csv`
  (and `…_steps.csv`), followed by "The error can be safely ignored if not
  requiring the csv module": fdsreader looks for CSV output the case does not
  have. The command line prints each such warning once per run.
- `Reroute debug: …` lines: a trace of the rerouting pass, printed with
  `--debug`.
- `Heat FED is off; pass --enable-heat-fed to accumulate it.`: the heat dose is
  off by default, as in FDS+Evac.

## Terminal UI

Messages of `pyfds-evac-tui`. How the terminal UI works is on
[Terminal UI](terminal-ui.md).

| Message | Cause | Fix |
|---|---|---|
| `PYFDS_EVAC_TUI_THEME='…' is not a theme; choose from evac-dark, solarized-light` | The environment variable names a theme that does not exist. | Unset it, or set it to one of the two themes. |
| "Terminal is W×H; the TUI needs 80×24." | The terminal is smaller than 80 × 24 characters. | Resize the window or zoom out. A run continues meanwhile. |
| "No assets/ folder here. Start the TUI in a folder that holds one …" | The terminal UI started in a folder without `assets/`. | `cd` into the unpacked example zip of the [Quickstart](quickstart.md) and start again, or use the **Open file** tab. |
| "This example ships the FDS deck only. Run FDS first, or continue without fire" | The example has no FDS output. | Run FDS on the deck, or choose **No FDS (clear air)**; see [What your FDS case must provide](fds-case-requirements.md). |
| "Could not inspect the FDS folder: … The run is still allowed; Review shows Level 1." | The folder could not be read as FDS output. | Check that the folder holds the `.smv` file; then choose "Inspect FDS folder" in the palette (`ctrl+k`). |
| "The run stopped without a result (process exit N)." | The run's process crashed or was killed. | `t` shows the end of `child.log`; the full log is in the run folder. |
| Nothing was copied after `c` or `y` (the message reads "Sent to clipboard (OSC 52). If nothing was copied, …") | The terminal does not support OSC 52: macOS Terminal, or `tmux` without `set -g set-clipboard on`. | Select the command shown on Review, or press `s` to write `command.sh` and `run.py`. |

## Known pitfalls

- **The progress line counts planned agents.** With flow spawning it can show
  more agents than the final summary
  ([#279](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/279)).
- **`evacuation_time` with incapacitated agents** is the end of the run, not
  an exit time; see [Outputs › Reading the results](outputs.md#reading-the-results).
