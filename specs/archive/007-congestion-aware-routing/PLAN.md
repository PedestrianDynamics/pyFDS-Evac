# Congestion-Aware Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a queueing cost term to route ranking so agents distribute across exits instead of all picking the same cheapest one.

**Architecture:** The queue penalty is added at the route-level composite cost (Phase 3), not in Dijkstra edge weights. Exit counts are tracked in a `dict[str, int]` derived from `AgentRouteState.current_exit` as the single source of truth. The reroute loop is decoupled from the smoke model so congestion routing works in clear-air scenarios.

**Tech Stack:** Python 3.11+, dataclasses, pytest, shapely (for test fixtures)

---

## File structure

| File | Responsibility |
|------|---------------|
| `pyfds_evac/core/route_graph.py` | `StageNode` + capacity field, `RouteCostConfig` + queue weights, `RouteCost` + queue_time_s, `evaluate_route` + queue term, `rank_routes` + exit_counts param, `evaluate_and_reroute` + exit_counts param |
| `pyfds_evac/core/scenario.py` | Remove smoke gate from reroute loop, zero-extinction fallback, seed exit_counts at startup, count on flow-spawn, maintain on reroute/removal, pass exit_counts to routing calls, add queue columns to CSV |
| `pyfds_evac/core/simulation_init.py` | Propagate `capacity_agents_per_s` from exit config into `direct_steering_info` |
| `tests/test_route_graph.py` | Unit tests for queue term, backward compat, capacity, exit count effect |
| `docs/routing.md` | Document queueing cost, config parameters, congestion behaviour |

---

### Task 1: Add `capacity_agents_per_s` to `StageNode`

**Files:**
- Modify: `pyfds_evac/core/route_graph.py:17-24`
- Modify: `pyfds_evac/core/route_graph.py:102-113`
- Test: `tests/test_route_graph.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_route_graph.py`:

```python
class TestStageNodeCapacity:
    def test_default_capacity_is_none(self):
        from pyfds_evac.core.route_graph import StageNode

        node = StageNode(
            stage_id="E0",
            centroid_x=0.0,
            centroid_y=0.0,
            stage_type="exit",
        )
        assert node.capacity_agents_per_s is None

    def test_capacity_set_from_constructor(self):
        from pyfds_evac.core.route_graph import StageNode

        node = StageNode(
            stage_id="E0",
            centroid_x=0.0,
            centroid_y=0.0,
            stage_type="exit",
            capacity_agents_per_s=2.5,
        )
        assert node.capacity_agents_per_s == 2.5

    def test_capacity_propagated_from_scenario(self):
        direct_steering_info = {
            "E0": {
                "polygon": _box(10, 0),
                "stage_type": "exit",
                "capacity_agents_per_s": 2.0,
            },
        }
        distributions = {
            "D0": {"coordinates": list(_box(0, 0).exterior.coords)},
        }
        transitions = [{"from": "D0", "to": "E0"}]
        graph = StageGraph.from_scenario(
            direct_steering_info, transitions, distributions
        )
        assert graph.nodes["E0"].capacity_agents_per_s == 2.0
        assert graph.nodes["D0"].capacity_agents_per_s is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m pytest tests/test_route_graph.py::TestStageNodeCapacity -v`
Expected: FAIL — `StageNode.__init__()` got unexpected keyword argument `capacity_agents_per_s`

- [ ] **Step 3: Add the field to `StageNode`**

In `pyfds_evac/core/route_graph.py`, change the `StageNode` dataclass (line 17-24):

```python
@dataclass(frozen=True)
class StageNode:
    """A node in the stage graph representing one stage."""

    stage_id: str
    centroid_x: float
    centroid_y: float
    stage_type: str  # "exit", "checkpoint", "distribution", "zone"
    capacity_agents_per_s: float | None = None
```

- [ ] **Step 4: Propagate capacity in `from_scenario`**

In `pyfds_evac/core/route_graph.py`, update the stage-node construction loop (line 102-113).  Change the `StageNode(...)` call to pass the capacity:

```python
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
                capacity_agents_per_s=info.get("capacity_agents_per_s"),
            )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run python -m pytest tests/test_route_graph.py::TestStageNodeCapacity -v`
Expected: 3 passed

- [ ] **Step 6: Run full test suite for regressions**

