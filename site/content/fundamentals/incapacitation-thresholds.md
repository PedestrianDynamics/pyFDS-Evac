---
title: "Incapacitation thresholds"
weight: 8
---

A fractional effective dose (FED) of 1 is, by definition, the dose at which
a person of median susceptibility is predicted to be incapacitated. Half of a
population is more susceptible. Design therefore uses a lower threshold, most
often 0.3. This page gives the published rationale for that value and the
limits of its population basis.

Symbols follow the [notation table](/docs/concepts.md#notation).

## The ISO 13571 rationale

ISO 13571:2012 (§4.1, §5.4) assumes a priori that occupant responses follow a
log-normal distribution about a median. The standard states that, in the
absence of actual data, the log-normal is the most defensible choice. FED and
fractional effective concentration (FEC) values of 1.0 correspond by
definition to the median, and users "shall use reduced FED and/or FEC
threshold criteria" for more conservative objectives (§5.4). The earlier
edition, ISO 13571:2007, gave 0.3 as an example threshold for most general
occupancies, noted that "the distribution of human responses to fire gases is
not known", and stated that at 0.3 about 11.4 % of the population would still
be susceptible, adding that no threshold is statistically safe for every
occupant (§5, Note). ISO/TR 13571-2:2016 repeats the 11.4 % figure for 0.3,
citing ISO 13571:2012, A.5.2.

## What the handbook says

Purser and McAllister (2016, Society of Fire Protection Engineers (SFPE)
Handbook Ch. 63) state that the endpoints of their
equations represent the median of the distribution, and that approximately
11.3 % of the population is likely to be susceptible below an FED of 0.3,
citing ISO 13571 (p. 2334; repeated on p. 2415). In the same paragraph they
write that approximately 90 % of the population is susceptible below an FED
of 1.3. For a log-normal with
median 1, these two statements are not consistent: 11.3 % below 0.3 implies a
log-scale standard deviation near 1.0, whereas 90 % below 1.3 implies about
0.2. The source does not give the distribution parameters that would resolve
this. Ch. 63 also notes that, because gas concentrations rise quickly in most
flaming fires, variations in individual susceptibility have relatively minor
effects on predicted times to incapacitation (p. 2334).

## NIST Technical Note 1797

The National Institute of Standards and Technology (NIST) Technical Note (TN)
1797 is often cited for population bands.

Averill et al. (2013), a report on high-rise fireground field experiments,
bins FED into four ranges with estimated population fractions incapacitated:
up to 11 % below 0.3, 11–50 % between 0.3 and 1.0, 50–89 % between 1.0 and
3.0, and more than 89 % above 3.0 (Table 8). The report cites ISO 13571
(2007) as the basis of FED. It contains no population data of its own, it
states that "the detailed probabilistic relationship between FED and the
percentage of people incapacitated is unknown", and its uncertainty appendix
cites an uncertainty of as much as ±20 % to 35 % (Appendix F). Its FED
included CO, CO₂ and O₂ only.

## What the numbers support

A log-normal with median 1 cannot match both TN 1797 bins exactly: 11 % at
0.3 implies a log-scale standard deviation of about 0.98, and 89 % at 3.0
implies about 0.90. Any single value is a compromise between two bin edges
that themselves rest on an assumed distribution, not on measured human
incapacitation. The 0.3 threshold and the 11 % figure are best read as a
design convention derived from the log-normal assumption. For reference
(arithmetic, not a statement of the sources): a log-normal with median 1 and
log-scale standard deviation 1.0 puts 11.4 % below 0.3, ISO's figure; the
preview does not state which standard deviation ISO used.

## Sources

- ISO (2012). *ISO 13571:2012 Life-threatening components of fire —
  Guidelines for the estimation of time to compromised tenability in
  fires*, §4.1 and §5.4. ISO, Geneva.
  [iso.org/standard/56172](https://www.iso.org/standard/56172.html). Read
  from the public preview; Annex A.5.2 was not available.
- ISO (2007). *ISO 13571:2007 Life-threatening components of fire —
  Guidelines for the estimation of time available for escape using fire
  data*, §5. ISO, Geneva. Withdrawn.
  [iso.org/standard/42967](https://www.iso.org/standard/42967.html). Read
  from the public preview.
- ISO (2016). *ISO/TR 13571-2:2016 Life-threatening components of fire —
  Part 2: Methodology and examples of tenability assessment*. ISO, Geneva.
  [iso.org/standard/65996](https://www.iso.org/standard/65996.html). Read
  from the public preview.
- Purser, D. A., & McAllister, J. L. (2016). *Assessment of hazards to
  occupants from smoke, toxic gases, and heat*. SFPE Handbook of Fire
  Protection Engineering, 5th ed., Ch. 63, 2308–2428.
  [doi:10.1007/978-1-4939-2565-0_63](https://doi.org/10.1007/978-1-4939-2565-0_63)
- Averill, J. D., Moore-Merrell, L., Ranellone, R. T., Jr., Weinschenk, C.,
  Taylor, N., Goldstein, R., Santos, R., Wissoker, D., & Notarianni, K. A.
  (2013). *Report on high-rise fireground field experiments* (K. M.
  Butler, Ed.). NIST Technical Note 1797.
  [doi:10.6028/NIST.TN.1797](https://doi.org/10.6028/NIST.TN.1797)

How pyFDS-Evac uses this: see [Fractional effective dose](/models/fed.md#tenability-irritant-slowdown-and-incapacitation).
