---
title: "Seeing and using exit signs"
weight: 5
---

A cue such as an exit sign must be perceived, paid attention to and
comprehended before an occupant acts on it (Kuligowski and Kinateder
2026, Ch. 65, p. 2113). [Visibility through smoke](/fundamentals/visibility.md) covers
the first step: Jin's law *V* = *C*/*K* for the distance at which a sign is
barely seen. This page covers the rest: the steps between seeing a sign and
acting on it, the waypoint method that applies Jin's law along a line of
sight to a sign, and the studies that measured how often occupants detect
and follow signs.

## Terms

The sources use the same words for different thresholds. This page uses:

- **Seen.** The sign is barely visible: Jin's obscuration threshold
  ([Seeing a sign versus reading it](/fundamentals/visibility.md#seeing-a-sign-versus-reading-it)).
  Börger et al. (2024, Table 2, p. 9) call a sign that passes their test
  "visible". [Models › Wayfinding](/models/wayfinding.md) calls it
  *legible*.
- **Detected.** The occupant noticed the sign during a trial, as judged
  from questionnaires and video (Xie et al. 2012, p. 371) or from eye
  fixations (Zhu et al. 2021, p. 4).
- **Read** or **identified.** The occupant can make out the content of the
  sign: its letters, symbol or arrow. Jin (1978, Fig. 7, p. 143) and Xie
  et al. (2007) call this *legible*. Models › Wayfinding uses "read" and
  "reading distance" for the seeing test instead.
- **Followed.** The occupant took the direction the sign gives. The
  sources also say *complied* or *accepted*.

## From seeing a sign to using it

The SFPE Handbook states the general rule for any cue: it "must be
perceived (e.g., heard or seen), paid attention to, and then comprehended
first before any actions take place" (Kuligowski and Kinateder 2026,
Ch. 65, p. 2113). Its decision model puts the same three processes before
any protective action (p. 2110).

No study measures all of these steps for one sign in smoke. Each measures
one or two of them:

| Step | Measured as | Studies |
|---|---|---|
| Seen | smoke density at which a sign of known location vanishes | Jin 1970–1972 (see [Visibility](/fundamentals/visibility.md)) |
| Detected | share of people who noticed the sign | Xie et al. 2012; Galea et al. 2014; Zhu et al. 2021 |
| Read | sign size, distance or smoke density at which the content is made out | Wong and Lo 2007; Xie et al. 2007; Cheung et al. 2026 (thresholds) |
| Understood and followed | share of those who detected the sign and took its direction | Xie et al. 2012; Galea et al. 2014; Zhu et al. 2021 |

*Our reading:* Xie et al. (2012) and Galea et al. (2014) report
understanding and following together ("correctly interpret and follow"),
so neither separates the two.

## The waypoint method

Börger, Belt and Arnold (2024) apply Jin's law along the line of sight
from each grid cell of a floor plan to each exit sign, instead of at the
cell alone. They state that visibility "is not considered to be a local
quantity" (p. 3). The equations below are in their notation; σ̄ is a mean
extinction coefficient, written \(\bar K\) in the
[notation table](/docs/concepts.md#notation).

**The map.** A cell *i*, *j* is marked 1 for the sign at waypoint
\(W_k\) at time *t* when the available visibility reaches the distance to
the sign (Eq. 2, p. 3):

$$
M^t_{i,j,k} =
\begin{cases}
1, & V^t_{i,j,k} \ge L_{i,j,k},\\
0, & \text{otherwise,}
\end{cases}
$$

with \(L_{i,j,k}\) the horizontal distance between cell and sign; the
vertical height difference is ignored (Eq. 3, pp. 3–4). A cell is
passable at time *t* if at least one sign is visible from it (Eq. 4,
p. 4).

**The view angle.** Signs are treated as Lambertian radiators, "although
this assumption is highly simplified depending on the sign's light source
and surface" (p. 4). The visual distance falls with cos θ, citing
DIN ISO 3864-1, and a sign cannot be seen at θ ≥ 90° (Eq. 7, p. 4):

$$
A_{i,j,k} = \max\!\left(0,\ \frac{\sin\alpha_k\,(X_i - X_k) + \cos\alpha_k\,(Y_j - Y_k)}{L_{i,j,k}}\right)
$$

with \(\alpha_k\) the rotation angle of the sign's observation normal.
Only the horizontal angle is taken into account. Signs above doors sit
above the evaluation level, which the authors call "a particular though
minor degree of uncertainty" (p. 5).

**The obstruction.** \(U_{i,j,k}\) is 1 if the cell is not hidden from
the sign by a wall, 0 otherwise. It comes from a ray cast from the sign
and rasterised on the grid; anti-aliased lines keep the collision
detection reliable where obstruction cells do not form a closed barrier
(p. 5).

**The mean extinction.** Along the line of sight (Eq. 8, p. 5):

$$
\bar\sigma^t_{i,j,k} = \frac{K_m(\lambda)\int_0^{L_{i,j,k}} \rho^t_{s,k}(l)\,dl}{L_{i,j,k}}
$$

with \(\rho_s\) the smoke density and \(K_m\) the mass-specific extinction
coefficient; they note that 8700 m²/kg for red light at 633 nm is "widely
adopted" as the default of many fire models (p. 5). Assuming the same
path length in every traversed cell turns the integral into the
arithmetic mean over the cells \(P_\text{cells}\) (Eq. 9, p. 5):

$$
\bar\sigma^t_{i,j,k} = \frac{K_m(\lambda)}{|P_\text{cells}|}\sum_{p\in P_\text{cells}} \rho^t_{s,k,p}
$$

They describe the loss of accuracy as "tolerable, given a sufficiently
fine discretisation of the floor" (p. 5).

**The visibility.** Eq. 10 (p. 5), as printed:

$$
V^t_{i,j,k} = \min\!\left(U_{i,j,k}\cdot A_{i,j,k}\cdot\frac{C_k}{\bar\sigma^t_{i,j,k}},\ V_{\max}\right)
$$

\(C_k\) is Jin's constant for the sign, "usually *C* = 3 for reflecting
signs and *C* = 8 for light emitting signs" (Table 1, p. 5).

**The cap.** \(V_{\max}\) is "usually 30 m" (p. 4). The authors call it "an
arbitrary upper boundary value", set "since Jin's relation is purely
empirical and would imply an infinite visibility in the absence of smoke",
and add that "the exit signs have a maximum visual distance even in a
smoke-free environment" (p. 5). They give no sign size, luminance or
measurement for that distance. In their comparison, the FDS visibility
slice "was calculated with *C* = 3 and truncated at a maximum boundary of
30 m" (Fig. 6 caption, p. 7). *Our reading:* the paper does not name the
FDS parameter behind that truncation.

**The plane.** The eye is assumed at the height of the signs, and the
extinction is read from one horizontal slice "at a height of 2 m above
the floor level" (p. 4). The authors call this and the 2D approach
"technical limitations" for future work (p. 4).

The authors also write that Jin's model "needs to be fundamentally
revised": it does not account for the different absorption and scattering
of flaming and smouldering smoke, and gives limited scope for ambient light
(p. 9).

## Detection and reading studies

None of these studies used real fire smoke with occupants under threat.
The table gives the setting at a glance; the sections below give the
values.

| Study | Setting | People | Smoke |
|---|---|---|---|
| Xie et al. 2007 | 39 m corridor, signs turned to 0–80° | 48 | none |
| Wong and Lo 2007 | 18 m corridor, normal and emergency light | 30 | none |
| Xie et al. 2012 | university building, instructed trials | 68 | none |
| Galea et al. 2014 | same building, dynamic sign | 53 | none |
| Zhu et al. 2021 | T-junction drills, eye tracking | 23–33 per drill | none |
| Kobes et al. 2010 | hotel, unannounced night drills | 83 | visible smoke in two scenarios |
| Cheung et al. 2026 (thresholds) | smoke chamber, three sign types | 5 | white smoke |

### Reading distance and the observation angle (Xie et al. 2007)

Building regulations implicitly treat the region from which a sign can be
read, the visibility catchment area (VCA), as a semicircle centred on the
sign, independent of the observation angle (pp. 48 and 62). Xie et al.
assume instead that the eye resolves a fixed minimum angle; the VCA is
then a circle tangent to the sign (Eq. 4, p. 47), with a diameter about
equal to the radius of the regulatory semicircle (p. 48).

Forty-eight volunteers, 29 men and 19 women, walked towards a sign in a
39 m corridor under strong artificial light until they could resolve half
the letters. The sign was turned to 0°, 30°, 60°, 70° and 80° (pp. 49–51).
For the three signs, the mean distance fell from 19.8–33.1 m at 0° to
4.6–6.3 m at 80° (Table 2, p. 52). The data form "a slightly flattened
circle" (p. 53). The luminance of the signs was not considered (p. 49).

*Our arithmetic:* for Sign 1, cos 60° × 23.38 m = 11.7 m, while
14.82 m was measured (Table 2), so at large angles the data lie above a
pure cos θ law. This is a reading threshold in clear air; it does not test
the cos θ factor of the waypoint method, which applies to seeing in smoke.

### Detected, identified, identified with confidence (Wong and Lo 2007)

Thirty volunteers aged 18–55 looked at signs at the end of an 18 m
corridor, in clear air (p. 1837). For each sign they reported whether the
content was detected, identified or identified with confidence; the
measured quantity is the height of the sign content needed for each
(p. 1838). Under normal lighting, 115 lx on the floor, identification
needed 30–40 mm; under emergency lighting, 5 lx, it needed 53–60 mm
(p. 1840; lighting levels in the note to Table 3, p. 1839). Under
emergency lighting, detection needed 31–37 mm (p. 1840), so the gap
between seeing and reading the content was measured directly.

### Detection and following in a building (Xie et al. 2012)

Sixty-eight people, 41 unfamiliar and 27 familiar with the building, were
told to leave a university building as quickly as possible, one at a time,
by any route (p. 370). The signs were reflective, 0.1 × 0.3 m, in
well-lit areas above 100 lx (p. 369). Whether a person detected a sign was
judged mainly from a questionnaire, checked against video (p. 371).

Pooled over two decision points, so that each person counts twice:

- 38 % (31/82) of the unfamiliar and 30 % (16/54) of the familiar
  encounters detected the sign;
- of those who detected it, 97 % (30/31) and 94 % (15/16) "correctly
  interpret and follow the information conveyed by the sign"
  (p. 375).

At the sign approached head-on, unfamiliar people who detected it decided
in 2.6 s on average, those who did not in 5.6 s (Table I, p. 372). The
authors note that the earlier buildingEXODUS model assumed that agents
inside the VCA see the sign and then comprehend and follow it, "ideal
assumptions and not based on real-world data" (p. 376).

### A dynamic sign (Galea et al. 2014)

The same set-up, with a sign that added lit, flashing elements, was run
with 53 people unfamiliar with the building (pp. 1130 and 1138). At the
first decision point,
41 (77 %) said they saw the sign, and all of them followed it, against
38 % detection for the static sign (p. 1135).

### Detection by eye tracking, and following other people (Zhu et al. 2021)

Participants wore eye-tracking glasses, and a sign counted as detected
when the gaze stayed on it longer than 0.1 s (p. 4). Ten drills of 23–33
participants each met a T-junction with the sign at the bottom or the top,
and 0, 1 or 3 "disturbers", strangers or acquaintances (Table 1, p. 3). For the top
sign, detection was below 20 % with no disturbers, 41 % with one and 33 %
with three (p. 4). Among those who detected the sign, about 20 % followed
the disturbers instead (22 %, p. 6; "around 20 %", p. 7). The authors
state that the probabilities hold only for the crowds and environment
tested (p. 16).

The SFPE Handbook describes a related experiment by Zhu et al., from a
room into a corridor, in which participants complied with the sign more
often when alone or with three actors than with one actor (Kuligowski and
Kinateder 2026, Ch. 65, p. 2123).

### Exit choice with smoke and low signs (Kobes et al. 2010)

Eighty-three hotel guests were woken at night by a phone call and told to
leave. The scenarios were: no smoke with ceiling-level signs (20 people),
smoke poured into the corridor from a room with ceiling-level signs (39),
and smoke with signs at floor level (24) (pp. 539–540, Table 1). The
nearest fire exit was used by 45 %, 64.1 % and 75.0 % (p. 546). Of the
people who said they had used the exit signs, 22.2 % in the first and
33.3 % in the second scenario did not leave by the nearest fire exit,
against 6.7 % with floor-level signs (p. 547). The authors find
self-assessments and interviews after an evacuation "a disputable method"
and real-time observation more reliable (abstract, p. 537).

### Sign types in smoke (Cheung et al. 2026, thresholds)

Cheung et al. (2026, *Visibility performance thresholds of exit signs*)
tested an internally illuminated, a photoluminescent and a reflective exit
sign in a smoke chamber. Five men aged 25–39, with visual acuity 0.8 to
above 1.2, adjusted the light until they could identify the running-man
symbol or read 28 mm text (§2.2–2.3, pp. 3–4). *Our reading:* this is a reading
threshold, not Jin's obscuration threshold, although the authors compare
their values with Jin's. They report σ*V* = 3–7 for the lit sign
and 0.5–2 for the photoluminescent and reflective signs (abstract, p. 1).
The observers knew where the sign was (§2.4, p. 4). Smaller details, such
as 16 mm text or arrows, "were often unrecognizable in dense smoke or at
longer distances", so a sign "may be detected as glowing objects" while
its information is not conveyed (§4.1, p. 9).

### Signs among other lights

A field survey in an underground shopping mall found exit signs "often
masked by other background light noises" (Yamada and Akizuki 2026,
Ch. 68, p. 2216).

## Known limits

- **Laboratory and drill conditions.** The detection studies used clear
  air; Kobes et al. used smoke poured into a corridor during an
  unannounced drill. *Our reading:* no study above measured detection or
  following in real fire smoke.
- **Known sign locations.** Jin's observers and those of Cheung et al.
  (thresholds, §2.4, p. 4) knew where the sign was; for Jin's data, see
  [Visibility › Known limits](/fundamentals/visibility.md#known-limits).
  Cheung et al. (thresholds) write that this may overestimate visibility
  (§4.1, p. 9).
- **No threat of fire.** *Our reading:* instructed trials and drills
  carry no real threat of fire, like the stated-choice studies on
  [Exit choice › Known limits](/fundamentals/exit-choice.md#known-limits).
- **Binary and graded outcomes.** Jin's threshold and the waypoint map are
  yes or no. Wong and Lo grade the response in three steps, and the field
  studies report probabilities of detecting and following.
- **Self-report.** Detection in Xie et al. (2012) and Galea et al. (2014)
  is mainly what participants said afterwards; Kobes et al. question that
  method, and Zhu et al. measure gaze instead.
- **Small samples.** Cheung et al. (thresholds) had five observers; Zhu et
  al. state that their values hold only for the people and setting tested.

How pyFDS-Evac uses this: a sign-legibility test, a variant of Börger et
al.'s method, decides which neighbouring nodes an agent learns; the coded
form and where it departs from the paper are on
[Models › Wayfinding](/models/wayfinding.md#sign-visibility).

How it is verified: [Familiarity](/verification/testing-familiarity.md).

## Sources

- Börger, K., Belt, A., & Arnold, L. (2024). *A waypoint based approach to
  visibility in performance based fire safety design*. Fire Safety
  Journal, 150, 104269. Eqs. 2–4 and 7–10, pp. 3–5; Table 1, p. 5; Fig. 6, p. 7;
  Table 2 and conclusions, p. 9.
  [doi:10.1016/j.firesaf.2024.104269](https://doi.org/10.1016/j.firesaf.2024.104269)
- Cheung, W. K., Bielawski, J., Arnold, L., Huang, X., & Węgrzyński, W.
  (2026). *Visibility performance thresholds of exit signs in smoky indoor
  environments*. Fire Safety Journal, 163, 104779.
  [doi:10.1016/j.firesaf.2026.104779](https://doi.org/10.1016/j.firesaf.2026.104779)
- Galea, E. R., Xie, H., & Lawrence, P. J. (2014). *Experimental and survey
  studies on the effectiveness of dynamic signage systems*. Fire Safety
  Science, 11, 1129–1143.
  [doi:10.3801/IAFSS.FSS.11-1129](https://doi.org/10.3801/IAFSS.FSS.11-1129)
- Kobes, M., Helsloot, I., de Vries, B., Post, J. G., Oberijé, N., &
  Groenewegen, K. (2010). *Way finding during fire evacuation; an analysis
  of unannounced fire drills in a hotel at night*. Building and
  Environment, 45, 537–548.
  [doi:10.1016/j.buildenv.2009.07.004](https://doi.org/10.1016/j.buildenv.2009.07.004)
- Kuligowski, E. D., & Kinateder, M. (2026). *Human behavior in fire in the
  built environment*. SFPE Handbook of Fire Protection Engineering, 6th
  ed., Ch. 65. pp. 2110, 2113 and 2123.
  [doi:10.1007/978-3-031-59212-6_65](https://doi.org/10.1007/978-3-031-59212-6_65)
- Wong, L. T., & Lo, K. C. (2007). *Experimental study on visibility of
  exit signs in buildings*. Building and Environment, 42, 1836–1842.
  [doi:10.1016/j.buildenv.2006.02.011](https://doi.org/10.1016/j.buildenv.2006.02.011)
- Xie, H., Filippidis, L., Gwynne, S., Galea, E. R., Blackshields, D., &
  Lawrence, P. J. (2007). *Signage legibility distances as a function of
  observation angle*. Journal of Fire Protection Engineering, 17, 41–64.
  [doi:10.1177/1042391507064025](https://doi.org/10.1177/1042391507064025)
- Xie, H., Filippidis, L., Galea, E. R., Blackshields, D., & Lawrence,
  P. J. (2012). *Experimental analysis of the effectiveness of emergency
  signage and its implementation in evacuation simulation*. Fire and
  Materials, 36, 367–382.
  [doi:10.1002/fam.1095](https://doi.org/10.1002/fam.1095)
- Yamada, T., & Akizuki, Y. (2026). *Visibility and human behavior in fire
  smoke*. SFPE Handbook of Fire Protection Engineering, 6th ed., Ch. 68,
  p. 2216.
  [doi:10.1007/978-3-031-59212-6_68](https://doi.org/10.1007/978-3-031-59212-6_68)
- Zhu, Y., Chen, T., Ding, N., Chraibi, M., & Fan, W.-C. (2021). *Follow
  people or signs? A novel way-finding method based on experiments and
  simulation*. Physica A, 573, 125926.
  [doi:10.1016/j.physa.2021.125926](https://doi.org/10.1016/j.physa.2021.125926)

Jin (1970, 1972, 1978) and Cheung et al. (2026, *Reappraisal of Jin's
visibility through fire smoke experiment*) are listed on
[Visibility through smoke](/fundamentals/visibility.md#sources).