Run: `uv run python -m pytest tests/test_route_graph.py -v`
Expected: all existing tests pass (the new optional field with `None` default doesn't break anything)

- [ ] **Step 7: Commit**

```bash
git add pyfds_evac/core/route_graph.py tests/test_route_graph.py
git commit -m "feat(routing): add capacity_agents_per_s to StageNode"
```

---

### Task 2: Add `w_queue` and `default_exit_capacity` to `RouteCostConfig`, add `queue_time_s` to `RouteCost`

**Files:**
- Modify: `pyfds_evac/core/route_graph.py:391-403` (`RouteCostConfig`)
- Modify: `pyfds_evac/core/route_graph.py:420-433` (`RouteCost`)
- Modify: `pyfds_evac/core/route_graph.py:586-597` (`evaluate_route` return)
- Modify: `pyfds_evac/core/route_graph.py:679-691` (visibility rejection `RouteCost` rebuild)
- Modify: `pyfds_evac/core/route_graph.py:704-715` (fallback `RouteCost` rebuild)
- Test: `tests/test_route_graph.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_route_graph.py`:

```python
class TestQueueConfigAndFields:
    def test_route_cost_config_defaults(self):
        config = RouteCostConfig()
        assert config.w_queue == 1.0
        assert config.default_exit_capacity == 1.3

    def test_route_cost_config_queue_disabled(self):
        config = RouteCostConfig(w_queue=0.0)
        assert config.w_queue == 0.0

    def test_route_cost_has_queue_time_field(self, linear_graph):
        field = ConstantExtinctionField(0.0)
        config = RouteCostConfig()
        rc = evaluate_route(
            linear_graph, ["D0", "C0", "E0"], 0.0, 0.0, field, None, config
        )
        assert hasattr(rc, "queue_time_s")
        assert rc.queue_time_s == 0.0
```

Note: this test imports `ConstantExtinctionField` from `pyfds_evac.core.smoke_speed` (already imported in the test file) and uses the existing `linear_graph` fixture.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m pytest tests/test_route_graph.py::TestQueueConfigAndFields -v`
Expected: FAIL — `RouteCostConfig` has no `w_queue` attribute / `RouteCost` has no `queue_time_s`

- [ ] **Step 3: Add fields to `RouteCostConfig`**

In `pyfds_evac/core/route_graph.py`, update `RouteCostConfig` (line 391-403):

```python
@dataclass(frozen=True)
class RouteCostConfig:
    """Weights and thresholds for route cost evaluation."""

    w_smoke: float = 1.0
    w_fed: float = 10.0
    w_queue: float = 1.0
    fed_rejection_threshold: float = 1.0
    visibility_extinction_threshold: float = 0.5
    sampling_step_m: float = 2.0
    base_speed_m_per_s: float = 1.3
    alpha: float = 0.706
    beta: float = -0.057
    min_speed_factor: float = 0.1
    default_exit_capacity: float = 1.3
```

- [ ] **Step 4: Add `queue_time_s` field to `RouteCost`**

In `pyfds_evac/core/route_graph.py`, update `RouteCost` (line 420-433):

```python
@dataclass(frozen=True)
class RouteCost:
    """Full cost evaluation for one candidate route."""

    exit_id: str
    path: list[str]
    path_length_m: float
    k_ave_route: float
    travel_time_s: float
    fed_max_route: float
    composite_cost: float
    segments: list[SegmentCost]
    rejected: bool
    rejection_reason: str | None
    queue_time_s: float = 0.0
```

- [ ] **Step 5: Update all `RouteCost(...)` constructor calls to pass `queue_time_s=0.0`**

There are three call sites in `route_graph.py`.  Add `queue_time_s=0.0` to each:

**Call site 1** — `evaluate_route` return (line ~586):

```python
    return RouteCost(
        exit_id=path[-1] if path else "",
        path=path,
        path_length_m=path_length,
        k_ave_route=k_ave,
        travel_time_s=travel_time,
        fed_max_route=fed_max,
        composite_cost=composite,
        segments=segments,
        rejected=rejected,
        rejection_reason=reason,
        queue_time_s=0.0,
    )
```

**Call site 2** — visibility rejection rebuild (line ~679):

```python
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
                    queue_time_s=rc.queue_time_s,
                )
