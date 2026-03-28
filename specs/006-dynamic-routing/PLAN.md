# Dynamic Smoke-Weighted Routing — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Dijkstra run on dynamic smoke/FED-adjusted edge weights so pathfinding and scoring use the same cost function, with polyline edge geometry from JPS RoutingEngine.

**Architecture:** Three layered changes — (1) add polyline geometry to `StageEdge` and sample smoke/FED along it, (2) run Dijkstra with dynamic weights computed from current smoke/FED, (3) wire `fed_rate_sampler` into the scenario loop. Each layer builds on the previous one; existing tests remain passing at every step via backward-compatible defaults.

**Tech Stack:** Python 3.11, pytest, JuPedSim (`jps.RoutingEngine`), Shapely

**Spec:** `specs/006-dynamic-routing/SPEC.md`

---

## File Map

| File | Role |
|------|------|
| `pyfds_evac/core/route_graph.py` | Core changes: `StageEdge.waypoints`, polyline sampling, dynamic Dijkstra |
| `pyfds_evac/core/scenario.py` | Integration: `RoutingEngine` creation, pass to graph builder, FED adapter |
| `tests/test_route_graph.py` | All new tests |
| `docs/routing.md` | Doc updates (last task) |

---

### Task 1: Add `waypoints` field to `StageEdge`

**Files:**
- Modify: `pyfds_evac/core/route_graph.py:27-33`
- Test: `tests/test_route_graph.py`

- [ ] **Step 1: Write failing test for waypoints field**

Add at the end of `tests/test_route_graph.py`:

```python
class TestEdgeWaypoints:
    def test_edge_has_waypoints_field(self):
        edge = StageEdge(source="A", target="B", weight=10.0, waypoints=[(0, 0), (5, 5), (10, 0)])
        assert edge.waypoints == [(0, 0), (5, 5), (10, 0)]

    def test_edge_waypoints_defaults_to_empty(self):
        edge = StageEdge(source="A", target="B", weight=10.0)
        assert edge.waypoints == []
```

Update the import at the top of the test file to include `StageEdge`:
```python
from pyfds_evac.core.route_graph import (
    StageEdge,
    StageGraph,
    ...
)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/test_route_graph.py::TestEdgeWaypoints -v`
Expected: FAIL — `StageEdge.__init__() got an unexpected keyword argument 'waypoints'`

- [ ] **Step 3: Add waypoints field to StageEdge**

In `pyfds_evac/core/route_graph.py`, change:

```python
@dataclass
class StageEdge:
    """A directed edge in the stage graph."""

    source: str
    target: str
    weight: float  # Euclidean distance between centroids
```

to:

```python
@dataclass
class StageEdge:
    """A directed edge in the stage graph."""

    source: str
    target: str
    weight: float  # edge length in metres (polyline or Euclidean)
    waypoints: list[tuple[float, float]] = field(default_factory=list)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest tests/test_route_graph.py::TestEdgeWaypoints -v`
Expected: PASS

- [ ] **Step 5: Run full test suite to verify no regressions**

Run: `uv run python -m pytest tests/test_route_graph.py -v`
Expected: All 53 existing tests PASS (existing code constructs `StageEdge(source, target, weight)` which still works with default `waypoints=[]`)

- [ ] **Step 6: Commit**

```bash
git add pyfds_evac/core/route_graph.py tests/test_route_graph.py
git commit -m "feat(routing): add waypoints field to StageEdge with empty default"
```

---

### Task 2: Compute polyline waypoints in `from_scenario()`

**Files:**
- Modify: `pyfds_evac/core/route_graph.py:48-120`
- Test: `tests/test_route_graph.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_route_graph.py`:

