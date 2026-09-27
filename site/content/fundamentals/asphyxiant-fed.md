---
title: "Asphyxiant fractional effective dose"
weight: 5
---

The fractional effective dose (FED) [-] is the fraction of an
incapacitating dose received, summed over short time steps; incapacitation
of a person of average susceptibility is predicted when it reaches 1. The
asphyxiants in fires are carbon monoxide (CO), hydrogen cyanide (HCN), low
oxygen (O₂) and carbon dioxide (CO₂), which speeds up breathing and so the
uptake of the others, and is itself an asphyxiant from about 5 % (Purser and
McAllister 2016, p. 2367).

Symbols follow the [notation table](/docs/concepts.md#notation). The
equations below keep the sources' own notation (\(F_I\) terms,
concentrations in brackets such as [CO], ventilation \(V_E\)).

## The ISO 13571 principle

ISO 13571:2012 (§6.1.1, Eq. 1) sums over gases *i* and time steps
\(\Delta t\) [min] the ratio \(C_i\,\Delta t/(C\cdot t)_i\) of the average
concentration \(C_i\) [µL/L] to the dose \((C\cdot t)_i\) that compromises
tenability, or equivalently \(\Delta t / t_i\) (Eq. 1a). Its gas-specific
terms are not reproduced here. Unlike Eq. 63.18 below, it expresses the CO
term as a Ct dose of 35 000 ppm·min, which Purser and McAllister equate to
light work at about 20 L/min rather than 25 L/min (2016, Note 2 to
Eq. 63.18, p. 2417), and does "not incorporate the rarefaction of oxygen", while
treating CO₂ as a hyperventilation factor (ISO/TR 13571-2:2016, §6.2).

## Purser's simplified equation

Purser and McAllister (2016, Society of Fire Protection Engineers (SFPE)
Handbook Ch. 63) give, for loss of consciousness of an adult doing light
work such as walking to escape,

$$
F_{IN} = \left(F_{I_{CO}} + F_{I_{CN}} + F_{I_{NO_x}} + FLD_{irr}\right)\times VCO_2 + F_{I_O}
\quad \text{or}\quad F_{I_{CO_2}} \qquad \text{(Eq. 63.38)}
$$

with the terms, *t* in minutes and concentrations in ppm or % by volume:

- **CO** (Stewart equation, Eq. 63.18):
  \(F_{I_{CO}} = 3.317\times10^{-5}\,[\mathrm{CO}]^{1.036}\,V_E\,t/D\), with
  \(V_E\) = 25 L/min (light work) and *D* = 30 % carboxyhaemoglobin (COHb)
  by default; *D* is 40 % at rest and 20 % for heavy work (table under
  Eq. 63.18, p. 2356). With these defaults the coefficient is
  \(3.317\times10^{-5}\times 25/30 = 2.764\times10^{-5}\) per minute, the
  constant used by FDS+Evac, the evacuation module of the Fire Dynamics
  Simulator (Korhonen 2021, Eq. 13).
- **HCN** (Eq. 63.24): \(F_{I_{CN}} = [\mathrm{CN}]^{2.36}\,t/(1.2\times10^{6})\),
  where [CN] may be corrected for other nitriles and for the protective effect
  of NO and NO₂ as \([\mathrm{CN}] = [\mathrm{HCN}] + [\text{organic nitriles}] - [\mathrm{NO}+\mathrm{NO_2}]\)
  (Eq. 63.26, p. 2362). The note to Eq. 63.38 writes the same correction with
  \(0.67\,[\mathrm{NO}+\mathrm{NO_2}]\) (p. 2372), so the chapter gives two
  coefficients.
- **NOₓ**: \(F_{I_{NO_x}} = [\mathrm{NO_x}]\,t/1500\) (definitions under Eq. 63.38).
- **Irritants**: \(FLD_{irr}\), the fractional lethal dose of irritants
  (Eq. 63.15; see [Irritant gases](/fundamentals/irritants.md)), included because
  irritants impair lung function and so add some hypoxia.
