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
| **Status** | passes on the stored runs (figure script); CI checks the time ratio within 8 % |

![Five copies of the ISO corridor, tinted darker the denser the smoke: clear air and K = 1, 3, 7.5 and 10 per metre; the occupant's colour shows its walking speed, and each corridor ends with the simulated and the expected egress time](/images/verification/iso18.gif)

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
  *x* = −49.64 m and is removed at *x* ≈ 48.5 m, once within its radius
  + 0.5 m of a target point drawn inside the exit zone
  ([`scenario.py`](https://github.com/PedestrianDynamics/pyFDS-Evac/blob/main/pyfds_evac/core/scenario.py)).
  So it walks about 98 m, not 100 m. The seed fixes the target, so it is the
  same in the clear and the smoky run. ISO's absolute time depends on that distance, so the page predicts
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
| clear runs: \(t = L/v_0 + a\) | *L* = 97.714 m, *a* = 0.609 s, largest residual 0.013 s | fit to the five clear runs, \(v_0\) = 1.25 to 0.25 m/s |
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
\(f v_0\) to 5.1 × 10⁻⁶.

![Left: simulated egress-time ratio against 1/f(K). Right: each smoky egress time minus the expected time, with its tolerance](/images/verification/iso18_ratio.png)

| Run | *K* [1/m] | \(v_0\) [m/s] | \(t_{\mathrm{clear}}\) [s] | \(t_{\mathrm{smoke}}\) [s] | \(t_{\mathrm{pred}}\) [s] | difference [s] | tolerance [s] | expected 1/*f* | simulated ratio |
|---|---|---|---|---|---|---|---|---|---|
| constant *K* | 0.5 | 1.25 | 78.77 | 82.06 | 82.068 | −0.008 | 0.033 | 1.04207 | 1.04177 |
| constant *K* | 1 | 1.25 | 78.77 | 85.64 | 85.646 | −0.006 | 0.033 | 1.08783 | 1.08722 |
| constant *K* | 3 | 1.25 | 78.77 | 103.77 | 103.766 | +0.004 | 0.033 | 1.31963 | 1.31738 |
| constant *K* | 7.5 | 1.25 | 78.77 | 198.79 | 198.774 | +0.016 | 0.033 | 2.53501 | 2.52368 |
| constant *K* | 10 | 1.25 | 78.77 | 406.40 | 406.410 | −0.010 | 0.033 | 5.19118 | 5.15932 |
| constant *K* | 1 | 1.0 | 98.32 | 106.91 | 106.905 | +0.005 | 0.033 | 1.08783 | 1.08737 |
| constant *K* | 1 | 0.75 | 130.90 | 142.35 | 142.337 | +0.013 | 0.033 | 1.08783 | 1.08747 |
| constant *K* | 1 | 0.5 | 196.05 | 213.21 | 213.201 | +0.009 | 0.033 | 1.08783 | 1.08753 |
| constant *K* | 1 | 0.25 | 391.46 | 425.78 | 425.794 | −0.014 | 0.033 | 1.08783 | 1.08767 |
| *K* from FDS | 0.99550 | 1.25 | 78.14 | 84.97 | 84.969 | +0.001 | 0.021 | 1.08740 | 1.08741 |

| Check | Expected | Simulated |
|---|---|---|
| recorded factor, constant *K* | *f*(*K*) by hand | equal to 1.1 × 10⁻¹⁶ |
| recorded *K*, FDS | inside the 1.5 m slice, outside the 2.0 m slice | 0.9955019 to 0.9955078: inside, outside |
| recorded factor, FDS | inside *f* of the 1.5 m slice's range | inside |
| walked speed / \(f v_0\) | 1 | 1 − 5.1 × 10⁻⁶ at worst |
| egress time | \(t_{\mathrm{pred}}\) within the tolerance | all 10 inside, largest +0.016 s on 199 s |

The simulated ratio is always a little below 1/*f*, by up to 0.61 % at
*K* = 10. That is the start-up time *a*: it does not scale with 1/*f*, so
\(t_{\mathrm{smoke}}/t_{\mathrm{clear}} \cdot f - 1 = -a(1-f)/t_{\mathrm{clear}}\),
which predicts −0.62 % at *K* = 10. Once *a* is taken from the clear runs, each egress time
matches to 16 ms. The collision-free model in the FDS case has no start-up
and matches the ratio to 10⁻⁵.

## Pass criteria

1. **Factor.** The recorded factor equals *f*(*K*) by hand to round-off,
   ≤ 10⁻¹². For the FDS case, the recorded *K* lies within the 1.5 m slice's
   range and outside the 2.0 m slice's range, and the factor within *f* of
   the 1.5 m range. The two ranges are 4.5 × 10⁻⁵ apart, almost four times
   the spread within one.
2. **Speed.** The speed along the path over the middle 40 m equals
   \(f v_0\) within 10⁻⁵. This tolerance is a margin, not derived. The
   collision-free model walks exactly at \(f v_0\); the social force model
   walks 1.7 to 5.1 × 10⁻⁶ slower, a property of the movement model. The
   smallest error the check must catch, a factor not applied at *K* = 0.5,
   is 1 − *f* = 4 %, four orders of magnitude larger.
3. **Egress time.** Each egress time is a whole number of time steps
   Δ*t* = 0.01 s. For the social force runs,
   \(|t_{\mathrm{smoke}} - t_{\mathrm{pred}}| \le r_{\max} + 2\,\Delta t\) =
   0.033 s. The clear fit's largest residual \(r_{\max}\) = 0.013 s covers
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

The tests run both cases in about 20 s. They are weaker than this page: the
coupled test reads the 2.0 m slice, not the 1.5 m slice the default height
picks; both compute the expected factor with the code's own function; and the
time ratio passes within 8 %
([#259](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/259)):

```bash
uv run pytest tests/test_smoke_speed.py -k iso_table21 tests/test_iso_table21_coupled.py
```

For the figures, run the 16 cases with `run.py`. The FDS output is committed
in `assets/iso_table21_coupled/fds/`; to rebuild it, run
`python assets/iso_table21_coupled/build_geometry.py` and then
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
this page are in the project's data folder (`fds-evac-data/iso_test_18/`).

## Limits

- Only the default law is run in the ISO layout. The `fridolf` option
  (`speed_law="fridolf"`), reachable only from Python, is checked by the
  [S2 corridor test](https://github.com/PedestrianDynamics/pyFDS-Evac/blob/main/tests/verification/test_s2_corridor_speed.py),
  not here.
- *K* = 0.5, 1 and 10 1/m lie outside the tunnel data (about 1.9 to
  7.4 1/m, the range given on the Fundamentals page; not re-checked against
  the report for this page). Passing Test 18 verifies the code, not the law,
  there.
- The FDS case confirms that the slice nearest 1.6 m is read. The two slices
  differ by only 6 × 10⁻⁵ 1/m, from hydrostatics. The test cannot show
  sampling in a real vertical or horizontal gradient, or at the occupant's
  *current* position and time
  ([#24](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/24)).
- No run reaches the floor *f* = 0.1 (*K* ≥ 11.15 1/m).
- In the social force runs the occupant spawns 0.36 m from the back wall.
  The wall push briefly takes it above \(f v_0\) at the start (0.57 m/s at
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
