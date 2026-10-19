# G5: what the FED-rate memo saves on a ten-run W1 study (#243)

Date 2026-10-18. G4 bounded a route-sample memo on W1 at 56.6 s per ten-run study from one diagnostic seed (D39: `sample_fed_rate` 35.4 s, `read_cells` 17.2 s, `sample_route` 4.0 s), against the bar of 23 s per study (D32). The fix branch `fix/243-fed-rate-memo` at `29f9d3a5` memoises the FED-rate reads. This report measures what that memo saves: W1 `O_norc` with the memo on (default) against `nomemo` (`routing.fed_rate_memo = false`, nothing else changed), ten seeds, one rep per seed, in one exclusive slot. Both arms run at `29f9d3a5` and carry the #239 fast path, so the difference is the memo alone.

## The slot

- `g5_all.sh`: START 05:51:10Z, END 06:17:44Z, elapsed 1594 s (`results/blocks/g5_status.tsv`, driver log `results/blocks/g5_all_20261018T055110Z.log`). Two blocks, both `rc=0`: `G5_memo_W1` (1442 s; 20 warm-ups and 20 timed reps) and `G5_ctr_W1` (148 s; 4 counters reps, diagnostic). 44 run directories under `results/raw/G5_*`.
- Stage `wt_29f9d3a5` (commit `29f9d3a583ac…`, clean, `uv.lock` pinned) in all 44 manifests. sha256 in the manifests: `benchmark.py` `536db325abef…`, `instrument/perf_run.py` `0ed17d9865b0…`; `attribute.py` at the slot commit `289f046` `f64cd03f990a…`.
- Flagged runs (D34, host rule: a foreign process above 20 % at a sample): 10 of 24 reps, 9 of the 20 timed ones (nomemo 6: seeds 3, 4, 5, 7, 8, 9; O_norc 3: seeds 2, 3, 5) and 1 of the 4 counters reps (nomemo rep 2). Offenders by name from `offenders_detail`: `Podcasts` (user_app, 109 %, nomemo seed 3), `mediaanalysisd` 104 %, `duetexpertd` 101 %, `PerfPowerServices` 96 %, `eligibilityd` 58 %, `airportd` 54–67 %, `runningboardd` 65 %, `opendirectoryd` 42 %, `WiFiAgent` 21–38 % (user_app), `launchd` 26–38 %. None is `claude`; the only `claude` offender in the slot is the first warm-up (seed 1, `O_norc`), which is no rep. Three timed reps show `claude` below the threshold (10–14 %: nomemo seeds 3 and 5, O_norc seed 9), from the restarts of the 600 s wait. All flagged reps stay in the medians.
- Equality (`results/g5/equality_G5_memo_W1.csv`): ten of ten seeds wrote identical `exit.csv` and `rh.csv`; the paired table recomputes this from the digests (`outputs_equal` True in every row).

## Per seed (`results/g5/paired_G5_memo_W1.csv`)

`d_s` = wall of `nomemo` minus wall of `O_norc`. Order: the first-run arm of the pair (abba alternates across seeds).

| seed | wall memo s | wall nomemo s | d s | flagged memo / nomemo | first |
|---|---|---|---|---|---|
| 1 | 32.520 | 35.229 | 2.709 | no / no | memo |
| 2 | 34.559 | 37.501 | 2.942 | yes / no | nomemo |
| 3 | 33.786 | 36.983 | 3.197 | yes / yes | memo |
| 4 | 32.827 | 35.525 | 2.698 | no / yes | nomemo |
| 5 | 32.891 | 34.552 | 1.662 | yes / yes | memo |
| 6 | 32.537 | 35.240 | 2.703 | no / no | nomemo |
| 7 | 35.744 | 37.989 | 2.244 | no / yes | memo |
| 8 | 34.544 | 37.396 | 2.852 | no / yes | nomemo |
| 9 | 34.628 | 37.989 | 3.361 | no / yes | memo |
| 10 | 32.755 | 35.737 | 2.982 | no / no | nomemo |

The flags are uneven across arms (6 nomemo, 3 O_norc); `d_s` is nomemo minus memo, so that tilt could only inflate the saving. The three pairs with no flag on either arm (seeds 1, 6, 10) give 2.709, 2.703 and 2.982 s, inside the range of the flagged pairs (1.662 to 3.361 s). This is context; the verdict below is the code's.

## D40

**D40** fix_first: the memo saves 2.781 s per W1 run (median of ten paired seeds, IQR 0.451 s), 27.806 s per ten-run study, against the bar of 23 s; the sum over the ten seeds is 27.351 s; 0.853 µs per agent-step (3,259,925 agent-steps in the `O_norc` counters runs). Tie rule: |median| 2.781 s > IQR 0.451 s, so no tie. Measured 27.8 s of the bounded 56.6 s (49 %; 79 % of the 35.4 s `sample_fed_rate` part the memo targets; bound from the 8f7d29a2 detail run); medians 33.34 s with the memo, 36.36 s without (median paired saving 2.781 s = 8.3 % of the memo arm's median wall).

## Memo counters (`results/g5/memo_counters_G5_ctr_W1.csv`)

| arm | reps | agent-steps | hits | misses | clears | hit share |
|---|---|---|---|---|---|---|
| `O_norc` (memo on) | 2 | 3,259,925 | 266,023 | 144,644 | 0 | 0.648 |
| `nomemo` | 2 | 3,259,925 | 0 | 0 | 0 | |

Both reps of each arm agree. The 144,644 misses equal the G4 `distinct` count for `sample_fed_rate` and 266,023 + 144,644 = 410,667 equals its G4 total reads, so the hit share 0.648 is the G4 figure (0.648). The nomemo arm does not touch the memo (0 hits, 0 misses). The same agent-steps in both arms are another sign that the arms run the same simulation.

## Caveats

- The memo alone at `29f9d3a5`, not the branch against `main`: the #239 fast path (about 45 ms per t_junction run, from the g5-243-fix hand-over) is in both arms and is not measured here.
- One host, one rep per seed, ten seeds, abba alternating across seeds; no repeated measurement of the same seed. The IQR is that of ten paired differences (exclusive-method quartiles).
- 9 of 20 timed reps were flagged, more of them on the nomemo arm; they stay in the medians (D34, D38). The sub-threshold `claude` readings come from the session's wait restarts; any G5b slot should use a single Monitor wait.
- The counters runs are diagnostic (`--instrument counters`, `--label diagnostic`) and give only agent-steps and the memo counts; their walls are not used.
- `G5_memo_W1` and `G5_ctr_W1` are record-only in `analyse.py` and never enter a pooled summary. The merge decision is the maintainer's.
