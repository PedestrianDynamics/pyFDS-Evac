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

This page covers the concentration criteria (ISO's FEC and Purser's FIC),
the denominators each one uses, Purser's relation between FIC and walking
speed, and the lung dose. In short, the published rule **adds** the speed
losses from smoke and from irritants. It does not multiply them
([Eq. 63.14](#combining-with-smoke-the-losses-add)).

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

In ISO's Eq. (4) (§6.2.1, p. 7), each term is the volume fraction of an
irritant divided by \(F_i\), the concentration of that irritant at which
tenability is expected to be seriously compromised:

$$
\mathrm{FEC} = \sum_i \frac{\varphi_i}{F_i}
$$

ISO gives \(F_i\) [µl/l, equal to ppm] as HCl 1000, HBr 1000, HF 500,
SO₂ 150, NO₂ 250, acrolein 30 and formaldehyde 250, with an uncertainty of
±50 % (§6.2.1). The sum is formed at each time increment and treated as
instantaneous (§6.2.1, NOTE 1). Irritants have no effect on the asphyxiant
FED (§6.1, NOTE 5). ISO 13571 gives no relation between irritants and
walking speed.

## Purser: the fractional irritant concentration (FIC)

Purser and McAllister (2016, Society of Fire Protection Engineers (SFPE)
Handbook Ch. 63) define the fractional irritant
concentration (FIC) [-] as a sum over irritants, each term being the current
concentration divided by the concentration predicted to cause a chosen
endpoint:

$$
\mathrm{FIC} = \mathrm{FIC_{HCl}} + \mathrm{FIC_{HBr}} + \mathrm{FIC_{HF}} + \mathrm{FIC_{SO_2}} + \mathrm{FIC_{NO_2}} + \mathrm{FIC_{CH_2CHO}} + \mathrm{FIC_{HCHO}} + \sum \mathrm{FIC}_x
\qquad \text{(Eq. 63.11)}
$$

The chapter repeats the sum as Eq. 63.12 (p. 2343) and in its appendix
(p. 2414); the 2026 edition numbers them Eqs. 70.9 and 70.10. The terms
stand for immediate sensory effects, so Ch. 63 expects them to ease when the
concentrations fall, for example when a person leaves the contaminated area
(p. 2343). Like the ISO FEC, the FIC is a concentration criterion. It is not
a dose and is not integrated over time.

### Which endpoint goes in the denominator

The chapter uses two endpoints, and different equations use different ones:

- **Escape impairment:** Eq. 63.8 (p. 2333) and the text under Eq. 63.12
  (p. 2343).
- **Either endpoint:** the appendix, which names both SFPE columns of
  Table 63.6 (p. 2414).
- **Incapacitation:** the walking-speed relation, Eq. 63.13, where FIC = 1
  means incapacitation (p. 2344; Purser 2003, p. 99). Ch. 63 introduces it
  for concentrations below the SFPE incapacitation column (p. 2343).
- p. 2325 reads FIC = 1 as significant impairment and FIC = 5 as roughly
  incapacitation, which in our reading is the escape-impairment scale.

The denominators [ppm] side by side: SFPE escape impairment, SFPE
incapacitation and AEGL-2 for 10 min from Table 63.6 (p. 2344), and ISO
13571 \(F_i\) (§6.2.1, p. 7):

| Gas | SFPE escape | SFPE incap. | ISO \(F_i\) | AEGL-2 |
|---|---|---|---|---|
| HCl | 200 | 900 | 1000 | 100 |
| HBr | 200 | 900 | 1000 | 100 |
| HF | 200 | 900 | 500 | 95 |
| SO₂ | 24 | 120 | 150 | 0.75 |
| NO₂ | 70 | 350 | 250 | 20 |
| Acrolein | 4 | 20 | 30 | 0.44 |
| Formaldehyde | 6 | 30 | 250 | 14 |

Three things follow from the table (our arithmetic):

- The escape-impairment values are about 0.2 of the incapacitation values:
  200/900 = 0.22 for the three halogen acids and 0.20 for the other four
  gases. This matches p. 2325, where FIC = 5 on the escape scale is roughly
  incapacitation.
- The sets disagree gas by gas. SFPE incapacitation and ISO differ by up to
  about 8× (formaldehyde, 30 against 250 ppm). SFPE escape impairment and ISO
  differ by up to about 40× (formaldehyde, 6 against 250 ppm). The same smoke
  gives very different FIC values depending on the set.
- ISO's FEC and SFPE's FIC do not share denominators, so an FEC of 1 and an
  FIC of 1 describe different mixtures.

**The factor 0.3.** Ch. 63 mentions it twice. The escape-impairment values
are to be used "with an FED factor of 0.3 to allow for sensitive
individuals" (p. 2343), and "a factor of 0.3 FEC for escape impairment"
should let nearly all exposed people escape (p. 2414). The same page 2343
explains the number: a significant proportion of people may be impaired at
about 0.3 of the concentration that affects the average person, which for
HCl is 60 ppm instead of 200 ppm. In our reading, 0.3 is therefore a
sensitive-person factor on the escape-impairment values. It is not the ratio
between the escape and incapacitation columns (about 0.2), and it does not
apply to the incapacitation values.

![Denominators of the FIC and FEC for seven irritant gases on a logarithmic ppm axis, one marker per endpoint set: SFPE escape impairment, SFPE incapacitation, ISO 13571 and AEGL-2. For SO₂ the four values run from 0.75 to 150 ppm](/images/fundamentals/fic_denominators.png)

*Denominators [ppm] per gas for four endpoint sets, log scale: SFPE escape
impairment and SFPE incapacitation (Table 63.6, p. 2344), ISO 13571
(§6.2.1, p. 7) and AEGL-2 for 10 min (Table 63.6). The dotted lines mark HCl
at 900 ppm (SFPE incapacitation) and 1000 ppm (ISO, the example of
Fig. 63.17). NO is left out: it has no escape-impairment value, its
incapacitation value is given only as ">1000", and it is not in the FIC
sum. Script: `scripts/figures/fundamentals_fic_denominators.py`.*

## Irritants and walking speed (FIC)

Purser (2003, pp. 94 and 99–100) proposed that irritants do not slow
people at low concentrations and stop effective movement at
incapacitation, FIC = 1, with a sigmoid fall in between: "a curve has been
fitted between these two extremes" (p. 94). Ch. 63 calls it an "estimated
relationship" based on a concept and on the concentration estimated to be
very painful (p. 2343); the curve is Fig. 63.17 (p. 2344). Neither source
gives walking data or fit statistics for it; in our reading, it is a concept
curve with no walking data behind it. Ch. 63 gives it as

$$
F_{wv\,irr} = \frac{e^{-(1000\,x/b)^2} + (-0.2\,x + 0.2)}{1.2},
\qquad b = 160,\ x = \mathrm{FIC}
\qquad \text{(Eq. 63.13)}
$$

where \(F_{wv\,irr}\) is the fractional walking speed (1 = normal walking
speed of 1.2 m/s). The 2026 edition gives the same curve as Eq. 70.11. The
source states only the end point, 0 at FIC = 1 (p. 2344). Our arithmetic
gives 1.000, 0.914, 0.714, 0.308, 0.141 and 0.083 at FIC = 0, 0.05, 0.1,
0.2, 0.3 and 0.5. The formula holds for 0 ≤ FIC ≤ 1 only: above 1 it turns
negative, for example −0.083 at FIC = 1.5.

Jin's experiments, which Ch. 63 cites for the link between irritancy and
walking speed (p. 2343), give no FIC values: they index irritancy by the
extinction coefficient *K*, and the smoke composition was not reported
(Purser 2003, p. 98).

**Which denominators?** Ch. 63 writes Eq. 63.13 with FIC = 1 meaning
incapacitation "(e.g., 1000 ppm HCl)" (p. 2344), as Purser does (2003,
p. 99). That HCl example is the ISO value; the SFPE incapacitation value is
900 ppm. Purser defines the FIC of his speed curve as the concentration
"expressed as a fraction of the concentration predicted to cause
incapacitation" (2003, p. 99), so the curve takes the incapacitation
denominators. With the escape-impairment set, walking speed would reach 0
at 200 ppm HCl instead of 900 ppm.

The earlier chapter (Purser 2002, SFPE 3rd ed., Sec. 2, Ch. 6) uses the
other scale: FIC = 1 there means escape impairment, and incapacitation lies
at a multiple of it that the chapter states three ways: FIC about 3–5
(p. 2–91), a factor of about four or more (p. 2–121), and 5–10 times the
FIC (p. 2–132).

![Fractional walking speed against FIC from Eq. 63.13: 1 at FIC 0, 0.71 at 0.1, 0.31 at 0.2, 0.08 at 0.5 and 0 at 1, continued as a dotted line to FIC 1.2 where it falls below zero](/images/fundamentals/irritant_speed.png)

*Fractional walking speed against fractional irritant concentration FIC
from Ch. 63, Eq. 63.13, drawn thin because, in our reading, no walking data
lie behind it. Dotted beyond FIC = 1, outside the curve's range, where the
formula goes negative. Script: `scripts/figures/fundamentals_irritant_speed.py`.*

### Combining with smoke: the losses add

Purser multiplies the unexposed walking speed by the fraction (2003,
p. 98). He treats the effects of smoke and irritants as essentially additive
(p. 99) and adds their losses (Purser 2003, p. 100; Ch. 63, Eq. 63.14,
p. 2345; Eq. 70.12 in the 2026 edition, p. 2289):

$$
F_{wv} = 1 - (1 - F_{wv\,smoke}) - (1 - F_{wv\,irr})
\qquad \text{(Eq. 63.14)}
$$

where \(F_{wv\,smoke}\) is the fractional walking speed due to smoke
obscuration (see [Walking speed in smoke](/fundamentals/walking-speed.md)).
The walking speed is \(F_{wv}\) times the unexposed speed.

- **No clipping.** The sum can fall below 0, and neither source clips it. It
  is at most 0 whenever \(F_{wv\,irr} = 0\) (FIC = 1) and
  \(F_{wv\,smoke} < 1\).
- **Non-irritant smoke only.** \(F_{wv\,smoke}\) has to be a law for
  non-irritant smoke. Purser pairs it with his fit to Jin's non-irritant data
  (2003, p. 98). Pairing it with Eq. 63.10, which is fitted to pooled
  "moderately irritant" data, would in our reading count irritancy twice (see
  [Walking speed in smoke](/fundamentals/walking-speed.md#purser-a-logarithmic-fit-for-irritant-smoke)).

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
from Eq. 63.13, not from the 2003 printing. Two minor misprints: Purser
(2003, p. 99) refers to "Figure 2" for the irritant curve, which is his
Fig. 1, and calls the FIC axis the "ordinate" (pp. 99–100), which is the
abscissa; Ch. 63 has "x-axis".
{{< /details >}}

## Purser: a dose term for lung effects

The lung effects are a dose. The fractional lethal dose of irritants
\(FLD_{irr}\) [-] sums, for each irritant, the Ct exposure dose [ppm·min]
divided by the dose predicted to be lethal to half the population (Eq. 63.15,
Table 63.7, e.g. 114 000 ppm·min for HCl). Purser notes that lung irritation
has relatively little effect on escape capability and "can be omitted from an
escape calculation" (p. 2415), but in the simplified asphyxiant equation he includes
\(FLD_{irr}\) inside the sum that is multiplied by the CO₂ factor, because
irritants impair lung function and add some hypoxia (Eq. 63.38; see
[Asphyxiant FED](/fundamentals/asphyxiant-fed.md)).

{{< details title="Misprints in Ch. 63 that the 2026 edition corrects" closed="true" >}}
- **"Numerator" for denominator.** Under Eq. 63.12, Ch. 63 calls both parts
  of each FIC term the "numerator" (p. 2343); the second is the denominator.
  The 2026 edition corrects it (p. 2289).
- **Table 63.7, AEGL-3 column.** For NO, acrolein and formaldehyde the
  values are shifted down one row (75, 2100 and blank). Table 70.5 of the
  2026 edition (p. 2290) gives NO blank, acrolein 75 and formaldehyde 2100.
  The 2026 values agree with the 30-min AEGL-3 concentrations of Table 63.6
  times 30 min (2.5 × 30 = 75 and 70 × 30 = 2100 ppm·min); that check is
  ours.
{{< /details >}}

## FDS+Evac and FDS

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

No equation in the guide uses \(F_{FIC}\), and the FDS+Evac source
(`evac.f90`) computes no FIC. FDS+Evac slows people only through the
Frantzich–Nilsson relation of the guide's Eq. 11, with a floor of
0.1·\(v_0\) (p. 29). FDS itself outputs \(\mathrm{FIC_{irr}}\) as a
diagnostic quantity (User's Guide 2025, Eq. 22.50 and Table 22.3, p. 390).
Its denominators are the concentrations expected to cause incapacitation in
half the population, the same values as the SFPE incapacitation column.

## Known limits

Human measurements at incapacitating concentrations cannot be made for
ethical reasons, and most of the experimental work behind the irritant
values used animals, mostly rodents, together with expert judgement
(Ch. 63, p. 2343). The three FIC and FEC denominator sets (SFPE escape impairment, SFPE
incapacitation, ISO) differ by up to about 40× for one gas (formaldehyde,
6 ppm for SFPE escape impairment against 250 ppm for ISO; our arithmetic), so the choice of endpoint set
changes FIC more than the choice of speed law does.
Individual sensitivity is wide: for HCl, Purser proposes 200 ppm as the
escape-impairment concentration for the average person, but notes that some
people may be impaired at 60 ppm and others may escape through about
400–600 ppm (p. 2343). The concentrations of acrolein and formaldehyde are
rarely known in a fire, and Ch. 63 suggests a smoke-density surrogate when
they are not (pp. 2344–2345). The walking-speed curve Eq. 63.13 is a concept
curve without fitted data and is defined only for FIC from 0 to 1.

## Sources

- ISO (2012). *ISO 13571:2012 Life-threatening components of fire —
  Guidelines for the estimation of time to compromised tenability in
  fires*, §4.2, §5.4, §6.1 (NOTE 5) and §6.2.1 (Eq. 4, NOTE 1, p. 7).
  ISO, Geneva.
  [iso.org/standard/56172](https://www.iso.org/standard/56172.html).
  Read from the full text; paraphrased except the quoted phrase of §4.2.1.
- Purser, D. A., & McAllister, J. L. (2016). *Assessment of hazards to
  occupants from smoke, toxic gases, and heat*. SFPE Handbook of Fire
  Protection Engineering, 5th ed., Ch. 63, 2308–2428. pp. 2325, 2333,
  2342–2345, 2414–2415; Eqs. 63.8, 63.11–63.15, 63.38; Tables 63.6–63.7.
  [doi:10.1007/978-1-4939-2565-0_63](https://doi.org/10.1007/978-1-4939-2565-0_63)
- Purser, D. A., & McAllister, J. L. (2026). *Assessment of hazards to
  occupants from smoke, toxic gases, and heat*. SFPE Handbook of Fire
  Protection Engineering, 6th ed., Ch. 70, 2271–2352. pp. 2287–2290;
  Eqs. 70.9–70.12; Table 70.4 (identical to Table 63.6) and Table 70.5.
  [doi:10.1007/978-3-031-59212-6_70](https://doi.org/10.1007/978-3-031-59212-6_70)
- Purser, D. A. (2002). *Toxicity assessment of combustion products*.
  SFPE Handbook of Fire Protection Engineering, 3rd ed., Sec. 2, Ch. 6.
  NFPA, Quincy, MA. pp. 2–91, 2–121, 2–132.
- Purser, D. A. (2003). *ASET and RSET: addressing some issues in relation
  to occupant behaviour and tenability*. Fire Safety Science, 7, 91–102.
  pp. 94, 98–100.
  [doi:10.3801/IAFSS.FSS.7-91](https://doi.org/10.3801/IAFSS.FSS.7-91)
- McGrattan, K., Hostikka, S., Floyd, J., McDermott, R., Vanella, M.,
  Mueller, E., & Paul, C. (2025). *Fire Dynamics Simulator User's Guide*,
  6th ed., Eq. 22.50 and Table 22.3, p. 390. NIST Special Publication 1019.
  [doi:10.6028/NIST.SP.1019](https://doi.org/10.6028/NIST.SP.1019)
- Korhonen, T. (2021). *Fire Dynamics Simulator with Evacuation: FDS+Evac.
  Technical Reference and User's Guide* (FDS 6.7.6, Evac 2.6.0 draft),
  §3.4, Eq. 11, Table 2. VTT Technical Research Centre of Finland.
  [github.com/tkorhon1/FDS-Evac-Guide](https://github.com/tkorhon1/FDS-Evac-Guide).
  Secondary source.

How pyFDS-Evac uses this: see [Fractional effective dose](/models/fed.md).
Its opt-in irritant slowdown uses a different curve and multiplies it with
the smoke factor
([Models › FED](/models/fed.md#irritant-slowdown-against-the-published-rule)).

How it is verified: the FED and FIC rows of the [Verification](/verification/_index.md) index; the HCN, NOₓ and irritant terms are not yet verified end to end ([#257](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/257)).
