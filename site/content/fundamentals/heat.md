---
title: "Heat"
weight: 7
---

Heat can incapacitate in three ways: heat stroke (hyperthermia), skin pain
followed by burns, and burns to the respiratory tract (Purser and McAllister
2016, Society of Fire Protection Engineers (SFPE) Handbook Ch. 63). The first is driven mainly by hot air around the body
(convective heat), the second mainly by thermal radiation onto exposed skin.
The two are described by **separate equations with different endpoints**,
and neither should be read as the other.

Symbols follow the [notation table](/docs/concepts.md#notation); *T* is the
gas temperature [°C]. The equations below keep the SFPE Handbook's notation
(\(t_I\), *q*, *r*).

## Convective heat: time to incapacitation

For exposures of up to 2 h to convected heat from air containing less than
10 % water vapour by volume, the time to incapacitation
\(t_{I\,\mathrm{conv}}\) [min] at air temperature *T* [°C] is

$$
t_{I\,\mathrm{conv}} = 5\times10^{7}\,T^{-3.4} \qquad \text{(Eq. 63.44)}
$$

derived from the tolerance data in Fig. 63.28. Purser notes that the
expression follows the worst-case (100 % humidity) line and deviates from
Blockley's curve at the ends: it is somewhat non-conservative at high
temperatures and somewhat over-conservative at low ones. For design, Ch. 63
proposes a better fit for mid-humidity conditions,

$$
t_{\mathrm{tol}} = 2\times10^{31}\,T^{-16.963} + 4\times10^{8}\,T^{-3.7561} \qquad \text{(Eq. 63.45)}
$$

with further expressions for serious injury (Eq. 63.46) and for fatal
exposure (Eq. 63.47). No heat flux enters Eqs. 63.44–63.47: they take the air
temperature only. Thermal tolerance data for unprotected skin suggest a
limit of about 120 °C for convected heat, above which considerable pain
occurs quickly (Ch. 63, p. 2383 and Table 63.20). Burns to the respiratory
tract do not occur from air with less than 10 % water vapour in the absence
of burns to the facial skin, but saturated air above only 60 °C can cause
them (p. 2382).

## Radiant heat: pain and burns

The tenability limit for radiant heat incident on skin is about
**2.5 kW/m²**, below which exposure can be tolerated for at least several
minutes; at and above it, pain is followed by burns within seconds
(Ch. 63, p. 2382 and Table 63.20). Below
this flux the radiant contribution is neglected. Above it, the time
\(t_{I\,\mathrm{rad}}\) [min] to a given endpoint at incident radiant flux
*q* [kW/m²] is

$$
t_{I\,\mathrm{rad}} = \frac{r}{q^{1.33}} \qquad \text{(Eq. 63.43)}
$$

where *r* [(kW/m²)^4/3·min] is the dose for the endpoint: about 1.33–1.67 for
severe skin pain, 4.0–12.2 for second-degree burns and 16.7 for third-degree
burns. Purser proposes 1.33 as a tolerance threshold and 10 as a threshold
for incapacitation and serious injury (p. 2382). For the average
population, r = 10 is also given as a 1 % fatality level and r = 16.7 as a
50 % lethal level (p. 2382); what these imply for the population spread is
discussed under
[Incapacitation thresholds](/fundamentals/incapacitation-thresholds.md#heat).
For occupants passing
under a hot smoke layer, 2.5 kW/m² corresponds approximately to a layer
temperature of 200 °C (p. 2382).

## Combining the two

Ch. 63 describes two ways to account for both. One sums the fractional
effective doses (FED) over time,

$$
\mathrm{FED} = \int_{t_1}^{t_2}\left(\frac{1}{t_{I\,\mathrm{rad}}} + \frac{1}{t_{I\,\mathrm{conv}}}\right)\mathrm{d}t \qquad \text{(Eq. 63.48)}
$$

valid while the temperature is stable or increasing. The other computes the
total heat flux to the skin from radiant and convective components (Eq. 63.49),
which the Handbook calls the total incident flux (p. 2383) but writes as a
net exchange with the skin surface, and applies Eq. 63.43 to it, with the dose *D* in place of *r*: 1.33 for
pain, 10 for second-degree burns and severe incapacitation, 16.7 for
third-degree burns and a potentially fatal exposure (p. 2384). In Eq. 63.49
the emissivity ε is 0.05 for a gas and "perhaps 0.5 for smoke", and the
convective heat transfer factor is "approximately 5–8 for slow-moving air",
with no unit given (p. 2384). The Handbook applies this method to total
fluxes above 2.5 kW/m² (p. 2384). Below a hot layer in clear air, the
significant radiant sources are the layer, the fire and hot surfaces
(p. 2384). ISO 13571:2012
(§4.4) likewise assesses heat and radiant energy with an FED model analogous
to the gas model; its equations are given
[below](#iso-135712012-clause-8).

A summed dose is interpretable only when both terms are taken for the same
endpoint. Ch. 63 pairs them as follows (pp. 2382–2384):

| Endpoint | Radiant *r* (Eq. 63.43) | Convective law |
|---|---|---|
| Tolerance, severe pain | 1.33 | Eq. 63.45 |
| Serious injury, incapacitation | 10 | Eq. 63.46 |
| Fatal | 16.7 | Eq. 63.47 |

Eq. 63.44 is labelled a time to incapacitation, but its times lie near the
tolerance curve. Note (our arithmetic, not from the sources): at 100 °C it
gives 7.9 min, against 12.3 min from Eq. 63.45 (tolerance) and 35.6 min from
Eq. 63.46 (injury).

## ISO 13571:2012, clause 8

ISO 13571:2012 gives its own heat method in clause 8 (pp. 9–10). Its
endpoint is "compromised tenability", the inability to perform cognitive
and motor-skill functions at an acceptable level (§3.1); the standard avoids
the word incapacitation because it can be read to include collapse and
unconsciousness (§1).

**Criteria.** Of three ways heat threatens life (hyperthermia, body-surface
burns, respiratory-tract burns), ISO keeps two for modelling: the threshold
of second-degree skin burns, and hyperthermia severe enough to cause mental
deterioration (§8.1). As in Ch. 63, respiratory-tract burns are not expected
from air with less than 10 % water vapour by volume without burns to the
skin or face, but can occur from saturated air above 60 °C (§8.1, Note).

**Radiant heat.** ISO gives about 2.5 kW/m² as the tenability limit for
skin, which it calls an incident heat flux level; below it, exposure can be
tolerated for 30 min or longer (§8.2). Ch. 63 says "at least several
minutes" and more than 5 min (p. 2382, Table 63.20). Above the limit, with
*q* the radiant heat flux [kW/m²] and times in minutes,

$$
t_{I\,\mathrm{rad}} = 6.9\,q^{-1.56} \qquad \text{(ISO Eq. 7, second-degree burns)}
$$

$$
t_{I\,\mathrm{rad}} = 4.2\,q^{-1.9} \qquad \text{(ISO Eq. 8, pain)}
$$

Both are taken from Wieczorek and Dembsey (2001), ISO ref. [17], with an
estimated uncertainty of ±25 % (§8.2). ISO relates 2.5 kW/m² to a *source
surface* temperature of about 200 °C (§8.2); Ch. 63 relates it to a hot
*layer* at 200 °C (p. 2382). ISO does not use the dose form of Eq. 63.43.

**Convective heat.** For air with less than 10 % water vapour by volume
(§8.3), with *T* the air temperature [°C]:

$$
t_{I\,\mathrm{conv}} = 4.1\times10^{8}\,T^{-3.61} \qquad \text{(ISO Eq. 9, fully clothed)}
$$

$$
t_{I\,\mathrm{conv}} = 5\times10^{7}\,T^{-3.4} \qquad \text{(ISO Eq. 10, unclothed or lightly clothed)}
$$

Eq. (9) is cited to Crane (1978), ISO ref. [18]. Eq. (10) is cited to
Purser's chapter in the 4th edition of the SFPE Handbook, ISO ref. [2], and
has the constants of Eq. 63.44. ISO calls both empirical fits to human data,
with an estimated uncertainty of ±25 % (§8.3.2). The 120 °C limit for
unprotected skin is repeated there (§8.3.2, Note).

**Combining.** The heat FED is the sum over time steps of
\(1/t_{I\,\mathrm{rad}} + 1/t_{I\,\mathrm{conv}}\) (ISO Eq. 11), the form of
Eq. 63.48. ISO makes it conditional on the temperature experienced by the
occupant being stable or increasing (§8.4); Ch. 63 states the condition for
the temperature in the fire (p. 2383). The radiant term is set to zero where the radiant flux to the
skin is below 2.5 kW/m² (§8.4). The time at which the sum exceeds the chosen
threshold is the time to compromised tenability, in the same manner as for
the gases (§8.5, pointing to §5.3); see
[Incapacitation thresholds](/fundamentals/incapacitation-thresholds.md#heat).

**What ISO does not give.** No total-flux method: no Eq. 63.49, and so no
emissivity, convective coefficient or skin temperature. No counterpart of
Eqs. 63.45–63.47 and no radiant doses *r*. No temperature or flux range for
Eqs. (7) to (10), and no exposure-duration limit for heat; the caution on
exposures shorter than 1 min or longer than 1 h (§5.8) is stated for
asphyxiant gases. Ch. 63 states "up to 2 h" for Eq. 63.44 (p. 2382).

| | ISO 13571:2012 | SFPE Ch. 63 |
|---|---|---|
| Radiant law | \(a\,q^{-b}\): Eq. (7) burns, Eq. (8) pain | \(r/q^{1.33}\) with *r* per endpoint (Eq. 63.43) |
| Radiant limit | 2.5 kW/m² incident; ≥ 30 min below | 2.5 kW/m²; several minutes, > 5 min below |
| 200 °C relates to | a radiating source surface | a hot layer |
| Convective laws | Eq. (9) clothed; Eq. (10) unclothed = Eq. 63.44 | Eq. 63.44; Eqs. 63.45–63.47 per endpoint |
| Combination | Eq. (11), summed FED | Eq. 63.48, or total flux (Eq. 63.49) |
| Summed dose valid while | temperature experienced by the occupant is stable or increasing | temperature in the fire is stable or increasing |
| Stated uncertainty | ±25 % for Eqs. (7)–(10) | none |
| Humidity limit | < 10 % water vapour | < 10 % water vapour |
| Duration limit for heat | none stated | up to 2 h (Eq. 63.44) |

Our reading of the text, not a statement of the standard:

- **Endpoint of Eqs. (9) and (10).** §8.3 introduces them as the time to
  prevention of escape; §8.3.1 calls the same time the time to experiencing
  pain. Ch. 63 calls Eq. 63.44 a time to incapacitation.
- **Which radiant law enters Eq. (11).** Eqs. (7) and (8) share the symbol
  \(t_{I\,\mathrm{rad}}\), and §8.4 does not say which one to use. Either
  choice sums a radiant endpoint (burns or pain) with a convective one that
  is not stated to be the same.
- **Clothing.** ISO recommends Eq. (9) for fully clothed subjects. Ch. 63
  holds that light indoor clothing adds little tolerance and does not
  protect the hands and head, so it treats the unclothed expressions as the
  relevant ones unless protective clothing is worn (p. 2336).

![Two log-scale panels. Left: time to endpoint against radiant flux from 2.5 to 20 kW/m², ISO Eqs. 7 and 8 against SFPE Eq. 63.43 for r = 1.33 and 16.7 with the second-degree band r = 4.0 to 12.2 shaded, and the two radiant rows of Table 63.20. Right: time against air temperature from 60 to 250 °C, ISO Eqs. 9 and 10 against SFPE Eqs. 63.45 to 63.47, and the five convective rows of Table 63.20](/images/fundamentals/heat_iso.png)

*(a) Radiant: ISO's burn law (Eq. 7, red, circles) runs through the low
end of Ch. 63's second-degree band; ISO's pain law (Eq. 8, orange, squares)
crosses Ch. 63's pain dose r = 1.33 near 7.5 kW/m². (b) Convective: ISO's
clothed law (Eq. 9) gives about three times the tolerance time of the
unclothed law (Eq. 10, identical to Eq. 63.44). Solid over the span of
Table 63.20 (2.5–10 kW/m², 100–180 °C), dotted outside it: neither source
states the data range of its fits.*

{{< details title="Figure provenance" closed="true" >}}
ISO Eqs. (7) to (10) as in §8.2 and §8.3; SFPE Eqs. 63.43 and 63.45–63.47
(pp. 2382–2383); points from Table 63.20 (p. 2383): 30 s at 2.5 kW/m²,
4 s at 10 kW/m², and 12, 7, 4, 2 and 1 min at 100, 120, 140, 160 and
180 °C. Our arithmetic: written as the *r* of Eq. 63.43, Eq. (7) gives
r = 5.6 at 2.5 kW/m² and 4.1 at 10 kW/m²; Eq. (8) gives 2.5 and 1.1,
against 1.33–1.67 in Ch. 63. Eq. (8) gives 44 s at 2.5 kW/m² and 3 s at
10 kW/m², against 30 s and 4 s in Table 63.20. Eq. (9) gives 24.7 min at
100 °C, Eq. (10) 7.9 min; their ratio falls from 3.1 at 100 °C to 2.8 at
180 °C. Script: `scripts/figures/fundamentals_heat_iso.py`.
{{< /details >}}

## Known limits

Some cross-references in the text of Ch. 63 do not match the printed
equation labels: the text calls the radiant equation "Equation 63.41" and the
summed dose "Equation 63.46", and gives the endpoint times from flux as
"Equation 63.49" where the form is that of Eq. 63.43 (p. 2384). The labels above are those printed beside each
equation. The caption of Table 63.21 says its rates follow Eq. 63.44, but the
printed values (0.02, 0.19, 1.57 and 15.55 per minute at 65, 125, 220 and
405 °C) are those of Eq. 63.45. The note under Eq. 63.48 says that
\(t_{I\,\mathrm{rad}}\) tends to zero below 2.5 kW/m²; it is
\(1/t_{I\,\mathrm{rad}}\) that does.
Eq. 63.49 is printed with the division by 1000 on the convective term only,
although both terms are in W/m² and *q* is defined in kW/m².
The radiant tolerance data (Table 63.19) are incident flux on the skin,
whereas Eq. 63.49 is written as a net exchange with the skin surface; at the
200 °C anchor the two differ by about 20 %. FDS's `RADIATIVE HEAT FLUX` and
`RADIATIVE HEAT FLUX GAS` outputs are net as well,
\(\varepsilon_s(\dot q''_{\mathrm{inc}} - \sigma T_s^4)\) with
\(\varepsilon_s\) the surface emissivity; `INCIDENT HEAT FLUX` is the
incident term \(\dot q''_{\mathrm{inc}}\) (FDS User Guide 6.10,
Sec. 22.10.12, pp. 380–382).
The convective data concern hyperthermia in air of low humidity, and the
radiant data concern bare skin: clothing changes both. None of these
equations describe the effect of heat on walking speed or on route choice.

## Sources

- Purser, D. A., & McAllister, J. L. (2016). *Assessment of hazards to
  occupants from smoke, toxic gases, and heat*. SFPE Handbook of Fire
  Protection Engineering, 5th ed., Ch. 63, 2308–2428. Eqs. 63.43–63.49,
  Fig. 63.28 and Table 63.20.
  [doi:10.1007/978-1-4939-2565-0_63](https://doi.org/10.1007/978-1-4939-2565-0_63)
- ISO (2012). *ISO 13571:2012 Life-threatening components of fire —
  Guidelines for the estimation of time to compromised tenability in
  fires*, §1, §3.1, §4.4, §5.8 and clause 8 (Eqs. 7–11). ISO, Geneva.
  [iso.org/standard/56172](https://www.iso.org/standard/56172.html). Read
  in full from a licensed copy.
- Wieczorek, C. J., & Dembsey, N. A. (2001). Human variability correction
  factors for use with simplified engineering tools for predicting pain
  and second degree skin burns. *Journal of Fire Protection Engineering*,
  11(2), 88–111. ISO ref. [17] for Eqs. (7) and (8); not consulted.
  [doi:10.1106/0D9U-KLP9-TG1P-XJ1B](https://doi.org/10.1106/0D9U-KLP9-TG1P-XJ1B)
- Crane, C. (1978). *Human tolerance limit to elevated temperature: an
  empirical approach to the dynamics of acute thermal collapse*. Federal
  Aviation Administration, Memorandum Report ACC-114-78-2. ISO ref. [18]
  for Eq. (9); not consulted.

How pyFDS-Evac uses this: see [Models › Heat](/models/heat.md).
