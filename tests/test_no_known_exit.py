"""An agent that knows no exit (#610, #91): the ``no_known_exit`` modes.

A distribution's ``no_known_exit`` decides what its agents do while no exit
is reachable in their known subgraph:

* ``default_route`` (default, the FDS+Evac counterpart): follow the scripted
  plan -- the journey, or for a distribution without one the exit nearest by
  walking distance -- and flag leaving through an exit absent from the map;
* ``explore``: frontier, then patrol; with nothing to explore, stand;
* ``return``: walk back over known legs to a node with a known exit;
* ``stay``: stand until an exit becomes known.

Under the opt-in modes no agent walks toward a stage absent from its map
(C4). The unit tests use a hand-built stage graph; the run tests a 20 x 10 m
room with a wall that makes the straight-line nearest exit the far one on
foot.
"""

from __future__ import annotations

import contextlib
import io

import jupedsim as jps
import pytest
from shapely.geometry import Polygon, box

from pyfds_evac.config import rules
from pyfds_evac.core.cognitive_map import (
    AgentCognitiveMap,
    distribution_no_known_exit,
)
from pyfds_evac.core.direct_steering_runtime import advance_path_target
from pyfds_evac.core.route_graph import (
    AgentRouteState,
    RerouteConfig,
    RouteCostConfig,
    StageGraph,
    evaluate_and_reroute,
)
from pyfds_evac.core.scenario import Scenario, _check_run_modes, run_scenario
from pyfds_evac.core.simulation_init import _find_nearest_exit
from pyfds_evac.core.smoke_speed import ConstantExtinctionField

CONFIG = RerouteConfig(cost_config=RouteCostConfig(base_speed_m_per_s=1.3))
STAGES = {
    "C": {"polygon": box(-1, 9, 1, 11), "stage_type": "checkpoint"},
    "EB": {"polygon": box(-1, 29, 1, 31), "stage_type": "exit"},
    "EA": {"polygon": box(9, 9, 11, 11), "stage_type": "exit"},
}


def _graph(**exit_schedule) -> StageGraph:
    """S -> C -> {EB (20 m on), EA (10 m on)}."""
    direct = {k: dict(v) for k, v in STAGES.items()}
    direct["EB"].update(exit_schedule)
    return StageGraph.from_scenario(
        direct,
        [
            {"from": "S", "to": "C"},
            {"from": "C", "to": "EB"},
            {"from": "C", "to": "EA"},
        ],
        distributions={"S": {"polygon": box(-1, -1, 1, 1)}},
    )


def _wait_info(mode: str | None, **extra) -> dict:
    """An agent of journey S -> C -> EB (99 %) / EA (1 %), walking to C."""
    info = {
        "mode": "path",
        "path_choices": {"S": [("C", 100.0)], "C": [("EB", 99.0), ("EA", 1.0)]},
        "stage_configs": {k: dict(v) for k, v in STAGES.items()},
        "current_origin": "S",
        "current_target_stage": "C",
        "target": (0.0, 10.0),
        "target_assigned": True,
        "state": "to_target",
        "base_seed": 7,
        "step_index": 0,
        "current_position": (0.0, 3.0),
        "no_known_exit": mode,
    }
    info.update(extra)
    return info


def _cmap(nodes, edges=(), visited=("S",)) -> AgentCognitiveMap:
    return AgentCognitiveMap(
        familiarity="discovery",
        known_nodes=set(nodes),
        known_edges=set(edges),
        visited_nodes=set(visited),
    )


def _evaluate(wait_info, route_state, cmap, graph=None, time_s=1.0):
    return evaluate_and_reroute(
        agent_id=1,
        wait_info=wait_info,
        route_state=route_state,
        graph=graph or _graph(),
        current_time_s=time_s,
        current_fed=0.0,
        extinction_sampler=ConstantExtinctionField(0.0),
        fed_rate_sampler=None,
        config=CONFIG,
        cognitive_map=cmap,
        agent_position=wait_info.get("current_position"),
    )