```

**Call site 3** — fallback un-reject rebuild (line ~704):

```python
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
            queue_time_s=best.queue_time_s,
        )
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run python -m pytest tests/test_route_graph.py::TestQueueConfigAndFields -v`
Expected: 3 passed

- [ ] **Step 7: Run full test suite for regressions**

Run: `uv run python -m pytest tests/test_route_graph.py -v`
Expected: all existing tests pass

- [ ] **Step 8: Commit**

```bash
git add pyfds_evac/core/route_graph.py tests/test_route_graph.py
git commit -m "feat(routing): add w_queue, default_exit_capacity to config; queue_time_s to RouteCost"
```

---

### Task 3: Add queue term to `evaluate_route` and wire `exit_counts` into `rank_routes`

**Files:**
- Modify: `pyfds_evac/core/route_graph.py:539-597` (`evaluate_route`)
- Modify: `pyfds_evac/core/route_graph.py:600-717` (`rank_routes`)
- Test: `tests/test_route_graph.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_route_graph.py`:

```python
class TestQueueCostTerm:
    def test_evaluate_route_adds_queue_cost(self, multi_exit_graph):
        """Queue term increases composite cost for a congested exit."""
        field = ConstantExtinctionField(0.0)
        config = RouteCostConfig(w_smoke=0.0, w_fed=0.0, w_queue=1.0)

        # Without queue counts: route to E0 (distance ~10)
        rc_no_queue = evaluate_route(
            multi_exit_graph,
            ["D0", "E0"],
            0.0,
            0.0,
            field,
            None,
            config,
        )

        # With queue counts: 20 agents at E0
        rc_with_queue = evaluate_route(
            multi_exit_graph,
            ["D0", "E0"],
            0.0,
            0.0,
            field,
            None,
            config,
            exit_counts={"E0": 20, "E1": 0},
        )

        assert rc_with_queue.composite_cost > rc_no_queue.composite_cost
        assert rc_with_queue.queue_time_s > 0.0
        assert rc_no_queue.queue_time_s == 0.0

    def test_queue_cost_uses_distance_equivalent(self, multi_exit_graph):
        """Queue cost = w_queue * base_speed * N / capacity."""
        field = ConstantExtinctionField(0.0)
        base_speed = 1.3
        capacity = 1.3
        n_agents = 10
        config = RouteCostConfig(
            w_smoke=0.0,
            w_fed=0.0,
            w_queue=1.0,
            base_speed_m_per_s=base_speed,
            default_exit_capacity=capacity,
        )
        rc = evaluate_route(
            multi_exit_graph,
            ["D0", "E0"],
            0.0,
            0.0,
            field,
            None,
            config,
            exit_counts={"E0": n_agents},
        )
        expected_queue_time = n_agents / capacity
        expected_queue_distance = base_speed * expected_queue_time
        # path_length is ~10m, composite = 10 + 1.0 * queue_distance
        assert abs(rc.queue_time_s - expected_queue_time) < 1e-6
        assert abs(
            rc.composite_cost - (rc.path_length_m + expected_queue_distance)
        ) < 0.1

    def test_w_queue_zero_disables_queue(self, multi_exit_graph):
        """w_queue=0 means exit_counts have no effect."""
        field = ConstantExtinctionField(0.0)
        config = RouteCostConfig(w_smoke=0.0, w_fed=0.0, w_queue=0.0)
        rc_no_counts = evaluate_route(
            multi_exit_graph,
            ["D0", "E0"],
            0.0,
            0.0,
            field,
            None,
            config,
        )
        rc_with_counts = evaluate_route(
            multi_exit_graph,
            ["D0", "E0"],
            0.0,
            0.0,
            field,
            None,
            config,
            exit_counts={"E0": 100},
        )
        assert abs(rc_no_counts.composite_cost - rc_with_counts.composite_cost) < 1e-9

    def test_custom_capacity_reduces_penalty(self, multi_exit_graph):
        """Higher capacity → lower queue penalty for same agent count."""
        field = ConstantExtinctionField(0.0)
        config_low = RouteCostConfig(
            w_smoke=0.0, w_fed=0.0, w_queue=1.0, default_exit_capacity=1.0
        )
        config_high = RouteCostConfig(
            w_smoke=0.0, w_fed=0.0, w_queue=1.0, default_exit_capacity=5.0
        )
        counts = {"E0": 20}
        rc_low = evaluate_route(
            multi_exit_graph,
            ["D0", "E0"],
            0.0,
            0.0,
            field,
            None,
            config_low,
            exit_counts=counts,
        )
        rc_high = evaluate_route(
            multi_exit_graph,
            ["D0", "E0"],
            0.0,
            0.0,
            field,
            None,
            config_high,
            exit_counts=counts,
        )
        assert rc_low.composite_cost > rc_high.composite_cost

    def test_node_capacity_overrides_default(self):
        """StageNode.capacity_agents_per_s overrides config default."""
        direct_steering_info = {
            "E0": {
                "polygon": _box(10, 0),
                "stage_type": "exit",
                "capacity_agents_per_s": 10.0,
            },
        }
        distributions = {
            "D0": {"coordinates": list(_box(0, 0).exterior.coords)},
        }
        transitions = [{"from": "D0", "to": "E0"}]
        graph = StageGraph.from_scenario(
            direct_steering_info, transitions, distributions
        )
        field = ConstantExtinctionField(0.0)
        config = RouteCostConfig(
            w_smoke=0.0, w_fed=0.0, w_queue=1.0, default_exit_capacity=1.0
        )
        counts = {"E0": 10}
        rc = evaluate_route(
            graph, ["D0", "E0"], 0.0, 0.0, field, None, config,
            exit_counts=counts,
        )
        # capacity=10 → queue_time = 10/10 = 1.0s
        assert abs(rc.queue_time_s - 1.0) < 1e-6


class TestRankRoutesWithCongestion:
    def test_congestion_shifts_best_exit(self, multi_exit_graph):
        """With enough agents at E0, E1 becomes cheaper despite being farther."""
        field = ConstantExtinctionField(0.0)
        config = RouteCostConfig(w_smoke=0.0, w_fed=0.0, w_queue=1.0)

        # Without congestion: E0 is closer (10m vs 20m)
        ranked_no_q = rank_routes(
            multi_exit_graph, "D0", 0.0, 0.0, field, None, config
        )
        assert ranked_no_q[0].exit_id == "E0"

        # With heavy congestion at E0: E1 should become cheaper
        # E0: 10m + 1.0 * 1.3 * 50/1.3 = 10 + 50 = 60
        # E1: 20m + 1.0 * 1.3 * 0/1.3  = 20 + 0  = 20
        ranked_q = rank_routes(
            multi_exit_graph, "D0", 0.0, 0.0, field, None, config,
            exit_counts={"E0": 50, "E1": 0},
        )
        assert ranked_q[0].exit_id == "E1"

    def test_rank_routes_without_exit_counts_unchanged(self, multi_exit_graph):
        """Omitting exit_counts gives identical results to current behaviour."""
        field = ConstantExtinctionField(0.0)
        config = RouteCostConfig()
        ranked = rank_routes(
            multi_exit_graph, "D0", 0.0, 0.0, field, None, config
        )
        assert ranked[0].exit_id == "E0"
        assert ranked[0].queue_time_s == 0.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m pytest tests/test_route_graph.py::TestQueueCostTerm tests/test_route_graph.py::TestRankRoutesWithCongestion -v`
Expected: FAIL — `evaluate_route` doesn't accept `exit_counts` / `rank_routes` doesn't accept `exit_counts`

- [ ] **Step 3: Add `exit_counts` parameter to `evaluate_route` and compute queue term**

In `pyfds_evac/core/route_graph.py`, modify `evaluate_route` (line 539-597).

Change the signature to accept `exit_counts`:

```python
def evaluate_route(
    graph: StageGraph,
    path: list[str],
    time_s: float,
    current_fed: float,
    extinction_sampler: ExtinctionSampler,
    fed_rate_sampler: FedRateSampler | None,
    config: RouteCostConfig,
    *,
    cached_segments: dict[tuple[str, str], SegmentCost] | None = None,
    exit_counts: dict[str, int] | None = None,
) -> RouteCost:
```

After the existing composite cost computation (line 577-578), add the queue term:

```python
    # Composite cost: path_length * (1 + w_smoke * K_ave) + w_fed * FED_max
    composite = path_length * (1.0 + config.w_smoke * k_ave) + config.w_fed * fed_max

    # Queue cost: convert queue delay to distance-equivalent units.
    queue_time = 0.0
    if exit_counts is not None and config.w_queue > 0 and path:
        exit_id = path[-1]
        n_exit = exit_counts.get(exit_id, 0)
        exit_node = graph.nodes.get(exit_id)
        capacity = (
            exit_node.capacity_agents_per_s
            if exit_node is not None and exit_node.capacity_agents_per_s is not None
            else config.default_exit_capacity
        )
        if capacity > 0:
            queue_time = n_exit / capacity
            queue_distance = config.base_speed_m_per_s * queue_time
            composite += config.w_queue * queue_distance
