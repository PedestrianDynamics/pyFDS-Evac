---
title: "Station nightclub fire: coupled exit choice against survivor exit use"
linkTitle: "Station nightclub fire (exit use, a failed test)"
weight: 4
---

We ran coupled pyFDS-Evac simulations of the 2003 Station nightclub fire
and compared the exit use of the simulated survivors with survivor exit-use
data (Fahy, Proulx & Flynn 2011, Table 2). The comparison was
pre-registered: the criteria were frozen before the first FDS fire run.

**Every gate scored at first publication fails.** V1 fails, V2 fails and
V3, the primary claim, fails. V4 to V6 and the other owed items were scored
afterwards, as disclosed results with some deviations
([below](#owed-items-scored-afterwards)). The registered wording for the
primary claim applies: **"coupling adds no measurable skill to exit choice here"**.

This page publishes the failure under the pre-registration's failure
policy (§8): "A failed criterion is published as a disclosed failure".
Nothing was tuned afterwards.

{{< callout type="info" >}}
The results come from the tag `station-prereg-v1`, commit `aaeda1f3`. The
page reports one scenario run with research software, compared with
survivor exit-use data. It gives no design or safety verdict. It does not
validate the model, reconstruct the event or count deaths; see
[What this page does not claim](#what-this-page-does-not-claim).
{{< /callout >}}

## The result in brief

| Gate | Measured | Result |
|---|---|---|
| V1, arm C, `station_nist` | T1 58.8 % (56.5 / 58.7 / 63.4), bias +7.7; W 0.336 (0.323 / 0.344 / 0.361) | FAIL: T1 is 1.1 points above the band; W is above 0.15 |
| V1, `station_fahy` geometry | T1 58.0 %, bias +6.9; W 0.321 | FAIL |
| V2, arm R, central fire (primary) | T1 39.3 % (37.4 / 39.7 / 41.7), bias −11.7; W 0.425 (0.392 / 0.429 / 0.456) | FAIL on both |
| V3, R against C+jam, same agents (244–264 per seed) | R lower in 0 of 20 seeds; mean +0.078 (pairs +0.031 to +0.105) | FAIL |
| V3m, R against U | 0 of 20; mean +0.093 (pairs +0.062 to +0.137) | Reported, no band |

Spreads are min / median / max over the 20 scored seeds, as `validate.py`
reports them. Each row covers 6660 placed survivor-agents (333 × 20).

- **The front-door closure moves T1 most.** Arm C gives 58.8 %; closing the
  front door at 86 s (C+jam) gives 40.4 %.
- **W is higher with coupling on the same agents.** R is worse than C+jam
  in every seed of the primary row.
- **The baseline already misses W.** C and C+jam have W ≥ 0.30, against a
  band of 0.15 and a noise floor of 0.08 to 0.11. This gap exists before
  any fire enters, and its cause is not studied here.
- **No variant or sensitivity row passes V3.** The closest is the −15 s
  fire: R lower in 6 of 20 seeds, mean +0.004.

## What was registered

The freeze is the tag `station-prereg-v1`, archived on Zenodo as
[10.5281/zenodo.24190605](https://doi.org/10.5281/zenodo.24190605). The
frozen files are in `assets/station_prereg/`: `preregistration.md`,
`freeze_record.md` and `SHA256SUMS`. All 20 checksums were OK before
scoring (`shasum -a 256 -c assets/station_prereg/SHA256SUMS`). The
reproduction commands (build, run, scoring) are in `freeze_record.md`.
Versions: JuPedSim 1.4.2, fdsvismap 0.3.3, fdsreader 1.14.0, Python
3.12.13, FDS 6.10.1 (`FDS-6.10.1-0-g12efa16-release`).

The run records (635 runs), the 34 scorer outputs, the score summary and
the look log are archived at
[doi:10.5281/zenodo.24226552](https://doi.org/10.5281/zenodo.24226552).
The trajectory files are not included.

**Targets.**

- T1: the front-door share among door users, placed rows 117 of 229 =
  51.1 % (Fahy, Proulx & Flynn 2011, Table 2).
- W: the door-user-weighted total variation distance of the exit matrix by
  starting area. Per row it is ½ Σ |model − Fahy| over the doors, weighted
  by Fahy's door users. Fahy resampled against itself gives a noise floor
  with median 0.079 and 95th percentile 0.109.

**Arms.**

| Arm | Conditions |
|---|---|
| C | Clear air, no closure |
| C+jam | Clear air, front door closes at 86 s |
| U | Fire, smoke-blind, jam |
| R | Coupled, jam |

The coupling is described in [routing](/docs/routing.md) (`w_queue`) and
the [smoke-speed model](/models/smoke-speed.md).

**Run design.** N = 455 agents per run: 333 placed survivors, 22
unplaceable survivors and 100 victims. Victims and unplaceable agents are
excluded from T1 and W. Seeds 4 to 23 are scored (20 seeds); pilots 1 to 3
are not. The horizon is 250 s (234 s for the −15 s variant). t = 0 is first
flame. Pre-movement times are uniform bands after Galea et al. (2008,
p. 473). `w_queue` = 0.

**Criteria.**

| # | Registered criterion | Role |
|---|---|---|
| V1 | Arm C: T1 in 44.5 to 57.7 %, W ≤ 0.15 | Baseline; not blind |
| V2 | Arm R, central fire: same bands | Primary |
| V3 | W(R) − W(C+jam) per seed, same agents: R lower in at least 15 of 20 seeds and mean difference at least 0.03, central fire only | Primary claim |
| V3m | W(R) − W(U) per seed, same agents: sign count, no band | Mechanism test |

Same agents means the agents that reached a door in both arms at that seed
(`validate.py --against`).

**What had been seen before scoring** (pre-registration §6). The
registration is not blind throughout, and the page says where.

- V1 was not blind. Stage 1 front-door shares of 31 to 34 %, a `w_queue`
  sweep and the V0 end times had been seen.
- V2 stayed marked blind, but the end line of the unscored pilot seed 1
  (331 of 455 evacuated) had been seen.
- `w_queue` = 0 was chosen after the V0 looks.
- The 0.024 row is a fit to Fahy (53.0 % against Fahy's 52.9 %, the T1′
  share that includes the unplaceable rows) and is labelled so.

## Results

### Beside T1 and W

| Arm | FED ≥ 1 | Censored | Never reached a door | Before / after t_jam (descriptive) |
|---|---|---|---|---|
| C | n/a (no FED recorded) | 0 % | 0 | not split (no closure) |
| R | 28.3 % (1885 of 6660) | 0 % | 1531 | T1 39.4 / 39.2 %; W 0.404 / 0.567 |

Context arms, not registered criteria: C+jam has T1 40.4 %
(37.5 / 40.4 / 42.9) and W 0.300. U has T1 41.1 % (39.3 / 41.4 / 42.6),
W 0.293 and FED ≥ 1 for 24.4 % of agents; that value is not acted on,
because incapacitation is off in U.

**Denominator.** The pre-registration counts agents that exited by the
horizon. The frozen scorer `validate.py` (sha256 `2313b91a…`) counts an
agent as having exited when its last position lies within `--reach`
(2.0 m) of a door. This page reports that definition and does not change
it. "Never reached a door" (1531) differs from FED ≥ 1 (1885): 354 agents
have FED ≥ 1 and still count as having reached a door. The reason is not
established.

### Fire variants

Reported, not gated. V3 is gated on the central fire only, as decided before the freeze.

| Variant | T1 (R) | W (R) | FED ≥ 1 | V3: R lower, mean | V3m: R lower, mean |
|---|---|---|---|---|---|
| central | 39.3 % | 0.425 | 28.3 % | 0/20, +0.078 | 0/20, +0.093 |
| low yields | 37.8 % | 0.422 | 22.5 % | 0/20, +0.092 | 0/20, +0.103 |
| high yields | 41.6 % | 0.399 | 32.7 % | 1/20, +0.033 | 0/20, +0.046 |
| +15 s | 43.4 % | 0.380 | 13.7 % | 0/20, +0.068 | 0/20, +0.079 |
| −15 s (234 s horizon, against `Cjam_h234`) | 35.1 % | 0.435 | 51.0 % | 6/20, +0.004 | 5/20, +0.021 |

V3 pairs each variant with the primary C+jam runs, because C+jam has no
fire. V3m pairs each variant with its own U runs. The ±15 s rows are an
envelope on the fire time. They are not a knob and no row is a match.

### Sensitivity rows

Never pooled with the primary rows.

| Row | C+jam T1 / W | R T1 / W (FED ≥ 1) | V3 | V3m |
|---|---|---|---|---|
| t_jam 71 s | 28.5 % / 0.339 | 36.4 % / 0.395 (28.2 %) | 1/20, +0.030 | 1/20, +0.031 |
| t_jam 102 s | 49.5 % / 0.305 (2 censored) | 39.4 % / 0.425 (28.3 %) | 0/20, +0.074 | 0/20, +0.092 |
| pre-movement zero | 55.6 % / 0.307 | 44.9 % / 0.422 (4.3 %) | 0/20, +0.106 | 0/20, +0.117 |
| pre-movement tracked (one reading of the pre-movement data) | 44.8 % / 0.300 | 40.9 % / 0.425 (20.3 %) | 0/20, +0.096 | 0/20, +0.113 |
| `w_queue` 0.024 (a fit to Fahy) | 33.0 % / 0.338 | 33.1 % / 0.411 (25.2 %) | 0/20, +0.030 | 0/20, +0.082 |
| R-na (no anticipation) | primary C+jam | 40.4 % / 0.413 (30.2 %) | 0/20, +0.075 | 0/20, +0.089 |
| dose only | primary C+jam | 33.3 % / 0.393 (28.2 %; 15.1 % censored) | 0/20, +0.072 | 0/20, +0.084 |

The 0.024 row is a calibration to Fahy's front-door share. It is not a
result. The [routing page](/docs/routing.md#provenance-of-the-stations-queue-weight)
states that 0.024 no longer reproduces Fahy's split at 0.5.0 (34.8 %).

Provenance: the 0.024 row was scored with the global-tally queue term, before
the agents-ahead count of #89. It does not reproduce on main after that change.
The primary arms and the V1-V3 scores use `w_queue = 0` and are unaffected.

### How to read them

- **T1 shares cover different agent sets per arm.** The low T1 of V2 alone
  is not evidence about coupling.
- **W is higher with coupling on the same agents.** V3 compares R and C+jam
  on the agents that reached a door in both runs of a seed. R is worse in
  every seed of the primary row and in at least 14 of 20 seeds of every
  other row (the fewest is the −15 s row, 14 of 20).
- **Switching off one part leaves the failure.** With anticipation off
  (R-na, +0.075) or the incapacitation stop off (dose only, +0.072), V3
  still fails. This shows that disabling either one alone does not remove
  the failure. It does not show that neither contributes. Dose only also
  censors 15.1 %.
- **The finding is no measurable skill gain.** The page does not claim a
  mechanism by which coupling lowers the match.

## Agents left inside at the end of R runs

{{< callout type="warning" >}}
This whole section is a post-score look, outside the pre-registration and
unscored. The run-end counts cover all R runs; the counterfactual table is
one seed (primary central fire, seed 04). It is recorded in the look log
and changes no registered number.
{{< /callout >}}

**How R runs end.** Every R run exits with code 2 (the run ended with agents still inside). Apart from the 20
dose-only runs, which reach the time limit, R runs end with
`all_mobile_left`. In all R runs together, 27,193 of the 27,193 agents
still inside at the end have FED ≥ 1. Of these, 15,160 moved less than
0.5 m in the 10 s before FED reached 1. The deadlock detector fired in four
C+jam runs only, with 2 agents each.

**What changes the count (seed 04).**

| Run | What differs from R | FED ≥ 1 | End |
|---|---|---|---|
| R (frozen) | none | 125 | `all_mobile_left`, 103 s |
| R, bodies removed (diagnostic) | incapacitated agents removed instead of held in place | 125 | all agents gone |
| X1 (exploratory) | smoke speed factor fixed at 1 | 89 | `all_mobile_left`, 97 s |
| U (frozen) | smoke-blind: no slowdown, no rerouting, no incapacitation | 106, crossing between 72 and 91 s | all exit |

The smoke speed law is Lund with floor 0.1
([smoke-speed model](/models/smoke-speed.md)). Fixing the factor at 1
lowers the count from 125 to 89 in this seed. The mechanism, a longer stay
in the dose, is a reading, not tested.

What the evidence supports: the stops are dominated by dose in the queue
region, present in every fire arm, with a smaller share from the smoke
speed law. It does not exclude a contribution of the movement model
(queue speed under WarpDriver) to the time spent in the dose. These are
single-seed counterfactuals.

## What this page does not claim

- That the model is validated. The page compares the model with survivor
  exit-use data.
- A forensic reconstruction of the event.
- Death counts or survival.
- FED or visibility as validated, or FED compared with deaths by area
  (a pre-freeze decision).
- Any fire-time shift as a match. The ±15 s rows are an envelope.
- Novelty beyond smoke-dependent exit choice.

**Known bias.** CO and HCN yields as published leave a 34 % per-MJ shortfall
against Purser's 14.9 MJ/kg, so FED is biased low.

**Inputs.** The geometry `station_nist` is "provenance unverified": the
NCSTAR 2 App. L.2.2 deck, transcribed. Victim placement is an assumption;
Spearpoint (2012) Table 1 gives no recovery sites. The fire field was
checked against NIST only afterwards, and only partly (see V6 below): the
fire is model against model at best.

## Owed items, scored afterwards

{{< callout type="warning" >}}
These items are required by the pre-registration and were owed when the
page was first published
([#950](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/950)).
They are disclosed results, scored after V1 to V3 were known. The scorers
are in `assets/station_fahy/score_owed.py`. Each was committed with its
tests before its first look, except where [Deviations and
history](#deviations-and-history) lists a change after a look; every look is
in the look log. They use the same runs (seeds 4 to 23, commit `aaeda1f3`); nothing was
re-run and nothing was tuned. The frozen `validate.py` is unchanged
(sha256 `2313b91a…`). The scorers read the outputs with the current
lockfile, not the freeze lockfile (`uv.lock` differs only in pedpy 1.4.0 →
1.5.1 and Playwright entries; jupedsim 1.4.2, fdsvismap 0.3.3 and fdsreader
1.14.0 are as frozen; the runs do not differ).
{{< /callout >}}

| Item | Result | Registered band | Status |
|---|---|---|---|
| V4, first-target front share | not scored | none | The runs did not record the first target (`output_route_history` was unset). |
| V4, NIST construct, arm R | 0.329 pooled (per seed 0.312 / 0.330 / 0.345) | none | Reported. Arm C+jam 0.400 (0.387 / 0.398 / 0.420), arm U 0.408 (0.387 / 0.408 / 0.424). |
| V5, highest 60 s moving mean | undefined as registered in all 20 seeds of C+jam, U and R. Post-hoc reading, disclosed: the 60 s window ending at t_jam, which starts before the first arrival, gives 3.0 to 3.3 (C+jam), 3.1 to 3.3 (U) and 2.05 to 2.27 (R) person/s | 0.9 to 1.5 person/s | No 60 s window fits between the first arrival and t_jam. The post-hoc reading is above the band in every seed, against the registered direction (biased low). It is not a pass and not a fail. |
| V6, T5 (50 % of dance-floor gas cells above 120 °C at the 1.5 m slice) | 68.0 s (10 %: 67.0 s, 90 %: 72.0 s) | [65, 100] s | pass |
| V6, T6 (95 % of masked gas cells below 12 % O₂) | not reached by 250 s; the masked share peaks at 92.1 % at 234 s | [65, 115] s | not reached by 250 s, with the connectivity-only mask. The registered mask also subtracts bathrooms, office and storage by name; no coordinates are registered, and subtracting any room would be a post-hoc change |
| V6, 0.1 m grid check | not scored | T5, T6 | The 0.1 m run has no output: the data folder holds the deck only. |
| V6, realised against prescribed HRR | energy ratio 0.764; peak 52.1 MW at 92.0 s against 56.7 MW at 91 s | none | Reported (central deck). |
| Survival under Fahy resampling | see the table below | none | Reported beside V3. |
| Heat-incapacitated agents | not produced | reported | The runs did not compute heat FED: the recorded column is 0.0 everywhere and heat incapacitation was off. |
| Raised-floor FED | arm R: 212 of 367 agents (57.8 %) against 26.6 % elsewhere | reported | FED only; K is not recorded in the runs. |
| Vestibule count at 86 s | C+jam 4 to 8 (median 6), U 5 to 8 (6.5), R 1 to 4 (3) | reported | Ranges over the 20 seeds. |
| Censored shares and t_jam splits | table below | reported | Reported. |

V5 and V6 are on the central fire and the primary row (arms C+jam, U and
R). V5 is a secondary check and V6 a model-against-model check; neither
validates the model.

**V4.** NIST's construct is (agents that exited by the front + agents
stopped in the entry and sunroom) / (door users + stopped agents), over all
agents. "Stopped" are the agents still on the grid when the run ended, which
only arm R has (117 to 138 per seed). In arm R, 2542 front exits and 456
stopped agents in the entry and sunroom stand against 6585 door users and
2515 stopped agents over the 20 seeds. The entry and sunroom are boxes read
from the deck plan (approximate in their source). The first-target share
cannot be computed from these runs; a rerun with route history on would
give it, and the pre-registration forbids re-running the matrix.

**V5.** The first agent crosses the 914 mm interior-door line (y = −14.36
m) at 30.5 to 34.1 s, and t_jam is 86 s, so the span is 51.9 to 55.5 s.
Registered: the highest 60 s moving mean from the first arrival to t_jam.
The window is not shortened and does not run past t_jam, so no V5 value
exists as registered. In that span 182 to 197 agents cross in C+jam, 184 to
200 in U and 123 to 136 in R; the crossings match the front exits. Flow
before the first arrival is zero, so the 60 s window ending at t_jam holds
every crossing. Its rate is 3.0 to 3.3 person/s in C+jam, 3.1 to 3.3 in U and
2.05 to 2.27 in R (min to max over seeds), above 1.5 in every seed. This is a
post-hoc reading, disclosed as such: it lets the window start before the
first arrival (26 s), it is not the registered one, and it runs against the
registered direction. The V5 result is "undefined as registered"; the
post-hoc reading is neither a pass nor a fail (maintainer decision,
2026-11-20). The first arrival is read as the first crossing of the door
line, one reading of "first arrival".

**V6.** T5 is the first slice frame (1 s interval) at which at least half
of the 654 gas nodes of the dance-floor box (A4) exceed 120 °C. NIST's
FDS 4 result is 80 to 85 s, so the model reaches it earlier, inside the
registered window. The slice at the nominal 1.5 m is read at 1.6 m (the same
cell, registered in C24), at the grid nodes. T6 needs a mask of "interior
gas cells connected to the dance floor, minus the bathrooms, office and
storage". The registration gives no coordinates for those rooms, so the
mask is built by connectivity only: nodes of the slice plane that can be
reached from the dance floor in the closed initial state (10 522 of 14 453
gas nodes). With it, the masked share below 12 % oxygen reaches 83 % at
150 s and 92.1 % at 234 s, never 95 %. The T6 result is "not reached by 250 s". The nodes still at or above 12 % at
the end lie mostly in two groups (an observation), 433 nodes at x −3.4 to 1.6 m, y −1.4 to
3.2 m and 360 nodes at x −12.0 to −10.2 m, y −6.8 to 0.4 m. Whether they
are the excluded rooms is not established. The deck labels none of its obstructions
as an office or storage room and one as bathroom fixtures, at x −1.42 m,
y −1.24 m, inside the first group's box; the second group has no room label.
The groups are not excluded: excluding them would be a post-hoc change, and
the registration does not make that choice (maintainer decision, 2026-11-20). By zone (O₂ 95 %):
dance floor 102 s, sunroom 96 s, main bar 109 s, dart room 114 s, foyer
122 s. The sunroom reaches 120 °C (half of its nodes) at 84 s on the 1.6 m
plane; NIST's "by 90 s" refers to a vertical slice.

**Survival of W differences under Fahy resampling.** Registered as a rate
reported beside the V3 sign test (plan, line 146): how often a W difference
survives resampling of Fahy's table. These are rates for a difference in W;
they say nothing about occupants. Reading: 4000 multinomial resamples of
Fahy's table, one per draw, shared by all 20 seeds and both arms. Two
readings of "survives" are given. "Sign" is primary (maintainer decision,
2026-11-20): the difference keeps its observed sign; it reproduces the
plan's own figure (above 99 % for a uniform 0.03 difference), which the
tests check on a synthetic case. "Size", shown beside it: the difference
keeps its sign and is at least 0.03, the reading used first; it gives 0.46 to
0.50 for the rows at +0.030 to +0.033. The
plan does not say whether its rates are the referee's three synthetic cases
or rates on observed differences. "V3 holds" is the share of draws in which V3
as registered (R lower in at least 15 of 20 seeds and a mean at least 0.03
lower) holds.

| Row | Mean W(R) − W(C+jam) | Sign, per seed (min / median / max) | Sign, mean | Size, per seed | Size, mean | V3 holds |
|---|---|---|---|---|---|---|
| primary, central | +0.078 | 0.998 / 1.000 / 1.000 | 1.000 | 0.601 / 0.996 / 1.000 | 0.999 | 0.000 |
| low yields | +0.092 | 1.000 / 1.000 / 1.000 | 1.000 | 0.971 / 1.000 / 1.000 | 1.000 | 0.000 |
| high yields | +0.033 | 0.544 / 0.969 / 1.000 | 0.984 | 0.000 / 0.511 / 0.996 | 0.496 | 0.000 |
| +15 s | +0.068 | 0.966 / 1.000 / 1.000 | 1.000 | 0.481 / 0.994 / 1.000 | 0.998 | 0.000 |
| −15 s | +0.004 | 0.265 / 0.930 / 1.000 | 0.586 | 0.000 / 0.170 / 0.969 | 0.000 | 0.001 |
| t_jam 71 s | +0.030 | 0.467 / 0.976 / 1.000 | 0.979 | 0.004 / 0.467 / 0.927 | 0.461 | 0.000 |
| t_jam 102 s | +0.074 | 1.000 / 1.000 / 1.000 | 1.000 | 0.868 / 1.000 / 1.000 | 1.000 | 0.000 |
| pre-movement zero | +0.106 | 1.000 / 1.000 / 1.000 | 1.000 | 1.000 / 1.000 / 1.000 | 1.000 | 0.000 |
| pre-movement tracked | +0.096 | 1.000 / 1.000 / 1.000 | 1.000 | 0.995 / 1.000 / 1.000 | 1.000 | 0.000 |
| `w_queue` 0.024 (a Fahy fit) | +0.030 | 0.509 / 0.986 / 1.000 | 0.985 | 0.001 / 0.460 / 0.984 | 0.472 | 0.000 |
| R-na | +0.075 | 0.991 / 1.000 / 1.000 | 1.000 | 0.872 / 0.994 / 1.000 | 0.997 | 0.000 |
| dose only | +0.072 | 0.999 / 1.000 / 1.000 | 1.000 | 0.749 / 1.000 / 1.000 | 1.000 | 0.000 |

The V3m pairs (R against U) are scored the same way: the primary row has
mean +0.093, per-seed sign survival 0.992 / 1.000 / 1.000 and size survival
0.894 / 1.000 / 1.000. The result is the one already reported: the primary
difference is positive (R worse) and keeps its sign under resampling; no row
passes V3 in more than 0.1 % of draws.

**Raised floors.** Agents are counted as on a raised floor when they start
inside the platform or rear-strip boxes of the deck plan (302 and 66 placed
survivors over 20 seeds, 367 in all: the boxes overlap by 0.15 m and one agent
starts in both; the alcove holds none). In arm R 57.8 % of them
reach FED 1 against 26.6 % of the others; in arm U, where nobody stops, 35.7 %
against 23.7 %. The slice is sampled at an absolute height
([#365](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/365)), so on
these floors it sits 0.2 to 0.6 m lower above the feet than elsewhere (the
1.6 m plane is 1.0 m above the platform). No claim is made from the
difference.

### Censored shares and t_jam splits

Over the 20 seeds, T1 and W of the agents that exited before and at or
after t_jam (descriptive, not a gate). After t_jam the front door is closed:
in the clear-air rows nobody uses it, and the W values after t_jam rest on
few agents.

| Row | Arm | Censored | Before t_jam: T1, W | At or after t_jam: T1, W |
|---|---|---|---|---|
| primary | C+jam | 0 | 49.7 %, 0.343 | 0.0 %, 0.564 |
| primary | U | 0 | 51.2 %, 0.329 | 0.0 %, 0.569 |
| primary | R | 0 | 39.4 %, 0.404 | 39.2 %, 0.567 |
| low yields | R | 0 | 37.8 %, 0.416 | 36.9 %, 0.463 |
| high yields | R | 0 | 40.8 %, 0.375 | 51.4 %, 0.505 |
| +15 s | R | 0 | 44.6 %, 0.395 | 21.5 %, 0.434 |
| −15 s (234 s) | R | 0 | 35.1 %, 0.410 | 35.2 %, 0.515 |
| t_jam 71 s | C+jam | 0 | 42.9 %, 0.379 | 0.0 %, 0.553 |
| t_jam 71 s | R | 0 | 38.4 %, 0.408 | 20.4 %, 0.376 |
| t_jam 102 s | C+jam | 2 | 54.6 %, 0.333 | 0.0 %, 0.608 |
| t_jam 102 s | R | 0 | 39.4 %, 0.404 | 39.3 %, 0.567 |
| pre-movement zero | C+jam | 0 | 57.9 %, 0.324 | 0.0 %, 0.611 |
| pre-movement zero | R | 0 | 44.7 %, 0.422 | 78.8 %, 0.378 |
| pre-movement tracked | C+jam | 0 | 52.2 %, 0.340 | 0.0 %, 0.579 |
| pre-movement tracked | R | 0 | 40.8 %, 0.410 | 43.4 %, 0.522 |
| `w_queue` 0.024 (a Fahy fit) | C+jam | 0 | 38.5 %, 0.364 | 0.0 %, 0.562 |
| `w_queue` 0.024 (a Fahy fit) | R | 0 | 32.9 %, 0.391 | 35.8 %, 0.631 |
| R-na | R | 0 | 39.9 %, 0.388 | 47.7 %, 0.598 |
| dose only | R | 1008 (15.1 %) | 39.2 %, 0.403 | 0.0 %, 0.598 |

Censored counts are of 6660 placed survivor-agents per row. `validate.py`
takes an agent's last recorded frame as its exit time, so in the R rows the
group at or after t_jam includes agents that stopped near a door.

## Deviations and history

- The owed scorers read the t_jam rows with `assets/station_nist/config_full.json`
  and `--horizon 234` where needed, because the built configs of the
  coupled matrix no longer exist. The frozen `validate.py` with these
  configs reproduces all 32 score files of the data record (diff of every
  file).
- The first version of the V6 mask read the slice at cell centres and its
  flood fill leaked through zero-thickness walls (fdsreader's cell mask does
  not see them). T5 was the same in both versions and T6 was not reached in
  both. The version reported reads the plane at its grid nodes. The first
  result had been seen when the mask was changed; both are in the look log.
- The slice used for V6 is read at 1.6 m (the cell of the 1.5 m request), as
  registered in C24.
- The registration leaves some readings open: the first arrival of V5, the
  stopped agents and the entry and sunroom of V4, the rooms of the T6 mask,
  which agents are on a raised floor, and what "survives" means for a W
  difference. Each reading is stated above. Most were fixed in the scorer
  before its first look. These were changed or added after a look, and are
  disclosed as such: the cell-to-node mask of V6 (above); the rule for a T6
  or T5 value not reached by the last frame, first coded as "fail" after the
  first T6 result and relabelled "not reached by <time> s" by maintainer
  decision (2026-11-20), and the list of masked nodes still above 12 %
  oxygen, added after the first T6 result; the count of heat-incapacitated
  agents, added after the first look at the agent scalars;
  the sign reading of "survives", added after the size reading had given 0.46
  to 0.50 for differences of 0.03, against the plan's 99 %; and the V5 rate of
  the window ending at t_jam, added after V5 was undefined.

- Pre-movement, `w_queue` and t_jam rows have no arm-C build. They were
  scored for C+jam, U and R only.
- R-na and dose-only were paired with the primary C+jam and U runs (the
  analyst's choice). The same-agent check passed.
- Arm C was scored without the t_jam split.
- The look order was V1, V2, V3, V3m, context arms, fire variants,
  sensitivities. The analyst chose it; the pre-registration sets none.
- The arm C-NIST row and the N = 440 and N = 462 rows were dropped before
  the freeze.
- The look log is public in the data record
  ([doi:10.5281/zenodo.24226552](https://doi.org/10.5281/zenodo.24226552)).
  That version ends on 2026-11-14. The looks of the owed scoring (2026-11-20)
  are appended to the log and are not in the record until it is updated.

## Limits

- One scenario, 20 seeds, a 0.2 m FDS grid and one realisation per fire.
  The page draws no general conclusion from it.
- WarpDriver at the 0.52 to 0.77 m openings:
  [jupedsim#1720](https://github.com/PedestrianDynamics/jupedsim/issues/1720)
  and
  [jupedsim#1719](https://github.com/PedestrianDynamics/jupedsim/issues/1719).
- Heat never reaches route choice: `rank_routes` takes the gas dose only.
- Raised floors are open
  ([#365](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/365)).

## Sources

{{< details title="Sources" closed="true" >}}

- Fahy, R. F., Proulx, G., & Flynn, J. (2011). The Station Nightclub fire:
  an analysis of witness statements. *Fire Safety Science* 10, 197–209.
  [doi:10.3801/IAFSS.FSS.10-197](https://doi.org/10.3801/IAFSS.FSS.10-197).
  Table 2.
- Grosshandler, W., Bryner, N., Madrzykowski, D., & Kuntz, K. (2005).
  *Report of the Technical Investigation of The Station Nightclub Fire*,
  NIST NCSTAR 2, Vol. I.
  [doi:10.6028/NIST.NCSTAR.2v1](https://doi.org/10.6028/NIST.NCSTAR.2v1).
  Used: Table 2-2 (first
  flame, ±2 s); p. 5-41 and Fig. 5-55 (T5); p. 5-49 and Fig. 5-61 (T6);
  Fig. 5-42 (heat release rate); Table 5-6 (venting); pp. 6-23, 8-4, 8-5;
  App. L.2.2.
- Galea, E. R., Wang, Z., Veeraswamy, A., Jia, F., Lawrence, P., & Ewer, J.
  (2008). Coupled fire/evacuation analysis of the Station Nightclub fire.
  *Fire Safety Science* 9, 465–476.
  [doi:10.3801/IAFSS.FSS.9-465](https://doi.org/10.3801/IAFSS.FSS.9-465).
  p. 473 (pre-movement) and p. 468 (HCN).
- Purser, D. A. (2016). Combustion toxicity. In M. J. Hurley et al. (Eds.),
  *SFPE Handbook of Fire Protection Engineering*, 5th ed., Ch. 62,
  pp. 2207–2307. Springer.
  [doi:10.1007/978-1-4939-2565-0_62](https://doi.org/10.1007/978-1-4939-2565-0_62).
  Table 62.18, p. 2280: CMHR polyurethane foam, ISO TS 19700 tube furnace at
  650 °C, fuel-rich row φ = 2.07, effective heat of combustion 14.9 MJ/kg,
  CO 246 and HCN 14. The column header reads g/g; the values are read as
  mg/g (CO yield 0.246), an inference. A bench-scale value, used as the
  central yield by choice.
- Spearpoint, M. (2012). Network modeling of The Station Nightclub fire
  evacuation. *Journal of Fire Protection Engineering* 22(3), 157–181.
  [doi:10.1177/1042391512447044](https://doi.org/10.1177/1042391512447044).
  Table 1, p. 160.
- Pre-registration: tag `station-prereg-v1`, Zenodo
  [doi:10.5281/zenodo.24190605](https://doi.org/10.5281/zenodo.24190605).
- Fire input (pre-registration §5): prescribed heat release rate from
  NCSTAR Fig. 5-42 (`nist_fig5_42_hrr.csv`); see
  [Design fires](/fundamentals/design-fires.md#fires-used-in-pyfds-evac-studies).

{{< /details >}}
