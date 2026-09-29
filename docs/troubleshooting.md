---
title: "Troubleshooting"
weight: 10
---

Find the message you see, then its cause and fix. Errors stop the run;
warnings let it continue, often with part of the model switched off, so read
them. The deck-side causes (missing slices, `&REAC` yields) are explained on
[What your FDS case must provide](fds-case-requirements.md).

## Errors

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
| `run.py: error: argument --heat-u-factor: must be in [0.25, 1.0], got …` | *f* outside its range. | Use a value in [0.25, 1]. |
| `IndexError: No slice with quantity '…' found in DIR` | A direct library call (`FdsFedField.from_fds`, `ExtinctionField.from_fds`, `load_slice_sampler`) on a case without that slice. `run.py` warns instead. | Add the slice to the deck, or check the case with `--inspect-fds` first. |

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

## Harmless log lines

- `WARNING:root:Module csv: [Errno 2] No such file or directory: …_hrr.csv`
  (and `…_steps.csv`), followed by "The error can be safely ignored if not
  requiring the csv module": fdsreader looks for CSV output the case does not
  have.
- `Reroute debug: …` lines: a trace of the rerouting pass.
- `Heat FED is off; pass --enable-heat-fed to accumulate it.`: the heat dose is
  off by default, as in FDS+Evac.

## Known pitfalls

- **One scenario per process for studies.** Run each seed in its own
  process ([why](limitations.md#reproducibility), #198).
- **Tied routes and `PYTHONHASHSEED`.** Set `PYTHONHASHSEED` to a fixed value
  for bit-identical reruns of discovery agents
  ([why](limitations.md#reproducibility), #199).
- **The progress line counts planned agents.** With flow spawning it can show
  more agents than the final summary
  ([#279](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/279)).
- **`evacuation_time` with incapacitated agents** is the end of the run, not
  an exit time; see [Outputs › Reading the results](outputs.md#reading-the-results).