```

Update the return statement to pass `queue_time_s=queue_time`:

```python
    return RouteCost(
        exit_id=path[-1] if path else "",
        path=path,
        path_length_m=path_length,
        k_ave_route=k_ave,
        travel_time_s=travel_time,
        fed_max_route=fed_max,
        composite_cost=composite,
        segments=segments,
        rejected=rejected,
        rejection_reason=reason,
        queue_time_s=queue_time,
    )
```

- [ ] **Step 4: Add `exit_counts` keyword-only parameter to `rank_routes`**

In `pyfds_evac/core/route_graph.py`, modify the `rank_routes` signature (line 600-610):

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
    exit_counts: dict[str, int] | None = None,
) -> list[RouteCost]:
```

Pass `exit_counts` through to `evaluate_route` in the Phase 3 loop (line ~658):

```python
        rc = evaluate_route(
            graph,
            path,
            time_s,
            current_fed,
            extinction_sampler,
            fed_rate_sampler,
            config,
            cached_segments=cached_segments,
            exit_counts=exit_counts,
        )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run python -m pytest tests/test_route_graph.py::TestQueueCostTerm tests/test_route_graph.py::TestRankRoutesWithCongestion -v`
Expected: all passed

- [ ] **Step 6: Run full test suite for regressions**

Run: `uv run python -m pytest tests/test_route_graph.py -v`
Expected: all existing tests pass (new param is keyword-only with `None` default)

- [ ] **Step 7: Commit**

```bash
git add pyfds_evac/core/route_graph.py tests/test_route_graph.py
git commit -m "feat(routing): add queue cost term to evaluate_route and rank_routes"
```

---

### Task 4: Wire `exit_counts` into `evaluate_and_reroute`

**Files:**
- Modify: `pyfds_evac/core/route_graph.py:848-929` (`evaluate_and_reroute`)
- Test: `tests/test_route_graph.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_route_graph.py`:

```python
class TestEvaluateAndRerouteWithCongestion:
    def test_congestion_triggers_reroute(self, multi_exit_graph):
        """Agent switches from congested E0 to uncongested E1."""
        field = ConstantExtinctionField(0.0)
        cost_config = RouteCostConfig(w_smoke=0.0, w_fed=0.0, w_queue=1.0)
        config = RerouteConfig(reevaluation_interval_s=1.0, cost_config=cost_config)

        wait_info = {
            "mode": "path",
            "current_origin": "D0",
            "current_target_stage": "E0",
            "path_choices": {"D0": [("E0", 100.0)]},
            "stage_configs": {
                "E0": {
                    "polygon": _box(10, 0),
                    "stage_type": "exit",
                    "waiting_time": 0.0,
                    "waiting_time_distribution": "constant",
                    "waiting_time_std": 1.0,
                    "enable_throughput_throttling": False,
                    "max_throughput": 1.0,
                    "speed_factor": 1.0,
                },
                "E1": {
                    "polygon": _box(20, 0),
                    "stage_type": "exit",
                    "waiting_time": 0.0,
                    "waiting_time_distribution": "constant",
                    "waiting_time_std": 1.0,
                    "enable_throughput_throttling": False,
                    "max_throughput": 1.0,
                    "speed_factor": 1.0,
                },
            },
            "state": "to_target",
        }
        route_state = AgentRouteState(current_exit="E0", eval_offset_s=0.0)

        switch = evaluate_and_reroute(
            agent_id=1,
            wait_info=wait_info,
            route_state=route_state,
            graph=multi_exit_graph,
            current_time_s=10.0,
            current_fed=0.0,
            extinction_sampler=field,
            fed_rate_sampler=None,
            config=config,
            exit_counts={"E0": 50, "E1": 0},
        )
        assert switch is not None
        assert switch.new_exit == "E1"
        assert switch.old_exit == "E0"

    def test_no_exit_counts_backward_compatible(self, multi_exit_graph):
        """Without exit_counts, behaviour is identical to current."""
        field = ConstantExtinctionField(0.0)
        config = RerouteConfig(reevaluation_interval_s=1.0)
        wait_info = {
            "mode": "path",
            "current_origin": "D0",
            "current_target_stage": "E0",
            "path_choices": {"D0": [("E0", 100.0)]},
            "stage_configs": {},
            "state": "to_target",
        }
        route_state = AgentRouteState(eval_offset_s=0.0)

        switch = evaluate_and_reroute(
            agent_id=1,
            wait_info=wait_info,
            route_state=route_state,
            graph=multi_exit_graph,
            current_time_s=10.0,
            current_fed=0.0,
            extinction_sampler=field,
            fed_rate_sampler=None,
            config=config,
        )
        # Initial assignment to E0 (nearest)
        assert switch is not None
        assert switch.new_exit == "E0"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m pytest tests/test_route_graph.py::TestEvaluateAndRerouteWithCongestion -v`
