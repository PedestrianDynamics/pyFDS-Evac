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
| `--enable-rerouting` | Let agents re-evaluate exits during the run. |
| `--reroute-interval S` | Seconds between per-agent reevaluations (default 10). |
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

### Smokeview export

| Flag | Purpose |
|------|---------|
| `--smv-export` | Write `<CHID>_agents.prt5` + patch `<CHID>.smv` and drop a `<CHID>.svo` with our custom AVATARDEF. Requires `--fds-dir`. See [docs/smv-avatars.md](smv-avatars.md) for the mechanism. |
| `--smv-particle-z M` | Agent height in metres for the particle export (default 0.0, so avatars stand on the floor). |
| `--smv-class-id LABEL` | `CLASS_OF_PARTICLES` label (default `Human`). Bound to an AVATARDEF via the PROP block we write. |
| `--smv-avatar-style {human,arrow,sphere}` | Which AVATARDEF we emit to `<CHID>.svo`. `human` (default) is a detailed humanoid. `arrow` is a body sphere plus a red directional marker — useful to sanity-check whether per-particle rotation is working. `sphere` is a single plain sphere for position-only rendering. |
| `--smv-with-azimuth` | Write `AZIMUTH = atan2(ori_y, ori_x) mod 360` (deg) as a PRT5 quantity column. **Off by default**: per-particle avatar rotation is not supported by current Smokeview ([firemodels/smv#2597](https://github.com/firemodels/smv/issues/2597)), and writing the quantity also triggers a separate `CreatePartBoundFile` bug that sticks playback on frame 0. Enable only if you want the AZIMUTH colorbar entry and accept broken playback. See `docs/smv-avatars.md` for the full trace. |

### Typical invocations

```bash
# Bare JuPedSim run, no smoke coupling
uv run python run.py --scenario assets/demo/config.json

# Smoke-coupled run with all diagnostic outputs
uv run python run.py --scenario assets/demo/config.json \
    --fds-dir fds_data/demo \
    --output-sqlite demo3.sqlite \
    --output-smoke-history smoke.csv \
    --output-fed-history fed.csv \
    --output-route-history routes.csv \
    --output-route-cost-history route_costs.csv \
    --enable-rerouting \
    --vis-cache fds_data/demo/vismap_cache.pkl
```

## Inspecting an FDS case

`scripts/inspect_fds.py` summarises what quantities FDS wrote and whether
they are within tenability-relevant ranges.

```bash
uv run python scripts/inspect_fds.py fds_data/demo --plot --height 2.0
```

## Probing FED without running a simulation

`scripts/probe_fed.py` integrates FED at fixed `(x, y)` points directly
from the FDS output. Useful as a sanity check ("if an agent stood still
here, would it be incapacitated?").

```bash
uv run python scripts/probe_fed.py --fds-dir fds_data/demo \
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

Positional CLI (no flags). `config.json` is used to draw exit polygons;
`route_costs.csv` colours each agent by its last-chosen exit.

```
uv run python scripts/plot_trajectories.py <traj.sqlite> [config.json] [route_costs.csv] [out.png]
```

### Route cost curves — `plot_route_costs.py`

Mean composite cost per exit over time.

```
uv run python scripts/plot_route_costs.py route_costs.csv [routes.csv]
```

### Exit choice distribution — `plot_exit_choice.py`

Time series and histogram of exit targeting.

```
uv run python scripts/plot_exit_choice.py route_costs.csv [routes.csv [config.json]]
```

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

## One-shot driver — `scripts/run_and_plot.sh`

Runs one simulation and produces the full plot set into a results
directory.

```bash
./scripts/run_and_plot.sh assets/demo/config.json fds_data/demo results/demo
```

Arguments: `<scenario> <fds-dir> <results-dir>`. The script calls
`run.py` with all diagnostic outputs enabled and then invokes each
plotting script against the resulting CSVs / SQLite.
