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
population would still be susceptible (§5.2, Note). The 2012 edition makes a
reduced threshold mandatory, keeps 0.3 only as an informative example and
adds the 0.2 and 0.1 figures. ISO/TR 13571-2:2016 repeats the 11.4 % figure
for 0.3, citing ISO 13571:2012, A.5.2.

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

No source we could consult gives a population spread for tolerance of
convective heat, the dose pyFDS-Evac computes (Eq. 63.44). SFPE Ch. 63 gives
population figures for heat only for radiant lethality (p. 2382): a radiant
dose of 10 (kW/m²)^4/3·min "represents a fatal level for a vulnerable
population (over 65 years of age) or a 1 % fatality level for the average
population, whereas 16.7 (kW/m²)^4/3·min represents a 50 % probability
lethal level for the average population". The chapter cites Hockey and Rew
(1996) and Purser (1997) for its radiant dose relation (refs. [133, 134],
p. 2382). Hockey and Rew is a candidate source for probit relations behind
these figures; we have not read it.

Inference, not a statement of the sources: if the lethal dose is log-normal
with median 16.7 and 1 % below 10, its log-scale standard deviation is
ln(16.7/10)/2.326 = 0.513/2.326, so \(\sigma \approx 0.22\). The median
is the fatal dose D = 16.7 of the total-flux method; Purser's spreadsheet
value 16.667 gives the same σ to two decimals. Its limits:

- The Handbook states no distribution; the log-normal is assumed.
- Two figures fix two parameters, so nothing tests the fit.
- The figures are for radiant lethality, the fatal endpoint of the opt-in
  total-flux dose (`--heat-fed-method total-flux`,
  `specs/016-heat-fed/SPEC.md`). They do not apply to the convective
  Eq. 63.44 time used by default.

With FED = 1 at D = 16.7, the 1 % fatality dose is FED = 0.60. The gas
dose's σ = 0.94, which the opt-in probabilistic heat mode borrows, would put
29 % of people below FED = 0.60 instead of 1 %. The heat threshold therefore
stays deterministic by default. A probit in the natural log of dose with
slope b gives σ = 1/b. A published probit slope for the endpoint in use
would settle the value for that endpoint; Hockey and Rew is the source to
check first
([#225](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/225)).

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
- Purser, D. A., & McAllister, J. L. (2016). *Assessment of hazards to
  occupants from smoke, toxic gases, and heat*. SFPE Handbook of Fire
  Protection Engineering, 5th ed., Ch. 63, 2308–2428.
  [doi:10.1007/978-1-4939-2565-0_63](https://doi.org/10.1007/978-1-4939-2565-0_63)
- Averill, J. D., Moore-Merrell, L., Ranellone, R. T., Jr., Weinschenk, C.,
  Taylor, N., Goldstein, R., Santos, R., Wissoker, D., & Notarianni, K. A.
  (2013). *Report on high-rise fireground field experiments* (K. M.
  Butler, Ed.). NIST Technical Note 1797.
  [doi:10.6028/NIST.TN.1797](https://doi.org/10.6028/NIST.TN.1797)
- Hockey, S. M., & Rew, P. J. (1996). *Human response to thermal
  radiation*. Contract Research Report 97/1996. HSE Books, Sudbury. Cited
  by Ch. 63 as ref. [133]; not consulted.
- Purser, D. A. (1997). Review of human response to thermal radiation.
  *Fire Safety Journal*, 28, 290–291. Cited by Ch. 63 as ref. [134]; not
  consulted.

How pyFDS-Evac uses this: see [Fractional effective dose](/models/fed.md#tenability-irritant-slowdown-and-incapacitation).