Expected: FAIL — `evaluate_and_reroute` doesn't accept `exit_counts`

- [ ] **Step 3: Add `exit_counts` parameter to `evaluate_and_reroute`**

In `pyfds_evac/core/route_graph.py`, modify the signature (line 848-859):

```python
def evaluate_and_reroute(
    agent_id: int,
    wait_info: dict,
    route_state: AgentRouteState,
    graph: StageGraph,
    current_time_s: float,
    current_fed: float,
    extinction_sampler: ExtinctionSampler,
    fed_rate_sampler: FedRateSampler | None,
    config: RerouteConfig,
    cached_segments: dict[tuple[str, str], SegmentCost] | None = None,
    *,
    exit_counts: dict[str, int] | None = None,
) -> RouteSwitch | None:
```

Pass `exit_counts` through to `rank_routes` (line ~871-880):

```python
    ranked = rank_routes(
        graph,
        source,
        current_time_s,
        current_fed,
        extinction_sampler,
        fed_rate_sampler,
        config.cost_config,
        cached_segments=cached_segments,
        exit_counts=exit_counts,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m pytest tests/test_route_graph.py::TestEvaluateAndRerouteWithCongestion -v`
Expected: all passed

- [ ] **Step 5: Run full test suite for regressions**

Run: `uv run python -m pytest tests/test_route_graph.py -v`
Expected: all existing tests pass

- [ ] **Step 6: Commit**

```bash
git add pyfds_evac/core/route_graph.py tests/test_route_graph.py
git commit -m "feat(routing): wire exit_counts into evaluate_and_reroute"
```

---

### Task 5: Decouple reroute loop from smoke model in `scenario.py`

**Files:**
- Modify: `pyfds_evac/core/scenario.py:1483-1491` (reroute loop guard)
- Modify: `pyfds_evac/core/scenario.py:1547` (smoke_speed_model.field reference)
- Modify: `pyfds_evac/core/scenario.py:1579` (smoke_speed_model.field reference)

This task changes the runtime guard.  No new unit tests are added here — the clear-air integration test in Task 8 validates the behaviour.

- [ ] **Step 1: Add the zero-extinction sampler import at the top of `scenario.py`**

Near the existing imports from `pyfds_evac.core.smoke_speed`, add:

```python
from pyfds_evac.core.smoke_speed import ConstantExtinctionField
```

And define the zero-extinction constant after the imports:

```python
_ZERO_EXTINCTION = ConstantExtinctionField(0.0)
```

- [ ] **Step 2: Remove `smoke_speed_model is not None` from the reroute-loop guard**

In `pyfds_evac/core/scenario.py`, change the reroute-loop condition (line 1483-1491) from:

```python
            if (
                reroute_config is not None
                and stage_graph is not None
                and smoke_speed_model is not None
                and agent_wait_info
                and (
                    last_reroute_check_time is None
                    or simulation.elapsed_time() - last_reroute_check_time >= 1.0
                )
            ):
```

to:

```python
            if (
                reroute_config is not None
                and stage_graph is not None
                and agent_wait_info
                and (
                    last_reroute_check_time is None
                    or simulation.elapsed_time() - last_reroute_check_time >= 1.0
                )
            ):
```

- [ ] **Step 3: Compute `extinction_sampler` once at the top of the reroute block**

Right after the guard (before `route_segment_cache = {}`), add:

```python
                extinction_sampler = (
                    smoke_speed_model.field
                    if smoke_speed_model is not None
                    else _ZERO_EXTINCTION
                )
```

- [ ] **Step 4: Replace `smoke_speed_model.field` with `extinction_sampler` in the reroute block**

There are two references to `smoke_speed_model.field` inside the reroute block:

**Line ~1547** (route cost history collection):
Change `smoke_speed_model.field,` to `extinction_sampler,`

**Line ~1579** (evaluate_and_reroute call):
Change `extinction_sampler=smoke_speed_model.field,` to `extinction_sampler=extinction_sampler,`

- [ ] **Step 5: Run full test suite for regressions**

Run: `uv run python -m pytest tests/ -v`
Expected: all existing tests pass

- [ ] **Step 6: Commit**

```bash
git add pyfds_evac/core/scenario.py
git commit -m "feat(routing): decouple reroute loop from smoke model

Use ConstantExtinctionField(0.0) as fallback when no smoke field
is configured, so congestion-aware routing works in clear-air
scenarios."
```