class TestDefaultRoute:
    def test_follows_the_journey_and_logs_it_once(self):
        wait_info = _wait_info(None)
        state = AgentRouteState()
        switch = _evaluate(wait_info, state, _cmap({"S"}))
        assert switch is not None
        assert (switch.reason, switch.old_exit, switch.new_exit) == (
            "default_route",
            None,
            "EB",
        )
        # The journey stays as scripted: it is the default route.
        assert wait_info["path_choices"]["C"] == [("EB", 99.0), ("EA", 1.0)]
        assert (state.current_exit, state.default_exit) == (None, "EB")
        assert state.counted_exit == "EB"
        assert _evaluate(wait_info, state, _cmap({"S"}), time_s=11.0) is None

    def test_an_idle_agent_takes_the_nearest_exit_on_foot(self):
        wait_info = _wait_info(
            "default_route", current_origin="C", state="idle", path_choices={}
        )
        state = AgentRouteState()
        switch = _evaluate(wait_info, state, _cmap({"S", "C"}, visited={"S", "C"}))
        assert switch is not None and switch.reason == "default_route"
        assert switch.new_exit == "EA"
        assert wait_info["current_target_stage"] == "EA"

    def test_a_closed_scripted_exit_is_replaced_by_an_open_one(self):
        wait_info = _wait_info("default_route")
        state = AgentRouteState()
        switch = _evaluate(
            wait_info, state, _cmap({"S"}), graph=_graph(closed_after_s=0.5)
        )
        assert switch is not None and switch.new_exit == "EA"
        assert state.default_exit == "EA"

    def test_the_first_known_exit_is_an_initial_choice(self):
        """F5: the default exit is not a known exit to switch away from."""
        wait_info = _wait_info("default_route", current_origin="C", state="idle")
        state = AgentRouteState(default_exit="EB")
        cmap = _cmap({"S", "C", "EA"}, {("S", "C"), ("C", "EA")}, {"S", "C"})
        switch = _evaluate(wait_info, state, cmap)
        assert switch is not None
        assert (switch.reason, switch.old_exit, switch.old_cost) == (
            "initial",
            None,
            None,
        )
        assert (state.current_exit, state.default_exit) == ("EA", None)


class TestOptInModes:
    def test_explore_stands_rather_than_walk_to_an_unknown_stage(self):
        """C4: the journey's first stage is not in the map."""
        wait_info = _wait_info("explore")
        state = AgentRouteState()
        switch = _evaluate(wait_info, state, _cmap({"S"}))
        assert switch is not None and switch.reason == "stay"
        assert wait_info["state"] == "idle"
        assert wait_info["current_target_stage"] == "S"
        # The runtime gives it the point it stands on.
        assert wait_info["target"] == (0.0, 3.0)
        assert wait_info["target_assigned"] is False
        assert state.counted_exit is None
        assert _evaluate(wait_info, state, _cmap({"S"}), time_s=11.0) is None

    def test_explore_keeps_walking_to_a_known_frontier(self):
        wait_info = _wait_info("explore")
        state = AgentRouteState()
        switch = _evaluate(wait_info, state, _cmap({"S", "C"}, {("S", "C")}))
        assert switch is None
        assert wait_info["state"] == "to_target"
        assert wait_info["current_target_stage"] == "C"

    def test_stay_stands_once(self):
        wait_info = _wait_info("stay")
        state = AgentRouteState()
        cmap = _cmap({"S", "C"}, {("S", "C")})
        switch = _evaluate(wait_info, state, cmap)
        assert switch is not None and switch.reason == "stay"
        assert state.standing
        assert _evaluate(wait_info, state, cmap, time_s=11.0) is None

    def test_return_walks_back_over_a_one_way_leg(self):
        """From D the known exit is reachable only through C, behind it."""
        direct = {k: dict(v) for k, v in STAGES.items()}
        direct["D"] = {"polygon": box(-1, 19, 1, 21), "stage_type": "checkpoint"}
        graph = StageGraph.from_scenario(
            direct,
            [
                {"from": "S", "to": "C"},
                {"from": "C", "to": "D"},
                {"from": "C", "to": "EA"},
            ],
            distributions={"S": {"polygon": box(-1, -1, 1, 1)}},
        )
        wait_info = _wait_info(
            "return",
            current_origin="D",
            current_target_stage="D",
            state="idle",
            path_choices={},
            current_position=(0.0, 20.0),
        )
        wait_info["stage_configs"]["D"] = direct["D"]
        cmap = _cmap(
            {"S", "C", "D", "EA"},
            {("S", "C"), ("C", "D"), ("C", "EA")},
            {"S", "C", "D"},
        )
        switch = _evaluate(wait_info, AgentRouteState(), cmap, graph=graph)
        assert switch is not None and switch.reason == "return"
        assert switch.new_exit == "C"
        assert wait_info["current_target_stage"] == "C"

    def test_a_scripted_leg_to_an_unknown_stage_is_not_taken(self):
        wait_info = _wait_info("explore")
        advance_path_target(wait_info, may_enter={"S", "C"}.__contains__)
        assert wait_info["state"] == "idle"
        assert wait_info["current_origin"] == "C"


