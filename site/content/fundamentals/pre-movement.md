---
title: "Pre-movement time"
weight: 9
---

Pre-movement time, also called pre-travel activity time or pre-evacuation
time, \(t_{\mathrm{pre}}\) [s], is the interval between the alarm or first
cue and the first deliberate movement towards safety. It is a term of the
required safe escape time (RSET; see [ASET and RSET](/fundamentals/aset-rset.md)).

## Definition as published

The Society of Fire Protection Engineers (SFPE) Handbook defines \(t_{\mathrm{pre}}\) as the interval between the
time at which a general alarm or warning is given and the time at which the
first deliberate evacuation movement is made, and splits it into a
recognition time, from perceiving the alarm to interpreting it as an
emergency, and a response time, from recognition to the first move
(Gwynne and Boyce 2016, Ch. 64). ISO/TR 16738:2009 (§5.7) uses the same two
elements and distinguishes the pre-travel time of the first occupants from
the distribution of pre-travel times over the whole group. There is no
equation for \(t_{\mathrm{pre}}\): it is taken from observed distributions.

## Why it is long

ISO/TR 16738 (§5.4) reports that the pre-travel activity phase can often be
the longest part of the total escape time. Response time includes activities
such as fighting the fire, warning others, gathering family members,
dressing, collecting belongings and calling the fire service (Ch. 64).
Kuligowski (2016, Ch. 58) explains these delays with the Protective Action
Decision Model, in which environmental cues such as the sight of smoke and
social cues such as warnings interrupt normal activity only if they are
perceived as a threat; the occupant then seeks more information, protects
people or property, or resumes normal activity, depending on the perceived
threat and on whether protective action seems feasible.

## The data

Lovreglio, Kuligowski, Gwynne and Boyce (2019) assembled pre-evacuation times
from 9 fire incidents and 103 evacuation drills, covering 13 591 evacuees in
16 countries, grouped by occupancy type and clustered to identify
sub-groups. They fitted gamma, log-normal, log-logistic and Weibull
distributions, all two-parameter, positive and right-skewed, for use as
model inputs (their Eqs. 2–5). The database extends the tables of Gwynne and Boyce (2016,
Ch. 64). A corrigendum was published in 2019. ISO/TR 16738 (Annex E) gives
guidance and default pre-travel times from published data.

## Known limits

Drills make up 103 of the 112 data sets, so the database describes drills
far more than fires. The authors could not definitively
establish the factors that generated the clusters, and advise users to pick
the occupancy and cluster closest to their case and to consult the original
sources. Pre-movement and travel times within an enclosure interact, so the
two distributions cannot simply be added (ISO/TR 16738, §7).

## Sources

- ISO (2009). *ISO/TR 16738:2009 Fire-safety engineering — Technical
  information on methods for evaluating behaviour and movement of people*,
  §5.4, §5.7 and §7. ISO, Geneva.
  [iso.org/standard/42887](https://www.iso.org/standard/42887.html). Read
  from the public preview.
- Gwynne, S. M. V., & Boyce, K. E. (2016). *Engineering data*. SFPE
  Handbook of Fire Protection Engineering, 5th ed., Ch. 64, 2429–2551.
  [doi:10.1007/978-1-4939-2565-0_64](https://doi.org/10.1007/978-1-4939-2565-0_64)
- Kuligowski, E. D. (2016). *Human behavior in fire*. SFPE Handbook of
  Fire Protection Engineering, 5th ed., Ch. 58, 2070–2114.
  [doi:10.1007/978-1-4939-2565-0_58](https://doi.org/10.1007/978-1-4939-2565-0_58)
- Lovreglio, R., Kuligowski, E., Gwynne, S., & Boyce, K. (2019). *A
  pre-evacuation database for use in egress simulations*. Fire Safety
  Journal, 105, 107–128.
  [doi:10.1016/j.firesaf.2018.12.009](https://doi.org/10.1016/j.firesaf.2018.12.009).
  Corrigendum: Fire Safety Journal, 108, 102829.
  [doi:10.1016/j.firesaf.2019.102829](https://doi.org/10.1016/j.firesaf.2019.102829)
- Lovreglio, R., Ronchi, E., & Nilsson, D. (2015). *A model of the
  decision-making process during pre-evacuation*. Fire Safety Journal, 78,
  168–179.
  [doi:10.1016/j.firesaf.2015.07.001](https://doi.org/10.1016/j.firesaf.2015.07.001)
  (further reading; not summarised here).

How pyFDS-Evac uses this: see the [RSET ensemble how-to](/docs/howto-rset-ensemble.md).
