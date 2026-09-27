# Contributing to pyFDS-Evac

pyFDS-Evac is maintained by one researcher at Forschungszentrum Jülich
([@chraibi](https://github.com/chraibi)). It is research software, provided
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

The project uses [uv](https://github.com/astral-sh/uv) and Python 3.11, as in
CI:

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

CI runs a fixed list of test files; see
[`.github/workflows/tests.yml`](.github/workflows/tests.yml).

The docs are a Hugo site (hextra theme) in `site/`, with the reference pages in
`docs/` mounted into it. The strict build needs Hugo extended (CI uses 0.144)
and Go:

```bash
uv run pytest tests/test_docs_defaults.py tests/test_examples.py -q
cd site && hugo --minify --panicOnWarning -e production
```

Delete `site/public` afterwards; it is not committed.

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
