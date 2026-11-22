# Plan b17: what the C/VM2 ballroom run spends its time on

Measurement only. No production code, default or dependency changes, no FDS
runs, no merges. Run it serially on an otherwise quiet machine.

## Why

A cProfile of one ballroom run (seed 1, rerouting on, 1000 agents, 8:22 wall
under the profiler) is Python-bound. Inclusive shares of the profiled time:

| function | calls | inclusive |
|---|---|---|
| `route_graph._first_leg` | 1.40 M | 74 % |
| `route_graph._measure_route` | 0.82 M | 29 % |
| `scenario.sample_fed_rate` | 4.31 M | 17 % |
| `route_graph.sample_extinction` | 4.31 M | 17 % |
| `direct_steering_runtime.update_checkpoint_speed` | 28.8 M | 15 % |
| `fds_sampling.read_cells` | 4.16 M | 11 % |
| JuPedSim `wrap_iter` | 30.9 M | 4 % |

Inclusive times nest and cProfile inflates call-heavy code, so these are
diagnostic only. They point at rerouting and at call counts, not at the
language. An earlier Rust-port tool found nothing portable. This plan measures
what rerouting costs in plain wall time on this workload.

## Question

On the ballroom, how much plain wall time does rerouting cost per run, and what
does one run spend on sampling and steering?

## Setup

1. Work from `origin/main`. Record `git rev-parse HEAD` in `results.md`.
2. `uv sync --frozen`. Use `.venv/bin/python`, check with `which python`.
3. FDS data: the finished fire run, `cvm2-ballroom/fire/` (smv, `.out`,
   `cvm2_ballroom_hrr.csv`, the `cvm2_ballroom_<m>_<n>.sf` slices, 934 MB). It
   is not in the buildServer subset yet. If
   `$FDS_EVAC_DATA/cvm2-ballroom/fire/cvm2_ballroom.smv` is missing, stop and
   tell the maintainer to rsync that folder (no `*_evac*`, no `mc*`).
4. fdsreader refuses a folder holding the `_evac` and `_evmc` files, so stage
   the fire files alone:

   ```bash
   FIRE=$OUT/fire_only; mkdir -p $FIRE
   for f in cvm2_ballroom.smv cvm2_ballroom_hrr.csv cvm2_ballroom.out \
            cvm2_ballroom_[0-9]*_[0-9]*.sf; do
     ln -sf $FDS_EVAC_DATA/cvm2-ballroom/fire/$f $FIRE/$f
   done
   ```

5. `OUT=$FDS_EVAC_DATA/profiling-ballroom` (a new folder, so the laptop can
   rsync it back to sciebo).
6. Quiet host: record `nproc`, `uptime` and the busiest foreign processes
   (`ps aux --sort=-%cpu | head`) in `results.md`. If another user's work holds
   more than 4 cores, wait; do not start a block on a loaded host.

## Steps

**S0, smoke.** One run, seed 1, rerouting on, plain (no profiler):
`python plans/b17-ballroom-perf/bench.py run --fire $FIRE --out $OUT/s0 --seed 1 --reps 1`
(one base and one nrr run; both count toward the plain-wall estimate). Check the scenario
loads on this commit (unknown-key warnings are fine; errors are not) and the
run ends with the evacuation completed. Record plain wall. **Stop and report
if one run takes more than 20 min.**

**S1, block A (seed 1).** Warm-up plus five interleaved reps per variant:
`python plans/b17-ballroom-perf/bench.py run --fire $FIRE --out $OUT/A --seed 1 --reps 5 --warmup`
`python plans/b17-ballroom-perf/bench.py summary --out $OUT/A`

**S2, block B (seeds 2 and 3).** Three reps each:
`for s in 2 3; do python plans/b17-ballroom-perf/bench.py run --fire $FIRE --out $OUT/B --seed $s --reps 3 --warmup; done`
`python plans/b17-ballroom-perf/bench.py summary --out $OUT/B`

**S3, one profile (diagnostic).** Same command as S0 under cProfile, saved to
`$OUT/prof/ball.prof`, plus a text table of the top 30 by `tottime` and by
`cumtime` with call counts. Compare with the table above.

   ```bash
   python -m cProfile -o $OUT/prof/ball.prof .venv/bin/pyfds-evac \
     --scenario plans/b17-ballroom-perf/scenario --fds-dir $FIRE --seed 1 \
     --smoke-slice-height 2.0
   ```

Run S0 to S3 one after another. Run nothing else on the machine meanwhile.

## What to record (`$OUT/results.md`)

- Commit, `uv.lock` hash, Python version, host (`nproc`, RAM, load before and after).
- `bench.py summary` output for both blocks, all runs listed, none dropped. A
  failed or incomplete run stays in `runs.jsonl` and is reported.
- Agents spawned, evacuated and the termination reason per run (from `run.log`).
- Determinism: same seed and variant must give identical `exits_sha`. If not,
  say so and do not report a median as clean.
- Profile table from S3.

## Reading the result

- `base` against `nrr` is an end-to-end difference: rerouting off changes
  trajectories, crowding and exits. Label it a ceiling on what rerouting costs,
  not a per-subsystem cost, and never subtract it from other arms.
- Bar: 5 % of ten base runs (`0.5 x median base wall`, printed by the summary).
  Above the bar, rerouting is worth a fix plan. Below it, close the question.
- If the two medians lie within the larger IQR, call it a tie.
- A profile share is evidence for where to look, not a saving.

## Out of scope

- Exact-repeat counting of route walks (the earlier W1 study did this with
  counters outside this repository). Without them, caching ideas stay
  hypotheses. Add them only if S1 is above the bar.
- Any optimisation. Findings become issues or backend tasks after the maintainer
  reads `results.md`.

## Stop conditions

- A run exceeds 20 min, or more than one run in a block fails.
- The host load check fails twice in a row.
- The FDS data is missing or incomplete.

## Time

About 3 to 5 min per plain run (a guess; S0 measures it). Block A is about 12
runs, block B about 14, S3 about 8 min: roughly 2 to 3 h in total, serial.
Disk use is negligible apart from the 934 MB FDS copy.
