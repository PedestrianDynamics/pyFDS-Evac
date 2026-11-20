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
p. 2318).

Hockey and Rew review the probits for radiant exposure. All use the dose
\(V = I^{4/3} t\) in (kW/m²)^4/3·s and the natural log of *V*:

| Probit (as cited by Hockey and Rew) | Endpoint | *Y* | σ = 1/*b* |
|---|---|---|---|
| Eisenberg et al. (1975), §4.2.2, pp. 15–16 | death | −14.9 + 2.56 ln *V* | 0.39 |
| Tsao and Perry (1979), §4.2.3, p. 17 | death | −12.80 + 2.56 ln *V* | 0.39 |
| Tsao and Perry (1979), p. 17 | thermal injury | −12.03 + 3.0186 ln *V* | 0.33 |
| TNO Green Book, §4.2.4, p. 17 | second-degree burn | −15.34 + 3.0186 ln *V* | 0.33 |

A probit in ln *V* with slope *b* is a log-normal with σ = 1/*b* (our
arithmetic). Their Table 5.1 (p. 23) gives the matching lethal doses for
Eisenberg, 960 (1 %) and 2380 (50 %): ln(2380/960)/2.326 = 0.39, the same
σ. Eisenberg's probit is fitted to the casualties of Hiroshima and
Nagasaki, an ultraviolet exposure; Tsao and Perry's has the same slope,
shifted for infrared (p. 16). The report adds that the cause of death in
those data is uncertain (p. 16).

So the only sourced spread for a heat endpoint is σ ≈ 0.39, for radiant
lethality. It is not a spread for convective tolerance: nothing in the
report concerns convected heat (ISO 13571:2012 Eqs. (9) and (10); SFPE
Eq. 70.42), and carrying it over to a total-flux dose would need an
argument the report does not make.

The Handbook's two figures are not these probits. In the report's units
they are 600 and 1000 (kW/m²)^4/3·s; the report gives 1000 as the HSE
dangerous dose for the average population, about 1 % lethal, and 500 for
the vulnerable (Table 5.1, after Kinsman), not 1000 as a 50 % level. An
earlier version of this page read 10 and 16.7 as the 1 % and 50 % points
of a log-normal, which gives σ ≈ 0.22; the report does not support that
pairing, so the 0.22 is withdrawn.

With FED = 1 at the median, σ = 0.94, the gas value between the two
TN 1797 bin values above, puts 1 % of people below FED = 0.11; σ = 0.39
puts them below FED = 0.40 (our arithmetic). Heat stays deterministic by
default, since no source gives a spread for the convective laws
([#225](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/225)).

### Radiant pain and burn times

Wieczorek and Dembsey (2001) give time-to-pain and time-to-burn
correlations for radiant exposure of the skin, with *q* the incident
radiant flux [kW/m²] and times in seconds (p. 96):

| Equation | Endpoint | Time | Safety factor | Stated range [kW/m²] |
|---|---|---|---|---|
| Eq. (4), p. 96 | pain | \(t_p = 125\,q^{-1.9}\) | 2 on time | 1.7–10, confirmed to 20 |
| Eq. (5), p. 96 | superficial second-degree burn | \(t_{2b} = 260\,q^{-1.56}\) | 1.6 on exposure time | 2–50 |
| Eq. (4a), p. 97 | pain | \(t_p = 250\,q^{-1.9}\) | none | as Eq. (4) |
| Eq. (5a), p. 97 | superficial second-degree burn | \(t_{2b} = 416\,q^{-1.56}\) | none | as Eq. (5) |

Both pairs are fitted to the authors' skin heat-transfer model at the
reference skin of their Table 2 (p. 93: 32.5 °C initial temperature,
80 µm epidermis, pain receptors at 100 µm); the model is Eq. (1) for pain
(p. 94) and Eqs. (2)–(3) for the burn damage integral (pp. 94–95). The
paper states that 1.7 kW/m² is the critical flux below which no pain is
experienced however long the exposure (p. 96). The recommended equations
are (4) and (5); (4a) and (5a) are given "for comparative purposes" (p. 97).
Against the full model, the simplified times differ by at most 0.1 s from
10 kW/m² up, and are shorter at 1.7 and 2 kW/m² (by 12 % for pain and up
to 29 % for burns at the coldest skin of the paper's range, p. 106).

ISO 13571:2012 Eqs. (7) and (8), which cite this paper as ref. [17], are
the equations without the safety factors: 6.9 *q*^−1.56 min is 414 s,
Eq. (5a) with 416 s, and 4.2 *q*^−1.9 min is 252 s, Eq. (4a) with 250 s
(our conversion; the small differences are rounding of the constants).
ISO's times are therefore 1.6 times (burn) and 2 times (pain) longer than
those of the equations the paper recommends. At 2.5 kW/m², the ISO
threshold flux, pain comes at about 44 s by ISO against 22 s by Eq. (4),
and a burn at about 99 s against 62 s by Eq. (5) (our arithmetic).

The paper compares (4a) and (5a) with the dose form \(t = A\,q^{-4/3}\)
used in the United Kingdom, which it cites to Hymes, Boydell and Prescott
(1996) (ref. [12]): pain at 92 (kW/m²)^4/3·s and a superficial
second-degree burn at 210–700 (kW/m²)^4/3·s, with 113 for pain from Mudan
and Croce (pp. 96–97). It finds the unfactored times consistent with these
(conclusions, p. 108). We have not read ref. [12].

Heat-tolerance variability enters the paper as ranges, not as a
distribution. Initial skin temperature is varied over 27–38 °C and
epidermal thickness over 16–430 µm, (Table 9, p. 103; the paper's literature
review, pp. 98–102, supplies the data); pain receptor depth is held fixed
for lack of data (p. 103). With β the skin temperature over 32.5 °C and
γ the epidermal thickness over 80 µm, correction factors multiply the
time of Eqs. (4) and (5): a quadratic in β for pain (Eq. 6, p. 104),
another for burns (Eq. 7, p. 105), and a function of *q* and γ for
thickness (Eq. 8, p. 106). Table 10 (p. 107) gives the pain-time factor
as 1.92 at 27 °C and 0.29 at 38 °C, the burn-time factor as 1.25 to 0.50,
and the thickness factor at 50 kW/m² as 0.76 (16 µm) to 2.35 (430 µm). These are
min/max bounds with no stated probability, so they give no σ and do not
replace the σ ≈ 0.39 above, which is a lethality probit slope. The
paper contains no probit, no convective-heat data and no FED threshold.

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
  by Ch. 70 as ref. [125]; read in full (§4.2, Table 5.1, App. B).
- Wieczorek, C. J., & Dembsey, N. A. (2001). Human variability correction
  factors for use with simplified engineering tools for predicting pain
  and second degree skin burns. *Journal of Fire Protection Engineering*,
  11(2), 88–111; pp. 93–97, 103–107. ISO ref. [17] for Eqs. (7) and (8);
  read in full.
  [doi:10.1106/0D9U-KLP9-TG1P-XJ1B](https://doi.org/10.1106/0D9U-KLP9-TG1P-XJ1B)
- Purser, D. A. (1997). Review of human response to thermal radiation.
  *Fire Safety Journal*, 28, 290–291. Cited by Ch. 70 as ref. [126]; a
  one-page review of Hockey and Rew, read; it gives no probit.

How pyFDS-Evac uses this: see [Fractional effective dose](/models/fed.md#tenability-irritant-slowdown-and-incapacitation).

How it is verified: the probabilistic runs on the [CO dose](/verification/testing-homogeneous.md) and [Heat dose](/verification/testing-heat.md) pages.
