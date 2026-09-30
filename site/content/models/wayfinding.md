---
title: "Wayfinding"
weight: 5
math: true
aliases: [/models/visibility/]
---

> [!NOTE]
> This page is the specification of the wayfinding model. For worked cases on
> the assets (runs, figures, numbers), see [Wayfinding in practice](/docs/wayfinding.md).

Based on: [Visibility through smoke](/fundamentals/visibility.md) and
[Exit choice and familiarity](/fundamentals/exit-choice.md).

fdsvismap is pinned to commit `64d9aa7` in `pyproject.toml` (dependency
`fdsvismap`).

The [routing model](/models/routing.md) ranks and refuses routes. This page
describes the part of the model that decides which routes it may rank: what
each agent knows about the stage graph, how that knowledge starts, how it
grows, and how route choice reads it. The intuition is on
[Concepts › Wayfinding](/docs/concepts.md#wayfinding). Symbols follow the
[notation table](/docs/concepts.md#notation).

## Terms

These words are used with one meaning each, here and on the linked pages.

- **Stage graph.** The directed graph of spawn areas, checkpoints, waypoints
  and exits, with the walkable legs between them as edges
  (`route_graph.py`, `StageGraph.from_scenario`). A **neighbour** of a node is the target of one
  of its outgoing edges.
- **Sign.** A descriptor \(\{x, y, \alpha_s, C\}\) attached to a node: position,
  compass bearing \(\alpha_s\) of the direction the sign faces, and the
  visibility constant *C* of Jin's law.
- **Legible.** A sign is legible from a grid cell at a time when it passes the
  precomputed sign-legibility test below. Legibility is a property of the
  present position and time.
- **Known.** A node or edge is known to an agent when it is stored in that
  agent's cognitive map. Knowledge persists.
- **Learn.** A node or edge is learned when it is added to the map.
- **Visited.** A node is visited when the agent's stage at that node
  completes, after any wait there (`expand_on_arrival`, called at
  `scenario.py`, `run_scenario`). This includes a stage with nothing scripted after
  it, where the agent goes idle (`direct_steering_runtime.py`, `advance_path_target`). The
  spawn node is visited from the start.
- **Frontier.** A known node that is not visited.
- **Sign-legibility test** versus **route exposure gate.** The first decides
  whether a neighbour is learned. The second, described on the
  [routing page](/models/routing.md), judges the smoke along a route that is
  already known. They are separate mechanisms.

## Coded form

<a id="sign-visibility"></a>

### 1. The sign-legibility test

Every exit, checkpoint and waypoint carries a sign (`visibility.py`, `extract_sign_descriptors`). A
non-empty authored `"sign"` is used as written and must give `x` and `y`. A
node without one, or with an empty one, receives a synthesised sign at its
routing point with \(C = 3\) and \(\alpha_s\) = `None` (`visibility.py`, `_default_sign`).
A node whose polygon cannot give a position gets no sign. Spawn areas carry no
sign. The model treats every node without a sign as legible from everywhere
(`visibility.py`, `VisibilityModel.node_is_visible`).

```json
"exits": {
  "exit_A": { "sign": {"x": 0.5, "y": 11.5, "alpha": 90, "c": 3} }
}
```

An optional `"max_distance"` (m, positive) sets that sign's reading distance
\(V_{\max}\), for example for a larger or internally illuminated sign.

\(\alpha_s\) is a bearing in degrees, clockwise from north (+y). The sign faces
\((\sin\alpha_s, \cos\alpha_s)\), so 90 is readable from the east, 270 from the
west and 180 from the south (`visibility.py`, `VisibilityModel`).

The test is computed by [fdsvismap](https://github.com/FireDynamics/fdsvismap)
(pinned at `64d9aa7` in `pyproject.toml`). For sign *k* and a grid cell at
distance \(L\) (`FDSVisMap._get_view_angle_array`, `_get_visibility_array`,
`get_vismap`):

$$
A = \begin{cases}
\operatorname{clip}_{[0,1]}\!\left(\dfrac{\sin\alpha_s\,\Delta x + \cos\alpha_s\,\Delta y}{L}\right) & \alpha_s \text{ given},\\[1ex]
1 & \alpha_s = \texttt{None},
\end{cases}
\qquad
\bar K = \frac{1}{|P|}\sum_{p\in P} K_p ,
$$

$$
V = A \cdot U \cdot \min\!\left(\frac{C}{\bar K},\, V_{\max}\right),
\qquad \text{legible} \iff V \ge L .
$$

- \((\Delta x, \Delta y)\) is the cell position minus the sign position
  (`FDSVisMap.py`, `VisMap._get_view_angle_array`), and \(L\) is their distance; reversing the
  vector would flip the readable half-plane.
- \(U\) is 0 when an obstruction cell lies on the rasterised ray from the sign,
  1 otherwise (anti-aliased rays, `aa=True`).
- \(\bar K\) is the arithmetic mean extinction over the cells of a rasterised
  line between the two cells, not a length-weighted integral.
- When \(\bar K = 0\), the capped term is \(V_{\max}\).
- \(V_{\max}\) is the sign's reading distance: 30 m by default, as in
  fdsvismap and Börger et al. `--max-sign-distance` sets it for every sign,
  and a sign's own `max_distance` overrides it for that sign
  (`_apply_distance_caps` in `visibility.py`). It caps \(C/\bar K\) before
  \(A\) and \(U\) apply, as upstream, so in clear air a sign is legible up
  to \(A \cdot V_{\max}\).

The obstruction factor applies in clear air too: a wall hides a sign there as
it does in smoke.

![Animation of a sign turning away from a standing agent. As the angle grows, the visibility curve falls; when it drops below the 6 m distance near 53°, the sight line turns from solid blue to dashed red and the heading changes from a filled blue "sign legible" to a hollow red "sign not legible"](/images/wayfinding/sign_rotation.gif)

*An agent stands 6 m from a sign in uniform smoke (\(\bar K\) = 0.3 m⁻¹,
C = 3, so \(C/\bar K\) = 10 m) while the sign turns away. Every value comes
from the pyFDS-Evac visibility model. Right: the visibility
\(A \cdot C/\bar K\) against the bearing \(\alpha_s\); the dotted line is the
agent's distance \(L\). Solid blue line and filled marker: legible; dashed red
line and hollow marker: not legible. Yellow cells are the positions from which
the model reads the sign; the gold arrow shows which way it faces. \(V_{\max}\)
= 30 m does not bind. The sign is lost at about
53°, well before it is side-on.
Script: `scripts/figures/sign_rotation.py`.*

**Two ways to build the model** (`run_config.py`, `_build_vis_model`):

- **From an FDS run** (`--fds-dir`). Grid, obstructions and extinction come
  from the FDS output. The `SOOT EXTINCTION COEFFICIENT` slice is the
  horizontal one nearest `--smoke-slice-height` (1.6 m by default since #164,
  `run.py`, `_build_parser`), chosen by the same rule as walking speed and
  FED, with a warning when it is more than 0.5 m away (`fds_sampling.py`,
  `select_horizontal_slice`). Stored times are spaced by `--reroute-interval`
  (`visibility.py`, `_build_vismap`; `run_config.py`, `_build_vis_model`).
- **From clear air** (no `--fds-dir`). The walkable polygon is rasterised at
  `--vis-cell-size`. A cell is an obstruction when its centre lies outside the
  polygon (`visibility.py`, `_blocked_runs`, `VisibilityModel.clear_air`). A wall thinner than one cell
  *may* therefore let sight through, depending on how it falls on the grid.
  The extinction is zero, and one time point is stored (`visibility.py`, `VisibilityModel.clear_air`).

At run time the model answers `node_is_visible(t, x, y, node)` by looking up
the nearest stored time and cell, clamped to the stored range
(`visibility.py`, `_VisMapCache._nearest`, `VisibilityModel.node_is_visible`). No ray is cast inside the time loop.
`--vis-cache` stores the arrays in an `.npz` file. The FDS cache is keyed by
the FDS directory path, the signs, the time step, the slice height and the
maximum sign distance; it
does not hash the FDS output, so replacing the output in place leaves a stale
cache valid (`visibility.py`, `_make_meta`, `_load_vismap_cache`).
fdsvismap also reads the obstructions at the slice height, so which walls
occlude a sign can change with `--smoke-slice-height`
([#165](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/165)).

<a id="which-visibility-setting-am-i-running"></a>

**Which model a run gets** (`run_config.py`, `_build_vis_model`):

| invocation | model |
|---|---|
| no flags, some group with familiarity < 1 | clear air |
| no flags, every group at familiarity 1 | none |
| `--clear-air-visibility` | clear air, even if every group is fully familiar |
| `--no-visibility` | none |
| `--fds-dir DIR` with a `SOOT EXTINCTION COEFFICIENT` slice, some group with familiarity < 1 | FDS smoke, uncached |
| `--fds-dir DIR --vis-cache PATH` with a `SOOT EXTINCTION COEFFICIENT` slice | FDS smoke, cached |
| `--fds-dir DIR` without a `SOOT EXTINCTION COEFFICIENT` slice, some group with familiarity < 1 | clear air, with a warning ([#248](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/248)) |
| `--fds-dir DIR --vis-cache PATH` without a `SOOT EXTINCTION COEFFICIENT` slice | clear air, cached, with a warning |
| `--fds-dir DIR`, every group at familiarity 1 | none (smoke still drives speed, FED and the exposure gate) |
| `--vis-cache PATH`, no `--fds-dir` | clear air, cached |

In every case a scenario from which no sign can be extracted gets no model
(`run_config.py`, `_build_vis_model`). Rejected combinations: `--clear-air-visibility`
with `--fds-dir`, `--clear-air-visibility` with `--no-visibility`, and
`--vis-cache` with `--no-enable-rerouting` (`run_config.py`, `validate_opts`).

<a id="cognitive-maps"></a>

### 2. The knowledge contract

Haensel (2014) split the cognitive map into knowledge, perception and
decision-making, with first-order knowledge (the spatial layout, as a
graph) and second-order knowledge that adds perceived information such as
smoke, signs or jams (as summarised by Schröder et al. 2015, p. 329).
Schröder et al. added a smoke sensor that feeds this second-order
knowledge. In pyFDS-Evac the map holds only the layout; smoke
enters through the route cost, not the map.

Each agent's `AgentCognitiveMap` holds known nodes, known edges and visited
nodes (`cognitive_map.py`, `AgentCognitiveMap`). The contract has four parts.

**2.1 Initial knowledge** (`init_cognitive_map`, `cognitive_map.py`).
`familiarity` is a scenario key on a distribution group, normalised to a
probability \(p\): `"full"` is 1, `"discovery"` is 0, a number in [0, 1] is
used as given, anything else raises (`cognitive_map.py`, `familiarity_probability`). The key
defaults to `"full"` (`simulation_init.py`, `_initialize_with_fallback`).

- \(p = 1\): the map is the whole stage graph. It is never extended.
- \(p < 1\): the map starts with the spawn node, marked visited. Then, in
  order:
  1. **Entrance.** If `entrance` names an exit reachable from the spawn node,
     the shortest path to it is learned. A name that is missing, is not an
     exit, or cannot be reached is silently ignored (`cognitive_map.py`,
     `_learn_route_to`, `init_cognitive_map`).
  2. **Familiarity draw.** Each other reachable exit is learned, with its
     shortest path, with probability \(p\). The draw uses an RNG seeded from
     the run seed and the agent's spawn order, not its JuPedSim id
     (`agent_seed.py`, `agent_rng`; `scenario.py`, `_assign_initial_exit`,
     `run_scenario`). A library caller
     that passes no RNG gets no draw (`cognitive_map.py`, `init_cognitive_map`).
  3. **Perception at spawn.** Each neighbour of the spawn node whose sign is
     legible **from the spawn node's routing point** is learned
     (`cognitive_map.py`, `init_cognitive_map`). Agents of one spawn area that spawn at
     the same time therefore start with the same perceived neighbours.

Paths learned in steps 1 and 2 add forward edges only
(`cognitive_map.py`, `_learn_route_to`).

**2.2 Learning** (\(p < 1\) only). Two calls add knowledge:

- **Periodic.** When an agent's re-evaluation is due, each neighbour of its
  current node (`current_origin`, else `current_target_stage`) whose sign is
  legible from the agent's **stored position** is learned
  (`expand_from_visibility`, `cognitive_map.py`, called at
  `scenario.py`, `run_scenario`). The stored position is written in the steering
  loop (`scenario.py`, `run_scenario`), which runs after the reroute pass, so it holds
  the previous step's coordinates. Without a visibility model nothing is
  learned.
- **On advancing along the path.** When the agent completes a stage and its
  path advances (after any waiting time at that stage), the node is marked
  visited, and each of its neighbours whose sign is legible from the agent's
  position is learned (`expand_on_arrival`, `cognitive_map.py`,
  called at `scenario.py`, `run_scenario`). Without a visibility
  model, **every** neighbour is learned.

The three places knowledge is sensed from:

| When | Sensing position | Code |
|---|---|---|
| Initialisation | spawn node's routing point | `cognitive_map.py`, `init_cognitive_map` |
| Periodic learning | previous step's stored position | `scenario.py`, `run_scenario` |
| Stage completion (arrival) | current position | `scenario.py`, `run_scenario` |

Learning is **limited to neighbours** of one node. A legible sign that belongs
to any other node is not tested. An edge learned by either call also teaches
its reverse when the graph contains that reverse edge (`_learn_edge`,
`cognitive_map.py`). With automatic wiring, exits have no outgoing
edges and spawn areas no incoming ones (`route_graph.py`, `StageGraph.from_scenario`), so no
reverse edge into a spawn area or out of an exit is learned. Explicit
`transitions` are added without these restrictions (`route_graph.py`, `StageGraph.from_scenario`).

**2.3 Memory.** No code removes a node or an edge from the map of an agent
that is still in the simulation. A node learned while its sign was legible
stays known after the sign stops being legible, through distance, bearing,
obstruction or smoke. The map is deleted when the agent leaves
(`scenario.py`, `run_scenario`).

**2.4 Decision.** Route ranking works on the known subgraph only:
`rank_routes` replaces the stage graph with `cognitive_subgraph(map, graph)`
before it evaluates any edge (`route_graph.py`, `rank_routes`;
`cognitive_map.py`, `cognitive_subgraph`). Dijkstra, the exposure gate, the ordering and the
all-refused fallback see known nodes and edges only. An exit that is not known
is not refused; it is absent, and the fallback cannot restore it.

**Exception ([#91](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/91)).**
Every agent receives the geometrically nearest exit as its steering target
before its map exists (`simulation_init.py`, `_find_nearest_exit`). The opening choice
replaces that target only when the map contains a reachable exit
(`scenario.py`, `_assign_initial_exit`). If it contains none, and neither exploration nor
patrol yields a target (below), the agent keeps steering towards that
geometric exit (`route_graph.py`, `_decide_explore`). For a map that holds only the
spawn node neither does: the spawn node is visited from the start
(`cognitive_map.py`, `init_cognitive_map`), so there is no frontier, and the patrol
excludes the current node, so a one-node map has no stop
(`cognitive_map.py`, `wander_target`). Periodic learning may add the exit
on the way once its sign is legible, but the target was never chosen from the
map. This is a defect, not intended behaviour (see also defect 2 in
`assets/blind_spawn_discovery/README.md`).

The contract covers **ranking**, not **adoption**. Ranking orders the known
routes; adoption is whether a moving agent switches to the first of them. The
two differ:

- **Opening choice** (`_assign_initial_exit`, `scenario.py`). It
  ranks the routes from the spawn node, with distances measured from the
  agent's position, as re-evaluation measures them, and without the queue
  tally (`scenario.py`, `_assign_initial_exit`). Agents of one spawn area
  can therefore start towards different exits.
- **Re-evaluation** (`evaluate_and_reroute`). It ranks from the agent's
  position. It adopts a different exit only if the rival passes the
  [switching rule](/models/routing.md#switching-rule) of the routing model:
  an optical-depth margin, then an anchor on the ranking cost. The
  optional queue term (`w_queue`, 0 by default) enters the ranking cost.
- **All refused.** When every known route fails the gate, the least smoky one
  is re-admitted, but the current route is kept first if the rival's worst
  extinction is not lower by `fallback_switch_margin`
  (`route_graph.py`, `_apply_fallback`, `_fallback_holds_current`).

An agent can therefore keep a known route that is not first in the ranking.

*Worked example (clear air).* Every \(\tau\) is 0, both routes are clean,
and the optical-depth deadband (\(\tau_{\max}\cdot\) `tau_deadband` =
6 × 0.1) is not crossed. The switch falls through to the anchor: a rival is
adopted only if its ranking cost, here its travel time, is below 0.9 times the
current route's (`route_graph.py`, `_AnchoredPolicy.anchor_allows`;
`exit_switch_anchor` = 0.9, `RerouteConfig.exit_switch_anchor`; `tau_max` = 6.0 and `tau_deadband` = 0.1,
`RouteCostConfig.tau_max`, `RouteCostConfig.tau_deadband`). An exit learned on the way is therefore adopted only if it is
more than 10 % faster than the exit the agent is heading for.

**No known exit.** When the known subgraph contains no reachable exit,
`evaluate_and_reroute` looks for a target (`route_graph.py`, `_decide_explore`):

1. **Explore.** The frontier node with the lowest path cost through the known
   subgraph, with the first leg measured from the agent's position; ties
   break on node id (`nearest_frontier_target`, `cognitive_map.py`).
   Logged as `reason="explore"`.
2. **Wander.** When no frontier is reachable, the next node in a fixed
   rotation over the sorted known nodes other than the current one, reached
   over known edges taken **in either direction**
   (`wander_target`, `_undirected_known_path`, `cognitive_map.py`).
   Logged as `reason="wander"`.

**What route choice does not read.** Route choice never reads the
sign-legibility test or a line-of-sight visibility
(`route_graph.py`, `AdditivePolicy.apply_candidate_set_rules`). `VisibilityModel.visibility_to_node` and
`distance_to_node` have no caller in `pyfds_evac/`
([#158](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/158)). Route
smoke is sampled from the global extinction field (see
[routing](/models/routing.md)) along the stored node-to-node polylines. The
route mean \(\bar K\), and so \(\tau\), the gate and the ranking, take the
first leg as the agent's share of that polyline. When the agent's position is
given, the first leg is also resampled along the walk from the agent to its
next node, for every familiarity tier (`_polyline_stats` in `evaluate_route`).
That walk is the routing engine's path through the walkable area, the same one
that measures the first leg's length; without an engine, or when the query
fails, it is the straight line. Samples are spaced at most `sampling_step_m`
along the walk's full length, including the stretch behind the route's origin
node. The resample feeds only two secondary quantities: the route's worst sample
`k_max_route`, which decides whether an agent keeps its exit when every route
is refused (`route_graph.py`, `_fallback_holds_current`), and the worst leg mean, which decides the optional
clean tier, off by default (`clean_extinction_threshold` = 0). Under the `"additive"` model only, a route
whose every segment has \(\bar K \ge 0.5\) m⁻¹ is refused while another
non-refused route has a segment below it (`route_graph.py`, `AdditivePolicy.apply_candidate_set_rules`); this is
an extinction threshold, not a sign test.

## Parameters

`familiarity`, `entrance` and `sign` are scenario keys. The other rows are
command-line options, with the default of the underlying class for direct
library use.

| Setting | Source | `run.py` value | Library default | Unit | Meaning |
|---|---|---|---|---|---|
| `familiarity` | distribution `parameters` | – | `"full"` (`simulation_init.py`, `_initialize_with_fallback`) | – | `"full"`, `"discovery"` or \(p \in [0,1]\) |
| `entrance` | distribution `parameters` | – | none (`simulation_init.py`, `_initialize_with_fallback`) | – | a reachable exit learned at spawn |
| `sign.c` | node `sign` | – | 3 (`visibility.py`, `_default_sign`, `_build_vismap`) | – | *C* |
| `sign.alpha` | node `sign` | – | `None`, i.e. \(A = 1\) (`visibility.py`, `_default_sign`) | ° | bearing the sign faces |
| \(V_{\max}\) | `--max-sign-distance` | 30 | 30 (`DEFAULT_MAX_SIGN_DISTANCE_M`) | m | reading distance of every sign, also in clear air |
| `sign.max_distance` | node `sign` | – | none, i.e. \(V_{\max}\) | m | reading distance of this sign |
| `--smoke-slice-height` | CLI | 1.6 (`run.py`, `_build_parser`) | 1.6 (`visibility.py`, `VisibilityModel.__init__`) | m | FDS slice height |
| `--reroute-interval` | CLI | 1.0 (`run.py`, `_build_parser`) | 10.0 (`route_graph.py`, `RerouteConfig.reevaluation_interval_s`) | s | re-evaluation interval, hence periodic learning |
| vismap time step | = `--reroute-interval` | 1.0 (`run_config.py`, `_build_vis_model`) | 10.0 (`visibility.py`, `VisibilityModel.__init__`) | s | FDS model only; clear air stores one time |
| `--vis-cell-size` | CLI | 0.25 (`run.py`, `_build_parser`) | 0.5 (`visibility.py`, `VisibilityModel.clear_air`) | m | clear-air grid; FDS models use the FDS mesh |
| `--vis-cache` | CLI | none | none | – | `.npz` cache path |

The `--vis-cell-size` docstring advises a cell smaller than the thinnest wall
(`visibility.py`, `VisibilityModel.clear_air`). Results for discovery agents have not converged
with the cell size ([#168](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/168)).

## Where it acts in the time step

1. **Before the loop.** The visibility model is built or loaded
   (`run_config.py`, `build_run_kwargs`). Each agent placed at t = 0 gets its map and opening
   choice (`scenario.py`, `run_scenario`); flow-spawned agents get theirs when they
   appear (`scenario.py`, `run_scenario`).
2. **Reroute pass.** It runs at most once per simulated second
   (`scenario.py`, `run_scenario`). For each agent whose re-evaluation is due,
   periodic learning runs first, then ranking and possible adoption.
3. **Steering loop, every step.** Positions are stored
   (`scenario.py`, `run_scenario`), and learning on advancing along the path runs when a
   stage completes (`scenario.py`, `run_scenario`). This learning is not tied to the
   reroute pass.
4. **History.** With `collect_cognitive_map_history` (on in `run.py`,
   `run_config.py`, `build_run_kwargs`), a row is written whenever the number of known nodes or
   edges changes (`scenario.py`, `run_scenario`).

With `--no-enable-rerouting`, the map is still built, still sets the opening
choice, and still grows on advancing along the path, but no later decision
reads it.

## Deviations from the literature

The published visibility law is on
[Visibility through smoke](/fundamentals/visibility.md). The legibility test
is the waypoint method of Börger, Belt and Arnold (2024), Eqs. (2) and
(7)–(10). The cognitive map follows the design of Haensel (2014).

- **Per-sign reading distance.** Börger et al. cap visibility at 30 m and
  add that "the exit signs have a maximum visual distance even in a
  smoke-free environment" (p. 5, below Eq. 10). pyFDS-Evac keeps 30 m as the
  default and lets a sign set its own `max_distance`. It does not derive that
  distance from sign size or a signage standard.
- **Cap before angle.** Börger et al. write
  \(V = \min(U\,A\,C/\bar\sigma,\ V_{\max})\) (Eq. 10, p. 5). fdsvismap computes
  \(A\,U\,\min(C/\bar K, V_{\max})\). They agree while \(C/\bar K < V_{\max}\);
  in clear air, off-axis, the paper gives \(V_{\max}\) and fdsvismap gives
  \(A\,V_{\max}\). This is our reading of the rendered Eq. (10) against the
  pinned source.
- **Averaged extinction.** \(\bar K\) is the cell average of Börger et al.
  Eq. (9), a simplification of their Eq. (8). Jin measured his law in uniform
  smoke, so applying it to an average along a line of sight is an
  extrapolation.
- **View angle.** The cosine factor is the Lambertian assumption of Börger et
  al., who call it "highly simplified" (p. 4). It is not part of Jin's
  experiments.
- **Sampling height.** Börger et al. use one slice at 2 m, with the eye at
  sign height (p. 4). The code uses 1.6 m, the [FDS+Evac](https://github.com/firemodels/fds/tree/c9da70d7a/Source) `HUMAN_SMOKE_HEIGHT`.
  The extinction slice is the horizontal one nearest that height, as for
  walking speed and FED. *Our inference:* exit signs are usually mounted above
  doors, higher than 1.6 m. Under a hot smoke layer, a 1.6 m slice reads less
  extinction than the line of sight to such a sign crosses, so it overstates
  legibility. That error is non-conservative.
- **Synthesised signs.** A sign the building may not have: reflective,
  *C* = 3, readable from every direction. *C* = 3 is the FDS default for a
  reflecting sign; the Fundamentals page gives Jin's range as 2–4 for
  reflecting and 5–10 for light-emitting signs.
- **Legibility is binary** and acts only on knowledge. In the discrete-choice
  studies on [Exit choice and familiarity](/fundamentals/exit-choice.md), exit
  visibility enters the utility as a graded attribute.
- **Knowledge of topology, not of smoke**
  ([#125](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/125)).
  Learning is limited by the sign-legibility test. Route costs are not: an
  agent that knows an exit prices the whole route to it from the global
  extinction field, including legs it has never seen and, with `anticipate`,
  future times (`route_graph.py`, `RouteCostConfig.anticipate`, `RouteCostConfig.foresight_horizon_s`). The route choice of a discovery
  agent is therefore not limited by what it has perceived.
- **Haensel's heuristics are not reproduced.** Haensel (2014, §3.2) weights
  known edges by sensors (smoke, density, room-to-corridor) and uses a
  `LastDestinationsSensor` against back-tracking. He reports that with an
  empty map and no sensors agents stay where they are, and calls the
  `DiscoverDoorsSensor` mandatory for empty maps (§4.3, p. 47). That sensor
  "adds all possible out edges" of the agent's current sub-room (§3.2.2). It is
  the counterpart of `expand_on_arrival` without a visibility model. With a
  visibility model, the code gates the same step by sign legibility. The code
  uses frontier exploration and a patrol instead of his weighting heuristics.

## Limitations

- **An agent with no known exit can walk to an unknown one**
  ([#91](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/91)). See
  the exception under §2.4. The intended behaviour is exploration.
- **FED and arrival times behind the origin node**
  ([#171](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/171), open).
  The first-leg smoke now follows the walked path at `sampling_step_m`, but
  the FED growth over the walk to the route's origin node is not counted, and
  anticipated arrival times start at the origin node (`route_graph.py`,
  `_measure_route`, `_arrival_time`). See §2.4, "What route choice does not
  read".
- **A sign is never read beyond its reading distance.** \(V_{\max}\) is
  30 m by default ([#173](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/173)),
  so in clear air a sign farther away is illegible at any bearing, and a
  discovery agent in a space wider than that must approach an exit to learn
  it. The value is a default, not derived from sign size or a signage
  standard; set `"max_distance"` per sign where it matters. FDS+Evac has no
  such limit ([Coming from FDS+Evac](/docs/coming-from-fds-evac.md#seeing-a-door-vs-reading-a-sign)).
- **Learning is limited to neighbours**, spawn perception is per spawn area,
  and periodic learning uses the previous step's position (§2.1–2.2).
- **The patrol can stall**
  ([#122](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/122)). It
  visits only known nodes. When smoke limits legibility to a few metres, the
  walks between them may never pass a new legible sign.
- **Discovery results depend on the clear-air grid**
  ([#168](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/168)). Do
  not report a discovery egress time without its grid;
  [Wayfinding in practice](/docs/wayfinding.md) gives the measured spread.
- **No per-exit familiarity**
  ([#136](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/136)). One
  \(p\) per group, plus one `entrance`.
- **Discovery agents turn back at the door of the only exit**
  ([#250](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/250)).

**Fixed behaviour.** Two earlier defects are fixed: discovery agents ranked
the first leg as a straight line through walls
([#172](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/172), fixed
by #174), and clear-air travel time was under-priced when an agent was
farther from its next node than the route's origin
([#167](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/167), fixed
by #170).
- **No sharing.** Maps are per agent; no agent learns from another.
- **No individual variation** in *C*, eye height or the legibility threshold.

## Relation to FDS+Evac

From `materials/evac.f90` (FDS commit c9da70d7a, FDS 6.7.6); line numbers
refer to that file. The detailed account of FDS+Evac door choice is on
[model comparison](/docs/model-comparison.md).

| Concept | FDS+Evac | pyFDS-Evac |
|---|---|---|
| **Visible** | Geometric line of sight from agent to door centre, or to the door's `XB` centre from the correct side; no range limit, no contrast, no angle factor | *Legible*: sign test with *C*, view angle, obstruction, \(V_{\max}\) and line-of-sight extinction |
| **Known** | `KNOWN_DOOR` (default `.FALSE.`) and `KNOWN_DOOR_PROBS` per door, written at initialisation into a per-agent or per-group list; afterwards only downgraded | *Known*: seeded by `familiarity` (one \(p\) per group) and `entrance`, then learned from legible signs; never downgraded |
| **Visible counts as known** | for the current target in `imode == 1` calls (`:16533–16535`), and for any visible door for type-1 agents; both for the current call only | a legible neighbour is learned and kept |
| **Memory of the target** | a current target with positive `I_Target` stays visible | every known node persists |
| **Smoke-free door** | tiers 1–3 admit a door with \(\bar K < \lvert\texttt{FED\_DOOR\_CRIT}\rvert\) = 0.03 m⁻¹ by default (≈ 100 m visibility); the door of the current flow field is tested at `FAC_DOOR_OLD` = 0.1 × \(\bar K\), so it passes below 0.3 m⁻¹ | roughly the exposure gate, applied to route optical depth \(\tau = \bar K L\) along the route |
| **Last resort** | tier 4 ranks by \(0.5\,d/(3/\bar K)\); a door with value ≥ 1 is struck out for that call | the all-refused fallback re-admits the least smoky known route |
| **Smoke memory** | lone agents mark the previous target negative or zero | none |
| **Default** | agent type 2, `KNOWN_DOOR = .FALSE.` | `familiarity = "full"` |

Details, with line numbers:

- **Default knowledge.** `KNOWN_DOOR` defaults to `.FALSE.` on `&EXIT` and
  `&DOOR` (`:2291`, `:2733`), and the default agent type is 2, the "known
  door" agent (`:3774`). Our reading is that FDS+Evac's default agent is
  closer to `discovery` than to `full`. The two are not equivalent: see
  "Knowledge" below.
- **Visibility.** `See_door` casts a straight line and returns `.FALSE.` only
  when an obstruction blocks it (`:15682–15813`, walls at `:15762`, `:15803`).
  It also returns the mean extinction on that line. A door counts as seen when
  its centre is seen, or when the centre of its `XB` is seen from the correct
  side: `PP_see_door = See_door(X,Y) .OR. (See_door(XB) .AND. PP_correct_side)`
  (`:16486–16494`). For DOORs without `EXIT_SIGN`, visibility also needs the
  door to be the current target or already known (`:16500–16507`).
- **Smoke acts in the door choice, not in seeing.** \(\bar K\) is floored at
  \(0.5\,\lvert\texttt{FED\_DOOR\_CRIT}\rvert\) = 0.015 m⁻¹ for either sign of the
  criterion (`:16497`), which is converted from a visibility with
  \(S = 3/K\) (`:5494–5496`).
  - Tiers 1–3 admit a door only while \(\bar K < \lvert\texttt{FED\_DOOR\_CRIT}\rvert\)
    (`:16589`, `:16601`, `:16608`, `:16683–16690`, `:16732–16737`).
    The door that shares the current target's flow field is discounted
    first: its \(\bar K\) is multiplied by `FAC_DOOR_OLD` (default 0.1,
    `:1571`; applied at `:16591`, `:16685`, `:16734`), so the current door
    stays "smoke free" up to 0.3 m⁻¹ by default. This is a hysteresis on
    route retention, comparable in role to our anchor and deadband.
  - In tier 4, with the default criterion, a door is scored
    \(0.5\,d/(3/\bar K)\). \(d\) is the Euclidean distance for a visible door
    and the L1 distance for a non-visible one (`:16793–16797`). A score ≥ 1
    clears the door's visible and known flags for that call (`:16798–16801`).
- **Knowledge.** The known list is written at initialisation (`:16230`,
  `:16279–16293`), per agent or per group (`Group_Known_Doors`,
  `:16259–16276`), and it persists across calls. The visible and known flags
  of one call are rebuilt from it each time (`:16170–16171`). Type-1 agents
  count a visible door as known within the call (`:16513`), and a current
  target with positive `I_Target` stays visible (`:16531`).
- **Smoke marks** (lone agents only, `HR%GROUP_ID < 0`, `:16628`). For the
  previous target, `L2_tmp` and `L2_tmp2` are scaled by `FAC_DOOR_OLD2` and
  `FAC_DOOR_OLD` (`:16626–16627`). When `L2_tmp2 ≥ |FED_DOOR_CRIT|`, the list
  entry becomes its negative node id, or zero when `L2_tmp ≥ 1`
  (`:16628–16637`). Under the defaults the mark starts at
  \(\bar K \ge 0.3\) m⁻¹.
- **The difference.** In our reading of the code, FDS+Evac never adds a door
  to the known list after initialisation. It only downgrades entries. What an
  agent sees counts only within the call that sees it. pyFDS-Evac learns: a
  legible sign adds the node to the map, and the node stays known after the
  sign stops being legible. The legibility test itself (*C*, bearing, view
  angle, line-of-sight extinction) has no FDS+Evac counterpart. The exposure
  gate is a separate mechanism, related to FDS+Evac's smoke-free and tier-4
  criteria (see [routing](/models/routing.md)).
- **No counterpart.** FDS+Evac's herding and follower agents (types 3 and 4)
  and its group behaviour.

<a id="verification-familiarity-comparison"></a><a id="visualising-cognitive-map-evolution"></a><a id="diagnostic-scripts"></a>

## Verification

These tests check implementation behaviour. They do not validate human
wayfinding or evacuation times. The FDS-case check is
[Verification › Familiarity](/verification/testing-familiarity.md): its
criteria 1–5 pass, and the discovery egress time is not grid-converged
([#168](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/168),
[#250](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/250)).

- `tests/test_exit_visibility_alpha.py` (`assets/exit_visibility_alpha`): the
  bearing of the near sign decides whether the near exit is learned; an
  unknown exit is absent, not refused.
- `tests/test_cognitive_map_memory.py` (`assets/cognitive_map_memory`): an exit
  is learned inside its legibility region, stays known and routable outside
  it, is not learned by a probe that never enters the region, and ranks first
  at a return probe where its sign is not legible.
- `tests/test_blind_spawn_discovery.py` (`assets/blind_spawn_discovery`):
  learning hop by hop, occlusion on advancing, reverse edges, frontier choice
  by position, termination of exploration.
- `tests/test_scalar_familiarity.py`: \(p\) as a probability, reproducible
  draws, `entrance` known and reachable.
- `tests/test_initial_exit_from_cognitive_map.py`: the opening choice ranks
  the map, with rerouting off.
- `tests/test_initial_exit_per_agent.py`: the opening choice is measured from
  each agent's position; one spawn area in a room with two mirrored doors
  splits between them.
- `tests/verification/test_cognitive_map_verif.py`: tier invariants on a toy
  graph.

`tests/test_familiarity_routing.py::TestDiscoveryMeasuresAroundWalls` pins
the #172 fix. No test pins the #91 behaviour or convergence with the grid
(#168).

## Sources

- Börger, K., Belt, A., & Arnold, L. (2024). *A waypoint based approach to
  visibility in performance based fire safety design*. Fire Safety Journal,
  150, 104269.
  [doi:10.1016/j.firesaf.2024.104269](https://doi.org/10.1016/j.firesaf.2024.104269)
- Haensel, D. (2014). *A knowledge-based routing framework for pedestrian
  dynamics simulation*. Diploma thesis, Technische Universität Dresden. No
  DOI or public URL known.
- Schröder, B., Haensel, D., Chraibi, M., Arnold, L., Seyfried, A., &
  Andresen, E. (2015). *Knowledge- and perception-based route choice
  modelling in case of fire*. Proceedings of the 6th International
  Symposium on Human Behaviour in Fire, Cambridge, UK, pp. 327–338.
  Interscience Communications. No DOI;
  [juser.fz-juelich.de/record/255940](https://juser.fz-juelich.de/record/255940).
- fdsvismap, [github.com/FireDynamics/fdsvismap](https://github.com/FireDynamics/fdsvismap),
  commit `64d9aa73144b3902bdc6d2cdd1a08e3494ec5690`.
- Korhonen, T. (2021). *Fire Dynamics Simulator with Evacuation: FDS+Evac.
  Technical Reference and User's Guide*.
  [github.com/tkorhon1/FDS-Evac-Guide](https://github.com/tkorhon1/FDS-Evac-Guide).
