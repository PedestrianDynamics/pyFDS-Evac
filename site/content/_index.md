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

<div class="hx-mb-6">
{{< hextra/hero-button text="Get started" link="docs/quickstart" >}}
</div>

<div class="hx-mb-6">
Research software, provided without warranty. Not intended for regulatory or design use.
</div>

<div class="hx-mt-6"></div>

{{< hextra/feature-grid >}}
  {{< hextra/feature-card
    title="Speed"
    subtitle="Extinction coefficient reduces walking speed with the Frantzich–Nilsson law (the linear FDS+Evac law), or Fridolf's non-linear law from Python. Irritant gases add a further slowdown."
  >}}
  {{< hextra/feature-card
    title="Dose"
    subtitle="Purser fractional effective dose as in the FDS+Evac guide, from up to 12 gas species, plus a convective heat dose accumulated separately. By default each agent stops at its own threshold."
  >}}
  {{< hextra/feature-card
    title="Route choice"
    subtitle="Optical depth integrated along the route the agent will actually walk refuses exits and orders the rest. Re-decided every second."
  >}}
  {{< hextra/feature-card
    title="Wayfinding"
    subtitle="fdsvismap decides which signs an agent can read through smoke. What it reads enters its cognitive map; staff know the building, visitors discover it."
  >}}
  {{< hextra/feature-card
    title="One-way coupling"
    subtitle="FDS runs once. Egress reads the stored slices through one sampling interface, so a synthetic field replaces FDS in tests and routing sweeps never re-run the fire."
  >}}
  {{< hextra/feature-card
    title="One entry point"
    subtitle="Script, test, command line, and the optional web GUI all call the same run_scenario(). Results are a JuPedSim trajectory file plus per-agent CSV histories."
  >}}
{{< /hextra/feature-grid >}}

<div class="content hx-mt-16">

## Installation

pyFDS-Evac is installed from the repository until the PyPI release, which waits
on an upstream fdsvismap merge.

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
  {{< card link="docs/quickstart" title="Quickstart" subtitle="One run on a tracked scenario, no FDS output needed." >}}
  {{< card link="docs/coming-from-fds-evac" title="Coming from FDS+Evac" subtitle="Where each FDS+Evac input goes, and what has no equivalent." >}}
  {{< card link="docs/walkthrough" title="Real-FDS walkthrough" subtitle="From tracked FDS output to doses and exit times." >}}
  {{< card link="docs/limitations" title="Limitations" subtitle="Status, library-level parameters, and what is not modelled." >}}
{{< /cards >}}

## Your own FDS case

Bringing your own FDS case? Read [what your FDS case must provide](docs/fds-case-requirements)
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
[Concepts](docs/concepts) and the talk
[*A Modular Workflow for Visibility-Aware Evacuation Modelling*](https://pedestriandynamics.org/pyFDS-Evac/talks/visibility-seminar-2026/)
([PDF](https://pedestriandynamics.org/pyFDS-Evac/talks/pyFDS-Evac_visibility_seminar_2026.pdf)).

</div>
