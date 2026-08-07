# ISO 20414 Table 22, coupled to real FDS output

**Does a dose computed from an actual FDS case reach incapacitation when the
hand calculation says it should?**

## What the standard specifies

ISO 20414:2020 Table 22 — *Test 19, Occupant incapacitation by fire/smoke*:

| | |
|---|---|
| Geometry | "A room with no fire source (10 m × 10 m × 3 m)" |
| Step 1 | occupant at the centre, "held in a fixed initial position by setting a high pre-evacuation time (> 10 000 000 s)"; hazardous conditions per the incapacitation sub-model |
| Step 2 | "perform a FED measurement in the same location … either using hand calculations or an independent validated fire model" |
| Expected | "the time to reach occupant incapacitation (FED=1) in Step 1 is the same as the time to reach FED=1 … in Step 2" |
| Repeat | "for each hazardous condition available in the incapacitation sub-model" |

Step 1 here is a real `run_scenario`. Step 2 is `time_to_fed_threshold_s()`,
which is exact because the gas is *prescribed* by a single `&INIT` rather than
burned, so it is uniform in space and constant in time.

## Where the concentrations come from

ISO deliberately prescribes none — it says to repeat for each hazardous
condition. The FDS+Evac Technical Reference, **Figure 8** ("A FED test"),
supplies exactly the concrete sets ISO leaves to the tester:

| case | CO₂ % | CO % | O₂ % | isolates | FED = 1 |
|---|---|---|---|---|---|
| a | 2.00 | 0.10 | 15.0 | all three terms | 982 s |
| b | 0.00 | 0.00 | 12.0 | O₂ hypoxia alone | 1666 s |
| c | 0.00 | 0.10 | 21.0 | CO alone | 1626 s |
| d | 3.43 | 0.10 | 21.0 | CO + CO₂ factor | 847 s |

Cases c and d share the same CO and differ only in CO₂, so d must be strictly
faster — that pair is what makes the hyperventilation factor observable. Case b
has no CO at all, and c and d sit above the 19.5 % O₂ gate so the hypoxia term
is switched off in them. A single case could not separate any of this.

## What is live

```
deck → FDS → fdsreader → slice selection → unit conversion
     → DefaultFedInputs → accumulator → fed_history
```

Every step. Options are built through `build_run_kwargs`, the function `run.py`
uses, so `_build_fed_model` and the slice-height plumbing are covered rather
than bypassed.

Contrast `assets/ISO-table22`, which performs the same ISO test with the field
**stubbed**: its FED model ignores `time_s`, `x` and `y` and returns hardcoded
numbers, so no slice is read, no unit converted, no position sampled. That
verifies the accumulator; this verifies the chain from deck to dose. Both are
worth having — they fail for different reasons.

## The occupant is held still by ISO's method

`use_premovement: true` with a uniform draw over **[1.2 × 10⁷, 2 × 10⁷] s**,
satisfying ISO's "> 10 000 000 s".

The lower bound matters. `assets/ISO-table22` draws over `[0, 2 × 10⁷]`, which
can return a few seconds and let the occupant walk away mid-test; its own test
sidesteps that by overriding `use_premovement = False` and `v0 = 0`. Bounding
the draw below is both faithful and robust, and no override is needed.

`agents_remaining == 1` and the position-invariance check are guards, not
results: if the occupant moved, the exposure would have changed and the timing
comparison would mean nothing.

## Running it

```bash
.venv/bin/python assets/iso_table22_coupled/build_geometry.py

for c in a b c d; do
  mkdir -p /tmp/t22/$c && cp assets/iso_table22_coupled/iso_table22_$c.fds /tmp/t22/$c/
  (cd /tmp/t22/$c && fds iso_table22_$c.fds)        # ~40 s each
  .venv/bin/python run.py \
      --scenario assets/iso_table22_coupled/config_$c.json \
      --fds-dir /tmp/t22/$c --output-fed-history /tmp/t22/fed_$c.csv
done
```

## The FDS output is committed

`fds/{a,b,c,d}/` holds **256 kB total** — four slices per case on a 20 × 20 × 6
mesh — forced past `.gitignore`, **so the test runs in CI**. A test that skipped
when output was missing would leave this path exactly as untested as it was
before, which is how the FIC speed factor came to compound to zero unnoticed.

`DT_SLCF` is 500 s, not the usual few seconds: the field is constant by
construction, so temporal resolution buys nothing and costs bytes. The test
asserts the constancy rather than assuming it.

Only `.sf`, `.sf.bnd` and `.smv` are kept. The `_hrr.csv` FDS also writes is
272 kB per case — larger than everything retained — and nothing reads it.

## What this catches that the stubbed test cannot

- a ppm / vol-% confusion anywhere in the sampler
- a mass fraction delivered where a volume fraction is expected
- a slice read at the wrong height
- a species missing from the deck, which silently disables FED and leaves every
  column at zero — indistinguishable from clean air
- a sampler returning a default instead of a real reading: cases b and c assert
  species that must be **exactly zero**

Verified by mutation: claiming case c contains 1.5 % CO₂ when its deck says 0
fails three assertions independently — the concentration check, the rate, and
the crossing time.

## Tests

`tests/test_iso_table22_coupled.py`, 37 tests over the four cases, ~26 s.
