# Contributing to pyFDS-Evac

Everyone is welcome to contribute. Code contributions include new features and
bug fixes. Documentation and website contributions include new pages,
corrections, examples and figures. Documentation matters as much as code.

pyFDS-Evac is research software developed at Forschungszentrum Jülich (IAS-7),
provided without warranty and not intended for regulatory or design use; see
[LICENSE](LICENSE) and [Limitations](docs/limitations.md). The maintainers are
listed in [CODEOWNERS](.github/CODEOWNERS). Versions follow Semantic
Versioning, and notable changes are listed in [CHANGELOG.md](CHANGELOG.md).

## How to contribute

1. [Open an issue](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/new/choose)
   with the bug report, feature request or documentation template.
2. [Fork the repository](https://github.com/PedestrianDynamics/pyFDS-Evac/fork)
   and make your change on a branch.
3. Open a pull request that links the issue (`Fixes #123` or `Refs #123`) and
   work through the checklist in the
   [pull request template](.github/pull_request_template.md).

## Before you open a pull request

```bash
uv sync --all-groups
uv run ruff check . && uv run ruff format --check .
uv run pytest -q
```

For changes to the website, build it as described in
[Development](docs/development.md#build-the-documentation).

## Questions, conduct and security

Ask questions in an [issue](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/new/choose).
By taking part you agree to the [Code of Conduct](CODE_OF_CONDUCT.md). Report
security problems privately as described in [SECURITY.md](SECURITY.md).

## Licence

pyFDS-Evac is released under the [MIT License](LICENSE). By submitting a
contribution you agree that it is licensed under the same terms. There is no
contributor licence agreement.

Development setup, CI details, docs build, commit style and versioning:
[Development](docs/development.md).
