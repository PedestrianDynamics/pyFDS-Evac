# 006 — Dynamic smoke-weighted routing

## Problem

Dijkstra currently runs on static Euclidean edge weights, then
smoke-scores the resulting paths separately. This means:

- If two routes reach the same exit, only the geometrically shorter
  one is ever considered — even if smoke makes the longer route
  cheaper.
- Extinction is sampled along centroid-to-centroid rays, not along
  the corridor the agent actually walks.
- `fed_rate_sampler` is hardcoded to `None` in the scenario loop,
  so FED does not influence route ranking.

## Goal

Make the routing system behave as **dynamic shortest-path on a
fixed graph with time-varying edge weights**: static topology,
dynamic edge costs recomputed from smoke and FED at each
reevaluation tick, Dijkstra finds the cheapest path per exit
using those costs.

## Design

### 1. Edge polyline geometry

**`StageEdge`** gains a `waypoints` field:

```python
@dataclass(frozen=True)
class StageEdge:
    source: str
    target: str
    weight: float              # polyline length (metres)
    waypoints: list[tuple[float, float]]  # corridor-following polyline
```

Polylines are computed **once at graph construction** using
JuPedSim's `RoutingEngine`:

```python
routing = jps.RoutingEngine(walkable_polygon)
waypoints = routing.compute_waypoints(centroid_A, centroid_B)
```

`StageGraph.from_scenario()` receives the walkable polygon as a
new parameter. If no polygon is provided (e.g. in unit tests),
edges fall back to the straight centroid-to-centroid ray.

`weight` becomes the polyline length (sum of segment lengths)
instead of Euclidean distance.

### 2. Smoke/FED sampling along polylines

`integrated_extinction_along_los()` and the FED midpoint sampling
in `evaluate_segment()` walk the polyline stored on the edge
instead of the straight centroid-to-centroid ray.

The `_sample_segment_extinction()` helper receives the edge's
waypoints and samples K at uniform intervals along the polyline.
Same Beer-Lambert arithmetic mean, different geometry.

### 3. Dynamic Dijkstra

At each reevaluation tick, `rank_routes` computes dynamic edge
costs **before** running Dijkstra:

1. For each edge in the graph, call `evaluate_segment()` with
   the current smoke/FED fields to get a `SegmentCost`.
2. Build a weight map: `dict[(src, tgt)] -> composite_edge_cost`.
   Edge cost = `length_m * (1 + w_smoke * k_avg) + w_fed * fed_growth`
   (the per-edge decomposition of the route-level composite cost).
3. Pass the weight map to `_dijkstra()` so pathfinding uses
   smoke-adjusted costs.
4. `shortest_paths_to_exits()` returns one cheapest path per
   exit — now cheapest under current conditions, not geometry.

`_dijkstra()` signature changes to accept an optional dynamic
weight override:

```python
def _dijkstra(
    self,
    source: str,
    dynamic_weights: dict[tuple[str, str], float] | None = None,
) -> tuple[dict[str, float], dict[str, str | None]]:
```

When `dynamic_weights` is provided, edge cost is looked up there
instead of from `self._edges`. When `None`, falls back to static
Euclidean weights (preserving backward compatibility for
`shortest_exit()` and tests).

### 4. FED activation

`scenario.py` wraps the FED model in a `_FedRateAdapter` (see
FED rate sampler interface section below) and passes it into
`evaluate_and_reroute`:

```python
# Before (line ~1564):
fed_rate_sampler=None,

# After:
fed_rate_adapter = _FedRateAdapter(fed_model) if fed_model else None
...
fed_rate_sampler=fed_rate_adapter,
```

`evaluate_segment()` already dispatches on `fed_rate_sampler is
not None`, but its FED midpoint sampling currently uses the
centroid midpoint `((x_from + x_to) / 2, ...)`. With polyline
edges, this must change to the midpoint along the polyline (by
arc length). This is a real interface change to
`evaluate_segment()` — it needs access to the edge waypoints to
compute the polyline midpoint, not just the source/target
centroids.

### 5. Segment caching update

The segment cache is currently keyed by `(source, target)` and
reused within a single timestep. This remains correct: edge
geometry is static, and smoke fields don't change within a tick.
The cache is already invalidated between ticks.

