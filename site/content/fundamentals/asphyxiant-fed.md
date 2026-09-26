---
title: "Asphyxiant fractional effective dose"
weight: 5
---

The fractional effective dose (FED) [-] expresses an exposure to toxic gases
as the fraction of the dose that would incapacitate a person of average
susceptibility. Fractions are summed over successive short time steps, and
incapacitation of that average person is predicted when the sum reaches 1.
The asphyxiants of concern in fires are carbon monoxide (CO), hydrogen
cyanide (HCN), low oxygen (O₂) and, indirectly, carbon dioxide (CO₂), which
speeds up breathing and so the uptake of the others.

## The ISO 13571 principle

ISO 13571:2012 (§6.1.1, Eq. 1) defines the FED \(X_{\mathrm{FED}}\) as the
sum over asphyxiant gases *i* and time increments \(\Delta t\) [min] of
\(C_i\,\Delta t/(C\cdot t)_i\), where \(C_i\) [µL/L] is the average
concentration and \((C\cdot t)_i\) [µL/L·min] the exposure dose that
compromises tenability, or equivalently of \(\Delta t / t_i\), where \(t_i\) is the time to compromised tenability at
that concentration (Eq. 1a). The gas-specific terms of the standard are not
reproduced here. Two points of contrast with Purser are documented in
secondary sources: ISO 13571 expresses the CO term as a Ct dose of
35 000 ppm·min (Purser and McAllister 2016, Note 2 to Eq. 63.18), and its
asphyxiant model "does not incorporate the rarefaction of oxygen", while
treating CO₂ as a hyperventilation factor (ISO/TR 13571-2:2016, §6.2).

## Purser's simplified equation

Purser and McAllister (2016, Society of Fire Protection Engineers (SFPE)
Handbook Ch. 63) give, for loss of
consciousness of an adult doing light work such as walking to escape,

$$
F_{IN} = \left(F_{I_{CO}} + F_{I_{CN}} + F_{I_{NO_x}} + FLD_{irr}\right)\times VCO_2 + F_{I_O}
\quad \text{or}\quad F_{I_{CO_2}} \qquad \text{(Eq. 63.38)}
$$

with the terms, *t* in minutes and concentrations in ppm or % by volume:

- **CO** (Stewart equation, Eq. 63.18):
  \(F_{I_{CO}} = 3.317\times10^{-5}\,[\mathrm{CO}]^{1.036}\,V_E\,t/D\), with
  \(V_E\) = 25 L/min (light work) and *D* = 30 % carboxyhaemoglobin (COHb)
  by default. With these defaults the coefficient is
  \(3.317\times10^{-5}\times 25/30 = 2.764\times10^{-5}\) per minute, the
  constant used by FDS+Evac, the evacuation module of the Fire Dynamics
Simulator (Korhonen 2021, Eq. 13).
- **HCN** (Eq. 63.24): \(F_{I_{CN}} = [\mathrm{CN}]^{2.36}\,t/(1.2\times10^{6})\),
  where [CN] may be corrected for other nitriles and for the protective effect
  of NO and NO₂ as \([\mathrm{CN}] = [\mathrm{HCN}] + [\text{organic nitriles}] - [\mathrm{NO}+\mathrm{NO_2}]\)
  (Eq. 63.26).
- **NOₓ**: \(F_{I_{NO_x}} = [\mathrm{NO_x}]\,t/1500\) (definitions under Eq. 63.38).
- **Irritants**: \(FLD_{irr}\), the fractional lethal dose of irritants
  (Eq. 63.15; see [Irritant gases](/fundamentals/irritants.md)), included because
  irritants impair lung function and so add some hypoxia.
- **CO₂ hyperventilation** (Eq. 63.35): \(VCO_2 = \exp([\mathrm{CO_2}]/5)\).
  Purser recommends a limiting value of 70 L/min for \(V_E\times VCO_2\).
- **Low-oxygen hypoxia** (Eq. 63.50):
  \(F_{I_O} = t/\exp\left[8.13 - 0.54\,(20.9 - [\%\mathrm{O_2}])\right]\),
  added outside the CO₂ multiplier because CO₂ improves oxygen uptake.
- **CO₂ as an asphyxiant**, \(F_{I_{CO_2}}\), from
  \(t_{I_{CO_2}} = \exp(6.1623 - 0.5189\,\%\mathrm{CO_2})\) (Eqs. 63.36–63.37),
  used as an alternative endpoint and normally negligible.

## The CO₂ factor has several published forms

Ch. 63 derives \(VCO_2\) in steps (Eqs. 63.31–63.35). A regression of minute
volume on CO₂ gives \(\exp(0.2496\,\%\mathrm{CO_2} + 1.9086)/6.8\)
(Eq. 63.32), simplified to \(\exp([\mathrm{CO_2}]/4)\) (Eq. 63.33). Because
that overstates uptake, a form modified after the Coburn–Forster–Kane
equation is given as

$$
VCO_2 = \frac{\exp(0.1903\,\%\mathrm{CO_2} + 2.0004)}{7.1} \qquad \text{(Eq. 63.34)}
$$

which is simplified to \(\exp([\mathrm{CO_2}]/5)\) (Eq. 63.35), the form used
in Eq. 63.38. The FDS+Evac guide uses Eq. 63.34 and the older exponential HCN
term \(\left(\exp(C_{CN}/43)/220 - 0.0045\right)\) with \(C_{CN} = C_{HCN} - C_{NO_2}\),
citing Purser in the 3rd edition of the Handbook (Korhonen 2021, Eqs. 12–19).
A result quoted as "Purser FED" therefore depends on the edition.

## The data

The CO term comes from the Stewart equation, obtained from young adult male
volunteers; Purser notes that it somewhat underestimates uptake in children
and that the Coburn–Forster–Kane equation is preferable near equilibrium.
The HCN term is fitted to exposures of non-human primates, the hypoxia term to
human data, and the CO₂ curve to three human data sets (Ch. 63). The
default is light work; \(V_E\) = 8.5 L/min at rest and 50 L/min for heavy work.

## Known limits

The equations predict incapacitation of an average person; a threshold below
1 is needed to protect more susceptible people (see
[Incapacitation thresholds](/fundamentals/incapacitation-thresholds.md)).
ISO 13571 (§5.8) states that there is very little reliable information on
exposures shorter than 1 min or longer than 1 h. Its Introduction states that,
for ethical reasons, much of the methodology has not been and cannot be
validated with humans, while the database for CO is extensive and
well-validated with human experience.

## Sources

- D. A. Purser and J. L. McAllister (2016). Assessment of hazards to
  occupants from smoke, toxic gases, and heat. *SFPE Handbook*, 5th ed.,
  Ch. 63, 2308–2428.
  [doi:10.1007/978-1-4939-2565-0_63](https://doi.org/10.1007/978-1-4939-2565-0_63)
- ISO 13571:2012. *Life-threatening components of fire — Guidelines for the
  estimation of time to compromised tenability in fires.*
  [iso.org/standard/56172](https://www.iso.org/standard/56172.html). Read
  from the public preview (§1–6.1.1).
- ISO/TR 13571-2:2016. *Life-threatening components of fire — Part 2:
  Methodology and examples of tenability assessment.*
  [iso.org/standard/65996](https://www.iso.org/standard/65996.html). Read
  from the public preview.
- T. Korhonen (2021). *FDS+Evac Technical Reference and User's Guide*, §3.4.
  VTT Technical Research Centre of Finland. Secondary source.

How pyFDS-Evac uses this: see [Fractional effective dose](/models/fed.md).
