---
title: "ISO 20414 Test 18: walking speed in smoke"
linkTitle: "ISO Test 18"
weight: 18
math: true
aliases: [/models/verification/iso-test-18/]
---

| | |
|---|---|
| **Component** | Smoke-speed law ([Models › Smoke-speed](/models/smoke-speed.md)) |
| **Level** | Runner with *K* injected (no FDS); FDS case with *K* read from committed FDS output |
| **Asset** | `assets/ISO-table21`, `assets/iso_table21_coupled` |
| **Expected value from** | hand calculation of the model's law, as ISO 20414 asks; for the FDS case, *K* from FDS's own slice, cross-checked against the deck's soot; egress times predicted from clear runs of the same layout (no smoke) |
| **Status** | Frantzich–Nilsson law: passes on the stored runs (figure script); CI checks the time ratio within 8 %. Both laws on the standard's grid: CI checks the speed on all 16 cells and the egress time on 10 corridor runs |

![Five copies of the ISO corridor, tinted darker the denser the smoke: clear air and K = 1, 3, 7.5 and 10 per metre; the occupant's colour shows its walking speed, and each corridor ends with the simulated and the expected egress time](/images/verification/iso18.gif)

{{< example-files-link "iso-test-18" >}}

## What is tested

Whether smoke slows an occupant by exactly the factor the smoke-speed law
gives, and whether that slower speed really changes the egress time. A factor
that is computed but never applied, applied to the wrong speed, or applied
twice, changes the egress time. In the FDS case, a wrong slice, quantity,
height or position lookup changes the *K* the occupant sees.

## Equation

Frantzich and Nilsson fitted \(v = \alpha + \beta K\) to 32 walks in a lit
smoke tunnel (Lund report 3126, Eq. 3, App. D, Table D2, model 1), with
α = 0.706 m/s and β = −0.057 m²/s (standard errors 0.069 and 0.015); see
[Fundamentals › Walking speed](/fundamentals/walking-speed.md#frantzich-and-nilsson-a-linear-regression-in-dense-smoke).
[FDS+Evac](https://github.com/firemodels/fds/tree/c9da70d7a/Source) divides
by α to make it a factor of the unimpeded speed and adds a floor of 0.1.
That is the default law (`lund`) of pyFDS-Evac
([Models › Smoke-speed](/models/smoke-speed.md#coded-form)). It turns the
extinction coefficient *K* [1/m] into a speed factor *f* [-]:

$$
f(K) = \min\!\left(1,\ \max\!\left(0.1,\ 1 + \frac{\beta}{\alpha}K\right)\right),
\qquad \frac{\beta}{\alpha} = -0.0807~\mathrm{m} .
$$

The walking speed is \(v = f(K)\,v_0\), with \(v_0\) [m/s] the unimpeded
speed. In a corridor where *K* is the same everywhere, the occupant walks the
same distance at \(f v_0\) instead of \(v_0\), so ISO 20414's expected result is

$$
\frac{t_{\mathrm{smoke}}}{t_{\mathrm{clear}}} = \frac{1}{f(K)} .
$$

Here the **egress time** *t* is the simulated time at which the occupant is
removed at the exit (`run.log`, "Simulation finished in").

For the FDS case the deck prescribes a soot mass fraction \(Y_s\), and FDS
computes \(K = K_m\,\rho\,Y_s\) with the mass extinction coefficient
\(K_m = 8700\) m²/kg and the gas density ρ [kg/m³].

## Setup

![Plan of the ISO corridor: the full 100 m length with the start and removal points of the occupant, then both ends at true scale](/images/verification/iso18_setup.png)

- **Corridor:** ISO 20414 Table 21, 100 × 2 m, with an exit zone of
  1 × 0.92 m at the far end. One occupant, \(v_0\) = 1.25 m/s, seed 420, so
  it starts at the same point in the clear and the smoky run. It starts at
  *x* = −49.53 m and is removed at *x* ≈ 49.0 m, once its centre comes
  within 0.03 m of the exit zone
  ([`direct_steering_runtime.py`](https://github.com/PedestrianDynamics/pyFDS-Evac/blob/main/pyfds_evac/core/direct_steering_runtime.py)).
  So it walks about 98.5 m, not 100 m. The seed fixes the target point it
  heads for, so the path is the same in the clear and the smoky run. ISO's absolute time depends on that distance, so the page predicts
  each smoky time from clear runs of the same layout. ISO leaves the
  quantitative method to the tester.
- **Constant *K*** (`assets/ISO-table21`, social force model): *K* = 0.5, 1,
  3, 7.5 and 10 1/m, as in ISO's Table 21, and at *K* = 1 also
  \(v_0\) = 1.0, 0.75, 0.5 and 0.25 m/s. Each smoky run has its own clear run.
- **FDS** (`assets/iso_table21_coupled`, collision-free speed model): the
  corridor filled with soot at \(Y_s = 9.546\times10^{-5}\), no fire, one mesh
  with 0.5 m cells. Slices of *K* at 2.0 m and at 1.6 m, which FDS writes at
  1.5 m. The occupant reads the 1.5 m slice, nearest the default sampling
  height of 1.6 m.
- **Runs:** `run.py` with a smoke update every 0.1 s and a time step of
  0.01 s. Rerouting is off; irritant slowing (FIC) and incapacitation are off
  (`--disable-tenability`), as ISO asks: visibility only. 16 runs in all.

## Expected

| Quantity | Value | From |
|---|---|---|
| *f*(0.5), *f*(1), *f*(3), *f*(7.5), *f*(10) | 0.95963, 0.91926, 0.75779, 0.39448, 0.19263 | the law above, by hand |
| 1/*f* for the same *K* | 1.0421, 1.0878, 1.3196, 2.5350, 5.1912 | by hand |
| *K* where the floor *f* = 0.1 starts | 11.15 1/m | by hand; no run reaches it |
| clear runs: \(t = L/v_0 + a\) | *L* = 98.321 m, *a* = 0.592 s, largest residual 0.016 s | fit to the five clear runs, \(v_0\) = 1.25 to 0.25 m/s |
| expected smoky egress time, social force | \(t_{\mathrm{pred}} = L/(f v_0) + a\) | the clear fit and *f* by hand |
| ρ of the deck's air at 20 °C | 1.19889 kg/m³ | ideal gas, N₂ + 23.1 % O₂ by mass + soot, 28.84 g/mol |
| *K* the deck prescribes | 0.99567 1/m | \(8700 \times 1.19889 \times 9.546\times10^{-5}\) |
| *K* in the FDS slice at 1.5 m | 0.9954990 to 0.9955111 1/m, mean 0.99550 | read with `fdsreader`, all cells, all times |
| *K* in the FDS slice at 2.0 m | 0.9954427 to 0.9954541 1/m | read with `fdsreader`; the slice the occupant must *not* read |
| *f* and 1/*f* for the FDS case | 0.91963, 1.08740 | by hand, from the 1.5 m slice |
| expected smoky egress time, FDS case | \(t_{\mathrm{pred}} = t_{\mathrm{clear}}/f\) | the collision-free model has no inertia (*a* = 0) |

A smoky run at *K* and \(v_0\) is a clear run at desired speed \(f v_0\):
the law only scales the desired speed. So the clear runs of the \(v_0\)
sweep give the expected smoky time, start-up included.

Our inference for the slices: FDS's density falls with height by
\(\rho g z / p\). That predicts 1.74 × 10⁻⁴ below the deck's value at 1.5 m
and 2.32 × 10⁻⁴ at 2.0 m; the slices lie 1.70 × 10⁻⁴ and 2.27 × 10⁻⁴ below.
The deck aimed at *K* = 1.0 1/m with 1.2041 kg/m³, the density of dry air
(28.96 g/mol). Its background has no argon, so its molar mass and density are
0.43 % lower. That, plus the hydrostatic drop, and not a coupling error, is
the gap to 0.9955.

## Result

![The speed-factor law against K, solid over the tunnel data and dashed outside, with the factor each run recorded and the speed the occupant actually walked](/images/verification/iso18_speed_factor.png)

Every run records the factor of the law, and the occupant walks at that
speed. Over the middle 40 m of the corridor, the speed along its path matches
\(f v_0\) to 9.8 × 10⁻⁶.

![Left: simulated egress-time ratio against 1/f(K). Right: each smoky egress time minus the expected time, with its tolerance](/images/verification/iso18_ratio.png)

| Run | *K* [1/m] | \(v_0\) [m/s] | \(t_{\mathrm{clear}}\) [s] | \(t_{\mathrm{smoke}}\) [s] | \(t_{\mathrm{pred}}\) [s] | difference [s] | tolerance [s] | expected 1/*f* | simulated ratio |
|---|---|---|---|---|---|---|---|---|---|
| constant *K* | 0.5 | 1.25 | 79.24 | 82.55 | 82.558 | −0.008 | 0.036 | 1.04207 | 1.04177 |
| constant *K* | 1 | 1.25 | 79.24 | 86.15 | 86.157 | −0.007 | 0.036 | 1.08783 | 1.08720 |
| constant *K* | 3 | 1.25 | 79.24 | 104.39 | 104.390 | +0.000 | 0.036 | 1.31963 | 1.31739 |
| constant *K* | 7.5 | 1.25 | 79.24 | 200.01 | 199.988 | +0.022 | 0.036 | 2.53501 | 2.52410 |
| constant *K* | 10 | 1.25 | 79.24 | 408.91 | 408.913 | −0.004 | 0.036 | 5.19118 | 5.16040 |
| constant *K* | 1 | 1.0 | 98.91 | 107.55 | 107.549 | +0.001 | 0.036 | 1.08783 | 1.08735 |
| constant *K* | 1 | 0.75 | 131.69 | 143.21 | 143.201 | +0.009 | 0.036 | 1.08783 | 1.08748 |
| constant *K* | 1 | 0.5 | 197.25 | 214.52 | 214.505 | +0.015 | 0.036 | 1.08783 | 1.08755 |
| constant *K* | 1 | 0.25 | 393.87 | 428.41 | 428.417 | −0.007 | 0.036 | 1.08783 | 1.08769 |
| *K* from FDS | 0.99550 | 1.25 | 78.44 | 85.30 | 85.296 | +0.005 | 0.021 | 1.08740 | 1.08746 |

| Check | Expected | Simulated |
|---|---|---|
| recorded factor, constant *K* | *f*(*K*) by hand | equal to 1.1 × 10⁻¹⁶ |
| recorded *K*, FDS | inside the 1.5 m slice, outside the 2.0 m slice | 0.9955019 to 0.9955078: inside, outside |
| recorded factor, FDS | inside *f* of the 1.5 m slice's range | inside |
| walked speed / \(f v_0\) | 1 | 1 − 9.8 × 10⁻⁶ at worst |
| egress time | \(t_{\mathrm{pred}}\) within the tolerance | all 10 inside, largest +0.022 s on 200 s |

The simulated ratio is always a little below 1/*f*, by up to 0.59 % at
*K* = 10. That is the start-up time *a*: it does not scale with 1/*f*, so
\(t_{\mathrm{smoke}}/t_{\mathrm{clear}} \cdot f - 1 = -a(1-f)/t_{\mathrm{clear}}\),
which predicts −0.60 % at *K* = 10. Once *a* is taken from the clear runs, each egress time
matches to 22 ms. The collision-free model in the FDS case has no start-up
and matches the ratio to 6 × 10⁻⁵.

## Both laws on the standard's grid

Table 21 asks for the correlation the model uses, repeated over a range of
unimpeded speeds and extinction coefficients, with 1.0, 0.75, 0.5 and
0.25 m/s and *K* = 10, 7.5, 3.0 and 0.5 1/m as examples. pyFDS-Evac ships
two laws, and Ronchi et al. (2013) showed that results depend on which
smoke–speed data a model uses, so both are checked
([#841](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/841)).

### The Fridolf law

`speed_law="fridolf"` (Python only) uses Fridolf, Ronchi, Nilsson and
Frantzich (2019, Eq. 7; [Fundamentals › Walking speed](/fundamentals/walking-speed.md#fridolf-et-al-2019-speed-as-a-function-of-visibility)),
with \(w\) [m/s] the walking speed, \(w_{\mathrm{free}}\) the unimpeded speed
and *x* [m] the visibility:

$$
w = \min\!\bigl(w_{\mathrm{free}},\ \max\!\bigl(0.2,\ w_{\mathrm{free}} - 0.34\,(3 - x)\bigr)\bigr),
\qquad x = \frac{A}{K},
\qquad f = \frac{w}{w_{\mathrm{free}}} .
$$

The reduction is additive: 0.34 m/s per metre of visibility below 3 m, the
same for everyone. The floor is an absolute 0.2 m/s, not a fraction of
\(w_{\mathrm{free}}\); it never lifts a walker above \(w_{\mathrm{free}}\),
so a 0.25 m/s walker in dense smoke has \(f = 0.2/0.25 = 0.8\). Unlike the
Lund factor, this factor depends on \(w_{\mathrm{free}}\).

**The visibility constant.** *K* is turned into a visibility by Jin's
relation \(x = A/K\), the paper's Eq. 1 (Fridolf et al. 2019).
pyFDS-Evac uses \(A = 2\), the paper's value for light-reflecting items:
the walls, obstacles and surroundings a walker must see
(`SmokeSpeedConfig.visibility_factor_c`, which holds the paper's *A*). The
paper uses \(A = 8\) for light-emitting items; set
`visibility_factor_c = 8` for those. The 2018 extended abstract gives no
constant. Before, the FDS convention \(C = 3\) was the default, which is
not the paper's: the knee \(x = 3\) m was at \(K = 1\) 1/m, against 0.67 for
\(A = 2\) and 2.67 for \(A = 8\), so agents slowed later and less than the
calibration. The grid's smallest *K*, 0.5 1/m, gives \(x = 4\) m and so no
slowing at all under this law. The tests also check \(C = 3\) and
\(A = 8\) as configured values.

### Hand calculation

\(w\) with \(A = 2\), by hand from the equation above (\(x\) = 0.2, 0.2667,
0.6667 and 4 m for *K* = 10, 7.5, 3 and 0.5 1/m; the drop is 0.952, 0.9293,
0.7933 and 0 m/s). "floor" means the unfloored value is below 0.2 m/s. The Lund
column is \(f(K) = 1 - 0.0807\,K\), the same for every
\(w_{\mathrm{free}}\).

| *K* [1/m] | Lund *f* | \(w_{\mathrm{free}}\) = 1.25 | 1.0 | 0.75 | 0.5 | 0.25 |
|---|---|---|---|---|---|---|
| 10 | 0.192635 | 0.298 | 0.2 (floor) | 0.2 (floor) | 0.2 (floor) | 0.2 (floor) |
| 7.5 | 0.394476 | 0.3207 | 0.2 (floor) | 0.2 (floor) | 0.2 (floor) | 0.2 (floor) |
| 3 | 0.757790 | 0.4567 | 0.2067 | 0.2 (floor) | 0.2 (floor) | 0.2 (floor) |
| 0.5 | 0.959632 | 1.25 | 1.0 | 0.75 | 0.5 | 0.25 |

The Lund floor is not reached in the grid: \(f = 0.1\) starts at
\(K = 0.9 \times 0.706 / 0.057 = 11.147\) 1/m, which the tests check
separately at 11, 11.147, 12 and 100 1/m. In the Fridolf law the floor
decides 11 of the 16 grid cells, 4 are unaffected (*K* = 0.5) and only one
(\(w_{\mathrm{free}}\) = 1.0, *K* = 3) is on the slope, 0.0067 m/s above the
floor. The 1.25 m/s column is added because it is the corridor's own
unimpeded speed and the only one where the slope shows at *K* = 7.5 and 10.
For \(w_{\mathrm{free}}\) = 1.0 the unfloored values are 0.0707 and
0.048 m/s there.

### What CI runs

`tests/test_iso_test_18_speed_laws.py`, marker `iso20414`, about 25 s:

- **All 16 grid cells, both laws**, on the model's speed factor and speed.
  The expected values are the hand-written ones above, not the code's own
  function ([#259](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/259)).
  It also checks the 1.25 m/s column, the floor edges of both laws, the knee
  at \(x = 3\) m, and \(C = 3\) and \(A = 8\).
- **Ten corridor runs** (100 × 2 m, 1 m exit, one occupant, social force
  model, seed 420, constant *K*, update every 0.1 s). The expected egress
  time is the clear time of the same occupant plus
  \(L\,(1/w - 1/w_{\mathrm{free}})\), with \(w\) by hand and
  \(L\) = 98.321 m, the walked length fitted on this page. Each run also
  checks the recorded *K*, the base speed, the desired speed and the factor
  at every update.

| Law | \(w_{\mathrm{free}}\) | *K* | \(w\) by hand [m/s] | Expected [s] | Simulated [s] | Difference [s] | Tolerance [s] | What the cell tests |
|---|---|---|---|---|---|---|---|---|
| Fridolf | 1.25 | 3 | 0.4567 | 215.885 | 215.91 | +0.025 | 0.050 | slope |
| Fridolf | 1.25 | 7.5 | 0.3207 | 307.198 | 307.22 | +0.022 | 0.059 | slope |
| Fridolf | 1.25 | 10 | 0.298 | 330.519 | 330.54 | +0.021 | 0.062 | slope |
| Fridolf | 1.0 | 3 | 0.2067 | 476.336 | 476.32 | −0.016 | 0.074 | slope, just above the floor |
| Fridolf | 1.0 | 7.5 | 0.2 | 492.194 | 492.17 | −0.024 | 0.076 | floor |
| Fridolf | 0.5 | 3 | 0.2 | 492.213 | 492.17 | −0.043 | 0.066 | floor is absolute, not fractional |
| Fridolf | 0.25 | 7.5 | 0.2 | 492.191 | 492.17 | −0.021 | 0.046 | floor against \(w_{\mathrm{free}}\), *f* = 0.8 |
| Fridolf | 0.75 | 0.5 | 0.75 | 131.690 | 131.69 | 0.000 | 0.036 | no slowing above 3 m |
| Lund | 1.0 | 7.5 | 0.394476 | 249.834 | 249.86 | +0.026 | 0.051 | the other law in the same layout |
| Lund | 0.5 | 3 | 0.378895 | 260.102 | 260.11 | +0.008 | 0.042 | the other law in the same layout |

The three floored Fridolf runs at \(w_{\mathrm{free}}\) = 1.0, 0.5 and
0.25 m/s all reach the exit at 492.17 s: the floor is an absolute speed. The
tolerance is 2 time steps of 0.01 s (the clear and the smoky time are each a
whole number of steps), the clear-run fit's largest residual of 0.016 s, and
an assumed 0.01 m error in \(L\) times \(|1/w - 1/w_{\mathrm{free}}|\). The
clear times are from runs of the same layout: 79.24, 98.91, 131.69, 197.25
and 393.87 s for 1.25 to 0.25 m/s.

The other grid cells are checked on the speed only. The Lund law's *K* sweep
at 1.25 m/s and its \(w_{\mathrm{free}}\) sweep at *K* = 1 are the runs
earlier on this page. Lund at 0.25 m/s and *K* = 10 (0.048 m/s, about
2000 s) is not run in a corridor.

## Pass criteria

1. **Factor.** The recorded factor equals *f*(*K*) by hand to round-off,
   ≤ 10⁻¹². For the FDS case, the recorded *K* lies within the 1.5 m slice's
   range and outside the 2.0 m slice's range, and the factor within *f* of
   the 1.5 m range. The two ranges are 4.5 × 10⁻⁵ apart, almost four times
   the spread within one.
2. **Speed.** The speed along the path over the middle 40 m equals
   \(f v_0\) within 10⁻⁵. This tolerance is a margin, not derived. The
   collision-free model walks exactly at \(f v_0\); the social force model
   walks 2.2 to 9.8 × 10⁻⁶ slower, a property of the movement model. The
   smallest error the check must catch, a factor not applied at *K* = 0.5,
   is 1 − *f* = 4 %, four orders of magnitude larger.
3. **Egress time.** Each egress time is a whole number of time steps
   Δ*t* = 0.01 s. For the social force runs,
   \(|t_{\mathrm{smoke}} - t_{\mathrm{pred}}| \le r_{\max} + 2\,\Delta t\) =
   0.036 s. The clear fit's largest residual \(r_{\max}\) = 0.016 s covers
   the fit's misfit; one Δ*t* is the rounding of the smoky time, one the
   rounding in the fitted line. For the FDS case,
   \(|t_{\mathrm{smoke}} - t_{\mathrm{clear}}/f| \le (1 + 1/f)\,\Delta t\) =
   0.021 s: the clear time's rounding, scaled by 1/*f*, plus the smoky
   time's. The expected time uses no smoky run. Two runs lie just outside
   the clear runs' speed range (0.25 to 1.25 m/s): *K* = 10 at 1.25 m/s
   (\(f v_0\) = 0.241 m/s) and *K* = 1 at 0.25 m/s (0.230 m/s). Their
   predictions are small extrapolations; both pass.

The pytest tests ask for less: the ratio within 8 %, and the factor equal to
six decimals ([#259](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/259)).

## Run it yourself

{{< example-files "iso-test-18" >}}

The tests of the first two cases run in about 20 s. They are weaker than this page: the
coupled test reads the 2.0 m slice, not the 1.5 m slice the default height
picks; both compute the expected factor with the code's own function; and the
time ratio passes within 8 %
([#259](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/259)):

```bash
uv run pytest tests/test_smoke_speed.py -k iso_table21 tests/test_iso_table21_coupled.py tests/test_iso_test_18_speed_laws.py
```

For the figures, run the 16 cases with `run.py`. The FDS output is committed
in `assets/iso_table21_coupled/fds/`; to rebuild it, run
`uv run python assets/iso_table21_coupled/build_geometry.py` and then
`fds iso_table21_coupled.fds` (about 10 s). `assets/ISO-table21` stops at
300 s, too early for *K* = 10 and for \(v_0\) = 0.25 m/s, so the constant-*K*
runs use a copy with 600 s:

```bash
OUT=<out>
run() {  # name scenario [extra options]
  name=$1 scen=$2; shift 2
  mkdir -p $OUT/evac/$name
  uv run python run.py --scenario $scen --seed 420 --smoke-update-interval 0.1 \
    --no-enable-rerouting --disable-tenability "$@" \
    --output-sqlite $OUT/evac/$name/run.sqlite \
    --output-smoke-history $OUT/evac/$name/smoke_history.csv > $OUT/evac/$name/run.log
}
for v in 1.25 1 0.75 0.5 0.25; do
  d=$OUT/scenarios/v0_$v; mkdir -p $d; cp assets/ISO-table21/geometry.wkt $d/
  uv run python -c "import json,sys; c=json.load(open('assets/ISO-table21/config.json')); \
c['config']['simulation_settings']['simulationParams']['max_simulation_time']=600; \
[d['parameters'].update(v0=float(sys.argv[1])) for d in c['distributions'].values()]; \
json.dump(c, open(sys.argv[2]+'/config.json','w'), indent=2)" $v $d
done
run clear $OUT/scenarios/v0_1.25
for K in 0.5 1 3 7.5 10; do run K$K $OUT/scenarios/v0_1.25 --constant-extinction $K; done
for v in 1 0.75 0.5 0.25; do
  run v0_${v}_clear $OUT/scenarios/v0_$v
  run v0_${v}_K1 $OUT/scenarios/v0_$v --constant-extinction 1
done
cp -R assets/iso_table21_coupled/fds $OUT/fds
run coupled_clear assets/iso_table21_coupled/config.json
run coupled_fds assets/iso_table21_coupled/config.json --fds-dir $OUT/fds
uv run python scripts/verification/iso_test_18_figures.py --data $OUT
```

The script prints the table above, writes the figures, and exits with an
error if a pass criterion fails. The runs behind
this page, made on the branch of
[#401](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/401) at
`8fc26b1` with a clean tree, give this table. The same commands on main
at `9c820e0f` (Python 3.12.13) print the same table and figures.

## Limits

- The Fridolf law is run in the same corridor (see above) with constant *K*
  only, not *K* from FDS. The
  [S2 corridor test](https://github.com/PedestrianDynamics/pyFDS-Evac/blob/main/tests/verification/test_s2_corridor_speed.py)
  also checks it. The hand calculation checks the code against Eq. 7 as
  printed in the paper (p. 38): form, slope 0.34, threshold 3 m and floor
  0.2 m/s match. It checks the equation, not the paper's data. The paper
  converts extinction to visibility with \(A\) = 2 (light-reflecting) or 8
  (light-emitting); the default is \(A\) = 2. The tests do not check
  which of the two a given scene needs.
- *K* = 0.5, 1 and 10 1/m lie outside the tunnel data (about 1.9 to
  7.4 1/m, the range given on the Fundamentals page; the report's text says
  about 2 to 7 1/m). Passing Test 18 verifies the code, not the law,
  there.
- The FDS case confirms that the slice nearest 1.6 m is read. The two slices
  differ by only 6 × 10⁻⁵ 1/m, from hydrostatics. The test cannot show
  sampling in a real vertical or horizontal gradient, or at the occupant's
  *current* position and time
  ([#24](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/24)).
- No run reaches the floor *f* = 0.1 (*K* ≥ 11.15 1/m).
- In the social force runs the occupant spawns 0.47 m from the back wall.
  The wall push briefly takes it above \(f v_0\) at the start (0.34 m/s at
  *K* = 10, against 0.24 m/s). This is movement-model behaviour; the time
  criterion absorbs it through the start-up time *a* of the clear runs.
- One occupant per condition, one seed. The ISO test asks for no more, but
  it says nothing about crowds in smoke.
- The tight criteria on this page are checked by the figure script on stored
  output. CI checks the time ratio within 8 %, reads the 2.0 m slice in the
  coupled test, and takes the expected factor from the code under test
  ([#259](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/259)).
- `assets/ISO-table21/ISO-table21.fds` is a template deck with a fire; no
  test and no run on this page uses it.
