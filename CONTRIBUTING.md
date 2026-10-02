# Contributing to pyFDS-Evac

pyFDS-Evac is developed at Forschungszentrum Jülich (IAS-7); its maintainers
are listed in [CODEOWNERS](.github/CODEOWNERS). It is research software, provided
without warranty, and not intended for regulatory or design use (see
[LICENSE](LICENSE) and [docs/limitations.md](docs/limitations.md)). There is no
release policy yet, so behaviour and defaults can change between commits.

By taking part you agree to the [Code of Conduct](CODE_OF_CONDUCT.md).
Security problems go through [SECURITY.md](SECURITY.md), not public issues.

## Reporting bugs and proposing features

Open an [issue](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/new/choose)
and pick a template:

- **Bug report:** the commit, the exact command, the scenario and, if an FDS
  run is involved, the FDS version. A report that can be rerun is much
  easier to fix.
- **Feature request:** what you want to model and why. Features that do not
  exist yet are tracked as issues, not described in the docs.
- **Documentation:** a wrong or unclear page. For a scientific claim, cite the
  primary source.

## Development setup

The project uses [uv](https://github.com/astral-sh/uv) and supports Python
3.12, 3.13 and 3.14; CI tests all three, and lint and docs run on 3.14:

```bash
git clone https://github.com/PedestrianDynamics/pyFDS-Evac.git
cd pyFDS-Evac
uv sync --all-groups     # add --all-extras for the web GUI
```

## Tests, lint and docs build

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
```

CI runs the whole suite with the `gui` extra and deselects the tests marked
`external_data`, which need FDS output from the external data store; see
[`.github/workflows/tests.yml`](.github/workflows/tests.yml).

CI also measures line and branch coverage and reports it on
[Codecov](https://app.codecov.io/gh/PedestrianDynamics/pyFDS-Evac). To see the
report locally:

```bash
uv run --python 3.14 pytest -q --cov --cov-report=term
```

Measure coverage under Python 3.14, as above and as in CI. Coverage measures
branches (`branch = true`), and coverage.py measures branches with the fast
`sys.monitoring` core only from Python 3.14 on. On 3.12 and 3.13 it falls back
to its trace function, which slows `run_scenario`, one very long function, by
two orders of magnitude, and the suite takes hours.

The docs are a Hugo site (hextra theme) in `site/`, with the reference pages in
`docs/` mounted into it. The strict build needs Hugo extended (CI uses 0.144)
and Go:

```bash
uv run pytest tests/test_docs_defaults.py tests/test_examples.py -q
uv run python scripts/docs/bundle_examples.py
cd site && hugo --minify --panicOnWarning -e production
```

`bundle_examples.py` builds the example downloads that
`site/data/examples.toml` lists; Hugo fails without them. Delete
`site/public` afterwards; it is not committed, and neither are the zips.

## Commits and pull requests

- **Tests first for fixes.** Add a test that fails on `main`, then fix it.
- **Small PRs.** One change per PR; link the issue (`Fixes #123` or
  `Refs #123`).
- **Commit messages** in kernel style: an imperative subject of at most
  50 characters with an optional `area:` prefix (`visibility:`,
  `route_graph:`, `docs:`, `tests:`), no trailing period, a blank line, and a
  body wrapped at 72 columns that says what changed and why.

## Documentation

- The docs describe what the code does now. A feature that does not exist yet
  goes into an issue, not onto a page.
- Pages that quote code defaults or embed code from `examples/` are checked by
  `tests/test_docs_defaults.py` and `tests/test_examples.py`; update the page
  when you change the code.
- Figures are made by the scripts in [`scripts/figures/`](scripts/figures/).
  Change the script, rerun it, and commit the image; CI reruns every script on
  each docs build and fails if one no longer runs.
- Do not add FDS output to the repository; point to the case instead. The
  small verification fixtures already committed (e.g.
  `assets/iso_table21_coupled`) stay.

## Licence

pyFDS-Evac is released under the [MIT License](LICENSE). By submitting a
contribution you agree that it is licensed under the same terms. There is no
contributor licence agreement.
