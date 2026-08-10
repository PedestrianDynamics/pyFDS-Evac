# Stage Graph, Crossings and Signs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let crossings participate in cost-driven routing without a hand-authored journey, make every routable stage smoke-gated by a sign, and measure position-aware distances along the walkable area instead of straight lines.

**Status (2026-08-05):** Tasks 1, 2 and 4 land on `fix/per-agent-spawn-origin`. Task 3 is deferred to a follow-up PR — see the note on that task.

**Architecture:** Three independent changes to `pyfds_evac/core`. `StageGraph.from_scenario` gains a stage-type-agnostic auto-wiring path and retains its `jps.RoutingEngine` on the graph object; `visibility.extract_sign_descriptors` synthesises a default sign for every exit and crossing that lacks one; `route_graph._position_aware_length` asks that retained routing engine for walkable distances, falling back to Euclidean when it is absent.

**Tech Stack:** Python 3.12, shapely, jupedsim (`jps.RoutingEngine`), fdsvismap, pytest, ruff.

## Global Constraints

- Repo root: `/Users/chraibi/workspace/PedestrianDynamics/Fire/fds_visibility/fds-evac`. Branch: `fix/per-agent-spawn-origin`.
- Use the project venv for everything: `.venv/bin/python`, `.venv/bin/pytest`, `.venv/bin/ruff`. Never system Python.
- TDD: write the failing test, watch it fail, implement minimally, watch it pass, commit.
- Before every commit: `.venv/bin/ruff format <files>` then `.venv/bin/ruff check <files>` must pass.
- `tests/verification/test_fed_verif.py::test_a2_3_o2_gate_finite_just_below_threshold` **fails on clean `main`** and is unrelated to this work. A full-suite run is green when that is the only failure.
- Never use `--no-verify` when committing. No AI-attribution lines or `Claude-Session:` trailers in commit messages.
- Existing behaviour must not change when `transitions` is non-empty, or when no walkable polygon is supplied.
- Style: guard clauses over nesting, max two levels of indentation per function, no unrelated refactoring.

---

### Task 1: Auto-wire all stage types when no transitions exist

Today `StageGraph.from_scenario` auto-connects distributions to exits only while **every** node is a distribution or an exit. Adding one crossing makes the guard false and the graph ends up with zero edges, so routing dies silently.

**Files:**
- Modify: `pyfds_evac/core/route_graph.py:128-143` (the auto-connect block)
- Test: `tests/test_route_graph.py` (append a new class at end of file)

**Interfaces:**
- Consumes: `StageGraph.from_scenario(direct_steering_info, transitions, distributions=None, walkable_polygon=None)`, `StageNode.stage_type` (one of `"distribution"`, `"checkpoint"`, `"exit"`), `_make_edge(src_node, tgt_node, routing_engine) -> StageEdge`
- Produces: no signature change. After this task, a graph built with crossings and `transitions=[]` has edges from every distribution and every crossing to every crossing and every exit.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_route_graph.py`:

```python
class TestAutoWiringWithCrossings:
    """A graph with no transitions must wire itself whatever stages exist.

    Auto-wiring previously bailed out as soon as a non-exit, non-distribution
    node appeared, leaving a graph with nodes and no edges -- routing silently
    dead for anyone who drew a crossing but no journey.
    """

    @staticmethod
    def _stages():
        return {
            "e0": {"polygon": _box(0, 0), "stage_type": "exit"},
            "e1": {"polygon": _box(30, 0), "stage_type": "exit"},
            "c0": {"polygon": _box(15, 0), "stage_type": "checkpoint"},
        }

    def test_crossing_does_not_kill_auto_wiring(self):
        graph = StageGraph.from_scenario(
            self._stages(),
            [],
            distributions={"d0": {"polygon": _box(5, 0)}},
        )
        assert sum(len(e) for e in graph.edges.values()) > 0

    def test_distribution_reaches_every_exit_and_crossing(self):
        graph = StageGraph.from_scenario(
            self._stages(),
            [],
            distributions={"d0": {"polygon": _box(5, 0)}},
        )
        targets = {edge.target for edge in graph.edges.get("d0", [])}
        assert targets == {"e0", "e1", "c0"}

    def test_crossing_reaches_exits_but_exits_are_terminal(self):
        graph = StageGraph.from_scenario(
            self._stages(),
            [],
            distributions={"d0": {"polygon": _box(5, 0)}},
        )
        assert {edge.target for edge in graph.edges.get("c0", [])} == {"e0", "e1"}
        assert graph.edges.get("e0", []) == []

    def test_no_edge_points_back_at_a_distribution(self):
        graph = StageGraph.from_scenario(
            self._stages(),
            [],
            distributions={"d0": {"polygon": _box(5, 0)}},
        )
        all_targets = {e.target for edges in graph.edges.values() for e in edges}
        assert "d0" not in all_targets

    def test_explicit_transitions_still_win(self):
        """With transitions given, only those edges exist -- unchanged behaviour."""
        graph = StageGraph.from_scenario(
            self._stages(),
            [{"from": "c0", "to": "e0"}],
            distributions={"d0": {"polygon": _box(5, 0)}},
        )
        assert sum(len(e) for e in graph.edges.values()) == 1
        assert graph.edges["c0"][0].target == "e0"