```python
class TestPolylineEdges:
    def test_from_scenario_with_walkable_polygon_sets_waypoints(self):
        """When a walkable polygon is provided, edges get polyline waypoints."""
        direct_steering_info = {
            "C0": {"polygon": _box(10, 0), "stage_type": "checkpoint"},
            "E0": {"polygon": _box(20, 0), "stage_type": "exit"},
        }
        distributions = {
            "D0": {"coordinates": list(_box(0, 0).exterior.coords)},
        }
        transitions = [
            {"from": "D0", "to": "C0"},
            {"from": "C0", "to": "E0"},
        ]
        # A simple rectangular walkable area covering all stages.
        walkable = Polygon([(-5, -5), (25, -5), (25, 5), (-5, 5)])
        graph = StageGraph.from_scenario(
            direct_steering_info, transitions, distributions,
            walkable_polygon=walkable,
        )
        # Each edge should have non-empty waypoints.
        for edges in graph.edges.values():
            for edge in edges:
                assert len(edge.waypoints) >= 2, (
                    f"Edge {edge.source}->{edge.target} has no waypoints"
                )

    def test_from_scenario_without_polygon_uses_centroid_ray(self):
        """Without walkable polygon, edges get 2-point centroid-to-centroid waypoints."""
        direct_steering_info = {
            "C0": {"polygon": _box(10, 0), "stage_type": "checkpoint"},
            "E0": {"polygon": _box(20, 0), "stage_type": "exit"},
        }
        distributions = {
            "D0": {"coordinates": list(_box(0, 0).exterior.coords)},
        }
        transitions = [
            {"from": "D0", "to": "C0"},
            {"from": "C0", "to": "E0"},
        ]
        graph = StageGraph.from_scenario(
            direct_steering_info, transitions, distributions,
        )
        for edges in graph.edges.values():
            for edge in edges:
                assert len(edge.waypoints) == 2
                src_node = graph.nodes[edge.source]
                tgt_node = graph.nodes[edge.target]
                assert edge.waypoints[0] == pytest.approx(
                    (src_node.centroid_x, src_node.centroid_y)
                )
                assert edge.waypoints[1] == pytest.approx(
                    (tgt_node.centroid_x, tgt_node.centroid_y)
                )

    def test_edge_weight_is_polyline_length(self):
        """Edge weight equals the polyline length, not Euclidean distance."""
        direct_steering_info = {
            "E0": {"polygon": _box(20, 0), "stage_type": "exit"},
        }
        distributions = {
            "D0": {"coordinates": list(_box(0, 0).exterior.coords)},
        }
        transitions = [{"from": "D0", "to": "E0"}]
        # Without walkable polygon, weight = Euclidean = polyline length
        # (2-point straight ray).
        graph = StageGraph.from_scenario(
            direct_steering_info, transitions, distributions,
        )
        edge = graph.edges["D0"][0]
        expected = 20.0  # Euclidean (0,0)->(20,0)
        assert edge.weight == pytest.approx(expected, abs=0.01)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/test_route_graph.py::TestPolylineEdges -v`
Expected: FAIL — `from_scenario() got an unexpected keyword argument 'walkable_polygon'` and waypoints assertions fail.

- [ ] **Step 3: Implement polyline computation in `from_scenario()`**

In `pyfds_evac/core/route_graph.py`, change `from_scenario`:

```python
@classmethod
def from_scenario(
    cls,
    direct_steering_info: dict,
    transitions: list[dict],
    distributions: dict | None = None,
    walkable_polygon=None,
) -> StageGraph:
    """Build the stage graph from scenario data.

    Parameters
    ----------
    direct_steering_info:
        Maps stage_id -> dict with at least "polygon" (Shapely Polygon)
        and "stage_type" (str).
    transitions:
        List of dicts with "from" and "to" keys defining directed edges.
    distributions:
        Optional dict of distribution_id -> dict with "coordinates".
        Distributions are spawn areas and are added as nodes with type
        "distribution" so that shortest-path queries can start from them.
    walkable_polygon:
        Optional Shapely Polygon of the walkable area.  When provided,
        edge waypoints are computed via JuPedSim RoutingEngine so that
        smoke/FED is sampled along the actual corridor geometry.  When
        None, edges use a straight centroid-to-centroid ray.
    """
    graph = cls()

    # Add distribution nodes (not in direct_steering_info).
    if distributions:
        for dist_id, dist_info in distributions.items():
            coords = dist_info.get("coordinates")
            if coords is None:
                polygon = dist_info.get("polygon")
            else:
                polygon = Polygon(coords)
            if polygon is None:
                continue
            cx, cy = polygon.centroid.x, polygon.centroid.y
            graph.nodes[dist_id] = StageNode(
                stage_id=dist_id,
                centroid_x=cx,
                centroid_y=cy,
                stage_type="distribution",
            )

    # Add stage nodes from direct_steering_info.
    for stage_id, info in direct_steering_info.items():
        polygon = info.get("polygon")
        if polygon is None:
            continue
        cx, cy = polygon.centroid.x, polygon.centroid.y
        stage_type = info.get("stage_type", "checkpoint")
        graph.nodes[stage_id] = StageNode(
            stage_id=stage_id,
            centroid_x=cx,
            centroid_y=cy,
            stage_type=stage_type,
        )

    # Build routing engine if walkable polygon provided.
    routing_engine = None
    if walkable_polygon is not None:
        import jupedsim as jps
        routing_engine = jps.RoutingEngine(walkable_polygon)

    # Add edges from transitions.
    for tr in transitions:
        src = tr.get("from", "")
        tgt = tr.get("to", "")
        if src not in graph.nodes or tgt not in graph.nodes:
            continue
        src_node = graph.nodes[src]
        tgt_node = graph.nodes[tgt]

        if routing_engine is not None:
            waypoints = list(
                routing_engine.compute_waypoints(
                    (src_node.centroid_x, src_node.centroid_y),
                    (tgt_node.centroid_x, tgt_node.centroid_y),
                )
            )
            weight = _polyline_length(waypoints)
        else:
            waypoints = [
                (src_node.centroid_x, src_node.centroid_y),
                (tgt_node.centroid_x, tgt_node.centroid_y),
            ]
            weight = _euclidean(
                src_node.centroid_x,
                src_node.centroid_y,
                tgt_node.centroid_x,
                tgt_node.centroid_y,
            )

        edge = StageEdge(
            source=src, target=tgt, weight=weight, waypoints=waypoints,
        )
        graph.edges.setdefault(src, []).append(edge)

    return graph
```

