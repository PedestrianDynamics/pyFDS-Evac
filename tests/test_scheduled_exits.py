"""Exits that open and close on a schedule (issue #373).

An exit with ``open_from_s`` or ``closed_after_s`` accepts agents only while
``open_from_s <= t < closed_after_s``. A closed exit removes nobody, and the
agents heading for it re-decide on the exits they know: through the reroute
pass, or in a run without one (smoke-blind, rerouting off) at the same
one-second check, by the opening choice's scoring (#395).

The scenario is synthetic: a 30 x 10 m room with one door in the west wall
and its mirror in the east wall, and one spawn area covering the room.
"""

from __future__ import annotations

import contextlib
import math
import sqlite3

import pytest
from shapely.geometry import Point, Polygon, box

from pyfds_evac.core.route_graph import (
    RerouteConfig,
    StageGraph,
    StageNode,
    without_closed_stages,
)
from pyfds_evac.core.scenario import Scenario, run_scenario

LENGTH_M = 30.0
WIDTH_M = 10.0
DOOR_M = 1.0
DOOR_DEPTH_M = 1.0
NUM_AGENTS = 40
SEED = 7
T_CLOSE_S = 4.0
T_OPEN_S = 8.0
MAX_TIME_S = 90.0
# Agents are removed inside the door polygon, so their last recorded position
# lies within this distance of the door they left through.
AT_DOOR_M = 0.5
# One trajectory frame of slack around a schedule time.
FRAME_S = 0.1
# A long interval: a closure must not wait for the regular re-evaluation.
REROUTE = RerouteConfig(reevaluation_interval_s=30.0)
# An opening is noticed only at the regular re-evaluation, so the opening test
# re-evaluates often.
REROUTE_OFTEN = RerouteConfig(reevaluation_interval_s=2.0)
# The west door's pocket: the closed door and the strip of room in front of it
# where agents that know no other exit wait.
WEST_POCKET_M = 2.5


def _door(west: bool) -> Polygon:
    lo, hi = WIDTH_M / 2.0 - DOOR_M / 2.0, WIDTH_M / 2.0 + DOOR_M / 2.0
    if west:
        return box(-DOOR_DEPTH_M, lo, 0.0, hi)
    return box(LENGTH_M, lo, LENGTH_M + DOOR_DEPTH_M, hi)


DOORS = {"west": _door(True), "east": _door(False)}


def _coords(polygon: Polygon) -> list[list[float]]:
    return [[x, y] for x, y in polygon.exterior.coords]


def _scenario(
    schedules: dict[str, dict], doors: dict[str, Polygon] = DOORS, **dist_params
) -> Scenario:
    walkable = box(0.0, 0.0, LENGTH_M, WIDTH_M)
    for door in doors.values():
        walkable = walkable.union(door)
    exits = {
        name: {
            "type": "polygon",
            "coordinates": _coords(poly),
            "enable_throughput_throttling": False,
            "max_throughput": 0,
            **schedules.get(name, {}),
        }
        for name, poly in doors.items()
    }
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
        "exits": exits,
        "distributions": {
            "room": {
                "type": "polygon",
                "coordinates": _coords(box(0.3, 0.3, LENGTH_M - 0.3, WIDTH_M - 0.3)),
                "parameters": {
                    "number": NUM_AGENTS,
                    "radius": 0.2,
                    "v0": 1.2,
                    "use_flow_spawning": False,
                    "distribution_mode": "by_number",
                    "use_premovement": False,
                    "radius_distribution": "constant",
                    "v0_distribution": "constant",
                    **dist_params,
                },
            }
        },
        "checkpoints": {},
        "zones": {},
        "journeys": [],
        "transitions": [],
    }
    sim_params = raw["config"]["simulation_settings"]["simulationParams"]
    return Scenario(
        raw=raw,
        walkable_area_wkt=walkable.wkt,
        model_type="CollisionFreeSpeedModel",
        seed=SEED,
        sim_params=sim_params,
        source_path=None,
    )


def _last_seen(result) -> list[tuple[float, float, float]]:
    """Each agent's last recorded time and position."""
    with contextlib.closing(sqlite3.connect(result.sqlite_file)) as con:
        fps = float(
            con.execute("SELECT value FROM metadata WHERE key='fps'").fetchone()[0]
        )
        rows = con.execute(
            "SELECT id, frame, pos_x, pos_y FROM trajectory_data ORDER BY frame"
        ).fetchall()
    last = {agent_id: (frame, x, y) for agent_id, frame, x, y in rows}
    return [(frame / fps, x, y) for frame, x, y in last.values()]


