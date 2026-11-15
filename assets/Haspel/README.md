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

This scenario places 260 agents (100 Hörsaal, 30 at the Mensa food counter, 30 eating in the Mensa, 50 roaming the Foyer, 50 roaming the exhibition area), so it matches no scenario headcount: scenario 1 has 300, scenario 3 has 450 including 100 on the upper floors. The comparison question is: **does a clear-air pyfds-evac run land anywhere near PathFinder's ~57s?** Not an exact match (different model, different assumptions), but close enough to explain the gap, or a signal something's genuinely wrong.

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

These are the only two exits. The scenario has no checkpoints; the north exit and the four door checkpoints were removed with #229. Every sign faces the agents walking towards it (`alpha` is the bearing the sign faces).

| Spawn area | Where | Agents |
|---|---|---|
| `jps-distributions_0` | exhibition area (x 16–26, y 13–17), roaming | 50 |
| `jps-distributions_1` | Mensa food counter (x 37–51, y 20.9–24.9) | 30 |
| `jps-distributions_2` | Foyer (x 27.5–36.3, y 15.5–34.5), roaming | 50 |
| `jps-distributions_3` | Hörsaal (x 12–26.4, y 22.4–36.8), including the seat rows | 100 |
| `jps-distributions_4` | Mensa seating (x 37–54, y 27–36.5), eating | 30 |

Until #894 the scenario prescribed three journeys with fixed exit shares (85/15, 90/10), and two of its checkpoints sat in doorways the agents then had to walk back from: the Hörsaal group turned back into its own queue at the north door, and the Mensa group walked north to the Foyer door and back south to `exit_south`. In clear air 74 of 300 agents deadlocked (#894, #132).

## Current status: not a valid comparison yet

Clear air (no `--fds-dir`), seeds 1–5, this population: one seed clears all 260 agents (seed 2, 119.7 s). The other four end on a deadlock with 2 agents left, after 258 have left. In seeds 1, 4 and 5 the two agents block each other at the west end of a Hörsaal seat row (x ≈ 13.4–13.9, y ≈ 32); in seed 3 one agent stops in front of `jps-exits_1` (x 31.3, y 8.6). The earlier result, 400 agents out by 103.2 s at seed 42, was for the old population and exits.

**1. The FDS output predates the deck.**
`haspel.fds` was changed for #229: the mesh now covers the whole floor plan (x 6.25–61.25, y 5.75–43.25, 0.1 m cells, 88 meshes, about 10.3 million cells against 6.75 million before), so both exits lie inside the sampled smoke field. Walls 0.2 m thick, 5 m high, now follow the WKT outline, and the domain sides are open (`SURF_ID='OPEN'`), so smoke leaves the building only through the two exits. The strip between the building and the outline, including the strip north of the long wall at y ≈ 37.1 that the floor plan treats as outdoors, is therefore an enclosed walkway in FDS. The burner (2 × 2 m, x 44.2–46.2, y 17.2–19.2) is now in the kitchen, whose north wall and door to the Mensa food counter (x 41.8–48.7, y ≈ 19.7) were removed, so the kitchen opens to the counter. The fire ramps linearly to 200 kW (50 kW/m² × 4 m²) at 300 s. No FDS output of this deck exists yet; it needs a run on JURECA. See #229.

**Before running the comparison:** run FDS on this deck (#229), match the inputs above, and compare a clear-air run against scenario 1 (#230). Keep fire runs as a separate comparison against scenario 2, once its blocked routes and impaired agents are modelled.

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
