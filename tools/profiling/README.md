# pyFDS-Evac profiling package

What makes a representative coupled pyFDS-Evac study expensive.
- Spec: `~/.claude/docs/profiling_team.md` (v2).
- Scope, gates and limits: `plan.md`.
- Workloads: `scenarios.json` and `model_handoff_g0.md`.

Every command below was run as written. `$STUDY` is this directory.

## 1. Environment (recreate from scratch)

```bash
FDSEVAC=/Users/chraibi/workspace/PedestrianDynamics/Fire/fds_visibility/pyFDS-EVAC   # any clone of pyFDS-Evac; never `git checkout` in it
P=/Users/chraibi/profiling-stage                                                  # durable location, outside the clone
COMMIT=8f7d29a2e056db46183e8cccabce338c398606a1   # main after PR #790

git -C "$FDSEVAC" worktree add --detach "$P/wt_8f7d29a2" $COMMIT
cd "$P/wt_8f7d29a2"
UV_CACHE_DIR="$P/uvcache" uv sync --frozen --python 3.12            # baseline venv: $P/wt_8f7d29a2/.venv
UV_CACHE_DIR="$P/uvcache" UV_PROJECT_ENVIRONMENT="$P/venv_prof_8f7d29a2" uv sync --frozen --python 3.12
UV_CACHE_DIR="$P/uvcache" uv pip install --python "$P/venv_prof_8f7d29a2/bin/python" \
    py-spy==0.4.2 scalene==2.3.0 memray==1.20.0 pyinstrument==5.1.3   # profiler venv, same lock
shasum -a 256 uv.lock      # 7f64a58db6d321441e320ad47ba960dc51d25c4a8dbaff8e8d95ba09fac25fc8
```

Notes on the environment:
- **Python.** CPython 3.12 (pyproject allows >=3.12,<3.15). The lock at this commit resolves scikit-image 0.26.0 (the v0.2.0 lock resolved 0.23.2).
- **Profiler venv.** It imports `pyfds_evac` from the same `wt_8f7d29a2` source as the baseline venv.
- **Inventory.** `$PY $STUDY/collect_env.py "$P/wt_8f7d29a2" $STUDY/environment.json --profiling-python "$P/venv_prof_8f7d29a2/bin/python"` writes `environment.json`.
- **Paths.** The durable paths are wired as defaults in `benchmark.py`, `g1_all.sh` and `launch_detached.sh`. Elsewhere, set `PROF_WT`, `PROF_PY`, `PROF_PROFILER_PY` and `PROF_STAGE` (or `--wt`, `--py`, `--prof-py`, `--stage`); `COMMIT` and `LOCK_SHA256` in `benchmark.py` must match the worktree.
- **Re-freezing.** Remove with `git -C "$FDSEVAC" worktree remove --force "$P/wt_8f7d29a2"` only when the study is finished. Never edit files inside the worktree: `benchmark.py` refuses a dirty tree.

## 2. FDS data (never read from sciebo during runs)

```bash
SB="/Users/chraibi/sciebo - ped23 (ped23.pbox@fz-juelich.de)@fz-juelich.sciebo.de/fds-evac-data"
ST=/Users/chraibi/profiling-stage            # fixed path: the vismap cache metadata stores the resolved fds_dir
mkdir -p $ST/fds $ST/cache
rsync -a --exclude '*.pickle' "$SB/schroeder2015-route/a047_pvc_h40/" $ST/fds/a047_pvc_h40/
rsync -a --exclude '*.pickle' "$SB/t_junction/fire_2MW_PVC/"          $ST/fds/t_junction_fire_2MW_PVC/
rsync -a --exclude '*.pickle' "$SB/cognitive_map_memory/clear_air/"   $ST/fds/cmm_clear_air/
rsync -a --exclude '*.pickle' "$P/wt_8f7d29a2/assets/iso_table21_coupled/fds/" $ST/fds/iso_table21_coupled/
for c in a b c d; do rsync -a --exclude '*.pickle' "$P/wt_8f7d29a2/assets/iso_table22_coupled/fds/$c/" $ST/fds/iso_table22_$c/; done
$PY $STUDY/verify_stage.py $ST $STUDY/results/stage_verification_v2.json   # must print OK for all 8
```

Here `$PY` is `$P/wt_8f7d29a2/.venv/bin/python`. If sciebo is unreachable, the per-file sha256 values in `preflight/input_hashes.json` define the expected files.

## 3. Benchmark harness

`benchmark.py` runs blocks serially, with one fresh process per run. Its docstring gives the timing, phase and cache-state definitions.