---

### Task 6: Seed `exit_counts` at startup and on flow-spawn, maintain on reroute and removal

**Files:**
- Modify: `pyfds_evac/core/scenario.py:997-1011` (after graph construction — seed)
- Modify: `pyfds_evac/core/scenario.py:1268-1269` (flow spawn path A)
- Modify: `pyfds_evac/core/scenario.py:1314` (flow spawn path B)
- Modify: `pyfds_evac/core/scenario.py:1572-1583` (evaluate_and_reroute call — pass exit_counts)
- Modify: `pyfds_evac/core/scenario.py:1584+` (after switch — update counts)
- Modify: `pyfds_evac/core/scenario.py:1636-1639` (agent removal — decrement)

- [ ] **Step 1: Add a helper to extract terminal exit from `wait_info`**

Add near the top of `scenario.py` (or in a utility section):

```python
def _extract_terminal_exit(
    wait_info: dict,
    graph_nodes: dict,
) -> str | None:
    """Return the exit stage ID from an agent's wait_info, or None."""
    if wait_info.get("mode") != "path":
        return None
    # Try path_choices: walk the chain to find the terminal stage.
    path_choices = wait_info.get("path_choices", {})
    stage = wait_info.get("current_target_stage")
    visited = set()
    while stage and stage in path_choices and stage not in visited:
        visited.add(stage)
        choices = path_choices[stage]
        if choices:
            stage = choices[0][0] if isinstance(choices[0], (list, tuple)) else choices[0]
        else:
            break
    # Check if the terminal stage is an exit node.
    if stage and stage in graph_nodes:
        node = graph_nodes[stage]
        if node.stage_type == "exit":
            return stage
    # Fallback: current_target_stage itself.
    fallback = wait_info.get("current_target_stage")
    if fallback and fallback in graph_nodes and graph_nodes[fallback].stage_type == "exit":
        return fallback
    return None
```

- [ ] **Step 2: Initialise and seed `exit_counts` after graph construction**

In `pyfds_evac/core/scenario.py`, after the `stage_graph = StageGraph.from_scenario(...)` block (line ~1004-1011), add:

```python
        exit_counts: dict[str, int] = {}
        if reroute_config is not None and stage_graph is not None:
            # Initialise all exits to zero.
            for node_id, node in stage_graph.nodes.items():
                if node.stage_type == "exit":
                    exit_counts[node_id] = 0
            # Seed from initial agent assignments.
            for agent_id_init, wi in agent_wait_info.items():
                exit_id = _extract_terminal_exit(wi, stage_graph.nodes)
                if exit_id is not None:
                    exit_counts[exit_id] = exit_counts.get(exit_id, 0) + 1
                    # Pre-create AgentRouteState with current_exit set.
                    if agent_id_init not in agent_route_state:
                        agent_route_state[agent_id_init] = AgentRouteState(
                            current_exit=exit_id,
                            eval_offset_s=compute_eval_offset(
                                agent_id_init,
                                reroute_config.reevaluation_interval_s,
                            ),
                        )
                    else:
                        agent_route_state[agent_id_init].current_exit = exit_id
```

- [ ] **Step 3: Count flow-spawned agents at spawn time**

**Spawn path A** (line ~1268-1269) — after `agent_wait_info[agent_id] = path_state`:

```python
                                    if path_state and stage_graph is not None:
                                        exit_id = _extract_terminal_exit(
                                            path_state, stage_graph.nodes
                                        )
                                        if exit_id is not None:
                                            exit_counts[exit_id] = (
                                                exit_counts.get(exit_id, 0) + 1
                                            )
```

**Spawn path B** (line ~1314) — after `agent_wait_info[agent_id] = {...}`:

```python
                                        if stage_graph is not None:
                                            _spawn_exit = _extract_terminal_exit(
                                                agent_wait_info[agent_id],
                                                stage_graph.nodes,
                                            )
                                            if _spawn_exit is not None:
                                                exit_counts[_spawn_exit] = (
                                                    exit_counts.get(_spawn_exit, 0) + 1
                                                )
```

- [ ] **Step 4: Pass `exit_counts` to routing calls and update counts on reroute**

In the reroute loop, pass `exit_counts` to `rank_routes` (for route cost history collection, line ~1542) and to `evaluate_and_reroute` (line ~1572):

For `rank_routes` call (line ~1542):

```python
                            ranked = rank_routes(
                                stage_graph,
                                source,
                                current_time,
                                current_fed,
                                extinction_sampler,
                                _fed_rate_adapter,
                                reroute_config.cost_config,
                                cached_segments=route_segment_cache,
                                exit_counts=exit_counts,
                            )
```

For `evaluate_and_reroute` call (line ~1572):

```python
                    switch = evaluate_and_reroute(
                        agent_id=agent_id,
                        wait_info=wait_info,
                        route_state=rs,
                        graph=stage_graph,
                        current_time_s=current_time,
                        current_fed=current_fed,
                        extinction_sampler=extinction_sampler,
                        fed_rate_sampler=_fed_rate_adapter,
                        config=reroute_config,
                        cached_segments=route_segment_cache,
                        exit_counts=exit_counts,
                    )
```

After the `if switch is not None:` block, update exit counts:

