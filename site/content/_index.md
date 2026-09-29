---
title: pyFDS-Evac
layout: hextra-home
---

{{< hextra/hero-badge link="https://github.com/PedestrianDynamics/pyFDS-Evac" >}}
  <span>Alpha, MIT licence</span>
  {{< icon name="arrow-circle-right" attributes="height=14" >}}
{{< /hextra/hero-badge >}}

<div class="hx-mt-6 hx-mb-6 hx-flex hx-items-center hx-gap-6">
<img src="images/logo.png" alt="" width="96" height="96" style="border-radius:16px; flex:none">
{{< hextra/hero-headline >}}
  Visibility-aware evacuation&nbsp;<br class="sm:hx-block hx-hidden" />modelling on FDS output
{{< /hextra/hero-headline >}}
</div>

<div class="hx-mb-12">
{{< hextra/hero-subtitle >}}
  A Python library that couples a finished Fire Dynamics Simulator run to&nbsp;<br class="sm:hx-block hx-hidden" />JuPedSim agents: smoke slows them, dose stops them, smoke along a route&nbsp;<br class="sm:hx-block hx-hidden" />changes their exit, and sign legibility decides which exits they know.
{{< /hextra/hero-subtitle >}}
</div>

<div class="hx-mb-6 hx-flex hx-flex-wrap hx-items-center hx-gap-4">
{{< hextra/hero-button text="Quickstart" link="docs/getting-started/quickstart/" >}}
{{< hextra/hero-button text="Coming from FDS+Evac" link="docs/getting-started/coming-from-fds-evac/" >}}
{{< hextra/hero-button text="Documentation" link="docs/" >}}
</div>

<div class="content hx-mb-6">
Research software, provided without warranty. Not intended for regulatory or design use.
</div>

<div class="content hx-mb-6">
Defaults follow <a href="https://github.com/firemodels/fds/tree/c9da70d7a/Source">FDS+Evac</a>; see <a href="docs/getting-started/coming-from-fds-evac/#defaults-follow-fdsevac">what changed</a>.
</div>

<div class="hx-mt-6"></div>

{{< hextra/feature-grid >}}
  {{< hextra/feature-card
    title="Speed"
    subtitle="Extinction coefficient reduces walking speed with the Frantzich–Nilsson law (the linear FDS+Evac law), or the `fridolf` option (Fridolf et al. 2019, Eq. 7), from Python, with an optional irritant slowdown."
    link="fundamentals/walking-speed/"
  >}}
  {{< hextra/feature-card
    title="Dose"
    subtitle="Purser fractional effective dose as computed by FDS+Evac (the FED function of FDS), from up to 12 gas species, plus an opt-in convective heat dose accumulated separately. By default every agent stops at FED 1, as in FDS+Evac."
    link="models/fed/"
  >}}
  {{< hextra/feature-card
    title="Route choice"
    subtitle="Optical depth integrated along the route the agent will actually walk refuses exits and orders the rest. Re-decided every second, the run.py default (--reroute-interval)."
    link="models/routing/"
  >}}
  {{< hextra/feature-card
    title="Wayfinding"
    subtitle="fdsvismap decides which signs an agent can read through smoke. What it reads enters its cognitive map; fully familiar agents know the building, discovery agents learn it."
    link="models/wayfinding/"
  >}}
  {{< hextra/feature-card
    title="Verification"
    subtitle="Each model checked against hand calculations, published tables and FDS's own output, one page per test with the setup, the expected value and the simulated result."
    link="verification/"
  >}}
  {{< hextra/feature-card
    title="One-way coupling"
    subtitle="FDS runs once. Egress reads the stored slices through one sampling interface, so a synthetic field replaces FDS in tests and routing sweeps never re-run the fire."
    link="docs/understanding/concepts/#one-way-coupling-and-the-data-flow"
  >}}
  {{< hextra/feature-card
    title="One entry point"
    subtitle="Script, test, command line, and the optional web GUI all call the same run_scenario(); run.py and the GUI also build the same models for it. Results are a JuPedSim trajectory file plus per-agent CSV histories."
    link="docs/using/usage/"
  >}}
{{< /hextra/feature-grid >}}

<div class="content hx-mt-16">

## Installation

pyFDS-Evac is installed from the repository until the PyPI release, which waits
on an upstream fdsvismap merge. Requirements (Python 3.11 or 3.12, uv, git) and
a check that the install works are on the [Install](docs/getting-started/install/) page.

```bash
pip install "pyfds-evac @ git+https://github.com/PedestrianDynamics/pyFDS-Evac.git"
```

The examples and the tracked scenarios live in the repository (`examples/`,
`assets/`), not in the installed package. To run them, clone the repository and
use [uv](https://github.com/astral-sh/uv):

```bash
git clone https://github.com/PedestrianDynamics/pyFDS-Evac.git
cd pyFDS-Evac
uv sync
uv run python run.py --scenario assets/ISO-table21 --cleanup
```

## Where to start

{{< cards >}}
  {{< card link="docs/getting-started/install/" title="Install" subtitle="Requirements, install, and a one-line check." >}}
  {{< card link="docs/getting-started/quickstart/" title="Quickstart" subtitle="One run on a tracked scenario, no FDS output needed." >}}
  {{< card link="docs/getting-started/coming-from-fds-evac/" title="Coming from FDS+Evac" subtitle="Where each FDS+Evac input goes, and what has no equivalent." >}}
  {{< card link="docs/getting-started/walkthrough/" title="Real-FDS walkthrough" subtitle="From tracked FDS output to doses and exit times." >}}
  {{< card link="docs/understanding/limitations/" title="Limitations" subtitle="Status, library-level parameters, and what is not modelled." >}}
{{< /cards >}}

## Your own FDS case

Bringing your own FDS case? Read [what your FDS case must provide](docs/using/fds-case-requirements/)
first: pyFDS-Evac does not run FDS, it samples the output of a finished run, and
the deck has to dump specific slices for that to work.

## Workflow

| Library | Role |
|---|---|
| [FDS](https://github.com/firemodels/fds) | Fire physics. Writes slices: extinction coefficient, temperature, CO, CO₂, O₂, HCN, irritants. |
| [fdsreader](https://github.com/FireDynamics/fdsreader) | Nearest-neighbour lookup of any slice quantity at a time and position. |
| [fdsvismap](https://github.com/FireDynamics/fdsvismap) | Per sign and time: which floor cells can read it, Beer–Lambert along the sight line. |
| pyFDS-Evac | Speed factor, dose, route ranking, cognitive maps. Decides where each agent goes and how fast. |
| [JuPedSim](https://jupedsim.org) | Moves agents collision-free on the walkable area. |

pyFDS-Evac adds no movement model and no fire model.

For the ideas behind speed, route choice and wayfinding, read
[Concepts](docs/understanding/concepts/) and the talk
[*A Modular Workflow for Visibility-Aware Evacuation Modelling*](https://pedestriandynamics.org/pyFDS-Evac/talks/visibility-seminar-2026/).

</div>
