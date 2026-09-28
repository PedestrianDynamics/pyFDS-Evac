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

This scenario's population (200 Mensa / 100 Hörsaal = 300) matches scenario 1's headcount. The comparison question is: **does a clear-air pyfds-evac run land anywhere near PathFinder's ~57s?** Not an exact match (different model, different assumptions), but close enough to explain the gap, or a signal something's genuinely wrong.

### Inputs that differ from the reference

| Input | Reference (per report) | `config.json` |
|---|---|---|
| Free walking speed | 1.60 m/s | 1.4 m/s (`v0`), constant |
| Speed spread | not recorded here | none (`v0_distribution: constant`); DIN 18009-2 (draft) G.4.1 asks for a ±20 % normal spread |
| Impaired agents | 47 in scenario 2 | none |
| Blocked routes | scenarios 2 and 4 | none modelled |
| Pre-movement, agent size, stairs | not recorded here | no pre-movement, radius 0.2 m, ground floor only |

With a 12.5 % lower mean speed and no spread, a longer egress time is expected even on identical geometry and routes. A gap to PathFinder can only be read as a model disagreement once these inputs match.

## Current status: not a valid comparison yet

A run exists locally at `results/Haspel/probabilistic/seed42/Haspel.sqlite` (not committed): 300 agents, 900s cap, **with** the FDS fire, so smoke slowdown and FED were active. That makes it neither PathFinder scenario 1 (no fire) nor scenario 2 (impaired agents and blocked routes, not modelled here). The numbers are:

| | PathFinder (scenario 1) | This run (with fire) |
|---|---|---|
| Building fully cleared | **~57s** | **never**: 26% of agents (78/300) still inside at the 900s cap |
| Half of agents out by | ~57s (all of them) | **198.4s** |
| Agents out by 57s | 300/300 | ~30/300 (10%) |

That gap is not read as "the routing model disagrees with PathFinder". It points at problems in this asset:

**1. Checkpoints are too small for the crowds routed through them (likely cause, not yet confirmed from trajectories).**
All three are 1.62 m² or smaller (1.62, 1.15 and 0.50 m²); the smallest is about one person's standing space, funneling 100–200 agents each. The 26%-stuck number lines up in scale with the Hörsaal group (100 agents) jamming at its 1.15 m² checkpoint. See #132.

**2. The smoke field and the building geometry may not line up (possible contributor).**
The committed `haspel.fds` meshes x 11.25–56.25, y 10.75–40.75 (a 45 × 30 m box); the WKT floor plan spans x 8.48–58.83, y 8.05–40.61. #131 reports the smoke slice of the ~5.4 GB FDS output at `(0,0)`–`(45,30)`; that output is not in the repository, and the reading cannot be reproduced from the committed deck, which uses the WKT frame. Whatever the origin, the mesh does not cover the whole floor plan: `exit_south` (y 8.06–8.43) lies below it and `exit_east` (x 58.18–58.80) beyond it, so agents queuing at either exit are outside the sampled smoke field. The fire ramps linearly to 200 kW (50 kW/m² × 4 m²) at 300 s, about 38 kW at 57 s. No clear-air control run exists, so the smoke's share of the slowdown is not established.

**3. The fire sits inside a spawn area.**
The burner (x 46.47–48.47, y 21.09–23.09) lies inside the Mensa spawn polygon (x 37–51, y 20.9–24.9), so some agents start on or next to the fire.

**4. Routing only ever chooses between paths the scenario author wired up, not the shortest real path.**
Agents don't compute a fresh route across open floor. They pick the best of the fixed spawn→checkpoint→exit connections in `config.json`, and the exit shares at each checkpoint are prescribed (85/15 and 90/10 south/east), not predicted. A match with PathFinder's time would therefore not validate the exit choice. If PathFinder found a shorter real path that never got wired into this graph, no amount of route-cost tuning here will find it either. See #133.

**Before re-running the comparison:** fix #131 and #132, match the inputs above, and compare a clear-air run against scenario 1. Keep fire runs as a separate comparison against scenario 2, once its blocked routes and impaired agents are modelled.

## Parameters

`config.json` overrides these routing defaults for this scenario only; the code defaults are unchanged.

| Key | Value | Default | Source |
|---|---|---|---|
| `routing.fed_rejection_threshold` | 0.3 | 1.0 | not stated; consistent with the ISO 13571 threshold for susceptible populations |
| `routing.visibility_extinction_threshold` | 0.15 1/m | 0.5 1/m | not stated; with C = 3 this is S = 3/K = 20 m |
| `routing.w_smoke` | 40 | 1.0 | not stated |
| `waypoint_routing` exit shares | 85/15, 90/10 | model's exit choice | prescribed by the scenario author |
| `v0` | 1.4 m/s | | not stated; differs from the reference 1.60 m/s |

In `haspel.fds` the fuel is labelled `N-HEPTANE`, but `HEAT_OF_COMBUSTION=20000` kJ/kg, `SOOT_YIELD=0.015` and `CO_YIELD=0.008` have no stated source. FDS produces soot and CO from yield × HRR / ΔHc, so the extinction field, and every agent's visibility and FED, depend on these values. Treat them as a generic fuel assumption.

## `inifile_template.json` is not a second scenario

A leftover from an old, unrelated JuPedSim format, not a real scenario. The picker lists it anyway since it's technically openable JSON. Ignore it.