- **CO₂ hyperventilation** (Eq. 63.35): \(VCO_2 = \exp([\mathrm{CO_2}]/5)\).
  Purser recommends a limiting value of 70 L/min for \(V_E\times VCO_2\)
  (Ch. 63, p. 2416). At \(V_E\) = 25 L/min this caps \(VCO_2\) at 2.8,
  which Eq. 63.35 reaches at about 5.1 % CO₂ (our arithmetic).
- **Low-oxygen hypoxia** (Eq. 63.50):
  \(F_{I_O} = t/\exp\left[8.13 - 0.54\,(20.9 - [\%\mathrm{O_2}])\right]\),
  added outside the CO₂ multiplier because CO₂ improves oxygen uptake.
- **CO₂ as an asphyxiant**, \(F_{I_{CO_2}}\), from
  \(t_{I_{CO_2}} = \exp(6.1623 - 0.5189\,\%\mathrm{CO_2})\) (Eqs. 63.36–63.37),
  used as an alternative endpoint and normally negligible; sudden exposure
  to more than about 7 % CO₂, however, can itself cause rapid intoxication
  and collapse (pp. 2371–2372).

![CO FED rate per minute against CO concentration from 100 to 10 000 ppm on log–log axes: the Stewart equation for rest, light work and heavy work as three parallel lines about 12-fold apart, and the ISO 13571 rate C/35 000 just below the light-work line](/images/fundamentals/fed_co.png)

*CO FED rate [1/min] from the Stewart equation, Eq. 63.18, for rest
(pale blue, squares), light work (mid blue, circles) and heavy work (dark blue,
triangles), and the ISO 13571 dose of 35 000 ppm·min (red, dash-dot).
Heavy work accumulates dose about 12 times as fast as rest; the ISO rate
equals the Stewart form at D = 30 % for a V_E of about 20 L/min.*

{{< details title="Figure provenance" closed="true" >}}
Stewart: \(3.317\times10^{-5}\,[\mathrm{CO}]^{1.036}\,V_E/D\) per minute
(Eq. 63.18, p. 2356), with \(V_E\) = 8.5, 25 and 50 L/min and *D* = 40, 30
and 20 % (table under Eq. 63.18, p. 2356; table beside Eq. 63.39,
p. 2416). At 1000 ppm this gives 0.0090, 0.0354 and 0.106 per minute
(our arithmetic). ISO: [CO]/35 000 per minute, 0.0286 at 1000 ppm, the
Ct dose as given in Ch. 63, Note 2 to Eq. 63.18 (p. 2417). The \(V_E\)
at which the two agree for *D* = 30 % drifts from about 22 L/min at
100 ppm to 18.5 L/min at 10 000 ppm, because of the exponent 1.036 (our
arithmetic). Script: `scripts/figures/fundamentals_fed_co.py`.
{{< /details >}}

## Published forms differ

The FDS+Evac guide (Korhonen 2021, Eqs. 12–19) and the FDS User's Guide
(McGrattan et al. 2025, Eqs. 22.42–22.49) do not use Eq. 63.38 as printed:
they take Eq. 63.34 for CO₂ instead of its simplification Eq. 63.35, and an
HCN term \(\exp(C/43)/220\) that is not in Chs. 62–63 of the 5th edition,
where "exponential" names the power law of Eq. 63.20 (p. 2360). The
FDS+Evac guide cites the 3rd edition for these equations, the header of the
FDS `FED` function (`func.f90`) the 4th, and the FDS User's Guide the 5th.
The 3rd edition gives the term: \(F_{ICN} = \exp([\mathrm{CN}]/43)/220\)
(Purser 2002, p. 2-105), which it calls a simplification of
\(t_{ICN} = \exp(5.396 - 0.023\,C_{HCN})\) min (Eq. 9, regression
coefficient 0.984): \(1/0.023 \approx 43\) and \(e^{5.396} \approx 220\) (our
arithmetic). It has no offset. The 4th edition, which the FDS code cites, was
not read here. The User's Guide
reference (ref. [91]) is Ch. 62, which contains neither Eq. 63.34 nor an
HCN incapacitation term (text search of Ch. 62). A result quoted as "Purser FED"
therefore depends on the variant used.

