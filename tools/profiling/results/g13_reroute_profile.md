# G13: what the parts of rerouting cost on W1 at main after #814 (#243)

2026-10-18. D44 (G12) measured that switching rerouting off (`nrr`) saves 13.84 s per W1 run at `main` `b6dff31c`
(138.39 s per ten-run study, `fix_first`) but not which part is expensive. G13 profiles one W1 run with pyinstrument,
plain and profiled reps interleaved, and tabulates the inclusive time of every call path below the two rerouting entry
points, scaled to the plain wall. The shares are attribution evidence and upper bounds on what removing a part saves,
not fix savings (D32); the bar is 23 s per ten-run study.

## The slot

- `g13_all.sh` ran 19:43:49Z to 19:49:59Z on 2026-10-18 (elapsed 370 s; `results/blocks/g13_status.tsv`, driver log
  `results/blocks/g13_all_20261018T194349Z.log`), stage `wt_b6dff31c`, commit `b6dff31c1375…`; both invocations `rc=0`.
- Blocks: `G13_prof_W1` (6 runs: warm-up and two timed reps per arm, abba) and `G13_det_W1` (1 detail-counters run);
  7 manifests. Profiler venv `venv_prof_b6dff31c` (pyinstrument 5.1.3), passed as `--prof-py`.
- sha256 at the slot commit (`08884b0`): `benchmark.py` `b933a0e1e54c…`, `instrument/perf_run.py` `574736824993…`
  (both in all 7 manifests), `instrument/perf_counters.py` `c23f04a8ecf5…`, `attribute.py` `32e14b81489a…` (this task
  adds `--reroute-tree`; `813757c0456…` at the task commit).
- Flagged timed reps (D34, all kept): plain rep 1 (WiFiAgent), pyinstrument rep 1 (fseventsd, 36.7 % CPU) and rep 2
  (spotlightknowledged.updater, 315.5 % CPU; AddressBookSourceSync); plain rep 2 is clean. The detail run (launchd,
  dataaccessd) and the profiled warm-up (launchd) are flagged too. `claude` offenders: none. The profiled walls differ
  by 2 % and the shares by at most 0.38 points, so both reps are trusted.
- Walls (medians of two reps): plain 30.80 s (30.98, 30.61), profiled 71.91 s (71.16, 72.65); pyinstrument adds 41.1 s,
  a factor of 2.34; profile times are scaled by 30.80 / 71.91 = 0.428 to plain-run seconds.

## The two entry points

`results/g13/reroute_tree_G13_prof_W1.csv`, depth-0 rows (56 rows; deeper rows need a median share of at least 1 %).

| Entry point | cum_s (profiled) | share of profiled wall | cost_plain_s | cost_per_study_s | verdict |
|---|---|---|---|---|---|
| `evaluate_and_reroute` (`route_graph.py`) | 23.12 | 32.2 % | 9.90 | 99.02 | above_bar |
| `_assign_initial_exit` (`scenario.py`) | 0.20 | 0.28 % | 0.09 | 0.85 | below_bar |

D44 `nrr` for comparison: 13.84 s per run, 138.39 s per study. The profile total below the entry points is 9.99 s per run,
72 % of that. They measure different things: the removal also drops what rerouting triggers (different routes change what
agents do afterwards) and changes the trajectories, while the profile counts only the frames below the two entry points.
In the other direction the profile scales by a uniform factor, while pyinstrument's overhead grows with call count and
rerouting is call-heavy, so `cost_plain_s` may over-state its part. Treat 9.9 s as the call-tree cost (the upper bound for
a behaviour-keeping fix) and 13.8 s as the ceiling of removing rerouting (trajectories change).

## Ranked parts

Call paths down to depth 3 (`cost_plain_s` in s per run, `cost_per_study_s` in s per ten-run study; `agreement_pts`,
the spread of the share over the two profiled reps, is at most 0.38 points on every row). Paths nest, so rows are not
additive.

| Path below `evaluate_and_reroute` | depth | cost_plain_s | cost_per_study_s | verdict |
|---|---|---|---|---|
| (entry point itself) | 0 | 9.90 | 99.02 | above_bar |
| `rank_routes` | 1 | 8.51 | 85.07 | above_bar |
| `rank_routes > measure` | 2 | 5.10 | 51.00 | above_bar |
| `rank_routes > measure > _measure_route` | 3 | 4.81 | 48.08 | above_bar |
| `rank_routes > _generate_candidates` | 2 | 3.17 | 31.70 | above_bar |
| `rank_routes > _generate_candidates > _first_hops` | 3 | 2.94 | 29.35 | above_bar |
| `_decide_same_exit` | 1 | 1.26 | 12.64 | below_bar |
| `_decide_same_exit > evaluate_route` | 2 | 1.20 | 12.00 | below_bar |
| `_decide_same_exit > evaluate_route > _measure_route` | 3 | 1.11 | 11.07 | below_bar |

Largest deeper rows, each below the bar as a single row: `… > _measure_route > evaluate_segment` 20.47, `… > _first_hops > _first_leg_dose`
14.47, `… > _measure_route > _first_leg` 13.57, `… > _first_hops > _first_leg` 12.79 per study. `_assign_initial_exit` has
no row below depth 0 at 1 %.

