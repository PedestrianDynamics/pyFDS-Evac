# Stage graph, crossings and signs — design

Date: 2026-08-03

## Problem

pyFDS-Evac wants a routing mode that plain JuPedSim does not have: **crossings in
the graph, no author-defined journey, agents free to choose by cost.** Today that
combination cannot be expressed.

Two routing modes exist:

- **No journey** — every agent targets its nearest exit, chosen per agent by
  straight-line distance to the exit polygon (`find_nearest_exit_journey`).
  Crossings are irrelevant, exactly as in JuPedSim.
- **Explicit journey** — the editor stores `journeys_v2` as `{id, name, color,
  sequence}`, an ordered path per distribution selected through
  `journey_weights`. `_migrate_journeys_v2` rewrites it into a linear chain.

The stage graph auto-wires itself only in the first mode, and only while every
node is a distribution or an exit (`route_graph.py:131`). Adding one crossing
without transitions silences the guard and produces a graph with **zero edges**:

```
no crossing : 3 nodes, 2 edges
one crossing: 4 nodes, 0 edges
```

So an author who draws crossings but no journey gets no routing at all, and a
scenario needing intermediate nodes must hand-author its transitions — which
means encoding a guess about the building's circulation and then measuring the
model against a benchmark it was told the answer to.

This matters because smoke acts on two channels, and one of them needs
intermediate nodes:

- **Cost** — smoke and FED raise the price of routes through them.
- **Information** — smoke hides signs, so an agent may not know an alternative
  exists.

With a bipartite distribution→exit graph the second channel is inert: sign
gating checks the sign of `path[1]`, which *is* the exit, and discovery has no
intermediate node to arrive at.

## Element semantics (settled, no change needed)

- **exit** — terminal stage; the agent leaves through it.
- **crossing / checkpoint** — intermediate stage; somewhere to route through and
  re-decide.
- **distribution** — spawn area; a source node only.
- **sign** — `{x, y, alpha, c}` attached to a node. Marks *its own* node and
  answers "is that stage legible from here". 1:1 with an fdsvismap waypoint.

`alpha` is a compass bearing (degrees clockwise from north) defining a
**half-plane** of readability with cosine falloff: head-on gives factor 1, 90°
to the side gives 0, behind is clipped to 0. `alpha=None` is natively supported
by fdsvismap and means **omni-directional** (`FDSVisMap.py:353`).

Agents on the `discovery` tier expand their cognitive map by three rules; only
two are smoke-dependent:

| when | rule | smoke-dependent |
|---|---|---|
| at spawn | spawn node + adjacent nodes whose signs are legible from the centroid | yes |
| on arrival at a node | all its neighbours | **no — unconditional, by decision** |
| at re-evaluation | adjacent nodes whose signs are legible from the agent's position | yes |

Arrival stays unconditional: standing at a junction means you have read every
sign there. This keeps discovery monotone — an agent never fails to learn what
it walked to.

Note that `expand_from_visibility` adds all neighbours when no `VisibilityModel`
is loaded, so **discovery is only meaningful with visibility data present**;
without it a discovery agent converges to full familiarity after one tick.

## Change 1 — auto-wire all stage types

When `transitions` is empty, build the graph from stage types instead of bailing
out:

- **distributions** → outgoing edges to every crossing and every exit
- **crossings** → outgoing edges to every other crossing and every exit
- **exits** → terminal, no outgoing edges

An edge is a directed pair of nodes and carries no geometry of its own. Its
realised path comes from `_make_edge`, which asks JuPedSim's routing engine for
a polyline through the walkable area — so the path turns corners rather than
cutting through walls, and both the edge weight (`_polyline_length`) and the
sampled mean extinction (`integrated_extinction_along_polyline`) are measured
along that real route. A straight centroid-to-centroid ray is used only when no
walkable polygon is supplied, which in practice means unit tests.

Explicit `transitions`, when present, remain authoritative and this path is
skipped, so existing scenarios are untouched.

Consequence: with no smoke the direct distribution→exit edge is cheapest, agents
take the nearest exit, and crossings sit inert — matching plain JuPedSim. With
smoke, a two-hop path through a crossing can undercut the direct one, so agents
route around the smoke and may end at a different exit.

Cost is O(n²) routing-engine calls once at graph build, cached in
`route_segment_cache`. A 22-node graph is ~500 edges.

**JuPedSim's constraint does not apply here.** A JuPedSim waypoint stage needs a
journey, but pyFDS-Evac does not steer through journeys: agents sit on a
`DirectSteeringStage` and their target coordinate is written every tick from
`wait_info["current_target_stage"]` (`direct_steering_runtime.py:81`). Routing
lives entirely in `StageGraph`; the JuPedSim journey is a formality.

## Change 2 — signs mandatory, with an omni default

Every exit and crossing gets a sign. When the author supplies none, synthesise:

| field | default | rationale |
|---|---|---|
| `x, y` | node polygon centroid | the sign sits on the exit/crossing |
| `c` | 3 | reflective; the conservative half of the 3/8 convention |
| `alpha` | `None` | omni-directional — no orientation guess |

A guessed `alpha` silently blanks half the floor for agents on the wrong side,
however clear the air; a missing `alpha` merely omits an effect. Declining to
guess is strictly safer.

This closes a hole: `node_is_visible` currently returns `True` for any node
without a sign (`visibility.py:254`), making it permanently known regardless of
smoke and silently exempt from the model. With synthesised signs every node is
gated uniformly.