```

- [ ] **Step 1b: Write the smoke-detour test**

This is the point of the change: a crossing must be inert in clear air and
attractive once smoke sits on the direct route. Append to the same class:

```python
    def test_crossing_is_inert_in_clear_air(self):
        """Direct spawn-to-exit is cheapest with no smoke, so no detour."""
        graph = StageGraph.from_scenario(
            {
                "e0": {"polygon": _box(20, 0), "stage_type": "exit"},
                "c0": {"polygon": _box(10, 10), "stage_type": "checkpoint"},
            },
            [],
            distributions={"d0": {"polygon": _box(0, 0)}},
        )
        ranked = rank_routes(
            graph,
            "d0",
            0.0,
            0.0,
            ConstantExtinctionField(0.0),
            None,
            RouteCostConfig(base_speed_m_per_s=1.0, w_smoke=1.0),
        )
        assert ranked[0].path == ["d0", "e0"]

    def test_smoke_on_the_direct_route_pushes_agents_through_the_crossing(self):
        class SmokeOnTheDirectLine:
            """Dense smoke in a band along y = 0, clear everywhere else."""

            def sample_extinction(self, time_s, x, y):
                del time_s
                return 5.0 if (4.0 < x < 16.0 and abs(y) < 2.0) else 0.0

        graph = StageGraph.from_scenario(
            {
                "e0": {"polygon": _box(20, 0), "stage_type": "exit"},
                "c0": {"polygon": _box(10, 10), "stage_type": "checkpoint"},
            },
            [],
            distributions={"d0": {"polygon": _box(0, 0)}},
        )
        ranked = rank_routes(
            graph,
            "d0",
            0.0,
            0.0,
            SmokeOnTheDirectLine(),
            None,
            RouteCostConfig(base_speed_m_per_s=1.0, w_smoke=1.0),
        )
        assert ranked[0].path == ["d0", "c0", "e0"]
```

Both need `rank_routes`, `RouteCostConfig` and `ConstantExtinctionField`, which
`tests/test_route_graph.py` already imports.

- [ ] **Step 2: Run the tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/test_route_graph.py::TestAutoWiringWithCrossings -v
```

Expected: `test_crossing_does_not_kill_auto_wiring`, `test_distribution_reaches_every_exit_and_crossing` and `test_crossing_reaches_exits_but_exits_are_terminal` FAIL (0 edges). `test_no_edge_points_back_at_a_distribution` and `test_explicit_transitions_still_win` already pass — that is expected and correct; they are regression guards.

- [ ] **Step 3: Replace the auto-connect block**

In `pyfds_evac/core/route_graph.py`, replace the whole block that begins with the comment `# When no transitions are defined and the graph contains only` and ends with the inner `graph.edges.setdefault(src_id, []).append(edge)` loop, with:

