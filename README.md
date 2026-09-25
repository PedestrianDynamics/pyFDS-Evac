[![code quality](https://github.com/PedestrianDynamics/pyFDS-Evac/actions/workflows/code-quality.yml/badge.svg)](https://github.com/PedestrianDynamics/pyFDS-Evac/actions/workflows/code-quality.yml)
[![tests](https://github.com/PedestrianDynamics/pyFDS-Evac/actions/workflows/tests.yml/badge.svg)](https://github.com/PedestrianDynamics/pyFDS-Evac/actions/workflows/tests.yml)

# pyFDS-Evac

Fire Dynamics Simulator (FDS) coupled evacuation modeling with smoke-speed reduction, toxic gas dose (FED), and dynamic route rerouting.

The project includes:

- Smoke-speed model (visibility/extinction-based speed reduction)
- Full ISO 13571 FED model (toxic gas dose accumulation)
- Convective heat FED (ISO TS 13571 eq. 5), accumulated as a dose independent
  of the gas track -- an agent is incapacitated when either crosses its own
  threshold, because thermal injury and asphyxiation are different mechanisms
  and the standard does not sum them. Radiant heat is not modelled, and heat
  does not enter route choice. It also does not slow an agent down: unlike
  smoke and irritants, heat has no effect at all until the dose is reached, at
  which point the agent stops.
- Dynamic smoke-based route rerouting with congestion awareness
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

Reference materials are stored in [`materials/`](materials/), each with a
short summary alongside the PDF:

- [FDS+Evac Technical Reference and User's Guide](materials/FDS+EVAC_Guide.pdf) — Korhonen (2021). Primary reference for the FED equations (Section 3.4) and smoke-speed model (Section 3.4, Eq. 11).
- [Boerger et al. (2024)](materials/waypoint_based_visibility.pdf) ([summary](materials/waypoint_based_visibility_summary.md)) — Beer-Lambert integrated extinction along line of sight (Eq. 8-9), waypoint-based visibility maps. *Fire Safety Journal* 150:104269.
- [Haensel (2014)](materials/Haensel2014.pdf) ([summary](materials/haensel2014_summary.md)) — Knowledge-based routing and cognitive map framework for evacuation modelling.
- [Schroder et al. (2020)](materials/Schroder2020.pdf) ([summary](materials/schroder2020_summary.md)) — Waypoint-based visibility and evacuation modeling.
- [Ronchi et al. (2013)](materials/Ronchi2013.pdf) — FDS+Evac evacuation model validation and verification.
- [evac.f90](materials/evac.f90) — Original FDS+Evac Fortran source for cross-referencing implementation details.
- [Haghani & Sarvi (2017)](materials/haghani2017_summary.md) — Human exit-choice behaviour under evacuation conditions: literature synthesis.
- [Haghani & Sarvi (2018)](materials/haghani2018_summary.md) — Herding and route-choice in immersive-VR evacuation experiments.
- [Lovreglio et al. (2014)](materials/lovreglio2014_summary.md) — Random-utility discrete choice model of exit selection.
- [Lovreglio et al. (2016)](materials/lovreglio2016_summary.md) — Validation of a Bayesian random-utility exit-choice model.

## Assets

Scenario definitions are stored in [`assets/`](assets/).
[`assets/README.md`](assets/README.md) indexes the folders and the file
conventions; what each one proves is below.

- **ISO-table21**: **ISO 20414:2020 Table 21** (Test 18, *reduced visibility vs
  walking speed*) — corridor 2 m x 100 m, one occupant at 1,25 m/s, constant
  extinction. See [the asset README](assets/ISO-table21/README.md) for the
  clause-by-clause comparison, including the two places we deviate. Proves the smoke speed reduction law is applied correctly end to end:
  `test_iso_table21_constant_extinction_matches_expected_time_ratio` runs the
  scenario clear and then under a `ConstantExtinctionField` at five extinction
  coefficients (0.5, 1.0, 3.0, 7.5, 10.0 /m), asserting the ratio of evacuation
  times matches `1 / speed_factor_from_extinction(k)` within 8% and that every
  recorded `speed_factor` equals the expected one exactly. Doubles as the
  standard small fixture in `test_progress_callback.py`, `test_webapp.py` and
  `test_fed.py`, which use it for its size rather than its ISO provenance.
- **ISO-table22**: **ISO 20414:2020 Table 22** (Test 19, *occupant
  incapacitation by fire/smoke*) — room 10 m x 10 m x 3 m, one occupant held
  still by ISO's prescribed pre-evacuation time above 10 000 000 s. See
  [the asset README](assets/ISO-table22/README.md). The gas field is stubbed, so
  it verifies the accumulator, not the FDS coupling; the coupled four-case
  version is [`iso_table22_coupled`](assets/iso_table22_coupled/README.md). One
  agent with `v0` forced to 0 in a fixed gas concentration; config and geometry only, no deck. Proves the
  runtime FED accumulator agrees with the closed form:
  `test_iso_table22_stationary_runtime_matches_analytic_threshold_time` takes
  the analytic FED=1.0 time from `time_to_fed_threshold_s()` and asserts the
  observed crossing lands within one timestep of it, that `fed_max >= 1.0`, and
  that the agent does not evacuate. Holding the gas inputs constant is
  deliberate; this tests the accumulator, not the gas sampling. Also backs the
  FED history throttling test.
- **t_junction**: T-corridor FDS scenario with cable fire, two exits (A open, B smoke-accumulating),
  200 visitors spawning in the branch; used for visibility-aware routing and cognitive
  map verification (Spec 008). Includes `config_full.json` and `config_discovery.json`
  for familiarity-tier comparison. The rerouting mechanism itself is verified by
  scenario **S4** in
  [`tests/verification/test_s4_tjunction_reroute.py`](tests/verification/test_s4_tjunction_reroute.py)
  (control arm and null-field control both record zero switches; smoke forces
  every agent B→A and never the reverse; reroute latency stays within the
  configured interval; switch count is reproducible under a fixed seed). Note
  that S4 builds its own T-corridor via `harness.t_junction_scenario()` with a
  synthetic smoke field rather than loading this asset, so the mechanism is
  covered but the deck and config here are not exercised by the suite. This
  config uses flow spawning deliberately: under by-number placement an agent's
  route-eval source node is its assigned exit, which makes rerouting degenerate
  ([issue #21](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/21)).
- **fed_incap_co_2000ppm** / **fed_incap_co_4000ppm** / **fed_incap_co_8000ppm**:
  FED accumulation and probabilistic-incapacitation validation against a
  hand-calculated reference (`fed_hand_calc.py`), at three constant CO
  concentrations (2000/4000/8000 ppm) in a sealed, spatially uniform room —
  removing gas-transport physics as a variable isolates the FED/incapacitation
  *pipeline* logic. 100 non-evacuating agents circling a rectangular path, FDS
  domain split across 4 MPI meshes to confirm gas data is consistent at mesh
  boundaries. All three concentrations currently match the hand-calc's FED=1.0
  crossing time to <0.5% (2000 ppm: 782.4 s hand-calc vs 786 s simulated;
  4000 ppm: 382.3 s vs 384 s; 8000 ppm: 186.6 s vs 187 s). Validated by running
  the cases and comparing, not by a test in `tests/`. (See the bug fixes on the
  [FED page](https://pedestriandynamics.org/pyFDS-Evac/models/fed/):
  this suite is what surfaced
  both the O2 rate bug and the conflicting-`&INIT` FDS pitfall. The earlier
  `fed_incap_co_v1`, `fed_incap_co_v2` and `fed_incap_co_smol` iterations from
  the same debugging lineage are no longer tracked.) Full writeup:
  `docs/testing-homogeneous.md`.
- **Cognitive Map Memory**: 4x32 m corridor with a side alcove, 20 `discovery`
  agents. The side exit's sign faces west and is legible only from
  `y ∈ [12.5, 27.5]` on the centreline — a window that falls out of
  `view_angle * max_vis >= distance` rather than being tuned, and that
  `build_geometry.py` recomputes and asserts. Proves the cognitive map does the
  one thing a visibility query cannot: **remember**. The side exit is unknown at
  spawn, enters the map on crossing `y=12.5`, and is *still* there at `y=30`
  where the sign is long unreadable. Persistence is the load-bearing claim —
  delete the expansion rules and acquisition still appears to work for any agent
  starting inside the window. A third test closes the loop to routing: a
  remembered-but-illegible exit must still be routable, which it was not before
  the visibility consolidation. `scripts/generate_cognitive_map_states.py` renders the
  three states (unknown / legible now / remembered), and the amber band is the
  memory made visible. Checked by `tests/test_cognitive_map_memory.py`.
- **FIC vs FED Speed**: 4x50 m sealed corridor, 30 agents, one exit. The gas is
  *prescribed* by a single `&INIT` (CO at 2000 ppm, acrolein at 10 ppm) rather
  than burned, so concentration is constant in space and time and the only
  variable across runs is which tenability rules are enabled — set from the
  command line (`--disable-tenability`, `--fic-alpha 0`, or the default).
  Separates the two rules by timescale: **FED is a cumulative dose with a
  threshold and does nothing below it** (0.079 /min here, so 13 minutes to reach
  FED = 1, against a ~33 s egress), while **FIC responds instantaneously**
  (`FIC = 0.5`, speed factor 0.65, so ~51 s). The prediction is stated in the
  asset README before running and is falsifiable: if FED materially slows an
  agent over a minute of exposure, the model or the reasoning is wrong. A
  control test records that acrolein is *not* only an irritant — it also sits in
  FED's Fractional Lethal Dose sum, so removing it takes 100% of the speed
  penalty but only 3% of the dose rate, and that asymmetry is what makes the two
  rules separable. Also pins the O2 hypoxia term against the published closed
  form (Fire Safety Journal, surrogate-gases paper, Eq. 9) rather than against
  our own docs. Checked by `tests/test_fic_vs_fed_speed.py`.
- **Exit Visibility Alpha**: 4x30 m corridor, 40 `discovery` agents, two
  exits. The two configs differ in exactly one value — the viewing bearing
  (`alpha`) of the near exit's sign — so any difference in exit choice is
  attributable to sign orientation and nothing else. Proves that legibility
  decides cognitive-map membership, and membership decides the exit: at
  `alpha=0` both exits enter the map and agents take the nearer one; at
  `alpha=180` the near exit never enters the map and agents walk 10 m further
  to the only exit they know about, even though distance favours the near one
  by more than 2:1. The near exit is *absent*, not rejected — a stronger claim,
  since a rejected route still appears in the ranking and the all-rejected
  fallback can reinstate it. Checked by
  `tests/test_exit_visibility_alpha.py`, which needs no FDS output: it
  reimplements fdsvismap's clear-air rule (`view_angle * max_vis >= distance`)
  so the test exercises the routing decision rather than the third-party
  solver. A companion test pins that a `full`-familiarity agent ignores the
  bearing entirely — signs are wayfinding information and bind only where
  knowledge is incomplete. The folder README documents the **30 m visibility
  ceiling** that makes a sign illegible at any bearing, and how much tighter it
  becomes once smoke is present (`c / K̄`, so 6 m at `c=3`, `K̄=0.5`).
- **Familiarity Test Full** / **Familiarity Test Discovery**: `SocialForceModel`
  scenario on a hand-drawn maze-like floor plan (20x18 m, 0.1 m walls, 1.2 m
  doors throughout, generated parametrically by each folder's
  `build_geometry.py`), differing only in the spawn distribution's
  `familiarity` value. A matching fire deck lives at
  `assets/familiarity_test_full/familiarity_test.fds` (real
  combustion via `&REAC`, not a prescribed `&INIT`; walls mirror the
  walkable geometry exactly so smoke propagates through the same
  doorways agents use). These two configs use the legacy `journeys`/
  `transitions` shape directly (the web editor's `journeys_v2` format is
  auto-migrated to this shape by `load_scenario`, but was hand-converted
  here to add the extra edge below). The maze's start room is one open
  box that connects directly to the checkpoint outside the exit door
  (`jps-checkpoints_0 → jps-checkpoints_3`), completely bypassing the
  scripted checkpoint tour through the rest of the maze — a real ~39%
  shorter route (32 m vs 52 m) that's declared as an extra graph edge
  (tagged `journey_id: "shortcut"` in `transitions`, invisible to the
  static spawn-time journey) for the rerouting/cognitive-map system to
  find. Run with `--enable-rerouting` (no `--fds-dir`/vis-cache needed —
  divergence here is pure-distance, not smoke-driven) to see it: `full`
  agents know the whole graph immediately and reroute onto the shortcut
  within the first reevaluation tick; `discovery` agents start knowing
  only the spawn's declared neighbor and explore the nearest
  known-but-unvisited doorway at each step — which for this maze's
  geometry happens to coincide with the original scripted tour the whole
  way, so they end up taking the long route without ever finding the
  shortcut. Verified: `full` evacuates in 35.1 s vs `discovery`'s 75.1 s
  (both 20/20 evacuated; see the results table in
  [`docs/testing-familiarity.md`](docs/testing-familiarity.md)).

## Dependencies

- jupedsim
- pedpy
- fdsreader
- plotly
- nbformat
