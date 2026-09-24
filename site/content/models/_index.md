---
title: Models
weight: 2
cascade:
  type: docs
---

The sub-models that turn FDS output into agent behaviour, one page each,
with the equations, the configuration keys, and the references. The
[documentation](/docs) section holds the full reference for each model;
these pages are the overview.

{{< cards >}}
  {{< card link="smoke-speed" title="Smoke-speed model" subtitle="Extinction coefficient to walking speed: Frantzich–Nilsson and Fridolf." >}}
  {{< card link="fed" title="Fractional effective dose" subtitle="ISO 13571 toxic gas dose, convective heat dose, irritant concentration." >}}
  {{< card link="routing" title="Dynamic route rerouting" subtitle="Smoke integrated along the route refuses and orders exits." >}}
  {{< card link="visibility" title="Visibility and cognitive maps" subtitle="Sign legibility through smoke decides what each agent knows." >}}
  {{< card link="verification" title="Verification suite" subtitle="Closed-form checks per model and behavioural scenarios through the coupling." >}}
{{< /cards >}}
