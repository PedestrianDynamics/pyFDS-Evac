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
  `build_geometry.py` (`assets/familiarity_test_full/`,
  `assets/familiarity_test_discovery/`). One spawn room (bottom-right), one
  exit alcove (top-right).
- **Model:** `SocialForceModel`, seed 420, 20 agents (`by_number` spawn, all
  at once — not flow-spawned).
- **Fire deck:** `assets/familiarity_test_full/familiarity_test.fds`.
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

1. Load both configs (`assets/familiarity_test_full`,
   `assets/familiarity_test_discovery`) — identical except `familiarity`.
2. Run each with rerouting enabled (default on) and route-history collection
   turned on.
3. Compare total evacuation time and inspect `route_history` for which
   reroute reasons fired for each tier.

## Directory Contents

```
assets/familiarity_test_full/
├── config.json          — JuPedSim scenario: exits, checkpoints, distribution
│                           (familiarity: "full"), scripted journey +
│                           shortcut-only transitions
├── geometry.wkt          — Walkable area (Shapely WKT), matches the FDS deck
├── build_geometry.py     — Parametric geometry generator (re-run to reshape)
├── layout_preview.png    — Rendered floor plan (green=spawn, red=exit)
└── familiarity_test.fds  — FDS input, real &REAC combustion; walls mirror
                             geometry.wkt so smoke propagates through the
                             same doorways agents use. Not run/committed
                             here — see Scope for what does and doesn't
                             need it.

assets/familiarity_test_discovery/
└── (same five files; config.json differs only in familiarity: "discovery")

tests/test_familiarity_routing.py     — Unit tests for shortest_path_to,
                                          nearest_frontier_target, and the
                                          better_path/explore reroute branches
```

## How to Run

CLI (rerouting is on by default; shown explicitly for clarity):

```bash
uv run run.py --scenario assets/familiarity_test_full \
  --enable-rerouting --reroute-interval 1 \
  --output-route-history results/familiarity_full_routes.csv \
  --seed 420

uv run run.py --scenario assets/familiarity_test_discovery \
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

## Observing the map from outside: `collect_cognitive_map_history`

The cognitive map is built and grown inside `run_scenario`, so until recently
the only way to inspect it was to re-implement the expansion against a graph
built the same way — which tests the re-implementation, not the engine's call
sites, and those call sites are where the bugs above actually lived.

`run_scenario(..., collect_cognitive_map_history=True)` returns
`ScenarioResult.cognitive_map_history`: one row each time an agent's map
changes, with `time_s`, `agent_id`, `familiarity`, `known_nodes` and
`known_edges`. Maps only ever grow, so recording changes rather than every
timestep keeps a crowd-scale run cheap while losing nothing.

```python
result = run_scenario(scenario, seed=420, vis_model=vis,
                      collect_cognitive_map_history=True)
for event in result.cognitive_map_history:
    print(event["time_s"], len(event["known_nodes"]))
```

`scripts/animate_cognitive_map.py` turns that history into a movie of one agent
walking with its known nodes highlighted, and authors inward-facing sign angles
for a deck that has none.

**Perception needs a visibility model.** With `vis_model=None`,
`cognitive_map._expand_visible` returns immediately, so a discovery agent's map
grows only when it physically arrives somewhere (`expand_on_arrival`). On a deck
where the agent walks straight from spawn to an exit, that means it never grows
at all — see the "blind agent" issue in the tracker. A clear-air stand-in
(line of sight against the walkable polygon plus the sign's readable half-plane)
is enough to exercise the wiring without FDS output; the test suite and the
animation script each carry one.

## Clear-air visibility without an FDS run

`VisibilityModel.clear_air(walkable, sign_descriptors, cell_size_m=...)` builds a
visibility model from geometry alone: fdsvismap's own ray casting, view angle and
`max_vis` handling, over a uniform zero extinction field. It exists because
`vis_model=None` silently disables perception — a discovery agent's map then
never grows — and because five separate approximations of fdsvismap had
accumulated in this repo, none of them applying the view angle.

**Resolution is a real parameter.** A cell blocks sight when its centre lies
outside the walkable polygon, so a wall thinner than one cell disappears and
sight passes through it — the same property an FDS mesh has. At the 0.5 m
default the ~0.4 m walls of `assets/blind_spawn_discovery` vanish entirely and
occlusion tests silently stop testing anything; 0.25 m resolves them. Cost grows
as the inverse square. Pick it below the thinnest wall that must block.

This requires the fdsvismap branch adding `set_grid` / `set_uniform_extco`
(FireDynamics/fdsvismap#41); `pyproject.toml` pins it until that is released.
