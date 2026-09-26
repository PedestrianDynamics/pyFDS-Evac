---
title: "ASET, RSET and the egress timeline"
weight: 1
---

Performance-based fire-safety design compares two times. The available
safe escape time (ASET) is the time until conditions in a space, or on the
route out of it, become untenable. The required safe escape time (RSET) is
the time occupants need to reach a place of safety. A design is acceptable
when ASET exceeds RSET by an adequate margin (ISO/TR 16738:2009, §5.6).

## The equations as published

ISO/TR 16738:2009 writes the margin of safety and the escape time as

$$
t_{\mathrm{marg}} = t_{\mathrm{ASET}} - t_{\mathrm{RSET}} \qquad \text{(ISO/TR 16738, Eq. 1)}
$$

$$
t_{\mathrm{RSET}} = t_{\mathrm{det}} + t_{\mathrm{warn}} + \left(t_{\mathrm{pre}} + t_{\mathrm{trav}}\right) \qquad \text{(Eq. 2)}
$$

All times are in seconds or minutes. \(t_{\mathrm{det}}\) is the time from
ignition to detection, by a system or by the first occupant to notice fire
cues. \(t_{\mathrm{warn}}\) runs from detection to a general alarm or
warning. \(t_{\mathrm{pre}}\) is the pre-travel activity time, also called
pre-movement or pre-evacuation time, and \(t_{\mathrm{trav}}\) is the travel
time. The standard notes that the evacuation time \(t_{\mathrm{evac}}\)
consists of the last two terms only, and it splits \(t_{\mathrm{pre}}\) into
a recognition time and a response time. The Society of Fire Protection
Engineers (SFPE) Handbook uses the same terms
(Gwynne and Boyce 2016, Ch. 64).

## What the timeline rests on

ASET comes from the fire: the time-concentration curves of heat, toxic gases
and smoke at the occupants' positions, compared with tenability limits. The
[fractional effective dose (FED)](/fundamentals/asphyxiant-fed.md), [irritant](/fundamentals/irritants.md), [heat](/fundamentals/heat.md) and
[visibility](/fundamentals/visibility.md) pages give those limits. ISO 13571:2012 (§5.1)
states that its time to compromised tenability may reasonably be equated
to ASET when escape to a place of refuge is the outcome considered.

RSET comes from people. ISO/TR 16738 (§5.4) reports that the pre-travel
activity phase can often be the longest part of the total escape time. Each
occupant has their own \(t_{\mathrm{pre}}\) and \(t_{\mathrm{trav}}\), so
the standard treats them as distributions, and warns that within an
enclosure the two terms cannot be added directly because the distributions
interact (§7). See [Pre-movement time](/fundamentals/pre-movement.md).

## Known limits

The definitions differ in where the clock starts. ISO/TR 16738 Eq. 2 and
SFPE Ch. 64 count RSET from ignition, since they include detection. SFPE
Ch. 56 (Bukowski and Tubbs 2016) defines RSET from the notification of
occupants and ASET from notification to the onset of untenable conditions,
while also stating that evacuation times consist of detection, notification,
pre-movement and movement times. When two analyses are compared, check which
origin each uses. The terms also vary: "escape" in ISO/TR 16738, "egress" or
"evacuation" in the SFPE Handbook, for the same quantities.

ASET is not one number. It varies with position and with the tenability
criterion chosen, and the criterion itself is set for a fraction of the
population (see [Incapacitation thresholds](/fundamentals/incapacitation-thresholds.md)).

## Sources

- ISO/TR 16738:2009. *Fire-safety engineering — Technical information on
  methods for evaluating behaviour and movement of people.* ISO, Geneva.
  [iso.org/standard/42887](https://www.iso.org/standard/42887.html).
  Read from the public preview (§1–7).
- R. W. Bukowski and J. S. Tubbs (2016). Egress concepts and design
  approaches. *SFPE Handbook*, 5th ed., Ch. 56, 2012–2046.
  [doi:10.1007/978-1-4939-2565-0_56](https://doi.org/10.1007/978-1-4939-2565-0_56)
- S. M. V. Gwynne and K. E. Boyce (2016). Engineering data. *SFPE
  Handbook*, 5th ed., Ch. 64, 2429–2551.
  [doi:10.1007/978-1-4939-2565-0_64](https://doi.org/10.1007/978-1-4939-2565-0_64)
- ISO 13571:2012. *Life-threatening components of fire — Guidelines for the
  estimation of time to compromised tenability in fires.*
  [iso.org/standard/56172](https://www.iso.org/standard/56172.html).

How pyFDS-Evac uses this: see the
[RSET ensemble how-to](/docs/howto-rset-ensemble.md).
