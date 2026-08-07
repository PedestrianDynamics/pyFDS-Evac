# Stationary FED, read from real FDS output

**Does a dose computed from an actual FDS case reach the threshold when the
closed form says it should?**

`assets/ISO-table22` asks a narrower question. Its test injects a FED model
whose `advance()` ignores `time_s`, `x` and `y` and returns three hardcoded
numbers, so no slice is read, no unit is converted and no position is sampled.
It verifies the accumulator integrates correctly — our arithmetic against our
arithmetic — and nothing about how gas reaches that arithmetic.

Until this asset, **no test in the repository read a real FDS slice into the
model.** Every `fds_dir` in `tests/` was a string for cache-metadata comparison
or a mocked sampler. That is the gap that let the FIC speed factor compound to
zero unnoticed for months.

## What is live here

```
deck → FDS → fdsreader → slice selection → unit conversion
     → DefaultFedInputs → accumulator → fed_history
```

Every step. The test builds its options through `build_run_kwargs`, the same
function `run.py` uses, so `_build_fed_model` and the slice-height plumbing are
covered rather than bypassed.

## Why an analytic answer still exists

The gas is **prescribed**, not burned. A single `&INIT` fills a sealed 4 × 4 m
box with a fixed mixture: no combustion, no transient, no spatial gradient. So
the concentration is a known constant and `time_to_fed_threshold_s()` predicts
the crossing exactly. The technique — and its pitfall, that a second `&INIT`
without `XB` silently resets the whole domain — follows
[`fic_vs_fed_speed`](../fic_vs_fed_speed/README.md).

| | value |
|---|---|
| CO | 0.10 vol % (1000 ppm) |
| CO₂ | 5.00 vol % |
| O₂ | 12.00 vol % |
| FED rate | 0.1316 /min |
| **analytic FED = 1** | **456.0 s** |
| **observed** | **457.0 s** |

That's the `combined` case from `tests/test_fed.py`, so both tests describe the
same occupant and their answers are directly comparable.

**All three terms matter, and none dominates.** CO alone would take 1626 s; CO
plus the CO₂ hyperventilation factor, 628 s; the O₂ hypoxia term brings it to
456 s. A unit slip in any one of the three moves the crossing detectably, which
is what makes the single number a real check rather than a coincidence.

## The FDS output is committed

`fds/` holds 136 kB — four slices on an 8 × 8 × 6 mesh, dumped every 10 s. It is
in git (forced past `.gitignore`, which excludes `*.sf` and `*.smv` by default)
**so the test runs in CI**. A test that skipped when FDS output was missing
would leave this path exactly as untested as it was before.

Regenerate it only if the deck changes:

```bash
.venv/bin/python assets/iso_table22_coupled/build_geometry.py
mkdir -p /tmp/iso22c && cp assets/iso_table22_coupled/iso_table22_coupled.fds /tmp/iso22c/
cd /tmp/iso22c && fds iso_table22_coupled.fds && cd -
cp /tmp/iso22c/*.sf /tmp/iso22c/*.sf.bnd /tmp/iso22c/*.smv /tmp/iso22c/*.out \
   assets/iso_table22_coupled/fds/
git add -f assets/iso_table22_coupled/fds
```

Only those four file types are kept. The `_hrr.csv` FDS also writes is 272 kB —
twice the rest combined — and nothing reads it; `fdsreader` logs a warning about
its absence which is safe to ignore, as its own message says.

## What this catches that the stubbed test cannot

- a ppm / vol-% confusion anywhere in the sampler
- a mass-fraction value delivered where a volume fraction is expected
- a slice read at the wrong height
- a species missing from the deck, which silently disables FED and leaves every
  column at zero — indistinguishable from a clean atmosphere, and the reason
  [`docs/fds-case-requirements.md`](../../docs/fds-case-requirements.md) calls
  it a silent failure mode
- a mesh whose extent does not cover the agent

Verified by mutation: changing the expected CO from 0.10 to 0.05 while the
committed FDS output stays fixed fails four assertions independently — the
concentration check, the rate check, the crossing time, and the premise guard.

## Deliberate choices

**The occupant is stationary by construction** — `v0: 0`, `use_premovement:
false`. `ISO-table22` achieves the same thing with a pre-movement time of
20 000 000 s that its own test then overrides; two mechanisms, neither obvious.

**`agents_remaining == 1` is a guard, not a result.** If the agent walked out
the exposure would have ended early and the timing comparison would be
meaningless. `test_it_does_not_move` checks the position never changes.

**There is an exit** because one is structurally required. It sits in a corner
an agent with zero desired speed can never reach.

**Optically clear.** `SOOT` is declared only so the extinction slice has a
species to report on — `SPEC_ID` is mandatory once species are declared
explicitly, or FDS raises ERROR 1004. With no combustion its mass fraction stays
zero, so smoke never enters the result.

## Tests

`tests/test_iso_table22_coupled.py`, 11 tests, ~2 s: the gas arrives unaltered
and constant, none of the three species is silently zero, the rate and the
crossing match the closed form, the dose is monotone, and the occupant stays put.
