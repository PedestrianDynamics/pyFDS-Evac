---
title: Documentation
weight: 1
cascade:
  type: docs
  math: true
---

How to install, run and read pyFDS-Evac. Pick the path that fits you; each
page links to the next.

**New to pyFDS-Evac.** Install it, run one scenario, then read real FDS
output:

{{< cards >}}
  {{< card link="getting-started/install" title="Install" subtitle="Requirements, install, and a one-line check." >}}
  {{< card link="getting-started/quickstart" title="Quickstart" subtitle="One run on a tracked scenario, with no FDS output needed." >}}
  {{< card link="getting-started/walkthrough" title="Real-FDS walkthrough" subtitle="From tracked FDS output to FED histories and exit times, and how to spot a run that succeeds but is wrong." >}}
  {{< card link="getting-started/first-fds-case" title="A crowd in a fire" subtitle="150 agents, a 2 MW FDS fire, and a figure for every step." >}}
{{< /cards >}}

**Engineer with your own FDS case.** Prepare the deck, run, and read the
results:

{{< cards >}}
  {{< card link="using/fds-case-requirements" title="Your FDS case" subtitle="Which slices and yields a deck must provide, and the silent failure modes." >}}
  {{< card link="using/usage" title="Usage" subtitle="Running simulations, every CLI flag, and the post-processing scripts." >}}
  {{< card link="using/scenario-json" title="Scenario JSON" subtitle="The keys a scenario reads, with their defaults." >}}
  {{< card link="using/outputs" title="Outputs" subtitle="Every file a run writes, column by column, and how to read the results." >}}
  {{< card link="using/howto-rset-ensemble" title="RSET from an ensemble" subtitle="How to get RSET with its spread from runs over several seeds." >}}
  {{< card link="using/troubleshooting" title="Troubleshooting" subtitle="Error messages and warnings, with their cause and fix." >}}
  {{< card link="understanding/limitations" title="Limitations" subtitle="Research-software status, library-level parameters, and what is not modelled." >}}
{{< /cards >}}

**Coming from FDS+Evac.** Map your inputs, then check where the two tools
differ:

{{< cards >}}
  {{< card link="getting-started/coming-from-fds-evac" title="Coming from FDS+Evac" subtitle="Where each FDS+Evac input goes, and what has no equivalent." >}}
  {{< card link="understanding/model-comparison" title="FDS+Evac comparison" subtitle="Mechanism by mechanism against FDS+Evac, where the two agree and where they differ." >}}
{{< /cards >}}

**Understanding the models, maintaining the code.** The ideas, the code
paths, and the evidence:

{{< cards >}}
  {{< card link="understanding/concepts" title="Concepts" subtitle="Speed, route choice and wayfinding: the ideas behind the models, with figures." >}}
  {{< card link="implementation/speed" title="Speed in practice" subtitle="Configuration, API, and the ISO 20414 Table 21 runs." >}}
  {{< card link="implementation/routing/routing" title="Routing in practice" subtitle="Cost formulas, the exposure gate, and the decision pipeline." >}}
  {{< card link="implementation/routing/route-cost-gate" title="Gate model in practice" subtitle="How one quantity refuses a route and orders the survivors." >}}
  {{< card link="implementation/wayfinding" title="Wayfinding in practice" subtitle="Sign legibility, per-agent cognitive maps, and the examples of the talk." >}}
  {{< card link="implementation/fds-sampling" title="FDS slice sampling" subtitle="How slice values are read at agent positions." >}}
  {{< card link="../verification/" title="Verification" subtitle="Each model checked against hand calculations, published tables and FDS output." >}}
  {{< card link="../talks/" title="The talk" subtitle="Visibility Seminar 2026 slides: the theory behind speed, routing and wayfinding." >}}
{{< /cards >}}