Reading: rerouting is almost entirely `rank_routes` (8.51 of 9.90 s per run); route measurement is about 1.6 times
candidate generation and the same-exit decision is small. Below `_measure_route` the time spreads over
`evaluate_segment`, `_first_leg` and shared callees (`read_cells`, FED-rate sampling) that have a row under each path, so
no one row shows their total; the route-path table counts per function.

Per-function totals across paths (s per ten-run study; sum of the CSV rows of the function at its outermost occurrence
on each path, so the inner `read_cells > read_cells` recursion is not counted twice): `_polyline_stats` 60.2 (5 paths),
`_measure_route` 59.2 (2 paths), `_los_stats` 52.3 (5), `_first_leg` 33.3 (3), `_cell_los_stats` 32.8 (4),
`_read_part` 29.8 (4). Each is above the 23 s bar as a sum over several call paths. They are lower bounds, because rows
under 1 % are absent, and they nest (`_los_stats` sits inside `_polyline_stats`, `_read_part` inside `_cell_los_stats`),
so they are not additive. They are attribution evidence and upper bounds on savings, not a recommendation.

## Route paths at main

`results/g13/route_paths_G13_det_W1.csv`, one detail run (diagnostic, wall 46.4 s against 30.8 s plain), next to the
pre-fix table (`results/g4_attribution.md`, `8f7d29a2`).

| Path | calls | net s G13 | net s G4 | distinct | hit share |
|---|---|---|---|---|---|
| `evaluate_segment` | 62,499 | 3.753 | 4.490 | | |
| `first_leg` | 193,879 | 5.844 | 5.810 | | |
| `cell_los_stats` | 265,829 | 6.362 | 6.173 | | |
| `step_los_stats` | 85,576 | 2.019 | 4.643 | | |
| `read_cells` | 475,368 | 3.711 | 3.579 | 247,342 | 0.480 |
| `sample_fed_rate` | 410,667 | 2.019 | 5.462 | 144,644 | 0.648 |
| `sample_route` | 90,478 | 0.269 | 0.409 | 1,531 | 0.983 |
| `line_parts` | 265,829 | 0.719 | 0.693 | | |
| remainder | | 0.728 | 0.704 | | |
| TOTAL net s per run | | 9.596 | 10.300 | | |
| TOTAL avoidable s per study | | 33.53 | 56.56 | | |

Calls, distinct points and hit shares equal the pre-fix run (same workload, same repeats); the cost per call changed.
After the merged fixes (#812 FED-rate memo, #813 faster scalar point lookup, #814 prune) `sample_fed_rate` fell from 5.46
to 2.02 s, `step_los_stats` from 4.64 to 2.02 s, `evaluate_segment` from 4.49 to 3.75 s and `sample_route` from 0.41 to
0.27 s per run; the counters do not split the three fixes. `read_cells` (3.71 s, 48 % of 475,368 reads repeat) is
unchanged. The avoidable figure assumes every repeat costs the mean call. That held before the memo, not at `main`: the
memo key `(frames, x, y)` is the key of `distinct`, so most of the 64.8 % repeats of `sample_fed_rate` are memo hits
already and its 13.1 s per study is not open headroom. The open part is about `read_cells` 17.8 plus `sample_route` 2.6 =
20.5 s per study, below the bar; the 33.5 s total overstates it. These are detail-run seconds with wrapper overhead
subtracted, not plain-run seconds.

## D45

**D45** profile (G13, 2026-10-18): at `main` `b6dff31c` rerouting costs 99.02 s per ten-run study by profile
(`evaluate_and_reroute`, 32.2 % of the profiled wall; `_assign_initial_exit` adds 0.85 s) against D44 `nrr` 138.4 s.
Call paths above the 23 s bar: `evaluate_and_reroute` 99.02, `> rank_routes` 85.07, `> rank_routes > measure` 51.00,
`> … > measure > _measure_route` 48.08, `> rank_routes > _generate_candidates` 31.70, `> … > _first_hops` 29.35.
Everything else (`_decide_same_exit` 12.64, every row of depth 4 or more) is below the bar. Attribution evidence, upper
bounds, not savings; the maintainer chooses the next fix.

## What follows

- Rerouting is above the bar as a whole and through two parts of `rank_routes`: route measurement (51.0) and candidate
  generation (31.7). The same-exit decision and the initial exit choice are below the bar, and so is every single
  row of depth 4 or more.
- Per-row, the largest row below depth 3 is `evaluate_segment` at 20.47 s per study. Summed over call paths, the
  line-of-sight chain is above the bar: `_polyline_stats` about 60 s, `_los_stats` about 52 s, `_cell_los_stats` about
  33 s and `_read_part` about 30 s per study (see "Reading"; lower bounds, nested, not additive). One fix on that chain
  acts on several rows at once, so whether it can reach the bar is open. The open part of the repeated reads is about
  20.5 s per study in detail-run seconds with wrapper overhead subtracted (`read_cells` 17.8 plus `sample_route` 2.6;
  the memo already serves the `sample_fed_rate` repeats), below the bar. No fix is chosen here; the maintainer decides.

## Caveats

- One host, one stage, W1 only, two profiled reps; flagged reps kept (D34), three of four timed reps flagged. Native time
  (NumPy, shapely, fdsreader) lands on the calling Python frame. The route-path table is one diagnostic seed with the
  detail group's overhead (the profile is seed 1 too). The G13 blocks are record-only in `analyse.py`, never pooled.
