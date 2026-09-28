---
title: "Heat dose in a uniform room"
linkTitle: "Heat dose"
weight: 15
math: true
aliases: [/docs/testing-heat/, /models/verification/testing-heat/]
---

| | |
|---|---|
| **Component** | Heat FED and heat incapacitation ([Models › Heat](/models/heat.md)) |
| **Level** | FDS case: a full run on FDS output |
| **Asset** | `assets/fed_incap_heat_150c` (also `_100c` and `_200c`) |
| **Expected value from** | hand sum of SFPE Eq. 63.48 (rate from Eq. 63.44) on FDS's own `TEMPERATURE` slice |
| **Status** | passes; checks the pipeline, not the law ([#219](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/219)) |

![100 agents walk a loop in a room at 150 °C; their colour shows the heat dose, and all of them stop at 125 s](/images/verification/heat_room.gif)

## What is tested

Whether the heat dose an agent accumulates in pyFDS-Evac is the dose the
equation gives for the gas temperature FDS computed at that agent, and
whether the agent stops when the dose reaches its threshold. The room has
almost the same temperature everywhere, so every agent follows nearly one
curve. Any difference from the hand calculation comes from the code:
reading the slice, sampling it at the agent, summing the dose, or applying
the threshold. It checks that the code applies SFPE Eqs. 63.44 and 63.48
correctly, not that they predict human tolerance.

## Equation

SFPE Handbook 5th ed., Ch. 63 ([Models › Heat](/models/heat.md)). The time
to incapacitation by convected heat, with *T* the gas temperature in °C
(Eq. 63.44, p. 2382):

$$
t_{I,\mathrm{conv}} = 5\times10^{7}\,T^{-3.4}\ \text{min}.
$$

The Handbook states it for exposures of up to 2 h in air with less than
10 % water vapour by volume. The dose is summed over the exposure
(Eq. 63.48, p. 2383, without its radiant term), with Δ*t* in minutes:

```
FED_HEAT = sum_{t1}^{t2} [ T^3.4 / 5e7 ] * dt
```

Eq. 63.48 holds "providing that the temperature in the fire is stable or
increasing".

At a constant temperature the sum has a closed form, and FED = 1 is reached
at \(t^{*}\):

```
FED_HEAT(t) = (T^3.4 / 5e7) x t_min
```

$$
t^{*} = \frac{60 \times 5\times10^{7}}{T^{3.4}}\ \text{s}.
$$

A 1 % error in *T* (in °C) gives a 3.4 % error in the dose.

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
  never leave. Each agent's temperature is sampled every second. Seed 42
  (the default `baseSeed`).
- **Runs:** `--enable-heat-fed` (heat is off by default), deterministic at
  all three temperatures; probabilistic at 150 °C.
- **No soot:** the decks have no soot slice, so `run.py` warns that smoke
  speed reduction is off and that visibility falls back to clear air
  ([#248](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/248)).
  Neither enters the heat-dose rate; clear-air visibility changes only where
  agents walk, and the expected dose is read at those positions.

## Expected

FDS does not keep the room at the deck value. Within the first minute the
room mean at 1.5 m falls by 0.7, 1.2 and 1.8 % (100, 150, 200 °C) and then
stays; the spread across the room is about 1 K. So the expected dose is not
the closed form at the deck temperature. It is the sum of Eq. 63.48 over the
temperature FDS wrote at each agent's position, read from the slice with
fdsreader, independent of pyFDS-Evac.

![Room temperature at 1.5 m against time for the three decks, as a percentage of the deck value](/images/verification/heat_room_temperature.png)

| Deck | Slice *T* after 60 s | \(t^{*}\) at the deck *T* | \(t^{*}\) at the slice *T* | First update with hand FED ≥ 1 |
|---|---|---|---|---|
| 100 °C | 98.9 – 99.5 °C | 475.5 s | 486.6 s | **487 s** |
| 150 °C | 147.7 – 148.5 °C | 119.8 s | 124.1 s | **125 s** |
| 200 °C | 195.7 – 196.8 °C | 45.0 s | 47.0 s | **48 s** |

"Slice *T*" is the \(T^{3.4}\)-weighted mean of the slice values the agents
saw up to the stop (99.32, 148.43 and 197.48 °C). The hand sum is taken at
each agent's own position and update times. For all 100 agents it first
reaches 1 at the same update, so each deck has a single expected stop time.

The gap to the closed form at the deck value has two parts: FDS runs cooler
(+11.2, +4.3 and +2.0 s), and the dose is checked only every 1 s, so the stop
falls on the next update (+0.4, +0.9 and +1.0 s).

For the probabilistic run at 150 °C, *F*(999 s) = 98.7 % of agents are
expected to have stopped by the end.

## Result

![Heat FED against time for the 100 agents at 150 °C, the hand sum and the closed form; below, each agent's difference from its own hand sum](/images/verification/heat_room_fed.png)

At 150 °C every agent's dose equals its hand sum to 3.1 × 10⁻⁸. The
difference comes from one agent, at one update, standing next to the corner
where the four meshes meet; there the meshes differ by up to 0.040 K
([#239](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/239)).
Summed from the temperature the agent recorded, the dose agrees to
2.5 × 10⁻¹⁴.

![Time to heat FED = 1 against temperature on log axes: the closed form, the hand sum and the simulated stop for the three decks](/images/verification/heat_room_scaling.png)

At all three temperatures the simulated stop (×) falls on the hand sum (○).
The shift from the closed form at the deck value (◆) is FDS running cooler
plus the 1 s update, not the code.

![Fraction of agents incapacitated by heat against time in the probabilistic run at 150 °C, with the expected log-normal curve and its 95 % band](/images/verification/heat_room_incapacitation.png)

| Check | Expected | Simulated |
|---|---|---|
| agent *T* against the slice, off shared nodes, 100 / 150 / 200 °C | ≤ 10⁻¹⁰ K | max 1.4 × 10⁻¹⁴ / 0 / 2.8 × 10⁻¹⁴ K |
| agent *T* against the slice, at shared nodes, 100 / 150 / 200 °C | ≤ 0.028 / 0.040 / 0.055 K | max 1.4 × 10⁻¹⁴ / 1.7 × 10⁻⁴ / 3.8 × 10⁻⁴ K |
| agent FED against the hand sum of its recorded *T*, 100 / 150 / 200 °C | ≤ 9.2 × 10⁻¹³ / 3.6 × 10⁻¹² / 9.3 × 10⁻¹² | max 7.6 × 10⁻¹⁵ / 2.5 × 10⁻¹⁴ / 1.7 × 10⁻¹³ |
| agent FED against the hand sum on the slice, 100 / 150 / 200 °C | ≤ seam bound, row by row | max 7.6 × 10⁻¹⁵ / 3.1 × 10⁻⁸ / 1.4 × 10⁻⁷, all within |
| margin of the hand FED from 1 at the updates around the stop, 100 / 150 / 200 °C | > seam bound up to the stop (≤ 3.7 / 4.5 / 6.1 × 10⁻⁵) | ≥ 5.1 × 10⁻⁴ / 8.2 × 10⁻⁴ / 9.4 × 10⁻⁵ |
| deterministic stop, 100 °C | 487 s | all 100 agents at 487 s |
| deterministic stop, 150 °C | 125 s | all 100 agents at 125 s |
| deterministic stop, 200 °C | 48 s | all 100 agents at 48 s |
| cause of every stop | `heat` | `heat` |
| probabilistic, 150 °C: stopped by 999 s | 98.7 % | 100 of 100 |
| probabilistic, 150 °C: largest gap between the curves | ≤ 0.136 | 0.120 (p = 0.11) |

## Pass criteria

1. **Slice to agent.** The temperature each agent recorded equals the slice
   value at its nearest node and nearest slice time, to float noise
   (10⁻¹⁰ K). The only larger difference allowed is at a node two meshes
   share, where the slice holds two values; there the tolerance is the
   largest such gap in the run (0.028, 0.040 and 0.055 K).
2. **Dose.** Every agent's FED equals the hand sum of Eq. 63.48 over the
   temperatures it recorded to round-off. Both sums add *n* = 1000 positive
   terms, each rounding by at most *n* ε FED, so the tolerance is
   2 *n* ε FED_max with ε = 2.2 × 10⁻¹⁶ (9.2 × 10⁻¹³, 3.6 × 10⁻¹² and
   9.3 × 10⁻¹²). End to end, against the hand sum on the slice, each update
   at a shared node may add 3.4 · Δ*T*_seam / *T* · rate · Δ*t*, since a
   relative error in *T* grows 3.4 times in the rate. The seam bound is this
   term summed over the agent's updates at shared nodes.
3. **Deterministic stop.** Every agent stops at the first update where its
   hand sum reaches 1, with cause `heat`. Updates are 1 s apart
   (`--smoke-update-interval`). The stop is exact, not approximate, as long
   as the hand FED at the updates on either side of the stop is further from
   1 than the seam bound; otherwise the adjacent update would also pass. The
   tightest case is 200 °C: at least 9.4 × 10⁻⁵ from 1, against a seam
   bound of at most 6.1 × 10⁻⁵.
4. **Probabilistic stop.** The fraction of stopped agents stays within the
   95 % Kolmogorov–Smirnov band of *F*(*t*),
   \(1.36/\sqrt{n} = 0.136\) for *n* = 100. This is one draw (seed 42);
   D = 0.120 has p = 0.11, so it passes at the 5 % level, and by
   construction one seed in twenty would fail.

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
    --output-sqlite <data>/fed_incap_heat_${T}c/evac/deterministic/run.sqlite \
    --output-fed-history <data>/fed_incap_heat_${T}c/evac/deterministic/fed_history.csv
done
# and once more for 150 °C with --heat-incapacitation-mode probabilistic,
# into evac/probabilistic/
uv run python scripts/verification/heat_room_figures.py --data <data>
```

Each run takes about three minutes and uses the default seed 42. A
temperature without output is skipped.

The published figures come from runs that also passed
`--constant-extinction 0 --no-visibility`, which ran without a visibility
model. Add those two flags to reproduce them exactly. On the same FDS
output, a paired deterministic 150 °C run with and without the two flags
stops all 100 agents at the same update in both; agent positions differ
slightly, and the maximum heat FED differs by less than 10⁻⁴ (relative).
The paired outputs are in
`<data>/fed_incap_heat_150c/evac/no_soot_fallback_248/`.

## Limits

- **The law is not verified.** The expected values use Eqs. 63.44 and
  63.48, the same formulas as the code. Expected values from SFPE's tables
  are pending
  ([#219](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/219)).
  The Handbook calls Eq. 63.44 somewhat non-conservative at high
  temperatures and over-conservative at low ones; its Table 63.20 gives
  12 min at 100 °C where the equation gives 7.9 min.
- **The room is not at the deck temperature.** FDS settles 0.7, 1.2 and
  1.8 % below the `&INIT` value within the first minute, so the stop times
  are 2 – 7 % later than the closed form at the deck temperature
  ([#253](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/253)). The page checks
  against the slice, so this does not affect the verdict; it matters if
  the deck value is quoted as the exposure.
- **The exposure is not rising.** Eq. 63.48 assumes stable or rising
  temperature. Here the room mean still falls by more than 0.01 K per slice
  step until 18, 36 and 59 s;
  at 200 °C that covers nearly the whole 48 s exposure. The code sums the
  same terms either way, so the check holds; the physiology of a falling
  exposure is outside it.
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
