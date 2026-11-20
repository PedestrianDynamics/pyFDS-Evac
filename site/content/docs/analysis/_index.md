---
title: Analysis
weight: 4
---

What to compute from a finished run and from FDS output: when the fire makes
each place untenable, when each place is last occupied, and who wins. These
pages post-process. They change nothing in a simulation. The sub-models that
produce the fire's effect on agents are on [Models](/models/_index.md).

{{< cards >}}
  {{< card link="aset-rset-maps" title="ASET, RSET and DIFF maps" subtitle="The map of when each cell becomes untenable, when it is last occupied, and their difference, with the criteria and the limits." >}}
  {{< card link="howto-aset-rset-check" title="How-to: ASET/RSET check with FED" subtitle="Check each agent against the time a limit is reached, with the per-agent exposure summary." >}}
  {{< card link="howto-rset-ensemble" title="How-to: egress time from an ensemble" subtitle="How to get RSET with its spread from runs over several seeds." >}}
{{< /cards >}}

The Schröder et al. (2020) demonstration, re-run with our own fire and crowds,
is the study [ASET-RSET maps after Schröder et al. (2020)](/docs/study-schroeder2020.md).
