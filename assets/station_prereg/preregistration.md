# Station coupled study: pre-registration

**Status: FROZEN** by the tag `station-prereg-v1` of the pyFDS-Evac repository. Drafted by Enrico, 2026-11-08; open items settled by the maintainer on 2026-11-13 (§10). This file is the frozen copy; the values recorded at freeze (§7) are in `freeze_record.md` beside it.

**Freeze form (D-V14, accepted 2026-09-30).** The freeze is **one tagged commit in the fds-evac repo, archived on Zenodo for a DOI**, made before the first FDS fire run (O11). The frozen copy lives in the tag, in `assets/station_prereg/`, together with every item in §7.

**Sources.**
- `studies/station_validation_plan.md`, the canonical plan, including its maintainer decisions of 2026-09-30. `station_part2_plan.md` is the pre-referee draft and says it is no longer maintained. Where the two differ, the canonical plan is followed (see §9).
- `plans/b11-station-v0/decisions.md`, `contract.md` (M1–M5) and `seen_outputs.md`.
- PR #925, merged at `d07eb9f7`.
- `plans/b12-station-fire-jureca/decisions.md` and `fire_inputs/fire_inputs.md`.

**What it may be called.** "Compared with survivor exit-use data". Never "validated", and never a forensic reconstruction.

## 1. Targets

| Symbol | Quantity | Value | Source |
|---|---|---|---|
| T1 | Front-door share among door users, placed rows | 117/229 = 51.1 % | Fahy 2011 Table 2 (`fahy_table2.py`, `PLACEABLE`) |
| T1′ | The same, including unplaceable rows | 127/240 = 52.9 % | Not a gate |
| T2 | Exit matrix by starting area, renormalised over the four doors | per row | Fahy Table 2. Seven rows with ≥ 10 door users (Near stage door 14, Near stage/dance floor 28, Behind dance floor 56, Between bars 24, Rear bar/dart room 24, Entryway 17, Main bar 32), plus one pooled row (Stage, Back wall platform, Sunroom, Back hallway, Center stage-side; 34) |
| T3 | Share of occupants who tried the front door | 56–66 % | NCSTAR p. 6-23, p. 8-4. It is an end-location count, not a first target. |
| T4 | Flow through the 914 mm interior front door | "a bit faster than 1 person/s" for more than 1 min | NCSTAR p. 8-5 |
| T5 | Dance floor > 120 °C at 1.5 m | (80, 85] s | NCSTAR p. 5-41, Fig. 5-55 (FDS 4, model against model) |
| T6 | O₂ < 12 % at 1.5 m throughout | (80, 100] s | NCSTAR p. 5-49, Fig. 5-61 (model against model) |

## 2. Registered criteria

| # | Metric | Band | Role | Blind |
|---|---|---|---|---|
| **V1** | T1, and W against T2, arm C (`--t-jam none`) | T1 ∈ **44.5–57.7 %** (±2 binomial SE, n = 229); **W ≤ 0.15**. The signed bias (model − 51.1 %) is reported. | Baseline | **No** (§6) |
| **V2** | T1 and W, arm R, central fire | Same bands as V1 | **Primary** | Yes, subject to §6 |
| **V3** | W(R) − W(C+jam) per seed, on the same-agent set | R lower in **≥ 15 of 20 seeds** (sign test, p ≈ 0.02) **and** mean difference ≥ **0.03**, for the **central fire variant** | **Primary claim.** If it fails, the report says "coupling adds no measurable skill to exit choice here". | Yes |
| V3m | W(R) − W(U) per seed, same-agent set | Sign count reported, **no band** | Mechanism test | Yes |
| V4 | First-target front share over all agents; beside it, NIST's construct | Reported, **no band** | Descriptive | — |
| V5 | Highest 60 s moving mean through the 914 mm door, from the first arrival to t_jam | **0.9–1.5 person/s** | Secondary. Registered direction: biased **low** (walkable gap 0.81 m against 914 mm). | Yes |
| V6 | Realised HRR (`_hrr.csv`) against Fig. 5-42; T5 and T6 crossing times at z = 1.5 m | T5 ∈ **[65, 100] s**; T6 ∈ **[65, 115] s** (NIST ± 15 s) | Fire-side check, model against model. **Not validation.** | Yes |

