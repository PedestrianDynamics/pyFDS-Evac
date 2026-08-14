# Routing, Exit Choice & Exit Signs — Notes

Working notes on how the current model chooses routes and exits, how the exit-sign
visibility system works, and where the exit-choice research papers disagree with
each other. All code references point at `pyfds_evac/core/route_graph.py`,
`pyfds_evac/core/visibility.py`, and `pyfds_evac/core/smoke_speed.py`.

Symbols used below:
- `K` — smoke extinction coefficient [1/m], sampled from the FDS field.
- `FED` — Fractional Effective Dose (toxic dose; incapacitation at ~1.0).
- Config defaults come from `RouteCostConfig` (`route_graph.py:609`), which a
  deck overrides through its `routing` block.
- `cost_model` selects between the default `"gate"` and the historical
  `"additive"` model — see [route-cost-gate.md](route-cost-gate.md).

---

## Part 1 — How routing & exit choice works

1. **The graph is built once, from static geometry.**
   `StageGraph.from_scenario()` (`route_graph.py:50`) creates a directed graph.
   - Nodes = stages: `distribution` (spawn), `checkpoint` (waypoint), `exit`.
   - Edges = the scenario's `transitions`, each with a fixed length in metres.
   - Smoke, FED and crowds are **not** stored in the graph — they are layered on
     live at query time.

2. **Edge length is the true walked distance where possible.**
   With a JuPedSim `RoutingEngine` + walkable polygon, each edge length is the
   polyline length around obstacles; otherwise it is the straight centroid line:
   ```
   length = polyline_length(waypoints)          # preferred
   length = euclidean(src_centroid, tgt_centroid)  # fallback
   ```

3. **Each edge gets a live cost from current conditions.**
   `evaluate_segment()` (`route_graph.py:528`) computes, at the current time:
   - Mean smoke along the edge: `k_avg` (integrated extinction over the edge).
   - Walking-speed slowdown from smoke — the **Lund / FDS+Evac linear law**
     (`smoke_speed.py:205`, α = 0.706, β = −0.057):
     ```
     speed_factor = clamp( 1 + (β · K) / α ,  min_factor=0.1 , 1.0 )
     ```
   - Effective speed and time to cross the edge (base speed = 1.3 m/s):
     ```
     effective_speed = base_speed · speed_factor
     travel_time     = length / effective_speed
     ```
   - Toxic dose picked up crossing the edge (fed_rate sampled at edge midpoint):
     ```
     fed_growth = fed_rate · travel_time / 60      # /60: per-minute → seconds
     ```
   - A crude per-edge visibility flag: `visible = (k_avg < 0.5)`.