However, with dynamic Dijkstra the cache now serves double duty:
segments evaluated for the weight map are reused when building the
final `RouteCost` objects. This avoids redundant extinction
sampling.

## What stays the same

- **Graph nodes**: distributions, checkpoints, exits — same types,
  same config format.
- **Source resolution**: `current_origin` fallback to
  `current_target_stage`.
- **Staggered reevaluation**: `compute_eval_offset()` and
  `should_reevaluate()` unchanged.
- **Rejection logic**: FED threshold + visibility filter.
- **Fallback un-rejection**: cheapest rejected route if all fail.
- **`RouteSwitch` diagnostics**: same fields and reasons.
- **Composite cost formula**: `path_length * (1 + w_smoke * K_ave)
  + w_fed * FED_max` — applied at route level after Dijkstra.

## Files to modify

| File | Changes |
|------|---------|
| `pyfds_evac/core/route_graph.py` | `StageEdge` gains `waypoints`; `StageGraph.from_scenario()` accepts walkable polygon and computes polylines; `_dijkstra()` accepts dynamic weights; `_sample_segment_extinction()` walks polyline; `rank_routes()` pre-computes edge costs and passes to Dijkstra |
| `pyfds_evac/core/scenario.py` | Create `RoutingEngine` from `scenario.walkable_polygon`; pass it to `StageGraph.from_scenario()`; pass `fed_rate_sampler` to `evaluate_and_reroute` |
| `tests/test_route_graph.py` | Update fixtures for new `StageEdge` shape; add tests for polyline sampling and dynamic Dijkstra |
| `docs/routing.md` | Update to reflect dynamic weights, polyline geometry, and FED activation |

## Edge cost function

For Dijkstra weights, each edge cost should reflect what the
composite formula penalises at route level. Per-edge:

```
edge_cost = length_m * (1 + w_smoke * k_avg) + w_fed * fed_growth
```

Note: the route-level formula uses `FED_max = current_fed +
sum(fed_growth)`, so `sum(edge_costs)` equals the route composite
cost **only when `current_fed` is zero**. In general,
`sum(edge_costs)` differs from the route composite cost by
`w_fed * current_fed`. However, `current_fed` is constant across
all candidate routes for one agent at one tick, so it does not
affect the ranking — Dijkstra's optimality guarantee still holds
because `current_fed` shifts all routes equally and all per-edge
terms are non-negative.

## FED rate sampler interface

The `FedRateSampler` protocol (route_graph.py:270) expects:

```python
def sample_fed_rate(self, time_s: float, x: float, y: float) -> float
```

`DefaultFedModel` (fed.py:305) has `sample_rate(time_s, x, y)`
which returns `(inputs, rate_per_min)`. A thin adapter is needed:

```python
class _FedRateAdapter:
    def __init__(self, model: DefaultFedModel):
        self._model = model

    def sample_fed_rate(self, time_s: float, x: float, y: float) -> float:
        _, rate = self._model.sample_rate(time_s, x, y)
        return rate
```

This adapter lives in `scenario.py` next to where `fed_model` is
constructed.

## Backward compatibility

- `StageEdge(source, target, weight)` construction still works if
  `waypoints` defaults to an empty list (straight-ray fallback).
- `_dijkstra()` without `dynamic_weights` uses static Euclidean
  weights as before.
- Tests that construct graphs without a walkable polygon continue
  to work with centroid-to-centroid rays.

## Verification

1. **Unit tests** (`test_route_graph.py`):
   - Diamond graph with asymmetric smoke: Dijkstra with dynamic
     weights picks the longer-but-cleaner path.
   - Polyline sampling: extinction sampled along waypoints, not
     straight ray.
   - FED growth: non-zero when `fed_rate_sampler` provided.
   - Backward compat: existing tests pass without modification
     (static Euclidean fallback).

2. **Integration** (demo scenario):
   - Run the demo with `reroute_config` enabled.
   - Confirm `route_cost_history.csv` shows dynamic costs change
     over time.
   - Confirm agents reroute when smoke shifts edge costs.

3. **Regression**:
   - Full test suite: `uv run python -m pytest tests/ -q`
