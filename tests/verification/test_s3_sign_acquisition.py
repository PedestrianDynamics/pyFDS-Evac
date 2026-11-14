"""S3 -- sign acquisition inside a real run (wiring level).

One 20 x 8 m room, one exit on the east wall, one authored omni-directional
sign at (19.125, 5.125) with c = 3. Agents spawn 16.6-18.7 m from the sign, so
a sign read at R = c / K is out of reach at spawn exactly when R is small:

- ``clear``  K = 0   -> R = 30 m (the cap): every agent knows the exit at t = 0;
- ``smoky``  K = 0.5 -> R = 6 m: the exit is learnt by *sight* later, at the
  first reevaluation at which the agent's cell is within R of the sign;
- ``control`` no visibility model: nothing is learnt by sight;
- ``wrong_way`` the sign faces east (alpha = 90), agents come from the west:
  the half-plane hides it, so nothing is learnt by sight;
- ``full`` familiarity "full" at K = 0.5: every exit is known at t = 0 by the
  familiarity draw, whatever the smoke.

Acquisition window for the smoky arm, with the agent's true position recorded
by wrapping ``jps.Simulation.iterate``: the agent was outside R at the previous
reevaluation (``Delta`` = 1 s earlier, at most ``v0 * Delta`` ago) and its cell
centre is within R of the sign, so ``R - v0*Delta - delta <= d <= R + delta``,
``delta`` = half a 0.25 m cell diagonal = 0.177 m.

Not asserted (not model properties here): that agents wait for the sign, or
that smoky egress exceeds clear egress. With the default
``no_known_exit = default_route`` an agent that knows no exit walks to the
nearest one anyway, and visibility does not slow walking.

Also covers two run-level residuals of the cognitive-map verification (#23):
discovery agents know the exits they see at t = 0, and the same seed gives the
same exit multiset (aggregate only).
"""

from __future__ import annotations

import math

import jupedsim as jps
import pytest
from harness import ROOM_EXIT, ROOM_SIGN_XY, RoomSpec, room_with_sign
from shapely import wkt as shapely_wkt

from pyfds_evac.core.route_graph import RerouteConfig, RouteCostConfig
from pyfds_evac.core.scenario import run_scenario
from pyfds_evac.core.visibility import VisibilityModel, extract_sign_descriptors

pytest.importorskip("fdsvismap")

C = 3.0
K_SMOKY = 0.5
R_SMOKY = C / K_SMOKY  # 6 m
V0 = 1.3
REEVAL_S = 1.0
CELL_M = 0.25
CELL_OFFSET_M = CELL_M * math.sqrt(2) / 2  # 0.177 m
NUM_AGENTS = 4
SPAWN_MIN_DISTANCE_M = 16.0  # every spawn point is farther than this from the sign


@pytest.fixture
def positions(monkeypatch):
    """Each agent's true (time, x, y), recorded before every JuPedSim step."""
    rows: dict[int, list[tuple[float, float, float]]] = {}

    class RecordingSimulation(jps.Simulation):
        def iterate(self, count: int = 1):
            t = self.elapsed_time()
            for agent in self.agents():
                pos = agent.position
                rows.setdefault(int(agent.id), []).append((t, pos[0], pos[1]))
            return super().iterate(count)

    monkeypatch.setattr(jps, "Simulation", RecordingSimulation)
    return rows


def _run(k=None, **spec_kwargs):
    """Run the room; ``k=None`` leaves the visibility model out (control arm)."""
    spec = RoomSpec(**spec_kwargs)
    scenario = room_with_sign(spec)
    vis = None
    if k is not None:
        walkable = shapely_wkt.loads(scenario.walkable_area_wkt)
        vis = VisibilityModel.clear_air(
            walkable,
            extract_sign_descriptors(scenario.raw),
            cell_size_m=CELL_M,
            extinction_per_m=k,
        )
    return run_scenario(
        scenario,
        seed=spec.seed,
        reroute_config=RerouteConfig(
            reevaluation_interval_s=REEVAL_S, cost_config=RouteCostConfig()
        ),
        vis_model=vis,
        collect_cognitive_map_history=True,
    )


def _exit_rows(result):
    return [r for r in result.knowledge_history if r["exit_id"] == ROOM_EXIT]


def _distance_to_sign(track, time_s):
    t, x, y = min(track, key=lambda r: abs(r[0] - time_s))
    assert abs(t - time_s) < 1e-6, "no recorded step at the acquisition time"
    return math.hypot(x - ROOM_SIGN_XY[0], y - ROOM_SIGN_XY[1])


def _assert_all_evacuated(result):
    assert result.metrics["agents_evacuated"] == NUM_AGENTS
    assert result.metrics["agents_remaining"] == 0


def test_control_without_visibility_learns_nothing_by_sight():
    result = _run(k=None)
    try:
        assert not [r for r in result.knowledge_history if r["how"] == "sight"]
        _assert_all_evacuated(result)
    finally:
        result.cleanup()


def test_clear_air_agents_know_the_exit_at_spawn_by_sight():
    result = _run(k=0.0)
    try:
        rows = _exit_rows(result)
        assert len(rows) == NUM_AGENTS
        assert len({r["agent_id"] for r in rows}) == NUM_AGENTS
        assert all(r["time_s"] == 0.0 and r["how"] == "sight" for r in rows)
        _assert_all_evacuated(result)
    finally:
        result.cleanup()


def test_smoky_agents_acquire_the_sign_at_the_reading_distance(positions):
    result = _run(k=K_SMOKY)
    try:
        rows = _exit_rows(result)
        assert len(rows) == NUM_AGENTS
        # Discriminating inequality: spawn is beyond R, so t = 0 cannot see it.
        assert SPAWN_MIN_DISTANCE_M > R_SMOKY + V0 * REEVAL_S + CELL_OFFSET_M
        low = R_SMOKY - V0 * REEVAL_S - CELL_OFFSET_M
        high = R_SMOKY + CELL_OFFSET_M
        for row in rows:
            assert row["how"] == "sight"
            assert row["time_s"] > 0.0
            d = _distance_to_sign(positions[row["agent_id"]], row["time_s"])
            assert low <= d <= high, (row, d)
        _assert_all_evacuated(result)
    finally:
        result.cleanup()


def test_wrong_way_sign_is_never_read(positions):
    """A sign facing east, approached from the west, is hidden at any distance."""
    result = _run(k=K_SMOKY, sign_alpha=90.0)
    try:
        assert not [r for r in result.knowledge_history if r["how"] == "sight"]
        _assert_all_evacuated(result)
    finally:
        result.cleanup()


def test_full_familiarity_knows_the_exit_at_t0_by_the_draw():
    result = _run(k=K_SMOKY, familiarity="full")
    try:
        rows = _exit_rows(result)
        assert len(rows) == NUM_AGENTS
        assert all(r["time_s"] == 0.0 and r["how"] == "familiarity_draw" for r in rows)
        _assert_all_evacuated(result)
    finally:
        result.cleanup()


def test_same_seed_gives_the_same_exit_and_knowledge_multisets():
    """Aggregate only: per-agent trajectories are not reproducible."""
    first, second = _run(k=K_SMOKY), _run(k=K_SMOKY)
    try:
        assert sorted(r["exit_id"] for r in first.exit_history) == sorted(
            r["exit_id"] for r in second.exit_history
        )
        assert sorted(r["how"] for r in first.knowledge_history) == sorted(
            r["how"] for r in second.knowledge_history
        )
    finally:
        first.cleanup()
        second.cleanup()