4. **A full route's cost is the composite formula — under `cost_model:
   "additive"`.**
   The default is now `"gate"`, where the composite is still computed but does
   not rank; see item 8a below and [route-cost-gate.md](route-cost-gate.md).
   `evaluate_route()` (`route_graph.py:971`) sums edges into one route:
   ```
   path_length = Σ length
   K_ave       = Σ (k_avg · length) / Σ length      # length-weighted mean smoke
   travel_time = Σ travel_time
   FED_max     = current_fed + Σ fed_growth          # dose you'd ARRIVE with
   ```
   Composite cost (`route_graph.py:629`) — the number routes are ranked by:
   ```
   composite = path_length · (1 + w_smoke · K_ave)     ← distance, inflated by smoke
             + w_fed · FED_max                          ← toxicity penalty
             + w_queue · queue_distance                 ← congestion-at-exit delay
   ```
   where the queue term converts a wait into distance-equivalent units:
   ```
   queue_time     = n_at_exit / exit_capacity
   queue_distance = base_speed · queue_time
   ```
   **The three routing weights live here:** `w_smoke = 1.0`, `w_fed = 10.0`,
   `w_queue = 0.0`. `w_smoke` and `w_fed` are hand-picked and NOT calibrated.
   The queue term is **off by default**: it scales with a global `N`, so the
   weight expressing a given preference depends on the population and no
   constant suits every deck. `assets/station_fahy` opts in at `w_queue = 0.03`,
   calibrated against Fahy Table 2 at that deck's crowd of 333
   (`scripts/sweep_queue_weight.py`).

5. **Pathfinding uses live edge weights, not raw geometry.**
   `rank_routes()` (`route_graph.py:668`) runs in three phases:
   - Phase 1 — give every edge a dynamic weight (`route_graph.py:723`):
     ```
     edge_weight = length · (1 + w_smoke · k_avg) + w_fed · fed_growth
     ```
     (`current_fed` and the queue term are left out here because they are the
     same for every route to a given exit, so they don't change the *path*.)
   - Phase 2 — **Dijkstra** with those weights → cheapest path to *each* exit.
   - Phase 3 — re-score each full path with the composite (adds queue + FED).

6. **Toxicity is (also) a hard reject.**
   `route_graph.py:649`: if `FED_max > fed_rejection_threshold (1.0)` the route is
   marked **rejected**. NOTE: FED currently appears twice — as the `w_fed` penalty
   *and* as this hard cut — which is conceptually muddled (see the toxicity notes).

7. **Visibility is a hard reject too** (details in Part 2).

8. **Routes are sorted; the agent takes the best.**
   Sort key (`route_graph.py:1322`), additive:
   ```
   ( rejected? , composite_cost , hops )
   ```
   → survivable routes first, cheapest first, ties broken by fewer hops.

8a. **Under the default gate model, smoke gates instead of pricing.**
   A route is refused when Jin's sighting distance `S = c/K` drops below
   `sight_distance_fraction` (0.5) × the distance still to walk
   (`route_graph.py:1152`), and the survivors sort as
   ```
   ( rejected? , travel_time + w_queue·queue_time , hops )
   ```
   The quickest available route wins — smoke says which exits exist, not what
   each metre of them costs. The visibility band (`S // band_width_m`, capped at
   3 classes) no longer enters this sort; it survives as a diagnostic, as the
   ordering of the all-refused fallback, and as a condition on the anchor
   bypass. Refusals are recomputed every tick and never remembered, so the
   criterion relaxes as an agent closes on an exit.

9. **There is always a fallback.**
   If *every* route is rejected (`route_graph.py:1350`), the least-bad one is
   un-rejected so the agent always has somewhere to go. Under the gate,
   "least bad" is banded then nearest, held by `fallback_switch_margin` (0.2)
   against the rival's worst-case K.

10. **Agents re-choose periodically, staggered.**
    - `should_reevaluate()` (`route_graph.py:856`): re-run every
      `reevaluation_interval_s` (default 10 s).
    - `compute_eval_offset()`: each agent offset by `(agent_id mod steps) · dt`
      so they don't all recompute on the same tick.
    - `reroute_agent()` (`route_graph.py:873`): if the chosen exit changed, rewrite
      the agent's `path_choices` to follow the new path; log a `RouteSwitch`.

11. **Familiarity restricts the graph before routing.**
    If a `cognitive_map` is passed, `rank_routes` first cuts the graph down to the
    agent's *known* subgraph (`cognitive_subgraph`, `route_graph.py:696`). An
    unfamiliar agent can only route over stages it has discovered.

---

## Part 2 — How exit signs & visibility work

1. **Every routable node has a sign; authoring one is optional.**
   Any exit / checkpoint / waypoint may carry a `sign` block (e.g.
   `assets/t_junction/config.json:45`):
   ```json
   "sign": { "x": 0.5, "y": 11.5, "alpha": 90, "c": 3 }
   ```
   - `x, y` — the sign's world position.
   - `alpha` — compass bearing the sign faces (deg from north, clockwise).
   - `c` — contrast/visibility constant (default 3).
   `extract_sign_descriptors()` collects every exit, checkpoint and waypoint.
   An authored `sign` is kept verbatim; **a node without one gets a sign
   synthesised at its centroid** with `c = 3` and `alpha = None`
   (omni-directional), so no routable stage escapes smoke-dependent legibility.
   A node whose coordinates cannot form a polygon is skipped and stays ungated.

2. **Signs are directional.**
   A sign is only readable from the side it faces (`visibility.py:209`):
   ```
   alpha =  90  → visible from the EAST
   alpha = 270  → visible from the WEST
   alpha = 180  → visible from the SOUTH
   ```

