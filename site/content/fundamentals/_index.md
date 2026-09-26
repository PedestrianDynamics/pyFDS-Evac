---
title: Fundamentals
weight: 2
cascade:
  type: docs
  math: true
---

The published laws that fire-safety engineering uses to judge whether
occupants can escape a fire: the egress timeline, smoke obscuration,
walking speed in smoke, toxic and thermal dose, and occupant decisions.
These pages are written for PhD students and pedestrian-dynamics engineers
who are new to fire toxicology and human behaviour in fire.

Fundamentals is about the literature, not about this code. Each page gives
one quantity, its equation in the source's own notation and constants, the
data it rests on, its known limits, and the primary citations. Nothing here
states a pyFDS-Evac default. How pyFDS-Evac implements a law, and where it
departs from the source, is on the [Models](/models/_index.md) pages. The
intuition behind the models is on the [Concepts](/docs/concepts.md) page.

These pages are summaries, not a textbook. For the full treatment, read the
*SFPE Handbook of Fire Protection Engineering*, 5th ed.
([Hurley et al. 2016](https://doi.org/10.1007/978-1-4939-2565-0)),
chapters 56–64, which most pages cite.

{{< cards >}}
  {{< card link="aset-rset" title="ASET, RSET and the egress timeline" subtitle="Detection, warning, pre-travel activity and travel, against the time to untenable conditions." >}}
  {{< card link="extinction" title="Extinction coefficient" subtitle="Beer–Lambert attenuation, optical density and the mass-specific extinction coefficient." >}}
  {{< card link="visibility" title="Visibility through smoke" subtitle="Jin's S = C/K and why C is a property of the sign." >}}
  {{< card link="walking-speed" title="Walking speed in smoke" subtitle="Jin, Frantzich and Nilsson, Fridolf et al., and the fractional versus absolute readings." >}}
  {{< card link="asphyxiant-fed" title="Asphyxiant fractional effective dose" subtitle="CO, HCN, CO₂ hyperventilation and low-oxygen hypoxia after Purser and ISO 13571." >}}
  {{< card link="irritants" title="Irritant gases" subtitle="FEC as a separate endpoint in ISO 13571; FIC and FLD in Purser." >}}
  {{< card link="heat" title="Heat" subtitle="Convective and radiant heat: separate equations, separate endpoints." >}}
  {{< card link="incapacitation-thresholds" title="Incapacitation thresholds" subtitle="FED 1 against 0.3, the log-normal assumption, and what its population basis is." >}}
  {{< card link="pre-movement" title="Pre-movement time" subtitle="Why the longest part of escape is often spent before anyone moves." >}}
  {{< card link="exit-choice" title="Exit choice and familiarity" subtitle="Movement to the familiar, social influence and discrete-choice models." >}}
{{< /cards >}}
