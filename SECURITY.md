# Security policy

## Supported versions

Only the `main` branch is supported: security fixes land there. Releases
(currently `v0.2.0`) and older revisions are not patched.

## Reporting a vulnerability

Do not open a public issue. Report it privately through GitHub's private
vulnerability reporting: on the
[Security tab](https://github.com/PedestrianDynamics/pyFDS-Evac/security), click
**Report a vulnerability**. Include the commit, the steps to reproduce and what
an attacker could do.

The project is maintained by a small research team (see
[CODEOWNERS](.github/CODEOWNERS)), so replies are best effort.

## Scope

pyFDS-Evac is research software, provided without warranty (see
[LICENSE](LICENSE)). It is not intended for safety-critical, design or
regulatory use, and a simulation result is not an assessment of a building.
A model that gives a physically wrong answer is a bug: report it as an
[issue](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/new/choose),
not here.
