---
title: "How do I check each agent against ASET with FED, as in Pathfinder?"
linkTitle: "How-to: ASET/RSET check with FED"
weight: 15
---

A Pathfinder-style check keeps the occupants moving through the fire's
smoke, records the dose each one collects on the way, and compares the time
a limit is reached with the time the occupant leaves. This page does the
same with `--output-fed-summary`. It reads no new physics: the summary is
a post-processing of the FED and smoke histories the run already writes.

**You need** the FDS output of [A crowd in a fire](first-fds-case.md) in
`$FDS`. Nothing here runs FDS.

## 1. Keep the occupants walking and the dose on

`--disable-tenability` turns off the irritant slowdown and both
incapacitation checks. Smoke still slows walking, and the gas FED, the heat
FED and the FIC are still accumulated and written. Nobody drops, so every
agent has one RSET and the margin to each limit is defined for all of them.

```bash
uv run python run.py --scenario assets/t_junction --fds-dir "$FDS" \
    --disable-tenability \
    --output-fed-summary tj/summary.csv
```

This checks a design: the occupants are not allowed to fall. Leaving the
checks on, and the dose with them, answers a different question, what
happens to the people once they drop. Run both when both matter.

## 2. Read the summary

One row per agent. For each criterion there are three columns:

- `t_<criterion>_s`: first sample time at which the value reached the
  threshold (`>=`), empty if never;
- `diff_<criterion>_s`: crossing time minus exit time, so a negative value
  means the limit was reached before the agent left (the sign of
  DIFF = ASET - RSET);
- `outcome_<criterion>`: `fail`, `pass`, `open` or `not_evaluated`.

An agent still inside at `max_simulation_time` has no exit time
(`censored` is `True`, `exit_time_s` is empty). If it crossed, it failed,
with no margin. If it did not, the outcome is `open`: its margin is
undetermined, and the summary never fills it from the last frame. Read the
counts of `pass` only together with the number of censored agents.

Heat is `not_evaluated` when the run had no TEMPERATURE slice, not
ambient. The run's console output ends with one line per criterion giving
the outcome counts and the first crossing.

The thresholds are options: `--summary-fed-low` and `--summary-fed-high`
(0.3 and 1) for the gas FED, the heat FED and the FIC;
`--summary-visibility-limit-m` (10 m) and `--summary-visibility-c` (3) for
the visibility, which is crossed when K reaches C / limit, 0.3 1/m by
default. See [Outputs](outputs.md#exposure-summary) for the columns and the
sources of the defaults.

## What differs from Pathfinder

These are differences in the run, not in the summary:

- the O2 term starts below 20 % here and below 19.5 % in Pathfinder (set
  `--o2-threshold-percent 19.5` to match);
- the speed in smoke follows Lund by default here; Fridolf's Eq. 7 is
  available and is being verified
  ([#146](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/146));
- the gas is read at one slice height for everyone, not at each occupant's
  own height
  ([#150](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/150),
  [#157](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/157)).

The crossing time has the resolution of `--smoke-update-interval` (1 s by
default). An agent that crossed between its last sample and its exit reads
`pass`.
