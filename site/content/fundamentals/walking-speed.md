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

Jin's subjects walked along a 20 m corridor filled with smoke from an early
stage of fire. Irritant white smoke came from burning wood cribs and less
irritant black smoke from burning kerosene (Yamada and Akizuki 2016,
Society of Fire Protection Engineers (SFPE) Handbook Ch. 61).
According to the summary of Ronchi et al. (2013), the population was 17 women
and 14 men aged 20 to 51. In irritant smoke the speed fell from about 1.0 to
0.3 m/s as *K* rose from 0.1 to 0.5 1/m, and subjects walked zigzag or along
the wall because they could not keep their eyes open. In non-irritant smoke
the speed fell more gradually, from about 1.0 to 0.5 m/s over *K* = 0.2 to
1.0 1/m. At high densities subjects moved at about 0.3 m/s, as if in darkness.

## Frantzich and Nilsson: a linear regression in dense smoke

Frantzich and Nilsson (2003, Lund report 3126) sent 46 volunteers (30 men,
16 women, mean age about 22, mostly students) one at a time through a tunnel
36.75 m long and 5 m wide, filled with artificial smoke to which acetic acid
was added to irritate the eyes and airways. The measured smoke density was
about 2 to 7 1/m in the tunnel (§3.2); their comparison with Jin gives the
range as about 2 to 8 1/m. For the 32 observations with the tunnel lighting
on, a linear regression (report Eq. 3, Table D2, model 1) gave the
**absolute** speed

$$
v = \alpha + \beta K, \qquad \alpha = 0.706~\mathrm{m/s}\;(\text{s.d. } 0.069),\quad
\beta = -0.057~\mathrm{m^2/s}\;(\text{s.d. } 0.015),
$$

with \(R^2\) = 0.342. With the lighting off (12 observations) the slope was
not significantly different from zero. A second model with the share of the
route walked along the wall fitted better (adjusted \(R^2\) 0.416 against
0.320): walking along the wall raised the speed. The 95 % prediction
interval at *K* = 4 1/m was about 0.2 to 0.7 m/s, and the authors state that
a randomly chosen person in dense smoke (*K* = 8 1/m) could walk at anything
between 0 and 0.6 m/s. The participants were young and fit, so the authors
expect a real population to do worse.

## The fractional form is FDS+Evac's normalisation

FDS+Evac, the evacuation module of the Fire Dynamics Simulator (FDS), does not use the regression as an absolute speed. It assumes that
the speed in smoke relative to the speed without smoke is the same for all
agents, and scales each agent's unimpeded speed \(v_i^0\) (Korhonen 2021,
Eq. 11):

$$
v_i^0(K_s) = \max\!\left(v^0_{i,\min},\; v_i^0\left(1 + \frac{\beta}{\alpha}K_s\right)\right),
\qquad v^0_{i,\min} = 0.1\,v_i^0 \text{ by default.}
$$

The factor \(1 + \beta K/\alpha\) divides the regression by its intercept,
0.706 m/s, which is an extrapolation to *K* = 0 from data taken at *K* ≈ 2–8
1/m, not a measured free walking speed. Ronchi et al. (2013) classify
the two readings as a fractional reduction (the speed depends on the initial
speed) and an absolute reduction (the speed depends only on the smoke),
combined with no, a constant or an individual minimum speed, and show that
the same model can give different evacuation times depending on the data set
and reading chosen.

## Purser: a logarithmic fit for irritant smoke

Purser and McAllister (2016, Ch. 63) suggest, for able-bodied occupants in
typically irritant fire smoke, an average speed

$$
W_{\mathrm{smoke}}~[\mathrm{m/s}] = -0.1364\,\ln \alpha_k + 0.6423 \qquad \text{(Eq. 63.10)}
$$

where \(\alpha_k\) [1/m] is the extinction coefficient, with a standard
deviation of 0.157 m/s for the population.

## Fridolf et al. 2019: speed as a function of visibility

Fridolf, Ronchi, Nilsson and Frantzich (2019) reviewed walking-speed data
from smoke-filled tunnel and corridor experiments in Sweden, Japan, the UK,
Norway, Finland, Canada and the Netherlands. They express walking speed as a
function of visibility rather than extinction coefficient, which lets data
recorded under different lighting be compared, and they propose three methods
for representing walking speed in design, with an explicit treatment of
uncertainty. Their fitted equations are not reproduced on this page; see the
paper.

## Known limits

All of these relations come from short walks by healthy, mostly young adults
who knew they were in an experiment. None covers a real fire's heat or toxic
gases. The Jin and Frantzich–Nilsson data do not overlap in *K*, differ in
irritancy and lighting, and should not be combined as if they were one data
set. Using a relation outside its measured *K* range is an extrapolation.

## Sources

- T. Jin (1978). Visibility through fire smoke. *Journal of Fire &
  Flammability* 9:135–157. No DOI.
- H. Frantzich and D. Nilsson (2003). *Utrymning genom tät rök: beteende och
  förflyttning* [Evacuation in dense smoke: behaviour and movement]. Report
  3126, Department of Fire Safety Engineering, Lund University.
  LUTVDG/TVBB--3126--SE.
  [lup.lub.lu.se (open access)](https://lup.lub.lu.se/search/publication/2b23c428-7809-46e1-87b0-22bf247f6386)
- E. Ronchi, S. M. V. Gwynne, D. A. Purser and P. Colonna (2013).
  Representation of the impact of smoke on agent walking speeds in
  evacuation models. *Fire Technology* 49:411–431.
  [doi:10.1007/s10694-012-0280-y](https://doi.org/10.1007/s10694-012-0280-y)
- K. Fridolf, E. Ronchi, D. Nilsson and H. Frantzich (2019). The
  representation of evacuation movement in smoke-filled underground
  transportation systems. *Tunnelling and Underground Space Technology*
  90:28–41.
  [doi:10.1016/j.tust.2019.04.016](https://doi.org/10.1016/j.tust.2019.04.016)
- D. A. Purser and J. L. McAllister (2016). *SFPE Handbook*, 5th ed., Ch. 63.
  [doi:10.1007/978-1-4939-2565-0_63](https://doi.org/10.1007/978-1-4939-2565-0_63)
- T. Yamada and Y. Akizuki (2016). *SFPE Handbook*, 5th ed., Ch. 61.
  [doi:10.1007/978-1-4939-2565-0_61](https://doi.org/10.1007/978-1-4939-2565-0_61)
- T. Korhonen (2021). *Fire Dynamics Simulator with Evacuation: FDS+Evac.
  Technical Reference and User's Guide* (FDS 6.7.6, Evac 2.6.0 draft). VTT
  Technical Research Centre of Finland. Secondary source for the fractional
  form.

How pyFDS-Evac uses this: see the [smoke-speed model](/models/smoke-speed.md).
