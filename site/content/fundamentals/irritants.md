---
title: "Irritant gases"
weight: 7
---

Irritant gases such as hydrogen chloride (HCl), hydrogen bromide (HBr),
hydrogen fluoride (HF), sulphur dioxide (SO₂), nitrogen dioxide (NO₂),
acrolein and formaldehyde act in two ways. Sensory irritation of the eyes and
upper airways is felt immediately and depends on the concentration: it
impairs escape at once. Damage to the deep lung depends on the inhaled dose
and develops over hours. The literature treats the two with different
quantities, and the standards and the handbook combine them differently.

Symbols follow the [notation table](/docs/concepts.md#notation). The
equations below keep the sources' own notation (FEC, \(F_{\mathrm{FIC}}\),
\(F_{\mathrm{FLD}}\)).

## ISO 13571: a separate concentration endpoint

ISO 13571:2012 treats asphyxiants and irritants separately, because they are
"physiologically unrelated and mechanistically independent" (§4.2.1). For
irritants it considers only eye and upper-respiratory-tract sensory
irritation. It computes a fractional effective concentration (FEC) [-] for
each irritant at each time increment, from the concentration and not from
the dose, and compromised tenability is predicted when the sum of the FECs
exceeds a threshold (§4.2.3). The FEC is a separate endpoint: it is not added
to the asphyxiant fractional effective dose (FED). The same threshold value must be used for FED and FEC
in a given estimation (§5.4). Pulmonary irritation is excluded because its
serious effects appear hours to days after exposure (§4.2.1).

## Purser: a concentration term and a dose term

Purser and McAllister (2016, Society of Fire Protection Engineers (SFPE)
Handbook Ch. 63) define the fractional irritant
concentration (FIC) [-] as a sum over irritants, each term being the current
concentration divided by the concentration predicted to cause a chosen
endpoint:

$$
\mathrm{FIC} = \mathrm{FIC_{HCl}} + \mathrm{FIC_{HBr}} + \mathrm{FIC_{HF}} + \mathrm{FIC_{SO_2}} + \mathrm{FIC_{NO_2}} + \mathrm{FIC_{CH_2CHO}} + \mathrm{FIC_{HCHO}} + \sum \mathrm{FIC}_x
\qquad \text{(Eq. 63.11)}
$$

The denominators are tabulated for two endpoints, escape impairment and
incapacitation (Table 63.6, SFPE columns). Purser states that a factor of
0.3 on the FEC for escape impairment should allow nearly all exposed people
to escape (Ch. 63, p. 2414). Like the ISO FEC, the FIC is a concentration criterion and is
not integrated over time. The same table lists the corresponding ISO 13571
values, which differ for several gases: for HCl, for example, the SFPE
incapacitation concentration is 900 ppm and the ISO value 1000 ppm
(Table 63.6).

The lung effects are a dose. The fractional lethal dose of irritants
\(FLD_{irr}\) [-] sums, for each irritant, the Ct exposure dose [ppm·min]
divided by the dose predicted to be lethal to half the population (Eq. 63.15,
Table 63.7, e.g. 114 000 ppm·min for HCl). Purser notes that lung irritation
has relatively little effect on escape capability and "can be omitted from an
escape calculation" (p. 2415), but in the simplified asphyxiant equation he includes
\(FLD_{irr}\) inside the sum that is multiplied by the CO₂ factor, because
irritants impair lung function and add some hypoxia (Eq. 63.38; see
[Asphyxiant FED](/fundamentals/asphyxiant-fed.md)).

## Purser: irritants and walking speed

Purser (2003, pp. 93 and 99–100) proposed that irritants do not slow
people at low concentrations and stop effective movement at
incapacitation, FIC = 1, with a sigmoid fall in between: "a curve has been
fitted between these two extremes" (p. 93). Ch. 63 calls it an "estimated
relationship" based on a concept (p. 2343, Fig. 63.17). In our reading, no
walking data lie behind the curve. Ch. 63 gives it as

$$
F_{wv\,irr} = \frac{e^{-(1000\,x/b)^2} + (-0.2\,x + 0.2)}{1.2},
\qquad b = 160,\ x = \mathrm{FIC}
\qquad \text{(Eq. 63.13)}
$$

where \(F_{wv\,irr}\) is the fractional walking speed (1 = normal walking
speed of 1.2 m/s). It is 1 at FIC = 0, about 0.31 at FIC = 0.2 and 0 at
FIC = 1 (Ch. 63, p. 2344). The smoke and irritant effects are combined by
adding their losses (Purser 2003, p. 100; Ch. 63, Eq. 63.14, p. 2345):

$$
F_{wv} = 1 - (1 - F_{wv\,smoke}) - (1 - F_{wv\,irr})
$$

