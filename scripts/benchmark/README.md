# Benchmark harness for the runtime table

Re-runs the cases of the paper's runtime table on any commit of this
repository (for example the submission tag) and summarises wall time,
process-tree CPU, peak RSS and outcome per case.

## Requirements

- An exclusive machine: nothing else running simulations, tests, builds
  or updates while a batch runs. The harness records load and the busiest
  processes before and after every run, but does not enforce this.
- A clean checkout at the commit under test, with its environment synced
  (`uv sync --frozen`). The harness refuses to start unless `HEAD` is the
  requested commit, the tree is clean, and the child imports `pyfds_evac`
  from the checkout.
- For the FDS cases (W1a, W1a_minimal, W1a_n100, W1a_n400, W1b) the FDS
  data subset in `$FDS_EVAC_DATA`, with these directories:
  - `schroeder2015-route/rerun_796/a047_pvc_h40` (W1a family; the
    top-level `schroeder2015-route/a047_pvc_h40` is the older deck and is
    not used),
  - `cvm2-function-centre/evac/north` and `cvm2-function-centre/fds/f1`
    (W1b only).

  Paths may contain spaces; quote them. W2a and W3 need no external data
  (W3 uses the tracked extinction-only extract under `scripts/figures/data`).

## Commands

```
export FDS_EVAC_DATA="<path to the fds-evac-data directory>"
git worktree add ../bench-target <tag-or-commit>     # clean tree of the commit to time
(cd ../bench-target && uv sync --frozen)
scripts/benchmark/rerun_paper.sh --checkout ../bench-target \
    --commit <tag-or-commit> --outdir "$PWD/results-paper"
```

The harness is not part of older commits, so it is run from a checkout that
has it and times a second checkout of the commit named by `--commit`. The
child interpreter is the `.venv` of that second checkout. The harness runs
on Linux only (it reads `/proc` and reports `ru_maxrss` in KiB); on other
systems it stops before the first run.

- `--dry-run` prints the runs without executing them.
- `--with-w1b` adds `paper_table_w1b.json` (C/VM2, long).
- `--commit REV` names the commit the checkout must be at (default: its
  `HEAD`); the harness never checks anything out itself. `--checkout DIR`
  names the checkout to time (default: the repository of the script). Batch
  items cannot set `--commit`, `--checkout`, `--outdir` or `--python`.
- `PYTHON=<interpreter>` overrides the child interpreter (default:
  `.venv/bin/python` of the repository).
- Results never go inside `scripts/benchmark`; the default `--outdir` is
  `./benchmark-results`. Untracked files inside the results directory do not
  count against the clean-tree check, so a second run is not refused for the
  first one's output. Use a fresh directory per batch: a run id that already
  exists is refused.

Single runs and comparisons:

```
.venv/bin/python scripts/benchmark/benchmark.py run --case W3 --seed 42 \
    --rep 1 --kind first_use --outdir <dir>
.venv/bin/python scripts/benchmark/compare_outputs.py <dir>/raw/RUN_A <dir>/raw/RUN_B
.venv/bin/python scripts/benchmark/analyse.py --outdir <dir>
```

`compare_outputs.py` compares two runs without tolerance (all sqlite
tables, every CSV, outcome and seed, stdout without progress lines,
stderr, vis cache) and exits 0 only if EQUAL. In a batch, runs of the same
`group` are compared with the previous run of that group and the report is
written to `<outdir>/compare/`.

## Protocol

Every run is a fresh process (`PYTHONHASHSEED=0`, `TMPDIR` inside the run
directory). W1a, W2a, W3 reuse and W1b have one untimed warm-up; they have 5
repetitions (W1a, W2a, W3 reuse) or 2 (W1b). W1a_minimal, W3 first use,
W1a_n100 and W1a_n400 have no warm-up and 3 repetitions. W1a and W1a_minimal
alternate. The vis cache of W3 is a disposable file in the run directory;
for the reuse runs it is seeded from a copy of the first-use cache. Page
cache is not controlled. Exit status 2 is a valid outcome only when the run printed its
"Simulation incomplete" line (an argument error also exits 2 and counts as
`failed`); any other non-zero status or a kill at the
cap (900 s, W1b 3600 s) is recorded as `failed` or `cap_hit`, counted in
`n_failed` and never dropped.

The cases are in `cases.json`: argv, staged inputs, expected input sha256
values and cache state. W1a_n100 and W1a_n400 are the W1a deck with only
`distributions.jps-distributions_0.parameters.number` overridden in the
config copy staged into the run directory (`config_edits`; the repository
file is untouched). W1b stages the C/VM2 north config with its horizon cut
to 300 s the same way and writes smoke and FED histories. Expected input
hashes are checked and recorded in the manifest
(`input_fingerprints.input_sha256_check`); a mismatch, for example a deck
changed after 71b5fc76, is reported there and does not stop the run.

## Output

`<outdir>/raw/<run_id>/manifest.json` (command, environment probe, hashes,
wall, tree CPU, peak RSS, phases, outcome; missing values are null),
stdout and stderr, the case outputs; `<outdir>/summary.csv` (one row per
run); `analyse.py` adds `stats.csv`, `paper_table.md` (median, range, IQR
for n >= 4, n, peak RSS, outcome per case) and `runs_table.md` (every
run).

## Runtime

About 1 h for `paper_table.json` (W1a about 160 s, W1a_minimal 126 s, W2a
54 s, W3 20 s, W1a_n100 75 s, W1a_n400 427 s per run on the 1.0 study
machine). W1b adds about 2.5 h (three runs of about 47 min).

## Relation to the 1.0 study

The package `fds-evac-data/profiling-1.0/` (sciebo) holds the study at
commit 71b5fc76 with its numbers (`results/summary.csv`,
`results/stats_g1.csv`, `report.md`, `appendix.md`). This harness is the
plain-run part of that study's `benchmark.py`, `compare_outputs.py` and
`analyse.py`, with the measurement method, manifest fields, cap handling,
exit-2 rule and comparison semantics unchanged. At 71b5fc76 the paths
of its tracked inputs are identical, so a re-run there should reproduce the
study's medians on the same machine.

Not included: the opt-in instrumentation (work counters, loop timers,
ranking trace) and the profiler passthroughs (py-spy, cProfile, memray).
The loop breakdown of the 1.0 study used them; they are diffs against
71b5fc76 only (`instrumentation_counters_g1.diff`,
`instrumentation_g2.diff`) and live, with the profiles, in
`fds-evac-data/profiling-1.0/`. Case names differ in one place: W1b here is
the study's `W1b_activation` template (the measured one). Manifest fields
`instrumentation_*`, `profiler_state` and `environment_json_sha256` are not
written; `scenarios_json_sha256` is `cases_json_sha256` and
`harness.frozen_commit` is `harness.commit`.