def _door_at(x: float, y: float) -> str | None:
    """The door the point (x, y) stands in, if any."""
    return next(
        (n for n, p in DOORS.items() if p.distance(Point(x, y)) <= AT_DOOR_M),
        None,
    )


def _frames(result) -> list[tuple[float, float, float]]:
    """Every recorded (time, x, y) of the run."""
    with contextlib.closing(sqlite3.connect(result.sqlite_file)) as con:
        fps = float(
            con.execute("SELECT value FROM metadata WHERE key='fps'").fetchone()[0]
        )
        rows = con.execute("SELECT frame, pos_x, pos_y FROM trajectory_data")
        return [(frame / fps, x, y) for frame, x, y in rows]


def _run(scenario: Scenario, with_frames: bool = False, **kwargs) -> dict:
    result = run_scenario(scenario, seed=SEED, **kwargs)
    try:
        last_seen = _last_seen(result)
        return {
            "last_seen": last_seen,
            "departures": [(t, _door_at(x, y)) for t, x, y in last_seen],
            "routes": list(result.route_history or []),
            "frames": _frames(result) if with_frames else [],
            "evacuated": result.agents_evacuated,
            "remaining": result.agents_remaining,
        }
    finally:
        result.cleanup()


# The three ways a run decides routes: the reroute pass, and the two runs
# without one, which re-decide only when an exit closes (#395).
RUN_MODES = {
    "reroute": {"reroute_config": REROUTE},
    "no_reroute": {"reroute_config": None},
    "smoke_blind": {"smoke_blind": True},
}
NO_REROUTE_MODES = ["no_reroute", "smoke_blind"]


@pytest.fixture(scope="module", params=list(RUN_MODES))
def closing_run(request) -> dict:
    """The west door closes at T_CLOSE_S."""
    scenario = _scenario({"west": {"closed_after_s": T_CLOSE_S}})
    return _run(scenario, **RUN_MODES[request.param])


def test_closed_exit_removes_nobody_after_closing(closing_run):
    late = [t for t, door in closing_run["departures"] if door == "west"]
    assert late, "nobody left by the west door before it closed"
    assert max(late) <= T_CLOSE_S + FRAME_S


def test_agents_heading_for_closed_exit_reroute(closing_run):
    closed = [r for r in closing_run["routes"] if r["reason"] == "exit_closed"]
    assert closed
    assert {(r["old_exit"], r["new_exit"]) for r in closed} == {("west", "east")}
    # The closure is acted on at the next one-second reroute check, not after
    # the 30 s re-evaluation interval.
    assert all(T_CLOSE_S <= r["time_s"] <= T_CLOSE_S + 1.0 for r in closed)
    assert not [
        r
        for r in closing_run["routes"]
        if r["new_exit"] == "west" and r["time_s"] >= T_CLOSE_S
    ]


def test_everyone_leaves_by_the_open_exit(closing_run):
    assert closing_run["evacuated"] == NUM_AGENTS
    assert closing_run["remaining"] == 0


def test_exit_opens_on_schedule():
    """Agents spawned by the east door walk west until it opens, then use it."""
    scenario = _scenario({"east": {"open_from_s": T_OPEN_S}})
    near_east = box(LENGTH_M - 8.0, 0.3, LENGTH_M - 0.3, WIDTH_M - 0.3)
    scenario.raw["distributions"]["room"]["coordinates"] = _coords(near_east)
    run = _run(scenario, reroute_config=REROUTE_OFTEN)
    east = [t for t, door in run["departures"] if door == "east"]
    assert east, "nobody left by the east door once it opened"
    assert min(east) >= T_OPEN_S
    to_east = [r["time_s"] for r in run["routes"] if r["new_exit"] == "east"]
    assert to_east and min(to_east) >= T_OPEN_S
    assert run["evacuated"] == NUM_AGENTS