Two edits follow. `_build_vismap` does `alpha=float(sign["alpha"])` and must
accept and pass through `None`. `extract_sign_descriptors` gains the synthesis
step so it returns a descriptor for every exit and crossing.

## Change 3 — position-aware distance from the router, not a straight line

> **DEFERRED to a follow-up PR (decided 2026-08-05).** This change edits
> `_position_aware_length`, which exists only on
> `fix/route-cost-first-segment-exposure` (PR #44, unmerged). It is **not** part
> of `fix/per-agent-spawn-origin`; on that branch and on `main` the logic is
> still inline inside `evaluate_route`. Changes 1 and 2 shipped without it.

`_position_aware_length` measures the agent's remaining distance and its
backtrack with `math.hypot`:

```python
remaining = math.hypot(px - next_node.centroid_x, py - next_node.centroid_y)
backtrack = math.hypot(px - first_node.centroid_x, py - first_node.centroid_y)
```

Both cut corners. On an L-corridor a mid-leg agent's remaining distance is
understated by 17 % and the straight segment lies outside the walkable area
entirely. Both branches understate, so mid-leg agents are systematically
under-priced against the node-aligned agents the graph assumes — and the error
is largest in the corridor layouts where position-aware routing was introduced
to cure rerouting oscillation.

Replace both with the routing engine's walkable path length, the same source of
truth `_make_edge` already uses:

```python
remaining = _polyline_length(routing_engine.compute_waypoints(agent_pos, next_centroid))
```

The routing engine is therefore threaded from `StageGraph` into route
evaluation. Where it is absent — unit tests without a walkable polygon — the
Euclidean form remains as the fallback, matching `_make_edge`'s own behaviour.
If a query fails or returns fewer than two waypoints, fall back to Euclidean
rather than raising: a wrong distance degrades ranking, an exception ends the
run.

**Cost is not a concern.** Measured at ~1 µs per query on a Station-sized mesh:
420 agents × 2 endpoints is 0.8 ms of a 1 s tick. The expensive part of
`RoutingEngine` is building the navigation mesh once, which already happens at
graph construction. Within a single `rank_routes` call an agent has one current
target and one source node, so all candidate routes share the same two
endpoints and the natural memo key is `(position, node_id)` — but even the naive
per-route call is affordable.

## Scenario instance — The Station nightclub

The model changes above stand alone. The Station is one scenario that exercises
them, and its benchmark value is that NIST NCSTAR 2 Vol. I §6.6 specifies the
setup completely and publishes results from two independent models.

**Geometry.** `assets/station/geometry.wkt` is the single source of truth.
Internal walls belong in it; `wkt_to_fds.py` inverts the walkable area to solid
cells and emits `&MESH` plus greedy-merged `&OBST` boxes, auto-refining `dx` to
resolve thin walls. The same WKT therefore drives JuPedSim, FDS, and — through
the generated deck — fdsvismap's occlusions.

**Stages.** 8 distributions at NIST's per-room densities (2.17 / 1.56 / 0.72
persons/m², 36 scattered, 420 total); 4 exits at the clear widths of Table 7-6
(all side doors 914 mm; the main entrance limited by its 914 mm interior door);
and 2 crossings, both documented in Table 6-1 rather than invented:

- `cp_ticket_area` — main floor → ticket area → vestibule → double doors, marked
  by LSF 13 ("exit sign in the main floor area with an arrow towards the ticket
  area") and LSF 10. This is where the 914 mm constriction and the crush were.
- `cp_rear_bar` — LSF 9, "exit sign located near the rear bar; it appears to be
  pointing toward the kitchen exit door".

**No `journeys`, `transitions`, or `waypoint_routing`.** Change 1 builds the
graph; cost decides.

**Signs** default per Change 2, except where Table 6-1 documents otherwise.
LSF 11/12 record that the platform exit sign was not always illuminated, which
maps onto the `c=3` reflective versus `c=8` light-emitting distinction and gives
a sensitivity case for free.

**One config serves both paper sections:**

- **§5 validation** — no smoke, `familiarity: full`, all hazard weights zero,
  rerouting disabled. Crossings inert, nearest exit. NIST's rule unmodified.
- **§6 parameter study** — FDS fields plus `VisibilityModel`,
  `familiarity: discovery`. Same geometry and graph; smoke now raises route
  costs and hides signs.

## Testing

- Auto-wiring with a crossing present yields a connected graph and every exit
  reachable from every distribution; the current 0-edge behaviour is the
  regression being fixed.
- Explicit transitions still take precedence — an existing single-distribution
  asset produces an unchanged graph.
- A synthesised sign appears for every exit and crossing lacking one, at the
  node centroid with `c=3` and `alpha=None`.
- `alpha=None` reaches fdsvismap unconverted and yields omni-directional
  visibility.
- With smoke on the direct route and a clear two-hop alternative, the cheaper
  route runs through the crossing; without smoke it does not.
- On an L-corridor, a mid-leg agent's credited remaining distance equals the
  walkable path length, not the straight line, and exceeds the Euclidean value.
- Without a routing engine, the Euclidean fallback still applies and existing
  position-aware tests are unchanged.

## Out of scope

- Discovery and familiarity behaviour beyond what Change 2 requires; the
  arrival rule is settled and unchanged.
- The Station throughput gap against NIST's 188 s. Diagnosing that needs the
  corrected graph first, and is separate work.
- Directional signs as independent objects pointing at a remote destination.
  Settled: a sign marks its own node.
