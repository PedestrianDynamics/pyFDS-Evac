# perf-qa review

## G0

Reviewer: perf-qa. Date: 2026-10-02. Spec: `~/.claude/docs/profiling_team.md` v2.0, gate G0.

**Status: PASS.** G1 may start once the entry conditions below are met. I accept the comparison design, data availability and resource limits. No finding blocks G0. Six important findings are G1 entry conditions: I1–I6, owners named. This review covers the coordinator's update: `plan.md` (W3 row, O_study/O_norc/O_min, D9), `engineer_handoff_g0.md` §9 and `model_handoff_g0.md` §9. No timed runs were made by QA. All checks were read-only. Scratch output: `<scratch>/perf-qa/stage_verify_qa.json`.

`<scratch>` = `/private/tmp/claude-503/-Users-chraibi-workspace-PedestrianDynamics-Fire-fds-visibility-visibility-workshop/912eedf9-4145-46cc-bb81-967d1c8ae7ac/scratchpad`, `<P>` = `<scratch>/profiling`, `R` = `results/raw`.

### Checks performed

| Check | Result | Evidence |
|---|---|---|
| Frozen commit, lock, clean worktree | OK | `git -C <P>/wt6 rev-parse HEAD` = `6fd7878c9ef5…`. `git status --porcelain` is empty; only `.venv/` and `__pycache__/` are ignored. sha256: `uv.lock` `2731a9e7…`, `run.py` `a192580e…`, `pyproject.toml` `922daba3…`. All equal `scenarios.json`. |
| `6fd7878c` vs `289b33d0` changes no model code | OK | `git diff --name-only 289b33d0 6fd7878c -- pyfds_evac run.py assets` returns 0 files. |
| Run manifests | OK | `R/g0_w1_gate_s1_6fd7878c`, `R/g0_w2_nf_s1_6fd7878c`, `R/g0_w3_tj_committed300_{diag,s43,s44}`. All have commit `6fd7878c`, `git_dirty` false, lock `2731a9e7…`, `spawn-key-blake2b-v2` and jupedsim 1.4.2 / fdsreader 1.11.7 / fdsvismap 0.3.1. All read the staged `fds_dir` and run the scenario from `wt6`. The `289b33d0` run carries `status_label: SUPERSEDED` in `R/g0_w1_gate_s1_repro/manifest.json`. |
| Staged inputs | OK, independently re-run | `verify_stage.py /Users/chraibi/profiling-stage <scratch>/perf-qa/stage_verify_qa.json`: 8/8 directories, rc 0, aggregates identical to `results/stage_verification.json`. The stage dirs have no subdirectories, so the flat check is complete. |
| Reference hashes come from sciebo | OK, spot-checked | `.fds`, `.out`, `.smv` and the first `.sf` of a047, t_junction and cmm, read from sciebo, equal `preflight/input_hashes.json` (12/12). |
| Sciebo pickles untouched | OK | `stat` size and mtime equal `scenarios.json` `user_caches_untouched` to 0.01 s: 475989 / 312508 / 102532 B. |
| Derived configs | OK, by flat JSON diff, not by trusting `make_derived.py` | n100/n400: only `distributions.jps-distributions_0.parameters.number` (200→100/400). cap270 and cmm cap120: only `max_simulation_time`. All 4 `geometry.wkt` files are byte-identical to the base, and the sha256 values match `scenarios.json`. |
| Profiler venv runs the same source | OK | Both `wt6/.venv` and `venv_prof6` import `pyfds_evac` from `<P>/wt6/pyfds_evac/__init__.py` on CPython 3.12.13, with identical jupedsim/fdsreader/scikit-image (0.23.2)/numpy versions. `uv pip list` diff: the profiler venv only adds packages (py-spy, scalene, memray, pyinstrument and their deps) and changes no version. `pyfds_evac`, fdsreader, fdsvismap and jupedsim do not import any of the added packages (rg). |
| W1 is genuinely coupled | OK, recomputed from raw outputs | Recomputed from `gate_s1_fed.csv`, `gate_s1_rc.csv`, `gate_s1_rh.csv` and `gate_s1.sqlite`, without `g0_activation.py`. Smoke speed: 0 < speed factor < 1 on 4 951 rows / 123 agents, min 0.10. FED > 0 on 14 960 rows, max 0.0383; O2 min 18.76 %. Route cost: 65 142 rows, 44 293 with `k_ave_route > 0`, 6 656 rejected. Switches 267: 109 `smoke_reroute`, 91 `better_path`, 67 `fallback`, at 47–209 s. Spawning: 200 agents at frame 0, 4 000 frames. Domain: 0 rows outside. Horizon bound `max(time_s + path_length_m/1.0)` = 430.6 s < 481 s. |
| W3 window | Resolved: committed 300 s deck for all seeds | s43/s44 exit with code 2, without `FdsHorizonError` or hold. Bounds: 58.8 s / 57.8 s, against 301 s. |
| W3 vismap build | Deterministic across processes | The `vis`, `metres`, `time_points`, coords and `meta` arrays are equal in the three `w3_vis.npz` files (diag, s43, s44), compared array by array. |
| W1 determinism observation | Partly confirmed | The 4 CSV sha256 values (`f0bc5745`, `781fa749`, `2f10f443`, `ddf9057e`) equal `R/g0_w1_gate_s1_repro/output_hashes.sha256`. The trajectory prefix `623a346a` could not be cross-checked because the serialisation recipe is not recorded (O3). This is an observation, not the formal G1 gate. |
| Roles and labels W1–W4 | OK | W1 is the time-limited 400 s window with gate as the headline arm. W2 is the `nf` arm, matching `run_p1.sh` (`nf) ;;` without `--fds-dir`). W3 is labelled sign discovery, time-limited and incomplete, with work counted over spawned agents. W4 is mechanism-only. Arm comparisons are labelled end-to-end, and the "never subtract" rule is declared (`model_handoff_g0.md` §4). |
| Equivalence declared before data | OK | `model_handoff_g0.md` §3: exact equality, `PYTHONHASHSEED=0`, `repr` comparison, determinism gate first, no tolerance, list of compared and excluded fields. The changed-workload classification is in place. |
| Limits and stop rules | OK | `plan.md` and `engineer_handoff_g0.md` §5 contain the slot check, the 300/900 s and 4/8 GB caps, the repetitions (1+5 up to 15, first-use 3, seeds 2–3 × 3, ABAB), the 4 h cap → PARTIAL, and 6 stop rules. These meet spec §6/§8. |
| Preflight outputs | OK | `preflight/w*.json` agree with the handoffs. W1: 6 meshes, 0–480 s at 1 s, CO/CO2/O2/K/T at 1.6 m, K also at 2.0/2.8 m. W3: 4 meshes, 0–300 s, all quantities at 2.0 m only, incl. HCl and VISIBILITY. cmm: 0–120 s at 2.07 s, 2.0 m. iso21: K at 1.5/2.0 m, 0/75/150 s. iso22 a–d: 1.5 m, every 500 s. `preflight_fds.py` reads `.smv`/`.sf` directly and does not import fdsreader. The ISO preflights were taken from `main_f5c6`, but `assets/` is unchanged between `289b33d0` and `6fd7878c`, and the staged copies verify. |
| W1 output variants | OK as designed | `model_handoff_g0.md` §9.1 defines O_study, O_norc and O_min with an untimed exact-equivalence check before timing. If the check fails, the comparison is labelled end-to-end. The route-cost history stays part of normal output (study figure `p1_tau`). The possible order dependence in `route_segment_cache` is correctly routed to the backend team, not fixed here. |
| `--allow-fds-horizon-hold` | Only the declared exception | W4-cmm arm A (untimed, equivalence-only, `scenarios.json`) is the only use. No G0 run used it (all `cmd.sh` checked). |
| No G0 run presented as a measurement | OK | Every G0 file and handoff says "not a measurement". The times appear only as limit sizing, with the load average 2.7–9.1 recorded in `load_before.txt`. |
| py-spy gap (D8) | Accepted | See O1. |

### Blocking

None.

### Important (G1 entry conditions)

**I1. fdsreader "repeated use" does not mean "no `.smv` parse".** Owners: perf-engineer (measurement and labels), perf-model (cache-state definitions).

*Mechanism (static).* In fdsreader 1.11.7, `Simulation._loading` is a class attribute (`fdsreader/simulation.py:57`). The first pickle load sets it to True (`:71-72`) and nothing resets it. Every later `Simulation(path)` in the same process skips the cache, re-parses the `.smv` and dumps the pickle again (`:198-202`).

*Sites.* One CLI process reaches several independent constructions:
- `run_config.py:131` via `fds_output_horizon` (`fds_sampling.py:366`);
- `run_config.py:146/153/222` via `inspect_fds_quantities` (`fds_inventory.py:70`);
- `load_slice_sampler` without `simulation=` (`fds_sampling.py:344`);
- for W3 also `visibility.py:154` and fdsvismap `FDSVisMap.py:487`.

*Corroborating observation.* The t_junction stage pickle mtime is 17:20:13. That is 1 s into s44, which started at 15:20:12Z (17:20:12 local), right after s43. The pickle state before s44 is not recorded, so this observation alone is ambiguous.

*Consequence.* "Pickle present" means:
- the first open comes from the cache;
- later opens are re-parsed;
- the file is rewritten during every run.

The fdsreader first-use vs repeated-use difference is a hypothesis ("probably small"), not a finding.

*Required for G1.*
- Count pickle loads vs full parses per process with a wrapper on `Simulation.__new__`/`__init__`, and label repeated use accordingly.
- Record `pickle_present_before` for every run. W3 dirs lack it today.

**I2. Most W3 sign queries hit an all-invisible map. The §8 condition is "met" too loosely.** Owner: perf-model; perf-engineer for the counter.

*Visible-cell fraction.* In `R/g0_w3_tj_committed300_diag/w3_vis.npz` (denominator: all 121×53 grid cells, including non-walkable), the fraction per sign `[exit_A_left, exit_B_right, jps-checkpoints_0]` is:

| t | exit_A_left | exit_B_right | jps-checkpoints_0 |
|---|---|---|---|
| 0 s | 0.224 | 0.230 | 0.150 |
| 43 s | 0.034 | 0.001 | 0.037 |
| 60 s | 0.002 | 0 | 0.005 |
| 100–300 s | 0 | 0 | 0 |

The arrays are identical for s42, s43 and s44.

*Dev counter run (`R/dev_counters_w3_s42/counters.json`).*
- 87 % of the 21 169 `node_is_visible` calls (18 398) fall at t ≥ 100 s, where every in-grid sign query must return False.
- `node_is_visible_true` (410) also counts the unconditional `True` for nodes without a sign descriptor (`visibility.py:830-832`). It is therefore not a sign-visibility count.

*Required.*
- Split the `True` counter into sign / non-sign / off-grid (`_sight_outside_grid`) and bin it in time.
- State in the W3 label that late visibility work is querying a fully smoke-obscured map.

This is a legitimate cost and W3 stays valid, with #91 already labelled (model §9.2). Engineer §9.3 and model §9.3 call the condition "met in substance"; that is premature until the split exists.

**I3. Instrumentation (D9): wrapper design accepted. `plan.md` is internally inconsistent.** Owners: coordinator (`plan.md`), perf-engineer (wrapper).

*Accepted.* I read `instrument/perf_counters.py` and `perf_run.py`:
- the hooks call the original with unchanged arguments and return its result;
- the counters read only arguments and return values, plus the read-only `agent_count()`, `delta_time()` and `in_grid()`;
- names bound at import time in `scenario.py` are re-bound (`init_cognitive_map`, `expand_on_arrival`, `evaluate_and_reroute`, `rank_routes`);
- `route_graph.py:2691` imports `nearest_frontier_target`/`wander_target` lazily, so the wrapped versions are seen;
- I found no other early binding of the wrapped names in `pyfds_evac/` (rg).

*Still to fix or check in G1:*
- `plan.md` line 20 still says "on its own branch in the worktree", which contradicts D9.
- Record the instrumentation identity in every manifest: the sha256 of `instrument/*.py` plus `PYFDS_PERF_COUNTERS_OUT` set or unset.
- The overhead baseline must be plain `run.py`. `perf_run.py` without the environment variable is a different entry point (`runpy`, `sys.path`).
- The `iterate` wrapper splits `iterate(count)` into `count` calls of `iterate(1)`. The only call site, `scenario.py:3021`, calls `simulation.iterate()` with the default count of 1, so this is harmless for every workload here.
- The dev equivalence (`dev_counters_*`) is development evidence only. It is not the formal G1 overhead/equivalence result.

**I4. The harness does not exist yet.** Owner: perf-engineer.
- `benchmark.py`, `analyse.py`, `README.md`, `results/summary.csv` and `findings.json` are absent. The exclusive-slot check and the §11 per-run manifest fields are therefore not implemented. Those fields are: run ID, case/variant, instrumentation identity, input and cache fingerprints (fdsreader and vismap separately), profiler state, termination status and thread env.
- `manifest.git_dirty` uses `--untracked-files=no`, and `assets/**/*.pickle` is ignored, so it cannot detect untracked additions. The harness must record `git status --porcelain --untracked-files=all` itself.
- Entry condition: perf-qa reviews `benchmark.py` before the first measured block.

**I5. W2 routing work is not yet shown.** Owner: perf-engineer.
- W2 writes no route-cost CSV and has 0 switches. Its log prints `Reroute debug pass` only at t = 0 (1 occurrence), so the logs cannot show that 1 s routing passes run in clear air.
- The G1 counter (route evaluations per 10 s bin, already in the draft) must be nonzero across the run before W2 steering/routing shares are reported.

**I6. Exclusive slot not met today.** Owner: coordinator.
- Load averages were 2.7–9.1, with `/tmp/release-check.*` active, and `git worktree list` shows `/tmp/release-check.S0wXgR/repo` and the `docs/release-fixes` worktree still present.
- G1 measured blocks start only after the coordinator confirms that the release check and the other agents have stopped. The plan already says so; this records that the condition is currently false.

### Optional

**O1. D8 accepted.**
- sudo would only enable `py-spy record` without `--native` on macOS. That gives Python-only stacks, which pyinstrument already provides.
- Conditions:
  - declare pyinstrument's mode (wall vs CPU) and its thread coverage;
  - use Scalene's Python/native split and `/usr/bin/sample` for native hot spots;
  - keep "no joint Python+native sample" in the report's Limits.
- No maintainer decision is needed unless they want py-spy for subprocess or low-overhead sampling.

**O2. Stale W3 cap text.** Owner: perf-model / coordinator.
- `model_handoff_g0.md` §1 (table: "capped at 270 s") and §2 (preflight "cap 270 s") still contradict §8/§9.3 and `scenarios.json` (300 s).
- `plan.md` D5 still reads "horizon fallback 270 s", and Scheduling step 1 is done.
- Mark them superseded and record D5 as closed (bounds 56.8/58.8/57.8 s).

**O3. Trajectory hash recipe.** Owner: perf-engineer. Record the exact serialisation behind the trajectory hash prefixes (`623a346a`). QA's `repr`-joined `frame,id,pos_x,pos_y,ori_x,ori_y` ordered by `frame,id` gives `1ef52fdc` for the same file. Put one script in the package so that the G1 determinism gate is reproducible.

**O4. Incorrect safeguard claim.** Owner: perf-model. `model_handoff_g0.md` §6 says a pickle in the worktree "would make `git_dirty` true". It would not, because `.gitignore:193` covers `assets/**/*.pickle` and the manifest ignores untracked files. W4 pytest (`test_iso_table21_coupled.py:45`) reads `wt6/assets/.../fds` and will write pickles there. Correct the claim, and record the pickle state for the pytest fixture runs.

**O5. Thread environment.** `OMP_NUM_THREADS=4` is inherited from the shell, and `VECLIB_MAXIMUM_THREADS` is unset. Set both explicitly in `benchmark.py`, or document them in README, so that QA and colleagues reproduce the same environment.

**O6. Ephemeral environment.** The frozen worktree and venvs live in the session scratchpad under `/private/tmp`. README must give the recreate recipe:
- `git worktree add --detach … 6fd7878c`;
- `UV_CACHE_DIR=… uv sync --frozen --python 3.12`;
- the profiler venv command.

G3 reproduction must not depend on this session's directories.

**O7. N = 400 placement.** Not yet shown; the 300 fallback is declared. Confirm in the first G1 scaling run that 400 agents spawn, before the repetitions.

### What perf-model / perf-engineer must check next

- perf-engineer:
  - the fdsreader parse/load counter and `pickle_present_before` (I1);
  - the sign/non-sign/off-grid `True` split, binned (I2);
  - the instrumentation identity and the plain `run.py` overhead baseline (I3);
  - the harness (I4), the W2 evaluation counter (I5).
  - Send `benchmark.py` to perf-qa before the first measured block.
- perf-model: the tightened W3 condition and label (I2), O2, O4.
- Coordinator:
  - correct `plan.md` line 20 and D5 (I3, O2);
  - confirm the exclusive slot (I6).

## G0 follow-up

Inputs reviewed: `engineer_handoff_g0.md` §10, `benchmark.py`, `analyse.py`, `traj_hash.py`, `README.md`, `instrument/perf_counters.py` (fdsreader hook), and the `dev10_*` manifests and counters. All work was read-only and untimed. All `dev10_*` runs are `--shared` and contaminated; I use them as development evidence only.

**Status: G0 PASS stands.** G1 is still blocked by **I6** (busy machine). Before the first measured block, F1 and F2 below must be fixed. F3 and F4 must be fixed before the overhead and output-variant blocks.

### I2 disagreement: resolved. The counters are right, and my map reading was wrong.

My "0 from 100 s" came from rounding the visible fraction to 3 decimals. One cell is 1/6 413 = 0.00016 of the grid, so a few visible cells showed as 0.000.

Exact count from `R/g0_w3_tj_committed300_diag/w3_vis.npz` (same arrays for s43/s44), for t ≥ 100 s:

| Sign | Time points with any visible cell | Visible cell-instants in total |
|---|---|---|
| exit_A_left | 201 of 201 | 391 |
| exit_B_right | 201 of 201 | 432 |
| jps-checkpoints_0 | 201 of 201 | 255 |

The remaining visible cells are the 1–4 cells next to each sign (≤ 0.25 m away):
- exit_A_left at (0.5–0.75, 11.5);
- exit_B_right at (29.25–29.5, 11.25–11.75);
- the checkpoint at (18.5, 10.25–10.5), at the junction that wandering agents cross.

So the engineer's 21 sign-positive in-grid results at t ≥ 100 s are consistent with the array. They are agents standing at a sign.

**Corrected I2 conclusion.** After about 60 s, each sign can be seen only from the cells next to it. 18 398 of 21 169 sign queries (87 %) come at t ≥ 100 s, and 21 of those are positive. That is a legitimate, smoke-driven cost, and W3 shows activation under the model §10 criterion (sign-True > 0, sign-sighting growth 41 events, non-sign 0). The W3 label must still say that late sign queries are made against a field where signs are visible only at arm's length.

**I2 closed.** perf-model should add that wording to the W3 label.

### Status of earlier findings

