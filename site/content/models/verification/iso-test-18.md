---
title: "ISO 20414 Test 18: walking speed in smoke"
linkTitle: "ISO Test 18"
weight: 18
math: true
---

| | |
|---|---|
| **Component** | Smoke-speed law ([Models › Smoke-speed](/models/smoke-speed.md)) |
| **Level** | FDS case: a constant *K* supplied directly, and *K* read from committed FDS output |
| **Asset** | `assets/ISO-table21`, `assets/iso_table21_coupled` |
| **Expected value from** | hand calculation of the model's own law, as ISO 20414 asks; for the FDS case, the soot density the deck prescribes |
| **Status** | passes |

![Five copies of the ISO corridor, one in clear air and four in smoke with K = 1, 3, 7.5 and 10 per metre; the occupant's colour shows its walking speed, and the smokier the corridor, the later it arrives](/images/verification/iso18.gif)

## What is tested

Whether smoke slows an occupant by exactly the factor the smoke-speed law
gives, and whether that slower speed really changes the egress time. A factor
that is computed but never applied, applied to the wrong speed, or applied
twice, changes the time ratio. In the FDS case, a wrong slice, a wrong
quantity or a wrong soot-to-*K* conversion changes the *K* the occupant sees.

## Equation

The default law (`lund`, the linear law of
[FDS+Evac](https://github.com/firemodels/fds/tree/c9da70d7a/Source) by
Frantzich and Nilsson; see
[Models › Smoke-speed](/models/smoke-speed.md#coded-form)) turns the
extinction coefficient *K* [1/m] into a speed factor *f* [-]:

$$
f(K) = \min\!\left(1,\ \max\!\left(0.1,\ 1 + \frac{\beta}{\alpha}K\right)\right),
\qquad \alpha = 0.706,\quad \beta = -0.057 .
$$

The walking speed is \(v = f(K)\,v_0\), with \(v_0\) [m/s] the unimpeded
speed. In a corridor where *K* is the same everywhere, the occupant walks the
same distance at \(f v_0\) instead of \(v_0\), so ISO 20414's expected result is

$$
\frac{t_{\mathrm{smoke}}}{t_{\mathrm{clear}}} = \frac{1}{f(K)} .
$$

For the FDS case the deck prescribes a soot mass fraction \(Y_s\), and FDS
computes \(K = K_m\,\rho\,Y_s\) with the mass extinction coefficient
\(K_m = 8700\) m²/kg and the gas density ρ [kg/m³].

## Setup

![Plan of the ISO corridor: the full 100 m length with spawn box and exit, then both ends at true scale](/images/verification/iso18_setup.png)

- **Corridor:** ISO 20414 Table 21, 100 × 2 m, one exit 1 m wide at the far
  end. One occupant, \(v_0\) = 1.25 m/s, seed 420, so it starts at the same
  point in the clear and the smoky run.
- **Constant *K*** (`assets/ISO-table21`, social force model): *K* = 0.5, 1,
  3, 7.5 and 10 1/m, as in ISO's Table 21, and at *K* = 1 also
  \(v_0\) = 1.0, 0.75, 0.5 and 0.25 m/s. Each smoky run has its own clear run.
- **FDS** (`assets/iso_table21_coupled`, collision-free speed model): the
  corridor filled with soot at \(Y_s = 9.546\times10^{-5}\), no fire, one mesh
  with 0.5 m cells. Slices of *K* at 2.0 m and at 1.6 m, which FDS writes at
  1.5 m. The occupant reads the 1.5 m slice, nearest the default sampling
  height of 1.6 m.
- **Runs:** `run.py` with a smoke update every 0.1 s, rerouting and
  incapacitation off, as in the tests. 16 runs in all.

## Expected

| Quantity | Value | From |
|---|---|---|
| *f*(0.5), *f*(1), *f*(3), *f*(7.5), *f*(10) | 0.95963, 0.91926, 0.75779, 0.39448, 0.19263 | the law above, by hand |
| 1/*f* for the same *K* | 1.0421, 1.0878, 1.3196, 2.5350, 5.1912 | by hand |
| *K* where the floor *f* = 0.1 starts | 11.15 1/m | by hand; no run reaches it |
| ρ of the deck's air at 20 °C | 1.19889 kg/m³ | ideal gas, N₂ + 23.1 % O₂ + soot |
| *K* the deck prescribes | 0.99567 1/m | \(8700 \times 1.19889 \times 9.546\times10^{-5}\) |
| *K* in the FDS slice at 1.5 m | 0.99550 1/m (0.9954990 to 0.9955111) | read with `fdsreader`, all cells, all times |
| *f* and 1/*f* for the FDS case | 0.91963, 1.08740 | by hand, from the slice |

The slice lies 1.7 × 10⁻⁴ below the deck's value. That is the weight of
1.5 m of air: FDS's density falls with height by \(\rho g z / p\) =
1.7 × 10⁻⁴. The deck aimed at *K* = 1.0 1/m with a density of 1.2041 kg/m³;
the 0.45 % gap to 0.9955 is that assumption, not a coupling error.

## Result

![The speed-factor law against K, with the factor each run recorded and the speed the occupant actually walked](/images/verification/iso18_speed_factor.png)

Every run records the factor of the law, and the occupant walks at that
speed. Over the middle 40 m of the corridor, the walked speed matches
\(f v_0\) to 5 × 10⁻⁶.

![Left: simulated egress-time ratio against 1/f(K). Right: its relative error, with the pass band](/images/verification/iso18_ratio.png)

| Run | *K* [1/m] | \(v_0\) [m/s] | \(t_{\mathrm{clear}}\) [s] | \(t_{\mathrm{smoke}}\) [s] | expected 1/*f* | simulated ratio | error | band |
|---|---|---|---|---|---|---|---|---|
| constant *K* | 0.5 | 1.25 | 78.77 | 82.06 | 1.04207 | 1.04177 | −0.03 % | 0.08 % |
| constant *K* | 1 | 1.25 | 78.77 | 85.64 | 1.08783 | 1.08722 | −0.06 % | 0.13 % |
| constant *K* | 3 | 1.25 | 78.77 | 103.77 | 1.31963 | 1.31738 | −0.17 % | 0.33 % |
| constant *K* | 7.5 | 1.25 | 78.77 | 198.79 | 2.53501 | 2.52368 | −0.45 % | 0.79 % |
| constant *K* | 10 | 1.25 | 78.77 | 406.40 | 5.19118 | 5.15932 | −0.61 % | 1.05 % |
| constant *K* | 1 | 1.0 | 98.32 | 106.91 | 1.08783 | 1.08737 | −0.04 % | 0.10 % |
| constant *K* | 1 | 0.75 | 130.90 | 142.35 | 1.08783 | 1.08747 | −0.03 % | 0.08 % |
| constant *K* | 1 | 0.5 | 196.05 | 213.21 | 1.08783 | 1.08753 | −0.03 % | 0.05 % |
| constant *K* | 1 | 0.25 | 391.46 | 425.78 | 1.08783 | 1.08767 | −0.01 % | 0.03 % |
| *K* from FDS | 0.99550 | 1.25 | 78.14 | 84.97 | 1.08740 | 1.08741 | +0.001 % | 0.13 % |

| Check | Expected | Simulated |
|---|---|---|
| recorded factor, constant *K* | *f*(*K*) by hand | equal to 1.1 × 10⁻¹⁶ |
| recorded *K* and factor, FDS | inside the slice's range | *K* 0.9955019 to 0.9955078, inside |
| walked speed / \(f v_0\) | 1 | 1 − 5 × 10⁻⁶ at worst |
| time ratio | 1/*f* within the band | all 10 pairs inside, largest −0.61 % at *K* = 10 |

The social force runs all come out slightly short of 1/*f*, more so at high
*K*. Their egress times follow \(t = L/v + a\) to within 0.02 s, with
*L* = 97.71 m and a start-up time *a* = 0.61 s that does not scale with
1/*f* (fit over the clear run and the five *K* at \(v_0\) = 1.25 m/s). The
collision-free model in the FDS case has no inertia and matches to 10⁻⁵.

## Pass criteria

1. **Factor.** The recorded factor equals *f*(*K*) by hand to round-off,
   ≤ 10⁻¹². For the FDS case, *K* and the factor lie within the range of the
   slice, whose cells differ by 1.2 × 10⁻⁵.
2. **Speed.** The walked speed over the middle 40 m equals \(f v_0\) within
   10⁻⁵. The occupant drifts sideways by about 0.25 m over 100 m, which
   shortens the speed along the corridor by about 3 × 10⁻⁶.
3. **Time ratio.** Write each egress time as \(t = L/v + a\): a walk at the
   steady speed plus a start-up time *a* that does not depend on the speed.
   Then
   \(\dfrac{t_{\mathrm{smoke}}}{t_{\mathrm{clear}}}\,f - 1 = -\dfrac{a\,(1-f)}{t_{\mathrm{clear}}}\).
   An occupant that relaxes to its desired speed with time constant τ loses
   τ, so \(a \approx \tau\) = 0.5 s in the social force model and
   *a* = 0 in the collision-free model. The social force model does not
   relax exactly exponentially, and the fit above gives *a* = 0.61 s, so the
   band allows 2τ = 1 s. Each egress time is also a whole number of time
   steps, which adds one step Δ*t* per run:

   $$
   \left|\frac{t_{\mathrm{smoke}}}{t_{\mathrm{clear}}}\,f - 1\right|
   \le \frac{2\tau\,(1-f) + 2\,\Delta t}{t_{\mathrm{clear}}},
   $$

   with Δ*t* = 0.01 s (social force) and 0.05 s (collision-free).

The pytest tests ask for less: the ratio within 8 %, and the factor equal to
six decimals.

## Run it yourself

The tests run both cases in about 20 s:

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
- *K* is the same everywhere, so this test cannot show whether the field is
  sampled at the occupant's *current* position, or at the right height; a
  gradient is needed for that
  ([#24](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/24)).
- No run reaches the floor *f* = 0.1 (*K* ≥ 11.15 1/m).
- One occupant per condition, one seed. The ISO test asks for no more, but
  it says nothing about crowds in smoke.
- The pass band on this page is checked by the figure script on stored
  output. The pytest tests use the looser 8 % and six decimals.
- `assets/ISO-table21/ISO-table21.fds` is a template deck with a fire; no
  test and no run on this page uses it.