Also add this helper function after `_euclidean`:

```python
def _polyline_length(waypoints: list[tuple[float, float]]) -> float:
    """Sum of Euclidean segment lengths along a polyline."""
    total = 0.0
    for i in range(len(waypoints) - 1):
        total += _euclidean(
            waypoints[i][0], waypoints[i][1],
            waypoints[i + 1][0], waypoints[i + 1][1],
        )
    return total
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest tests/test_route_graph.py::TestPolylineEdges -v`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `uv run python -m pytest tests/test_route_graph.py -v`
Expected: All tests PASS. Existing fixtures don't pass `walkable_polygon`, so they get the centroid-to-centroid fallback with 2-point waypoints. The `test_from_scenario_without_polygon_uses_centroid_ray` test confirms this works.

- [ ] **Step 6: Commit**

```bash
git add pyfds_evac/core/route_graph.py tests/test_route_graph.py
git commit -m "feat(routing): compute polyline waypoints via JPS RoutingEngine in from_scenario"
```

---

### Task 3: Sample extinction along polyline instead of centroid ray

**Files:**
- Modify: `pyfds_evac/core/route_graph.py:212-264` (`integrated_extinction_along_los`), `pyfds_evac/core/route_graph.py:318-347` (`_sample_segment_extinction`)
- Test: `tests/test_route_graph.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_route_graph.py`:

```python
class TestPolylineSampling:
    def test_extinction_along_polyline_samples_waypoints(self):
        """Extinction sampling should follow polyline, not straight ray."""
        from pyfds_evac.core.route_graph import integrated_extinction_along_polyline

        class SpatialField:
            """Returns K=0 below y=5, K=10 above y=5."""
            def sample_extinction(self, time_s, x, y):
                return 0.0 if y < 5.0 else 10.0

        # Polyline that goes up through the smoky region and back down.
        # (0,0) -> (0,10) -> (10,10) -> (10,0)
        # Half the path length is in the smoky region (y>=5).
        waypoints = [(0, 0), (0, 10), (10, 10), (10, 0)]
        k_avg = integrated_extinction_along_polyline(
            waypoints=waypoints,
            time_s=0.0,
            extinction_sampler=SpatialField(),
            step_m=1.0,
        )
        # Roughly half the path is in smoke (K=10), half clear (K=0).
        assert k_avg == pytest.approx(5.0, abs=1.0)

    def test_extinction_along_polyline_two_points_matches_los(self):
        """Two-point polyline should match the straight-line LOS function."""
        from pyfds_evac.core.route_graph import (
            integrated_extinction_along_los,
            integrated_extinction_along_polyline,
        )

        field = ConstantExtinctionField(k=3.0)
        waypoints = [(0, 0), (10, 0)]
        k_poly = integrated_extinction_along_polyline(
            waypoints=waypoints,
            time_s=0.0,
            extinction_sampler=field,
            step_m=2.0,
        )
        k_los = integrated_extinction_along_los(
            0, 0, 10, 0,
            time_s=0.0,
            extinction_sampler=field,
            step_m=2.0,
        )
        assert k_poly == pytest.approx(k_los, abs=0.01)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/test_route_graph.py::TestPolylineSampling -v`
Expected: FAIL — `cannot import name 'integrated_extinction_along_polyline'`

- [ ] **Step 3: Implement `integrated_extinction_along_polyline`**

Add after `integrated_extinction_along_los` in `route_graph.py`:

