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
exposure (Eq. 63.47). Thermal tolerance data for unprotected skin suggest a
limit of about 120 °C for convected heat, above which considerable pain
occurs quickly (Ch. 63, p. 2383 and Table 63.20). Burns to the respiratory
tract do not occur from air with less than 10 % water vapour in the absence
of burns to the facial skin, but saturated air above only 60 °C can cause
them (p. 2382).

## Radiant heat: pain and burns

The tenability limit for radiant heat on skin is about
**2.5 kW/m²**, below which exposure can be tolerated for at least several
minutes; at and above it, pain is followed by burns within seconds
(Ch. 63, p. 2382 and Table 63.20). Below
this flux the radiant contribution is neglected. Above it, the time
\(t_{I\,\mathrm{rad}}\) [min] to a given endpoint at radiant flux
*q* [kW/m²] is

$$
t_{I\,\mathrm{rad}} = \frac{r}{q^{1.33}} \qquad \text{(Eq. 63.43)}
$$

where *r* [(kW/m²)^4/3·min] is the dose for the endpoint: about 1.33–1.67 for
severe skin pain, 4.0–12.2 for second-degree burns and 16.7 for third-degree
burns. Purser proposes 1.33 as a tolerance threshold and 10 as a threshold
for incapacitation and serious injury (p. 2382). For occupants passing
under a hot smoke layer, 2.5 kW/m² corresponds approximately to a layer
temperature of 200 °C (p. 2382).

## Combining the two

Ch. 63 describes two ways to account for both. One sums the fractional
effective doses (FED) over time,

$$
\mathrm{FED} = \int_{t_1}^{t_2}\left(\frac{1}{t_{I\,\mathrm{rad}}} + \frac{1}{t_{I\,\mathrm{conv}}}\right)\mathrm{d}t \qquad \text{(Eq. 63.48)}
$$

valid while the temperature is stable or increasing. The other computes the
total heat flux to the skin from radiant and convective components (Eq. 63.49)
and applies Eq. 63.43 to it. ISO 13571:2012 (§4.4) likewise assesses heat
and radiant energy with an FED model analogous to the gas model. Note (not
from the sources): a summed dose is interpretable only when both terms are
taken for the same endpoint, for example incapacitation (*r* = 10) with
Eq. 63.44; the radiant pain dose (*r* = 1.33) is a different endpoint.

## Known limits

Some cross-references in the text of Ch. 63 do not match the printed
equation labels: the text calls the radiant equation "Equation 63.41" and the
summed dose "Equation 63.46". The labels above are those printed beside each
equation.
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
  fires*, §4.4. ISO, Geneva.
  [iso.org/standard/56172](https://www.iso.org/standard/56172.html).

How pyFDS-Evac uses this: see [Fractional effective dose](/models/fed.md#convective-heat).
