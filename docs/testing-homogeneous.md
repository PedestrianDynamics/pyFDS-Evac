---
title: "CO dose in a uniform room"
linkTitle: "CO dose"
weight: 14
math: true
aliases: [/docs/testing-homogeneous/, /models/verification/testing-homogeneous/]
---

| | |
|---|---|
| **Component** | Gas FED and incapacitation ([Models › FED](/models/fed.md)) |
| **Level** | FDS case: a full run on FDS output |
| **Asset** | `assets/fed_incap_co_2000ppm` |
| **Expected value from** | hand calculation, and FDS's own `FED` device |
| **Status** | passes |

![100 agents walk a loop in a room filled with 2000 ppm CO; their colour shows the dose, and a cross marks an incapacitated agent](/images/verification/co_room.gif)

## What is tested

Whether the dose an agent accumulates in pyFDS-Evac is the dose the
equations give, and whether agents stop when it says they should. The room
holds the same gas everywhere and at all times, so every agent, wherever it
walks, must follow one curve, FED(*t*), that can be computed by hand. Any
difference comes from the code: reading the FDS slice, sampling it at the
agent, summing the dose, or applying the threshold.

## Equation

The gas FED, as in FDS's `FED` function
([Models › FED](/models/fed.md#coded-form); the published law is on
[Fundamentals › Asphyxiant FED](/fundamentals/asphyxiant-fed.md)), with *C* in ppm for CO and in
volume percent for CO₂ and O₂, and *t* in minutes:

```
FED_CO = 2.764e-5 x (C_CO)^1.036 x t
HV_CO2 = exp(0.1903 x C_CO2 + 2.0004) / 7.1   if C_CO2 > 0
HV_CO2 = 1                                    if C_CO2 <= 0 (or not finite)
FED_O2 = t / exp[8.13 - 0.54 x (20.9 - C_O2)]  only below 20 % O2
FED    = FED_CO x HV_CO2 + FED_O2
```

With a constant mixture the dose grows linearly, and FED = 1 is reached at

$$
t^{*} = \frac{60}{r_{\mathrm{CO}}\,\mathrm{HV}_{\mathrm{CO_2}}}\ \text{s},
\qquad r_{\mathrm{CO}} = 2.764\times10^{-5}\,C_{\mathrm{CO}}^{1.036}\ \text{min}^{-1}.
$$

In `probabilistic` mode (opt-in) agent *i* stops at its
own threshold \(D_i = \exp(\sigma Z_i)\), \(Z_i \sim N(0,1)\), σ = 0.94. Because
FED grows linearly, agent *i* stops at \(D_i\,t^{*}\), and the fraction of
agents stopped by time *t* is

$$
F(t) = \Phi\!\left(\frac{\ln(t/t^{*})}{\sigma}\right).
$$

## Setup

![Plan of the 30 m room: spawn area, the loop the agents walk, the exit, and the CO slice at breathing height](/images/verification/co_room_setup.png)

- **FDS:** a sealed 30 × 30 × 3 m room, no fire, no vents, four meshes. At
  *t* = 0 it is filled with 2000 ppm CO, 500 ppm CO₂, 20.9 % O₂ and soot for
  *K* ≈ 1 /m. Slices at 1.6 m, which FDS places at 1.5 m on this 0.5 m grid.
- **Agents:** 100 agents walk a loop between four corner checkpoints, so they
  stay in the room and keep moving; the field is sampled at each agent's
  position every second.
- **Runs:** once with `--incapacitation-mode deterministic` (the default,
  given explicitly), once with
  `--incapacitation-mode probabilistic`.

## Expected

The concentrations are read from the FDS slice itself, independently of
pyFDS-Evac: 1999.86 ppm CO, 0.049992 % CO₂ and 20.8985 % O₂, the same in every
cell and at all 1001 slice times. O₂ is above 20 %, so its term is zero. Then

| Quantity | Value |
|---|---|
| \(r_{\mathrm{CO}}\) | 0.072673 /min |
| \(\mathrm{HV}_{\mathrm{CO_2}}\) | 1.05108 |
| \(t^{*}\), hand calculation | **785.49 s** |
| \(t^{*}\), FDS's own `FED` device in the same run | 785.44 s |
| agents stopped by 999 s, probabilistic, \(F(999\ \mathrm{s})\) | 60.1 % |

Earlier versions of this page quoted 782.4 s. That value added an O₂ term at
20.9 % O₂, which FDS and pyFDS-Evac apply only below 20 %.

## Result

![FED against time for the 100 agents, the hand calculation and FDS's FED device; below, the difference from the hand calculation](/images/verification/co_room_fed.png)

All 100 agents follow the hand calculation to within 1.4 × 10⁻¹⁴, round-off
in the last digit. FDS's own device lies up to 7.7 × 10⁻⁵ above it at 1000 s,
a relative difference of 6 × 10⁻⁵.

![Fraction of agents incapacitated against time in the probabilistic run, with the expected log-normal curve and its 95 % band](/images/verification/co_room_incapacitation.png)

| Check | Expected | Simulated |
|---|---|---|
| FED of every agent against the hand calculation | equal | max difference 1.4 × 10⁻¹⁴ |
| deterministic: incapacitation time | 785.49 s | all 100 agents at 786.0 s (first FED update after *t*\*) |
| probabilistic: agents stopped by 999 s | 60.1 % | 61 of 100 |
| probabilistic: largest gap between the curves | ≤ 0.136 | 0.048 |

## Pass criteria

1. **Dose.** Every agent's FED equals the hand calculation to round-off,
   |FED − FED_hand| ≤ 10⁻⁹.
2. **Deterministic stop.** Every agent stops at the first FED update at or
   after *t*\*: \(t^{*} \le t_i < t^{*} + \Delta t\), with the update interval
   Δ*t* = 1 s (`--smoke-update-interval`).
3. **Probabilistic stop.** The empirical fraction of stopped agents stays
   within the 95 % Kolmogorov–Smirnov band of *F*(*t*),
   \(1.36/\sqrt{n} = 0.136\) for *n* = 100 agents. Agents whose threshold
   lies beyond the end of the run are counted as not yet stopped.

## Run it yourself

The FDS output is not in the repository (254 MB). Either get it from the
project's data folder (`fds-evac-data/fed_incap_co_2000ppm/fds/`), or rerun
FDS, about one minute on four cores:

```bash
cd assets/fed_incap_co_2000ppm
mpiexec -n 4 fds fed_incap_co_2000ppm.fds
```

Then run pyFDS-Evac in both modes and draw the figures:

```bash
for mode in deterministic probabilistic; do
  uv run python run.py --scenario assets/fed_incap_co_2000ppm \
    --fds-dir <fds output> --incapacitation-mode $mode \
    --output-sqlite <out>/$mode/run.sqlite \
    --output-fed-history <out>/$mode/fed_history.csv
done
uv run python scripts/verification/co_room_figures.py --data <out>
```

The evacuation itself takes about three minutes. Before it starts, the first
run builds the sign-visibility cache for the 25 checkpoints at every FDS time,
which takes much longer
([#236](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/236)); add
`--vis-cache <file>` to both runs so the second one reuses it.

## Limits

- One concentration. The 4000 and 8000 ppm decks
  (`assets/fed_incap_co_4000ppm`, `assets/fed_incap_co_8000ppm`) have CO₂ and
  O₂ slices at 2.0 m only (CO also at 0.5–2.5 m) and no 1.6 m slices, and
  have not been rerun.
- CO only, with CO₂ at an ambient level and O₂ above 20 %, so the O₂ term and
  the optional gases (HCN, NOx, irritants) are not exercised here. The FDS
  [`FED_FIC` case](https://github.com/PedestrianDynamics/pyFDS-Evac/blob/main/tests/verification/test_fed_fic_all_zones.py)
  covers those as an equation-level check.
- A uniform field cannot show whether the field is sampled at the agent's
  *current* position; that needs a gradient
  ([#24](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/24)).
- A uniform field also hides which slice height the dose is read from. That
  is checked separately in a room with CO in layers
  ([test_fed_slice_height.py](https://github.com/PedestrianDynamics/pyFDS-Evac/blob/main/tests/verification/test_fed_slice_height.py));
  until [#238](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/238)
  was fixed, the FED read the first slice of each species in the deck.
- This page is not yet an automated test: the check runs from the figure
  script on the stored output.