```python
def integrated_extinction_along_polyline(
    waypoints: list[tuple[float, float]],
    time_s: float,
    extinction_sampler: ExtinctionSampler,
    step_m: float = 2.0,
) -> float:
    """Return the Beer-Lambert path-integrated mean extinction along a polyline.

    Samples K at uniform intervals along each segment of the polyline and
    returns the overall arithmetic mean, weighted by segment length.

    Parameters
    ----------
    waypoints : list of (x, y) tuples
        The polyline vertices in order.
    time_s : float
        Simulation time for the extinction snapshot.
    extinction_sampler : ExtinctionSampler
        Provides ``sample_extinction(time_s, x, y) -> float``.
    step_m : float
        Maximum spacing between sample points along each segment.
    """
    if step_m <= 0:
        raise ValueError(f"step_m must be positive, got {step_m}")
    if len(waypoints) < 2:
        if waypoints:
            return extinction_sampler.sample_extinction(
                time_s, waypoints[0][0], waypoints[0][1]
            )
        return 0.0

    total_k = 0.0
    total_samples = 0
    for i in range(len(waypoints) - 1):
        x0, y0 = waypoints[i]
        x1, y1 = waypoints[i + 1]
        seg_len = _euclidean(x0, y0, x1, y1)
        if seg_len < 1e-9:
            total_k += extinction_sampler.sample_extinction(time_s, x0, y0)
            total_samples += 1
            continue
        n_samples = max(2, int(math.ceil(seg_len / step_m)) + 1)
        for j in range(n_samples):
            t = j / (n_samples - 1)
            x = x0 + t * (x1 - x0)
            y = y0 + t * (y1 - y0)
            total_k += extinction_sampler.sample_extinction(time_s, x, y)
            total_samples += 1

    return total_k / total_samples if total_samples > 0 else 0.0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest tests/test_route_graph.py::TestPolylineSampling -v`
Expected: PASS

- [ ] **Step 5: Update `_sample_segment_extinction` to use polyline**

Change `_sample_segment_extinction` in `route_graph.py` from:

```python
def _sample_segment_extinction(
    src_node: StageNode,
    tgt_node: StageNode,
    time_s: float,
    extinction_sampler: ExtinctionSampler,
    step_m: float,
) -> tuple[float, float]:
```

to:

```python
def _sample_segment_extinction(
    src_node: StageNode,
    tgt_node: StageNode,
    time_s: float,
    extinction_sampler: ExtinctionSampler,
    step_m: float,
    waypoints: list[tuple[float, float]] | None = None,
) -> tuple[float, float]:
    """Sample extinction along edge geometry.

    Uses the polyline waypoints if provided, otherwise falls back to the
    centroid-to-centroid line of sight.

    Returns (segment_length, mean_extinction).
    """
    if waypoints and len(waypoints) >= 2:
        length = _polyline_length(waypoints)
        k_avg = integrated_extinction_along_polyline(
            waypoints, time_s, extinction_sampler, step_m,
        )
    else:
        length = _euclidean(
            src_node.centroid_x,
            src_node.centroid_y,
            tgt_node.centroid_x,
            tgt_node.centroid_y,
        )
        k_avg = integrated_extinction_along_los(
            src_node.centroid_x,
            src_node.centroid_y,
            tgt_node.centroid_x,
            tgt_node.centroid_y,
            time_s,
            extinction_sampler,
            step_m,
        )
    return length, k_avg
```

- [ ] **Step 6: Update `evaluate_segment` to pass waypoints**

Change `evaluate_segment` to look up the edge waypoints from the graph and pass them through:

```python
def evaluate_segment(
    graph: StageGraph,
    source: str,
    target: str,
    time_s: float,
    extinction_sampler: ExtinctionSampler,
    fed_rate_sampler: FedRateSampler | None,
    config: RouteCostConfig,
) -> SegmentCost:
    """Evaluate cost for one edge of a route."""
    src_node = graph.nodes[source]
    tgt_node = graph.nodes[target]

    # Look up edge waypoints.
    waypoints = None
    for edge in graph.edges.get(source, []):
        if edge.target == target:
            waypoints = edge.waypoints
            break

    length, k_avg = _sample_segment_extinction(
        src_node, tgt_node, time_s, extinction_sampler,
        config.sampling_step_m, waypoints=waypoints,
    )
    sf = speed_factor_from_extinction(
        k_avg,
        alpha=config.alpha,
        beta=config.beta,
        min_speed_factor=config.min_speed_factor,
    )
    effective_speed = config.base_speed_m_per_s * sf
    travel_time = length / effective_speed if effective_speed > 1e-9 else math.inf

    fed_growth = 0.0
    if fed_rate_sampler is not None:
        mid_x, mid_y = _polyline_midpoint(waypoints) if waypoints else (
            (src_node.centroid_x + tgt_node.centroid_x) / 2,
            (src_node.centroid_y + tgt_node.centroid_y) / 2,
        )
        fed_rate = fed_rate_sampler.sample_fed_rate(time_s, mid_x, mid_y)
        fed_growth = fed_rate * travel_time / _SECONDS_PER_MINUTE

    visible = k_avg < config.visibility_extinction_threshold

    return SegmentCost(
        source=source,
        target=target,
        length_m=length,
        k_avg=k_avg,
        speed_factor=sf,
        travel_time_s=travel_time,
        fed_growth=fed_growth,
        visible=visible,
    )
```

