---
title: "Development"
weight: 90
---

Set up pyFDS-Evac for development, run the tests, build the documentation
and prepare a pull request. The short version is in
[CONTRIBUTING.md](https://github.com/PedestrianDynamics/pyFDS-Evac/blob/main/CONTRIBUTING.md).

pyFDS-Evac is research software, provided without warranty and not intended
for regulatory or design use; see
[LICENSE](https://github.com/PedestrianDynamics/pyFDS-Evac/blob/main/LICENSE)
and [Limitations](limitations.md).

## Issues

Open an [issue](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/new/choose)
and pick a template:

- **Bug report:** give the commit, the exact command, the scenario and, if an
  FDS run is involved, the FDS version. A report that can be rerun is much
  easier to fix.
- **Feature request:** say what you want to model and why. Features that do
  not exist yet are tracked as issues.
- **Documentation:** point to the wrong or unclear page. For a scientific
  claim, cite the primary source.

## Set up

The project uses [uv](https://github.com/astral-sh/uv) and supports Python
3.12, 3.13 and 3.14. CI tests all three on main and 3.12 and 3.14 on pull
requests; lint and docs run on 3.14.

```bash
git clone https://github.com/PedestrianDynamics/pyFDS-Evac.git
cd pyFDS-Evac
uv sync --all-groups     # add --all-extras for the web GUI and the terminal UI
```

## Test and lint

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
```

CI runs the whole suite with the `gui` extra. It deselects the tests marked
`external_data`, which need FDS output from the external data store; locally
they skip themselves when that data is absent. See
[`.github/workflows/tests.yml`](https://github.com/PedestrianDynamics/pyFDS-Evac/blob/main/.github/workflows/tests.yml).

### Coverage

CI measures line and branch coverage and reports it on
[Codecov](https://app.codecov.io/gh/PedestrianDynamics/pyFDS-Evac). To see
the report locally:

```bash
uv run --python 3.14 pytest -q --cov --cov-report=term
```

Measure coverage under Python 3.14, as CI does.

{{< details title="Why Python 3.14 for coverage" closed="true" >}}
Coverage measures branches (`branch = true`). coverage.py measures branches
with the fast `sys.monitoring` core only from Python 3.14 on. On 3.12 and 3.13
it falls back to its trace function, which is slow on `run_scenario`, one very
long function: on 3.12 the suite with coverage reached 8 % in 20 minutes. On
3.14 the whole suite with coverage takes about as long as without it.
{{< /details >}}

## Build the documentation

The docs are a Hugo site (hextra theme) in `site/`. The reference pages live
in `docs/` and are mounted into it. The strict build needs
[Hugo extended](https://gohugo.io/installation/) (CI uses 0.144.0) and Go.

```bash
uv run python scripts/docs/bundle_examples.py
uv run pytest -q tests/test_docs_defaults.py tests/test_examples.py \
  tests/test_heat_endpoint_docs.py tests/test_smoke_speed_widget.py \
  tests/test_example_downloads.py
cd site && hugo --minify --panicOnWarning -e production
```

`bundle_examples.py` builds the example downloads listed in
`site/data/examples.toml`; Hugo fails without them. The second command runs
the doc tests that CI runs. Delete `site/public` afterwards. Neither it nor
the zips are committed. See
[`.github/workflows/docs.yml`](https://github.com/PedestrianDynamics/pyFDS-Evac/blob/main/.github/workflows/docs.yml).

## Documentation rules

- The docs describe what the code does now. A feature that does not exist yet
  goes into an issue.
- The doc tests above check pages that quote code defaults or embed code
  from `examples/`. When you change the
  code, update the page.
- Figures come from the scripts in
  [`scripts/figures/`](https://github.com/PedestrianDynamics/pyFDS-Evac/tree/main/scripts/figures).
  Change the script, rerun it and commit the image. CI reruns every script on
  each docs build and fails if one no longer runs.
- Do not add FDS output to the repository; point to the case instead. The
  small verification fixtures already committed (e.g.
  `assets/iso_table21_coupled`) stay.

## Commits and pull requests

- **Tests first for fixes.** Add a test that fails on `main`, then fix the
  code.
- **Small pull requests.** One change per pull request; link the issue
  (`Fixes #123` or `Refs #123`).
- **Kernel-style commit messages.** An imperative subject of at most 50
  characters with an optional `area:` prefix (`visibility:`, `route_graph:`,
  `docs:`, `tests:`) and no trailing period, then a blank line, then a body
  wrapped at 72 columns that says what changed and why.

## Versioning

pyFDS-Evac follows [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html).
Notable changes are listed in
[CHANGELOG.md](https://github.com/PedestrianDynamics/pyFDS-Evac/blob/main/CHANGELOG.md),
in the [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format.

- Versions are `MAJOR.MINOR.PATCH`, and release tags are `vX.Y.Z`
  (`v0.2.0`).
- While MAJOR is 0, a breaking change bumps MINOR and a fix bumps PATCH.
  Breaking changes include removed or renamed CLI flags, changed output
  columns, changed defaults, changed exit codes and changes to the public
  API.
- A released version is never retagged or reused. A fix ships as a new
  version.
- The tag `v0.1` predates this convention; it is release 0.1.0.
