# 008 — Visibility-aware routing with cognitive maps

## Problem

pyFDS-Evac's current routing model has two unrealistic assumptions:

1. **Global knowledge**: every agent knows the complete stage graph — all
   corridors, junctions, and exits — from the start of the simulation.
   Route selection runs Dijkstra over the full graph.  A hotel guest or
   casual visitor would not know the building layout at this level.

2. **Geometric route rejection only**: the visibility heuristic
   (`K_vis` threshold on path-averaged extinction) is a scalar proxy.
   It does not account for whether an agent can actually *see* the next
   sign or junction, nor for architectural occlusion or viewing angle.

The combined effect is that agents behave like omniscient computers rather
than humans navigating under smoke.

## References

- **Haensel 2014** — knowledge-based routing framework; cognitive maps,
  discovery mode, sensor-driven edge weights, knowledge hierarchies.
  (`materials/haensel2014_summary.md`)
- **Börger et al. (vismap / FDSVismap)** — waypoint-based visibility:
  path-integrated Beer-Lambert extinction along the line of sight,
  Lambertian cosine angle correction, Bresenham ray-cast occlusion,
  visibility maps and ASET maps.
  (`materials/waypoint_based_visibility_summary.md`)

## Goals

1. **Replace the K_vis scalar heuristic** with a physically grounded
   visibility check: an agent can only target a next node if they can
   see the corresponding sign/landmark (via vismap).
2. **Introduce two knowledge tiers** for agents:
   - `familiarity=full` — agent knows the complete stage graph from the
     start (current behaviour, e.g. trained staff).
   - `familiarity=discovery` — agent starts with an empty cognitive map
     and expands it by line-of-sight as they move through the building.
3. **Extend the stage graph** so every node (exit, waypoint, junction)
   carries a sign descriptor used by vismap.
4. Keep the change **opt-in and backward-compatible**: when no vismap
   data is configured, behaviour is identical to the current model.

## Key concepts

### Waypoints are decision nodes, not only exits

JuPedSim waypoints (intermediate stages in a journey) and exits are
both graph nodes.  A T-junction should be a waypoint node in two senses:

- A **JuPedSim stage** (polygon the agent steers toward).
- A **vismap landmark** — a sign at `(x, y, alpha)` facing the
  corridor it points toward.

`alpha` is a compass bearing (degrees from north, clockwise): 90 = sign
visible from the east, 270 = from the west, 180 = from the south.

Example: a junction sign with `alpha=90` faces east; agents approaching
from the east see it face-on; agents to the west see it from behind
(invisible).

### Sign descriptor in config.json

Each stage node gains an optional `"sign"` field:

```json
"waypoints": {
  "junction_T": {
    "type": "polygon",
    "coordinates": [[14,9],[16,9],[16,14],[14,14],[14,9]],
    "sign": {"x": 15.0, "y": 10.0, "alpha": 90}
  }
},
"exits": {
  "exit_A_left": {
    "type": "polygon",
    "coordinates": [[0,10],[1,10],[1,13],[0,13],[0,10]],
    "sign": {"x": 0.5, "y": 11.5, "alpha": 90}
  },
  "exit_B_right": {
    "type": "polygon",
    "coordinates": [[29,10],[30,10],[30,13],[29,13],[29,10]],
    "sign": {"x": 29.5, "y": 11.5, "alpha": 270}
  }
}
```

If `"sign"` is absent for a node, that node is assumed always visible
(fallback to current behaviour).

### Vismap pre-computation and caching

```python
waypoints_for_vismap = [
    (node_id, sign["x"], sign["y"], sign["alpha"])
    for node_id, sign in all_sign_descriptors.items()
]
vis = load_or_compute_vis(
    fds_dir, waypoints_for_vismap, times, pickle_path="vis_cache.pkl"
)
```

`load_or_compute_vis` runs Bresenham ray-casting over the full spatial
grid for each timestep — expensive once, then cached.  The pickle is
invalidated when `fds_dir` or the waypoint list changes.