```python
                    if switch is not None:
                        # Update exit_counts: decrement old, increment new.
                        if switch.old_exit and switch.old_exit in exit_counts:
                            exit_counts[switch.old_exit] = max(
                                0, exit_counts[switch.old_exit] - 1
                            )
                        if switch.new_exit in exit_counts:
                            exit_counts[switch.new_exit] = (
                                exit_counts.get(switch.new_exit, 0) + 1
                            )
```

- [ ] **Step 5: Decrement exit_counts on agent removal**

In the agent cleanup section (line ~1636-1639), when removing dead agents from `agent_route_state`, also decrement `exit_counts`:

```python
                if agent_route_state:
                    for tracked_agent_id in list(agent_route_state.keys()):
                        if tracked_agent_id not in live_agent_ids:
                            removed_state = agent_route_state.pop(
                                tracked_agent_id, None
                            )
                            if (
                                removed_state is not None
                                and removed_state.current_exit
                                and removed_state.current_exit in exit_counts
                            ):
                                exit_counts[removed_state.current_exit] = max(
                                    0,
                                    exit_counts[removed_state.current_exit] - 1,
                                )
```

- [ ] **Step 6: Run full test suite for regressions**

Run: `uv run python -m pytest tests/ -v`
Expected: all existing tests pass

- [ ] **Step 7: Commit**

```bash
git add pyfds_evac/core/scenario.py
git commit -m "feat(routing): seed and maintain exit_counts in scenario loop

Seed from initial agent assignments after graph construction.
Count flow-spawned agents at spawn time. Decrement on agent
removal. Pass exit_counts to rank_routes and evaluate_and_reroute."
```

---

### Task 7: Add queue columns to `route_cost_history` CSV

**Files:**
- Modify: `pyfds_evac/core/scenario.py:1553-1571` (route_cost_history append)

- [ ] **Step 1: Add queue columns to route_cost_history**

In `pyfds_evac/core/scenario.py`, find the route_cost_history append block (line ~1553-1571).  Add three new fields at the end of the dict:

```python
                            for route_rank, rc in enumerate(ranked, start=1):
                                # Resolve exit capacity for this route's exit.
                                _exit_node = stage_graph.nodes.get(rc.exit_id)
                                _exit_cap = (
                                    _exit_node.capacity_agents_per_s
                                    if _exit_node is not None
                                    and _exit_node.capacity_agents_per_s is not None
                                    else reroute_config.cost_config.default_exit_capacity
                                )
                                route_cost_history.append(
                                    {
                                        "time_s": round(float(current_time), 6),
                                        "agent_id": agent_id,
                                        "source": source,
                                        "current_exit": rs.current_exit or "",
                                        "current_fed": float(current_fed),
                                        "route_rank": route_rank,
                                        "exit_id": rc.exit_id,
                                        "path": " > ".join(rc.path),
                                        "path_length_m": float(rc.path_length_m),
                                        "k_ave_route": float(rc.k_ave_route),
                                        "travel_time_s": float(rc.travel_time_s),
                                        "fed_max_route": float(rc.fed_max_route),
                                        "composite_cost": float(rc.composite_cost),
                                        "rejected": bool(rc.rejected),
                                        "rejection_reason": rc.rejection_reason or "",
                                        "queue_time_s": float(rc.queue_time_s),
                                        "exit_count": exit_counts.get(rc.exit_id, 0),
                                        "exit_capacity": float(_exit_cap),
                                    }
                                )
```

- [ ] **Step 2: Run full test suite for regressions**

Run: `uv run python -m pytest tests/ -v`
Expected: all existing tests pass

- [ ] **Step 3: Commit**

```bash
git add pyfds_evac/core/scenario.py
git commit -m "feat(routing): add queue_time_s, exit_count, exit_capacity to route_cost_history"
```

---

### Task 8: Propagate `capacity_agents_per_s` from scenario config into `direct_steering_info`

**Files:**
- Modify: `pyfds_evac/core/simulation_init.py:759-769`

- [ ] **Step 1: Add `capacity_agents_per_s` to the exit info dict**

In `pyfds_evac/core/simulation_init.py`, at line 759-769 where each exit's `direct_steering_info` entry is built, add the new field.  The `exit_data` dict comes from `data["exits"][exit_id]` in the scenario config JSON.

Change:

```python
                direct_steering_info[exit_id] = {
                    "polygon": exit_polygon,
                    "waiting_time": 0.0,
                    "waiting_time_distribution": "constant",
                    "waiting_time_std": 0.0,
                    "speed_factor": 1.0,
                    "ds_stage_id": ds_stage,
                    "enable_throughput_throttling": enable_throttling,
                    "max_throughput": float(exit_data.get("max_throughput", 0.0)),
                    "stage_type": "exit",
                }
```

to:

```python
                direct_steering_info[exit_id] = {
                    "polygon": exit_polygon,
                    "waiting_time": 0.0,
                    "waiting_time_distribution": "constant",
                    "waiting_time_std": 0.0,
                    "speed_factor": 1.0,
                    "ds_stage_id": ds_stage,
                    "enable_throughput_throttling": enable_throttling,
                    "max_throughput": float(exit_data.get("max_throughput", 0.0)),
                    "stage_type": "exit",
                    "capacity_agents_per_s": exit_data.get(
                        "capacity_agents_per_s"
                    ),
                }
```

This ensures that when `StageGraph.from_scenario` reads `info.get("capacity_agents_per_s")` (added in Task 1), it picks up the value from the scenario config JSON.  When `capacity_agents_per_s` is absent from config, the value is `None` and the default from `RouteCostConfig.default_exit_capacity` applies.