{{< details title="The CO₂ factor and HCN term (Eqs. 63.31–63.35)" closed="true" >}}
A regression of minute volume on CO₂, fitted to three published human data
sets (Eq. 63.31, Fig. 63.26), gives the factor
\(\exp(0.2496\,\%\mathrm{CO_2} + 1.9086)/6.8\) (Eq. 63.32), simplified to
\(\exp([\mathrm{CO_2}]/4)\) (Eq. 63.33). Because that overstates uptake,
Ch. 63 modifies it after the Coburn–Forster–Kane equation to

$$
VCO_2 = \frac{\exp(0.1903\,\%\mathrm{CO_2} + 2.0004)}{7.1} \qquad \text{(Eq. 63.34)}
$$

and simplifies this to \(\exp([\mathrm{CO_2}]/5)\) (Eq. 63.35), the form
used in Eq. 63.38. The two agree within about 4 % below 5 % CO₂, and
at 0 % CO₂ Eq. 63.34 gives \(\exp(2.0004)/7.1 \approx 1.04\), not 1 (our
arithmetic; Hostikka and Linna 2025 make the same point). The chapter's own
worked example (Table 63.16, p. 2374), stated to follow Eq. 63.38, lists
\(VCO_2\) = 1.442, 2.376 and 4.434 at 1.5, 3.5 and 6 % CO₂. These match
Eq. 63.32, not Eq. 63.35, which gives 1.35, 2.01 and 3.32 (our arithmetic),
so the chapter is inconsistent here. Its 6 % point also exceeds the
70 L/min cap: 25 × 4.434 = 111 L/min (our arithmetic).