### VisibilityModel API wrapper

```python
class VisibilityModel:
    def __init__(self, fds_dir, sign_descriptors, times, cache_path):
        waypoints = [(nid, s["x"], s["y"], s["alpha"])
                     for nid, s in sign_descriptors.items()]
        self.vis = load_or_compute_vis(fds_dir, waypoints, times, cache_path)
        self.wp_ids = {nid: i for i, (nid, *_) in enumerate(waypoints)}

    def node_is_visible(self, time: float, x: float, y: float,
                        node_id: str) -> bool:
        wp_id = self.wp_ids.get(node_id)
        if wp_id is None:
            return True  # no sign descriptor → always visible
        return self.vis.wp_is_visible(time=time, x=x, y=y, waypoint_id=wp_id)

    def local_visibility_m(self, time: float, x: float, y: float,
                           c: float) -> float:
        return self.vis.get_local_visibility(time=time, x=x, y=y, c=c)
```

### Two knowledge tiers

#### `familiarity=full` (staff, trained occupants)

Agent starts with the complete stage graph.  Dijkstra runs as today.
The only change: at Phase 3 route rejection, replace the `K_vis`
scalar check with `vis_model.node_is_visible(t, ax, ay, next_node_id)`
for the *first* node on each candidate route.

If the next node on the route is not visible, the route is rejected
(agent cannot see the sign they would need to follow).

#### `familiarity=discovery` (visitors, unfamiliar occupants)

Agent starts with an **empty cognitive map** — knows only their spawn
node.  At each reevaluation:

1. From current node $u$, query `node_is_visible` for all nodes
   adjacent to $u$ in the *full* graph.
2. Add visible adjacent nodes to the agent's cognitive map.
3. Run Dijkstra only over the agent's cognitive map.
4. If no exit is reachable in the cognitive map, navigate toward the
   best visible adjacent node (closest with lowest smoke) — discovery
   mode (Haensel §2.B).

On **arrival** at a node, all nodes adjacent to it in the full graph
are added to the cognitive map unconditionally (the agent is now
physically there and can look around).

```
cognitive_map[agent_id]:
  known_nodes: set of node_ids
  known_edges: set of (u, v) pairs
```

### Route rejection update (Phase 3)

```python
# Current K_vis heuristic (kept as fallback when vis_model is None)
rejected = all(k_bar >= K_vis for segment in route)

# With vismap (replaces the above when vis_model is not None)
next_node = route.path[1]  # first hop from current node
rejected = not vis_model.node_is_visible(sim_time, agent_x, agent_y,
                                          next_node)
rejection_reason = "next_node_not_visible"
```

### Per-agent familiarity in config.json

```json
"distributions": {
  "staff_area": {
    "parameters": {
      "number": 20,
      "familiarity": "full"
    }
  },
  "visitor_area": {
    "parameters": {
      "number": 180,
      "familiarity": "discovery"
    }
  }
}
```

Default when `"familiarity"` is absent: `"full"` (current behaviour).

## What this does NOT include (future work)

- **Information sharing**: a discovery agent who finds a smoked corridor
  does not warn other agents.  Each agent updates only its own
  cognitive map.
- **Angle-weighted cost**: `get_local_visibility(c=c)` could penalise
  routes where the sign is near the edge of the visual cone, not just
  absent/present.  Left as a continuous cost term for a later spec.
- **Full waypoint-chasing navigation**: agents following a sequence of
  visible signs hop-by-hop, updating their JuPedSim target at each
  visible waypoint.  This requires changes to the JuPedSim steering
  API and is a larger architectural change.
- **ASET/RSET postprocessing**: vismap's ASET maps + pedpy's RSET maps
  + Schröder's difference maps and consequence scalar $C$ as a
  postprocessing pipeline on pyFDS-Evac output.  Tracked separately.

## Visualisations and verification plots

Two vismap plot methods are directly useful for verifying progress at
each phase.

### `vis.create_time_agg_wp_agg_vismap_plot(plot_obstructions=True)`

