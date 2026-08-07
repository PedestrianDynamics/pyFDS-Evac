# ISO 20414 Table 22 — occupant incapacitation by fire/smoke

**Source:** ISO 20414:2020(E), §5.4, **Test 19 — Occupant incapacitation by
fire/smoke**, specified in **Table 22**.

> *Objective* — "Assess consistency between the assigned occupant
> incapacitation by fire/smoke calculation method and model representation."
>
> *Geometry* — "A room with no fire source (10 m × 10 m × 3 m)."
>
> *Scenario, Step 1* — "place an occupant in the centre of the room. The
> occupant is held in a fixed initial position by setting a high pre-evacuation
> time (> 10 000 000 s). Hazardous conditions are implemented in the model in
> relation to the incapacitation sub-model in use."
>
> *Step 2* — "Construct the same room and perform a FED measurement in the same
> location of the occupant, (either using hand calculations or an independent
> validated fire model …)."
>
> *Expected result* — "the time to reach occupant incapacitation (FED=1) in
> Step 1 is the same as the time to reach FED=1 in the measurement point in
> Step 2. This test should be repeated for each hazardous condition available in
> the incapacitation sub-model."

## Why the pre-evacuation time is 20 000 000 s

Because the standard says so. `premovement_param_b: 20000000` is **not** a typo
or a hack — it is ISO's own method of holding the occupant still, and any reader
who assumes otherwise (as one did) will "fix" a compliant asset into a
non-compliant one.

| ISO 20414 Table 22 | this asset | |
|---|---|---|
| room 10 m × 10 m × 3 m | `POLYGON((-5 -5, -5 5, 5 5, 5 -5))` = 10 × 10 m | ✅ |
| occupant in the centre | spawn box centred on the origin, `number: 1` | ✅ |
| pre-evacuation > 10 000 000 s | uniform draw over **[0, 20 000 000]** | ⚠️ |
| no fire source | no deck at all; the field is supplied by the test | ✅ |
| Step 2 by hand calculation | `time_to_fed_threshold_s()` | ✅ |
| repeat per hazardous condition | **one condition only** | ❌ |

The height is absent because the walkable area is 2-D; nothing in the test
depends on it.

## The two deviations

**The pre-evacuation draw is unbounded below.** A uniform draw over
`[0, 2 × 10⁷]` can return a few seconds, which would let the occupant walk away
mid-test — the opposite of what ISO asks for. In practice this never bites,
because the test overrides `use_premovement = False` and `v0 = 0.0` before
running, achieving the same stationarity by a different route. That override is
also why the flaw went unnoticed. Bounding the draw below at 1,2 × 10⁷ would be
both faithful and robust; see
[`assets/iso_table22_coupled`](../iso_table22_coupled/README.md), which does.

**Only one hazardous condition.** ISO asks for the test to be repeated for each
condition the sub-model supports. This asset runs a single mixture
(CO 0,1 %, CO₂ 5 %, O₂ 12 %). The four-case version lives in
`iso_table22_coupled`.

## What the test asserts, and what it does not

`tests/test_fed.py::test_iso_table22_stationary_runtime_matches_analytic_threshold_time`
runs a real `run_scenario`, takes the analytic FED = 1 time from
`time_to_fed_threshold_s()`, and asserts the observed crossing lands within one
timestep of it, that `fed_max ≥ 1.0`, and that the occupant does not evacuate.

The last of those is a **guard, not a result**: if the occupant walked out, the
exposure would have ended early and the timing comparison would be meaningless.

**The gas field is stubbed.** `_ConstantInputsFedModel.advance()` ignores
`time_s`, `x` and `y` and returns three hardcoded numbers. So no slice is read,
no unit is converted, no position is sampled — this verifies that the runtime
*accumulator* integrates a dose correctly over time, and nothing about how gas
reaches that arithmetic. It cannot catch a ppm/vol-% confusion, a slice read at
the wrong height, or a species missing from a deck.

That is a legitimate unit-level test, and worth keeping. It is not a coupled
one. [`assets/iso_table22_coupled`](../iso_table22_coupled/README.md) performs
the same ISO test with every step live, and with the four gas cases ISO asks for.

## Also used as a generic fixture

`test_fed.py` uses this asset for unrelated FED-history throttling tests,
because it is small and stationary.

## Related

- [`assets/ISO-table21`](../ISO-table21/README.md) — ISO 20414 Table 21, the
  walking-speed-in-smoke counterpart.
- FDS+Evac Technical Reference **Figure 8** ("A FED test") is the vendor's
  version of this test and supplies the four concentration sets ISO leaves to
  the tester.