def test_agent_knowing_only_the_closed_exit_learns_no_other():
    """Familiarity holds: a closed entrance does not reveal the other door.

    Such an agent knows only its spawn area, already visited, and the closed
    door. Under no_known_exit "explore" it has nowhere to explore or wander,
    so it keeps its route and waits at the closed door.
    """
    scenario = _scenario(
        {"west": {"closed_after_s": T_CLOSE_S}},
        familiarity=0.0,
        entrance="west",
        no_known_exit="explore",
    )
    run = _run(scenario, reroute_config=REROUTE)
    doors = [(t, door) for t, door in run["departures"] if t < MAX_TIME_S - 1.0]
    assert all(door == "west" and t <= T_CLOSE_S + FRAME_S for t, door in doors)
    assert run["remaining"] > 0
    assert not run["routes"]
    waiting = [(x, y) for t, x, y in run["last_seen"] if t >= MAX_TIME_S - 1.0]
    assert len(waiting) == run["remaining"]
    west = DOORS["west"]
    assert all(west.distance(Point(x, y)) <= WEST_POCKET_M for x, y in waiting)


@pytest.mark.parametrize("mode", list(RUN_MODES))
def test_agent_knowing_only_the_closed_exit_takes_the_default_route(mode):
    """Under the default no_known_exit the agent takes the open door (#610).

    The closed entrance leaves it no known exit, so it follows the default
    route: the nearest open exit on foot, which is not in its map. A run
    without rerouting does the same (#395).
    """
    scenario = _scenario(
        {"west": {"closed_after_s": T_CLOSE_S}}, familiarity=0.0, entrance="west"
    )
    run = _run(scenario, **RUN_MODES[mode])
    late = [door for t, door in run["departures"] if t > T_CLOSE_S + FRAME_S]
    assert late and set(late) <= {"east"}
    default = [r for r in run["routes"] if r["reason"] == "default_route"]
    assert default
    assert {(r["old_exit"], r["new_exit"]) for r in default} == {("west", "east")}
    assert all(r["time_s"] >= T_CLOSE_S for r in default)


def test_unscheduled_exits_are_always_open():
    node = StageNode("e", 0.0, 0.0, "exit")
    assert node.is_open(0.0) and node.is_open(1e9)
    graph = StageGraph(nodes={"e": node})
    assert without_closed_stages(graph, 5.0) is graph


def test_schedule_window_is_half_open():
    node = StageNode("e", 0.0, 0.0, "exit", open_from_s=2.0, closed_after_s=5.0)
    assert [node.is_open(t) for t in (1.99, 2.0, 4.99, 5.0)] == [
        False,
        True,
        True,
        False,
    ]


@pytest.mark.parametrize(
    "schedule, match",
    [
        ({"closed_after_s": -1.0}, "closed_after_s must be finite and >= 0"),
        ({"open_from_s": math.inf}, "open_from_s must be finite and >= 0"),
        ({"open_from_s": "5"}, "open_from_s must be a number"),
        ({"open_from_s": True}, "open_from_s must be a number"),
        (
            {"open_from_s": 5.0, "closed_after_s": 5.0},
            "closed_after_s must be greater than open_from_s",
        ),
    ],
)
def test_invalid_schedule_is_rejected(schedule, match):
    with pytest.raises(ValueError, match=match):
        run_scenario(_scenario({"west": schedule}), reroute_config=REROUTE)


@pytest.mark.parametrize("kwargs", [{}, {"smoke_blind": True}])
def test_schedule_without_rerouting_runs(kwargs):
    """A scheduled exit no longer needs rerouting (#395)."""
    scenario = _scenario({"west": {"closed_after_s": T_CLOSE_S}})
    run = _run(scenario, **kwargs)
    assert run["evacuated"] == NUM_AGENTS


def test_schedule_with_replay_exits_is_rejected():
    scenario = _scenario({"west": {"closed_after_s": T_CLOSE_S}})
    with pytest.raises(ValueError, match="--replay-exits cannot be combined"):
        run_scenario(scenario, reroute_config=REROUTE, replay_exits={})


