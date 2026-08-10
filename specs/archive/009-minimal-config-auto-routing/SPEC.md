# 009 — Minimal-config auto-routing (no transitions, no signs)

## Problem

When a scenario defines only **distributions + exits** (no `transitions`, no
`checkpoints`, no signs), the simulation falls back to a greedy
nearest-exit assignment with no rerouting capability:

1. `_initialize_scenario_from_json` detects `transitions=[]` → sets
   `needs_fallback=True`.
2. `StageGraph.from_scenario()` is still called with `transitions=[]` → graph
   has nodes but **zero edges**.
3. Dijkstra finds no paths → `rank_routes()` returns nothing → rerouting is
   permanently disabled.
4. All agents are stuck on their initial nearest-exit assignment regardless of
   smoke conditions.

## Goal

A config with only distributions + exits must support full smoke/FED-based
rerouting without requiring the user to manually define transitions.

## Design

### Auto-edge generation in `StageGraph.from_scenario()`

When `transitions` is empty *after* all nodes have been added, automatically
generate direct `distribution → exit` edges for every (distribution, exit)
pair:

```python
if not transitions:
    dist_ids = [nid for nid, n in graph.nodes.items()
                if n.stage_type == "distribution"]
    exit_ids  = [nid for nid, n in graph.nodes.items()
                if n.stage_type == "exit"]
    for src_id in dist_ids:
        for tgt_id in exit_ids:
            # same polyline / Euclidean logic as explicit transitions
            ...
```

This is the only change required.  The fallback path in
`simulation_init.py` already populates `direct_steering_info` with both
exits and sets up `direct_steering_stage` per exit, so agents can be
retargeted at rerouting ticks once the graph has valid edges.

### Familiar agents

Agents with `familiarity=full` (the default) already receive full graph
knowledge at spawn time — they know both exits.  No additional change is
needed.

For `familiarity=discovery` agents, the cognitive-map expansion runs on the
existing `stage_graph` nodes and edges, so auto-generated edges are
discovered normally when agents reach the distribution centroid.

## Affected files

| File | Change |
|------|--------|
| `pyfds_evac/core/route_graph.py` | Add auto-edge block (~15 lines) after the transitions loop |

## Verification

```bash
uv run python run.py \
  --scenario assets/demo2 \
  --fds-dir  assets/demo2 \
  --enable-rerouting \
  --reroute-interval 10 \
  --output-route-cost-history route_costs.csv \
  --output-route-history      routes.csv
```

Expected:
- Log: `edges=2` (not `edges=0`) for the stage graph line
- `routes.csv` contains agent route switches between `exit_A_left` and
  `exit_B_right` driven by smoke costs
- `route_costs.csv` shows costs evaluated for both exits at each tick