| Finding | Status | Evidence |
|---|---|---|
| I1 fdsreader cache | **Closed** | Hook on `Simulation.__new__`/`__init__` (`perf_counters.py:76-112`): `_hash` presence at `__init__` separates a pickle load from a parse, and nested unpickling `__new__` calls are tracked by depth. W3 s42 shows 8 opens / 1 load / 7 parses in both states (`dev10_W3_O_study_s42_rep1_…T153508`, `…T153521`). Labels are derived from the observed state (`benchmark.py derive_cache_label`), and pickle presence and sha256 are recorded before and after each run. The `counters_agree:false` on `…T153508` is a stale label from the earlier rule; leave it, it is a dev run. |
| I2 | **Closed** (see above) | |
| I3 instrumentation identity and baseline | **Closed** in harness; `plan.md` still open | The manifest records the sha256 of `instrument/*.py` and `benchmark.py` and whether counters were on. The overhead baseline is plain `run.py` (`build_command`). `plan.md` line 20 ("branch in the worktree") still contradicts D9; coordinator. |
| I4 harness | **Partly closed**, see F1–F6 | The files exist. Slot gating, the clean-worktree check (untracked-all), §11 manifest fields, process-group kill, ABAB/ABBA interleaving and kept warm-ups/failures are all present. |
| I5 W2 routing work | **Closed** | `dev10_W2_nf_s1_rep1_…T153554`: 29 910 evaluations, nonzero in every 10 s bin, 0–310 s. |
| I6 exclusive slot | **Open, blocks G1** | `benchmark.py check` fails (engineer §10.1). |
| O1 py-spy / profiler mode | Open (optional) | pyinstrument's sampling mode (wall clock, interval) is not yet recorded in the manifest. |
| O2 stale 270 s text | Open (optional) | Not re-checked. |
| O3 trajectory hash | **Closed** | `traj_hash.py` repr-v1 = `1ef52fdc…` (equals mine); sqlite-cli = `623a346a…`. Both recipes are documented. |
| O4 git_dirty claim | Open (optional) | perf-model. |
| O5 threads | **Closed** | Fixed in `child_env`, recorded in the manifest. |
| O6 recreate recipe | **Closed** | README §1–2. |
| O7 N = 400 | **Closed** | `dev10_W1_n400_…T153615`: 400/400 placed at frame 0, 0 not spawned. |

### Harness review: new findings

**F1 (important; perf-engineer): runs shorter than the monitor period are never sampled for contamination.**
- `monitor()` waits `--monitor-s` (15 s) before its first `ps` sample. The W3 dev run `…T153521` (11.9 s wall) has 0 host samples. W2 (~17 s) gets at most 1.
- Contamination of short runs is therefore judged only by `slot_before`.
- Fix:
  - include `slot_after` in `contaminated`;
  - use a shorter period, for example 2 s; `ps` costs only a few ms.

**F2 (important; perf-engineer): the "loop" phase is not the evacuation loop.**
- `"Simulation started."` is printed (`run.py:657`) after `build_run_kwargs`, but before `run_scenario`.
- The `phase_loop_s` window therefore includes the setup inside `run_scenario`: JuPedSim `Simulation` construction, geometry, spawning, the first samplers and the initial route choice. It also includes the temp-SQLite trajectory writing.
- `phase_startup_s` covers imports, config, FDS inventory and horizon, and for W3 the vismap build/load.
- Fix:
  - rename the metrics to `phase_pre_run_s` / `phase_run_scenario_s` / `phase_post_run_s`;
  - state which phase each setup step falls in;
  - `loop_us_per_agent_step` in `analyse.py` then means "run_scenario per agent-step";
  - spec §6 asks for startup/loop/finalisation separately, so G2 needs an in-process loop timer from the counters (with an overhead check).
- With the honest names this does not block the G1 baseline.

**F3 (important; perf-engineer, perf-model): no tool implements the model §3 equivalence check.**
- `analyse.py` only counts distinct trajectory hashes within a group. Groups split by `instrumented` and `variant`, so it never compares baseline against counters, or O_study against O_norc/O_min_check.
- Model §3 also compares:
  - exit, route, route-cost and FED histories (they are in `output_sha256`; the app manifest must be excluded because it has a timestamp);
  - exit code;
  - outcome;
  - for W3, `cognitive_map_history`, which the CLI does not write and no harness collects yet.
- Before any G1ovh/G1out result is labelled `controlled-cost`, add a comparison script that applies the §3 field list and exclusions across the paired runs. Also add the `build_run_kwargs` harness for the W3 map history, or record that comparison as a named gap.

**F4 (important; coordinator, perf-engineer): self-load can trip the per-run contamination flag.**
- `contaminated` uses `slot_before.ok`, which includes 1-min load < 1.5. This is measured right after the previous serial run.
- The benchmark's own back-to-back runs may hold load1 near 1. It is unknown whether this crosses 1.5.
- Check this in the first exclusive block:
  - if runs are tagged only on load1 while no foreign process is heavy, fix the rule (for example, foreign-only for per-run tagging), record it in `plan.md`, and do not silently loosen it;
  - the block-start gate can stay as it is.

**F5 (optional; perf-engineer): `--dry-run` has a small side effect.** `child_env()` creates `$STAGE/tmp/<run_id>/` before the dry-run return, and the directory is not removed. Cache unlinking is correctly skipped.

**F6 (optional; perf-engineer): small manifest gaps.**
- The study-dir `geometry.wkt` of derived scenarios is not hashed per run. The worktree check covers only in-repo geometry.
- There is no venv fingerprint, such as a hash of `uv pip freeze`, for either interpreter.
- The profiler options are not recorded (O1).
- README has no commands for O_min_check, W4 iso22, cmm arm A or the W4 pytest set. These are in `scenarios.json`; add them or point to it.

**Accepted as is:**
- `start_new_session` plus `killpg(SIGKILL)` kills `/usr/bin/time` and the child together, and a missing `time_l.txt` gives null, not 0.
- `order()` gives ABAB or ABBA across (variant × instrumentation), with warm-ups per combination.
- First-use deletes only the own-stage pickle (path assert), and a missing repeated-use cache aborts the run.
- `analyse.py`:
  - excludes warm-ups and non-measured runs;
  - groups never pool case, variant, seed, observed cache state, instrumentation, profiler, commit or label;
  - contaminated runs are counted but left out of the statistics;
  - values are null, never 0.
- `PYTHONUNBUFFERED=1` vs the file redirect in `scenarios.json`: the progress line already uses `flush=True` (`scenario.py:1841`), with about 900 writes per W1 run, so the difference is negligible. It stays recorded as `phase_method`.

### Entry conditions for the first measured G1 block

1. I6: `benchmark.py check` passes (coordinator).
2. F1 fixed; F2 metric names corrected (perf-engineer). QA re-reads the diff; no re-review of the whole harness is needed.
3. F3 is required before G1ovh/G1out only. The determinism gate and the baseline blocks may start without it, as long as the determinism comparison uses repr-v1 plus `output_sha256` (without the app manifest) and that comparison is written down.

## G0 follow-up 2: harness re-review (engineer_handoff_g0.md §11)

**Scope.** I re-read `benchmark.py`, `analyse.py`, `compare.py`, `instrument/perf_counters.py` (fdsreader, `run_scenario` and loop timers), `instrument/perf_run.py` and README §3–§6. I also re-ran `compare.py` read-only on the dev11 runs, writing to the QA scratchpad only. No runs were made.

**Outcome.** The harness is **cleared for the first measured G1 block, pending only I6**: `benchmark.py check` must pass on a free machine. Condition C1 below applies to any `--capture-result` run in an `--exclusive` block. It does not affect the timed baseline blocks in README §3.

| Item | Status | Evidence |
|---|---|---|
| F1 contamination coverage | Closed | The default `--monitor-s` is 2.0 (`benchmark.py:656`). A slot check runs after every run (`:504`). `contamination_reasons` records foreign load before, during and after, plus `load1_before` and power. The engineer reports 5 samples on an 11.4 s run. |
| F2 phase names and loop timer | Closed | The phases are now `phase_pre_run_s`, `phase_run_scenario_s` and `phase_post_run_s`, and `analyse.py` rates are per `run_scenario`. The diagnostic `timers_s` measures the in-process loop from the first `iterate` start to the last `iterate` end (`perf_counters.py:354-356`), plus setup and tail around it inside `run_scenario` (`:366-371`). It exists only in counters runs. Its overhead belongs to the G1ovh check, and it must stay labelled diagnostic. |
| F3 equivalence tool | Closed | `compare.py` covers the 12 items of model §11.2. "Not in both" and "absent" are reported separately, and gaps are named. I reproduced both W3 dev verdicts independently:<br>• `dev11w3_…T154559` vs `…_ctr_…T154611`: equivalent, no gaps;<br>• `dev11w3plain_…T154624` vs `…T154611`: equivalent, gap "cognitive-map state not compared".<br>Negative control: W3 vs W3b_cmm is NOT equivalent on 10 items, so the tool detects differences. That control is coarse: different case. The capture (`perf_run.py`) wraps `pyfds_evac.core.run_scenario` before `runpy` executes `run.py`. `run.py:12` imports it from `pyfds_evac.core` at exec time, so the binding is caught; 263 map events were captured. |
| F4 self-load | Open by design | `load1_before` is a separate reason. The decision is due after the first exclusive block (engineer → coordinator); any rule change goes into `plan.md`. |
| F5 dry-run | Closed | `run_one` and `child_env` create no directories under `--dry-run`. |
| F6 manifest gaps | Closed | The manifest now records geometry sha256, the `uv pip freeze` fingerprints of both venvs and `profiler_options` (pyinstrument wall clock, 1 ms, main thread). README points to `scenarios.json` for W4, cmm arm A and pytest. |
| I3 `plan.md` "branch" | Closed | `rg -i branch plan.md` finds nothing. |

**C1 (important; perf-engineer): capture runs can be grouped as measurements.**
- `--capture-result` changes the entry point to `perf_run.py` and writes JSON inside the timed process. Neither `analyse.py` `GROUP` nor the run ID marks this. `instrumented` covers counters only.
- The README example `G1eqW3 … --exclusive --capture-result --label equivalence` is separated today only by its `--label`.
- Fix either way:
  - add `entry_point` and `result_capture_env_set` to `GROUP` and the run-ID tag;
  - or make `--capture-result` set `measurement_status: not_a_measurement`.
- Required before the first capture run in an exclusive block; it does not hold up the baseline blocks.

**Optional:**
- **O8.** Run the W3 determinism gate (`G1det --case W3`) with `--capture-result` on both runs, so that item 12 is compared there too, not only in the counters pair.
- **O9.** Add one sensitive negative control to `compare.py`'s checks: same case and seed, one output perturbed, for example a copy of `exit.csv` with one byte changed in a scratch directory. The current control only shows that the tool detects gross differences.

**Gate state.** G0 is PASS. The harness is cleared for the first measured block. G1 is still blocked only by I6.

## G0 follow-up 3: contamination rule (engineer_handoff_g0.md §14) and the v0.2.0 re-pin (§13)

**Scope.** I re-read only:
- the `benchmark.py` contamination diff: `SLOT`, `foreign_heavy()`, `own_tree()`, `slot_check()`, `monitor()` and `run_one` `host_during`;
- README §3, the rule text;
- the re-pin facts in §13.

The review was read-only and untimed.

**Answer: YES.** The harness is cleared for the first measured block, pending only the exclusive slot (I6). Nothing in this diff blocks it.

### Contamination rule

| Check | Result |
|---|---|
| The name pattern is gone | Yes. `SLOT = {"max_load1": 1.5, "max_foreign_cpu": 20.0}` (`benchmark.py:68`). `foreign_heavy()` filters only on `pcpu > 20`, and its callers pass rows that already exclude the own tree. |
| One definition of the own tree | `own_tree()` (`:193-195`) = `descendants(os.getpid())` ∪ {parent shell}. Both `slot_check()` and `monitor()` use it, so the definition is the same before, during and after a run. It covers `/usr/bin/time`, the run under test and the harness's own `ps`/`pmset`/`git` children, which are children of the benchmark process and alive while sampled. |
| Applied before, during and after; recorded | `contamination_reasons` (before/during/after/`load1_before`/power), `offenders_max_pcpu` (name → highest %CPU over all snapshots) and the rule text are in `host_during` (`:516-549`). Analysis is unchanged: contaminated runs are counted and left out of the statistics. |
| README §3 | Matches the code: name-independent, 20 %, own tree defined, sampled every 2 s, reasons listed. |
| Evidence | §14: `check` ok = false because of load 5.8 and WindowServer at 26 %. A dry run left no files. `dev13_W2_…T170402` (`--shared`) recorded 10 offenders. I did not re-run these. |

**Important (coordinator; decide before data, not after): the rule may contaminate every run on a desktop session.**
- WindowServer, syspolicyd, mdworker and airportd crossed 20 % in the dev13 run. A busy terminal raises WindowServer.
- If they do so routinely, every exclusive run will be tagged, and stop rule 5 ends the configuration as inconclusive.
- Declare the policy in `plan.md` **before** the first measured block. Either:
  - run with the display asleep and no foreground apps; or
  - name an explicit list of system processes, with a per-process limit, whose presence is recorded but does not contaminate.
- Choosing the list after seeing the data would be post-hoc loosening.
- The current rule is the conservative default. If the block cannot start or every run is tagged, that is an honest I6 outcome, not a harness defect.

**Optional:**
- **O10.** macOS `ps %cpu` is a decaying average (BSD scheduler estimate, roughly the last minute), not an instantaneous rate. It can flag a process that went idle just before the run, and smooth over short bursts during it. Add this sentence to the README rule and the report's Limits. The 2 s sampling does not change it.
- **O11.** The benchmark's grandparent is not in the own tree: the agent CLI that launched the shell. If it is busy during a run, it will correctly count as foreign. The operator should start blocks from an otherwise idle terminal.

### Re-pin to v0.2.0 (`3ef4ea75`): verified

- `git -C <P>/wt020 rev-parse HEAD` = `3ef4ea75e485…`, which is tag `v0.2.0` (`git describe --exact-match`). Status with untracked files included is empty.
- Hashes: `uv.lock` sha256 `171626cd…`; `run.py` is unchanged (`a192580e…`).
- `git diff --name-only 6fd7878c 3ef4ea75 -- pyfds_evac run.py app.py` returns 0 files. Under `assets/`, only `cognitive_map_memory/README.md` and `.png` changed, and no workload config or geometry.
- `uv pip freeze` of `wt6/.venv` and `wt020/.venv` differs only in the editable path. scikit-image is 0.23.2.
- Both `wt020/.venv` and `venv_prof020` import `pyfds_evac` from `wt020`.
- `benchmark.py` enforces `COMMIT = 3ef4ea75…` and `LOCK_SHA256 = 171626cd…`, with defaults pointing to `wt020` and `venv_prof020`.

**Conclusion.** The G0 activation, preflight and equivalence evidence gathered at `6fd7878c` transfers to v0.2.0 for the workloads, because the executed code and inputs are identical. The G1 determinism gate re-establishes it on the new pin.

**Important (perf-model): `scenarios.json` still pins the old freeze.** It reads `target.commit 6fd7878c…`, `uv_lock_sha256 2731a9e7…` and the 6fd7878c freeze-risk and placeholder text (lines 7, 18–19, 26). `plan.md` is updated, so `scenarios.json` disagrees with `plan.md` and with every G1 manifest. Update it to `3ef4ea75` / `171626cd…` and keep the old values as history before the first measured block. This is a one-line class of fix and does not need another QA pass beyond a grep.

### Gate state

G0 is PASS. The harness is **cleared (YES)** for the first measured G1 block once:
1. **I6:** `benchmark.py check` passes.
2. **Coordinator:** the system-process policy is declared in `plan.md`.
3. **perf-model:** the `scenarios.json` pin is updated.

Items 2 and 3 are paperwork that must exist before data. They need no re-review beyond a grep.

---

## G0 v2