- [ ] **Step 2: Run full test suite for regressions**

Run: `uv run python -m pytest tests/ -v`
Expected: all existing tests pass

- [ ] **Step 3: Commit**

```bash
git add pyfds_evac/core/simulation_init.py
git commit -m "feat(routing): propagate capacity_agents_per_s from scenario config to StageNode"
```

---

### Task 9: Update `docs/routing.md`

**Files:**
- Modify: `docs/routing.md`

- [ ] **Step 1: Add congestion-aware routing section**

Add a new section after "### Configuration" (before "## Dynamic rerouting"):

```markdown
### Congestion-aware routing

When `w_queue > 0`, an exit-congestion term is added to the
composite cost:

```
queue_distance = base_speed_m_per_s * N_exit / capacity
composite = path_length * (1 + w_smoke * K_ave)
          + w_fed * FED_max
          + w_queue * queue_distance
```

where:

- `N_exit` is the number of agents currently targeting that exit
- `capacity` is the exit's `capacity_agents_per_s` (default 1.3)
- `base_speed_m_per_s` converts queueing delay (seconds) into
  distance-equivalent cost (metres) so all terms share the same
  unit space

The queue term is applied at route-level ranking (Phase 3) only,
not in Dijkstra edge weights, because it is a per-exit constant
that cannot change which path is selected to a given exit.

Setting `w_queue = 0` disables congestion-aware routing entirely
(backward compatible with existing behaviour).

Exit capacity can be configured per exit in the scenario config:

```json
{
  "exits": {
    "exit_1": {
      "capacity_agents_per_s": 2.5
    }
  }
}
```

When not specified, the default from
`RouteCostConfig.default_exit_capacity` (1.3 agents/s) is used.

This approach is inspired by the game-theoretic exit selection
model of Ehtamo et al. (2010), where each agent minimises
estimated evacuation time (queueing + walking). The staggered
reevaluation schedule provides natural convergence to Nash
equilibrium without explicit iteration.
```

- [ ] **Step 2: Update `RouteCostConfig` example**

In the Configuration section, update the example to include the new fields:

```python
config = RouteCostConfig(
    w_smoke=1.0,                          # smoke cost weight
    w_fed=10.0,                           # FED cost weight
    w_queue=1.0,                          # queueing cost weight (0 disables)
    fed_rejection_threshold=1.0,          # reject if FED_max exceeds
    visibility_extinction_threshold=0.5,  # K threshold for visibility
    sampling_step_m=2.0,                  # ray sample spacing
    base_speed_m_per_s=1.3,               # clear-air walking speed
    alpha=0.706,                          # speed-law coefficient
    beta=-0.057,                          # speed-law coefficient
    min_speed_factor=0.1,                 # speed factor floor
    default_exit_capacity=1.3,            # fallback capacity (agents/s)
)
```

- [ ] **Step 3: Update `RouteCost` data structure table**

Add the new field to the `RouteCost` table:

```markdown
| `queue_time_s`     | `float`             | Estimated queueing time at exit |
```

- [ ] **Step 4: Add Ehtamo reference**

In the References section at the bottom:

```markdown
- Ehtamo, H., Heliövaara, S., Korhonen, T. & Hostikka, S. (2010).
  Game theoretic best-response dynamics for evacuees' exit selection.
  *Advances in Complex Systems*, 13(1), 113–134.
```

- [ ] **Step 5: Commit**

```bash
git add docs/routing.md
git commit -m "docs(routing): document congestion-aware routing"
```

---

### Task 10: Lint and format

**Files:**
- All modified files

- [ ] **Step 1: Run ruff lint**

Run: `uv run ruff check pyfds_evac/core/route_graph.py pyfds_evac/core/scenario.py tests/test_route_graph.py`
Expected: no errors.  If errors, fix them.

- [ ] **Step 2: Run ruff format**

Run: `uv run ruff format pyfds_evac/core/route_graph.py pyfds_evac/core/scenario.py tests/test_route_graph.py`

- [ ] **Step 3: Run full test suite**

Run: `uv run python -m pytest tests/ -v`
Expected: all pass

- [ ] **Step 4: Commit if any formatting changes**

```bash
git add -u
git commit -m "style: apply ruff format"
```

---

## Summary of verification coverage

| Spec verification | Task |
|-------------------|------|
| 1. Diamond graph — congestion shifts exit choice | Task 3: `TestRankRoutesWithCongestion::test_congestion_shifts_best_exit` |
| 2. Backward compat — `w_queue=0` | Task 3: `TestQueueCostTerm::test_w_queue_zero_disables_queue` |
| 3. Capacity effect | Task 3: `TestQueueCostTerm::test_custom_capacity_reduces_penalty` |
| 4. Integration (smoke) | Validated by running demo scenario after all tasks |
| 5. Integration (clear-air) | Validated by running demo scenario without smoke after Task 5 |
| StageNode capacity | Task 1: `TestStageNodeCapacity` |
| Node capacity overrides default | Task 3: `TestQueueCostTerm::test_node_capacity_overrides_default` |
| Distance-equivalent conversion | Task 3: `TestQueueCostTerm::test_queue_cost_uses_distance_equivalent` |
| evaluate_and_reroute congestion | Task 4: `TestEvaluateAndRerouteWithCongestion` |
