# G8: what the faster slice point lookup saves on W1 (#242)

2026-10-18. D41 bounds the removal of every scalar `SliceFieldSampler.sample` at 30.73 s per ten-run study. The
pyFDS-Evac branch `fix/242-faster-point-lookup` at `62106002` replaces two `np.searchsorted` calls by `bisect` and
shares one lookup between samplers on equal grids. G8 measures that change itself: `O_norc` (new lookup) against
`nlk` (the pre-change `sample` patched in by the wrapper) on the same stage, ten paired seeds, one exclusive slot.
Both arms follow the same trajectory and differ only in the lookup.

## The slot

- `g8_all.sh` ran 11:15:30Z to 11:41:24Z on 2026-10-18 (elapsed 1554 s; `results/blocks/g8_status.tsv`, driver log
  `results/blocks/g8_all_20261018T111530Z.log`), stage `wt_62106002`, commit `621060020b84…`.
- Blocks: `G8_lk_W1` (40 runs, 20 timed: 10 `O_norc`, 10 `nlk`, abba across seeds, warm-up 1) and `G8_ctr_W1`
  (4 counters runs, diagnostic); both `rc=0`, 44 manifests.
- sha256 at the slot commit (f768606): `benchmark.py` `04d105730fb7…` and `instrument/perf_run.py` `2f7233120650…`
  (both in all 44 manifests), `attribute.py` `c075039338dc…` at f768606; the table was written by `81332998f928…` (Task 3).
- Flagged timed reps: 10 of 20 (`O_norc` 5, `nlk` 5; D34, all kept). Offenders by occurrence, `O_norc`:
  spotlightknowledged.updater 3, mediaanalysisd 2, launchd, eligibilityd; `nlk`: launchd 4, WiFiAgent 2,
  airportd, photolibraryd, spotlightknowledged.updater. No `claude` offender among the timed and counters reps,
  nothing excluded. Two warm-ups (not reps) carry a `claude` sample (`G8_lk_W1_W1_nlk_s1_warmup1_20261018T111614`,
  `G8_lk_W1_W1_O_norc_s5_warmup1_20261018T112458`); they do not enter the table.

## Per seed

`F` = flagged. `d` = `nlk` − `O_norc` (positive: the shared lookup is faster). Walls and `d` in s. Pair order:
`O_norc` first on odd seeds.

| seed | first | wall O_norc | wall nlk | d | flag O_norc / nlk | outputs equal |
|------|-------|-------------|----------|---|-------------------|---------------|
| 1 | O_norc | 33.28 | 34.25 | 0.97 | - / F | yes |
| 2 | nlk | 33.86 | 34.87 | 1.01 | - / - | yes |
| 3 | O_norc | 33.69 | 34.88 | 1.18 | - / - | yes |
| 4 | nlk | 32.78 | 33.97 | 1.20 | F / F | yes |
| 5 | O_norc | 31.85 | 33.08 | 1.23 | F / - | yes |
| 6 | nlk | 32.45 | 33.58 | 1.13 | F / F | yes |
| 7 | O_norc | 34.43 | 35.74 | 1.31 | F / - | yes |
| 8 | nlk | 34.13 | 35.45 | 1.32 | F / F | yes |
| 9 | O_norc | 34.51 | 35.75 | 1.24 | - / - | yes |
| 10 | nlk | 32.35 | 33.61 | 1.26 | - / F | yes |

Table: `results/g8/paired_lookup_G8_lk_W1_nlk.csv` (`attribute.py --paired-lookup G8_lk_W1 --arm nlk
--counters-block G8_ctr_W1 --out results/g8`).

**D42** below_bar: `median_d_s` 1.213 s, `iqr_d_s` 0.171 s, `diff_per_study_s` 12.130 s, `sum_d_s` 11.856 s,
`d_us_per_agent_step` 0.372 µs (median `O_norc` agent-steps 3,259,925), ten seeds, none dropped.

`d` is positive on all ten seeds (0.97 to 1.32 s), about 3.6 % of a W1 run, and the median exceeds the IQR, so the
saving is not a tie. At ten runs per study it is 12.13 s, below the 23 s bar (D32). D41 removed every lookup and
changed trajectories; D42 changes only how the lookup is done and is a saving of the branch, so the two are not
subtracted.

## Equality

`exit.csv`, `rh.csv` and `fed.csv` of every pair were compared by sha256: equal on 10 of 10 seeds, so both arms
produced identical outputs and there is no run-length confounder.

## What follows

Per design decision 6: `below_bar` leaves the maintainer to decide between merging a small exact speed-up and
closing #242, quoting D41, D42 and the numbers above. Nothing is written to GitHub and nothing is pushed by this
plan.

## Caveats

- One host, one rep per seed, abba across seeds. Tie rule: `|median| ≤ IQR` (exclusive quartiles of the ten `d`).
- Flagged runs stay in the medians (D34): 10 of 20 timed reps, five per arm.
- The stub patches `sample` only, so any cost of the `nlk` arm outside `sample` is in both arms; both arms enter
  through the wrapper, so its cost is in both.
- The counters runs (`G8_ctr_W1`) are diagnostic and give only the agent-step count.
- The micro-benchmarks of the pyFDS-Evac plan `g7-242-fix` (`sample` 1.98 → 0.76 µs per call; four species at one
  point 7.64 → 2.7 µs) are estimates and not part of this verdict.
- One workload, W1 with its six meshes: the grid pool and its sharing behave as on that case only.
- The table does not itself check the stage commit; all 44 manifests record `62106002`, and all 22 `nlk` runs
  (timed, warm-up and counters) record `stubs: ["nlk"]`.
