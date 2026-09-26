[![code quality](https://github.com/PedestrianDynamics/pyFDS-Evac/actions/workflows/code-quality.yml/badge.svg)](https://github.com/PedestrianDynamics/pyFDS-Evac/actions/workflows/code-quality.yml)
[![tests](https://github.com/PedestrianDynamics/pyFDS-Evac/actions/workflows/tests.yml/badge.svg)](https://github.com/PedestrianDynamics/pyFDS-Evac/actions/workflows/tests.yml)

# pyFDS-Evac

Fire Dynamics Simulator (FDS) coupled evacuation modeling with smoke-speed reduction, toxic gas dose (FED), and dynamic route rerouting.

The project includes:

- Smoke-speed model (visibility/extinction-based speed reduction)
- Purser FED model as in the FDS+Evac guide (toxic gas dose accumulation, up to 12 species)
- Convective heat FED (ISO TS 13571 eq. 5), accumulated as a dose independent
  of the gas track -- an agent is incapacitated when either crosses its own
  threshold, because thermal injury and asphyxiation are different mechanisms
  and the standard does not sum them. Radiant heat is not modelled, and heat
  does not enter route choice. It also does not slow an agent down: unlike
  smoke and irritants, heat has no effect at all until the dose is reached, at
  which point the agent stops.
- Dynamic smoke-based route rerouting, with an optional exit-queue term
  (off by default)
- Smoke-gated exit availability, and sign visibility for what agents learn (fdsvismap integration)
- Per-agent cognitive maps with `full` and `discovery` familiarity tiers
- JuPedSim scenario loading and simulation

## Documentation

The model descriptions, usage and verification live on the documentation site:
**<https://pedestriandynamics.org/pyFDS-Evac/>**

- [Usage](https://pedestriandynamics.org/pyFDS-Evac/docs/usage/): CLI flags, post-processing scripts, run-and-plot driver
- [Smoke-speed model](https://pedestriandynamics.org/pyFDS-Evac/models/smoke-speed/), including FDS data access through `fdsreader`
- [Fractional effective dose](https://pedestriandynamics.org/pyFDS-Evac/models/fed/), including heat dose and irritant slowdown
- [Dynamic route rerouting](https://pedestriandynamics.org/pyFDS-Evac/models/routing/)
- [Visibility-aware routing and cognitive maps](https://pedestriandynamics.org/pyFDS-Evac/models/visibility/)
- [Verification suite](https://pedestriandynamics.org/pyFDS-Evac/models/verification/)

## Talks

- **A Modular Workflow for Visibility-Aware Evacuation Modelling**, Visibility
  Seminar 2026, University of Wuppertal, 25 September 2026:
  [slides](https://pedestriandynamics.org/pyFDS-Evac/talks/visibility-seminar-2026/),
  [PDF](https://pedestriandynamics.org/pyFDS-Evac/talks/pyFDS-Evac_visibility_seminar_2026.pdf)

## Installation

This project uses [uv](https://github.com/astral-sh/uv) for dependency management.

```bash
uv sync
```

## Development

Activate the virtual environment:

```bash
uv shell
```

Run a JSON-first scenario with the CLI runner:

```bash
uv run run.py --scenario assets/ISO-table21 --cleanup
```

See [docs/usage.md](docs/usage.md) for the full catalogue of CLI flags,
post-processing scripts, and the `scripts/run_and_plot.sh` driver that
runs a simulation and produces every plot in one go.

**Bringing your own FDS case?** Read
[docs/fds-case-requirements.md](docs/fds-case-requirements.md) first. pyFDS-Evac
does not run FDS, it samples the output of a finished run, and your deck has to
dump specific slices for that to work. That page also covers the `&REAC` yields
those slices depend on, and two failure modes that stay silent otherwise.

## Web GUI

A [FastHTML](https://fastht.ml/) web GUI 
exposes the same model behind a form: pick a scenario, set any `run.py` flag
(the `fds dir` field has a folder browser), run it, watch live progress, and
explore the results.

Two ways to view a finished run's trajectories:

- **Interactive [Plotly](https://plotly.com/python/) charts** — cumulative
  FED, smoke, and route cost over time.
- **Canvas trajectory replay** (`pyfds_evac/webapp/trajviz.py`) — agents
  interpolated smoothly between downsampled trajectory samples, coloured by
  cumulative FED (safe → alert → critical → severe) or by assigned exit, with
  play/pause, a scrub bar, and ¼×–4× playback speed. When the run has an
  `fds_dir`, the FDS extinction slice is drawn as a smoke layer underneath
  the agents (toggleable), sampled via `fdsreader`'s multi-mesh
  `to_global()` and clipped to the walkable polygon.

Install the optional GUI dependencies and launch:

```bash
uv sync --extra gui
uv run app.py
```

Then open <http://localhost:5001>. The GUI calls the same
`run_scenario()` as the CLI (via the shared
`pyfds_evac.core.run_config.build_run_kwargs` option builder), so a run
configured in the browser is identical to the equivalent `run.py`
invocation. Runs execute on a background thread and stream progress over
Server-Sent Events; one run is active at a time.

## Agent speed and pre-movement

**Smoke-speed parameters are library-level fields, not scenario configuration.** `speed_law`,
`alpha`, `beta`, `min_speed_factor` and `visibility_factor_c` are constructed
with their defaults by `run_config.py` and are reachable from no CLI flag and
no scenario JSON key, so a configured run always uses the Lund law with
`alpha=0.706`, `beta=-0.057`, `min_speed_factor=0.1`. The `routing` block
does accept keys named `alpha`, `beta` and `min_speed_factor` with the same
defaults, but those parameterise the speed factor used to *estimate travel
time when pricing a route* — setting them changes what routes cost, not how
fast agents walk. The same split applies to speed itself: `routing.
base_speed_m_per_s` (1.3 m/s) is a route-pricing constant, while an agent's
own `desired_speed` defaults to 1.2 m/s (see below).

Each distribution group sets the attributes an agent starts with:

| Key | Default | Effect |
|-----|---------|--------|
| `desired_speed` (`v0`) | `1.2` m/s (`0.8` for `SocialForceModel`) | Clear-air walking speed. Every smoke, irritant and zone factor multiplies *this*, not `routing.base_speed_m_per_s`. |
| `desired_speed_distribution` | `"constant"` | `"gaussian"` draws per agent instead. |
| `desired_speed_std` | none | Spread when Gaussian. Draws are clipped to `[0.1, 5.0]` m/s. |
| `radius` (`radius_std`) | `0.2` m | Body radius: packing, spawn spacing, and the `radius + 0.5` m arrival distance at a stage. Clipped to `[0.1, 1.0]` m. |
| `use_premovement` | `false` | Delay before the agent starts moving. |
| `premovement_distribution` | `"gamma"` | `gamma` / `lognormal` / `weibull` / `uniform`; `premovement_param_a`/`_b` override the presets. |

Pre-movement is implemented by spawning the agent at `v0 = 0` and restoring
its sampled speed on release. While it waits, the smoke update skips it, so a
delayed occupant's baseline speed is never degraded by smoke it has not walked
through, and it starts at full clear-air speed however dense the smoke has
become around it.

For real FDS output, `fdsreader` provides the local extinction field
via `SliceFieldSampler`. For verification cases such as ISO 20414 Table 21,
the runner can also apply a constant extinction coefficient directly.

## Agent scalars for fds-viewer

When `--output-sqlite` is combined with FED computation, the SQLite also carries
an optional `agent_scalars(frame, id, fed, heat_fed, speed)` table. The base
JuPedSim schema is unchanged, so `jupedsim` replay and Web-Based-JuPedSim still
read the file. Note `heat_fed` was inserted **before** `speed` rather than
appended, so a consumer reading positionally with `SELECT *` -- fds-viewer among
them -- must be updated with this release; name your columns and it does not
matter. [fds-viewer](https://github.com/PedestrianDynamics/fds-viewer) reads this
table to colour agents by FED dose or speed in a 3D scene alongside the FDS
smoke.

## Visualising agents

Agent visualisation is handled by
[fds-viewer](https://github.com/PedestrianDynamics/fds-viewer), which
renders the JuPedSim trajectory SQLite in a 3-D scene alongside the FDS
smoke. Run with `--output-sqlite` to produce the file fds-viewer loads:

```bash
uv run run.py --scenario assets/t_junction \
              --fds-dir assets/t_junction \
              --output-sqlite demo.sqlite
```

When FED is computed, the SQLite also carries the optional
`agent_scalars(frame, id, fed, heat_fed, speed)` table (see above), which
fds-viewer uses to colour agents by FED dose or speed.

## References

See [docs/model-comparison.md](docs/model-comparison.md) for a
section-by-section comparison of the FDS+Evac and pyFDS-Evac evacuation
models (movement, smoke speed, FED, routing), referenced against the
FDS+Evac guide below and the pyFDS-Evac source.

Short summaries are stored in [`materials/`](materials/). The papers
themselves are linked by DOI and not redistributed here:

- FDS+Evac Technical Reference and User's Guide — Korhonen (2021). Primary reference for the FED equations (Section 3.4) and smoke-speed model (Section 3.4, Eq. 11).
- [Boerger et al. (2024)](https://doi.org/10.1016/j.firesaf.2024.104269) ([summary](materials/waypoint_based_visibility_summary.md)) — Beer-Lambert integrated extinction along line of sight (Eq. 8-9), waypoint-based visibility maps. *Fire Safety Journal* 150:104269.
- Haensel (2014) ([summary](materials/haensel2014_summary.md)) — Knowledge-based routing and cognitive map framework for evacuation modelling.
- [Schroder et al. (2020)](https://doi.org/10.1016/j.firesaf.2020.103154) ([summary](materials/schroder2020_summary.md)) — A map representation of the ASET-RSET concept. *Fire Safety Journal*.
- [Ronchi et al. (2013)](https://doi.org/10.1007/s10694-012-0280-y) — Representation of the impact of smoke on agent walking speeds in evacuation models. *Fire Technology* 49.
- [evac.f90](materials/evac.f90) — Original FDS+Evac Fortran source for cross-referencing implementation details.
- [Haghani & Sarvi (2017)](materials/haghani2017_summary.md) — Human exit-choice behaviour under evacuation conditions: literature synthesis.
- [Haghani & Sarvi (2018)](materials/haghani2018_summary.md) — Herding and route-choice in immersive-VR evacuation experiments.
- [Lovreglio et al. (2014)](materials/lovreglio2014_summary.md) — Random-utility discrete choice model of exit selection.
- [Lovreglio et al. (2016)](materials/lovreglio2016_summary.md) — Validation of a Bayesian random-utility exit-choice model.

## Assets

Scenario definitions are stored in [`assets/`](assets/).
[`assets/README.md`](assets/README.md) indexes the folders and the file
conventions; [docs/assets.md](docs/assets.md) describes what each scenario
proves and where that proof is checked.

## Dependencies

- jupedsim
- pedpy
- fdsreader
- plotly
- nbformat
