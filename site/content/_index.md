---
title: pyFDS-Evac
layout: hextra-home
---

{{< hextra/hero-badge link="https://github.com/PedestrianDynamics/pyFDS-Evac" >}}
  <span>Alpha, MIT licence</span>
  {{< icon name="arrow-circle-right" attributes="height=14" >}}
{{< /hextra/hero-badge >}}

<div class="hx-mt-6 hx-mb-6">
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
{{< hextra/hero-button text="Get started" link="docs/usage" >}}
</div>

<div class="hx-mt-6"></div>

{{< hextra/feature-grid >}}
  {{< hextra/feature-card
    title="Speed"
    subtitle="Extinction coefficient reduces walking speed with the Frantzich–Nilsson law used by FDS+Evac, or Fridolf's non-linear law. Irritants slow agents instantly and recover on leaving the plume."
  >}}
  {{< hextra/feature-card
    title="Dose"
    subtitle="Full ISO 13571 fractional effective dose from twelve species, plus a convective heat dose accumulated separately. Each agent stops at its own threshold."
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

## Installation

pyFDS-Evac is installed from the repository until the PyPI release, which waits
on an upstream fdsvismap merge.

```bash
pip install "pyfds-evac @ git+https://github.com/PedestrianDynamics/pyFDS-Evac.git"
```

For development, clone the repository and use [uv](https://github.com/astral-sh/uv):

```bash
git clone https://github.com/PedestrianDynamics/pyFDS-Evac.git
cd pyFDS-Evac
uv sync
uv run run.py --scenario assets/ISO-table21 --cleanup
```

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
