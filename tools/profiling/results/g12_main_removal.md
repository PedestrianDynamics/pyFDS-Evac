# G12: what removing rerouting and the slice lookups still saves on W1 at main after #814 (#243, #242)

2026-10-18. D39 bounded route sampling on W1 at 56.6 s per ten-run study before any fix (`sample_fed_rate` 35.4 s,
`read_cells` 17.2 s, `sample_route` 4.0 s, one diagnostic seed at `8f7d29a2`). PR #812 (FED-rate memo), #813
(slice lookup) and #814 (exit-reach prune) are merged. G12 runs two profiler-free removal arms at `main`
`b6dff31c`, each paired with `O_norc` over ten seeds: `nrr` (`--no-enable-rerouting`) and `nss` (every scalar
`SliceFieldSampler.sample` stubbed). They bound what rerouting as a whole and the scalar slice lookup still cost.
Both change trajectories, so they are ceilings, not fix savings, and they overlap. Sign convention:
`d_s = wall(O_norc) − wall(arm)`; positive means removing the mechanism saves time.

## The slot

- `g12_all.sh` ran 18:23:04Z to 19:02:44Z on 2026-10-18 (elapsed 2381 s; `results/blocks/g12_status.tsv`, driver
  log `results/blocks/g12_all_20261018T182303Z.log`), stage `wt_b6dff31c`, commit `b6dff31c1375…`, three invocations `rc=0`.
- Blocks: `G12_nrr_W1` (40 runs, 20 timed, no wrapper), `G12_nss_W1` (40 runs, 20 timed, `--via-wrapper`), `G12_ctr_W1`
  (6 counters runs, diagnostic); 86 manifests. abba across seeds, warm-up 1.
- sha256 at the slot commit (`d89fa27`): `benchmark.py` `b933a0e1e54c…` and `instrument/perf_run.py` `574736824993…`
  (both in all 86 manifests), `attribute.py` `32e14b81489a…` (unchanged by this task).
- Flagged timed reps: 14 of 40 (D34, all kept): `O_norc` 9 of 20 (4 in the `nrr` block, 5 in the `nss` block), `nrr` 1 of 10,
  `nss` 4 of 10. Offenders by rep count: launchd 10, airportd 3, WiFiAgent 2, spotlightknowledged.updater 2, and one
  each of deleted_helper, deleted, tccd, mobileassetd, cloudd, duetexpertd, BackgroundShortcutRunner,
  AddressBookSourceSync, contactsd, knowledge-agent.
- `claude` offenders: none among the 40 timed reps. One warm-up (`G12_nrr_W1_W1_nrr_s1_warmup1_20261018T182346`) carries a `claude` sample; warm-ups never enter the tables, so nothing was excluded.

## Per seed: rerouting (`nrr`)

`F` = flagged. Walls and `d` in s. First = variant run first within the pair.

| seed | first | wall O_norc | wall nrr | d | flag O_norc / nrr | sim time O_norc / nrr | evacuated O_norc / nrr |
|---|---|---|---|---|---|---|---|
| 1 | O_norc | 29.18 | 15.91 | 13.26 | - / - | 400.00 / 400.00 | 199 / 199 |
| 2 | nrr | 29.44 | 16.56 | 12.88 | F / - | 400.00 / 400.00 | 197 / 196 |
| 3 | O_norc | 31.42 | 15.71 | 15.72 | F / - | 362.98 / 362.98 | 200 / 200 |
| 4 | nrr | 30.62 | 16.38 | 14.25 | - / - | 400.00 / 400.00 | 198 / 198 |
| 5 | O_norc | 29.40 | 15.80 | 13.60 | - / F | 400.00 / 400.00 | 198 / 197 |
| 6 | nrr | 29.26 | 16.04 | 13.22 | - / - | 400.00 / 400.00 | 197 / 197 |
| 7 | O_norc | 31.50 | 16.06 | 15.44 | F / - | 400.00 / 400.00 | 197 / 197 |
| 8 | nrr | 31.60 | 16.84 | 14.76 | - / - | 400.00 / 400.00 | 197 / 196 |
| 9 | O_norc | 31.34 | 17.26 | 14.08 | - / - | 400.00 / 400.00 | 199 / 198 |
| 10 | nrr | 29.39 | 16.27 | 13.12 | F / - | 400.00 / 400.00 | 197 / 197 |

## Per seed: scalar slice lookup (`nss`)

