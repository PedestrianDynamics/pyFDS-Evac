# G1b pass 2: perf-model acceptance (workload comparability, equivalence, D31)

Reviewer: perf-model. Date: 2026-10-17. Evidence review only; nothing was run or timed. Spec: `~/.claude/docs/profiling_team.md` sections 4, 7, 8.
Inputs read: `plan.md` (D10, D26, D30 and the three G1b run records), `README.md` sections 3-7, `results/blocks/g1b_status.tsv`, `analyse_G1b.txt`, `results/summary_groups.csv` (clean), `summary_groups_all.csv` (flagged-inclusive), `results/equivalence/G1b_*.json`, all `results/raw/G1b_*/manifest.json` (host_during, metrics, outcome, trajectory_hash_repr_v1, inputs, env, command). Pass 1 (prefix G1, `g1v2_status.tsv`) is the comparison. Labels follow section 7: end-to-end workload comparison (EE) or controlled cost experiment (CC). All wall values are `wall_s` medians from `summary_groups_all.csv` unless stated.

Verdict. Comparability (section 1) and scientific equivalence (section 5): PASS, unconditional, no blocking issue. Timing statistics: not reportable as "clean" under the predeclared rule (plan.md, "more than a third of a block's runs flagged = inconclusive") for seven blocks (disposition table in section 2) until the maintainer records D31; with D31 as proposed below they are reportable flagged-inclusive with the stated sensitivity. Six non-blocking conditions are in section 6.

Note: `plan.md` has no D31 row yet; the text only says "D31 reclassification rule". Section 2 is my proposed wording for the maintainer or coordinator to decide. It is a post-hoc decision (made after the data were seen) and must be recorded as such.

## 1. Comparability of each block with pass 1 and with the plan manifest

Checked per case/variant/seed over every run of both passes (manifest fields, not source reading):

