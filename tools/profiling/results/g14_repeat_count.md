# G14: how often the route walks repeat on W1 at main after #814 (#243)

2026-10-18. D45 (G13) ranked rerouting at `main` `b6dff31c`: `_first_leg` 33.3 s, `_first_leg_dose` 14.5 s and
`evaluate_segment` 20.5 s per ten-run study (inclusive, summed over call paths), against the 23 s bar (D32). A cache of
whole segment evaluations is therefore bounded at 20.5 s even with no cost left; the larger costs are the per-agent
walks, which start where an agent stands. G14 counts, exactly, how often each walk is asked for again under a key that
holds every input that can differ at one field frame, on W1 at seeds 1 and 2. Counts only: no timing, no change to
pyFDS-Evac.

## The slot

- `g14_all.sh` ran 21:26:36Z to 21:28:11Z on 2026-10-18 (elapsed 95 s; `results/blocks/g14_status.tsv`, driver log
  `results/blocks/g14_all_20261018T212636Z.log`), stage `wt_b6dff31c`, commit `b6dff31c1375…`; one block,
  `G14_cnt_W1`, 2 runs (seeds 1 and 2, `--instrument detail`, diagnostic), `rc=0`.
- sha256 at the slot commit (`36ee3bc`): `instrument/perf_counters.py` `47e6820f2a86…`, `attribute.py` `40b261faecac…`
  (this task adds `--repeat-ceiling`).
- Both runs ended `incomplete_time_limit` (400 s window); no key set hit its cap.
- Flagged runs (D34, kept): seed 1 is host-flagged (launchd 33.1 %, `claude` 44.5 %, one sample during the blocking
  wait); seed 2 is clean. Counts are workload properties, not timings, so the flag does not affect them: the G13 seed-1
  detail run and this one have equal calls and distinct counts on every old path. `claude` offender: seed 1
  (`G14_cnt_W1_W1_O_norc_det_s1_rep1_20261018T212636`); nothing excluded.

## What the keys cover

Two calls with equal keys return equal values; `graph` and `config` are fixed within a run. A frame index is the
sampler's own `_time_index`; a sampler without one keys the raw time, which only over-counts distinct keys.

| Path | Key | `total` counts |
|---|---|---|
| `first_leg` | position as passed (exact floats), node, extinction frames at `time_s`, foresight-clock descriptor | calls of `_first_leg` that compute (calls served by its `walks` cache are not counted) |
| `first_leg_dose` | the leg's waypoints and length, `walk_time_s`, the first segment's source, target, length and fed growth, FED frames at `time_s`, whether a sampler is given | calls of `_first_leg_dose` |
| `segment` | source, target, extinction and FED frames at the arrival time, foresight-clock descriptor | calls of `evaluate_segment` |
| `first_leg_r01` | the `first_leg` key with the position rounded to 0.1 m | as `first_leg`; information only |

The foresight-clock descriptor is `None` without a clock, else `(t0, min(horizon_end_s, max(decision_time_s,
end_s)))`. Omitted input: none known for the three exact keys beyond the fixed `graph` and `config`.

## Counts and ceilings

Source: `results/g14/repeat_ceiling_G14_cnt_W1.csv`. Hit share = 1 − distinct / total; ceiling = hit share × cost per
ten-run study (G13 tree, outermost occurrence of the function, summed over paths); bar 23 s.

| Seed | Path | Total | Distinct | Hit share | Cost (s) | Ceiling (s) | Verdict | Capped |
|---|---|---|---|---|---|---|---|---|
| 1 | `first_leg` | 145580 | 114986 | 0.2102 | 33.33 | 7.00 | below_bar | no |
| 1 | `first_leg_dose` | 193879 | 84807 | 0.5626 | 14.47 | 8.14 | below_bar | no |
| 1 | `segment` | 62499 | 62499 | 0.0000 | 20.47 | 0.00 | below_bar | no |
| 1 | `first_leg_r01` | 145580 | 114986 | 0.2102 | 33.33 | 7.00 | info | no |
| 2 | `first_leg` | 146265 | 115637 | 0.2094 | 33.33 | 6.98 | below_bar | no |
| 2 | `first_leg_dose` | 194838 | 85132 | 0.5631 | 14.47 | 8.15 | below_bar | no |
| 2 | `segment` | 63564 | 63564 | 0.0000 | 20.47 | 0.00 | below_bar | no |
| 2 | `first_leg_r01` | 146265 | 115637 | 0.2094 | 33.33 | 6.98 | info | no |

