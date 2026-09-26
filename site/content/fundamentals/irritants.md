---
title: "Irritant gases"
weight: 6
---

Irritant gases such as hydrogen chloride (HCl), hydrogen bromide (HBr),
hydrogen fluoride (HF), sulphur dioxide (SO₂), nitrogen dioxide (NO₂),
acrolein and formaldehyde act in two ways. Sensory irritation of the eyes and
upper airways is felt immediately and depends on the concentration: it
impairs escape at once. Damage to the deep lung depends on the inhaled dose
and develops over hours. The literature treats the two with different
quantities, and the standards and the handbook combine them differently.

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

For the effect of irritants on walking, Ch. 63 gives a fractional walking
speed that falls to zero at FIC = 1 (Eq. 63.13, a Gaussian-type curve with
*b* = 160), and combines it with the smoke-visibility effect by adding the
two losses, \(F_{wv} = 1 - (1 - F_{wv\,smoke}) - (1 - F_{wv\,irr})\) (Eq. 63.14).

The lung effects are a dose. The fractional lethal dose of irritants
\(FLD_{irr}\) [-] sums, for each irritant, the Ct exposure dose [ppm·min]
divided by the dose predicted to be lethal to half the population (Eq. 63.15,
Table 63.7, e.g. 114 000 ppm·min for HCl). Purser notes that lung irritation
has relatively little effect on escape capability and "can be omitted from an
escape calculation" (p. 2415), but in the simplified asphyxiant equation he includes
\(FLD_{irr}\) inside the sum that is multiplied by the CO₂ factor, because
irritants impair lung function and add some hypoxia (Eq. 63.38; see
[Asphyxiant FED](/fundamentals/asphyxiant-fed.md)).

## The Purser / FDS+Evac guide form

The guide to FDS+Evac, the evacuation module of the Fire Dynamics Simulator
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
- Korhonen, T. (2021). *Fire Dynamics Simulator with Evacuation: FDS+Evac.
  Technical Reference and User's Guide* (FDS 6.7.6, Evac 2.6.0 draft),
  §3.4. VTT Technical Research Centre of Finland.
  [github.com/tkorhon1/FDS-Evac-Guide](https://github.com/tkorhon1/FDS-Evac-Guide).
  Secondary source.

How pyFDS-Evac uses this: see [Fractional effective dose](/models/fed.md).
