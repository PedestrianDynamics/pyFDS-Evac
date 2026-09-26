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

## Jin: irritant and non-irritant smoke

Jin's subjects walked along a 20 m corridor filled with irritant white smoke
(burning wood cribs) or less irritant black smoke (burning kerosene)
(Yamada and Akizuki 2016, Society of Fire Protection Engineers (SFPE)
Handbook Ch. 61, Fig. 61.22, citing Jin 1978 and Jin and Yamada 1985; see
also Jin 1997). In irritant smoke the speed fell from about 1.0 to 0.3 m/s
as *K* rose from 0.1 to 0.5 1/m, and subjects walked zigzag or along the
wall because they could not keep their eyes open. In non-irritant smoke it
fell from about 1.0 to 0.5 m/s over *K* = 0.2 to 1.0 1/m (Ronchi et al.
2013, p. 414 and Fig. 1). At high densities subjects moved at about
0.3 m/s, as if in darkness (Purser and McAllister 2016, Ch. 63,
pp. 2340–2341).

## Frantzich and Nilsson: a linear regression in dense smoke

Frantzich and Nilsson (2003, Lund report 3126) sent 46 young volunteers one
at a time through a 36.75 m tunnel filled with artificial smoke made
irritant with acetic acid, at *K* ≈ 2–7 1/m (§3.2). For the 32 runs with
the lighting on, a linear regression (report Eq. 3, Table D2, model 1) gave
the **absolute** speed

$$
v = \alpha + \beta K, \qquad \alpha = 0.706~\mathrm{m/s}\;(\text{s.d. } 0.069),\quad
\beta = -0.057~\mathrm{m^2/s}\;(\text{s.d. } 0.015),
$$

with \(R^2\) = 0.342.

{{< details title="More on the Frantzich–Nilsson data" closed="true" >}}
The participants were 30 men and 16 women, mean age about 22, mostly
students; the tunnel was 5 m wide. Their comparison with Jin gives the
smoke range as about 2 to 8 1/m. With the lighting off (12 observations)
the slope was not significantly different from zero. A second model with
the share of the route walked along the wall fitted better (adjusted
\(R^2\) 0.416 against 0.320): walking along the wall raised the speed. The
95 % prediction interval at *K* = 4 1/m was about 0.2 to 0.7 m/s, and the
authors state that a randomly chosen person in dense smoke (*K* = 8 1/m)
could walk at anything between 0 and 0.6 m/s. The participants were young
and fit, so the authors expect a real population to do worse.
{{< /details >}}

## The fractional form is FDS+Evac's normalisation

FDS+Evac, the evacuation module of the Fire Dynamics Simulator (FDS), does
not use the regression as an absolute speed. It scales each agent's
unimpeded speed \(v_i^0\) by the same factor (Korhonen 2021, Eq. 11):

$$
v_i^0(K_s) = \max\!\left(v^0_{i,\min},\; v_i^0\left(1 + \frac{\beta}{\alpha}K_s\right)\right),
\qquad v^0_{i,\min} = 0.1\,v_i^0 \text{ by default.}
$$

The factor divides the regression by its intercept, 0.706 m/s, an
extrapolation to *K* = 0 from data at *K* ≈ 2–8 1/m, not a measured free
walking speed. Ronchi et al. (2013) call the two readings fractional and
absolute reductions, and show that the same model can give different
evacuation times depending on the data set and reading chosen.

## Purser: a logarithmic fit for irritant smoke

For able-bodied occupants in moderately irritant smoke, Purser and
McAllister (2016, Ch. 63) give an average speed, with a population
standard deviation of 0.157 m/s (p. 2414),

$$
W_{\mathrm{smoke}}~[\mathrm{m/s}] = -0.1364\,\ln \alpha_k + 0.6423 \qquad \text{(Eq. 63.10)}
$$

where \(\alpha_k\) [1/m] is the extinction coefficient.

