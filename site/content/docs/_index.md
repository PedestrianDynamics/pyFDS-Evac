---
title: Documentation
weight: 1
cascade:
  type: docs
---

Reference documentation, served from the `docs/` directory of the repository.

{{< cards >}}
  {{< card link="getting-started/quickstart" title="Quickstart" subtitle="One run on a tracked scenario, with no FDS output needed." >}}
  {{< card link="getting-started/walkthrough" title="Real-FDS walkthrough" subtitle="From tracked FDS output to FED histories and exit times, and how to spot a run that succeeds but is wrong." >}}
  {{< card link="using/howto-rset-ensemble" title="RSET from an ensemble" subtitle="How to get RSET with its spread from runs over several seeds." >}}
  {{< card link="getting-started/coming-from-fds-evac" title="Coming from FDS+Evac" subtitle="Where each FDS+Evac input goes, and what has no equivalent." >}}
  {{< card link="understanding/limitations" title="Limitations" subtitle="Research-software status, library-level parameters, and what is not modelled." >}}
  {{< card link="understanding/concepts" title="Concepts" subtitle="Speed, route choice and wayfinding: the ideas behind the models, with figures." >}}
  {{< card link="https://pedestriandynamics.org/pyFDS-Evac/talks/visibility-seminar-2026/" title="The talk" subtitle="Visibility Seminar 2026 slides: the theory behind speed, routing and wayfinding." >}}
  {{< card link="using/usage" title="Usage" subtitle="Running simulations, every CLI flag, and the post-processing scripts." >}}
  {{< card link="using/fds-case-requirements" title="Your FDS case" subtitle="Which slices and yields a deck must provide, and two silent failure modes." >}}
  {{< card link="implementation/speed" title="Speed in practice" subtitle="Configuration, API, and the ISO 20414 Table 21 runs." >}}
  {{< card link="implementation/routing/routing" title="Routing in practice" subtitle="Cost formulas, the exposure gate, and the decision pipeline." >}}
  {{< card link="implementation/routing/route-cost-gate" title="Gate model in practice" subtitle="How one quantity refuses a route and orders the survivors." >}}
  {{< card link="implementation/wayfinding" title="Wayfinding in practice" subtitle="Sign legibility, per-agent cognitive maps, and the examples of the talk." >}}
  {{< card link="understanding/model-comparison" title="FDS+Evac comparison" subtitle="Mechanism by mechanism against FDS+Evac, where the two agree and where they differ." >}}
{{< /cards >}}
