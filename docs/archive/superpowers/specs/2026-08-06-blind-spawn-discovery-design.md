# Blind spawn: discovery through occlusion

Date: 2026-08-06

## Why

Three cognitive-map mechanisms are unit-tested and have never run in a
simulation. Two recent bugs — #61 and the position-aware cost — were both cases
where the unit tests passed and the simulation did the opposite, so
"unit-tested" is not the reassurance it looks like.

| mechanism | current coverage | never exercised |
|---|---|---|
| frontier exploration (`reason="explore"`) | 2 tests in `test_familiarity_routing.py`, hand-built graph | any simulation |
| `expand_on_arrival` (unconditional reveal) | `test_cognitive_map_verif.py`, 1 hop | multi-hop growth, any simulation |
| betweenness pruning of auto-wired edges | `TestAdjacencyIsMeaningful`, synthetic graph | any simulation |
| line-of-sight occlusion (`non_concealed_cells_array`) | **nothing, at any level** | everything |

Every existing discovery asset is a spawn area and two exits in one convex
room, and every builder *asserts* that at least one exit is legible from the
spawn area — deliberately, to keep those scenarios interpretable. The
consequence is that no asset can produce an agent that knows no exit, which is
the state the Station's dance floor is in.

## What "legible" means

Taken from the installed `fdsvismap`, not from our READMEs, which omit the last
two terms. A sign `w` at `(x_w, y_w)` with bearing `α` and factor `c` is legible
from `(x, y)` at time `t` iff

```
view_angle · visibility · non_concealed  ≥  distance
```

| term | definition | source |
|---|---|---|
| `distance` | `hypot(x − x_w, y − y_w)` | `_get_dist_array` |
| `view_angle` | `clip((sin α·(x−x_w) + cos α·(y−y_w)) / distance, 0, 1)`, or `1` when `α is None` | `_get_view_angle_array:352` |
| `visibility` | `min(c / K̄, max_vis)`, `= max_vis` where `K̄ = 0`; `max_vis = 30 m` | `_get_visibility_array:557` |
| `K̄` | mean extinction **along the ray** from sign to cell | `_get_mean_extco_array_at_time` |
| `non_concealed` | 0/1 line-of-sight mask — geometry blocks | `all_wp_non_concealed_cells_array_dict` |

A further clause, `≥ min_vis`, never fires: `min_vis` defaults to 0.

`_default_sign()` synthesises `{alpha: None, c: 3}` for every crossing, so
crossings are omni-directional: legible whenever within `min(c/K̄, 30)` m **and
not occluded**. That is what makes exploration possible here — the doorways are
visible, the exits behind them are not.

## Geometry

Two exit rooms behind a corridor behind a hall. All internal walls are in the
WKT, so `wkt_to_fds` carries them into the deck and hence into fdsvismap's
occlusion mask.

```
 y=30  +---------------+---------------+
       |   west room   |   east room   |
       |   [E_west]    |   [E_east]    |
 y=22  +-----[C2]------+------[C3]-----+     doorways, 2 m wide
       |          corridor             |
 y=18  +------------[C1]---------------+     doorway, 2 m wide
       |                               |
       |          spawn hall           |
       |         30 agents             |
 y=0   +-------------------------------+
      x=0                            x=24
```

- `C1` at `(12, 18)` — the only thing a spawning agent can see.
- `C2` at `(6, 22)`, `C3` at `(18, 22)`.
- `E_west` at `(6, 28)`, `E_east` at `(18, 28)`.
- Spawn area `x ∈ [2, 22]`, `y ∈ [2, 8]`; centroid `(12, 5)`.

Distances from the spawn centroid: `C1` 13 m, `E_west` 24.7 m, `E_east` 24.7 m.

**Every exit is inside the 30 m ceiling.** That is the point, and the builder
must assert it: the exits are hidden by the *wall*, not by distance. Without
that guard the asset degrades into a second copy of the visibility-ceiling
pitfall documented in `assets/exit_visibility_alpha/README.md`, and the
occlusion term — the only untested one — would carry none of the result.

`E_west` and `E_east` are symmetric so that neither wins on distance; which one
an agent takes is decided by which doorway it explores first, and by nothing
else. Ties are resolved by `nearest_frontier_target`'s deterministic
`sorted(frontier)` ordering, so the split is reproducible rather than
arbitrary — a test asserts it is *not* 30/0, which would mean the frontier
choice ignores position.

> **Outcome.** It was 30/0. `nearest_frontier_target` measured from the graph
> node and never from the agent, so the tie broke identically for everyone. The
> asset first shipped documenting that limitation; issue #68 fixed it and the
> split is now 18/12. This paragraph was the prediction, and it was right for a
> reason the spec did not anticipate.

## The expected sequence

For a `discovery` agent, clear air:

