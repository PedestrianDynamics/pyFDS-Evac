---
title: Fundamentals
weight: 2
cascade:
  type: docs
  math: true
---

The published laws that fire-safety engineering uses to judge whether
occupants can escape a fire: the egress timeline, the design fire, smoke obscuration,
walking speed in smoke, toxic and thermal dose, and occupant decisions.
These pages are written for PhD students and pedestrian-dynamics engineers
who are new to fire toxicology and human behaviour in fire.

Smoke from a fire rises, forms a hot layer under the ceiling and spreads
through the building. Its hazards to occupants are heat and toxic gases
carried in the smoke, and the obscuration the smoke causes (Engineers
Australia Society of Fire Safety 2014, §3.1).

{{< svg-figure src="images/concepts/fire-hazards.svg" min-width="34rem" >}}

*Hazards of a building fire, as a sketch, not to scale. The sketch shows
mechanisms only; it states no acceptance criteria and no software
defaults. Figure inspired by Fig. 1 of the Engineers Australia practice
note for tenability criteria (2014).*

- **Convected heat**, the hot gas around the occupant:
  [Heat › Convective heat](/fundamentals/heat.md#convective-heat-time-to-incapacitation).
- **Radiant heat** from the flame and the hot layer:
  [Heat › Radiant heat](/fundamentals/heat.md#radiant-heat-pain-and-burns).
- **Toxic and irritant gases**: asphyxiants such as CO and HCN on
  [Asphyxiant fractional effective dose](/fundamentals/asphyxiant-fed.md),
  irritants such as HCl and acrolein on [Irritant gases](/fundamentals/irritants.md).
- **Smoke obscuration**: soot attenuates light
  ([Extinction coefficient](/fundamentals/extinction.md)), which shortens
  the distance at which signs can be read
  ([Visibility through smoke](/fundamentals/visibility.md)) and slows
  walking ([Walking speed in smoke](/fundamentals/walking-speed.md)).

Each page gives one published law: its quantity, its equation in the
source's own notation and constants, the data it rests on, its known limits,
and the primary citations. pyFDS-Evac defaults are on the Models pages. How
pyFDS-Evac implements a law, and where it
departs from the source, is on the [Models](/models/_index.md) pages. The
intuition behind the models is on the [Concepts](/docs/concepts.md) page.

For the full treatment, see Part VIII, Human Behavior (Ch. 65–72), of the
*SFPE Handbook of Fire Protection Engineering*, 6th ed.
([SFPE 2026](https://doi.org/10.1007/978-3-031-59212-6)).

{{< cards >}}
  {{< card link="aset-rset" title="ASET, RSET and the egress timeline" subtitle="Detection, warning, pre-travel activity and travel, against the time to untenable conditions." >}}
  {{< card link="design-fires" title="Design fires" subtitle="The t² growth law and its four classes, how growth is capped, and what a design fire represents." >}}
  {{< card link="extinction" title="Extinction coefficient" subtitle="Beer–Lambert attenuation, optical density and the mass-specific extinction coefficient." >}}
  {{< card link="visibility" title="Visibility through smoke" subtitle="Jin's V = C/K, where C comes from, and how it changes in dim light." >}}
  {{< card link="walking-speed" title="Walking speed in smoke" subtitle="Jin, Frantzich and Nilsson, Fridolf et al., and the fractional versus absolute readings." >}}
  {{< card link="asphyxiant-fed" title="Asphyxiant fractional effective dose" subtitle="CO, HCN, CO₂ hyperventilation and low-oxygen hypoxia after Purser and ISO 13571." >}}
  {{< card link="irritants" title="Irritant gases" subtitle="FEC as a separate endpoint in ISO 13571; FIC and FLD in Purser." >}}
  {{< card link="heat" title="Heat" subtitle="Convective and radiant heat: separate equations, separate endpoints." >}}
  {{< card link="incapacitation-thresholds" title="Incapacitation thresholds" subtitle="FED 1 against 0.3, the log-normal assumption, and what its population basis is." >}}
  {{< card link="pre-movement" title="Pre-movement time" subtitle="Why the longest part of escape is often spent before anyone moves." >}}
  {{< card link="exit-choice" title="Exit choice and familiarity" subtitle="Movement to the familiar, social influence and discrete-choice models." >}}
{{< /cards >}}

## Sources

- Engineers Australia Society of Fire Safety (2014). *Practice note for
  tenability criteria in building fires*, version 2.0, 3 April 2014.
  Society of Fire Safety, NSW Chapter, Engineers Australia.
  [engineersaustralia.org.au](https://www.engineersaustralia.org.au/sites/default/files/2024-01/tenability-criteria-practice-note_0.pdf).
  §3.1 and Fig. 1, p. 7.