Add the `_polyline_midpoint` helper after `_polyline_length`:

```python
def _polyline_midpoint(
    waypoints: list[tuple[float, float]],
) -> tuple[float, float]:
    """Return the point at half the arc length along a polyline."""
    if not waypoints:
        return (0.0, 0.0)
    if len(waypoints) == 1:
        return waypoints[0]

    total = _polyline_length(waypoints)
    if total < 1e-9:
        return waypoints[0]

    half = total / 2.0
    acc = 0.0
    for i in range(len(waypoints) - 1):
        x0, y0 = waypoints[i]
        x1, y1 = waypoints[i + 1]
        seg = _euclidean(x0, y0, x1, y1)
        if acc + seg >= half:
            t = (half - acc) / seg if seg > 1e-9 else 0.0
            return (x0 + t * (x1 - x0), y0 + t * (y1 - y0))
        acc += seg
    return waypoints[-1]
```

- [ ] **Step 7: Run full test suite**

Run: `uv run python -m pytest tests/test_route_graph.py -v`
Expected: All tests PASS. Existing tests use graphs without waypoints on edges; the fallback path in `_sample_segment_extinction` handles `waypoints=None` or `waypoints=[]`.

- [ ] **Step 8: Commit**

```bash
git add pyfds_evac/core/route_graph.py tests/test_route_graph.py
git commit -m "feat(routing): sample extinction and FED along polyline edge geometry"
```

---

### Task 4: Dynamic Dijkstra with smoke-adjusted weights

**Files:**
- Modify: `pyfds_evac/core/route_graph.py:160-180` (`_dijkstra`), `pyfds_evac/core/route_graph.py:132-146` (`shortest_paths_to_exits`), `pyfds_evac/core/route_graph.py:457-540` (`rank_routes`)
- Test: `tests/test_route_graph.py`

- [ ] **Step 1: Write failing test for dynamic Dijkstra**

Add to `tests/test_route_graph.py`:

```python
class TestDynamicDijkstra:
    def test_dynamic_weights_override_static(self, diamond_graph):
        """Dijkstra with dynamic weights picks a different path than static."""
        # Static: D0->C0->E0 is shorter than D0->C1->E0.
        static_paths = diamond_graph.shortest_paths_to_exits("D0")
        static_path = static_paths["E0"][1]
        assert "C0" in static_path  # shorter geometric path

        # Dynamic: make D0->C0 very expensive, D0->C1 cheap.
        dynamic_weights = {
            ("D0", "C0"): 1000.0,
            ("D0", "C1"): 1.0,
            ("C0", "E0"): 1.0,
            ("C1", "E0"): 1.0,
        }
        dynamic_paths = diamond_graph.shortest_paths_to_exits(
            "D0", dynamic_weights=dynamic_weights
        )
        dynamic_path = dynamic_paths["E0"][1]
        assert "C1" in dynamic_path  # longer geometric but cheaper dynamic

    def test_dynamic_weights_none_uses_static(self, diamond_graph):
        """When dynamic_weights=None, behavior is unchanged."""
        paths_default = diamond_graph.shortest_paths_to_exits("D0")
        paths_explicit = diamond_graph.shortest_paths_to_exits(
            "D0", dynamic_weights=None
        )
        assert paths_default == paths_explicit
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/test_route_graph.py::TestDynamicDijkstra -v`
Expected: FAIL — `shortest_paths_to_exits() got an unexpected keyword argument 'dynamic_weights'`

- [ ] **Step 3: Add `dynamic_weights` parameter to `_dijkstra` and `shortest_paths_to_exits`**

Update `_dijkstra`:

```python
def _dijkstra(
    self,
    source: str,
    dynamic_weights: dict[tuple[str, str], float] | None = None,
) -> tuple[dict[str, float], dict[str, str | None]]:
    """Run Dijkstra from *source*.  Returns (dist, prev) dicts.

    When *dynamic_weights* is provided, edge cost is looked up from
    the dict instead of using the static edge weight.  Keys are
    ``(source_id, target_id)`` tuples.
    """
    if source not in self.nodes:
        return {}, {}
    dist: dict[str, float] = {sid: math.inf for sid in self.nodes}
    prev: dict[str, str | None] = {sid: None for sid in self.nodes}
    dist[source] = 0.0
    heap: list[tuple[float, str]] = [(0.0, source)]

    while heap:
        d, u = heapq.heappop(heap)
        if d > dist[u]:
            continue
        for edge in self.edges.get(u, []):
            if dynamic_weights is not None:
                w = dynamic_weights.get((edge.source, edge.target), edge.weight)
            else:
                w = edge.weight
            alt = d + w
            if alt < dist[edge.target]:
                dist[edge.target] = alt
                prev[edge.target] = u
                heapq.heappush(heap, (alt, edge.target))

    return dist, prev
```

