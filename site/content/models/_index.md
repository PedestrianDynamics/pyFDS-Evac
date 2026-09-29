---
title: Models
weight: 3
cascade:
  type: docs
---

The sub-models that turn FDS output into agent behaviour, one page each,
with the equations, the configuration keys, and the references. The
[documentation](/docs/) section holds the full reference for each model;
these pages are the overview.

{{< svg-figure src="images/concepts/model-responses.svg" >}}

*What pyFDS-Evac does with each hazard of the
[Fundamentals](/fundamentals/_index.md) figure. A sketch, not to scale.
Figure inspired by Fig. 1 of the Engineers Australia practice note for
tenability criteria (2014).*

Every quantity is read from the FDS slices at the agent's position, at
`--smoke-slice-height`: 1.6 m by default, the `HUMAN_SMOKE_HEIGHT` of
[FDS+Evac](https://github.com/firemodels/fds/tree/c9da70d7a/Source).

- **Smoke obscuration** (on by default). The extinction coefficient *K*
  sets each agent's walking-speed factor
  ([Smoke-speed model](/models/smoke-speed.md)), and the smoke along each
  route refuses and orders exits
  ([Dynamic route rerouting](/models/routing.md)). For agents not fully
  familiar with the building, sign legibility through smoke decides which
  exits they learn ([Wayfinding](/models/wayfinding.md)).
- **Toxic and irritant gases** (on by default when the case has CO, CO₂
  and O₂ slices). Each agent accumulates a gas FED, irritants included,
  and stops once it reaches 1; every agent has the same threshold unless
  `--incapacitation-mode probabilistic`. Slowing by irritants (FIC) is
  opt-in, `--enable-fic-speed`
  ([Fractional effective dose](/models/fed.md)).
- **Convected heat** (opt-in, `--enable-heat-fed`). A heat dose from the
  gas temperature, kept apart from the gas FED, with its own stop
  ([Heat](/models/heat.md)).
- **Radiant heat** (opt-in, `--heat-fed-method total-flux`). A radiant
  term in the heat dose: from the gas at the head by default, from a hot
  layer with `--heat-regime layer`, or from the FDS `INTEGRATED INTENSITY`
  slice with `--heat-radiant-source integrated-intensity`
  ([Heat › Total flux](/models/heat.md#total-flux)).

{{< cards >}}
  {{< card link="smoke-speed" title="Smoke-speed model" subtitle="Extinction coefficient to walking speed: Frantzich–Nilsson, and the `fridolf` option." >}}
  {{< card link="fed" title="Fractional effective dose" subtitle="Purser toxic gas dose, convective heat dose, irritant concentration." >}}
  {{< card link="heat" title="Heat" subtitle="Opt-in convective heat dose and thermal incapacitation." >}}
  {{< card link="routing" title="Dynamic route rerouting" subtitle="Smoke integrated along the route refuses and orders exits." >}}
  {{< card link="wayfinding" title="Wayfinding" subtitle="Sign legibility through smoke decides what each agent knows." >}}
{{< /cards >}}

## Sources

- Engineers Australia Society of Fire Safety (2014). *Practice note for
  tenability criteria in building fires*, version 2.0, 3 April 2014.
  Society of Fire Safety, NSW Chapter, Engineers Australia.
  [engineersaustralia.org.au](https://www.engineersaustralia.org.au/sites/default/files/2024-01/tenability-criteria-practice-note_0.pdf).
  Fig. 1, p. 7.