```python
        # With no transitions the author has drawn stages but not routes, so
        # wire the graph by stage type and let cost decide: spawn areas and
        # crossings reach every crossing and every exit, exits are terminal,
        # and nothing points back at a spawn area.
        if not transitions:
            targets = [
                nid
                for nid, n in graph.nodes.items()
                if n.stage_type in ("checkpoint", "exit")
            ]
            sources = [
                nid
                for nid, n in graph.nodes.items()
                if n.stage_type in ("distribution", "checkpoint")
            ]
            for src_id in sources:
                for tgt_id in targets:
                    if src_id == tgt_id:
                        continue
                    edge = _make_edge(
                        graph.nodes[src_id], graph.nodes[tgt_id], routing_engine
                    )
                    graph.edges.setdefault(src_id, []).append(edge)
```

- [ ] **Step 4: Run the new tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/test_route_graph.py::TestAutoWiringWithCrossings -v
```

Expected: 7 passed.

- [ ] **Step 5: Run the full suite for regressions**

```bash
.venv/bin/python -m pytest tests/ -q 2>&1 | tail -5
```

Expected: only `test_a2_3_o2_gate_finite_just_below_threshold` fails. If any other test fails, stop and report — most likely a scenario that relied on the old bipartite-only wiring.

- [ ] **Step 6: Lint and commit**

```bash
.venv/bin/ruff format pyfds_evac/core/route_graph.py tests/test_route_graph.py
.venv/bin/ruff check pyfds_evac/core/route_graph.py tests/test_route_graph.py
git add pyfds_evac/core/route_graph.py tests/test_route_graph.py
git commit -m "feat(routing): auto-wire crossings when no journey is defined

Auto-wiring only fired while every node was a distribution or an exit, so
adding a single crossing without transitions produced a graph with nodes
and no edges -- rerouting silently dead for anyone who drew a crossing but
no journey.

Wire by stage type instead: spawn areas and crossings reach every crossing
and every exit, exits stay terminal, nothing points back at a spawn area.
Explicit transitions remain authoritative and skip this path entirely."
```

---

### Task 2: Synthesise a sign for every exit and crossing

`node_is_visible` returns `True` for any node without a sign, so an unsigned stage is permanently known regardless of smoke — silently exempt from the mechanism the model is about. Give every exit and crossing a default sign at its centroid, omni-directional.

**Files:**
- Modify: `pyfds_evac/core/visibility.py:14-22` (`extract_sign_descriptors`)
- Modify: `pyfds_evac/core/visibility.py:36-43` (`_build_vismap`, the `alpha=` argument)
- Test: `tests/test_visibility.py` (append a new class at end of file)

**Interfaces:**
- Consumes: `raw_config` dict with optional `"exits"`, `"checkpoints"`, `"waypoints"` sections, each `{node_id: {"coordinates": [[x, y], ...], "sign": {...}?}}`
- Produces: `extract_sign_descriptors(raw_config) -> dict[str, dict]` now returns an entry for **every** exit and crossing, each `{"x": float, "y": float, "alpha": float | None, "c": float}`. `alpha` may be `None`, and `_build_vismap` passes `None` through to `fdsvismap.VisMap.set_waypoint`, which treats it as omni-directional.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_visibility.py`:

