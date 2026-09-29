---
title: "Visibility through smoke"
weight: 3
---

Visibility *V* [m] is the greatest distance at which an object, typically an
exit sign, can still be seen through smoke. Its engineering form, *V* =
*C*/*K*, is due to Tadahisa Jin, who measured in the 1970s the smoke density
at which a sign in a smoke-filled chamber vanished for an observer outside
it. Cheung et al. (2026) rebuilt that chamber and repeated the experiment
at lower ambient light. It is the only modern replication we have, and this
page follows it where it tests Jin's law.

Symbols follow the [notation table](/docs/concepts.md#notation), except
that this page writes *V* for the table's *S*, as every source does; *L*
here is ambient light and α a reflectance. The sources use other letters
for the same quantities:

| This page | Meaning | Jin 1970–1972 | Jin and Yamada 1985; SFPE Ch. 61 | Cheung et al. 2026 |
|---|---|---|---|---|
| *K* [1/m] | extinction coefficient, natural log | σ | \(C_s\) | σ |
| *V* [m] | visibility at the obscuration threshold | *V* | *V* | *V* |
| *C* [–] | constant of *V* = *C*/*K* | σ·*V* | *k* in Ch. 61 Eq. 61.4 | *K* |
| \(B/L\) [–] | sign luminance over ambient light | \(B_{E0}/L\) | \(B_{EO}/L\) with \(L = E/\pi\); \(L_t/(E/\pi)\) | \(\pi L_t/E\) |
| \(\delta_c\) [–] | threshold contrast | \(\delta_c\) | \(\delta_c\) | \(\delta_c\) |
| \(k_s\) [–] | scattering over total extinction | *k* | *K* (1985); α (Ch. 61) | α |

Jin and Yamada (1985) also use α for the reflectance of a placard. Jin
measured sign luminance in apostilb (asb); 1 asb = 1/π cd/m² (Cheung et
al., Eq. 5). Jin 1970 (B in asb, *L* the illuminance; Fig. 9 plots B/E)
and Jin and Yamada 1985 (B in cd/m², *L* = *E*/π, Appendix Eq. A-3) define
the same ratio, \(\pi L_t/E\). Jin 1971 prints B in asb together with
*L* = *E*/π, which would make the ratio π times larger and break the
placard identity \(B = \alpha L\); *in our reading* this is a unit slip.
The redraws of Jin's lit-sign data in Jin and Yamada (1985, Fig. 1) and
Jin (2002, Fig. 2-4.2) label as "500 and 2000 cd/m²" the signs that Jin
(1971, Fig. 1) gives as 500 and 2000 asb, that is, 159 and 637 cd/m²; the
data points match (our comparison), so the redraws overstate those
luminances by π.

## Jin's experiments

Everything below rests on a short series of papers, all by Jin and all
read for this page.

| Paper | Set-up | Range |
|---|---|---|
| Jin 1970, *Visibility through fire smoke (I)* | Chamber 1.2 × 1.2 × 5.5 m, lit by 24 fluorescent lamps of 10 W, white paint inside; signs viewed from outside through glass; two mirrors extend the path to 10.5 and 15.5 m; white smoke from 5–10 g of filter paper heated to 400 °C at about 10 % O₂; a 1 m light-path densitometer (pp. 3–4, Fig. 3). Lit sign: a circle of 5, 10 or 15 cm projected on frosted glass, sized for the same visual angle at each distance, brightness set by the observer. Placard: circles of four fixed reflectances on a black backing (p. 4). | *V* = 5.5, 10.5, 15.5 m; ambient 22, 60, 180 lx; *K* ≈ 0.3–1.8 1/m for lit signs and about 0.1–0.8 1/m for placards (Figs. 4–10). The number of observers is not stated. |
| Jin 1971, *(II)* | Same method, smoke from Japanese cedar and plastics, smouldering (white) and flaming (black); measured \(k_s\), \(\delta_c\) and particle sizes. | Lit signs of 500–2000 asb in acrylic smoke at 80 lx (Fig. 1); placards of reflectance 0.13–0.70 in polystyrene smoke at 40 lx (Fig. 2); *V* ≈ 5.5–15.5 m (our reading of the points). |
| Jin 1972, *(III)* | Ten observers aged 23–37 (Table 1; all male according to Jin 1976, p. 12), walked a 20 m smoke-filled corridor towards a commercial lit EXIT sign and marked where they saw it, told its colour and read its letters (Figs. 1–2). Irritant white smoke from tightly packed wood cribs, non-irritant black smoke from kerosene. Corridor at about 80 lx, or a blackout at 0.1–0.5 lx (p. 13). | *K* ≈ 0.3–1.1 1/m, *V* ≈ 4–16 m (Figs. 3–5, our reading). Observers waited in a normally lit room first, so the blackout runs were not dark-adapted (p. 12). |
| Jin and Yamada 1985 | Twelve subjects aged 20–30, one woman, read a Landolt ring chart at 4 m in an 18 m² room filled with irritant smoke from smouldering wood chips, wearing sealed ski goggles or, as the comparison "without goggles", an
unsealed, perforated goggle of the same 65 % transmittance, with noses
covered by a towel (pp. 82–84). | *K* ≈ 0–0.7 1/m (Figs. 5–6). |