@pytest.mark.parametrize("mode", list(RUN_MODES))
def test_journey_agent_with_schedule_is_rejected(mode):
    """An agent on a JuPedSim journey leaves by a JuPedSim exit stage."""
    scenario = _scenario({"west": {"closed_after_s": T_CLOSE_S}})
    raw = scenario.raw
    room = raw["distributions"].pop("room")
    # Keep the two spawn areas apart; placement does not check across them.
    room["coordinates"] = _coords(box(0.3, 0.3, 15.0, WIDTH_M - 0.3))
    lobby = {
        "type": "polygon",
        "coordinates": _coords(box(20.0, 1.0, 25.0, 4.0)),
        "parameters": dict(room["parameters"], number=5),
    }
    # Journeys name spawn areas by the editor's "jps-distributions_" ids.
    raw["distributions"] = {"jps-distributions_0": room, "jps-distributions_1": lobby}
    raw["journeys"] = [{"id": "j0", "stages": ["jps-distributions_0", "east"]}]
    raw["transitions"] = [
        {"from": "jps-distributions_0", "to": "east", "journey_id": "j0"}
    ]
    with pytest.raises(ValueError, match="walks a JuPedSim journey"):
        run_scenario(scenario, **RUN_MODES[mode])


# ── Runs without a reroute pass (#395) ────────────────────────────────

# A third door, in the middle of the north wall: nearer than the east door
# to every agent bound west.
NORTH_DOOR = box(
    LENGTH_M / 2.0 - DOOR_M / 2.0,
    WIDTH_M,
    LENGTH_M / 2.0 + DOOR_M / 2.0,
    WIDTH_M + DOOR_DEPTH_M,
)
# Dense smoke over the north door from the start, clear of the straight
# lines from the west half of the room to the east door.
NORTH_SMOKE = (
    LENGTH_M / 2.0 - 1.5,
    LENGTH_M / 2.0 + 1.5,
    WIDTH_M - 1.5,
    WIDTH_M + DOOR_DEPTH_M,
)
NORTH_SMOKE_PER_M = 5.0


class _NorthSmoke:
    """Extinction NORTH_SMOKE_PER_M over NORTH_SMOKE, zero elsewhere."""

    def sample_extinction(self, time_s: float, x: float, y: float) -> float:
        x0, x1, y0, y1 = NORTH_SMOKE
        return NORTH_SMOKE_PER_M if x0 <= x <= x1 and y0 <= y <= y1 else 0.0


def _smoke_model():
    from pyfds_evac.core.smoke_speed import SmokeSpeedConfig, SmokeSpeedModel

    return SmokeSpeedModel(
        _NorthSmoke(), SmokeSpeedConfig(fds_dir=".", update_interval_s=1.0)
    )


def _three_door_closing_run(**kwargs) -> dict:
    doors = {**DOORS, "north": NORTH_DOOR}
    scenario = _scenario({"west": {"closed_after_s": T_CLOSE_S}}, doors=doors)
    return _run(scenario, smoke_speed_model=_smoke_model(), **kwargs)


def _closed_switches(run: dict) -> set[tuple[str, str]]:
    return {
        (r["old_exit"], r["new_exit"])
        for r in run["routes"]
        if r["reason"] == "exit_closed"
    }


def test_closure_rechoice_without_rerouting_sees_the_smoke():
    """Rerouting off changes when routes are re-ranked, not how (D5).

    The north door is nearer than the east door to every agent bound west,
    and it is filled with smoke: with rerouting off the re-choice avoids it.
    """
    run = _three_door_closing_run(reroute_config=None)
    assert _closed_switches(run) == {("west", "east")}


def test_smoke_blind_closure_rechoice_is_made_in_clear_air():
    """A smoke-blind agent re-chooses as in clear air: the nearer north door."""
    run = _three_door_closing_run(smoke_blind=True)
    assert ("west", "north") in _closed_switches(run)


def test_smoke_blind_closure_run_walks_as_the_run_without_fire():
    """Smoke-blind changes no motion and no choice, closure included.

    The smoke fills the open east door, the one every agent bound west
    switches to.
    """

    class _EastSmoke:
        def sample_extinction(self, time_s: float, x: float, y: float) -> float:
            return NORTH_SMOKE_PER_M if x >= LENGTH_M - 6.0 else 0.0

    from pyfds_evac.core.smoke_speed import SmokeSpeedConfig, SmokeSpeedModel

    smoke = SmokeSpeedModel(
        _EastSmoke(), SmokeSpeedConfig(fds_dir=".", update_interval_s=1.0)
    )
    scenario = _scenario({"west": {"closed_after_s": T_CLOSE_S}})
    blind = _run(scenario, smoke_blind=True, smoke_speed_model=smoke)
    no_fire = _run(scenario, reroute_config=None)
    assert blind["last_seen"] == no_fire["last_seen"]
    # JuPedSim numbers agents across runs; the rows are compared without ids.
    rows = [
        [{k: v for k, v in r.items() if k != "agent_id"} for r in run["routes"]]
        for run in (blind, no_fire)
    ]
    assert rows[0] == rows[1]
    assert _closed_switches(blind) == {("west", "east")}