```python
class TestSignSynthesis:
    """Every routable stage carries a sign, so nothing opts out of smoke gating.

    A node with no sign descriptor reports visible unconditionally, which made
    it permanently known however dense the smoke.  Synthesising a default sign
    at the node centroid closes that hole.
    """

    @staticmethod
    def _square(x, y):
        return [[x, y], [x + 2, y], [x + 2, y + 2], [x, y + 2], [x, y]]

    def _config(self):
        return {
            "exits": {
                "e0": {"coordinates": self._square(0, 0)},
                "e1": {
                    "coordinates": self._square(10, 0),
                    "sign": {"x": 11.0, "y": 0.5, "alpha": 90, "c": 8},
                },
            },
            "checkpoints": {"c0": {"coordinates": self._square(5, 0)}},
            "distributions": {"d0": {"coordinates": self._square(20, 0)}},
        }

    def test_every_exit_and_crossing_gets_a_descriptor(self):
        signs = extract_sign_descriptors(self._config())
        assert set(signs) == {"e0", "e1", "c0"}

    def test_synthesised_sign_sits_at_the_node_centroid(self):
        signs = extract_sign_descriptors(self._config())
        assert signs["e0"]["x"] == pytest.approx(1.0)
        assert signs["e0"]["y"] == pytest.approx(1.0)

    def test_synthesised_sign_is_omnidirectional_and_reflective(self):
        signs = extract_sign_descriptors(self._config())
        assert signs["c0"]["alpha"] is None
        assert signs["c0"]["c"] == 3

    def test_authored_sign_is_left_alone(self):
        signs = extract_sign_descriptors(self._config())
        assert signs["e1"] == {"x": 11.0, "y": 0.5, "alpha": 90, "c": 8}

    def test_distributions_get_no_sign(self):
        """Spawn areas are sources, never navigation targets."""
        signs = extract_sign_descriptors(self._config())
        assert "d0" not in signs
```

Add `import pytest` to the file's imports if it is not already there.

- [ ] **Step 2: Run the tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/test_visibility.py::TestSignSynthesis -v
```

Expected: the first three FAIL — `extract_sign_descriptors` currently returns only `{"e1": ...}`. `test_authored_sign_is_left_alone` and `test_distributions_get_no_sign` already pass as regression guards. You will also need `extract_sign_descriptors` in the import line at the top of the test file; add it to the existing `from pyfds_evac.core.visibility import ...`.

- [ ] **Step 3: Implement synthesis**

Replace `extract_sign_descriptors` in `pyfds_evac/core/visibility.py` with:

```python
def _default_sign(entry: dict) -> dict | None:
    """A reflective, omni-directional sign at the node's centroid.

    alpha is left None on purpose.  fdsvismap reads alpha as a half-plane of
    readability, so a guessed bearing silently blanks the sign for every agent
    on the wrong side however clear the air, whereas None means omni-directional
    and merely omits the orientation effect.
    """
    coords = entry.get("coordinates")
    if not coords:
        return None
    from shapely.geometry import Polygon

    centroid = Polygon(coords).centroid
    return {"x": float(centroid.x), "y": float(centroid.y), "alpha": None, "c": 3}


def extract_sign_descriptors(raw_config: dict) -> dict[str, dict]:
    """Return {node_id: {x, y, alpha, c}} for every exit, crossing and waypoint.

    Nodes with an authored 'sign' keep it verbatim; the rest get a default so
    that no routable stage escapes smoke-dependent legibility.
    """
    descriptors: dict[str, dict] = {}
    for section in ("exits", "checkpoints", "waypoints"):
        for node_id, data in raw_config.get(section, {}).items():
            sign = data.get("sign") or _default_sign(data)
            if sign is not None:
                descriptors[node_id] = sign
    return descriptors
```

- [ ] **Step 4: Let `alpha=None` reach fdsvismap**

In `_build_vismap`, replace the `set_waypoint` call with:

```python
    for wp_id, (node_id, sign) in enumerate(sign_descriptors.items()):
        alpha = sign.get("alpha")
        vis.set_waypoint(
            wp_id,
            float(sign["x"]),
            float(sign["y"]),
            c=float(sign.get("c", 3)),
            # None is meaningful: fdsvismap reads it as omni-directional.
            alpha=None if alpha is None else float(alpha),
        )
