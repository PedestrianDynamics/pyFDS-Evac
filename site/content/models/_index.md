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

{{< svg-figure src="images/concepts/model-responses.svg" min-width="34rem" >}}

*What pyFDS-Evac does with each hazard of the
[Fundamentals](/fundamentals/_index.md) figure. A sketch, not to scale:
it shows implemented behaviour, not a simulation result. Which models run
depends on the configuration and on the slices in the FDS output. Figure
inspired by Fig. 1 of the Engineers Australia practice note for
tenability criteria (2014).*

Walking speed, route smoke, sign legibility and the gas and heat doses read the horizontal
FDS slice nearest `--smoke-slice-height`: 1.6 m by default, the `HUMAN_SMOKE_HEIGHT` of
[FDS+Evac](https://github.com/firemodels/fds/tree/c9da70d7a/Source). This
holds for extinction, the gas species, temperature and, when selected,
`INTEGRATED INTENSITY`. The height is an absolute z in the FDS domain, not
a height above each floor. If the nearest slice is more than 0.5 m away,
the run logs a warning and carries on at that slice's height, so check the
slice elevations in your case ([FDS slice sampling](/docs/fds-sampling.md)).
`--heat-regime layer` also reads a `TEMPERATURE` slice at
`--heat-layer-height`.

Where a value is read depends on the model. Walking speed and the gas and
heat doses use the value at the agent's position. Route smoke is sampled
along each candidate route. Sign legibility averages the extinction
along the straight line, in plan, from the agent's cell to the sign, on that
one extinction slice ([Wayfinding](/models/wayfinding.md)). It is a 2-D line
on one slice, not a 3-D ray up to the sign.

- **Smoke obscuration** (on by default). The extinction coefficient *K*
  sets each agent's walking-speed factor
  ([Smoke-speed model](/models/smoke-speed.md)), and the smoke along each
  route refuses and orders exits
  ([Dynamic route rerouting](/models/routing.md)). For agents not fully
  familiar with the building, sign legibility through smoke decides which
  exits they learn ([Wayfinding](/models/wayfinding.md)). Smoke is not the
  only routing input: when the gas FED model is loaded, a route whose
  projected gas FED exceeds `fed_rejection_threshold` (1.0) is refused
  under both cost models.
- **Toxic and irritant gases** (on by default when the case has CO, CO₂
  and O₂ slices). Each agent accumulates a gas FED, irritants included,
  and by default stops once it reaches 1. The threshold is
  `--fed-threshold` (default 1.0); every agent has the same threshold
  unless `--incapacitation-mode probabilistic`. With
  `--disable-tenability` nobody stops, but the FED is still accumulated.
  Slowing by irritants (FIC) is opt-in, `--enable-fic-speed`
  ([Fractional effective dose](/models/fed.md)).
- **Convected heat** (opt-in, `--enable-heat-fed`). A heat dose from the
  gas temperature, kept apart from the gas FED; it can incapacitate an
  agent by itself. Heat does not slow agents and plays no part in route
  choice ([Heat](/models/heat.md)).
- **Radiant heat** (opt-in, `--heat-fed-method total-flux`). A radiant
  term inside the one heat dose, not a second dose. It comes from the gas
  at the head by default, from a hot layer with `--heat-regime layer`, or
  from the FDS `INTEGRATED INTENSITY` slice with
  `--heat-radiant-source integrated-intensity`
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