where \(F_{wv\,smoke}\) is the fractional walking speed due to smoke
obscuration (see [Walking speed in smoke](/fundamentals/walking-speed.md)).
The sum can fall below 0, and neither source clips it. It assumes a smoke
term for non-irritant smoke, as in Purser's 2003 fit to Jin's data; pairing
it with Eq. 63.10, which is fitted to pooled "moderately irritant" data,
would in our reading count irritancy twice (see
[Walking speed in smoke](/fundamentals/walking-speed.md#purser-a-logarithmic-fit-for-irritant-smoke)).

![Fractional walking speed against FIC from Eq. 63.13: 1 at FIC 0, 0.71 at 0.1, 0.31 at 0.2, 0.08 at 0.5 and 0 at 1](/images/fundamentals/irritant_speed.png)

*Fractional walking speed against fractional irritant concentration FIC
from Ch. 63, Eq. 63.13, drawn thin because, in our reading, no walking data
lie behind it. Script: `scripts/figures/fundamentals_irritant_speed.py`.*

{{< details title="The equation as printed in Purser (2003)" closed="true" >}}
Purser (2003, p. 100) prints the curve of his Fig. 1 as
\(F_{wv\,irr} = 1 - \big((1 - e^{-(x/b)^a}) + (-0.2x + 0.2)/1.2\big)\)
with *a* = 2, *b* = 160, *x* = FIC. As printed it gives 0.83 at FIC = 0
and rises to 1 at FIC = 1, the opposite of his Fig. 1. We compared it
with values read from Fig. 1 (about 1.0, 0.92, 0.71, 0.31, 0.14, 0.08 and
0 at FIC = 0, 0.05, 0.1, 0.2, 0.3, 0.5 and 1), scaling *x* by 1, 10, 100,
1000 and 10 000, in both terms or in the exponential term only. No scaling
gives 1 at FIC = 0, because the linear term alone fixes 0.83 there. The
best tested case, 1000 *x* in the exponent only, ends at 0 at FIC = 1 but
dips to −0.10 in between, with a mean absolute error of 0.16 against the
readings. Ch. 63's Eq. 63.13, with 1000 *x* in the exponent and the whole
numerator divided by 1.2, matches the readings with a mean absolute error
of 0.002, and is the form given above. The figure on this page is computed
from Eq. 63.13, not from the 2003 printing. A second, minor misprint:
Purser (2003, p. 99) refers to "Figure 2" for the irritant curve, which is
his Fig. 1.
{{< /details >}}

## The Purser / FDS+Evac guide form

The guide to [FDS+Evac](https://github.com/firemodels/fds/tree/c9da70d7a/Source), the evacuation module of the Fire Dynamics Simulator
(Korhonen 2021, Eqs. 12 and 17, Table 2), follows this
structure: its total dose

$$
\mathrm{FED_{tot}} = \left(\mathrm{FED_{CO}} + \mathrm{FED_{CN}} + \mathrm{FED_{NO_x}} + \mathrm{FLD_{irr}}\right)\times \mathrm{HV_{CO_2}} + \mathrm{FED_{O_2}}
$$

adds the irritant lethal dose into the incapacitation sum, and its Table 2
lists both the lethal doses \(F_{FLD}\) and the incapacitating concentrations
\(F_{FIC}\). The values in that table agree with the SFPE columns of Tables
63.6 and 63.7. This sum is the Purser / FDS+Evac guide form. It is not the
ISO 13571 form, which keeps irritants out of the FED altogether.

## Known limits

Human measurements at incapacitating concentrations cannot be made for
ethical reasons, and most of the experimental work behind the irritant
values used animals, mostly rodents (Ch. 63, p. 2343). The endpoint concentrations
differ between sources by up to an order of magnitude; for SO₂, Table 63.6
gives 24 ppm for SFPE escape impairment and 150 ppm for ISO incapacitation.
Individual sensitivity is wide: for HCl, Purser proposes 200 ppm as the
escape-impairment concentration for the average person, but notes that some
people may be impaired at 60 ppm and others may escape through about
400–600 ppm (p. 2343). The concentrations of acrolein and formaldehyde are
rarely known in a fire, and Ch. 63 suggests a smoke-density surrogate when
they are not (pp. 2344–2345).

## Sources

- ISO (2012). *ISO 13571:2012 Life-threatening components of fire —
  Guidelines for the estimation of time to compromised tenability in
  fires*, §4.2 and §5.4. ISO, Geneva.
  [iso.org/standard/56172](https://www.iso.org/standard/56172.html). Read
  from the public preview.
- Purser, D. A., & McAllister, J. L. (2016). *Assessment of hazards to
  occupants from smoke, toxic gases, and heat*. SFPE Handbook of Fire
  Protection Engineering, 5th ed., Ch. 63, 2308–2428. Eqs. 63.11,
  63.13–63.15, 63.38, Tables 63.6–63.7.
  [doi:10.1007/978-1-4939-2565-0_63](https://doi.org/10.1007/978-1-4939-2565-0_63)
- Purser, D. A. (2003). *ASET and RSET: addressing some issues in relation
  to occupant behaviour and tenability*. Fire Safety Science, 7, 91–102.
  [doi:10.3801/IAFSS.FSS.7-91](https://doi.org/10.3801/IAFSS.FSS.7-91)
- Korhonen, T. (2021). *Fire Dynamics Simulator with Evacuation: FDS+Evac.
  Technical Reference and User's Guide* (FDS 6.7.6, Evac 2.6.0 draft),
  §3.4. VTT Technical Research Centre of Finland.
  [github.com/tkorhon1/FDS-Evac-Guide](https://github.com/tkorhon1/FDS-Evac-Guide).
  Secondary source.

How pyFDS-Evac uses this: see [Fractional effective dose](/models/fed.md).

How it is verified: the FED and FIC rows of the [Verification](/verification/_index.md) index; the HCN, NOₓ and irritant terms are not yet verified end to end ([#257](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/257)).