Aggregates visibility across all waypoints and all timesteps into a
single spatial map.  Each floor cell is coloured by how often (or
whether) it can see any sign.

**Use before Phase 1:**
- Run immediately after placing sign descriptors in `config.json`.
- Confirm no large dead zones exist where agents could never see the
  next node.  If a corridor appears persistently blind, either the sign
  needs repositioning or an intermediate junction waypoint is missing.
- With `plot_obstructions=True`: walls are overlaid explicitly,
  distinguishing architectural occlusion from smoke-driven invisibility.

### `vis.create_aset_map_plot(plot_obstructions=True)`

Shows when each floor cell first loses visibility to any exit sign —
pure fire + geometry output, no evacuation model needed.

**Use to validate the fire scenario:**
- Confirms that the region near exit_B loses sign visibility first and
  earliest, consistent with `fds_inspection.png`.
- Natural input for the ASET/RSET postprocessing pipeline
  (Schröder difference maps + consequence scalar $C$).

**Use to verify Phase 1 rejection logic:**
- After Phase 1 implementation, overlay route rejection events from
  `route_costs.csv` (column `rejected=True`, `rejection_reason=
  "next_node_not_visible"`) onto the ASET map.
- Rejection events should cluster in the same floor cells and start at
  the same times where the ASET map shows visibility loss.
- Mismatch → bug in the rejection logic or the sign placement.

**Use to compare Phase 2 knowledge tiers:**
- `familiarity=full` agents: rejection events should track ASET closely
  (they know all routes but reject the invisible ones).
- `familiarity=discovery` agents: rejection events may appear earlier
  and in more cells because their cognitive map is incomplete —
  they cannot route around a smoked junction they have not yet seen.

## Implementation phases

### Phase 0 — Plots only, no code change

Before touching any routing logic:

1. Place sign descriptors for all nodes in `assets/demo/config.json`.
2. Run `load_or_compute_vis(fds_dir, waypoints, times, cache_path)`.
3. Produce `create_time_agg_wp_agg_vismap_plot` → check sign coverage.
4. Produce `create_aset_map_plot` → validate fire scenario geometry.
5. Commit plots to `assets/demo/figs/` as baseline.

No code changes; pure configuration and visualisation.

### Phase 1 — Visibility-gated route rejection (drop-in)

- Add `"sign"` field to config schema (optional, backward-compatible).
- Implement `VisibilityModel` wrapper around vismap API.
- Wire into `rank_routes` Phase 3: replace `K_vis` scalar with
  `node_is_visible` when `vis_model` is not None.
- Add `--vis-cache` CLI flag to `run.py`.
- All agents still have `familiarity=full`.
- **Verification**: overlay rejection events on ASET map; confirm
  spatial and temporal alignment.
- Tests: mock `VisibilityModel`, verify rejection fires correctly.

### Phase 2 — Cognitive map and discovery mode

- Add `AgentCognitiveMap` dataclass (known_nodes, known_edges).
- Add `familiarity` field to distribution parameters.
- At reevaluation: filter stage graph to agent's cognitive map before
  Dijkstra.
- On arrival at node: expand cognitive map with adjacent nodes.
- Discovery mode: if no exit reachable, navigate to best visible
  adjacent node.
- **Verification plots**:
  - Animate cognitive map growth per agent over time (known nodes
    highlighted on floor plan).
  - Egress time distributions: `full` vs `discovery` agents.
  - Exit choice split per familiarity tier over time.
- Tests: two-corridor scenario, verify discovery agents take longer
  but find correct exit; staff agents unaffected.

## Open questions

1. Should discovery agents share their cognitive map with agents in the
   same distribution group (partial social knowledge)?
2. How does the `familiarity` parameter interact with pre-movement
   time?  (Unfamiliar agents might also have longer pre-movement.)
3. Should the visibility check use the agent's *current position* or
   their *current stage node centroid*?  Current position is more
   accurate but requires passing (x, y) at reevaluation time.