```

- [ ] **Step 4b: Test that `alpha=None` survives the trip to fdsvismap**

Append to `TestSignSynthesis`:

```python
    def test_none_alpha_is_passed_through_not_coerced(self):
        """fdsvismap reads alpha=None as omni-directional; float(None) raises."""
        from unittest.mock import MagicMock, patch

        from pyfds_evac.core.visibility import _build_vismap

        fake = MagicMock()
        fake.fds_time_points.max.return_value = 10.0
        with patch("fdsvismap.VisMap", return_value=fake):
            _build_vismap(
                "unused",
                {"c0": {"x": 1.0, "y": 2.0, "alpha": None, "c": 3}},
                time_step_s=5.0,
                slice_height_m=2.0,
            )
        assert fake.set_waypoint.call_args.kwargs["alpha"] is None
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/test_visibility.py -v
```

Expected: all pass, including the pre-existing `TestVisibilityModelCache`.

- [ ] **Step 6: Run the full suite for regressions**

```bash
.venv/bin/python -m pytest tests/ -q 2>&1 | tail -5
```

Expected: only the known `test_a2_3_o2_gate_finite_just_below_threshold` failure. Watch `tests/test_familiarity_routing.py` and `tests/verification/test_cognitive_map_verif.py` in particular — discovery agents now see gated signs on nodes that were previously unconditionally visible.

- [ ] **Step 7: Lint and commit**

```bash
.venv/bin/ruff format pyfds_evac/core/visibility.py tests/test_visibility.py
.venv/bin/ruff check pyfds_evac/core/visibility.py tests/test_visibility.py
git add pyfds_evac/core/visibility.py tests/test_visibility.py
git commit -m "feat(visibility): give every exit and crossing a sign

node_is_visible returns True for a node with no sign descriptor, so an
unsigned stage was permanently known however dense the smoke -- silently
exempt from the mechanism the model exists to represent.

Synthesise a default sign at the node centroid for every exit, crossing
and waypoint that lacks one: reflective (c=3) and omni-directional
(alpha=None), since fdsvismap reads alpha as a half-plane and a guessed
bearing would blank the sign for every agent on the wrong side."
```

---

### Task 3: Measure position-aware distance along the walkable area

> **DEFERRED to a follow-up PR (decided 2026-08-05).** This task edits
> `_position_aware_length`, which exists only on `fix/route-cost-first-segment-exposure`
> (PR #44, unmerged). On `main` and on this branch the logic is still inline
> inside `evaluate_route`, with no `first_share` and no `first_length_m`.
> Run this task on a branch cut from #44 once it merges. Tasks 1, 2 and 4 are
> independent of it and land on this branch.

`_position_aware_length` uses `math.hypot` for the agent's remaining distance and its backtrack, so both cut corners. Measured on an L-corridor, the remaining distance is understated by 17 % and the straight segment leaves the walkable area. The base path already respects walls; only the position correction does not.

**Files:**
- Modify: `pyfds_evac/core/route_graph.py` — `StageGraph` dataclass fields, `from_scenario` (store the engine), `_position_aware_length`
- Test: `tests/test_route_graph.py` (append a new class at end of file)

**Interfaces:**
- Consumes: `_polyline_length(waypoints) -> float`, `jps.RoutingEngine.compute_waypoints(from_xy, to_xy) -> iterable[tuple[float, float]]`
- Produces: `StageGraph` gains a field `routing_engine: object | None = None`, set by `from_scenario` when a walkable polygon is supplied. New helper `_walkable_distance(routing_engine, from_xy, to_xy) -> float` returning the walkable path length, or the Euclidean distance when the engine is absent or the query is unusable.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_route_graph.py`:

```python
class TestWalkableRemainingDistance:
    """Position-aware distance must follow the walkable area, not cut corners.

    The graph's own edges already route around walls; measuring the agent's
    remaining distance with a straight line contradicted that and understated
    it, most severely in the corridor layouts position-aware routing exists to
    fix.
    """

    @staticmethod
    def _l_corridor():
        """An L: a horizontal leg and a vertical leg meeting at the far end."""
        from shapely.ops import unary_union
        from shapely.geometry import box as _shp_box

        return unary_union([_shp_box(0, 0, 20, 3), _shp_box(17, 0, 20, 20)])

    def _graph(self):
        stages = {
            "j": {"polygon": _box(18, 2), "stage_type": "checkpoint"},
            "e0": {"polygon": _box(18, 18), "stage_type": "exit"},
        }
        return StageGraph.from_scenario(
            stages,
            [{"from": "j", "to": "e0"}],
            walkable_polygon=self._l_corridor(),
        )

    def test_routing_engine_is_retained_on_the_graph(self):
        assert self._graph().routing_engine is not None

    def test_remaining_distance_follows_the_corridor(self):
        """An agent in the horizontal leg must walk to the corner, not through it."""
        import math

        graph = self._graph()
        agent = (5.0, 1.5)
        effective, share = _position_aware_length(
            graph, ["j", "e0"], agent, "e0", path_length=16.0, first_length_m=16.0
        )
        straight = math.hypot(agent[0] - 18.0, agent[1] - 18.0)
        assert effective > straight

    def test_euclidean_fallback_without_a_routing_engine(self):
        import math

        graph = StageGraph.from_scenario(
            {
                "j": {"polygon": _box(18, 2), "stage_type": "checkpoint"},
                "e0": {"polygon": _box(18, 18), "stage_type": "exit"},
            },
            [{"from": "j", "to": "e0"}],
        )
        agent = (5.0, 1.5)
        effective, _ = _position_aware_length(
            graph, ["j", "e0"], agent, "e0", path_length=16.0, first_length_m=16.0
        )
        straight = math.hypot(agent[0] - 18.0, agent[1] - 18.0)
        assert effective == pytest.approx(16.0 - 16.0 + straight)
```

