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
(Gwynne et al. 2026, Ch. 72, p. 2378).

![Schematic egress timeline. A top bar shows the detection time followed by the warning time, from ignition to the general alarm. Below, six occupant rows start at the alarm, each with a light pre-travel bar followed by a dark travel bar of different lengths, sorted by exit time. A solid vertical line marks t_RSET at the exit of the last occupant, a dashed red line marks t_ASET later, and a bracket between them marks the margin t_marg. A bracket under the last row marks t_evac,i = t_pre,i + t_trav,i](/images/fundamentals/aset_rset_timeline.png)

*The egress timeline of Eqs. 1–2 as a schematic; the times are
illustrative. Detection and warning happen once for the whole building.
After the general alarm, each occupant has their own pre-travel time
\(t_{\mathrm{pre},i}\) (light) and travel time \(t_{\mathrm{trav},i}\)
(dark); a dot marks each exit. ISO/TR 16738 (§7) warns that the two
distributions interact, so they cannot be added directly. The figure draws
\(t_{\mathrm{RSET}}\) at the exit of the last occupant, the latest time from
ignition to exit, as RiMEA 4.1.1 (§2.13) defines its evacuation time, which starts at
ignition.
Figure inspired by Fig. 2 of RiMEA 4.1.1 (p. 10). Script:
`scripts/figures/fundamentals_aset_rset_timeline.py`.*

## What the timeline rests on

ASET comes from the fire (see [Design fires](/fundamentals/design-fires.md)): the time-concentration curves of heat, toxic gases
and smoke at the occupants' positions, compared with tenability limits. The
[fractional effective dose (FED)](/fundamentals/asphyxiant-fed.md), [irritant](/fundamentals/irritants.md), [heat](/fundamentals/heat.md) and
[visibility](/fundamentals/visibility.md) pages give those limits. ISO 13571:2012 (§5.1)
states that its time to compromised tenability may reasonably be equated
to ASET when escape to a place of refuge is the outcome considered.

Tenability is judged in one of two ways. With fixed limits, conditions at
one height are compared with one value per hazard, and a space is
untenable as soon as any value is exceeded: for exposures of up to
10 minutes, the Engineers Australia practice note gives 100&nbsp;°C,
2.5 kW/m², 2,700 ppm CO, 140 ppm HCN and a visibility of 10 m, evaluated
2.0 m above the floor (2014, §5.2 and Fig. 8, p. 15). With a dose, the
exposure of each occupant is summed over time along the path they take,
and incapacitation is expected at a fractional effective dose of 1 for the
median occupant (the same note, §5 and §5.3, after the SFPE Handbook and
ISO 13571). The note computes heat exposure as one FED and toxic-gas
exposure as another (§5.3). For more susceptible
occupants a lower threshold may suit; see
[Incapacitation thresholds](/fundamentals/incapacitation-thresholds.md).

{{< svg-figure src="images/concepts/tenability-limits.svg, images/concepts/tenability-dose.svg" >}}

*Fixed limits: the short-exposure criteria of the practice note (Fig. 8,
"Tenability Criteria – Short Exposure", p. 15); for small enclosures, of
the order of 10 m, the note allows a visibility of 5 m. Dose along each
path: the dose approach, schematic, for two occupants; the same fire gives
each one a different dose. The curves are the toxic-gas FED; heat is
judged as a second, separate FED (§5.3). Figure inspired by Fig. 8 of the Engineers Australia
practice note for tenability criteria (2014).*

RSET comes from people. ISO/TR 16738 (§5.4) reports that the pre-travel
activity phase can often be the longest part of the total escape time. Each
occupant has their own \(t_{\mathrm{pre}}\) and \(t_{\mathrm{trav}}\), so
the standard treats them as distributions, and warns that within an
enclosure the two terms cannot be added directly because the distributions
interact (§7). See [Pre-movement time](/fundamentals/pre-movement.md).

## Known limits

The definitions differ in where the clock starts. ISO/TR 16738 Eq. 2 and
the SFPE Handbook count RSET from ignition: Ch. 66 defines RSET as the time
from fire initiation until the last occupant reaches a safe place, and ASET
as the time from fire initiation to the onset of untenable conditions
(Tubbs and Alonso-Gutierrez 2026, p. 2158), and Ch. 72 starts its timeline
at ignition (p. 2378). The 2016 edition (Bukowski and Tubbs 2016, Ch. 56,
p. 2038) counted both from the notification of occupants, so older analyses
may use that origin. When two analyses are compared, check which origin
each uses. The terms also vary: "escape" in ISO/TR 16738, "egress" or
"evacuation" in the SFPE Handbook, for the same quantities.

