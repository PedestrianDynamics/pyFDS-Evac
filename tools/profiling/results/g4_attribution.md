# G4: what a route-sample memo can save on a ten-run W1 study (#243)

Date 2026-10-17. G3 removed rerouting from W1 and saved 17.46 s per run, 174.57 s per ten-run study (`nrr`, `results/g3_removal.md`), against the bar of 23 s per study (D32). This report bounds, before any fix is built, how much of that a memo on the route-sampling reads could remove: one instrumented W1 run times each path under `evaluate_segment` and `_first_leg` and counts, per path, the reads that repeat a key a memo would use. Counts are deterministic; timers are diagnostic.

## The run

- Run `G4det_W1_O_norc_det_s1_rep1_20261017T183958` (`results/raw/`, ignored by git), block `G4det`, case W1, variant `O_norc`, seed 1, `--shared`, `--label diagnostic`; manifest `measurement_status` `not_a_measurement`, exit 2 `incomplete_time_limit` (W1's normal outcome). It is the only attempt (`results/blocks/g4_runs.md`).
- Command: `$PY benchmark.py run --shared --block G4det --case W1 --variants O_norc --seeds 1 --instrument detail --warmup 0 --reps 1 --label diagnostic`; `counters.json` sha256 `4903b70f7153…`.
- Wall 54.10 s (`time_l.txt` 54.09 s real) against 36.21 s for the plain run: the detail group walks stack frames per call and the wrapper calibration adds about 0.4 s at install. No timed path is a measurement of the plain run.
- Host: manifest `contaminated` true (`(top)` 27.1 %, `launchd` 29.7 %), no `claude` offender. Shared host, so the seconds are diagnostic; the counts do not depend on it.
- Wrapper overhead: `route_paths_overhead` = 1,000,000 no-op wrapper calls in 0.0726 s, 0.0726 µs per call. `overhead_s` is calls × that, subtracted before `avoidable_s`; it sums to 0.13 s over all paths. The detail group's own work inside the timers (stack walks, key building, 5.9 s on `step_los_stats` alone) is measured and already left out of `seconds` (`hook_seconds` in `counters.json`).

## Table (`results/g4/route_paths_G4det.csv`, `$PY attribute.py --route-paths G4det --out results/g4`)

| Path | calls | net s | total | distinct | hit share | avoidable s | per ten-run study s |
|---|---|---|---|---|---|---|---|
| `evaluate_segment` | 62,499 | 4.490 | | | | | |
| `first_leg` | 193,879 | 5.810 | | | | | |
| `cell_los_stats` | 265,829 | 6.173 | | | | | |
| `step_los_stats` | 85,576 | 4.643 | | | | | |
| `read_cells` | 475,368 | 3.579 | 475,368 | 247,342 | 0.480 | 1.717 | 17.17 |
| `line_parts` | 265,829 | 0.693 | | | | | |
| `sample_fed_rate` | 410,667 | 5.462 | 410,667 | 144,644 | 0.648 | 3.538 | 35.38 |
| `sample_route` | 90,478 | 0.409 | 90,478 | 1,531 | 0.983 | 0.402 | 4.02 |
| `remainder` | | 0.704 | | | | | |
| TOTAL | | 10.300 | | | | 5.656 | 56.56 |

Paths nest and are reached from several parents, so the `net s` column must not be summed. TOTAL `net s` is `evaluate_segment` + `first_leg`; its avoidable columns sum the three keyed paths, which do not overlap. `remainder` is the `self_seconds` of `evaluate_segment` (time no timed path covers) less its wrapper overhead; subtracting the flat seconds of its children would be wrong, because `cell_los_stats` is also reached from `first_leg` (3.60 of its 6.19 s) and `step_los_stats` and most of `sample_fed_rate` run outside `evaluate_segment` altogether. No set reached the 2,000,000 cap (`capped` false in all three rows).

Where the keyed time sits (`by_parent` in `counters.json`): `read_cells` is entirely under `cell_los_stats`; `sample_fed_rate` has 1.16 s under `evaluate_segment` and 4.33 s under `step_los_stats`, which is called with no timed parent (4.64 s, outside `evaluate_segment` and `first_leg`); `sample_route` is almost all under `first_leg`. Timed route time, gross: `evaluate_segment` 4.49 + `first_leg` 5.82 + `step_los_stats` 4.65 = 14.97 s of the 17.46 s that G3 removed.

## Bound

A memo on the keyed paths can save at most 56.6 s per ten-run study on W1 (5.66 s per run; `sample_fed_rate` 35.4, `read_cells` 17.2, `sample_route` 4.0), against the bar of 23 s and the `nrr` bound of 174.6 s. It is an upper bound: it assumes a repeated read costs as much as the average read, charges nothing for the lookup, and takes keys as exact floats and frame tuples as in the design.

Not avoidable by a memo: `remainder` 0.70 s, `first_leg` own time 1.13 s (`self_seconds`), `cell_los_stats` own time 2.58 s, `step_los_stats` own time 0.32 s and the non-repeating share of the keyed paths, about 9.3 s of the 14.97 s per run. That is the ceiling for "cheaper samples" work (#242) on the route side.

## Caveats

One seed on a contaminated shared host; timers are diagnostic and carry detail overhead (54 s against 36 s plain); the hit share applies to path time on the assumption of equal cost per call; the memo's own cost is not charged; `sample_fed_rate` carries 28.0 of its 35.4 s per study under `step_los_stats`, whose caller outside `evaluate_segment` and `first_leg` is not timed here and a fix plan has to locate; the run is a diagnostic and feeds no summary (`G4det` is in `RECORD_ONLY_BLOCKS`, `results/summary*.csv` untouched).

## Proposed D39 (the maintainer decides)

- Bound 56.6 s ≥ 23 s: start the follow-on fix plan in a pyFDS-Evac worktree (#239 lowest-index fix, memo on `sample_fed_rate` first, then `read_cells`, ten-seed slot).
- Bound below 23 s: close #243 towards #242 and the remainder, record the bound on the issue.

The measured bound lies in the first branch; this report does not choose.
