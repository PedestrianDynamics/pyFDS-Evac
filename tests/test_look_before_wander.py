"""An explorer looks from the node point before it patrols (#250, #387).

A visit to a checkpoint is complete within ``agent_radius + 0.5 m`` of a
random point in it, so an explorer can complete it short of the doorway
from which the next sign is legible. With nothing left to explore it would
patrol away and never read the sign (#250 at CP3, #387 at C1). Before a
patrol leg it now walks until the node point lies under its body and looks
from there.

The run test is a 20 x 10 m room with no FDS data. The checkpoint, 8 m east
of the spawn, is a doorway stage in miniature: two 0.6 m lobes joined by a
0.2 m neck that holds its node point. The exit is visible only from within
0.25 m of that point.
"""

from __future__ import annotations

import contextlib
import io
import logging
import math

import pytest
from shapely.geometry import Point, box
from shapely.ops import unary_union

from pyfds_evac.core.cognitive_map import AgentCognitiveMap
from pyfds_evac.core.geometry import node_position
from pyfds_evac.core.route_graph import (
    AgentRouteState,
    RerouteConfig,
    RouteCostConfig,
    StageGraph,
    evaluate_and_reroute,
)
from pyfds_evac.core.scenario import Scenario, run_scenario
from pyfds_evac.core.smoke_speed import ConstantExtinctionField

SPAWN = box(1, 1, 3, 3)
CHECKPOINT = unary_union(
    [box(9.9, 1.6, 10.1, 2.4), box(9.7, 2.4, 10.3, 3.0), box(9.7, 1.0, 10.3, 1.6)]
)
EXIT = box(1, 9, 3, 10)
WALKABLE = box(0, 0, 20, 10)
NODE_POINT = (10.0, 2.0)
SEEN_WITHIN_M = 0.25


class _ExitSeenNearNodePoint:
    """The checkpoint is visible from everywhere; the exit only from within
    ``SEEN_WITHIN_M`` of the checkpoint's node point; nothing else."""

    def __init__(self, checkpoint_id: str, exit_id: str) -> None:
        self.checkpoint_id = checkpoint_id
        self.exit_id = exit_id

    def node_is_visible(self, time_s, ax, ay, node_id) -> bool:
        if node_id == self.checkpoint_id:
            return True
        if node_id == self.exit_id:
            gap = math.hypot(ax - NODE_POINT[0], ay - NODE_POINT[1])
            return gap <= SEEN_WITHIN_M
        return False

    def signs_outside_grid(self) -> list:
        return []


def _coords(polygon) -> list[list[float]]:
    return [[x, y] for x, y in polygon.exterior.coords]


def _scenario() -> Scenario:
    params = {
        "number": 1,
        "radius": 0.15,
        "v0": 1.3,
        "distribution_mode": "by_number",
        "use_premovement": False,
        "familiarity": "discovery",
        "no_known_exit": "explore",
    }
    sim_params = {"max_simulation_time": 30.0, "model_type": "CollisionFreeSpeedModel"}
    raw = {
        "project_version": "2.0",
        "config": {
            "simulation_settings": {
                "simulationParams": sim_params,
                "numberOfSimulations": 1,
                "baseSeed": 3,
            }
        },
        "exits": {"jps-exits_0": {"type": "polygon", "coordinates": _coords(EXIT)}},
        "distributions": {
            "jps-distributions_0": {
                "type": "polygon",
                "coordinates": _coords(SPAWN),
                "parameters": params,
            }
        },
        "checkpoints": {
            "jps-checkpoints_0": {
                "type": "polygon",
                "coordinates": _coords(CHECKPOINT),
                "waiting_time": 0,
            }
        },
        "zones": {},
        "journeys": [],
        "transitions": [],
    }
    return Scenario(
        raw=raw,
        walkable_area_wkt=WALKABLE.wkt,
        model_type="CollisionFreeSpeedModel",
        seed=3,
        sim_params=sim_params,
        source_path=None,
    )


