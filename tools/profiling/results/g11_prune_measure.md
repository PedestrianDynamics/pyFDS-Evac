# G11: what the exit-reach prune saves on W1 (#429)

2026-10-18. The G3 `nst` arm bounds the exit-test cost at 28.69 s per ten-run study (it replaces the stage polygon
test by the point-distance test; a ceiling, not a fix saving). The pyFDS-Evac branch `perf/429-exit-reach-prune` at
`f7efcf9b` rejects a far agent from the exit polygon's cached bounds before building a shapely Point. G11 measures
that change itself: `O_norc` (pruned) against `nrp` (the pre-change `reached_stage` patched in by the wrapper) on the
same stage, ten paired seeds, one exclusive slot. Both arms follow the same trajectory and differ only in the exit
test.

## The slot

- `g11_all.sh` ran 16:28:46Z to 16:52:34Z on 2026-10-18 (elapsed 1428 s; `results/blocks/g11_status.tsv`, driver log
  `results/blocks/g11_all_20261018T162846Z.log`), stage `wt_f7efcf9b`, commit `f7efcf9b25b9…`.
- Blocks: `G11_pr_W1` (40 runs, 20 timed: 10 `O_norc`, 10 `nrp`, abba across seeds, warm-up 1) and `G11_ctr_W1`
  (4 counters runs, diagnostic); both `rc=0`, 44 manifests.
- sha256 in all 44 manifests: `benchmark.py` `61e2fa447e21…`, `instrument/perf_run.py` `574736824993…`; `attribute.py`
  `81332998f928…` at the slot commit 82c73ce; the table was written by `32e14b81489a…` (Task 3).
- Flagged timed reps: 6 of 20 (`O_norc` 3, `nrp` 3; D34, all kept). Offenders, `O_norc`: launchd, airportd,
  WiFiAgent, sysmond; `nrp`: tccd, contactsd, suggestd, knowledge-agent, postersyncd, contactsdonationagent,
  spotlightknowledged.updater, runningboardd, PerfPowerServices, airportd, WiFiAgent. No `claude` offender among the
  timed and counters reps, nothing excluded. One warm-up (not a rep) carries a `claude` sample
  (`G11_pr_W1_W1_nrp_s1_warmup1_20261018T162916`); it does not enter the table.

## Per seed

`F` = flagged. `d` = `nrp` − `O_norc` (positive: the prune is faster). Walls and `d` in s. Pair order: `O_norc` first
on odd seeds.

| seed | first | wall O_norc | wall nrp | d | flag O_norc / nrp | outputs equal |
|------|-------|-------------|----------|---|-------------------|---------------|
| 1 | O_norc | 29.38 | 32.36 | 2.98 | - / - | yes |
| 2 | nrp | 30.85 | 31.79 | 0.94 | - / - | yes |
| 3 | O_norc | 30.30 | 31.90 | 1.60 | F / F | yes |
| 4 | nrp | 29.34 | 31.40 | 2.06 | - / - | yes |
| 5 | O_norc | 28.74 | 31.33 | 2.59 | F / F | yes |
| 6 | nrp | 30.15 | 31.44 | 1.30 | - / - | yes |
| 7 | O_norc | 32.01 | 33.26 | 1.25 | - / - | yes |
| 8 | nrp | 31.34 | 33.23 | 1.89 | F / - | yes |
| 9 | O_norc | 31.19 | 33.43 | 2.24 | - / - | yes |
| 10 | nrp | 30.05 | 32.13 | 2.07 | - / F | yes |

Table: `results/g11/paired_lookup_G11_pr_W1_nrp.csv` (`attribute.py --paired-lookup G11_pr_W1 --arm nrp
--counters-block G11_ctr_W1 --out results/g11`).

**D43** below_bar: `median_d_s` 1.976 s, `iqr_d_s` 1.042 s, `diff_per_study_s` 19.759 s, `sum_d_s` 18.909 s,
`d_us_per_agent_step` 0.606 µs (median `O_norc` agent-steps 3,259,925), ten seeds, none dropped.

`d` is positive on all ten seeds (0.94 to 2.98 s), about 6 % of a W1 run, and the median exceeds the IQR, so the
saving is not a tie. At ten runs per study it is 19.76 s, below the 23 s bar (D32). The G3 arm removed the test and
changed decisions; D43 changes only how the test is done and is a saving of the branch, so the two are not
subtracted (28.69 s is a ceiling, 19.76 s is what this branch delivers). For scale, D42 (G8, the lookup change merged
in PR #813) was 12.13 s per study.

## Equality

`exit.csv`, `rh.csv` and `fed.csv` of every pair were compared by sha256: equal on 10 of 10 seeds, so both arms
produced identical outputs and there is no run-length confounder.

## What follows

Per design decision 5: `below_bar` leaves the maintainer to decide between merging a small exact speed-up and
closing #429, quoting the G3 bound and D43. Nothing is written to GitHub and nothing is pushed by this plan.

## Caveats

- One host, one rep per seed, abba across seeds. Tie rule: `|median| ≤ IQR` (exclusive quartiles of the ten `d`).
  The spread is wide (0.94 to 2.98 s), so the 19.76 s per study is an estimate with that uncertainty.
- How close `below_bar` is: the per-run bar (23 s / 10 = 2.3 s) lies inside the interquartile range of `d` (exclusive
  quartiles 1.284 s and 2.326 s), and two of ten seeds exceed it (2.98 s, 2.59 s). The median `d` is 2.238 s where
  `O_norc` ran first and 1.891 s where `nrp` ran first (about 22.4 s and 18.9 s per study); that order split is as
  large as the 0.32 s per run between the median and the bar.
- Flagged runs stay in the medians (D34): 6 of 20 timed reps, three per arm.
- The stub restores `reached_stage` only: the arms differ only in `reached_stage`, and both enter through the
  wrapper, so the wrapper's own cost is in both.
- The counters runs (`G11_ctr_W1`) are diagnostic and give only the agent-step count.
- The micro-benchmark of the pyFDS-Evac plan `g10-429-fix` (far points 4.58 → 0.30 µs per exit test) is an estimate
  and not part of this verdict.
- One workload, W1: the share of far agents and the exit geometry are those of that case only.
