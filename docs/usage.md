# Usage: running simulations and producing plots

This page catalogues every user-facing script in the repository: how to run
an evacuation simulation, what artefacts it writes, and which plotting
script consumes each artefact. All commands assume the project venv
(`uv run ...`).

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
| `--seed N` | Override scenario seed. |
| `--print-summary` | Print the loaded scenario summary before running. |
| `--output-sqlite PATH` | Copy the JuPedSim trajectory SQLite here. When FED is computed, also writes an optional `agent_scalars(frame, id, fed, speed)` side table (base JuPedSim schema untouched) so [fds-viewer](https://github.com/PedestrianDynamics/fds-viewer) can colour agents by FED or speed. |
| `--cleanup` | Delete the temp SQLite after the run. |
| `--export-app-bundle DIR` | Write `config.json` and `geometry.wkt` for the app. |
| `--export-only` | Export the bundle without running the simulation. |

### FDS coupling (smoke / FED / visibility)

Your FDS case has to dump specific slices before any of this works. See
[fds-case-requirements.md](fds-case-requirements.md) for the deck lines to add
and two failure modes (FED silently disabled, wrong slice height) that stay
silent unless you check the warning log.

| Flag | Purpose |
|------|---------|
| `--fds-dir DIR` | FDS result directory driving smoke-speed and FED. |
| `--constant-extinction K` | Use a constant `K` [1/m] instead of FDS. |
| `--smoke-update-interval S` | Seconds between smoke-speed refreshes. |
| `--smoke-slice-height M` | FDS slice height (m) for extinction sampling. |
| `--output-smoke-history CSV` | Write `(t, agent, K, v, factor)` CSV. |
| `--output-fed-history CSV` | Write per-agent per-sample FED+species CSV. |
| `--inspect-fds` | Inspect FDS quantities (like `scripts/inspect_fds.py`) and exit. |

### Dynamic rerouting (smoke-aware route choice)

| Flag | Purpose |
|------|---------|
| `--enable-rerouting` / `--no-enable-rerouting` | Let agents re-evaluate exits during the run (on by default). |
| `--reroute-interval S` | Seconds between per-agent reevaluations (default 1). |
| `--output-route-history CSV` | Write route switches. |
| `--output-route-cost-history CSV` | Ranked route cost snapshots. |
| `--vis-cache PKL` | Vismap pickle cache; gates routes by visibility. Requires `--fds-dir`. |

### Tenability (FIC slowdown + FED incapacitation)

A FED model is instantiated automatically when `--fds-dir` points at
an FDS case that exposes the ISO 13571 species (CO, CO₂, O₂ at
minimum — HCN, NO/NO₂, and irritants are used if present). When that
happens, the Purser FIC slowdown and the `FED ≥ 1` incapacitation gate
are on by default. Without `--fds-dir` (or with a case missing the
required species) no FED is computed and these flags have no effect.

| Flag | Purpose |
|------|---------|
| `--disable-tenability` | Turn both rules off. |
| `--fic-alpha F` | Slope of `v/v₀ = max(μ, 1 − α·FIC)` (default 0.7). |
| `--fic-min-factor F` | Floor `μ` (default 0.3). |
| `--fed-threshold F` | FED at which agents are declared incapacitated (default 1.0). |

### Agent visualisation

Agent 3-D visualisation is handled by
[fds-viewer](https://github.com/PedestrianDynamics/fds-viewer), which
loads the JuPedSim trajectory SQLite written by `--output-sqlite` (and
its optional `agent_scalars` table for FED/speed colouring).

### Typical invocations

```bash
# Bare JuPedSim run, no smoke coupling
uv run python run.py --scenario assets/t_junction/config.json

# Smoke-coupled run with all diagnostic outputs
uv run python run.py --scenario assets/t_junction/config.json \
    --fds-dir assets/t_junction \
    --output-sqlite demo3.sqlite \
    --output-smoke-history smoke.csv \
    --output-fed-history fed.csv \
    --output-route-history routes.csv \
    --output-route-cost-history route_costs.csv \
    --enable-rerouting \
    --vis-cache assets/t_junction/vismap_cache.npz
```

## Inspecting an FDS case

`scripts/inspect_fds.py` summarises what quantities FDS wrote and whether
they are within tenability-relevant ranges.

```bash
uv run python scripts/inspect_fds.py assets/t_junction --plot --height 2.0
```

## Probing FED without running a simulation

`scripts/probe_fed.py` integrates FED at fixed `(x, y)` points directly
from the FDS output. Useful as a sanity check ("if an agent stood still
here, would it be incapacitated?").

```bash
uv run python scripts/probe_fed.py --fds-dir assets/t_junction \
    --point 17,12 --point 20,12 \
    --output probe.csv --plot probe.png
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
| *(default)* | Spaghetti plot: one cumulative-FED line per agent. |
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
FED CSV. The walkable area is drawn as backdrop via pedpy.

| Flag | Purpose |
|------|---------|
| `--sqlite PATH` | JuPedSim SQLite; backdrop via `pedpy.load_walkable_area_from_jupedsim_sqlite`. |
| `--agents 7,8,43` | Comma-separated agent ids (default: all). |
| `--vmax F` | Upper bound for the colormap (default: data max). |
| `--linewidth F` | Polyline width (default 0.5). |
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
| `--config` (required) | Exit polygons, and the colour key. |
| `-o/--out` (required) | Output PNG. |
| `--route-history` | `run.py --output-route-history` CSV. Colours each path by the exit targeted **at that moment** and marks every switch with a dot. Without it paths are coloured by the exit finally reached, which hides mid-run decisions entirely. |
| `--geometry` | Walkable-area WKT; defaults to `geometry.wkt` beside the config. |
| `--reach` | Metres from an exit polygon that count as having reached it (default 1.5). Agents that finish elsewhere are drawn grey and counted separately. |

### Route cost curves — `plot_route_costs.py`

Mean composite cost per exit over time.

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
| `generate_iso_table21_sweep.py` / `generate_iso_table22_stationary_plot.py` | ISO 13571 sensitivity sweeps. |
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
./scripts/run_and_plot.sh assets/t_junction/config.json assets/t_junction results/demo
```

Arguments: `<scenario> <fds-dir> <results-dir>`. The script calls
`run.py` with all diagnostic outputs enabled and then invokes each
plotting script against the resulting CSVs / SQLite.
