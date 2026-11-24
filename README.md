[![code quality](https://github.com/PedestrianDynamics/pyFDS-Evac/actions/workflows/code-quality.yml/badge.svg)](https://github.com/PedestrianDynamics/pyFDS-Evac/actions/workflows/code-quality.yml)
[![tests](https://github.com/PedestrianDynamics/pyFDS-Evac/actions/workflows/tests.yml/badge.svg)](https://github.com/PedestrianDynamics/pyFDS-Evac/actions/workflows/tests.yml)
[![ISO 20414](https://github.com/PedestrianDynamics/pyFDS-Evac/actions/workflows/iso-20414.yml/badge.svg)](https://pedestriandynamics.org/pyFDS-Evac/verification/iso-20414/)
[![NIST TN 1822](https://github.com/PedestrianDynamics/pyFDS-Evac/actions/workflows/nist-tn1822.yml/badge.svg)](https://pedestriandynamics.org/pyFDS-Evac/verification/nist-tn1822/)
[![codecov](https://codecov.io/gh/PedestrianDynamics/pyFDS-Evac/graph/badge.svg)](https://codecov.io/gh/PedestrianDynamics/pyFDS-Evac)
[![docs](https://github.com/PedestrianDynamics/pyFDS-Evac/actions/workflows/docs.yml/badge.svg)](https://pedestriandynamics.org/pyFDS-Evac/)
[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](https://github.com/PedestrianDynamics/pyFDS-Evac/blob/main/LICENSE)
[![PyPI](https://img.shields.io/pypi/v/pyfds-evac.svg)](https://pypi.org/project/pyfds-evac/)
[![Python](https://img.shields.io/pypi/pyversions/pyfds-evac.svg)](https://pypi.org/project/pyfds-evac/)

# pyFDS-Evac

Evacuation modelling coupled to the Fire Dynamics Simulator (FDS): smoke-speed
reduction, toxic gas dose (FED), dynamic rerouting and sign-based wayfinding,
on top of JuPedSim.

- Smoke-speed model from FDS extinction (visibility-based speed reduction)
- Purser FED as computed by
  [FDS+Evac](https://github.com/firemodels/fds/tree/c9da70d7a/Source), up to
  12 species; opt-in convective heat FED (ISO 13571), a separate dose that
  incapacitates but does not slow agents or enter route choice
- Dynamic smoke-based rerouting with smoke-gated exits; an exit-queue term is
  off by default
- Sign visibility and per-agent cognitive maps (`full` and `discovery`
  familiarity), through fdsvismap
- JuPedSim scenario loading and simulation

## Documentation

**<https://pedestriandynamics.org/pyFDS-Evac/>** has the model descriptions,
usage and verification:
[Install](https://pedestriandynamics.org/pyFDS-Evac/docs/getting-started/install/),
[Usage](https://pedestriandynamics.org/pyFDS-Evac/docs/using/usage/),
[Outputs](https://pedestriandynamics.org/pyFDS-Evac/docs/using/outputs/),
[Scenario JSON](https://pedestriandynamics.org/pyFDS-Evac/docs/using/scenario-json/)
(speed, size and pre-movement keys),
[models](https://pedestriandynamics.org/pyFDS-Evac/models/smoke-speed/) and the
[verification suite](https://pedestriandynamics.org/pyFDS-Evac/verification/).
Defaults follow FDS+Evac; see
[what changed](https://pedestriandynamics.org/pyFDS-Evac/docs/getting-started/coming-from-fds-evac/#defaults-follow-fdsevac)
and the [changelog](CHANGELOG.md). Talk:
[Visibility Seminar 2026](https://pedestriandynamics.org/pyFDS-Evac/talks/visibility-seminar-2026/).

## Installation

pyFDS-Evac needs Python 3.12, 3.13 or 3.14.

```bash
pip install pyfds-evac
pyfds-evac --help
```

`pyfds-evac init deck.fds` starts a scenario from an FDS or FDS+Evac deck
([guide](https://pedestriandynamics.org/pyFDS-Evac/docs/getting-started/start-from-fds-deck/)).
The package contains no scenarios; each example page offers its inputs as a
zip. pyFDS-Evac does not run FDS, it samples the output of a finished run, so
your deck must dump specific slices: read
[what your FDS case must provide](https://pedestriandynamics.org/pyFDS-Evac/docs/using/fds-case-requirements/)
first. Dependencies and pins (fdsvismap is pinned exactly) are in
[`pyproject.toml`](pyproject.toml).

## Development

To run the examples, scripts and tracked scenarios in [`assets/`](assets/)
([index](assets/README.md)), clone the repository and use
[uv](https://github.com/astral-sh/uv):

```bash
git clone https://github.com/PedestrianDynamics/pyFDS-Evac.git
cd pyFDS-Evac
uv sync
uv run run.py --scenario assets/ISO-table21
```

`run.py` has the same command line as `pyfds-evac`. Tests, the docs build and
pull requests: [Development](https://pedestriandynamics.org/pyFDS-Evac/docs/development/)
and [CONTRIBUTING.md](CONTRIBUTING.md).

## Terminal UI and web GUI

```bash
pip install "pyfds-evac[tui]" && pyfds-evac-tui   # for SSH; stops when the terminal closes
pip install "pyfds-evac[gui]" && pyfds-evac-gui   # local app at http://127.0.0.1:5001
```

See [Terminal UI](https://pedestriandynamics.org/pyFDS-Evac/docs/using/terminal-ui/)
and [Web GUI](https://pedestriandynamics.org/pyFDS-Evac/docs/using/web-gui/).

## Visualising agents

[fds-viewer](https://github.com/PedestrianDynamics/fds-viewer) renders the
trajectory SQLite in 3-D beside the FDS smoke. Run with `--output-sqlite`; with
FED computed, the file also carries `agent_scalars(frame, id, fed, heat_fed,
speed)`, which fds-viewer uses to colour agents. Name the columns when reading
it: `heat_fed` sits before `speed`.

## How pyFDS-Evac is built

pyFDS-Evac is a research code written and maintained by researchers in
pedestrian dynamics and fire safety. It is developed with generative AI coding
tools (Claude Code, with Codex as an independent reviewer; see
[AI_USAGE.md](AI_USAGE.md)). The AI tools are development aids, not scientific
authors: the named authors are responsible for the models, the results and the
maintenance, and the maintainer decides what merges and what ships. Nothing in
the software, its GUI or its TUI calls an AI service at runtime.

The [Fundamentals](https://pedestriandynamics.org/pyFDS-Evac/fundamentals/)
pages state the published laws the software rests on, with primary sources.
Where FDS+Evac has a counterpart, its default is kept and every departure is
documented in the
[model comparison](https://pedestriandynamics.org/pyFDS-Evac/docs/understanding/model-comparison/).
A change that can affect what the software computes starts with a written model
contract and regression tests, and is checked by an independent read-only step
before merging. The verification cases (ISO 20414, the FDS+Evac guide cases,
the FED equations) run in CI with every pull request. To cite the software, see
[CITATION.cff](CITATION.cff).

## Contributing

Contributions are made with whatever tools their authors choose and go
through the same review; see [CONTRIBUTING.md](CONTRIBUTING.md).

> [!IMPORTANT]
> We require all commits with AI-generated code to be flagged with
> a git trailer naming the model and the provider's no-reply address, e.g.:
> `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`

## References

The [model comparison](https://pedestriandynamics.org/pyFDS-Evac/docs/understanding/model-comparison/)
lists the sources section by section. Short summaries of the main papers
(Korhonen 2021, Börger et al. 2024, Haensel 2014, Schröder et al. 2020, Ronchi
et al. 2013, Haghani & Sarvi, Lovreglio et al.) are in
[`materials/`](materials/); the papers are not redistributed.

## License

pyFDS-Evac is released under the [MIT license](LICENSE). Two third-party parts
keep their own licenses and are not in the published packages:
[`assets/fds_evac_guide/`](assets/fds_evac_guide/) (GPL-3.0-only) and
`materials/evac.f90` (NIST software notice). [`REUSE.toml`](REUSE.toml) records
every file's license; CI checks it with `reuse lint`.