def test_closure_rechoice_uses_the_map_the_agent_holds(monkeypatch):
    """The re-choice adds no perception step of its own (D6, R-A).

    Without rerouting the map grows only on arrival at a stage: the agents
    learn the north door at the checkpoint and switch to it by name, while
    nothing expands their map from sight.
    """
    import pyfds_evac.core.scenario as scenario_module

    calls: dict[str, int] = {"sight": 0, "arrival": 0}

    def _spy(name, wrapped):
        def _counted(*args, **kwargs):
            calls[name] += 1
            return wrapped(*args, **kwargs)

        return _counted

    for name, attr in (
        ("sight", "expand_from_visibility"),
        ("arrival", "expand_on_arrival"),
    ):
        monkeypatch.setattr(
            scenario_module, attr, _spy(name, getattr(scenario_module, attr))
        )
    t_close = 12.0
    run = _run(_checkpoint_scenario(t_close), reroute_config=None)
    assert {(r["new_exit"], r["reason"]) for r in run["routes"]} == {
        ("north", "exit_closed")
    }
    assert calls["arrival"] > 0
    assert calls["sight"] == 0
    # The spy sees the expansion the reroute pass makes.
    _run(_checkpoint_scenario(t_close), reroute_config=REROUTE)
    assert calls["sight"] > 0


@pytest.mark.parametrize("mode", NO_REROUTE_MODES)
def test_exit_opening_changes_no_choice_without_rerouting(mode):
    """Nobody re-decides when an exit opens (D7).

    Agents by the east door choose the west door at spawn, while the east
    one is shut; it opens long before they reach the west door.
    """
    scenario = _scenario({"east": {"open_from_s": T_OPEN_S}})
    near_east = box(LENGTH_M - 8.0, 0.3, LENGTH_M - 0.3, WIDTH_M - 0.3)
    scenario.raw["distributions"]["room"]["coordinates"] = _coords(near_east)
    run = _run(scenario, **RUN_MODES[mode])
    assert run["routes"] == []
    assert {door for _t, door in run["departures"]} == {"west"}
    assert run["evacuated"] == NUM_AGENTS


@pytest.mark.parametrize("mode", NO_REROUTE_MODES)
def test_agents_wait_when_every_exit_is_closed(mode):
    """With every exit closed the agents stay, and nothing is recorded."""
    schedule = {"closed_after_s": T_CLOSE_S}
    scenario = _scenario({"west": schedule, "east": schedule})
    scenario.sim_params["max_simulation_time"] = 20.0
    run = _run(scenario, **RUN_MODES[mode])
    late = [t for t, door in run["departures"] if door and t < 20.0 - 1.0]
    assert all(t <= T_CLOSE_S + FRAME_S for t in late)
    assert run["remaining"] > 0
    assert run["routes"] == []


def test_run_without_schedule_or_rerouting_records_no_routes():
    """A run without rerouting and without a schedule is left as it was."""
    run = _run(_scenario({}), reroute_config=None)
    assert run["routes"] == []
    assert run["evacuated"] == NUM_AGENTS


@pytest.mark.parametrize("mode", list(RUN_MODES))
def test_flow_spawned_journey_agent_with_schedule_is_rejected(mode, monkeypatch):
    """A flow agent that walks a JuPedSim journey is refused in every mode.

    The run places nobody at t=0, so only the check that follows a flow
    spawn can see the agent. The agent is handed to JuPedSim by marking its
    path state as a journey.
    """
    import pyfds_evac.core.simulation_init as simulation_init

    build = simulation_init.build_agent_path_state

    def _journey_state(*args, **kwargs):
        return {**build(*args, **kwargs), "mode": "journey"}

    monkeypatch.setattr(simulation_init, "build_agent_path_state", _journey_state)
    scenario = _scenario(
        {"west": {"closed_after_s": T_CLOSE_S}},
        number=5,
        use_flow_spawning=True,
        flow_start_time=1.0,
        flow_end_time=2.0,
    )
    raw = scenario.raw
    raw["distributions"] = {"jps-distributions_0": raw["distributions"].pop("room")}
    raw["journeys"] = [{"id": "j0", "stages": ["jps-distributions_0", "east"]}]
    raw["transitions"] = [
        {"from": "jps-distributions_0", "to": "east", "journey_id": "j0"}
    ]
    with pytest.raises(ValueError, match="walks a JuPedSim journey"):
        run_scenario(scenario, **RUN_MODES[mode])


