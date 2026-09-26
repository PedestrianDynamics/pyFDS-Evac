---
title: "Visibility-aware routing and cognitive maps"
weight: 4
math: true
---

Based on: [Visibility through smoke](/fundamentals/visibility.md) and [Exit choice and familiarity](/fundamentals/exit-choice.md).

Implements [Spec 008](https://github.com/PedestrianDynamics/pyFDS-Evac/blob/main/specs/008-visibility-aware-routing/SPEC.md): sign
visibility gates what each agent comes to *know*, and per-agent cognitive maps
carry that knowledge into routing. Sign visibility does not reject routes.

Symbols follow the [notation table](/docs/concepts.md#notation).

Background: the [Concepts](/docs/concepts.md) page and the talk [*A Modular Workflow for Visibility-Aware Evacuation Modelling*](https://pedestriandynamics.org/pyFDS-Evac/talks/visibility-seminar-2026/)
([PDF](https://pedestriandynamics.org/pyFDS-Evac/talks/pyFDS-Evac_visibility_seminar_2026.pdf)).

## Sign visibility

Each exit and checkpoint can carry a `"sign"` descriptor in the scenario
config:

```json
{
  "exits": {
    "exit_A": {
      "sign": {"x": 0.5, "y": 11.5, "alpha": 90, "c": 3}
    }
  }
}
```

`alpha` is a compass bearing (degrees from north, clockwise): 90 = sign
visible from the east, 270 = from the west, 180 = from the south.

Every exit, checkpoint and waypoint gets a sign: nodes without an authored
`"sign"` get one synthesised at the node's polygon centroid (`c=3`,
`alpha=None`, i.e. omni-directional). A node is never exempt from
visibility gating for lack of an authored sign.

At each reevaluation tick the `VisibilityModel` checks whether an agent can see
a node's sign, using a cached
[fdsvismap](https://github.com/FireDynamics/fdsvismap) grid.

**Sign legibility decides what an agent *knows*, not whether a route is
allowed.** A sign it can see admits that node to the agent's cognitive map
(`cognitive_map.expand_from_visibility`), and the map is what Dijkstra may route
over -- so an unknown exit is *absent from the graph* rather than
present-and-vetoed. Route choice does not consult the visibility model at all,
so an agent can use an exit it has learned after the sign goes out of view.

![Two 30 m corridors, each with an exit at both ends; left, the near sign faces the agents and all 40 go to the near exit; right, the near sign faces away and all 40 walk to the far exit](/images/concepts/sign_bearing.png)

*`assets/exit_visibility_alpha`: 4 m × 30 m corridor in clear air, 40 agents with
familiarity 0. The two configurations differ only in the bearing of the near
exit's sign. Facing the agents (0°), all 40 took the near exit; facing away
(180°), all 40 walked to the far exit. One run of each configuration, as
recorded in the asset README. Script: `scripts/figures/sign_bearing.py`.*

```bash
# Build or reuse the vismap cache; smoke hides signs from the cognitive map
uv run run.py \
  --scenario assets/t_junction \
  --fds-dir assets/t_junction \
  --enable-rerouting \
  --vis-cache assets/t_junction/vismap_cache.npz \
  --output-route-cost-history route_costs.csv \
  --cleanup
```

Under the default `"gate"` route-cost model the only rejection reasons a route-cost CSV carries are `tau ...`
(optical depth over budget), `FED_max ...` (dose over threshold), and either of
those under a `fallback:` prefix.

### Which visibility setting am I running?

Sight gating decides how an agent comes to know a node, and the flags choose
between three different scenarios. Nothing here changes the physics; it changes
what the agent is allowed to perceive.

| invocation | model | the scenario it means |
|---|---|---|
| *(no flags)*, deck has discovery agents | clear air | **no fire.** Agents learn a node by seeing its sign: walls occlude, sign facing and contrast apply |
| *(no flags)*, every agent `familiarity = 1.0` | none built | agents hold the whole graph from t=0 and never consult it, so building one would cost time and change nothing |
| `--clear-air-visibility` | clear air, forced | as above, on a deck whose agents are fully familiar -- only useful for comparison runs |
| `--no-visibility` | none | **not a fire scenario.** Sight gating is absent, so an agent learns every neighbour of each node it reaches, by contact rather than by sight |
| `--fds-dir DIR` | none for sight | smoke drives speed reduction and FED, but what an agent can *see* is ungated |
| `--fds-dir DIR --vis-cache PATH` | smoke | **the coupled run.** Sight gated by that fire's extinction field: smoke hides signs, so the map stops growing |
| `--vis-cache PATH` (no `--fds-dir`) | clear air, cached | same as the default, with the grid reused between runs |

Rejected combinations:

| combination | why |
|---|---|
| `--clear-air-visibility --fds-dir` | claims clear sight while a fire burns -- the one combination that silently produces a wrong answer |
| `--clear-air-visibility --no-visibility` | contradictory |
| `--vis-cache` or `--clear-air-visibility` with `--no-enable-rerouting` | a sight gate with nothing to act on |

`--vis-cell-size` sets the grid the scene is rasterised at (default 0.25 m). A
wall thinner than one cell stops occluding, so keep it below the thinnest wall
that must block sight.

The three settings are genuinely different agents. Measured on
`assets/world_100`, one agent, `familiarity = 0`, same seed:

| setting | evacuation | route switches | cognitive map |
|---|---|---|---|
| `--no-visibility` | 58.5 s | 0 | learns each node's neighbours on arrival |
| clear air (default) | 188.8 s | 31, mostly `explore` | grows 3 -> 28 nodes |
| `--fds-dir` + `--vis-cache` | did not evacuate (400 s cap) | 30, nearly all `wander` | stays at 3 nodes: no sign is legible, so no frontier appears |

### Diagnostic scripts

```bash
# Coverage and ASET maps (sign placement validation)
uv run python scripts/demo_vismap_phase0.py

# With fresh vismap recompute
uv run python scripts/demo_vismap_phase0.py --no-cache
```

## Cognitive maps

Agents have a familiarity tier that controls how much of the building they
know at the start of the simulation:

| Tier | `familiarity` | Knowledge at spawn | Expansion |
|------|---------------|--------------------|-----------|
| Trained staff | `"full"` | Complete stage graph | — |
| Visitors | `"discovery"` | Spawn node + visible neighbors | On arrival + at reevaluation |

**The tier limits topology, not perception of smoke.** A `discovery` agent does
not know the building — it routes only over its cognitive subgraph and learns
nodes through the perception-limited `VisibilityModel`. It *does* know the smoke
field: to choose among the exits it knows, it integrates `tau = K_ave * L` over
the whole remaining route (optical depth, dimensionless), including legs it has never visited, and with
`anticipate = True` and `foresight_horizon_s = inf` at times that have not
happened. So route choice is an **optimality bound over the agent's known
subgraph**, not a behavioural model — map growth, exploration order and wander
behaviour are unaffected, but nothing here licenses the claim that a discovery
agent's *route choice* is perception-limited. Open as
[#125](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/125).

Set per distribution group in the scenario config:

```json
{
  "distributions": {
    "visitors": {
      "parameters": {
        "familiarity": "discovery"
      }
    }
  }
}
```

A deck with discovery agents gets a visibility model either way — from the FDS
extinction field when `--fds-dir` is given, from clear air otherwise (see the
table above) — because sight is gated by geometry, sign facing and contrast
whether or not there is a fire. Running with no model at all is what
`--no-visibility` asks for. Without a model the perception step adds nothing, so
a `discovery` agent starts
out knowing only its spawn node, its `entrance`, and whatever the familiarity
draw gave it. Graph adjacency is not used as a stand-in for line of sight:
with no `transitions` declared the graph is auto-wired from every spawn area to
every unblocked stage, so treating a neighbour as seen would hand most agents
most of the building's exits at t=0 and make `familiarity` inert.

The tier binds whether or not the scenario defines a journey, and it binds from
the **first step**: the agent's cognitive map is built at spawn and the exits it
knows are ranked by the same cost the reroute pass uses, so an agent
who knows only the front door walks to the front door however far it is.
`tests/test_initial_exit_from_cognitive_map.py` pins the
contract with rerouting off, where the opening choice is the only choice.

Each agent is rooted at its spawn area, and routing ranks every exit reachable
from there. Rooting it at the assigned exit instead would collapse the ranking
to that one exit at zero cost;
`tests/test_no_journey_routing_origin.py` pins the contract.

Default when the key is absent: `"full"` (backward compatible).

**Discovery expansion rules:**

1. **At spawn** — agent learns its spawn node, its `entrance` if one is set,
   each exit drawn as known by a scalar `familiarity`, and any adjacent node
   whose sign is currently visible from the spawn centroid. It then picks its
   first exit by ranking that map, not by geometry.
2. **On arrival** — when an agent physically reaches a node, the immediate
   neighbours whose sign is visible from where it stands are added (all of
   them when no visibility model is supplied).
3. **At reevaluation** — adjacent nodes whose sign is visible from the
   agent's current position are added.

Learning an edge also learns its reverse when the graph has one: knowledge
of a corridor is bidirectional, so an agent can always retrace its steps
out of a dead end whose far side shows it nothing new.

Routing (Dijkstra) runs over the agent's known sub-graph only. If no exit
is reachable in the cognitive map, the agent heads toward the nearest
known-but-unexplored node instead (a doorway it knows exists but hasn't
been through) — expanding its knowledge on arrival and re-evaluating from
there, until an exit becomes known. Reroute events for this show up in
`route_history` with `reason="explore"`. When every known node has been
visited and still no exit is reachable, the agent wanders: it patrols the
nodes it knows in a deterministic rotation (`reason="wander"`), because
sign legibility depends on position — a leg walked between two known nodes
can make a sign readable that never was from either node, restarting
discovery. Once an exit is known, the agent
also reroutes onto a cheaper *path* to that same exit as its knowledge
grows, not only when a different exit becomes preferable
(`reason="better_path"`).

### Visualising cognitive map evolution

```bash
# 4-panel figure: spawn → junction → reroute → full baseline
uv run python scripts/demo_cognitive_map_vis.py

# Without cached vismap (all neighbours assumed visible at spawn)
uv run python scripts/demo_cognitive_map_vis.py --no-cache
```

Figure: ![cognitive map evolution](/t_junction/cognitive_map_evolution.png)

## Verification: familiarity comparison

Two scenario configs differ only in familiarity tier:

| Config | Tier |
|--------|------|
| `assets/t_junction/config_full.json` | `familiarity=full` |
| `assets/t_junction/config_discovery.json` | `familiarity=discovery` |

Run both back-to-back and produce a 3-panel comparison (exit split,
rejection timeline, evacuation time):

```bash
uv run python scripts/run_familiarity_comparison.py \
    --fds-dir assets/t_junction \
    --vis-cache assets/t_junction/vismap_cache.npz
```

Outputs: `results/familiarity_comparison/{full,discovery}_route_costs.csv`,
`results/familiarity_comparison/comparison.png`.

## Deviations from the literature

The published law is on [Visibility through smoke](/fundamentals/visibility.md).
There *C* is a property of the sign, but every node without an authored sign
receives a synthetic reflective sign, readable from every direction, at its
centroid (`pyfds_evac/core/visibility.py:58`).
Legibility uses the mean extinction along the line of sight and a
view-angle correction (Börger et al. 2024), neither of which is part of Jin's
experiments in uniform smoke. fdsvismap's 30 m cap on visibility, the FDS
default, is raised to the domain diagonal before the map is computed
(`visibility.py:103`).