3. **Visibility is computed by `fdsvismap` (waypoint method).**
   `VisibilityModel` (`visibility.py:206`) wraps the external `fdsvismap` library —
   the same waypoint-based approach as the `waypoint_based_visibility` paper.
   The call (`visibility.py:44`):
   ```
   vis.compute_all(view_angle=True, obstructions=True, aa=True)
   ```
   accounts for three things at once:
   - **Smoke** — integrated extinction `K` along the line of sight (from FDS).
   - **View angle** — Lambertian falloff; a sign seen edge-on is less readable
     (`cos θ` effect, tied to `alpha`).
   - **Obstructions** — walls / geometry blocking the sightline (ray-cast).
   The result is a precomputed boolean grid: for every `(time, sign, x, y)`, can an
   agent at `(x, y)` read that sign at that time? Cached to a safe `.npz`.

4. **There are two routing queries, and they answer different questions.**
   - `node_is_visible(time, x, y, node_id)` (`visibility.py:531`) → True/False:
     can the sign be *read* from here. Nodes with no descriptor — spawn areas, and nodes whose geometry
     was unusable — return True.
   - `visibility_to_node(time, x, y, node_id)` (`visibility.py:545`) → metres:
     how far the agent can *see* toward that node. This is Jin's `c / K_ave`
     with `K_ave` averaged along the real, obstruction-aware sight line — the
     same quantity FDS+Evac's `See_door` returns. It returns `None` rather than
     0 when there is no answer to give, because fdsvismap multiplies the sight
     line by the sign's readable half-plane and by obstructions, so a zero means
     "concealed", "behind the sign" or "smoked out" indistinguishably, and only
     the last is a statement about passability. A hidden sign is not a wall.
   - `distance_to_node(x, y, node_id)` supplies the straight-line distance the
     sighting distance is tested against. It is computed from the descriptor,
     not asked of the backend, so a run loaded from an `.npz` cache still has it.

5. **Legibility no longer rejects routes; it decides what the agent knows.**
   `rank_routes` does **not** consult sign legibility (see the comment at
   `route_graph.py:1294`). Readability feeds
   `cognitive_map.expand_from_visibility`, and the cognitive map decides what
   Dijkstra can see — so an unknown exit is *absent from the graph* rather than
   present-and-vetoed. Checking it again in ranking double-gated the same
   criterion, blocked agents who already knew the building, and forbade an agent
   from using an exit it had legitimately learned once the sign left view.

6. **Where the sight line does enter the route decision: the gate.**
   Under `cost_model: "gate"`, `evaluate_route` asks `visibility_to_node` for
   the sighting distance to the *exit's own* sign and refuses the route when it
   falls below `sight_distance_fraction × distance_to_node`. The rejection
   reason reads `sight (los) …`. When no sight line resolves — no descriptor, a
   concealed sign, or the agent standing behind it — it falls back to the *mean*
   K over the route polyline against the whole remaining length, reason
   `sight (path) …`. Both criteria average K; `path` is the harsher of the two
   only through its distance, which is the full bending route rather than a
   straight line to a sign.

   The eye position is a separate parameter (`los_position`) from
   `agent_position` on purpose: `agent_position` also re-measures every route's
   length from that point, and conflating them silently re-ranked routes whose
   edges carry waypoints.

7. **The crude per-segment rule still exists, under both models.**
   Reject routes where *all* segments are non-visible, i.e. every segment has
   `k_avg ≥ visibility_extinction_threshold` (0.5) — but only if some other
   route does have visibility. It was meant to be additive-model machinery and was not
   removed when the gate landed.

8. **How to turn the sign model on.**
   `_build_vis_model()` (`run_config.py:167`) builds one when *any* of these
   holds, provided the config contains sign descriptors:
   - the deck has agents below full familiarity (they need it to discover), or
   - `--vis-cache <path>` was passed, or
   - rerouting is on and `cost_model` is `"gate"` — i.e. the default, which is
     why familiarity-1.0 decks now pay for a vismap precompute they used to
     skip (`_gate_needs_sight`). `--vis-cache` makes it a one-off.
   - `--clear-air-visibility` forces it on with no fire.

   `--no-visibility` turns it off entirely; agents then learn every neighbour of
   each node they reach by contact. With `--fds-dir` the model reads the FDS
   field and reuses `--reroute-interval` as its time step and
   `--smoke-slice-height` as its slice; without one it is built from clear air
   at `--vis-cell-size` resolution.

9. **Current limitation vs the literature.**
   Sight is now **purely gating**: it decides whether a route is available and
   nothing else. In the choice papers, visibility (VIS) is the single largest
   *positive weight* in the utility (≈ +0.71 in Haghani 2018) — a visible exit
   should be *more attractive* on a spectrum. Banding was the one step toward
   that, and it was removed from the ordering in `cea33ce` because it decided
   rather than broke ties. The gap is therefore wider than it was, not
   narrower.