def test_an_explorer_reads_the_exit_from_the_node_point():
    """AT-250-R: the explorer completes its visit to the checkpoint at the
    random point it was sent to, in a lobe, where the exit is not visible.
    Without the look it patrols back to its spawn; with it, it reads the exit
    from the node point and leaves."""
    checkpoint_id, exit_id = "jps-checkpoints_0", "jps-exits_0"
    # Precondition: the random target keeps 0.8 x 0.2 m from the stage's
    # edge, so it lies in a lobe, more than SEEN_WITHIN_M from the node point,
    # and an explorer that never walks to the node point never sees the exit.
    assert node_position(CHECKPOINT) == pytest.approx(NODE_POINT)
    assert CHECKPOINT.buffer(-0.16).distance(Point(NODE_POINT)) > 0.5
    # Precondition: only the checkpoint's neighbours are learned there, so
    # the run's auto-wired graph must hold the checkpoint -> exit edge.
    graph = StageGraph.from_scenario(
        {
            checkpoint_id: {"polygon": CHECKPOINT, "stage_type": "checkpoint"},
            exit_id: {"polygon": EXIT, "stage_type": "exit"},
        },
        [],
        distributions={"jps-distributions_0": {"polygon": SPAWN}},
        walkable_polygon=WALKABLE,
    )
    assert exit_id in {edge.target for edge in graph.edges[checkpoint_id]}
    vis = _ExitSeenNearNodePoint(checkpoint_id, exit_id)
    with contextlib.redirect_stdout(io.StringIO()):
        result = run_scenario(
            _scenario(),
            seed=3,
            reroute_config=RerouteConfig(reevaluation_interval_s=0.1),
            vis_model=vis,
        )
    try:
        rows = [(row["new_exit"], row["reason"]) for row in result.route_history]
        assert "wander" not in {reason for _, reason in rows}
        assert rows == [(checkpoint_id, "explore"), (exit_id, "initial")]
        assert result.agents_evacuated == 1
    finally:
        result.cleanup()


# AT-250-U: the decision itself, on a hand-built graph. S -> C -> E, the
# agent stands at C knowing only S and C, both visited.
STAGES = {
    "C": {"polygon": CHECKPOINT, "stage_type": "checkpoint"},
    "E": {"polygon": EXIT, "stage_type": "exit"},
}
CONFIG = RerouteConfig(
    reevaluation_interval_s=0.1,
    cost_config=RouteCostConfig(base_speed_m_per_s=1.3),
)


def _graph(stages=STAGES) -> StageGraph:
    return StageGraph.from_scenario(
        stages,
        [{"from": "S", "to": "C"}, {"from": "C", "to": "E"}],
        distributions={"S": {"polygon": SPAWN}},
        walkable_polygon=WALKABLE,
    )


def _idle_at_checkpoint(stages=STAGES) -> dict:
    return {
        "mode": "path",
        "path_choices": {"S": [("C", 100.0)]},
        "stage_configs": {k: dict(v) for k, v in stages.items()}
        | {"S": {"polygon": SPAWN, "stage_type": "distribution"}},
        "current_origin": "C",
        "current_target_stage": "C",
        "target": (10.1, 2.1),
        "target_assigned": True,
        "state": "idle",
        "base_seed": 7,
        "step_index": 1,
        "no_known_exit": "explore",
        "body_radius": 0.2,
    }


def _exhausted() -> AgentCognitiveMap:
    return AgentCognitiveMap(
        familiarity="discovery",
        known_nodes={"S", "C"},
        known_edges={("S", "C")},
        visited_nodes={"S", "C"},
    )


def _evaluate(wait_info, route_state, position, graph=None):
    return evaluate_and_reroute(
        agent_id=1,
        wait_info=wait_info,
        route_state=route_state,
        graph=graph or _graph(),
        current_time_s=5.0,
        current_fed=0.0,
        extinction_sampler=ConstantExtinctionField(0.0),
        fed_rate_sampler=None,
        config=CONFIG,
        cached_segments={},
        cognitive_map=_exhausted(),
        agent_position=position,
    )


def _route_state() -> AgentRouteState:
    return AgentRouteState(current_path=["S", "C"], wander_step=0)


def _arrive_at_node_point(wait_info: dict) -> None:
    """What the runtime does once the node point lies under the agent."""
    wait_info.pop("look_point")
    wait_info["state"] = "idle"


