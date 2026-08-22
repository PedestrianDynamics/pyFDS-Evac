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

7. **Visibility is not a reject at all under the gate.** Sign legibility decides
   what enters the agent's cognitive map, and the map decides what Dijkstra can
   see — an unknown exit is absent from the graph, not present-and-vetoed. The
   per-segment `all segments non-visible` reject survives under `"additive"`
   only. Details in Part 2, points 5 and 7.

8. **Routes are sorted; the agent takes the best.**
   Sort key (`route_graph.py:1322`), additive:
   ```
   ( rejected? , composite_cost , hops )
   ```
   → survivable routes first, cheapest first, ties broken by fewer hops.

8a. **Under the default gate model, one quantity gates and orders.**
   A route is refused when its optical depth `tau = K_ave × L` exceeds `tau_max`
   (6), or `tau_max × tau_return_margin` (4.8) for an exit the agent is not
   already walking to, and the survivors sort as
   ```
   ( rejected? , tau , travel_time + w_queue·queue_time , hops )
   ```
   with the current exit's `tau` scaled by `current_exit_discount` (0.9). `tau`
   already contains the distance, so a cleaner route wins only by carrying
   enough less smoke to pay for its extra metres; in clear air every `tau` is
   zero and travel time decides alone. Dijkstra weights each edge by its own
   `tau` too, so path choice and exit choice are one objective. The visibility
   band and the sighting distance were removed at `0d9bf79`. Refusals are
   recomputed every tick and never remembered, so the criterion relaxes as an
   agent closes on an exit.

9. **There is always a fallback.**
   If *every* route is rejected (`route_graph.py:1350`), the least-bad one is
   un-rejected so the agent always has somewhere to go. Under the gate,
   "least bad" is the lowest undiscounted `tau_route`, then the lowest
   `rank_cost`, held by `fallback_switch_margin` (0.2) against the rival's
   worst-case K.

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
     sighting distance was tested against when the sight line still gated. It is
     computed from the descriptor, not asked of the backend, so a run loaded
     from an `.npz` cache still has it. The gate no longer reads it.

5. **Legibility no longer rejects routes; it decides what the agent knows.**
   `rank_routes` does **not** consult sign legibility (see the comment at
   `route_graph.py:1399`). Readability feeds
   `cognitive_map.expand_from_visibility`, and the cognitive map decides what
   Dijkstra can see — so an unknown exit is *absent from the graph* rather than
   present-and-vetoed. Checking it again in ranking double-gated the same
   criterion, blocked agents who already knew the building, and forbade an agent
   from using an exit it had legitimately learned once the sign left view.

6. **The sight line no longer enters the route decision, and neither does
   sight.** Under `cost_model: "gate"`, `evaluate_route` refuses a route when
   the *mean* K over its own polyline times the remaining length exceeds
   `tau_max`; the reason reads `tau 8.41 > 6.00 (K_ave 0.145 x 58.0 m)`. The
   `visibility_to_node` reading is still taken and reported, but since
   `b16e900` it does not gate: it resolves only where a sign does, so choosing
   the criterion per exit let sign geometry decide which exits were tested at
   all — the `l_corridor` far exit lies around two corners, was never tested,
   and the deck's diversion disappeared. Since `0d9bf79` the polyline test is
   named for what it is, an exposure budget rather than a sighting distance:
   integrating K along a route that turns two corners does not measure how far
   anyone can see. Jin's `S = c/K` keeps its proper meaning one section up, in
   sign legibility, where the question really is what an occupant can read.

   The eye position is a separate parameter (`los_position`) from
   `agent_position` on purpose: `agent_position` also re-measures every route's
   length from that point, and conflating them silently re-ranked routes whose
   edges carry waypoints.

7. **The crude per-segment rule is now additive-only.**
   Reject routes where *all* segments are non-visible, i.e. every segment has
   `k_avg ≥ visibility_extinction_threshold` (0.5) — but only if some other
   route does have visibility. It was always meant to be additive-model
   machinery; under the gate it was a second, hysteresis-free smoke criterion on
   top of the sight test, and `22c0888` retired it there.

8. **How to turn the sign model on.**
   `_build_vis_model()` (`run_config.py:167`) builds one when *any* of these
   holds, provided the config contains sign descriptors:
   - the deck has agents below full familiarity (they need it to discover), or
   - `--vis-cache <path>` was passed, or
   - `--clear-air-visibility` forces it on with no fire.

   The gate no longer triggers it. `b16e900` moved the sight criterion onto the
   route polyline and `89d13d4` removed the `_gate_needs_sight` precompute, so a
   familiarity-1.0 gate deck builds no visibility model and runs without a
   vismap.

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
- **"`w_smoke` is redundant" is now true under the gate.** Since `0d9bf79` the
  gate weights each Dijkstra edge by its own optical depth and ranks routes by
  theirs, so neither `w_smoke` nor `w_fed` reaches route choice; the composite is
  computed and reported only. Under `"additive"` both still apply.
- Toxicity is a threshold, not a preference → keep it as the reject, drop `w_fed`.
- Visibility is richly modelled but enters route choice only through the
  cognitive map. What gates a route is exposure, not sight.
- For distance-vs-congestion, prefer Haghani's **revealed-choice** weights over the
  Lovreglio **survey** weights.
