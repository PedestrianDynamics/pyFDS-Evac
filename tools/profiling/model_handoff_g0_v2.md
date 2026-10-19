# perf-model handoff, gate G0 v2 (re-freeze at pyFDS-Evac main 8f7d29a2)

Supplements `model_handoff_g0.md` (v1, frozen at v0.2.0 `3ef4ea75`). Where this file is silent, v1 stands. Purpose of the round: the 0.6.0 perf track, measure before fixing #236, #241, #242, #243, #739, #429 (umbrella #244).

Inputs: pyFDS-Evac `8f7d29a2` (`v0.5.0-98`, pyproject version 0.5.0), repo `/Users/chraibi/workspace/PedestrianDynamics/Fire/fds_visibility/pyFDS-EVAC` read-only; `uv.lock` sha256 `7f64a58d…`, `pyproject.toml` `b323bc2a…`, `run.py` `ccb6d4a3…` (17-line shim; the CLI is `pyfds_evac/cli.py`, the parser `pyfds_evac/config/parameters.py`). Installed in the maintainer's `.venv` (CPython 3.12.13): jupedsim 1.4.2, fdsreader 1.11.7, fdsvismap 0.3.2, shapely 2.1.2, numpy 2.4.4, scikit-image 0.26.0. No simulation was run; only `--show-config` (setup, no loop).

## 1. Workload re-validation

### 1.1 Configs still load

All G0 inputs are byte-identical to `preflight/input_hashes.json` (config_gate, geometry.wkt, a047 .fds, config_discovery, t_junction geometry, cmm config and geometry, iso21 config, iso22 config_a). Only `run.py`, `uv.lock`, `pyproject.toml` changed.

`--show-config` at `8f7d29a2` (exit 0 = would run):

| Case | Result | Routing block as parsed |
|---|---|---|
| W1 `config_gate.json` + a047 | 0; smoke, gas FED, tenability, rerouting 1 s on; visibility off | anticipate True, base_speed 1.0*, gate, w_smoke 1.0 |
| W2 same, no `--fds-dir` | 0; rerouting on, everything else off | same |
| W3 `config_discovery.json` + fire_2MW_PVC | 0; visibility on, smoke-aware, 3 signs, step 1.0 s | w_smoke 5.0*, w_fed 10, w_queue 0, fed_rejection 1.0, vis_ext 0.5, step 2.0, base_speed 1.3, capacity 1.3 |
| W3b cmm base (cap 300) + clear_air | **1**: `max_simulation_time=300 s runs past the FDS output (120 s, interval 2.1 s)` | w_smoke 0*, w_fed 0* |
| W3b cmm cap120 (`scenarios/w4_cmm_cap120/config_cap120.json`) | 0 | same |
| W4 iso21 (+`--smoke-update-interval 0.1`) | 0; smoke speed only, FDS "interval 100 s" | n/a |
| W4 iso22 a | 0 | n/a |

