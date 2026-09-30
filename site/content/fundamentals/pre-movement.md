---
title: "Pre-movement time"
weight: 10
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
(Gwynne et al. 2026, Ch. 72, p. 2378). ISO/TR 16738:2009 (§5.7) uses the same two
elements and distinguishes the pre-travel time of the first occupants from
the distribution of pre-travel times over the whole group. There is no
equation for \(t_{\mathrm{pre}}\): it is taken from observed distributions.

## Why it is long

ISO/TR 16738 (§5.4) reports that the pre-travel activity phase can often be
the longest part of the total escape time. Occupants spend the pre-travel
time seeking information, alerting and assisting others, fighting the fire
and preparing to leave (Kuligowski and Kinateder 2026, Ch. 65, p. 2102), for
example by gathering belongings or getting dressed (Ch. 72, p. 2406).
Kuligowski and Kinateder (Ch. 65, pp. 2109–2110) explain these delays with the Protective Action
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
model inputs (their Eqs. 2–5). The database includes the data of the
previous edition of the SFPE Handbook's egress-data chapter (Ch. 72,
p. 2386). A corrigendum was published in 2019. ISO/TR 16738 (Annex E) gives
guidance and default pre-travel times from published data.

## Known limits

Drills make up 103 of the 112 data sets, so the database describes drills
far more than fires. The authors could not definitively
establish the factors that generated the clusters, and advise users to pick
the occupancy and cluster closest to their case and to consult the original
sources. Pre-movement and travel times within an enclosure interact, so the
two distributions cannot simply be added (ISO/TR 16738, §7).

The corrigendum corrects the log-normal *a* parameter in Tables 3, 5, 7, 9,
11, 13, 15, 17 and 18. Fits within a cluster have R² as low as about 0.55
(Business Cluster 1), and the authors state R² must not be used to choose
between clusters.

## Sources

- ISO (2009). *ISO/TR 16738:2009 Fire-safety engineering — Technical
  information on methods for evaluating behaviour and movement of people*,
  §5.4, §5.7 and §7. ISO, Geneva.
  [iso.org/standard/42887](https://www.iso.org/standard/42887.html). Read
  from the public preview.
- Gwynne, S. M. V., Boyce, K. E., & Lovreglio, R. (2026). *Egress data for
  engineering analysis*. SFPE Handbook of Fire Protection Engineering,
  6th ed., Ch. 72, 2375–2484. pp. 2378, 2386, 2406.
  [doi:10.1007/978-3-031-59212-6_72](https://doi.org/10.1007/978-3-031-59212-6_72)
- Kuligowski, E. D., & Kinateder, M. (2026). *Human behavior in fire in the
  built environment*. SFPE Handbook of Fire Protection Engineering, 6th ed.,
  Ch. 65, 2099–2137. pp. 2102, 2109–2110.
  [doi:10.1007/978-3-031-59212-6_65](https://doi.org/10.1007/978-3-031-59212-6_65)
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

How pyFDS-Evac uses this: the presets and their sources are in
[Coming from FDS+Evac › Pre-movement parameters](/docs/coming-from-fds-evac.md#pre-movement-parameters),
the scenario keys in [Scenario JSON](/docs/scenario-json.md), and a worked
ensemble in the [RSET ensemble how-to](/docs/howto-rset-ensemble.md).

How it is verified: the pre-movement row of the [Verification](/verification/_index.md) index.
