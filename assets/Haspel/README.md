# Haspel

A real-building asset for a model-to-model comparison with a PathFinder student study, not a synthetic test deck. The building and headcount are the same as the study's; its evacuation times are the numbers to compare against. PathFinder is itself a model, so agreement would be cross-model verification, not validation against experimental data.

## The reference

> *Qualitative Entwurfsanalysen Evakuierungssimulation — Bergische Universität Wuppertal, Gebäude HC* (unpublished student project, architecture/civil engineering faculty), simulated in Thunderhead Engineering **PathFinder**, a commercial microscopic evacuation model.

The report is not in this repository and has no authors, year or archive ID recorded here. Every number in the table below comes from it and has not been checked against the source; ask the maintainer for a copy.

According to the report, the same building (BUW Campus Haspel, Gebäude HC) was modelled independently in PathFinder across four scenarios. Its walking speeds were 1.60 m/s on the level and 0.55 m/s up indoor stairs, the under-30 means in E DIN 18009-2:2021-06 (draft), Tab. G.1 and G.2. It used 1.19 m/s for impaired agents. In the draft that value is the level mean for people over 50 (Tab. G.1); DIN gives no value for people with reduced mobility.

| # | Scenario | Population | Fire | PathFinder result |
|---|---|---|---|---|
| 1 | Evening comedy show | 300 (100 Hörsaal + 160+40 Mensa) | none | **~57s** to fully clear |
| 2 | Same evening event | 300, 47 impaired | Mensa fire blocks the outside door *and* the upper-right terrace route | **~71s** to clear; last person off the safe outdoor walkway at **~101s** |
| 3 | Daytime lecture + freshers' week | 450 (260 Hörsaal + 90 Mensa/Foyer + 100 upper floors) | none | **~74s** to clear, ~89s to all reach an exit |
| 4 | Same daytime event | 450, same split | Mensa fire blocks the outside door | **~85s** to clear |

This scenario places 400 agents (200 Mensa, 100 Hörsaal, 100 in the exhibition area), so it matches no scenario headcount exactly: scenario 1 has 300, scenario 3 has 450 including 100 on the upper floors. The comparison question is: **does a clear-air pyfds-evac run land anywhere near PathFinder's ~57s?** Not an exact match (different model, different assumptions), but close enough to explain the gap, or a signal something's genuinely wrong.

### Inputs that differ from the reference

| Input | Reference (per report) | `config.json` |
|---|---|---|
| Free walking speed | 1.60 m/s | 1.4 m/s (`v0`), constant |
| Speed spread | not recorded here | none (`v0_distribution: constant`); DIN 18009-2 (draft) G.4.1 asks for a ±20 % normal spread |
| Impaired agents | 47 in scenario 2 | none |
| Blocked routes | scenarios 2 and 4 | none modelled |
| Pre-movement, agent size, stairs | not recorded here | no pre-movement, radius 0.2 m, ground floor only |

With a 12.5 % lower mean speed and no spread, a longer egress time is expected even on identical geometry and routes. A gap to PathFinder can only be read as a model disagreement once these inputs match.

## Routes

The scenario has no journeys. Each agent's exit, and its way to it through the building, is chosen by pyfds-evac's route choice, not prescribed. The stages are:

| Stage | Where | Role |
|---|---|---|
| `jps-exits_0` | east door (x 58.2–58.8) | exit |
| `jps-exits_1` | south door (y 8.1–8.4) | exit |
| `jps-exits_2` | outside, north of the building (x 23.7–25.7, y 38.7–39.7) | exit; the strip north of the long wall at y ≈ 37.1 is outdoors |
| `jps-checkpoints_0` | Foyer north door | crossing to the outside |
| `jps-checkpoints_1` | Mensa door | crossing |
| `jps-checkpoints_2` | Hörsaal north door | crossing to the outside |
| `jps-checkpoints_3` | Hörsaal east door | crossing into the Foyer |

Every sign faces the agents walking towards it (`alpha` is the bearing the sign faces).

Until #894 the scenario prescribed three journeys with fixed exit shares (85/15, 90/10), and two of its checkpoints sat in doorways the agents then had to walk back from: the Hörsaal group turned back into its own queue at the north door, and the Mensa group walked north to the Foyer door and back south to `exit_south`. In clear air 74 of 300 agents deadlocked (#894, #132).

## Current status: not a valid comparison yet

Clear air (no `--fds-dir`), seed 42: all 400 agents leave, the last at **103.2 s**; half are out by 48.5 s and 246 of 400 by 57 s. The inputs below still differ from the reference, so this is not yet a comparison with PathFinder's ~57 s. Remaining problems of this asset:

**1. The smoke field and the building geometry may not line up.**
The committed `haspel.fds` meshes x 11.25–56.25, y 10.75–40.75 (a 45 × 30 m box); the WKT floor plan spans x 8.48–58.83, y 8.05–40.61. #131 reports the smoke slice of the ~5.4 GB FDS output at `(0,0)`–`(45,30)`; that output is not in the repository, and the reading cannot be reproduced from the committed deck, which uses the WKT frame. Whatever the origin, the mesh does not cover the whole floor plan: `jps-exits_1` (south, y 8.06–8.43) lies below it and `jps-exits_0` (east, x 58.18–58.80) beyond it, so agents queuing at either exit are outside the sampled smoke field. The fire ramps linearly to 200 kW (50 kW/m² × 4 m²) at 300 s, about 38 kW at 57 s. See #229.

**2. The fire sits inside a spawn area.**
The burner (x 46.47–48.47, y 21.09–23.09) lies inside the Mensa spawn polygon (x 37–51, y 20.9–24.9), so some agents start on or next to the fire. See #229.

**Before running the comparison:** fix #131 and #229, match the inputs above, and compare a clear-air run against scenario 1 (#230). Keep fire runs as a separate comparison against scenario 2, once its blocked routes and impaired agents are modelled.

## Parameters

`config.json` overrides these routing defaults for this scenario only; the code defaults are unchanged.

| Key | Value | Default | Source |
|---|---|---|---|
| `routing.fed_rejection_threshold` | 0.3 | 1.0 | not stated; consistent with the ISO 13571 threshold for susceptible populations |
| `routing.visibility_extinction_threshold` | 0.15 1/m | 0.5 1/m | not stated; with C = 3 this is S = 3/K = 20 m |
| `routing.w_smoke` | 40 | 1.0 | not stated |
| `v0` | 1.4 m/s | | not stated; differs from the reference 1.60 m/s |

In `haspel.fds` the fuel is labelled `N-HEPTANE`, but `HEAT_OF_COMBUSTION=20000` kJ/kg, `SOOT_YIELD=0.015` and `CO_YIELD=0.008` have no stated source. FDS produces soot and CO from yield × HRR / ΔHc, so the extinction field, and every agent's visibility and FED, depend on these values. Treat them as a generic fuel assumption.

## `inifile_template.json` is not a second scenario

A leftover from an old, unrelated JuPedSim format, not a real scenario. The picker lists it anyway since it's technically openable JSON. Ignore it.
