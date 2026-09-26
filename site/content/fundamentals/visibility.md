---
title: "Visibility through smoke"
weight: 3
---

Visibility *S* [m] is the greatest distance at which an object, typically an
exit sign, can still be seen through smoke. Its standard engineering form is
due to Tadahisa Jin, who measured the distance at which signs vanished in
smoke-filled chambers.

Symbols follow the [notation table](/docs/concepts.md#notation). The
equations below keep the SFPE Handbook's own notation: *V* for the
visibility *S*, \(C_s\) for the extinction coefficient *K* and *k* for the
constant *C*.

## The equation as published

Jin found that, in the range of visibilities from about 5 to 15 m, the
product of the visibility at the obscuration threshold and the smoke density
was almost constant (Jin 1978, as reported by Yamada and Akizuki 2016,
Society of Fire Protection Engineers (SFPE) Handbook Ch. 61, Eq. 61.4 and
Fig. 61.8). Ch. 61
writes it with \(C_s\) [1/m] for the extinction coefficient:

$$
V = k\,\frac{1}{C_s} \qquad \text{(Eq. 61.4)}
$$

with the constant in the range

$$
V = \frac{5}{C_s} \text{ to } \frac{10}{C_s} \;\text{for a light-emitting sign},
\qquad
V = \frac{2}{C_s} \text{ to } \frac{4}{C_s} \;\text{for a reflecting sign}
\qquad \text{(Eqs. 61.5, 61.6)}
$$

The Fire Dynamics Simulator (FDS) User Guide (§22.10.5, Eq. 22.23) writes the same law as
\(S = C/K\), with *C* = 8 for a light-emitting sign and *C* = 3 for a
light-reflecting sign, citing Mulholland (2002) in the 3rd edition of the
SFPE Handbook, and uses *C* = 3 by default (`VISIBILITY_FACTOR`). FDS
reports visibility up to a maximum of 30 m by default
(`MAXIMUM_VISIBILITY`, §22.10.5).

## What *C* means

*C* is not a tuning constant. Jin derived the law from a contrast model
(Ch. 61, Eq. 61.3) in which the visibility of a sign depends on the sign's
brightness, the contrast threshold of the observer, the illuminance and the
scattering properties of the smoke. For reflecting signs the constant depends
mainly on the sign's reflectance and the illuminating light. *C* is therefore
a property of the sign and its lighting, and should be chosen from the type
of sign, not adjusted to fit an outcome.

## The data

Jin viewed signs in a smoke-filled chamber from outside through a window
(Ch. 61, Fig. 61.8). Later experiments in non-irritant white smoke without
background light found the constant tends to be larger than Jin's values;
ordinary light-emitting exit signs were lost at about 10 m in smoke of
\(C_s\) = 1.0 1/m (Ch. 61, Fig. 61.9 and Table 61.1). Visibility in black (flaming) smoke was somewhat better than
in white smoke of the same density. For reading the words on a sign, the
constant product holds only in non-irritant smoke. In irritant smoke,
legibility falls sharply above a certain density, and above about
0.5 1/m subjects could keep their eyes open only briefly (Ch. 61,
Fig. 61.11, from the corridor experiments of Jin 1978 and Jin and Yamada
1985).

## Known limits

The law describes a straight, unobstructed line of sight through uniform
smoke to one object. It does not describe how far a person can see around
corners, or how much smoke a person walks through. The constant was measured
over a limited visibility range (about 5–15 m for Eq. 61.4), and the range of
*C* for a given sign type is a factor of two wide. The equation gives a
threshold for seeing a sign, not for recognising or understanding it.

## Sources

- Jin, T. (1978). *Visibility through fire smoke*. Journal of Fire &
  Flammability, 9, 135–157. No DOI or public URL; read through Ch. 61
  (its ref. 6).
  [Fridolf et al. (2019)](https://doi.org/10.1016/j.tust.2019.04.016) give
  9(2), 135–155, and the
  [FDS+Evac guide](https://github.com/tkorhon1/FDS-Evac-Guide) gives
  9, 135–155.
- Jin, T., & Yamada, T. (1985). *Irritating effects of fire smoke on
  visibility*. Fire Science and Technology, 5(1), 79–90.
  [doi:10.3210/fst.5.79](https://doi.org/10.3210/fst.5.79)
- Yamada, T., & Akizuki, Y. (2016). *Visibility and human behavior in fire
  smoke*. SFPE Handbook of Fire Protection Engineering, 5th ed., Ch. 61,
  2181–2206.
  [doi:10.1007/978-1-4939-2565-0_61](https://doi.org/10.1007/978-1-4939-2565-0_61)
- McGrattan, K., Hostikka, S., Floyd, J., McDermott, R., Vanella, M.,
  Mueller, E., & Paul, C. (2025). *Fire Dynamics Simulator User's
  Guide*. National Institute of Standards and Technology (NIST) Special
  Publication 1019, 6th ed., revision FDS-6.10.1-0-g12efa16, §22.10.5.
  [github.com/firemodels/fds/releases/tag/FDS-6.10.1](https://github.com/firemodels/fds/releases/tag/FDS-6.10.1)
- Mulholland, G. W. (2002). *Smoke production and properties*. SFPE
  Handbook of Fire Protection Engineering, 3rd ed. National Fire
  Protection Association, Quincy, MA. No DOI or public URL; cited through
  the FDS User Guide (its ref. 83).

How pyFDS-Evac uses this: see
[visibility and cognitive maps](/models/visibility.md).
