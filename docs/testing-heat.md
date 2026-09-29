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
| **Expected value from** | closed form of SFPE Eq. 63.44 (ISO 13571:2012 Eq. (10), `--heat-clothing unclothed`) at the deck temperature; per agent, hand sum of Eq. 63.48 on FDS's own `TEMPERATURE` slice |
| **Status** | passes with `--heat-clothing unclothed`; checks the pipeline, not the law (the law against the Handbook's tables: `test_heat_fed_verif.py`, A3.8–A3.10, A3.12); the default law, ISO Eq. (9), has expected times only |

![100 agents walk a loop in a room at 150 °C; their colour shows the heat dose, and all of them stop at 120 s](/images/verification/heat_room.gif)

## What is tested

Whether the heat dose an agent accumulates in pyFDS-Evac is the dose the
equation gives for the gas temperature FDS computed at that agent, and
whether the agent stops when the dose reaches its threshold. FDS holds the
room at the deck temperature everywhere, so every agent follows one curve,
the closed form. Any difference from the hand calculation comes from the code:
reading the slice, sampling it at the agent, summing the dose, or applying
the threshold. It checks that the code applies SFPE Eqs. 63.44 and 63.48
correctly, not that they predict human tolerance.

The runs use `--heat-clothing unclothed`. The default law is ISO 13571:2012
Eq. (9), for fully clothed subjects
([Models › Heat](/models/heat.md#clothing),
[#290](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/290)). The
two laws share the pipeline this page checks and differ only in their
constants. Under Eq. (9) the 100 °C room would reach FED = 1 at 1482 s,
after the end of the 1000 s FDS record, so that deck could not check the
default without a longer FDS run; the page therefore stays on Eq. (10) and
lists the Eq. (9) times as expected values only.

## Equation

SFPE Handbook 5th ed., Ch. 63 ([Models › Heat](/models/heat.md)). The time
to incapacitation by convected heat, with *T* the gas temperature in °C
(Eq. 63.44, p. 2382):

$$
t_{I,\mathrm{conv}} = 5\times10^{7}\,T^{-3.4}\ \text{min}.
$$

The Handbook states it for exposures of up to 2 h in air with less than
10 % water vapour by volume. ISO 13571:2012 gives the same expression as
its Eq. (10) (§8.3.2), for unclothed or lightly clothed subjects, cited to
Purser's chapter in the 4th edition of the Handbook, with an estimated
uncertainty of ±25 %
([Fundamentals › Heat](/fundamentals/heat.md#iso-135712012-clause-8)). The dose is summed over the exposure
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
  or 200 °C, and the ambient temperature `TMPA` is set to the same value, so
  the walls and the radiation field start at the gas temperature.
  `TEMPERATURE` slices at 1.5 m, the one nearest the 1.6 m sampling height
  on this 0.5 m grid.
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

FDS holds the room at the deck value. Over the whole 1000 s, every node of
the 1.5 m slice stays within 0.65 mK of it, and every `TEMPERATURE` device
within 0.52 mK (`assets/fed_incap_heat_<T>c/fds/*_devc.csv`). A 1 mK error
moves the dose by at most 3.4 × 10⁻⁵, far below the margins in the Result
table. So the expected stop is the closed form at the deck temperature,
rounded up to the next 1 s dose update. Per agent, the expected dose is
also the sum of Eq. 63.48 over the temperature FDS wrote at the agent's
position, read from the slice with fdsreader, independent of pyFDS-Evac.

![Room temperature at 1.5 m against time for the three decks, as the difference from the deck value in mK](/images/verification/heat_room_temperature.png)

| Deck | \(t^{*}\) at the deck *T* | First update with FED ≥ 1 | \(t^{*}\) under ISO Eq. (9), the default (not run) |
|---|---|---|---|
| 100 °C | 475.5 s | **476 s** | 1482.3 s, after the 1000 s record |
| 150 °C | 119.8 s | **120 s** | 343.0 s |
| 200 °C | 45.0 s | **46 s** | 121.4 s |

The last column is \(60 \times 4.1\times10^{8}/T^{3.61}\) s.

The hand sum on the slice, taken at each agent's own position and update
times, first reaches 1 at the same update for all 100 agents. The gap to
the closed form (+0.5, +0.2 and +1.0 s) is the 1 s update interval: the
stop falls on the next update.

For the probabilistic run at 150 °C, *F*(999 s) = 98.8 % of agents are
expected to have stopped by the end.

## Result

![Heat FED against time for the 100 agents at 150 °C, the hand sum and the closed form; below, each agent's difference from its own hand sum](/images/verification/heat_room_fed.png)

At 150 °C every agent's dose equals its hand sum on the slice to
8.7 × 10⁻⁹. The difference comes from updates where an agent stands at a
node two meshes share; there the meshes differ by up to 9.2 × 10⁻⁵ K
([#239](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/239)).
Summed from the temperature the agent recorded, the dose agrees to
2.2 × 10⁻¹³.

![Time to heat FED = 1 against temperature on log axes: the closed form, the hand sum and the simulated stop for the three decks](/images/verification/heat_room_scaling.png)

At all three temperatures the simulated stop (×) falls on the hand sum (○)
and on the closed form at the deck value (◆), up to the 1 s update.

![Fraction of agents incapacitated by heat against time in the probabilistic run at 150 °C, with the expected log-normal curve and its 95 % band](/images/verification/heat_room_incapacitation.png)

| Check | Expected | Simulated |
|---|---|---|
| agent *T* against the slice, off shared nodes, 100 / 150 / 200 °C | ≤ 10⁻¹⁰ K | max 1.4 × 10⁻¹⁴ / 0 / 2.8 × 10⁻¹⁴ K |
| agent *T* against the slice, at shared nodes, 100 / 150 / 200 °C | ≤ 1.3 × 10⁻⁴ / 9.2 × 10⁻⁵ / 7.6 × 10⁻⁵ K | max 5.3 × 10⁻⁵ / 4.6 × 10⁻⁵ / 3.1 × 10⁻⁵ K |
| agent FED against the hand sum of its recorded *T*, 100 / 150 / 200 °C | ≤ 9.3 × 10⁻¹³ / 3.7 × 10⁻¹² / 9.9 × 10⁻¹² | max 4.4 × 10⁻¹⁴ / 2.2 × 10⁻¹³ / 5.9 × 10⁻¹³ |
| agent FED against the hand sum on the slice, 100 / 150 / 200 °C | ≤ seam bound, row by row | max 3.8 × 10⁻⁹ / 8.7 × 10⁻⁹ / 1.2 × 10⁻⁸, all within |
| margin of the hand FED from 1 at the updates around the stop, 100 / 150 / 200 °C | > seam bound up to the stop (≤ 1.8 / 1.0 / 0.86 × 10⁻⁷) | ≥ 9.8 × 10⁻⁴ / 1.8 × 10⁻³ / 9.4 × 10⁻⁴ |
| deterministic stop, 100 °C | 476 s | all 100 agents at 476 s |
| deterministic stop, 150 °C | 120 s | all 100 agents at 120 s |
| deterministic stop, 200 °C | 46 s | all 100 agents at 46 s |
| cause of every stop | `heat` | `heat` |
| probabilistic, 150 °C: stopped by 999 s | 98.8 % | 100 of 100 |
| probabilistic, 150 °C: largest gap between the curves | ≤ 0.136 | 0.122 (p = 0.10) |

## Pass criteria

1. **Slice to agent.** The temperature each agent recorded equals the slice
   value at its nearest node and nearest slice time, to float noise
   (10⁻¹⁰ K). The only larger difference allowed is at a node two meshes
   share, where the slice holds two values; there the tolerance is the
   largest such gap in the run (1.3 × 10⁻⁴, 9.2 × 10⁻⁵ and
   7.6 × 10⁻⁵ K).
2. **Dose.** Every agent's FED equals the hand sum of Eq. 63.48 over the
   temperatures it recorded to round-off. Both sums add *n* = 1000 positive
   terms, each rounding by at most *n* ε FED, so the tolerance is
   2 *n* ε FED_max with ε = 2.2 × 10⁻¹⁶ (9.3 × 10⁻¹³, 3.7 × 10⁻¹² and
   9.9 × 10⁻¹²). End to end, against the hand sum on the slice, each update
   at a shared node may add 3.4 · Δ*T*_seam / *T* · rate · Δ*t*, since a
   relative error in *T* grows 3.4 times in the rate. The seam bound is this
   term summed over the agent's updates at shared nodes.
3. **Deterministic stop.** Every agent stops at the first update where its
   hand sum reaches 1, with cause `heat`. Updates are 1 s apart
   (`--smoke-update-interval`). The stop is exact, not approximate, as long
   as the hand FED at the updates on either side of the stop is further from
   1 than the seam bound; otherwise the adjacent update would also pass. The
   tightest case is 200 °C: at least 9.4 × 10⁻⁴ from 1, against a seam
   bound of at most 8.6 × 10⁻⁸. The stop also equals the first update at
   or after the closed-form \(t^{*}\) at the deck temperature.
4. **Probabilistic stop.** The fraction of stopped agents stays within the
   95 % Kolmogorov–Smirnov band of *F*(*t*),
   \(1.36/\sqrt{n} = 0.136\) for *n* = 100. This is one draw (seed 42);
   D = 0.122 has p = 0.10, so it passes at the 5 % level, and by
   construction one seed in twenty would fail.

## Run it yourself

The FDS slices are not in the repository (65 MB per deck); only FDS's
device output `*_devc.csv` is, under `assets/fed_incap_heat_<T>c/fds/`.
Either get the slices from the project's data folder
(`fds-evac-data/fed_incap_heat_<T>c/fds/`),
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
    --enable-heat-fed --heat-clothing unclothed \
    --heat-incapacitation-mode deterministic \
    --output-sqlite <data>/fed_incap_heat_${T}c/evac/deterministic/run.sqlite \
    --output-fed-history <data>/fed_incap_heat_${T}c/evac/deterministic/fed_history.csv
done
# and once more for 150 °C with --heat-incapacitation-mode probabilistic,
# into evac/probabilistic/
uv run python scripts/verification/heat_room_figures.py --data <data>
```

Each run takes about three minutes and uses the default seed 42. A
temperature without output is skipped. The published runs were made when
Eq. 63.44 was the default law, before `--heat-clothing` existed;
`--heat-clothing unclothed` selects the same law, and
`tests/verification/test_heat_endpoint_coupled.py` checks, in a synthetic
corridor, that it reproduces the FED history of that code.

The published figures come from runs that also passed
`--constant-extinction 0 --no-visibility`, which ran without a visibility
model. Add those two flags to reproduce them exactly. On the same FDS
output, a paired deterministic 150 °C run with and without the two flags
stops all 100 agents at the same update in both; agent positions differ
slightly, and the maximum heat FED differs by less than 10⁻⁴ (relative).
The paired outputs are in
`<data>/fed_incap_heat_150c/evac/no_soot_fallback_248/`.

## Limits

- **The law is not verified here.** The expected values use Eqs. 63.44 and
  63.48, the same formulas as the code. The law itself is compared with the
  Handbook's tables in `tests/verification/test_heat_fed_verif.py`
  ([#219](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/219)):
  Eq. 63.44 gives 0.61 to 1.07 times the times of Table 63.20's convective
  rows (p. 2383), shorter at 100–140 °C (7.9 min against 12 min at 100 °C),
  as the Handbook says it is "somewhat overconservative at the
  low-temperature end" (p. 2382); and it never exceeds the dry-air
  tolerance times of Table 63.17 (p. 2375).
- **σ = 0.94 has no source for heat.** It is borrowed from the gas dose
  ([#225](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/225)). The
  probabilistic run checks the code path, not the spread.
- **Convective heat only.** This room checks the convective laws; it does
  not run `--heat-fed-method total-flux`. That method is checked against
  hand formulas of Eqs. 63.49 and 63.43 on synthetic fields
  (`tests/test_heat_total_flux.py`,
  `tests/verification/test_heat_total_flux_coupled.py`). Its
  `--heat-regime layer` is checked the same way, against hand formulas and
  the 200 °C / 2.5 kW/m² anchor of p. 2382
  (`tests/test_heat_layer_flux.py`,
  `tests/verification/test_heat_layer_flux_coupled.py`); it has no FDS case
  yet ([#224](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/224)).
  The `INTEGRATED INTENSITY` source is checked in
  `tests/test_heat_integrated_intensity.py` and
  `tests/verification/test_heat_integrated_intensity_coupled.py`
  ([#221](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/221)).
  Below the threshold heat changes neither speed nor route
  ([#81](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/81)).
- A near-uniform field cannot show whether the field is sampled at the
  agent's *current* position; that needs a gradient
  ([#24](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/24)).
- The agent checks are not an automated test: they run from the figure
  script on the stored output. In CI,
  `tests/verification/test_heat_room_decks.py` checks the decks (adiabatic
  faces, `TMPA` equal to the `&INIT` temperature), that FDS's committed
  device output holds the deck value to 0.01 K, and the stop times in the
  table above. The equation-level tests
  (`tests/verification/test_s6_heat_fed.py`, `test_heat_fed_verif.py`) run
  on synthetic fields in CI. `test_heat_flame_pass_reference.py` and the
  radiant checks in `test_heat_fed_verif.py` (A3.11) call no pyFDS-Evac
  code: they are Handbook reference values kept apart from the total-flux
  method, which has its own tests (`tests/test_heat_total_flux.py`,
  [#223](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/223)).
- The reference tests rest on choices that are not Handbook tolerances.
  Flame pass: the flame is a black-body sphere of radius 0.1 m, the skin
  faces it at 35 °C, there is no convective term, and one pass must stay
  below FED 0.02. Hot-layer anchor: a black-body layer with a full view,
  surface at 20 or 35 °C, within ±10 % of the Handbook's "approximately
  2.5 kW/m²". Table 63.20 radiant rows: within ±30 %, the band chosen in
  [#219](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/219).
  D = 16.7 as printed on pp. 2382 and 2384 of Ch. 63.