Reviewer: perf-qa. Date: 2026-10-14. Spec: `~/.claude/docs/profiling_team.md` v2.0, gate G0. Subject: the re-freeze at pyFDS-Evac `main` `8f7d29a2` for the 0.6.0 perf track (issues #236 #241 #242 #243 #739 #429, umbrella #244). The v0.2.0 freeze (sections above) is superseded; nothing in it is reused as evidence for `8f7d29a2`.

**Status: PASS.** G1 may start once the entry conditions IV1–IV9 below are met. No finding blocks G0 v2. Nine important findings are G1 entry conditions; none changes the comparison design, but IV1 changes what the #242 counters may claim, and IV6 (the W1r label) and IV8 (the #241/#236 wording) change what the report may claim. Every `g0v2*` run is `not_a_measurement` and stays out of every summary.

Notation: `<P>` = `/Users/chraibi/workspace/PedestrianDynamics/Fire/fds_visibility/visibility_workshop/studies/profiling`, `WT` = `/Users/chraibi/profiling-stage/wt_8f7d29a2`, `R` = `<P>/results/raw`, `S` = `/Users/chraibi/profiling-stage`, `<scratch>` = `/private/tmp/claude-503/-Users-chraibi-workspace-PedestrianDynamics-Fire-fds-visibility-pyFDS-EVAC/5c558fd2-180c-4d74-9dd9-79f7f1d1d258/scratchpad`.

### Checks performed

| Check | Result | Evidence |
|---|---|---|
| Frozen commit, lock, clean worktree | OK | `git -C WT rev-parse HEAD` = `8f7d29a2e056…`; `git status --porcelain --untracked-files=all` empty before and after my runs. sha256: `uv.lock` `7f64a58d…`, `pyproject.toml` `b323bc2a…`, `run.py` `ccb6d4a3…`. All equal `scenarios.json` `target`, `environment.json` and every `g0v2*` manifest (`worktree.commit_ok`, `clean`, `uv_lock_sha256`; checked for all 11 manifests). Venv fingerprint identical in all manifests (74 packages, `63e5772a…`). |
| `environment.json` vs `scenarios.json` vs manifests | OK | Versions agree (CPython 3.12.13, jupedsim 1.4.2, fdsreader 1.11.7, fdsvismap 0.3.2, numpy 2.4.4, shapely 2.1.2, scikit-image 0.26.0). `OMP_NUM_THREADS=4` in `environment.json` equals the manifests' `env`. `benchmark.py` `COMMIT`/`LOCK_SHA256` equal the frozen values. Stale pins elsewhere: IV4. |
| Data availability, 10/10 | OK, independently re-run | `python3 -I verify_stage.py S <scratch>/stage_check.json`: 10/10 OK, output byte-identical (after key sort) to `results/stage_verification_v2.json`. |
| Hashes reproducible from sciebo | OK, spot sample | For each of the 5 sciebo FDS dirs (a047, t_junction, cmm, fed_incap_co_2000ppm, world100): the largest file, the `.smv`/`.fds` and 3 random files, hashed from sciebo and from the stage; sciebo = stage = `preflight/input_hashes.json` for 30/30 files. File lists of the live sciebo dirs equal the reference lists (no extra, no missing, pickles excluded). The 5 sciebo deck/config files (`config_gate`, `config_additive`, `geometry.wkt`, `deck_config_stream_east.json`, `deck_geometry.wkt`) equal `sciebo_files`. iso21/22: staged dirs equal `WT/assets/…` (`diff -rq`, ignoring pickles). |
| fdsreader cache label gone (D13) | Mechanism supported; labels partly survive | Code: `fdsreader_adapter.py:76-106` sets `ENABLE_CACHING=False` and redirects `_get_pickle_filename` into a temp dir for every open, so every open parses; the staged `.pickle` files (v1 leftovers, `S/fds/{a047…,t_junction…,cmm…}/*.pickle`) are never read. `benchmark.py` has no `--fds-cache`; `cache_label` of `g0v2b*`/`g0v2d*` carries only `vis`, opens, opener seconds. Surviving labels: IV3. |
| W3 relabel (no exploration under `no_known_exit=default_route`) | OK, code and outputs agree | `cognitive_map.py:69` `DEFAULT_NO_KNOWN_EXIT="default_route"`; `config_discovery.json` has no `no_known_exit` key (rg over assets and config: only code hits). `route_graph.py:4411-4432` calls `_decide_no_known_exit` when `rank_routes` is empty; `:4224-4260` returns `_decide_default_route` for that mode; `_decide_explore` is reached only for `explore`/`return`/`stay`. Outputs of `R/g0v2b_W3_…124620`: `rh.csv` reasons `default_route` 150, `learned_exit` 10, `smoke_reroute` 2, `initial` 1; `exit.csv` 150 rows, `exit_in_map` False 138 / True 12; counters `explore=wander=frontier=wander_calls` absent/0. |
| Six issues: mechanism, workload, nonzero counter | OK (with IV1) | See the pairing table below. |
| #241 "fdsvismap 0.3.2 already fixed it" | Half true | Source `WT/.venv/…/fdsvismap/FDSVisMap.py`: `_get_slice_frame` (`:621-640`) calls `slc.to_global()` once for all required time steps and keeps float32 frames; `_get_mean_extco_array_at_time` (`:698-720`) uses `np.add.reduceat`. That removes the two costs in the issue text (per-call `to_global`, per-cell `np.sum` loop; issue options 3 and, in effect, 2). Still present at `8f7d29a2`: `_vis_metre_array` (`visibility.py:541-565`) calls `_get_visibility_array` a second time for every (t, wp) (issue body, first point). W3 counters `get_visibility_array_calls = get_mean_extco_array_calls = get_extco_array_calls = 1806 = 2×301×3`; `slice_read_lazy` occurs once (0.0127 s, `events.vismap_build`). The issue stays open for the second pass and dense storage. |
| #236 "every frame identical" | Not refuted, not confirmed as the model claims | `preflight/fed_incap_co_2000ppm.json`: soot extinction at 1.5 m ranges 0.9992793–0.9992923 over 1001 frames (spread 1.3e-5 /m). So "10 of 10 distinct" (byte equality) is float noise on a physically constant field. See IV8. |
| No double counting; denominators | Partly | Activation table percentages carry denominators (agent-steps). One is ambiguous: "98.8 % served from the pass cache" is `_reevaluate:2282` only (192 588 of 194 982); the `:2340` calls are 100 % hits. Optional (OV5). |
| Comparison design: every comparison labelled | OK, with fixes | W1r: separate case key, label "end-to-end, different workload (world100, WarpDriver), cap 250 s; never pooled with W1"; `analyse.py` GROUP contains `case`, `commit`, `comparison_label`, so W1r cannot pool with W1. Fixture (`W4_flow_saturated`) and V-build are labelled mechanism/kernel, not throughput, in `scenarios.json`, `benchmark.py` and `plan.md` D15/D16. Labels in `benchmark.py` CASES lag D14 for W3/W3b: IV4. |
| Derived decks, flat JSON diff vs base | OK | `<scratch>/fdiff.py` (flattens both JSONs, prints differing leaves). `scenarios/w1r_cap250/config_stream_east_cap250.json` vs `S/decks/world100_evac_4exits/deck_config_stream_east.json`: exactly one leaf, `simulationParams.max_simulation_time` 330.0 → 250; geometry byte-identical (sha `e99a07d6…`); base deck sha `fc50f2b8…` = sciebo. `scenarios/w4_flow_saturated/config_flow_saturated.json` vs `WT/assets/t_junction/config_discovery.json` (sha `f55444ae…`): `max_simulation_time` 300→200; `jps-distributions_0`: `number` 200→300, `flow_end_time` 400→60, `familiarity` discovery→full; new `jps-distributions_1` (150 agents, same 28 m² polygon, `use_flow_spawning` false, `use_premovement` true, constant 100 s, full); `journey_1` + 3 transitions + `waypoint_routing` copied. Flow distribution `use_premovement` stays false (amendment applied). sha `982c50ac…` equals `scenarios.json`; geometry equals `assets/t_junction/geometry.wkt` (`a7610c86…`). `make_derived.py` vs `make_derived.py.v2b`: only the premovement move and `make_w1r_cap250`. |
| `scenarios.json` edits limited to the model's A4 table | OK | `fdiff.py` of `S/tmp/scenarios_pre_v2c.json` vs current: changes only under `target`, `global_rules`, `workloads.{W1,W2,W3,W4.fixtures,W1r}`, `equivalence`, `kernel_experiments`, `preflight_evidence`; vs `scenarios_pre_v2d.json`: exactly the 3 hash entries + 1 note + path text. |
| Harness/instrument diffs limited to the listed ones | OK | `benchmark.py` vs `benchmark.py.v2pre`: cache/pickle logic removed, cases `W1r` and `W4_flow_saturated`, `PYFDS_PERF_DETAIL`. `perf_counters.py` current sha `f8ccf893…` = `g0v2d2` manifests (the earlier `g0v2d` runs carry `09455267…`; the counter added in between is `add_agent_position_refusals`). |
| Equivalence contract declared before data and matches files produced | OK | `model_handoff_g0_v2.md` §3 (13 items) predates any G1 datum (no measured run exists). Against `S/runs/g0v2b_W3_O_study_det_s42_rep1_20261014T124620`: `exit.csv` columns = contract item 3 (with `exit_in_map`); `rh.csv` = item 4; `rc.csv` 24 columns = item 5; `fed.csv` has the item-6 additions (`fic`, `fic_speed_factor`, `incapacitation_cause`, `heat_*`) plus `in_fds_domain` (not named, harmless); `traj.manifest.json` keys include `outcome{status,end_reason,agents_remaining,agents_not_spawned}`, `fds_coverage`, `fds_outside`, `git_dirty`, `agent_seeding`; `vis.npz` keys and `meta.format = 6` = item 11. Item 10's "Looks from a node point…" line appears in no stdout/stderr of any W3 run (rg), consistent with D14 (no looks without explore); OV6. |
| Determinism and plain-vs-instrumented (cheap, untimed) | One point, positive | `compare.py` on the existing pairs `g0v2_{W1,W2,W3}_*_ctr` vs `g0v2b_*_det` and the two fixture runs: all items "equal" (trajectory repr-v1, spawn/removal frames, exit/rh/rc/fed CSV, agent scalars, vismap arrays); item 12 absent for W3 (named gap). Plus my own plain `run.py`, no instrumentation, W3b arm B (command of the `W3b_cmm` case, `PYTHONHASHSEED=0`, outputs in `<scratch>/qa_w3b/r{1,2}`): two runs, trajectory hash `28e59c8b780b` = the `g0v2b` detail run's `trajectory_hash_repr_v1`, `exit.csv`, `rh.csv` byte-equal, `vis.npz` arrays all `array_equal`, `meta` equal except `fds_dir`, `format` 6. Worktree clean afterwards. This is not the G1 determinism gate (host loaded, W3b only, 1.4 s). |
| W1 coupled, horizon | OK, criterion needs a definition | Counters: 40 000 iterations, 3 259 925 agent-steps, 32 497 reroute evaluations, 172 switches, sampler/`read_cells` nonzero, FED rows 32 697. Horizon: model §1.4c asks for "the latest anticipated sample bound from the rc CSV, < 481.1 s". Taken literally (`time_s + travel_time_s`, the smoke-slowed time) the maximum is 825.7 s; that is the wrong quantity. The foresight clock uses the unimpeded `base_speed_m_per_s` (`route_graph.py:1340-1352`, `_foresight_clock` `speed=base_speed`). Recomputed as `time_s + path_length_m / base_speed`: W1 430.6 s < 481.1 s (base 1.0), W3 56.8 s < 301.2 s (base 1.3). Independently, no "Route foresight reaches beyond" warning in the W1, W3 or W3b stderr. Both agree. See IV7 for W1r. |
| `analyse.py` | Runs; not a G1 blocker | Copy run in scratch with `results/raw` symlinked (`<scratch>/an`, `python3 -I analyse.py --include-dev`): 22 rows, 19 groups, no exception; 11 rows are `8f7d29a2`. Columns `reroute_evaluations`, `sign_queries`, `agent_steps` filled for counters runs. Gaps: IV2, OV3. The engineer's note "only syntax-checked" is out of date as a risk: it runs. |
| `compare.py` | Runs; its gaps block G1 acceptance, not G1 runs | Section "G1 blocking analysis" below. |
| Resource limits, stop rules, exclusive slot | PARTIAL | v1 caps are "adopted unchanged" by reference (`plan.md` lines 41-48); the v2 section (lines 85-119) does not restate them or add stop rules for W1r, the fixture or V-build: IV9. `benchmark.py check` now: `ok` False, load1 7.9, foreign processes at 89–100 % CPU (`plugin-container`, `duetexpertd`, two `jupedsim-network-station` pythons). No exclusive slot exists at the time of this review and none is agreed for G3. No `g1_all` process is running (`ps`); `results/blocks/g1_status.tsv` still holds only the v1 START line. |

### Six issues paired with an active mechanism (second check)

| Issue | Workload | Counter (run) | Verdict |
|---|---|---|---|
| #236 | W3, W3b (+V-build later) | W3: 1 smoke-aware build, `[301,3,53,121]`, 0.468 s, 300 of 301 distinct frames (`results/vbuild_distinct_W3.json`); W3b: 1 build, 121×2, **1 of 121** distinct (`vbuild_distinct_W3b.json`) | Active. Magnitude not on these decks (sub-second). Exact dedupe: nothing (W3), everything (W3b). |
| #241 | W3, W3b | `_get_visibility_array` 1 806 = 2×301×3 and 484 = 2×121×2 (`g0v2b_W3_…`, `g0v2b_W3b_…`); `vis_metre_array` 0.143 s vs `compute_all` 0.218 s incl. slice read 0.0127 s | Active for the second pass; the upstream part is fixed (above). |
| #242 | W1, W3, W3b, W1r | `sampler_sample_calls`, `read_cells_calls` 725 445 (W1), `line_parts` hits/misses | Active; attribution defective: IV1. |
| #243 | W1 (6 misses per 1 s pass: 2 394 misses ≈ 400 passes × 6), W3 (150 initial choices, no cache dict), W1r (120 × 368 edges, 44 160 misses, 0 hits) | `generate_candidates_*` by caller | Active. W1r is the only dense-graph case; its label and foresight-held share: IV7. |
| #739 | `w4_flow_saturated` only | `flow_spawns_deferred_steps` 5 602 (≥1 000), `crowds_agents_calls` 1 022 315, `add_agent_position_refusals` 1 022 179, `occupied_calls` 5 738; W1–W3b all 0 deferrals | Active on the fixture, inactive elsewhere, as stated. Same trajectory hash `ee23c36b…` in `g0v2d` and `g0v2d2`. |
| #429 | W1, W2, W3, W3b, W1r | `distance_to_polygon_calls` 468 333 / 331 735 / 452 290 / 32 228 / 77 663; code `direct_steering_runtime.py:133-141` builds a `shapely.Point` per call | Active; share of agent-steps is a call count, not a cost. |

### Blocking

None.

### Important (G1 entry conditions)

- **IV1. #242 caller attribution is wrong; the engineer's reading and the model's mechanism text both need correction (perf-engineer: counters; perf-model: `scenarios.json` W1 `expected_activation_g0v2b`, §2 #242 row).** The detail key for `SliceFieldSampler.sample` records two frames and stops at `fed.sample_inputs`. That function is reached from the per-agent FED update **and** from the route FED-rate path (`scenario.py:160 sample_fed_rate` → `fed.py:1092 sample_rate` → `sample_inputs`). The counts show the split is not what the handoff states ("dominant volume is gas-FED per agent"; "route FED-midpoint sampling does not appear in any run"):
  - W1 `R/g0v2b_W1_…124453`: per-agent smoke-speed samples 32 697 ≈ agent-steps × dt (3 259 925 × 0.01 = 32 599) = one per agent-second. `<fed.csv>` has 32 697 data rows. So per-agent FED is about 32.7 k per quantity, against **756 088** counted per quantity: about 4 % per agent, about 96 % route-side. 45 615 distinct (x, y) against 32.7 k agent-ticks also says the route population is mostly repeated points.
  - Separately, `_polyline_stats` calls `sample` 160 814 times on 4 distinct points (zero-length segments or one-point lists, `route_graph.py:760-776`); the model's text said route extinction is not on this path any more. It is, for degenerate polylines, and it is the purest "static point" population in the matrix.
  - W3: per-agent samples 9 352 (fed.csv rows) of 11 831 calls per quantity (79 %), so W3 is mostly per-agent; the W1 distribution is the odd one.
  - Required: key the caller on the first frame outside `fed.py`/`fds_sampling.py` (as `_opener` does), report static vs moving points per caller from distinct (x, y), re-run `g0v2b`-style on W1 (untimed), and rewrite the W1 activation text. Until then no #242 share is quoted.
- **IV2. Harness records a wrong termination and no outcome for the #742 ending form (perf-engineer).** `benchmark.py` `SUMMARY_RE` only knows "finished" and "incomplete: time limit reached". The fixture ends with "Simulation incomplete: flow windows closed after 179.15 s (286/286 evacuated, 0 remaining, 164 not spawned)". Result in `R/g0v2d2_W4_…130102/manifest.json`: `outcome = {"summary_line": null}` and `termination = "incomplete_time_limit"` (derived from rc 2), while `traj.manifest.json` says `end_reason: flows_closed`. `summary.csv` rows for the fixture have empty evacuated/total. Fix: parse both forms and record `end_reason` from `traj.manifest.json`. Does not affect W1, W2, W3, W3b or W1r (time limit or completion). Consequence for the evidence: `compare.py` item 10 is "equal" for the fixture pair only because both summary lines are null; I report that pair as equivalent on trajectories and CSVs, not on item 10.
- **IV3. D13 labels survive in documents and old manifests (perf-engineer; coordinator for plan.md).** (a) `<P>/README.md` lines 123–125: "`fdsreader` is `first_use` … or `repeated_use` (pickle present)", "the first `Simulation()` open must be a `full_parse` or a `pickle_load` … otherwise `counters_agree` is false", "fdsreader caches only the first open per process"; this contradicts the harness and the adapter. Also README line 152 "checks 12 items" while the contract has 13. (b) `instrument/perf_counters.py` docstring lines 11–12 and the `kind: pickle_load|full_parse`/`pickle_present_at_open` records still describe the dropped state (observational, harmless, but a reader will take them as a state). (c) `plan.md` line 35 (v1 "Cache states (I1): first use = no `.pickle` in the stage…") and the top table (v0.2.0 commit, `wt6`, 8 dirs, "G0 status PASS", "Status: G0 submitted") are not marked superseded; add a banner. (d) `R/g0v2_W1_…122834` and `R/g0v2_W3_…122943` carry `cache_label.fdsreader = repeated_use`, `counters_agree = false`; `analyse.py` does not export these fields, so no table is affected. Mark the runs superseded in a note; do not delete them. (e) The stage still holds three v1 `.pickle` files; unused, but `plan.md` says "pickles excluded".
- **IV4. Stale labels and pins (perf-engineer).** `benchmark.py` CASES `W3` label "time-limited, incomplete (300 s); #91 applies" goes into every W3 manifest, contradicting D14 (#91 closed; "sign legibility in smoke under default_route; no exploration"); `W3b_cmm` label "second visibility case, 120 s" omits its D14 role as the exact-dedupe case. `preflight/input_hashes.json`: `commit` is `3ef4ea75` and 4 of 24 `repo_files` differ from `8f7d29a2` (`run.py`, `uv.lock`, `pyproject.toml`, `scripts/ab_trajectories.py`; the other 20 configs, geometries and iso FDS files are identical); `preflight/hash_inputs.py` `COMMIT` is v0.2.0. The staged data hashes are unaffected (checked above).
- **IV5. G1 driver does not cover the v2 question and cannot enforce the determinism gate (perf-engineer, coordinator).** (a) `g1_all.sh` has no block for `W1r`, `W4_flow_saturated` or V-build. (b) V-build exists only as `vbuild.py`: no manifest, no slot check, no host monitor, no fresh-process repetitions, no commit/lock record; it always installs `perf_counters` ("method: instrumented (stage hooks), diagnostic"), so its totals are instrumented; the plan's "5 repetitions, median and IQR, exclusive slot" has no runner, and an uninstrumented total is missing. Also `n`: engineer says 1000, model and `scenarios.json` say 1001 (the list has 1001 points; n = 1000 would drop the last). (c) Every counter that backs the six pairings except the sign/vismap ones comes from `--instrument detail`; `g1_all.sh` measures overhead only for `none,counters`, never for `detail` (its own header says "diagnostic-only until measured"). Add a `none,detail` overhead/equivalence block on W1 (and W1r if used). (d) The pytest block lists 19 files; `scenarios.json` and the engineer's 857-passed run use 26 (adds `test_route_grid_sampling`, `test_foresight_arrival_time`, `test_flow_spawn_spacing`, `test_flow_window_end`, `test_fdsreader_adapter`, `test_fds_read_only`, `test_fdsvismap_adapter`). (e) The driver runs `compare.py` only after all timed blocks (step 9), so a failed determinism gate cannot stop the driver. Run G1det and compare it (with the fixed `compare.py`) before the rest, or add a gate. (f) `results/blocks/g1_status.tsv` will append v2 lines under the v1 START; start a new status file. (g) Plain timed runs have no counters, so `agent_steps` is empty for baselines in `analyse.py`; join it from the matching deterministic counters run (same case and seed) and say so.
- **IV6. `compare.py` gaps (perf-engineer), required before any G1 equivalence verdict is accepted; they do not stop G1 runs from being taken.** Confirmed by reading and by running: `APP_FIELDS` omits `fds_outside` and `git_dirty` (contract item 9); `log_facts` looks for "Route switches: N", which the CLI no longer prints, so both sides are None; the "Looks from a node point" line (item 10) is never compared; item 11 compares `meta` equality but not that `format` is 6; item 13 needs `--capture-result` (named gap, fine); item 10 is vacuous where the summary line is null (IV2). The raw outputs keep everything, so the data can be compared after the fact. Gate decision: they do **not** block starting G1 runs; they **do** block accepting G1 timings, because the model agent accepts equivalence from this script. Order G1det first.
- **IV7. W1r label and foresight share (perf-model).** `w1r_cap250` is a different movement model (WarpDriver) on a different FDS output; the 250 s cap equals the FDS end (guard 252 s). The engineer reports "one #666 warning". The warning is logged once per run, which understates the effect: with the model's own bound (`time_s + path_length_m/1.3`, base from the deck's `RouteCostConfig` default, assumption) 812 of 9 856 route-cost rows (8.2 %), from t = 208 s, price route segments at the held last frame. Label W1r "foresight held at the last FDS frame (#666) for 8.2 % of route-cost rows" wherever its #242/#243 volumes are quoted, and state that its counts are magnitudes of mechanism volume, not a timing claim. Decide whether W1r enters G1 at all (coordinator, D17/D19).
- **IV8. Wording of #241/#236/D20 in the report (perf-model; coordinator for the issue numbers).** (a) Say "#241 half fixed upstream", not "fixed": the per-call `to_global` and per-cell loop are gone (source above), the second pass and dense storage remain. (b) D20 says the revision difference explains "most of the ~70 min". The issue's own figure is 0.862 s/frame; × 1001 frames ≈ 14 min, not 70, and the n=10 trial (0.045 s/time point) is a different revision. The reconciliation is a source reading, not a measurement at the old revision. Retire both issue numbers as "measured at another revision (`6e70313`, fdsvismap `64d9aa7`), not reconciled". (c) "The trial refutes 'every frame is identical'" over-reads byte-inequality: extinction spans 1.3e-5 /m over the whole run (preflight). Write "nearly constant (spread 1.3e-5 /m), not bit-identical; exact dedupe removes nothing; a tolerance dedupe is a behaviour change and is not measured as an optimisation". The consecutive-frame statistic in `vbuild.py` is the right instrument; it has run only on W3b (all identical).
- **IV9. v2 resource limits and stop rules are not declared (coordinator).** `plan.md` v2 section adds decisions D11–D20 but no limits. State, before G1: that the v1 caps (300 s normal, 900 s profiled, 4/8 GB RSS, repetitions, 4 h hard cap → PARTIAL) apply; the cap for W1r (the dev run used `--timeout 1500`; G1 default is 300 s and the run takes about 21 s), the fixture (about 78 s) and V-build (900 s profiled); stop rules for the new pairings (zero counter where "active" is claimed; deferral < 1 000 steps on the fixture; V-build total over cap; horizon-warning count change). Budget: the matrix in `g1_all.sh` I estimate at about 1–1.2 h exclusive (W1 ≈ 50 s × ≈ 48 runs, scale400 ≈ 6 runs, W2/W3 minutes) plus about 15 min for W1r, fixture, V-build and the detail-overhead block: inside the 2–2.5 h plan and the 4 h cap. Estimate, not measured.

### Optional

- **OV1. Fixture rationale and expectation (perf-model).** `scenarios.json` and model A1 justify saturation by "2×0.15 m spacing discs (0.283 m² each, 42 m²) exceed the 28 m²". That disc has radius 0.30 m; two agents keep 0.30 m centre distance, i.e. discs of radius 0.15 m (0.071 m²). The run placed 150 + 136 = 286 agents in the 28 m², so the area does not saturate from t = 0: it fills to a random-placement limit and then defers (5 602 steps from t = 2.60 s). The stated expectation ("~6000 deferred, 300 not spawned") differed from the result (164 not spawned); acceptance (≥ 1 000 steps) is met. Correct the text; the amendment (flow `use_premovement` false) stands on its own reason (inert key).
- **OV2. Proof counter and attribution for #739 (perf-model, perf-engineer).** `_crowds_agents` returned true 0 times of 1 022 315 (by design for CFSM: `simulation_init.py:623-649` leaves refused positions to `add_agent`), so the proof counter should be `add_agent_position_refusals` or `flow_spawns_deferred_steps`. The handoff's "exception-driven, not the Python crowding check" is a call-count inference: seconds were not measured. Cost attribution (1.0 M gap computations vs 1.0 M caught `RuntimeError`s) belongs to G2.
- **OV3. `analyse.py` columns.** `fds_opens_by_opener` (dict) is not exported; `end_reason`, `flow_spawns_deferred` and the stage timers are not columns. Add when the first analysis needs them.
- **OV4. `tests/test_fds_read_only.py:73` is skipped ("needs an xdist worker")**, the one test that checks the D13 premise most directly (case folder untouched). The 857-passed run has zero FDS-dependent skips as claimed, but this skip means the D13 premise rests on `test_fdsreader_adapter.py` and my reading of the adapter. Run it once with the xdist option.
- **OV5. Denominator label.** "98.8 % served from the pass cache" (W1 `_generate_candidates`) is `_reevaluate:2282` only; with `:2340` and the initial pass the figure is 388 764 of 391 164 edge evaluations (99.4 %).
- **OV6. Contract item 10 names a log line that no W3 run prints** ("Looks from a node point before a patrol"); keep it as "compared if present".
- **OV7. Fixture and G0 runs on a loaded host.** All `g0v2*` timings (wall 20–78 s) are indicative only and must not be quoted; the engineer states this. Counters are deterministic quantities (two fixture runs give identical counts and trajectory hash `ee23c36b…`).

### G1 blocking analysis (the question on `analyse.py`/`compare.py`)

- **Block starting G1 runs: no.** Every run keeps its CSVs, SQLite, npz and manifest; `analyse.py` ran on all manifests, `compare.py` ran on four pairs.
- **Block accepting G1 results: `compare.py` yes (IV6), the harness outcome parse for flows_closed endings yes for the fixture only (IV2), `analyse.py` no (OV3, IV5g).**

### What the other owners must check next

- **perf-engineer:** IV1 (re-key the sampler counter; re-run W1 and W3 detail untimed and compare outputs to the existing `g0v2b` runs), IV2, IV3 (README), IV4, IV5, IV6.
- **perf-model:** IV1 (activation text), IV7, IV8, OV1, OV2; confirm the horizon criterion as `time_s + path_length_m / base_speed` and replace the rc-CSV wording.
- **Coordinator:** IV9, IV3(c), IV7 (W1r in or out), IV8 (issue numbers retired as another revision), the exclusive slot (below).

### Handoff

**Inputs/commit.** pyFDS-Evac `8f7d29a2e056db46183e8cccabce338c398606a1` in `WT` (read-only, clean), lock `7f64a58d…`; profiling package at `<P>` as of 2026-10-14 15:03 local (`plan.md` D11–D20, `model_handoff_g0_v2.md` incl. v2c, `engineer_handoff_g0_v2.md` §G0 v2/v2b/v2c, `scenarios.json` `7fa5a1ad…`, `benchmark.py` `0877d010…`, `perf_counters.py` `f8ccf893…`, `compare.py` `0fd3a6f2…`, `analyse.py` `981b7e31…`, `vbuild.py` `6f757899…`); sciebo reference data (read only); issues #236, #241, #242, #243, #739 read with `gh issue view`.

**Files produced.** This section of `<P>/review.md` only. Scratch, outside the package: `<scratch>/fdiff.py`, `<scratch>/stage_check.json`, `<scratch>/an/` (copy of `analyse.py`, symlinked `results/raw`), `<scratch>/qa_w3b/` (two plain W3b runs), `<scratch>/review.md.before` (copy of this file before the append). Nothing in the package, the worktree or `S` was changed (`<P>/__pycache__` still holds only the 2026-10-02 `traj_hash` pyc; `git status` of `WT` empty after the W3b runs).

**Commands executed.** `git -C WT rev-parse/status`; `shasum -a 256` of lock, pyproject, run.py, derived decks, scripts; `python3 -I verify_stage.py S <scratch>/stage_check.json`; a Python script hashing 30 FDS files from sciebo and the stage and the 5 sciebo deck files against `preflight/input_hashes.json`; `diff -rq` of iso dirs; `python3 <scratch>/fdiff.py A B` for the derived decks and the two `scenarios.json` backups; `diff` of `perf_counters.py`, `make_derived.py`, `benchmark.py` against their backups; `python3 -I analyse.py --include-dev` in `<scratch>/an`; `WT/.venv/bin/python -B compare.py A B` for four pairs; `rg` over code, docs, logs and manifests; `gh issue view 236/241/242/243/739`; csv arithmetic on `rc.csv`, `fed.csv`, `rh.csv`, `exit.csv` of `S/runs/g0v2b_*` and `g0v2d_W1r_*`; `python3 -B benchmark.py check`; two plain `run.py` W3b runs (about 1.5 s each, `PYTHONDONTWRITEBYTECODE=1`) with trajectory/CSV/npz comparison. No timed measurement; no run longer than a few seconds.

**Observations.** (1) The comparison design and data availability are sound: commit, lock, stage (10/10, sciebo spot sample 30/30) and both derived decks are exactly as declared. (2) All six issues have an active mechanism and nonzero counter on a named workload (#739 only on `w4_flow_saturated`), but the #242 split is defective (IV1) and W1r's volumes come from a run whose foresight is held for 8 % of rows (IV7). (3) The W3 relabel is supported by code and outputs. (4) fdsvismap 0.3.2 fixes about half of #241. (5) The equivalence contract matches the files produced; the tooling that checks it lags (IV6, IV2). (6) A plain `run.py` and the detail-instrumented run of W3b are bit-identical in all compared outputs, twice.

**Uncertainties.** The W1r base speed 1.3 behind the 8.2 % is the deck default, not read from a manifest. The sciebo check is a sample (30 files of 558); the full staged tree equals the reference list. The W3b equivalence point is one small, clear-air case on a loaded host, not the determinism gate and not evidence about W1. I did not run `make_derived.py` (it writes into the package) or any W1/W3 run. The explanation of why `rc.csv` `travel_time_s` is much larger than the foresight clock horizon rests on `route_graph.py:1340-1352` and the absence of the warning, not on an extra run. D20's revision hypothesis was not tested at fdsvismap `64d9aa7`.

**What the coordinator must decide.** (1) Accept G0 v2 = PASS with IV1–IV9 as entry conditions, and the order: fix IV2/IV6, then G1det with `compare.py`, then the rest. (2) The exclusive slot for G1 and, separately, for my G3 reproduction (not agreed; the machine is loaded now; the maintainer must close apps, D10). (3) Whether W1r enters G1 given IV7, and in what words. (4) That the #236/#241 issue figures are retired as "another revision, not reconciled" and #241 is reported as half fixed. (5) The v2 limits and stop rules (IV9), and whether V-build gets a harness runner (IV5b) or is run as an unmanifested diagnostic with that label.

### G0 v2 re-check

Reviewer: perf-qa. Date: 2026-10-14, after the closures of IV1–IV9 (engineer `engineer_handoff_g0_v2.md` §G0 v2d and v2e; perf-model `model_handoff_g0_v2.md` v2d; coordinator `plan.md` D21–D24 and banner). Read-only; no timed run, no simulation. Files now: `benchmark.py` `43a1e0b0…`, `compare.py` `7852a6ff…`, `g1_all.sh` `92e8c906…`, `perf_counters.py` `0ac2e2b5…`, `vbuild.py` `fd5e11fc…`, `vbuild_bench.py` `a67b7b94…`, `scenarios.json` `5ad82489…` (v2e), `preflight/input_hashes.json` `583580d5…`. Backups used for diffs: `/Users/chraibi/profiling-stage/tmp/*.v2d_pre`. Worktree `8f7d29a2` still clean.

**G1 entry verdict: G1 may start when the exclusive slot opens.** No IV is open and the closures broke nothing I could find; the notes below are conditions on how the first blocks are read, not reasons to wait. The slot itself is not open: `benchmark.py check` just now returned `ok` False.

| IV | State | Evidence |
|---|---|---|
| IV1 #242 split | Closed | `R/g0v2f_W1_O_study_det_s1_rep1_20261014T132114/counters.json`: `sampler_sample_by_side` agent 32 697 per quantity (CO, CO2, O2, extinction); route 723 391 per gas quantity and 160 814 extinction. Total 2 461 775 = 130 788 + 2 330 987 (route 94.7 %; gas 95.7 %). Equals my arithmetic (fed.csv 32 697 rows). Same iterations, agent-steps, switches, `read_cells`, `distance_to_polygon` and trajectory hash `c6e61a8d…` as `g0v2b_W1`. `scenarios.json` W1 text and model v2d addendum withdraw the old sentence. Residual: W3 not re-run with the new key (stated by the engineer); the side rule is a substring test on a five-frame chain; seed 1 only. Call counts, not time shares. |
| IV2 flows_closed | Closed | `parse_summary` run by me on the four real summary lines: the flows_closed line gives `end_reason` flows_closed, 286/286, 164 not spawned; time-limit and finished lines unchanged. `R/g0v2f_W4_…132219/manifest.json`: `termination` flows_closed, full `outcome`. Old `g0v2d*` fixture manifests keep null outcome, so `compare.py` of old vs new fixture runs gives item 10 DIFFERENT (correct detection, not a regression; do not pair old with new). |
| IV3 D13 labels | Closed | README lines 123–125 now state no fdsreader cache state; `perf_counters.py` docstring updated; the two early manifests carry `status_label: SUPERSEDED_LABEL` with a note (all other keys untouched); `find S/fds -name '*.pickle'` = 0 and `verify_stage.py` re-run 10/10 (my run, scratch output); `plan.md` has the superseded banner. README line 125 keeps the vismap `first_use`/`repeated_use`/`noflag` labels, which are the legitimate ones. |
| IV4 labels and pins | Closed | `CASES` W3/W3b labels match D14. `input_hashes.json`: `commit` 8f7d29a2; all 24 `repo_files` equal the worktree; against `input_hashes.v2d_pre.json` only `run.py`, `uv.lock`, `pyproject.toml`, `ab_trajectories.py` changed in `repo_files`, `repo_dirs` and `sciebo_files` identical, `fds_dirs` changed only for the three v1 dirs (pickle entry removed), v2 entries (fed_incap `09c76e3d`, world100 `1a3c577c`) carried over. `hash_inputs.py` alone no longer reproduces the v2 entries (engineer's own caveat). |
| IV5 `g1_all.sh` | Closed as written; unexecuted | `bash -n` OK. Diff vs `g1_all.sh.v2d_pre`: `gate G1det W1/W3` directly after the two `G1det` blocks, `exit 1` on missing runs, non-equivalent verdict or failed negative control; blocks `G1w1r` (300 s), `G1flow`, `vblock G1vbuild --n 1001`, `G1ovhD` (`none,counters,detail`, accepted by the `--instrument` check at `benchmark.py:704`); 26-file pytest list; old end-of-script G1det loop removed; status file `g1v2_status.tsv`. The gate's run-id glob (`G1det_W1_*`, `G1det_W3_*`, the latter containing `_cap_`) matches the harness naming. |
| IV6 `compare.py` | Closed | Diff: `APP_FIELDS` + `fds_outside`, `git_dirty`; dead "Route switches" regex removed; `Looks from a node point…` parsed from stdout and stderr; new item `11b_vismap_format_is_6`. My runs (no `--out`): `g0v2_W3` ctr vs `g0v2b_W3` det and `g0v2b_W1` vs `g0v2f_W1` both equivalent, with 11/11b equal on W3. Engineer's `g0v2e_negative_control_W3b.json`: identity equivalent, one byte of `exit.csv` and one ulp both detected, PASS. Untested by anyone: a wrong npz format and a run that prints the Looks line. I did not run `--negative-control` myself because it writes a temp directory inside the package. |
| IV7 W1r | Closed | Label and 8.2 % confounder text in `scenarios.json` W1r; counters independent of held foresight listed; my bounds reproduced by the model (430.6 s, 812 of 9 856). |
| IV8 wording | Closed | `reconciliation_D20` and v2d text: "another revision, not reconciled", 14 min not 70, "half fixed", "nearly constant 1.3e-5 /m", n = 1001. Residual: the A1 paragraph of the model handoff still carries the 0.283 m² saturation arithmetic (OV1); `scenarios.json` no longer does. |
| IV9 limits | Closed | `scenarios.json` `resource_limits` (W1r 300 s/4 GB, fixture 120 s/2 GB, V-build 300/900 s/8 GB, stop rules), D24 in `plan.md`; `g1_all.sh` timeouts and `vbuild_bench.py` limits agree. |

**Notes (no closure broken; read these before the first block):**
1. `scenarios.json` says the fixture runs "1 warm-up + 5"; `g1_all.sh` `G1flow` uses `--warmup 1 --reps 3`. Pick one (perf-engineer/perf-model).
2. The horizon criterion (IV6/IV7) is defined but not automated: no script computes `max(bound)`, the held-foresight share or the #666 warning count, and the W1r stop rule (warning count 1, share 8.2 %) depends on it. Someone must run it per W1, W3, W3b and W1r run before the block is accepted (perf-model to specify, perf-engineer to script, or QA does it at G1 review).
3. `g1_all.sh`, `gate`, `vblock` and `vbuild_bench.py` at n = 1001 have never run end to end. A first failure there is a harness fault, not a result. `__pycache__/benchmark.cpython-312.pyc` appeared in the package from the engineer's `vbuild_bench` import (timestamp 15:24, before my commands); harmless, but not source.
4. Detail-counter overhead remains unmeasured until `G1ovhD` runs; until then detail-derived numbers (#242, #243, #429, #739 volumes) are diagnostic.
5. Still open from my optional list: OV1 (A1 text), OV2 (#739 cost attribution is G2), OV3, OV4 (`test_fds_read_only.py:73` skipped), OV5.

**Inputs/commit.** `8f7d29a2`, lock `7f64a58d…`; files and hashes above. **Files produced.** This subsection of `<P>/review.md`; scratch `<scratch>/stage2.json`. **Commands executed.** `shasum`, `bash -n g1_all.sh`, `diff` of `benchmark.py`, `compare.py`, `g1_all.sh` against the `.v2d_pre` backups, `diff` of `scenarios.json` keys against `scenarios_pre_v2d.json` (changes only under keys the perf-model lists), JSON checks of counters and manifests, `parse_summary` on four strings, `compare.py` on three pairs (no output file), `verify_stage.py` to scratch, `find … -name '*.pickle'`, `benchmark.py check`. **Uncertainties.** The gate and runners are verified by reading, not execution; IV1 rests on one untimed seed-1 run; the sciebo hash sample from the earlier section is not repeated. **Coordinator decides:** open the exclusive slot (maintainer closes apps, D10); resolve notes 1–2 before or during the G1det block; agree the G3 reproduction slot.

---

## G1

Reviewer: perf-qa. Date: 2026-10-16. Read-only accounting check of the G1 record at `8f7d29a2` (no run, no reproduction; G3 slot separate, D28). Inputs: `results/blocks/g1v2_status.tsv`, `g1_all.sh`, `g1_resume{,2,3}.sh`, `results/raw/G1*/manifest.json` (149 runs), `results/summary.csv` (179 rows), `results/summary_groups.csv` (24 groups), `results/equivalence/G1*.json`, `plan.md` D30 and "G1 run record". File hashes at check time: `benchmark.py` `ac2c3c21…`, `compare.py` `7852a6ff…` (as reviewed), `analyse.py` `e362b3ee…` (changed since my re-check: adds `horizon.json` columns only), `perf_counters.py` `0ac2e2b5…`, `scenarios.json` `5ad82489…`.

**Status: PARTIAL.** Accounting is sound: block set, run counts, warm-up exclusion, cache states, interleaving and the harness changes check out. PARTIAL because (a) no W1-family group has an admissible statistic (every group 100 % flagged, so no W1, W1_n100, W1_n400, W1r headline number exists yet), and (b) the items under 5 and the `analyse.py` points under 2 must be fixed or labelled before anything is quoted. No evidence of an invalid or mislabelled run was found.

### 1. Block set and counts

- All 22 blocks of `g1_all.sh` appear exactly once in the status file with rc=0, spread over three drivers as stated (`G1det` W1 in `g1_all.sh`, W3 in `g1_resume.sh`; `G1base` in `g1_resume2.sh`; rest `g1_resume3.sh`). No SKIPPED remains. `G1w4_extra` is a record directory (log, status), not a run. The only other directories without `manifest.json` are the pre-G1 ones already known (`g0_*`, `dev_counters_*`, `g0v2_W3_…122925`). No orphan G1 run from the failed attempts: the refused `G1seeds` call (rc=1, no run dir) and the skipped W3 call left nothing; `G1seeds` has exactly 8 runs.
- Runs per block (warm-up + measured) match the declared repetitions: G1base 1+5, G1seeds seeds 2,3 each 1+3, G1w2 1+5, G1w1r 1+5, G1flow 1+5, G1vbuild 1+5 plain and 1 instrumented diagnostic (`not_a_measurement`), G1w3first 0+3, G1w3rep/noflag 1+5, G1w3seeds 43,44 each 1+3, G1w3bfirst 0+3, G1w3brep 1+5, G1ovh and G1ovhW3 2×(1+5), G1ovhD 3×(1+5), G1out 3×(1+5), G1scale100/400 1+5, G1outchk 1, G1w4 1, G1det 2 W1 + 2 W3.
- Warm-ups: `analyse.py` skips `role == warmup`; group `n_runs` equals measured reps in every group (checked against the table above).
- Every G1 manifest: commit `8f7d29a2`, clean, `slot_before` and `host_during` present; `wall_s`/`cpu_s` present on all 149. `slot_after` is absent as a top-level key only for the 7 VBUILD manifests (it sits inside `host_during` there; schema difference of `vbuild_bench.py`, not a gap).
- Gaps: runs shorter than the 2 s sample period have `host_during.samples = []`: all W3b blocks (1.1–1.2 s), `G1w4` (1.0 s). Their flag rests on `slot_before`/`slot_after` only, so "0 contaminated" for `W3b repeated_use` and `W4_iso21` means "not observed during the run", not "clean". Label those groups.

### 2. Timing accounting

- Sources: `wall_s` = parent `perf_counter` around the child; `cpu_s` = user+sys of `/usr/bin/time -l` (equal to `time_real_s` within 0.01 s); instructions retired and RSS from the same file. Plain runs for baselines; counters and detail only in the overhead blocks. VBUILD plain reps are uninstrumented (`--plain --no-stats`).
- Cache states (from `cache_before`/`cache_after`, not requested): `G1w3first`/`G1w3bfirst` 3/3 `first_use` (absent before, present after); `G1w3rep`/`G1w3brep` 5/5 `repeated_use` with identical npz sha before and after (loaded, not rebuilt), the warm-up is the `first_use` build; `G1w3noflag` has no cache record (`noflag`); `G1ovhW3` counters runs show `load_hit` events and `counters_agree` True. `cache_before`/`cache_after` are empty by design for runs without a vismap cache (111 manifests).
- Interleaving, from `t_start_utc`: `G1ovh` and `G1ovhW3` N C N C … (ABAB) after N C warm-ups; `G1ovhD` N C D | D C N | N C D | D C N | N C D (ABBA) after three warm-ups; `G1out` cycles O_study, O_norc, O_min. As designed.
- Between-block offsets matter more than within-group spread. W1 plain O_study seed 1 wall medians: `G1base` 46.5 s, `G1ovh` 47.3, `G1ovhD` 47.3, `G1out` 47.5 (within-block range 0.2–1.7 s). A 1.5–2 % offset between blocks exceeds the within-block IQR. The pooled groups in `summary_groups.csv` mix blocks (see "analyse.py" below).
- Work is identical across W1 plain runs: instructions retired 794.1–795.0 ×10⁹ in all but one run (`G1base` rep 3, 799.0 ×10⁹, load1 2.4 before, wall−cpu 0.18 s); wall−cpu ≤ 0.06 s elsewhere. So the process was not preempted and did the same work; what remains unobserved is frequency, core type and cache/bandwidth effects of the daemons.
- `G1det` W1 rep 2 started at load1 7.56 (self-flagged `load1_before`); both W1 determinism runs are labelled `measured` with `comparison_label = determinism`. They are equivalence evidence only; keep them out of timing tables (they are in a separate group, n=2).

### 3. Harness changes during the run

- **D30 (`max_load1` 1.5 → 2.5).** It changes admission of a block, not what a run does or records; `flagged` per run still uses the same rule (`load1_before` flags at ≥ the *new* 2.5, so a few runs carry it). Bias risk: blocks now start while the maintainer's session and macOS services keep load at 1.5–2.5, which the old rule would have refused. `G1det` (hash `43a1e0b0`, threshold 1.5) and all other G1 blocks (hash `ac2c3c21`) therefore differ in the instrumentation sha only by that constant (diff against `benchmark.py.v2d_pre`: SLOT, the two labels, the flows-closed parse). I see no effect on a measured quantity, but the D30 load range (G1base load1_before 1.5–2.4) is part of the condition for every W1 number.
- **`g1_resume3.sh` retry and glob guard.** The retry re-invokes `benchmark.py run --exclusive` only on rc=1 with the message "exclusive slot check failed", i.e. before any run directory exists (5 `SLOT_RACE_RETRY` lines; no duplicate or partial run dirs found); the glob guard only skips an unmatched horizon check. Neither touches a running measurement. The difference `g1_all.sh` → `g1_resume3.sh` is exactly these lines plus the removed finished blocks (`diff`).
- **Exclusions from the three attempts:** none required. The first driver's `G1det` W1 pair (rc=0) and the W3 pair from the second driver are used as the determinism gate; both gates PASS in all three later START lines (re-run each time, same result). The refused `G1seeds` call produced no data.
- Inherited from before G1: the slot check runs once per block, not per run; per-run contamination is judged afterwards from `host_during`.

### 4. Contamination: independent position

Counts: 106 of 149 G1 manifests carry `contaminated` (136 of 179 in `summary.csv` including dev and G0 runs; the coordinator's 103/179 matches neither; use 106/149 for G1). All reasons are `foreign_heavy_*` (before, during or after) with a few `load1_before`; offenders: `mds_stores` 296 %, `mediaanalysisd` 259 %, `Podcasts`, `corespotlightd`, `hybridsearchd`, `duetexpertd`, `mobileassetd`. `ps` %CPU is a decaying average (known, O10).

Evidence in hand that bears on whether a flagged run is usable:
1. Not preempted: wall−cpu ≤ 0.06 s (0.1 %) on 24 of 25 flagged W1 baseline/overhead/out runs; same instructions retired (±0.03 %).
2. Flag insensitivity at 8 s: in W3 groups with both kinds, flagged and unflagged medians differ by ≤ 1.6 % (`G1w3rep` 7.81 vs 7.94 s; `G1ovhW3` plain 7.73 vs 7.81; `G1w3noflag` 8.19 vs 8.18). This does not transfer to 47 s W1 runs, which have no unflagged control.
3. Between-block offsets of 1.5–2 % (section 2) are the larger uncertainty.

Position: (a) `analyse.py`'s exclusion is the right default, because it is the rule declared before the data; keep it, but add a second table that includes flagged runs, labelled "flagged", with the reasons, so that all-flagged groups are not empty and nothing is silently dropped. (b) A D31 reclassification fitted now is post hoc (the spread is already seen). It is acceptable only if it is stated as post hoc, applied to every flagged run in every group (not W1 only), and uses run-level criteria that do not depend on the outcome of interest: wall−cpu ≤ 1 % of wall, instructions retired within 0.1 % of the group median, `slot_before` and `slot_after` observed, and offenders limited to the named background daemons. Even then, reported as "flagged, criteria met", with the between-block offset shown. (c) The independent evidence I would require is an anchor: rerun one W1 block (the `G1base` 1+5 on seed 1, ~5 min) with Spotlight off on `/System/Volumes/Data` (`mdutil -a -i off`), unflagged. If its median is within the flagged `G1base` range plus the block offset, the flagged W1 numbers may be reported as anchored; if not, rerun the headline blocks. A rerun of the other W1-family blocks is cheaper than a defended rule if the anchor disagrees. (d) A short flag is weaker than it looks for runs under 2 s (section 1).

### 5. Do not quote

- **O_min / O_norc / O_min_check "NOT equivalent" (`G1out_vs_G1base.json`, `G1outchk_vs_G1base.json`): not evidence of a changed computation.** The only differing item in all 13 pairs is `10_exit_summary_counts`, because `route_cost_samples` is printed only when `--output-route-cost-history` is given (O_study: 64,994; others: None). Everything else compared is equal: O_norc has trajectories, spawn/removal frames, exit, route history, FED and scalars equal; `O_min_check` has trajectories, frames, exit and scalars equal. `O_min` writes no SQLite, so its trajectories are "not compared" (6 pairs): O_min's equivalence is untested except by summary line and exit code; `O_min_check` is the nearest evidence. This is a comparator limitation (item 10 mixes a flag-dependent log line with the outcome), for perf-model and perf-engineer, not a finding about the code.
- **`G1det_W3` and every W3 "equivalent": cognitive-map state was not compared.** The two W3 determinism runs were launched with `--capture-result` (`perf_run.py`), the manifests point to `result_capture.json`, but the file does not exist in either run directory, so items 12/12b are "absent" and the named gap is printed. At this commit the capture hook (`core_pkg.run_scenario` replaced in `instrument/perf_run.py`) evidently does not reach the call path used by `run.py`. The gate PASS is therefore on trajectories and CSVs only. Say so wherever "determinism gate PASS" is quoted for W3; item 13 (`result.metrics`) is likewise never compared in G1.
- `G1ovh_W3.json`: 11 "equivalent" with the same gap. `G1ovh_W1.json` and `G1ovhD_W1.json`: equivalent on all compared items (counters and detail vs plain, 28 pairs), fine to quote as "outputs identical", not as "overhead < 5 %" (that is a timing statement from the contaminated runs).
- The `G1ovhD` combos label counters and detail runs both as `True`; the reference is an instrumented run, so "detail vs counters" is covered but not distinguished in the JSON.
- Do not quote `G1det_W1` rep 2 timing (load1 7.56).

### `analyse.py` / `summary_groups.csv` (for perf-engineer; none changes accounting)

1. Groups pool across blocks: "W1 O_study controlled-cost plain n=15" = `G1ovh` N + `G1ovhD` N + `G1out` O_study; "instrumented True n=15" mixes counters and detail. Add the block and the instrument level to the group key (already an open item).
2. Statistics are printed when clean n < 3: `W4_flow_saturated` n=5, 4 flagged → IQR 0.0 from one clean run; `W3b first_use` (2 clean), `VBUILD` (3 clean of 5), `W2` (4 of 5). Print n_clean and suppress or mark IQR for n_clean < 3.
3. V-build: 10.7 s per plain run at n = 1001 against ~50 s in the G0 trial: noted by the coordinator as open; not an accounting fault.

### Handoff

**Inputs/commit.** `8f7d29a2`, lock `7f64a58d…`, files above. **Files produced.** This section only; no scratch files beyond reads. **Commands executed.** Python over `results/raw/G1*/manifest.json`, `summary.csv`, `summary_groups.csv`, `results/equivalence/*.json`; `diff`/`shasum` of the driver scripts, `benchmark.py`, `analyse.py` against the backups; `ls`. No run, no write outside `review.md`. **Uncertainties.** Section 4 point 2 uses W3 only; the 1.5–2 % block offset could partly be real drift (thermal, load) or seed-independent cache state, which I cannot separate; the explanation for the missing `result_capture.json` is from reading `perf_run.py`, not from a test. **Coordinator decides:** D31 (post hoc rule with criteria above) versus the Spotlight-off anchor rerun; whether `analyse.py` gets the flagged-inclusive table before the report; how the W3 determinism gate is worded; and the G3 slot.

## G1b pass 2

Reviewer: perf-qa. Date: 2026-10-17. Read-only accounting and claims check of the G1b record at `8f7d29a2` (173 run manifests with prefix `G1b_`, three drivers). Inputs: `plan.md` (D10, D26, D27, D30, D31, G1b run records), `README.md` sections 3 to 7, `g1_all.sh`, `g1_resume4.sh`, `g1_resume5.sh`, `benchmark.py`, `analyse.py`, `results/blocks/g1b_status.tsv`, driver logs `g1_all_20261016T114431Z.log`, `g1_all_20261016T192523Z.log`, `g1_all_20261017T045138Z.log`, `results/blocks/analyse_G1b.txt`, `results/summary.csv`, `summary_groups.csv`, `summary_groups_all.csv`, `results/equivalence/G1b_*.json`, `results/raw/G1b_*/{manifest.json,time_l.txt,horizon.json}`; pass-1 `G1*` manifests for comparison. Derived numbers below come from a read-only Python pass over these files (no write outside this file). No run, no reproduction.

**Status: PARTIAL.** Run records, warm-up handling, cache labels, interleaving, equivalence and replacement blocks are sound, and all headline ratios (instrumentation overhead, output cost, scaling) are consistent with pass 1 and between independent designs. PARTIAL because (a) the reproduction of the primary baseline and one leading finding is **not run in this review, slot pending** (G3, D28), (b) 54 of 84 W1-family measured runs are flagged and the D31 rule is not yet decided or correctly implemented, so no W1-family number may be quoted without the labelling rule in section 3, and (c) the important items in section 6. No finding blocks G1b acceptance of the record as evidence. Two findings (section 6, items 1 and 2) block quoting W1-family numbers in `report.md` until fixed or labelled; items 3 to 9 are important and do not block quoting once the labels of items 1 and 2 are applied.

### 1. Cache-state and timing accounting

- **Block set.** 173 manifests: 22 blocks of `g1_all.sh` plus `G1b_ovhD2` and `G1b_scale400b`; `G1b_w4_extra` is a record directory without manifest (status, logs, pytest). Every manifest: commit `8f7d29a2`, worktree clean before and after (173/173), identical sha256 of `benchmark.py` (`58896794…`), `instrument/perf_counters.py` and `perf_run.py` in all three drivers, so the harness that made the runs did not change between drivers (only the driver scripts changed). No traceback in any `stderr.log`/`stdout.log`; no run directory without manifest.
- **Warm-up.** One untimed warm-up per variant/seed in every W1/W2/W1r/flow/W3 repeated/noflag/ovh/out/scale block (`role=warmup`, kept in `summary.csv`, skipped by `analyse.py`); 0 warm-up by design for `w3first`, `w3bfirst`, `outchk`, `w4`, `det`. Measured repetitions 5 (seeds 2,3 and W3 seeds 43,44: 3). Warm-up wall is not special (`G1b_base` warm-up 47.48 s vs reps 47.42 to 47.65), so no first-run effect remains in the reps.
- **Order.** `order()` in `benchmark.py`: `alternate` = ABAB (same order every rep), `abba` = reversed on odd reps. Verified from timestamps: `G1b_ovh`, `G1b_ovhW3` N,C,N,C ...; `G1b_ovhD`/`G1b_ovhD2` (abba, 3 variants) N,C,D | D,C,N | N,C,D | D,C,N | N,C,D. `G1b_out` is **not counterbalanced**: O_study, O_norc, O_min in this order in every rep (default `alternate`). The plan says ABAB for paired variants, so this follows the plan, but with three variants O_study is always first and O_min always last (see 4b). `abba` for `ovhD*` differs from the plan text (ABAB) but was accepted in pass 1; with 5 reps the three-variant abba is forward 3 times and reverse 2 times, balanced only approximately.
- **Cache states.** W1 has no application cache state (D13); fdsreader parses on every open. W3 vismap: `first_use` 3 reps without warm-up, `repeated_use` 1+5 with a warm-up that builds the npz, `noflag` in-memory build (wall: first 8.38, repeated 7.98, noflag 8.42 s, `G1b_w3first/w3rep/w3noflag`; pass 1 8.34/7.92/8.19). Labels come from observed `cache_before/after`. "First use" means the vismap npz only; the OS page cache is uncontrolled (a new process is not OS-cold): the first-use reps show no cold effect (range 0.09 %), but the report must say "page cache uncontrolled".
- **Sampling period.** `ps` every 2.0 s (`--monitor-s 2.0`, ~23 samples per 47 s W1 run, ~58 per 118 s N=400 run) plus a slot check before and after each run. `ps` %CPU is a decaying average, so a burst is smeared and a flag marks "a foreign process had a high recent average", not "was running during the run". Runs shorter than 2 s (W3b 1.1 s, W4 1.0 s) have zero samples (carried over from pass 1). The "after" check of run k and the "before" check of run k+1 are taken seconds apart, so one burst can flag two adjacent runs (optional).
- **Do flagged runs deviate from unflagged siblings beyond the pass-1 dispersion?** No. Pass-1 within-block ranges (all flagged, same host class): `G1base` 3.48 % (IQR 0.88 s), `G1w2` 3.29 %, `G1seeds` s2 2.66 %, `G1scale100` 2.24 %. In pass 2, mean(flagged) minus mean(clean) per group with at least one clean run is between -1.8 % and +2.2 %, signs mixed (`G1b_base` -0.13 %, `G1b_ovh` none -0.03 %, `G1b_out` O_norc +2.15 %, `G1b_out` O_study -0.55 %, `G1b_ovhD2` none -1.75 %, `G1b_scale400b` +1.03 % against one clean run). The largest, `G1b_out_W1_O_norc_s1_rep5` (+0.78 s), is a continuation of the within-block upward drift (36.04, 36.16, 36.38, 36.59, 37.07 s), flagged only by `foreign_heavy_before`. The run with the most heavy samples (`G1b_base` rep 1, `duetexpertd` 101 %, 9 of 23 samples) has wall 47.68 s against 47.61 and 47.65 s for the two clean reps (+0.1 %); rep 4 (`appstoreagent` 92 %, `PerfPowerServices` 143 % before and during) has the lowest wall of the block (47.42 s). Second check, independent of wall: instructions retired and cycles elapsed from `time_l.txt` are within 0.1 to 0.9 % across all W1 runs of a block whether flagged or not (for example `G1b_base` instructions 794.6 to 797.6 x10^9, cycles 179.0 to 179.9 x10^9; `wall - cpu` at most 0.06 s in every W1 block except `G1b_ovhD2` counters (0.16 s), `G1b_ovhD` (0.31 s) and the `G1b_det` pair (1.30 s)). The work is identical; only clock rate varies.
- **Positive control (the monitor works for sustained load).** `G1b_ovhD` (macOS update, `installd` up to 506 %, `appstoreagent` 99 % in 24 to 31 of ~30 samples, 18/18 flagged) has plain W1 at 50.26 s vs 47.53 s for `G1b_ovh` plain, +5.7 %, identical instructions (796.4 vs 794.7 x10^9) and a lower clock (cycles/wall 3.57 vs 3.77 GHz). Short bursts (`launchd`, one to two samples) do not show this; sustained installer/Spotlight load does.
- **Between-block offsets are clock-rate offsets, larger than within-block spread.** Plain W1 O_study, median wall (cycles / wall in GHz): `G1b_base` 47.61 s (3.775), `G1b_ovh` 47.53 (3.773), `G1b_out` 46.27 (3.875), `G1b_ovhD2` 45.68 (3.922), pass 1 `G1base` 46.51 (3.882), `G1out` 47.51 (3.774). Instructions and cycles are the same in all (instructions 794.5 to 796.4 x10^9, cycles 179.2 to 180.5 x10^9). So blocks 4 % apart in wall did the same work at a different effective clock (thermal/power state or the reboot; `kernel_task` and frequency are not observable, D10). Within-block drift is also clock-driven: `G1b_ovhD2` plain 44.31 to 46.00 s (+3.8 %), counters 45.24 to 47.34 s, at constant cycles. **Consequence:** absolute walls from different blocks must not be compared; every ratio below is within one block, with instructions/cycles as the clock-free second check.
- **Fault in the record.** OS version and boot time are not in the run manifests. `environment.json` (collected 2026-10-14) says macOS 27.0.1 build 26A434, `plan.md` says 27.0 before the 2026-10-16 update and 27.0.1 after the reboot. I cannot establish from the package which runs ran on which build. Needed: `sw_vers` and `sysctl kern.boottime` per manifest (or per block), or a statement that both builds are 26A434. Not blocking (the cross-driver determinism and work invariance below do not depend on it); important for the appendix provenance.

### 2. Replacement blocks and reference choice

- **ovhD to ovhD2 and scale400 to scale400b are sound as a procedure.** Both flagged blocks are kept untouched: `G1b_ovhD_*` (18 runs) manifests have `mtime` equal to the run end of driver 1 (last 12:45:00 UTC) and `G1b_scale400_*` (6 runs) equal to driver 2 end (last 21:06:34 UTC); no file inside them is newer than the block, `G1b_ovhD_W1.json` was written at the end of driver 1. The replacements have their own prefixes, so `first_id` and `compare.py --block` (`glob(f"{block}_*")`) cannot pick them up by accident: `^G1b_ovhD_W1_` does not match `G1b_ovhD2_W1_`, and the `G1b_ovh_` block does not match `ovhD`/`ovhW3` (11, 17, 17 pairs = block sizes minus the reference). `analyse.py` keys on block, so old and new blocks are never pooled (62 groups, `summary_groups.csv`).
- **Reasons for the replacement are not selection by outcome.** ovhD: sustained installer load, 18/18 flagged, positive-control evidence above. scale400: 6/6 flagged but by short Python bursts, which is **less** severe than ovhD; the wall range of scale400 (116.02 to 117.67 s) and scale400b (117.00 to 118.63 s) agree within 1.0 %, so the replacement neither improved nor changed the number (median 116.98 vs 118.18 s, clock 3.846 vs 3.806 GHz, instructions 2043.7 vs 2042.6 x10^9). The replacement is also not fastest-run selection: both blocks stay in `summary_groups_all.csv`. Report both, and state that scale400b is the headline only because 4 of 5 reps are flagged less than scale400's 5 of 5, not because it is faster (it is slower by 1 %).
- **`first_id` reference.** It returns the alphabetically first run of the block: for `G1b_ovh`, `G1b_ovhD`, `G1b_ovhD2` that is the counters `rep1` run (`..._ctr_s1_rep1`), not a plain one; for `outchk`/`out` it is `G1b_base_..._rep1` (plain, flagged, pre-reboot). Equality is transitive and flags do not matter for exact equality, so verdicts stand (ovhD2: 17/17 equal on every item W1 writes (items 1 to 6, 8 to 10, 10c; items 7, 11, 11b, 12, 12b are `absent` for W1) for none, counters, detail; ovh W1 11/11; out vs base: norc 6/6 incl. trajectories, 18/18 verdict "equivalent"). Two limits: (i) the out comparison crosses the reboot, which is a plus for determinism: trajectory hashes are `c6e61a8d1c` in `G1base`, `G1b_base`, `G1b_ovhD2`, `G1b_out` (study, norc), `G1b_outchk`; `32fe677f1f` (N=100) in `G1scale100`/`G1b_scale100`; `7af05dfbac` (N=400) in `G1scale400`, `G1b_scale400`, `G1b_scale400b`. (ii) The three drivers re-ran the determinism gates on the existing `G1b_det` runs (driver 1, before the update), so they did not re-establish determinism on the post-reboot host; the hash equality above does.
- **N=200 anchor for scaling is the weak point.** `g1_all.sh` states "N=200 is `${PASS}_base`", but `G1b_base` is a driver-1 block at a clock 4 % below driver 3 (section 1). The correct same-driver N=200 is `G1b_out` O_study (46.27 s, instructions 796.2 x10^9, same case/variant/seed, 5 reps) or `G1b_ovhD2` plain (45.68 s). Use one of those with `G1b_scale100` and `G1b_scale400b`; see 4c.

### 3. Contamination monitor: D31 classification and the clean/flagged split

- **Data available.** Each snapshot records `pid`, `ppid`, `pcpu`, executable path, per-sample timestamps (`t`), and `host_during.offenders_detail` has per path `max_pcpu`, `ppids`, `class`. Per-run burst length is derivable (number of samples with `foreign_heavy`, 2 s each). `summary.csv` carries only `contamination_reasons`, not offenders, classes or sample counts, so the reporting rule cannot be applied from the summary tables.
- **The classifier does not separate what it is meant to.** Rule (`benchmark.py` `offender_class`): `system_daemon` iff `ppid == 1` and path starts with `/System/`, `/usr/libexec/`, `/usr/sbin/`. Defects seen in the data: (i) **`launchd` itself (`/sbin/launchd`, ppid 0) is `user`**: 49 offender entries, the most frequent offender, 18 runs flagged by `launchd` alone, so the `user` class is dominated by the OS. (ii) **User apps under `/System/Applications` and `.appex` extensions are `system_daemon`**: `Podcasts` (107 % in `G1b_ovhD2_W1_O_study_s1_rep3`, three entries), `Finder`, `Siri AI`, `CalendarWidgetExtension`; the README says Podcasts must be closed. (iii) Genuine user-attributable offenders are classed `user` correctly but are rare and some are our own fault: `claude` (the coordinator session) 45 % in `G1b_det_W1_..._rep1`, 25 % in `G1b_seeds_W1_O_study_s2_rep1`; `spindump` 100 %, `pmset` 90 %, `claude` in `G1b_scale400` (host inspection during a block); `python` from `~/.hermes` 57 to 88 % in `scale400` rep 3 to 5; WhatsApp `ServiceExtension` 23 % (`ovhD2` plain rep 3), `DropboxFileProvider` (`ovh` warm-up): user apps were not all closed in driver 3 either. (iv) The class is "every observed instance", but only the maximum is stored, not duration; classification does not enter the verdict (by design).
- **Residual `launchd` bursts after the respawn loop was stopped are unexplained.** `launchd` is an offender in 14 driver-3 runs (`G1b_out` 5, `G1b_ovhD2` 4, `G1b_scale400b` 4, `G1b_scale100` 1) although `g1_resume5.sh` refused to start on a KeepAlive respawn loop and no `hermes` process appears in driver 3. `launchctl list` still shows non-zero exits for `pl.skrajewski.restic_backup`, `com.user.syncal`, `Tmux.Start.plist` (not KeepAlive, so `agents_quiet` ignores them); whether they or another scheduled job drive `launchd` is not shown by the data. Do not claim the loop explains all `launchd` flags. The burst narrative for driver 2 is supported by the `scale400` manifests (python from `~/.hermes`, ppids 1 then children) but not by the driver log (no reason lines in drivers 1 and 2); the "222 runs by 21:11 UTC" figure is not checkable from the package.
- **Is the clean/flagged split applied consistently in `analyse.py`?** Mechanically yes: both tables come from the same `groups` dictionary, same key (block, case, variant, seed, vis_cache, instrument level, capture, entry, profiler, commit, comparison label, status), so `summary_groups.csv` (`table=clean`) and `summary_groups_all.csv` (`table=flagged_inclusive`) have the same 62 groups with `n_runs`, `n_contaminated`, `n_used`; warm-ups excluded; replaced blocks separate. Defects: (i) the clean table prints a median from `n_used` 1 or 2 (`G1b_scale400b` 117.00 s from one run, `G1b_out` O_min 36.74 from one, `G1b_base` 47.63 from two) and suppresses only the IQR; add an explicit marker or blank the median below 3. (ii) The plan's "more than a third flagged means the block is reported inconclusive" is not implemented: no column. (iii) "contaminated" mixes `foreign_heavy_before/after`, `load1_before` and `during`; add the reason split and `n_samples_heavy` to `summary.csv`. (iv) The `G1b_det` runs (labelled `determinism`) appear as `measured` groups; keep them out of timing tables.
- **What the predeclared rule says.** `plan.md` ("System processes during measured blocks", decided before any G1 data): if more than a third of a block's runs are still flagged, the block is reported inconclusive, and the list is not extended after seeing data. Applied to the measured reps of pass 2 that makes `G1b_base` (3/5), `G1b_seeds` (4/6), `G1b_ovh` (4/10), `G1b_ovhD2` (8/15), `G1b_out` (7/15), `G1b_scale400b` (4/5), `G1b_w1r` (2/5), `G1b_flow` (5/5) inconclusive; only `G1b_scale100` (1/5), `G1b_vbuild` (1/5), `G1b_w2` and the W3/W3b blocks survive. Every N=200 and N=400 headline in section 4 therefore depends on D31 overriding that rule, and a classification fitted after seeing the data is exactly what the rule forbids. That override is an explicit decision for the coordinator and the maintainer; the alternative is a rerun of those blocks on a host that meets the guards. The rule below is my recommendation if the override is taken, not something the data imply.
- **Recommended rule for reporting each flagged group** (labelled post hoc, because the data are seen; stated once in `plan.md` as D31 before `report.md` is written; the plan's literal 1/3 rule stays as a visible column):
  1. *Report flagged-inclusive median, IQR and all n_runs, labelled "flagged-inclusive: n_flagged of n"* for a group when all four hold: every flagged run has at most 3 heavy samples (at most 6 s); no offender is an installer/updater/Spotlight indexer or a user process outside the harness (`claude`, `python`, an app) in that run; the flagged runs' instructions retired and cycles elapsed are within 1 % of the group median (same work) and `wall - cpu` < 0.1 s; and flagged-vs-clean wall differs by less than the larger of the group's clean range and the pass-1 dispersion (3.5 %; this wall tolerance is weak because the pass-1 ranges come from all-flagged blocks, so the instructions/cycles condition is the one that discriminates). Applied per run to the measured reps (script over `host_during.samples` and `offenders_detail`; disqualifying offenders: installers and updaters, Spotlight indexers, `mediaanalysisd`, apps and extensions, the coordinator session, `python`, `spindump`, `pmset`): every flagged run of `G1b_ovh` (both levels), `G1b_ovhD2` counters and detail, `G1b_out` O_study and O_norc, `G1b_scale100`, `G1b_seeds` s3 passes. Runs that fail it: `G1b_base` rep 1 (9 heavy samples) and rep 4 (`appstoreagent`); `G1b_flow` rep 4 and `G1b_out` O_min rep 5 (`corespotlightd`); `G1b_ovhD2` plain rep 3 (4 heavy samples, Podcasts 107 %, WhatsApp extension); `G1b_scale400b` rep 1 (`CalendarWidgetExtension`) and rep 3 (4 heavy samples); `G1b_seeds` s2 rep 1 (`claude`); `G1b_w1r` rep 5 (5 heavy samples, Podcasts). For those groups report the flagged-inclusive statistic with the failing runs named, and also the statistic without them where at least 3 reps remain (`G1b_base` 3 of 5 remain, `G1b_flow` 4, `G1b_out` O_min 4, `G1b_ovhD2` plain 4, `G1b_scale400b` 3, `G1b_w1r` 4); `G1b_seeds` s2 keeps only 2 reps, below the 3-rep spec, so report it flagged-inclusive with the `claude` run marked (47.62 to 47.84 s, range 0.5 %). Wall and instructions of the failing runs do not differ from their siblings (section 1), so the exclusion is a precaution, not a correction.
  2. *Record only, no statistic in `report.md`*: `G1b_ovhD` (sustained installer), `G1b_scale400` (host inspection and Python loop in the run), `G1b_det` (own session), `G1b_outchk` (n=1, equivalence only; `mediaanalysisd` 104 %, `spotlightknowledged.updater` 198 %).
  3. Use ratios within a block, and always give instructions/cycles next to wall for every cost claim that carries a flagged group, since they separate work from clock. Never compare absolute walls across blocks or drivers.
  4. Mark every table with the denominator "n flagged of n" and the driver; do not list a flagged group in the clean table.

### 4. Headline claims implied by the numbers (all within-block; instructions x10^9 and cycles x10^9 are the clock-free second check, medians of 5)

**a. Instrumentation overhead (W1 O_study seed 1, 1+5 each, controlled-cost, comparison "controlled cost" valid only because outputs are equal).**

| Block (run id prefix) | Plain wall | Counters wall | Detail wall | Counters vs plain | Detail vs plain |
|---|---|---|---|---|---|
| `G1b_ovh` (ABAB, driver 1, 3/5 plain flagged, 1/5 counters) | 47.53 s | 47.93 s | none | +0.40 s, +0.84 % (instr +0.42 %, cycles +0.84 %) | n/a |
| `G1b_ovhD2` (abba, driver 3, 3/5, 3/5, 2/5 flagged) | 45.68 s | 46.17 s | 59.31 s | +0.49 s, +1.07 % (instr +0.35 %, cycles +1.1 %) | +13.63 s, +29.8 % (instr +24.1 %, cycles +27.0 %) |
| pass 1 `G1ovh`, `G1ovhD` (all flagged) | 47.26 / 47.31 s | 47.61 / 47.77 s | 60.08 s | +0.35 s (+0.74 %) / +0.46 s (+0.97 %) | +12.77 s, +27.0 % (instr +24.0 %, cycles +26.6 %) |
| `G1b_ovhD` (installer, record only) | 50.26 s | 50.42 s | 63.23 s | +0.3 % | +25.8 % |

- Counters add about 0.4 to 0.5 s (0.8 to 1.1 %) on 46 to 48 s, below the 5 % limit in four blocks over two passes and two designs (ABAB and abba), per-rep pair differences 0.15 to 1.42 s (the largest, `G1b_ovhD2` counters rep 5, 47.34 s, is unflagged and sits at the end of the clock drift). Memory +1 MB. `G1b_ovhW3`: counters 8.12 vs plain 7.98 s (+1.8 %, 0/5 and 1/5 flagged); pass 1 +1.8 %. Equivalence: W1 11/11 and 17/17, W3 11/11 but "cognitive-map state not compared" (item 12 only in the det gate and the dev runs).
- **Detail is diagnostic-only.** 24.0 to 24.1 % more instructions in both passes (3.26 M agent-steps, `G1b_ovhD2` counters `agent_steps` 3,259,925: about 4.2 us per agent-step), +27 to 30 % wall, +22 MB RSS. The wall figure varies 25.8 to 29.8 % with the clock; quote 24 % instructions and 27 to 30 % wall. Any caller-split time from detail runs is diagnostic and must not be used as a share of the plain loop.
- ovhD2 vs ovh: the relative overhead agrees (+0.8 vs +1.1 %), the absolute walls do not (45.68 vs 47.53 s, clock 3.922 vs 3.773 GHz, same instructions). That is expected, not a discrepancy.

**b. Output-variant cost (W1, `G1b_out`, ABC order, controlled-cost; equivalence per 2).**

| Variant | wall | instr | cycles | RSS | flagged |
|---|---|---|---|---|---|
| O_study | 46.27 s (rep 1 to 5: 46.02, 46.27, 46.17, 46.44, 46.57) | 796.2 | 179.3 | 480 MB | 2/5 |
| O_norc | 36.38 s (36.04 to 37.07) | 629.8 (-20.9 %) | 140.8 (-21.5 %) | 397 MB (-84) | 1/5 |
| O_min | 36.89 s (36.74 to 37.05) | 623.5 (-21.7 %) | 139.7 (-22.1 %) | 386 MB (-94) | 4/5 |

- Pass 1 (all flagged): 47.51, 37.24, 37.05 s. The route-cost history (O_study to O_norc) costs 9.9 s (-21.4 % wall, -20.9 % instructions) in pass 2 and 10.3 s (-21.6 %) in pass 1: robust. O_min vs O_norc: +0.51 s (+1.4 %) in pass 2 with fewer instructions (-1.0 %) and cycles (-0.8 %), -0.19 s (-0.5 %) in pass 1: sign flips, all within the 1.5 % clock effect and with O_min always last. **Report as "no measurable difference between O_norc and O_min"**, not as "SQLite and CSV outputs cost nothing".
- **The equivalence evidence for O_min is thin.** In `G1b_out_vs_G1b_base.json` the 6 O_min pairs compare only item 10 (`10_exit_summary_counts`); items 1 to 6, 8, 9 are `not_in_both` (O_min writes none of the files) and the gap text says so, yet the verdict reads "equivalent" (18/18 incl. warm-ups). The claim "O_min computes the same trajectory" rests on `G1b_outchk` (one untimed run, `O_min_check`, equivalent to `G1b_base`, trajectory hash `c6e61a8d`, 625.1 instructions, flagged) which is a different command from the timed O_min. Acceptable as a controlled-cost experiment (same instruction count within 0.3 % supports it) but quote the verdict as "equivalent on the items both runs write; O_min computation checked by `G1b_outchk` n=1".
- **Mechanism not yet explained (spec 9 needs a second check).** 9.9 s and 20.9 % fewer instructions from not writing 64,994 route-cost rows is far more than formatting; the history evidently triggers extra evaluation or retention (RSS -84 MB). No counter, phase or profile shows which. Label as "measured, mechanism unresolved" until a G2 experiment (route-evaluation counters in O_study vs O_norc, or a sampling profile) exists.

**c. Scaling (W1 family, time-limited 400 s window, all three levels end the window with 1 to 3 agents inside, `G1b_scale100` 99/100, `G1b_out` 199/200, `G1b_scale400b` 397/400).**

| N | Run ids | wall | instr | cycles | RSS | flagged |
|---|---|---|---|---|---|---|
| 100 | `G1b_scale100_W1_n100_O_study_s1_rep1..5` | 22.48 s | 379.6 | 86.8 | 366 MB | 1/5 |
| 200 | `G1b_out_W1_O_study_s1_rep1..5` (same driver) | 46.27 s | 796.2 | 179.3 | 480 MB | 2/5 |
| 200 | `G1b_base_W1_O_study_s1_rep1..5` (driver 1) | 47.61 s | 796.4 | 179.8 | 480 MB | 3/5 |
| 400 | `G1b_scale400b_W1_n400_O_study_s1_rep1..5` | 118.18 s | 2042.6 | 449.7 | 832 MB | 4/5 |
| 400 | `G1b_scale400_...` (record) | 116.98 s | 2043.7 | 449.9 | 832 MB | 5/5 |

- Ratios, clock-free: N 100 to 200 x2.10 instructions (x2.07 cycles); 200 to 400 x2.57 (x2.51). Wall with the same-driver anchor: x2.06, x2.55; with `G1b_base` as anchor x2.12 and x2.48. The superlinear step from 200 to 400 (instructions per agent 3.80, 3.98, 5.11 x10^9; RSS per agent 3.7, 2.4, 2.1 MB for the totals, +114 MB then +352 MB for the increments) is robust to the anchor choice; the pass-1 values (22.41, 47.51, 119.55 s; instructions 379.7, 794.8, 2043.2) agree within 1.5 % in ratio. Trajectory hashes are identical across passes for each N.
- Workload effects, not complexity: higher N means density and a longer queue at the exits within the same 400 s; `report.md` must say "per agent grows 28 % from 200 to 400" with that caveat.
- **Gap: time per measured agent-step is missing for N=100 and N=400.** `agent_steps` exist only for counters runs (N=200: 3,259,925). Spec 7 asks for time per agent-step at each level. Needs counters runs at N=100 and N=400 (instrumented, labelled diagnostic, ~1 % overhead).
- **Gap: no horizon check for `W1_n100`, `W1_n400`.** `block()` in all three drivers runs `horizon_check.py` only for `W1|W3|W3b_cmm|W1r`. The O_study runs write `rc.csv`, so the check can be computed afterwards (untimed, by the engineer); N=400 could pass the 481 s guard that N=200 meets with bound 430.6 s. Until then "valid horizon" is unverified for the scaling points.
- `G1b_w2` (clear air, no fire) 19.17 s, 313.5 s simulated, 200/200, is in a different clock state (3.7 to 3.9 GHz not checked) and is not part of the scaling claim.

**d. Other numbers likely to be quoted.** W3 first use vs repeated: 8.38 vs 7.98 s (+5 %; vismap build about 0.4 s; pass 1 +5 %). W3b 1.24 vs 1.13 s: 1 s runs, unsampled, label as such. `G1b_vbuild` plain 10.72 s (IQR 0.01; pass 1 10.70). W1 seeds: 47.72 s (seed 2) and 47.72 s (seed 3) vs 47.61 s seed 1, each 3 reps, 2 of 3 flagged, instructions 796.6 to 802.4 x10^9: seed spread 0.2 %, timing spread inside it; headline holds on both extra seeds. W1r 16.13 s (`G1b_w1r`), horizon fails by design (6/6 `passes: false`). `G1b_flow` 70.26 s (pass 1 67.93 s, +3.4 %, 5/5 flagged in pass 2).

### 5. Harness faults (D27) in the three drivers

1. **`SKIPPED_SLOT` without a reason in drivers 1 and 2** (`g1_all.sh`, `g1_resume4.sh`): `wait_slot` swallows the `check` JSON. Driver 1 skipped five blocks (105 min), driver 2 four blocks (80 min), and the cause (update daemons; respawn loop) was found by manual inspection afterwards, which itself contaminated `G1b_scale400` (`claude`, `spindump`, `pmset`). Fixed in `g1_resume5.sh` (`slot busy: load1 1.12 ... heavy [assistantd 29%]` is printed; one poll failed in the whole of driver 3, so the new log is exercised but barely). `README.md` section 7 and the plan describe the fix; keep the status "fixed, not exercised on a long wait". Not a result.
2. **Gate re-check on existing runs** (drivers 2 and 3 re-ran `compare.py` and the negative control on the driver-1 `G1b_det` runs and rewrote `results/equivalence/G1b_det_*.json`). Harmless for exactness, but it is not a determinism check on the new host state (see 2). Record it as "gate re-validated the same pair, not a new pair". **Latent fault (D27, perf-engineer):** `gate()` discards the exit code of `compare.py` and reads the JSON from disk, and in drivers 2 and 3 the driver-1 JSON files already existed, so a `compare.py` crash would have produced a stale PASS. Driver 3 is clean: `results/equivalence/G1b_det_W1.json`, `G1b_det_W3.json` and both `*_negative_control.json` were written 04:51:40 to 04:51:47 UTC (file mtimes 06:51:40 to 06:51:47 CEST), inside the gate window 04:51:39 to 04:51:47 UTC. Driver 2 cannot be verified (its files were overwritten by driver 3). Fix: delete the JSON before comparing, or check the exit code.
3. **`G1b_det` W1 `rep1` flagged by `claude` 45 % and `syspolicyd`; `G1b_seeds` s2 rep 1 by `claude` 25 %.** Own-session activity during blocks in driver 1, contrary to the plan. Not harmful (equal work) but it counts as a coordinator-process fault; mark those two runs.
4. **No horizon check for `W1_n100`/`W1_n400`** (4c): omitted case in the `case` statement of `block()`, a driver gap, not a run fault.
5. **W4 fixture `G1b_w4` 0.99 s** (1 run, no warm-up, rc 0, `completed`): not a timing result (n=1, includes cold imports), consistent with its label "fixture". Same work as pass 1: `G1b_w4_W4_iso21_fixture_s420_rep1_20261016T210634` and `G1w4_W4_iso21_fixture_s420_rep1_20261016T060800` both end "finished in 85.30 s (1/1 evacuated)" with trajectory hash `33e9d5d6…`; wall 0.99 vs 0.95 s (+4 %, a 1 s process). `plan.md` says "same as pass 1" for the time: it is 0.95 s in pass 1. Correct the sentence. The W4 extras were checked too (no traceback in `results/raw/G1b_w4_extra/*.log`; the two `worktree_*_pytest.txt` hits are the word in file names): `iso22_a` to `iso22_d` each exit 2 with "Simulation incomplete: time limit reached after 1150 s (a), 1950 s (b, c), 1000 s (d) (0/1 evacuated, 1 remaining)"; no document I read states that this outcome is expected for the ISO 22 fixtures, so perf-model should confirm it (the 857 pytest cases for `test_iso_table22_coupled.py` pass); `cmm_armA` rc 0, 20/20 evacuated in 21.47 s.
6. **`G1b_w4_extra` records overwritten by the second run**: `iso22_*.log`, `cmm_armA.log` and `pytest.log` are from driver 2 (21:06 to 21:09 UTC); `status.txt` has both sets (rc 2 for iso22 a to d, 0 for cmm arm A and pytest, 857 passed, 1 skipped in the surviving log); the driver-1 logs are gone. Optional.
7. **Driver changes between passes are all outside the measured path** (guards `updates_off`, `agents_quiet`, `SLOT_REASON_PY`): confirmed by the identical `benchmark.py` sha256 in 173 manifests. No traceback anywhere.
8. **Gap carried over, not a fault:** `G1b_det_W3`'s W3 gate compares cognitive-map state now (capture runs); `G1b_ovhW3` pairs still do not (item 12 absent): the counters equivalence for W3 cognitive-map state is covered only by the det gate and the dev runs.

### 6. Findings

**Blocking (for quoting numbers in `report.md`; not for the evidence record):**
1. No W1-family statistic until D31 is decided in `plan.md` and applied by `analyse.py` per the rule in section 3, with `n_flagged of n` and instructions/cycles beside wall. Owner: coordinator (rule), perf-engineer (implementation).
2. Scaling must use the same-driver N=200 anchor (`G1b_out` O_study or `G1b_ovhD2` plain), not `G1b_base`, and show instructions as the clock-free ratio. Owner: perf-engineer (analysis/figure), coordinator (report).

**Important:**
3. Offender classifier (`benchmark.py` `offender_class`): `/sbin/launchd` (ppid 0) and `/System/Applications/*.app`, `*.appex` are misclassified; add offender classes, heavy-sample count and burst length to `summary.csv`. Owner: perf-engineer; meaning of classes: perf-model.
4. Quiet-host list incomplete in driver 3: Podcasts 107 %, WhatsApp `ServiceExtension`, Dropbox extension present; residual `launchd` bursts (14 driver-3 runs) unexplained; scheduled non-KeepAlive agents (`restic_backup`, `syncal`) unguarded; coordinator host inspection during blocks. Owner: coordinator with the maintainer; perf-engineer for a `launchctl` schedule check in `agents_quiet`.
5. `analyse.py`: blank the median for `n_used` < 3 or mark it, add the 1/3 rule column, exclude `determinism` groups from timing tables; add a generated overhead/ratio table (paired, within block, with instructions and cycles) so the numbers in 4a to 4c are not hand-entered (spec 10). Owner: perf-engineer.
6. Horizon check for `W1_n100`/`W1_n400` (and counters runs at N=100/400 for time per agent-step). Owner: perf-engineer.
7. O_min equivalence: wording of the verdict and the `G1b_outchk` n=1 basis; add an O_min-with-SQLite-copy check comparison or state the limit; the route-cost-history mechanism needs a G2 second check. Owner: perf-model (classification), perf-engineer (experiment).
8. OS version and boot time in the manifest; resolve the 27.0 vs 27.0.1 statement. Owner: perf-engineer.
9. Order in `G1b_out` is fixed ABC (O_min always last): the O_min vs O_norc comparison is inconclusive and must be reported so; if it matters, rerun with `--order abba` in a quiet slot. Owner: coordinator.

**Optional:**
10. Keep `G1b_w4_extra` logs per driver; `plan.md` "same as pass 1" for W4 (0.95 s); correct the "103/179" style counts (G1b: 54 of 84 W1-family measured runs flagged; 10/18, 1/1, 9/18, 1/6, 5/6 in the continuation match the manifests).

### 7. Verdict items and gaps

- **Reproduction: not run in this review, slot pending** (G3, D28; agree an exclusive slot with perf-engineer; planned: `G1b_ovhD2`-style W1 plain vs counters pair and one `G1b_out` O_study vs O_norc pair in a QA directory, same commit, same driver conditions, with the section 3 guards).
- **Verification gaps recorded:** OS build per run (item 8); horizon for scaling levels (6); time per agent-step at N=100/400 (4c); mechanism of the route-cost-history cost (7); cognitive-map equivalence of the W3 counters pairs (5.8); flagged-group rule applied to `G1b_flow` instructions (3).
- **G2 note.** Claims in 4a to 4c are measured for these workloads and this host; none is a root-cause claim. Payoff estimates for report.md must use `1/((1-p)+p/s)` on non-overlapping critical-path time; the O_study to O_norc cost (21 % of wall) is an end-to-end output-set cost, not a component profile, and is not additive with the instrumentation overhead.

### Handoff

**Inputs/commit.** `8f7d29a2`, lock `7f64a58d…`, files listed above, 173 `G1b_` manifests and the 149 pass-1 manifests. **Files produced.** This section (appended to `review.md`; backup of the previous file in the QA scratchpad); analysis scripts in the QA scratchpad only. **Commands executed.** Read-only Python over manifests, `time_l.txt`, `horizon.json`, `summary*.csv`, `results/equivalence/*.json`; `diff` of `g1_all.sh`, `g1_resume4.sh`, `g1_resume5.sh`; `stat` of record mtimes; `launchctl list` (read only); `sw_vers`. No benchmark, no reproduction, no write outside `review.md`.

### Reproduction (perf-qa, 2026-10-17, G1b pass 2 reproduction slot)

**Status: PARTIAL.** Work and equivalence reproduce; wall time reproduces only within the session shift, and the slot was not quiet (19 of 19 QA runs flagged by user applications). Timed runs 07:06:55 to 07:21:38 UTC (manifests; the `QA2_base` warm-up id is `...T070655`), untimed `QA2_n100` 07:22:29 to 07:22:53 UTC. Machine free from 07:23 UTC. Commit `8f7d29a2`, `benchmark.py` sha256 `ab19ce4d...` (README section 3, matches all 19 manifests), same venv and stage as G1b. Outputs: `results/raw/QA2_base_*`, `QA2_ovh_*`, `QA2_n100_*` only; `compare.py` outputs and an `analyse.py` copy (writing to scratch, so the shared `summary*.csv` were not rewritten) are in the QA scratchpad `eq/` and `an/`. Driver log: scratchpad `qa2.log`.

**Slot.** `benchmark.py check` printed `ok: false` at 07:06:39 (`claude` 44 %), `ok` at 07:06:46, and the block started. Every run is flagged: during the runs the host monitor recorded iTerm2 (20 to 31 %), Firefox and its helpers (up to 149 %), Zotero 185 %, `claude` 27 to 75 % (reps 4 of base and counters), LibreOffice, WhatsApp extension, System Settings and its extensions, plus system bursts (`spotlightknowledged.updater` 122 %, `corespotlightd` 138 %, `duetexpertd` 123 %, `mobileassetd` 168 %, Siri AI 154 %). The idle-machine condition was not met; the slot check passed only because `ps` %CPU is a decaying average. Under D31 rule (b) all 10 plain and all 5 counters QA runs are excluded from the sensitivity statistic (user apps, `claude`), so QA groups carry no sensitivity median. This is the same failure mode as G1b, with user apps instead of daemons.

**Numbers (seed 1, W1 O_study, runs without warm-up; wall in s, instructions and cycles x10^9, medians of 5).**

| Group | Run ids | Wall med [q1, q3] | Instr | Cycles | GHz |
|---|---|---|---|---|---|
| QA2 base (plain) | `QA2_base_W1_O_study_s1_rep1..5` | 46.85 [45.81, 47.00] (45.11 45.81 46.85 49.86 47.00) | 795.6 | 180.2 | 3.85 |
| QA2 ovh plain | `QA2_ovh_W1_O_study_s1_rep1..5` | 48.15 [47.92, 48.50] | 795.2 | 180.6 | 3.76 |
| QA2 ovh counters | `QA2_ovh_W1_O_study_ctr_s1_rep1..5` | 48.92 [48.24, 49.13] | 797.5 | 181.6 | 3.73 |
| G1b_base | driver 1 | 47.61 | 796.4 | 179.8 | 3.78 |
| G1b_out O_study | driver 3 | 46.27 | 796.2 | 179.3 | 3.88 |
| G1b_ovhD2 plain / counters | driver 3 | 45.68 / 46.17 | 795.2 / 798.0 | 179.2 / 181.2 | 3.92 |

- **Baseline.** QA median 46.85 s is -1.6 % vs `G1b_base` (47.61) and +1.3 % vs `G1b_out` O_study (46.27); the plain run in the QA ovh block is 48.15 s (+1.1 % vs `G1b_base`). Instructions agree within 0.1 % (795.2 to 795.6 vs 796.4 to 796.2), cycles within 0.4 %. The wall differences are clock (3.73 to 3.85 GHz vs 3.78 to 3.92) plus contamination (rep 4 of base: 49.86 s, +6 %, RSS 427 MB instead of 480 MB, `claude` 75 % and a burst of daemons at that time). Reproduced within the 3 to 4 % session shift of D31(d); not a clean-slot reproduction. Do not quote 46.85 s as a baseline; it is a flagged 5 of 5 group.
- **Counters vs none (abba, 1+5 each).** Wall +0.77 s, **+1.6 %** (G1b: +0.84 % `G1b_ovh`, +1.07 % `G1b_ovhD2`); instructions +0.29 % (G1b +0.42 and +0.35 %), cycles +0.55 % (G1b +0.84 and +1.1 %). The work-based overhead reproduces, below 1.1 %; the wall ratio is 0.5 point above the stated +0.8 to +1.1 % band, with both groups 5 of 5 flagged and a plain-group spread of 2.5 s (rep 1 50.41 s). Conclusion unchanged: counters overhead is about 1 to 1.6 %, far below the 5 % limit. I do not claim +1.6 % as a better estimate than the G1b figure; the G1b value stays the quoted one, this is the reproduction envelope. Instructions and cycles are the clock-free check.
- **Equivalence.** `compare.py --block QA2_ovh --ref G1b_ovhD2_W1_O_study_ctr_s1_rep1_20261017T045502` (the harness's `first_id`): 12 of 12 equivalent, exit 0; `QA2_base` vs the same reference: 6 of 6 equivalent. Same trajectories as G1b across driver, boot state and instrumentation.

**Step 3, driver path.** `block()` from `g1_resume5.sh` (sourced into a scratch script, prefix `QA2`, status file in scratch) ran `W1_n100` once: `QA2_n100_W1_n100_O_study_s1_rep1_20261017T072229`, exit 2 (expected), 23.32 s, flagged. `horizon_check.py` ran and wrote `horizon.json`: max bound 430.6 s vs guard 481.1 s, 0 rows past the guard or last frame, held share 0, 0 warnings, `passes: true`. The new manifest carries `os` (`product_version` 27.0.1, `build_version` 26A434, boottime 2026-10-16 21:17:07, the post-update reboot) and `offenders_detail` with classes (`user_app`, `own_session`, `indexer`, `system_tool` for `launchd`, `system_daemon`, `user`) and `offenders_class_rule`. All 19 manifests have them. `/System/Applications/Siri AI.app` and `FindMy.app` are still `user_app` (descriptive, D31(e)); `launchd` is now `system_tool`, not user. The old `G1b_scale100` and `G1b_scale400b` runs have no `horizon.json` (the new `block()` only applies to future runs): gap, below.

**Step 4, analyse.py (copy writing to scratch, same code).** 375 runs, 66 groups in both tables. `flag_status` and `wall_s_median_sensitivity`, `n_sensitivity`, `excluded_runs` are present. QA groups: `QA2_base`, `QA2_ovh` none and counters, `QA2_n100`: `inconclusive`, `n_used` 0 (n100: 1 in the all table), clean table blank, all table shows medians. G1b rows match the acceptance numbers: `G1b_base` 47.613 (sensitivity 47.629 without rep4, n 4; rep1 kept as D31(b) says), `G1b_out` O_study 46.267 / O_norc 36.375 / O_min 36.895 (O_norc `ok` 1 of 5; rep5 excluded; O_min `inconclusive`), `G1b_ovhD2` none 45.682, counters 46.171 (sensitivity n 3, reps 2 and 4 excluded as D31 amendment says), detail 59.308, `G1b_outchk` `record_only`.

**D31 as recorded and implemented.** Consistent. The amendment in (b) matches the code: rep1 of `G1b_base` not excluded (system daemon, instructions within 1 %), `G1b_out` O_norc rep5 and `G1b_ovhD2` counters reps 2 and 4 excluded; the one-third rule is per group (variant x seed x instrument level); clean table blanks n_used < 3 and keeps n_used. Two wording points, optional: (i) the (a) list still names `G1b_base` rep1 and `G1b_out` O_min rep5; the amendment resolves it, but `G1b_ovhD2` plain rep3 is the only plain exclusion; (ii) with user apps in the exclusion list, a QA-style session with iTerm2 open excludes every run (QA groups have no sensitivity median): the rule works as intended but shows that the sensitivity column cannot rescue a session in which a user app is always running.

**perf-engineer changes.** Classification (by name, `system_tool`, `own_session`, `os` block), blanking, sensitivity columns, `record_only`: correct on the data above. `gate()` in `g1_resume5.sh` (read, not executed in this session): both `compare.py` exits are checked before the JSON is read, `FAIL(compare.py exit)` stops with exit 1: correct by reading; not exercised on a failing `compare.py`. Horizon for `W1_n100`: exercised and correct. Not exercised by me: `W1_n400` horizon, `gate()` failure path, `agents_quiet` in anger.

**Remaining items for closing issue #803 (none changes the G1b evidence record):**
1. (important, perf-engineer) Run `horizon_check.py` untimed on `G1b_scale100_*` and `G1b_scale400b_*` and store `horizon.json` (the `block()` fix applies only to new runs); the n = 100 run above passes with the same 430.6 s bound as N = 200.
2. (important, coordinator with maintainer) This slot was not quiet enough to produce a clean reproduction. For a clean G3 (D28) close the apps in the list above (iTerm2, Firefox, Zotero, WhatsApp, LibreOffice, System Settings) and do not run any `claude` session during the block; the slot check should also treat user apps above 20 % at the start sample as blockers (it already does) but a pre-start settle period of a few minutes would remove the decaying-average artefact.
3. (optional, perf-engineer) Gate failure path and `W1_n400` horizon never exercised: one dry exercise with a deliberately failing `compare.py` argument.
4. Open from the earlier review and not touched by this reproduction: time per agent-step at N = 100/400, mechanism of the route-cost-history cost (G2).

**Verdict.** PARTIAL for G3: the primary baseline and the counters-vs-none finding reproduce in instructions, cycles, outputs and conclusion (<5 %, about 1 to 1.6 %), and wall within the 3 to 4 % session shift; the +0.8 to +1.1 % wall figure is reproduced as +1.6 % on a fully flagged slot. No blocking item against closing #803 on the evidence record; the G3 reproduction should be repeated in a quiet slot if a clean number is wanted for `report.md`.

### Reproduction (2026-10-17, perf-qa; G3 slot, appended; the text above is unchanged)

Note: a second perf-qa instance sharing the same scratchpad wrote the subsection above while this one was running; both worked from the same 19 `QA2_*` runs (one set of runs, not two) and reach the same status and numbers. The discrepancy about the `QA2_n100` script below is explained by that: the other instance rewrote `qa2_n100.sh` and ran the n100 block (07:22:29 UTC) while this instance's version was being started. This subsection is an independent second analysis of the same data.

**Status: PARTIAL.** The work reproduces exactly and the numbers land inside the stated session shift, but the slot was not clean: all 18 timed runs are flagged by the host rule, so neither number is a clean-host reproduction. No result is rescaled.

**What ran.** Host check `benchmark.py check` printed `ok: true` at 07:06:46 UTC (load1 1.72, no heavy foreign process; an earlier check at 07:06:39 had failed on `claude` 44 % and passed on the next poll). Timed runs 07:06:55 to 07:21:38 UTC, `--exclusive`, `benchmark.py` sha256 `ab19ce4d…`, worktree `8f7d29a2` clean, serial, driver `qa2.sh` in the QA scratchpad (slot wait, then the two blocks):
- `QA2_base` (W1 plain, 1 warm-up + 5 reps): `benchmark.py run --block QA2_base --case W1 --exclusive`, rc 0.
- `QA2_ovh` (W1 `--instrument none,counters --order abba --label controlled-cost`, 1 warm-up + 5 reps per variant): rc 0.
- Untimed: `QA2_n100_W1_n100_O_study_s1_rep1_20261017T072229` (07:22:29 to 07:22:54 UTC), 1 run through `block()` cut from `g1_resume5.sh` (so `horizon_check.py` is called by the driver path). Discrepancy to record: the script text I wrote named the block `QA2_scale100` with `--label end-to-end`; the file on disk and the run say `QA2_n100`, label `equivalence` (file mtime = run start). I cannot explain it; the run is untimed and its label does not enter any statistic.
- Outputs only under `results/raw/QA2_*` (19 run directories), `results/equivalence/QA2_ovh_vs_G1b_ovhD2.json`, and `$STAGE/runs/QA2_*`. `analyse.py` was run from a copy in the QA scratchpad (`scratchpad/an/`, `results/raw` symlinked read-only) because it overwrites `results/summary*.csv`; the repo `results/summary*.csv` are untouched. No `G1b_*` path was written.

**Contamination (G1 accounting).** 18/18 timed runs and the n100 run are flagged. The host was not idle: Firefox (up to 133 %), iTerm2 (20 to 31 %), Zotero 185 %, LibreOffice `unopkg`, WhatsApp extension, System Settings (open on the desktop), `top`, `claude` (22 to 75 % in 5 runs, `QA2_base` rep4, `QA2_ovh` ctr rep1, rep4, plain rep3, n100), plus Spotlight family (`spotlightknowledged.updater` 66 to 122 %, `corespotlightd` up to 138 %, `mediaanalysisd`, `duetexpertd`). Per `QA2_base` rep4 (49.86 s, RSS 427 MB instead of 480 MB, 13 offenders) the largest disturbance is visible in wall but not in instructions (795.6). Under D31 the groups are `inconclusive` (5/5 flagged) and the sensitivity column is empty (every run has a rule-(b) offender: `/applications/` hits Firefox or iTerm2 in all of them). Coordinator/maintainer must say who had those apps open; the slot instruction was "machine idle", and `benchmark.py check` does not see short bursts (README section 3).

**Baseline (W1 plain, `QA2_base`).**

| | wall median [q1, q3] | instr x10^9 | cycles x10^9 | GHz | flagged |
|---|---|---|---|---|---|
| `QA2_base` (this slot) | 46.85 s [45.81, 47.00], runs 45.11, 45.81, 46.85, 47.00, 49.86 | 795.6 | 180.2 | 3.846 | 5/5 |
| `G1b_base` | 47.61 s | 796.4 | 179.8 | 3.775 | 3/5 |
| `G1b_out` O_study | 46.27 s | 796.2 | 179.3 | 3.808 | 2/5 |

Instructions agree within 0.1 % and cycles within 0.5 %, so the work is reproduced; wall is -1.6 % vs `G1b_base` and +1.3 % vs `G1b_out`, bracketed by the two G1b values and consistent with the clock (3.85 GHz lies between 3.78 and 3.81 to 3.92), i.e. inside the 3 to 4 % session shift of D31(d). Outcome, termination and trajectory hash are identical: 199/200 at 400 s, `c6e61a8d1c` in `QA2_base`, `QA2_ovh` and all G1b W1 O_study groups; `agent_steps` 3,259,925 in the counters runs equals `G1b_ovhD2`. The IQR (1.19 s) is 10 to 40 times the G1b IQR because of the flagged runs; the median is not shown to be stable at the 1 % level from this block alone.

**Counters vs none (`QA2_ovh`, abba, equivalence 12/12 against `G1b_ovhD2` first run via `compare.py --block QA2_ovh`, rc 0, no gaps).**

| | plain | counters | counters vs plain |
|---|---|---|---|
| wall median | 48.15 s [47.92, 48.50] | 48.92 s [48.24, 49.13] | +0.77 s (+1.6 %); median of 5 pair differences +0.63 s (+1.3 %), pair range -2.47 to +1.83 s |
| instructions | 795.2 | 797.5 | +0.29 % |
| cycles | 180.6 | 181.6 | +0.55 % |

The reference result was +0.8 to +1.1 % wall (instr +0.35 to +0.42 %, cycles +0.8 to +1.1 %). The reproduction confirms the sign and that the overhead is far below the 5 % limit, and the instruction ratio matches. The wall ratio is 0.2 to 0.8 points higher and the cycle ratio 0.3 to 0.5 points lower than G1b: with 10/10 runs flagged, a pair range of 4.3 s and plain rep1 at 50.41 s (190.3 x10^9 cycles, Firefox 34 %), the difference between +1.3 % and +1.1 % is not resolvable. Claim as reproduced: "counters overhead about 1 % (instructions +0.3 %), under 5 %"; do not quote +0.8 to +1.1 % as reproduced to that precision. Absolute walls 48.2 and 48.9 s are 1 to 5 % above `G1b_ovhD2` (45.7, 46.2 s) and `G1b_ovh` (47.5, 47.9 s), clock 3.71 to 3.75 GHz, lower than any G1b block, so within-block comparison only (D31(d)).

**analyse.py and the groups.** With the QA2 runs added (375 runs): QA2 groups appear with `flag_status` `inconclusive`, `n_contaminated` 5/5 (n100 1/1), blank clean medians (`n_used` 0 in the clean table), flagged-inclusive medians as above, `n_sensitivity` 0. G1b rows match the D31 acceptance text: `G1b_base` sensitivity excludes rep4 (offender `appstoreagent`) and not rep1 (`duetexpertd`), median 47.629 over 4 vs 47.613; `G1b_ovhD2` counters excludes reps 2 and 4 (median over 3), plain excludes rep3; `G1b_out` O_norc excludes rep5, O_min rep5; `flag_status` is per group (G1b_base 3/5, G1b_out O_study 2/5 and O_min 4/5 inconclusive, O_norc 1/5 ok, ovh counters 1/5 ok, ovh plain 3/5 inconclusive); `G1b_ovhD`, `_scale400`, `_det`, `_outchk` are `record_only` with blank statistics. I confirmed by scan of all manifests that no `mds` or `claude` substring in rule (b) hits a path that is not that process.

**Checks of the perf-engineer changes.**
1. Offender classes (`benchmark.py offender_class`): names applied to the QA2 manifests give `own_session` for `claude`, `indexer` for `spotlightknowledged`, `corespotlightd`, `managedcorespotlightd`, `app_extension` for `.appex`, `system_tool` for `/sbin/launchd`, `system_daemon` for `/usr/libexec` and `/System` daemons. Residual labelling (descriptive only, D31(e)): `/System/Library/CoreServices/*.app` (WiFiAgent, MenuBarAgent, ControlCenter) and `/System/Applications` apps (FindMy, Siri AI, System Settings) are `user_app`; rule (b) names only `/system/applications/` so WiFiAgent/ControlCenter/MenuBarAgent are `user_app` but do not exclude a run. Optional: rename the class or document the difference. Correct as recorded.
2. Blanking: clean-table medians and spread are blank for `n_used` < 3 (QA2 and G1b_base), spread needs >= 3 runs, record-only groups blank. Correct.
3. Sensitivity rule: implemented as D31(b) (name substrings or instructions > 1 % from the group median, needs 3 instruction values), matches the recorded exclusions above. Correct. The one-third rule uses `3 * n_flagged > n_runs`, so exactly one third is `ok`; wording "more than one third" agrees.
4. Gate: `gate()` aborts on a non-zero exit of either `compare.py` call and reads the JSON only afterwards; read, not executed (no gate or negative control was run by me, and `compare.py` has no `sys.exit` for NOT equivalent, so the exit code catches crashes only; the verdict test on the JSON handles the rest). A stale JSON can no longer yield a PASS after a crash. Correct by reading; exercised path not run.
5. Horizon: `block()` now lists `W1_n100` and `W1_n400`; exercised for `W1_n100` on `QA2_n100_..._rep1`: `horizon.json` written, `passes: true`, `max_bound_s` 430.62 vs guard 481.12 s, held share 0, 0 warnings, rows 30,110 (`warning_count` and `held_share` appear in `analyse.py`). `W1_n400` not exercised (same code path, case glob only); its bound is unknown. n100 outcome 99/100 at 400 s, 379.5 x10^9 instructions (G1b_scale100: 379.6), wall 23.32 s flagged.
6. Manifest `os` block: present in the first new manifest and all QA2 manifests (`product_version` 27.0.1, `build_version` 26A434, `boottime` 2026-10-16 21:17:07 local). Resolves review item 8.
7. `benchmark.py` hash `ab19ce4d…` in all 19 QA2 manifests, equals README section 3.

**D31 as recorded and implemented.** Consistent: the plan text says rule (b) in `analyse.py` is authoritative, the implementation reproduces the stated exclusions, the one-third rule is per group, record-only blocks are blank, absolute walls are within-block with instructions and cycles. One wording gap, optional: plan.md (a) still lists G1b_base rep1 among the named runs; (b) overrides it explicitly, so it is documented. QA2 shows rule (b) excludes every run when a user app (iTerm2) hovers at 20 to 30 %, so on a machine with a terminal open the sensitivity column is empty and carries no information; that is a property of the rule, not a fault.

**Remaining items for closing #803.**
- Blocking: none for the evidence record. Blocking for the statement "primary baseline and leading finding reproduced on a clean host": a repeat slot with `check` re-polled and the host genuinely idle (no Firefox, Zotero, LibreOffice, System Settings, WhatsApp extension, iTerm2, no `claude` activity from the coordinator; `corespotlightd`, `spotlightknowledged`, `mediaanalysisd` still active although Spotlight indexing was reported off). Owner: coordinator with the maintainer; perf-engineer to decide whether D31 reporting is enough instead (the numbers above hold within the stated shift under D31(a)).
- Important: no horizon or counters for `W1_n400` (time per agent-step at N=100/400 still absent, unchanged from the earlier review); O_min vs O_norc and the route-cost-history mechanism remain unresolved (earlier items 7 and 9); `QA2_n100` block name and label differ from the script I wrote (unexplained, untimed).
- Not reproduced here (not in the agreed slot): output-variant cost, scaling ratios, W3, detail overhead; the earlier G1b numbers for those stand as PARTIAL.

**Handoff.** Inputs: commit `8f7d29a2`, `benchmark.py` `ab19ce4d…`, drivers as above. Files: `results/raw/QA2_*` (19 runs), `results/equivalence/QA2_ovh_vs_G1b_ovhD2.json`, QA scratchpad `qa2.sh`, `qa2.log`, `an/results/summary*.csv`. Commands: `benchmark.py check`, the two `benchmark.py run` lines above, `compare.py --block QA2_ovh --ref G1b_ovhD2_W1_O_study_ctr_s1_rep1_20261017T045502`, `analyse.py` from the copy. Next check: clean-host repeat or acceptance under D31(a) by the coordinator.

### Reproduction, clean host (2026-10-17, perf-qa; G1b pass 2, third slot, prefix `QA3_`)

**Status: PARTIAL (work, equivalence and leading finding reproduce; the slot was quiet of user apps and `claude`, but 13 of 18 timed runs are still flagged by the host rule, all by macOS system activity).** Timed runs 07:37:15 to 07:51:39 UTC (first and last manifest `t_start_utc` and `t_end_utc`; driver START 07:37:14, compare steps finished 07:52:07). Commit `8f7d29a2`, `benchmark.py` sha256 per README section 3, OS build 26A434. Driver `qa3.sh` and log `qa3.log` in the QA scratchpad: `benchmark.py run --block QA3_base --case W1 --exclusive` (rc 0), `run --block QA3_ovh --case W1 --exclusive --instrument none,counters --order abba --label controlled-cost` (rc 0), then `compare.py --block QA3_ovh` and `--block QA3_base` against `G1b_ovhD2_W1_O_study_ctr_s1_rep1_20261017T045502` (both rc 0, outputs in scratchpad `eq3/`). I also ran the two compares for completeness; only the first was requested. Outputs only under `results/raw/QA3_*` (18 run directories); `analyse.py` ran from a scratchpad copy (`an/`), the shared `summary*.csv` were not rewritten.

**Deviations from the method, recorded.** (1) `benchmark.py check` was `ok: false` once (my own `claude` session at 15.6 to 18.5 % decaying average), `ok` on the next poll; I started the script with a 90 s settle (`sleep 90` inside the `nohup caffeinate -s` command) so the decaying average would fall. (2) The harness rejected a standalone `sleep 1500`, so I waited with a single `until grep -q "STEP end" qa3.log; do sleep 30; done` call (moved to background after 600 s, completion notice received, no other tool calls during the runs). That loop is a light child process of my tool call and may appear as `claude` activity; no manifest lists `claude` as an offender.

**Flagged count: 13 of 18 timed runs (5 clean).** Clean: `QA3_base` rep1, rep3; `QA3_ovh` plain warm-up, counters warm-up, counters rep1. Flagged offenders by name (class, max %CPU):
- `QA3_base` warm-up: WhatsApp (user_app, 200), syspolicyd (system_daemon, 100), talagentd (30). rep2: WiFiAgent (user_app, 30), launchd (system_tool, 26). rep4: launchd 32. rep5: launchd 38.
- `QA3_ovh` plain: rep1 launchd 26; rep2 locationd 26; rep3 coreaudiod 21; rep4 XProtectRemediator Adload, Dolittle, SheepSwap (each 96 to 99, macOS malware-remediation scans, labelled user_app by path), contactsd, suggestd, SafeBrowsing, opendirectoryd; rep5 XProtectRemediator Adload, DubRobber, Pirrit, SheepSwap (94 to 100), trustd, plus `foreign_heavy_before`, `_after` and `load1_before`.
- `QA3_ovh` counters: rep2 launchd 26; rep3 AddressBookSourceSync (user_app, 29), AssetMetricsExtension, contactsd 99, photolibraryd 49, dasd, launchd 44; rep4 `spotlightknowledged.updater` (indexer, 104), coreduetd 74, runningboardd 70, PerfPowerServices; rep5 XProtectRemediator Adload and Pirrit (100), launchd 45, with `foreign_heavy_before/_after`.
- No Firefox, Zotero, LibreOffice, iTerm2, System Settings or `claude` in any run. Residual user-class names are WhatsApp (warm-up, untimed statistic), WiFiAgent, AddressBookSourceSync and the XProtect scans. XProtectRemediator ran in the last 2 reps of each ovh variant, i.e. a system scan started during the block; it is not something the maintainer could have closed.
- Group status from `analyse.py`: `QA3_base` `inconclusive` (3 of 5 reps flagged, `n_used` 2); `QA3_ovh` none `inconclusive` (5 of 5, `n_used` 0); counters `inconclusive` (4 of 5, `n_used` 1); D31(b) sensitivity excludes only `QA3_ovh_..._ctr_s1_rep4` (indexer), so `wall_s_median_sensitivity` is 47.77 s over 4 for counters and equals the plain median for the other two (n 5). No clean-table median exists for any QA3 group, so none of the numbers below may be quoted as a clean baseline.

**Numbers (seed 1, 5 reps, medians; instructions and cycles x10^9).**

| Group | Wall med | Wall runs | Instr | Cycles |
|---|---|---|---|---|
| `QA3_base` plain | 46.03 s | 44.76, 45.76, 46.03, 47.53, 47.55 | 794.6 | 179.7 |
| `QA3_ovh` plain | 47.48 s | 46.91, 47.18, 47.48, 47.48, 47.60 | 795.1 | 180.0 |
| `QA3_ovh` counters | 47.71 s | 47.25, 47.46, 47.71, 48.07, 48.12 | 797.5 | 181.6 |

- **Baseline.** 46.03 s vs `G1b_base` 47.61 s: -3.3 %; vs `G1b_out` O_study 46.27 s: -0.5 %. Instructions 794.6 vs 796.4 and 796.2 (-0.2 %); cycles 179.7 vs 179.8 and 179.3. The wall difference to `G1b_base` is within the 3 to 4 % session shift of D31(d) and the reproduction falls inside the two G1b values' envelope (the lower G1b value is 0.5 % away). The clean reps alone (44.76 and 47.55 s) span 6 %, so the median is not stable at the 1 % level. Work reproduces to 0.2 %.
- **Counters vs none (abba, 1 + 5 each).** Wall +0.24 s, **+0.50 %** (G1b: +0.84 % and +1.07 %); instructions +0.31 % (G1b +0.42 and +0.35 %); cycles +0.89 % (G1b +0.84 and +1.1 %). Instruction ratio and cycle ratio are inside or at the edge of the stated bands; wall is 0.3 to 0.6 points below the +0.8 to +1.1 % band, not above it as in QA2 (+1.6 %). Taken with QA2 (+1.6 %) the wall estimate scatters from +0.5 to +1.6 % with flagged runs; the clock-free ratios (+0.3 % instr, +0.9 % cycles) are the stable result. Claim: counters overhead about 1 % (instructions +0.3 %, cycles +0.9 %), well under the 5 % limit.
- **Equivalence.** `compare.py --block QA3_ovh`: 12 of 12 `equivalent`, no gaps, exit 0. `compare.py --block QA3_base`: 6 of 6 `equivalent`, exit 0. Trajectory hash `c6e61a8d1c42...` identical in all 15 timed reps (same as G1b and QA2); RSS 480 MB (plain) and 481 MB (counters), no run with the 427 MB anomaly of QA2 rep4.

**Verdict.** PARTIAL under the stated rule: no user-application or `claude` offender in any statistic-bearing run, which is what the maintainer's clean-host condition aimed at, but 13 of 18 runs (3 of 5 base reps, 9 of 10 ovh reps) are flagged by macOS system activity (launchd, contactsd, XProtectRemediator scans, indexing), and every QA3 group is `inconclusive` with blank clean medians. Nothing contradicts G1b: instructions, cycles, outputs and the counters conclusion reproduce, and wall reproduces within the session shift.

**Issue #803.** My recommendation for the coordinator: it can be closed with "primary baseline and leading finding reproduced; equivalence 18 of 18; QA3 host had no user applications or `claude` running, residual flags are macOS system daemons (XProtectRemediator scans, indexing, launchd)". The unqualified wording "reproduced on a clean host" is not supported, because `analyse.py` shows no clean group. If the maintainer needs the unqualified wording, it needs a block where the macOS background scans (XProtect, Spotlight, contactsd) are idle, which a user cannot always arrange. No blocking finding against the evidence record. Items 1 (horizon.json for `G1b_scale100`/`G1b_scale400b`), 3 (gate failure path) and the open G2 items from "Reproduction (perf-qa, 2026-10-17, G1b pass 2 reproduction slot)" are unchanged by this slot.

**Handoff.** Run ids `QA3_base_W1_O_study_s1_{warmup1,rep1..5}_*` and `QA3_ovh_W1_O_study_{,ctr_}s1_{warmup1,rep1..5}_*` under `results/raw/`. Scratchpad: `qa3.sh`, `qa3.log`, `eq3/QA3_ovh.json`, `eq3/QA3_base.json`, `an/results/summary_groups*.csv`.