Jin's later reviews (Jin and Yamada 1985, §2; Jin 1997, §1.2; Jin 2002,
the SFPE Handbook 3rd ed., Ch. 2-4) restate these results and cite a 1978
journal paper for them, which we could not obtain (see [Sources](#sources)).

## The contrast model

Jin (1970, pp. 2–3) starts from the contrast between a sign and its
background. A sign is seen while its contrast with the background exceeds a
threshold \(\delta_c\); smoke both dims the light from the sign and scatters
ambient light towards the eye. For a sign much brighter than its background
this gives (Jin 1970, Eq. 4; the same in V-form in Jin 1971, Eq. 1)

$$
K\,V \approx \ln\frac{B_{E0}}{\delta_c\, k_s\, L} \qquad \text{(Jin 1970, Eq. 4)}
$$

with \(B_{E0}\) the sign's brightness, *L* the ambient light and
\(k_s = \sigma_s/K\) the share of extinction due to scattering. Jin takes
\(\delta_c \approx 0.01\) under general lighting and \(k_s \approx 1\) for
nearly white smoke (abstract, p. 1). For a placard, \(B_{E0} = \alpha L\)
with reflectance α, and *L* cancels (Eq. 7, p. 6):

$$
K\,V \approx \ln\frac{\alpha}{\delta_c\, k_s} \qquad \text{(Jin 1970, Eq. 7; Jin 1971, Eq. 2)}
$$

Jin and Yamada (1985, Appendix, pp. 88–89) derive the same result in
detail.

The constants are partly measured and partly assumed:

- \(\delta_c\) was measured photometrically only at 180 lx: 0.010–0.013
  looking directly and 0.018–0.021 through the two mirrors, at *K* =
  0.8–1.4 1/m (Jin 1970, Table 1, p. 6). Elsewhere it is back-calculated
  from threshold data through \(\delta_c = (B_{E0}/k_s L)\,e^{-KV}\) with
  \(k_s\) assumed (Jin 1971, Eq. 3, p. 22): 0.01–0.02 over 5–15 m under
  usual corridor light, rising steeply when the light falls below about
  30–60 lx (Jin 1971, Fig. 8, pp. 22–23). Jin (1972, Figs. 6–7) gives only
  relative values of the same kind (p. 14). 0.01–0.05
  (Jin and Yamada 1985, p. 80). When observers did not know where the sign
  was, 0.05–0.10 instead of 0.01–0.02 (Jin 1972, p. 15, citing a 1972
  paper of his in the Transactions of the Architectural Institute of
  Japan, not read).
- \(k_s\): 1 for smouldering smoke is *assumed*, on the reasoning that
  white smoke hardly absorbs (Jin 1971, p. 19); flaming values are ratios
  to it, 0.3–1.0, for example 0.3 for kerosene and polyurethane foam and
  0.5 for Japanese cedar (Tables 1–2). Jin and Yamada (1985, p. 80) and Jin
  (1997, p. 5) give 0.4–1.0. Because \(k_s\) sits inside the logarithm,
  0.4–1.0 changes *KV* by ln 2.5 ≈ 0.9 and 0.3–1.0 by ln 3.3 ≈ 1.2 (our
  arithmetic).

Jin found that the measured critical *K* at 5.5 m rose linearly with the
logarithm of sign brightness at each ambient light (Jin 1970, Figs. 4–5,
p. 4), and that plotting against \(B_{E0}/L\) collapsed the three light
levels onto one line (Fig. 6, p. 5). At 180 lx, the data at all three
distances followed the theoretical curve with \(\delta_c = 0.01\) and
\(k_s = 1\) (Fig. 11, p. 7; the figure shows only 180 lx). Jin (1970,
p. 4) recorded the sign brightness and the change of chamber illuminance
during each run; lit-sign runs reproduced within about three repeats,
placards needed more than ten.

## From the model to V = C/K

If the sign, the ambient light and the smoke are fixed, the right-hand side
of Eq. 4 is a constant (Jin 1970, Eq. 5, p. 5):

$$
V = \frac{C}{K}
$$

**The ranges.** Jin (1970, abstract, p. 1) gives the visibility of the
placard as about (2–4)/*K* and of the lit sign as about (5–10)/*K*. The
ends are partly estimates. Our translation of p. 7: from Fig. 11,
\(B_{E0}/L = 1\) gives *KV* ≈ 4.5; a placard of reflectance 1 is hard to
make, so the best real placard reaches about 4; a lit sign can in theory
reach any value by a brighter lamp, but in practice perhaps 10 at most. The
measured placard lines are *KV* = 4.0, 3.1 and 2.2 for reflectances of 60,
30 and 14 % on a 7 % background at 180 lx (Fig. 10, p. 6). Jin and Yamada
(1985, p. 81), Jin (1997, Eqs. 3–4, p. 6) and Jin (2002, Eqs. 3–4,
p. 2-43) repeat the ranges; Yamada and Akizuki (2016, SFPE Handbook 5th
ed., Ch. 61, Eqs. 61.4–61.6, pp. 2186–2187) reproduce them.

**The range of validity.** Jin (1971, abstract p. 17 and p. 18) states that
*KV* is almost constant for visibilities of 5–15 m, in white and in black
smoke, for lit signs and placards; strictly, *KV* falls slightly as the
distance grows, which he attributes to \(\delta_c\) rising with distance
(Jin 1971, p. 22, our translation). Jin (1970, p. 5) states that Eq. 5
holds for lit signs at least over 5.5–15.5 m, his chamber distances.

**C = 8 and C = 3.** Jin (1971) draws, not fits, the line *KV* = 8.0
through lit signs of 500–2000 asb (159–637 cd/m²) in acrylic smoke at
80 lx, with points spread over *KV* ≈ 6.7–9.9 (Fig. 1), and *KV* = 3.0
through placards of reflectance 0.13–0.70 in polystyrene smoke at 40 lx,
with points over *KV* ≈ 1.4–4.0 (Fig. 2; spreads our reading).
Mulholland (2002, SFPE Handbook 3rd ed., Ch. 2-13, Eqs. 14–15 and
Fig. 2-13.5, p. 2-265) gives *KS* = 8 for a light-emitting and *KS* = 3
for a light-reflecting sign, citing Jin (1978). His figure's range bars
"include data for both flame- and smolder-generated smoke and sign
illumination levels varying by about a factor of 4", and he notes that the
subjects viewed the smoke through glass, so irritation was excluded.
*Our comparison:* his range bars match Jin 1971 Figs. 1–2 point for point
(lit-sign bars at *V* ≈ 5.4, 7, 9, 12 and 15.5 m with the same *K* spans;
brightness 500–2000 asb is his factor of 4; 750 and 500 °C burning are his
flaming and smouldering), so C = 8 and 3 appear to trace to Jin's 80 lx
and 40 lx data. The FDS User's Guide takes C = 8 and 3 from Mulholland (see
[How FDS uses it](#how-fds-uses-it)).

![Two panels. (a) C = KV at the obscuration threshold against the ratio of sign luminance to ambient light on a log axis: Jin's theoretical line for δc k = 0.01 rising through the placard band 2–4 below ratio 1 and the lit-sign band 5–10 above it, with C = 3 and C = 8 marked about 150 times apart in the ratio, and shaded bands between Cheung et al.'s published bounding curves at 180 and 1 lx. (b) Visibility against extinction coefficient on log axes for C = 3 and 8, solid between 5.5 and 15.5 m, a point for C = 11 at 5.5 m, and the FDS 30 m cap](/images/fundamentals/visibility_constant.png)

*(a) Jin's Eq. 4 with \(\delta_c k_s\) = 0.01 (solid over the 0.1–50 range
of his Fig. 11), and 0.02 and 0.05 (dotted). C is the logarithm of a
brightness ratio: going from C = 3 to C = 8 needs about \(e^5\) ≈ 150
times the sign-to-light ratio (our arithmetic). Shaded: the bounding
curves Cheung et al. publish in their Fig. 11 at 180 lx (\(\delta_c k_s\) =
0.0025–0.025) and 1 lx (0.1–1), over the extent of their data there (our
reading of the axes). In our reading the 1 lx data sit below Jin's curve:
the higher C in dim light comes from the larger ratio for the same sign,
not from a shift of the curve. The points for C = 3 and 8 on the 0.01
curve are our construction, not where Jin 1971's data sit. (b) V = C/K for
C = 3 and 8; solid over 5.5–15.5 m, Jin's viewing distances, dashed
outside; shading: Jin's bands 2–4 and 5–10. Cheung et al.'s top value
C ≈ 11 was reached only at 5.5 m and with signs far brighter than exit
signs (marked by a point). Script: `scripts/figures/fundamentals_visibility_constant.py`.*

**Reflecting signs and ambient light: the sources differ in emphasis.**
Jin (1970, p. 6, our translation) concludes from Eq. 7 that in white smoke
the threshold density of a placard does not depend on the ambient light,
and finds almost no effect between 60 and 180 lx, but a lower threshold at
22 lx, the lowest level tested, which he calls extremely dark and
attributes to a change in \(\delta_c\) (p. 7, Fig. 9). Jin (1971, p. 18) says the same, "except when the light is
extremely weak" (our translation). The English reviews say instead that the
product for reflecting signs "depends mainly on the reflectance of the sign
and the brightness of illuminating light" (Jin and Yamada 1985, p. 81;
Jin 1997, p. 6; Jin 2002, p. 2-43; Ch. 61, p. 2186). Jin (1971,
Fig. 8) shows \(\delta_c\) rising steeply below about 30–60 lx. *In our
reading*, the light matters at 22 lx and below, which covers all
emergency-lighting levels (1–15 lx), so the reviews' wording is compatible
with the primaries: the primaries stress reflectance, the reviews add the
light.

**Black and white smoke.** At the same *K*, a lit sign was seen somewhat
farther in black (flaming) smoke than in white (smouldering) smoke (Jin
1971, p. 18 and Fig. 1; Jin and Yamada 1985, p. 81). Jin (1997, p. 5)
notes that black smoke has the smaller \(k_s\) and that, because \(k_s\)
sits inside the logarithm, the difference has little effect on visibility.
*Our inference:* a smaller \(k_s\) gives a larger *KV* in Eq. 4, the
direction observed.

**Walls, floors and doors.** Jin and Yamada (1985, p. 81), Jin (1997, p. 7)
and Jin (2002, p. 2-43) state that the visibility of walls, floors, doors
and stairs depends on the surroundings, "however, the minimum value for
reflecting signs may be applicable", that is, *C* ≈ 2 in our reading. Jin (1976, p. 17)
uses "Visibility (m) × Extinction coefficient (1/m) ≈ 2" to turn a required
visibility into an allowable smoke density.

**What C is.** Eq. 4 makes *C* a property of the sign, its lighting and the
smoke, through \(B_{E0}/L\), \(\delta_c\) and \(k_s\). *Our inference:* *C*
should be chosen from the type of sign and the light, not fitted to a
desired outcome.

## Cheung et al. (2026): the reappraisal

Cheung, Bielawski, Arnold, Huang and Węgrzyński rebuilt Jin's chamber at
5.5 m length with a larger 2.4 × 2.4 m cross-section, three mirrors for 5.5,
10.5 and 15.5 m, a lab-made LED sign box showing a Landolt "C" of 5, 10 or
15 cm, industrial white smoke (mineral oil, Concept Smoke Vulcan 5000), a
1 m densitometer with a 638 nm laser (§3, Table 1), and ambient light from
222 lx down to 1 lx (§4.2, Fig. 9). The observer raised the sign luminance until the "O"
shape, and then the gap of the "C", was barely visible; each set was
repeated twice (§3). They also replotted Jin's (1970) data in SI units
(§4.1).

What they **confirm**:

- The critical *K* rises linearly with the logarithm of sign luminance, and
  plotting against \(\pi L_t/E\) collapses the light levels onto one line
  (§4.1, Figs. 5–6; \(R^2\) = 0.96–0.99).
- The constants that FDS uses (C = 8 and 3) trace, in our comparison, to
  Jin's 80 lx and 40 lx data (Jin 1971, via Mulholland 2002), not to the
  180 lx data behind Cheung et al.'s "Jin's 5–8".
- At 180 lx, *KV* is comparable: 5–8 in Jin's data, 4.7–9.5 in theirs
  (abstract; §6). By distance, 5.3–9.5 at 5.5 and 10.5 m and 4.7–8 at
  15.5 m (§4.1, Fig. 8).
- At 15.5 m their data agree with Jin's (§4.1, Fig. 7).

What they **revise**:

- **Ambient light.** In dim light a sign of the same luminance stays
  visible in denser smoke. *KV* is 7.5–11 at 1 lx and 6–11 at 22 lx
  (§4.4, Fig. 11), against 5–8 at 180 lx. These ranges pool the "O" and
  "C" thresholds (Fig. 11), and in our inference span sign luminances up
  to the study's maximum of 22 500 cd/m² (§4.1 gives 128–22 500 cd/m² as
  the study's overall range). At luminances of ordinary exit signs their
  printed values give lower constants for *seeing the gap of the "C"*
  (§4.3; these are the lowest filled "C" markers of Fig. 10; our
  arithmetic): at 1 lx, *K* = 1.5, 0.8 and
  0.5 1/m at 189, 202 and 492 cd/m² for 5.5, 10.5 and 15.5 m, so *KV* ≈
  8.3, 8.4 and 7.8; at 22 lx, *K* = 1.4, 0.7 and 0.4 1/m at 224, 135 and
  220 cd/m², so *KV* ≈ 7.7, 7.4 and 6.2. Jin's criterion is the "O",
  which is reached at lower luminance (for example about 127 against
  191 cd/m² at 1 lx and 5.5 m, our reading of Fig. 10a), so constants for
  the "O" would be somewhat higher. At 5.5 m the critical *K* is about
  1.5 1/m at 1 lx and 0.9 1/m at 222 lx (§4.2), so *KV* ≈ 8.3 against
  5.0; in our reading of Fig. 9a both are near 130 cd/m², the first an "O"
  and the second a "C" point. They write that using *KV* = 5
  "may result in overestimation" and that "the actual visibility of the
  illuminated signage should be higher" (§4.4). *In our reading*, *KV* = 5
  understates the visibility of a lit sign in dim light. Jin's 5–8 refers
  to 180 lx (Fig. 8), while emergency lighting codes require only 1–15 lx
  (§4.2).
- **Jin's assumptions.** Their data do not follow Jin's curve with
  \(\delta_c = 0.01\) and \(k_s = 1\): \(k_s\) may be below 1, and
  \(\delta_c\) may vary with the light and the sign luminance (§4.1,
  §4.4). Their Fig. 11 draws bounding curves with \(\delta_c k_s\) =
  0.1–1 at 1 lx, 0.0125–0.125 at 22 lx, 0.005–0.05 at 60 lx and
  0.0025–0.025 at 180 lx.
- **Jin's sign luminance.** They state that Jin's lit signs, about
  3000 asb (955 cd/m²), were much brighter than common exit signs, which is
  why they were seen at *K* up to 1.8 1/m (§2). They also give Jin's range
  as 42–808 cd/m² (§4.1) or 36–810 cd/m² (§5), and common exit signs as
  about 100–500 cd/m² (§4.1) or 100–300 cd/m² (§5); *in our reading*
  these ranges overlap.
- **Distance.** At 5.5 and 10.5 m their critical *K* is about 20 % higher
  than Jin's at the lowest \(\pi L_t/E\) (§4.1). The critical *K* falls by
  nearly 40 % per 5 m of distance (§4.3). *Our arithmetic:* a constant *KV*
  alone predicts a fall of 48 % from 5.5 to 10.5 m and 32 % from 10.5 to
  15.5 m.

The **gaps they found** in Jin's work: it is not stated how Jin measured the
ambient light and the sign luminance, or where the densitometer was; Jin's
Figs. 5 and 6, and Figs. 5 and 7 at 5.5 m, do not match; and it is unclear
how the 10.5 m path was obtained (§4.1, §5). The sign size grew with
distance to keep the visual angle, so the law says nothing about a fixed
sign seen from farther away; they leave this to future work (§2, issue
III).

The **limits they state** (§5): one observer with visual acuity 1.0 who
knew the sign's shape, size and place; industrial white smoke, not
smouldering or sooty fire smoke; a laboratory Landolt "C", not a real exit
sign; no reflecting signs. The reflecting range 2–4 is therefore untested
by them, and so are black smoke and irritants.

*Our notes as readers:*

- On the direction of the 7–11 % difference, the abstract says their
  critical *K* is higher than Jin's. §4.1 and §6 say that Jin's is higher.
- They call \(\pi L_t/E\) not dimensionless, with units cd/m²·lx (§4.1).
  In SI, lx = cd·sr/m², so the ratio is dimensionless.
- Jin (1970, pp. 4–6 and Table 1) does describe two mirrors for 10.5 and
  15.5 m, a luminance meter built from a single-lens reflex camera for
  \(\delta_c\), and a correction of +0.5 to *KV* for the contrast lost in
  the mirrors. Whether the replotted 10.5 and 15.5 m points include that
  correction is not stated. Jin (1970, p. 4) also states that the sign
  brightness and the chamber illuminance were recorded during each run,
  and (p. 6) that the illuminance stayed nearly constant in white smoke,
  which answers part of their "not mentioned". Jin (1970, p. 5) says the
  two mirrors give 10.5 and 15.5 m, but his Fig. 3 shows only the 15.5 m
  path, so their doubt about 10.5 m stands.
- Their text says the contrast ratio is lower in dimmer light (§4.4). Their
  Fig. 11 bounds give a larger \(\delta_c k_s\) at 1 lx than at 180 lx, as
  does Jin (1971, Fig. 8), where \(\delta_c\) rises as the light falls.
- In their Fig. 11 the dim-light data lie *below* Jin's curve at the same
  \(\pi L_t/E\), except the 22 lx data at low ratios, which straddle it.
  The larger *KV* in dim light comes from the larger
  \(\pi L_t/E\) of the same sign when *E* is small, not from a sign being
  seen better than Jin's model predicts.

## Other data on real exit signs

Yamada and Akizuki (2016, Ch. 61, pp. 2187–2188) report experiments by
Yamada, Kubota, Abe and Iida (2004), which we have not read, on three
Japanese exit signs of 250–800 cd/m² in non-irritant white smoke without
background light (Table 61.1). The fitted slopes of *V* against 1/*K* are
9.1, 22.5 and 12.6 (\(R^2\) = 0.93–0.94, Fig. 61.9); they attribute the
22.5 of the larger B-class sign to its size ("twice as visible as others
due to size effect", p. 2187). An ordinary lit exit
sign was lost at about 10 m at *K* = 1.0 1/m, and they note that the
constant "tends to be larger" than Jin's. *Our inference:* larger constants
without background light agree in direction with Cheung et al.'s low-light
results.

## Seeing a sign versus reading it

All of the above is the obscuration threshold: the point where a sign is
barely seen. Jin (1970, p. 7) judged only whether the sign was there and
noted that reading its content depends on size and form.

**Jin (1972).** In the corridor, seeing the sign followed *KV* ≈ constant
in both irritant and non-irritant smoke. Telling its colour or reading its
letters did so only in thin smoke: in the irritant smoke, the visibility
fell sharply above some density (p. 13, Figs. 3–5). At *K* = 0.5 1/m it fell
"by more than 30 %" compared with non-irritant smoke of the same density
(English abstract, p. 11), and to "a fraction" (数分の1, p. 14, our
translation). Jin attributes this to tears and irritation, which raise the
contrast needed (Figs. 6–7, pp. 14–15). Even in thin, weakly irritant
smoke, the letters of a commercial exit sign needed a contrast 3–5 times
that for seeing the sign (p. 15). Normal lighting and the blackout gave
almost the same visibility (p. 15). Jin (1972, p. 15) concludes that
the obscuration contrast is little affected by irritation, so the chamber
values apply to seeing a sign whose location is known; not knowing the
location matters more (\(\delta_c\) 0.05–0.10). Cheung et al. (2026, §4.2, Fig. 9a)
give a modern data point for the same distinction: at 1 lx and
*K* = 1.6 1/m, 170 cd/m² sufficed to see the "O" and 440 cd/m² to see the
gap of the "C".

*Our caveats:* the irritant smoke was white and the non-irritant smoke
black, so irritancy and smoke colour change together; Jin (1972, p. 14)
notes that white smoke scatters more corridor light, but finds the
differences larger than that alone. The blackout changed the corridor light
and the sign's own lamps together (p. 13).

**Jin and Yamada (1985).** Visual acuity with the unsealed goggle, relative to
that with the sealed one, stayed almost constant below *K* = 0.25 1/m and fell
rapidly above it (Fig. 6, p. 85); the ratios near 1 were measured at
*K* ≈ 0–0.24 1/m. They fitted, for *K* ≥ 0.25 1/m,

$$
S = 0.133 - 1.47 \log K \qquad \text{(Jin and Yamada 1985, Eq. 3)}
$$

and wrote the legibility distance as

$$
V_1 = \frac{C}{K}\ (0.1 \le K < 0.25), \qquad
V_2 = \frac{C}{K}\,(0.133 - 1.47 \log K)\ (K \ge 0.25)
\qquad \text{(Eqs. 4–5)}
$$

with *C* = 6 matching the corridor data for reading the words of an exit
sign (p. 87, Fig. 2). The equations do not hold for *K* < 0.1 1/m or where
\(V_2 < 0\) (p. 86). Jin (1997, Eqs. 5–7, pp. 8–9) and Jin (2002,
Eqs. 5–7, p. 2-45) repeat them. The log is base 10: the drawn line in
Fig. 8 falls about 1.4 per decade, and *S*(0.25) = 1.02 is continuous with
*V*₁. *Our reading:* *S* is the ratio of Fig. 6, fitted to five points at
*K* ≈ 0.24–0.55 1/m (Fig. 8); the point near 0.32 1/m is 0.96 in Fig. 8 but
0.90 in Fig. 6. The non-irritant legibility points scatter around C = 6,
with *KV* ≈ 3.8–7.8 (Fig. 2, our reading).
They also found that with the eye blink rate 1.5–2.0 times normal, acuity
fell rapidly, and above 2.0 "presumably nothing can be seen beyond 4 m"
(p. 86).

![Two panels against extinction coefficient on a log axis. (a) Relative visual acuity: 1 below 0.25 1/m, solid over the measured ratios, then the line 0.133 − 1.47 log K, solid from 0.25 to 0.55 1/m and dashed to zero at 1.23 1/m. (b) Distance at which the words of an exit sign can be read: V = 6/K for non-irritant smoke, solid from 0.53 to 1.05 1/m, and V = (6/K) S for irritant smoke, solid from 0.40 to 0.55 1/m; at 0.5 1/m they give 12 and 6.9 m](/images/fundamentals/visibility_irritant.png)

*Jin and Yamada (1985), Eqs. 3–5 with C = 6. Solid over the data, as we
read their Figs. 2, 6 and 8 and Jin (1972, Fig. 5): acuity ratios at
0.1–0.55 1/m, non-irritant legibility points at about 0.53–1.05 1/m,
irritant legibility points at about 0.40–0.55 1/m; dashed outside. At K = 0.5 1/m the irritant law
gives 6.9 m against 12 m (our arithmetic). S reaches zero at K ≈ 1.23 1/m.
Script: `scripts/figures/fundamentals_visibility_irritant.py`.*

**The 0.5 1/m for open eyes.** Jin and Yamada (1985, p. 81) write that in
thick irritant smoke "the subjects could not keep their eyes open for a
long time", without a number. Yamada and Akizuki (2016, Ch. 61, p. 2190)
put it "under 0.5 [1/m]" and, two sentences later, "over 0.5 [1/m]". We
found no primary source for the number. Possible origins, not
established: Jin (1972, abstract) uses 0.5 1/m as its example of dense
irritant smoke; Jin (1997, §2.1) finds most subjects emotionally affected
near 0.5 1/m; Jin (2002, p. 2-45) assumes escape is still possible at
0.5 1/m; and in Jin and Yamada (1985, Fig. 6) a dashed construction meets
the acuity curve near 0.53 1/m.

## Known limits

- The law describes a straight, unobstructed line of sight through uniform
  smoke to one object. It does not describe how far one can see around
  corners, or how much smoke a person walks through.
- It was measured at 5.5–15.5 m (Jin 1970) and stated for 5–15 m (Jin
  1971). *V* outside that range, including the 30 m FDS cap, is an
  extrapolation.
- The sign grew with distance to keep its visual angle (Jin 1970, p. 3;
  Cheung et al., §2), so a real sign of fixed size is covered only
  partly: Jin (1970, Fig. 12) found the critical *K* of a placard at 10 m
  rising from about 0.2 to 0.4 1/m with size and saturating above a
  visual angle of about 0.45° (our reading), and Ch. 61 (p. 2187)
  attributes the B-class sign's larger slope to its size.
- *C* depends on the sign's luminance, the ambient light and the smoke.
  Jin's lit-sign values are for 22–180 lx. In 1–22 lx, Cheung et al.
  measured 6–11 over signs up to 22 500 cd/m², and about 6–8.4 at exit-sign
  luminances for seeing the gap of the "C" (our arithmetic from their
  §4.3).
- It is a threshold for seeing a sign, not for reading or understanding it.
  Reading needs more contrast (Jin 1972, p. 15), and in irritant smoke the
  distance drops faster than 1/*K* (Jin and Yamada 1985).
- Jin (1970, pp. 7–8, our translation) expected real visibility to be
  lower than in his chamber: the signs were viewed through glass, so the
  results strictly apply to people wearing smoke masks with eye protection;
  the observers knew where the sign was; and physiological and
  psychological effects were absent. Cheung et al. (§5) repeat this for their own
  observer.

## How FDS uses it

The Fire Dynamics Simulator (FDS) User's Guide (McGrattan et al. 2025,
§22.10.5, Eq. 22.23) writes the law as \(S = C/K\), with *C* = 8 for a
light-emitting and *C* = 3 for a light-reflecting sign, citing Mulholland
(2002), and uses *C* = 3 by default (`VISIBILITY_FACTOR`). FDS reports
visibility up to 30 m by default (`MAXIMUM_VISIBILITY`, §22.10.5).

Two recent papers describe how the law is used. Börger, Belt and Arnold
(2024, §1, p. 1) attribute the ranges 2–4 and 5–10 to Jin (1970), black
smoke to Jin (1971) and irritancy to Jin (1972), as this page does, and
apply the law along lines of sight to exit signs. Among the 210
practitioners who answered the question in a survey, C = 3 was the most
common single choice; at *K* = 0.33 1/m
it gives about 9 m, against about 24 m for C = 8 (Węgrzyński et al. 2026,
§4.4, Fig. 7a).

How pyFDS-Evac uses this: see [wayfinding](/models/wayfinding.md) and the
[smoke-speed model](/models/smoke-speed.md).

## Sources

Read for this page:

- Jin, T. (1970). *Visibility through fire smoke (I)* [煙中の見透し距離に
  ついて (I)]. Bulletin of the Fire Prevention Society of Japan, 19(2),
  1–8. In Japanese with an English abstract.
  [doi:10.11196/kasai.19.2.1](https://doi.org/10.11196/kasai.19.2.1)
- Jin, T. (1971). *Visibility through fire smoke (II)*. Bulletin of the
  Fire Prevention Society of Japan, 21(1), 17–23. In Japanese with an
  English abstract.
  [doi:10.11196/kasai.21.17](https://doi.org/10.11196/kasai.21.17)
- Jin, T. (1972). *Visibility through fire smoke (III)* [煙中の見透し距離に
  ついて (III)]. Bulletin of Japanese Association of Fire Science and
  Engineering, 22(1–2), 11–15. In Japanese with an English abstract.
  [doi:10.11196/kasai.22.11](https://doi.org/10.11196/kasai.22.11)
- Jin, T., & Yamada, T. (1985). *Irritating effects of fire smoke on
  visibility*. Fire Science and Technology, 5(1), 79–90.
  [doi:10.3210/fst.5.79](https://doi.org/10.3210/fst.5.79)
- Jin, T. (1997). *Studies on human behavior and tenability in fire
  smoke*. Fire Safety Science, 5, 3–21.
  [doi:10.3801/iafss.fss.5-3](https://doi.org/10.3801/iafss.fss.5-3)
- Jin, T. (2002). *Visibility and human behavior in fire smoke*. SFPE
  Handbook of Fire Protection Engineering, 3rd ed., Ch. 2-4, 2-42–2-53.
  National Fire Protection Association, Quincy, MA. No DOI or public URL.
- Mulholland, G. W. (2002). *Smoke production and properties*. SFPE
  Handbook of Fire Protection Engineering, 3rd ed., Ch. 2-13, 2-258–2-268.
  National Fire Protection Association, Quincy, MA. No DOI or public URL.
- Yamada, T., & Akizuki, Y. (2016). *Visibility and human behavior in fire
  smoke*. SFPE Handbook of Fire Protection Engineering, 5th ed., Ch. 61,
  2181–2206.
  [doi:10.1007/978-1-4939-2565-0_61](https://doi.org/10.1007/978-1-4939-2565-0_61)
- Cheung, W. K., Bielawski, J., Arnold, L., Huang, X., & Węgrzyński, W.
  (2026). *Reappraisal of Jin's visibility through fire smoke experiment:
  Insights into signage visibility and the impact of ambient light*. Fire
  Safety Journal, 159, 104573.
  [doi:10.1016/j.firesaf.2025.104573](https://doi.org/10.1016/j.firesaf.2025.104573)
- Börger, K., Belt, A., & Arnold, L. (2024). *A waypoint based approach to
  visibility in performance based fire safety design*. Fire Safety
  Journal, 150, 104269.
  [doi:10.1016/j.firesaf.2024.104269](https://doi.org/10.1016/j.firesaf.2024.104269)
- Węgrzyński, W., Spodyniuk, N., Zimny, M., Jahn, W., Vigne, G., &
  Arnold, L. (2026). *Tenability criteria in performance-based fire safety
  engineering: practitioner's perspectives from a global survey*. Fire
  Safety Journal, 165, 104938.
  [doi:10.1016/j.firesaf.2026.104938](https://doi.org/10.1016/j.firesaf.2026.104938)
- Jin, T. (1976). *Visibility through fire smoke, Part 5: Allowable smoke
  density for escape from fire*. Report of Fire Research Institute of
  Japan, 42, 11–18. No DOI or public URL.
- McGrattan, K., Hostikka, S., Floyd, J., McDermott, R., Vanella, M.,
  Mueller, E., & Paul, C. (2025). *Fire Dynamics Simulator User's
  Guide*. National Institute of Standards and Technology (NIST) Special
  Publication 1019, 6th ed., revision FDS-6.10.1-0-g12efa16, §22.10.5.
  [github.com/firemodels/fds/releases/tag/FDS-6.10.1](https://github.com/firemodels/fds/releases/tag/FDS-6.10.1)

Cited by the sources above, not obtained:

- Jin, T. (1978). *Visibility through fire smoke*. Journal of Fire &
  Flammability, 9, 135–157 (135–155 in some citations). Cited for the
  contrast model by Jin and Yamada (1985, ref. 5), Jin (1997, ref. 1), Jin
  (2002, ref. 2) and Ch. 61 (ref. 6), and for C = 8 and 3 by Mulholland
  (2002, ref. 22). Every statement on this page is taken from the papers
  above instead.
- Yamada, T., Kubota, K., Abe, N., & Iida, A. (2004). *Visibility of
  emergency exit signs and emergency lights through smoke*. Proc. 6th
  Asia-Oceania Symposium on Fire Science and Technology, Daegu, 227–238.
  Reported through Ch. 61 (ref. 7).
