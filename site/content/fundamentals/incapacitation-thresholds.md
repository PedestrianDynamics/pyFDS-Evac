---
title: "Incapacitation thresholds"
weight: 10
---

A fractional effective dose (FED) of 1 is, by definition, the dose at which
a person of median susceptibility is predicted to be incapacitated. Half of a
population is more susceptible. Design therefore uses a lower threshold, most
often 0.3. The published rationale for that value rests on a population
basis with known limits.

Symbols follow the [notation table](/docs/concepts.md#notation).

## The ISO 13571 rationale

ISO 13571:2012 (§4.1, §5.4) assumes a priori that occupant responses follow a
log-normal distribution about a median. The standard states that, in the
absence of actual data, the log-normal is the most defensible choice. FED and
fractional effective concentration (FEC) values of 1.0 correspond by
definition to the median, and users "shall use reduced FED and/or FEC
threshold criteria" for more conservative objectives (§5.4). Whatever the
value, a single one is to be used for both FED and FEC in a given estimation
(§5.4, A.5.2).

The informative Annex A.5.2 gives examples: under the log-normal assumption,
thresholds of 0.3, 0.2 and 0.1 leave 11.4 %, 5.4 % and 1.1 % of the
population statistically estimated to experience compromised tenability. ISO
cites a table of normal areas for these figures (ref. [43]), says that no
threshold is statistically safe for every occupant, and warns that the
percentages only show the trend and carry no assurance of validity. For CO,
0.3 corresponds to about 10 % instead of 30 % carboxyhaemoglobin (A.3.2).

The earlier edition, ISO 13571:2007, gave 0.3 as an example threshold for
most general occupancies, noted that "the distribution of human responses to
fire gases is not known", and stated that at 0.3 about 11.4 % of the
population would still be susceptible (§5.2, Note). The 2012 edition turns the
reduced threshold into a "shall" for more conservative objectives, keeps 0.3
only as an informative example and adds the 0.2 and 0.1 figures. It also
redefines FED = 1: in 2007 the dose that leaves an occupant of average
susceptibility unable to effect their own escape (§5.2), in 2012 the median
of compromised tenability (§5.4). ISO/TR 13571-2:2016 repeats the 11.4 % figure
for 0.3, citing ISO 13571:2012, A.5.2.

## What the handbook says

Purser and McAllister (2026, Society of Fire Protection Engineers (SFPE)
Handbook, 6th ed., Ch. 70) state that the endpoints of their
equations represent the median of the distribution, and that approximately
1 % of the population is likely to be susceptible below an FED of 0.3,
citing ISO 13571 (p. 2282; repeated on p. 2343). ISO 13571:2012 (A.5.2)
gives 11.4 % for 0.3, and the 2016 edition of the chapter gave 11.3 %
(Purser and McAllister 2016, p. 2334). The commentary to New Zealand's
Verification Method C/VM2, citing ISO 13571, reads a gas FED of 1.0 as the
point at which about 50 % of occupants might be incapacitated, and the 0.3
of Building Code clause C4.3 as the point at which about 11 % of the
population "would be susceptible to less severe exposures" (MBIE 2012,
p. 29). It applies the same 0.3 to the thermal dose, assuming that broadly
similar principles apply (p. 31). In the same paragraph as its 1 %
statement, Ch. 70 states
that approximately 90 % of the population is susceptible below an FED
of 1.3 (p. 2282). For a log-normal with
median 1, these two statements are not consistent: 1 % below 0.3 implies a
log-scale standard deviation near 0.52, whereas 90 % below 1.3 implies about
0.2 (our arithmetic; 11.3 % below 0.3 implies about 1.0). The source does
not give the distribution parameters that would resolve
this. For single gases, Ch. 70 puts about 1 % of people below an FED of
0.3 for CO (about 10 % COHb, p. 2298), HCN (p. 2302), low oxygen (p. 2305)
and CO₂ (p. 2307). Only the HCN figure rests on data: a probit analysis of
the primate experiments gives 1 % at FICN = 0.44 (p. 2302), which for a
log-normal with median 1 means σ ≈ 0.35 (our arithmetic). The 0.3 is then
widened for children and the elderly. Ch. 70 also notes that, because gas concentrations rise quickly in most
flaming fires, variations in individual susceptibility have relatively minor
effects on predicted times to incapacitation (p. 2282).

After the general asphyxiant equation (Eq. 70.39), Ch. 70 also states that
an FED of 0.1 should allow nearly all exposed people to escape (p. 2310),
while p. 2288 gives 0.3 for the general population and 0.1 for particularly
sensitive groups. The 2016 edition gave 0.3 for nearly all people and 0.1
as an option for especially vulnerable groups (p. 2372).

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
log-scale standard deviation 1.0 puts 11.4 % below 0.3, 5.4 % below 0.2 and
1.1 % below 0.1, all three of ISO's A.5.2 figures; ISO itself does not state
the standard deviation.

## Heat

ISO 13571:2012 applies the gas threshold logic to heat by reference: heat is
assessed with an FED model analogous to the gas model (§4.4), and the time at
which the heat dose exceeds the chosen threshold is found "in the same
manner" as for toxic gases (§8.5, pointing to §5.3). The standard gives no
population data, spread or separate threshold for heat. Its population
figures (A.5.2) sit in an annex on toxic potency whose evidence base is
laboratory data on gaseous effluents (A.5.1), and its footnote to A.5.2
calls the log-normal an assumption for responses to fire-gas toxicants. For
smoke obscuration, by contrast, ISO says explicitly that no data exist and
applies the same factor of 0.3 by analogy (clause 9, Note 5); there is no
such note for heat.

Our reading, not a statement of the standard: §4.1 and §5.4 make the
log-normal assumption and the rule of reduced thresholds general, so a
threshold such as 0.3 may be applied to the heat FED, but the 11.4 % figure
for heat rests on assumption alone. ISO does not establish it. §5.4 also asks
for a single threshold for FED and FEC in a given estimation, whereas its
report clause asks for the threshold chosen for each component (clause 10);
the text does not say whether the heat FED must share the gas threshold.
§8.5 finds the heat time "in the same manner" as for the gases.

No source we could consult gives a population spread for tolerance of
convective heat (ISO 13571:2012 Eqs. (9) and (10); SFPE Eq. 70.42). SFPE Ch. 70 gives
population figures for heat only for radiant lethality (p. 2318): a radiant
dose of 10 (kW/m²)^4/3·min is a fatal level for people over 65 and "a 1%
lethal level" for the average population, and 16.7 (kW/m²)^4/3·min is "a
50% lethal level". The chapter cites Hockey and Rew
(1996) and Purser (1997) for its radiant dose relation (refs. [125, 126],
p. 2318). Hockey and Rew is a candidate source for probit relations behind
these figures; we have not read it.

Inference, not a statement of the sources: if the lethal dose is log-normal
with median 16.7 and 1 % below 10, its log-scale standard deviation is
ln(16.7/10)/2.326 = 0.513/2.326, so \(\sigma \approx 0.22\). The median
is the fatal dose D = 16.7 of the total-flux method; Purser's spreadsheet
value 16.667 gives the same σ to two decimals. Its limits:

- The Handbook states no distribution; the log-normal is assumed.
- Two figures fix two parameters, so nothing tests the fit.
- The figures are for radiant lethality, the fatal dose *D* = 16.7 of
  Eq. 70.41. They concern neither convective tolerance nor the ISO
  convective times.

With FED = 1 at D = 16.7, the 1 % lethal dose is FED = 0.60. A log-normal
with σ = 0.94, between the two TN 1797 bin values above, would put 29 % of people
below FED = 0.60 instead of 1 %. A probit in the natural log of dose with
slope b gives σ = 1/b. A published probit slope for a heat endpoint would
settle the value for that endpoint; Hockey and Rew is the source to check
first ([#225](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/225)).

How pyFDS-Evac applies this: [Models › Heat › Incapacitation](/models/heat.md#incapacitation).

## Sources

- ISO (2012). *ISO 13571:2012 Life-threatening components of fire —
  Guidelines for the estimation of time to compromised tenability in
  fires*, §4.1, §4.4, §5.4, §8.5, clause 9 Note 5, clause 10, A.3.2 and
  A.5. ISO, Geneva.
  [iso.org/standard/56172](https://www.iso.org/standard/56172.html). Read
  in full from a licensed copy.
- ISO (2007). *ISO 13571:2007 Life-threatening components of fire —
  Guidelines for the estimation of time available for escape using fire
  data*, §5. ISO, Geneva. Withdrawn.
  [iso.org/standard/42967](https://www.iso.org/standard/42967.html). Read
  from the public preview.
- ISO (2016). *ISO/TR 13571-2:2016 Life-threatening components of fire —
  Part 2: Methodology and examples of tenability assessment*. ISO, Geneva.
  [iso.org/standard/65996](https://www.iso.org/standard/65996.html). Read
  from the public preview.
- Purser, D. A., & McAllister, J. L. (2026). *Assessment of hazards to
  occupants from smoke, toxic gases, and heat*. SFPE Handbook of Fire
  Protection Engineering, 6th ed., Ch. 70, 2271–2352. pp. 2282, 2288, 2298, 2302, 2305,
  2307, 2310, 2318, 2343.
  [doi:10.1007/978-3-031-59212-6_70](https://doi.org/10.1007/978-3-031-59212-6_70)
- Purser, D. A., & McAllister, J. L. (2016). *Assessment of hazards to
  occupants from smoke, toxic gases, and heat*. SFPE Handbook of Fire
  Protection Engineering, 5th ed., Ch. 63, 2308–2428. Cited only for the
  11.3 % figure (p. 2334), which Ch. 70 replaces, and for the 0.3 and 0.1
  FED factors (p. 2372).
  [doi:10.1007/978-1-4939-2565-0_63](https://doi.org/10.1007/978-1-4939-2565-0_63)
- MBIE (2012). *Commentary for Verification Method C/VM2*, December 2012.
  Ministry of Business, Innovation and Employment, Wellington.
  ISBN 978-0-478-39942-4. Commentary to clause C4.3 (pp. 29, 31); written for
  the first edition of C/VM2. The C4.3 limits are unchanged in the current
  Building Code and in C/VM2, 2nd edition (2025); see
  [ASET and RSET](/fundamentals/aset-rset.md).
- Averill, J. D., Moore-Merrell, L., Ranellone, R. T., Jr., Weinschenk, C.,
  Taylor, N., Goldstein, R., Santos, R., Wissoker, D., & Notarianni, K. A.
  (2013). *Report on high-rise fireground field experiments* (K. M.
  Butler, Ed.). NIST Technical Note 1797.
  [doi:10.6028/NIST.TN.1797](https://doi.org/10.6028/NIST.TN.1797)
- Hockey, S. M., & Rew, P. J. (1996). *Human response to thermal
  radiation*. Contract Research Report 97/1996. HSE Books, Sudbury. Cited
  by Ch. 70 as ref. [125]; not consulted.
- Purser, D. A. (1997). Review of human response to thermal radiation.
  *Fire Safety Journal*, 28, 290–291. Cited by Ch. 70 as ref. [126]; not
  consulted.

How pyFDS-Evac uses this: see [Fractional effective dose](/models/fed.md#tenability-irritant-slowdown-and-incapacitation).

How it is verified: the probabilistic runs on the [CO dose](/verification/testing-homogeneous.md) and [Heat dose](/verification/testing-heat.md) pages.