Add `_position_aware_length` to the existing `from pyfds_evac.core.route_graph import ...` line at the top of the test file.

- [ ] **Step 2: Run the tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/test_route_graph.py::TestWalkableRemainingDistance -v
```

Expected: `test_routing_engine_is_retained_on_the_graph` FAILS with `AttributeError: 'StageGraph' object has no attribute 'routing_engine'`; `test_remaining_distance_follows_the_corridor` FAILS because the Euclidean value equals `straight` rather than exceeding it. `test_euclidean_fallback_without_a_routing_engine` already passes.

- [ ] **Step 3: Retain the routing engine on the graph**

In the `StageGraph` dataclass, add the field after `edges`:

```python
    nodes: dict[str, StageNode] = field(default_factory=dict)
    edges: dict[str, list[StageEdge]] = field(default_factory=dict)
    # Kept so route evaluation can measure distances from an agent's actual
    # position along the walkable area, the same way edges are measured.
    routing_engine: object | None = None
```

In `from_scenario`, `graph = cls()` is created before the routing engine. Leave
that line alone and add one line directly after the `if walkable_polygon is not
None:` block that assigns `routing_engine`, so the block reads:

```python
        routing_engine = None
        if walkable_polygon is not None:
            import jupedsim as jps  # lazy import; jupedsim not always required

            routing_engine = jps.RoutingEngine(walkable_polygon)
        graph.routing_engine = routing_engine
```

- [ ] **Step 4: Add the walkable-distance helper**

Add next to `_polyline_length` in `pyfds_evac/core/route_graph.py`:

```python
def _walkable_distance(routing_engine, from_xy, to_xy) -> float:
    """Path length through the walkable area, or straight-line if unavailable.

    A wrong distance only degrades ranking, so a failed or degenerate query
    falls back rather than ending the run.
    """
    if routing_engine is None:
        return _euclidean(from_xy[0], from_xy[1], to_xy[0], to_xy[1])
    try:
        waypoints = list(routing_engine.compute_waypoints(from_xy, to_xy))
    except Exception:
        return _euclidean(from_xy[0], from_xy[1], to_xy[0], to_xy[1])
    if len(waypoints) < 2:
        return _euclidean(from_xy[0], from_xy[1], to_xy[0], to_xy[1])
    return _polyline_length(waypoints)
```

- [ ] **Step 5: Use it in `_position_aware_length`**

In `_position_aware_length`, replace the two `math.hypot` calls. The `remaining` line becomes:

```python
        remaining = _walkable_distance(
            graph.routing_engine, (px, py), (next_node.centroid_x, next_node.centroid_y)
        )
```

and the `backtrack` line becomes:

```python
        backtrack = _walkable_distance(
            graph.routing_engine,
            (px, py),
            (first_node.centroid_x, first_node.centroid_y),
        )
```

Leave the surrounding logic — the `first_length_m <= 1e-9` guard, the `share` clamp, and the returned tuple — exactly as they are.

- [ ] **Step 6: Run the tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/test_route_graph.py::TestWalkableRemainingDistance -v
```

