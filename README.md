[![code quality](https://github.com/PedestrianDynamics/pyFDS-Evac/actions/workflows/code-quality.yml/badge.svg)](https://github.com/PedestrianDynamics/pyFDS-Evac/actions/workflows/code-quality.yml)
[![tests](https://github.com/PedestrianDynamics/pyFDS-Evac/actions/workflows/tests.yml/badge.svg)](https://github.com/PedestrianDynamics/pyFDS-Evac/actions/workflows/tests.yml)
[![codecov](https://codecov.io/gh/PedestrianDynamics/pyFDS-Evac/graph/badge.svg)](https://codecov.io/gh/PedestrianDynamics/pyFDS-Evac)
[![docs](https://github.com/PedestrianDynamics/pyFDS-Evac/actions/workflows/docs.yml/badge.svg)](https://pedestriandynamics.org/pyFDS-Evac/)
[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](https://github.com/PedestrianDynamics/pyFDS-Evac/blob/main/LICENSE)
[![PyPI](https://img.shields.io/pypi/v/pyfds-evac.svg)](https://pypi.org/project/pyfds-evac/)
[![Python](https://img.shields.io/pypi/pyversions/pyfds-evac.svg)](https://pypi.org/project/pyfds-evac/)

# pyFDS-Evac

Fire Dynamics Simulator (FDS) coupled evacuation modeling with smoke-speed reduction, toxic gas dose (FED), and dynamic route rerouting.

The project includes:

- Smoke-speed model (visibility/extinction-based speed reduction)
- Purser FED as computed by [FDS+Evac](https://github.com/firemodels/fds/tree/c9da70d7a/Source) (the `FED` function of FDS; toxic gas dose accumulation, up to 12 species)
- Convective heat FED (ISO 13571:2012 Eq. (9), fully clothed; Eq. (10) =
  SFPE Handbook Eq. 63.44 with `--heat-clothing unclothed`), opt-in with
  `--enable-heat-fed` (FDS+Evac has none), accumulated as a dose
  independent of the gas track -- an agent is incapacitated when either crosses
  the threshold, one for both by default as in ISO 13571; the heat dose is a running total of its own and is never
  added to the gas FED. Radiant heat enters only through the opt-in
  total-flux method (gas at the head, a hot layer above the head, or FDS
  `INTEGRATED INTENSITY` with a user factor; a radiant term below
  2.5 kW/m² counts as zero, as in ISO 13571), and heat
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

- [Install](https://pedestriandynamics.org/pyFDS-Evac/docs/getting-started/install/): requirements and a check that the install works
- [Usage](https://pedestriandynamics.org/pyFDS-Evac/docs/using/usage/): CLI flags, post-processing scripts, run-and-plot driver
- [Outputs](https://pedestriandynamics.org/pyFDS-Evac/docs/using/outputs/) and [Scenario JSON](https://pedestriandynamics.org/pyFDS-Evac/docs/using/scenario-json/): what a run writes, and the keys a scenario reads
- Defaults follow FDS+Evac; see [what changed](https://pedestriandynamics.org/pyFDS-Evac/docs/getting-started/coming-from-fds-evac/#defaults-follow-fdsevac) and the [changelog](https://github.com/PedestrianDynamics/pyFDS-Evac/blob/main/CHANGELOG.md)
- [Smoke-speed model](https://pedestriandynamics.org/pyFDS-Evac/models/smoke-speed/), including FDS data access through `fdsreader`
- [Fractional effective dose](https://pedestriandynamics.org/pyFDS-Evac/models/fed/), including heat dose and irritant slowdown
- [Dynamic route rerouting](https://pedestriandynamics.org/pyFDS-Evac/models/routing/)
- [Wayfinding](https://pedestriandynamics.org/pyFDS-Evac/models/wayfinding/)
- [Verification suite](https://pedestriandynamics.org/pyFDS-Evac/verification/)

## Talks

- **A Modular Workflow for Visibility-Aware Evacuation Modelling**, Visibility
  Seminar 2026, University of Wuppertal, 25 September 2026:
  [slides](https://pedestriandynamics.org/pyFDS-Evac/talks/visibility-seminar-2026/)

## Installation

pyFDS-Evac needs Python 3.12, 3.13 or 3.14. Install it from PyPI:

```bash
pip install pyfds-evac
pyfds-evac --help
```

`pyfds-evac` runs a scenario; `python -m pyfds_evac` does the same. The
package contains no scenarios, examples or scripts. Each example page on the
documentation site offers its input files as a zip, which unpacks into a
folder of its own; run the commands from inside that folder. The
[Install](https://pedestriandynamics.org/pyFDS-Evac/docs/getting-started/install/) page has a full check on a
scenario.

## Development

To work on the code, or to run the examples, scripts and tracked scenarios of
the repository, clone it and use [uv](https://github.com/astral-sh/uv):

```bash
git clone https://github.com/PedestrianDynamics/pyFDS-Evac.git
cd pyFDS-Evac
uv sync
uv run run.py --scenario assets/ISO-table21 --cleanup
```

`run.py` is the same command line as `pyfds-evac` (`uv run` uses the project
environment; `source .venv/bin/activate` activates it for the shell).
[Usage](https://pedestriandynamics.org/pyFDS-Evac/docs/using/usage/) lists every CLI flag, the post-processing
scripts, and the `scripts/run_and_plot.sh` driver that runs a simulation and
produces every plot in one go.

Tests, the docs build and pull requests: see
[Development](https://pedestriandynamics.org/pyFDS-Evac/docs/development/)
and [CONTRIBUTING.md](CONTRIBUTING.md).

**Bringing your own FDS case?** Read
[what your FDS case must provide](https://pedestriandynamics.org/pyFDS-Evac/docs/using/fds-case-requirements/)
first. pyFDS-Evac does not run FDS, it samples the output of a finished run,
and your deck has to dump specific slices for that to work. That page also
covers the `&REAC` yields those slices depend on, and two failure modes that
stay silent otherwise.

## Terminal UI

For remote machines and SSH, a terminal UI configures, runs and inspects a
scenario with the same options as `pyfds-evac`:

```bash
pip install "pyfds-evac[tui]"
pyfds-evac-tui
```

The run stops when the terminal closes; use `tmux` or `screen` for long runs.
Documentation:
[Terminal UI](https://pedestriandynamics.org/pyFDS-Evac/docs/using/terminal-ui/).

## Web GUI

An optional local web app runs the same model behind a form:

```bash
pip install "pyfds-evac[gui]"
pyfds-evac-gui
```

Then open <http://127.0.0.1:5001>. The GUI listens on this computer only;
`--host` and `--port` change that. It lists the scenarios in `./assets` and
writes `./uploads` and `./results` under the folder it starts in. In a source
checkout, `uv sync --extra gui` and `uv run app.py` start it with the
checkout's folders, on 127.0.0.1 with auto-reload. The form
groups, the options it does not offer, the result views and how to export a
run as a Python script are on the
[Web GUI](https://pedestriandynamics.org/pyFDS-Evac/docs/using/web-gui/) page.

## Agent speed and pre-movement

The scenario keys that set an agent's speed, size and pre-movement, with
their defaults, are on the
[Scenario JSON](https://pedestriandynamics.org/pyFDS-Evac/docs/using/scenario-json/)
page. The smoke-speed law and its parameters are library-level fields, not
scenario keys; see the
[smoke-speed model](https://pedestriandynamics.org/pyFDS-Evac/models/smoke-speed/#parameters).

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
smoke. Run with `--output-sqlite` to produce the file fds-viewer loads; this
example uses a scenario and FDS output tracked in the repository, so run it
in a source checkout:

```bash
uv run run.py --scenario assets/iso_table22_coupled/config_a.json \
              --fds-dir assets/iso_table22_coupled/fds/a \
              --output-sqlite results/demo.sqlite
```

`--fds-dir` must hold the output of a finished FDS run (the `.smv` file), not
only the deck.

When FED is computed, the SQLite also carries the optional
`agent_scalars(frame, id, fed, heat_fed, speed)` table (see above), which
fds-viewer uses to colour agents by FED dose or speed.

## References

See the [model comparison](https://pedestriandynamics.org/pyFDS-Evac/docs/understanding/model-comparison/) for a
section-by-section comparison of the FDS+Evac and pyFDS-Evac evacuation
models (movement, smoke speed, FED, routing), referenced against the
FDS+Evac guide below and the pyFDS-Evac source.

Short summaries are stored in [`materials/`](https://github.com/PedestrianDynamics/pyFDS-Evac/tree/main/materials). The papers
themselves are linked by DOI and not redistributed here:

- FDS+Evac Technical Reference and User's Guide — Korhonen (2021). Primary reference for the FED equations (Section 3.4) and smoke-speed model (Section 3.4, Eq. 11).
- [Börger, Belt & Arnold (2024)](https://doi.org/10.1016/j.firesaf.2024.104269) ([summary](https://github.com/PedestrianDynamics/pyFDS-Evac/blob/main/materials/waypoint_based_visibility_summary.md)) — Beer-Lambert extinction averaged along the line of sight to a sign (Eq. 8-9), waypoint-based visibility maps. *Fire Safety Journal* 150:104269. Averaging along the walked route, as pyFDS-Evac's route cost does, is our extension.
- Haensel (2014) ([summary](https://github.com/PedestrianDynamics/pyFDS-Evac/blob/main/materials/haensel2014_summary.md)) — Knowledge-based routing and cognitive map framework for evacuation modelling.
- [Schroder et al. (2020)](https://doi.org/10.1016/j.firesaf.2020.103154) ([summary](https://github.com/PedestrianDynamics/pyFDS-Evac/blob/main/materials/schroder2020_summary.md)) — A map representation of the ASET-RSET concept. *Fire Safety Journal*.
- [Ronchi et al. (2013)](https://doi.org/10.1007/s10694-012-0280-y) — Representation of the impact of smoke on agent walking speeds in evacuation models. *Fire Technology* 49.
- [evac.f90](https://github.com/PedestrianDynamics/pyFDS-Evac/blob/main/materials/evac.f90) — Original FDS+Evac Fortran source for cross-referencing implementation details.
- [Haghani & Sarvi (2017)](https://github.com/PedestrianDynamics/pyFDS-Evac/blob/main/materials/haghani2017_summary.md) — Human exit-choice behaviour under evacuation conditions: literature synthesis.
- [Haghani & Sarvi (2018)](https://github.com/PedestrianDynamics/pyFDS-Evac/blob/main/materials/haghani2018_summary.md) — Herding and route-choice in immersive-VR evacuation experiments.
- [Lovreglio et al. (2014)](https://github.com/PedestrianDynamics/pyFDS-Evac/blob/main/materials/lovreglio2014_summary.md) — Random-utility discrete choice model of exit selection.
- [Lovreglio et al. (2016)](https://github.com/PedestrianDynamics/pyFDS-Evac/blob/main/materials/lovreglio2016_summary.md) — Validation of a Bayesian random-utility exit-choice model.

## Assets

Scenario definitions are stored in [`assets/`](https://github.com/PedestrianDynamics/pyFDS-Evac/tree/main/assets).
[`assets/README.md`](https://github.com/PedestrianDynamics/pyFDS-Evac/blob/main/assets/README.md) indexes the folders and the file
conventions; [Scenario assets](https://pedestriandynamics.org/pyFDS-Evac/verification/assets/) describes what each
scenario proves and where that proof is checked.

## Dependencies

pyFDS-Evac depends on jupedsim, pedpy, fdsreader, fdsvismap, numpy, shapely,
matplotlib, plotly and nbformat; the `gui` extra adds python-fasthtml,
monsterui and python-multipart. fdsvismap is pinned exactly (0.3.2), and a
plain `pip install` works on Python 3.12, 3.13 and 3.14. Versions and pins
are in
[`pyproject.toml`](https://github.com/PedestrianDynamics/pyFDS-Evac/blob/main/pyproject.toml).