## Fridolf et al. 2019: speed as a function of visibility

Fridolf, Ronchi, Nilsson and Frantzich (2019) reviewed smoke-filled tunnel
and corridor experiments from seven countries and express walking speed
*w* [m/s] as a function of visibility *x* [m], which lets data recorded
under different lighting be compared. They take \(x = A/K_s\) with *A* = 2
for light-reflecting and 8 for light-emitting items (their Eq. 1); note
that the reflecting value differs from the conventional *C* = 3 of Jin and
FDS (see [Visibility through smoke](/fundamentals/visibility.md)). Fitting
the data at 0–3 m visibility gives

$$
w = 0.34\,x + 0.31 \qquad \text{(Fridolf et al. 2019, Eq. 2)}
$$

with \(R^2\) = 0.54. For design, each person's clear-condition speed
\(w_{\text{smoke free}}\) is reduced by 0.34 m/s per metre of visibility
below 3 m, down to 0.2 m/s:

$$
w = \min\!\left(w_{\text{smoke free}},\; \max\!\left(0.2,\; w_{\text{smoke free}} - 0.34\,(3 - x)\right)\right) \qquad \text{(Eq. 7)}
$$

{{< details title="Fridolf et al.'s three design methods" closed="true" >}}
The methods differ in \(w_{\text{smoke free}}\): 1 m/s for everyone
(method 1, Eq. 3); 1.35, 1.10 or 0.85 m/s for medium, slow and very slow
walkers (method 2, Eqs. 4–6); or a value drawn for each person from a
normal distribution with mean 1.35 m/s and standard deviation 0.25 m/s,
truncated at 0.85 and 1.85 m/s (method 3, Eq. 7). The authors describe the
reduction as absolute, because every person loses the same speed, and
fractional, because it starts from each person's own clear-condition speed
(§3.4).
{{< /details >}}

## Known limits

All of these relations come from short walks by healthy, mostly young adults
who knew they were in an experiment. None covers a real fire's heat or toxic
gases. The Jin and Frantzich–Nilsson data do not overlap in *K*, differ in
irritancy and lighting, and should not be combined as if they were one data
set. Using a relation outside its measured *K* range is an extrapolation.

## Sources

- Jin, T. (1978). *Visibility through fire smoke*. Journal of Fire &
  Flammability, 9, 135–157. No DOI or public URL; pages 135–155 in
  Fridolf et al. (2019).
- Jin, T., & Yamada, T. (1985). *Irritating effects of fire smoke on
  visibility*. Fire Science and Technology, 5(1), 79–90.
  [doi:10.3210/fst.5.79](https://doi.org/10.3210/fst.5.79)
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
- Purser, D. A., & McAllister, J. L. (2016). *Assessment of hazards to
  occupants from smoke, toxic gases, and heat*. SFPE Handbook of Fire
  Protection Engineering, 5th ed., Ch. 63, 2308–2428.
  [doi:10.1007/978-1-4939-2565-0_63](https://doi.org/10.1007/978-1-4939-2565-0_63)
- Yamada, T., & Akizuki, Y. (2016). *Visibility and human behavior in fire
  smoke*. SFPE Handbook of Fire Protection Engineering, 5th ed., Ch. 61,
  2181–2206.
  [doi:10.1007/978-1-4939-2565-0_61](https://doi.org/10.1007/978-1-4939-2565-0_61)
- Korhonen, T. (2021). *Fire Dynamics Simulator with Evacuation: FDS+Evac.
  Technical Reference and User's Guide* (FDS 6.7.6, Evac 2.6.0 draft). VTT
  Technical Research Centre of Finland.
  [github.com/tkorhon1/FDS-Evac-Guide](https://github.com/tkorhon1/FDS-Evac-Guide).
  Secondary source for the fractional form.

How pyFDS-Evac uses this: see the [smoke-speed model](/models/smoke-speed.md).