# ── Closure rules shared by both modes (#395 R-A to R-C) ──────────────

REROUTE_AND_NOT = ["reroute", "no_reroute"]
CHECKPOINT_ID = "jps-checkpoints_0"
SPAWN_ID = "jps-distributions_0"


def _checkpoint_scenario(
    t_close: float, waiting_time: float = 0.0, number: int = 10
) -> Scenario:
    """Agents who know only the west door walk to it through a checkpoint.

    The checkpoint spans the room, west of the spawn area and east of the
    north door. Without a visibility model, arriving at it reveals every
    stage it leads to, the north door included.
    """
    doors = {"west": DOORS["west"], "north": NORTH_DOOR}
    scenario = _scenario(
        {"west": {"closed_after_s": t_close}},
        doors=doors,
        familiarity=0.0,
        entrance="west",
        number=number,
    )
    raw = scenario.raw
    room = raw["distributions"].pop("room")
    room["coordinates"] = _coords(box(22.0, 1.0, LENGTH_M - 1.0, WIDTH_M - 1.0))
    raw["distributions"] = {SPAWN_ID: room}
    raw["checkpoints"] = {
        CHECKPOINT_ID: {
            "type": "polygon",
            "coordinates": _coords(box(16.0, 0.0, 18.0, WIDTH_M)),
            "waiting_time": waiting_time,
            "waiting_time_distribution": "constant",
            "speed_factor": 1.0,
            "enable_throughput_throttling": False,
        }
    }
    raw["journeys"] = [{"id": "j0", "stages": [SPAWN_ID, CHECKPOINT_ID, "west"]}]
    raw["transitions"] = [
        {"from": SPAWN_ID, "to": CHECKPOINT_ID, "journey_id": "j0"},
        {"from": CHECKPOINT_ID, "to": "west", "journey_id": "j0"},
        {"from": CHECKPOINT_ID, "to": "north", "journey_id": "j1"},
    ]
    return scenario


def _north_departures(run: dict) -> int:
    return sum(
        1
        for _t, x, y in run["last_seen"]
        if NORTH_DOOR.distance(Point(x, y)) <= AT_DOOR_M
    )


@pytest.mark.parametrize("mode", REROUTE_AND_NOT)
def test_closure_rechoice_uses_exits_learned_at_a_checkpoint(mode):
    """The map at the closure holds what the agent learned on the way (R-A).

    The agents know only the west door at spawn and learn the north door on
    arriving at the checkpoint. When the west door closes they switch to
    it as an exit they know, not by the default route.
    """
    t_close = 12.0
    run = _run(_checkpoint_scenario(t_close), **RUN_MODES[mode])
    rows = {(r["old_exit"], r["new_exit"], r["reason"]) for r in run["routes"]}
    assert rows == {("west", "north", "exit_closed")}
    assert all(t_close <= r["time_s"] <= t_close + 1.0 for r in run["routes"])
    assert run["evacuated"] == 10
    assert _north_departures(run) == 10


@pytest.mark.parametrize("mode", REROUTE_AND_NOT)
def test_agent_waiting_at_a_checkpoint_rechooses_when_its_exit_closes(mode):
    """An agent in the middle of its wait at a checkpoint re-decides too.

    The agents reach the checkpoint within 10 s and wait 10 s there; the
    west door closes during the wait. An agent learns at a checkpoint when
    its wait ends, so it does not know the north door yet: it takes it as
    the nearest open exit on foot.
    """
    t_close = 12.0
    scenario = _checkpoint_scenario(t_close, waiting_time=10.0)
    run = _run(scenario, **RUN_MODES[mode])
    rows = {(r["old_exit"], r["new_exit"], r["reason"]) for r in run["routes"]}
    assert rows == {("west", "north", "default_route")}
    assert all(t_close <= r["time_s"] <= t_close + 1.0 for r in run["routes"])
    assert run["evacuated"] == 10
    assert _north_departures(run) == 10


