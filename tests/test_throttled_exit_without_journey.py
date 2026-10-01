"""Agents without a journey whose nearest exit is throttled (issue #434).

In a deck with journeys, a distribution without a journey sends each agent to
its nearest exit. A throttled exit is a JuPedSim direct-steering stage, which
neither steers agents nor removes them, so these agents are steered to the
throttled exit by the runtime and removed there under its cap. Before the fix
they stood at their spawn points until the time limit.

The deck is synthetic: a 20 x 10 m room, exit E1 in the west wall
(unthrottled), exit E2 in the east wall (throttled, 1 agent/s), D0 in the west
with a journey to E1, D1 in the east with no journey; E2 is nearest to D1.
"""

from __future__ import annotations

import contextlib
import io
import sqlite3

import pytest
from shapely.geometry import Polygon, box

from pyfds_evac.core.route_graph import RerouteConfig
from pyfds_evac.core.scenario import Scenario, run_scenario

SEED = 1
MAX_TIME_S = 60.0
MAX_THROUGHPUT = 1.0  # agents/s through E2
PER_DISTRIBUTION = 5
WALKABLE = box(0.0, 0.0, 20.0, 10.0)
E1 = box(0.0, 4.0, 0.2, 6.0)
E2 = box(19.8, 4.0, 20.0, 6.0)
D0 = "jps-distributions_0"
D1 = "jps-distributions_1"
# D1 lies east of this line, D0 west of it.
SPLIT_X_M = 10.0
# Trajectory frames are 0.1 s apart; an agent is removed within one frame of
# its last recorded position.
FRAME_S = 0.1


def _coords(polygon: Polygon) -> list[list[float]]:
    return [[x, y] for x, y in polygon.exterior.coords]


def _params(flow: bool = False) -> dict:
    params = {
        "number": PER_DISTRIBUTION,
        "radius": 0.15,
        "v0": 1.3,
        "use_flow_spawning": flow,
        "distribution_mode": "by_number",
        "use_premovement": False,
        "radius_distribution": "constant",
        "v0_distribution": "constant",
    }
    if flow:
        params.update(flow_start_time=0, flow_end_time=5)
    return params


def _scenario(throttled: bool = True, flow: bool = False, **e2_extra) -> Scenario:
    raw = {
        "project_version": "2.0",
        "config": {
            "simulation_settings": {
                "simulationParams": {
                    "max_simulation_time": MAX_TIME_S,
                    "model_type": "CollisionFreeSpeedModel",
                },
                "numberOfSimulations": 1,
                "baseSeed": SEED,
            },
            "ui_state": {"useShortestPaths": False},
        },
        "exits": {
            "E1": {"type": "polygon", "coordinates": _coords(E1)},
            "E2": {
                "type": "polygon",
                "coordinates": _coords(E2),
                "enable_throughput_throttling": throttled,
                "max_throughput": MAX_THROUGHPUT,
                **e2_extra,
            },
        },
        "distributions": {
            D0: {
                "type": "polygon",
                "coordinates": _coords(box(2.0, 2.0, 5.0, 8.0)),
                "parameters": _params(),
            },
            D1: {
                "type": "polygon",
                "coordinates": _coords(box(15.0, 2.0, 18.0, 8.0)),
                "parameters": _params(flow),
            },
        },
        "checkpoints": {},
        "zones": {},
        "journeys": [{"id": "J0", "stages": [D0, "E1"]}],
        "transitions": [{"from": D0, "to": "E1", "journey_id": "J0"}],
    }
    return Scenario(
        raw=raw,
        walkable_area_wkt=WALKABLE.wkt,
        model_type="CollisionFreeSpeedModel",
        seed=SEED,
        sim_params=raw["config"]["simulation_settings"]["simulationParams"],
        source_path=None,
    )


def _run(scenario: Scenario, reroute_config=None):
    with contextlib.redirect_stdout(io.StringIO()):
        return run_scenario(scenario, seed=SEED, reroute_config=reroute_config)


def _d1_last_frames(result) -> dict[int, int]:
    """Last recorded frame of each agent that spawned in D1."""
    with contextlib.closing(sqlite3.connect(result.sqlite_file)) as con:
        rows = con.execute(
            "SELECT frame, id, pos_x FROM trajectory_data ORDER BY frame"
        ).fetchall()
    first_x: dict[int, float] = {}
    last: dict[int, int] = {}
    for frame, agent_id, x in rows:
        first_x.setdefault(agent_id, x)
        last[agent_id] = frame
    return {aid: frame for aid, frame in last.items() if first_x[aid] > SPLIT_X_M}


@pytest.mark.parametrize(
    "reroute_config",
    [None, RerouteConfig(reevaluation_interval_s=1.0)],
    ids=["no-reroute", "reroute"],
)
def test_agents_leave_through_the_throttled_exit(reroute_config):
    result = _run(_scenario(), reroute_config)
    try:
        assert result.agents_remaining == 0
        assert result.success
        d1_frames = _d1_last_frames(result)
        assert len(d1_frames) == PER_DISTRIBUTION
        # Removed by the runtime at E2, the nearest exit, even with rerouting.
        exits = {row["agent_id"]: row["exit_id"] for row in result.exit_history}
        assert {exits[aid] for aid in d1_frames} == {"E2"}
        # The cap holds: removals at E2 at least 1 / max_throughput apart.
        frames = sorted(d1_frames.values())
        min_gap_frames = (1.0 / MAX_THROUGHPUT - FRAME_S) / FRAME_S
        assert all(b - a >= min_gap_frames for a, b in zip(frames, frames[1:]))
    finally:
        result.cleanup()


def test_flow_spawned_agents_leave_through_the_throttled_exit():
    """Flow spawning takes its own branch; its agents were never stalled."""
    result = _run(_scenario(flow=True))
    try:
        assert result.agents_remaining == 0
        assert result.agents_not_spawned == 0
        exits = {row["agent_id"]: row["exit_id"] for row in result.exit_history}
        assert {exits[aid] for aid in _d1_last_frames(result)} == {"E2"}
    finally:
        result.cleanup()


def test_scheduled_throttled_exit_is_still_refused():
    """An agent held to a scheduled exit could not leave once it closed."""
    with pytest.raises(ValueError, match="routed path"):
        _run(
            _scenario(closed_after_s=2.0),
            RerouteConfig(reevaluation_interval_s=1.0),
        )


def test_schedule_on_another_exit_no_longer_refuses_the_deck():
    """Held to an unscheduled throttled exit, the agents are on a routed path.

    Before #434 these agents had no path, so a schedule on any exit refused
    the deck at start.
    """
    scenario = _scenario()
    scenario.raw["exits"]["E1"]["closed_after_s"] = 30.0
    result = _run(scenario, RerouteConfig(reevaluation_interval_s=1.0))
    try:
        assert result.agents_remaining == 0
        exits = {row["agent_id"]: row["exit_id"] for row in result.exit_history}
        assert {exits[aid] for aid in _d1_last_frames(result)} == {"E2"}
    finally:
        result.cleanup()