- Application commit `8f7d29a2` (clean worktree), `uv.lock` sha `7f64a58d`, baseline venv freeze sha `63e5772a`, scenario sha (W1 `f73267f1`, W3 `f55444ae`), FDS-dir stat fingerprint (W1 `7e7cb198`, W3 `164aabdf`) are identical in both passes for every group. Commands are identical after stripping run-id paths (the only differences are per-run instrumentation output paths in `env`). Env fixed (`PYTHONHASHSEED=0`, `OMP_NUM_THREADS=4`, `VECLIB_MAXIMUM_THREADS` unset).
- `instrument/perf_counters.py` sha `0ac2e2b5e4` is identical in both passes. `instrument/perf_run.py` differs (`027743e004` pass 1, `24539eccd7` pass 2: the result-capture fix) and `benchmark.py` differs (pass-2 harness). Plain `run.py` runs are unaffected; counters runs use the fixed `perf_run.py` (see condition 4).
- Outcome identical in both passes for all 18 case/variant/seed combinations (exit code, termination, evacuated/total, sim time, remaining, not spawned). Examples: W1 s1 199/200 at 400 s (rc 2), s2 197/200 (rc 2), s3 200/200 at 362.98 s (rc 0), W2 200/200 at 313.53 s, W3 s42 99/150 with 50 unspawned, s43/s44 96/150, W1r 117/120 at 250 s, W3b 20/20.
- Repr-v1 trajectory hash is one value per case/variant/seed across both passes, all reps, all instrument levels and all output variants that write SQLite: W1 s1 `c6e61a8d1c42` (also O_norc, O_min_check), s2 `51bbfe1391d5`, s3 `2a9d9b4c9447`, n100 `32fe677f1fc0`, n400 `7af05dfbac31`, W1r `4bb6716f7ba7`, W2 `7c26feb32721`, W3 s42/43/44 `63e5429d17b0`/`642b9a39b9d7`/`929f7c7bb049`, W3b `28e59c8b780b`, flow fixture `ee23c36b4301`, ISO21 `33e9d5d66acc`. So pass 2 executed exactly the pass-1 workloads, which is the strongest comparability evidence available.
- Horizon criterion (D26, `horizon.json`) passes on every W1, W3, ovh*, out (O_study) run (W1 max_bound 430.62 s vs guard 481.12 s; seeds 393.62 s; W3 56.85 s / 104.46 s vs guard 301.15 s; 0 rows past last frame, 0 #666 warnings). W1r fails as declared (288.43 s vs guard 252.03 s, 812 rows past last frame, held 8.2 %, 1 warning), the D22 confounder. O_norc/O_min and W3b have no bound by design (D29).

| Block (pass 2) | Pass-1 counterpart | Same case, seeds, cache state, variants? | Label | Comparable? |
|---|---|---|---|---|
| G1b_det W1/W3 | G1det | yes; W3 now with result capture on both runs (pass 1 compared no cognitive-map state) | gate | yes (stronger) |
| G1b_base | G1base | W1 gate s1, 1 warm-up + 5, no application cache; same hash | EE baseline | yes |
| G1b_seeds | G1seeds | s2, s3, 1 warm-up + 3; same hashes and outcomes | EE baseline | yes |
| G1b_w2 | G1w2 | W2 nf s1; same hash | EE baseline | yes |
| G1b_w1r | G1w1r | W1r s1, held-foresight 8.2 % both | EE | yes, horizon fails as declared |
| G1b_flow | G1flow | W4 flow_saturated s42 | CC fixture | yes |
| G1b_vbuild | G1vbuild | n=1001 plain/det; 10.718 s vs 10.684 s (+0.3 %) | CC kernel | yes |
| G1b_w3first/rep/noflag/seeds | G1w3* | W3 s42 first_use 3, repeated_use 5, noflag 5, s43/s44 repeated 3 | CC (cache states), EE (seeds) | yes |
| G1b_w3bfirst/brep | G1w3b* | W3b first_use 3, repeated_use 5 | CC | yes |
| G1b_ovh, G1b_ovhW3 | G1ovh, G1ovhW3 | none vs counters, interleaved | CC instrumentation | yes |
| G1b_ovhD2 | G1ovhD | none/counters/detail, same 3 variants; replaces ovhD | CC instrumentation | yes (ovhD is a record only, see 2) |
| G1b_outchk, G1b_out | G1outchk, G1out | O_study/O_norc/O_min, same flags | CC output variants | yes; equivalence caveat in 5 |
| G1b_scale100, G1b_scale400b | G1scale100, G1scale400 | n100/n400 configs (densities 0.44/1.74 per m2) | EE scaling | yes; scale400 is a record (2) |
| G1b_w4 + extras | G1w4 | ISO21 s420 0.988 s vs 0.951 s; iso22 a-d rc 2, cmm A rc 0, pytest rc 0 | fixture | yes; not throughput evidence |

Cross-pass wall level differs by session, not by contamination. Pass-2 / pass-1 medians (flagged-inclusive) range from -3.4 % to +3.5 %: unflagged groups in a quiet host went up (W2 +3.5 %, W3 noflag +2.8 %, W3 rep +0.8 %, W3b rep +1.6 %), the pre-update W1 session (11:44-12:28 UTC) is +2.2 to +3.4 % (base +2.4 %, seeds +2.8/+2.2 %, flow +3.4 %), the post-reboot session (04:51 UTC onward) is -1.3 to -3.4 % (ovhD2 none -3.4 %, out O_study -2.6 %). Same code, same inputs: this +-3-4 % between-session level shift (thermal state, macOS 27.0 vs 27.0.1, ambient) is the resolution limit of any comparison that spans driver sessions. Quote only within-block ratios as comparisons.

Within-block drift exists: G1b_ovhD2 none 44.31 -> 46.00 s over five reps (3.8 %), ctr 45.24 -> 47.34 s (4.6 %); pass-1 G1base 44.94 -> 46.56 s (3.6 %). Early pass-2 blocks are tight (G1b_base range 47.42-47.68 s, 0.5 %; ovh none 0.5 %).

## 2. D31: how flagged runs are treated (recommendation)

Evidence (run ids in `results/raw/`, per-run host_during):
1. Offenders are bursts and names. Over the pass-2 timed reps of the W1/W1r/W3/flow/vbuild blocks (excl. ovhD) the recurring offender is `launchd` (28 runs, 20-48 %), then `spotlightknowledged.updater`, `PerfPowerServices`, `runningboardd`, `locationd`, `AssetMetricsExtension`, `spindump`, `mediaanalysisd`, `dasd`, `airportd`. `ps` %CPU is a decaying average (README section 3), so a flag says a process was recently busy and never gives the duration or the cores involved. The `class` field is unreliable and must not be used in a rule: `launchd` (`/sbin/launchd`, pid 1) and `spindump` are tagged `user`; `Podcasts` (`/System/Applications/...`) is tagged `system_daemon`. Use names.
2. Flagged runs are not slower than clean runs of the same variant in the same block (median flagged vs clean): base 47.61 vs 47.63 s; ovh none 47.55 vs 47.53; ovh counters 47.92 vs 48.00; seeds s2 47.73 vs 47.72; out O_study 46.14 vs 46.44; ovhD2 none 45.47 vs 45.96 and det 58.44 vs 59.38 (flagged faster); scale100 22.56 vs 22.48 (+0.4 %); scale400b 118.39 vs 117.00 (+1.2 %, one clean run); out O_min 36.94 vs 36.74 (+0.5 %, one clean run); out O_norc 37.07 vs 36.27 (+2.2 %, one flagged run that is also the last of a monotone 36.04 -> 37.07 s drift). Largest flagged-minus-clean difference is +2.2 % and it is confounded with drift. Example: ovhD2 none rep3 45.68 s with Podcasts 106.7 % (user app that should have been closed) equals the group median.
3. Tight dispersion alone is not proof of a clean level. G1b_ovhD is the counter-example: every one of 18 runs is flagged (installd up to 548.7 %, appstoreagent 59-200 %, `load1_before`, from 12:20 UTC), the five none-reps have a range of only 2.5 % (49.49-50.72 s), yet the level is 50.26 s versus 47.53 s (ovh) and 45.68 s (ovhD2): +5.7 % to +10 %. Contamination can shift a whole block. Hence the rule must be about the offender and a level check, not about the dispersion.
4. Contaminated pass 1 was not slower than quiet pass 2 (section 1). The flagged count is therefore no evidence of inflation at the 1 % level, but also no certification.

Per-block disposition under the predeclared rule (flagged runs / all runs of the block including warm-ups, from the manifests):

| Status | Blocks |
|---|---|
| More than 1/3 flagged: inconclusive without D31 | G1b_base 3/6, G1b_seeds 4/8, G1b_ovh 5/12, G1b_ovhD2 10/18, G1b_out 9/18 (O_min 4/6, O_norc 2/6, O_study 3/6), G1b_scale400b 5/6, G1b_flow 5/6 |
| Pass as is | G1b_w1r 2/6 (exactly one third, not more), G1b_scale100 1/6, G1b_ovhW3 1/12, G1b_w3seeds 2/8, G1b_vbuild 1/7, G1b_w2 0/6, W3/W3b first/rep/noflag/b 0 flagged |
| Records, not measurements | G1b_ovhD 18/18 (macOS update), G1b_scale400 6/6 (launch-agent loop), untimed G1b_det 2/4 and G1b_outchk 1/1 |

Proposed D31 (post hoc; to be decided by the maintainer or coordinator, who must record that it loosens a rule set before the data):
- Never delete or relabel a run. `summary.csv` keeps all 356 runs and the per-run flag.
- Headline numbers for the seven blocks above are quoted flagged-inclusive (`summary_groups_all.csv`) with three companion figures: the flagged count, the min-max range, and a sensitivity column "median without the runs whose offender set contains installer/indexer-class activity, a user app or the study's own tooling". No threshold is used as a gate: any threshold chosen now would be chosen after seeing the data (spec section 8), and a flagged-vs-clean comparison against one clean run has almost no power (scale400b +1.2 % on a single clean run; O_norc +2.2 % on a single flagged run that is the last of a monotone drift).
- Sensitivity computed (median of the 5 reps vs median after removing the named run): G1b_base without rep4 (appstoreagent 91.9 %, PerfPowerServices 143 %, storagekitd 72.9 %, osanalyticshelper 73.6 %; installer-class activity at 11:52 UTC, before the recorded 12:20 update onset) 47.629 vs 47.613 s (+0.03 %); G1b_ovhD2 none without rep3 (Podcasts 106.7 %, a user app that should have been closed) 45.697 vs 45.682 s (+0.03 %); G1b_seeds s2 without rep1 (`claude`, own tooling, 24.7 %) 47.781 vs 47.722 s (+0.12 %); G1b_w1r without rep5 (Podcasts 67.2 %, mobileassetd 100 %, deleted 97.6 %) 16.113 vs 16.126 s (-0.09 %); G1b_flow without rep4 (corespotlightd 93.3 %, an indexer) 70.266 vs 70.262 s (+0.01 %); G1b_scale400b without rep1 (CalendarWidgetExtension 52.9 %, launchd 43.6 %) 117.792 vs 118.175 s (-0.32 %). Removing the most suspicious run of each block moves the median by at most 0.3 %; that is the D31 evidence.
- Same-variant flagged vs clean medians agree: base 47.61 vs 47.63 s; ovh none 47.55 vs 47.53; ovh counters 47.92 vs 48.00; seeds s2 47.73 vs 47.72; out O_study 46.14 vs 46.44; ovhD2 none 45.47 vs 45.96 and det 58.44 vs 59.38 (flagged faster); scale100 22.56 vs 22.48; scale400b 118.39 vs 117.00 (one clean run); out O_min 36.94 vs 36.74 (one clean run); out O_norc 37.07 vs 36.27 (one flagged run). The n400 headline is further supported by agreement of three independent blocks: scale400 116.98 s (record), scale400b 118.18 s, pass-1 G1scale400 119.55 s, within 2.2 %.
- Not usable as headline (record only): G1b_ovhD (macOS update, 18/18, level +5.7 % to +10 % against the other none-blocks) and G1b_scale400 (launch-agent respawn loop, `~/.hermes/.../venv/bin/python` 57-88 % in 4 of 5 reps plus `spindump` 100 %; its median 116.98 s is -1.0 % against scale400b and is quoted only to bound the effect).
- Protocol deviation to record (own fault, not noise): the coordinator process `claude` at 24-45 % flagged G1b_det_W1 rep1 (44.9 %, 48.17 s), G1b_seeds s2 rep1 (24.7 %, 47.62 s) and scale400 rep2 (24.0 %). Effect on wall <= 0.5 % within block, but these runs cannot count as quiet.
- Proposed to supersede for pass 2: the plan rule "more than a third flagged = inconclusive", which would void most W1 blocks. It stays in force as the definition of the disposition table above.

Groups that must be reported from `summary_groups_all.csv` (clean file has fewer than 3 clean runs, so no IQR or no median; wall median [q1, q3] s, runs, flagged):

| Group (all-file row) | wall median [q1, q3] | n | flagged | clean file |
|---|---|---|---|---|
| G1b_base W1 s1 | 47.613 [47.607, 47.645] | 5 | 3 | n_used 2, IQR blank |
| G1b_seeds W1 s2 | 47.722 [47.669, 47.781] | 3 | 2 | n_used 1 |
| G1b_seeds W1 s3 | 47.720 [47.712, 47.816] | 3 | 2 | n_used 1 |
| G1b_ovh W1 none | 47.535 [47.521, 47.547] | 5 | 3 | n_used 2 |
| G1b_ovhD2 none | 45.682 [45.474, 45.919] | 5 | 3 | n_used 2 |
| G1b_ovhD2 counters | 46.171 [45.622, 46.411] | 5 | 3 | n_used 2 |
| G1b_ovhD2 detail | 59.308 [58.853, 59.375] | 5 | 2 | n_used 3 (keep all three on the all-file for a consistent triple) |
| G1b_out O_study | 46.267 [46.170, 46.444] | 5 | 2 | n_used 3 |
| G1b_out O_min | 36.895 [36.873, 36.994] | 5 | 4 | n_used 1 |
| G1b_scale400b W1_n400 | 118.175 [117.408, 118.600] | 5 | 4 | n_used 1 |
| G1b_flow (W4 flow_saturated) | 70.262 [70.234, 70.269] | 5 | 5 | n_used 0 |
| G1b_w3seeds s44 | 7.759 [7.744, 7.769] | 3 | 1 | n_used 2 |

Clean file is adequate (>= 3 clean): G1b_ovh counters (clean 4; keep the all-file row, 47.927 s, for a consistent none/counters pair), G1b_out O_norc (clean 4, 36.267 s; all-file 36.375 [36.160, 36.593] s), G1b_scale100 (22.481 s clean n 4; all-file 22.482), G1b_w1r (16.126 s, clean 3), G1b_vbuild (10.719 s, clean 4), G1b_ovhW3 none (7.982 s clean 4, all-file 7.976), all W3/W3b groups except s44. The untimed G1b_det and G1b_outchk runs are equivalence runs and enter no statistics. Because `summary_groups.csv` prints a median for n_used = 1-2 without q1/q3, its W1 rows can read as clean when they are 1-2 runs; quote only the all-file rows.

## 3. Instrumentation overhead (CC, observational; same variant order rotated, paired by rep index)

Plan target <= 5 %. All runs equivalent (section 5).

| Block | none | counters | detail | counters vs none | detail vs none |
|---|---|---|---|---|---|
| G1b_ovhD2 (pass 2, quiet, headline) | 45.682 | 46.171 | 59.308 | +1.07 % (paired median +1.07 %, range +0.33 to +3.09 %) | +29.8 % (paired median +29.83 %, range +27.9 to +32.6 %) |
| G1b_ovh (pass 2, earlier session) | 47.535 | 47.927 | not run | +0.82 % (paired median +1.12 %) | not run |
| G1b_ovhD (update, record only) | 50.256 | 50.424 | 63.231 | +0.33 % | +25.8 % |
| G1ovh / G1ovhD (pass 1, flagged) | 47.261 / 47.308 | 47.614 / 47.765 | 60.082 | +0.75 % / +0.97 % | +27.0 % |
| G1b_ovhW3 (W3, repeated_use) | 7.976 | 8.123 | not run | +1.84 % (pass 1 +1.76 %) | not run |

Peak RSS median: none 480.3 MB, counters 481.4 MB (+0.2 %), detail 502.7 MB (+4.7 %) (ovhD2). Number to quote: counters add about 1 % wall (0.3-3.1 % per pair), consistent across pass 1 (0.8-1.0 %), pass 2 and W3; the measured range is within the +-3 % drift, so "about 1 %, not distinguishable from 0 to 3 %". Detail counters cost about +26 to +30 % (block medians 25.8, 27.0, 29.8 %) and are diagnostic-only (above the 5 % limit); no number measured with detail on is a baseline. The all-file medians are used because clean n_used is 2-3.

Limit: pass-2 counters runs use the fixed `perf_run.py` (condition 4); `perf_counters.py` is unchanged.

## 4. Scaling (EE, fixed 400 s window; time-limited; densities 0.44 / 0.87 / 1.74 per m2)

| Level | Pass 2 wall median [q1, q3] (all-file) | Peak RSS | Outcome | Pass 1 |
|---|---|---|---|---|
| n100 `G1b_scale100` | 22.482 [22.479, 22.558] s | 366.1 MB | 99/100, 1 remaining, rc 2 | 22.406 s |
| n200 base `G1b_base` | 47.613 [47.607, 47.645] s | 480.3 MB | 199/200, 1 remaining, rc 2 | 46.510 s (G1base; other pass-1 n200 blocks 47.26-47.51) |
| n200 same session `G1b_out` O_study | 46.267 [46.170, 46.444] s | 480.2 MB | same | - |
| n400 `G1b_scale400b` | 118.175 [117.408, 118.600] s | 831.8 MB | 397/400, 3 remaining, rc 2 | 119.549 s (G1scale400) |
| n400 `G1b_scale400` (record) | 116.984 [116.157, 117.467] s | 831.8 MB | same | - |

Ratios: n200/n100 2.12 (2.06 using the same-session n200), n400/n200 2.48 (2.55 same session), n400/n100 5.26 (pass 1: 5.34). Wall per initial agent: 0.225 / 0.238 / 0.295 s. Local exponent about 1.08 then 1.31 per doubling (1.04 / 1.35 same session), uncertainty about +-0.06 from the +-4 % session shift. Pass 2 vs pass 1: n100 +0.3 %, n400 -1.1 % (b) or -2.2 % (flagged record). These are workload effects of a fixed window (density, exit queuing, premovement tail), not an algorithmic complexity claim (spec section 7). Per-agent-step rates are not available: scaling blocks are plain runs without counters, so the denominator (`agent_steps`) is missing. perf-engineer should obtain counters runs at n100/n400 before any per-agent-step statement.

Does the n400 "incomplete, time limit" outcome (exit 2, 397/400, 3 remaining, 0 unspawned, identical in pass 1) invalidate anything? No. All three levels are time-limited at 400 s (n100 99/100, n200 199/200), all agents spawn at t=0, the window is identical, and the label is EE fixed-window cost. It must not be called evacuation time or a completed evacuation, and the final timestamp is the window length (spec section 6). The remaining 3 agents are inside the hall, not unspawned. No `horizon.json` exists for the scale runs, so I read `rc.csv` of all 18 scale100/scale400/scale400b run directories in `/Users/chraibi/profiling-stage/runs/` (read-only, nothing written, same formula as `horizon_check.py`, base speed 1.0): max(time_s + path_length_m) is 430.62 s for n100 (30,110 rows) and 432.42 s for n400 (157,554 rows), identical in every run, against the guard 481.12 s; 0 rows past the guard; and `#666 Route foresight reaches beyond` appears 0 times in all scale stderr logs. The horizon criterion passes at all three levels (n200 430.62 s). The only open item is that `horizon.json` is not stored (condition 2).

## 5. Scientific equivalence verdict for pass 2

Exact equality, no tolerance (model_handoff_g0_v2.md section 3). Results:
- Determinism gates PASS: `G1b_det_W1.json` (rep1 vs rep2 equivalent, all 10 compared items equal), `G1b_det_W3.json` (equivalent, items 12 and 12b cognitive-map history and result metrics now compared and equal), both negative controls PASS (`G1b_det_W1_negative_control.json`, `G1b_det_W3_negative_control.json`: identity equivalent, one byte in exit.csv and one ulp in a trajectory float both detected).
- Instrumentation: `G1b_ovhD2_W1.json` 17/17 equivalent (ctr vs ctr, det and none, no gaps, all items equal); `G1b_ovh_W1.json` 11/11, `G1b_ovh_W3.json` 11/11 (gap "cognitive-map state not compared" on W3 counters, see condition 3), `G1b_ovhD_W1.json` 17/17 (record). Plus identical trajectory hashes across all counters/detail/none runs of both passes.
- Output variants: `G1b_out_vs_G1b_base.json` 18/18 equivalent, `G1b_outchk_vs_G1b_base.json` 1/1. The count overstates the coverage and must be reported as follows. 6 O_study pairs: all 15 items compared, equal (identity check). 6 O_norc pairs: trajectories, spawn/removal frames, exit.csv, rh.csv, FED history, agent scalars, manifest fields, exit counts equal; `rc.csv` and route-cost samples not written, so not compared. 6 O_min pairs: only exit summary counts compared (no SQLite, no CSVs), so the 6 O_min timed runs are not equivalent-checked beyond outcome (199/200, 400 s, rc 2). O_min is carried by the single untimed `G1b_outchk` run (trajectory hash `c6e61a8d1c42`, spawn/removal, exit.csv, agent scalars, manifest fields equal; rh/rc/FED not written). Rule 10c is thus applied correctly: O_norc and O_min are CC experiments whose route decisions are verified through trajectories + exit transitions, not through route-cost samples.
- Pass 1 vs pass 2: identical hash and outcome for every case (section 1), i.e. the model state evolution did not change between the dirty and quiet host or after the macOS 27.0 -> 27.0.1 update.
- Not equivalence-tested in pass 2: W1 seeds 2/3 and W3 s43/s44 beyond hash and outcome equality with pass 1; W3 counters with cognitive-map capture (only `results/equivalence/dev11_w3_capture_vs_capture_counters.json`, equivalent, a dev run).

Verdict: PASS. No behavioural difference between instrumented and plain runs, between output variants (to the stated coverage), or between passes. No blocking issue.

## 6. Conditions and what others must check

1. perf-engineer: report W1-family numbers from `summary_groups_all.csv` per section 2; fix `analyse.py` so that groups with n_used < 3 show blank medians (or add the all-file columns to the clean file); add `offender class` correction by name (launchd/spindump are tagged `user`, Podcasts `system_daemon`); add the quoted flagged-minus-clean difference column.
2. perf-engineer: store `horizon.json` for the scale100/scale400b runs (untimed); the numbers in section 4 come from my read-only recomputation and should be reproduced by the script.
3. perf-engineer: one untimed W3 counters-vs-none pair with `--capture-result` in a quiet slot so the G1b_ovh_W3 gap is closed with a G1b file.
4. perf-engineer: state in the report that pass-2 counters runs use the fixed `perf_run.py` and that pass-1 counters runs did not.
5. Coordinator: record D31 as post hoc; state the +-3-4 % between-session level and the 0.3-3.1 % overhead pair range in the report; quote only within-block ratios; scaling per agent-step waits for counters runs at n100/n400.
6. perf-qa: reproduce one W1 within-block ratio (counters vs none) in its own slot; check that the harness `class` field and the 1/3 rule are described as superseded for pass 2; confirm the O_min coverage statement (6 timed O_min runs equivalence-checked by outcome only).

Not claimed: any causal cost of a subsystem (nothing here is a subsystem toggle); anything about kernel_task or thermal throttling (D10, not observable); durations of the offender bursts.
