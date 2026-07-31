# Routing, Exit Choice & Exit Signs — Notes

Working notes on how the current model chooses routes and exits, how the exit-sign
visibility system works, and where the exit-choice research papers disagree with
each other. All code references point at `pyfds_evac/core/route_graph.py`,
`pyfds_evac/core/visibility.py`, and `pyfds_evac/core/smoke_speed.py`.

Symbols used below:
- `K` — smoke extinction coefficient [1/m], sampled from the FDS field.
- `FED` — Fractional Effective Dose (toxic dose; incapacitation at ~1.0).
- Config defaults come from `RouteCostConfig` (`route_graph.py:439`).

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

4. **A full route's cost is the composite formula.**
   `evaluate_route()` (`route_graph.py:589`) sums edges into one route:
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
   **The three hand-picked weights live here:** `w_smoke = 1.0`, `w_fed = 10.0`,
   `w_queue = 1.0`. These are NOT calibrated (the main open problem).

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
   Sort key (`route_graph.py:793`):
   ```
   ( rejected? , composite_cost , path_length )
   ```
   → survivable routes first, cheapest first, ties broken by fewer hops.

9. **There is always a fallback.**
   If *every* route is rejected (`route_graph.py:799`), the least-bad one is
   un-rejected so the agent always has somewhere to go.

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

1. **Signs are opt-in, defined per node in `config.json`.**
   Any exit / checkpoint / waypoint may carry a `sign` block (e.g.
   `on/config.json:60`):
   ```json
   "sign": { "x": 0.5, "y": 11.5, "alpha": 90, "c": 3 }
   ```
   - `x, y` — the sign's world position.
   - `alpha` — compass bearing the sign faces (deg from north, clockwise).
   - `c` — contrast/visibility constant (default 3).
   `extract_sign_descriptors()` (`visibility.py:14`) collects every node that has
   one. **A node with no `sign` is always treated as visible** (opt-in system).

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

4. **The routing query is a single boolean.**
   `node_is_visible(time, x, y, node_id)` (`visibility.py:251`) → True/False.
   Nodes without a sign always return True.

5. **Signs gate routes (rejection), they don't (yet) change cost.**
   In `rank_routes` (`route_graph.py:750`): a route is **rejected if the agent
   cannot currently see the sign for the next node** on that path. So a sign that is
   smoke-obscured, faced the wrong way, or behind a wall makes that route unusable.

6. **Fallback when no sign model is loaded.**
   If `vis_model is None`, a cruder rule applies (`route_graph.py:774`): reject
   routes where *all* segments are non-visible (`k_avg ≥ 0.5`), but only if some
   other route does have visibility.

7. **How to turn the full sign model on.**
   `_build_vis_model()` (`run_config.py:116`): active only if you pass
   **`--vis-cache <path>`** AND the config actually contains sign descriptors.
   It reuses `--fds-dir`, `--reroute-interval` (as time step), and
   `--smoke-slice-height`.

8. **Current limitation vs the literature.**
   Signs here are **binary + gating** (visible → allowed, else rejected). In the
   choice papers, visibility (VIS) is the single largest *positive weight* in the
   utility (≈ +0.71 in Haghani 2018) — a visible exit should be *more attractive*
   on a spectrum, not merely "not forbidden." The rich, physically-grounded
   visibility field is already computed; it is just wired as a filter, not a
   weighted term.

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
- The three routing weights (`w_smoke`, `w_fed`, `w_queue`) are uncalibrated — the
  core issue.
- `w_smoke` is redundant: smoke's real effect (slowdown) is already the calibrated
  Lund speed law → route on travel-time instead.
- Toxicity is a threshold, not a preference → keep it as the reject, drop `w_fed`.
- Visibility is already richly modelled but only used as a gate → could become a
  weighted term (biggest positive factor in the literature).
- For distance-vs-congestion, prefer Haghani's **revealed-choice** weights over the
  Lovreglio **survey** weights.
