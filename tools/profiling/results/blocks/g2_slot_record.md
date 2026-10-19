# G2 slot record (2026-10-17, 11:48:49Z to 12:21:03Z)

Corrections and handoff facts for the Task 4 commit `c69036e`. The
commit message stays as written; where it differs, this file is
authoritative. Task 5 copies the facts below into the report and the
plan's G2 run record.

## cProfile runs exit 0 by construction

`python -m cProfile` swallows the script's `SystemExit`
(`profile._Utils.run/runctx`), so every cProfile run records
`exit_code 0` / `termination completed` in its manifest and `rc=0` in
`g2_status.tsv`. The outcome of a cProfile run is its
`outcome.summary_line`. Both `G2_rc_cprof_*` runs read "time limit
reached after 400.00 s (199/200 evacuated, 1 remaining)", the same as
the plain and pyinstrument W1 runs (`exit 2`, `incomplete_time_limit`).
They are valid like-for-like completions for the rc-diff.

Harness follow-up, routed and not done in this plan task: run cProfile
through a small wrapper that re-raises the script's exit code, or derive
`termination` from `outcome` when `profiler == "cprofile"`. Either
option changes the harness hash and needs a `README.md` §3 entry; a bad
input under `--profiler cprofile` would otherwise be recorded as a
completed run.

## cProfile call graph is truncated

Both `G2_rc_cprof_*` profiles lack the enclosing frames above
`rank_routes` (`run_scenario`, `run.py`, `cli.main`); 125 entries have
no caller in each, and the root cumulative times sum to 63.7 s against
94.7 s total (O_study) and 54.7 s against 75.1 s (O_norc). Inner call
counts match the counters. A likely cause is an exit through an
exception under `-m cProfile`, the same wrapper issue as above. The
rc-diff is reliable for location only; `attribute.py` no longer
requires a `run_scenario` row.

## Corrections to the commit message

- The `SLOT_RACE_RETRY` on W1_n100 (12:07:11Z) was caused by the
  session's own CLI: `claude` (pid 7010, child of `cc-driver/drive.py`)
  at 33.5 %, then 22 % at the next poll, while the session made no tool
  call. It fell between blocks, so no manifest is affected. An idle CLI
  can cross the 20 % threshold by itself; the next exclusive slot (G3)
  should expect this.
- "Rerun clean" is wrong: the rerun finished `rc=0`, but 3 of the 4
  W1_n100 runs after it are flagged (`mediaanalysisd` 100-108 %,
  `MenuBarAgent` 20.3 %).
- `analyse.py` also picked up the 38 `QA2_*`/`QA3_*` runs (8 groups) of
  the G1 perf-qa reproduction (07:07-07:52Z, before this plan). They
  were kept out of the tracked tables by QA on purpose; the rows are
  correct and stay. More than half of the `summary.csv` diff is not G2.
- Deviations from the brief in Steps 3-4: the driver was started in a
  subshell without `sleep 20; cat "$L"`, and the single wait was a
  `run_in_background` Bash loop (it also matched `ABORT`), not a Monitor
  call. Zero tool calls were made between 11:48:52Z and the task
  notification at 12:21:23Z.

## Flagged runs by group

17 of 32 runs are flagged by macOS processes; none by `claude` (own-
session check: 32 manifests, `claude offenders: []`). `claude` appears
below the 20 % rule in `recorded_max_pcpu` of 13 manifests at
5.5-12.9 % (the coordinator CLI, sometimes the implementer; in the two
W1 profiled reps at 5.8 % and 8.5 %).

`heavy` = samples with a foreign process above the limit, of all
samples during the run.

| Group | Flagged | Offenders (max %CPU) | heavy |
|-------|---------|----------------------|-------|
| `G2_prof_W3` pyinstrument | rep2 | launchd 36.7 | 1/9 |
| `G2_prof_W1` pyinstrument | warm-up, rep1, rep2 (profiled reps 2/2) | rep1: IntelligencePlatformComputeService 68.2, airportd 60.2, launchd 28.9; rep2: launchd 21.8, spotlightknowledged.updater 46.5; warm-up: runningboardd 68.0, PerfPowerServices 79.7, biomesyncd 32.0 | rep1 3/51, rep2 2/51, warm-up 2/51 |
| `G2_prof_W1` plain | warm-up | spotlightknowledged.updater 25.4 | 1/22 |
| `G2_prof_W4flow` pyinstrument | rep1 | duetexpertd 101.8 | 9/49 |
| `G2_prof_W4flow` plain | rep1 | WiFiAgent 32.3 | 1/32 |
| `G2_rc_cprof` O_study / O_norc | both | launchd 28.9; launchd 27.1, spindump 49.9 | 1/54, 1/43 |
| `G2_ctr_scale` W1 | rep2 | spotlightknowledged.updater 41.0 | 1/23 |
| `G2_ctr_scale` W1_n100 | warm-up, rep1, rep3 | mediaanalysisd 100-108; MenuBarAgent 20.3 | 4/10, 1/10, 1/10 |
| `G2_ctr_scale` W1_n400 | warm-up, rep1-3 (3/3) | launchd 21-49 | 1/57-58 each |

Under D31 these groups have `n_used 0` and `flag_status inconclusive`
in `results/summary_groups.csv` (that is contamination, not decision 4's
"profiled reps disagree by more than 2 points"): `G2_prof_W1`
pyinstrument (line 68), `G2_ctr_scale` W1_n400 (line 66), both
`G2_prof_W4flow` arms (lines 73-74), both `G2_rc_cprof` runs (lines 75-76).

The two W1 profiled reps have walls of 106.37 s and 105.60 s (0.7 %
spread); 2-3 of 51 samples were heavy in each. A second slot cannot
refill the block: the driver skips complete blocks and `results/raw`
may not be deleted. Whether daemon-flagged profiled reps may be used
for the shares (with these sample counts and the wall spread stated),
or whether a second slot under a new prefix is needed, is the
maintainer's decision; Task 5 reports shares from `summary_groups_all.csv`
with "n flagged of n" under the D31 rule (a) and states that it did so.
