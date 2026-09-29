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

## Running a simulation — `run.py`

`run.py` is the single entry point for an evacuation run. It loads a
JSON-first JuPedSim scenario, optionally couples it to an FDS case for
smoke-speed / FED / visibility, and writes CSV/SQLite artefacts for
post-processing.

```
uv run python run.py --scenario <scenario.json|.zip|dir> [options]
```

### Scenario selection and export

| Flag | Purpose |
|------|---------|
| `--scenario PATH` | Scenario JSON, ZIP, or directory (required). |
| `--seed N` | Override the scenario's `baseSeed` (42 when the scenario sets none). |
| `--print-summary` | Print the loaded scenario summary before running. |
| `--output-sqlite PATH` | Copy the JuPedSim trajectory SQLite here, with the run manifest beside it as `<stem>.manifest.json`. When FED is computed, also writes an optional `agent_scalars(frame, id, fed, heat_fed, speed)` side table (base JuPedSim schema untouched) so [fds-viewer](https://github.com/PedestrianDynamics/fds-viewer) can colour agents by FED or speed. |
| `--cleanup` | Delete the temp SQLite after the run. |
| `--export-app-bundle DIR` | Write `config.json` and `geometry.wkt` for the app. |
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
| `--constant-extinction K` | none | Use a constant `K` [1/m] for walking speed instead of the FDS extinction slice. Speed only: FED, heat FED and sign legibility still read `--fds-dir` when it is given. |
| `--smoke-update-interval S` | 1.0 s | Seconds between smoke-speed updates. The same interval is the integration step of the gas FED and heat FED, and the row spacing of the smoke and FED histories. |
| `--smoke-slice-height M` | 1.6 m | Height of the horizontal slices that are read ([FDS+Evac](https://github.com/firemodels/fds/tree/c9da70d7a/Source) `HUMAN_SMOKE_HEIGHT`; 2.0 was the previous default). One height for speed, gas FED, heat FED and sign legibility: the nearest horizontal slice is used, with a warning only when it is more than 0.5 m away. See [FDS slice sampling](fds-sampling.md). |
| `--output-smoke-history CSV` | none | Write the smoke history; columns on [Outputs](outputs.md#smoke-history). |
| `--output-fed-history CSV` | none | Write the FED history; columns on [Outputs](outputs.md#fed-history). Not written when neither FED track runs. |
| `--inspect-fds` | off | List the FDS quantities of `--fds-dir` as JSON and exit. Needs `--fds-dir`. |

### Dynamic rerouting (smoke-aware route choice)

| Flag | Default | Purpose |
|------|---------|---------|
| `--enable-rerouting` / `--no-enable-rerouting` | on | Let agents re-evaluate exits during the run. |
| `--reroute-interval S` | 1.0 s | Seconds between per-agent reevaluations. With a smoke-aware visibility model it is also the time step at which sign legibility is computed. |
| `--output-route-history CSV` | none | Write route switches; see [Outputs](outputs.md#route-history). |
| `--output-route-cost-history CSV` | none | Write ranked route cost snapshots; see [Outputs](outputs.md#route-cost-history). |
| `--vis-cache NPZ` | none | Path to a vismap `.npz` cache — written if missing, loaded if present. Requires rerouting to be enabled (the run aborts otherwise). With `--fds-dir` it caches the smoke-aware vismap; without one, the clear-air grid. |
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

All flags in this table need `--enable-heat-fed`; without it they are ignored
and the run logs a warning for each one set. The laws, parameters and their
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
  walking speed only.

### Python API and command line

`run.py` and the web GUI build their models with `build_run_kwargs`.
`run_scenario()` called directly builds nothing you do not pass, so the same
scenario can behave differently:

| What | `run.py` | `run_scenario()` without that argument |
|------|----------|----------------------------------------|
| Rerouting | on, every 1 s (`--reroute-interval`) | off; `RerouteConfig()` defaults to 10 s |
| Smoke speed | from `--fds-dir` | none |
| Gas FED, heat FED | from `--fds-dir` (heat with `--enable-heat-fed`) | none |
| Incapacitation | `TenabilityConfig` whenever a FED track runs | none: a `fed_model` without `tenability_config` accumulates dose but never incapacitates |
| Visibility model | built for discovery agents, `--vis-cache` or `--clear-air-visibility` | none |

For a run identical to the command line, parse the same flags and build the
keywords the same way:

```python
import run  # run.py at the repository root
from pyfds_evac import build_run_kwargs, load_scenario, run_scenario

args = ["--scenario", "assets/iso_table22_coupled/config_a.json",
        "--fds-dir", "assets/iso_table22_coupled/fds/a"]
opts = run._build_parser().parse_args(args)
scenario = load_scenario(opts.scenario)
result = run_scenario(scenario, **build_run_kwargs(scenario, opts))
print(f"FED max: {result.metrics['fed_max']:.3f}")
result.cleanup()
```

Run it from the repository root with `PYTHONPATH=. uv run python script.py`,
so that `run.py` can be imported. It prints `FED max: 1.170`.

[A crowd in a real fire](first-fds-case.md) does this end to end.

### Agent visualisation

Agent 3-D visualisation is handled by
[fds-viewer](https://github.com/PedestrianDynamics/fds-viewer), which
loads the JuPedSim trajectory SQLite written by `--output-sqlite` (and
its optional `agent_scalars` table for FED/speed colouring).

### Typical invocations

```bash
# Bare JuPedSim run, no smoke coupling
uv run python run.py --scenario assets/t_junction/config.json --cleanup
```

```text
Simulation stopped after 300.00 s (142/150 evacuated, 8 remaining).
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
Simulation stopped after 1150.00 s (0/1 evacuated, 1 remaining).
Route switches: 0
Route cost samples: 1149
```

The occupant of this ISO 20414 Test 19 case never leaves; it is incapacitated
at 982 s. Rerouting is on by default, so `--enable-rerouting` is not needed.
The tracked FDS output of the T-junction fire is not in the repository; run
`assets/t_junction/t_junction.fds` with FDS, or see
[A crowd in a real fire](first-fds-case.md).

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
| `--cell-size M` | Visibility grid resolution in metres (default 0.5). |
| `--work DIR` | Working directory for the deck variant and run SQLite (default `results/cognitive_map_movie`). |

## Deriving inputs from an FDS deck

### Walkable area from FDS obstructions — `generate_walkable_from_fds.py`

Subtracts an FDS deck's blocking `&OBST` records from its mesh footprint and
writes the interior as WKT for JuPedSim. See the script's module docstring
for the `XB` axis-pairing pitfall, zero-thickness obstructions, and how the
CAD layer name decides what blocks.

```
uv run python scripts/generate_walkable_from_fds.py DECK.fds -o out.wkt \
    [--z-band 0.1 1.8] [--min-hole 0.25] [--plot out.png] [--report]
```

| Flag | Purpose |
|------|---------|
| `deck` (positional) | FDS input file. |
| `-o/--out` (required) | Output WKT path. |
| `--z-band LO HI` | Height band an upright occupant occupies (default 0.1 1.8). |
| `--half-cell M` | Half the grid spacing; widens zero-thickness obstructions (default 0.05). |
| `--min-hole M2` | Interior rings smaller than this are grid noise and get filled (default 0.25). |
| `--plot PNG` | Also render the walkable polygon. |
| `--report` | Print the per-layer blocked footprint and blocking verdict. |

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
cache into `<fds-dir>/vismap_cache.pkl`, so do not point it at a tracked
directory under `assets/`
([#313](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/313)). The usage line in the script itself still names
`assets/t_junction`, which has no FDS output
([#312](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/312)).
