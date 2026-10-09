---
title: "Usage: running simulations and producing plots"
linkTitle: "Usage"
weight: 6
aliases: [/docs/usage/]
---

This page catalogues every user-facing script in the repository: how to run
an evacuation simulation, every `run.py` flag with its default, and which
plotting script consumes each artefact. All commands assume the project venv
(`uv run ...`) and run from the repository root. What each output file
contains is on [Outputs](outputs.md); error messages and their fixes are on
[Troubleshooting](troubleshooting.md).

## Running a simulation — `run.py`, `pyfds-evac`

The pyFDS-Evac command line is the single entry point for an evacuation run.
In a source checkout it is `run.py`. It loads a
JSON-first JuPedSim scenario, optionally couples it to an FDS case for
smoke-speed / FED / visibility, and writes CSV/SQLite artefacts for
post-processing.

```
uv run python run.py --scenario <scenario.json|.zip|dir> [options]
```

After `pip install pyfds-evac` the same command line is installed as
`pyfds-evac`, and `python -m pyfds_evac` runs it too ([Install](install.md)).
Both take the flags below, with the same defaults, outputs and exit codes.
The commands on this page use `uv run python run.py` because they read the
scenarios and scripts of a source checkout; with pip, replace
`uv run python run.py` by `pyfds-evac` and run them where those files are.

### Scenario selection and export