class TestRunModes:
    """C5 / D33: an opt-in mode needs a reroute pass."""

    MODES = {"d0": "explore"}

    def test_smoke_blind_is_rejected_with_the_control_named(self):
        with pytest.raises(ValueError) as excinfo:
            _check_run_modes(True, None, None, None, None, self.MODES)
        message = str(excinfo.value)
        assert "'d0'" in message and "'explore'" in message
        assert "clear-air run (no --fds-dir)" in message

    def test_rerouting_off_is_rejected(self):
        with pytest.raises(ValueError, match="needs rerouting"):
            _check_run_modes(False, None, None, None, None, self.MODES)

    def test_the_default_stays_allowed(self):
        _check_run_modes(True, None, None, None, None, {"d0": "default_route"})
        _check_run_modes(False, CONFIG, None, None, None, self.MODES)

    @staticmethod
    def _raw(mode):
        return {"distributions": {"d0": {"parameters": {"no_known_exit": mode}}}}

    def test_the_front_ends_refuse_before_a_run(self):
        class Opts:
            smoke_blind = True
            enable_rerouting = True

        issue = rules.no_known_exit_issue(Opts(), self._raw("stay"))
        assert issue is not None and issue.rule == "D33"
        assert "clear-air run" in issue.message
        assert rules.no_known_exit_issue(Opts(), self._raw(None)) is None

    def test_the_cli_and_tui_configuration_reports_it(self):
        from argparse import Namespace

        from pyfds_evac.config.effective import effective_configuration

        cfg = effective_configuration(
            Namespace(smoke_blind=True, scenario="deck.json"),
            self._raw("explore"),
            inspect_fds=False,
        )
        assert [e.rule for e in cfg.errors] == ["D33"]
        assert "clear-air run" in cfg.errors[0].message

    def test_the_gui_refuses_the_form(self):
        from pyfds_evac.webapp.app import _resolve_form, _ScenarioError

        form = {"scenario": "familiarity_test_discovery", "smoke_blind": "on"}
        with pytest.raises(_ScenarioError, match="clear-air run"):
            _resolve_form(form)

    def test_an_unknown_mode_names_its_distribution(self):
        with pytest.raises(ValueError, match="distribution 'd0'.*'wait'"):
            distribution_no_known_exit(self._raw("wait"))
        assert rules.scenario_issue(self._raw("wait")) is not None


# --- C6: walking distance, and a run --------------------------------------