def test_an_idle_explorer_looks_before_it_patrols():
    wait_info, rs = _idle_at_checkpoint(), _route_state()
    assert _evaluate(wait_info, rs, (10.5, 2.0)) is None
    assert wait_info["target"] == pytest.approx(NODE_POINT)
    assert wait_info["state"] == "to_target"
    assert wait_info["current_target_stage"] == "C"
    assert wait_info["current_origin"] == "C"
    assert rs.wander_step == 0
    assert rs.current_path == ["S", "C"]
    # Still walking to the node point: no patrol leg pre-empts the look.
    assert _evaluate(wait_info, rs, (10.3, 2.0)) is None
    assert wait_info["target"] == pytest.approx(NODE_POINT)
    assert rs.wander_step == 0


def test_after_the_look_the_patrol_is_the_one_without_it():
    """Nothing learned at the node point: the patrol leg and the patrol step
    are the ones an agent that never looked takes."""
    wait_info, rs = _idle_at_checkpoint(), _route_state()
    _evaluate(wait_info, rs, (10.5, 2.0))
    _arrive_at_node_point(wait_info)
    switch = _evaluate(wait_info, rs, (10.05, 2.0))

    # Standing on the node point already, the other agent patrols at once.
    plain, plain_rs = _idle_at_checkpoint(), _route_state()
    plain_switch = _evaluate(plain, plain_rs, (10.05, 2.0))
    assert switch is not None and plain_switch is not None
    assert (switch.new_exit, switch.reason) == ("S", "wander")
    assert (switch.new_exit, switch.reason) == (
        plain_switch.new_exit,
        plain_switch.reason,
    )
    assert rs.wander_step == plain_rs.wander_step == 1
    assert rs.current_path == plain_rs.current_path
    assert wait_info["current_target_stage"] == plain["current_target_stage"]
    assert wait_info["path_choices"] == plain["path_choices"]


def test_the_look_happens_once_per_visit():
    wait_info, rs = _idle_at_checkpoint(), _route_state()
    _evaluate(wait_info, rs, (10.5, 2.0))
    # Given up short of the node point: the agent patrols from there.
    _arrive_at_node_point(wait_info)
    switch = _evaluate(wait_info, rs, (10.5, 2.0))
    assert switch is not None and switch.reason == "wander"


def test_an_exit_seen_during_the_look_replaces_it():
    """An exit learned on the way to the node point is taken at once, as
    from the node itself."""
    wait_info, rs = _idle_at_checkpoint(), _route_state()
    _evaluate(wait_info, rs, (10.5, 2.0))
    cmap = _exhausted()
    cmap.known_nodes.add("E")
    cmap.known_edges.add(("C", "E"))
    switch = evaluate_and_reroute(
        agent_id=1,
        wait_info=wait_info,
        route_state=rs,
        graph=_graph(),
        current_time_s=5.1,
        current_fed=0.0,
        extinction_sampler=ConstantExtinctionField(0.0),
        fed_rate_sampler=None,
        config=CONFIG,
        cached_segments={},
        cognitive_map=cmap,
        agent_position=(10.3, 2.0),
    )
    assert switch is not None
    assert (switch.new_exit, switch.reason) == ("E", "initial")
    assert wait_info["current_target_stage"] == "E"
    assert wait_info["state"] == "to_target"
    assert "look_point" not in wait_info


def test_no_look_when_the_agent_does_not_fit_on_the_node_point(caplog):
    """A node point against a wall: the agent patrols without looking, as
    before, with one warning per node and radius."""
    walled = dict(STAGES, C={"polygon": box(9.8, 9.8, 10.2, 10.0)})
    walled["C"]["stage_type"] = "checkpoint"
    graph = _graph(walled)
    with caplog.at_level(logging.WARNING, logger="pyfds_evac.core.route_graph"):
        for _ in range(2):
            wait_info, rs = _idle_at_checkpoint(walled), _route_state()
            switch = _evaluate(wait_info, rs, (10.0, 9.5), graph=graph)
            assert switch is not None and switch.reason == "wander"
            assert rs.wander_step == 1
    warnings = [r for r in caplog.records if "leaves no room" in r.getMessage()]
    assert len(warnings) == 1
    assert "C" in warnings[0].getMessage()


