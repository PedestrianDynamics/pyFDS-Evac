# Familiarity Routing Test (Full vs. Discovery)

## Purpose

This test case validates that the `full` and `discovery` agent familiarity
tiers produce **different evacuation behavior**, not just a config
flag with no observable effect.

- **`full`** agents know the entire building layout from the moment they
  spawn (trained staff) and take the true shortest route to the exit.
- **`discovery`** agents start knowing almost nothing (a first-time visitor)
  and can only route through checkpoints they've either started at or
  physically passed through. When no known route to an exit exists yet, they
  head toward the nearest checkpoint they know about but haven't explored,
  discover what's beyond it on arrival, and repeat until an exit is found.

The two configs (`Full`/`Discovery`) are identical except for one field
(`familiarity` on the spawn distribution) and share the same hand-drawn maze
geometry and the same paired real-fire FDS deck, so any difference in
outcome is attributable to the familiarity mechanism itself.

This test also exercises, indirectly, three engine-level fixes/features that
were required before familiarity could have *any* observable effect at all
(see [Background](#background-why-this-test-exists) below).

## Test Setup

- **Geometry:** hand-drawn maze-like floor plan, 20 m × 18 m, 0.1 m walls,
  1.2 m doors throughout, generated parametrically by each config folder's
  `build_geometry.py` (`assets/Familiarity Test Full/`,
  `assets/Familiarity Test Discovery/`). One spawn room (bottom-right), one
  exit alcove (top-right).
- **Model:** `SocialForceModel`, seed 420, 20 agents (`by_number` spawn, all
  at once — not flow-spawned).
- **Fire deck:** `testing directory/Familiarity Test/familiarity_test.fds`.
  Real combustion via `&REAC` (not a prescribed `&INIT`); the FDS walls
  mirror the walkable geometry exactly so smoke propagates through the same
  doorways agents use. *Not required for the pure-routing result below* —
  see [Scope](#scope--caveats).
- **Checkpoint graph:** the maze has one **scripted tour** —
  `spawn → CP0 → CP1 → CP2 → CP3 → exit` — walking the doorway at the west
  wall (CP0), through a floating-wall gap (CP1), a pocket door (CP2), and the
  door into the exit alcove (CP3). This is the only route either tier is
  *assigned* at spawn, and it's what a config with rerouting disabled always
  produces regardless of `familiarity`.
- **Shortcut edges:** the spawn room and the exit-alcove doorway (CP3) sit in
  the same open room with no wall between them — a real, walkable shortcut
  the scripted tour ignores. Two extra graph edges (`CP0→CP3`,
  `spawn→CP3`, real walking distance ≈12.3 m / ≈11.4 m via JuPedSim's own
  routing engine) are declared in each config's top-level `transitions`,
  tagged with a `journey_id` that isn't part of the scripted tour — so they
  exist only for the rerouting/cognitive-map system to discover, and never
  affect a plain (non-rerouted) run.

## What's Being Validated

1. **`full` finds and uses the shortcut** — with its complete graph
   knowledge, a `full` agent's very first route evaluation (forced to happen
   at spawn, before it starts walking the scripted tour) finds
   `spawn→CP3→exit` cheaper than the scripted route and reroutes onto it
   immediately (`reason="better_path"`).
2. **`discovery` explores instead of knowing** — a `discovery` agent starts
   knowing only its spawn's one declared neighbor (CP0). With no exit
   reachable in its own knowledge yet, it heads to the nearest known-but-
   unvisited checkpoint (frontier exploration, `reason="explore"`),
   physically arrives, learns what's beyond it, and repeats. For this
   maze's specific distances, the nearest unexplored checkpoint at every
   step happens to be the next stop on the original scripted tour (e.g. from
   CP0, the CP1 detour at ~6.5 m is closer than the CP3 shortcut at
   ~12.3 m) — so `discovery` retraces the full scripted tour, never
   discovering the shortcut before it reaches the exit anyway.
3. **The two tiers produce measurably different outcomes** — not just
   different internal state, but different total evacuation time.

## Background: why this test exists

Two independent bugs meant `familiarity` had *no effect whatsoever* before
this work, on any scenario:

- **`journeys_v2` schema mismatch.** The web editor saves drawn routes as
  `journeys_v2`; the simulation loader only ever read the legacy `journeys`
  field. Editor-drawn routes were silently dropped and the scenario fell
  back to auto-routing. Fixed by migrating `journeys_v2` → legacy
  `journeys`/`transitions` in `load_scenario`.
- **`familiarity` dropped before reaching agents.** `_process_distributions`
  rebuilt each distribution's parameters from a fixed allowlist that didn't
  include `familiarity`, so every agent was silently treated as `full`
  regardless of what the config said. Fixed by adding it to the allowlist
  and propagating it onto each spawned agent's path state.

And even with both fixed, the routing engine had no way to *act* on a
`full` agent's superior knowledge in a single-exit scenario: rerouting only
ever compared *which exit* to head for, never *which path* to a fixed exit.
Two additions closed that gap:

- `nearest_frontier_target` (frontier exploration) for the "no route to an
  exit known yet" case.
- Same-exit path-cost comparison in `evaluate_and_reroute`
  (`reason="better_path"`) so an agent can switch onto a cheaper path to the
  exit it's already assigned to, not just a different exit.

## Method

1. Load both configs (`assets/Familiarity Test Full`,
   `assets/Familiarity Test Discovery`) — identical except `familiarity`.
2. Run each with rerouting enabled (default on) and route-history collection
   turned on.
3. Compare total evacuation time and inspect `route_history` for which
   reroute reasons fired for each tier.

## Directory Contents

```
assets/Familiarity Test Full/
├── config.json          — JuPedSim scenario: exits, checkpoints, distribution
│                           (familiarity: "full"), scripted journey +
│                           shortcut-only transitions
├── geometry.wkt          — Walkable area (Shapely WKT), matches the FDS deck
├── build_geometry.py     — Parametric geometry generator (re-run to reshape)
└── layout_preview.png    — Rendered floor plan (green=spawn, red=exit)

assets/Familiarity Test Discovery/
└── (same four files; config.json differs only in familiarity: "discovery")

testing directory/Familiarity Test/
├── familiarity_test.fds              — FDS input, real &REAC combustion
├── social_force_sketch_fire.smv      — Smokeview scene file
├── social_force_sketch_fire.out      — FDS console output / run log
├── social_force_sketch_fire_devc.csv — Device output (time-series)
├── social_force_sketch_fire_hrr.csv  — Heat release rate over time
├── social_force_sketch_fire_steps.csv— Solver timestep log
├── social_force_sketch_fire.pickle   — Cached fdsreader data
└── social_force_sketch_fire_*.sf/.s3d — Slice/3D field data (multi-mesh)

tests/test_familiarity_routing.py     — Unit tests for shortest_path_to,
                                          nearest_frontier_target, and the
                                          better_path/explore reroute branches
```

## How to Run

CLI (rerouting is on by default; shown explicitly for clarity):

```bash
uv run run.py --scenario "assets/Familiarity Test Full" \
  --enable-rerouting --reroute-interval 1 \
  --output-route-history results/familiarity_full_routes.csv \
  --seed 420

uv run run.py --scenario "assets/Familiarity Test Discovery" \
  --enable-rerouting --reroute-interval 1 \
  --output-route-history results/familiarity_discovery_routes.csv \
  --seed 420
```

Or from the webapp: pick the scenario in the sidebar, leave `Enable
rerouting` checked (default), and run.

No `--fds-dir`/`--vis-cache` needed for the result below — the divergence is
purely distance-based (see [Scope](#scope--caveats)).

## Results / Pass Criteria

**Status: passing.** Both tiers evacuate all agents; `full` takes the
shortcut and finishes markedly faster than `discovery`, which retraces the
scripted maze tour.

| Tier      | Evacuated | Evacuation time | Route switches                    |
|-----------|-----------|------------------|------------------------------------|
| full      | 20/20     | **35.1 s**       | 20 × `better_path` (at spawn, t≈0) |
| discovery | 20/20     | **75.1 s**       | 0 (nearest-unexplored always matched the scripted tour) |

`discovery` showing zero explicit switches is expected, not a bug: its
frontier choice happens to coincide with the scripted route at every step
for this maze's specific checkpoint distances (see
[What's Being Validated](#whats-being-validated), point 2) — it's still
routing purely off its own explored knowledge, it just never gets lucky
enough to find the shortcut before finishing.

Full test suite (`tests/test_familiarity_routing.py` plus the existing
`tests/test_route_graph.py` / `tests/verification/test_s4_tjunction_reroute.py`)
passes with no regressions.

## Scope / Caveats

- **The scenario is authored to exhibit this behavior**, not automatically
  discovering it on arbitrary geometry. The shortcut edges are hand-added to
  the config; a checkpoint graph with only one possible route (or a
  single-hop map with nothing to explore) will make `full` and `discovery`
  behave identically regardless of the underlying mechanism.
- **This result doesn't need the fire deck.** `familiarity_test.fds` exists
  and is geometrically paired with this maze for a follow-up smoke/toxicity-
  driven variant (discovery agents losing sight of exits through smoke via
  `--vis-cache`).
- On a tie (two frontier candidates equidistant from a discovery agent), the
  choice is deterministic (lexicographically-first checkpoint ID), not
  randomized per agent — every discovery agent facing an identical tie makes
  the identical choice.