# A 20 x 10 m room with a wall from the floor to y = 8 m at x = 9..11 m.
WALKABLE = Polygon(
    [(0, 0), (9, 0), (9, 8), (11, 8), (11, 0), (20, 0), (20, 10), (0, 10)]
)
E_BEHIND_WALL = box(12.0, 0.0, 13.0, 0.5)  # 5 m away in a line, 17 m on foot
E_FAR = box(0.0, 9.5, 1.0, 10.0)  # 9 m away in a line, about 10 m on foot
SPAWN = box(6.0, 0.5, 8.0, 2.5)


def test_the_nearest_exit_is_measured_on_foot():
    exits = {"behind": E_BEHIND_WALL, "far": E_FAR}
    position = (7.0, 1.5)
    assert _find_nearest_exit(position, exit_geometries=exits) == "behind"
    engine = jps.RoutingEngine(WALKABLE)
    nearest = _find_nearest_exit(
        position, exit_geometries=exits, routing_engine=engine, walkable=WALKABLE
    )
    assert nearest == "far"


def _coords(polygon) -> list[list[float]]:
    return [[x, y] for x, y in polygon.exterior.coords]


def _scenario(mode: str | None) -> Scenario:
    params = {
        "number": 4,
        "radius": 0.15,
        "v0": 1.3,
        "distribution_mode": "by_number",
        "use_premovement": False,
        "familiarity": "discovery",
    }
    if mode is not None:
        params["no_known_exit"] = mode
    sim_params = {"max_simulation_time": 40.0, "model_type": "CollisionFreeSpeedModel"}
    raw = {
        "project_version": "2.0",
        "config": {
            "simulation_settings": {
                "simulationParams": sim_params,
                "numberOfSimulations": 1,
                "baseSeed": 3,
            }
        },
        "exits": {
            "behind": {"type": "polygon", "coordinates": _coords(E_BEHIND_WALL)},
            "far": {"type": "polygon", "coordinates": _coords(E_FAR)},
        },
        "distributions": {
            "d0": {
                "type": "polygon",
                "coordinates": _coords(SPAWN),
                "parameters": params,
            }
        },
        "checkpoints": {},
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


def _run(mode):
    with contextlib.redirect_stdout(io.StringIO()):
        return run_scenario(
            _scenario(mode),
            seed=3,
            reroute_config=RerouteConfig(reevaluation_interval_s=1.0),
        )


def test_default_route_leaves_by_the_nearest_exit_on_foot_and_is_flagged():
    """AT3: no sight, a map of the spawn area alone."""
    result = _run(None)
    try:
        assert result.agents_evacuated == 4
        assert {row["exit_id"] for row in result.exit_history} == {"far"}
        assert not any(row["exit_in_map"] for row in result.exit_history)
        assert result.metrics["agents_left_by_unknown_exit"] == 4
        reasons = [row["reason"] for row in result.route_history]
        assert reasons == ["default_route"] * 4
    finally:
        result.cleanup()


@pytest.mark.parametrize("mode", ["explore", "stay", "return"])
def test_opt_in_modes_never_leave_by_an_unknown_exit(mode):
    result = _run(mode)
    try:
        assert result.agents_evacuated == 0
        assert result.metrics["agents_left_by_unknown_exit"] == 0
        assert result.exit_history == []
        assert {row["reason"] for row in result.route_history} == {"stay"}
    finally:
        result.cleanup()


# --- C3 (#468): the walked leg is known ------------------------------------


def test_arrival_teaches_the_leg_walked():
    """AT2: arriving over S -> C makes (S, C) known."""
    from pyfds_evac.core.cognitive_map import expand_on_arrival

    graph = _graph()
    cmap = _cmap({"S"})
    expand_on_arrival(cmap, "C", graph, from_node="S")
    assert ("S", "C") in cmap.known_edges
    # The graph has no C -> S edge, so no reverse is invented.
    assert ("C", "S") not in cmap.known_edges


def test_arrival_teaches_the_reverse_when_the_graph_has_it():
    from pyfds_evac.core.cognitive_map import expand_on_arrival

    graph = StageGraph.from_scenario(
        {k: dict(v) for k, v in STAGES.items()},
        [{"from": "S", "to": "C"}, {"from": "C", "to": "S"}],
        distributions={"S": {"polygon": box(-1, -1, 1, 1)}},
    )
    cmap = _cmap({"S"})
    expand_on_arrival(cmap, "C", graph, from_node="S")
    assert {("S", "C"), ("C", "S")} <= cmap.known_edges


@pytest.mark.parametrize("mode", ["explore", "default_route"])
def test_seeing_a_node_first_or_arriving_there_ends_the_same(mode):
    """AT1 (F2): the agent that read C's sign on the way and the one that
    learned C on arrival hold the same map after it and decide alike."""
    from pyfds_evac.core.cognitive_map import expand_on_arrival

    graph = _graph()
    by_sign = _cmap({"S", "C"}, {("S", "C")})
    on_arrival = _cmap({"S"})
    decisions = []
    for cmap in (by_sign, on_arrival):
        expand_on_arrival(cmap, "C", graph, from_node="S")
        wait_info = _wait_info(mode, current_origin="C", state="idle")
        wait_info["current_target_stage"] = "C"
        switch = _evaluate(wait_info, AgentRouteState(), cmap)
        decisions.append(None if switch is None else (switch.reason, switch.new_exit))
    assert by_sign.known_edges == on_arrival.known_edges
    assert decisions[0] == decisions[1]


def _journey_scenario() -> Scenario:
    """S (west) -> checkpoint C (middle) -> exit E (east) in a 20 x 4 m hall."""
    params = {
        "number": 1,
        "radius": 0.15,
        "v0": 1.3,
        "distribution_mode": "by_number",
        "use_premovement": False,
        "familiarity": "discovery",
    }
    transitions = [
        {
            "from": "jps-distributions_0",
            "to": "jps-checkpoints_0",
            "journey_id": "journey_0",
        },
        {"from": "jps-checkpoints_0", "to": "jps-exits_0", "journey_id": "journey_0"},
    ]
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
        "exits": {
            "jps-exits_0": {
                "type": "polygon",
                "coordinates": _coords(box(19.5, 1, 20, 3)),
            }
        },
        "distributions": {
            "jps-distributions_0": {
                "type": "polygon",
                "coordinates": _coords(box(1, 1, 3, 3)),
                "parameters": params,
            }
        },
        "checkpoints": {
            "jps-checkpoints_0": {
                "type": "polygon",
                "coordinates": _coords(box(9, 1, 11, 3)),
                "waiting_time": 0,
            }
        },
        "zones": {},
        "journeys": [
            {
                "id": "journey_0",
                "stages": ["jps-distributions_0", "jps-checkpoints_0", "jps-exits_0"],
                "transitions": transitions,
            }
        ],
        "transitions": transitions,
    }
    return Scenario(
        raw=raw,
        walkable_area_wkt=box(0, 0, 20, 4).wkt,
        model_type="CollisionFreeSpeedModel",
        seed=3,
        sim_params=sim_params,
        source_path=None,
    )


def test_a_run_learns_the_leg_walked_to_a_checkpoint():
    """AT2 in a run: no sight, so only arrival teaches; the leg S -> C is
    walked and must be in the map afterwards (#468)."""
    with contextlib.redirect_stdout(io.StringIO()):
        result = run_scenario(
            _journey_scenario(),
            seed=3,
            reroute_config=RerouteConfig(reevaluation_interval_s=1.0),
            collect_cognitive_map_history=True,
        )
    try:
        final = result.cognitive_map_history[-1]
        assert "jps-checkpoints_0" in final["known_nodes"]
        assert ("jps-distributions_0", "jps-checkpoints_0") in {
            tuple(edge) for edge in final["known_edges"]
        }
    finally:
        result.cleanup()