Update `shortest_paths_to_exits`:

```python
def shortest_paths_to_exits(
    self,
    source: str,
    dynamic_weights: dict[tuple[str, str], float] | None = None,
) -> dict[str, tuple[float, list[str]]]:
    """Dijkstra from *source* to every reachable exit.

    Returns a dict mapping exit_id -> (cost, path) where path is the
    list of stage IDs from source to exit inclusive.

    When *dynamic_weights* is provided, edge costs are looked up from
    the dict instead of using static Euclidean weights.
    """
    dist, prev = self._dijkstra(source, dynamic_weights=dynamic_weights)
    results: dict[str, tuple[float, list[str]]] = {}
    for exit_id in self.exit_nodes():
        if exit_id in dist and math.isfinite(dist[exit_id]):
            path = self._reconstruct(prev, source, exit_id)
            results[exit_id] = (dist[exit_id], path)
    return results
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest tests/test_route_graph.py::TestDynamicDijkstra -v`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `uv run python -m pytest tests/test_route_graph.py -v`
Expected: All tests PASS. Existing callers don't pass `dynamic_weights`, so they use the default `None` path.

- [ ] **Step 6: Commit**

```bash
git add pyfds_evac/core/route_graph.py tests/test_route_graph.py
git commit -m "feat(routing): support dynamic edge weights in Dijkstra"
```

---

### Task 5: Wire dynamic weights into `rank_routes`

**Files:**
- Modify: `pyfds_evac/core/route_graph.py:457-540` (`rank_routes`)
- Test: `tests/test_route_graph.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_route_graph.py`:

```python
class TestDynamicRanking:
    def test_rank_routes_uses_dynamic_dijkstra(self, diamond_graph):
        """rank_routes should pick the dynamically cheaper path, not geometric shortest."""

        class SpatialSmoke:
            """Heavy smoke near C0 (0,10), clear near C1 (0,30)."""
            def sample_extinction(self, time_s, x, y):
                if abs(y - 10.0) < 5.0:
                    return 5.0  # heavy smoke near C0
                return 0.0

        ranked = rank_routes(
            diamond_graph,
            source="D0",
            time_s=0.0,
            current_fed=0.0,
            extinction_sampler=SpatialSmoke(),
            fed_rate_sampler=None,
            config=RouteCostConfig(),
        )
        assert len(ranked) >= 1
        best = ranked[0]
        # With heavy smoke on the C0 path, the C1 path should win
        # even though it is geometrically longer.
        assert "C1" in best.path, (
            f"Expected C1 path due to smoke, got {best.path}"
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/test_route_graph.py::TestDynamicRanking -v`
Expected: FAIL — `rank_routes` currently uses static Dijkstra, so it picks the C0 path (geometrically shorter) and only then smoke-scores it. With static Dijkstra, the C1 path is never even considered because Dijkstra finds D0→C0→E0 as the only shortest path to E0.

- [ ] **Step 3: Update `rank_routes` to pre-compute dynamic edge weights**

Replace the `rank_routes` function:

