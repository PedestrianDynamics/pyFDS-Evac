---
title: "Station nightclub fire: coupled exit choice against survivor exit use"
linkTitle: "Station nightclub fire (exit use, a failed test)"
weight: 4
---

We ran coupled pyFDS-Evac simulations of the 2003 Station nightclub fire
and compared the exit use of the simulated survivors with survivor exit-use
data (Fahy, Proulx & Flynn 2011, Table 2). The comparison was
pre-registered: the criteria were frozen before the first FDS fire run.

**Every scored gate fails.** V1 fails, V2 fails and V3, the primary claim,
fails. V4 to V6 were not scored. The registered wording for the primary
claim applies: **"coupling adds no measurable skill to exit choice here"**.

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
not checked against NIST: the fire is model against model at best, because
V6 was not scored.

## Owed and not yet produced

These items are required by the pre-registration and tracked in
[#950](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/950).

- V4: first-target front-door share.
- V5: 0.9 to 1.5 person/s through the 914 mm door.
- V6: fire-side check, T5 in 65 to 100 s and T6 in 65 to 115 s. It needs
  fire slices that nobody has opened.
- The §2 survival rates under Fahy resampling.
- The §3 heat-only incapacitation, raised-floor FED and K
  ([#365](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/365)
  is open), and the vestibule count at 86 s.
- Censored shares and t_jam splits beside every sensitivity row. They are
  in score files 08 to 34 and not tabulated here.

The frozen tree has no scorer for these. The pre-registration forbids
tuning, not implementing frozen analyses. None of them is a result of this
page.

## Deviations and history

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
