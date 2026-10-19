# perf-engineer handoff, gate G0

Date: 2026-10-02. Role: perf-engineer. Spec: `~/.claude/docs/profiling_team.md` v2.0.

Nothing in this file is a measurement. During every run the host was busy:
- load average 2.7–4.8;
- another agent's `/tmp/release-check.*/venv-3.11/bin/python3` at about 100 % CPU;
- sciebo pickles had been rewritten earlier today (see §3).

Times and RSS below only size the limits.

## 1. Inputs and isolation

| Item | Value |
|---|---|
| Target commit | `6fd7878c9ef53919d81640a747e4d7332f414000` (origin/main after #460). Versus `289b33d0`, it changes only packaging (`pyproject`, `uv.lock`, CI, figure-script shebangs, one test), not `pyfds_evac/`, `run.py` or `assets/`. |
| Worktree `$WT` | `<P>/wt6`, detached, `git status --porcelain` empty after all runs |
| `<P>` | `/private/tmp/claude-503/-Users-chraibi-workspace-PedestrianDynamics-Fire-fds-visibility-visibility-workshop/912eedf9-4145-46cc-bb81-967d1c8ae7ac/scratchpad/profiling` |
| Baseline venv `$PY` | `<P>/wt6/.venv/bin/python`, CPython 3.12.13 (Homebrew), built with `UV_CACHE_DIR=<P>/uvcache uv sync --frozen --python 3.12`; no extra packages |
| Profiling venv | `<P>/venv_prof6`: same lock and same command with `UV_PROJECT_ENVIRONMENT=<P>/venv_prof6`, plus `uv pip install py-spy scalene memray pyinstrument`. It imports `pyfds_evac` from the same `<P>/wt6` source. |
| `uv.lock` sha256 | `2731a9e77d2596c7cc3076e2f8873075d1d9542a1903470e7c18f3cd8a0913e2` (equals the run manifests and perf-model) |
| `$STAGE` | `/Users/chraibi/profiling-stage` (local, outside sciebo and git), containing `fds/`, `cache/` and `tmp/` (per-run `TMPDIR`) |
| User checkout and its `.venv`; sciebo | not touched. The sciebo pickles keep exactly the size and mtime recorded in `scenarios.json` (`stat` after all runs). |

Superseded and not used: the worktree `<P>/wt` at `289b33d0` with its 3.12 venv. Also unused are the 3.14 venvs `<P>/venv6_py314` and `<P>/venv_prof6_py314`, set aside after the coordinator chose 3.12, because 3.13/3.14 swap scikit-image 0.23.2 for 0.26.0.

## 2. Environment and profilers

`environment.json` was regenerated for `6fd7878c` / 3.12:

```
$PY studies/profiling/collect_env.py $WT studies/profiling/environment.json --profiling-python <P>/venv_prof6/bin/python
```

The earlier `289b33d0` inventory is kept as `results/raw/g0_w1_gate_s1_repro/environment_289b33d0.json`.

- **Host and OS.** macOS 27.0 (26A428), arm64. Mac15,6, Apple M3 Pro, 6 P-cores + 6 E-cores, 18 GiB RAM. AC power, low-power mode off.
- **Package versions.** pyfds-evac 0.1.0, jupedsim 1.4.2 (`Simulation(dt=0.01)` default, checked from the installed signature), fdsreader 1.11.7, fdsvismap 0.3.1, scikit-image 0.23.2, numpy 2.4.4 (BLAS/LAPACK: Apple Accelerate), scipy 1.17.1, shapely 2.1.2, pandas 2.3.3.
- **Same third-party packages in both locks.** On 3.12, `uv pip list` shows the same third-party set and versions under the `289b33d0` lock and the `6fd7878c` lock. Only the editable path differs.
- **Thread environment.** `OMP_NUM_THREADS=4` is inherited from the user's shell; the other thread variables are unset. Accelerate ignores `OMP_NUM_THREADS`. Runs set `PYTHONHASHSEED=0`, as in `scenarios.json` global_rules.

Tools were checked on a toy script, on both 3.12 and 3.14:

| Tool | Status |
|---|---|
| `/usr/bin/time -l` | works: wall, user, sys, max RSS, peak footprint, instructions |
| cProfile | works |
| py-spy 0.4.2 | **not usable**. `record` aborts with "This program requires root on OSX", and `--native` is "not supported on your platform". Running sudo is the maintainer's decision, and I did not do it. |
| pyinstrument 5.1.3 | works without root (statistical, Python frames only) |
| Scalene 2.3.0 | works (`python -m scalene run -o out.json …`): CPU and memory, JSON output |
| memray 1.20.0 | works, Python and `--native`, with native frames symbolised (`PyArray_*`). Use `stats`/`flamegraph`; `tree` is an interactive viewer (TUI), which hung when run from this non-interactive shell. |
| `/usr/bin/sample` | works without root on own processes: native C stacks (e.g. libBLAS) but no Python frames |

No tool on this host joins Python and native frames in one sample. That remains an attribution gap unless the maintainer allows py-spy as root, and even then without `--native`.

## 3. Data inventory and staging

Staged with:

```
rsync -a --exclude '*.pickle' <src>/ $STAGE/fds/<name>/
```

Sources:
- `a047_pvc_h40`, `t_junction_fire_2MW_PVC` and `cmm_clear_air` come from sciebo;
- `iso_table21_coupled` and `iso_table22_{a,b,c,d}` come from `$WT/assets/...`.

`verify_stage.py` checks every file against `preflight/input_hashes.json`. The result is in `results/stage_verification.json`. **All 8 directories match, with no missing, extra or mismatched files.** The aggregates equal perf-model's:

| Directory | Files | Aggregate hash |
|---|---|---|
| a047 | 145 | `441bc2c1…` |
| t_junction | 85 | `d84ee4ee…` |
| cmm | 23 | — |
| iso21 | 5 | — |
| iso22 a–d | 9 each | — |

Total about 1.0 GB.

| Workload | Output complete | Caches |
|---|---|---|
| W1 a047_pvc_h40 | `.out` "STOP: FDS completed successfully", T_END 480 s | fdsreader pickle written by the G0 run at `$STAGE/fds/a047_pvc_h40/a047_pvc_h40.pickle` (474 295 B). It is now present, so the next first-use run must remove this own-stage file first. |
| W3 t_junction fire_2MW_PVC | completed, T_END 300 s | pickle now present in the stage; no vismap cache existed anywhere. The diagnostic built `results/raw/g0_w3_tj_committed300_diag/w3_vis.npz` (1.78 MB). |
| W4 cmm clear_air | completed, 0–120 s | sciebo holds `vis_cmm.npz` copies (not staged) |
| W4 iso21/iso22 | committed output, staged out of the worktree | none in stage |

Cache facts:
- fdsreader writes `<fds_dir>/<chid>.pickle` and deletes it on a hash mismatch or a `clear_cache` (`fdsreader/simulation.py` 69–95, 202, 1058).
- `--cleanup` deletes only the temporary trajectory SQLite and its manifest (`Scenario.cleanup`, `run.py:718`).
- The pickle is about 0.47 MB and holds metadata only, so slice arrays load lazily in every process. fdsreader first-use versus repeated-use is therefore probably small for W1; the OS page cache, which cannot be controlled without root, is likely larger. This is indicative only.

## 4. G0 normal runs (all untimed, `PYTHONHASHSEED=0`, serial)

Exact scripts are in `results/raw/<run_id>/cmd.sh`, with logs, `time_l.txt`, `exit_code`, timestamps, `load_before.txt`, `activation.json` and all outputs. The W1 command is `scenarios.json` W1.command verbatim, with `$OUT = results/raw/g0_w1_gate_s1_6fd7878c`:

```
cd $WT && PYTHONHASHSEED=0 $PY run.py --scenario assets/schroeder2015_route/evac/config_gate.json --seed 1 \
  --fds-dir /Users/chraibi/profiling-stage/fds/a047_pvc_h40 --output-route-cost-history $OUT/gate_s1_rc.csv \
  --output-fed-history $OUT/gate_s1_fed.csv --output-sqlite $OUT/gate_s1.sqlite --cleanup \
  --output-route-history $OUT/gate_s1_rh.csv --output-exit-history $OUT/gate_s1_exit.csv > $OUT/gate_s1_log.txt 2>&1
```

Activation counts come from `g0_activation.py RUN_DIR PREFIX BASE_SPEED --horizon-guard S`. Missing outputs give null.

| Run ID | Workload | Exit | Summary line | Indicative wall / user / max RSS |
|---|---|---|---|---|
| `g0_w1_gate_s1_6fd7878c` | W1 gate s1, fdsreader first-use | 2 | incomplete: time limit at 400.00 s, 199/200 evacuated, 1 remaining | 40.5 s / 30.4 s / 427 MB (wall inflated by the foreign process) |
| `g0_w2_nf_s1_6fd7878c` | W2 nf s1 | 0 | finished in 313.50 s, 200/200 | 17.2 s / 16.8 s / 147 MB |
| `g0_w3_tj_committed300_diag` | committed t_junction `config_discovery.json` (300 s), W3 flags, seed 42, vis-cache first-use | 2 | incomplete: time limit at 300.00 s, 70/150 evacuated, 80 remaining, 50 not spawned | 12.0 s / 11.2 s / 279 MB, including the vismap build |

### Activation table (perf-model handoff §2)

| Check | W1 gate s1 | W2 nf s1 | W3 (committed 300 s deck, s42) |
|---|---|---|---|
| Exit code; FdsHorizonError; "holding the last frame" | 2; no; no | 0; no; no | 2; **no**; no |
| Setup lines | smoke, FED, rerouting, tenability | rerouting only | smoke, FED, rerouting, **"Configuring visibility model (3 signs)"**, tenability |
| `walkable_outside_m2`; "Outside the FDS domain" line | 0.0; absent | null (no FDS); absent | 0.0; absent |
| Manifest | 6fd7878c, `git_dirty` false, `spawn-key-blake2b-v2`, lock 2731a9e7 | same | same |
| Spawning | 200 at frame 0, `agents_not_spawned` 0 | 200 at frame 0, 0 | flow spawning, 1 at frame 0, 150 spawned, **50 not spawned** |
| Anticipated horizon bound `max(time_s + path_length_m/base_speed)` | 430.6 s vs guard 481 s (margin 50.4 s) | n/a (no route-cost CSV) | 56.8 s vs guard 301 s. Route-cost rows exist only for t = 7–43 s. |
| Smoke speed factor < 1 while moving (rows / agents; min) | 4 951 / 123; 0.10 | n/a | 14 120 / 148; 0.10 |
| FED cumulative > 0 (rows; max) | 14 960; 0.0383 | n/a | 14 227; 0.366 |
| FIC > 0 | 0 rows (no HCl/HCN, as expected) | n/a | 14 320 rows, max 38.0 (recorded only) |
| Route-cost rows / route switches | 65 142 / 267 | no CSV (flag off) / 0 | 265 / 180 (170 `wander`, 10 `smoke_reroute`) |
| Incapacitation events | 0 | n/a | 0 |
| Vismap built or loaded / sign queries / cognitive-map growth | off (no visibility) | off | built and saved (npz written); **query and growth counts need G1 counters** |
| Remaining at cap, by state | 1 inside, 0 not spawned | 0 / 0 | 80 inside, 50 not spawned |
| Route / exit history rows | 267 / 200 (E 124, F 76) | 0 / 200 (E 114, F 86) | 180 / 150 |

**W1 determinism observation (correctness only, not the formal gate).** Three W1 gate seed-1 runs produced byte-identical outputs: the exit, route, FED and route-cost CSVs, and the trajectory rows `frame,id,pos_x,pos_y,ori_x,ori_y` (sha256 prefixes `f0bc5745`, `ddf9057e`, `781fa749`, `2f10f443`, `623a346a`):

| Commit | Python | `PYTHONHASHSEED` |
|---|---|---|
| `289b33d0` | 3.12 | unset |
| `6fd7878c` | 3.14 | unset |
| `6fd7878c` | 3.12 | 0 |

Pinning the hash seed therefore does not change W1 on these builds. The formal determinism gate (two baseline runs on the frozen build) is still a G1 step.

**t_junction horizon diagnostic.** The committed 300 s deck ran without `FdsHorizonError` and without a hold. This refutes the prediction for seed 42. The reason: route pricing (the route-cost CSV) happened only between 7 and 43 s, for 12 agents. Later route-history entries are `wander` (no anticipated pricing); the last one is at 296 s. Exit history assigns 25 of 150 agents to a non-exit target: `jps-distributions_0` 15, `jps-checkpoints_0` 10.

Whether a later pricing can happen with other seeds is not shown. perf-model must decide between:
- adopting the committed deck (as `scenarios.json` allows "if it runs cleanly");
- keeping cap 270 for margin.

perf-model must also decide whether 80 agents inside plus 50 not spawned is an acceptable W3 workload.

## 5. Resource limits and stop conditions (draft for `plan.md`)

**Exclusive slot precondition.** It was **not met today**. Before each measured block, `benchmark.py` checks and records:
- 1-minute load average < 1.5;
- no other `python`, `fds`, `pytest`, `uv` or `node` process above 20 % CPU;
- AC power on;
- low-power mode off.

If a check fails, the block does not start. If such a process appears during a run, that run is tagged `contaminated` and kept.

**Fixed for every run.** Runs are serial, in a fresh process per run, with `PYTHONHASHSEED=0`. The thread variables are recorded, and each run gets its own `TMPDIR` under `$STAGE/tmp`. P/E-core placement is uncontrolled, which is recorded as a limitation.

| Limit | Value |
|---|---|
| Per-run wall cap, normal W1/W2 | 300 s (about 7× the indicative time). Kill and record `timeout`. |
| Per-run wall cap, W3 / W4 | 300 s |
| Per-run wall cap, profiled runs | 900 s |
| Peak RSS cap | 4 GB normal; 8 GB under memray or Scalene (18 GB host) |
| Capture size | ≤ 5 GB per file. Larger captures go to sciebo `fds-evac-data/profiling/` with sha256. |
| Repeated-use cache | 1 untimed warm-up + 5 measured runs; up to 15 if IQR/median > 5 % |
| First-use cache | 3 runs. Before each: remove the own-stage `<chid>.pickle`; for W3, use a fresh `--vis-cache` path. |
| Headline seeds | seeds 2 and 3 × 3 runs |
| Paired variants | ABAB order, 5 + 5 |

**Budget**, at about 30 s per W1 run, 17 s per W2 run and 12 s per W3 run:

| Block | Runs | Estimate |
|---|---|---|
| Determinism gate, W1 and W3 | 4 | 2 min |
| W1 baseline: warm-up and 5 runs, first-use 3, seeds 2–3 | 15 | 8 min |
| W2: same structure | 15 | 5 min |
| W3: first-use 3, repeated-use 1 + 5, no-flag 5, seeds 43–44 | 20 | 5 min |
| Instrumentation overhead and equivalence | about 20 | 8 min |
| W1 output variants | 24 | 12 min |
| W1 N = 100/200/400 scaling, 1 + 5 each plus seeds | about 36 | 25 min |
| Profiles: pyinstrument, cProfile, Scalene, memray | about 12 | 30 min |
| W4 fixtures and pytest set | — | 10 min |
| QA slot | — | 20 min |
| **Total** | about 150 | **about 2–2.5 h exclusive; hard cap 4 h** |

**Stop conditions**, per experiment; other valid work continues:
1. Zero activation where "yes" is expected, spawned < planned (W1), or a coverage/horizon failure.
2. Determinism or equivalence broken. There is no tolerance.
3. The cache state cannot be identified.
4. A wall or RSS cap is hit twice in one configuration.
5. IQR/median > 10 % after 15 runs, or the host check fails repeatedly. Report that configuration as inconclusive.
6. 4 h of total budget is used. Report PARTIAL.

## 6. Uncertainties

- Every wall time and RSS figure above comes from a loaded host. They size the limits only.
- The OS page cache was warm: the FDS files had just been copied and hashed. All runs are "process-fresh, page-cache uncontrolled".
- The W3 horizon result covers seed 42 only. The 25 agents whose exit-history target is not an exit were not investigated.
- The W1 agent remaining at 400 s is inside the building, not unspawned. Its cause is not investigated.
- Agent-steps are not measured. Agent-frames at 10 fps are W1 326 873, W2 300 202 and W3 144 000; the G1 counter must replace them.
- fdsreader logs a harmless "Module vents" parse warning in every W1 run.
- In the W1 route-cost CSV, `max(time_s + travel_time_s)` is 825.8 s, far above the guard, and no error occurs. `travel_time_s` therefore includes delays and is not the sampling horizon; the `path_length_m/base_speed` bound (430.6 s) is the one to use. perf-model should confirm.
- I did not edit `model_handoff_g0.md`. The filled activation table is in §4 above.

## 7. What perf-model must check

- Decide between the committed t_junction deck and cap 270, given §4. Judge whether W3's 80 inside, 50 not spawned and 25 non-exit targets make an acceptable workload.
- Confirm the horizon-bound definition, and the W2 expectation of 0 route switches.
- Define the counters W3 needs, for vismap build/load, sign queries and cognitive-map updates. I will implement them in G1.

## 8. What perf-qa must check

- The three run manifests match commit `6fd7878c`, lock `2731a9e7` and `git_dirty` false.
- `results/stage_verification.json` shows 8/8 directories matching `preflight/input_hashes.json`. Re-run with `$PY studies/profiling/verify_stage.py /Users/chraibi/profiling-stage /tmp/x.json`.
- The sciebo pickles are untouched: size and mtime equal `scenarios.json` `user_caches_untouched`.
- The profiling venv executes the same code as the baseline venv: same lock, `pyfds_evac` from `$WT`.
- Accept the py-spy/root gap, or get the maintainer's decision.
- The limits, rep counts and stop rules in §5. The exclusive-slot precondition was **not** met during G0. The coordinator must stop the `release-check` job and any other agent before G1.
- No G0 run is used as a measurement. `results/raw/g0_w1_gate_s1_repro/` (`289b33d0`) is marked SUPERSEDED.

## 9. After the G0 resolution (model §8, plan.md)

### 9.1 W3 horizon check, seeds 43 and 44

Both seeds ran the committed 300 s deck (untimed) with the same flags as the seed-42 diagnostic. The commands are in `results/raw/g0_w3_tj_committed300_s{43,44}/cmd.sh`. The run IDs below omit the `g0_w3_tj_committed300_` prefix.

The latest anticipated sample time is the bound `max(time_s + path_length_m / 1.3)`.

| Run | Exit | FdsHorizonError | Hold | Latest anticipated sample time | Route-cost rows (time span) | Outcome at 300 s |
|---|---|---|---|---|---|---|
| `diag` (s42) | 2 | no | no | 56.8 s | 7–43 s, 12 agents | 70 out, 80 inside, 50 not spawned |
| `s43` | 2 | **no** | no | **58.8 s** | 6–45 s, 12 agents | 73 out, 77 inside, 50 not spawned |
| `s44` | 2 | **no** | no | **57.8 s** | 8–44 s, 12 agents | 70 out, 80 inside, 50 not spawned |

All three bounds are far below the 296 s switch threshold, with a margin of at least 237 s, so the **committed 300 s deck stands for all W3 seeds**. The run manifests show `git_dirty` false, lock `2731a9e7` and coverage 0. Route history is dominated by `wander` (s43: 134 of 145; s44: 165 of 177). Indicative wall time on the loaded host is about 15 s.

### 9.2 Counters draft: design

**No production diff and no branch.** I implemented the counters as a wrapper harness in the profiling package instead of a branch in `$WT`:

- `instrument/perf_counters.py` defines the counters;
- `instrument/perf_run.py` runs `run.py` with the same arguments, under `runpy`.

The hooks wrap existing functions and methods. Each calls the original with identical arguments and returns its result unchanged. They count from arguments and return values only, and the process writes one JSON file at exit. Without `PYFDS_PERF_COUNTERS_OUT` the runner installs nothing.

Why this instead of a branch: instrumented and baseline runs then execute the same commit, with `git_dirty` false. The equivalence check compares one code path, not two. The coordinator can still ask for a branch.

How to run it (cwd `$WT`, any `run.py` arguments):

```
PYTHONHASHSEED=0 PYFDS_PERF_COUNTERS_OUT=$OUT/counters.json $PY $STUDY/instrument/perf_run.py <run.py args>
```

| Model §8 counter | Hook | Output keys |
|---|---|---|
| Vismap state and time | `visibility._load_vismap_cache`, `_build_cache_from_fds`, `_resolve_vis` | `vismap_events`: `load_hit` / `load_miss` (+ whether the file existed), `built` (seconds, time points, `vis` shape T×signs×H×W), `resolve` (seconds, signs); `vismap_resolve_calls` |
| Sign queries | `VisibilityModel.node_is_visible`, `visibility_to_node` | `*_calls`, `*_calls_by_<caller>` (`_expand_visible` / `expand_on_arrival` / `init_cognitive_map` / `other`), `node_is_visible_true`, `visibility_to_node_not_none`, `*_off_grid`; 10 s bins |
| Map growth | `cognitive_map.init_cognitive_map`, `expand_on_arrival`, `_expand_visible` | `*_calls`, `*_nodes_added`, `*_edges_added`, `*_growth_events`, `cognitive_maps_created`, `init_known_nodes`; `binned.agents_with_known_exit` (sampled at each 10 s boundary over every map created) |
| Discovery state, route evaluations | `route_graph.evaluate_and_reroute`, `rank_routes`, `evaluate_route`, `cognitive_map.nearest_frontier_target`, `wander_target` | `reroute_evaluations` split into `_exit_choice` / `_explore` / `_wander`; `reroute_switches`; `reroute_pass_sizes` (histogram of evaluations per 1 s pass); `rank_routes_calls`, `evaluate_route_calls`, `frontier_*`, `wander_*`; 10 s bins |
| Agent-steps, dt | `jupedsim.Simulation.iterate` | `agent_steps` (`agent_count()` before each step), `iterations`, `dt_s` from `delta_time()`; 10 s bins |

Known limits of the draft:

- The clear-air vismap (`VisibilityModel.clear_air`, used by W4-cmm) is not hooked yet.
- Eligible agents per pass are counted as evaluations, not as the loop-local `reroute_loop_agents`, because that count is not observable without a production diff.
- Growth from `_expand_visible` called inside `init_cognitive_map` is counted as `_expand_visible` growth.
- There are no timers yet for the mutually exclusive loop categories or for field sampling by caller. These are the next G1 step; they need an overhead check.

### 9.3 Smoke tests (development only, not measurements, host loaded)

`results/raw/dev_counters_w3_s42/` and `results/raw/dev_counters_w1_s1/` use exactly the G0 commands, run through `perf_run.py`.

**Equivalence.** All outputs are byte-identical to the uninstrumented G0 runs:
- the exit, route, FED and route-cost CSVs;
- the trajectory rows `frame,id,pos_x,pos_y,ori_x,ori_y` (W1 `623a346a`, W3 `3fcaeaa4`);
- the W3 log apart from progress wall times;
- every array in the W3 vismap `.npz`.

The formal ≤ 5 % overhead and equivalence check stays in G1, on the exclusive host.

**First counts:**

- **W1 gate s1.**
  - Work: `dt` 0.01 s, 40 000 iterations, **3 267 817 agent-steps**.
  - Routing: 32 571 reroute evaluations, all `exit_choice`, with 267 switches. There were 65 342 `rank_routes` calls and 29 394 `evaluate_route` calls.
  - Visibility: no sign queries and no vismap, as expected. The 200 cognitive maps are full familiarity.
- **W3 s42.**
  - Work: 30 000 iterations, 1 440 372 agent-steps.
  - Vismap: built once in 0.60 s, with 301 time points × 3 signs × 53 × 121 cells. The cache load before it was a miss because the file did not exist.
  - Sign queries: 21 169 `node_is_visible` calls. Of these, 20 720 come from `_expand_visible` and 449 from `expand_on_arrival`; 410 returned true. The queries run through the whole run, rising from 135 to 1 342 per 10 s bin. There were 0 `visibility_to_node` calls.
  - Map growth: 41 events from `_expand_visible` and 92 from `expand_on_arrival`.
  - Routing: 14 434 evaluations, made up of 14 040 wander, 214 explore and 180 exit-choice.
  - `agents_with_known_exit`: rises to 12 by 30 s, then stays at 12 to 290 s.

**This meets the §8 acceptance condition in substance:** sign queries > 0 after 43 s, map growth > 0, and one vismap build per process. The G1 baseline must confirm it formally.

### 9.4 Observations for perf-model

1. **Route-cost history output doubles `rank_routes`.** With `--output-route-cost-history`, `scenario.py` (about line 2690) calls `rank_routes` once per evaluation for the history, then `evaluate_and_reroute` ranks again. In W1, `rank_routes` calls = 2 × 32 571 evaluations + 200 initial choices = 65 342.
   - The two calls share `route_segment_cache`, so the extra cost is unknown.
   - This is a leading candidate for the "normal versus minimal output" controlled experiment. Decide whether route-cost history belongs to the normal W1 output.
2. **W3 sight queries use `node_is_visible` only.** `visibility_to_node` was not called in W3.
3. **Only 12 W3 agents ever have an exit node in their cognitive map, yet 70 evacuated.** The count covers all maps created, including those of agents already removed. Please check whether agents can leave through an exit they never knew (scripted journey, or walking through it), or whether my exit-node set from `stage_type == "exit"` misses something. It does not affect timings, but it bears on how W3 is described.

### 9.5 What perf-qa must check

- That §9.1 settles D5: one window, the committed deck, for all W3 seeds.
- That the wrapper approach is acceptable as "instrumentation separate from the baseline", and that the hooks are observational. Read `instrument/perf_counters.py`.
- That the dev smoke-test equivalence is not taken as the formal G1 equivalence or overhead result.

## 10. G1 entry items (review.md I1, I2, I4, I5; O3, O5–O7; model §10)

All runs below are `--shared` development runs (`measurement_status: not_a_measurement`), made on a loaded host with load average 4–8 and foreign Python processes at up to 99 % CPU. Every manifest records `contaminated: true`.

### 10.1 Harness (I4): ready for perf-qa review before the first measured block

New files:

| File | Role |
|---|---|
| `benchmark.py` | Harness. `check` runs the slot check; `run` runs a block (`--dry-run` plans without changing anything). |
| `analyse.py` | Builds `results/summary.csv` and `results/summary_groups.csv` |
| `traj_hash.py` | Trajectory hash |
| `README.md` | Recreate recipe (O6), staging, verification, exact G1 block commands |

What `benchmark.py` does:

- **Slot gating.** `--exclusive` refuses to start unless the slot check passes. `--shared` runs are never measurements.
- **Clean-worktree check.** The worktree must be at `6fd7878c`, with lock `2731a9e7`, and `git status --porcelain --untracked-files=all` empty. Ignored files other than the venvs are also recorded.
- **Fixed environment (O5).** `PYTHONHASHSEED=0`, `PYTHONUNBUFFERED=1`, `OMP_NUM_THREADS=4`, `VECLIB_MAXIMUM_THREADS` unset (Accelerate default), and a per-run `TMPDIR`.
- **Timing.** The parent measures wall time. `/usr/bin/time -l` gives CPU and peak RSS for the process tree. Phases come from the stdout markers "Simulation started." and the summary line.
- **Host monitoring.** `ps` is sampled every 15 s to tag contamination.
- **Timeout.** Kills the process group after 300 s (900 s for profiled runs).
- **Manifest.** Contains every §11 field, the instrumentation sha256 (`instrument/*.py` and `benchmark.py`), and whether counters were on.
- **Variant interleaving.** Paired variants run interleaved: `--variants A,B`, and `--instrument none,counters` for the overhead block. The overhead baseline is plain `run.py`, never `perf_run.py` with counters off.
- **Outputs.** Run outputs go to `$STAGE/runs/<run_id>/` and their sha256 to the manifest. Warm-ups and failures are kept.

`benchmark.py check` fails today (load average 4.1 and two foreign Python processes). The I6 blocker is therefore unchanged.

### 10.2 fdsreader cache (I1)

Counters now wrap `fdsreader.Simulation.__new__` and `__init__`. They record:
- whether a pickle is present at each open;
- for each open, whether it was a `pickle_load` (object came from the cache) or a `full_parse`;
- seconds per open.

**Confirmed, W3 seed 42** (`dev10_W3_O_study_s42_rep1_20261002T153508` / `…T153521`):

| State at process start | Opens | Pickle loads | Full parses |
|---|---|---|---|
| No pickle (first use) | 8 | 1 | 7 |
| Pickle present (repeated use) | 8 | 1 | 7 |

- In both states, every open after the first re-parses the `.smv`, about 0.011–0.025 s each.
- In first use, the second open loads the pickle that the first parse just wrote.
- The two states therefore differ by about one parse, of order 0.01–0.03 s, measured on a loaded host. This supports "small" for the fdsreader cache itself. It is not a timing result.

Other cases:
- W1 n400 with a pickle present: 5 opens, 1 load, 4 parses.
- W3b-cmm with no pickle: 8 opens, 1 load, 7 parses.

Labels are now derived from what was observed, as defined in model §10:
- `first_use` means no pickle at process start, and the first open must be a `full_parse`;
- `repeated_use` means a pickle was present, and the first open must be a `pickle_load`;
- if the counters disagree, `counters_agree` is set false and the run is relabelled, not dropped.

The pickle (presence, bytes, sha256) and the vis cache are recorded before and after every run.

The manifest of dev run `…T153508` still carries `counters_agree: false`. That label came from my first, stricter rule, which wrongly treated the second-open pickle load as a disagreement. Under the current rule, which only checks the first open, it agrees.

### 10.3 Sign-query split (I2, model §10)

`node_is_visible` and `visibility_to_node` are now split into three kinds:

| Kind | Meaning |
|---|---|
| `sign` | sign node, observer in the grid |
| `off_grid` | sign node, observer off the grid |
| `non_sign` | node without a descriptor, which is always True |

Each kind counts calls and positive results, by caller and in 10 s bins. Map growth is split into sign and non-sign nodes added. The clear-air vismap path (`VisibilityModel.clear_air`) is now hooked as well. W3b-cmm does not use it, because its FDS run has an extinction slice: it builds the smoke-aware map (0.13 s, 121 × 2 × 131 × 23).

| Run | Sign calls | Sign positive | off_grid / non_sign | Map growth from sign nodes |
|---|---|---|---|---|
| W3 s42 | 21 169 | 410 | 0 / 0 | `_expand_visible` 41 events (41 nodes); `expand_on_arrival` 92 events (97 nodes); non-sign nodes added: 0 |
| W3b-cmm s5150 | 666 | 467 | 0 / 0 | `_expand_visible` 40 events |

W3 sign-positive results by 10 s bin:

| Bins | Positive results per bin |
|---|---|
| 0–40 s | 33 / 125 / 105 / 83 / 28 |
| 50–90 s | 8 / 4 / 1 / 1 / 1 |
| ≥ 100 s | 1–4 in 10 of the 20 bins (21 in total) |

Meanwhile, sign calls per bin rise from 35 to 1 342.

**This partly disagrees with QA's I2.** QA reads the vis cache's visible fraction as 0 for every sign at 100–300 s. The counters nevertheless record 21 sign-positive results at t ≥ 100 s, all in the grid. I have not resolved this. Possible causes:
- the fraction was rounded;
- the query time or position snaps to a grid cell or time point that is visible.

perf-model and perf-qa should check one of these queries against the array.

Under the model §10 criterion (sign-True > 0 and growth from sign sightings > 0, with non-sign and off-grid counted separately), W3 shows activation. G1 confirms it on the baseline.

### 10.4 W2 route evaluations (I5)

`dev10_W2_nf_s1_rep1_20261002T153554` made 29 910 evaluations (all `exit_choice`, 0 switches). Every 10 s bin from 0 to 310 s has evaluations: 1 800–2 000 per bin early, then falling as agents leave, to 7 in the last bin. Routing work is therefore present across the whole clear-air run. Work: 3 001 088 agent-steps, 31 350 iterations.

### 10.5 Optional items

- **O3, trajectory hash.** `traj_hash.py` defines `repr-v1`: comma-joined `repr` of `frame,id,pos_x,pos_y,ori_x,ori_y` ordered by `frame,id`, one row per line, sha256. It also prints the `sqlite-cli` recipe (sqlite3 list mode, `%!.15g`). For `g0_w1_gate_s1_6fd7878c` these give `1ef52fdc…` (repr-v1, equal to QA's) and `623a346a…` (sqlite-cli, the value in my G0 handoff). The harness records repr-v1.
- **O5, threads.** Thread settings are fixed by the harness (§10.1) and documented in the README.
- **O6, recreating the environment.** The worktree and both venvs can be rebuilt from scratch with the README §1–2 recipe.
- **O7, N = 400.** `dev10_W1_n400_O_study_s1_rep1_20261002T153615` placed **400 of 400 agents at frame 0**, with `agents_not_spawned` 0. At 400 s: 379 out, 21 inside. Work: 8 607 732 agent-steps, 85 868 evaluations, 707 switches, 172 136 `rank_routes` calls. Indicative only: about 80 s loop and 620 MB RSS on the loaded host. The 300-agent fallback is not needed.

### 10.6 Observations for perf-model

- **W3b-cmm.** The config sets `dt: 0.05`, but the run executed 2 147 iterations at dt 0.01 s, because `jps.Simulation` is built without `dt` (see `scenarios.json`).
- **Indicative W3 phases (loaded host).** Startup was about 1.4–1.6 s, including the 0.6 s vismap build; the loop about 10 s; finalisation about 0.24 s.

### 10.7 What perf-qa must check

- Review `benchmark.py`. This is the I4 entry condition. Check in particular:
  - slot gating;
  - the manifest fields;
  - the derivation of cache labels;
  - the interleaving of paired combinations;
  - that the timeout kills the process group;
  - that `--dry-run` has no side effects;
  - the stdout-marker phase method under `PYTHONUNBUFFERED=1`. This is the same for every run, but it differs from `scenarios.json`, which redirects stdout to a file.
- The `counters_agree` rule (§10.2).
- The disagreement on late sign-positive results (§10.3).

## 11. perf-qa follow-up F1–F6 and model §11.2

All runs below are `--shared` development runs, not measurements, on a busy machine. Run IDs: `dev11cmm_*`, `dev11w3_*` and `dev11w3plain_*`.

### Fixes in `benchmark.py`

- **F1, contamination coverage.**
  - The host is now sampled every 2 s (`--monitor-s 2`).
  - A slot check runs after each run, as well as before.
  - The manifest now records `contamination_reasons`: `foreign_heavy_before`, `foreign_heavy_during`, `foreign_heavy_after`, `load1_before` and `power`.
  - Check: the 11.4 s W3 counters run got 5 samples.
- **F2, phase names.** The phases are now named `phase_pre_run_s`, `phase_run_scenario_s` and `phase_post_run_s`. Their content is defined in the docstring and the README. `analyse.py` now reports rates per `run_scenario` (`run_scenario_s_per_sim_s`, `run_scenario_us_per_agent_step`).
- **F2, in-process loop timer (G2).** It is built into the counters (`counters.json` `timers_s`) and is diagnostic.
  - It measures `run_scenario` total time, setup before the first `iterate`, first `iterate` to the end of the last, and the tail after the last `iterate`.
  - W3 s42, counters run (indicative only): run_scenario 9.88 s = setup 0.13 s + loop 9.70 s + tail 0.04 s. Pre-run took 1.26 s and post-run 0.26 s.
  - The overhead of this timer is part of the G1ovh check.
- **F4, self-load.** `load1_before` is recorded as a reason of its own, separate from the foreign-process reasons. The first exclusive block will show whether it trips on back-to-back runs alone. I will report to the coordinator before any rule change.
- **F5, dry runs.** `--dry-run` now creates no directories. A missing repeated-use cache is reported as a `DRY-RUN WARNING` instead of aborting. I removed the leftover `dry_*` directories, all of which were my own.
- **F6, manifest gaps.** The manifest now also records:
  - `geometry.wkt` sha256 next to each scenario, which covers the derived scenarios;
  - `venv_fingerprints`: the `uv pip freeze` sha256 of the baseline and profiling interpreters;
  - `profiler_options`, including pyinstrument's wall-clock 1 ms main-thread mode (O1).
  - The README points to `scenarios.json` for the W4, cmm arm A and pytest commands.

### F3, equivalence tool

`compare.py` implements the 12 items of model §11.2:

| # | Item |
|---|---|
| 1 | trajectories, repr-v1 |
| 2 | spawn and removal frames |
| 3–7 | exit, route, route-cost, FED and smoke CSVs, byte-equal |
| 8 | `agent_scalars` rows |
| 9 | app-manifest fields, with paths and `created_utc` excluded |
| 10 | exit code, summary line, switch and sample counts |
| 11 | vismap arrays, with meta compared without `fds_dir` |
| 12 | cognitive-map history plus result metrics, with wall, path and file keys excluded |

How it judges a pair:
- an item written by only one run is `not_in_both`; an item written by neither is `absent`;
- any `DIFFERENT` item means `NOT equivalent`;
- missing items are listed as gaps.

**Item 12.**
- `perf_run.py` has an opt-in variable, `PYFDS_PERF_RESULT_OUT` (in the harness, `--capture-result`). It wraps `pyfds_evac.core.run_scenario` and writes `result.cognitive_map_history` and `result.metrics` to JSON after the call.
- Item 12 is compared only when both runs carry the capture, so both go through `perf_run.py`.
- A W3 pair without it reports the gap "cognitive-map state not compared".

Dev checks, all results in `results/equivalence/dev11_*.json`:

| Pair | Verdict | Notes |
|---|---|---|
| W3b-cmm: capture vs capture + counters | equivalent | items 1–4 and 8–12 equal; 5–7 absent |
| W3 s42: capture vs capture + counters | equivalent | items 1–6 and 8–12 equal; 263 cognitive-map events |
| W3 s42: plain `run.py` vs capture + counters | equivalent on items 1–11 | gap: "cognitive-map state not compared" |

### Ask

perf-qa should re-read the diff:
- `benchmark.py`
- `analyse.py`
- `compare.py`
- `instrument/perf_counters.py` (fdsreader, run_scenario and loop timers)
- `instrument/perf_run.py`
- README §3–§6

No measured runs will start until the coordinator says the machine is free.

## 12. Review follow-up 2: C1, O8, O9

- **C1, capture runs.** A `--capture-result` run is now always `not_a_measurement`, whatever the block type (`benchmark.py`). Its run ID carries `_cap`, and `analyse.py` groups additionally by `result_capture` and `entry_point`. Capture runs can therefore never enter timing statistics.
- **O8, W3 determinism gate.** It is planned with `--capture-result` on both runs (README §3), so the gate also compares item 12, the cognitive-map history. It is followed by `compare.py --block G1det` and a negative control.
- **O9, negative control.** `compare.py --negative-control RUN` copies one run into a temporary directory under `results/` three times:
  - an unchanged copy, which must be equivalent;
  - a copy with one digit of `exit.csv` changed, which must be detected as item 3 only;
  - a copy with one trajectory `pos_x` moved by one ulp, which must be detected as item 1.

  Dev check on `dev11w3_W3_O_study_s42_rep1_20261002T154559` gave **PASS** (`results/equivalence/dev11_negative_control_w3.json`).

No measured runs have been made. The next step is waiting for the coordinator's free-machine signal, which closes I6.

## 13. Freeze moved to v0.2.0 (`3ef4ea75`)

**Rebuild.**
- New worktree `<P>/wt020`, detached at tag `v0.2.0` = `3ef4ea75e485c459a0a1e677d87fe1a9be728b09`, clean with untracked files included.
- Both venvs were rebuilt with `UV_CACHE_DIR=<P>/uvcache uv sync --frozen --python 3.12` (CPython 3.12.13):
  - baseline venv `<P>/wt020/.venv`;
  - profiling venv `<P>/venv_prof020`, which adds py-spy 0.4.2, scalene 2.3.0, memray 1.20.0 and pyinstrument 5.1.3.
- `uv.lock` sha256 is now `171626cd812919ab36b49a90299337e5379509ec15a23a6cfd42322f12e3e337`. pyfds-evac reports 0.2.0, and scikit-image stays at 0.23.2.
- The third-party packages are identical to those at `6fd7878c`: `uv pip freeze` of the two baseline venvs differs only in the editable path.

**Code unchanged.** `git diff 6fd7878c v0.2.0` changes nothing in `pyfds_evac/`, `run.py`, `app.py` or the asset configs. The only asset changes are `cognitive_map_memory/README.md` and its png.

**Updated.**
- `benchmark.py` defaults now point at `wt020`, its `.venv` and `venv_prof020`. `COMMIT` and `LOCK_SHA256` are updated, so the clean-worktree check enforces v0.2.0.
- README §1 commands are updated.
- `environment.json` was regenerated. The previous copy is kept as `results/raw/g0_w1_gate_s1_repro/environment_6fd7878c.json`.
- `results/stage_verification.json` was re-run: **8/8 OK**, with aggregates unchanged.
- The dev runs (`dev10_*`, `dev11_*`) and the G0 runs stay labelled with their original commits. None of them is a measurement.

**`benchmark.py check`** at 16:5x local: **ok = false**, so no block can start.
- The reason is load average 7.9 / 7.8 / 7.5.
- No process matched the foreign-process pattern (python, fds, pytest, uv, node and so on).
- Top CPU users were Firefox GPU Helper 65 %, WindowServer 47 %, Firefox plugin-container 36 % and iTerm2 24 %.
- AC power on, low-power mode off.
- A dry run of a W1 block planned 1 run and left no files.

**Observation for the coordinator.** The foreign-process pattern does not cover desktop apps such as Firefox or its GPU helper. Here, only the load rule stops the block. If the maintainer's apps are open during G1 while load is below 1.5, they would not mark runs as contaminated. Decide in `plan.md` whether to add them to the pattern (for example `firefox|GPU Helper|plugin-container`), or to require them to be closed.

**Kept, not deleted.** The old `<P>/wt6` worktree and its venvs are kept, because the dev manifests reference them.

## 14. Contamination rule: any foreign process (coordinator decision)

**What changed in `benchmark.py`.**
- The rule is now: any process outside the benchmark's own tree above 20 % CPU (`ps`) contaminates a run, whatever its name. The name pattern is removed.
- The own tree is the benchmark process, its descendants (the run under test and its `ps` calls) and its parent shell, defined by a single helper, `own_tree()`.
- The rule is checked before the run, every 2 s during it, and after it.
- Each manifest records `host_during.offenders_max_pcpu` (process name → highest %CPU) and the rule text. The README is updated to match.

**Checks.**
- `benchmark.py check`: ok = false, with load average 5.8 / 7.3 / 7.3 and WindowServer at 26 % now flagged.
- A dry run of a W1 block planned 1 run and left no files.
- Dev run `dev13_W2_nf_s1_rep1_20261002T170402` (`--shared`, not a measurement) took 10 samples and recorded these offenders (highest %CPU):

| Process | Highest %CPU |
|---|---|
| headless Chromium (`ms-playwright/chrome-headless-shell`) | 816 |
| Firefox plugin-container | 98 |
| `top` | 65 |
| WindowServer | 54 |
| airportd | 24 |
| Element renderer | 24 |
| iTerm2 | 25 |
| Firefox GPU Helper | 22 |
| syspolicyd | 21 |
| mdworker | 20 |

**Points for the coordinator.**
1. A headless Chromium from Playwright, probably another agent's screenshot or QA job, was using about 8 cores.
2. WindowServer and system daemons (syspolicyd, mdworker, airportd) can exceed 20 % even with apps closed. Under the new rule they will mark runs as contaminated. The first exclusive block will show how often this happens.
3. `top` at 65 % was a process outside the benchmark, presumably someone's monitor.

## 15. System-process rule and detached launch (`plan.md` "System processes during measured blocks")

- **Thresholds.** `benchmark.py` applies different limits to system and other processes:
  - `WindowServer`, `kernel_task`, `mds`, `mds_stores`, `mdworker*`, `syspolicyd` and `airportd` flag a run only above 50 % CPU. They are matched on the basename of the `ps` command.
  - Every other process outside the own tree flags above 20 %.
  - Each sample before, during (every 2 s) and after a run records every system-list process plus any other process at or above 5 %.
  - The manifest gains `recorded_max_pcpu` (per-process maximum, with an exempt flag) and `offenders_max_pcpu`. The rule text includes the decaying-average note (O10).
- **Gap: `kernel_task` is invisible.** `ps` does not list it for a non-root user here, so it can be neither recorded nor flagged. This is noted in the README.
- **`launch_detached.sh`.** It runs `nohup caffeinate -s $PY benchmark.py run …` detached. The log goes to `results/blocks/<block>_<UTC>.log` with a `.pid` file, and the script then calls `pmset displaysleepnow`. With `--dry-run` it runs in the foreground and leaves the display alone. The parent of `benchmark.py` is `caffeinate`, which counts as part of the own tree.
- **Dry run.** `./launch_detached.sh --block dry --case W1 --exclusive --reps 1 --warmup 0 --dry-run` planned 1 run and left no files in `results/raw`, `$STAGE/runs` or `$STAGE/tmp`.
- **`benchmark.py check` now** returns ok = false:
  - load average 5.5;
  - flagged: WindowServer 52 % (above 50), Firefox GPU Helper 54 %, Firefox plugin-container 26 %;
  - recorded but not flagged: mds, mds_stores, mdworker_shared, syspolicyd and airportd, all below 2 %.

No measured block has run. Waiting for the coordinator's go.

## 16. G1 launch

**Driver.** `g1_all.sh` runs the G1 blocks serially in README order. Before each block it polls `benchmark.py check` every 60 s for up to 20 min and records `SKIPPED_SLOT` if the slot never passes. The 4 h hard cap applies (`SKIPPED_CAP`).

| Step | Blocks |
|---|---|
| 1. Determinism gate | `G1det`: W1, and W3 with capture |
| 2. W1 baseline | `G1base`, `G1first`, `G1seeds` |
| 3. W2 | `G1w2` |
| 4. W3 and W3b cache states | W3: `G1w3first`, `G1w3rep`, `G1w3noflag`, `G1w3seeds`; W3b: `G1w3bfirst`, `G1w3brep` |
| 5. Overhead | `G1ovh` (W1), `G1ovhW3` |
| 6. Output variants | `G1outchk`, then `G1out` |
| 7. Scaling | `G1scale100`, `G1scale400` (N = 200 is `G1base`) |
| 8. W4 fixtures | `G1w4`, plus iso22 a–d, cmm arm A and the W4 pytest set, untimed, in `results/raw/G1w4_extra/` |
| 9. Analysis, after all timed work | `compare.py` for determinism, negative control, overhead and output/cache variants; then `analyse.py` |

**Records.** Block status goes to `results/blocks/g1_status.tsv`. The driver log is `results/blocks/g1_all_<UTC>.log`, with `.pid` next to it.

**Launch.**
- Command: `nohup caffeinate -s bash g1_all.sh … &`, then `pmset displaysleepnow`.
- The launching agent ends its turn immediately and does not poll.

**Estimate.**
- Runs take about 70–80 min of exclusive time; slot waits add 0–20 min per block in the worst case.
- Expected end is about 1.5 h after the start, and 4 h at most by the cap.

**Not covered.**
- The W4 pytest set runs only on the uninstrumented worktree.
- G2 profiling is not part of this launch.