```python
def rank_routes(
    graph: StageGraph,
    source: str,
    time_s: float,
    current_fed: float,
    extinction_sampler: ExtinctionSampler,
    fed_rate_sampler: FedRateSampler | None,
    config: RouteCostConfig,
    *,
    cached_segments: dict[tuple[str, str], SegmentCost] | None = None,
) -> list[RouteCost]:
    """Evaluate and rank all routes from *source* to reachable exits.

    Computes dynamic edge weights from current smoke/FED conditions,
    then runs Dijkstra with those weights so pathfinding picks the
    cheapest path under current conditions (not just the geometrically
    shortest).

    Returns routes sorted by composite cost (lowest first).
    Rejected routes are sorted to the end.
    If all routes are rejected, the least-bad route is un-rejected
    as a fallback.
    """
    # Phase 1: evaluate all edges to get dynamic costs.
    dynamic_weights: dict[tuple[str, str], float] = {}
    for src_id, edges in graph.edges.items():
        for edge in edges:
            cache_key = (edge.source, edge.target)
            if cached_segments is not None and cache_key in cached_segments:
                seg = cached_segments[cache_key]
            else:
                seg = evaluate_segment(
                    graph,
                    edge.source,
                    edge.target,
                    time_s,
                    extinction_sampler,
                    fed_rate_sampler,
                    config,
                )
                if cached_segments is not None:
                    cached_segments[cache_key] = seg
            # Per-edge cost: additive decomposition of the composite formula.
            # current_fed is constant across routes for one agent, so omitting
            # it from edge costs does not affect ranking.
            dynamic_weights[cache_key] = (
                seg.length_m * (1.0 + config.w_smoke * seg.k_avg)
                + config.w_fed * seg.fed_growth
            )

    # Phase 2: Dijkstra with dynamic weights.
    all_paths = graph.shortest_paths_to_exits(
        source, dynamic_weights=dynamic_weights
    )
    if not all_paths:
        return []

    # Phase 3: evaluate full routes (reusing cached segments).
    costs: list[RouteCost] = []
    for exit_id, (_dist, path) in all_paths.items():
        rc = evaluate_route(
            graph,
            path,
            time_s,
            current_fed,
            extinction_sampler,
            fed_rate_sampler,
            config,
            cached_segments=cached_segments,
        )
        costs.append(rc)

    # Check visibility rejection: reject routes where all segments
    # are non-visible, but only if at least one other route has visibility.
    any_visible = any(
        any(s.visible for s in rc.segments) for rc in costs if not rc.rejected
    )
    if any_visible:
        updated: list[RouteCost] = []
        for rc in costs:
            if not rc.rejected and not any(s.visible for s in rc.segments):
                rc = RouteCost(
                    exit_id=rc.exit_id,
                    path=rc.path,
                    path_length_m=rc.path_length_m,
                    k_ave_route=rc.k_ave_route,
                    travel_time_s=rc.travel_time_s,
                    fed_max_route=rc.fed_max_route,
                    composite_cost=rc.composite_cost,
                    segments=rc.segments,
                    rejected=True,
                    rejection_reason="all segments non-visible",
                )
            updated.append(rc)
        costs = updated

    # Sort: non-rejected first by cost, then rejected by cost.
    # Break ties by fewer intermediate stages.
    def sort_key(rc: RouteCost) -> tuple[int, float, int]:
        return (1 if rc.rejected else 0, rc.composite_cost, len(rc.path))

    costs.sort(key=sort_key)

    # Fallback: if all rejected, un-reject the least-bad.
    if costs and all(rc.rejected for rc in costs):
        best = costs[0]
        costs[0] = RouteCost(
            exit_id=best.exit_id,
            path=best.path,
            path_length_m=best.path_length_m,
            k_ave_route=best.k_ave_route,
            travel_time_s=best.travel_time_s,
            fed_max_route=best.fed_max_route,
            composite_cost=best.composite_cost,
            segments=best.segments,
            rejected=False,
            rejection_reason=f"fallback: {best.rejection_reason}",
        )

    return costs
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest tests/test_route_graph.py::TestDynamicRanking -v`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `uv run python -m pytest tests/test_route_graph.py -v`
Expected: All tests PASS. The existing `TestRankRoutes` tests use `ConstantExtinctionField` (uniform smoke), so dynamic Dijkstra produces the same ranking as static — the geometrically shorter path is also the smoke-cheapest when smoke is uniform.

- [ ] **Step 6: Commit**

```bash
git add pyfds_evac/core/route_graph.py tests/test_route_graph.py
git commit -m "feat(routing): run Dijkstra with dynamic smoke/FED-adjusted edge weights"
```

---

### Task 6: Wire FED rate sampler and RoutingEngine into scenario.py

**Files:**
- Modify: `pyfds_evac/core/scenario.py:989-994` (graph construction), `pyfds_evac/core/scenario.py:1556-1567` (evaluate_and_reroute call)
- Test: `tests/test_route_graph.py`

- [ ] **Step 1: Write test for FED adapter**

Add to `tests/test_route_graph.py`:

```python
class TestFedRateAdapter:
    def test_evaluate_segment_with_fed_sampler(self, linear_graph):
        """evaluate_segment should compute non-zero fed_growth when sampler is provided."""

        class ConstantFedRate:
            def sample_fed_rate(self, time_s, x, y):
                return 0.1  # 0.1 /min everywhere

        seg = evaluate_segment(
            linear_graph,
            "D0",
            "C0",
            time_s=0.0,
            extinction_sampler=ConstantExtinctionField(k=0.0),
            fed_rate_sampler=ConstantFedRate(),
            config=RouteCostConfig(),
        )
        assert seg.fed_growth > 0.0
        # travel_time = 10m / 1.3 m/s ≈ 7.69s; fed_growth = 0.1 * 7.69 / 60
        expected_growth = 0.1 * seg.travel_time_s / 60.0
        assert seg.fed_growth == pytest.approx(expected_growth, rel=0.01)
```

- [ ] **Step 2: Run test to verify it passes**

Run: `uv run python -m pytest tests/test_route_graph.py::TestFedRateAdapter -v`
Expected: PASS (this already works in the existing code — the test confirms the interface is correct).

