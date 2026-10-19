# G6: what removing the slice sampler lookups still saves on W1 at main after #812 (#242)

2026-10-18. G3b measured 47.18 s per ten-run study for the `nss` removal arm at `8f7d29a2`, before the
FED-rate memo of PR #812, which skips 266,023 of 410,667 route-side FED-rate reads on W1, each three or
more scalar `sample` calls. G6 re-measures the same `nss` arm (every scalar `SliceFieldSampler.sample`
stubbed) at `main` `d96894ac`, ten paired seeds, one exclusive slot. A removal arm bounds what a fix can
save; it is not a fix.

## The slot

- `g6_all.sh` ran 08:23:16Z to 08:47:57Z on 2026-10-18 (elapsed 1481 s; `results/blocks/g6_status.tsv`, driver
  log `results/blocks/g6_all_20261018T082316Z.log`), stage `wt_d96894ac`, commit `d96894acb085…`.
- Blocks: `G6_nss_W1` (40 runs, 20 timed: 10 `O_norc`, 10 `nss`, abba across seeds, warm-up 1) and `G6_ctr_W1`
  (4 counters runs, diagnostic); both `rc=0`, 44 manifests.
- sha256 at the slot commit (67777d8): `benchmark.py` `c6a162ff1d5e…`, `instrument/perf_run.py`
  `0ed17d9865b0…` (both in all 44 manifests), `attribute.py` `b0b2db4ed2b4…` (before Task 3).
- Flagged timed reps: 10 of 20 (`O_norc` 5, `nss` 5; D34, all kept). Offenders by occurrence, `O_norc`:
  launchd 3, spotlightknowledged.updater, Siri AI, photolibraryd, mobileassetd; `nss`: launchd 2,
  mediaanalysisd 2, PerfPowerServices, runningboardd, spotlightknowledged.updater,
  IntelligencePlatformComputeService, biomesyncd, airportd. No `claude` offender, nothing excluded.

## Per seed

`F` = flagged. Pair order: base first on odd seeds. Walls and `d` in s; `d` = `O_norc` − `nss`.

| seed | first | wall O_norc | wall nss | d | flag O_norc / nss | sim time O_norc / nss | evacuated O_norc / nss |
|------|-------|-------------|----------|---|-------------------|-----------------------|------------------------|
| 1 | O_norc | 33.67 | 29.91 | 3.76 | F / F | 400.00 / 313.53 | 199 / 200 |
| 2 | nss | 34.08 | 31.44 | 2.64 | - / F | 400.00 / 351.67 | 197 / 200 |
| 3 | O_norc | 33.89 | 32.14 | 1.75 | F / F | 362.98 / 303.42 | 200 / 200 |
| 4 | nss | 33.73 | 30.55 | 3.18 | F / - | 400.00 / 321.59 | 198 / 200 |
| 5 | O_norc | 32.29 | 29.87 | 2.42 | F / - | 400.00 / 381.81 | 198 / 200 |
| 6 | nss | 33.67 | 30.14 | 3.53 | - / - | 400.00 / 369.87 | 197 / 200 |
| 7 | O_norc | 35.32 | 32.93 | 2.39 | - / - | 400.00 / 321.94 | 197 / 200 |
| 8 | nss | 35.00 | 31.25 | 3.75 | - / F | 400.00 / 321.61 | 197 / 200 |
| 9 | O_norc | 35.58 | 31.66 | 3.92 | F / F | 400.00 / 317.43 | 199 / 200 |
| 10 | nss | 33.35 | 30.38 | 2.97 | - / - | 400.00 / 334.01 | 197 / 200 |

Table: `results/g6/paired_removal_G6_nss_W1_nss.csv` (`attribute.py --paired-removal G6_nss_W1 --arm nss
--counters-block G6_ctr_W1 --out results/g6`).

**D41** fix_first: `median_d_s` 3.073 s, `iqr_d_s` 1.341 s, `diff_per_study_s` 30.730 s, `sum_d_s` 30.292 s,
`d_us_per_agent_step` 0.943 µs (median `O_norc` agent-steps 3,259,925), ten seeds, none dropped.

G3b measured 47.18 s per study at `8f7d29a2` (4.72 s per run, five reps of seed 1); G6 measures 30.73 s at
`d96894ac` (ten seeds, another day). Different stage and day; the gap is consistent with the memo having
removed part of the sampler volume, not a measurement of it. 30.73 s is above the 23 s bar (D32).

## Run length

The `nss` arm changes trajectories: all ten `nss` runs finish with 200/200 evacuated, between 303.42 s and
381.81 s of simulated time, while `O_norc` runs to the 400 s window with 197–199 of 200 evacuated on nine
seeds (seed 3 completes at 362.98 s with 200/200). The saving therefore mixes removed lookups with a
shorter simulation, as in G3. The per-agent-step figure divides by the `O_norc` agent-steps and `d` also
contains the shorter simulation, so it is an upper bound for the lookup cost alone.

Seed 1 is the only seed with agent-step counts: `nss` removes 21.6 % of the iterations (31,353 against
40,000) but only 2.9 % of the agent-steps (3,165,697 against 3,259,925). Scaling its saving to equal
agent-steps (G3 method) gives 25.6–28.7 s per study depending on the source of the walls (timed pair,
counters loop timer, counters walls), still above the 23 s bar by 2.6–5.7 s. This correction covers seed 1
only; the ten-seed median cannot be corrected this way.

## What follows

Per design decision 6: `fix_first` leads to a fix plan for #242 (a bounded per-point index memo on
`SliceFieldSampler.sample`, after the #239 rule), with its own ten-seed measurement. Nothing is written to
GitHub by this plan.

## Caveats

- One host, one rep per seed, abba across seeds. Tie rule: `|median| ≤ IQR` (exclusive quartiles of the ten `d`).
- Flagged runs stay in the medians (D34): 10 of 20 timed reps, five per arm.
- The counters runs (`G6_ctr_W1`) are diagnostic and give only the agent-step count.
- The stub returns ambient values, so `nss` is not a model of the simulation.