def test_no_look_before_standing():
    """Nowhere to patrol to: the agent stays where it is, without a look."""
    wait_info, rs = _idle_at_checkpoint(), _route_state()
    lonely = AgentCognitiveMap(
        familiarity="discovery",
        known_nodes={"C"},
        known_edges=set(),
        visited_nodes={"C"},
    )
    switch = evaluate_and_reroute(
        agent_id=1,
        wait_info=wait_info,
        route_state=rs,
        graph=_graph(),
        current_time_s=5.0,
        current_fed=0.0,
        extinction_sampler=ConstantExtinctionField(0.0),
        fed_rate_sampler=None,
        config=CONFIG,
        cached_segments={},
        cognitive_map=lonely,
        agent_position=(10.5, 2.0),
    )
    assert switch is None
    assert wait_info["state"] == "idle"
    assert "look_point" not in wait_info


@pytest.mark.parametrize(
    ("distance", "speed", "expected"),
    [(1.3, 1.3, 12.0), (0.0, 1.3, 10.0), (1.0, 0.0, None), (1.0, None, None)],
)
def test_look_timeout_is_twice_the_free_walk_plus_the_allowance(
    distance, speed, expected
):
    # Imported here: the module must import on a revision without the look,
    # so the run test can show the defect there.
    from pyfds_evac.core.direct_steering_runtime import look_timeout_s

    timeout = look_timeout_s(distance, speed)
    if expected is None:
        assert timeout is None
    else:
        assert timeout == pytest.approx(expected)


def test_a_look_that_never_arrives_is_given_up_into_the_patrol(monkeypatch, caplog):
    """The node point is never reached (held for ever, as by a deadlocked
    pair): the look is given up once, after twice the free walk plus the
    crowd allowance, with a warning, and the agent patrols from there."""
    from pyfds_evac.core import scenario as scenario_module
    from pyfds_evac.core.direct_steering_runtime import (
        LOOK_CROWD_ALLOWANCE_S,
        look_timeout_s,
    )

    monkeypatch.setattr(scenario_module, "reached_node_point", lambda *a: False)
    timeouts = []

    def recorded(distance_m, desired_speed):
        timeouts.append(look_timeout_s(distance_m, desired_speed))
        return timeouts[-1]

    monkeypatch.setattr(scenario_module, "look_timeout_s", recorded)
    checkpoint_id, exit_id = "jps-checkpoints_0", "jps-exits_0"
    vis = _ExitSeenNearNodePoint(checkpoint_id, exit_id)
    monkeypatch.setattr(vis, "exit_id", "never-seen")
    with (
        contextlib.redirect_stdout(io.StringIO()),
        caplog.at_level(logging.WARNING, logger="pyfds_evac.core.scenario"),
    ):
        result = run_scenario(
            _scenario(),
            seed=3,
            reroute_config=RerouteConfig(reevaluation_interval_s=1.0),
            vis_model=vis,
        )
    try:
        give_ups = [r for r in caplog.records if "gave up walking" in r.getMessage()]
        assert len(give_ups) == 1
        _agent, stage, given_up_at, _short = give_ups[0].args
        assert stage == checkpoint_id
        rows = [
            (row["time_s"], row["new_exit"], row["reason"])
            for row in result.route_history
        ]
        assert rows[0][1:] == (checkpoint_id, "explore")
        assert rows[1][2] == "wander"
        # The first look is timed from its first step, once the agent is at
        # the checkpoint, at least 7 m from the spawn at 1.3 m/s. The patrol
        # brings it back to the checkpoint, a new visit with a new look.
        assert timeouts[0] > LOOK_CROWD_ALLOWANCE_S
        assert given_up_at - timeouts[0] > 7.0 / 1.3
        # The next reroute pass sends it on the patrol.
        assert given_up_at <= rows[1][0] <= given_up_at + 1.0
        assert result.agents_evacuated == 0
    finally:
        result.cleanup()