- [ ] **Step 3: Add `_FedRateAdapter` to scenario.py**

In `pyfds_evac/core/scenario.py`, add near the top-level imports (after the existing imports, before `run_scenario`):

```python
class _FedRateAdapter:
    """Adapt DefaultFedModel to the FedRateSampler protocol."""

    def __init__(self, model):
        self._model = model

    def sample_fed_rate(self, time_s: float, x: float, y: float) -> float:
        _, rate = self._model.sample_rate(time_s, x, y)
        return rate
```

- [ ] **Step 4: Pass walkable polygon to `StageGraph.from_scenario()`**

Change lines ~989-994 in `scenario.py` from:

```python
if reroute_config is not None and direct_steering_info:
    stage_graph = StageGraph.from_scenario(
        direct_steering_info,
        scenario.raw.get("transitions", []),
        distributions=scenario.raw.get("distributions"),
    )
```

to:

```python
if reroute_config is not None and direct_steering_info:
    stage_graph = StageGraph.from_scenario(
        direct_steering_info,
        scenario.raw.get("transitions", []),
        distributions=scenario.raw.get("distributions"),
        walkable_polygon=scenario.walkable_polygon,
    )
```

- [ ] **Step 5: Wire `fed_rate_sampler` into `evaluate_and_reroute` call**

Change line ~1564 in `scenario.py` from:

```python
fed_rate_sampler=None,
```

to:

```python
fed_rate_sampler=_fed_rate_adapter,
```

And add the adapter construction near where `stage_graph` is created (inside the `if reroute_config is not None` block):

```python
_fed_rate_adapter = _FedRateAdapter(fed_model) if fed_model else None
```

Also update the diagnostic `rank_routes` call (~line 1520) the same way — replace `fed_rate_sampler=None` with `fed_rate_sampler=_fed_rate_adapter` so the diagnostic history matches actual rerouting.

- [ ] **Step 6: Run full test suite**

Run: `uv run python -m pytest tests/ -q`
Expected: All tests PASS.

- [ ] **Step 7: Commit**

```bash
git add pyfds_evac/core/scenario.py tests/test_route_graph.py
git commit -m "feat(routing): wire RoutingEngine and FED rate sampler into scenario loop"
```

---

### Task 7: Update docs/routing.md

**Files:**
- Modify: `docs/routing.md`

- [ ] **Step 1: Update intro paragraph**

Remove the FED-inactive note added in the earlier doc fix. Replace lines 5-12 with:

```markdown
The pyFDS-Evac routing system implements dynamic, smoke-aware path
planning. Agents evaluate candidate routes based on smoke exposure
and toxic gas dose, and periodically reroute to lower-cost paths as
conditions change. Route costs are recomputed from current hazard
fields at each reevaluation tick, so the chosen path adapts as
conditions evolve.
```

- [ ] **Step 2: Update cost model section**

Revert the "(plus an inactive FED term)" wording at line ~48. Replace with:

```markdown
Each candidate route is scored by evaluating its segments (edges)
against current smoke and FED conditions. The cost model combines
path length, smoke exposure, and toxic gas dose.
```

Remove the "*(Currently inactive...)*" note from segment step 4.

- [ ] **Step 3: Update edge geometry description**

After the "Stage graph" section, add:

```markdown
### Edge geometry

Edges carry a polyline that follows the corridor geometry computed
by JuPedSim's `RoutingEngine` at graph construction time.  Smoke
and FED are sampled along this polyline, not along a straight
centroid-to-centroid ray.  Edge weight is the polyline arc length.

When no walkable polygon is provided (e.g. in unit tests), edges
fall back to a straight centroid-to-centroid ray.
```

- [ ] **Step 4: Update Dijkstra description in rerouting flow**

Change the rerouting flow pseudocode step 2 from:

```
2. rank_routes(source, t, FED, K_field)
   ├─ Dijkstra → one shortest path per reachable exit
   ├─ evaluate_route on each path (composite cost + rejection flags)
   │   (only the geometrically shortest path to each exit is scored;
   │    alternative paths to the same exit are not enumerated)
```

to:

```
2. rank_routes(source, t, FED, K_field)
   ├─ evaluate all edges → dynamic costs from current smoke/FED
   ├─ Dijkstra with dynamic weights → one cheapest path per reachable exit
   ├─ evaluate_route on each path (composite cost + rejection flags)
```

- [ ] **Step 5: Run full test suite (sanity check)**

Run: `uv run python -m pytest tests/ -q`
Expected: All tests PASS.

- [ ] **Step 6: Commit**

```bash
git add docs/routing.md
git commit -m "docs(routing): update for dynamic Dijkstra, polyline edges, and FED activation"
```
