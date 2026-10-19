# perf-engineer handoff, G0 v2 (re-freeze at 8f7d29a2)

v1 (`engineer_handoff_g0.md`, v0.2.0) is kept unchanged. Nothing below is a measurement: the machine was shared (other Python jobs and Firefox ran at 100 % CPU) and every run used `--shared`, so the harness stamped `measurement_status: not_a_measurement`.

## Inputs / commit

- Repo `pyFDS-EVAC`, commit `8f7d29a2e056db46183e8cccabce338c398606a1` (main after PR #790), detached worktree `/Users/chraibi/profiling-stage/wt_8f7d29a2`, clean (`git status` empty before and after every run).
- `uv sync --frozen --python 3.12` (pyproject: `>=3.12,<3.15`), `UV_CACHE_DIR=/Users/chraibi/profiling-stage/uvcache`. uv 0.10.4.
- `uv.lock` sha256 `7f64a58db6d321441e320ad47ba960dc51d25c4a8dbaff8e8d95ba09fac25fc8` (v1: `171626cd...`).
- Versions: CPython 3.12.13, pyfds-evac 0.5.0, jupedsim 1.4.2, fdsreader 1.11.7, fdsvismap 0.3.2, numpy 2.4.4, shapely 2.1.2, scikit-image 0.26.0 (v1 had 0.23.2; the new lock no longer holds it back). Baseline venv fingerprint: 74 packages, `uv pip freeze` sha256 `63e5772a...`.
- Profiler venv `/Users/chraibi/profiling-stage/venv_prof_8f7d29a2` (same lock plus py-spy 0.4.2, scalene 2.3.0, memray 1.20.0, pyinstrument 5.1.3) built; cheap (a few minutes). Not exercised. The profiler notes in `environment.json` (py-spy needs root on macOS, memray/scalene/pyinstrument work) are carried over from v1 and not re-verified with this venv.
- Staged FDS: `/Users/chraibi/profiling-stage/fds` (8 dirs), checked against `preflight/input_hashes.json`. Those hashes were taken at v0.2.0; the staged iso_table21/22 files are byte-identical to the 8f7d29a2 `assets/` copies (`diff -rq`).

## Files produced / changed (all in the profiling package; pyFDS-EVAC untouched, nothing committed)

- Created: `engineer_handoff_g0_v2.md`, `results/stage_verification_v2.json`, `results/blocks/g0v2_*.log`, `results/blocks/g0v2_exits.txt`, `results/raw/g0v2_*` (4 dirs, see below).
- Edited (paths and freeze constants only): `benchmark.py` (`ROOT`, default WT/PY/PROF paths, `COMMIT`, `LOCK_SHA256`, stage-verification reference name), `g1_all.sh` (`P`, `wt_8f7d29a2`), `launch_detached.sh` (`PY` default), `collect_env.py` (one hard-coded `venv_created_with` string), `README.md` section 1 (recreate recipe) and `wt020` references, `environment.json` (regenerated).
- Backups of the v1 `benchmark.py` and `environment.json` are in `/Users/chraibi/profiling-stage/tmp/` (`benchmark.py.v1`, `environment.v1.json`; the `benchmark.py.v1` copy predates all edits).
- Not updated, still v0.2.0: `plan.md`, `scenarios.json` (`target`, commit, lock, `run_py_sha256`, expected counts), `preflight/*.json` (the `fds_dir` fields name the old scratchpad), `preflight/hash_inputs.py` (`COMMIT`), `model_handoff_g0.md`, `review.md`. These are perf-model / coordinator documents; the `fds_dir` paths in `preflight/w4_*.json` are stale records.

## Commands executed

```bash
git -C .../pyFDS-EVAC worktree add --detach /Users/chraibi/profiling-stage/wt_8f7d29a2 8f7d29a2
cd /Users/chraibi/profiling-stage/wt_8f7d29a2 && UV_CACHE_DIR=/Users/chraibi/profiling-stage/uvcache uv sync --frozen --python 3.12
# profiler venv: README section 1
PY=/Users/chraibi/profiling-stage/wt_8f7d29a2/.venv/bin/python; cd $STUDY
$PY collect_env.py /Users/chraibi/profiling-stage/wt_8f7d29a2 environment.json --profiling-python /Users/chraibi/profiling-stage/venv_prof_8f7d29a2/bin/python
$PY verify_stage.py /Users/chraibi/profiling-stage results/stage_verification_v2.json      # 8/8 OK, run twice (before and after the smokes)
$PY benchmark.py check
for c in W2 W1 W3; do $PY benchmark.py run --block g0v2_$c --case $c --shared --label g0v2 --warmup 0 --reps 1 --instrument counters; done
$PY benchmark.py run --block g0v2_W3 --case W3 --shared --label g0v2 --warmup 0 --reps 1 --instrument counters --vis-cache first
```

Deviations from the brief: `--shared` (the CLI requires `--exclusive` or `--shared`), and `--instrument counters` so the wrappers could be checked (the runs go through `instrument/perf_run.py`, so they are diagnostic, not baselines). The first W3 call stopped by design ("repeated-use vis cache absent; run a warm-up first"), leaving an empty run dir `g0v2_W3_W3_O_study_ctr_s42_rep1_20261014T122925` and exit 1; kept, not deleted. W3 was re-run with `--vis-cache first`.

## Observations

Verification: stage 8/8 OK (`results/stage_verification_v2.json`). Scenario configs load under the current schema in all three cases. All 20 patched symbols in `perf_counters.py` still exist and are wrapped (checked by importing and reading `_perf_wrapped`); no wrapper change was needed. `perf_counters.py` was not edited.

| Run (`results/raw/...`) | harness exit | run exit | outcome | wall / CPU / peak RSS |
|---|---|---|---|---|
| `g0v2_W2_W2_nf_ctr_s1_rep1_20261014T122809` | 0 | 0 | completed, 200/200 at 313.53 s | 23.07 s / 20.6 s / 152 MB |
| `g0v2_W1_W1_O_study_ctr_s1_rep1_20261014T122834` | 0 | 2 | time limit at 400 s, 199/200 out, 1 inside, 0 unspawned (same as v1 G0) | 50.23 s / 49.9 s / 440 MB, log says `contaminated=True` (foreign Firefox process) |
| `g0v2_W3_W3_O_study_ctr_s42_rep1_20261014T122943` (vis first-use) | 0 | 2 | time limit at 300 s, 99/150 out, 51 inside, 50 not spawned (v1: 70/150 out) | 9.29 s / 9.0 s / 267 MB |

Run exit 2 is run.py's "incomplete" code, not a crash. Wall and CPU are indicative only: host load 4-5, counters on.

Counters (nonzero):
- W2 (no FDS): 31 353 iterations, 2 996 487 agent-steps, 29 862 reroute evaluations (all exit-choice), 30 062 `rank_routes`, 29 862 `evaluate_route`, 200 cognitive maps. Zero by design: fdsreader opens, vismap, sign queries.
- W1: 40 000 iterations, 3 259 925 agent-steps, 32 497 reroute evaluations, 172 switches, 65 194 `rank_routes`, 30 594 `evaluate_route`; fdsreader 7 opens, all full parses; vismap none; sign queries 0.
- W3: 30 000 iterations, 929 877 agent-steps, 9 352 reroute evaluations (all exit-choice), 13 switches, 18 854 `rank_routes`, 188 `evaluate_route`; `node_is_visible` 14 123 calls, all in-grid sign queries (13 867 from `_expand_visible`, 256 from `expand_on_arrival`), 364 positive; 34 sign nodes added by `_expand_visible` and 111 by `expand_on_arrival`; fdsreader 10 full parses; vismap `load_miss` then `built_smoke_aware` 0.46 s, grid 301 x 3 x 53 x 121, 3 signs. `visibility_to_node`, `off_grid`, `non_sign` are zero.

Findings for the harness and model:
1. **The fdsreader disk-cache state no longer exists in this code.** `pyfds_evac/core/fdsreader_adapter.py` (#716) turns fdsreader's pickle cache off and redirects the pickle path to an empty temporary folder for every open. Every open is therefore a full `.smv` parse, even though a `.pickle` sits in the staged dir (`pickle_present_at_open: true`, `fdsreader_pickle_loads: 0`). So `--fds-cache first|repeated` no longer separates two states, and the manifest `cache_label.counters_agree` is `false` in W1 and W3 for that reason (the label expects pickle loads for "repeated"). The harness was not redesigned. G1 "first-use vs repeated-use" has to be reduced to the vismap cache (W1/W3) unless perf-model wants an fdsreader-parse cost block instead; the adapter docstring puts that cost at 0.1-0.4 s for a large case, and the counter timings here are 0.02-0.045 s per open.
2. **W3 discovery behaviour changed.** v1 W3 (committed 300 s config) was dominated by 14 040 wander evaluations plus 214 explore. Here `explore`, `wander`, `frontier_calls`, `wander_calls` are all zero: `_decide_explore` was never reached, although the wrappers are attached (`nearest_frontier_target` and `wander_target` are looked up lazily at call time in `route_graph._decide_explore`, so the patch applies). Only 12 of 150 agents hold a known exit node (from 30 s on), yet 99 evacuated; I did not investigate how. Whether this W3 still exercises "discovery" as the model intended is for perf-model to decide (cf. the #743/#187 routing changes). Sign queries and vismap build/load are exercised.
3. Evacuation outcomes moved relative to v0.2.0 (W3 99 vs 70 out). Not a regression claim; different commit.
4. `benchmark.py check` works on this macOS and reports `ok: false` correctly: `foreign_heavy` listed two Python processes from `jupedsim-network-station` at ~100 % CPU, and other Python jobs and Firefox appeared in later samples. Exclusive slots will have to be arranged with the user.
5. Stage cache: `/Users/chraibi/profiling-stage/cache` is empty; the `--vis-cache first` run did not leave a file there.

## Uncertainties

- The `benchmark.py` sha recorded in the W2 and W1 manifests (`0e1c0620...`) differs from W3's and from the current file (`f76ade8c...`): I edited the stage-verification reference string while the block loop was running. Content difference is that one string.
- No overhead (counters vs none) or determinism check was done; nothing here supports ≤5 % overhead.
- Run-to-run equality, `--capture-result`, `compare.py`, `analyse.py` and `summary.csv` were not run or regenerated. `results/summary.csv`, `summary_groups.csv` still hold v0.2.0 data; `analyse.py` would mix them with the `g0v2_*` dirs unless filtered (it excludes `dev*`/dry-run by default; I did not check how it treats `g0v2`).
- Profiler functionality on the new venv is untested.
- Only W1 gate s1, W2 nf and W3 s42 were smoked; W4 fixtures, the W1 variants (O_norc, O_min), scaling cases `W1_n100`/`W1_n400` and a W1 first-use vismap path were not.

## What perf-model must check

- Is W3 still a valid discovery workload given zero explore/wander evaluations and 12 of 150 agents with a known exit; update expected mechanisms and activation criteria in `scenarios.json`.
- Re-derive expected counts and settings for the 8f7d29a2 defaults (CLI vs Python), including the `fdsreader_adapter` cache policy and what "cache state" now means for the plan.
- Whether W1 ending at 199/200 at 400 s (one agent inside, cause unknown, same as v1) is acceptable as a "time-limited" headline, and whether the horizon needs a decision.
- Decide the equivalence invariants and tolerance for this commit before any G1 comparison.
- Review the stale v0.2.0 content in `scenarios.json` / `plan.md`.

## What perf-qa must check

- That the frozen worktree is clean and `uv.lock` hash matches (`benchmark.py` enforces both), and that the 8/8 stage check is reproducible.
- That the `g0v2_*` runs are labelled `not_a_measurement` and are excluded from any summary (including the empty `..._122925` dir, which is an incomplete record, not data).
- That the cache labels in G1 manifests are not read as pickle-based first/repeated use (finding 1).
- That the exclusive slot is genuinely exclusive before G1; `benchmark.py check` was `ok: false` throughout this session.
- That the path edits are limited to the files listed above (`diff` against `/Users/chraibi/profiling-stage/tmp/benchmark.py.v1`).

---

# §G0 v2b: harness changes, counters, fixtures, staging, normal runs (2026-10-14)

Untimed; the machine stayed shared (other Python jobs at ~100 % CPU), all runs `--shared`, `measurement_status: not_a_measurement`. Same worktree `/Users/chraibi/profiling-stage/wt_8f7d29a2` at `8f7d29a2e056db46183e8cccabce338c398606a1`, clean before and after (`git status --porcelain --untracked-files=all` empty, also after the pytest set). Nothing changed in pyFDS-EVAC.

## 1. D13: fdsreader cache removed from the harness

- `benchmark.py`: `--fds-cache`, the pickle presence/removal logic, `cache_state_requested.fdsreader` and the pickle-based `counters_agree` are gone. `cache_label` now holds `vis` (first_use / repeated_use / noflag), `fds_opens_per_process`, `fds_open_seconds_total`, `fds_opens_by_opener` ({opener: opens, seconds}) and `vismap_events`; `counters_agree` only checks a repeated vis cache against a load event. Seconds are the `.smv` parse inside `Simulation.__init__`, reported as a setup sub-phase.
- `analyse.py`, `g1_all.sh`, `launch_detached.sh`, README: `--fds-cache`, the `G1first` block and the `fdsreader_cache` grouping column removed; `analyse.py` row now carries the two open fields. `analyse.py` was only syntax-checked, not run.
- New `--instrument detail` (counters plus the caller-keyed group of §2); the run ID tag is `_det`. `W4_flow_saturated` case added to `CASES` (not run).
- `instrument/perf_counters.py`: each fdsreader open records its opener (first frame outside fdsreader and the adapter). The vismap build is timed in stages: `extinction_slice_index_open` (its own open), `read_fds_data`, `slice_read_lazy` (fdsvismap reads the whole extinction slice lazily on first `get_extco_array_at_time`, inside `compute_all`), `compute_all_incl_slice_read`, `vis_bool_array`, `vis_metre_array`. Kernel = `compute_all` minus `slice_read_lazy`, plus `vis_metre_array`. Counters `get_visibility_array_calls` (+ seconds), `get_mean_extco_array_calls`, `get_extco_array_calls`.
- Backups of the pre-edit files: `/Users/chraibi/profiling-stage/tmp/{benchmark.py.v2pre,perf_counters.py.v2pre,input_hashes.v1.json,scenarios_pre_v2/}`.

## 2. The model's §2 counters (opt-in, `PYFDS_PERF_DETAIL=1`, via `--instrument detail`)

Hooks bind on current symbols (checked by running W3 and all four normal runs). Production code unchanged; arguments and return values pass through.

| Counter (key in `counters.json`) | Wrapped |
|---|---|
| `sampler_sample_calls[<quantity>|<caller<-caller2>]`, `detail.sampler_distinct_xy` (distinct exact `(x, y)` per key) | `SliceFieldSampler.sample` |
| `read_cells_calls`, `read_cells_cells` (returned array size) | `SliceFieldSampler.read_cells` |
| `line_parts_hits/misses/clears`, `time_index_hits/misses` | `SliceFieldSampler.line_parts`, `_time_index` (read-only cache probe before the call) |
| `generate_candidates_calls/edges/segment_misses/segment_hits/no_cache_dict[<scenario function:line>]` | `route_graph._generate_candidates`; edges = phase-1 edge count, misses = `evaluate_segment` calls made from `_generate_candidates` itself, hits = edges - misses |
| `evaluate_segment_calls[<caller:line>]` | `route_graph.evaluate_segment` |
| `reached_stage_calls[<stage_type>|<polygon>]`, `distance_to_polygon_calls` | `direct_steering_runtime.reached_stage` (also rebound in `scenario`), `distance_to_polygon` |
| `occupied_calls/agents`, `crowds_agents_calls/true`, `flow_spawns_deferred_steps` | `simulation_init._occupied`, `_crowds_agents`, `scenario._defer_flow_spawn` |

The detail group walks 1-3 stack frames per call and keeps a set of sampled keys: its overhead is unmeasured, so every detail run is diagnostic-only until the overhead block runs. The base counters group is unchanged. Not captured: the route FED-midpoint sampling does not appear in any run (no `sample` caller of that kind), so `fed.py` is the only FED sampler caller seen; `to_global` is not counted (it runs once, inside `slice_read_lazy`).

## 3. D16: `w4_flow_saturated` (built, NOT run)

- `scenarios/make_derived.py` now reads from `pyFDS-EVAC` at `8f7d29a2` (constants `REPO`, `COMMIT`); the other four derived configs regenerate byte-identically (checked by `diff -r` against the backup). New function `make_flow_saturated` writes `scenarios/w4_flow_saturated/config_flow_saturated.json` (sha256 `e3f3540b0614bf35bba8bf63d0ac6f3403d43c98aab37333c723b9d2facdabf4`) plus `geometry.wkt` (copy of `assets/t_junction/geometry.wkt`).
- Diff for perf-model: `w4_flow_saturated.diff` (config vs `config_discovery.json`, then the `make_derived.py` diff).
- Changes: `max_simulation_time` 200; `jps-distributions_0` becomes the flow (number 300, 0-60 s, premovement constant 100 s, familiarity full); new `jps-distributions_1` on the same 28 m² polygon, 150 agents at t = 0 (`use_flow_spawning` false, same premovement); second journey `journey_1`, its transitions and a `waypoint_routing` entry. Both groups wait 100 s, so the area fills; I set the flow agents' premovement too, which the model text did not say: without it they walk away and the area never saturates.
- Preflight by `--show-config` only (`rules.py` runs `_check_spawn_capacity`): exit 0, Errors none, Setup warnings none, rerouting on every 1 s, visibility off. `_estimate_max_capacity` for the polygon at r = 0.15 is 198 (150 standing fits; the 300-agent flow is checked as a rate, 5 /s). Unverified until it runs: whether placement actually defers (flow spacing 0.3 m should allow roughly 300-350 positions in 28 m², so 450 requested agents should saturate) and for how many steps. Acceptance remains perf-model's (`flow_spawns_deferred > 0` for ≥ 1000 steps).

## 4. D15/D17: staging and preflight

Copy only (`rsync -a --exclude '*.pickle'`), sciebo untouched, hashes compared source vs copy before being appended:

| Staged | Source (sciebo `fds-evac-data/`) | Files | Aggregate sha256 (first 12) |
|---|---|---|---|
| `/Users/chraibi/profiling-stage/fds/fed_incap_co_2000ppm` | `fed_incap_co_2000ppm/fds` | 177 | `09c76e3d4330` |
| `/Users/chraibi/profiling-stage/fds/world100_fire_4p5MW` | `world100/fire_4p5MW` | 128 | `1a3c577c8e5c` |
| `/Users/chraibi/profiling-stage/decks/world100_evac_4exits/` | `deck_config_stream_east.json`, `deck_geometry.wkt` (hashes in `sciebo_files`) | 2 | n/a |

`preflight/hash_inputs_v2.py` appended the entries to `preflight/input_hashes.json` (v1 entries untouched); `verify_stage.py` MAP extended; `results/stage_verification_v2.json` now shows 10/10 OK. Preflight JSON: `preflight/fed_incap_co_2000ppm.json`, `preflight/world100_fire_4p5MW.json`.

- **fed_incap_co_2000ppm**: 4 meshes, 1001 frames, 0-1000 s, interval 0.92 s; slices at 0.5/1.5/2.0/2.5 m (CO, CO2 [1.5, 2.0], O2, SOOT EXTINCTION COEFFICIENT 1.5 and 2.0, VISIBILITY, soot mass); extinction ≈ 0.9993 /m, nearly constant. The deck (`assets/fed_incap_co_2000ppm/config.json`) has 24 checkpoints + 1 exit and `max_simulation_time` 1000. Passes horizon (1000 + 0.92).
- **world100 (D17): FAIL on the horizon.** The FDS output ends at 250.0 s (interval 2.0 s, 126 frames, extinction/CO/CO2/O2 at 2.1 m, 8 meshes); the deck caps at 330 s. `--show-config` exits 1: "max_simulation_time=330.0 s runs past the FDS output ... pass --allow-fds-horizon-hold". With `--allow-fds-horizon-hold --require-fds-coverage` the config loads with Errors none, so coverage of the deck by the slice domain is not the problem; but holding the last frame for 80 s is a horizon relaxation I did not apply, and lowering the cap to 250 s would be a different workload. Per D17, W1r is dropped unless the coordinator chooses one of those two changes.
- **V-build sizing trial** (`vbuild.py`, one untimed run, n = 10, deck `assets/fed_incap_co_2000ppm/config.json`, 25 signs, grid 61 x 61): `results/vbuild_trial_n10.json` (+ `.counters.json`). Total 0.587 s: `_build_vismap` 0.535 s (slice-index open 0.069, `read_fds_data` 0.039, lazy slice read 0.035, `compute_all` incl. slice read 0.426), `_vis_bool_array` 0.0001 s, `_vis_metre_array` 0.051 s (0.205 ms per (t, wp)); 500 `_get_visibility_array` calls = 2 x 10 x 25; peak RSS 225 MB; 10 distinct extinction frames among 10 time points. Fixed cost about 0.14 s, variable about 0.045 s per time point, so the full 1000 points would take about 50 s unprofiled. **Chosen n = 1000 (the whole deck)**: with a profiler factor up to 15 it stays under 900 s and needs no extrapolation; if perf-model prefers a margin, n = 250. This rests on one n = 10 trial and assumes linear growth; the first n = 1000 run is itself the check. Note the model handoff expects about 70 min (#236) and 1000 frames "sealed room, constant soot": measured here is about 1 min at this grid, and extinction frames are not identical (see counts above), so those two expectations do not hold on this deck at 8f7d29a2.
- Runner: `vbuild.py` (package dir) calls the unchanged `_build_vismap`, `_vis_bool_array`, `_vis_metre_array` with `_vismap_time_points` cut to the first N points; distinct-frame count is computed after the timed part. Sizing trial only; no full run.

## 5. Untimed G0 normal runs (serial, `--instrument detail`, `--vis-cache first` where vismap applies)

Run IDs in `results/raw/`: `g0v2b_W1_O_study_det_s1_rep1_20261014T124453`, `g0v2b_W2_nf_det_s1_rep1_20261014T124556`, `g0v2b_W3_O_study_det_s42_rep1_20261014T124620`, `g0v2b_W3b_cmm_O_study_det_s5150_rep1_20261014T124631`. (`g0v2b_dev_W3_...124009` is the development run that tested the new hooks.) Harness exit 0 for all four; run exits 2 / 0 / 2 / 0. Time per run (wall, indicative, host loaded, detail counters on): W1 61.3 s, W2 22.7 s, W3 9.7 s, W3b 1.4 s.

**`dt` = 0.01 s confirmed** from `simulation.delta_time()` in all four (`counters.json` `dt_s`).

Outcomes (identical to the earlier `g0v2` smokes for W1, W2, W3):

| Run | Outcome | Iterations / agent-steps |
|---|---|---|
| W1 gate s1 | time limit 400 s, 199/200 out, 1 inside, 0 unspawned | 40 000 / 3 259 925 |
| W2 nf s1 | complete, 200/200 at 313.53 s | 31 353 / 2 996 487 |
| W3 s42 | time limit 300 s, 99/150 out, 51 inside, 50 not spawned | 30 000 / 929 877 |
| W3b cmm s5150 (arm B, cap 120) | complete, 20/20 at 21.47 s | 2 147 / 32 228 |

Note W3b finishes in 21.5 s of the 120 s window.

**Activation table** (nonzero = active; counts per run; "-" = not applicable):

| Mechanism | W1 | W2 | W3 | W3b | Verdict |
|---|---|---|---|---|---|
| #236/#241 vismap build in a process | none (vis off) | - | 1 build 0.47 s; 301 x 3 x 53 x 121; `_get_visibility_array` 1 806 = 2 x 301 x 3 | 1 build 0.105 s; 121 x 2; calls 484 = 2 x 121 x 2 | active on W3, W3b only; sub-second |
| #236 distinct extinction frames among the vismap time points (outside timing, `results/vbuild_distinct_W3*.json`) | - | - | 300 of 301 | **1 of 121** | exact-dedupe case = W3b; W3 almost no dedupe |
| #241 split | - | - | `_build_vismap` 0.25 s (incl. lazy slice read 0.013), `vis_metre_array` 0.14 s | 0.079 s / 0.029 s | second pass over every (t, wp) costs about 36 % of the build on W3 |
| #242 `SliceFieldSampler.sample` calls | 2 268 k gas (3 quantities x 756 088) + 160 814 route (4 distinct xy) + 32 697 smoke-speed; distinct xy: 45 615 gas, 8 337 smoke speed | 0 | 47 324 gas (4 x 11 831, 9 865 distinct) + 909 route (3 distinct) + 9 352 smoke speed | about 1.6 k gas + 544 route + 333 smoke speed | active on W1, W3, W3b; route extinction goes through `read_cells`/`line_parts` as the model said; `sample` from the route only for off-grid polylines |
| #242 `read_cells` / `line_parts` | 725 445 calls, 22.7 M cells; line_parts 393 583 hits / 16 690 misses, 0 clears | 0 | 3 761 / 88 523; 1 571 / 402 | 1 605 / 81 425; 1 132 / 473 | active on W1, W3, W3b |
| #242 time-index | hits 532 338 / misses 153 196 | - | 2 232 / 1 642 | 798 / 302 | recorded |
| #243 `_generate_candidates` | `_assign_initial_exit` 200 calls (6 misses of 1 200 edges), `_reevaluate:2282` 32 497 (2 394 misses of 194 982), `:2340` 32 497 (0 misses of 194 982); 98.8 % served from the pass cache | 200 initial + 29 862 at `:2340` (1 878 misses of 179 172) | initial 150 calls, **no cache dict** (all 20 edges evaluated); reevaluate 9 352 at `:2282` (363 misses of 4 913), 9 352 at `:2340` (0 misses) | 20 + 313 calls, 39 misses of 470 edges | active; the pass cache is shared inside a pass, misses = 6 edges per pass on W1; flow-spawn initial choice without cache is visible only on W3 (150 calls, 20 evaluations) |
| #243 `rank_routes` / `evaluate_route` | 65 194 / 30 594 | 30 062 / 29 862 | 18 854 / 188 | 333 / 293 | |
| #429 `reached_stage` / `distance_to_polygon` | 2 791 592 checkpoint + 468 333 exit; distance 468 333 (14 % of agent-steps) | 2 664 752 + 331 735 (11 %) | 477 587 + 452 290 (49 %) | exit 32 228 (100 %) | active on all four; W2 is the steering workload |
| #739 flow spawn blocking | - | - | `flow_spawns_deferred_steps` 0; `_occupied` 150 calls (4 548 agents read), `_crowds_agents` 196 calls, 0 true | - | **inactive** on every selected workload, as predicted; `w4_flow_saturated` needed |
| Routing | 32 497 evaluations, 172 switches | 29 862, 0 switches | 9 352, 13 switches | 313, 20 switches | |
| W3 items from model §1.4b | | | build = 1; sign queries 14 123 (all in-grid), 364 positive; `_expand_visible` +34 sign nodes, `expand_on_arrival` +111; explore = wander = 0 (expected) | sign queries 666, 467 positive; +40 sign nodes | items 1-4 met |

FDS opens per process (setup sub-phase, per opener; parse seconds): W1 7 opens, 0.203 s (`_open_simulation` 3 / 0.093, `inspect_fds_quantities` 3 / 0.091, `fed.from_fds` 1 / 0.019); W2 0; W3 10 opens, 0.125 s (+ `_extinction_slice_index` 1, `FDSVisMap.read_fds_data` 1, `inspect_fds_quantities` 4); W3b 10 opens, 0.036 s. The `.smv` is parsed ten times where one would do; each costs 3-10 ms on these cases, 20 ms on a047.

**W4 pytest set**: `PYTHONHASHSEED=0 PYTHONDONTWRITEBYTECODE=1 $PY -m pytest -q -rs -p no:cacheprovider` on the v1 list plus the seven additions of model §1.5 (26 files, list in `/Users/chraibi/profiling-stage/tmp/w4_pytest_files.txt`): **857 passed, 1 skipped, 146 s**. The skip is `tests/test_fds_read_only.py:73` "needs an xdist worker", not FDS data. **FDS-dependent skips: zero.** No `.pickle` appeared under `assets/`, and the worktree stayed clean. Log: `/Users/chraibi/profiling-stage/tmp/w4_pytest.log`.

## Inputs/commit

pyFDS-Evac `8f7d29a2e056db46183e8cccabce338c398606a1`, lock `7f64a58db6d321441e320ad47ba960dc51d25c4a8dbaff8e8d95ba09fac25fc8`; model handoff `model_handoff_g0_v2.md` §1.4a, §2 and plan D13-D18.

## Files produced

In `/Users/chraibi/workspace/PedestrianDynamics/Fire/fds_visibility/visibility_workshop/studies/profiling/`: `vbuild.py`, `w4_flow_saturated.diff`, `scenarios/w4_flow_saturated/`, `preflight/hash_inputs_v2.py`, `preflight/fed_incap_co_2000ppm.json`, `preflight/world100_fire_4p5MW.json`, `results/vbuild_trial_n10.json`, `results/vbuild_distinct_W3.json`, `results/vbuild_distinct_W3b.json` (+ `.counters.json` each), `results/stage_verification_v2.json` (10/10), `results/raw/g0v2b_*`, `results/blocks/g0v2b_*`. Edited: `benchmark.py`, `analyse.py`, `instrument/perf_counters.py`, `scenarios/make_derived.py`, `verify_stage.py`, `preflight/input_hashes.json`, `g1_all.sh`, `launch_detached.sh`, `README.md`. Staged under `/Users/chraibi/profiling-stage/`: `fds/fed_incap_co_2000ppm`, `fds/world100_fire_4p5MW`, `decks/world100_evac_4exits`.

## Commands executed

```bash
rsync -a --exclude '*.pickle' "$SB/fed_incap_co_2000ppm/fds/" $ST/fds/fed_incap_co_2000ppm/      # and world100/fire_4p5MW, deck + geometry
$PY preflight/hash_inputs_v2.py $ST ; $PY verify_stage.py $ST results/stage_verification_v2.json   # 10/10
$PY preflight/preflight_fds.py $ST/fds/fed_incap_co_2000ppm --probe 60,300,600,1000 --json preflight/fed_incap_co_2000ppm.json
$PY preflight/preflight_fds.py $ST/fds/world100_fire_4p5MW --probe 30,120,240,330 --json preflight/world100_fire_4p5MW.json
cd $WT && $PY run.py --scenario .../w4_flow_saturated/config_flow_saturated.json --seed 42 --show-config            # exit 0
cd $WT && $PY run.py --scenario $ST/decks/world100_evac_4exits/deck_config_stream_east.json --seed 1 --fds-dir $ST/fds/world100_fire_4p5MW --show-config   # exit 1 (horizon)
cd $WT && PYTHONHASHSEED=0 $PY $STUDY/vbuild.py assets/fed_incap_co_2000ppm/config.json $ST/fds/fed_incap_co_2000ppm 10 results/vbuild_trial_n10.json
for c in W1 W2 W3 W3b_cmm; do $PY benchmark.py run --block g0v2b --case $c --shared --label g0v2b --warmup 0 --reps 1 --instrument detail --vis-cache first; done
cd $WT && PYTHONHASHSEED=0 PYTHONDONTWRITEBYTECODE=1 $PY -m pytest -q -rs -p no:cacheprovider <26 files>
```

## Observations (summary)

- #739 is inactive on W1-W4 as predicted; every other issue has an active, nonzero mechanism on a selected workload. Magnitudes are small on these workloads (vismap builds 0.1-0.5 s; the second-pass share in the build is 36 % of 0.4 s on W3).
- #242: the dominant sampler volume is gas-FED per agent (756 k calls per quantity on W1, 2 268 k in total, 45 615 distinct positions); the route smoke path already uses `read_cells`.
- #243: inside one pass the segment cache serves 98.8 % of edge evaluations on W1; the avoidable work is across passes (misses repeat 6 edges per 1 s pass) and the uncached flow-spawn initial choice (W3: 150 calls, no cache dict).
- #429: `distance_to_polygon` is called for 11-14 % of agent-steps on W1/W2, 49 % on W3, 100 % on W3b.
- Outcomes of all four normal runs match the earlier smokes; this is a repeat of one run each, not a determinism gate.

## Uncertainties

- Detail-group overhead, counters overhead and determinism are all unmeasured; no instrumented/uninstrumented equivalence was checked. Treat the detail counters as diagnostic.
- The `sample` caller key uses two frames; the quantity name comes from the slice object. Distinct-`(x, y)` sets are exact floats, so near-identical points count as different.
- `hits = edges - misses` assumes phase 1 of `_generate_candidates` visits each edge once (true in the current code); a change there would silently skew it.
- W3 has 300 of 301 distinct extinction frames, with one duplicate not investigated.
- The V-build n rests on a single n = 10 trial; the fixed/variable split is read from three stage timers, not fitted. The model handoff's 70 min and sealed-room claims for this deck are not reproduced; I did not check whether another slice height or grid setting would reproduce them.
- `w4_flow_saturated` deferral is untested by design.
- World100 horizon failure is a fact of the staged output (ends 250 s) against the deck's 330 s cap; whether a longer FDS output exists in sciebo was not searched (`world100/rerun_7a3617d`, `tau_9f55f6e` unexamined).
- `analyse.py` and `compare.py` were not run after the label changes; `results/summary.csv` untouched and stale (v0.2.0).
- The detail run IDs end in `_det`; the `g0v2b_dev_W3` run is a hook test and must stay out of any table.

## What perf-model must check

- Review `w4_flow_saturated.diff`, especially the added flow premovement (100 s) and the 200 s cap, before any run; the fixture is not run.
- Decide the V-build n (1000 provisional) and whether the 70 min / constant-extinction expectations for `fed_incap_co_2000ppm` are retired; check that the runner's truncation of `_vismap_time_points` is an acceptable controlled change.
- Decide W1r given the horizon failure (hold flag, 250 s cap, other FDS output, or drop).
- Update `scenarios.json` (target block, removed fdsreader cache keys, W3 relabel, expected activation counts above, new fixtures) from these numbers.
- Confirm that the activation counters satisfy your table (notably #242 population, #243 miss accounting, #739 inactive) and which of them need an equivalence/overhead check before use in G1.

## What perf-qa must check

- That harness diffs are only those listed (compare with `/Users/chraibi/profiling-stage/tmp/*.v2pre` and `scenarios_pre_v2/`), and that `cache_label` no longer carries pickle fields.
- Reproduce one normal run (W3 is the cheapest with vismap) and compare counters; check `hits = edges - misses` against the source.
- That the staged copies equal the sciebo sources (`hash_inputs_v2.py` compared before appending) and `stage_verification_v2.json` is 10/10.
- That `g0v2b_dev_*`, `g0v2_*` and the empty `g0v2_W3_..._122925` directory are excluded from any summary.
- That the pytest result (857 passed, 1 skipped, the skip not FDS-related) is acceptable evidence for "zero FDS-dependent skips".
- That no detail-counter run is quoted as a timing, and the unmeasured overhead is stated wherever the counters are used.

---

# §G0 v2c: amended fixture, W1r cap 250, V-build statistic (2026-10-14)

Untimed, `--shared`, host loaded (other Python jobs), all runs `not_a_measurement`; worktree `/Users/chraibi/profiling-stage/wt_8f7d29a2` at `8f7d29a2e056db46183e8cccabce338c398606a1`, unchanged. Nothing in pyFDS-EVAC touched.

## 1. `w4_flow_saturated`, amended and run

- `make_derived.py` (backup `/Users/chraibi/profiling-stage/tmp/make_derived.py.v2b`): the flow distribution keeps `use_premovement` false; only the standing distribution has the constant 100 s premovement. New config sha256 `982c50aca481a3ac8736d6b4029821e19b4adf0aefba5c1640d4eb15739916dc` (superseded: `e3f3540b...`), recorded in `scenarios.json` (`sha256_as_built_by_engineer`, plus a note). `w4_flow_saturated.diff` regenerated. The other derived configs are unchanged (diff against the earlier backup).
- Run: `benchmark.py run --block g0v2d --case W4_flow_saturated --shared --label g0v2d --warmup 0 --reps 1 --instrument detail` (`results/raw/g0v2d_W4_flow_saturated_fixture_det_s42_rep1_20261014T125802`), repeated once after adding one counter (`g0v2d2_...130102`). Both runs: run exit **2**, harness exit 0, identical trajectory hash (`ee23c36b...`) and identical counts.
- Outcome: "Simulation incomplete: flow windows closed after 179.15 s (286/286 evacuated, 0 remaining, 164 not spawned)"; `end_reason` `flows_closed`; 136 of 300 flow agents entered (the 150 standing agents were placed at t = 0), 17 915 iterations, 2 592 057 agent-steps, wall 78 s (diagnostic, loaded host).
- **`flow_spawns_deferred` = 5 602 steps (acceptance ≥ 1 000: met)**, between t = 2.60 s and t = 60.00 s (the library's log line says so; **not spawned = 164**).
- Work counted inside the unchanged run: `_occupied` 5 738 calls (1 118 581 agent positions read, about 195 per call); `_crowds_agents` 1 022 315 calls with **0 true**; `add_agent` position refusals 1 022 179 (new counter `add_agent_position_refusals`, wraps `simulation_init._refuses_position`). So the retry cost is about 182 candidate positions per deferred step, every one passing `_crowds_agents` and being refused by JuPedSim's own `add_agent` with a `RuntimeError` that the code catches and discards. That is the work #739 describes, and it is exception-driven, not the Python crowding check.
- Not checked: whether a W3-like flow ever hits that path (W3: `_crowds_agents` 196 calls, 0 true, 0 deferrals).

## 2. `w1r_cap250`

- `scenarios/w1r_cap250/config_stream_east_cap250.json`, built by `make_derived.py` from the staged `$ST/decks/world100_evac_4exits/deck_config_stream_east.json` with only `max_simulation_time` 330 -> 250 (checked by loading both JSONs and comparing after setting the key). sha256 `672cb1a007760f0a92942269f7ea34eb792f384fc20a33927c70ffaf07f010da`. `geometry.wkt` byte-identical to the deck's `deck_geometry.wkt` (`cmp`; sha256 `e99a07d6...`, as in `scenarios.json`). Base deck sha256 `fc50f2b8...` matches `scenarios.json`. Hashes recorded in `scenarios.json` (`W1r.derived_config.sha256`, `geometry_sha256_built`). `scenarios.json` keeps its layout (diff against `/Users/chraibi/profiling-stage/tmp/scenarios_pre_v2d.json` is the three edits only).
- `benchmark.py`: case `W1r` (`--fds-dir fds/world100_fire_4p5MW`, W1 output set, seed 1). Staged FDS check still 10/10.
- Preflight (`scenarios.json` `preflight_required`): `--show-config` **exit 0**, Errors none, Setup warnings none (output kept in `/Users/chraibi/profiling-stage/tmp/w1r_cap250_showcfg.txt`); also exit 0 with `--require-fds-coverage`; "FDS output ends at 250.0 s, interval 2.0 s", cap 250.0 s; coverage in the run's manifest: `walkable_area_m2` 3 530.44, **`walkable_outside_m2` 0.0**, no areas, signs or edges outside, `fds_outside` 0 rows; spawned count **120** of 120; no `FdsHorizonError`.
- Run: `g0v2d_W1r_O_study_det_s1_rep1_20261014T125941`, harness exit 0, run exit **2**. Outcome: "Simulation incomplete: time limit reached after 250.00 s (117/120 evacuated, 3 remaining)"; `end_reason` `time_limit`; 0 not spawned; dt 0.01 s; 25 000 iterations; **agent_steps 252 617**; wall 20.6 s, pre-run 0.84 s (diagnostic, loaded host); route history 7 rows, 9 856 route-cost samples; 7 switches.
- **`_generate_candidates` by caller** (368 edges per call: 44 160 / 120):

| Caller (scenario.py line) | Calls | Edges | Segment misses | Segment hits |
|---|---|---|---|---|
| `_assign_initial_exit:1277` (flow spawn initial choice; no cache dict) | **120** | 44 160 | 44 160 | 0 |
| `_reevaluate:2282` | 2 464 | 906 752 | 91 632 | 815 120 (89.9 %) |
| `_reevaluate:2340` | 2 464 | 906 752 | 0 | 906 752 |

  Flow-spawn count 120 as expected; every initial choice evaluates all 368 edges (100 % misses).
- `evaluate_segment` calls: 135 792 from `_generate_candidates:2568` (= 44 160 + 91 632, equals the misses above) and 27 181 from `_measure_route:1819`; `rank_routes` 5 048, `evaluate_route` 2 464 (it equals the reroute evaluations).
- Sampling volume: `read_cells` 576 285 calls, 11.0 M cells; `line_parts` 387 337 hits / 23 228 misses; time index 520 337 hits / 82 280 misses; gas FED 3 x 39 015 distinct points; route extinction `sample` 44 distinct points; smoke speed 2 521. `reached_stage` 174 954 checkpoint + 77 663 exit (`distance_to_polygon` 77 663 = 31 % of agent-steps).
- FDS opens: 7, 0.137 s (`_open_simulation` 3, `inspect_fds_quantities` 3, `fed.from_fds` 1).
- **#666 foresight warning count = 1**: "Route foresight reaches beyond the earliest last FDS frame of the routing fields (t=250.2 s > 250.0 s): smoke and FED ahead are read from that frame for the rest of the run." (stderr of the run; reported, not relaxed).
- Compared with W1 (same counters): evaluate_segment calls from `_generate_candidates` are 135 792 in 120 agents x 250 s, against 2 400 for 200 agents x 400 s; the dense graph and the uncached flow spawn make that gap.

## 3. `vbuild.py`: consecutive-frame statistic

Added after the distinct-frame count, outside the timed section: `consecutive_frame_change_K_per_m` with `pairs`, `pairs_identical`, and max / median / min / p90 of max |K_t - K_(t-1)| over the grid for each pair. Not run on the deck. The only run was a syntax-and-logic check on the cheap W3b build (0.1 s, scratch output `/Users/chraibi/profiling-stage/tmp/vbuild_stat_check_W3b.json`): 120 pairs, all identical, max difference 0.0 (consistent with 1 distinct frame). No V-build rerun on `fed_incap_co_2000ppm`.

## 4. `analyse.py` / `compare.py`: what breaks or lags (not run, not fixed)

- `analyse.py`: runs unchanged on the new manifests (they keep the same keys; the dropped `fdsreader_cache` column is simply absent). It rewrites `results/summary.csv` from every `results/raw/*` manifest, so v0.2.0 (`3ef4ea75`) rows, `dev*`, `g0v2*`, `g0v2b*`, `g0v2d*` and the empty/refused dir mix in one file (the groups file filters on `measured` and groups by `commit`, so groups stay separate). The `g0v2_W3_..._122925` directory has no `manifest.json` and is skipped silently. `fds_opens_by_opener` (a dict) is not exported to `summary.csv`.
- `compare.py`: `APP_FIELDS` omits `fds_outside` (item 9 of the v2 contract); `log_facts` looks for "Route switches: N", which the CLI no longer prints (both sides read None, so it never discriminates); items 10 (summary line text and the "Looks from a node point" line) and 11 (npz `format` 6) are not compared as named; there are no CSV column checks for `exit_in_map`. Equality of the full files (items 3-6) still works because they are byte hashes.
- `g1_all.sh`: no `G1first` block now; `launch_detached.sh` / README no longer mention `--fds-cache`. Anything old that passes `--fds-cache` fails in argparse.
- `scenarios.json` `W4.w4_flow_saturated.command` has no counters; the `benchmark.py` case runs it with `--instrument detail`.

## Inputs/commit

pyFDS-Evac `8f7d29a2e056db46183e8cccabce338c398606a1`, lock `7f64a58d...`; `model_handoff_g0_v2.md` v2c appendix (A1, A3, A5); staged `fds/world100_fire_4p5MW` (aggregate `1a3c577c8e5c...`).

## Files produced

In the package dir: `scenarios/w1r_cap250/{config_stream_east_cap250.json,geometry.wkt}`, regenerated `scenarios/w4_flow_saturated/config_flow_saturated.json` and `w4_flow_saturated.diff`, `results/raw/g0v2d_W4_flow_saturated_*`, `results/raw/g0v2d2_W4_flow_saturated_*`, `results/raw/g0v2d_W1r_*`. Edited: `scenarios/make_derived.py`, `benchmark.py` (case `W1r`), `instrument/perf_counters.py` (`add_agent_position_refusals`), `vbuild.py`, `scenarios.json` (three hash entries). Backups in `/Users/chraibi/profiling-stage/tmp/`: `make_derived.py.v2b`, `scenarios_pre_v2d.json`.

## Commands executed

```bash
$PY scenarios/make_derived.py                               # w4_flow_saturated, w1r_cap250; other derived files unchanged
cmp scenarios/w1r_cap250/geometry.wkt $ST/decks/world100_evac_4exits/deck_geometry.wkt
$PY benchmark.py run --block g0v2d  --case W4_flow_saturated --shared --label g0v2d --warmup 0 --reps 1 --instrument detail
$PY benchmark.py run --block g0v2d2 --case W4_flow_saturated --shared --label g0v2d --warmup 0 --reps 1 --instrument detail   # after the refusals counter
cd $WT && $PY run.py --scenario .../w1r_cap250/config_stream_east_cap250.json --seed 1 --fds-dir $ST/fds/world100_fire_4p5MW --show-config [--require-fds-coverage]
$PY benchmark.py run --block g0v2d --case W1r --shared --label g0v2d --warmup 0 --reps 1 --instrument detail --timeout 1500
cd $WT && $PY $STUDY/vbuild.py <cmm cap120 config> $ST/fds/cmm_clear_air 100000 $ST/tmp/vbuild_stat_check_W3b.json      # statistic check only
```

## Observations

- #739 mechanism is active and large on the fixture: 5 602 deferred steps, about 1.02 M refused `add_agent` calls, 78 s wall for a 179 s window of 286 agents. The retry work is JuPedSim refusals, not `_crowds_agents` hits (0 of 1.02 M).
- The fixture repeats exactly (same trajectory hash and counters on two runs), though the second run had one more counter installed.
- W1r delivers the #243 population the issue describes: 120 uncached flow-spawn choices of 368 edges each, 90 % of reroute edge evaluations served from the pass cache, 135 792 segment evaluations, 576 k `read_cells` calls.
- The cap-250 deck has one foresight-cap warning, as the model predicted.

## Uncertainties

- Single runs on a loaded host; counts are deterministic quantities, seconds are not.
- The fixture's second run carried the extra counter; I did not run a third without it. The first run's trajectory hash equals the second's, which supports that the counter is observational for this case.
- `hits = edges - misses` assumption of v2b still holds (W1r: `_generate_candidates:2568` calls equal the summed misses).
- Whether the 164 not-spawned count is stable across seeds or the 100 s standing time was not varied.
- W1r is time-limited with 3 agents inside and uses a different movement model; no timing or outcome claim vs W1.
- Not examined: the `analyse.py` / `compare.py` items above beyond static reading.

## What perf-model must check

- That the 5 602 deferred steps, 164 not spawned and 1.02 M refusals match the fixture's intent, and whether the counter should replace `_crowds_agents` as the proof counter for #739 in `scenarios.json` (`_crowds_agents` never returned true).
- W1r numbers against `expected_activation` (flow-spawn calls 120 x 368 edges, one #666 warning) and the label.
- Whether `compare.py` needs the item 9/10/11 additions before the determinism gate; define what to add (I have not changed it).
- The consecutive-frame statistic's definition (max over the grid per pair) is the one you want.

## What perf-qa must check

- That `scenarios/w4_flow_saturated/config_flow_saturated.json` and `scenarios/w1r_cap250/*` hash as recorded, `geometry.wkt` equals the deck's, and the base deck equals the sciebo copy.
- That the `g0v2d*` runs, like earlier `g0v2*`, are excluded from summaries and never quoted as timings.
- That `benchmark.py` diffs since v2b are limited to the `W1r` case, `perf_counters.py` to one hook, `vbuild.py` to the statistic, `make_derived.py` to the premovement amendment and the `w1r` builder.
- That nobody quotes V-build against #236/#241 without the revision caveat; no deck rerun was done in this round.

---

# §G0 v2d: QA entry conditions IV1, IV2, IV3, IV5, IV6 and the V-build runner (2026-10-14)

Untimed, `--shared`, host loaded; every run below is `not_a_measurement`. Worktree `/Users/chraibi/profiling-stage/wt_8f7d29a2` at `8f7d29a2e056db46183e8cccabce338c398606a1`, clean before and after. Nothing in pyFDS-EVAC touched. Backups of the files edited in this round: `/Users/chraibi/profiling-stage/tmp/*.v2d_pre` (`perf_counters.py`, `benchmark.py`, `compare.py`, `g1_all.sh`, `README.md`, `vbuild.py`).

| Item | Status |
|---|---|
| IV1 caller split for #242 | **closed** (measured, below) |
| IV2 `flows_closed` outcome and termination | **closed** (fixture re-run confirms) |
| IV3 README labels, early smoke manifests | **closed** for README lines 123-125, the "12 items" line and the two manifests; **open**: (b) `perf_counters.py` docstring/`kind` fields, (c) `plan.md` banner (coordinator), (e) stage `.pickle` leftovers |
| IV4 stale labels and pins | **open** (not in this round: `CASES` W3/W3b labels, `preflight/input_hashes.json` commit, `hash_inputs.py` `COMMIT`) |
| IV5 `g1_all.sh` | **closed** as edited; the driver itself has not been run end to end (syntax check, gate snippet check only) |
| IV6 `compare.py` | **closed** for items 9, 10, 11; **open** by design: item 13 needs `--capture-result` |
| D24 V-build runner | **closed** (built and tested on a cheap deck; V-build on the deck not run) |

## IV1: the #242 sampler split, re-measured

`perf_counters.py`: the `SliceFieldSampler.sample` key is now the caller chain of up to five frames (reaching above `fed.sample_inputs`), a per-quantity `sampler_sample_by_side[<quantity>|route|agent|other]` counter, `polyline_stats_calls`, `polyline_stats_samples` and a distinct-point set `detail.sampler_distinct_xy["polyline_stats"]`. "route" = chain contains `sample_fed_rate`, `evaluate_segment`, `_polyline_stats` or `route_graph.`; "agent" = per-agent FED update or `smoke_speed.sample`. Side rule is mine and visible in the code.

Run: `g0v2f_W1_O_study_det_s1_rep1_20261014T132114` (W1 gate s1, detail). Its agent-steps, iterations, reroute evaluations, switches, `read_cells` and `distance_to_polygon` counts are identical to `g0v2b_W1_*`, and the outcome is the same (199/200 at 400 s).

| `SliceFieldSampler.sample` calls on W1 | Per-agent update | Route cost path | Route share |
|---|---|---|---|
| CO | 32 697 | 723 391 (`fed.sample_rate` <- `scenario.sample_fed_rate`) | 95.7 % |
| CO2 | 32 697 | 723 391 | 95.7 % |
| O2 | 32 697 | 723 391 | 95.7 % |
| Extinction | 32 697 (`smoke_speed.sample`) | 160 814 (`_polyline_stats`: 81 059 via `_first_hops`, 78 375 via `_measure_route`, 1 380 via `evaluate_segment`) | 83.1 % |
| All four | 130 788 | 2 330 987 | **94.7 %** of 2 461 775 |

QA's "about 96 %" is confirmed for the gas-FED path (95.7 %); over all `sample` calls it is 94.7 %. The earlier handoff sentence ("dominant volume is gas-FED per agent") was wrong: the per-agent FED update is 4 % of the gas calls.

Distinct `(x, y)` (exact floats): per-agent FED 8 337 per quantity (32 697 calls, 3.9 per point); route FED 37 473 per quantity (723 391 calls, 19.3 per point); per-agent smoke speed 8 337; `_polyline_stats` samples 160 814 on **4** distinct points; `_polyline_stats` was called 483 691 times, so only a third of its calls reach `sample` (the rest go through `read_cells`). The 4 points are off-grid polyline vertices, which is the only way the route path reaches `sample` for extinction.

Caveats: the first frames of the extinction chains include my own `perf_counters.polyline_stats` wrapper frame; the chain stops at five frames, so the route chains end at `scenario.sample_fed_rate` or `_first_hops`, not at the reroute pass. No W3 re-run was needed for the key change (W3's nonzero counters came from the same code path); the QA suggestion to re-run W3 and compare outputs was not done in this round.

## IV2: `flows_closed`

`benchmark.py`: `SUMMARY_RE` now accepts "incomplete: time limit reached" and "incomplete: flow windows closed"; `outcome` gets `end_reason` (`time_limit` or `flows_closed`); `termination` is `flows_closed` for rc 2 with that ending. Re-run: `g0v2f_W4_flow_saturated_fixture_det_s42_rep1_20261014T132219`: exit 2, `termination` `flows_closed`, `outcome` = {summary_line "Simulation incomplete: flow windows closed after 179.15 s (286/286 evacuated, 0 remaining, 164 not spawned)", status incomplete, end_reason flows_closed, sim_time_s 179.15, evacuated 286, total 286, remaining 0, not_spawned 164}. Time-limit runs also gain `end_reason: time_limit` in `outcome`. Earlier `g0v2d*` fixture manifests keep their null outcome (not rewritten); `compare.py` item 10 is meaningful for new fixture runs only.

## IV3: labels

- README "Cache-state labels": the three fdsreader bullets replaced by the no-cache statement and the `fds_opens_*` description; "checks 12 items" now names the 13-item v2 contract (items 1-12 plus 12b in the script).
- `results/raw/g0v2_W1_..._20261014T122834` and `g0v2_W3_..._20261014T122943`: only the keys `status_label: "SUPERSEDED_LABEL"` and `status_note` added (the JSON round-trip of the original was byte-identical before the edit, checked). The empty `g0v2_W3_..._122925` directory has no manifest and was left as is.

## IV5: `g1_all.sh`

Syntax-checked with `bash -n`; not executed. Status file is now `results/blocks/g1v2_status.tsv`.
- `gate <block> <case>` right after the two `G1det` blocks (W1 plain x2; W3 plain x2 with `--capture-result`): `compare.py --block` against the first run, plus `--negative-control`; both must pass or the driver logs `GATE ... FAIL` and `exit 1`, so no paired block can run after a failed gate. Missing runs also fail. The old end-of-script G1det comparison loop is removed.
- New blocks: `G1w1r` (W1r, `--timeout 300`), `G1flow` (fixture, 1 warm-up + 3 reps, `--timeout 120`), `vblock G1vbuild --n 1001` (V-build runner), `G1ovhD` (W1, `--instrument none,counters,detail --order abba`), and the 26-file pytest list in the W4 section; the post-run comparison adds `G1ovhD`. Limits follow D24: W1r 300 s, fixture 120 s, V-build 300/900 s and 8 GB.
- `.pickle` leftovers in the stage dir: not touched.
- Untested: `vblock` and `gate` inside the driver; the `abba` ordering with three instruments (it reverses the combo list on odd repetitions).

## `compare.py` (IV6)

`APP_FIELDS` gains `fds_outside` and `git_dirty`; the "Route switches" regex is gone; `log_facts` reads `stdout.log` and `stderr.log` and compares `Route cost samples` and the "Looks from a node point before a patrol: n, given up: m" line (both None where absent, as in every run so far); new item `11b_vismap_format_is_6` (npz meta `format` must be 6 in every run that has an npz). Check: two plain W3b runs, `g0v2e1_W3b_cmm_O_study_s5150_rep1_20261014T132106` and `g0v2e2_...132108` (`--vis-cache first`, so both carry `vis.npz`): verdict **equivalent**, items 1-4, 8-11, 11b equal, gap "cognitive-map state not compared" (plain runs); output `results/equivalence/g0v2e_W3b_plain_vs_plain.json`. Negative control on the first run: **PASS** (identity equivalent; one byte of `exit.csv` flagged in `3_exit.csv`; one ulp flagged in `1_trajectory_repr_v1`), `results/equivalence/g0v2e_negative_control_W3b.json`. The QA pair itself lived in QA's directory; I used my own. Not tested: a deliberately wrong npz format, the Looks line with a run that prints it.

## D24: `vbuild_bench.py`

- `vbuild.py` gets `--plain` (no hooks installed: the three top-level timings are plain) and `--no-stats` (skip the after-timing frame statistics, so plain repetitions have a clean peak RSS). Missing statistics are `null`, not zero.
- `vbuild_bench.py --block B --exclusive|--shared [--n 1001] [--reps 5] [--warmup 1] [--profiler none|cprofile] [--dry-run]`: slot check (refuses `--exclusive` if `ok` is false), frozen-worktree check, host monitor via `benchmark.monitor`, `/usr/bin/time -l`, one manifest per run with the benchmark schema (`case` `VBUILD`, variant `n<N>_plain|det`, venv fingerprint, deck sha256, limits, `vbuild_result`, `metrics.build_total_s` and stage seconds, `host_during`, `worktree_after`). Order: 1 warm-up + N plain reps, then 1 instrumented diagnostic run with counters and statistics; the instrumented run is always `not_a_measurement`, plain reps are `measured` only under `--exclusive`. Limits: 300 s plain, 900 s profiled, 8 GB tree RSS (kill, record `timeout` or `rss_limit`, never drop).
- `analyse.py` (run in a scratch copy with `results/raw` symlinked and `-I`) reads the new manifests without error: 30 rows, 24 groups; VBUILD rows present.
- Test on the cheap clear-air deck at n = 10 (not the V-build deck): `g0v2g_ok_VBUILD_n10_plain_*` (exit 0, plain method label, statistics null) and `..._det_*` (exit 0, 1 distinct frame). A first attempt `g0v2g_test_*` failed with exit 1 because I passed a relative deck path (cwd is the worktree); both run directories are kept as incomplete records. `--dry-run` for the default deck shows the n = 1001 command and the limits. No V-build on `fed_incap_co_2000ppm` was run.

## Inputs/commit

pyFDS-Evac `8f7d29a2e056db46183e8cccabce338c398606a1`, lock `7f64a58d...`; `review.md` "## G0 v2" (IV1-IV9) and `plan.md` D21-D24.

## Files produced

Package dir `/Users/chraibi/workspace/PedestrianDynamics/Fire/fds_visibility/visibility_workshop/studies/profiling/`: `vbuild_bench.py`; `results/raw/g0v2f_*`, `g0v2e1_*`, `g0v2e2_*`, `g0v2g_test_*`, `g0v2g_ok_*`; `results/equivalence/g0v2e_W3b_plain_vs_plain.json`, `g0v2e_negative_control_W3b.json`. Edited: `instrument/perf_counters.py`, `benchmark.py`, `compare.py`, `g1_all.sh`, `README.md`, `vbuild.py`; two manifests got the `status_label` key.

## Commands executed

```bash
$PY benchmark.py run --block g0v2f --case W1 --shared --label g0v2f --warmup 0 --reps 1 --instrument detail
$PY benchmark.py run --block g0v2f --case W4_flow_saturated --shared --label g0v2f --warmup 0 --reps 1 --instrument detail
$PY benchmark.py run --block g0v2e1 --case W3b_cmm --shared --label g0v2e --warmup 0 --reps 1 --vis-cache first   # and g0v2e2
$PY compare.py g0v2e1_... g0v2e2_... --out results/equivalence/g0v2e_W3b_plain_vs_plain.json
$PY compare.py --negative-control g0v2e1_... --out results/equivalence/g0v2e_negative_control_W3b.json
$PY vbuild_bench.py --block g0v2g_ok --shared --n 10 --reps 1 --warmup 0 --deck $PWD/scenarios/w4_cmm_cap120/config_cap120.json --fds $ST/fds/cmm_clear_air
bash -n g1_all.sh ; python3 -I analyse.py --include-dev   # in a scratch copy
```

## Observations

- The route cost path, not the per-agent updates, dominates `SliceFieldSampler.sample` volume on W1 (94.7 % of calls, 95.7 % of gas-FED calls), and it repeats positions (19 calls per distinct point); the 160 814 extinction samples from `_polyline_stats` use 4 points.
- `compare.py` still reports equivalence for a plain pair and detects both perturbations after the changes.
- The fixture manifest now carries the right termination and outcome.

## Uncertainties

- The route/agent side rule is a substring test on the call chain; chains are cut at five frames; the wrapper frame `perf_counters.polyline_stats` is in some keys. The exact-float distinct sets count near-identical positions as different.
- The detail counters' own overhead is still unmeasured (block `G1ovhD` exists, not run).
- `g1_all.sh` is unexecuted; a typo in `vblock`, `gate` or the `abba` ordering would show only at run time. The gate depends on `compare.py --block` globbing `G1det_<case>_*`.
- `compare.py` item 10's "Looks" line and item 11b were exercised only on runs that do not print / have format 6.
- The V-build runner's plain-vs-instrumented split is tested on n = 10 on a loaded host; no timing is meaningful.

## What perf-model must check

- The `scenarios.json` W1 `expected_activation_g0v2b` and the #242 row: replace the "gas-FED per agent dominant" statement with the split above (route 94.7 %, route-side FED 95.7 %), and decide whether "calls per distinct point" (19.3 route vs 3.9 agent) is the static-share statistic you want for #242.
- That `end_reason` in `outcome` and `termination: flows_closed` match the contract's item 10 wording.
- Whether the V-build plain/instrumented split and limits in `vbuild_bench.py` match D24 and the `V_build` entry in `scenarios.json` (n = 1001).

## What perf-qa must check

- Read-only re-check of IV1, IV2, IV3, IV5, IV6 and the V-build runner against the files above, in particular: the split table from `g0v2f_W1_*/counters.json`; the fixture manifest `termination`; the `bash -n` result and the gate logic in `g1_all.sh` (not executed); `compare.py` on your own pair and negative control.
- That the open items stay open in your list: IV3(b),(c),(e) and IV4.
- That `g0v2e*`, `g0v2f*`, `g0v2g*` runs are not in any summary as measurements.

---

# §G0 v2e: IV3 remainder and IV4 (2026-10-14)

Untimed, no runs. Worktree `/Users/chraibi/profiling-stage/wt_8f7d29a2` at `8f7d29a2e056db46183e8cccabce338c398606a1`, clean (`git status --porcelain --untracked-files=all` empty). pyFDS-EVAC and sciebo untouched for writing (`hash_inputs.py` read the sciebo FDS directories, as at staging). Backups: `/Users/chraibi/profiling-stage/tmp/input_hashes.v2d_pre.json`, `hash_inputs.py.v2d_pre`.

## Status per entry condition (engineer's side)

| IV | Subject | Status |
|---|---|---|
| IV1 | #242 caller split | closed (§G0 v2d: route side 94.7 % of `sample` calls, 95.7 % of gas-FED calls) |
| IV2 | `flows_closed` outcome/termination | closed (§G0 v2d; fixture re-run) |
| IV3 | D13 labels | closed on my side: README and the two early manifests (v2d), `perf_counters.py` docstring and the three `.pickle` leftovers (below); the `plan.md` banner is the coordinator's |
| IV4 | stale labels and pins | closed (below) |
| IV5 | `g1_all.sh` blocks and determinism gate | closed as edited; driver not executed end to end |
| IV6 | `compare.py` gaps | closed for items 9-11; item 13 remains capture-only by design |
| IV7 | W1r label and foresight share | perf-model/coordinator (D22); nothing outstanding on the harness side: `W1r` case label says "never pooled with W1" and the #666 warning count is recorded; the 8.2 % held-foresight share is QA's figure, not computed by the harness |
| IV8 | #241/#236 wording | perf-model/coordinator (D23); harness side: `vbuild.py` produces the consecutive-frame statistic (run on W3b only, not on the deck) |
| IV9 | v2 limits | coordinator (D24); implemented as `--timeout 300` (W1r), `--timeout 120` (fixture) in `g1_all.sh` and 300 s / 900 s / 8 GB in `vbuild_bench.py`; not exercised end to end |

## IV3 remainder

- `instrument/perf_counters.py` docstring: the fdsreader bullet now says every open is a full `.smv` parse (adapter #716/#720, no cache state, plan.md D13) and that the event fields `kind` and `pickle_present_at_open` are kept for old manifests only. Code unchanged; syntax-checked.
- Deleted the three v1 `.pickle` leftovers, each a path under `/Users/chraibi/profiling-stage/fds/` (`a047_pvc_h40/a047_pvc_h40.pickle` 474 295 B, `t_junction_fire_2MW_PVC/t_junction.pickle` 311 596 B, `cmm_clear_air/cognitive_map_memory.pickle` 102 088 B); `find ... -name '*.pickle'` now finds none. `verify_stage.py` re-run: **10/10 OK, exit 0, aggregates identical** to the earlier output (`441bc2c1676d`, `d84ee4ee1210`, `2e7466a24e27`, `09c76e3d4330`, `1a3c577c8e5c`, `44e6f679a565`, `d22773401cd4`, `1f5e28aebf32`, `e193c9fa4478`, `64d4d5fa49f9`), since pickles were excluded from the hashes.

## IV4

- `benchmark.py` `CASES` labels: W3 "sign legibility in smoke under no_known_exit=default_route; no exploration; time-limited 300 s"; W3b_cmm "second visibility case, 120 s, exact-dedupe case for #236, clear-air FDS". Syntax-checked; new manifests carry them (older ones keep the old text, not rewritten).
- `preflight/hash_inputs.py`: `REPO` is now the pyFDS-EVAC checkout and `COMMIT` `8f7d29a2e056db46183e8cccabce338c398606a1`. Regenerated to a scratch file, diffed against the old `input_hashes.json`, then written:
  - `commit` 3ef4ea75 -> 8f7d29a2.
  - `repo_files`: exactly the four expected entries changed (`run.py`, `uv.lock`, `pyproject.toml`, `scripts/ab_trajectories.py`); the other **20** (configs, geometries, `.fds`, `run_p1.sh`, `make_configs.py`) are identical; the key sets are equal. All 24 now equal the sha256 of the files in the frozen worktree (checked).
  - `repo_dirs` (iso21, iso22 a-d): identical (5 of 5). `sciebo_files` v1 entries: identical.
  - `fds_dirs` v1 entries (a047, t_junction, cmm): file hashes and aggregates identical; only `excluded_mutable_cache` went from one pickle each to empty, because the sciebo pickles no longer exist (D13; not removed by us).
  - The v2 entries (`fed_incap_co_2000ppm/fds`, `world100/fire_4p5MW`, the two world100 deck files) are not produced by `hash_inputs.py`; I carried them over verbatim from the old file (`hash_inputs_v2.py` remains their source). `verify_stage.py` against the merged file: 10/10.

## Inputs/commit

pyFDS-Evac `8f7d29a2e056db46183e8cccabce338c398606a1`, lock `7f64a58d...`; `review.md` IV3/IV4; coordinator message of this round.

## Files produced

Package dir `/Users/chraibi/workspace/PedestrianDynamics/Fire/fds_visibility/visibility_workshop/studies/profiling/`: edited `instrument/perf_counters.py` (docstring), `benchmark.py` (two labels), `preflight/hash_inputs.py` (`REPO`, `COMMIT`), `preflight/input_hashes.json` (regenerated plus v2 entries), `results/stage_verification_v2.json` (re-written by the re-run, 10/10). Scratch: `/Users/chraibi/profiling-stage/tmp/input_hashes.new.json`.

## Commands executed

```bash
rm -- $ST/fds/{a047_pvc_h40/a047_pvc_h40,t_junction_fire_2MW_PVC/t_junction,cmm_clear_air/cognitive_map_memory}.pickle
$PY verify_stage.py $ST results/stage_verification_v2.json          # 10/10, before and after the merge
$PY preflight/hash_inputs.py $ST/tmp/input_hashes.new.json          # after REPO/COMMIT edit
python3 (diff old vs new, merge v2 entries into preflight/input_hashes.json, sha256 of the 24 repo_files against the worktree)
```

## Observations

The staged data is unchanged by the pickle removal. Only the four lock/entry-point files differ between v0.2.0 and the frozen commit; every input config, geometry and iso FDS file is byte-identical.

## Uncertainties

- `hash_inputs.py` no longer reproduces the v2 entries on its own; a rerun without the merge would drop them.
- Old manifests keep the old W3/W3b labels and `cache_label` text; `analyse.py` groups by `case`, `variant`, `commit`, so labels do not mix groups.
- IV5's driver and the V-build runner at n = 1001 remain unexecuted.

## What perf-model must check

IV7, IV8 wording in `scenarios.json`, and that the W3/W3b labels in `benchmark.py` match your D14 text.

## What perf-qa must check

Read-only: no `.pickle` under `$ST/fds`; `verify_stage.py` 10/10; `input_hashes.json` `commit` and the 24 `repo_files` equal the frozen worktree; the 20-entry and staged-data diffs above; the docstring wording; and that IV5/IV9 are exercised only when the exclusive slot exists.

---

# §G0 v2f: D25-D27 pre-slot items (2026-10-14)

Untimed; no simulation run in this round (horizon_check only reads existing run outputs and opens the staged FDS directories read-only). Worktree `/Users/chraibi/profiling-stage/wt_8f7d29a2` at `8f7d29a2e056db46183e8cccabce338c398606a1`, clean. `g1_all.sh` was not started.

| Item | Status |
|---|---|
| D25 fixture repetitions | closed: `G1flow` is `--warmup 1 --reps 5 --timeout 120` |
| D26 `horizon_check.py` | closed: script, calls in `g1_all.sh`, `analyse.py` columns, reproduction test below; W3b has no route-cost output, so its bound is null |
| `__pycache__` | removed from the package and its subdirectories (count 0 after the last Python syntax check); any later import of `benchmark.py` recreates it, so the README "Before" list removes it again |
| `bash -n g1_all.sh` | OK, run after the final edit |
| README "Running G1" | written (section 7): checks before, start, watch, stop, harness fault vs result per D27 |

## `horizon_check.py`

`PY horizon_check.py RUN_DIR_OR_ID ...` writes `horizon.json` into `results/raw/<id>/`. Per run: `bound = time_s + path_length_m / base_speed` for each row of the run's `rc.csv` (located through the manifest's `outputs_dir`; base speed W1 family 1.0, W3 / W3b_cmm / W1r 1.3, hard-coded from `scenarios.json` `horizon_criterion`), `guard_s = last FDS frame + largest output interval` taken from the code's own `fds_sampling.fds_output_horizon` on the run's `--fds-dir` (so it is the rule the run applied, not a copy of it), `max_bound_s`, `rows`, `rows_past_guard`, `rows_past_last_frame` (the held-foresight rows), `held_share`, `warning_count` (lines "Route foresight reaches beyond" in `stderr.log`), `passes` (`max_bound < guard` and no warning). Missing inputs give null, never zero (W2: no FDS; W3b_cmm: no `rc.csv`).

Reproduction on existing untimed runs:

| Run | max bound | guard | rows past guard / past last frame / rows | held share | warnings |
|---|---|---|---|---|---|
| `g0v2b_W1_O_study_det_s1_rep1_20261014T124453` | 430.62 s | 481.12 s | 0 / 0 / 64 994 | 0.0 | 0 |
| `g0v2b_W3_O_study_det_s42_rep1_20261014T124620` | 56.85 s | 301.15 s | 0 / 0 / 277 | 0.0 | 0 |
| `g0v2d_W1r_O_study_det_s1_rep1_20261014T125941` | 288.43 s | 252.03 s | 739 / **812** / **9 856** | 8.24 % | **1** |
| `g0v2b_W3b_cmm_O_study_det_s5150_rep1_20261014T124631` | null | 122.07 s | null | null | 0 |

These match the required values (W1 430.6 vs 481.1, W3 56.8 vs 301.2, W1r 288.4 vs 252 with 812 / 9 856 and 1 warning). The 812 counts rows past the last FDS frame (250 s) as in `scenarios.json`; 739 rows are past the slightly larger guard (252.03 s).

**W3b gap:** the `W3b_cmm` case does not write `--output-route-cost-history`, so the horizon bound cannot be computed for it (guard and warning count are still recorded). Adding `rc.csv` to its outputs would change the case's output set and cost; I did not do that. perf-model/coordinator decide whether the W3b criterion is the guard plus the warning count only (W3b finishes at 21.5 s of a 122 s guard, so the bound cannot approach it by a wide margin) or whether to add the output.

## Driver and analysis

- `g1_all.sh`: after every block whose case is W1, W3, W3b_cmm or W1r, a loop calls `horizon_check.py` on each run directory `results/raw/<block>_<case>_*` (outside the block, untimed); a failure is logged `HORIZON_CHECK_FAILED <run>`. Fixture block now 1 + 5 repetitions. `bash -n` OK.
- `analyse.py`: `summary.csv` gains `max_bound`, `held_share`, `warning_count` read from each run's `horizon.json` (empty when absent). Checked in a scratch copy (`python3 -I`, `results/raw` symlinked): 30 rows, the three columns filled for the four runs above, no exception. The group file does not aggregate them.
- `horizon.json` now sits in five existing `g0v2*` run directories (added files; no manifest touched).

## README "Running G1"

Section 7 of `README.md`: pre-checks (`benchmark.py check` must print `ok: True`, `verify_stage.py` count 10, worktree clean, no `g1_all`/`benchmark.py` process, `__pycache__` removal), the start command (`nohup caffeinate -s bash g1_all.sh > results/blocks/g1_all_<UTC>.log 2>&1 < /dev/null &`, pid file, `sleep 2; pmset displaysleepnow`), what to watch (`results/blocks/g1v2_status.tsv`, the driver log, status line meanings), early stop, and the D27 split between a harness fault (traceback outside the model, run directory without a manifest, unreadable gate JSON, `HORIZON_CHECK_FAILED`, `vblock` failing without a manifest) and a result (a real `NOT equivalent` or failed negative control stops the driver; zero where a counter must be active; `passes: false` on W1 or W3; killed at a limit; W1r failing its horizon criterion is expected and declared). Expected duration about 1.5 h is an estimate.

## Inputs/commit

`8f7d29a2e056db46183e8cccabce338c398606a1`, lock `7f64a58d...`; `plan.md` D25-D28; `review.md` "G0 v2 re-check" notes 1-3.

## Files produced

Package dir `/Users/chraibi/workspace/PedestrianDynamics/Fire/fds_visibility/visibility_workshop/studies/profiling/`: new `horizon_check.py`; edited `g1_all.sh`, `analyse.py`, `README.md`; `results/raw/g0v2b_W1_*`, `g0v2b_W3_*`, `g0v2b_W3b_cmm_*`, `g0v2b_W2_*`, `g0v2d_W1r_*` each gained `horizon.json`.

## Commands executed

```bash
$PY horizon_check.py results/raw/{g0v2b_W1_O*,g0v2b_W3_O*,g0v2b_W3b*,g0v2d_W1r*,g0v2b_W2*}
python3 -I analyse.py --include-dev        # scratch copy with results/raw symlinked
bash -n g1_all.sh ; find . -name __pycache__ -prune -exec rm -rf {} +
```

## Observations

- The criterion now reproduces QA's and the model's numbers from the run files alone.
- Only W1r fails it, as declared (D22): 8.2 % held rows, one warning.
- The check needs the baseline venv (it imports `pyfds_evac` and opens the FDS directory with fdsreader); it prints the usual numpy and fdsreader warnings.

## Uncertainties

- `g1_all.sh`, `gate`, `vblock`, the horizon calls inside the driver and `vbuild_bench.py` at n = 1001 have not executed; the README fault/result table is my reading of D27 and the log formats, not tested on a real failure.
- `base_speed` is hard-coded per case (the decks set none); a deck change would not be seen.
- The bound is an upper bound of the latest sample time (scenarios.json wording), not a measured read time.
- Reading the horizon from the staged FDS opens it again after the run (one more parse per check, untimed).

## What perf-model must check

The W3b criterion (guard and warning count only, or add `rc.csv`), the base speeds, and that "rows past the last frame" is the held-share definition you want.

## What perf-qa must check

Read-only: re-run `horizon_check.py` on the four runs and compare with the table; `bash -n g1_all.sh`; the README section 7 commands against the real file names and the status-line formats; that no `__pycache__` is left before the slot.

---

### G1 pass 1 -> pass 2 harness (2026-10-16)

Harness only, untimed, no production code. Pass 1 untouched: `results/raw/G1*` (150 directories, same count before and after), `g1v2_status.tsv`, `summary*.csv` and the pass-1 equivalence JSONs are unchanged; analysis was tested in a scratch copy. Worktree `/Users/chraibi/profiling-stage/wt_8f7d29a2` clean. Backups: `/Users/chraibi/profiling-stage/tmp/{g1_all.sh,compare.py,analyse.py}.g1_pre`.

| # | Change | Check |
|---|---|---|
| 1 | `g1_all.sh`: `block()` takes the `g1_resume3.sh` changes (up to 3 tries; on rc 1 + "exclusive slot check failed" log `SLOT_RACE_RETRY`, `wait_slot`, retry; `[ -d "$d" ] \|\| continue` in the horizon loop). Pass tag `PASS=${G1_PASS:-G1b}`: every block name is `${PASS}_<name>` (`G1b_det`, `G1b_base`, ...), status file `results/blocks/g1b_status.tsv`, equivalence files `${PASS}_...json`, W4 extras `${PASS}_w4_extra`, analysis log `analyse_${PASS}.txt`. A `first_id` / `--block` glob such as `G1b_ovh_*` cannot match `G1b_ovhD_*` or any pass-1 `G1base_*`. New `G1_DRY_RUN=1` mode prints the planned blocks and exits (status goes to /dev/null). | `bash -n` OK; `G1_DRY_RUN=1 bash g1_all.sh` prints all 22 blocks, both gates, the V-build block, the W4 extras and exits 0 with no status file or run directory created |
| 2 | `compare.py` rule 10c: item 10 is now exit code, summary line and the looks line; `route_cost_samples` is item `10c_route_cost_samples`, compared only when both runs have `rc.csv` in their output directory, else `not_in_both` plus the gap text "10c route_cost_samples not compared (route-cost history not written by both)". `not_in_both` never counts as equal and never as a difference. | Re-derived `results/equivalence/G1out_vs_G1base_v2.json` (18 pairs) and `G1outchk_vs_G1base_v2.json` (1 pair) from the pass-1 outputs with `--ref G1base_W1_O_study_s1_rep1_20261016T043233`: all 19 `equivalent`, no DIFFERENT item. Against perf-model's `*_restricted.json` every item state matches pair by pair, with **one exception**: the 6 pairs `G1out O_study` vs `G1base O_study` (both wrote the history, 64 994 = 64 994) show `10c equal` in the new code but `not_in_both` in the restricted file, which marks 10c `not_in_both` for those too. By the rule written in that file ("compared only when both runs wrote the history") `equal` is the correct value; perf-model should confirm. Verdict wording differs only ("equivalent on items both write" vs "equivalent"). Negative control and an equivalence pair on W3 (below) still behave. |
| 3 | `analyse.py`: group key adds `block` and `instrument_level` (none / counters / detail, from `PYFDS_PERF_DETAIL` in the manifest env); no spread (q1, q3, IQR) for fewer than 3 runs used (median only; `n_used` column); two tables: `summary_groups.csv` (clean, default, flagged runs excluded) and `summary_groups_all.csv` (flagged-inclusive, `table` column labels it, `n_contaminated` kept). | Scratch copy (`python3 -I`, `results/raw` symlinked, `--include-dev`): 182 runs, 63 clean and 63 flagged-inclusive groups, 41 blocks, three instrument levels, no group with an IQR from fewer than 3 runs; G1ovhD splits into counters 47.77 s, detail 60.08 s, none 47.31 s (n = 5 each). |
| 4 | W3 capture: `instrument/perf_run.py` replaced `pyfds_evac.core.run_scenario`, but the CLI resolves `run_scenario` from `pyfds_evac.core.scenario` (`cli.py` lazy names), so the capture wrapper was never called and `result_capture.json` was never written. It now patches `pyfds_evac.core.scenario.run_scenario` as well. | Two untimed `--shared` W3 runs with `--capture-result --vis-cache noflag` (`g1c_dev_W3_...`, `g1c_dev2_W3_...`, not measurements): both wrote `result_capture.json` (274 cognitive-map history entries, metrics keys present); `compare.py` of the pair: `equivalent`, items `12_cognitive_map_history` and `12b_result_metrics` **equal**, no gaps. So tonight's gate compares the captured state; the metrics comparison excludes wall/elapsed/path/file/created fields (existing `METRIC_EXCLUDE`) and did not trip. |
| 5 | `benchmark.py` host monitor: each manifest's `host_during` gains `offenders_detail` (per executable path: `path`, `name`, observed `ppids`, `max_pcpu`, `class`) and `offenders_class_rule`. `class` is `system_daemon` when every observed instance has ppid 1 and a path under `/System/`, `/usr/libexec/` or `/usr/sbin/`, else `user`. The contamination verdict, thresholds and reasons are unchanged. | Dev runs (`g1c_dev3_W3b_...` clean: empty list; `g1c_dev4_W3b_...` with a `yes` busy loop started beside it): `yes` 100 % and `top` 33 % reported with their ppids, both `user`; `offender_class` unit-checked: ppid 1 under `/usr/libexec` and `/System` -> `system_daemon`; user app path or ppid != 1 -> `user`. The tag has not yet been seen on a real daemon offender. |

Other checks: `bash -n g1_all.sh` OK; `ruff check --no-cache .` in the package reports 22 findings, all style rules (PLW1510, BLE001, RUF046, RUF100, FURB, I001, RUF059, PLC0206) and none introduced by this round (the three edited scripts had the same 5 before and after; the rest are in other files); no autofix applied, to keep diffs minimal. `__pycache__` removed again at the end. README section 7 updated for the pass tag and `G1_DRY_RUN`.

**Inputs/commit.** `8f7d29a2e056db46183e8cccabce338c398606a1`, lock `7f64a58d...`; `model_handoff_g1.md`, `review.md` "## G1".

**Files produced.** `results/equivalence/G1out_vs_G1base_v2.json`, `G1outchk_vs_G1base_v2.json`; dev runs `results/raw/g1c_dev_*`, `g1c_dev2_*`, `g1c_dev3_*`, `g1c_dev4_*` (all `not_a_measurement`, exclude from summaries). Edited: `g1_all.sh`, `compare.py`, `analyse.py`, `benchmark.py`, `instrument/perf_run.py`, `README.md`.

**Commands executed.** `bash -n g1_all.sh`; `G1_DRY_RUN=1 bash g1_all.sh`; `compare.py --block G1out|G1outchk --ref G1base_W1_O_study_s1_rep1_20261016T043233 --out ..._v2.json`; four `benchmark.py run --shared` dev runs (W3 x2 with capture, W3b x2); scratch `analyse.py`; `ruff check --no-cache .`.

**Uncertainties.** `g1_all.sh` is still unexecuted as a whole (dry run plus `bash -n` only); the retry loop is copied from the script that ran. The `system_daemon` tag is tested on synthetic offenders only. The D31 criterion also names `/usr/sbin`, which I included; `top` in pass-1 manifests came from someone else's process (ppid not recorded then; now it is). The item-10c difference with the restricted file needs perf-model's ruling.

**Perf-model must check:** the 6 O_study pairs in `*_restricted.json` (10c equal vs not_in_both); the `class` rule paths for D31 (i). **Perf-qa must check:** the `_v2.json` files against the pass-1 outputs, the `result_capture.json` of tonight's `G1b_det_W3` runs, that `analyse.py` output has no pooling across blocks, and that no `G1b_*` directory shares a prefix with pass 1.