| Flag | Purpose |
|------|---------|
| `--scenario PATH` | Scenario JSON, ZIP, or directory (required). |
| `--seed N` | Override the scenario's `baseSeed` (42 when the scenario sets none). |
| `--print-summary` | Print the loaded scenario summary before running. |
| `--debug` | Print debug messages, such as the `Reroute debug` trace of the rerouting pass. From Python, `logging.getLogger("pyfds_evac").setLevel(logging.DEBUG)` with a handler does the same. |
| `--show-config` | Print the effective configuration and exit without running; see [Checking a configuration before the run](#checking-a-configuration-before-the-run). |
| `--output-sqlite PATH` | Copy the JuPedSim trajectory SQLite here, with the run manifest beside it as `<stem>.manifest.json`. When FED is computed, also writes an optional `agent_scalars(frame, id, fed, heat_fed, speed)` side table (base JuPedSim schema untouched) so [fds-viewer](https://github.com/PedestrianDynamics/fds-viewer) can colour agents by FED or speed. |
| `--cleanup` | Kept for compatibility: the temporary trajectory SQLite and its manifest are always removed after the run. |
| `--export-app-bundle DIR` | Write `config.json` and `geometry.wkt` [for the app](howto-create-scenario.md#open-a-scenario-in-the-app-again). |
| `--export-only` | Export the bundle without running the simulation. |

### FDS coupling (smoke, FED, visibility)

`--fds-dir` must point at the output of a finished FDS run: the directory that
holds the `.smv` file and the slice files. A directory with only the `.fds`
deck stops the run with `OSError: No simulations were found in the directory`.
Your deck has to write specific slices; see
[What your FDS case must provide](fds-case-requirements.md) for the lines to
add and the failure modes that stay silent unless you read the warnings.

| Flag | Default | Purpose |
|------|---------|---------|
| `--fds-dir DIR` | none | FDS output directory. Drives smoke speed, gas FED, heat FED (with `--enable-heat-fed`) and smoke-aware sign legibility. |
| `--constant-extinction K` | none | Use a constant `K` [1/m] instead of the FDS extinction slice for walking speed and for route pricing (the optical depth `K·L` of the route gate). FED, heat FED and sign legibility still read `--fds-dir` when it is given; without `--fds-dir`, sign legibility stays clear air, so a constant `K` hides no sign. |
| `--smoke-update-interval S` | 1.0 s | Seconds between smoke-speed updates. The same interval is the integration step of the gas FED and heat FED, and the row spacing of the smoke and FED histories. |
| `--smoke-slice-height M` | 1.6 m | Height of the horizontal slices that are read ([FDS+Evac](https://github.com/firemodels/fds/tree/c9da70d7a/Source) `HUMAN_SMOKE_HEIGHT`; 2.0 was the previous default). One height for speed, gas FED, heat FED and sign legibility: the nearest horizontal slice is used, with a warning only when it is more than 0.5 m away. See [FDS slice sampling](fds-sampling.md). |
| `--allow-fds-horizon-hold` | off | Let the run outlast the FDS output by holding the last slice frame, with a warning at setup and one per quantity. Without it, a `max_simulation_time` more than one slice output interval past the last FDS frame stops the run at setup, and so does any smoke, FED, heat or sign-visibility sample past it, except route foresight, which reads the last frame (#666). See [FDS slice sampling](fds-sampling.md#past-the-end-of-the-fds-output). |
| `--require-fds-coverage` | off | Stop the run when part of the scenario lies outside the FDS slices: at setup for the walkable area, an exit, checkpoint, spawn area, sign or route edge, and at any smoke, FED, heat or sign-visibility sample. Without it, those places read ambient air and clear sight, as in FDS+Evac; the run logs what lies outside at setup, flags each history row with `in_fds_domain`, and counts the samples outside at the end. See [Outputs](outputs.md). |
| `--output-smoke-history CSV` | none | Write the smoke history; columns on [Outputs](outputs.md#smoke-history). |
| `--output-fed-history CSV` | none | Write the FED history; columns on [Outputs](outputs.md#fed-history). Not written when neither FED track runs. |
| `--inspect-fds` | off | List the FDS quantities of `--fds-dir` as JSON and exit. Needs `--fds-dir`. |

### Dynamic rerouting (smoke-aware route choice)

| Flag | Default | Purpose |
|------|---------|---------|
| `--enable-rerouting` / `--no-enable-rerouting` | on | Let agents re-evaluate exits during the run. Needed by an exit with `open_from_s` or `closed_after_s` ([Scenario JSON](scenario-json.md#exits-exitsid)). |
| `--reroute-interval S` | 1.0 s | Seconds between per-agent reevaluations. With a smoke-aware visibility model it is also the time step at which sign legibility is computed. |
| `--output-route-history CSV` | none | Write route switches; see [Outputs](outputs.md#route-history). |
| `--output-route-cost-history CSV` | none | Write ranked route cost snapshots; see [Outputs](outputs.md#route-cost-history). |
| `--vis-cache NPZ` | none | Path to a vismap `.npz` cache — written if missing, loaded if present. Requires rerouting to be enabled (the run aborts otherwise). With `--fds-dir` that has an extinction slice it caches the smoke-aware vismap; otherwise the clear-air grid. |
| `--clear-air-visibility` | off | Force sight gating on a deck with no fire. Conflicts with `--fds-dir` (a deck with a fire has smoke to decide sight) and with `--no-visibility`. |
| `--no-visibility` | off | Turn sight gating off entirely; agents then learn each node's neighbours by contact. Not a fire scenario. |
| `--vis-cell-size M` | 0.25 m | Resolution of the clear-air visibility grid. Keep it below the thinnest wall that must block sight. |
| `--max-sign-distance M` | 30 m | Farthest distance from which a sign can be read, also in clear air. A sign's own `"max_distance"` overrides it. |

**The default route-choice model does not trigger the visibility model.** The
default `"gate"` route-cost model reads no vismap: its smoke criterion is the
optical depth along the route polyline, and sign legibility only decides what
enters an agent's cognitive map. A deck whose agents all start fully familiar therefore builds
no visibility model at all unless you pass `--vis-cache` or
`--clear-air-visibility`. A deck with discovery agents builds one either way,
because they need it to learn the graph. See
[route-cost-gate.md](route-cost-gate.md).

### Smoke-blind runs and exit replay

For ASET/RSET comparisons the same FDS output can be run in three arms: a
smoke-blind arm, a speed-only arm that keeps the smoke-blind arm's exits, and
the fully coupled default
([#341](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/341)).

| Flag | Default | Purpose |
|------|---------|---------|
| `--smoke-blind` | off | Sample the fire for the histories only. Agents walk at their free speed, choose their first exit with K = 0 and no FED, and see signs as in a run without the fire. Rerouting and tenability are off whatever the other flags say, so a scenario with a scheduled exit cannot run smoke-blind. Gas FED, heat FED and FIC still accumulate and are written to the FED history; `incapacitated` stays false. The smoke history holds the sampled K with `speed_factor` 1. |
| `--output-exit-history CSV` | none | Write each path agent's exit; see [Outputs](outputs.md#exit-history). |
| `--replay-exits CSV` | none | Send each agent to the exit its counterpart took in an earlier run, read from that run's `--output-exit-history` file. Agents are paired by origin and spawn order within it (`origin`, `spawn_index`), not by JuPedSim id. The route to that exit is the one clear-air costs rank best on the agent's map. Not allowed with an exit that has `open_from_s` or `closed_after_s`. |

A smoke-blind run with a fire gives the same trajectories as the run without
the fire, for the same scenario and seed. Replay pairs the n-th agent spawned
from an origin in one run with the n-th agent spawned from that origin in the
other, which needs the same scenario and seed. The origin is `initial` for the
agents placed at t = 0 and `flow:<distribution>` for a flow source, so a source
that is blocked and spawns later does not shift the pairing of another.
JuPedSim ids are not used: they can skip a number when a spawn position is
refused, and a slower crowd changes which positions are refused. Every
per-agent draw, such as the familiarity map, the target points and the journey
variant, is seeded from this spawn order, so paired agents draw the same in
both runs. An exit history written before per-agent draws were seeded this way
(its run's manifest has no `agent_seeding` key), or with another scheme such
as `spawn-key-blake2b-v1`, whose agents started at other positions, still
replays without error, but pairs agents whose draws differ; write it again. A replayed run fails when a spawn is missing
from the file, when the file names an exit the scenario lacks, or when an
agent cannot be sent to its exit; it logs a warning when agents of the file were
never spawned. With rerouting on, a replayed agent can still switch exits,
and the run logs a warning. The three arms, with tenability recorded but not
acting in all of them, so that incapacitated agents do not stay in the
building and lengthen the evacuation:

```bash
# U: smoke-blind; writes the exits for S
uv run python run.py --scenario S.json --fds-dir FDS --smoke-blind \
    --output-exit-history u_exits.csv --output-sqlite u.sqlite
# S: smoke slows agents, exits and routes as in U
uv run python run.py --scenario S.json --fds-dir FDS --no-enable-rerouting \
    --disable-tenability --replay-exits u_exits.csv --output-sqlite s.sqlite
# R: smoke slows agents and acts on routing
uv run python run.py --scenario S.json --fds-dir FDS --disable-tenability \
    --output-sqlite r.sqlite
```

[Evacuation with and without the fire](howto-with-without-fire.md) runs these arms against a run without the fire and compares them.

### Tenability (FIC slowdown and incapacitation)

The two dose tracks are independent:

- **Gas FED** runs when `--fds-dir` has the CO, CO₂ and O₂ slices (HCN, NO,
  NO₂ and the irritants are used if present). It is on by default whenever
  those slices exist.
- **Heat FED** runs when `--enable-heat-fed` is given and `--fds-dir` has a
  `TEMPERATURE` slice. It is off by default, as FDS+Evac has no heat dose.

Incapacitation applies to whichever track runs. Without `--fds-dir` neither
runs and the flags below have no effect. The FIC slowdown (a pyFDS-Evac
assumption, source unknown;
[#147](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/147)) is off
by default, as FDS+Evac has none. The equations are on
[Models › FED](/models/fed.md) and [Models › Heat](/models/heat.md).

| Flag | Default | Purpose |
|------|---------|---------|
| `--disable-tenability` | off | Turn off the FIC slowdown and both incapacitation checks. FED and heat FED are still accumulated and written. |
| `--enable-fic-speed` | off | Turn the FIC slowdown on. |
| `--fic-alpha F` | 0.7 | Slope of `v/v₀ = max(μ, 1 − α·FIC)`; needs `--enable-fic-speed`. |
| `--fic-min-factor F` | 0.3 | Floor `μ`; needs `--enable-fic-speed`. |
| `--fed-threshold F` | 1.0 | FED at which agents are incapacitated, as FDS+Evac; in probabilistic mode the median of the per-agent threshold. |
| `--o2-threshold-percent P` | 20.0 % | O₂ vol % at or above which the hypoxia term is zero, as FDS; 19.5 was the previous default. |
| `--incapacitation-mode MODE` | `deterministic` | `deterministic` or `probabilistic`. `deterministic`: every agent stops at `--fed-threshold`, as FDS+Evac. `probabilistic`: each agent draws a log-normal threshold with median `--fed-threshold`. |
| `--susceptibility-sigma S` | 0.94 | Log-normal σ of the gas threshold in probabilistic mode. |

### Heat dose (opt-in)

All flags in this table need `--enable-heat-fed`; without it they have no
effect. With `--fds-dir`, the run then warns for `--heat-endpoint`,
`--heat-clothing`, `--heat-fed-method`, `--heat-radiant-source` and
`--heat-regime`; the other heat flags are ignored silently. The laws, parameters and their
sources are on [Models › Heat](/models/heat.md); the table only lists what
each flag sets.

| Flag | Default | Values | Purpose |
|------|---------|-------|---------|
| `--enable-heat-fed` | off | — | Accumulate the heat dose from the `TEMPERATURE` slice and incapacitate on it. |
| `--heat-clothing C` | `clothed` | `clothed`, `unclothed` | Convective law: ISO 13571:2012 Eq. (9), clothed, or Eq. (10), unclothed. No effect with `--heat-endpoint` or `--heat-fed-method total-flux`. |
| `--heat-endpoint E` | none | `tolerance`, `injury`, `fatal` | Use an SFPE Handbook Ch. 63 endpoint law instead of the ISO law. With `total-flux` it selects the dose *D* (fatal without it). |
| `--heat-fed-method M` | `convective` | `convective`, `total-flux` | `total-flux`: heat flux to the skin (SFPE Eq. 63.49) with the ISO 2.5 kW/m² radiant threshold. |
| `--heat-emissivity E` | 0.5 | — | Gas emissivity at the head; `total-flux` only. |
| `--heat-convective-coefficient H` | 5.0 W/m²/K | — | Convective coefficient; `total-flux` only. |
| `--heat-skin-temperature T` | 35.0 °C | — | Fixed skin temperature; `total-flux` only. |
| `--heat-radiant-source S` | `gas` | `gas`, `integrated-intensity` | Radiant term from the gas at the head, or the excess flux from the FDS `INTEGRATED INTENSITY` slice. `integrated-intensity` needs `total-flux` and `--heat-u-factor`, and the slice at the slice height. |
| `--heat-u-factor F` | none | [0.25, 1] | Factor *f* on the integrated intensity *U*; required with `integrated-intensity`. |
| `--heat-regime R` | `smoke` | `smoke`, `layer` | `layer`: head in clear air under a hot layer. Needs `total-flux` and the three layer flags below, or the run stops with `ValueError`. |
| `--heat-layer-height M` | none | finite | Height of the `TEMPERATURE` slice read as the hot layer. |
| `--heat-view-factor φ` | none | [0, 1] | View factor from the skin to the layer. |
| `--heat-layer-emissivity ε_L` | none | [0, 1] | Layer emissivity. |
| `--heat-fed-threshold F` | none (uses `--fed-threshold`) | — | Separate heat threshold. ISO 13571 uses one threshold; setting it logs a warning and the manifest records it. |
| `--heat-incapacitation-mode MODE` | `deterministic` | `deterministic`, `probabilistic` | As `--incapacitation-mode`, for the heat track. |
| `--heat-susceptibility-sigma S` | 0.94 | — | Log-normal σ of the heat threshold in probabilistic mode (borrowed from the gas value). |

### Seed and precedence

- `--seed N` overrides the scenario's `baseSeed`; a scenario without one uses 42.
- `--constant-extinction` takes precedence over the FDS extinction slice for
  walking speed and route pricing. Sign legibility reads the FDS extinction
  slice, or clear air without `--fds-dir`; it never reads the constant `K`.
- A sign's own `max_distance` in the scenario JSON takes precedence over
  `--max-sign-distance`.
- `--heat-fed-threshold` takes precedence over `--fed-threshold` for the heat
  track.
- `--smoke-blind` turns rerouting and tenability off, whatever
  `--enable-rerouting` and `--disable-tenability` say.

### Python API and command line

`run.py`, the web GUI, the terminal UI and their equivalent Python scripts
build their models with `build_run_kwargs` (`pyfds_evac/core/run_config.py`)
and use the command-line defaults. `run_scenario()` called directly uses the
Python defaults: it builds nothing you do not pass. Both sets are intended,
but the same scenario can behave differently:

| What | `run.py` | `run_scenario()` without that argument |
|------|----------|----------------------------------------|
| Rerouting | on (`--enable-rerouting`) | off: `reroute_config=None` |
| Re-decision interval | 1.0 s (`--reroute-interval`) | 10.0 s: `RerouteConfig.reevaluation_interval_s` |
| Route costs | the scenario's `routing` block, for the first exit choice and for rerouting | the `routing` block for the first exit choice. A `RerouteConfig()` built by hand carries the code defaults of `RouteCostConfig` and ignores the `routing` block, for the first choice as well; pass `cost_config=RouteCostConfig.from_routing_params(scenario.raw.get("routing"))` to keep it |
| Smoke speed | from `--fds-dir`, or `--constant-extinction` | none |
| Gas FED, heat FED | from `--fds-dir` (heat with `--enable-heat-fed`) | none |
| Incapacitation | `TenabilityConfig` whenever a FED track runs, unless `--disable-tenability` | none: `tenability_config=None`; a `fed_model` without `tenability_config` accumulates dose but never incapacitates |
| Visibility model | built for discovery agents, `--vis-cache` or `--clear-air-visibility`, unless `--no-visibility` | none: `vis_model=None` |
| Visibility time step | = `--reroute-interval`, 1.0 s | 10.0 s: `VisibilityModel(time_step_s=)` |
| Smoke-blind, exit replay | `--smoke-blind`, `--replay-exits` | off: `smoke_blind=False`, `replay_exits=None` (a dict of `(origin, spawn_index)` to exit) |

A Python user who copies `run_scenario(scenario)` therefore gets no
rerouting, no sight gating and no incapacitation. In
`assets/familiarity_test_discovery` (discovery agents, no FDS), all 20
agents leave in 86.40 s with `run.py` and in 36.94 s with
`run_scenario(scenario)`: without a visibility model the agents learn
neighbours by contact.

For a run with the command-line defaults, start from `DEFAULTS`, set the
paths and build the keywords as `run.py` does:

```python
import argparse
from pyfds_evac import build_run_kwargs, load_scenario, run_scenario
from pyfds_evac.config import DEFAULTS

opts = argparse.Namespace(**{**DEFAULTS,
    "scenario": "assets/iso_table22_coupled/config_a.json",
    "fds_dir": "assets/iso_table22_coupled/fds/a"})
scenario = load_scenario(opts.scenario)
result = run_scenario(scenario, **build_run_kwargs(scenario, opts))
print(f"FED max: {result.metrics['fed_max']:.3f}")
result.cleanup()
```

Run it from the repository root with `uv run python script.py`; the scenario
and its FDS output are tracked there. It prints `FED max: 1.170`, as
`run.py` with the same two paths. To change a setting, add it to the dict,
for example `"reroute_interval": 10.0`. Start from the full `DEFAULTS`:
`build_run_kwargs` reads about 20 options, such as `fds_dir`,
`reroute_interval`, `fed_threshold` and the `heat_*` options, as plain
attributes, so a namespace that lacks an option a built model reads raises
`AttributeError`; start from the full `DEFAULTS`. `pyfds_evac.config`
and `DEFAULTS` are provisional public API in 0.3.x: names may change.

**Show equivalent Python** in the [web GUI](web-gui.md#show-the-run-as-python)
and `p` in the [terminal UI](terminal-ui.md#reproduce-a-run) write this
pattern with every option set; the script reproduces the run of the front end.
[A crowd in a fire](first-fds-case.md) runs a coupled case from Python end to
end.

### Checking a configuration before the run

`--show-config` prints the effective configuration and exits without
running: which models are on or off and why, every option with its unit and
whether it is the default or departs from FDS+Evac, the scenario's `routing`
values, options that have no effect, the setup warnings and errors the run
would report, and the shortest equivalent command, with absolute paths.
Errors include the value checks made when a model is built (for example
`--vis-cell-size 0` or `--heat-emissivity 2`); warnings logged while a model
is built, such as signs outside the FDS extinction slice, are not listed. With `--fds-dir` it reads
the FDS inventory (slices and output end time), not the slice data. It exits
with status 1 when the configuration has an error, else 0. It does not check
an unknown `routing.cost_model` or an alias that contradicts its `v0*` key;
the run reports them ([Troubleshooting](troubleshooting.md#errors),
[#571](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/571)).

```bash
uv run python run.py --scenario assets/t_junction/config_discovery.json \
    --constant-extinction 0.5 --enable-fic-speed --show-config
```

```text
Options with no effect:
  --enable-fic-speed on: without --fds-dir

Setup warnings:
  --enable-fic-speed has no effect without --fds-dir.
```

A run with such an option logs the same warning at setup. Options left at
their default are never reported. The run manifest written with
`--output-sqlite` records the configuration under `configuration`, checked
against the seed, the models and the model parameters the run used
(thresholds, FIC slope, incapacitation modes, heat law and parameters,
reroute interval and route costs, visibility grid and reading distance,
sampling interval and slice height): `source` is `run` when they agree.
When `run_scenario` was given other models or parameters than the options
imply, `source` is `run, options differ`: only the run's settings (`run`)
are recorded as facts, and the configuration of the options is kept apart
under `predicted_from_options`, with the differing settings in
`mismatches` (e.g. `tenability.fic_alpha`).
From Python, `pyfds_evac.config.effective_configuration(opts, scenario)`
returns it; `pyfds_evac.config` is provisional public API in 0.3.0 and can
change in 0.3.x.

### Agent visualisation

Agent 3-D visualisation is handled by
[fds-viewer](https://github.com/PedestrianDynamics/fds-viewer), which
loads the JuPedSim trajectory SQLite written by `--output-sqlite` (and
its optional `agent_scalars` table for FED/speed colouring).

### Typical invocations

```bash
# Bare JuPedSim run, no smoke coupling
uv run python run.py --scenario assets/t_junction/config.json
```

```text
Simulation incomplete: time limit reached after 300.00 s (144/150 evacuated, 6 remaining).
```

```bash
# FDS-coupled run with all diagnostic outputs, on a tracked FDS output
uv run python run.py --scenario assets/iso_table22_coupled/config_a.json \
    --fds-dir assets/iso_table22_coupled/fds/a \
    --output-sqlite results/demo.sqlite \
    --output-smoke-history results/smoke.csv \
    --output-fed-history results/fed.csv \
    --output-route-history results/routes.csv \
    --output-route-cost-history results/route_costs.csv
```

```text
Configuring smoke calculation.
Configuring FED calculation.
Heat FED is off; pass --enable-heat-fed to accumulate it.
Configuring rerouting.
Configuring tenability (FIC slowdown=off, FIC alpha=0.7, min=0.3, FED median=1.0, incapacitation=deterministic, heat FED median=1.0, heat incapacitation=deterministic).
…
Simulation incomplete: time limit reached after 1150.00 s (0/1 evacuated, 1 remaining).
Route switches: 0
Route cost samples: 1149
```

The occupant of this ISO 20414 Test 19 case never leaves; it is incapacitated
at 982 s. Rerouting is on by default, so `--enable-rerouting` is not needed.
The tracked FDS output of the T-junction fire is not in the repository; run
`assets/t_junction/t_junction.fds` with FDS, or see
[A crowd in a fire](first-fds-case.md).

### Exit status

| Status | Meaning |
|---|---|
| 0 | the run completed: every agent entered and left |
| 2 | the run is incomplete: it reached `max_simulation_time` with agents inside or flow agents still to enter; all requested outputs are written |
| 1 | an error; the run did not finish |

Both runs above exit with status 2. A script that runs `run.py` under
`set -e` must accept status 2 if incomplete runs are expected, e.g.
`uv run python run.py … || [ $? -eq 2 ]`. Argument errors also exit with
status 2, before the run starts.

## Inspecting an FDS case

`scripts/inspect_fds.py` summarises what quantities FDS wrote and whether
they are within tenability-relevant ranges. Its `--height` defaults to 2.0 m;
pass 1.6 to match `run.py`
([#313](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/313)).

```bash
uv run python scripts/inspect_fds.py assets/iso_table22_coupled/fds/a --height 1.6
```

```text
FED readiness:
  ✓ CO / CO2 / O2 all present and non-zero → default FED model will run
  ✗ Extinction coefficient → smoke-speed model will NOT run
```

This case has an extinction slice whose values are all zero, so `run.py` does
build the smoke model; it reads *K* = 0 (clear air).

## Probing FED without running a simulation

`scripts/probe_fed.py` integrates FED at fixed `(x, y)` points directly
from the FDS output. Useful as a sanity check ("if an agent stood still
here, would it be incapacitated?"). `--slice-height` defaults to 1.6 m.

```bash
uv run python scripts/probe_fed.py --fds-dir assets/iso_table22_coupled/fds/a \
    --point 5,5 --output results/probe.csv --plot results/probe.png
```

```text
       point    peak FED    peak rate    t(FED=threshold)
      (5, 5)      1.1724       0.0611             981.0 s
```

## Plotting

All plotting scripts are pure post-processors: they consume one of the
CSV/SQLite artefacts produced by `run.py` and write PNGs.

### Artefact → plotting-script map

| Artefact (run.py flag that writes it) | Plotting scripts |
|--------------------------------------|------------------|
| FED history (`--output-fed-history fed.csv`) | `plot_fed_history.py`, `plot_trajectories_by_speed.py` |
| Smoke history (`--output-smoke-history smoke.csv`) | `plot_smoke_history.py` |
| Route cost history (`--output-route-cost-history route_costs.csv`) | `plot_route_costs.py`, `plot_exit_choice.py` |
| JuPedSim SQLite (`--output-sqlite demo3.sqlite`) | `plot_trajectories.py`, `plot_trajectories_by_speed.py` (backdrop) |

### FED curves — `plot_fed_history.py`

```
uv run python scripts/plot_fed_history.py fed.csv [options]
```

| Flag | Mode |
|------|------|
| *(default)* | Spaghetti plot: one cumulative-FED line per agent; the first agent to reach the threshold (or, if none does, the one with the highest FED) is drawn bold and labelled. |
| `--show-rate` | Add a second panel with the FED rate. |
| `--stack AGENT_ID` | Per-species stacked FED breakdown for one agent. |
| `--stack-all DIR` | One stacked plot per agent, written as `DIR/fed_agent_NNNN.png`. |
| `--speed-vs-fed` | Scatter of desired speed vs cumulative FED, coloured by time. |
| `--speed-and-fed AGENT_ID` | Dual-axis time series (speed + FED) for one agent. |
| `--threshold F` | Threshold line (default 1.0). |
| `--title STR` | Override title. |
| `--output PNG` | Write PNG instead of showing. |

### Trajectories coloured by speed — `plot_trajectories_by_speed.py`

```
uv run python scripts/plot_trajectories_by_speed.py fed.csv \
    --sqlite demo3.sqlite --output trajs.png
```

Per-segment RdBu colouring (red = slow, blue = fast) from the extended
FED CSV; slower segments are also drawn wider, and the slowest sample is
ringed and labelled. The walkable area is drawn as backdrop via pedpy.

| Flag | Purpose |
|------|---------|
| `--sqlite PATH` | JuPedSim SQLite; backdrop via `pedpy.load_walkable_area_from_jupedsim_sqlite`. |
| `--agents 7,8,43` | Comma-separated agent ids (default: all). |
| `--vmax F` | Upper bound for the colormap (default: data max). |
| `--linewidth F` | Polyline width at full speed; slower segments are up to three times wider (default 0.5). |
| `--alpha F` | Polyline transparency (default 0.4). |
| `--title STR` / `--output PNG` | As usual. |

### Smoke history — `plot_smoke_history.py`

```
uv run python scripts/plot_smoke_history.py --input smoke.csv --output smoke.png
uv run python scripts/plot_smoke_history.py --input smoke.csv --output smoke_43.png --agent-id 43
```

| Flag | Purpose |
|------|---------|
| `--input CSV` (required) | Smoke history CSV. |
| `--output PNG` (required) | Output path. |
| `--agent-id N` | Single-agent plot instead of the aggregate. |

### Trajectories coloured by exit — `plot_trajectories.py`

Reads `trajectory_data` from the run's SQLite: what agents *did*, as opposed to
what `rank_routes` says they would do.

```
uv run python scripts/plot_trajectories.py <traj.sqlite> \
    --config <config.json> -o out.png [--title "..."] \
    [--route-history routes.csv] [--geometry geometry.wkt] [--reach 1.5]
```

| Flag | Effect |
|---|---|
| `--config` (required) | Exit polygons, and the colour and line-style key (one style per exit). |
| `-o/--out` (required) | Output PNG. |
| `--route-history` | `run.py --output-route-history` CSV. Colours each path by the exit targeted **at that moment** and marks every switch with a dot. Without it paths are coloured by the exit finally reached, which hides mid-run decisions entirely. |
| `--geometry` | Walkable-area WKT; defaults to `geometry.wkt` beside the config. |
| `--reach` | Metres from an exit polygon that count as having reached it (default 1.5). Agents that finish elsewhere are drawn grey and dotted, their end marked with a cross, and counted separately. |

### Route cost curves — `plot_route_costs.py`

Mean composite cost per exit over time.

**Under the default `"gate"` cost model this plot is not what ranks exits.**
The script reads the `composite_cost` column, which the gate computes and
reports but does not order on — it orders on `tau_route`, the route's optical
depth, with `rank_cost` (travel time plus weighted queue time) as tie-break. Read the curves as a smoke-exposure diagnostic, and
take exit choice from `plot_exit_choice.py`, the `tau_route` column or the
`rejection_reason` column instead.

The CSV also carries the gate's own diagnostics — `tau_route`, `rank_cost`,
`k_max_route`, `k_leg_max`, `clean` and `feasible` — which is what
makes a gate decision auditable: `feasible` says whether the route was
available, `tau_route` is the optical depth that both refused it and ordered
it, and `rank_cost` breaks ties between routes of equal `tau_route`. `k_leg_max` is the smokiest leg of the route and
`clean` whether that puts the exit in the clean-exit tier; `clean` is `False`
throughout unless the deck sets `clean_extinction_threshold`.

```
uv run python scripts/plot_route_costs.py route_costs.csv [routes.csv]
```

### Exit choice distribution — `plot_exit_choice.py`

Time series of how many agents target each exit at each evaluation tick,
plus a histogram of total agent-ticks per exit. Saves
`exit_choice_plot.png`.

```
uv run python scripts/plot_exit_choice.py route_costs.csv [routes.csv [config.json]]
```

### Quick interactive replay — `vis.py`

A one-line JuPedSim viewer: opens an interactive animation of a trajectory
SQLite instead of writing a file. Handy for a fast look without picking plot
options.

```
uv run python scripts/vis.py demo3.sqlite
```

## Cognitive-map movies and diagnostics

### One agent's walk, animated — `animate_cognitive_map.py`

Renders an MP4 (requires `ffmpeg` on PATH for MP4 output) of a single
agent walking a deck, with its known/unknown exits and checkpoints
colour-coded, sign facing arrows, and amber trail segments where the agent
is wandering (no known route). Runs its own simulation internally with
`collect_cognitive_map_history=True` — it does not consume a `run.py`
artefact.

```
uv run python scripts/animate_cognitive_map.py --scenario BUNDLE_DIR \
    -o cognitive_map.mp4 [--familiarity 0.0] [--agent ID] [--fps 12]
```

| Flag | Purpose |
|------|---------|
| `--scenario` (required) | Bundle directory with `config.json` + `geometry.wkt` (e.g. from `run.py --export-app-bundle`). |
| `--familiarity F` | Starting familiarity scalar for the spawn distributions (default 0.0). |
| `--agent ID` | Agent to follow (default: lowest id in the run). |
| `--seed N` | Run seed (default 420); needed to reproduce a specific movie. |
| `--fps N` | Movie frame rate (default 12). |
| `--cell-size M` | Visibility grid resolution in metres (default 0.25, as `--vis-cell-size`). |
| `--work DIR` | Working directory for the deck variant and run SQLite (default `results/cognitive_map_movie`). |

## Deriving inputs from an FDS deck

### Scenario from an FDS deck — `pyfds-evac init`

[Start from your own FDS case](start-from-fds-deck.md) walks through this
command on three decks.

Writes `config.json`, `geometry.wkt` and `import_report.json` into a
directory that `pyfds-evac --scenario` runs as it is, by default
`<deck stem>_scenario/` next to the deck (`-o DIR` picks another). It prints
the summary and the next steps: run FDS when its output is missing (with
the command, `mpiexec -n N` for N meshes), run the scenario, then refine it
in JuPedSim Web or the terminal UI. A scenario that cannot run gets no run
command, only the list of what to fix.

```
pyfds-evac init DECK.fds [-o DIR] [--walkable FILE.wkt] [--agents N] \
    [--exit x0,y0,x1,y1[,ior]] [--floor MESH_ID] [--floor-z Z] [--z-band LO HI] \
    [--exit-depth 0.5] [--no-fds] [--force] [-v]
```

- An FDS+Evac deck keeps its `&EXIT`, `&DOOR`, `&EVAC`, `&EVHO`, `&ENTR` and
  `&PERS` records, on one floor (the lowest; `--floor` picks another).
- A plain FDS deck gets an exit for every `SURF_ID='OPEN'` vent on the
  outside of its meshes between 0.1 and 1.8 m above the floor, plus any
  `--exit`. Each walkable part with an exit is a spawn area, with a
  placeholder of 100 agents in all unless `--agents` is given.
- An exit is a strip of `--exit-depth` metres on the room side of the exit
  line, so agents leave about 0.4 s before the line at 1.25 m/s.
- The walkable area is derived from the deck: the union of the floor's mesh
  footprints (the main evacuation meshes of an FDS+Evac deck), whose edge is
  a wall, minus the `&OBST` records in the walking band, less their `&HOLE`
  cuts. Only the parts that hold a spawn area, or
  without one an exit, are kept; `import_report.json` lists the dropped
  parts. `--walkable FILE.wkt` replaces the derived polygon.
- A spawn area that asks for more agents than the run can place (the same
  packing estimate the run uses) makes the scenario not runnable; the
  message gives the area, its capacity and the requested number.
- When `<CHID>.smv` lies next to a plain FDS deck, the run command gets
  `--fds-dir`, and the output says so; `--no-fds` leaves it out. An
  FDS+Evac deck needs the output of a fire-only run: the next steps say to
  run FDS on a copy without the evacuation namelists and meshes, and to
  pass that run's folder as `--fds-dir`. FDS+Evac output found next to the
  deck is reported but not used.
- The output folder, given with `-o` or the default, is refused when it
  holds a `config.json` the importer did not write (no `import_report.json`
  next to it), such as an authored scenario. `--force` overwrites it. A
  folder from an earlier `pyfds-evac init` is overwritten without asking.

The screen shows a short summary: each error on its own line with its deck
line, then every approximated or dropped input, whatever its level (each can
change what runs), grouped by pattern with the number of records each
concerns. Exact mappings and cosmetic keys are only in the report. `import_report.json` lists every input that was approximated or
dropped, with its line number; `-v`/`--verbose` prints all of it.

| Status | Meaning |
|---|---|
| 0 | written and runnable, nothing dropped at error level |
| 3 | written, but not runnable (no exit, no agents or too many agents for a spawn area; the summary prints `✗ Not runnable` and no run command), or runnable with an input dropped at error level, such as an exit too far from the walkable area |
| 1 | an error, including an argument error or a refused `-o` folder; nothing written |

#### What the importer derives

- **Deck type.** An FDS+Evac deck has a `&MESH` with `EVACUATION=.TRUE.`
  or any of `&EVAC`, `&EXIT`, `&PERS`, `&DOOR`, `&ENTR`, `&CORR`, `&EVHO`,
  `&EVSS`, `&STRS`, `&EDEV`; any other deck is a plain FDS deck.
- **Floor, FDS+Evac deck.** The main evacuation meshes (`EVAC_HUMANS=.TRUE.`,
  else all evacuation meshes), grouped by overlapping z. The lowest group is
  imported; `--floor MESH_ID` picks another. The floor level is the mesh
  mid-height minus `EVAC_Z_OFFSET` (default 1.0 m); the walking band is the
  evacuation mesh's own z range. `floors_not_imported` lists the other
  floors with their agent, `&EVAC`, `&EXIT` and `&DOOR` counts.
- **Floor, plain deck.** The floor level is the lowest mesh z (or
  `--floor-z`); the walking band is 0.1 to 1.8 m above it (or `--z-band`,
  absolute). Only meshes whose z range overlaps the band form the floor; a
  mesh wholly above or below it is left out with a warning. A horizontal
  `&OBST` over half the footprint, more than 2 m above the floor, is flagged
  as a possible upper floor.
- **Walkable area.** The union of the floor's mesh footprints (FDS+Evac:
  the main evacuation meshes only), whose edge is a wall, minus the `&OBST`
  footprints in the band, less the `&HOLE` footprints in the band. `MULT_ID`
  is expanded; `MESH_ID` is honoured; on an FDS+Evac floor, records with
  `EVACUATION=.FALSE.` are skipped. `&OBST` and `&HOLE` with `DEVC_ID` or
  `CTRL_ID` are taken as written. `&GEOM` is not represented; `&CATF`
  stops the import. Two touching evacuation meshes of one floor are joined,
  with a warning (FDS+Evac keeps their shared edge a wall).
- **Kept parts.** The parts of the walkable area that hold a spawn area are
  kept; with no spawn area, those that hold an exit; a part with an
  `--exit` is always kept; with neither, all parts are kept. Exits and spawn
  areas are then rebuilt on the kept polygon, so an `&EVAC` rectangle can
  split into numbered pieces. `--walkable FILE.wkt` is taken as given.
- **Exits, plain deck.** Every `SURF_ID='OPEN'` vent (`XB`, or an `MB`/`DB`
  face) on the outside of the mesh union that is vertical and meets the
  walking band; each gets an omni-directional sign (c = 3) at its centre. An
  `--exit` gets no sign. A vent wider than 5 m, or covering 80 % or more of
  its face, is flagged as a possible open boundary.
- **Exits, FDS+Evac deck.** The `&EXIT` and `&DOOR` lines of the floor. A
  `&DOOR` that leads off the floor (to a `&CORR` or `&STRS`) is imported as
  an exit. A `COUNT_ONLY` `&EXIT` is a counter, not an exit. The line stays
  where the deck puts it; `exits[].fds_evac_segment` reports where FDS+Evac
  would round it to its evacuation grid, without applying it.
- **Exit strip.** Every exit is a strip `--exit-depth` deep on the room
  side of its line, clipped to the walkable area. An exit is never moved; it
  is dropped, at error level, when its strip is empty or narrower than
  0.1 m.
- **Agents, plain deck.** Each kept part with an exit, minus the exit
  strips, is a spawn area; `--agents N` (or the placeholder of 100) is
  shared between them by area. A part without an exit gets no agents.
- **Agents, FDS+Evac deck.** `&EVAC` gives the spawn areas with
  `NUMBER_INITIAL_PERSONS`, `&PERS` the speed and pre-movement
  ([Coming from FDS+Evac](coming-from-fds-evac.md)); `--agents` is ignored.
  `&EVHO` is cut out of the spawn areas. `&ENTR` becomes flow spawning; an
  entry with `MAX_FLOW = 0` creates no agents. A point or line `&EVAC` is
  grown to a 0.6 m band across each zero-width axis, clipped to the walkable
  area (`distributions[].zero_width_expansion`).
- **Capacity.** A spawn area (groups sharing one polygon counted together,
  flow spawning left out) that asks for more agents than
  N<sub>max</sub> = max(1, ⌊0.5 · A / (π r²)⌋) makes the scenario not
  runnable, with A the area and r the largest agent radius, at least 0.1 m.
  The run applies the same estimate before it starts.
- **Settings.** `max_simulation_time` is `&TIME T_END`, or 300 s.
  `smoke_slice_height` is the floor level plus `HUMAN_SMOKE_HEIGHT` (the last
  `&PERS` value, else 1.6 m). Keys the deck does not set fall to the
  scenario defaults, listed per group in `distributions[].loader_defaults`.
- Fire surfaces (`HRRPUA`, `MLRPUA`) inside the walkable area are reported,
  not cut out.

| Constant | Value | Source |
|---|---|---|
| Walking band, plain deck | 0.1–1.8 m above the floor | assumption |
| Widening of a zero-thickness `&OBST` or `&HOLE` | 0.05 m each side | assumption |
| Free parts dropped and holes filled up to | 0.25 m² | assumption |
| Exit strip depth (`--exit-depth`) | 0.5 m | assumption |
| Minimum exit width | 0.1 m | assumption; below one agent diameter (0.4 m) |
| Band for a point or line `&EVAC` | 0.6 m | assumption |
| Placeholder agents, plain deck | 100 | flagged placeholder |
| Time limit without `T_END` | 300 s | assumption |
| Capacity packing | 0.5, r ≥ 0.1 m | the run's own estimate |
| Spawn density flag | 4 /m² | flag threshold, unsourced |
| Wide-opening flag | > 5 m, or ≥ 80 % of the face | assumption |
| `HUMAN_SMOKE_HEIGHT` default | 1.6 m | FDS+Evac guide §8.7 |

#### Messages and what to do

| Message (start) | Status | Cause | Fix |
|---|---|---|---|
| `no exit found: add exits in JuPedSim Web or with --exit …` | 3 | A plain deck without an outside `OPEN` vent in the band. | `--exit x0,y0,x1,y1[,ior]`; give `ior` when the room side is ambiguous. |
| `no exit found (every &EXIT is narrower than the minimum exit width 0.1 m: …` | 3 | The deck uses its exits only as flow-field targets, which pyFDS-Evac does not model. | None; draw real exits with `--exit` only if the building has them. |
| `no agents to place` | 3 | A plain deck with no exit, or an FDS+Evac floor with no `&EVAC`. | Plain deck: add exits, `--agents`. FDS+Evac deck: read `floors_not_imported[].agents`, and use `--floor MESH_ID` only when another floor has agents. When every floor has 0, the agents enter only through `&ENTR` fed by stairs or doors, and the deck is out of scope. |
| `spawn area X (A m2) holds about N agents of radius r m, but M are requested: …` | 3 | Capacity, see above. | Plain deck: a smaller `--agents` or a larger area. FDS+Evac deck: a lower `NUMBER_INITIAL_PERSONS` or a larger `&EVAC` area, in a copy of the deck. |
| Error item `exit dropped: its strip on the room side is empty; the line is D m from the walkable area` | 3, runnable | The exit is not next to the kept walkable area. | Check the floor and the band (`--z-band`), or pass `--exit`. The run works without that exit. |
| Error item `exit dropped: its strip on the room side is W m wide, below the minimum exit width of 0.1 m` | 3, runnable | A slot narrower than 0.1 m. | Widen the exit in a copy of the deck, or pass `--exit`. |
| `… holds a config.json that the importer did not write …` | 1 | `-o` points at an authored scenario. | Another `-o`, or `--force`. |
| `no &MESH reaches the walking band z = LO..HI m; …` | 1 | Wrong `--floor-z` or `--z-band`. | As the message says. |
| `--floor 'X' names no evacuation mesh; known: […]` | 1 | A wrong `--floor`. | Use a listed id. |
| `--exit (…): no walkable strip next to the line` | 1 | The `--exit` line is not on the walkable boundary. | Put the line on a wall or a mesh edge next to walkable space. |
| `argument --exit: need x0,y0,x1,y1[,ior]`, `the line must be parallel to x or y` | 1 | A malformed `--exit`. | Four or five numbers, the line parallel to x or y. |
| A parser error, such as `&RADI (line 21): no closing '/' before &DUMP on line 23` | 1 | Deck syntax; also `&CATF`, an unknown `MULT_ID`, a malformed `XB`. | Fix the deck. |
| `the walkable area (…) is empty or invalid`, `the deck has no &MESH with XB` | 1 | A degenerate deck or WKT. | Check the deck, or pass `--walkable`. |
| `cannot read the walkable WKT: …` | 1 | A bad `--walkable` file. | Fix the WKT. |

#### `import_report.json`

| Key | What it holds |
|---|---|
| `deck`, `chid`, `kind` | the deck path, its `CHID`, and `legacy` (FDS+Evac) or `modern` (plain FDS) |
| `floor` | `id`, `meshes`, `z_floor` and `z_band` of the imported floor |
| `floors_not_imported` | the other floors of an FDS+Evac deck, with their agent, `&EVAC`, `&EXIT` and `&DOOR` counts |
| `walkable` | `source` (`derived:deck`, `derived:evac-mesh` or `user`), `area_m2`, `components`, `holes`, `kept_by` (`single`, `spawn`, `exit` or `all`), `components_dropped` (area, bounds, reason), `diagnostics` |
| `counts` | per namelist, the number of records supported (S), approximated (A), dropped (D) and cosmetic (C) |
| `items` | one entry per record: `status` (S, A, D, C), `level` (info, warning, error), `group`, `id`, deck `line`, `message` |
| `exits` | per exit: `id`, `source` (`X1` vent, `X3` `--exit`, `&EXIT`, `&DOOR`), `segment`, `strip_area_m2`, `sign`, `fds_evac_segment`, and `open_from_s`, `closed_after_s`, `role` |
| `distributions` | per spawn area: `number`, `area_m2`, `density_per_m2`, `parameters_written`, `loader_defaults`, `placeholder`, `zero_width_expansion`, `source` |
| `recommendations` | `smoke_slice_height`; `slices` (one entry per item of the check: `status`, `required`, `z_requested`, `nearest_pbz`, `orientation_found`, `ok`, `fix`, `message`); `slice_check_ok`; `coverage` (walkable area and exits outside the fire meshes); `fds_meshes`, `fds_output_found`, `fds_dir`, `run_command` |
| `runnable`, `not_runnable_reasons` | whether `pyfds-evac --scenario` can run the folder, and why not |

#### Check a deck before running FDS — `pyfds-evac init --check`

```
pyfds-evac init DECK.fds --check [--floor MESH_ID] [--floor-z Z] [--z-band LO HI] \
    [--smoke-slice-height Z]
```

Reads the deck only, before FDS runs, and writes nothing. It chooses the
floor as `init` does and checks, at the smoke slice height `init` would
write (the floor plus the last `HUMAN_SMOKE_HEIGHT`, else 1.6 m;
`--smoke-slice-height Z` checks another absolute z), the FDS output the run
reads. It uses the run's rule: a horizontal slice (`PBZ`, or `XB` with equal
z and unequal x and y, as fdsreader reads it), the one nearest the height, the first declared on a tie; slices with
`EVACUATION=.TRUE.` do not count. Each line prints the requested and the
chosen z, and the fix as a deck line.

| Item | Fails the check (✗) | Reported only |
|---|---|---|
| `QUANTITY='EXTINCTION COEFFICIENT'`, no `SPEC_ID` or `SPEC_ID='SOOT'` (smoke speed, sign legibility) | none, or vertical only | nearest z more than 0.5 m away (`!`); `QUANTITY='EXTINCTION'` is a different quantity |
| `QUANTITY='VOLUME FRACTION'` with `SPEC_ID` `'CARBON MONOXIDE'`, `'CARBON DIOXIDE'`, `'OXYGEN'` (FED needs all three) | any of them none, or vertical only | z more than 0.5 m away |
| `&TIME T_END` | absent: FDS stops at its default of 1 s while `init` writes `max_simulation_time` 300 s | its value |
| HCN, NO, NO2, HCl, HBr, HF, SO2, acrolein, formaldehyde | | those present, with z |
| `TEMPERATURE`, `INTEGRATED INTENSITY` (heat FED, opt-in) | | their z; `!` when an `INTEGRATED INTENSITY` slice has no `TEMPERATURE` slice at its z |
| `DT_SLCF` | | `&DUMP DT_SLCF`, else (T_END − T_BEGIN)/NFRAMES; `!` when coarser than 1 s, the run's smoke update interval |
| `&REAC SOOT_YIELD`, `CO_YIELD` | | `!` when a simple-chemistry deck declares the slice but the yield is absent or 0 |

The z is the deck's: FDS moves a slice to the nearest grid plane, up to half
a cell away. `-o`, `--walkable`, `--exit`, `--agents`, `--exit-depth`,
`--force`, `--no-fds` and `-v` shape the written scenario and are refused
with `--check`.

| Status | Meaning |
|---|---|
| 0 | no ✗: the deck has every required item |
| 3 | at least one ✗: the deck is read, but not ready for a pyFDS-Evac run |
| 1 | the deck cannot be read, the floor cannot be chosen, or an argument error |

A plain `pyfds-evac init` runs the same check before it derives the walkable
area, prints its ✓, ✗ and `!` lines, and records every item under
`recommendations.slices` in `import_report.json`, with
`recommendations.slice_check_ok`. The check never changes the written files
or the exit status of `init`.

### Walkable area from FDS obstructions — `generate_walkable_from_fds.py`

Writes only the walkable area that `pyfds-evac init` derives (above) as
WKT, the same polygon as its `geometry.wkt`.

```
uv run python scripts/generate_walkable_from_fds.py DECK.fds -o out.wkt \
    [--z-band 0.1 1.8]
```

| Flag | Purpose |
|------|---------|
| `deck` (positional) | FDS input file. |
| `-o/--out` (required) | Output WKT path. |
| `--z-band LO HI` | Absolute height band an upright occupant occupies (default: the evacuation mesh slab, or 0.1 to 1.8 m above the lowest mesh). |

## Paper figures

These are generators for figures in `../pyFDS-Evac-paper/`. They don't
need a simulation run.

| Script | Figure |
|--------|--------|
| `generate_tenability_curves.py` | 3-panel Frantzich + FIC + combined heatmap (`--output PATH`). |
| `generate_fed_guide_plot.py` | FED guide reference curves. |
| `generate_iso_table21_sweep.py` / `generate_iso_table22_stationary_plot.py` | ISO 20414:2020 Test 18 (Table 21) sweep over extinction and walking speed / Test 19 (Table 22) stationary FED check. |
| `generate_routing_diagram.py` | Routing / cognitive-map diagram. |
| `generate_smoke_density_speed_plot.py` | Smoke-speed reference curve. |
| `generate_exit_visibility_map.py` | Which exit a `discovery` agent would take, gridded by position, for the two `assets/exit_visibility_alpha` configs (`-o OUT.png`). |
| `generate_cognitive_map_states.py` | Known/legible/remembered exit states probed along `assets/cognitive_map_memory`'s corridor (`-o OUT.png`). |
| `generate_smoke_weight_sweep.py` | How `w_smoke` reprices the T-junction's two routes, uniform vs. asymmetric smoke (`-o OUT.png`). |

## Calibration sweeps

### Route-cost queue weight — `sweep_queue_weight.py`

Sweeps `RouteCostConfig`'s queue weight against Fahy Table 2's front-door
share. Writes one scenario bundle per `(w_queue, seed)`, runs each with
`run.py`, and scores it against `assets/station_fahy/validate.py`'s
`observed_matrix`. Unlike the paper-figure scripts above, this drives real
simulation runs (in parallel processes), so it takes minutes, not seconds.

```
uv run python scripts/sweep_queue_weight.py \
    [--weights 0.0 0.03 0.1 ...] [--seeds 420 421 422] \
    [--jobs 4] [--out results/queue_weight_sweep] [--reuse-existing]
```

| Flag | Purpose |
|------|---------|
| `--weights F [F ...]` | `w_queue` values to sweep (default: the grid in `docs/routing.md`). |
| `--seeds N [N ...]` | Seeds per weight (default `420 421 422`). |
| `--jobs N` | Parallel worker processes (default 4). |
| `--out DIR` | Output directory for `sweep.csv`, `summary.csv`, `sweep.png`. |
| `--reuse-existing` | Score an existing `run.sqlite` instead of rerunning it, if its deck/seed digest still matches. |

### Station agreement statistic — `assets/station_fahy/validate.py`

Scores one or more Station runs against Fahy, Proulx & Flynn (2011) Table 2.
It prints the origin-to-door table (door users only, per row), then the
statistics of the Station validation study over the agents of all runs
pooled:

- **T1**, the front-door share of door users over the placed rows, against
  Fahy's 117/229 = 51.1 %, with the signed bias. The share with the 22
  unplaceable survivors (127/240 = 52.9 %) is printed as T1′, not a gate.
- **W**, the door-user-weighted total variation distance: per row
  ½ Σ |model share − Fahy share| over the four doors, averaged with Fahy's
  door users as weights. The seven rows with at least 10 door users are
  scored alone; the other five (34 door users) are pooled into one row, and
  the model agents from those areas with them. A scored row without a model
  door user counts as distance 1 (conservative); each line that reports W
  for a `--t-jam` split also prints how many scored rows have no model door
  user. The `--t-jam` split is descriptive only, not a gate.
- The **noise floor** of W: Fahy resampled multinomially against itself,
  each scored row (and the pooled row) as one multinomial (median 0.079,
  p95 0.109 at the default 20,000 draws).
- With several runs, the per-run min / median / max of T1 and W.

Agents that never reach a door are counted separately and left out of the
shares. Agents still on the grid at the horizon are **censored**: left out
of T1, W and the same-agent set even when they stand within `--reach` of a
door, and counted on their own line. An agent is censored when its last
frame is the run's last frame and that frame lies within one output
interval of the horizon; a run that empties earlier censors nobody, and a
run that ends after the horizon stops with an error. The origin-to-door
table above the statistics leaves censored agents out too.

```
uv run python assets/station_fahy/validate.py RUN.sqlite [RUN.sqlite ...] \
    --config assets/station_fahy/config.json \
    [--t-jam 86] [--against OTHER.sqlite ...]
```

| Flag | Purpose |
|------|---------|
| `--config PATH` | The scenario's `config.json`: spawn areas (`fahy_row`) and exits. |
| `--reach M` | Distance from a door polygon at which a last position counts as using it (default 2.0 m). |
| `--horizon S` | The horizon for censoring (default: `max_simulation_time` of `--config`). |
| `--t-jam S` | Also print T1 and W for agents whose last recorded frame is before `S` and at or after it. The split is descriptive only, not a gate. |
| `--against RUN [RUN ...]` | Runs of another arm, paired in order with the scored runs (one pair per seed). Prints W(run) − W(other) per pair on the **same agents**, those that reached a door, uncensored, in both, and in how many pairs the scored run is lower. Both runs of a pair must spawn the same agents (ids, areas, start positions), or it stops with an error. |
| `--noise-draws N` | Resamples for the noise floor (default 20,000). |
| `--noise-seed N` | Seed of the resampling (default 0). |

## One-shot driver — `scripts/run_and_plot.sh`

Runs one simulation and produces the full plot set into a results
directory.

```bash
./scripts/run_and_plot.sh assets/t_junction/config.json "$FDS" results/demo
```

Arguments: `<scenario> <fds-dir> <results-dir>`. `<fds-dir>` must hold a
finished FDS run (the `.smv` file); `$FDS` stands for such a directory, for
example the output of `assets/t_junction/t_junction.fds`. The script calls
`run.py` with all diagnostic outputs enabled and then invokes each
plotting script against the resulting CSVs / SQLite. It writes the vismap
cache into `<fds-dir>/vismap_cache.npz`, so do not point it at a tracked
directory under `assets/`
([#313](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/313)).
