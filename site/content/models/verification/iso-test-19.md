---
title: "ISO 20414 Test 19: incapacitation by toxic gases"
linkTitle: "ISO Test 19"
weight: 21
math: true
---

| | |
|---|---|
| **Component** | Gas FED and incapacitation ([Models › FED](/models/fed.md)) |
| **Level** | FDS case: a full run on FDS output |
| **Asset** | `assets/iso_table22_coupled` (four cases, a–d) |
| **Expected value from** | hand calculation, and FDS's own `FED` device |
| **Status** | passes |

![Four rooms side by side, one occupant each, coloured by its dose; a cross marks the moment the dose reaches 1](/images/verification/iso_test19.gif)

## What is tested

ISO 20414:2020, Test 19 (Table 22): an occupant stands still in gas, and
the time at which its dose reaches FED = 1 must equal a hand calculation.
The standard asks for the test to be repeated for each hazardous condition
the model has. Four gas mixtures switch the CO, CO₂ and O₂ terms on one at
a time. A wrong unit (ppm against %), a slice read at the wrong height, a
missing species read as zero, a dropped CO₂ factor or a wrong O₂ gate each
moves the crossing in at least one case.

## Equation

The gas FED, as in FDS's `FED` function
([Models › FED](/models/fed.md#coded-form)). *C*<sub>CO</sub> is in ppm,
*C*<sub>CO₂</sub> and *C*<sub>O₂</sub> are in volume percent, and rates are
per minute:

```
r_CO   = 2.764e-5 x (C_CO)^1.036
HV_CO2 = exp(0.1903 x C_CO2 + 2.0004) / 7.1    if C_CO2 > 0
HV_CO2 = 1                                     if C_CO2 = 0
r_O2   = 1 / exp[8.13 - 0.54 x (20.9 - C_O2)]  if C_O2 < 20 %, else 0
r      = r_CO x HV_CO2 + r_O2
```

The gas is constant, so FED grows linearly, FED(*t*) = *r t* / 60, and
reaches 1 at

$$
t^{*} = \frac{60}{r_{\mathrm{CO}}\,\mathrm{HV}_{\mathrm{CO_2}} + r_{\mathrm{O_2}}}\ \text{s}.
$$

## Setup

![Plan of the 10 m by 10 m room: the occupant at the centre, the FDS FED device next to it, and an exit in the corner that is never used](/images/verification/iso_test19_setup.png)

- **FDS:** the ISO room, 10 × 10 × 3 m, no fire, no vents, one mesh with
  0.5 m cells. At *t* = 0 a single `&INIT` fills it with one mixture per
  case. Gas slices at 1.6 m, which FDS places at 1.5 m. A `FED` device sits
  at (5, 5, 1.6) m, as in the guide's own version of this test.
- **Cases** (from Fig. 8 of the FDS+Evac guide; ISO gives no values):

  | case | CO₂ | CO | O₂ | terms switched on |
  |---|---|---|---|---|
  | a | 2 % | 0.1 % | 15 % | CO, CO₂ factor, O₂ |
  | b | 0 | 0 | 12 % | O₂ only |
  | c | 0 | 0.1 % | 21 % | CO only |
  | d | 3.43 % | 0.1 % | 21 % | CO and CO₂ factor |

- **Occupant:** one, near the centre (spawn box 4.4–5.6 m; it lands at
  (4.78, 4.94) m), held in place by a pre-evacuation time
  drawn from [1.2 × 10⁷, 2 × 10⁷] s, the method ISO prescribes (> 10⁷ s).
- **Runs:** one per case, `--incapacitation-mode deterministic`, so the
  occupant is incapacitated at FED = 1, not at a random threshold. The FED
  is updated every 1 s.

## Expected

The concentrations are read from the FDS slices with `fdsreader`,
independently of pyFDS-Evac. Every cell at every slice time holds the same
value, and each species is within 2 × 10⁻⁵ of what the deck prescribes.

| case | CO [ppm] | CO₂ [%] | O₂ [%] | r_CO [/min] | HV_CO₂ | r_O₂ [/min] | *t*\*, hand [s] | FDS `FED` device [s] |
|---|---|---|---|---|---|---|---|---|
| a | 1000.01 | 2.00000 | 15.0003 | 0.035444 | 1.52334 | 0.0071250 | **981.71** | 981.65 |
| b | 0 | 0 | 12.0002 | 0 | 1 | 0.036004 | **1666.49** | 1666.49 |
| c | 1000.01 | 0 | 21.0003 | 0.035444 | 1 | 0 | **1692.82** | 1692.72 |
| d | 1000.01 | 3.43000 | 21.0003 | 0.035444 | 1.99977 | 0 | **846.50** | 846.45 |

![Expected FED rate of each case split into its CO, CO2-factor and O2 parts](/images/verification/iso_test19_terms.png)

FDS's device crosses up to 0.10 s earlier. FDS uses 2.7641667 × 10⁻⁵ for the
CO coefficient, not 2.764 × 10⁻⁵. That speeds the CO term by 6.0 × 10⁻⁵,
which accounts for the whole gap: after correcting for it, FDS and the hand
calculation agree to 2 × 10⁻⁷ of *t*\*.

Before [#194](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/194),
pyFDS-Evac set HV_CO₂ = exp(2.0004)/7.1 = 1.041 at zero CO₂, which gave
1626 s for case c. FDS sets it to 1 when there is no CO₂, and its own device
gives 1692.7 s, as the hand calculation does.

## Result

![FED against time in the four cases: the occupant, the hand calculation and FDS's device lie on one line, and the cross at FED = 1 marks incapacitation](/images/verification/iso_test19_fed.png)

In every case the occupant's FED is on the hand line to within 3 × 10⁻¹⁴,
and it is incapacitated at the first FED update after *t*\*.

![Crossing time minus the hand calculation for each case: pyFDS-Evac within the 1 s band, FDS's device slightly early](/images/verification/iso_test19_crossing.png)

| case | Expected *t*\* | FDS device | Simulated: FED ≥ 1 and stop | Simulated − expected | Pass |
|---|---|---|---|---|---|
| a | 981.71 s | 981.65 s | 982.0 s | +0.29 s | yes |
| b | 1666.49 s | 1666.49 s | 1667.0 s | +0.51 s | yes |
| c | 1692.82 s | 1692.72 s | 1693.0 s | +0.18 s | yes |
| d | 846.50 s | 846.45 s | 847.0 s | +0.50 s | yes |

| Check | Expected | Simulated |
|---|---|---|
| gas at the occupant against the deck | within 10⁻⁴ | within 2.0 × 10⁻⁵; exactly 0 where the deck has none |
| FED rate against the hand calculation | equal | relative difference ≤ 1.1 × 10⁻¹⁵ |
| FED(*t*) against the hand line | equal | max difference 3.1 × 10⁻¹⁴ |
| occupant position | fixed | moved 0 m; not evacuated |

## Pass criteria

1. **Gas arrives unaltered.** Each concentration the occupant sees equals
   the prescribed value to 10⁻⁴ (relative), and is exactly 0 where the deck
   has none. The deck writes mass fractions to 6 significant digits from
   molar masses given to 3 decimals; each rounding is below 2 × 10⁻⁵.
2. **Dose.** |FED − *r t*/60| ≤ 10⁻⁹ at every update: both sides are the
   same arithmetic on the same numbers, so only round-off may differ.
3. **Crossing and stop.** The first update with FED ≥ 1 and the
   incapacitation are the same row, and \(t^{*} \le t < t^{*} + \Delta t\)
   with Δ*t* = 1 s, the FED update interval. The automated test allows
   2 Δ*t*.
4. **FDS agrees with the hand calculation.** After correcting for FDS's CO
   coefficient, |*t*<sub>FDS</sub> − *t*\*| ≤ 10⁻⁶ *t*\*. FDS writes the
   device with 8 significant digits, so interpolating the crossing is good
   to about 10⁻⁷.
5. **The occupant stays put.** Position unchanged and not evacuated:
   otherwise the exposure, and the comparison, would be meaningless.

## Run it yourself

The FDS output (slices only, 256 kB) is committed in
`assets/iso_table22_coupled/fds/`, and `tests/test_iso_table22_coupled.py`
runs on it in CI. For the figures you also need FDS's `_devc.csv`, which is
in the project's data folder (`fds-evac-data/iso_table22_coupled/`), or
rerun FDS, about 40 s per case:

```bash
python assets/iso_table22_coupled/build_geometry.py   # writes decks and configs
for c in a b c d; do
  mkdir -p <out>/fds/$c && cp assets/iso_table22_coupled/iso_table22_$c.fds <out>/fds/$c/
  (cd <out>/fds/$c && fds iso_table22_$c.fds)
done
```

Then run pyFDS-Evac, about 40 s per case, and draw the figures:

```bash
for c in a b c d; do
  uv run python run.py --scenario assets/iso_table22_coupled/config_$c.json \
    --fds-dir <out>/fds/$c --seed 420 --incapacitation-mode deterministic \
    --smoke-update-interval 1 \
    --output-sqlite <out>/evac/$c/run.sqlite \
    --output-fed-history <out>/evac/$c/fed_history.csv \
    --vis-cache <out>/evac/$c/vis_cache.npz
done
uv run python scripts/verification/iso_test19_figures.py --data <out>
```

The script prints each check and stops if a concentration misses the
deck.

## Limits

- CO, CO₂ and O₂ only. The optional gases (HCN, NOx, irritants) and the
  convective heat dose are not run in this layout; the heat dose is checked
  in [Heat dose in a uniform room](/models/verification/testing-heat.md).
- One occupant per case and the deterministic threshold. The probabilistic
  threshold, the default, is checked on 100 agents in
  [CO dose in a uniform room](/models/verification/testing-homogeneous.md).
- A uniform, constant field cannot show whether the gas is sampled at the
  agent's current position
  ([#24](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/24)) or at
  the right height; the height is checked in
  [test_fed_slice_height.py](https://github.com/PedestrianDynamics/pyFDS-Evac/blob/main/tests/verification/test_fed_slice_height.py).
- The automated test takes its expected values from pyFDS-Evac's own FED
  functions and allows 2 s; only the figure script uses the independent
  hand calculation and FDS's device
  ([#249](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/249)).
- The FED equations are the Purser forms FDS uses, not the SFPE 5th edition
  ones ([#149](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/149)).
- A second version of this test, `assets/ISO-table22` in
  `tests/test_fed.py`, supplies the gas directly without FDS. It checks the
  dose accumulator only, for one mixture (CO 0.1 %, CO₂ 5 %, O₂ 12 %).
