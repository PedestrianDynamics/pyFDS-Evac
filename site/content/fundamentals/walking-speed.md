---
title: "Walking speed in smoke"
weight: 4
---

Smoke slows people down because they see less, and irritant smoke slows them
further because it hurts their eyes and airways. Evacuation models take this
from a small number of experiments that relate walking speed *v* [m/s] to the
extinction coefficient *K* [1/m] (see [Extinction coefficient](/fundamentals/extinction.md)).
The data sets were recorded under different conditions and are not
interchangeable (Ronchi et al. 2013).

Symbols follow the [notation table](/docs/concepts.md#notation); each
section keeps its source's notation: Korhonen's \(K_s\), \(v_i^0\);
Purser's \(\alpha_k\) (= *K*, not the coefficient \(\alpha\)); Fridolf et
al.'s *w*, *x* (*S* in the notation table) and *A*, which plays the role of
*C* with its own values.

| Law | Variable | Equation | Data range | Reduction | Smoke |
|---|---|---|---|---|---|
| Jin, non-irritant (Purser's fit) | *K* | v = 1.0573 − 0.4326 K | 0.2–1.13 1/m | absolute | kerosene, less irritant |
| Jin, irritant (Purser's fit) | *K* | v = 1.1517 − 0.9578 K | 0.32–0.5 1/m | absolute | wood cribs, highly irritant |
| Purser 2003, fit to Jin, non-irritant | OD/m (K ≈ 2.303 OD/m) | F = 1.236 − 1.738 OD/m | OD/m 0.13–0.55 (K ≈ 0.30–1.27 1/m) | fractional | non-irritant |
| Frantzich–Nilsson, Eq. 3 | *K* | v = 0.706 − 0.057 K | 1.9–7.4 1/m | absolute | artificial, mild (acetic acid) |
| FDS+Evac, Eq. 11 | *K* | v = max(0.1 v₀, v₀ (1 − 0.057 K / 0.706)) | as Frantzich–Nilsson | fractional | as Frantzich–Nilsson |
| Purser, Eq. 63.10 | *K* | W = −0.1364 ln K + 0.6423 | 0.32–0.5 and 1.9–7.5 1/m | absolute | pooled, "moderately irritant" |
| Fridolf et al., Eq. 2 | *x* = *A*/*K* | w = 0.34 x + 0.31 | x ≈ 0.3–3 m | absolute | mostly non-irritant |
| Fridolf et al., Eq. 7 | *x* | w = min(w_sf, max(0.2, w_sf − 0.34 (3 − x))) | design rule | both | as Eq. 2 |

## Jin: irritant and non-irritant smoke

Jin's subjects walked along a 20 m corridor filled with highly irritant
white smoke (burning wood cribs with narrow spacing between the sticks) or
less irritant black smoke (burning kerosene) (Jin 1997, §1.3 and Fig. 3;
the same account and figure are in Yamada and Akizuki 2016, Society of Fire
Protection Engineers (SFPE) Handbook Ch. 61, Fig. 61.22). Jin gives no
fitted equation: his Fig. 3 shows the individual speeds with trend curves,
at *K* = 0.52–1.13 1/m in non-irritant smoke and 0.32–0.48 1/m in irritant
smoke. In irritant smoke the speed dropped sharply over a narrow
range of *K*, and subjects walked zigzag or along the wall because they
could not keep their eyes open.

Purser and McAllister (2016, Ch. 63) replot Jin's data in their Fig. 63.16
and fit straight lines to them (legend), over *K* = 0.2–1.13 1/m
(non-irritant) and 0.32–0.5 1/m (irritant) (p. 2339):

$$
v = 1.0573 - 0.4326\,K \quad (\text{non-irritant},\ R^2 = 0.27),
\qquad
v = 1.1517 - 0.9578\,K \quad (\text{irritant},\ R^2 = 0.035).
$$

{{< details title="Jin's data: sources, ranges and participants" closed="true" >}}
**Scatter.** The irritant fit explains almost none of the scatter: at an
average *K* = 0.42 1/m the speeds ranged from 0.37 to 1.1 m/s, mean
0.75 m/s (standard deviation (SD) 0.21). In non-irritant smoke, at an
average *K* = 0.73 1/m, the mean was 0.74 m/s (SD 0.17) (Ch. 63,
pp. 2339–2340).

**Two versions of the data.** Purser and McAllister's Fig. 63.16 (p. 2340)
is not a copy of Jin (1997, Fig. 3). It has a non-irritant point at
*K* ≈ 0.2 1/m (about 1.1 m/s), which Jin's figure lacks (his non-irritant
points start at 0.52 1/m), and its speeds sit a few hundredths of a m/s
below Jin's. Both may come from different Jin reports; Ch. 63 cites Jin's
FRI Report No. 42 (ref. 53) for this material. Purser's 2003 fit reaches OD/m 0.55 (*K* ≈ 1.27 1/m),
also beyond Jin's 1997 points. The fits above belong to Purser's replotted data,
and their ranges are his. Ronchi et al. (2013) give 0.2–1.0 and 0.1–0.5
1/m on p. 414, and 0.2–0.5 1/m for irritant smoke on p. 421. Their
"1.0 to 0.3 m/s as *K* rose from 0.1 to 0.5 1/m" appears, as our
inference, to follow Jin's irritant trend curve rather than the measured
points. That Jin's trend curves were drawn by hand is also our inference;
Jin (1997) does not say how they were obtained.

**Darkness.** Ch. 63 attributes the 0.3 m/s to Jin: in non-irritant smoke
at *K* ≈ 1.15 1/m, speed fell to about 0.3 m/s and subjects moved as if in
darkness (p. 2339, citing ref. 53), and speed "has been shown" to fall to
about 0.3 m/s (p. 2413); Ronchi et al. (p. 415) say the same. Ch. 63 pairs
*K* 1.15 with OD/m 0.55 in its prose but with OD/m 0.5 in Table 63.5 on
the same page; only 0.5 is consistent with base 10 (1.15/ln 10 = 0.50).
Purser (2003, p. 98) describes Jin's data "between the limits of 0.13 …
and 0.55 (above which movement speed is as in darkness at 0.3 m/s)" and
justifies the value "since it is still possible to move at this speed in
total darkness". Our inference is that 0.3 m/s is a floor assumption, not
a measured Jin point; only FRI Report No. 42 can settle it. No plotted
data set shows 0.3 m/s in non-irritant smoke: in Jin (1997, Fig. 3) the speed at *K* = 1.13 1/m is near 0.8 m/s
and none is below about 0.5 m/s, and in Fig. 63.16 the lowest non-irritant
point is about 0.45 m/s at *K* ≈ 0.97 1/m.

**Irritant smoke.** Jin (1997) and Ch. 61 describe burning wood cribs;
Purser (2003, p. 98) says "smoke from non-flaming wood" and Ch. 63
(p. 2339) "heating wood chippings". As our inference, the latter may be a
mix-up with the wood-chip furnace smoke of Jin and Yamada (1989).

**Source of the data.** Jin (1997) §1.3 attaches ref. [2], Jin and Yamada
(1985), *Irritating effects of fire smoke on visibility*, to the sentence
describing the corridor tasks; SFPE Ch. 61 cites the same sentence as
[6, 9], that is Jin (1978) and Jin and Yamada (1985) (pp. 2189, 2205–2206).
Whether either paper holds the walking data is not established. Fridolf et
al. (2019) name the study three ways: Jin 1976 in the Fig. 1 legend, Jin
1978 and 1997 in §3.2.1, and Jin 1979 in Table 2. FRI Report No. 42 is
dated 1975 in Purser (2003, ref. 7) and 1976 in Ch. 63 (ref. 53, same
title and number) and Ronchi et al. (ref. 11, same number); the year is
not established. That Fridolf et al.'s "Jin 1976" is the same report is
our inference.

**Measurement.** Speed was measured along the corridor axis from a cable
each subject unwound from a drum (Frantzich and Nilsson 2003, §3.3.1).

**Participants.** Ronchi et al. (p. 414) report 17 women and 14 men aged 20
to 51, without a citation of their own for that sentence. That is the
population of a different experiment: Jin and Yamada's 11 m corridor study
of emotional instability (Jin and Yamada 1989, "Subjects", p. 513; Jin
1997, §2.2). Fridolf et al. (2019, §3.2.1 and Table 2) list the 20 m study
as ten men aged 23 to 37. Jin 1997 does not give the number, and this page
has not been checked against Jin 1978.

**A third data set.** Jin and Yamada (1989) also measured walking speed
against *K* (Fig. 7, p. 517), with smoke from smouldering Japanese cedar
crib chips in an electric furnace, set to 1.2 1/m and decaying to about
0.1 1/m over 30 minutes (p. 512, "Experimental condition of the
corridor"), under radiant heat. The subjects breathed through a 16-layer
towel that removed about 90 % of the smoke and lessened its irritation
(pp. 513, 517), so these data do not give a law for unprotected walkers.
{{< /details >}}

## Purser 2003: a fractional law fitted to Jin

Purser (2003, p. 93 and pp. 98–99, Fig. 1) fitted "a curve directly to
Jin's data" on non-irritant smoke (refs. 7 and 15: Jin 1975/1976, FRI
Report No. 42, and Purser's own 2001 paper "Human Tenability") with a
fraction *F* of the unexposed walking speed:

$$
F = -1.738\;\mathrm{OD/m} + 1.236, \qquad 0.13 \le \mathrm{OD/m} \le 0.55,
$$

with normal speed below OD/m = 0.13 and, above 0.55, speed "as in darkness
at 0.3 m/s … since it is still possible to move at this speed in total
darkness". Purser does not define OD/m there; Ch. 63 defines it as
log₁₀(*I*₀/*I*) over 1 m (p. 2413), so *K* = ln 10 · OD/m ≈ 2.303 OD/m and
the fit spans *K* ≈ 0.30–1.27 1/m (our conversion). No fit quality or
number of points is given, and the squares in Fig. 1 lie exactly on the
line (1.010, 0.888, 0.715, 0.541, 0.454, 0.280 at OD/m 0.13–0.55), so
Fig. 1 shows the fitted line, not Jin's points. The floor is written as an
absolute 0.3 m/s (0.25 of 1.2 m/s), while the line reaches 0.28 at
OD/m 0.55 and Fig. 1 shows about 0.27. Whether 0.3 m/s was measured is open (see
the details block on Jin's data above).

## Frantzich and Nilsson: a linear regression in dense smoke

Frantzich and Nilsson (2003, Lund report 3126) sent 46 young volunteers one
at a time through a 36.75 m tunnel filled with artificial smoke made
irritating with acetic acid. For the 32 runs with the lighting on, a linear
regression (report Eq. 3, Table D2, model 1) gave the **absolute** speed

$$
v = \alpha + \beta K, \qquad \alpha = 0.706~\mathrm{m/s}\;(\text{s.e. } 0.069),\quad
\beta = -0.057~\mathrm{m^2/s}\;(\text{s.e. } 0.015),
$$

with \(R^2\) = 0.342 (Table D3); the bracketed values are standard errors
of the coefficients, not the spread between people. The lit runs cover
*K* ≈ 1.9–7.4 1/m (Fig. 9).

{{< details title="More on the Frantzich–Nilsson data" closed="true" >}}
**Participants.** 30 men and 16 women, mean age about 22, mostly students
(Table 1). The 32 lit runs pool four wayfinding scenarios, 1–4 in Table 3.

**Measurement.** *K* is the mean of two laser extinction meters (670 nm,
1 m path, 2.0 m above the floor), averaged over each person's time in the
tunnel (§2.5.1, App. D). The walking speed is the distance each person
actually walked, measured from the video on the tunnel plan, divided by the
time in the tunnel, stops included (§3.3.1). The speed over the
straight-line distance to the chosen exit (the "gross speed", Fig. 12) was
on average 0.88 of it (SD 0.09; Fig. 11). Measured speeds ranged from 0.2 to
0.9 m/s (§3.3.1), although the lit points in Fig. 9 reach only about
0.76 m/s.

**Smoke and light.** The acetic acid concentration was 10–15 ppm (§2.3).
Fridolf et al. (2019, Table 2) call the smoke "semi-irritant", and Ronchi et
al. (2013, p. 421) call the irritation much less severe than in Jin's
experiments. It follows, as our inference, that the regression already
includes the effect of this mild irritancy. The ceiling lighting gave
2–21 lx without smoke and 0–8 lx with smoke (§2.2).

**Range and scatter.** The report's text gives *K* ≈ 2–7 1/m (§3.2).
The 95 % prediction interval at *K* = 4 1/m is about 0.2–0.7 m/s
(§3.3.2); adjusted \(R^2\) is 0.320.

**Other models.** With the lighting off (12 runs) the slope was not
significantly different from zero (Table D1). A second model with the share
of the route walked along the wall fitted better (Eq. 4, Table D2 model 2:
α = 0.692 m/s, β₁ = −0.073 m²/s, β₂ = 0.139 m/s per unit share; adjusted
\(R^2\) 0.416 against 0.320): walking along the wall raised the speed. For
dense smoke (*K* = 8 1/m) the authors state that a randomly chosen person
could walk at anything between 0 and 0.6 m/s (§5), and expect a real
population to do worse than their young, fit participants (§3.1.1).
{{< /details >}}

## The fractional form is FDS+Evac's normalisation

FDS+Evac, the evacuation module of the Fire Dynamics Simulator (FDS), does
not use the regression as an absolute speed. It scales each agent's
unimpeded speed \(v_i^0\) by the same factor (Korhonen 2021, Eq. 11):

$$
v_i^0(K_s) = \max\!\left(v^0_{i,\min},\; v_i^0\left(1 + \frac{\beta}{\alpha}K_s\right)\right),
\qquad v^0_{i,\min} = 0.1\,v_i^0 \text{ by default.}
$$

The divisor 0.706 m/s is an extrapolation to *K* = 0, not a measured free
walking speed. Ronchi et al. (2013) call the two readings fractional and
absolute, and show that they give different evacuation times.

## Purser: a logarithmic fit for irritant smoke

Purser and McAllister (2016, Ch. 63, p. 2341) pooled Jin's irritant data
with Frantzich and Nilsson's and fitted a logarithm, which they suggest for
a simple, deterministic and most conservative estimate of the average
walking speed in moderately irritant smoke:

$$
W_{\mathrm{smoke}}~[\mathrm{m/s}] = -0.1364\,\ln \alpha_k + 0.6423 \qquad \text{(Eq. 63.10)}
$$

with \(R^2\) = 0.50 (Fig. 63.16) and a population SD of 0.157 m/s
(pp. 2341, 2414), on pooled data at \(\alpha_k\) = 0.32–0.5 and
1.9–7.5 1/m, with none in between (pp. 2339–2340).

{{< details title="Caveats on Eq. 63.10" closed="true" >}}
**Pooling.** The fit combines smoke from real fires with artificial smoke
made mildly irritating, which is the pooling the
[Known limits](#known-limits) section warns against; Purser and McAllister
do it deliberately, as a conservative envelope.

**Behaviour outside the data.** The logarithm has no upper bound as
\(\alpha_k \to 0\): it exceeds 1 m/s below \(\alpha_k\) ≈ 0.07 1/m (our
arithmetic).

**Other fits on the same page.** Fig. 63.16 also gives logarithmic fits to
other combinations of the Jin, Frantzich–Nilsson and Fridolf et al. data
(Ch. 63 ref. 55, Interflam 2013); the three that leave out the Fridolf data
are "quite similar" (p. 2341). Ch. 63 takes the Frantzich–Nilsson data from
their 2004 Human Behaviour in Fire paper (ref. 54), not from report 3126,
and its straight-line fit to them, v = 0.7099 − 0.0573 K (\(R^2\) = 0.349),
differs slightly from the report's.

**Population values.** p. 2341 also suggests drawing each person's speed
from a normal distribution "with a mean from Equation 63.12 and standard
deviation of 0.125"; Eq. 63.12 in this edition is the irritant FIC sum, so
the reference is probably meant to be Eq. 63.10, and 0.125 differs from the
0.157 given on the same page. For clear air it suggests a mean of 1.2 m/s
with SD 0.15 m/s. It compares Frantzich and Nilsson's mean of 0.45 m/s
(SD 0.21) with Jin's 0.3 m/s in dense smoke, noting that the slowest speed
measured by Jin was 0.37 m/s (p. 2341); Frantzich and Nilsson measured
0.2–0.9 m/s.
{{< /details >}}

![Two panels. (a) Walking speed against extinction coefficient: Purser's straight-line fits to Jin's irritant and non-irritant data below K = 1.2 1/m, the Frantzich–Nilsson regression at K 1.9 to 7.4 1/m, and Purser's Eq. 63.10 across both, dotted where it has no data. (b) Fractional speed against extinction coefficient: Purser's 2003 line from K 0.3 to 1.27 with dashed assumed segments, and the FDS+Evac normalised Frantzich–Nilsson line](/images/fundamentals/speed_extinction.png)

*(a) Absolute laws against K [1/m]: Purser's fits to his replotted Jin data
(red, mean ± 1 SD), Frantzich–Nilsson with its prediction interval (blue),
Purser Eq. 63.10 (orange). (b) Fractional laws: Purser 2003 (orange),
relative to the unexposed speed, and FDS+Evac Eq. 11 (blue), relative to
0.706 m/s, itself an extrapolation, so part of the gap is the reference.
Purser's floor is drawn at 0.28 (our construction; he writes 0.3 m/s, Fig. 1
shows about 0.27). Solid: source data; dashed: extrapolation or assumption.*

{{< details title="Figure provenance" closed="true" >}}
Jin: v = 1.0573 − 0.4326 K on K = 0.2–1.13 1/m and v = 1.1517 − 0.9578 K
on K = 0.32–0.5 1/m (Ch. 63, Fig. 63.16 legend; ranges as stated on
p. 2339 for Purser's replotted data, which differ from Jin 1997, Fig. 3);
means 0.74 ± 0.17 m/s at K = 0.73 1/m (circle) and 0.75 ± 0.21 m/s
at K = 0.42 1/m (square) (Ch. 63, pp. 2339–2340). Frantzich–Nilsson:
v = 0.706 − 0.057 K on K = 1.9–7.4 1/m (report Eq. 3; range from Fig. 9),
prediction interval 0.2–0.7 m/s at K = 4 1/m (§3.3.2, "ca 0,2 och 0,7").
Purser: W = −0.1364 ln K + 0.6423 (Eq. 63.10) on K = 0.32–0.5 and
1.9–7.5 1/m, the ranges Ch. 63 states for the pooled data (pp. 2339–2340).
Panel (b): Purser (2003, p. 98), F = −1.738 OD/m + 1.236 on OD/m
0.13–0.55, starting at the computed 1.010; F = 1 below (dashed, Purser's
stated normal speed); above 0.55 the fraction the equation reaches there,
0.28, dashed, as the darkness floor (a floor assumption in our reading); OD/m converted with
K = ln 10 · OD/m (base 10 as in Ch. 63, p. 2413; our conversion). FDS+Evac
(Korhonen 2021, Eq. 11): F = max(0.1, 1 − 0.057 K/0.706), solid over the
Frantzich–Nilsson data. No curve is digitised from a figure.
Script: `scripts/figures/fundamentals_speed_extinction.py`.
{{< /details >}}

## Fridolf et al. 2019: speed as a function of visibility

Fridolf, Ronchi, Nilsson and Frantzich (2019) reviewed smoke experiments
from seven countries and express walking speed *w* [m/s] against visibility
\(x = A/K_s\) [m], with *A* = 2 for light-reflecting and 8 for
light-emitting items (Eq. 1, citing Jin 2008). Fitting six data sets,
including Frantzich and Nilsson's, gives

$$
w = 0.34\,x + 0.31 \qquad \text{(Fridolf et al. 2019, Eq. 2)}
$$

with \(R^2\) = 0.54 on data at *x* ≈ 0.3–3 m, none between about 1.17 and
1.78 m (Fig. 3); the authors call it a first approximation (§3.3.3). For
design, each person's clear-condition speed is reduced by 0.34 m/s per
metre of visibility below 3 m, down to 0.2 m/s:

$$
w = \min\!\left(w_{\text{smoke free}},\; \max\!\left(0.2,\; w_{\text{smoke free}} - 0.34\,(3 - x)\right)\right) \qquad \text{(Eq. 7)}
$$

Eq. 7 is a design rule, not a fit: the slope of Eq. 2 plus two thresholds
chosen for conservatism (§3.3.2). Above 3 m, speed is taken as unaffected.

{{< details title="Caveats on Fridolf et al.'s laws" closed="true" >}}
**The visibility constant.** *A* is chosen for each data set from its
lighting (§3.3.1); the paper does not list which *A* was applied to which
set. Jin (1997, Eqs. 3–4) gives *V* = (5–10)/*C*ₛ for light-emitting and
(2–4)/*C*ₛ for reflecting signs, and his Fig. 1 draws the line
*C*ₛ·*V* = 8 for light-emitting signs, which matches *A* = 8; *A* = 2 is
the lower end of the reflecting range. FDS uses *C* = 3 for reflecting
signs by default (see [Visibility through smoke](/fundamentals/visibility.md)).
*A* = 2 is also the constant Frantzich and Nilsson (2003, report Eq. 2)
used for lit walls and objects. Jin's constants come from a chamber lit at
22–180 lx, and his σV values for light-emitting signs refer to 180 lx
(Cheung et al. 2026, §2 and §4.1); in dimmer light the constant for
light-emitting signs is larger (see [Do the sources conflict?](#do-the-sources-conflict)).

**The data sets.** Jin's non-irritant data only, Frantzich and Nilsson
(2003), Akizuki et al. (2007), Fridolf et al. (2013, 2014), Ronchi et al.
(2017) with Fridolf et al. (2015), and Seike et al. (2016) (§3.3). They
include an older group (Akizuki et al., mean age 70) and walks of up to
700 m (Table 2). Frantzich and Nilsson's data are an input to Eq. 2, so
the two laws agreeing is not an independent check.

**The data range.** The points in Fig. 3 span *x* ≈ 0.3–3 m, with none
between about 1.17 and 1.78 m. The value at *x* = 0, 0.31 m/s, is an
extrapolation. In terms of *K*, *x* = 0.3–3 m corresponds to
*K* = *A*/3 to *A*/0.3 (our arithmetic; each data set was converted with
its own *A*).

**Speed definitions.** All speeds include pauses. Table 2 codes Frantzich
and Nilsson's speed as "shortest way with pauses", whereas the report's
Eq. 3 uses the speed along the actual path, about 1/0.88 of the
shortest-way speed (report Fig. 11).

**Irritancy.** The authors call the selected data sets "non-irritant"
(§3.3). Table 2 marks Frantzich and Nilsson and Fridolf et al. (2013, 2014)
as "semi-irritant" and Ronchi et al. (2017) as non-irritant, while §4 names
Fridolf et al. (2013) and Ronchi et al. (2017) as the experiments with
acetic acid. They caution that the recommendation may not be conservative
in irritant smoke, where Jin saw speeds drop at visibilities of about 5 m,
against below 3 m in non-irritant smoke (§4).

**The floor.** The 0.2 m/s floor is attributed to Purser and McAllister
(2016) (§3.3.2); Ch. 63 gives about 0.3 m/s for walking in darkness
(pp. 2339 and 2413).

**The three design methods.** \(w_{\text{smoke free}}\) is 1 m/s for
everyone (method 1, Eq. 3); 1.35, 1.10 or 0.85 m/s for medium, slow and
very slow walkers (method 2, Eqs. 4–6); or drawn for each person from a
normal distribution with mean 1.35 m/s and SD 0.25 m/s, truncated at 0.85
and 1.85 m/s (method 3, Eq. 7). The authors describe the reduction as
absolute, because every person loses the same speed, and fractional,
because it starts from each person's own clear-condition speed (§3.3.3 and
§4). Worked example: at 2 m visibility, 1.2 m/s becomes 0.86 m/s and
1.0 m/s becomes 0.66 m/s (§3.3.3).
{{< /details >}}

![Two panels. Left: walking speed against visibility, with Fridolf's regression over 0.3 to 3 m, the Eq. 7 design lines for four clear-condition speeds, and Frantzich–Nilsson converted with x = 2/K. Right: Fridolf's regression converted to extinction coefficient with A = 2 and A = 8, next to Frantzich–Nilsson and Purser](/images/fundamentals/speed_visibility.png)

*(a) Speed against visibility x [m]: Fridolf Eq. 2 (dark), Eq. 7 design
lines (thin), Frantzich–Nilsson with x = 2/K (blue). (b) Eq. 2 converted to
K [1/m] with x = A/K (A = 2, 8; Fridolf's A, not the FDS C) over x = 0.3–3 m,
beside Frantzich–Nilsson and Purser.*

{{< details title="Figure provenance" closed="true" >}}
In (a), Eq. 2, w = 0.34 x + 0.31, is solid over x = 0.3–3 m, dotted over
the gap without data at 1.17–1.78 m and dashed below 0.3 m (Fridolf et al.
2019, Fig. 3). Eq. 7 is
drawn for the clear-condition speeds of Eqs. 3–6 (1.00, 1.35, 1.10 and
0.85 m/s); Eq. 4 runs 0.02 m/s above Eq. 2 below 3 m. Frantzich–Nilsson,
v = 0.706 − 0.057 K on K = 1.9–7.4 1/m, is converted with their own
constant for lit objects, x = 2/K, to x ≈ 0.27–1.05 m; its speed is along the
actual path, not the shortest way (see the caveats above). In (b) the
conversion x = A/K maps x = 0.3–3 m to K = A/3 to A/0.3. Each data set was
converted with its own A, which the paper does not state, so the curves
show the two bounding conversions, not data ranges in K. Purser Eq. 63.10
is drawn on K = 0.32–0.5 and 1.9–7.5 1/m. Script: `scripts/figures/fundamentals_speed_visibility.py`.
{{< /details >}}

## Known limits

All laws come from volunteers who knew they were in an experiment: short
walks by healthy, mostly young adults for Jin (20 m) and Frantzich and
Nilsson (37 m), plus longer tunnels and older people in Fridolf et al.'s fit.
Only Jin used smoke from real fires, and none covers heat. The Jin and
Frantzich–Nilsson data should not be combined as one data set, and a
relation used outside its measured range is an extrapolation.

## Do the sources conflict?

In our assessment, mostly not in their data.

**Citation chains.** Most apparent conflicts come from how later sources
cite Jin: a participant population taken from another Jin study, a
0.3 m/s darkness speed that Ch. 63 attributes to Jin but that, in our
inference, is a floor assumption, three descriptions of the irritant smoke, two page ranges and
several dates for Jin's work, and a floor of 0.2 or 0.3 m/s. One difference sits in the data: Purser's replotted Jin
points are not those of Jin (1997, Fig. 3), possibly because they come
from a different Jin report. Details are in the block below.

**Different measurements.** The experiments differ in smoke, light, speed
definition and *K* range, and their *K* ranges do not overlap. Each law is
consistent with its own data; they part where one is extrapolated into
another's range. The visibility constant also depends on light: Cheung et
al. (2026) found σV = 4.7–9.5 for light-emitting signs at 180 lx, close to
Jin's 5–8, but 6–11 at 1–22 lx (§4.4, §6). They measured seeing a sign,
not walking; our inference is that any law written in *x* = *A*/*K*
carries the lighting of its experiments.

**The functional form is not established.** Linear in *K*
(Frantzich–Nilsson), logarithmic in *K* (Purser) or linear in *x*
(Fridolf): the data cannot choose, because there are none where the forms
differ most (about 1.1–1.9 1/m, and low *K*), \(R^2\) is only 0.34–0.54,
irritancy and low light are confounded in the Frantzich–Nilsson tunnel,
and low light also shifts the visibility constant. We read this as not
established rather than conflicting.

{{< details title="The assessment in detail" closed="true" >}}
**Citation chains.** Ronchi et al.'s population of 17 women and 14 men
belongs to Jin and Yamada's 1989 heat-and-smoke study, not the walking
experiment. Ch. 63 attributes the 0.3 m/s "as if in darkness" to Jin;
Purser (2003, p. 98) gives it for OD/m above 0.55 "since it is still
possible to move at this speed in total darkness". Our inference is that it
is a floor assumption, which only FRI Report No. 42 can settle; it appears
neither in Fig. 63.16 (lowest
non-irritant point about 0.45 m/s) nor in Jin (1997, Fig. 3). The
irritant smoke is burning wood cribs in Jin (1997) and Ch. 61, non-flaming
wood in Purser (2003) and heated wood chippings in Ch. 63. Jin 1978 is
given as pp. 135–157 and 135–155. FRI Report No. 42 is dated 1975 by
Purser (2003) and 1976 by Ch. 63 and Ronchi et al., same title and number; Fridolf et al. date
the same Jin study 1976, 1978/1997 and 1979, and take a 0.2 m/s floor from
Purser and McAllister, who give about 0.3 m/s. Purser's Jin fits use
his own replotted points (non-irritant *K* = 0.2–1.13 1/m); Jin's 1997
figure starts at 0.52 1/m and sits a few hundredths of a m/s higher. That
is an open question about sources, not an error by either.

**Different measurements.** Smoke: real-fire smoke, irritant or not, in
Jin; cold artificial smoke with 10–15 ppm acetic acid in Frantzich and
Nilsson. Light: 0–8 lx in the smoke-filled Frantzich–Nilsson tunnel.
Speed: along the corridor for Jin, along the walked path for Frantzich and
Nilsson (about 1/0.88 of the shortest-way speed that Fridolf et al.
record). *K*: Jin's data end near 1.1 1/m and Frantzich and Nilsson's
begin at 1.9 1/m.
{{< /details >}}

{{< details title="Cheung et al. (2026) in more detail" closed="true" >}}
Cheung et al. rebuilt Jin's 5.5 m chamber (2.4 × 2.4 m cross-section),
viewed a light-emitting Landolt "C" through industrial white smoke at 5.5,
10.5 and 15.5 m, and varied the ambient light from 1 to 222 lx (§3).
Findings relevant here:

- Jin's σV range of 5–8 for light-emitting signs refers to 180 lx; at that
  light they measure 5.3–9.5 at 5.5 and 10.5 m and 4.7–8 at 15.5 m
  (§4.1, Fig. 8). At 1 lx σV is 7.5–11, and at 22 lx 6–11 (§4.4, Fig. 11).
  σV rises with the logarithm of the normalised sign brightness πLₜ/E, so
  it is constant only for a given brightness.
- At 60 and 22 lx, a sign of the same luminance was seen at about 7 % and
  11 % higher extinction in Jin's data than in theirs (§4.1, §6); the
  abstract states the direction the other way round.
- The critical extinction coefficient falls by about 40 % for every 5 m
  added to the viewing distance (§4.3).
- Limits they state: one observer with visual acuity 1.0 who knew the
  sign's shape and location, industrial smoke rather than fire smoke, a
  laboratory sign, and no reflecting signs, so the reflecting range
  C = 2–4 is not retested (§5).

They identify Jin's source for the sign experiment as Jin (1970),
*Visibility through fire smoke (I)*, Bull. Japan Assoc. Fire Sci. Eng. 19,
with parts II (1971) and III (1972) following; "Part 5" (FRI Report
No. 42, 1975/1976) appears to belong to the same series (our inference).
{{< /details >}}

## Sources

- Jin, T. (1975/1976). *Visibility through fire smoke, Part 5: Allowable
  smoke density for escape from fire*. Report of Fire Research Institute
  of Japan, No. 42, p. 12. No DOI or public URL. Dated 1975 in Purser
  (2003, ref. 7) and 1976 in SFPE Ch. 63 (ref. 53) and Ronchi et al.
  (2013, ref. 11); the year is not established.
- Jin, T. (1978). *Visibility through fire smoke*. Journal of Fire &
  Flammability, 9, 135–157. No DOI or public URL; pages 135–155 in
  Fridolf et al. (2019).
- Jin, T., & Yamada, T. (1985). *Irritating effects of fire smoke on
  visibility*. Fire Science and Technology, 5(1), 79–90.
  [doi:10.3210/fst.5.79](https://doi.org/10.3210/fst.5.79)
- Jin, T., & Yamada, T. (1989). *Experimental study of human behavior in
  smoke filled corridors*. Fire Safety Science, 2, 511–519.
  [doi:10.3801/iafss.fss.2-511](https://doi.org/10.3801/iafss.fss.2-511)
- Jin, T. (1997). *Studies on human behavior and tenability in fire
  smoke*. Fire Safety Science, 5, 3–21.
  [doi:10.3801/iafss.fss.5-3](https://doi.org/10.3801/iafss.fss.5-3)
- Frantzich, H., & Nilsson, D. (2003). *Utrymning genom tät rök: beteende
  och förflyttning* [Evacuation in dense smoke: behaviour and movement].
  Report 3126, LUTVDG/TVBB--3126--SE, Department of Fire Safety
  Engineering, Lund University.
  [lup.lub.lu.se (open access)](https://lup.lub.lu.se/search/publication/2b23c428-7809-46e1-87b0-22bf247f6386)
- Ronchi, E., Gwynne, S. M. V., Purser, D. A., & Colonna, P. (2013).
  *Representation of the impact of smoke on agent walking speeds in
  evacuation models*. Fire Technology, 49(2), 411–431.
  [doi:10.1007/s10694-012-0280-y](https://doi.org/10.1007/s10694-012-0280-y)
- Fridolf, K., Ronchi, E., Nilsson, D., & Frantzich, H. (2019). *The
  representation of evacuation movement in smoke-filled underground
  transportation systems*. Tunnelling and Underground Space Technology,
  90, 28–41.
  [doi:10.1016/j.tust.2019.04.016](https://doi.org/10.1016/j.tust.2019.04.016)
- Purser, D. A. (2003). *ASET and RSET: addressing some issues in relation
  to occupant behaviour and tenability*. Fire Safety Science, 7, 91–102.
  [doi:10.3801/IAFSS.FSS.7-91](https://doi.org/10.3801/IAFSS.FSS.7-91)
- Purser, D. A., & McAllister, J. L. (2016). *Assessment of hazards to
  occupants from smoke, toxic gases, and heat*. SFPE Handbook of Fire
  Protection Engineering, 5th ed., Ch. 63, 2308–2428.
  [doi:10.1007/978-1-4939-2565-0_63](https://doi.org/10.1007/978-1-4939-2565-0_63)
- Yamada, T., & Akizuki, Y. (2016). *Visibility and human behavior in fire
  smoke*. SFPE Handbook of Fire Protection Engineering, 5th ed., Ch. 61,
  2181–2206.
  [doi:10.1007/978-1-4939-2565-0_61](https://doi.org/10.1007/978-1-4939-2565-0_61)
- Cheung, W. K., Bielawski, J., Arnold, L., Huang, X., & Węgrzyński, W.
  (2026). *Reappraisal of Jin's visibility through fire smoke experiment:
  Insights into signage visibility and the impact of ambient light*. Fire
  Safety Journal, 159, 104573.
  [doi:10.1016/j.firesaf.2025.104573](https://doi.org/10.1016/j.firesaf.2025.104573)
- Korhonen, T. (2021). *Fire Dynamics Simulator with Evacuation: FDS+Evac.
  Technical Reference and User's Guide* (FDS 6.7.6, Evac 2.6.0 draft). VTT
  Technical Research Centre of Finland.
  [github.com/tkorhon1/FDS-Evac-Guide](https://github.com/tkorhon1/FDS-Evac-Guide).
  Secondary source for the fractional form.

How pyFDS-Evac uses this: see the [smoke-speed model](/models/smoke-speed.md).
