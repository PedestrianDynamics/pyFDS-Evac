# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `pyfds-evac init DECK.fds` starts a scenario from an FDS deck. It writes
  `config.json`, `geometry.wkt` and `import_report.json` to
  `<deck stem>_scenario/` next to the deck (`-o DIR` picks another folder),
  prints a short summary and the next steps, and exits 0 when runnable, 3
  when written but not runnable or an input was dropped at error level, and
  1 on an error, with nothing written (#605, part of #606, #632).
  - An FDS+Evac deck keeps its `&EXIT`, `&DOOR`, `&EVAC`, `&EVHO`, `&ENTR`
    and `&PERS` records for one floor. Detection plus reaction becomes one
    pre-movement delay with the same mean and variance, and no agent
    starts before the earliest FDS+Evac start.
  - A plain FDS deck gets exits from `SURF_ID='OPEN'` vents on the outside
    of its meshes, or from `--exit`, and a flagged placeholder of 100
    agents unless `--agents` is given.
  - `import_report.json` lists every input that was imported, inferred,
    approximated or dropped, with its deck line; `-v` prints all of it.
  - The walkable area comes from `scripts/generate_walkable_from_fds.py`
    (source checkout only) or from `--walkable FILE.wkt`; the Station
    layer rules are opt-in (`--layer-rules station`).
- `--force` lets `pyfds-evac init` overwrite an output folder that holds a
  `config.json` it did not write; without it, such a folder is refused
  (#632).
- Scenario key `simulationParams.smoke_slice_height` [m]: the absolute FDS
  slice height of a run. `pyfds-evac init` writes the floor level plus
  `HUMAN_SMOKE_HEIGHT`. `--smoke-slice-height` overrides it; a run that
  samples elsewhere logs a warning. A bad value stops the run with a
  one-line error (#632).
- Scenario key `distributions.<id>.parameters.premovement_offset_s` [s]:
  a fixed delay added to every drawn pre-movement time, with and without
  journeys. It needs `use_premovement: true` (#632).
- The 182 input decks of the FDS+Evac guide in `assets/fds_evac_guide/`,
  copied unmodified from tkorhon1/FDS-Evac-Guide at a pinned commit, as
  reference input for the deck importer. They are GPL-3.0-only and are
  excluded from the wheel and the sdist. A test fails when a deck is
  changed, added or removed (#633).
- `REUSE.toml`, `LICENSES/` and `NOTICE` declare the license of every
  file: MIT by default, GPL-3.0-only for the guide decks and the NIST
  software notice for `materials/evac.f90`. CI checks this with
  `reuse lint` (#633).

### Changed

- `pyfds-evac --scenario` takes the slice height from the scenario's
  `smoke_slice_height` when `--smoke-slice-height` is not given, and says
  so. A scenario without the key runs as before (#632).
- `pyfds-evac --help` lists `pyfds-evac init` among its examples (#606).
- SocialForceModel friction is passed to JuPedSim as 0, with a warning
  when a deck declares `sfm_friction` above 0. JuPedSim 1.4.2 applies
  the wall friction with the wrong sign (jupedsim#1677). The clamp goes
  once a JuPedSim release with that fix is pinned (#635).

### Fixed

- The SocialForceModel builder reads `sfm_body_force` (default 120000,
  JuPedSim's) as the body force *k* and passes it as `body_force=`. It
  used to pass `agent_strength` (2000) as *k* and `agent_range` (0.08)
  as the friction, through the deprecated `bodyForce=`.
  `sfm_obstacle_scale` reaches the per-agent `obstacle_scale` (default
  2000). Negative, non-finite or non-numeric `sfm_body_force`,
  `sfm_friction` and `sfm_obstacle_scale` raise `ValueError`. The run
  manifest records the effective values under `sfm`. Shipped decks in clear air and every
  documented number are unchanged; the `ft_full_gate_detour` and
  `ft_full_additive_detour` golden snapshots, with contact under
  synthetic smoke, are regenerated (#611).
- `--show-config`, the TUI and the GUI report a distribution whose
  `desired_speed`, `desired_speed_distribution` or `desired_speed_std`
  differs from its `v0*` key, with the error the run stops on. They used
  to accept the deck. The check,
  `pyfds_evac.core.agent_params.check_speed_aliases`, does not import
  JuPedSim; runs are unchanged (#612).
- Sign visibility from an FDS run no longer stores a time point past the
  end of the FDS output when `--reroute-interval` does not divide `T_END`;
  the last stored point is `T_END`. It now raises `FdsHorizonError` only
  more than one FDS output interval past the end, the window the setup
  check and the smoke and FED samplers use, so a run the setup check
  accepts no longer fails mid-run in sign visibility. The vismap cache
  format goes from 5 to 6, so existing caches are rebuilt once (#510).
- Routes that tie exactly for a discovery agent no longer rank in an
  order that depends on `PYTHONHASHSEED`: the agent's known subgraph is
  built in sorted order, so an exact tie goes to the alphabetically
  first exit. Full-familiarity agents keep the scenario's order (#199).
- Under the gate, route optical depths `tau` at most 1e-9 apart rank as
  equal, so travel time decides. Round-off such as 1e-19 against 4e-15
  used to decide the order, and with it whether the exit-switch anchor
  was asked at all. Neighbouring ties form one group; within it, travel
  time, path length and then the candidate order decide, never the raw
  `tau`. Three FDS decks move, each from a tie with |Δtau| ≤ 1.6e-12:
  `t_junction` goes from 0 to 1 switch, one agent of `l_corridor_gate`
  first picks the near exit (far exit 28 → 27 agents), and agents 5 and
  6 of `world100_stream_east` take another exit. CI goldens and snapshots
  are unchanged (#452).

## [0.3.1] - 2026-10-06

### Removed

- The unused agent-parameter builders and second speed sampler in
  `core.scenario`. Runs never called them; spawning uses
  `core.simulation_init`. Results are unchanged (#569).

### Fixed

- `create_agent_parameters` raises `ValueError` naming an unknown
  `model_type` and the accepted ones. It used to return collision-free
  speed model parameters, so a misspelled model type silently ran a
  different model (#570).
- The plan-view frame recorder of the terminal UI gets a frozen copy of
  the run's incapacitated agents, not the run's own set, so it cannot
  change who is incapacitated. Frames and results are unchanged (#561).
- A SocialForceModel deck whose `simulationParams` omits
  `relaxation_time`, `agent_strength` or `agent_range` runs with 0.5,
  2000 and 0.08 for the missing keys, the values already used without
  simulation parameters. It used to crash, report a spawn area that is
  too small, or spawn no flow agents. An error other than a failed
  placement while spawning agents on a journey keeps its own type
  instead of being reported as a placement failure (#568).
- `--show-config` exits 1 on a scenario whose `routing.cost_model` names no
  route cost model, which every run rejects; the GUI rejects such a
  scenario at upload and submit, and the terminal UI lists it in Review
  (#571).
- The exported `run.py` gives `replay_exits` as an absolute path, so a
  script run from another folder still replays the exits, and a script
  written by the terminal UI no longer says it came from the GUI (#558,
  #576).
- A blank FDS folder is left out of the equivalent CLI command instead of
  becoming the current folder (#557).
- Terminal UI:
  - Save and Copy command right after an edit include that edit (#559).
  - Save, Copy command and Show Python refuse while a field does not
    parse, and name the field; they used to write the default value
    (#619).
  - The Recent tab keeps entries whose scenario or FDS folder is gone,
    dimmed and labelled with what is missing; `Delete` removes the
    highlighted entry, and two long paths no longer look the same
    (#600).
  - Checks are described in words instead of rule IDs (D3, D17, ...);
    the JSON output keeps the IDs (#573).
  - "Open docs page" opens the Terminal UI page (#575), and no redraw
    runs after the app closes (#602).
- Web GUI: decimal fields no longer ask for a keypad without a decimal
  point (#552), and units keep their case in the uppercase form labels,
  e.g. "(m)" instead of "(M)" (#348).
- The FDS case warnings link the published FDS case page instead of a
  path in the repository (#323).
- The analysis scripts that call `run.py` report a run that ends with
  exit status 2 as incomplete instead of using it silently (#449).

### Documentation

- Smoke speed model: FDS+Evac reference speeds from the guide's component
  test; the plot is no longer called a verification, and new
  verification tests check the speed and FED cases of the FDS+Evac guide
  against formulas rebuilt from `evac.f90` and `func.f90` (#631).
- Web GUI: the `run.py` listing matches the exported script (#558, #576).
- Terminal UI: the Recent tab (#600).

## [0.3.0] - 2026-10-05

### Added

- `pyfds-evac-tui`, a terminal UI (`pip install 'pyfds-evac[tui]'`, built
  on Textual): pick a scenario and FDS folder, configure with the options
  of `pyfds-evac` (inactive options greyed out with the reason), review
  the effective configuration and the equivalent command, run in a
  separate process with a live plan view of walls, exits, agents and
  smoke, and inspect the outcome and output files. Runs write to the GUI's
  folder layout under `./results`; the same options give the same files as
  `pyfds-evac` (#485). Keys and navigation:
  - every footer shows `^q quit  ? keys  ^k palette`; `?` and `F1` open the
    key list on every step (#598, #583);
  - `ctrl+n` / `ctrl+p` go to the next / previous step, and the footer names
    the target; `Esc` also goes back; the command palette is on `ctrl+k`;
  - on Configure, `↑`/`↓` move between options and the focused option's row
    is highlighted as in the palette; a click on an inactive option shows
    why it is inactive;
  - the FDS folder box and the Open file tab browse folders as Emacs `dired`
    does, with fzf-like filtering, `Tab` completion and `..`; FDS output
    folders and scenarios are marked;
  - on Results, `←`/`→` replay the plan frames, `v` opens it full screen, and
    `Enter` on an output file previews it (text lines, SQLite tables, folder
    contents) with `y` copy path and `o` open (not over SSH);
  - in a terminal with 256 or 16 colours, a notice says the theme colours
    are approximate and how to get truecolor (#599).
- `pyfds_evac.config.frontend`: the run folders and outcome wording the GUI
  and the TUI share (provisional) (#485).
- `pyfds_evac.config`: one model of the run options (name, type, unit,
  default, choices, help, the Python field each sets) from which the
  `pyfds-evac` parser and the GUI form are built, the effective
  configuration of a run (models on or off and why, options with their
  origin, options that have no effect, setup warnings and errors) and the
  equivalent command and Python script. Provisional public API: it can
  change in 0.3.x. Flags, defaults, help and results are unchanged (#484).
- `--show-config` prints the effective configuration and exits without
  running; exit status 1 when the configuration has an error (#484).
- The run manifest written with `--output-sqlite` records the effective
  configuration under `configuration`, checked against the seed, models and
  model parameters the run used (`ScenarioResult.run_settings`,
  provisional) (#484).
- `ProgressEvent` counts incapacitated agents and flow agents not yet
  spawned (`incapacitated`, `not_spawned`; provisional) (#484).
- For the terminal UI (#485), provisional:
  - `pyfds_evac.config.rules.applies` / `applicability`: whether each
    option changes the run, also at its default, with the rule and reason
    of the "has no effect" warnings; `Parameter.tier` (`common` for the
    GUI's sections, else `advanced`).
  - `pyfds_evac.core.run_stream.stream_run`: runs the options as
    `pyfds-evac` does and sends status events instead of printing:
    phases, log lines, warnings (with the simulated time), progress, a
    `PlanEvent` (walkable outline, exits and their openings, signs, spawn
    areas, smoke mode, the FDS slice height read), throttled `FrameEvent`s
    (agent positions and states, agents per exit, a coarse float16
    extinction grid) and a `ResultEvent` with the outcome (evacuated,
    total, remaining, incapacitated, not spawned, end time, seed, files).
    Frames are off unless asked for; results are the same with them.
  - `ScenarioResult.agents_incapacitated`.

### Changed

- An option set away from its default that changes nothing in the run now
  logs a warning at setup, e.g. `--enable-fic-speed has no effect without
  --fds-dir.` Runs with default options log nothing new (#484).
- `uv.lock` takes the security fixes of pillow, starlette, anyio, idna,
  soupsieve and oauthlib (#525).
- `uv run app.py` and `python -m pyfds_evac.webapp.app` listen on
  127.0.0.1 instead of all interfaces, as `pyfds-evac-gui` does; `--host`
  and `--port` work as for `pyfds-evac-gui`. All three print a warning
  when `--host` makes the GUI reachable from other computers. `app.py` and
  `python -m pyfds_evac.webapp.app` now stop with a usage error on
  arguments other than `--host` and `--port` (#477).
- GUI and TUI results show an Incapacitated count after Remaining, or
  "not modelled in this run" when no dose model applies. Counts read
  "e of n agents", or "e of n that entered" when flow agents were cut
  off. The smoke overlay draws the horizontal FDS slice at the run's
  smoke slice height on fixed K bins, with a caption naming the slice
  and the frame time. The smoke chart has fixed axes, a dashed mean K
  and a numeric summary. `ResultEvent` and `PlanEvent` gain
  `incapacitation_modelled` (#321).

### Fixed

- The GUI no longer prints a `SyntaxWarning: invalid escape sequence`
  on its first import: a regular expression in its inline JavaScript was
  not escaped for Python. The page sends the same JavaScript (#476).
- The custom replay speed of the GUI's trajectory viewer shows a decimal
  point on a host with a comma region (`1.5`, not `1,5`). It takes digits
  with a point, at least 0.05; any other value (`1,5`, `2x`, `-1`) is not
  applied, and a message under the controls says so and names the speed
  that is kept. Before, `1,5` applied as 1 (#493).
- The GUI's results-only view lists the run manifest under "Output
  files", as the finished view does (#494).
- GUI and TUI runs write the exit history CSV
  (`<run>_exit_history.csv`, as `--output-exit-history`) to the run's
  folder, and the GUI lists it with the other output files. Before, no
  front end set the option, so the file was never written (#547).
- An unknown routing `cost_model` or smoke `speed_law` raises
  `ValueError` and names the allowed values. Before, any `cost_model`
  other than `"gate"` ran the additive model and any `speed_law` other
  than `"fridolf"` ran lund, so `"Gate"` or `"Fridolf"` silently gave the
  other model. Names are matched exactly (`"gate"`, `"additive"`,
  `"lund"`, `"fridolf"`); an absent key still means `"gate"` and
  `"lund"`. Valid inputs give the same results (#305).
- A scenario JSON accepts `desired_speed`, `desired_speed_distribution`
  and `desired_speed_std` as aliases of `v0`, `v0_distribution` and
  `v0_std`, as `Scenario.set_agent_params()` does. Before, the run
  ignored them without a warning and used 1.25 m/s. A distribution that
  sets an alias and its `v0*` key to different values is an error; equal
  values are accepted. Scenarios without these keys run unchanged. The
  SocialForceModel agent parameters fall back to 1.25 m/s, not 0.8, when
  no `v0` is given; no run reached that fallback (#143).
- In the layer heat regime, the effective configuration reports a
  missing layer input once, not twice, and attributes layer errors to
  the layer emissivity option, not to `heat_emissivity` (#522).
- A `run_scenario` that fails removes its temporary trajectory SQLite
  and its manifest. Before, they were left behind (#331).
- Stale user-facing text: the usage of `scripts/run_and_plot.sh` names a
  finished FDS run as `<fds-dir>`; the `--smoke-slice-height` help names
  walking speed, FED and sign legibility; `examples/walkthrough.py` uses
  the 1.6 m slice height; `examples/rset_ensemble.py` writes its figure
  to a temporary folder or to its first argument, not over the tracked
  site figure (#312).

### Documentation

- New Terminal UI page (#537).
- Scenario JSON and Troubleshooting document the exact names of
  `cost_model` and `speed_law` and the `desired_speed*` aliases; Usage
  tables the defaults of `pyfds-evac` and `run_scenario()` (#584, #585).
- Visibility (Fundamentals): Jin's limits of 0.15 1/m for occupants
  unfamiliar with a building and 0.5 1/m for familiar ones, checked
  against Jin (1981); the routing threshold of 0.5 1/m applies to all
  agents (#515, #608).
- Coming from FDS+Evac names FDS 6.7.7 as the last FDS+Evac release, and
  the Wayfinding, Route-cost gate and model comparison pages mark
  0.03 1/m as the Evac 2.6.0 door threshold (#542, #543).
- Fundamentals pages state published laws only; the slice-height default
  moved from ASET/RSET to the docs (#588).

## [0.2.4] - 2026-10-03

### Added

- `scripts/release_check.sh` has an install gate, in `--quick` and
  `--full`: it builds the wheel of the commit and, per supported Python
  version, installs `<wheel>[gui]` with plain pip into a fresh venv. It
  checks `pip check`, `pyfds-evac --help`, an argument error,
  `python -m pyfds_evac --help`, the GUI page and the `ISO-table21`
  scenario from a folder outside the repository, and the install hint
  of `pyfds-evac-gui` without the extra. The first `pyfds-evac --help`
  and `pyfds-evac-gui --help` after the install are timed with an empty
  matplotlib cache and fail above 1 s. CI runs the same check on Python
  3.12 with a 3 s limit (#478).

### Fixed

- `pyfds-evac --help` and argument errors no longer load numpy. The
  heat options of the parser read their constants from `core.fed`,
  which loaded the FDS slice sampler and numpy with it; the sampler now
  loads when FDS data is read. On macOS the first numpy import after an
  install took up to 1.2 s and made the 1 s limit of the install gate
  fail now and then (#503).

### Documentation

- New how-to "Create a scenario": the three ways to get `config.json` and
  `geometry.wkt` (JuPedSim Web, an example download, matching the FDS
  deck), the keys to add by hand after an export from the app, and how to
  check a scenario before a run (#506, #512). Scenario JSON documents
  `waypoint_routing`, `transitions` and `journeys_v2`.
- `CONTRIBUTING.md` is one screen: issue, fork, pull request. Setup, CI,
  docs build, commit style and versioning moved to a new Development
  page. The Limitations page states the release policy (SemVer) (#511,
  closes #502).

## [0.2.3] - 2026-10-03

### Fixed

- `pyfds-evac --help` and argument errors return at once, also on the
  first call after an install: JuPedSim, fdsreader, fdsvismap and
  matplotlib now load when a run starts, not when the command starts.
  The first run after an install still builds matplotlib's font cache.
  Flags, defaults and outputs are unchanged (#496).

## [0.2.2] - 2026-10-02

### Changed

- `pyfds-evac --help` is shorter to read: a one-line usage
  (`pyfds-evac --scenario PATH [--fds-dir DIR] [options]`), a description
  of what the tool does, the flags in eight groups (scenario and run,
  outputs, FDS input and smoke, toxic gas, heat, routing, visibility and
  signs, ASET/RSET tools) and copy-paste examples. It is rendered by
  rich-argparse, a new runtime dependency (`>=1.8`), in colour on a
  terminal and as plain text when piped or with `NO_COLOR`. Flag names,
  defaults, choices and behaviour are unchanged.

### Fixed

- GUI: decimal fields show "1.6", not "1,6", when the operating system's
  region uses a decimal comma (Chromium on macOS formats number inputs
  by the OS region). They are text fields now; a typed comma is flagged
  before the run starts. Submitted values are unchanged (#487).
- GUI: "Artifacts written" and the results-only file list show the
  results folder once, with a Copy path button, and each file relative
  to it; the full path is in the tooltip (#488).
- GUI: the Smoke and Cognitive map growth plots are left out when the
  run has no data for them (no smoke source, no agent's cognitive map
  grew); one "Not shown" note says why (#489).
- A default run no longer prints the `Reroute debug` trace of the
  rerouting pass; it is a debug log, printed with the `--debug` flag. The
  command line prints fdsreader's repeated module-parse warning (such as
  `Module vents`) once instead of once per opened case. Results and
  written outputs are unchanged (#486).

## [0.2.1] - 2026-10-02

First release on PyPI: `pip install pyfds-evac`.

### Added

- Releases are published to PyPI as `pyfds-evac` by a GitHub workflow
  with Trusted Publishing, when a GitHub release is published (#472).
  The sdist leaves out the site, specs and working material.

### Changed

- fdsvismap 0.3.2 replaces 0.3.1, still pinned exactly. Its code is the
  same; it allows scikit-image `>=0.23.2,<1.0` instead of `~=0.23.2`.
  The uv override of scikit-image is removed, and `pip install` now
  works on Python 3.12, 3.13 and 3.14. The lock moves scikit-image from
  0.23.2 to 0.26.0 on Python 3.12, as on 3.13 and 3.14 already; a seeded
  reference run gives identical trajectories and visibility maps (#479).

### Fixed

- The CLI and the GUI work from an installed wheel (#471). The CLI moved
  from `run.py` into `pyfds_evac.cli` and installs as the `pyfds-evac`
  command and as `python -m pyfds_evac`; `run.py` still runs it, with the
  same flags, defaults and outputs. The GUI starts with the
  `pyfds-evac-gui` command (gui extra; without it the command says how to
  install it), listening on 127.0.0.1:5001; `uv run app.py` still works.
  Installed outside a source checkout, the GUI reads scenarios from
  `./assets` and writes `uploads/` and `results/` under the directory it
  starts in, not under site-packages.

### Documentation

- Install, Web GUI, Usage, Quickstart, Troubleshooting and the README
  describe `pip install pyfds-evac` and the installed commands
  `pyfds-evac`, `python -m pyfds_evac` and `pyfds-evac-gui`: where the
  GUI reads and writes, its 127.0.0.1 default, the message without the
  gui extra, and that an example zip unpacks into a folder of its own
  (#475). The README links are absolute, so they work on PyPI.
- The page "A crowd in a real fire" is renamed "A crowd in a fire". Its
  address (`first-fds-case`) and anchors stay, so links keep working.
  The Fundamentals and the figure of the design-fire page say "fire"
  where they said "real fire".

## [0.2.0] - 2026-10-02

Highlights. Smoke along a route now changes an agent's exit: route costs
add smoke and dose, and a gate on the route's optical depth rejects a
smoky path. Agents choose exits from a cognitive map that grows with
familiarity, signs they can read and exits they discover. The heat dose
follows ISO 13571 and the SFPE Handbook, with opt-in total-flux,
hot-layer and `INTEGRATED INTENSITY` methods. Defaults follow FDS+Evac
where a mechanism has a direct counterpart. Exits can open and close on
a schedule. A run checks its scenario against the FDS domain and stops at
the end of the FDS output. A run that reaches its time limit with agents
inside is reported as incomplete, and `run.py` then exits with status 2.
Seeded results differ from v0.1; see Changed. pyFDS-Evac runs on Python
3.12, 3.13 and 3.14. Release 0.2.0 is installed from the source tree
with uv; it is not published on PyPI.

Breaking changes, which make this a MINOR release while MAJOR is 0:

- Python 3.12, 3.13 or 3.14 is required; Python 3.11 and earlier are no
  longer supported (Removed).
- Exit status and run outcome: `run.py` exits with status 2 for an
  incomplete run, and `success` is then `False` (Changed).
- A run that outlasts the FDS output stops with `FdsHorizonError` (Changed).
- Defaults follow FDS+Evac: sampling height, FIC slowdown, heat dose,
  incapacitation, O2 threshold, pre-movement and `v0` (Changed, Migration).
- Heat: the ISO 13571 clothed law by default, and one threshold for gas and
  heat (Changed).
- Seeded placements and outcomes differ from earlier versions (Changed).
- Agents leave at an exit when their centre enters the exit polygon, and the
  opening exit is ranked from each agent's position (Changed).
- Exits are priced from where the agent stands, which changes route
  switches and exit choice in smoke (Fixed, #451).
- Rerouting is on by default, `w_queue` defaults to 0, `EXTINCTION` is no
  longer read as smoke, and the FDS decks and demo assets moved to
  `fds_directory/` and `assets/t_junction/` (Changed).
- `speed_law="fridolf"` is Eq. 7 of Fridolf et al.; the V/(V+2) law is
  removed (Changed).
- New output columns and manifest keys: `in_fds_domain`, `fds_coverage`,
  `outcome`, `agent_seeding` and the heat columns (Added, Changed).
- Web GUI: the cumulative FED chart, sparkline and mean line (Removed).
- The unused modules `pyfds_evac.config` and `pyfds_evac.utilities`
  (Removed).

### Added

- `scripts/release_check.sh`, the release gate. In a detached worktree of
  the current commit it runs the tests per supported Python, builds and
  follows the download bundles, runs the documented commands listed in
  `scripts/release_check.toml` and builds the site, then writes
  `release-check-<commit>.md`. Checks of pages an open issue already
  lists are reported as STALE and do not fail the gate (#462).
- Python 3.13 and 3.14 support; CI tests 3.12, 3.13 and 3.14.
  On 3.13 and 3.14, `uv sync` installs scikit-image 0.26 instead of the
  0.23 that fdsvismap requires, which does not build there; fdsvismap's
  sight lines are unchanged. A pip install needs Python 3.12.
- A setup check of the scenario against the FDS slice coverage: the
  walkable area, exits, checkpoints, spawn areas and route edges outside
  the slices of every sampled quantity (m² and m), and signs outside them
  or off the vismap grid, are logged once and recorded as `fds_coverage` in
  the run manifest and in `metrics`. The smoke and FED histories gain an
  `in_fds_domain` column, `agent_scalars` the same column, and the run ends
  with a count of agents and samples outside (`metrics["fds_outside"]`).
  Outside the slices the values are unchanged: ambient air and clear sight,
  as in FDS+Evac.
- `--require-fds-coverage` (`require_fds_coverage=True` on
  `run_scenario`, `ExtinctionField`, `FdsFedField`, `FdsHeatField` and
  `VisibilityModel`): anything the setup check finds outside is an error,
  and so is any smoke, FED, heat or sign-visibility sample outside the
  slices (`FdsDomainError`, naming the quantity, position and time).
- Exits that open and close on a schedule: the optional exit keys
  `open_from_s` and `closed_after_s` keep an exit open while
  `open_from_s` ≤ t < `closed_after_s`. A closed exit removes nobody, is left
  out of route ranking and of explore and wander targets, and an agent
  heading for it re-evaluates at the next reroute check, on the exits it
  knows; the switch is logged as `exit_closed`. An agent that knows no other
  node waits at the closed exit. An opened exit is taken at the next regular
  re-evaluation. A schedule needs rerouting and routed agents:
  `--no-enable-rerouting`, `--smoke-blind`, `--replay-exits` and agents on
  JuPedSim journeys are rejected. `StageNode` gains `open_from_s`,
  `closed_after_s` and `is_open()`; `route_graph` gains
  `without_closed_stages` and `stage_closed`. Without a schedule results are
  unchanged ([#373](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/373)).
- `assets/station_fahy/validate.py` prints the agreement statistics of the
  Station validation study: T1 over the placed rows (Fahy 117/229 =
  51.1 %) with its signed bias; W, the door-user-weighted total variation
  distance, with the rows under 10 door users pooled; W's noise floor from
  20,000 multinomial resamples of Fahy; the per-run spread over several
  runs; the split at `--t-jam`, descriptive only; and, with `--against`,
  the paired W difference per seed on the agents that exited in both arms.
  A scored row without a model door user counts as distance 1. Agents still
  on the grid at the horizon (`max_simulation_time` of `--config`, or
  `--horizon`) are censored: counted, and left out of T1, W and the
  same-agent set; `observed_matrix` is unchanged
  ([#374](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/374),
  [#382](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/382)).
- `--smoke-blind`, `--replay-exits CSV` and `--output-exit-history CSV`
  for ASET/RSET arms on the same FDS output. `--smoke-blind` samples the fire
  for the smoke and FED histories only: agents walk at free speed, choose
  their first exit with K = 0 and no FED, see signs as without the fire, and
  rerouting and tenability are off; FED, heat FED and FIC still accumulate.
  `--output-exit-history` writes each agent's exit
  (`agent_id,origin,spawn_index,exit_id`), and `--replay-exits` sends the
  n-th agent spawned from an origin in a later run to the exit of the n-th
  agent from that origin there, by clear-air costs on the agent's map,
  failing on a missing spawn, an unknown exit or an exit it cannot apply.
  `run_scenario` takes `smoke_blind` and `replay_exits`, `ScenarioResult`
  gains `exit_history`, and the manifest records both options when on,
  the replay as its agent count and sha256
  ([#341](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/341)).
- `--heat-regime {smoke,layer}` (opt-in, with `--heat-fed-method
  total-flux`; default `smoke`, the behaviour below): `layer` takes the head
  to be in clear air below a hot layer, with q = h(T_g − T_s)/1000 plus the
  net layer flux φ ε_L σ(T_L⁴ − T_s⁴)/1000 and no radiant term of the gas at
  the head, so the two radiant terms are never summed (spec 016). T_L is read
  from a second `TEMPERATURE` slice at `--heat-layer-height`;
  `--heat-view-factor` and `--heat-layer-emissivity` set φ and ε_L. None of
  the three has a default. The FED history gains `heat_layer_temperature_c`
  and the manifest's `heat_flux_parameters` the regime and layer parameters
  ([#222](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/222)).
- `--heat-radiant-source integrated-intensity` with `--heat-u-factor f`
  (opt-in, with `--heat-fed-method total-flux`; default source `gas`): the
  radiant term is the excess f·(U − 4σT_s⁴) over an isotropic field at the
  skin temperature (maintainer decision) from the FDS `INTEGRATED
  INTENSITY` slice at the slice height, in place of the gas term
  ε σ (T_g⁴ − T_s⁴), so q = f·(U − 4σT_s⁴/1000) + h (T_g − T_s)/1000.
  f in [0.25, 1] has no default and is
  required; a case without the slice, a U slice at another height than the
  TEMPERATURE slice, or an agent inside only one of the two slices is an
  error. With `--heat-regime layer` as well, U supplies the radiant term
  and the layer term is not added (U already holds the layer's emission),
  with one warning and `layer_term: false` in the manifest. The FED
  history gains
  `heat_integrated_intensity_kw_m2` and the manifest `radiant_source`,
  `u_factor` and `radiant_flux` (`excess`). Agents outside the FDS domain
  get a zero rate, with U and q NaN in the FED history, and one warning
  per run. Surroundings at or below the skin temperature give no dose for
  any f; a negative excess counts as zero and the rate is never negative
  ([#221](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/221)).
- `--heat-fed-method total-flux` (opt-in, with `--enable-heat-fed`; default
  `convective`): the heat dose is q^1.33/D (SFPE Handbook Ch. 63 Eq. 63.43)
  with q the heat flux to the skin of Eq. 63.49, both terms divided by 1000
  together. The radiant term of q (the gas term, the `INTEGRATED
  INTENSITY` excess or the layer term) counts as zero in the dose below
  2.5 kW/m² (ISO 13571:2012 §8.2, §8.4, spec 016; 2.5 itself counts); the
  convective term counts at every level, so hot air still gives a dose.
  D is the dose of `--heat-endpoint`, the fatal 16.7 without it (SFPE Ch. 63 p. 2384). `--heat-emissivity` (0.5),
  `--heat-convective-coefficient` (5) and `--heat-skin-temperature` (35 °C)
  set the flux; their defaults are assumptions. The FED history gains
  `heat_flux_kw_m2` (the physical q) and the manifest `heat_fed_method`
  and `heat_flux_parameters`, with `radiant_threshold_kw_m2`. This is the
  head-in-smoke regime
  ([#223](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/223)).
- `--heat-endpoint {tolerance,injury,fatal}` (opt-in, with
  `--enable-heat-fed`): the heat dose uses the convective law of that
  endpoint, SFPE Handbook Ch. 63 Eq. 63.45, 63.46 or 63.47, paired with its
  radiant dose (1.33, 10, 16.7; SFPE Ch. 63 pp. 2382 and 2384). The FED history gains `heat_endpoint`,
  `heat_outside_validity` (above 205 °C, an assumed limit, or a non-finite
  temperature) and `heat_humidity` (`unknown`, as humidity is not sampled),
  and the run manifest records `heat_endpoint` and `heat_validity`. Without the option the dose is
  the ISO 13571:2012 law of `--heat-clothing`
  ([#220](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/220)).
- A run warns once when CO is sampled with zero CO2: the hyperventilation
  factor is then 1, and the FDS deck probably has no ambient CO2.
- Web GUI: a light/dark theme switch, a Cancel control for a running scenario,
  a Clear control for finished results, and a trajectory viewer that fills
  the screen in fullscreen. A cancel stops the run at its next progress tick
  or between phases; output files written before the cancel stay on disk.
- `assets/Haspel`: the BUW Campus Haspel ground floor with an FDS deck, for
  a model-to-model comparison with a PathFinder student study. Not yet a
  valid comparison; see `assets/Haspel/README.md`
  ([#134](https://github.com/PedestrianDynamics/pyFDS-Evac/pull/134)).
- `assets/heat_radiometer`: three FDS decks for the heat dose (spec 016,
  L3): a sealed adiabatic room with a hot sooty layer above 2 m, the same
  room uniformly hot (the isotropic control), and a propane burner in the
  open. Skin radiometers and gauges (35 C, h = 8 W/(m2 K)) at 1.6 and
  1.8 m face up, sideways and down next to `INTEGRATED INTENSITY`
  devices and slices. `scripts/verification/heat_radiometer.py` tabulates
  q/U and `heat_radiometer_figures.py` draws it; page
  `docs/testing-heat-radiometer.md`. Reference data for #221-#223; the
  heat model is unchanged ([#224](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/224)).

- Routing and wayfinding since v0.1: congestion-aware routing (#16);
  visibility-aware routing with cognitive maps (#17); auto-routing for
  minimal configs with distributions and exits only (#18), whose
  auto-wired adjacency has physical lengths (#58); familiarity-aware
  frontier exploration for discovery agents (#39); familiarity as a
  probability, with entrance seeding (#59); smoke as a gate on route
  optical depth (#123); cognitive-map growth recorded by `run_scenario`
  (#93).
- An FDS deck generated from a JuPedSim walkable WKT (#28), and placeable
  fires for discovery decks (#117).
- Warnings on silent slice-height and FED mismatches (#67).
- jupedsim 1.4.2 with `WarpDriverModel` (#85).
- Web GUI: FDS smoke overlay in the trajectory viewer (#36), playback
  speed and a live FED panel (#37), a dark theme (#38), results-only runs
  and scenario upload (#109), a theme switch, run controls and a working
  fullscreen viewer (#130), and a "Show equivalent Python" export (#329).
- Verification and test scenarios: ISO 20414 Tables 21 and 22 (#82, #83),
  stationary FED against FDS output (#74), blind-spawn discovery (#66),
  cognitive-map acquisition and exit visibility scenarios (#50, #54), and
  an in-repo world generator with invariant tests on generated decks
  (#97).
- CI runs the whole test suite (#381) and reports coverage on Codecov
  (#435). Golden snapshots pin rerouting decisions (#201), and tests pin
  route smoke sampling, scenario loading, spawn placement and direct
  steering (#438-#441).
- The FDS+Evac source of FDS 6.7.6 is bundled with an `evac.f90` notice
  as the reference for the ported equations (#205, #206), and the
  repository has community health files (#203).

### Changed

- fdsvismap 0.3.1 from PyPI replaces the git pin, pinned exactly because
  `visibility.py` patches its private `_get_visibility_array`. numpy is now
  at least 2.1. fdsvismap 0.3.1 also picks the horizontal slice nearest the
  height (fdsvismap#55), so the patch of fdsreader's slice lookup is
  removed; the extinction slice is still chosen by
  `fds_sampling.select_horizontal_slice` and passed by index. Vismap caches
  written before are rebuilt (cache format 5). `pyfds_evac/jpstooling.py`,
  `scripts/demo_vismap_phase0.py` and `scripts/demo_cognitive_map_vis.py`,
  which used the removed waypoint API and had no caller, are deleted.
- A run that reaches `max_simulation_time` with agents inside, or with flow
  agents still to enter, is incomplete: `success` is `False` (it was
  `True`, #139), the new `metrics["status"]` is `"incomplete"` (else
  `"completed"`), and `metrics["agents_not_spawned"]` counts the flow agents
  that never entered. The run manifest records the same under `outcome`,
  and the `run.py` summary line reads `Simulation incomplete: time limit
  reached after …`. `run.py` exits with status 2 for an incomplete run
  (outputs are still written); `scripts/run_and_plot.sh`,
  `scripts/sweep_queue_weight.py` and `assets/schroeder2015_route/run_p1.sh`
  accept it.

- **Seeded placements differ from earlier versions.** The start positions,
  their shuffle, the radius and v0 samples and the default pre-movement
  stream of each distribution are seeded from a blake2b hash of the run
  seed, the purpose and the distribution key, not from `seed + index`,
  `seed + 1000` or the bare seed. Distribution 1 under seed s used to draw
  what distribution 0 draws under seed s + 1, so ensembles over
  consecutive seeds reused streams; in the full-config initialiser all
  t=0 distributions shared one position stream and one pre-movement
  stream. An explicit `premovement_seed` still wins. The manifest's
  `agent_seeding` is now `spawn-key-blake2b-v2`; per-agent seeds are
  unchanged. Goldens and the cheap documented numbers were regenerated
  ([#360](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/360)).
- **An agent leaves at an exit when its centre enters the exit polygon**,
  not within its radius + 0.5 m of a target point inside it, so the door
  width sets the door flow. Before, a door drawn flush with a wall acted
  up to about 1.3 m wider and agents left from the room beside it.
  Checkpoints keep the distance rule. A single agent now leaves about
  0.3 s later; crowd results move by more, since the door now bounds the
  flow (the golden decks end up to 0.8 s later). The golden snapshots,
  the single-run pages, the RSET how-to and ISO Test 18 are regenerated;
  the with/without-fire how-to
  ([#391](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/391)),
  the Schröder study
  ([#388](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/388)),
  the web GUI screenshots
  ([#389](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/389))
  and the pages still on runs before #360 (A crowd in a real fire,
  familiarity, wayfinding;
  [#384](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/384))
  still show the earlier runs
  ([#349](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/349)).
- **The opening exit is ranked from each agent's position**, as
  re-evaluation ranks it, not from its spawn area's node. Before, every
  agent of one spawn area started towards the same exit, including agents
  beside another door; a shortest-path crowd in a room with two doors now
  splits between them. The golden snapshots and the example outputs are
  unchanged
  ([#350](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/350)).
- **Seeded outcomes differ from earlier versions.** Every per-agent random
  draw is seeded from the run seed and the agent's spawn key
  `(origin, spawn_index)`, through a blake2b hash that does not depend on
  the process, the platform or `PYTHONHASHSEED`, not from the JuPedSim id,
  a per-distribution index or a stream shared by all agents: the
  familiarity map, the start stage and target points, the journey variant
  of a flow spawn (now one draw per spawn, not per candidate position),
  the later direct-steering target, wait and next-stage draws (each on its
  own stream), the probabilistic gas and heat incapacitation thresholds
  and the reevaluation offset, `((spawn_index + 1) % steps) * dt`. The
  same scenario and seed therefore give other trajectories and counts than
  before; goldens and documented numbers were regenerated. A second run in
  the same process now gives the same results as a fresh one, under other
  JuPedSim ids, and a refused spawn no longer shifts the draws of later
  agents. The JuPedSim id stays the key of all per-agent state and output.
  Exit histories written before this change replay without error but pair
  agents whose draws differ; the manifest gains `agent_seeding`
  (`spawn-key-blake2b-v1`) to tell the two apart. A flow journey variant
  with a positive weight and no valid entry stage now fails at setup
  ([#353](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/353),
  [#198](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/198)).

- **Breaking:** a run that outlasts the FDS output stops instead of
  holding the last slice frame. `build_run_kwargs` (so `run.py` and the
  web GUI) rejects a `max_simulation_time` more than one slice output
  interval past the last frame of any FDS slice at setup, even when all
  agents would leave before `T_END` (the default of 300 s now fails on a
  shorter FDS run), and smoke, gas FED, heat FED and sign-visibility
  samples past that point raise `FdsHorizonError`, a `ValueError`, naming
  the quantity, the requested time and the last FDS time. Previously every
  such sample silently returned the last frame, so agents walked through
  frozen smoke and kept accumulating dose at the final concentrations.
  `--allow-fds-horizon-hold` (and `allow_horizon_hold=True` on
  `SliceFieldSampler`, `load_slice_sampler`, the `from_fds` constructors
  and `VisibilityModel`) restores the hold with one warning per quantity
  and a setup warning ([#340](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/340)).
- With `--enable-heat-fed` the default convective law is ISO 13571:2012
  Eq. (9), fully clothed,
  t = 4.1e8 · T^-3.61 min (T in °C, air with less than 10 % water vapour),
  in place of SFPE Handbook Eq. 63.44, t = 5e7 · T^-3.4 min. At 100, 150
  and 200 °C the time to heat FED = 1 grows from 7.9, 2.0 and 0.75 min to
  24.7, 5.7 and 2.0 min. `--heat-clothing unclothed`
  (`opts.heat_clothing`, `DefaultHeatFedModel(..., clothing="unclothed")`)
  selects ISO Eq. (10), which has the constants of Eq. 63.44, and gives the
  previous behaviour. The manifest records `heat_clothing`.
  `--heat-endpoint` and `--heat-fed-method total-flux` are unchanged
  ([#290](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/290)).
- The heat threshold is now the gas threshold `--fed-threshold`, as ISO
  13571:2012 asks for one threshold for FED and FEC (§5.4, §8.5). `--heat-fed-threshold` and
  `TenabilityConfig.heat_fed_threshold` default to none; a value sets a
  separate heat threshold, logs a warning that it departs from ISO, and is
  recorded in the manifest as `heat_fed_threshold_override`. Runs with the
  default `--fed-threshold 1.0` are unaffected; a run that changed
  `--fed-threshold` and wants the previous heat threshold passes
  `--heat-fed-threshold 1.0`. Both doses stay deterministic by default.
- Docs: Models › Heat explains where the 2.5 kW/m² radiant threshold of
  total flux acts: from about 285 °C at the default ε, with a step in the
  rate there and no radiant dose at the 200 °C anchor. A figure
  (`scripts/figures/heat_radiant_threshold.py`) shows it, and the
  verification table lists the total-flux, layer, `INTEGRATED INTENSITY`
  and threshold tests.
- Docs: Fundamentals › Incapacitation thresholds states what is known
  about the population spread of heat tolerance: SFPE Ch. 63 gives figures
  only for radiant lethality, which imply σ ≈ 0.22 if log-normal, not the
  borrowed 0.94. No code change; the heat threshold stays deterministic by
  default ([#225](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/225)).
- Heat FED tests take their expected values from the SFPE Handbook
  (5th ed., Ch. 63) instead of the code's own formula: Eq. 63.44 as printed
  (p. 2382), Table 63.20's convective rows (p. 2383) and Table 63.17's
  dry-air rows (p. 2375). Table 63.21 (p. 2385, whose values follow
  Eq. 63.45 despite its caption), Table 63.20's radiant rows and a
  walking-past-a-flame case are added as reference values for a future
  Eq. 63.45 option and the planned radiant term; they call no pyFDS-Evac
  code. The heat dose
  itself is unchanged
  ([#219](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/219)).
- Docs, heat dose: each formula states whether it takes incident flux, net
  flux or air temperature; Models › Heat and Limitations say that heat
  FED = 1 and gas FED = 1 are different endpoints that set the same
  `incapacitated` flag, told apart only by `incapacitation_cause`; the
  stale line references on Models › FED are corrected, the `fed.py` ones
  checked by a test
  ([#218](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/218)).
- Performance: the per-step speed update of direct-steering runs scans
  only the zones whose speed factor is not 1, precomputed once per run
  (`active_steering_zones`), and leaves an agent outside every such zone
  alone while its speed state (base speed, smoke, FIC, active zone) is
  unchanged. Trajectories are identical. Any code that writes an agent's
  `desired_speed` must also update its speed state (#240).
- Web GUI: a flag with a fixed set of choices (the heat clothing, endpoint,
  dose method, radiant source, regime and heat incapacitation mode) is a
  dropdown of its argparse choices with the CLI default preselected, in
  place of a free text field. A flag without a default offers a blank
  "default" entry.
- Web GUI: the FED section is titled "Purser / FDS" instead of
  "ISO 13571"; the coded form is the Purser sum as in the FDS `FED` function.
- `speed_law="fridolf"` now implements Eq. 7 (method 3) of
  Fridolf, Ronchi, Nilsson & Frantzich (2019),
  [doi:10.1016/j.tust.2019.04.016](https://doi.org/10.1016/j.tust.2019.04.016),
  also in Fridolf et al. (2018, SFPE extended abstract), a summary of their
  2016 SP report:
  w = min(v₀, max(0.2, v₀ − 0.34 (3 − V))) with V = C/K. C = 3 is the
  coded FDS default; the 2019 paper used A = 2 for reflecting targets. The
  reduction is additive with an absolute 0.2 m/s floor, and speed is
  unchanged above 3 m. The option used to compute V/(V+2), which has no
  known source; that law is removed and cannot be selected. New
  `SmokeSpeedConfig` fields: `fridolf_slope`, `fridolf_visibility_threshold_m`,
  `fridolf_min_speed_m_per_s`. `SmokeSpeedModel.sample` and `speed_factor`
  take an optional `free_speed_m_per_s` (1 m/s, method 1, if omitted)
  ([#146](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/146)).

Defaults now follow FDS+Evac where a mechanism has a direct FDS+Evac
counterpart ([#157](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/157)).
See [Defaults follow FDS+Evac](https://pedestriandynamics.org/pyFDS-Evac/docs/getting-started/coming-from-fds-evac/#defaults-follow-fdsevac).

- Smoke, heat and visibility are sampled at 1.6 m (`HUMAN_SMOKE_HEIGHT`)
  instead of 2.0 m.
- The irritant (FIC) slowdown is off by default. `--enable-fic-speed` turns it
  on.
- The HCN term of the FED subtracts NO + NO2 and uses the offset 1/220, as the
  FDS `FED` function that FDS+Evac calls, instead of NO2 alone with 0.0045
  (FDS+Evac Guide Eq. 15)
  ([#159](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/159)).
- The CO2 hyperventilation factor is 1 when there is no CO2 (or no CO2
  reading), as in the FDS `FED` function, instead of exp(2.0004)/7.1 = 1.0411.
  FED from CO, HCN, NOx and irritants in CO2-free air is therefore about 4 %
  lower; this matches FDS's `FED_FIC` verification case. Runs with FDS's
  default ambient CO2 (about 0.04 vol %) are unaffected; only cells with
  exactly zero CO2 change
  ([#194](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/194)).
- The O2 term of the FED applies below 20 % O2 instead of 19.5 %.
  `--o2-threshold-percent` sets the threshold.
- A spawn area that sets no pre-movement gets a constant 10 s (`PRE_MEAN`),
  with a warning, instead of 0 s. A `constant` pre-movement distribution is
  added.
- A spawn area that sets no `v0` walks at 1.25 m/s (`VEL_MEAN`) instead of
  1.2 m/s.
- The convective heat dose is off by default. `--enable-heat-fed` turns it on;
  before, it was on whenever the FDS output had a `TEMPERATURE` slice.
- Heat incapacitation is deterministic by default: every agent stops at the
  heat threshold, which is `--fed-threshold` unless `--heat-fed-threshold`
  overrides it. No population spread for heat is published; the
  log-normal draw with σ = 0.94, borrowed from the gas dose, is opt-in with
  `--heat-incapacitation-mode probabilistic`.
- Gas incapacitation is deterministic by default: every agent stops at
  `--fed-threshold` (1.0), as in FDS+Evac. The per-agent log-normal draw
  (σ = 0.94, fitted to NIST TN 1797) is opt-in with
  `--incapacitation-mode probabilistic`. The web GUI's default output folder
  is `results/<scenario>/deterministic/…` accordingly
  ([#235](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/235)).

- Rerouting is on by default and re-evaluates every 1 s (#41).
- `w_queue` defaults to 0; the Station case sets its calibration against
  Fahy Table 2 (0.03) in its deck (#90, #94).
- Clear-air visibility comes from fdsvismap (#95), and the cognitive map
  is the only visibility gate (#53). Discovery decks without FDS data use
  clear-air sight instead of unlimited sight (#117).
- `EXTINCTION` is no longer read as the smoke extinction coefficient; a
  deck needs a `SOOT EXTINCTION COEFFICIENT` slice (#71).
- Repository layout: `fds_data/` and `testing directory/` are merged into
  `fds_directory/` (#47), and `assets/demo` is `assets/t_junction`; unused
  scenarios are retired (#51).

**Migration.** To reproduce results from earlier pyFDS-Evac versions, pass
`--smoke-slice-height 2.0 --enable-fic-speed --o2-threshold-percent 19.5
--enable-heat-fed --heat-incapacitation-mode probabilistic
--incapacitation-mode probabilistic` to `run.py` (or set the matching `opts` attributes), and
give every spawn area `"use_premovement": false` and `"v0": 1.2` unless it
already sets them. Python callers that build the models themselves pass
`TenabilityConfig(enable_fic_speed=True, heat_incapacitation_mode="probabilistic",
incapacitation_mode="probabilistic")`,
`DefaultFedConfig(o2_threshold_percent=19.5, slice_height_m=2.0)`, and
`slice_height_m=2.0` to `SmokeSpeedConfig`, `ExtinctionField.from_fds`,
`FdsHeatField.from_fds` and `VisibilityModel`; a heat dose needs a
`DefaultHeatFedModel` passed to `run_scenario`, as before. The earlier HCN form is not available: it was a
documentation error in the FDS+Evac Guide, and it differs from the current
one only when NO is present or by the offset, 4.5 × 10⁻⁵ /min.

### Removed

- Python 3.11 support. pyFDS-Evac requires Python 3.12, 3.13 or 3.14
  (`requires-python = ">=3.12,<3.15"`). Python 3.15 waits on jupedsim
  wheels for it.
- The unused modules `pyfds_evac.config` (`SimulationConfig`) and
  `pyfds_evac.utilities` (`distance`); nothing in the package has
  imported them since `jpstooling.py` was removed. Code that imports
  them breaks; this is acceptable for 0.2.0 under SemVer 0.x. Also the
  three images in `assets/t_junction/` written by the removed demo
  scripts (`cognitive_map_evolution.png`, `vismap_aset.png`,
  `vismap_coverage.png`).
- Web GUI: the Cumulative FED results chart, the FED sparkline and the mean
  FED line. The viewer and the live chart show the highest FED of any agent
  at each time.

- The notebooks and `Gregory.md` (#205).

### Fixed

- A directional sign is legible from its own grid cell. fdsvismap before
  0.3.0 divided 0 by 0 there, so the sign was hidden and
  `visibility_to_node` returned `None`. Only FDS-backed discovery runs whose
  agents pass a sign's cell change; on the first FDS case 70 of 150 agents
  leave instead of 72.
- Exits are priced from where the agent stands (#451). The path search
  starts at the agent's position and never routes back through the node the
  agent last left, the first leg is charged the smoke on the
  walk ahead of the agent rather than a share of its edge's mean, and the
  current exit is never priced above the path the agent walks
  (`rank_routes(current_path=...)`, #186). An agent past smoke near its
  origin no longer leaves an exit a few seconds ahead for a detour, and a
  walk back through smoke is charged. Without `agent_position` nothing
  changes; FED keeps the share of the first segment (#171).
- The mean extinction of a route edge (`k_avg`) averaged over all samples
  of its polyline, so short segments and interior vertices weighed too much
  and the mean depended on where the routing engine put its vertices. It is
  now the length-weighted mean of the per-segment means; the sample points
  and the worst sample `k_max` are unchanged, and so are two-point edges
  and clear-air runs. Route costs and choices in smoke change (#437).
- In a deck with journeys, agents of a distribution without a journey whose
  nearest exit is throttled stood at their spawn points until the time
  limit. They are now steered to that exit and leave through it under its
  cap (#434).

- A point that some loaded gas slices cover and others do not raises
  `ValueError`, as heat already did, instead of reading ambient air for
  every gas ([#427](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/427)).
- An agent off the vismap grid no longer reads the sign visibility of the
  nearest edge cell. It sees a sign in clear air when the sign is within its
  reading distance, measured from the agent, and `visibility_to_node`
  returns `None` there. A sign off the grid logs a warning, as fdsvismap
  casts its sight lines from the grid edge
  ([#426](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/426)).
- An agent could stop 0.01-0.02 m short of an exit polygon drawn thinner
  than about 0.25 m against a wall, held there by the wall or a door jamb,
  and was never removed; about one run in ten of the Schröder room configs
  ran to `max_simulation_time` with one or two agents left. An exit now
  also counts as reached when the agent's centre is within 0.03 m of its
  polygon. A single agent leaves about 0.02 s earlier (clear ISO corridor
  79.26 -> 79.24 s); the golden decks end 0.02-0.10 s earlier. The golden
  snapshots, the single-run pages, the RSET how-to and ISO Test 18 are
  regenerated; pages already on earlier runs keep their notes
  ([#401](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/401)).
- A flow spawn whose setup failed after `add_agent` had succeeded was
  retried at the next candidate position, which left a half-initialised
  agent in the simulation and added a second one. The error is now raised
  ([#353](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/353)).

- Sign legibility and the route `next_node_not_visible` gate read the
  horizontal extinction slice nearest `--smoke-slice-height`, the slice
  walking speed and FED read, with the same warning when it is more than
  0.5 m away. fdsvismap used fdsreader's `get_nearest`, which returns the
  first horizontal slice declared, or a vertical one through the plan
  origin. Visibility caches are rebuilt (format 4)
  ([#296](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/296)).

- `scripts/fed_heat_hand_calc.py` cited "ISO TS 13571 eq. 5" for
  t = 5e7 · T^-3.4; it is ISO 13571:2012 Eq. (10) (§8.3.2), equal to SFPE
  Eq. 63.44
  ([#291](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/291)).

- A heat-only FDS case (TEMPERATURE slice, no SOOT EXTINCTION COEFFICIENT
  slice) no longer crashes `run.py`. Smoke speed reduction is then off and
  the visibility model falls back to clear air, each with a warning, so
  `--constant-extinction 0 --no-visibility` is no longer needed
  ([#248](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/248)).

- The uniform heat rooms `assets/fed_incap_heat_{100,150,200}c` set `TMPA`
  to the deck temperature instead of 20 °C. FDS started the walls and the
  radiation field at `TMPA`, so the room lost heat at t = 0 and settled
  0.7–1.8 % below its `&INIT` value. It now holds the deck value to within
  1 mK, and the deterministic heat stops of the verification page are the
  closed form at the deck temperature (476 / 120 / 46 s, were 487 / 125 /
  48 s). FDS's device output is committed so CI checks the hold
  ([#253](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/253)).
- With direct steering, an agent slowed by smoke outside every speed zone
  kept its reduced speed once the smoke factor returned to exactly 1 (for
  example on walking into air with K = 0). The restore now also writes when
  the factors last applied were below 1, so the agent walks at its free speed
  again. Runs where agents leave smoke for clear air change; the rerouting
  golden snapshots are regenerated
  ([#246](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/246)).
- The gas FED read the first CO, CO2 and O2 slice listed in the FDS deck,
  whatever its height, instead of the slice nearest `--smoke-slice-height`
  (1.6 m). It now selects each species like smoke speed and heat do. Slice
  selection also skips vertical (PBX/PBY) slices, whose mid-height could
  look closest to the requested height; a quantity with only vertical slices
  now raises an error
  ([#238](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/238)).
- The FDS slice sampler reads the value nearest to the query point: the
  nearest node of a node-centred slice (the FDS default) and the nearest
  cell centre of a `CELL_CENTERED=T` slice, including on stretched grids.
  It used to space the values evenly with half-cell offsets, which on
  node-centred slices read the wrong node for about a quarter of positions
  ([#212](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/212)).
- The O2 hypoxia rate was 60 times too slow (#35, #52), and the FIC speed
  factor compounded every step (#73).
- Routing: first-segment FED and smoke were charged twice mid-leg (#44);
  each agent is routed from its own spawn area (#46) and no-journey agents
  are rooted at their spawn area (#64); distances are measured along the
  walkable area (#48); every route is priced from the agent's position
  (#65) and the frontier is chosen from where the agent stands (#70); the
  first exit comes from the agent's cognitive map, not geometry (#87);
  arrival learning is gated by visibility and learns reverse edges (#96);
  stale `path_choices` no longer trap discovery agents (#107); a stage's
  node lies inside its polygon, at its most open interior point for a
  concave stage (#105, #108).
- Web GUI: trajectories play at the recorded rate (#106), and agents are
  drawn at map scale (#111).
- Assets: the ISO-table21 deck runs (#79), and the Station doorways open
  to their clear width (#110, #112).
- Docs for the release (#470): the ISO Test 19 page runs
  `build_geometry.py` with `uv run python` (#464); bundle READMEs quote
  the printed rows verbatim (#465); the how-tos, limitations,
  first-fds-case and routing pages describe incomplete runs and exit
  status 2 (#442); the with/without-fire study and the cognitive-map
  memory example are re-run on the current code (#391).
