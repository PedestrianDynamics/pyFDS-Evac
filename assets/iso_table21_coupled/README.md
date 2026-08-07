# ISO 20414 Table 21, coupled to real FDS output

**Does the extinction coefficient read out of an FDS slice slow an occupant by
the amount the hand calculation says it should?**

## What the standard specifies

ISO 20414:2020 Table 21 — *Test 18, Reduced visibility vs walking speed*:

| | |
|---|---|
| Geometry | "A corridor 2 m wide and 100 m long. One exit (1 m wide) is placed at the end" |
| Scenario | unimpeded walking speed "equal to 1,25 m/s"; "A constant extinction coefficient equal to 1,0/m is implemented in the corridor prior to running the simulation" |
| Expected | "the time needed by the occupant to cover the distance of the corridor is the same as the time manually calculated employing the correlation used by the model" |

## Why this exists next to `assets/ISO-table21`

That asset implements the same clause and is faithful — ISO says the coefficient
is *implemented*, not that it comes from a fire model. But it supplies K through
`ConstantExtinctionField`, so **no slice is ever read**.

That left the extinction path unverified end to end, and extinction is the
busier of the two hazard signals: it drives the walking-speed factor *and* the
routing cost through `w_smoke`. It is also where `EXTINCTION` and
`SOOT EXTINCTION COEFFICIENT` were once treated as synonyms — two unrelated FDS
quantities (User Guide §22.10.29 vs §22.10.5), one a 0/1/−1 combustion flag.
Before this asset, the only `ExtinctionField.from_fds` in the test suite used a
*fake* simulation object.

Here K arrives the way it does in a real case:

```
deck → FDS → fdsreader → SliceFieldSampler → speed factor → egress time
```

## A cross-check, not just plumbing

FDS computes its `SOOT EXTINCTION COEFFICIENT` slice as

```
K = MASS_EXTINCTION_COEFFICIENT × soot density        (default 8700 m²/kg)
```

and `extinction_from_soot_density()` uses the same 8700. The deck therefore
prescribes the soot density that *should* produce K = 1,0/m and the test checks
what comes back — verifying our conversion against FDS's own, not merely the
transport between them. A test that injected K directly could not tell the two
apart.

| | value |
|---|---|
| target K | 1.000 /m |
| prescribed soot | 114.9 mg/m³ (mass fraction 9.546 × 10⁻⁵) |
| **K read back from the slice** | **0.99545 /m** |
| agreement | **0.46 %** |

The residual is the air density assumed when turning a target *density* into the
mass *fraction* FDS wants (1.2041 kg/m³ at 20 °C). It is not a plumbing error,
and the test asserts 1 % rather than pretending to be exact.

## The result

| run | egress |
|---|---|
| clear (no `--fds-dir`) | 78.29 s |
| K from FDS = 0.99545 /m | 85.13 s |
| observed ratio | 1.0874 |
| expected `1 / speed_factor(0.99545)` | 1.0874 |

The recorded `speed_factor` is 0.919631 at every sample, matching
`speed_factor_from_extinction(0.99545)` exactly.

## Running it

```bash
.venv/bin/python assets/iso_table21_coupled/build_geometry.py

mkdir -p /tmp/t21 && cp assets/iso_table21_coupled/iso_table21_coupled.fds /tmp/t21/
(cd /tmp/t21 && fds iso_table21_coupled.fds)          # ~10 s

.venv/bin/python run.py --scenario assets/iso_table21_coupled/config.json \
    --fds-dir /tmp/t21 --smoke-update-interval 0.1 \
    --output-smoke-history /tmp/t21/smoke.csv
```

The CSV is how you check this by hand: every row carries the sampled extinction
and the `speed_factor` derived from it.

## The FDS output is committed

`fds/` holds **28 kB** — one slice on a 200 × 4 × 6 mesh — forced past
`.gitignore` so the test runs in CI. A test that skipped when output was missing
would leave the path as untested as it was before.

`DT_SLCF` is 100 s because the field is constant by construction; the test
asserts that constancy rather than assuming it.

## Deliberate choices

**Prescribed soot, not a fire.** A single `&INIT` fills the corridor with a fixed
soot mass fraction — no combustion, no plume, no gradient — so K is constant and
the hand calculation stays exact. Same technique as
[`iso_table22_coupled`](../iso_table22_coupled/README.md) and
[`fic_vs_fed_speed`](../fic_vs_fed_speed/README.md).

**`w_smoke = 0`.** This asset isolates the *speed* effect. Extinction also feeds
the routing cost, but with one occupant and one exit there is nothing to reroute,
and mixing the two would make an unexplained egress time ambiguous.

**Tenability disabled.** Soot alone, no CO or O₂ in the deck, so there is no dose
to accumulate and nothing competes with the speed reduction.

## Tests

`tests/test_iso_table21_coupled.py`, 11 tests, ~3 s.

Two of them are controls rather than results:

- `test_smoke_actually_slows_the_occupant` — without it, a coupling that
  silently did nothing would still satisfy a ratio assertion whose expected
  value is close to 1;
- `test_it_is_not_zero` — a missing or misnamed slice reads as clear air and
  would pass every downstream ratio check.

One asserts this README quotes the K actually measured, so the numbers above
cannot drift away from the run without a test failing.