Harness hash (manifests record `benchmark.py` sha256): `5889679487ec036787669221a38cc36c68a8ea6357059ab1fbc1df473eb852c0` up to 2026-10-17 (166 G1* manifests; earlier ones carry `ac2c3c2194` or `43a1e0b024`); `ab19ce4df112f08fc8a864c88fd091bae37793589e83809f2b3ce6f867d38385` from 2026-10-17 (D31 follow-ups: offender class by name, OS build and boot time in `manifest["os"]`; measured path unchanged); `7084570ebc0eb493e0c7c8f189955f8ad6e440c5b573c2478a2857944dee46c0` from 2026-10-17 (G2 Task 1: `--profiler` comma list interleaved like `--instrument`, per-run `profiler` in the manifest, `_pyi`/`_cpr`/`_scl`/`_mem` run-id tags; plain measured path unchanged). `03d639d0e2e378e94512106614a6a0a6bd7befaf0341bc6ae0316f90c3151f21` from 2026-10-17 (G2 Task 2 review fix: the pyinstrument head carries `-p processor_options.filter_threshold=0` so no frame is pruned; plain measured path unchanged). `01bdbec869551e246998693c46c998be1552ba3b5a66fb4a45830ba7d446eb23` from 2026-10-17 (G2 Task 5 follow-up: case `W1_nrr`, W1 with `--no-enable-rerouting`, variant `nrr`; plain measured path unchanged). `58eec7f447244ffc0e1c4d79f9c836b6217e4570d39ccd151e1297417167ecc4` from 2026-10-17 (G2 Task 6 review fix: `nrr` is a variant of case `W1` instead of the case `W1_nrr`, so `--case W1 --variants O_norc,nrr` interleaves both arms; plain measured path unchanged). `6aa81e896b98434a6454cfcb5cc05dbdcbc8ac7cf8d4836138a1e8fbb3faf703` from 2026-10-17 (G3 Task 1: W1 variants `nss`, `nst` with env `PYFDS_PERF_STUB`, run flag `--via-wrapper`, manifest `instrumentation.stubs`; plain measured path unchanged). `0e4697d3579787688a64feff5fecdc0ad2ea7c2282f94a7f22068a4697e097b0` from 2026-10-17 (G3 Task 1 review fix: `--via-wrapper` with `--profiler` is refused; plain measured path unchanged). `536db325abef41ab589fc7aa4c8639d62bed7fd86d9667871b52bcea30441860` from 2026-10-18 (G5: per-stage pin table `STAGES`, W1 variant `nomemo` with `variant_scenario`, `abba` alternating across seeds, `PYFDS_PERF_MEMO_LOG` for counters runs; the baseline stage's plain measured path is unchanged). `c6a162ff1d5eb736bb22ee124acf8a4255c71a28258494298b583b8edb78b8b8` from 2026-10-18 (G6: stage pin `wt_d96894ac`, `main` after PR #812; the baseline stage's plain measured path is unchanged). `04d105730fb71ecc7bbb12f571cd0f1ba285e0ebfbe8764daf097dec877df42b` from 2026-10-18 (G8: stage pin `wt_62106002` and variant `nlk`; the baseline stage's plain measured path is unchanged). `61e2fa447e2153005bbc10eb984e8ea7a5ce186de2b5a57f47a76960dc74d869` from 2026-10-18 (G11: stage pin `wt_f7efcf9b` and variant `nrp`; the baseline stage's plain measured path is unchanged). `b933a0e1e54c389f7145600ea21bd9d9cb1c73bafa3bd3e436cc0edb0e24fb40` from 2026-10-18 (G12: stage pin `wt_b6dff31c`, `main` after PR #814; the baseline stage's plain measured path is unchanged).

```bash
cd $STUDY
$PY benchmark.py check                                   # exclusive-slot check (JSON)
$PY benchmark.py run --block B --case W1 --exclusive --dry-run   # print the plan, change nothing
```

Every `run` must pass exactly one of `--exclusive` or `--shared`:

- **`--exclusive`** marks a measured block. The slot check must pass first: 1-min load < 1.5; no process outside the benchmark's own process tree (itself, the run under test, its `ps` calls and its parent, e.g. `caffeinate`) above 20 % CPU, whatever its name; the macOS system processes `WindowServer`, `kernel_task`, `mds`, `mds_stores`, `mdworker*`, `syspolicyd` and `airportd` flag only above 50 % (`plan.md`, "System processes during measured blocks"); AC power; low-power mode off. Otherwise the block does not start.
- **`--shared`** marks development runs. Their `measurement_status` is `not_a_measurement`, and they never enter statistics.

Contamination is judged per run from the slot check before, `ps` samples every 2 s during, and the slot check after. The same rule applies to every sample. Limits of the rule:
- `ps` %CPU on macOS is a decaying average (the BSD scheduler estimate, roughly the last minute), not an instantaneous rate. It can flag a process that went idle just before a run, and it smooths over short bursts during it. Sampling every 2 s does not change this (review O10).
- `kernel_task` (pid 0) is not listed by `ps` for a non-root user on this host, so it is never recorded.

Each sample records every process on the system list and any other process at or above 5 %; `recorded_max_pcpu` gives the per-process maximum. `contamination_reasons` lists `foreign_heavy_before/during/after`, `load1_before` and `power`, and `offenders_max_pcpu` gives each offending process name with its highest %CPU. `load1_before` may be self-load from the previous serial run (review F4); the first exclusive block checks this, and any rule change goes into `plan.md`.

Phases come from stdout markers (review F2):
- `phase_pre_run_s` covers imports, config, `build_run_kwargs`, the FDS inventory and horizon, the samplers, and the vismap build or load.
- `phase_run_scenario_s` is the whole `run_scenario`: JuPedSim setup, spawning, the initial route choice, the loop and the temporary SQLite.
- `phase_post_run_s` covers the output copies.

The time loop alone is timed in-process only in counter runs (`counters.json` `timers_s`), which are diagnostic.

Fixed child environment: `PYTHONHASHSEED=0`, `PYTHONUNBUFFERED=1`, `OMP_NUM_THREADS=4` (the maintainer's shell value), `VECLIB_MAXIMUM_THREADS` unset (Accelerate default; NumPy uses Accelerate, which ignores OMP), and `TMPDIR=$STAGE/tmp/<run_id>`.

Cases are `W1`, `W1_n100`, `W1_n400`, `W1_add`, `W1_sb`, `W1r`, `W2`, `W3`, `W3b_cmm`, `W4_iso21` and `W4_flow_saturated`. W1 output variants are `O_study` (normal), `O_norc`, `O_min`, `nrr` (`O_norc` with rerouting off, removal experiment), `nss` (`O_norc` with `SliceFieldSampler.sample` stubbed; route line-of-sight still reads the slice), `nst` (`O_norc` with `reached_stage` reduced to the point test; both G3 removal arms, `--via-wrapper`), `nomemo` (`O_norc` outputs at the fix head `29f9d3a5` with `routing.fed_rate_memo` false, scenario `scenarios/w1_nomemo`, G5) and `O_min_check`, an untimed equivalence check of `O_min`.

Measured blocks are started detached, with all user apps closed. `launch_detached.sh` runs `nohup caffeinate -s` around `benchmark.py run`, writes `results/blocks/<block>_<time>.log` plus a pid file, then puts the display to sleep (`pmset displaysleepnow`). The launching agent then stays idle until the block ends. With `--dry-run` it only prints the plan and leaves the display alone.

```bash
./launch_detached.sh --block G1base --case W1 --exclusive
```

Planned G1 blocks (each started through `launch_detached.sh` with these arguments):

```bash
# determinism gate (untimed purpose, 2 runs each)
$PY benchmark.py run --block G1det --case W1 --exclusive --warmup 0 --reps 2 --label determinism
# W3 with the result capture on both runs, so item 12 is compared too (review O8);
# capture runs are never measurements (C1)
$PY benchmark.py run --block G1det --case W3 --exclusive --warmup 0 --reps 2 --vis-cache noflag --capture-result --label determinism
$PY compare.py --block G1det --ref <first G1det run ID of each case> --out results/equivalence/G1det.json
$PY compare.py --negative-control <one G1det run ID> --out results/equivalence/G1det_negative_control.json   # must PASS (O9)
# W1 baseline: 1 warm-up + 5 (no fdsreader cache state since D13; opens/parses are in cache_label)
$PY benchmark.py run --block G1base --case W1 --exclusive
# headline seeds
$PY benchmark.py run --block G1seeds --case W1 --exclusive --seeds 2,3 --reps 3
# instrumentation overhead and equivalence: plain run.py vs counters, interleaved ABAB
$PY benchmark.py run --block G1ovh --case W1 --exclusive --instrument none,counters --label controlled-cost
# output variants (after the O_*_check equivalence)
$PY benchmark.py run --block G1out --case W1 --exclusive --variants O_study,O_norc,O_min --label controlled-cost
# W3 vismap cache states
$PY benchmark.py run --block G1w3 --case W3 --exclusive --vis-cache first --warmup 0 --reps 3
$PY benchmark.py run --block G1w3 --case W3 --exclusive --vis-cache repeated
$PY benchmark.py run --block G1w3 --case W3 --exclusive --vis-cache noflag
# scaling
for c in W1_n100 W1 W1_n400; do $PY benchmark.py run --block G1scale --case $c --exclusive; done
```

The overhead baseline is always plain `run.py` (`--instrument none`). It is never `instrument/perf_run.py` without the environment variable, because that is a different entry point.

**What each run writes:**
- `results/raw/<run_id>/`:
  - `manifest.json`: ID, case/variant/seed/rep/role, commit, the worktree's `git status --porcelain --untracked-files=all` and ignored files, lock hash, instrumentation sha256 (`instrument/*.py`, `benchmark.py`) and whether counters were on, scenario sha256, FDS dir stat fingerprint, fdsreader pickle and vis-cache presence/sha256 before and after, the observed cache label, slot check before/after, host samples during the run, command, environment, exit code and termination, summary-line outcome, metrics, output sha256 and the repr-v1 trajectory hash;
  - `stdout.log`, `stderr.log` and `time_l.txt`;
  - `counters.json` and profiler captures, when used.
- `$STAGE/runs/<run_id>/`: the large run outputs (SQLite, CSVs, vis cache).

**Cache-state labels** are derived from what was observed, not from what was requested:
- There is no fdsreader cache state: the adapter (#716/#720) turns the on-disk cache off, so every `Simulation()` open parses the `.smv` (a `.pickle` in the stage dir is never read).
- With counters, `cache_label` lists `fds_opens_per_process`, `fds_open_seconds_total` and `fds_opens_by_opener` (opens and parse seconds per opening function), a setup sub-phase reported apart from the loop and the vismap build.
- `vis` is `first_use`, `repeated_use` or `noflag`.

## 4. Counters (opt-in, observational)

```bash
cd "$P/wt_8f7d29a2" && PYTHONHASHSEED=0 PYFDS_PERF_COUNTERS_OUT=/abs/counters.json \
    $PY $STUDY/instrument/perf_run.py <run.py arguments>
```

Through the harness, use `--instrument counters`. The groups are:
- fdsreader opens, loads and parses;
- vismap load, build and clear-air events;
- sign queries split into `sign`, `off_grid` and `non_sign`, with positive results, by caller and in 10 s bins;
- map growth split into sign and non-sign nodes;
- route evaluations as exit_choice, explore and wander, per pass and per 10 s;
- iterations, agent-steps and dt.

They are defined in the `instrument/perf_counters.py` docstring.

G4 (plan.md D39): with `PYFDS_PERF_DETAIL=1` the detail group also times the route paths (`evaluate_segment`, `_first_leg`, `_cell_los_stats`, `_step_los_stats`, `read_cells`, `line_parts`, `sample_fed_rate`, route-side `sample`) and counts, per path, total reads against distinct memo keys (`read_cells`: subslice, frame tuple, cell indices; `sample_fed_rate`: species frame tuple, x, y; `sample`: sampler, frame, x, y), under `detail.route_paths`; wrapper overhead is calibrated at install under `detail.route_paths_overhead`. Route-side `sample` leaves out the species reads behind `sample_fed_rate`. Each path also carries `by_parent` (seconds per innermost enclosing path), `self_seconds` (seconds not in timed children; for `evaluate_segment` this is the remainder) and `hook_seconds` (detail-group work inside the timer, already left out of `seconds`); paths nest, so do not add `seconds` across paths. Key construction runs after the read and is not counted in `time_index_hits`/`time_index_misses`; it can still fill a sampler cache entry the read itself did not use.

## 5. Equivalence (model §3, §11.2)

```bash
$PY compare.py RUN_A RUN_B --out results/equivalence/NAME.json      # one pair
$PY compare.py --block BLOCK --ref RUN_ID --out results/equivalence/BLOCK.json   # all runs of a block vs one
```

The script checks the 13 items of model_handoff_g0_v2.md §3 exactly (1-12 plus 12b in the script) and reports `equivalent` or `NOT equivalent`, plus a list of gaps:
- an item written by only one run is `not_in_both`;
- item 12 (cognitive-map history and result metrics) needs `--capture-result` on both runs, which makes `perf_run.py` the entry point for both. Capture runs carry `_cap` in the run ID, `entry_point` and `result_capture` in the grouping, and are always `not_a_measurement` (review C1);
- `--negative-control RUN` copies one run, changes one byte of `exit.csv` and one trajectory float by one ulp, and requires both to be detected while the unchanged copy stays equivalent (review O9);
- W3/W3b verdicts without item 12 name the gap "cognitive-map state not compared".

Timed baselines are plain `run.py`, so item 12 is checked in separate untimed pairs, for example:

```bash
$PY benchmark.py run --block G1eqW3 --case W3 --exclusive --warmup 0 --reps 1 \
    --instrument none,counters --capture-result --vis-cache first --label equivalence
```

W4 fixtures, the cmm arm A and the W4 pytest set run with the commands in `scenarios.json` (`workloads.W4.fixtures`); the harness case `W4_iso21` covers ISO table 21.

## 6. Analysis

```bash
$PY analyse.py            # results/summary.csv (all runs) + results/summary_groups.csv (measured, uncontaminated)
                          # rates are per run_scenario second (run_scenario_s_per_sim_s, run_scenario_us_per_agent_step)
$PY traj_hash.py RUN.sqlite   # repr-v1 trajectory hash (and the sqlite-cli variant quoted in G0 handoffs)
```

Both group tables carry `flag_status` (`inconclusive` when more than one third of a group's runs are flagged, `record_only` for the determinism and output-check blocks, else `ok`; D31); the clean table blanks every statistic when `n_used` < 3 and keeps `n_used`, and `summary_groups_all.csv` adds `wall_s_median_sensitivity`, `n_sensitivity` and `excluded_runs` (the median without the runs D31 rule (b) excludes by offender name or by an instructions deviation above 1 % from the group median).

Figures are made by the plotter from these frozen tables (matplotlib skill), not hand-entered.

## 7. Running G1 (slot-start sequence)

`gate()` in `g1_all.sh` and `g1_resume5.sh` treats a non-zero exit of either `compare.py` call as `GATE FAIL(compare.py exit)` and reads the equivalence JSON only after both calls exited 0; `block()` runs `horizon_check.py` for W1, W1_n100 and W1_n400 (D31).

`g1_all.sh` is the whole G1 driver. It has never been run end to end; its first failure in a path nobody has executed (gate, `vblock`, `vbuild_bench.py` at n = 1001) is a harness fault (plan.md D27). All commands run from the package directory, `$PY` is the baseline venv python (`/Users/chraibi/profiling-stage/wt_8f7d29a2/.venv/bin/python`).

**Before** (the maintainer closes user apps; no other agent runs anything, D10):

```bash
cd /Users/chraibi/workspace/PedestrianDynamics/Fire/fds_visibility/visibility_workshop/studies/profiling
PY=/Users/chraibi/profiling-stage/wt_8f7d29a2/.venv/bin/python
$PY benchmark.py check | $PY -c 'import json,sys; d=json.load(sys.stdin); print("ok:", d["ok"], "load1:", d["load_avg"][0], [r["comm"] for r in d["foreign_heavy"]])'   # must print ok: True
$PY verify_stage.py /Users/chraibi/profiling-stage /Users/chraibi/profiling-stage/tmp/stage_check.json | grep -c OK                                    # 10
git -C /Users/chraibi/profiling-stage/wt_8f7d29a2 status --porcelain --untracked-files=all | wc -l                        # 0
pgrep -fl 'g1_all|benchmark.py' || echo none                                                                            # none
defaults read /Library/Preferences/com.apple.SoftwareUpdate | grep -E 'AutomaticallyInstallMacOSUpdates|AutomaticDownload'   # both = 0
ps -Ao pcpu=,comm= | awk '/(installd|appstoreagent|softwareupdated)$/ && $1 > 5.0' || echo none                # none: these daemons are always resident, only their CPU matters
rm -rf __pycache__ instrument/__pycache__ preflight/__pycache__ scenarios/__pycache__
```

**Automatic updates off** (G1b pass 2, 2026-10-16: a macOS background update started at 12:20 UTC, ran for hours at
~200 % CPU (`appstoreagent`, `installd`), contaminated `G1b_ovhD` and blocked the slot for the last five blocks;
the drivers now refuse to start, `ABORT ... software_update`, while either key is 1 or an installer runs):

```bash
sudo defaults write /Library/Preferences/com.apple.SoftwareUpdate AutomaticallyInstallMacOSUpdates -bool false
sudo defaults write /Library/Preferences/com.apple.SoftwareUpdate AutomaticDownload -bool false
```

**No launch agent in a respawn loop** (G1b pass 2 continuation, 2026-10-16 19:25 UTC: a user launch agent with
`KeepAlive` kept failing at start, `ThrottleInterval` 30 s, so launchd started a short-lived python above 20 % CPU
every 31 s; four blocks were SKIPPED_SLOT and `G1b_scale400` was 6/6 flagged. `g1_resume5.sh` refuses to start,
`ABORT ... launch_agent_loop`, while one exists; the check names the job and the command):

```bash
launchctl list | awk '$1 == "-" && $2 != 0 {print $3}' | while read l; do launchctl print gui/$(id -u)/$l | grep -q 'properties = .*keepalive' && echo "$l"; done   # none
launchctl bootout gui/$(id -u)/<label>     # stop it for this login; the plist stays, it returns at the next login
```

**Quiet the host first** (offenders recorded by the host monitor during the 2026-10-16 G1 pass; all need the maintainer, several need sudo):

```bash
sudo mdutil -a -i off                 # Spotlight on ALL volumes (mds_stores reached 296 %; `-i off /` alone leaves /System/Volumes/Data indexing)
osascript -e 'quit app "Docker Desktop"'   # its VM idles at 30-110 % CPU
osascript -e 'quit app "Podcasts"'; osascript -e 'quit app "Stats"'; osascript -e 'quit app "Dropbox"'
pmset -g | grep lowpowermode          # must be 0; machine on AC
mdutil -a -s                          # every volume "Indexing disabled."
```

`ecosystemd`, `launchd`, `corespotlightd`, `PerfPowerServices`, `duetexpertd` burst above 20 % on their own and cannot be stopped; they are the reason for D30/D31. Keep the coordinator terminal window closed while the driver runs (iTerm2 rendering alone held load1 near 2). Re-enable afterwards with `sudo mdutil -a -i on`.

**Start** (detached, awake on AC, display asleep; nothing in the foreground):

```bash
nohup caffeinate -s bash g1_all.sh > results/blocks/g1_all_$(date -u +%Y%m%dT%H%M%SZ).log 2>&1 < /dev/null &
echo $! > results/blocks/g1_all.pid
sleep 2; pmset displaysleepnow
```

The driver caps itself at 4 h; a block whose slot check never passes (21 polls, 60 s apart) is recorded `SKIPPED_SLOT`, a block started after the cap `SKIPPED_CAP`. Expected duration is about 1.5 h (estimate, not measured).

**Watch** (a cheap read from another terminal, nothing else):

```bash
tail -f results/blocks/g1b_status.tsv      # UTC, block, case, status, seconds
ls -t results/blocks/g1_all_*.log | head -1 | xargs tail -n 20
```

Status lines: `START`; `<block> <case> rc=<n> <s>` after each block; `GATE G1b_det_W1 PASS|FAIL`, `GATE G1b_det_W3 PASS|FAIL` (a FAIL stops the driver with exit 1); `HORIZON_CHECK_FAILED <run>`; `SKIPPED_SLOT`, `SKIPPED_CAP`; `END g1_all elapsed_s=...`. Per-run results are in `results/raw/<run_id>/manifest.json` (`exit_code`, `termination`, `outcome`, `host_during.contaminated`); after W1, W3, W3b and W1r blocks `horizon.json` sits next to it (`python horizon_check.py RUN` recomputes: `max_bound_s` vs `guard_s`, `rows_past_last_frame`, `held_share`, `warning_count`; `analyse.py` shows `max_bound`, `held_share`, `warning_count`).

**Stop early:** `kill $(cat results/blocks/g1_all.pid); pkill -f 'benchmark.py run'; pkill -f vbuild_bench.py`. Every run directory already written stays; nothing is deleted.

**Harness fault or result (D27).** A run is a *result* only if `results/raw/<run_id>/manifest.json` exists with `exit_code` 0 or 2, `termination` in `completed`, `incomplete_time_limit`, `flows_closed` (or `timeout`/`rss_limit`: recorded, and a cap hit twice is a stop rule), and the outcome parsed (not null; the V-build runs have none). Exit 2 is expected on W1, W3, W1r and the fixture. Contaminated runs are results, flagged; more than a third of a block flagged makes the block inconclusive (plan.md).

*Harness fault* (fix the harness, keep the broken run directories as records, restart only the unfinished blocks from a copy of `g1_all.sh` with the finished ones removed and the determinism gate kept; never report as a result):
- a Python traceback in the driver log or in a run's `stderr.log` that is not the model's own error (argparse usage, `FileNotFoundError`, `KeyError` in `benchmark.py`, `compare.py`, `horizon_check.py`, `vbuild_bench.py`);
- a run directory without `manifest.json`;
- `GATE ... FAIL` where `results/equivalence/G1b_det_<case>.json` is missing or unreadable, or lists no runs;
- `HORIZON_CHECK_FAILED`; a `vblock` line with rc other than 0 and no `VBUILD` manifest.

*Result, not a fault* (stop or record per plan.md, tell perf-model): `GATE ... FAIL` where the JSON exists and a pair says `NOT equivalent` or the negative control says FAIL (determinism is broken: stop, nothing downstream may be quoted); a counter that must be nonzero is zero; `horizon.json` `passes: false` on W1 or W3 (W1r is expected to fail: guard 252 s, 8.2 % held, one warning, a declared confounder); a run killed at its limit.

`SKIPPED_SLOT` is neither: the slot was not exclusive; re-run that block when it is.

**Pass tag.** Block names and the status file carry the pass prefix from `G1_PASS` (default `G1b`: run ids `G1b_base_W1_...`, status `results/blocks/g1b_status.tsv`); pass 1 (`G1base_...`, `g1v2_status.tsv`) is never touched and cannot be picked up by `first_id`. `G1_DRY_RUN=1 bash g1_all.sh` prints the planned blocks and exits.

## 8. Running G2 (attribution slot)

G2 profiles the G1 workloads with pyinstrument and attributes wall time to the six perf target issues. Prepare the host as for G1 (§7 "Before"), then start from the package directory:

```bash
cd /Users/chraibi/workspace/PedestrianDynamics/Fire/fds_visibility/visibility_workshop/studies/profiling
nohup caffeinate -s bash g2_all.sh > results/blocks/g2_all_$(date -u +%Y%m%dT%H%M%SZ).log 2>&1 < /dev/null &
```

`G2_DRY_RUN=1 bash g2_all.sh` prints the plan without running. Blocks and expected run directories (warm-ups included): `G2_prof_W3` 4, `G2_prof_W1r` 6, `G2_prof_W4flow` 2, `G2_prof_W1` 6, `G2_rc_cprof` 1 + 1, `G2_ctr_scale` 4 + 4 + 4; 32 runs in about 55 min, hard cap 2 h. Status: `results/blocks/g2_status.tsv` (ends with an `END` line).

Skip rule: a block whose runs are all done is recorded as complete and skipped, so a second slot reruns only missing blocks. A block whose slot check never passes is `SKIPPED_SLOT`, one not started within the cap `SKIPPED_CAP`; quiet the host and run again. A block with run directories but too few done runs is `PARTIAL` and not rerun (it would pool reps of two sessions under one name); rerun it under another pass tag (`G2_PASS=G2b`).

Attribution tables, from this directory with the baseline interpreter:

```bash
$PY attribute.py --block <block> --out results/g2        # attribution_<block>_<case>.csv
$PY attribute.py --rc-diff G2_rc_cprof --out results/g2  # rc_diff_G2_rc_cprof.csv
$PY attribute.py --counters G2_ctr_scale --out results/g2  # counters_G2_ctr_scale.csv
```

The report is `results/g2_attribution.md`; every number in it comes from a CSV in `results/g2/` or from a file the report names (`results/blocks/acceptance_G1b_model.md`, `results/summary_groups_all.csv`, `results/blocks/g2_status.tsv`, `results/blocks/g2_slot_record.md`, the frozen worktree source).

Own-session rule: the session that starts the slot makes one blocking wait on the status file (`until grep -q END results/blocks/g2_status.tsv; do sleep 30; done`) and no other tool call while runs execute; any call during a run makes the session an offender in the manifests. Check `host_during.offenders_max_pcpu` for `claude` afterwards.

## 9. Running G3 (removal slot)

G3 removes one mechanism per arm from W1 and measures the end-to-end difference (arms `nrr`, `nss`, `nst` against `O_norc`). Prepare the host as for G1 (§7 "Before"), then start from the package directory:

```bash
cd /Users/chraibi/workspace/PedestrianDynamics/Fire/fds_visibility/visibility_workshop/studies/profiling
nohup caffeinate -s bash g3_all.sh > results/blocks/g3_all_$(date -u +%Y%m%dT%H%M%SZ).log 2>&1 < /dev/null &
```

`G3_DRY_RUN=1 bash g3_all.sh` prints the plan without running (two `DRY block` lines). Blocks and expected run directories (warm-ups included): `G3_rm_W1` 4 + 20 (`--case W1 --variants O_norc,nrr,nss,nst --via-wrapper --order abba --warmup 1 --reps 5`) and `G3_ctr_W1` 8 (same variants, `--instrument counters --warmup 0 --reps 2`); 32 runs in about 20 min, hard cap 2 h. Status: `results/blocks/g3_status.tsv` (ends with an `END` line). The skip rule and the `PARTIAL` rule are those of §8 (`G3_PASS=G3b` for a rerun of a partial block). `G3_ARMS` (default `O_norc,nrr,nss,nst`, `O_norc` first) selects the arms; the expected run counts are 6 per arm for the removal block and 2 per arm for the counters block, so `G3_PASS=G3b G3_ARMS=O_norc,nss` runs `G3b_rm_W1` (12 runs) and `G3b_ctr_W1` (4 runs).

Removal and counters tables, from this directory with the baseline interpreter:

```bash
$PY attribute.py --removal G3_rm_W1 --counters-block G3_ctr_W1 --out results/g3 [--exclude RUN_ID ...]  # removal_G3_rm_W1.csv
$PY attribute.py --counters G3_ctr_W1 --out results/g3                                                   # counters_G3_ctr_W1.csv
```

`--exclude` leaves out a rep whose offenders include `claude`. `--rerun-block G3b_rm_W1 --rerun-counters-block G3b_ctr_W1` replaces the arms of the rerun block (`nss`) by their comparison with that block's own `O_norc`; the last CSV column `source_block` names the block each row's arm and baseline come from. The report is `results/g3_removal.md`; every number in it comes from a CSV in `results/g3/` or from a file the report names (`results/blocks/g3_status.tsv`, `results/g2/attribution_G2_prof_W1_W1.csv`, the manifests).

Rerun of the `nss` arm: the first `nss` arm (`G3_rm_W1_W1_nss_*`, `G3_ctr_W1_W1_nss_*`) is invalid (oxygen 0 %, hypoxia artefact) and stays in `results/raw/` as evidence. The `nss` rows of `results/g3/counters_G3_ctr_W1.csv` and the `G3_*`/`nss` groups of `results/summary_groups*.csv` come from that invalid arm and feed no verdict. `G3_PASS=G3b G3_ARMS=O_norc,nss bash g3_all.sh` (status `results/blocks/g3b_status.tsv`, 16 runs in about 12 min) reran it beside a fresh `O_norc`; the tables are regenerated with `$PY attribute.py --removal G3_rm_W1 --counters-block G3_ctr_W1 --rerun-block G3b_rm_W1 --rerun-counters-block G3b_ctr_W1 --out results/g3` and `$PY attribute.py --counters G3b_ctr_W1 --out results/g3`.

Own-session rule: the session that starts the slot makes one blocking wait on the status file (`until grep -q END results/blocks/g3_status.tsv; do sleep 30; done`) and no other tool call while runs execute; any call during a run makes the session an offender in the manifests. Check `host_during.offenders_max_pcpu` for `claude` afterwards.

## 10. Running G4 (route-path attribution)

G4 bounds what a route-sample memo can save on W1 (#243) from one instrumented run; it is a diagnostic and is never pooled. From the package directory with the baseline interpreter (about one minute, no slot needed):

```bash
$PY benchmark.py run --shared --block G4det --case W1 --variants O_norc --seeds 1 --instrument detail --warmup 0 --reps 1 --label diagnostic > /tmp/profiling-2-g4det.log 2>&1
$PY attribute.py --route-paths G4det --out results/g4                                    # route_paths_G4det.csv
```

The run directory `results/raw/G4det_*` (ignored by git) holds `manifest.json`, `counters.json` with `detail.route_paths` and `detail.route_paths_overhead`, and `time_l.txt`; note each attempt in `results/blocks/g4_runs.md`. `--shared` and `--label diagnostic` mark the manifest `not_a_measurement`, and `G4det` is in `RECORD_ONLY_BLOCKS` of `analyse.py`, so no summary pools it. The table has one row per path, `remainder` (the `self_seconds` of `evaluate_segment`, less its wrapper overhead) and `TOTAL`; the report is `results/g4_attribution.md`, which proposes decision D39 for the maintainer.

## 11. Running G5 (memo slot)

G5 measures what the FED-rate memo of pyFDS-Evac `fix/243-fed-rate-memo` (`29f9d3a5`) saves on W1 over ten seeds: variant `O_norc` (memo on) against `nomemo` (`routing.fed_rate_memo = false`, scenario `scenarios/w1_nomemo/config_gate.json`), both at the fix stage, so the difference is the memo alone. The verdict is decision D40 against the 23 s per ten-run-study bar. Prepare the host as for G1 (§7 "Before"), then start from the package directory:

```bash
cd $STUDY
nohup caffeinate -s bash g5_all.sh > results/blocks/g5_all_$(date -u +%Y%m%dT%H%M%SZ).log 2>&1 < /dev/null &
```

`G5_DRY_RUN=1 bash g5_all.sh` prints the plan without running (three `DRY` lines). Blocks and expected run directories (warm-ups included): `G5_memo_W1` 40 (`--case W1 --variants O_norc,nomemo --seeds 1,...,10 --order abba --warmup 1 --reps 1`; the arm order alternates across seeds) and `G5_ctr_W1` 4 (`--seeds 1 --instrument counters --warmup 0 --reps 2 --label diagnostic`, with `memo.log` per run). After the memo block the driver runs the equality step; `G5_PASS=G5b` reruns a partial block under another prefix. Stage the log with `git add -f results/blocks/g5_all_*.log` (a global `*.log` ignore rule hides it).

Tables, from this directory with the baseline interpreter:

```bash
$PY attribute.py --equality G5_memo_W1 --out results/g5                                  # equality_G5_memo_W1.csv (exit 3 when a pair differs; `--exclude` is honoured and exits 2 when an excluded id removes an arm)
$PY attribute.py --paired G5_memo_W1 --counters-block G5_ctr_W1 --out results/g5 [--exclude RUN_ID ...]   # paired_G5_memo_W1.csv, ALL row = D40
$PY attribute.py --memo-counters G5_ctr_W1 --out results/g5                              # memo_counters_G5_ctr_W1.csv
```

`paired_*.csv` has one row per seed (`d_s` = wall of `nomemo` minus wall of `O_norc`) and an `ALL` row with the median, IQR, `diff_per_study_s` (10 × median), the sum and the `verdict`: `invalid_outputs_differ`, `tie` (|median| ≤ IQR), `fix_first` (per study above 23 s) or `below_bar`. `--exclude` leaves out a rep whose offenders include `claude`. The report is `results/g5_memo.md`.

`G5_memo_W1` and `G5_ctr_W1` are record-only in `analyse.py` and are never pooled with the 8f7d29a2 blocks. The stage `/Users/chraibi/profiling-stage/wt_29f9d3a5` was created with `git worktree add --detach` at `29f9d3a5` in the pyFDS-Evac clone and its venv with `UV_CACHE_DIR=~/profiling-stage/uvcache uv sync --frozen --python 3.12`; `benchmark.py` refuses it unless the commit, the clean state and the `uv.lock` hash match the pin. The own-session rule of §9 applies: the session that starts the slot makes one blocking wait and no other tool call while runs execute; check `host_during.offenders_max_pcpu` for `claude` afterwards.

## 12. Running G6 (removal re-measurement at main)

G6 re-measures what removing the slice sampler's scalar lookups (#242, variant `nss`: every `SliceFieldSampler.sample` stubbed) still saves on W1 at `main` after the FED-rate memo of PR #812 (`d96894ac`), against `O_norc` of the same stage, over ten paired seeds. The verdict is decision D41 against the 23 s per ten-run-study bar; `nss` is a removal arm that bounds a fix, not a fix. Prepare the host as for G1 (§7 "Before"), then start from the package directory:

```bash
cd $STUDY
nohup caffeinate -s bash g6_all.sh > results/blocks/g6_all_$(date -u +%Y%m%dT%H%M%SZ).log 2>&1 < /dev/null &
```

`G6_DRY_RUN=1 bash g6_all.sh` prints the plan without running (two `DRY` lines at the stage `wt_d96894ac`). Blocks and expected run directories (warm-ups included), both with `--via-wrapper` and `--wt`/`--py` of the main stage: `G6_nss_W1` 40 (`--case W1 --variants O_norc,nss --seeds 1,...,10 --order abba --warmup 1 --reps 1 --label removal`) and `G6_ctr_W1` 4 (`--seeds 1 --instrument counters --warmup 0 --reps 2 --label diagnostic`). There is no equality step: `nss` changes trajectories by construction, so each row of the table carries the simulated time and evacuated count of both reps instead. `G6_PASS=G6b` reruns a partial block under another prefix. Stage the log with `git add -f results/blocks/g6_all_*.log`.

Table, from this directory with the baseline interpreter:

```bash
$PY attribute.py --paired-removal G6_nss_W1 --arm nss --counters-block G6_ctr_W1 --out results/g6 [--exclude RUN_ID ...]   # paired_removal_G6_nss_W1_nss.csv, ALL row = D41
```

`paired_removal_*.csv` has one row per seed (`d_s` = wall of `O_norc` minus wall of the arm, with flags, `sim_time_*_s` and `evacuated_*` of both reps) and an `ALL` row with `n_seeds`, `n_seeds_dropped`, the median, IQR (exclusive quartiles), `diff_per_study_s` (10 × median), the sum, the `O_norc` agent-step median, the per-agent-step figure and the `verdict`: `tie` (|median| ≤ IQR), `fix_first` (per study above 23 s) or `below_bar`. `--arm` accepts `nrr`, `nss` or `nst`; `--exclude` leaves out a rep whose offenders include `claude` and exits 2 when the id matches no rep. The report is `results/g6_nss_remeasure.md`.

`G6_nss_W1` and `G6_ctr_W1` are record-only in `analyse.py` and are never pooled with the 8f7d29a2 blocks. The stage `/Users/chraibi/profiling-stage/wt_d96894ac` was created with `git worktree add --detach` at `d96894ac` in the pyFDS-Evac clone and its venv with `UV_CACHE_DIR=~/profiling-stage/uvcache uv sync --frozen --python 3.12`; `benchmark.py` refuses it unless the commit, the clean state and the `uv.lock` hash match the pin. The stage `wt_29f9d3a5` of §11 is retired (its pin stays for the G5 record). The own-session rule of §9 applies: the session that starts the slot makes one blocking wait and no other tool call while runs execute; check `host_during.offenders_max_pcpu` for `claude` afterwards.

## 13. Running G8 (lookup measurement)

G8 measures what the faster slice point lookup of pyFDS-Evac `fix/242-faster-point-lookup` (`62106002`) saves on W1 (#242). Variant `O_norc` runs the branch's lookup; variant `nlk` patches the pre-change `SliceFieldSampler.sample` back in (time-index cache, `_find_subslice`, `ValueError` for an outside point, two `_nearest_index` calls) through `instrument/perf_run.py`, selected by `PYFDS_PERF_STUB=nlk`, on the same stage, so the two arms follow the same trajectory and write identical outputs. The verdict is decision D42 against the 23 s per ten-run-study bar. Prepare the host as for G1 (§7 "Before"), then start from the package directory:

```bash
cd $STUDY
nohup caffeinate -s bash g8_all.sh > results/blocks/g8_all_$(date -u +%Y%m%dT%H%M%SZ).log 2>&1 < /dev/null &
```

`G8_DRY_RUN=1 bash g8_all.sh` prints the plan without running (two `DRY` lines at the stage `wt_62106002`). Blocks and expected run directories (warm-ups included), both with `--via-wrapper` and `--wt`/`--py` of the stage: `G8_lk_W1` 40 (`--case W1 --variants O_norc,nlk --seeds 1,...,10 --order abba --warmup 1 --reps 1 --label lookup`; the arm order alternates across seeds) and `G8_ctr_W1` 4 (`--seeds 1 --instrument counters --warmup 0 --reps 2 --label diagnostic`). `O_norc` also enters through the wrapper, so its cost is in both arms. Stage the log with `git add -f results/blocks/g8_all_*.log` (a global `*.log` ignore rule hides it).

Table, from this directory with the baseline interpreter:

```bash
$PY attribute.py --paired-lookup G8_lk_W1 --arm nlk --counters-block G8_ctr_W1 --out results/g8 [--exclude RUN_ID ...]   # paired_lookup_G8_lk_W1_nlk.csv, ALL row = D42
```

`paired_lookup_*.csv` has one row per seed (`d_s` = wall of `nlk` minus wall of `O_norc`; positive means the shared lookup is faster), the flags of both reps and `outputs_equal` (sha256 of `exit.csv`, `rh.csv` and `fed.csv` of the two reps), and an `ALL` row with the median, IQR, `diff_per_study_s` (10 × median), the sum, the agent-steps of the counters block and the `verdict`: `invalid_outputs_differ`, `tie` (|median| ≤ IQR), `fix_first` (per study above 23 s) or `below_bar`. A differing pair gives `invalid_outputs_differ` and exit 3 after the CSV is written; `--exclude` leaves out a rep whose offenders include `claude`; warm-ups never enter the table, and an id that matches no rep exits 2. The report is `results/g8_lookup_measure.md`.

`G8_lk_W1` and `G8_ctr_W1` are record-only in `analyse.py` and are never pooled with other blocks. The stage `/Users/chraibi/profiling-stage/wt_62106002` was created with `git worktree add --detach` at `62106002` in the pyFDS-Evac clone and its venv with `UV_CACHE_DIR=~/profiling-stage/uvcache uv sync --frozen --python 3.12`; `benchmark.py` refuses it unless the commit, the clean state and the `uv.lock` hash match the pin. The own-session rule of §9 applies: the session that starts the slot makes one blocking wait and no other tool call while runs execute; check `host_during.offenders_max_pcpu` for `claude` afterwards.

## 14. Running G11 (exit-reach prune measurement)

G11 measures what the exit-reach prune of pyFDS-Evac `perf/429-exit-reach-prune` (`f7efcf9b`) saves on W1 (#429). Variant `O_norc` runs the branch's `reached_stage`, which rejects a far agent from the exit polygon's cached bounds before building a shapely Point; variant `nrp` patches the pre-change `reached_stage` back in (exit with polygon: `distance_to_polygon(...) <= EXIT_REACH_TOLERANCE_M`, then the target-distance test, then the checkpoint containment test) through `instrument/perf_run.py`, selected by `PYFDS_PERF_STUB=nrp`, on the same stage. The prune only skips tests whose answer is already known, so both arms follow the same trajectory and write identical outputs. The verdict is decision D43 against the 23 s per ten-run-study bar. Prepare the host as for G1 (§7 "Before"), then start from the package directory:

```bash
cd $STUDY
nohup caffeinate -s bash g11_all.sh > results/blocks/g11_all_$(date -u +%Y%m%dT%H%M%SZ).log 2>&1 < /dev/null &
```

`G11_DRY_RUN=1 bash g11_all.sh` prints the plan without running. Blocks and expected run directories (warm-ups included), both with `--via-wrapper` and `--wt`/`--py` of the stage `wt_f7efcf9b`: `G11_pr_W1` 40 (`--case W1 --variants O_norc,nrp --seeds 1,...,10 --order abba --warmup 1 --reps 1 --label prune`; the arm order alternates across seeds) and `G11_ctr_W1` 4 (`--seeds 1 --instrument counters --warmup 0 --reps 2 --label diagnostic`). `O_norc` also enters through the wrapper, so its cost is in both arms. Stage the log with `git add -f results/blocks/g11_all_*.log` (a global `*.log` ignore rule hides it).

Table, from this directory with the baseline interpreter:

```bash
$PY attribute.py --paired-lookup G11_pr_W1 --arm nrp --counters-block G11_ctr_W1 --out results/g11 [--exclude RUN_ID ...]   # paired_lookup_G11_pr_W1_nrp.csv, ALL row = D43
```

The table has the columns and the verdict rule of §13 (`d_s` = wall of `nrp` minus wall of `O_norc`; positive means the prune is faster). A differing pair of outputs gives `invalid_outputs_differ` and exit 3 after the CSV is written; `--exclude` leaves out a rep whose offenders include `claude`; warm-ups never enter the table, and an id that matches no rep exits 2. The report is `results/g11_prune_measure.md`.

`G11_pr_W1` and `G11_ctr_W1` are record-only in `analyse.py` and are never pooled with other blocks. The stage `/Users/chraibi/profiling-stage/wt_f7efcf9b` was created with `git worktree add --detach` at `f7efcf9b` in the pyFDS-Evac clone and its venv with `UV_CACHE_DIR=~/profiling-stage/uvcache uv sync --frozen --python 3.12`; `benchmark.py` refuses it unless the commit, the clean state and the `uv.lock` hash match the pin. The own-session rule of §9 applies: the session that starts the slot makes one blocking wait and no other tool call while runs execute; check `host_during.offenders_max_pcpu` for `claude` afterwards.

## 15. Running G12 (removal bounds at main after #814)

G12 measures what removing rerouting (variant `nrr`, `--no-enable-rerouting`) and the scalar slice lookups (variant `nss`, every `SliceFieldSampler.sample` stubbed) still saves on W1 at `main` after PR #814 (`b6dff31c`), each against `O_norc` of the same stage, over ten paired seeds. Both arms change trajectories, so the result is a ceiling per arm against the 23 s per ten-run-study bar (decision D44), not a fix saving; the two ceilings overlap and are not added. Prepare the host as for G1 (§7 "Before"), then start from the package directory:

```bash
cd $STUDY
nohup caffeinate -s bash g12_all.sh > results/blocks/g12_all_$(date -u +%Y%m%dT%H%M%SZ).log 2>&1 < /dev/null &
```

`G12_DRY_RUN=1 bash g12_all.sh` prints the plan without running. Blocks and expected run directories (warm-ups included), all with `--wt`/`--py` of the stage `wt_b6dff31c`: `G12_nrr_W1` 40 (`--case W1 --variants O_norc,nrr --seeds 1,...,10 --order abba --warmup 1 --reps 1 --label removal`, no wrapper), `G12_nss_W1` 40 (`--variants O_norc,nss --via-wrapper`, otherwise the same) and `G12_ctr_W1` 6 (`--variants O_norc,nrr,nss --via-wrapper --seeds 1 --instrument counters --warmup 0 --reps 2 --label diagnostic`). There is no equality step: both arms change trajectories, so each table row carries the simulated time and evacuated count of both reps. Stage the log with `git add -f results/blocks/g12_all_*.log`.

Tables, from this directory with the baseline interpreter:

```bash
$PY attribute.py --paired-removal G12_nrr_W1 --arm nrr --counters-block G12_ctr_W1 --out results/g12 [--exclude RUN_ID ...]   # paired_removal_G12_nrr_W1_nrr.csv, ALL row = D44 nrr
$PY attribute.py --paired-removal G12_nss_W1 --arm nss --counters-block G12_ctr_W1 --out results/g12 [--exclude RUN_ID ...]   # paired_removal_G12_nss_W1_nss.csv, ALL row = D44 nss
```

The columns and the verdict rule are those of §12 (`d_s` = wall of `O_norc` minus wall of the arm; positive means removing the mechanism saves time). Warm-ups never enter the table, and `--exclude` takes rep ids only (an id that matches no rep exits 2). The report is `results/g12_main_removal.md`.

`G12_nrr_W1`, `G12_nss_W1` and `G12_ctr_W1` are record-only in `analyse.py` and are never pooled with other blocks. The stage `/Users/chraibi/profiling-stage/wt_b6dff31c` was created with `git worktree add --detach` at `b6dff31c1375f9b8a2cfe7b08a085917ebc72285` in the pyFDS-Evac clone and its venv with `UV_CACHE_DIR=~/profiling-stage/uvcache uv sync --frozen --python 3.12`; `benchmark.py` refuses it unless the commit, the clean state and the `uv.lock` hash match the pin. The own-session rule of §9 applies: the session that starts the slot makes one blocking wait and no other tool call while runs execute; check `host_during.offenders_max_pcpu` for `claude` afterwards.

## 16. Running G13 (rerouting profile at main)

G13 opens rerouting on W1 at `main` after PR #814 (`b6dff31c`): a pyinstrument profile (plain and profiled reps interleaved) gives the inclusive time of every call path below the two rerouting entry points (`evaluate_and_reroute` in `route_graph.py`, `_assign_initial_exit` in `scenario.py`), scaled to the plain wall, and one detail-counters run regenerates the route-path table. Shares are attribution evidence and upper bounds on what removing a part saves, not fix savings (decision D32); decision D45 ranks the parts against the 23 s per ten-run-study bar.

```bash
cd $STUDY
nohup caffeinate -s bash g13_all.sh > results/blocks/g13_all_$(date -u +%Y%m%dT%H%M%SZ).log 2>&1 < /dev/null &
```

`G13_DRY_RUN=1 bash g13_all.sh` prints the plan without running. Two blocks, both with `--wt`/`--py` of the stage `wt_b6dff31c`: `G13_prof_W1` 6 runs (`--case W1 --variants O_norc --profiler none,pyinstrument --order abba --warmup 1 --reps 2 --label diagnostic --prof-py $PROF_PY`) and `G13_det_W1` 1 run (`--instrument detail --warmup 0 --reps 1 --label diagnostic`). `benchmark.py`'s default profiler interpreter is the venv of `8f7d29a2`, so the profiled block passes `--prof-py /Users/chraibi/profiling-stage/venv_prof_b6dff31c/bin/python` explicitly; that venv was built from the stage with `UV_PROJECT_ENVIRONMENT=… uv sync --frozen --python 3.12` and `uv pip install pyinstrument==5.1.3`. Measured: plain 30.8 s, pyinstrument 71.9 s, the slot 370 s.

Tables, from this directory with the baseline interpreter:

```bash
$PY attribute.py --reroute-tree G13_prof_W1 --out results/g13 [--exclude RUN_ID ...]   # reroute_tree_G13_prof_W1.csv
$PY attribute.py --route-paths G13_det_W1 --out results/g13                            # route_paths_G13_det_W1.csv
```

`reroute_tree_*.csv` has one row per (`entry`, `path`), `path` being the function names from the entry point joined by ` > ` and `depth` the position below it (0 = the entry point). Depth-0 rows are always written; deeper rows when their median share of the profiled wall is at least 1 %. `cum_s` is the inclusive pyinstrument time of that call path (the same path reached from several call sites is summed; a frame below both entry points has a row under each), `self_s` the frame's own time (`[self]` and `<built-in>` children count as its own), `share_profiled` = `cum_s` / profiled wall, `agreement_pts` the spread of the share over the profiled reps (blank with one), `cost_plain_s` = `cum_s` × plain wall / profiled wall, `cost_per_study_s` = 10 × `cost_plain_s`, and `verdict` is `above_bar` when that exceeds 23 s, else `below_bar`. All seconds are medians over the profiled reps; paths nest, so rows are not additive. Rows key on function names, so distinct functions that share a name under the same parent (two `<genexpr>`, say) merge into one row and `file` is taken from the first rep; on the G13 data that is at most 0.053 s, below the 1 % threshold. Warm-ups never enter the table; `--exclude` takes rep ids of profiled and plain reps alike, and a plain rep with an unusable termination is ignored (an id that matches no rep exits 2). The report is `results/g13_reroute_profile.md`.

`G13_prof_W1` and `G13_det_W1` are record-only in `analyse.py` and are never pooled with other blocks. The own-session rule of §9 applies: the session that starts the slot makes one blocking wait and no other tool call while runs execute; check `host_during.offenders_max_pcpu` for `claude` afterwards.

## 17. Running G14 (repeat count at main)

G14 counts how often the per-agent route walks of rerouting are asked for again on W1 at `main` (`b6dff31c`): total calls against distinct exact keys for `first_leg`, `first_leg_dose` and the cross-pass `segment` key (and, as information only, `first_leg_r01`, the `first_leg` key with the position rounded to 0.1 m). It measures counts, not time: no timing claim, no pyFDS-Evac change. Decision D46 multiplies each repeat share by the path's cost from the G13 profile and compares it with the 23 s per ten-run-study bar.

```bash
cd $STUDY
nohup caffeinate -s bash g14_all.sh > results/blocks/g14_all_$(date -u +%Y%m%dT%H%M%SZ).log 2>&1 < /dev/null &
```

`G14_DRY_RUN=1 bash g14_all.sh` prints the plan without running. One block, `G14_cnt_W1`, 2 runs (`--case W1 --variants O_norc --instrument detail --seeds 1,2 --warmup 0 --reps 1 --label diagnostic`, `--wt`/`--py` of the stage `wt_b6dff31c`), about 95 s.

Tables, from this directory with the baseline interpreter:

```bash
$PY attribute.py --route-paths G14_cnt_W1 --out /tmp/g14_old_paths                                                            # old paths only (no G14 keys), not committed
$PY attribute.py --repeat-ceiling G14_cnt_W1 --tree results/g13/reroute_tree_G13_prof_W1.csv --out results/g14 [--exclude RUN_ID ...]   # repeat_ceiling_G14_cnt_W1.csv
```

`repeat_ceiling_*.csv` has one row per usable detail run (seed) and path in the order `first_leg`, `first_leg_dose`, `segment`, `first_leg_r01`. `total` and `distinct` are the calls and distinct exact keys, `hit_share` = 1 − `distinct` / `total` (blank when `total` is 0), `capped` is true when the key set hit its cap (distinct is then under-counted and the share over-stated), `cost_per_study_s` is the path's cost from the tree CSV (`_first_leg`, `_first_leg_dose` or `evaluate_segment`: the sum over call paths of the rows whose last element is that function and which do not nest it), `ceiling_per_study_s` = `hit_share` × `cost_per_study_s`, and `verdict` is `above_bar` when the ceiling exceeds 23 s, else `below_bar`; `first_leg_r01` is `info` (an inexact key, no verdict). The ceiling assumes a repeat costs the mean call. The report is `results/g14_repeat_count.md`.

`G14_cnt_W1` is record-only in `analyse.py` and is never pooled with other blocks. The own-session rule of §9 applies: the session that starts the slot makes one blocking wait and no other tool call while runs execute; check `host_during.offenders_max_pcpu` for `claude` afterwards (counts do not depend on it).