---

## Part 3 — Where the papers contradict each other

The four exit-choice papers (`materials/`) broadly agree on *signs and significance*
(nearer = better, smoke = avoid, visible = better) but disagree in ways that matter
for picking weights. Key tensions:

1. **Does distance matter much? Stated vs revealed disagree.**
   - *Lovreglio 2016* (stated-preference VR survey): DIST has a **weak** effect with
     huge dispersion — many respondents effectively ignored distance.
   - *Haghani 2017* (stated vs revealed head-to-head): survey data **systematically
     overweights congestion relative to distance** vs. real drill behaviour.
   → So Lovreglio's "distance barely matters" is likely a survey artefact; real
   behaviour weights distance more. If forced to choose, trust the **revealed**
   (Haghani) DIST/CONG balance over the survey one.

2. **The "crowd" term flips sign depending on where the crowd is.**
   - *Lovreglio 2014*: NPDM (crowd heading toward an exit near you) is **positive** →
     herding / follow-the-crowd.
   - *Lovreglio 2016*: NCE (crowd already *at* the exit) is **negative** →
     crowd-avoidance; NCDM negative on average but with **huge dispersion** (both
     behaviours coexist across people).
   → There is no single "congestion weight". A crowd blocking the exit repels; a
   crowd moving *with* you can attract; and the sign genuinely differs person to
   person. A one-number congestion term cannot represent this.

3. **Flow direction: Lovreglio and Haghani disagree.**
   - *Lovreglio 2016*: FL (flow *through* an exit) is **positive** — a flowing exit
     signals throughput / escapability.
   - *Haghani 2018*: flow toward a **visible** exit is **negative** (crowding
     signal), but flow toward an **invisible** exit is **positive** (informational —
     "others must know something").
   → "Flow = good" is not universal; its sign depends on whether you can already see
   the exit. Context-dependent, and the two papers do not cleanly agree.

4. **Simple routing rules are provably suboptimal.**
   - *Haghani 2018*: both pure shortest-distance AND pure follow-the-crowd routing
     produce **longer** evacuation times than a calibrated multi-attribute tradeoff.
   → Cuts against the common modelling default (and against leaning too hard on any
   single term, including distance, in our Dijkstra cost).

5. **The method itself biases the numbers (but not the predictions).**
   - *Haghani 2017*: stated-choice surveys — which the Lovreglio models rely on
     entirely — give **biased coefficient magnitudes**, though final choice
     *probabilities* end up similar to revealed data.
   → Usable, but don't trust the relative magnitudes of survey-derived weights
   literally.

6. **Even the same author contradicts himself on gender.**
   - *Lovreglio 2014*: gender significantly affects exit choice.
   - *Lovreglio 2016*: **no** significant gender effect (attributed to the richer
     variable set absorbing what gender previously proxied for).

7. **The gap that dooms `w_fed`: none of them include toxicity.**
   All four are drills or VR videos — nobody is being incapacitated by CO. They can
   ground distance / congestion / visibility / flow weights, but they say **nothing**
   about how to trade FED against those. So `w_fed` cannot be calibrated from this
   literature; toxicity weighting must come from tenability science
   (ISO 13571 / Purser), which is exactly why it fits better as the FED **rejection
   constraint** than as a smooth weighted term.

---

### One-line takeaways
- `w_smoke` and `w_fed` are uncalibrated — the core issue. `w_queue` is off by
  default: it scales with a global agent tally, so any constant is calibrated at
  one crowd size only. The Station deck opts in at 0.03 (Fahy Table 2).
- **"`w_smoke` is redundant: route on travel time instead" is now the default.**
  Under `cost_model: "gate"` the ranking number *is* travel time and smoke only
  decides availability. `w_smoke` and `w_fed` are not gone, though: they still
  weight the Dijkstra edge costs that pick which path reaches each exit, under
  both models. That is a known limitation, not a design.
- Toxicity is a threshold, not a preference → keep it as the reject, drop `w_fed`.
- Visibility is richly modelled but enters route choice only as a gate — the
  band ordering was removed — and never as an attractive term.
- For distance-vs-congestion, prefer Haghani's **revealed-choice** weights over the
  Lovreglio **survey** weights.