| hop | map before | routing | why |
|---|---|---|---|
| 0 | `{spawn, C1}` | `rank_routes` → **empty** → explore to `C1` | no exit known; `C1` legible, exits occluded |
| 1 | `+ C2, C3` on arrival at `C1` | still empty → explore to nearer of `C2`/`C3` | `expand_on_arrival` reveals neighbours unconditionally; `spawn→exit` and `C1→exit` edges are pruned by betweenness, so no exit is adjacent yet |
| 2 | `+ E_west` (or `E_east`) on arrival | exit ranked, agent commits | first exit reached is the one behind the doorway it chose |

This is the first scenario in the repository where the map grows over more than
one hop, and the first where `reason="explore"` appears in a run.

## Configs

One geometry, four configs, each changing exactly one thing.

| config | familiarity | entrance | what it isolates |
|---|---|---|---|
| `config_discovery.json` | `discovery` | — | the sequence above |
| `config_full.json` | `full` | — | contrast and lower bound: straight out, no exploration |
| `config_entrance.json` | `discovery` | `E_west` | seeding: knows `E_west` at t=0, so it never explores |
| `config_mixed.json` | `0.5` | — | scalar familiarity in a run: roughly half explore |

`config_entrance.json` is the mechanism behind the Station crush in miniature —
everyone entered by one door, so everyone knows that door — and it is currently
wired through the code with no behavioural test anywhere.

## Claims, and what would falsify each

**Exploration**
1. A discovery agent's map at t = 0 is exactly `{spawn, C1}`. Falsified if any
   exit is in it — occlusion is not working.
2. The run produces `reason="explore"` switches. Falsified if the route history
   has none: agents found an exit without exploring.
3. Every agent evacuates. Falsified by a stall — exploration that does not
   terminate is worse than no exploration.
4. Discovery egress > full egress. The cost of not knowing the building.

**Occlusion, guarded from both ends**
5. `build_geometry.py` refuses to write the asset unless every exit is within
   `MAX_VIS_M` of the spawn centroid *and* occluded from it.
6. A test asserts the same, and additionally that removing the walls makes the
   exits legible — so the occlusion mask, not some accident of bearing or
   distance, is what hides them.

**Multi-hop map growth**
7. `C2` and `C3` enter the map only after arrival at `C1`, not before.
8. No exit is adjacent to the spawn area or to `C1` in the auto-wired graph.
   This is betweenness pruning, and if it regresses the whole scenario
   collapses to one hop without any test failing on the pruning itself.

**Entrance and scalar familiarity**
9. `config_entrance.json` produces **zero** explore switches and an egress time
   at or near the `full` bound, with every agent leaving by `E_west`.
10. `config_mixed.json` at `p = 0.5` puts the share of agents that explore in a
    band around 0.5 — a band, not a point, because 30 agents is a small sample.
11. Two runs of `config_mixed.json` at the same seed give the same split.

## Fire variant (phase 3, separable)

A deck with a burner in the west room, so `E_west` becomes FED-lethal after an
agent has committed to it. This is the one safety corner with no test at any
level: the only known exit turns deadly, `old_must_flee` bypasses the
`exit_switch_anchor` — and then what? If `E_east` is not yet known, the agent
must fall back to exploration rather than stand still.

Held separate because it needs a real fire and a tuned burner, and because the
clear-air claims must be established first; a run where both smoke and
exploration are in play cannot attribute an outcome to either.

## Deliberate choices

**Clear air in phase 1 and 2.** The extinction field is zero, so
`visibility = max_vis` everywhere and legibility depends on geometry alone. Any
change in what an agent knows is attributable to where it stands.

**No journeys or transitions.** The graph auto-wires and cost decides, which is
also what puts betweenness pruning on the critical path.

**Symmetric exits.** Removes distance as an explanation for the split.

**30 agents.** Enough that a 50/50 familiarity draw is not dominated by one
agent, few enough that the corridor does not congest and add a queue term
nobody asked for.

## Out of scope

- Smoke-driven rerouting: `assets/t_junction` covers it.
- Sign bearing: `assets/exit_visibility_alpha` covers it.
- Memory persistence: `assets/cognitive_map_memory` covers it.
- Any tuning of `exit_switch_anchor` or the frontier heuristic. This asset is
  built to observe them, not to fit them.

## Risks

**Betweenness pruning might not prune what the sequence assumes.** The rule uses
walkable distance when a routing engine is present, so `C1` genuinely lies on
every path from the hall to any exit and the `spawn→exit` edges should go. If
they survive, claim 8 fails first and loudly, before any behavioural claim is
misread. That ordering is deliberate.

**`expand_on_arrival` may reveal more than intended.** It ignores visibility
entirely. If arriving at `C1` reveals the exits as well as `C2`/`C3`, the
scenario becomes two hops instead of three — which is a real finding about the
degeneracy the Station spec flags, not a defect in the asset. Claim 7 is written
to detect it either way.

**FDS run time.** The deck is geometry plus slices, no fire, so it is cheap; the
same output serves all four configs, since they differ only in JSON. The fire
variant does not share it.