Expected: 3 passed.

- [ ] **Step 7: Run the full suite for regressions**

```bash
.venv/bin/python -m pytest tests/ -q 2>&1 | tail -5
```

Expected: only the known `test_a2_3_o2_gate_finite_just_below_threshold` failure. `TestPositionAwareRouting` builds graphs without a walkable polygon, so it takes the Euclidean fallback and must be unchanged. If `tests/verification/test_s4_tjunction_reroute.py` shifts, that is the real behaviour change — mid-leg agents now see truer, longer distances in corridors. Report the new numbers rather than adjusting the test to fit.

- [ ] **Step 8: Lint and commit**

```bash
.venv/bin/ruff format pyfds_evac/core/route_graph.py tests/test_route_graph.py
.venv/bin/ruff check pyfds_evac/core/route_graph.py tests/test_route_graph.py
git add pyfds_evac/core/route_graph.py tests/test_route_graph.py
git commit -m "fix(routing): measure position-aware distance along the walkable area

The graph's edges route around walls, but the position correction layered
on top measured the agent's remaining distance and its backtrack with
math.hypot. On an L-corridor that understated the remaining distance by
17 percent and the straight segment left the walkable area entirely.

Retain the RoutingEngine on StageGraph and ask it for both distances,
falling back to Euclidean where no engine exists or the query is
degenerate. Measured at roughly 1 us per query, so the cost is negligible."
```

---

### Task 4: Update the docs the changes invalidate

**Files:**
- Modify: `docs/routing.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: behaviour established in Tasks 1-3.
- Produces: no code. Documentation consistent with shipped behaviour.

- [ ] **Step 1: Check what the changes contradict**

```bash
rg -n "nearest exit|auto-connect|distribution.*exit|no transitions" docs/routing.md README.md
rg -n "sign|visible|checkpoint" docs/routing.md README.md
```

- [ ] **Step 2: Record the three behaviour changes**

In `docs/routing.md`, in or near the section describing how the stage graph is built, add:

```markdown
### Graph construction without a journey

When a scenario defines no `transitions`, the stage graph wires itself by
stage type: spawn areas and crossings reach every crossing and every exit,
exits are terminal, and nothing points back at a spawn area. Crossings
therefore participate in cost-driven routing without a hand-authored journey.
In clear air the direct spawn-to-exit edge is cheapest, so agents take the
nearest exit and crossings sit inert; smoke can make a route through a
crossing cheaper.

Explicit `transitions` remain authoritative and skip this path entirely.
```

`docs/rerouting-oscillation-notes.md` is **not** edited in this task: the
walkable-distance change it would describe is Task 3, which is deferred.

- [ ] **Step 3: Verify no stale claims remain**

```bash
rg -n "only.*distributions and exits|always visible|no sign" docs/ README.md
```

Fix anything that now contradicts the code. In particular, any statement that a node without a sign is always visible is no longer true — every exit and crossing now gets a synthesised sign.

- [ ] **Step 4: Commit**

```bash
git add docs/routing.md README.md
git commit -m "docs: record stage-graph auto-wiring and default signs"
```

---

## Verification

After all four tasks:

```bash
.venv/bin/ruff format --check pyfds_evac tests
.venv/bin/ruff check pyfds_evac tests
.venv/bin/python -m pytest tests/ -q 2>&1 | tail -5
```

Green means one failure only: `test_a2_3_o2_gate_finite_just_below_threshold`.

## Deliberately not in this plan

- **The Station asset.** `assets/station/build_geometry.py` is untracked and still emits hand-authored journeys, transitions and checkpoints. Rebuilding it on top of these changes — distributions, exits and two documented crossings, no journeys — is separate work with its own validation against NCSTAR Table 6-2.
- **The Station throughput gap.** 98/420 evacuated against NIST's 420 in 188 s is unexplained. Diagnosing it needs the corrected graph first.
- **Internal walls in the Station WKT**, which `wkt_to_fds.py` would carry into the FDS deck and hence into fdsvismap's occlusions.