@pytest.mark.parametrize("mode", REROUTE_AND_NOT)
def test_agent_standing_in_the_closed_exit_leaves_when_another_opens(mode):
    """An agent that reached its exit after it closed walks on later.

    The crowd starts by the west door, which closes at 2 s while the east
    door is shut until 6 s. Agents that reach the west door meanwhile stand
    in it; at the first check after 6 s they head for the east door.
    """
    t_close, t_open = 2.0, 6.0
    scenario = _scenario(
        {"west": {"closed_after_s": t_close}, "east": {"open_from_s": t_open}}
    )
    by_west = _coords(box(0.3, 2.0, 5.0, WIDTH_M - 2.0))
    scenario.raw["distributions"]["room"]["coordinates"] = by_west
    run = _run(scenario, with_frames=True, **RUN_MODES[mode])
    standing = [
        (t, x, y)
        for t, x, y in run["frames"]
        if t_close + 1.0 < t < t_open
        and DOORS["west"].distance(Point(x, y)) <= AT_DOOR_M
    ]
    assert standing, "nobody stood in the closed west door"
    late = [door for t, door in run["departures"] if t > t_close + FRAME_S]
    assert late and set(late) == {"east"}
    switches = [r for r in run["routes"] if r["new_exit"] == "east"]
    assert switches
    assert all(t_open <= r["time_s"] <= t_open + 1.0 for r in switches)
    assert {(r["old_exit"], r["reason"]) for r in switches} == {("west", "exit_closed")}
    assert run["evacuated"] == NUM_AGENTS


@pytest.mark.parametrize("mode", REROUTE_AND_NOT)
def test_sequential_closures_leave_from_the_exit_walked_to(mode):
    """Each closure row names the exit the agent was walking to (R-B).

    The agents know only the west door. It closes at T1, and their default
    route takes them to the nearest open door on foot: the north one, or the
    east one for agents near it. The north door closes at T2 and its agents
    go on to the east door. No row is ``initial``, and the second closure's
    rows have ``old_exit`` north, not empty.
    """
    t1, t2 = T_CLOSE_S, 9.0
    doors = {**DOORS, "north": NORTH_DOOR}
    scenario = _scenario(
        {"west": {"closed_after_s": t1}, "north": {"closed_after_s": t2}},
        doors=doors,
        familiarity=0.0,
        entrance="west",
    )
    run = _run(scenario, **RUN_MODES[mode])
    routes = run["routes"]
    assert routes
    assert {r["reason"] for r in routes} == {"default_route"}
    first = [r for r in routes if r["old_exit"] == "west"]
    second = [r for r in routes if r["old_exit"] == "north"]
    assert first and second
    assert len(first) + len(second) == len(routes)
    assert "north" in {r["new_exit"] for r in first}
    assert {r["new_exit"] for r in first} <= {"north", "east"}
    assert all(t1 <= r["time_s"] <= t1 + 1.0 for r in first)
    assert {r["new_exit"] for r in second} == {"east"}
    assert all(t2 <= r["time_s"] <= t2 + 1.0 for r in second)
    assert run["evacuated"] == NUM_AGENTS


def _east_smoke_model():
    from pyfds_evac.core.smoke_speed import SmokeSpeedConfig, SmokeSpeedModel

    class _EastSmoke:
        def sample_extinction(self, time_s: float, x: float, y: float) -> float:
            return NORTH_SMOKE_PER_M if x >= LENGTH_M - 6.0 else 0.0

    return SmokeSpeedModel(
        _EastSmoke(), SmokeSpeedConfig(fds_dir=".", update_interval_s=1.0)
    )


@pytest.mark.parametrize("mode", REROUTE_AND_NOT)
def test_closure_onto_a_refused_route_is_labelled_exit_closed(mode):
    """The closure, not the fallback, is the reason for the switch (R-C).

    Smoke refuses every route to the east door, the only one left open, so
    the agents bound west are given it as a gate fallback.
    """
    scenario = _scenario({"west": {"closed_after_s": T_CLOSE_S}})
    run = _run(scenario, smoke_speed_model=_east_smoke_model(), **RUN_MODES[mode])
    closure = [r for r in run["routes"] if r["old_exit"] == "west"]
    assert closure
    assert {(r["new_exit"], r["reason"]) for r in closure} == {("east", "exit_closed")}
    assert not [r for r in run["routes"] if r["reason"] == "fallback"]