| seed | first | wall O_norc | wall nss | d | flag O_norc / nss | sim time O_norc / nss | evacuated O_norc / nss |
|---|---|---|---|---|---|---|---|
| 1 | O_norc | 30.43 | 29.16 | 1.27 | - / - | 400.00 / 313.53 | 199 / 200 |
| 2 | nss | 30.62 | 28.66 | 1.96 | - / F | 400.00 / 351.67 | 197 / 200 |
| 3 | O_norc | 31.57 | 29.47 | 2.10 | F / - | 362.98 / 303.42 | 200 / 200 |
| 4 | nss | 30.09 | 28.00 | 2.08 | F / F | 400.00 / 321.59 | 198 / 200 |
| 5 | O_norc | 29.83 | 28.39 | 1.44 | F / - | 400.00 / 381.81 | 198 / 200 |
| 6 | nss | 29.88 | 28.22 | 1.66 | - / F | 400.00 / 369.87 | 197 / 200 |
| 7 | O_norc | 32.01 | 30.06 | 1.96 | F / - | 400.00 / 321.94 | 197 / 200 |
| 8 | nss | 31.96 | 29.10 | 2.86 | F / F | 400.00 / 321.61 | 197 / 200 |
| 9 | O_norc | 31.55 | 30.12 | 1.43 | - / - | 400.00 / 317.43 | 199 / 200 |
| 10 | nss | 29.71 | 28.09 | 1.62 | - / - | 400.00 / 334.01 | 197 / 200 |

## Verdicts

Both verdicts are the `verdict` column of the `ALL` row, produced by `_removal_verdict` (tie when |median| ≤ IQR with
exclusive quartiles; `fix_first` when 10 × median exceeds the 23 s bar of D32). Tables:
`results/g12/paired_removal_G12_nrr_W1_nrr.csv` and `results/g12/paired_removal_G12_nss_W1_nss.csv`; `n_seeds` 10, `n_seeds_dropped` 0.

**D44 nrr** fix_first: `median_d_s` 13.839 s (per run), `iqr_d_s` 1.729 s, `diff_per_study_s` 138.391 s, `sum_d_s` 140.328 s, `d_us_per_agent_step` 4.245 µs (3,259,925 agent-steps of `O_norc`, counters block).

**D44 nss** below_bar: `median_d_s` 1.808 s (per run), `iqr_d_s` 0.654 s, `diff_per_study_s` 18.078 s, `sum_d_s` 18.372 s, `d_us_per_agent_step` 0.555 µs.

## What is left

Ceilings per ten-run study, in s, next to the earlier figures (different stages, different quantities; G3/G3b: seed 1 × 5 reps, arm medians, via wrapper; G6/G12: ten paired seeds):

| Quantity | Before the fixes (`8f7d29a2`) | After the memo (`d96894ac`) | At main after #814 (`b6dff31c`, G12) |
|---|---|---|---|
| `nrr` ceiling (rerouting off) | 174.57 (G3) | not measured | 138.39 |
| `nss` ceiling (scalar lookups stubbed) | 47.18 (G3b) | 30.73 (G6, D41) | 18.08 |
| Route sampling bound (D39, one seed) | 56.6 | not measured | not measured |

Measured savings of the merged fixes, each on its own stage against its own baseline: D40 memo 27.8, D42 lookup 12.1,
D43 prune 19.8 s per study. They are not subtracted from the ceilings.

The two ceilings overlap and are not added: rerouting is the main caller of the sampler, so most sampler calls are inside what `nrr` removes
(the per-agent FED and smoke-speed updates and the initial exit ranking stay in both arms). Neither ceiling is what a fix would save, because each arm also removes the
work that the removed mechanism triggers and changes the trajectories.

## What follows

- `nrr` is above the bar: removing rerouting as a whole saves 138.39 s per study against 23 s, so rerouting as a whole is the next target on W1 if the maintainer wants a further speed-up. The numbers do not say which part of rerouting; the G4 route-path table (`results/g4/route_paths_G4det.csv`, `8f7d29a2`, quoted not regenerated) predates the memo and the lookup change.
- `nss` is below the bar: even removing every scalar lookup saves 18.08 s per study, so the scalar slice lookup family (#242) is closed on W1.
- The maintainer decides.

## Caveats

- One host, one rep per seed, abba across seeds; flagged runs are kept (D34).
- Tie rule: |median| ≤ IQR with exclusive quartiles; neither arm is near it.
- Both arms change trajectories. The sim times differ between arms (`nss` ends at 303–382 s against the 400 s window of `O_norc`; `nrr` equals `O_norc` on all ten seeds; the shorter `nss` runs inflate its `d`, so `below_bar` is conservative), so per-run walls are not like-for-like workload.
- The counters runs are diagnostic and carry no exit-test counters; `agent_steps_median` is the `O_norc` figure.
- W1 only; nothing here applies to W3, W1r or W4flow.
- The G4 path table is from before the fixes.
