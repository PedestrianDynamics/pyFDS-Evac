# Haspel

A validation case against a real, published evacuation study — not a synthetic test deck. Same building, same headcount, a real commercial evacuation tool's numbers to check against.

## The reference

> *Qualitative Entwurfsanalysen Evakuierungssimulation — Bergische Universität Wuppertal, Gebäude HC* (student project, architecture/civil engineering faculty), simulated in Thunderhead Engineering **PathFinder**, a commercial microscopic evacuation model.

Same building — BUW Campus Haspel, Gebäude HC — modelled independently in PathFinder across four scenarios, DIN 18009-2 walking speeds (1.6 m/s flat, 0.55 m/s climbing stairs, 1.19 m/s for impaired agents):

| # | Scenario | Population | Fire | PathFinder result |
|---|---|---|---|---|
| 1 | Evening comedy show | 300 (100 Hörsaal + 160+40 Mensa) | none | **~57s** to fully clear |
| 2 | Same evening event | 300, 47 impaired | Mensa fire blocks the outside door *and* the upper-right terrace route | **~71s** to clear; last person off the safe outdoor walkway at **~101s** |
| 3 | Daytime lecture + freshers' week | 450 (260 Hörsaal + 90 Mensa/Foyer + 100 upper floors) | none | **~74s** to clear, ~89s to all reach an exit |
| 4 | Same daytime event | 450, same split | Mensa fire blocks the outside door | **~85s** to clear |

This scenario's population (200 Mensa / 100 Hörsaal = 300) is built to match scenario 1's baseline exactly. Once this asset is fixed (see below), the validation question is: **does a clear-air pyfds-evac run land anywhere near PathFinder's ~57s?** Not an exact match — different model, different assumptions — but close enough to explain the gap, or a signal something's genuinely wrong.

## Current status: not a valid comparison yet

A real run already exists — `results/Haspel/probabilistic/seed42/Haspel.sqlite`, 300 agents, 900s cap. Checked against the reference directly, no rounding in anyone's favor:

| | PathFinder (scenario 1) | This run |
|---|---|---|
| Building fully cleared | **~57s** | **never** — 26% of agents (78/300) still inside at the 900s cap |
| Half of agents out by | ~57s (all of them) | **198.4s** |
| Agents out by 57s | 300/300 | ~30/300 (10%) |

Roughly an order of magnitude slower to reach the same completion point, and more than a quarter of the building never gets out inside a 15-minute simulated window. That gap is not read as "the routing model disagrees with PathFinder" — it's read as this specific asset having two bugs that actively corrupt the run, found precisely *by* trying to validate against the reference:

**1. The smoke and the building geometry disagree about where the building is.**
The FDS mesh's coordinate origin doesn't match the architectural drawing's. FDS thinks the building spans `(0,0)` to `(45,30)`; the drawing says `(8.48, 8.05)` to `(58.83, 40.61)`. Rendered smoke sits ~8.5m off from the walls it's supposed to be inside, and every agent's smoke-driven slowdown/FED for the whole 900s is computed against the wrong position. Confirmed by comparing the two files directly.

**2. Checkpoints are too small for the crowds routed through them.**
All three are under 1.6 m² — one is 0.5 m², about one person's standing space — funneling 100–200 agents each. The 26%-stuck number above lines up in scale almost exactly with the Hörsaal group (100 agents) jamming at its 1.15 m² checkpoint. Same failure mode already documented in this repo for `assembly_hall`.

**3. Routing only ever chooses between paths the scenario author wired up, not the shortest real path.**
Agents don't compute a fresh route across open floor — they pick the best of whatever fixed spawn→checkpoint→exit connections exist in `config.json`. If PathFinder's model found a shorter real path that never got wired into this graph, no amount of route-cost tuning here will find it either.

**Re-run the comparison after #131 and #132 are fixed, not before.** #131 (coordinate mismatch), #132 (checkpoint sizing), #133 (fixed-graph routing, may be a documentation issue rather than a bug).

## `inifile_template.json` is not a second scenario

A leftover from an old, unrelated JuPedSim format — not a real scenario. The picker lists it anyway since it's technically openable JSON. Ignore it.
