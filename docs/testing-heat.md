---
title: "Heat dose in a uniform room"
linkTitle: "Heat dose"
weight: 15
math: true
aliases: [/docs/testing-heat/]
---

| | |
|---|---|
| **Component** | Heat FED and heat incapacitation ([Models › Heat](/models/heat.md)) |
| **Level** | FDS case: a full run on FDS output |
| **Asset** | `assets/fed_incap_heat_150c` (also `_100c` and `_200c`) |
| **Expected value from** | hand calculation of SFPE Eq. 63.44 on FDS's own `TEMPERATURE` slice |
| **Status** | passes; checks the pipeline, not the law ([#219](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/219)) |

![100 agents walk a loop in a room at 150 °C; their colour shows the heat dose, and all of them stop at 125 s](/images/verification/heat_room.gif)

## What is tested

Whether the heat dose an agent accumulates in pyFDS-Evac is the dose the
equation gives for the gas temperature FDS computed at that agent, and
whether the agent stops when the dose reaches its threshold. The room has
almost the same temperature everywhere, so every agent follows nearly one
curve. Any difference from the hand calculation comes from the code:
reading the slice, sampling it at the agent, summing the dose, or applying
the threshold. It checks that the code applies SFPE Eq. 63.44 correctly,
not that the equation predicts human tolerance.

## Equation

The convective heat dose, SFPE Handbook 5th ed., Ch. 63, Eq. 63.44
([Models › Heat](/models/heat.md)), with *T* the gas temperature in °C and
Δ*t* in minutes:

```
FED_HEAT = sum_{t1}^{t2} [ T^3.4 / 5e7 ] * dt
```

At a constant temperature the sum has a closed form, and FED = 1 is reached
at \(t^{*}\):

```
FED_HEAT(t) = (T^3.4 / 5e7) x t_min
```

$$
t^{*} = \frac{60 \times 5\times10^{7}}{T^{3.4}}\ \text{s}.
$$

A 1 % error in *T* gives a 3.4 % error in the dose.

In the default `deterministic` mode every agent stops at FED = 1. In
`probabilistic` mode (opt-in) agent *i* stops at its own threshold
\(D_i = \exp(\sigma Z_i)\), \(Z_i \sim N(0,1)\), σ = 0.94, so the fraction
of agents stopped by time *t* is

$$
F(t) = \Phi\!\left(\frac{\ln \mathrm{FED}(t)}{\sigma}\right).
$$

## Setup

![Plan of the 30 m room: spawn area, the loop the agents walk, and the TEMPERATURE slice at breathing height](/images/verification/heat_room_setup.png)

- **FDS:** a sealed 30 × 30 × 3 m room, no fire, no species, adiabatic on
  all six faces, four meshes. At *t* = 0 the whole room is set to 100, 150
  or 200 °C. `TEMPERATURE` slices at 1.5 m, the one nearest the 1.6 m
  sampling height on this 0.5 m grid.
- **Agents:** 100 agents walk a loop between four corner checkpoints and
  never leave. Each agent's temperature is sampled every second.
- **Runs:** `--enable-heat-fed` (heat is off by default), deterministic at
  all three temperatures; probabilistic at 150 °C.
- **Workaround:** the decks have no soot, so the runs need
  `--constant-extinction 0 --no-visibility`
  ([#248](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/248)).
  Neither changes the heat dose.

## Expected

FDS does not keep the room at the deck value. Within the first minute the
temperature at 1.5 m falls by about 1 % and then stays; the spread across the
room is about 1 K. So the expected dose is not the closed form at the deck
temperature. It is the sum of Eq. 63.44 over the temperature FDS wrote at
each agent's position, read from the slice with fdsreader, independent of
pyFDS-Evac.

![Room temperature at 1.5 m against time for the three decks, as a percentage of the deck value](/images/verification/heat_room_temperature.png)

| Deck | Slice *T* after 60 s | \(t^{*}\) at the deck *T* | Hand sum reaches FED = 1 |
|---|---|---|---|
| 100 °C | 98.9 – 99.5 °C | 475.5 s | **487 s** |
| 150 °C | 147.7 – 148.5 °C | 119.8 s | **125 s** |
| 200 °C | 195.7 – 196.8 °C | 45.0 s | **48 s** |

The hand sum is taken at each agent's own position and update times. For
all 100 agents it reaches 1 at the same update, so each deck has a single
expected stop time.

For the probabilistic run at 150 °C, *F*(999 s) = 98.7 % of agents are
expected to have stopped by the end.

## Result

![Heat FED against time for the 100 agents at 150 °C, the hand sum and the closed form; below, each agent's difference from its own hand sum](/images/verification/heat_room_fed.png)

At 150 °C every agent's dose equals its hand sum to 3.1 × 10⁻⁸. The
difference comes from one agent, at one update, standing next to the corner
where the four meshes meet; there the meshes differ by up to 0.04 K
([#239](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/239)).
Summed from the temperature the agent recorded, the dose agrees to
2.5 × 10⁻¹⁴.

![Time to heat FED = 1 against temperature on log axes: the closed form, the hand sum and the simulated stop for the three decks](/images/verification/heat_room_scaling.png)

At all three temperatures the simulated stop (×) falls on the hand sum (○).
The shift from the closed form at the deck value (◆) is FDS's 1 % drop, not
the code.

![Fraction of agents incapacitated by heat against time in the probabilistic run at 150 °C, with the expected log-normal curve and its 95 % band](/images/verification/heat_room_incapacitation.png)

| Check | Expected | Simulated |
|---|---|---|
| agent *T* against the slice, 100 / 150 / 200 °C | equal, within 0.03 / 0.04 / 0.05 K | max 1.4 × 10⁻¹⁴ / 1.7 × 10⁻⁴ / 3.8 × 10⁻⁴ K |
| agent FED against the hand sum of its recorded *T*, 100 / 150 / 200 °C | ≤ 10⁻⁹ | max 7.6 × 10⁻¹⁵ / 2.5 × 10⁻¹⁴ / 1.7 × 10⁻¹³ |
| agent FED against the hand sum on the slice, 100 / 150 / 200 °C | equal, but for the mesh border | max 7.6 × 10⁻¹⁵ / 3.1 × 10⁻⁸ / 1.4 × 10⁻⁷ |
| deterministic stop, 100 °C | 487 s | all 100 agents at 487 s |
| deterministic stop, 150 °C | 125 s | all 100 agents at 125 s |
| deterministic stop, 200 °C | 48 s | all 100 agents at 48 s |
| cause of every stop | `heat` | `heat` |
| probabilistic, 150 °C: stopped by 999 s | 98.7 % | 100 of 100 |
| probabilistic, 150 °C: largest gap between the curves | ≤ 0.136 | 0.120 |

## Pass criteria

1. **Slice to agent.** The temperature each agent recorded equals the slice
   value at its nearest node and nearest slice time. The only allowed
   difference is at a node two meshes share, where the slice holds two
   values; the tolerance is the largest such gap in the run (0.03, 0.04 and
   0.05 K).
2. **Dose.** Every agent's FED equals the hand sum of Eq. 63.44 over the
   temperatures it recorded to round-off, |FED − FED_hand| ≤ 10⁻⁹. With
   criterion 1 this covers the whole chain from slice to dose.
3. **Deterministic stop.** Every agent stops at the first update where its
   hand sum reaches 1, with cause `heat`. Updates are 1 s apart
   (`--smoke-update-interval`).
4. **Probabilistic stop.** The fraction of stopped agents stays within the
   95 % Kolmogorov–Smirnov band of *F*(*t*),
   \(1.36/\sqrt{n} = 0.136\) for *n* = 100.

## Run it yourself

The FDS output is not in the repository (65 MB per deck). Either get it
from the project's data folder (`fds-evac-data/fed_incap_heat_<T>c/fds/`),
or rerun FDS outside the repository, about one minute per deck on four
cores:

```bash
mkdir -p <data>/fed_incap_heat_150c/fds && cd $_
cp <repo>/assets/fed_incap_heat_150c/fed_incap_heat_150c.fds .
mpiexec -n 4 fds fed_incap_heat_150c.fds
```

Then run pyFDS-Evac and draw the figures. The data folder must hold
`fed_incap_heat_<T>c/fds/` and `fed_incap_heat_<T>c/evac/<mode>/`:

```bash
for T in 100 150 200; do
  uv run python run.py --scenario assets/fed_incap_heat_${T}c \
    --fds-dir <data>/fed_incap_heat_${T}c/fds \
    --enable-heat-fed --heat-incapacitation-mode deterministic \
    --constant-extinction 0 --no-visibility \
    --output-sqlite <data>/fed_incap_heat_${T}c/evac/deterministic/run.sqlite \
    --output-fed-history <data>/fed_incap_heat_${T}c/evac/deterministic/fed_history.csv
done
# and once more for 150 °C with --heat-incapacitation-mode probabilistic,
# into evac/probabilistic/
uv run python scripts/verification/heat_room_figures.py --data <data>
```

Each run takes about three minutes. A temperature without output is skipped.

## Limits

- **The law is not verified.** The expected values use Eq. 63.44, the
  same formula as the code. Expected values from SFPE's tables are pending
  ([#219](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/219)).
- **The room is not at the deck temperature.** FDS settles about 1 % below
  the `&INIT` value within the first minute, so the stop times are 2 – 7 %
  later than the closed form at the deck temperature
  ([#253](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/253)). The page checks
  against the slice, so this does not affect the verdict; it matters if
  the deck value is quoted as the exposure.
- **Heat-only cases need a workaround.** Without a soot slice `run.py`
  crashes unless given `--constant-extinction 0 --no-visibility`
  ([#248](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/248)).
- **σ = 0.94 has no source for heat.** It is borrowed from the gas dose
  ([#225](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/225)). The
  probabilistic run checks the code path, not the spread.
- **Convective heat only.** No radiant dose
  ([#221](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/221)).
  Below the threshold heat changes neither speed nor route
  ([#81](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/81)).
- A near-uniform field cannot show whether the field is sampled at the
  agent's *current* position; that needs a gradient
  ([#24](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/24)).
- This page is not an automated test: the check runs from the figure
  script on the stored output. The equation-level tests
  (`tests/verification/test_s6_heat_fed.py`, `test_heat_fed_verif.py`) run
  on synthetic fields in CI.