**W.** The door-user-weighted total variation distance: per row ½ Σ_doors |model − Fahy|, weighted by Fahy's door users. Noise floor (Fahy resampled against itself): median 0.079, p95 0.109.

**V6 operationalisation [A7, approved 2026-11-07].**
- T5 is the first time at which ≥ 50 % of the dance-floor box's gas cells at z = 1.5 m exceed 120 °C. The 10 % and 90 % crossings are also reported.
- T6 is the first time at which ≥ 95 % of the masked gas cells at z = 1.5 m have X_O₂ < 0.12. The mask is the interior gas cells connected to the dance floor, minus the bathrooms, office and storage. Per-zone times are reported.
- The sunroom "> 120 °C by 90 s" is a secondary per-zone check.

**Evaluation (registered).**

| Item | Rule |
|---|---|
| T1, W in V1/V2 | Pooled over the 20 scored seeds; per-seed spread reported |
| V3, V3m | Per-seed paired. Same-agent set: agents that reached a door in **both** arms at that seed (`validate.py --against`). |
| Before/after t_jam | Split reported (`--t-jam`). Descriptive, not a gate. |
| V3 sampling noise | Survival rates under Fahy resampling reported beside the sign test |

## 3. Denominator and outcome reporting

| Item | Rule |
|---|---|
| T1, W (V1, V2) | Placed survivor-agents who **exited by the horizon** |
| T1, W (V3, V3m) | Same-agent set (§2) |
| Excluded | Victim agents; the 22 unplaceable survivors |
| Reported beside T1 and W | Share of placed survivor-agents **incapacitated (FED ≥ 1)** and share **censored** at the horizon, as separate disagreement signals |
| Heat | Heat-incapacitated agents reported separately: heat never reaches route choice (`rank_routes` gets the gas dose only) |
| Raised floors | FED and K for agents on raised floors reported separately (#365 open) |
| Horizon | Same for every arm |
| Censoring | Agents inside within one output interval of 250 s are censored. RSET > horizon and stopped agents are never compared by size. |

## 4. Run design

| Item | Value |
|---|---|
| Deck, V2/V3 | `station_nist` (NIST-derived geometry, "provenance unverified") |
| Deck, V1 | `station_nist` and `station_fahy` (geometry sensitivity) |
| Config | `config_full.json`, **N = 455** (333 placed + 22 unplaceable + 100 victims). Unplaceable and victim agents are spread over the areas by the placed survivors' shares (O4). |
| Seeds | 1–3 pilot, not scored. **4–23 scored (20).** No extension (O1). |
| Horizon | `max_simulation_time` = **250 s**; 234 s for the −15 s variant (`--horizon 234`, O6). FDS `T_END` = 250 s; route foresight past `T_END` reads the last frame (#356). |
| t = 0 | First flame (NCSTAR Table 2-2, ±2 s) |
| Jam | `jps-exits_0` `closed_after_s` = **86 s**. Agents re-route and are not trapped (M1). Vestibule count at 86 s reported per seed. |
| Pre-movement | Uniform per Galea p. 473, Reading A (M3): main hall 25–30 s, front of house 30–35 s, back hallway 35–41 s. Galea's reading of the video. |
| Familiarity | By visit class, 0–0.85; every agent knows the front door. Not fitted. |
| Cues | As committed: stage door unlit (`c = 3`); kitchen sign `c = 8`; `entrance` = front door. This deviates from the plan (C21, O10). |
| w_queue | **0** (library default). See §6 for its history. |
| Windows | None. Renormalised per row. |
| Incapacitation | FED ≥ 1 (#235); stopped agents stay as obstacles |

### Arms

| Arm | Definition | Use |
|---|---|---|
| C | Clear air, `--t-jam none` | V1 |
| C+jam | Clear air, closure at 86 s (the committed configs) | V3 baseline |
| U | Fire, `--smoke-blind`, jam | V3m |
| **R** | Coupled (default), jam | V2, V3 |

### Sensitivities (each a separate row, never pooled)

| Row | Change | Applies to |
|---|---|---|
| t_jam | 71 s; 102 s (`--t-jam`) | C+jam, U, R |
| Pre-movement | 0 s (`--premovement zero`); tracked lower bound (`--premovement tracked`: 18 s main hall, 29 s elsewhere; an interpretation, M5, confirmed 2026-11-13) | all |
| w_queue | 0.024 (`--w-queue 0.024`). **This is a Fahy fit** (§6). | all |
| R-na | `routing.anticipate: false` (`--no-anticipate`, #125) | R |
| Dose only | `--disable-tenability` | R |
| Geometry | `station_fahy` | V1 only |

Sensitivities are built with build-script options from the freeze commit, each with a `build_options.json` record.

## 5. Fire

| Item | Central (registered) | Sensitivities (separate rows) |
|---|---|---|
| HRR | NCSTAR Fig. 5-42, prescribed, `nist_fig5_42_hrr.csv` (84 vertices, 1.6–249.8 s). No extrapolation. Burner `RAMP` replaces NIST's 150 kW ignition vents [A1]. | **±15 s**: two extra 0.2 m FDS runs, HRR ramp shifted, venting fixed |
| Grid | 0.2 m | **0.1 m**, whole domain, central yields, one node: V6 grid check only (T5, T6). Not a coupled arm. |
| Fuel | C6.3H7.1O2.1N1.0, `HEAT_OF_COMBUSTION` 22,600 kJ/kg [A2], one PU reaction [A3] | — |
| SOOT_YIELD | 0.10 (NIST club deck, p. L-17) | low 0.05 (p. L-9); high 0.227 (SFPE A.39 GM23) |
| CO_YIELD | 0.246 (Purser Table 62.18, φ 2.07) | low 0.010; high 0.246 |
| HCN_YIELD | 0.010 (Galea p. 468; secondary, Q3) | low 0.004; high 0.014 |
| Yield scaling | As published, factor 1.0. The 34 % per-MJ CO/HCN shortfall against Purser's 14.9 MJ/kg is reported as a known bias. | — |
| Burner zones | Time map [A5] and zones [A4]; paneling as burning area, HRRPUA ≤ about 650 kW/m² [A6] | — |
| Venting | NCSTAR Table 5-6 (front 30 s; stage 29 s; side 45/60 s; windows 78–130 s) [A9]. Fire input, not egress. | — |
| Slices | 2.0 m and 1.5 m; at 0.2 m, 1.6 m falls in the same cell as 1.5 m (k = 8) and is dropped; the 0.1 m deck also has 1.6 m. Every coupled run passes `--smoke-slice-height 1.5`: smoke speed, FED and sign legibility read the 1.5 m slice, and sign obstructions are tested at 1.5 m. | — |
| Software | FDS 6.10.1, `FDS-6.10.1-0-g12efa16-release` (JURECA validated build) | — |

**Gating across variants.** V3 is gated on the central variant only. Its sign under the yield triplet and ±15 s is reported (D-V15, accepted 2026-11-13).

**Seeds per variant (O5).** Every fire variant (yield low and high, ±15 s) runs seeds 4–23 in arms U and R, so the V3 sign is reported per variant.

**−15 s end (O6).** The −15 s deck ends at 234 s, the end of the shifted curve, and that row is censored at 234 s. The +15 s deck holds the first value (72 kW) over 0–16.6 s.

## 6. Already seen (V1 is not blind)

| What | Value | Where |
|---|---|---|
| Stage 1 front share among door users | **31–34 %** | `station_fahy/rerun_7a3617d` (plan §0) |
| `w_queue` sweep, `station_fahy`, old geometry | 0 → 65.9 %; 0.03 → 53.3 %; 0.05 → 48.4 %; 0.1 → 44.9 %; 1.0 → 22.9 % | `docs/routing.md` |
| **0.024 fitted to Fahy** | 53.0 % (seeds 420–422) against 52.9 % (T1′); 0.02 → 55.0 %, 0.03 → 50.2 % | `station_fahy/build_scenario.py`, `docs/routing.md` |
| Later reruns of 0.024 / 0.03 | 31.4–35.0 % at `8bda7f7`, `7a3617d`, `81726ea`, `22beb01c`; **34.8 %** at 0.5.0 (`c619a046`) | `docs/routing.md` |
| V0 sweep, **arm C+jam** (committed configs), seeds 4–23 | `station_fahy`: all evacuated, 116.25–152.35 s (median 126.6 s), vestibule 6–9 (median 8). `station_nist`: all evacuated, 134.12–179.63 s (median 150.0 s), vestibule 4–8 (median 6). | `plans/b11-station-v0/seen_outputs.md` |
| V0 closure and pre-movement checks | Seed 4 (and 5 at init), both decks; all pass | same |
| `station_nist`, before V0 | 96.6–126.0 s (median 107.1 s); no pre-movement, no jam, 600 s cap | `station_nist/README.md` |
| Fire field | **None seen.** No coupled run. On 2026-11-13 the six decks ran 2 s smoke tests on JURECA (jobs 15843769–15843771). Only the run records were read: outcome, MPI ranks, FDS revision. No slice, HRR or device output was opened. | `<deck>/provenance/*_smoke_*.run.txt` |

**Not seen at V0.** T1, W, door shares and exit matrices of the V0 configs.

**Consequences.**
- V1 is not blind.
- `w_queue = 0` was chosen after these looks. Its V0 T1 was never scored.
- The 0.024 row is a Fahy fit and is labelled as one wherever it is reported.
- V2 stays marked blind: no fire-coupled output was seen. The report states this history (O2).

Configs on `origin/main` (`14fd1134`) are byte-identical to the seen commit `edc239f8`. `git diff edc239f8 origin/main -- assets/station_*/config*.json` is empty.

## 7. To record at freeze

| Item | Value |
|---|---|
| pyFDS-Evac | main commit at freeze; the tag name; the Zenodo DOI |
| `validate.py` | `assets/station_fahy/validate.py` sha256 at the tag |
| Configs | `station_nist` and `station_fahy` `config_full.json`, `config.json`, `geometry.wkt` sha256, including cues and spawn polygons |
| Build options | Exact command line for each arm and sensitivity |
| Seeds | 1–3 pilot; 4–23 scored |
| FDS | 6.10.1, `FDS-6.10.1-0-g12efa16-release`; deck sha256; `nist_fig5_42_hrr.csv` sha256 |
| JuPedSim | Installed version (`importlib.metadata`), not the `>=1.4.2` specifier; uv.lock resolves 1.4.2 today |
| fdsvismap | Installed version (pinned `==0.3.3`) |
| fdsreader | Installed version |
| Python, uv.lock | Version; lockfile sha256 |

## 8. Failure policy

| Rule |
|---|
| A failed criterion is **published as a disclosed failure**. |
| **No tuning afterwards.** Nothing is tuned to Fahy, NCSTAR or Galea after V1 is scored, and nothing in §2–§5 changes once a fire field exists. |
| No fire-time shift is chosen to match an outcome. The ±15 s rows are an envelope, not a knob. |
| A `deadlock` end or a jupedsim#1720 error is a finding, not a reason to reseed. |
| Every look at an output is logged in a seen-outputs log, as at V0. |
| Not claimed (canonical plan §10): "validated"; death counts or survival; FED or visibility as validated; novelty beyond smoke-dependent **exit choice**; FED compared with deaths by area (D-V16). |

## 9. Changes from the plan

| # | Plan text (`station_part2_plan.md`) | Registered here | Authority |
|---|---|---|---|
| C1 | T1 band 41–61 % | 44.5–57.7 %, signed bias reported | Canonical plan D-V2, accepted 2026-09-30 |
| C2 | V4 band 51–71 % | Descriptive, no band | Canonical plan |
| C3 | No V3m | V3m added, reported only | Canonical plan |
| C4 | V3 over all exited agents | Same-agent set | Canonical plan |
| C5 | Pooling of seeds unstated | T1/W pooled over seeds; V3 per seed | Canonical plan |
| C6 | Zone FED ≥ 1 against deaths by area | Dropped | D-V16, accepted |
| C7 | Freeze is a dated file | Tagged fds-evac commit + Zenodo | D-V14, accepted |
| C8 | Pre-movement "elsewhere 35–41 s" | Reading A: main hall 25–30, front of house 30–35, back hallway 35–41 | M3, 2026-11-07 |
| C9 | Jam is the front closure; NCSTAR trapped the vestibule | Closure at the exterior doorway strip; agents re-route; vestibule count reported | M1 |
| C10 | `station_fahy` front exit outside the wall | Moved to the doorway line | M2 |
| C11 | Committed configs unspecified | Committed = C+jam; arm C via `--t-jam none` | M4 |
| C12 | No `w_queue` row in §2 | `w_queue` 0 primary; 0.024 sensitivity | b11 decisions |
| C13 | Grid check "0.1 m near the stage" | 0.1 m whole domain, central yields, one node; 5 cm and 10 cm trial dropped | b12 decisions |
| C14 | Yields: triplet, central registered | Triplet of `fire_inputs.md` §3, as published (factor 1.0); per-MJ bias reported (Q2 settled) | b12 decisions |
| C15 | ±15 s shift, form unstated | Two 0.2 m FDS runs, HRR shifted, venting fixed | b12 decisions |
| C16 | V6 "within ±15 s of NIST" | Operational T5/T6 [A7] with pass windows [65, 100] s and [65, 115] s | b12 decisions |
| C17 | D-V10 external requests | No external contacts | Canonical plan, rejected |
| C18 | Add seeds 24–43 if W and T1 are not stable | No extension; 20 scored seeds | O1, 2026-11-13 |
| C19 | Arm C-NIST (N 420, 0 s pre-movement, full familiarity) | Dropped: no build option, context only | O8, 2026-11-13 |
| C20 | N sensitivities 440 and 462 | Dropped: no build option | O9, 2026-11-13 |
| C21 | Stage-door sign off and sightline cut; kitchen not visible from the main room | Committed cues: stage door unlit (`c = 3`), kitchen sign `c = 8` | O10, 2026-11-13 |
| C22 | D-V17: check Spearpoint Table 1 for recovery sites | It gives none (see O4); area-share placement kept, no rebuild | O4, 2026-11-13 |
| C23 | FDS `T_END` ≥ 250 s + look-ahead | `T_END` = 250 s (234 s for −15 s); foresight past the end reads the last frame | Decks as built (b12); maintainer 2026-11-13 |
| C24 | Slices 2.0 m and 1.6 m | 2.0 m and 1.5 m at 0.2 m (same cell as 1.6 m); runs pass `--smoke-slice-height 1.5` | Deck snapping, b12; maintainer 2026-11-13 |

## 10. Settled before freeze (2026-11-13)

The maintainer accepted every recommendation of the draft.

| # | Item | Decision |
|---|---|---|
| O1 | Seed-extension rule | 20 scored seeds (4–23), no extension (C18). |
| O2 | w_queue history and V2 blindness | V2 stays blind; the history is stated in the report; the 0.024 row is labelled a Fahy fit (§6). |
| O3 | D-V15 | Accepted: central variant gated, variants reported (§5). |
| O4 | D-V17, victim placement | Spearpoint 2012 Table 1 (p. 160) gives no recovery sites. Its "Victims" column (sunroom 59, dance floor 41) is the author's assumption, chosen so the dance floor (238) and sunroom (76) match the NIST design load (p. 161). Victims stay spread by area share as committed (`station_fahy/build_scenario.py`, `VICTIM_TOTAL`); no rebuild (C22). |
| O5 | Seeds per fire variant | 20 seeds (4–23) per variant, arms U and R (§5). |
| O6 | −15 s and +15 s ends | −15 s ends at 234 s, censored there; +15 s holds 72 kW over 0–16.6 s (§5). |
| O7 | M5, `--premovement tracked` | Confirmed, labelled an interpretation (§4). |
| O8 | C-NIST build path | Arm dropped (C19). |
| O9 | N 440 and 462 | Rows dropped (C20). |
| O10 | Cue form | Committed cues registered; deviation stated (C21). |
| O11 | V6 before the freeze | §2 and §5 freeze before the first FDS fire run. The 2 s smoke tests ran before the freeze; only their run records were read (§6). |
| O12 | Raised-floor slice height (#365) | Reported separately (§3); #365 is not fixed between the freeze and the coupled runs. |