For HCN, the FDS+Evac guide uses
\(\left(\exp(C_{CN}/43)/220 - 0.0045\right)\) with
\(C_{CN} = C_{HCN} - C_{NO_2}\) (Korhonen 2021, Eqs. 14–15), citing Purser
in the 3rd edition (Purser 2002). The FDS User's Guide writes the same term
with \(C_{CN} = C_{HCN} - C_{NO_2} - C_{NO}\) (Eqs. 22.44–22.45). Both
manuals print the offset 0.0045, whereas FDS `func.f90` uses
0.00454545 ≈ 1/220; with 0.0045 the term is about \(4.5\times10^{-5}\)
per minute at 0 ppm instead of 0 (our arithmetic). The 5th
edition gives the power form instead (Eq. 63.24); its rat-lethality FED in
the companion chapter subtracts [NOx] from [CN] with coefficient 1 and uses
yet another CO₂ factor, \(1 + (\exp(0.14\,[\mathrm{CO_2}]) - 1)/2\)
(Purser 2016, Eq. 62.3, pp. 2227–2228). The offset makes the term
zero at zero concentration: Hostikka and Linna (2025, Eq. 3) write it as
\(F_{I,CN0} = \exp(0)/220\). They cite a 2010 Purser chapter ("Toxic hazard
calculation models for use with fire effluent data", their ref. [2]) for
three NOₓ reduction factors, 0 in simple conservative analyses, otherwise
2/3 or 1, "without a clear guidance which one to choose"; that chapter was
not read here. For low oxygen, the FDS+Evac
guide divides by an extra factor 60 while stating *t* in minutes (Eq. 18);
Eq. 63.50 and the FDS User's Guide (Eq. 22.48) do not. The factor is a
leftover from the 2009 guide (VTT Working Papers 119, FDS 5.3.0), which
gave every FED equation with *t* in seconds: its Eq. 12 is
\(4.607 \times 10^{-7}\,C_{CO}^{1.036}\,t\), i.e. \(2.764 \times 10^{-5}/60\),
and its Eq. 13 is \(t/(60\exp[8.13 - 0.54(20.9 - C_{O_2})])\), "where t is
time in seconds". The 2021 guide rewrote Eqs. 13–17 per minute and dropped
the 60, but kept it in Eq. 18. The FDS code divides by 60 because its time
step is in seconds (`func.f90`, function `FED`, before and after commit
694e033), so the code is consistent and only the 2021 guide's Eq. 18 is
not. The 2009 guide also prints the CO₂ coefficient as 0.1930 (Eq. 14),
where Purser and the code use 0.1903.
{{< /details >}}

![VCO2 against CO2 from 0 to 10 %: Eqs. 63.32 and 63.33 rise to about 12 at 10 %, Eqs. 63.34 and 63.35 lie close together and reach about 7; the three Table 63.16 points sit on Eq. 63.32; a horizontal line at 2.8 marks the 70 L/min cap](/images/fundamentals/fed_co2.png)

*CO₂ hyperventilation factor VCO₂ from Ch. 63: the regression Eq. 63.32
(red, circles) and its simplification Eq. 63.33 (red, dotted), the
modified Eq. 63.34 used by FDS and FDS+Evac (blue, squares) and its
simplification Eq. 63.35, used in Eq. 63.38 (orange, dash-dot). Diamonds:
the worked example, Table 63.16. Dotted grey: the cap of 2.8, i.e.
70 L/min at V_E = 25 L/min. Line styles here only separate the curves;
all lie within the 0–10 % CO₂ data.*

{{< details title="Figure provenance" closed="true" >}}
Eqs. 63.32–63.35 as written above (Ch. 63, pp. 2369–2371); Table 63.16
(p. 2374): 1.442, 2.376 and 4.434 at 1.5, 3.5 and 6 % CO₂, which Eq. 63.32
reproduces to three decimals (our arithmetic). The cap of 2.8 is Purser's
70 L/min limit for \(V_E\times VCO_2\) (p. 2416) at \(V_E\) = 25 L/min;
Eqs. 63.32 and 63.33 reach it at 4.2 and 4.1 % CO₂, Eq. 63.34 at 5.2 % and
Eq. 63.35 at about 5.1 % (our arithmetic). Script: `scripts/figures/fundamentals_fed_co2.py`.
{{< /details >}}

![Time to incapacitation by HCN against concentration from 20 to 300 ppm on a log time axis: Eq. 63.20 and the FDS exponential form cross near 70 and 115 ppm and diverge above 150 ppm, where the exponential form falls much faster; the critical range 80 to 180 ppm is shaded](/images/fundamentals/fed_hcn.png)

*Time to incapacitation [min] by HCN: Ch. 63 Eq. 63.20 (orange, circles)
and the FDS form 220/(exp(C/43) − 1) (blue, squares). Solid over the
primate data behind Eq. 63.20 (about 85–250 ppm, Fig. 63.24), dashed
outside; shaded: the critical range of about 80–180 ppm (p. 2361). The two
agree within 6 % between about 70 and 115 ppm; at 250 ppm the FDS form
gives 0.66 min against 2.6 min, four times shorter.*

{{< details title="Figure provenance" closed="true" >}}
Eq. 63.20: \(t_{ICN} = 1.2\times10^{6}/[\mathrm{CN}]^{2.36}\) (p. 2360).
FDS form: the inverse of the rate \(\exp(C/43)/220 - 1/220\) in FDS
`func.f90` (function `FED`), which uses the offset 0.00454545 ≈ 1/220, not
the manuals' 0.0045. The data span is that of Eq. 63.20's primate points
(our reading of Fig. 63.24); no data behind the FDS form are verified here.
Ratios of Eq. 63.20 to the FDS form: 0.96 at 100 ppm, 1.27 at 150, 2.1 at
200 and 4.0 at 250 ppm (our arithmetic).
Script: `scripts/figures/fundamentals_fed_hcn.py`.
{{< /details >}}

{{< details title="The data behind the terms" closed="true" >}}
- **CO.** The Stewart equation was obtained from young adult male
  volunteers; it somewhat underestimates uptake in children, and the
  Coburn–Forster–Kane equation is preferable near equilibrium (Ch. 63,
  Note 1 to Eq. 63.18, pp. 2416–2417). The linear form is offered for short
  exposures "when the blood concentration is well below saturation level"
  (p. 2352); that it overpredicts uptake as COHb approaches saturation is our
  inference, consistent with the source's comparison: for a 4 h exposure it predicts 50 % COHb at 550 ppm where the
  Coburn–Forster–Kane equation needs 840 ppm (p. 2352).
- **HCN.** The time to incapacitation \(t_{ICN} = 1.2\times10^{6}/[\mathrm{CN}]^{2.36}\)
  (Eq. 63.20) is fitted to resting macaque monkeys, with a regression
  coefficient of 0.84 (p. 2360; Fig. 63.24, primate points from about 85 to
  250 ppm). The legend of Fig. 63.24 gives the constant as
  \(1.21\times10^{6}\), the equation as \(1.2\times10^{6}\). It is applied to humans because the time to incapacitation of
  an average adult doing light work "would be similar to that in a resting
  monkey" (p. 2360). The critical range is about 80 ppm, below which incapacitation
  is unlikely within 1 h, to 180 ppm, above which it is rapid (p. 2361).
  Below about 85 ppm, the lower edge of the primate data, Eq. 63.20 is an
  extrapolation, and the 80 ppm bound sits at that edge (our reading of
  Fig. 63.24).
- **Low oxygen.** Eq. 63.27 is derived from the time of useful consciousness
  of resting humans after sudden decompression (under 1 s) to simulated
  altitudes of 20 000–40 000 ft, a sea-level equivalent of 9.6 % down to
  3.9 % O₂ (Fig. 63.25, pp. 2365–2366). In humans there is little effect
  down to 15 % O₂ (p. 2364). Use above about 10 % O₂ is therefore an
  extrapolation (our inference); the equation gives \(t_{IO}\) ≈ 140 min at
  15 % and about 35 h at 20 % O₂ (our arithmetic).
- **CO₂.** The minute-volume curve is an average of three human data sets
  covering 0–10 % CO₂ (Eq. 63.31, Fig. 63.26). \(t_{ICO_2}\) (Eq. 63.36) is
  derived from approximate tolerance data in Fig. 63.26, whose three points
  are 5 % for 30 min, 7.5 % for 10 min and 10.5 % for 2 min. It gives
  9.7 min at 7.5 % and 2.0 min at 10.5 %, but 35 min at 5 % (our
  arithmetic; p. 2368 uses 35.44 min); the 5 % point is severe breathing
  discomfort, not loss of consciousness. Eq. 63.36 thus rests on data from
  5 to 10.5 % CO₂ only; below 5 % it is an extrapolation (our inference).
- **Activity.** The default is light work; \(V_E\) = 8.5 L/min at rest and
  50 L/min for heavy work (table beside Eq. 63.39, p. 2416).
{{< /details >}}

![Low-oxygen time to incapacitation against O2 from 3.9 to 20.9 % on a log time axis: a straight line, solid over the decompression data from 3.9 to 9.6 % and dashed above, with vertical lines at 15 % (140 min) and 20 % (about 2090 min)](/images/fundamentals/fed_o2.png)

*Time to incapacitation by low oxygen, \(t_{IO}\) [min], from Eq. 63.50
(derived as Eq. 63.27): solid over the decompression data (3.9–9.6 % O₂,
shaded), dashed above. Dotted: 15 % O₂, down to which there is little
effect in humans (p. 2364), 140 min. Dash-dot: 20 % O₂, at or above which
FDS sets the O₂ term to zero, about 2090 min.
Almost all of the O₂ range a fire simulation visits is extrapolation.*

{{< details title="Figure provenance" closed="true" >}}
\(t_{IO} = \exp[8.13 - 0.54\,(20.9 - \%\mathrm{O_2})]\) (Eq. 63.50;
Eq. 63.27, pp. 2365–2366), 0.35 min at 3.9 %, 7.6 min at 9.6 % and
3395 min at 20.9 % (our arithmetic). Data span from Fig. 63.25. The 20 %
gate is the condition X_O2 < 0.20 in FDS `func.f90` (function `FED`),
quoted, not imported. Script: `scripts/figures/fundamentals_fed_o2.py`.
{{< /details >}}

## Known limits

The equations predict incapacitation of an average person; protecting more
susceptible people needs a threshold below 1 (see
[Incapacitation thresholds](/fundamentals/incapacitation-thresholds.md)).
ISO 13571 (§5.8) finds very little reliable information on exposures
shorter than 1 min or longer than 1 h, and its Introduction states that,
for ethical reasons, much of the method cannot be validated with humans,
although the CO database is extensive and well validated. The irritant
term \(FLD_{irr}\) is defined as a fractional lethal dose (p. 2416) but
described as a correction for the effect of irritants on lung function,
which adds some hypoxia (p. 2372). Read the first way, Eq. 63.38 adds a
lethal-dose fraction to incapacitating-dose fractions (Hostikka and Linna
2025); read the second way, it is a hypoxia correction scaled by the lethal
dose. The chapter does not say which reading is intended.

## Sources

- Purser, D. A., & McAllister, J. L. (2016). *Assessment of hazards to
  occupants from smoke, toxic gases, and heat*. SFPE Handbook of Fire
  Protection Engineering, 5th ed., Ch. 63, 2308–2428.
  [doi:10.1007/978-1-4939-2565-0_63](https://doi.org/10.1007/978-1-4939-2565-0_63)
- ISO (2012). *ISO 13571:2012 Life-threatening components of fire —
  Guidelines for the estimation of time to compromised tenability in
  fires*. ISO, Geneva.
  [iso.org/standard/56172](https://www.iso.org/standard/56172.html). Read
  from the public preview (§1–6.1.1).
- ISO (2016). *ISO/TR 13571-2:2016 Life-threatening components of fire —
  Part 2: Methodology and examples of tenability assessment*. ISO, Geneva.
  [iso.org/standard/65996](https://www.iso.org/standard/65996.html). Read
  from the public preview.
- Korhonen, T. (2021). *Fire Dynamics Simulator with Evacuation: FDS+Evac.
  Technical Reference and User's Guide* (FDS 6.7.6, Evac 2.6.0 draft),
  §3.4. VTT Technical Research Centre of Finland.
  [github.com/tkorhon1/FDS-Evac-Guide](https://github.com/tkorhon1/FDS-Evac-Guide).
  Secondary source.
- Purser, D. A. (2016). *Combustion toxicity*. SFPE Handbook of Fire
  Protection Engineering, 5th ed., Ch. 62, 2207–2307.
  [doi:10.1007/978-1-4939-2565-0_62](https://doi.org/10.1007/978-1-4939-2565-0_62)
- FDS source code, `Source/func.f90`, function `FED`, tag FDS6.7.6.
  [github.com/firemodels/fds](https://github.com/firemodels/fds/blob/FDS6.7.6/Source/func.f90).
  Secondary source.
- McGrattan, K., Hostikka, S., Floyd, J., McDermott, R., Vanella, M.,
  Mueller, E., & Paul, C. (2025). *Fire Dynamics Simulator User's Guide*,
  6th ed. (FDS 6.10.1), §22.10.18. NIST Special Publication 1019.
  [doi:10.6028/NIST.SP.1019](https://doi.org/10.6028/NIST.SP.1019).
  Secondary source.
- Hostikka, S., & Linna, A. (2025). *On the use of surrogate gases in fire
  toxicity calculations*. Fire Safety Journal, 156, 104435.
  [doi:10.1016/j.firesaf.2025.104435](https://doi.org/10.1016/j.firesaf.2025.104435).
  Secondary source.
- Purser, D. A. (2002). *Toxicity assessment of combustion products*. SFPE
  Handbook of Fire Protection Engineering, 3rd ed., 2-83–2-171. National
  Fire Protection Association, Quincy, MA. No DOI or public URL; cited
  through Korhonen (2021, ref. 29), which dates it 2003.

How pyFDS-Evac uses this: see [Fractional effective dose](/models/fed.md).