ASET varies with position and with the tenability
criterion chosen, and the criterion itself is set for a fraction of the
population (see [Incapacitation thresholds](/fundamentals/incapacitation-thresholds.md)).

Which part of the pre-movement distribution matters depends on density.
Where occupant density is high relative to exit width, the pre-movement of
the first few occupants and the exit flow capacity set the evacuation time;
at low density, the late tail of the distribution does (Purser 2003,
pp. 96–97).

Purser (2003, pp. 92–93) noted that most travel-time calculations assumed
no interaction between occupants and the fire effluent, and that
engineering tenability calculations used only smoke density and/or CO,
with yields often treated as constants, usually for the well-ventilated
case.

The concept itself is disputed. Babrauskas, Fleming and Russell (2010,
pp. 347–348) argue that RSET is a distribution rather than one number, that
the test ASET > RSET hides how much more time one design gives than
another, and that there is no agreed population for tenability criteria to
protect. Following Fleming (2000), whom they cite, they propose reporting
the margin ASET − RSET to compare designs (pp. 350–351). Their evidence comes from fires in single-family homes.

## Sources

- ISO (2009). *ISO/TR 16738:2009 Fire-safety engineering — Technical
  information on methods for evaluating behaviour and movement of people*.
  ISO, Geneva. [iso.org/standard/42887](https://www.iso.org/standard/42887.html).
  Read from the public preview (§1–7).
- ISO (2012). *ISO 13571:2012 Life-threatening components of fire —
  Guidelines for the estimation of time to compromised tenability in
  fires*. ISO, Geneva.
  [iso.org/standard/56172](https://www.iso.org/standard/56172.html).
- RiMEA e.V. (2025). *Guideline for Microscopic Evacuation Analysis*,
  version 4.1.1, 11 September 2025. [rimea.de](https://rimea.de/).
  §2.8–2.13 (pp. 9–10) and Fig. 2 (p. 10).
- Tubbs, J. S., & Alonso-Gutierrez, V. (2026). *Egress concepts and design
  strategies*. SFPE Handbook of Fire Protection Engineering, 6th ed.,
  Ch. 66, 2139–2164. p. 2158.
  [doi:10.1007/978-3-031-59212-6_66](https://doi.org/10.1007/978-3-031-59212-6_66)
- Bukowski, R. W., & Tubbs, J. S. (2016). *Egress concepts and design
  approaches*. SFPE Handbook of Fire Protection Engineering, 5th ed.,
  Ch. 56, 2012–2046. p. 2038; cited only for the notification origin of
  that edition.
  [doi:10.1007/978-1-4939-2565-0_56](https://doi.org/10.1007/978-1-4939-2565-0_56)
- Engineers Australia Society of Fire Safety (2014). *Practice note for
  tenability criteria in building fires*, version 2.0, 3 April 2014.
  Society of Fire Safety, NSW Chapter, Engineers Australia.
  [engineersaustralia.org.au](https://www.engineersaustralia.org.au/sites/default/files/2024-01/tenability-criteria-practice-note_0.pdf).
  §5 (p. 13), §5.2 and Fig. 8 (p. 15), §5.3 (p. 17).
- Purser, D. A. (2003). *ASET and RSET: addressing some issues in relation
  to occupant behaviour and tenability*. Fire Safety Science, 7, 91–102.
  [doi:10.3801/IAFSS.FSS.7-91](https://doi.org/10.3801/IAFSS.FSS.7-91)
- Babrauskas, V., Fleming, J. M., & Russell, B. D. (2010). *RSET/ASET, a
  flawed concept for fire safety assessment*. Fire and Materials, 34(7),
  341–355. [doi:10.1002/fam.1025](https://doi.org/10.1002/fam.1025)
- Gwynne, S. M. V., Boyce, K. E., & Lovreglio, R. (2026). *Egress data for
  engineering analysis*. SFPE Handbook of Fire Protection Engineering,
  6th ed., Ch. 72, 2375–2484. p. 2378.
  [doi:10.1007/978-3-031-59212-6_72](https://doi.org/10.1007/978-3-031-59212-6_72)

How pyFDS-Evac uses this: see the
[RSET ensemble how-to](/docs/howto-rset-ensemble.md), and
[A crowd in a real fire › ASET and RSET](/docs/first-fds-case.md#aset-rset)
for a per-agent comparison on a real FDS fire, and
[ASET-RSET maps after Schröder et al. (2020)](/docs/study-schroeder2020.md) for ASET, RSET and their
difference as maps. Each agent carries
its own dose along its path; see
[Fractional effective dose](/models/fed.md).

RSET from a run without the fire against a coupled run:
[Evacuation with and without the fire](/docs/howto-with-without-fire.md).

How it is verified: the [Verification](/verification/_index.md) index; ASET and RSET themselves are outputs of a study.