`first_leg_r01` is information: a key rounded to 0.1 m would not be exact, so it is no candidate. Here it merges no
key (distinct equals that of the exact key). Clocked calls carry the foresight-clock descriptor, whose `t0` is a
continuous start time, so they collide only within one decision, where the exact position already matches. Unclocked
calls (`_first_leg` from `_first_hops`, the `_first_hops` fallback `evaluate_segment`, the phase-1 edge evaluation) key on
the frame index at `time_s`; on W1 the reroute interval (1.0 s) is at least the slice output interval (`DT_SLCF` 1.0 s) and
the lookup takes the nearest frame, so consecutive passes almost always read a new frame. What decides the result is
the reroute interval relative to the slice output interval, not foresight alone.

**D46** below_bar on every exact path (G14, 2026-10-18): hit share and ceiling per ten-run study, seed 1 / seed 2:
`first_leg` 0.210 / 0.209, 7.00 s / 6.98 s (minimum 6.98 s); `first_leg_dose` 0.563 / 0.563, 8.14 s / 8.15 s
(minimum 8.14 s); `segment` 0.000 / 0.000, 0.00 s / 0.00 s (minimum 0.00 s). No exact path is above the 23 s bar on
either seed, so by the rule fixed in `design.md` (decision 5) no candidate is named.

## What follows

No exact cache of these three walks can reach the 23 s bar on W1 at `main`. Under the stated assumptions the largest
single path is `first_leg_dose` at 8.15 s per ten-run study, and a cache that served every repeat of all three walks at
no cost would remove the sum of their disjoint ceilings, 15.14 s (seed 1: 7.00 + 8.14 + 0.00) and 15.12 s (seed 2:
6.98 + 8.15 + 0.00), about two thirds of the bar. The cross-pass `segment` key repeats not at all on the costed `_measure_route` path (its key holds the same arrival time
and limit as pyFDS-Evac's own per-pass cache key, so calls are distinct within a pass by construction); the unclocked
callers were not checked for key-build failures. `segment` (20.47 s) and `first_leg_dose` (14.47 s) are below 23 s at any
hit share; only `first_leg` could have reached the bar, with a hit share of at least 0.69 (measured 0.21). Repeats exist (`first_leg` 0.21, `first_leg_dose` 0.56) but are worth less than the bar; the rest of the
rerouting cost is computation without repeats. This report does not plan or choose a fix.

## Caveats

- Two seeds of one workload (W1); both runs hit the 400 s window, not the end of the evacuation.
- The ceiling assumes a repeat costs the mean call and uses the inclusive costs of the G13 profile (quoted, not
  re-measured).
- The cost base of `_first_leg` includes calls served by `walks`, which are not in `total`: the ceiling slightly
  over-states it.
- Exact floats as keys: positions that differ in the last bit are distinct.
- Two biases push the ceilings down. The G13 tree cuts its cost base at 1 % of the profiled wall (about 3.1 s per
  study), and `_first_leg_dose` is also called from `_measure_route` chains below the cut: `first_leg_dose` `total`
  equals `first_leg` `calls`, so its 14.47 s is a lower bound, short by up to about 6.2 s. The dose key is stricter
  than the function's inputs, so its `distinct` is an upper bound and its hit share a lower bound. The verdict holds:
  with the dose cost below 20.6 s, even a hit share of 1.0 stays under 23 s, and the measured share gives about
  0.563 × 20.6 = 11.6 s.
- Counts only, no timing.
