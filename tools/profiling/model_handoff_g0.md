# perf-model handoff, gate G0

Inputs: fds-evac `6fd7878c` (origin/main after #460), sciebo `fds-evac-data/`, spec v2.0, `studies/brief_study_schroeder2015.md` and `studies/backend_task_429_steering_perf.md`. Code was read at `289b33d0`. `6fd7878c` changes only packaging (`pyproject`, `uv.lock`, a scikit-image contract test), not `pyfds_evac/`, `run.py` or `assets/`, so the effective settings are unchanged. Hashes were redone at `6fd7878c`: `uv.lock` `2731a9e7…`. No timed runs, no FDS runs, no production code changed. The manifest is `scenarios.json`.

## 1. Workloads

| ID | Case | Run as | Why |
|---|---|---|---|
| W1 `w1_gate` | Schröder 2015, `config_gate.json`, fire `a047_pvc_h40`, arm `gate` | seed 1; 2 and 3 to confirm | Fully coupled: smoke speed, gas FED with incapacitation, and anticipated gate rerouting every 1 s all read the FDS field. `gate` is the default router and the router of the study. |
| W2 `w2_nf` | Same deck, no fire (`nf` arm) | seed 1; 2, 3 | Same geometry, stage graph and crowd as W1. Rerouting stays on and uses clear-air costs. Steering is timed separately from `iterate()` within the unchanged run. |
| W3 `w3_tj_discovery` | t_junction `config_discovery.json` on `fire_2MW_PVC`, committed 300 s deck (superseded G0 plan: cap 270 s; see §8, §9.3) | seed 42; 43, 44 | Agents must discover the exits from signs: builds or loads the smoke vismap, queries signs and grows cognitive maps, coupled with smoke, FED/FIC and rerouting. |
| W4 | ISO table 21/22 coupled (committed FDS output), `cognitive_map_memory` capped at 120 s, 19 targeted test files (incl. the scikit-image contract test) | as listed | Check mechanisms and instrumentation. They are no evidence of throughput. |

**Zeros that come from configuration, not from measurement.** In W1, visibility is never built: `familiarity: full` and no `--vis-cache`. Heat FED is off by CLI default, although a TEMPERATURE slice exists. FIC has no HCl/HCN input. Only W3 and W4-cmm exercise visibility.

**W3 cap.** The committed deck (300 s) cannot run without relaxing the horizon:
- the FDS output ends at 300 s, so the guard is at 301 s;
- anticipation is on by default, and `_arrival_time` does not clip;
- flow spawning continues to 400 s;
- the longest route takes 21.9 s at 1.3 m/s.

Any route priced after about 279 s therefore raises `FdsHorizonError`. The cap of 270 s follows the maintainer's own t_junction study (`CAP = 270`). This is a prediction from reading the code; one diagnostic run of the committed deck confirms or refutes it. *Superseded:* the G0 runs refuted the prediction for seeds 42–44, and W3 uses the committed 300 s deck (§8, §9.3).

**cmm cap.** The reference rerun at `289b33d0` used `--allow-fds-horizon-hold`, because the FDS output ends at 120 s against a 300 s cap. It also ran on 3.11 under the old lock. Use it only for egress time and switch counts. The exact check is done on the frozen environment and compares two arms:
- arm A: cap 300 with the hold flag, untimed;
- arm B: cap 120 without the hold flag.

The two arms must be identical, and arm A must log no hold.

**Sampling height.** The CLI default of 1.6 m is kept everywhere. On t_junction and cmm, which have slices only at 2.0 m, the samplers fall back to the 2.0 m slice. fdsvismap 0.3.1, however, also uses 1.6 m as the height of its obstruction test. So the height is a behavioural setting for visibility, not a cosmetic one.

## 2. Preflight

### Checked now, without running a simulation

| Item | W1 a047_pvc_h40 | W3 fire_2MW_PVC | W4 |
|---|---|---|---|
| FDS finished | `.out`: "STOP: FDS completed successfully", 5423 s | same | cmm same; ISO output committed |
| Meshes / frames | 6 meshes, 481 frames, 0–480 s at 1 s | 4 meshes, 301 frames, 0–300 s | iso21 0/75/150 s; iso22 every 500 s; cmm 61 frames, 0–120 s |
| Quantities at sampling height | K, CO, CO2, O2 and T at 1.6 m; K also at 2.0 and 2.8 m | K, CO, CO2, O2, HCl and VISIBILITY at 2.0 m only | iso21 K at 1.5/2.0 m; iso22 at 1.5 m; cmm at 2.0 m |
| Horizon | cap 400 s, guard 481 s. Earlier run: latest anticipated sample 432.4 s | superseded: committed cap 300 s, guard 301 s; measured bounds 56.8/58.8/57.8 s (§9.3) | cmm: cap 120 s, guard 122.1 s |
| Coverage | earlier manifest: 0.0 of 470.6 m² walkable outside the slices | 0.0 of 150 m², no sign off the grid | cmm 0.0 of 130 m² |
| Deck matches repo | header comment only | identical | committed |

Slice extremes are not hazard ranges at agent positions. O2, CO2 and CO read 0 in solid cells. K reaches 44 /m inside the non-walkable Room 3. Take hazard ranges from the sampled histories in G1.

### Must be shown in the engineer's G0 normal run

Before G1, every coupled run on CPython 3.12 at `6fd7878c` must meet all of the following:

- **Exit code.** 0 or 2, with no `FdsHorizonError` and no "holding the last frame".
- **Setup lines in the log.**
  - W1: smoke, FED, rerouting and tenability lines.
  - W3: in addition, "Configuring visibility model (3 signs)".
- **Coverage.** The manifest `fds_coverage` reports `walkable_outside_m2 = 0`. The "Outside the FDS domain" line is absent.
- **Manifest.** `git_dirty: false`, `agent_seeding: spawn-key-blake2b-v2`, and the lock hash `2731a9e7…`.
- **Spawning.**
  - W1: 200 placed at t = 0, `agents_not_spawned = 0`.
  - W3: spawned count reported, with `agents_not_spawned > 0` expected.
- **Anticipated horizon.** Compute `max(time_s + path_length_m / base_speed)` from the route-cost CSV. This is an upper bound: each edge is sampled at the time the agent arrives at its start. The bound must be < 481 s (W1) and < 301 s (W3). If the margin is under 5 s, flag it to the coordinator.
- **Nonzero activation**, as counts from the run outputs:

| Mechanism | W1 | W2 | W3 |
|---|---|---|---|
| Smoke speed factor < 1 for some agent and time | yes | n/a | yes |
| FED cumulative > 0 | yes | n/a | yes |
| FIC > 0 | n/a | n/a | yes (recorded only) |
| Route-cost rows / route switches | > 0 / > 0 | rows only with flag / any | > 0 / > 0 |
| Incapacitation events | configured, 0 expected (study: none) | n/a | report count |
| Vismap built or loaded, sign queries > 0, cognitive-map growth > 0 | n/a (off) | n/a | yes, needs engineer counters |
| Agents remaining at the cap, by state (inside vs not spawned) | report | report | report |

Earlier W1 runs, at other commits and in parallel jobs, give orders of magnitude only: 235–267 switches, about 65 000 route-cost rows and 0–3 agents remaining at 400 s per seed. They are neither equivalence nor timing references. The 3 min 18 s wall time came from 6 concurrent jobs.

**Stop rule.** If any activation is zero where "yes" is expected, stop that workload and report it. Do not change flags to make it run.

## 3. Equivalence (§8), declared before any data

**Method.** Exact equality on the same machine, build and interpreter, with `PYTHONHASHSEED=0`.
- Floats are compared as `repr` strings.
- Trajectories use `scripts/ab_trajectories.py`, or the same row-wise check on `trajectory_data`: `frame, id, pos_x, pos_y, ori_x, ori_y`.

**Outputs compared**:
- `metrics`, excluding wall-clock and path fields;
- the manifest `outcome`;
- the exit code and the summary line;
- exit history, route history (`old/new_exit`, cost, reason);
- route-cost history (when on), FED history (doses, FIC, `incapacitated`, cause);
- smoke history (when on);
- the per-agent removal frame (the last trajectory frame);
- the spawn count per origin.

For W3 and W4-cmm, `cognitive_map_history` must also be compared. The CLI does not write it, so equivalence runs must save `ScenarioResult.cognitive_map_history` through a `build_run_kwargs` harness.

**Excluded fields.** Timestamps, absolute paths, temporary file names, progress-line wall times, and the vismap cache's `fds_dir` metadata.

**Determinism gate, first.** Two uninstrumented baseline runs at the same seed must be identical. If they are not, stop and investigate. No tolerance may be introduced afterwards.

**Tolerance: none.** Instrumentation and cache-state variants (vis cache built, loaded or absent; fdsreader pickle present or absent) are behaviour-preserving claims, so any difference is a defect. Cross-platform equality is not required.

**Behavioural changes are classified, not tolerated.** Any of these is a changed workload: fewer spawned agents, altered exits, missing histories, earlier termination.

## 4. Comparison labels (§7)

| Comparison | Label |
|---|---|
| W1 gate vs sb vs nf vs add | End-to-end. `sb` is expected to match `nf` in trajectories but samples the fire; this was verified at `7e9c4c30` and must be re-checked. Never subtract arms. |
| W1 N = 100/200/400 | End-to-end scaling. Report time per measured agent-step. |
| Rerouting off, other reroute intervals, discovery vs full, anticipate off | End-to-end. Changes behaviour and is a model/accuracy tradeoff. |
| W1 normal vs minimal output | Controlled cost experiment, valid only if trajectories and exits match exactly (untimed check run keeps `--output-sqlite`). |
| W3 vis cache first-use / repeated / no flag; fdsreader pickle absent/present | Controlled cost experiment, conditional on exact equality. |
| Steering pass, smoke/FED/routing/visibility timers inside W1/W2/W3 | Controlled cost experiment (instrumented, unchanged run). Overhead ≤ 5 % or diagnostic-only. |
| Sampling-query replay | Controlled kernel experiment; does not establish an end-to-end speedup. |
| Native JuPedSim journeys vs W2 | Diagnostic architectural comparison. |
| #430 cases at `4f859bf5` | Historical link to another revision, not a baseline. |

**Scaling family.** W1 at 100, 200 and 400 agents:
- this gives 0.44, 0.87 and 1.74 /m² in the 229 m² hall;
- the window is 0–400 s;
- seed 1 with the full repetitions, plus seeds 2 and 3 at 3 repetitions each.

Expected confounders:
- more agents still inside at 400 s as N grows;
- door queues;
- different route-switch counts.

These are workload effects, not evidence of complexity. If 400 agents cannot be placed, use 300.

## 5. Open questions for the coordinator

1. *(Closed in §8/§9.3: committed 300 s deck.)* Approve the W3 cap at 270 s. Also decide whether to spend one diagnostic run of the committed 300 s deck to confirm the horizon prediction.
2. Approve the W4-cmm cap at 120 s.
3. Freeze on CPython 3.12. It keeps scikit-image 0.23.2, the version fdsvismap pins; 3.13 and 3.14 swap in 0.26.0. Use a fresh worktree at `6fd7878c` with its own `uv sync --frozen` venv. The 3.11 venv of `main_f5c6` is no longer supported.
4. Set `$STAGE`, a local directory of about 1.1 GB outside sciebo, with a fixed path. The vismap cache key includes the resolved `fds_dir`.
5. Decide whether the W2 #430 historical case is worth one run, labelled as historical.

## 6. What perf-engineer must check

- Stage the FDS copies without `*.pickle` and verify them against `preflight/input_hashes.json`. This includes the ISO `fds/` directories committed in the worktree. *Corrected (§10.3):* a pickle written there does **not** make `git_dirty` true (`.gitignore` covers `assets/**/*.pickle`); stage anyway so that the cache state is controlled.
- Never run from sciebo or from the user's checkout.
- Run the G0 normal runs of W1, W2 and W3 serially and fill the activation table in §2.
- Add counters for vismap build/load, sign queries, cognitive-map updates, field samples per caller, and route searches/edges. W3 cannot pass preflight on log lines alone.
- Verify `dt = 0.01` from `simulation.delta_time()` in one run.
- Build any in-process harness with `build_run_kwargs` on a `run.py`-parsed Namespace.

## 7. What perf-qa must check

- The determinism gate passed before any instrumented comparison.
- Every run manifest matches the commit, the lock hash and the input hashes.
- The derived configs differ from their bases only in the one stated key (re-run `scenarios/make_derived.py`; hashes in `scenarios.json`).
- No run used `--allow-fds-horizon-hold` or a relaxed coverage setting.
- The W4 pytest set ran with zero skips of FDS-dependent tests.
- Every comparison carries the label from §4.

## 8. G0 resolution

These decisions are based on `engineer_handoff_g0.md` §4. No timed runs were made.

### 1. W3

**Window.** Use the committed 300 s deck, `assets/t_junction/config_discovery.json` (sha `f55444ae…`), for every seed.
- Seed 42 refuted my horizon prediction. Route pricing ran only between 7 and 43 s, and the latest bound was 56.8 s against the 301 s guard.
- The committed deck needs no derived input, so it is preferred.
- Keep `scenarios/w3_t_junction_cap270/` only as a fallback.

**Settle the horizon question with seeds 43 and 44 (untimed).** These are W3's confirmation seeds, so the runs serve both purposes. Same flags as the G0 diagnostic.
- If either run raises `FdsHorizonError`, or its bound `max(time_s + path_length_m / 1.3)` exceeds 296 s (a margin under 5 s), switch every W3 seed to the 270 s cap.
- One window must apply to all W3 seeds. Never add `--allow-fds-horizon-hold`.

**Is it acceptable as a visibility workload?** Yes, with conditions. It is a sign-discovery workload in smoke. It is not a routing or throughput workload.
- **80 inside and 50 never spawned.** These are properties of the deck: flow spawning runs from 0 to 400 s against a 300 s cap, and the smoke is heavy. Label the run "time-limited, incomplete".
- **Count work over spawned agents only.** Agent-steps and per-agent rates use the agents actually processed at each tick. The 50 unspawned agents are neither "remaining" nor work done.
- **25 agents whose target is not an exit.** These are discovery agents that never learned an exit and patrol their known nodes (`wander`, 170 of 180 switches). This is the mechanism W3 is meant to exercise, not a defect: they keep querying sight and growing their maps.
  - Exit history records their current target, so 25 non-exit rows are expected.
  - Equivalence must compare these rows like any other.

**Acceptance condition, checked in the G1 baseline.** The G1 counters must show all of the following:
- sign-visibility queries > 0, both after 43 s and in total;
- cognitive-map growth events > 0;
- vismap built, or loaded, exactly once per process.

If the queries turn out to be negligible, W3 does not exercise visibility. In that case, use the W4-cmm clear-air case as a second visibility kernel, accepting that it is small. I know of no other existing fire case with discovery agents.

**Counters W3 needs.** They are observational, aggregated per run, and contain no per-sample logs.

| Counter | Where | What |
|---|---|---|
| Vismap cache state and time | `visibility._resolve_vis` | built (`_build_vismap` / `compute_all`) vs loaded (`np.load`) vs metadata mismatch rebuild; seconds; time-point count, number of signs, grid shape |
| Sign queries | `VisibilityModel.node_is_visible`, `visibility_to_node` | calls, `True` results, calls past the grid, calls by caller (`expand_on_arrival` vs `_expand_visible`) |
| Map growth | `cognitive_map._expand_visible`, `expand_on_arrival`, `_learn_edge` | nodes and edges added; agents with ≥ 1 known exit per 10 s bin |
| Discovery state | reroute pass in `scenario.py` | eligible agents per tick by mode (path / wander), and route evaluations, not only switches |

### 2. W1: the 400 s window

**Keep the 400 s window.** Label W1 "time-limited, 400 s observation window". With 1 agent inside, the outcome is incomplete. The final timestamp is not an evacuation time.
- The window is the study design (maintainer decision 2). Earlier runs had 0–3 agents inside at 400 s.
- Extending the window changes the workload and moves the anticipated bound (430.6 s now) towards the 481 s guard.
- Coverage and horizon checks stay as they are.

**What G1 reports for W1.**
- The remaining agent's state (inside, FED, last target) as an outcome.
- Termination as part of equivalence: the exit code 2 and the counts 199/1/0 must match exactly across variants.

### 3. Other confirmations

- **Horizon bound.** The engineer is right. `path_length_m / base_speed_m_per_s` is the anticipation offset that `_arrival_time` uses. `travel_time_s` contains other terms and is not the sampling time.
- **W2 with 0 route switches** is expected. Clear-air costs do not change over time because `w_queue` is 0. Rerouting passes still run every 1 s, so G1 must count route evaluations in W2 to show that the routing work is present.

## 9. Answers to engineer_handoff_g0.md §9.4

This section rests on reading the code at `6fd7878c` (`wt6`) and on the outputs of `g0_*` and `dev_counters_w3_s42`. No runs were made.

### 9.1 Route-cost history: part of normal W1 output

**The route-cost history belongs to the normal output.** The study writes it for the `gate` and `add` arms (`run_p1.sh`, `--output-route-cost-history`). The study's τ figure, `p1_tau`, is built from the `tau_route` column of that output. So the W1 command in `scenarios.json` is the normal output as it stands.

**Three output variants**, with every other flag identical:

| Variant | Flags | Use |
|---|---|---|
| `O_study` (normal) | W1 command as in `scenarios.json`: SQLite copy, route, exit, route-cost and FED histories | Headline and baseline |
| `O_norc` | `O_study` without `--output-route-cost-history` | Isolates the cost of the route-cost history: the second `rank_routes` per evaluation at `scenario.py:2685-2741` and its CSV |
| `O_min` | No `--output-*` flag, with `--cleanup` | Minimal user cost |

The temporary trajectory SQLite is written in every variant. It is fixed in `run_scenario` (`every_nth_frame=10`). `collect_cognitive_map_history=True` is also always on in the CLI.

**Variants count as controlled cost experiments only if they pass an exact-equivalence check.** Before timing them, run each variant once, untimed, with `--output-sqlite` and `--output-exit-history` added. Compare the trajectory rows, the exit history and the exit code with `O_study`. Compare the route history too where it is written.

**Why this check matters here.** The two `rank_routes` calls of one evaluation share `route_segment_cache` (`scenario.py:2698`, `2759`).
- With anticipation, its key buckets the arrival time to the second: `(src, tgt, round(t_arrive))` at `route_graph.py:1280-1281`.
- The value stored under that key is computed at the exact `t_arrive` of the first caller (`route_graph.py:1287-1297`).
- So the cache contents seen by later agents in the same pass can depend on whether the history ranking ran first.

I have not shown that this changes any output. If `O_norc` is not identical to `O_study`, then:
- the route-cost history is not observational;
- the output comparison becomes end-to-end;
- the cause is a candidate issue for the backend team (order-dependent cache values). It is not a profiling fix.

### 9.2 W3: agents leave through exits they never knew

**This is a known model defect. It is not a gap in the engineer's exit list.**
- The list `{exit_A_left, exit_B_right}` is correct: the deck has exactly these two exit stages.
- `agents_with_known_exit` = 12 matches the route-cost data. Only agents 1–12 have route-cost rows, because `rank_routes` returns rows only over known exits. These are the agents spawned before the smoke hid the signs.

**Evidence from `dev_counters_w3_s42`:**

| Group | Count | Route-cost rows | Route history |
|---|---|---|---|
| Removed at `exit_A_left` (x < 1.5) | 10 | yes (agents 1–12 set) | `smoke_reroute` B→A |
| Removed at `exit_B_right` (x > 28.5), knowing an exit | 2 | yes | none |
| Removed at `exit_B_right`, no exit in their map | **58** | **none** | **none** |

Among the 58, the first are agents 29–36, 38–44, and so on. Agent 29 spawned at frame 561 (56.1 s) at (21.48, 3.71), passed the junction, and was removed at frame 902 (90.2 s) at (28.97, 12.39). It has no route-cost row and no route-history row.

Of the 80 agents still inside at 300 s, the exit history gives 55 heading for `exit_B_right`, 15 for `jps-distributions_0` and 10 for `jps-checkpoints_0`.

**Mechanism at `6fd7878c`:**
1. Each agent receives the geometrically nearest exit as its steering target before its cognitive map exists: `simulation_init.py:1552` `_find_nearest_exit`. Here that is `exit_B_right`, 10 m from the junction.
2. The opening choice replaces that target only when the map holds a reachable exit. Otherwise "the geometric assignment is left in place" (`scenario.py:1029`; `_assign_initial_exit` returns `None`).
3. Most maps start with only the spawn node:
   - `cognitive_maps_created` = 150 and `init_known_nodes` = 170;
   - the spawn node counts as visited, so there is no frontier (`frontier_none` = 14 040);
   - the patrol excludes the current node, so it finds no stop (`wander_none` = 9 177; `route_graph.py:2696-2709`);
   - the decision is therefore "keep", and the agent walks on to the geometric exit;
   - direct steering removes it on reaching that exit polygon.

**Documentation.** `site/content/models/wayfinding.md` (§2.4 "Exception", and Limitations) and `docs/concepts.md` state this as "a defect, not intended behaviour". It is open as issue **#91**.

**Consequence for W3.** The workload remains valid for profiling, because the defect is the current behaviour at the frozen commit and every variant must reproduce it exactly. The report has to describe W3 accurately:
- 12 agents route on learned exits;
- the rest explore or patrol, or walk to an exit they never learned (#91);
- the evacuated count is not evidence of successful wayfinding.

Nothing to fix under this assignment, and no new issue to file: #91 already covers it.

### 9.3 W3 window

**Closed.** The committed 300 s deck applies to all W3 seeds.

| Seed | Latest anticipated sample | Guard |
|---|---|---|
| 42 | 56.8 s | 301 s |
| 43 | 58.8 s | 301 s |
| 44 | 57.8 s | 301 s |

None of the three raised `FdsHorizonError`. `scenarios/w3_t_junction_cap270/` is kept only as an unused fallback.

The §8 acceptance condition is met in substance in the dev smoke run:
- 21 169 sign queries, continuing throughout the run;
- 133 map-growth events;
- one vismap build.

The G1 baseline confirms it formally.

## 10. Response to review.md (G0 PASS): I2, I1, O2, O4

This section is read-only analysis. No runs were made.

### 10.1 I2: W3 activation condition and label (replaces the "met in substance" in §8 and §9.3)

**W3 label:** "Visibility work measured, mostly under fully obscured sight."
- From about 60 s, the smoke vismap is almost entirely dark for all 3 signs (visible-cell fraction 0.002 or less).
- From 100 s it is fully dark.
- 87 % of the sign queries come after 100 s and therefore return False by construction.
- The query *cost* is still real and is counted. What W3 does not exercise after about 60 s is learning that depends on legibility.

**Restated activation condition for G1.** It needs the engineer's split counter. All of the following must hold:
1. One vismap build or load per process, as before.
2. Sign queries by agents on the grid that return True > 0, counted for nodes with a sign descriptor only, binned in time. Expected: only in the bins before about 60 s.
3. Map growth from `_expand_visible` with sign-visible True > 0.
4. The non-sign True count and the off-grid count are reported separately and never added to item 2.
5. The share of sign queries made while the vismap has zero visible cells is reported. This is the denominator for "obscured" in the label.

If item 2 or item 3 is zero, W3 measures visibility *cost* only, and the report says so.

**cognitive_map_memory: yes, add it as the second visibility case (W4-cmm promoted to "W3b").**
- It is the only existing case where sign legibility discriminates throughout the run: the vismap is built from a smoke-free FDS run, so the geometry and sign bearing decide.
- Every agent switches once, after learning the side exit.
- It uses the FDS-built `VisibilityModel`, so the existing hooks apply.
- It is small (20 agents, about 21 s simulated). Label it "visibility kernel and learning check, not throughput".
- Run it with the commands in `scenarios.json` (`w4_cmm_visibility`, arms A/B). For timing, use the cap-120 arm B only. It gets the same counters, with the same activation items 1–5, and item 2 is expected > 0 across its whole run.

### 10.2 I1: definition of the fdsreader cache states

fdsreader 1.11.7 uses the pickle only for the first `Simulation()` opened in a process. Later opens in the same process re-parse the `.smv` and rewrite the pickle (review I1). The states are therefore defined by what exists when the process starts, and are confirmed by counters:

| State | Definition at process start | Expected counters | Label |
|---|---|---|---|
| fdsreader first use | `<chid>.pickle` absent in the staged FDS dir (removed by the harness from the stage only) | pickle loads = 0, parses = n_opens | "no fdsreader cache" |
| fdsreader repeated use | `<chid>.pickle` present, written by the previous run of the same code, lock and staged path | pickle loads = 1, parses = n_opens − 1 | "fdsreader cache present (first open only)" |

Rules for both states:
- Record per run: `pickle_present_before` (and its size, mtime and sha256), the number of opens, loads and parses, and `pickle_present_after`.
- A run whose counters do not match its declared state is relabelled, not discarded.
- The first-use vs repeated-use difference measures at most one `.smv` parse per process. Whether that is small is a hypothesis to be measured.
- Repeated parses within a process belong to the normal run in both states. They are a candidate finding (an upstream class-attribute behaviour). They are not to be removed or patched.

**Kept separate:**
- Vismap cache states (§1, `scenarios.json` W3 `cache_variants`): npz absent, present and matching, or no flag.
- OS page cache: uncontrolled, labelled "process-fresh, page cache uncontrolled".
- In-process reuse: a third workload, not used.

### 10.3 O2 and O4: corrections

- **O2.** I marked the 270 s text in §1, §2 and §5 superseded. D5 is closed: committed 300 s deck for all W3 seeds, bounds 56.8, 58.8 and 57.8 s. `plan.md` D5 belongs to the coordinator and needs the same update.
- **O4.** My §6 claim was wrong. A pickle in the worktree does not make `git_dirty` true, because `.gitignore` covers `assets/**/*.pickle` and the manifest ignores untracked files.
  - The W4 pytest set reads `$WT/assets/.../fds` directly (e.g. `tests/test_iso_table21_coupled.py:45`) and writes pickles there.
  - For pytest runs, record per directory whether the pickle exists before and after, and its hash, together with `git status --porcelain --untracked-files=all`.
  - Pytest results are correctness checks only, so this cache state need not be controlled, only recorded.

## 11. W3 label after the I2 follow-up; F3 equivalence list

### 11.1 W3 label (replaces §10.1's label)

"Visibility work measured, mostly under near-total obscuration."
- After about 60 s, each sign is visible only from 1–4 grid cells within 0.25 m of it.
- 21 of the 18 398 queries made after 100 s return visible (perf-qa follow-up, `review.md`).
- The activation items of §10.1 stand, with one change: item 2 is no longer expected to be zero late, only near zero.

W3b (`cognitive_map_memory`) remains the case where legibility discriminates.

### 11.2 F3: outputs compared for equivalence (exact, per model §3)

Pairs are compared on the same build and interpreter with `PYTHONHASHSEED=0`. The pairs are:
- baseline vs counters;
- `O_study` vs `O_norc`;
- `O_study` vs `O_min` check run;
- cache-state variants.

Floats are compared as `repr` strings, with the row order as written.

| # | Output | Source | Rule | Excluded |
|---|---|---|---|---|
| 1 | Trajectories | `trajectory_data` in the copied SQLite | Rows `frame, id, pos_x, pos_y, ori_x, ori_y`, ordered by `frame, id`, all equal. A single recorded recipe (O3) | Other SQLite tables with paths or timestamps (`metadata`) |
| 2 | Per-agent removal frame and spawn frame | Derived from 1 (`max(frame)`, `min(frame)` per id) | Equal | — |
| 3 | Exit history | `*_exit.csv` | Byte-equal | — |
| 4 | Route history | `*_rh.csv` | Byte-equal | Not written by `O_min` (check run adds it) |
| 5 | Route-cost history | `*_rc.csv` | Byte-equal | Only where written: not in `O_norc` / `O_min` |
| 6 | FED history | `*_fed.csv` (doses, FIC, `incapacitated`, cause, speed factors) | Byte-equal | Only where written |
| 7 | Smoke history | `--output-smoke-history` | Byte-equal | W4-iso21 only |
| 8 | `agent_scalars` table | SQLite (written when the FED history exists) | Rows equal | — |
| 9 | Outcome | Manifest `outcome`, `fds_coverage`, `seed`, `agent_seeding`, `versions`, `uv_lock_sha256`, `git_commit` | Equal | `created_utc`, `scenario_path`, `fds_dir` (paths); the whole app manifest file hash |
| 10 | Exit code and summary line | `exit_code`; `Simulation finished` / `incomplete` line, plus "Route switches: N" and "Route cost samples: N" | Equal | Progress lines (wall times), warnings carrying paths |
| 11 | Vismap arrays (W3, W3b) | `.npz` arrays, compared array by array | Equal | Metadata `fds_dir` |
| 12 | Cognitive-map history (W3, W3b) | **Not written by any CLI output.** It exists only as `ScenarioResult.cognitive_map_history`; the CLI collects it (`run_config.py:609`) and discards it. Only the count `metrics["cognitive_map_events"]` (`scenario.py:3094`) exists, and it is also not written | Rows `time_s, agent_id, familiarity, known_nodes, known_edges` equal | — |

**How to obtain item 12.** The engineer extends `perf_run.py` with an opt-in observational dump (`PYFDS_PERF_CMAP_OUT`, say).
- It wraps `pyfds_evac.core.scenario.run_scenario` and, after it returns, writes `result.cognitive_map_history` and `result.metrics` to JSON.
- It does not change arguments or the return value, and with the variable unset it is inactive.
- Because this dump changes the entry point (`runpy`), compare item 12 only between two runs that both go through `perf_run.py`, with the dump on for both. Items 1–11 still compare plain `run.py` against the instrumented run.
- If this is not built before G1ovh/G1out, record "cognitive-map state not compared" as a named gap in every W3 equivalence verdict. Do not treat it as passed.

**Verdict rule.** Any difference in items 1–12 means the pair is not equivalent, and the variant is labelled end-to-end (§4). There are no tolerances.