Removed routing keys (`tau_return_margin`, `path_switch_anchor`, `fed_return_margin`, `fallback_return_lockout_s`) now raise `ValueError` (`route_graph.py:869-897`); none of our decks sets one. New routing keys take defaults: `exit_switch_anchor` 0.9, `current_exit_discount`, `clean_exit_margin` 0.1, `tau_deadband`, `fallback_switch_margin`, fallback rule `tau`/`hold` (#696), `impassable_extinction_threshold` 3.0 (additive only). `simulationParams.smoke_slice_height` is a new deck key; none of our decks sets it, so 1.6 m applies everywhere. `simulationParams.dt` (cmm: 0.05) is explicitly **not read** (`simulation_init.py:1117`); dt stays JuPedSim's 0.01.

### 1.2 Code changes since v0.2.0 that change the executed workload with identical inputs

G0 run outputs (`results/raw/g0_*`, `dev_counters_w3_s42`) are therefore activation expectations only, not references.

| Change | Effect on W1–W4 |
|---|---|
| #653/#736 route smoke read once per FDS grid cell (`line_parts` + `read_cells`, `_LINE_CACHE_SIZE` 65536) | route costs change; route extinction no longer goes through `SliceFieldSampler.sample` (see #242) |
| #678 foresight samples read on arrival; `_cap_at_fds_end`; cache key exact `(src, tgt, t_arrive, foresight_limit)` | v1 §9.1 `round(t_arrive)` order concern is gone; fewer cross-agent cache hits in `rank_routes` |
| #187 stage 2 margins (39a97fb1) | gate switching hysteresis; W1 switch counts will differ from G0 |
| #663 look from a node point before a patrol; #658/#610 `no_known_exit` modes (default unchanged: geometric exit; #91 closed as modeller knowledge) | W3 discovery agents walk to a node point before patrolling; new log line "Looks from a node point before a patrol: n, given up: m" |
| #726 checkpoint reached inside its polygon | W1 door stages (doorA/B) arrival timing |
| #710/#738 flow spawns keep 2 x max radius from placed agents | W3 spawn positions/ids may differ; `metrics.flow_spawns_deferred` |
| #728 spawn keys / fill modes; #742 end when flows closed and empty (`end_reason`) | W3 window ends 400 s > cap 300 s, so `end_reason` stays `time_limit` |
| #642 vismap time grid ends at the last FDS frame; cache format 6 | W3: 301 points (0..299, 300); W3b: 121 points |
| #479 fdsvismap 0.3.2; lock now pins scikit-image 0.26.0 on 3.12 | v1 freeze risk "3.12 keeps 0.23.2" is obsolete; one interpreter, one skimage |
| #720 fdsreader never touches the case folder | **fdsreader cache states no longer exist** (§1.4) |
| #240 (closed 2026-09-28, before v0.2.0) | already in the G0 baseline; `is_inside_polygon` now uses `shapely.intersects_xy` with a bbox pre-test |

### 1.3 Effective settings at 8f7d29a2 (what executes)

Common: CollisionFreeSpeedModel with the deck's parameters; dt 0.01 (JuPedSim default, `jps.Simulation` built without dt); trajectory SQLite every 10th frame always written to a temp file; `collect_cognitive_map_history=True` always; rerouting on at 1.0 s (CLI default; Python default 10 s), staggered per agent; vismap time step = reroute interval 1.0 s; smoke/FED update 1.0 s; sampling height 1.6 m (W3/W3b fall back to the 2.0 m slices with a warning; fdsvismap obstruction test still at 1.6 m); heat FED off; FIC slowdown off; incapacitation deterministic, FED 1.0, O2 20 %; coverage not required; no horizon hold. Horizon guard = last frame + output interval, where the interval is the **largest** frame spacing: W1 480 + 1.1 = 481.1 s, W3 300 + 1.2 = 301.2 s, W3b 120 + 2.1 = 122.1 s.

| | W1 `w1_gate` | W2 `w2_nf` | W3 `w3_tj_discovery` | W3b `w4_cmm_visibility` arm B |
|---|---|---|---|---|
| Cap / window | 400 s, time-limited | 400 s | 300 s, time-limited | 120 s (derived; base cap 300 fails preflight without the hold flag) |
| Spawning | 200 at t = 0, Weibull premovement | as W1 | flow 200 over 0–400 s, 28 m², 0.5 /s, r 0.15, v0 1.2 | 20 at t = 0 |
| Familiarity | full | full | discovery | discovery |
| Routing | gate, anticipate, base 1.0, w_smoke 1.0, E = 6 | gate on clear-air costs | gate, w_smoke 5, w_fed 10, base 1.3 | gate, w_smoke 0, w_fed 0 |
| Fields | K, CO, CO2, O2 at 1.6 m; T unused | none | K, CO, CO2, O2 (+HCl: FIC recorded) at 2.0 m | K, CO, CO2, O2 at 2.0 m, smoke-free |
| Visibility | off | off | smoke-aware, 3 signs, 301 points | smoke-aware, 2 signs, 121 points |
| Outputs | sqlite, rh, exit, rc, fed | sqlite, rh, exit | sqlite, rh, exit, rc, fed | sqlite, rh, exit, vis npz |
| Cache state | none (§1.4) | none | vismap npz: first-use / repeated / no flag | same |

### 1.4 Cache states: fdsreader state dropped

Every FDS open (`fds_sampling.py:21`, `fed.py:945`, `visibility.py:153`, `_build_vismap` via `fdsreader_without_cache`) runs with `settings.ENABLE_CACHING = False` and the pickle path redirected into a `TemporaryDirectory` (`fdsreader_adapter.py:76-106`). Consequences:

- every `Simulation()` open parses the `.smv`; there is no on-disk reader cache in any run, so v1 §10.2 ("first use = pickle absent, repeated use = pickle present") is void. Delete the fdsreader pair from the cache matrix; keep `opens`/`parses` as counters (repeated parses within a process remain a candidate finding).
- the sciebo pickles listed in `scenarios.json` `user_caches_untouched` no longer exist (`stat`: no such file; not removed by this task). A pickle in the staged copy is ignored (engineer: `pickle_present_at_open: true`, loads 0).
- staging stays mandatory (isolation, hashes), but for the vismap cache only; `fds_coverage`/horizon checks unchanged.

Remaining cache states: vismap npz (absent -> build+save; present and metadata-equal -> load; no flag -> build, never saved) and the uncontrolled OS page cache.

### 1.4a Decision: how G1 treats FDS opens (engineer finding 1)

Confirmed from the counters: W1 7 opens, W3 10, all full parses, pickle loads 0 although the staged `.pickle` exists.

- **G1 keeps one cache split only: the vismap npz (first-use / repeated / no flag) on W3 and W3b.** W1 and W2 have no cache state; label them "no application cache". Remove `--fds-cache first|repeated` from the matrix and from the manifest labels; `cache_label.counters_agree` must not be computed against pickle loads.
- **Repeated `.smv` parses are a setup sub-phase, not loop cost.** Report per run: `fdsreader_new_calls` (= parses), seconds per open, and the opener (smoke-speed sampler, FED field, heat, coverage/inventory, `_extinction_slice_index`, `_build_vismap` `read_fds_data`). Label the quantity "FDS opens per process (adapter policy #716/#720: cache off, every open parses)". It belongs to lifecycle "FDS parsing", mutually exclusive from the vismap build and from the loop.
- **Attribution for #241/#242.** The #241 kernel is `compute_all` + `_vis_metre_array` **after** `read_fds_data`; time `read_fds_data` separately so a parse is never counted as cache-build cost. #242 is loop-time sampling; parses do not touch it. In the lifecycle figure, parses appear once as their own bar.
- Candidate finding, not a fix: n opens where one would do. Record the count; do not patch.

### 1.4b Decision: W3 at 8f7d29a2 (engineer finding 2)

**Mechanism.** PR #658 (closes #610, #91) replaced the geometric exit seed by the distribution key `no_known_exit`, default `"default_route"` (`cognitive_map.py`, `DEFAULT_NO_KNOWN_EXIT`). In `evaluate_and_reroute` (`route_graph.py:4411-4432`), when `rank_routes` finds no exit in the agent's known subgraph, `_decide_no_known_exit` (`:4224-4260`) returns `_decide_default_route`: the agent keeps its scripted journey (`jps-distributions_0 -> jps-checkpoints_0 -> waypoint_routing 1 %/99 % -> exit_B_right`), logged once as `reason="default_route"`. `_decide_explore` (frontier, then patrol) is reached only under the opt-in modes `explore`/`return`/`stay`, which `config_discovery.json` does not set. That is why explore/wander/frontier are all 0 and why 99 agents leave: 12 learned an exit before the smoke hid the signs (route-cost rows exist only for them), the rest walked the journey to `exit_B_right`, 10 m past the junction, and are counted by `metrics.agents_left_by_unknown_exit` with `exit_in_map=False` in the exit history. The documentation calls this the FDS+Evac counterpart (follow the flow field) and modeller knowledge, not perception (`site/content/models/wayfinding.md:321-345`). It is intended behaviour, not a defect, and must reproduce exactly in every variant.

**Decision: W3 stays, relabelled.** "Sign-legibility workload in smoke under `default_route`; no exploration (opt-in modes off)." It is no longer an exploration or cognitive-map-growth workload and never was a throughput one. What it exercises, with the G0 v2 counts as expectations: one vismap build or load per process (301 x 3 x 53 x 121; build 0.46 s on the loaded machine), `node_is_visible` 14 123 sign queries (13 867 from `_expand_visible` at every reroute evaluation, 256 at arrivals), 364 positive, 34 + 111 sign nodes added, 12 agents with a known exit, 13 switches, 277 route-cost rows. Activation items for G1: (1) one build/load; (2) sign queries > 0 and positives > 0 in the bins before ~60 s; (3) `_expand_visible` growth > 0; (4) `explore = wander = 0` is **expected** and is not a stop; (5) `agents_left_by_unknown_exit` reported. If item 2 or 3 is zero, stop W3.

**For #236/#241 W3 proves activation, not magnitude.** Its build is sub-second. W3b (`cognitive_map_memory`, 121 x 2, clear-air FDS so every frame is identical) is the exact-dedupe case for #236 and stays. The issues' magnitude lives in `assets/fed_incap_co_2000ppm` (100 discovery agents, 24 checkpoints + 1 exit = 25 signs, 1000 s; sciebo `fed_incap_co_2000ppm/fds`, `demo_homogeneous_CO_2000ppm.smv`; `--vis-cache` or discovery agents trigger the build, `run_config.py:396`). Its full build (~70 min per #236) exceeds every cap, so I propose **V-build, a controlled kernel experiment**: time `_build_vismap` + `_vis_bool_array` + `_vis_metre_array` on the first n time points of that deck (n chosen so one repetition stays under the 900 s profiled cap), report seconds per (t, wp), `_get_visibility_array` calls (expect 2 n n_wp), `to_global` calls, and the number of distinct extinction frames (expect 1: sealed room, constant soot). Extrapolation to 1000 frames is stated as an extrapolation. The evacuation of that deck is not run. Coordinator decision; without it, the report says #236/#241 are confirmed active with sub-second builds on the selected workloads.

### 1.4c Outcomes of the smoke runs: expected at 8f7d29a2

- **W1 199/200 at 400 s, 1 inside, 0 unspawned:** same as G0 at v0.2.0 and the earlier seeds (0–3 inside). Expected; label stays "time-limited, 400 s observation window". The remaining agent's state (position, FED, target, premovement draw) is an outcome to report in G1, not a reason to extend the window. No horizon decision needed: the latest anticipated sample bound must still be computed from the rc CSV and be < 481.1 s.
- **W3 99/150 out, 51 inside, 50 not spawned:** expected order at this commit. PR #658 regenerated the same FDS case at 93/150 with 82 by an unknown exit; `assets/t_junction/README.md` (c619a046, `config_full`) reports 97/150. The 50 not spawned are the deck (flow to 400 s, cap 300 s). The exact 99 becomes the reference once the determinism gate passes; the v1 figure 70/150 belongs to the old routing and is retired.
- **W2 200/200 at 313.53 s:** complete, as before; 0 route switches expected (clear-air costs do not change; `route_switches` key absent or 0). Reroute evaluations 29 862 show the routing work is present.

### 1.5 W4

All 19 pytest files of v1 exist. Add to the mechanism set: `tests/test_route_grid_sampling.py` (#736 sampling), `test_foresight_arrival_time.py` (#678), `test_flow_spawn_spacing.py` and `test_flow_window_end.py` (#738/#742), `test_fdsreader_adapter.py` and `test_fds_read_only.py` (#720), `test_fdsvismap_adapter.py` (`_vis_metre_array` vs `get_visibility_to_sign`). `tests/test_routing_refactor_equivalence.py`, named in #242/#243 as the guard that "asserts cache contents and sampler call order", does **not** exist in this tree; the guards are `test_rerouting_golden.py` and `test_route_grid_sampling.py`.

## 2. Issue -> workload -> counters

Rule: a mechanism counts as active only when its counter is nonzero in the normal run of that workload. Zero where "active" is claimed is a stop for that pairing. All counters are observational aggregates (D9 wrappers); none may change arguments or return values.

| Issue | Mechanism at 8f7d29a2 (location) | Active on | Proof counters (per run) | Not active / caveat |
|---|---|---|---|---|
| **#236** vis cache recomputed per FDS step | `_build_cache_from_fds` -> `_build_vismap` -> `compute_all` over `_vismap_time_points(T_end, 1.0)` (`visibility.py:177-209, 629-665`) | W3 first-use and no-flag states (301 x 3); **W3b** first-use and no-flag (121 x 2, clear-air FDS: all frames identical, so dedupe gain is maximal here and near zero on W3's time-varying fire) | build seconds; `n_t`, `n_wp`, grid shape; number of **distinct** extinction frames among the time points (array_equal, computed outside the timed build); `_get_visibility_array` calls | W1/W2/W4-ISO: visibility off. Repeated-use state: `np.load` only, build cost 0 by design (label). W3's build is sub-second (0.46 s smoke): activation, not magnitude. Magnitude only via the V-build kernel experiment on `fed_incap_co_2000ppm` (§1.4b), coordinator decision |
| **#241** each frame computed twice | `compute_all` (bool) then `_vis_metre_array` calls `vis._get_visibility_array(wp, t)` again per (t, wp) (`visibility.py:541-565`) | same as #236 | `_get_visibility_array` calls = **2 x n_wp x n_t** (W3: 1806; W3b: 484); fdsvismap `to_global`/`get_extco_array_at_time` calls; seconds split compute_all vs `_vis_metre_array` | same as #236. Equivalence item 11 covers the `vis` and `metres` arrays |
| **#242** sampler index search per static point | `SliceFieldSampler.sample` (`fds_sampling.py:374-394`): `_find_subslice`, `_axes`, 2 x `_nearest_index` per call. Callers at `8f7d29a2`: per-agent smoke speed and gas FED (1 per agent-second per quantity); the **route FED midpoint** of every `evaluate_segment` (`route_graph.py:1518` -> `fed.sample_rate` -> `sample_inputs`, 3 quantities); `_polyline_stats` for degenerate (zero-length / one-point) polylines (`route_graph.py:760-776`) and off-grid points. Grid-cell route extinction goes through `line_parts` + `read_cells`, not `sample` | W1 (route-dominated), W3 (agent-dominated), W3b, W1r | **IV1 closed, `g0v2f_W1` (one untimed seed-1 run, detail counters re-keyed above `fed.sample_inputs`):** per-agent vs route: CO/CO2/O2 32 697 vs 723 391 each (route 95.7 %); extinction 32 697 vs 160 814 (`_polyline_stats`, 4 distinct points; route 83.1 %); all four 130 788 vs 2 330 987 = **94.7 %** of 2 461 775 `sample` calls. Distinct (x, y): route FED 37 473 per quantity (19.3 calls per point), per-agent 8 337 (3.9 per point). `read_cells` 725 445 calls / 22.7 M cells, `line_parts` 393 583 hits / 16 690 misses, outside these counts. W3: 9 352 of 11 831 per quantity are per-agent (79 %) | Call counts, not cost: no #242 time share until G2. W1's graph has 6 edges; the dense-graph magnitude is W1r's (324 678 gas per quantity; 105 079 `_polyline_stats`). Replay through the real sampler is valid only with values identical; #239 forbids reordering |
| **#243** segments re-sampled every pass and every flow spawn | `route_segment_cache = {}` at each reroute pass (`scenario.py:3263`); flow-spawn `_initial_exit_choice` passes no cache (`scenario.py:2794, 2884`; t = 0 agents share `_initial_segment_cache`, `:2047-2049`); `_generate_candidates` evaluates all E edges keyed `(src, tgt)` (`route_graph.py:2560-2580`); `rank_routes` keys exact `t_arrive` when anticipating (`:1802-1831`) | W1 (pass every 1 s, E = 6, ~200 path agents: misses = 6 per pass); **W3** is the only deck in the matrix with flow spawning (150 initial choices without cache; small graph) | `_generate_candidates` calls by caller (pass / t = 0 / flow spawn); `evaluate_segment` calls, cache hits/misses, new entries per pass; `rank_routes` and `evaluate_route` calls; eligible path agents per pass | W1/W2 have no flow spawning. Flow decks in the repo: `t_junction/config{,_full,_discovery}.json`, `l_corridor/config.json`. The issue's magnitude needs a dense graph: sciebo `world100/evac_4exits/deck_config_stream_east.json` (120 flow agents 0–240 s, 40 checkpoints, 4 exits, **WarpDriverModel**, 330 s) with `fire_4p5MW`. Optional companion "W1r", a different workload (different movement model), end-to-end label, full preflight first |
| **#739** waiting flow checks every candidate each step | `_flow_source_due` true every step while agents remain, the next spawn is due and the window open (`scenario.py:905-921`); on no free position `_defer_flow_spawn` and retry next step with `_occupied` + `_crowds_agents` per candidate (`:2550-2565, 2710, 2909`) | **none of W1–W4.** W3's flow (0.5 /s into 28 m², r 0.15) is uncrowded: expected `flow_spawns_deferred = 0` | `metrics.flow_spawns_deferred` (> 0 required), "Flow spawning: '…' found no free position at N steps" line; `_occupied` and `_crowds_agents` calls; candidates per attempt; spawn-block seconds | Smallest activating deck: none shipped. Repo fixture `tests/test_flow_spawn_spacing.py::test_a_full_area_defers_the_flow_and_reports_it` (4 standing + flow of 5, 1 s) proves the mechanism but is too short to time. Define a derived W4 fixture `w4_flow_saturated` from `config_discovery.json`, clear air (no `--fds-dir`), familiarity full, one extra distribution on the same 28 m² polygon: 150 standing agents with constant premovement 100 s, flow of 300 over 0–60 s (the issue's synthetic). Acceptance: `flow_spawns_deferred > 0` for >= 1000 steps and exit 0 or 2. Label "controlled mechanism fixture, not throughput". The engineer builds it with `scenarios/make_derived.py`; I review the diff |
| **#429** shapely `Point` per agent per step | `distance_to_polygon` builds `Point` per call (`direct_steering_runtime.py:133-141`), from `reached_stage` for every path agent whose target is an exit with a polygon, every step (`scenario.py:3460`); `is_inside_polygon` no longer builds a Point | W1 and W2 (agents past their door target exit_E/F), W3 (most agents target exit_B_right from spawn), W3b | `reached_stage` calls per step by stage type; `distance_to_polygon` calls (expected ~ exit-bound agents x steps); steering-pass seconds vs wrapped `iterate()` (existing instrument) | The 2026-09 76–80 % steering shares (#429, `backend_task_429_steering_perf.md`) predate #240 and v0.2.0; re-measure, do not cite. W2 is the designated steering workload |

## 3. Equivalence contract at 8f7d29a2 (replaces v1 §3 / §11.2 where listed)

Unchanged: exact equality, same machine/build/interpreter, `PYTHONHASHSEED=0`, floats as `repr`, determinism gate first (two plain runs identical), **no tolerance**, every difference classifies the pair as end-to-end. Reason the no-tolerance rule still holds: all six mechanisms are claimed observational; #239 is an order dependence, so a variant that reorders sampler calls is a changed computation, not a case for a tolerance.

Files and names: same flags, same files (`*_rc.csv`, `*_fed.csv`, `*_rh.csv`, `*_exit.csv`, smoke CSV, SQLite copy, manifest next to the trajectory file, vismap `.npz`). Column sets now:

| # | Output | Rule / change |
|---|---|---|
| 1–2 | `trajectory_data` rows, spawn/removal frame per id | unchanged (`scripts/ab_trajectories.py` exists) |
| 3 | exit history | byte-equal; columns `agent_id, origin, spawn_index, exit_id, exit_in_map` (`exit_in_map` new, #610) |
| 4 | route history | byte-equal; `time_s, agent_id, old_exit, new_exit, old_cost, new_cost, reason` |
| 5 | route-cost history | byte-equal; `time_s, agent_id, source, current_exit, current_fed, route_rank, exit_id, path, path_length_m, k_ave_route, travel_time_s, fed_max_route, composite_cost, rank_cost, k_max_route, tau_route, k_leg_max, clean, feasible, rejected, rejection_reason, queue_time_s, exit_count, exit_capacity` |
| 6 | FED history | byte-equal; adds `fic, fic_speed_factor, incapacitation_cause, heat_*`; heat endpoint columns only with heat FED |
| 7–8 | smoke history (iso21), `agent_scalars` | unchanged |
| 9 | manifest | compare `outcome` = `{status, end_reason, agents_remaining, agents_not_spawned}`, `fds_coverage`, `fds_outside`, `seed`, `agent_seeding`, `versions`, `uv_lock_sha256`, `git_commit`, `git_dirty=false`; exclude `created_utc`, `scenario_path`, `fds_dir` |
| 10 | exit code and summary line | `Simulation finished in X s (a/b evacuated).` or `Simulation incomplete: time limit reached|flow windows closed after X s (a/b evacuated, r remaining[, n not spawned]).` The CLI no longer prints "Route switches: N" (an agent's first decision is not a switch, #733); `Route cost samples: N` is printed only with the rc flag. New W3 line "Looks from a node point before a patrol: n, given up: m" (logger) is compared as text |
| 11 | vismap npz | arrays `vis`, `metres`, `time_points`, `x_coords`, `y_coords`, `output_interval_s` equal; `meta` equal except `fds_dir`; `format` must be 6 |
| 12 | cognitive-map history | still not written by any CLI output (`run_config.py:610` collects, `run_outputs.py` discards); the `perf_run.py` opt-in dump remains the only source, or the named gap |
| 13 (new) | `result.metrics` via the same dump | `end_reason`, `agents_evacuated/remaining/not_spawned`, `flow_spawns_deferred`, `agents_left_by_unknown_exit`, `route_switches` (key present only with history rows), `route_cost_samples`, `cognitive_map_events`, `fed_max`, `smoke_history_samples`, `fed_history_samples`, `fds_outside`; exclude wall-clock fields |

Pairs: baseline vs counters; `O_study` vs `O_norc` vs `O_min` (v1 §9.1 still applies, but the `round(t_arrive)` mechanism I named there is gone: keys are exact now, so an `O_norc` difference would need a new explanation before it is filed); vismap cache states (absent / present / no flag); `w4_cmm` arm A (cap 300 + hold) vs arm B (cap 120), arm A must log no hold. The fdsreader pair is removed.

## 4. Comparison labels (additions to v1 §4)

| Comparison | Label |
|---|---|
| W1r world100 stream deck vs W1 | different workload (WarpDriver, 368 edges); end-to-end; never a W1 scaling point |
| `w4_flow_saturated` | controlled mechanism fixture for #739; count `_crowds_agents` work inside the unchanged run; no throughput claim |
| Vis cache first-use vs repeated vs no flag (W3, W3b) | controlled cost experiment, conditional on item 11 and items 1–10 equal |
| V-build on `fed_incap_co_2000ppm`, first n time points | controlled kernel experiment; per-(t, wp) cost; extrapolation labelled; no evacuation run, no end-to-end claim |
| FDS opens/parses per process | lifecycle sub-phase "FDS parsing", reported per opener; never inside the #241 kernel or the loop |
| Any run on the old G0 outputs | not comparable (§1.2) |

## 5. Handoff

**Inputs/commit.** `8f7d29a2` as above; profiling package v1 files; `engineer_handoff_g0_v2.md` and `results/raw/g0v2_*` (counters.json, manifest.json, stdout.log; not measurements); issues #244, #236, #241, #242, #243, #739, #429 (all open), #240/#91/#653/#710/#742/#750 closed, #239 open; PR #738.

**Files produced.** This file only. `scenarios.json` is **not** updated yet; it needs: `target` block (commit, lock/pyproject/run.py hashes, versions, freeze risk rewritten for skimage 0.26.0), `global_rules.fdsreader_cache_states` and `user_caches_untouched` removed (§1.4), `cli_vs_python_defaults` unchanged, W3/W3b `effective_settings.visibility` time points, new fixtures `w4_flow_saturated` and optional `W1r`. I will do that on the coordinator's go, after the engineer's first normal runs fix the activation numbers. Scratch: `scratchpad/showcfg.sh`, `showcfg2.sh` (the `--show-config` calls).

**Commands executed.** `git` log/diff/hash checks in the repo; `gh issue view` for the issues above; `rg`/`sed` reads of `pyfds_evac/core/{scenario,route_graph,fds_sampling,visibility,direct_steering_runtime,fdsreader_adapter,run_config,run_outputs,manifest,simulation_init}.py`, `pyfds_evac/cli.py`, `pyfds_evac/config/parameters.py`; `.venv/bin/python run.py … --show-config` for the seven configs in §1.1 (sciebo FDS dirs read directly; `#720` guarantees no write, and no pickle appeared); sha256 of the configs against `preflight/input_hashes.json`.

**Observations.** Decisions for the coordinator are in §1.4a (fdsreader split dropped, parses as a setup sub-phase), §1.4b (W3 kept and relabelled; V-build proposed) and §1.4c (smoke outcomes expected). All four scenario families load; only the cmm base deck fails preflight (horizon), as in v1. The W1 FDS output interval is reported as 1.1 s (max spacing), not 1.0 s. #736 already removed the per-point sampler from route extinction, so #242's call volume at this commit is a different population from the issue's measurement. `_vis_metre_array` still recomputes every (t, wp). #739 is inactive on every selected workload.

**Uncertainties.** (a) W3 horizon bound (≤ 58.8 s at G0) is from the old routing code; #678 reads samples on arrival and caps at the FDS end, so I expect no `FdsHorizonError`, unverified. (b) W3 spawn count/ids under #738 unknown until the first run. (c) Whether the W1 route-cost arm (`O_norc`) is still observational is untested. (d) World100 deck preflight (coverage, 330 s cap vs FDS end) not done. (e) The `w4_flow_saturated` spawn capacity (150 + 300 in 28 m²) must pass `_check_spawn_capacity`; numbers may need to shrink.

**perf-engineer must check.** Build the worktree at `8f7d29a2` with `uv sync --frozen` (3.12, skimage 0.26.0); stage FDS copies and re-hash; drop `--fds-cache` and the pickle-based `cache_label` from the harness and record opens/parses by opener with seconds instead (§1.4a); time `read_fds_data` apart from `compute_all` + `_vis_metre_array` in every build; verify the instrument hooks still bind (`_resolve_vis`, `_build_cache_from_fds`, `_load_vismap_cache`, `node_is_visible`, `visibility_to_node`, `init_cognitive_map`, `expand_on_arrival`, `_expand_visible`, `nearest_frontier_target`, `wander_target`, `evaluate_and_reroute`, `rank_routes`, `evaluate_route`, `Simulation.iterate`, `run_scenario` all exist) and add the §2 counters (`sample` by caller, `read_cells`, `line_parts`, `_generate_candidates` by caller, `evaluate_segment` hits/misses, `_get_visibility_array`, `distance_to_polygon`, `_crowds_agents`, `flow_spawns_deferred`); run the G0 normal runs of W1, W2, W3, W3b serially and fill the activation table; confirm `dt = 0.01` from `simulation.delta_time()`; build `w4_flow_saturated` via `make_derived.py` and send me the diff before running it.

**perf-qa must check.** Determinism gate passed at `8f7d29a2` before any instrumented pair; every manifest has `git_dirty=false`, lock `7f64a58d…`, commit `8f7d29a2`; no run used `--allow-fds-horizon-hold` except cmm arm A; the fdsreader cache state is absent from every label and the `g0v2_*` W3 explore/wander zeros are not read as a stop (§1.4b item 4); each of the six issues is paired with a nonzero activation counter or an explicit "inactive on this workload" (#739 on W1–W4); W4 pytest ran with zero FDS-dependent skips; W1r, if used, is never pooled with W1.

---

## Appendix v2c (2026-10-14): fixture review, D20, D19, `scenarios.json`

Inputs: `engineer_handoff_g0_v2.md` §G0 v2b, `plan.md` D13–D20, `w4_flow_saturated.diff`, `results/vbuild_trial_n10.json`, `vbuild.py`, `results/raw/g0v2b_*` counters, installed fdsvismap 0.3.2 source. No simulations run.

### A1. `w4_flow_saturated.diff`: accepted with one amendment

Accepted: cap 200 s; `jps-distributions_0` as the flow (300 over 0–60 s, full); `jps-distributions_1` on the same polygon (150 at t = 0, constant premovement 100 s, full); `journey_1` with transitions and `waypoint_routing`; `make_derived.py` repointed to `8f7d29a2`, the four older derived configs byte-identical.

Amendment, required before the run: **revert the flow distribution's `use_premovement` to `false`.** Flow-spawned agents never receive a premovement entry at `8f7d29a2`: `premovement_times` is filled only in `simulation_init._add_agents` for agents placed at t = 0 (`simulation_init.py:3489, 3582`), and the flow block in `scenario.py` (2660–2910) sets none, so the key is inert and would mislead a reader of the fixture. The engineer's reason for adding it (the area would not fill) does not hold either way: saturation comes from the 150 standing agents, whose 2 × 0.15 m spacing discs (0.283 m² each, 42 m²) exceed the 28 m² area, so no flow candidate finds a free position while they stand; they stand for 100 s, past the 60 s window. Expected: deferral at nearly every step of 0–60 s (~6000), 300 not spawned, exit 2, `end_reason` `time_limit` or `flows_closed`. Acceptance unchanged: `flow_spawns_deferred ≥ 1000`, the "found no free position" line, `_crowds_agents` calls ≫ `_occupied` calls. **The engineer may regenerate and run it** (seed 42, clear air, command in `scenarios.json` W4). Record the new sha256.

### A2. D20: reconciliation of the V-build trial with #236/#241

The trial is the production path (`_build_vismap`, `_vis_bool_array`, `_vis_metre_array`, unchanged), same deck, same 61 × 61 grid and 25 signs as the issues. The difference is the **revision of fdsvismap**:

- #236/#241 were measured at pyFDS-Evac `6e70313` with fdsvismap `64d9aa7`, where `get_extco_array_at_time` called `self.slc.to_global()` per call (re-assembling the whole (n_t, nx, ny) series: O(n_t) per call, O(n_t²) per build at n_t = 1001) and `_get_mean_extco_array_at_time` looped over 3721 cells with one `np.sum` per ray. Those two terms are in the 0.862 s/frame of #241; how the ~70 min of #236 arose is not reconciled.
- fdsvismap 0.3.2 (pinned by #479) reads the slice once and keeps the time points in memory (`FDSVisMap.py:642-650`, docstring; the lazy read shows up as the engineer's `slice_read_lazy` stage) and computes the ray means with `np.add.reduceat` (`:698-720`). That is #241 half fixed upstream (the second pass and the dense storage remain). Hence 0.045 s per time point, ~50 s for the deck. This is a source reading, not a measurement at the old revision: the issue figures (70 min; 0.862 s/frame, which × 1001 is about 14 min, not 70) are retired as "measured at another fdsvismap revision, not reconciled" (D23).

What remains at `8f7d29a2`, and what V-build must therefore measure to speak to the issues:

1. **#241, second pass:** `_vis_metre_array` repeats `_get_visibility_array` for every (t, wp). Counter `_get_visibility_array` = 2 n_wp n_t (50 050 on the deck); seconds of `compute_all` kernel vs `_vis_metre_array` (36 % of the W3 build, 27 % of W3b, 9 % of the n = 10 trial, where `read_fds_data`/opens dominate). Report the split, not a speed-up.
2. **#241, storage:** peak RSS and the array sizes (bool 93 MB, float16 186 MB on the deck).
3. **#236, recompute regardless of change:** exact distinct-frame count plus the distribution of max |K_t − K_{t−1}| between consecutive time points (outside the timed part). The field is nearly constant, not bit-identical: soot extinction at 1.5 m spans 0.9992793–0.9992923 over 1001 frames (max consecutive change 1.3e-5 /m, `preflight/fed_incap_co_2000ppm.json`), so byte-equality finds 10 of 10 distinct (W3 300 of 301; W3b 1 of 121). An exact dedupe removes nothing on this deck; a tolerance dedupe is a model change (sight gating decides discovery), classified as such in the report, not measured as an optimisation here (D23).
4. Setup sub-phase apart: `_extinction_slice_index` open, `read_fds_data`, lazy slice read (D13).

**n = 1001** (the whole `_vismap_time_points(1000, 1.0)` list), so the runner's truncation is a no-op and nothing is extrapolated; 5 repetitions in an exclusive slot, ~1 min each unprofiled. The 70 min / 0.862 s-per-frame figures are retired as measured at another revision, not reconciled; the "identical frames" expectation becomes "nearly constant, max consecutive change 1.3e-5 /m". V-build stays (D15 holds); it is kept out of every end-to-end figure.

### A3. D19: W1r kept as `w1r_cap250`

Decision: **keep**, as a derived deck with `max_simulation_time` 330 → 250 (FDS ends 250 s, guard 252 s, no hold). Reasons: the flow window 0–240 s lies inside the cap, so all 120 uncached flow-spawn initial choices (#243, 368 edges each) and every 1 s reroute pass over the dense graph (#242/#243) still occur; the issue's own run ended at 257 s, so the mechanism population is nearly unchanged. Costs: time-limited and incomplete by construction (late spawns stay inside), WarpDriverModel (not CFSM), routes decided near 250 s have their foresight capped at the last frame with one logged warning (#666: model behaviour, reported, not a relaxation). Label: separate end-to-end workload for routing-density magnitude; never pooled with W1 or its scaling family; one seed. Preflight before any run: `--show-config` exit 0 on the derived deck, `fds_coverage` 0 m² outside, 120 spawned, no `FdsHorizonError`, count of the foresight-cap warning. `make_derived.py` entry and command are in `scenarios.json` W1r.

### A4. `scenarios.json` v2c: changes made

Backup of the pre-edit file: `/Users/chraibi/profiling-stage/tmp/scenarios_pre_v2c.json` (or the scratchpad if that path was not writable). Edits:

| Key | Change |
|---|---|
| `schema`, `revision` | gate G0 v2, v2c |
| `target` | commit `8f7d29a2`, lock `7f64a58d…`, pyproject `b323bc2a…`, run.py shim, versions at commit (fdsvismap 0.3.2, scikit-image 0.26.0), freeze risks rewritten (one interpreter; v1 outputs are expectations only; list of behaviour-changing PRs), commit note |
| `placeholders` | `WT` = `/Users/chraibi/profiling-stage/wt_8f7d29a2`, `PY`, `STAGE` = `/Users/chraibi/profiling-stage` |
| `global_rules` | removed `user_caches_untouched`, `fdsreader_cache_states`; added `fds_opens` (D13 rule with the G0 v2b opens) and `cache_states` (vismap only); `fds_staging` lists the v2 staged dirs; `dt_s` confirmed; `exit_codes` with `end_reason`; `always_on_in_cli` (no "Route switches" line, looks line) |
| `cli_vs_python_defaults` | fdsvismap 0.3.2; new rows `no_known_exit` and deck `smoke_slice_height` |
| `W1` | routing/horizon/cache_state settings at `8f7d29a2`; labels; `expected_activation_g0v2b` (iterations, agent-steps, routing, sampler, read_cells, reached_stage, opens) |
| `W2` | cache_state, labels, `expected_activation_g0v2b` |
| `W3` | role/case/why/cap_reason/labels relabelled per D14; cache_variants without fdsreader text; visibility 0.3.2, 301 points, format 6; spawning outcome; `expected_activation_g0v2b` incl. explore = wander = 0 expected, #739 inactive |
| `W4.w4_cmm_visibility` | W3b role (exact-dedupe case), settings, `expected_activation_g0v2b` |
| `W4.w4_flow_saturated` | new: derived config (engineer sha `e3f3540b…`), the A1 amendment, command, acceptance, label |
| `W4.w4_pytest` | 26-file command, G0 v2b result (857 passed, 1 non-FDS skip) |
| `W1r` | new workload `w1r_cap250` per A3, with base/geometry hashes, staged FDS hash, command, settings, preflight, expected activation |
| `kernel_experiments.V_build` | new: deck, n = 1001, must-measure list, D20 reconciliation |
| `equivalence`, `preflight_evidence` | v2 §3 (13 items), new preflight files, `stage_verification_v2.json` |

Not changed: W1 `inputs`/`fds_output`/`scaling_family`/`arms_for_explicit_questions_only`, W2 `measure`/`reference_only`, W3 `inputs`/`fds_output`, iso fixtures (inputs unchanged; the iso expectations "egress 85.30 s" and "FED = 1 at 982/1666/1693/847 s" still carry "re-confirm" and now mean re-confirm at `8f7d29a2`).

### A5. Handoff

**Files produced/changed (v2c).** `model_handoff_g0_v2.md` (this appendix), `scenarios.json` (edits above). **Commands.** `rg`/`sed` reads of `scenario.py`, `simulation_init.py`, `route_graph.py`, installed `fdsvismap/FDSVisMap.py`; `python3` JSON edit and validation of `scenarios.json`. No runs.

**Observations.** The fixture's flow premovement is inert (A1). The V-build discrepancy is explained by a revision difference in fdsvismap (source reading, not reconciled by measurement); #241 is half fixed upstream, the second pass, dense storage and recompute-regardless-of-change remain, and exact dedupe has nothing to remove on the issue's nearly constant field (A2, D23). W1r survives on a 250 s cap (A3).

**Uncertainties.** `w4_flow_saturated` deferral count and whether 150 standing agents place at all under the t = 0 spacing are untested until it runs; W1r coverage and the foresight-cap warning count are unverified; the engineer's trial n = 10 was on a loaded host.

**perf-engineer.** Regenerate `w4_flow_saturated` with the flow `use_premovement` false, record the sha256 in `scenarios.json`, run it once untimed and fill the acceptance line; build `scenarios/w1r_cap250/` via `make_derived.py` and preflight it per A3; run V-build at n = 1001 only in an exclusive slot; add the consecutive-frame difference statistic to `vbuild.py` outside the timed part.

**perf-qa.** `scenarios.json` diff against `/Users/chraibi/profiling-stage/tmp/scenarios_pre_v2c.json` is limited to the A4 table; no fdsreader cache field remains; the fixture that runs is the amended one (flow `use_premovement` false); V-build numbers are never quoted against the #236/#241 figures without the revision caveat; W1r never appears in a W1 table.

---

## Appendix v2d (2026-10-14): G1 entry conditions owned by perf-model (QA G0 v2 PASS, D21–D24)

Inputs: `review.md` "## G0 v2" IV1–IV9, `plan.md` D21–D24, `results/raw/g0v2d_*` counters, `/Users/chraibi/profiling-stage/runs/*/rc.csv` of the `g0v2b` W1/W3 and `g0v2d` W1r runs. No simulations run. `scenarios.json` backup before this edit: `/Users/chraibi/profiling-stage/tmp/scenarios_pre_v2d.json`.

### IV6/IV7: horizon criterion, computable from `rc.csv`

For every route-cost row: `bound = time_s + path_length_m / base_speed_m_per_s`, with the deck's routing base speed (W1 1.0; W3, W3b, W1r 1.3, the `RouteCostConfig` default; the world100 deck has no routing block, confirmed). A run passes when `max(bound) < guard` (guard = last FDS frame + output interval, largest spacing) and stderr carries no `Route foresight reaches beyond` (#666) warning. `bound` is an upper bound of the latest sample time a decision could read: the first leg is read at the decision time, later legs at their arrival time, each capped at the FDS end. Rows with `bound >` last frame are held-foresight rows. Recomputed by me from the run outputs:

| Run | base | rows | max bound | guard | rows past last frame | warning |
|---|---|---|---|---|---|---|
| W1 `g0v2b` s1 | 1.0 | 64 994 | 430.6 s | 481.1 s | 0 past 480 s | none |
| W3 `g0v2b` s42 | 1.3 | 277 | 56.8 s | 301.2 s | 0 | none |
| W1r `g0v2d` s1 | 1.3 | 9 856 | 288.4 s | 252 s | 812 (8.2 %), from t = 208 s | 1 (logged once per run by design) |

Written into `scenarios.json` `global_rules.horizon_criterion`, W1 `effective_settings.horizon`, W1r `effective_settings.horizon`. Never relaxed; a margin under 5 s goes to the coordinator.

**W1r confounder (D22).** Label in every W1r table: "foresight held at the last FDS frame (#666) for 8.2 % of route-cost rows; counts are magnitudes of mechanism volume, not a timing claim". Independent of the held pricing (they count calls, edges and cache hits, not values): `generate_candidates` by caller (120 flow-spawn initial choices with no cache dict, 2 × 2 464 reevaluations), 368 edges per call, segment hits/misses (initial 44 160 misses / 0 hits; `:2282` 91 632 / 815 120; `:2340` 0 / 906 752), `evaluate_segment` (135 792 + 27 181), `read_cells` 576 285, `line_parts` 387 337 / 23 228, sampler calls per quantity (324 678 gas each, 105 079 `_polyline_stats`, 2 584 smoke speed), `distance_to_polygon` 77 663. Dependent on it: sampled values after t = 208 s and everything downstream (7 switches, 117/120 at 250 s), reported as outcomes only. Stop rule: the warning count or the 8.2 % share changing at seed 1 means a changed workload.

### IV8: wording corrected (D23)

Corrected in this file (§1.4b, A2, A5 observations) and in `scenarios.json` `kernel_experiments.V_build.reconciliation_D20`: issue figures retired as "measured at another fdsvismap revision (`6e70313`, fdsvismap `64d9aa7`), not reconciled" (0.862 s/frame × 1001 ≈ 14 min, not 70); #241 "half fixed upstream" (slice read once, `reduceat`) with the second `_get_visibility_array` pass in `visibility.py:541-565` and dense storage remaining; fed_incap field "nearly constant, max consecutive change 1.3e-5 /m, not bit-identical"; exact dedupe removes nothing there, a tolerance dedupe is a model change. V-build n = 1001 (the whole list; n = 1000 drops the last point).

### IV9: v2 resource limits and stop rules (D24)

Written to `scenarios.json` `resource_limits`: W1r 300 s wall / 4 GB, repetitions as W1, seed 1; `w4_flow_saturated` 120 s / 2 GB; V-build 300 s plain, 900 s profiled, 8 GB, 1 warm-up + 5 plain repetitions with instrumented stage runs separate; v1 caps and the 4 h hard cap otherwise unchanged. Stop rules per case: zero counter where active is claimed; fixture deferral < 1 000 steps (rebuild, never relax); W1r `FdsHorizonError`, spawned ≠ 120, coverage outside > 0, warning count ≠ 1; V-build plain total over cap, `_get_visibility_array` ≠ 50 050, arrays differing between repetitions; plus the general v1 stops.

### IV1: #242 row, corrected now; final counts await the engineer's re-keyed run

Correction to §2 and to the v2b activation text: the `fed.sample_inputs` key merges two callers, the per-agent FED update and the route FED-rate path (`scenario.py sample_fed_rate` → `fed.sample_rate` → `sample_inputs`). On W1 the per-agent FED ticks are about 32.7 k per quantity (= fed.csv rows), so about 96 % of the 756 088 gas samples per quantity are route-side (`evaluate_segment` FED midpoint, once per segment evaluation, 3 quantities), and the 45 615 distinct (x, y) are mostly repeated route points. My earlier sentence "route extinction is not on `sample` any more" is also too strong: `_polyline_stats` calls `sample` for degenerate polylines (zero-length or one-point, `route_graph.py:760-776`): 160 814 calls on 4 distinct points on W1, the purest static-point population in the matrix. W3 is mostly per-agent (9 352 of 11 831 per quantity). The #242 mechanism remains active on W1, W3, W3b and W1r; **no #242 share is quoted until the engineer re-keys the caller at the first frame outside `fed.py`/`fds_sampling.py`, reports static vs moving points per caller and reruns W1 untimed.** I will check that restatement when relayed and close IV1 then. `scenarios.json` W1 `expected_activation_g0v2b.sampler_sample_calls` carries the corrected text.

### Fixture acceptance (D16, from `g0v2d`/`g0v2d2`)

`flow_spawns_deferred_steps` 5 602 ≥ 1 000; `_crowds_agents` 1 022 315 calls against 5 738 `_occupied`; `add_agent_position_refusals` 1 022 179 (the spacing mirror returned False for every candidate and JuPedSim's own refusal rejected them, so both halves of the per-candidate path run); 136 flow agents entered, 164 not spawned; ends 179.15 s `flows_closed`; identical trajectory hash in both runs. Accepted; the amended config (flow `use_premovement` false) is the one that ran (sha `982c50ac…`, QA flat diff). Recorded in `scenarios.json` W4 `w4_flow_saturated.acceptance_g0v2d`.

### Status per IV

| IV | Owner | Status | Closing block |
|---|---|---|---|
| IV1 | engineer (counters), perf-model (text) | **closed** (v2d addendum below: `g0v2f_W1` split confirmed; §2 #242 row and `scenarios.json` W1 rewritten) | this appendix |
| IV2 | engineer | open (not mine) | `benchmark.py` summary parse of `flows_closed` |
| IV3 | engineer / coordinator | open (not mine) | README, stale labels, plan banner |
| IV4 | engineer | open (not mine) | CASES labels per D14, `input_hashes.json` commit |
| IV5 | engineer / coordinator | open (not mine) | `g1_all.sh` blocks, V-build runner, determinism gate first |
| IV6 | engineer (`compare.py`), perf-model (criterion) | perf-model part **closed** (criterion above); `compare.py` fixes open | engineer |
| IV7 | perf-model | **closed** (label, confounder, independent counters, stop rule) | this appendix, `scenarios.json` W1r |
| IV8 | perf-model | **closed** (wording per D23 in both documents) | this appendix |
| IV9 | perf-model (`scenarios.json`), coordinator (`plan.md`) | perf-model part **closed** | `scenarios.json` `resource_limits`; coordinator mirrors in `plan.md` |

### Handoff v2d

**Files changed.** `model_handoff_g0_v2.md` (sentences in §1.4b, A2, A5 corrected; this appendix), `scenarios.json` (`revision`, `global_rules.horizon_criterion`, `resource_limits`, `kernel_experiments.V_build` n/limits/reconciliation, W1 horizon and sampler text, W1r config sha/routing/horizon/labels/independent counters/`expected_activation_g0v2d`/limits, fixture sha/`acceptance_g0v2d`/limits). **Commands.** Python over `rc.csv` of the three runs (bounds above), `shasum` of the two derived configs, reads of the `g0v2d*` counters and manifests, JSON edit and validation. **Observations.** My bounds reproduce QA's (430.6 s; 812 of 9 856). **Uncertainties.** IV1 final numbers pending; the fixture's spacing mirror never fired (JuPedSim refused first), which is the fixture's property, not a defect. **perf-engineer:** rerun W1 untimed with the re-keyed sampler caller and send the split; mirror `resource_limits` in `benchmark.py` timeouts (W1r 300, fixture 120, V-build 300/900). **perf-qa:** re-check `scenarios.json` against `scenarios_pre_v2d.json` (keys listed above only) and that every W1r table in later documents carries the 8.2 % label.

### v2d addendum: IV1 closed

Source: `results/raw/g0v2f_W1_O_study_det_s1_rep1_20261014T132114` (engineer handoff §G0 v2d): W1 gate, seed 1, one untimed run with `--instrument detail`, sampler caller keyed on a five-frame chain above `fed.sample_inputs`; agent-steps, iterations, reroute evaluations, switches, `read_cells` and `distance_to_polygon` identical to `g0v2b_W1`, outcome 199/200 at 400 s. Denominator of every share below: all `SliceFieldSampler.sample` calls of that run (2 461 775), or the per-quantity total where stated.

| Quantity | Per-agent update | Route cost path | Route share |
|---|---|---|---|
| CO, CO2, O2 (each) | 32 697 | 723 391 (`fed.sample_rate` <- `scenario.sample_fed_rate`) | 95.7 % |
| Extinction | 32 697 (`smoke_speed.sample`) | 160 814 (`_polyline_stats`: 81 059 `_first_hops`, 78 375 `_measure_route`, 1 380 `evaluate_segment`; 4 distinct points) | 83.1 % |
| All four | 130 788 | 2 330 987 | 94.7 % |

Distinct exact (x, y): route FED 37 473 per quantity (19.3 calls per point), per-agent FED and smoke speed 8 337 (3.9 per point). Grid-cell route extinction (`read_cells` 725 445 calls, 22.7 M cells) is a separate population. Reading: on W1 the #242 mechanism is a route-side, repeated-point population (static route points re-searched about 19 times each); the per-agent update is 5 % of the calls. This is a call-count statement from one untimed seed-1 run under the engineer's side rule (route = chain contains `sample_fed_rate`, `evaluate_segment`, `_polyline_stats` or `route_graph.`); it is not a time share, and W3 differs (79 % per-agent). The §2 #242 row and `scenarios.json` W1 `expected_activation_g0v2b.sampler_sample_calls` / `labels` carry these numbers (`scenarios.json` revision v2e). My earlier text ("dominant volume is gas-FED per agent"; "route FED midpoint does not appear") is withdrawn.

All perf-model entry conditions (IV1 text, IV6 criterion, IV7, IV8, IV9 limits) are now closed; IV2–IV5 and the `compare.py` part of IV6 remain with the engineer/coordinator per their v2d table. **perf-qa:** confirm the §2 #242 row against `g0v2f_W1` counters.json and that no document quotes a #242 time share.
