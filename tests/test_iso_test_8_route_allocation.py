"""ISO 20414:2020 Test 8 (Table 9): exit route allocation.

Setup of the test: a corridor with rooms (Figure 5), pre-evacuation time 0 s.
Occupants in rooms 1-4 and 7-10 are allocated to the main exit, the others to
the secondary exit. Expected result: allocated occupants use their exits. The
tester states whether the allocation is user-defined or predictive.

The standard text is not in the repository; the layout below is read from the
issue (#844) and from JuPedSim's implementation of the test,
``TestIso08RouteAllocation`` in ``tests/vv/test_iso.py`` of
PedestrianDynamics/jupedsim-web-community, with its scenario file
``standards/iso/scenario_files/Iso-08-route-allocation.zip`` (commit
41ea11215b2519f72c6f0100080bbd1fbe9f9cc8).

Reading of the geometry (metres): a corridor 0.9 m wide runs west to east
(y from -0.6 to 0.3) with six rooms on its north side and six on its south
side, each entered through a 0.8 m door in the middle of its corridor wall.
Rooms are numbered 1-6 along the north side and 7-12 along the south side,
west to east. That numbering is an assumption (the numbering of Figure 5 is
not in the repository); it reproduces the allocation of Table 9: rooms 1-4
and 7-10 are the four western rooms of each side, rooms 5, 6, 11 and 12 the
two eastern ones. The rooms are 2.8 m to 2.9 m wide and 3.8 m deep; room 3 is
narrower (1.9 m). The main exit is the north end of a 1.1 m wide passage
between rooms 2 and 3 (x from -3.8 m to -2.7 m); the secondary exit is the
east end of the corridor.

Counts: two occupants per room and one in room 3, which is 1.9 m wide where
the others are 2.8 m to 2.9 m. That gives 11 x 2 + 1 = 23, the number of
Table 9, with 15 occupants in the eight main-exit rooms and 8 in the four
secondary-exit rooms. The count follows the JuPedSim file; Figure 5 itself
was not checked. All occupants have radius 0.15 m and v0 = 1.3 m/s, as in
that file.

Allocation is user-defined: each room's distribution is tied to its exit by a
journey in the scenario JSON, and the model does not choose the exit from the
geometry. A journey's exit is a preference unless the journey sets
``"allocation": "hard"`` (#854): an agent keeps it unless the other exit costs
less than ``exit_switch_anchor`` (0.9) times as much. The checks below that
the allocation holds run with ``"allocation": "hard"`` on every journey, so
they test the allocation itself. At seed 42 the preference reading holds too,
by a thin margin only: rooms 4 and 10 start at a ratio of 0.913 to 0.926 of
the cost of the secondary exit over that of the main exit and come no lower
than 0.904 to 0.918 along the walk, which makes it a
fragile check; the preference rule is covered by occupants pinned to one
position instead. The allocation is partly against distance: the occupants of rooms 4
and 10 (x about 0.9 m) are allocated to the main exit, about 9 m from the
room door by the passage, although the secondary exit is about 8 m away
along the corridor (agents: 10.7 m against 9.8 m of path).
Without the journeys (predictive reading: pyFDS-Evac picks the exit by its
route cost) the occupants of rooms 4 and 10 take the secondary exit, which
differs from Table 9 for 4 of the 23; the other rooms agree. So pyFDS-Evac
passes the user-defined reading, and the predictive reading only where the
nearest exit is the allocated one.

Measurements, per room (an agent's room is the spawn area holding its first
trajectory position): the exit recorded in ``ScenarioResult.exit_history``,
and independently the exit nearest to each agent's last trajectory position.
Both must equal the allocated exit for every agent. The case is run twice:
rerouting off (deterministic allocation, 100 % compliance expected) and
rerouting on in clear air with the default interval (no smoke, no dose:
expected no switch). Any switch would be listed with its ``switch_reason``.

Pinned occupants: one occupant of room 4 at the east end of the room, 8.9 m
from the secondary exit and 10.0 m from the main one by the navmesh (ratio
0.885, below the anchor), takes the secondary exit under the preference rule
and keeps the main one under ``"allocation": "hard"``.

Fire variant (issue #850, allocation under smoke). A step extinction field
switches on at t = 5 s in the main passage, a box x in [-3.8, -2.7] m,
y in [0.3, 2.3] m (2.0 m long), K = 5 /m, Lund speed law; the router samples
every 0.25 m and re-evaluates every 1 s. The box lies on main-exit routes only.
Under the gate model a route is refused above tau = K_ave x L > tau_max = 6,
and an exit is left when its tau exceeds the rival's by more than
tau_max x tau_deadband = 0.6.

- A main route entered from the corridor: tau = 5 x 2.0 = 10, refused;
  the secondary route has tau = 0. By default the allocation is a preference
  and yields: occupants not yet in the passage switch to the secondary exit
  (``smoke_reroute``) on the first pass at or after t_on, within 1 s + 0.03 s.
- Occupants already past the box (y > 2.3 m) have tau = 0 and keep main.
- Under ``"allocation": "hard"`` nobody moves: the route graph holds only the
  allocated exit, and the agents walk the smoke slowed (D5).
"""

from __future__ import annotations

import contextlib
import io

import pytest
from shapely.geometry import Point, box
from shapely.ops import unary_union

from pyfds_evac.config.parameters import REROUTE_INTERVAL_S
from pyfds_evac.core.route_graph import RerouteConfig, RouteCostConfig
from pyfds_evac.core.scenario import Scenario, run_scenario
from pyfds_evac.core.smoke_speed import SmokeSpeedConfig, SmokeSpeedModel

pytestmark = [pytest.mark.iso20414, pytest.mark.nist_tn1822]

SEED = 42
RADIUS_M = 0.15
SPEED_MPS = 1.3
MAX_TIME_S = 120.0
DOOR_WIDTH_M = 0.8
WALL_M = 0.1
SPAWN_MARGIN_M = 0.3
PIN_HALF_M = 0.2
CORRIDOR = (-9.9, -0.6, 9.0, 0.3)
MAIN = "main"
SECONDARY = "secondary"

# Room number -> (x_min, x_max, north side?) of the room interior.
ROOMS = {
    1: (-9.8, -6.9, True),
    2: (-6.8, -4.0, True),
    3: (-2.6, -0.7, True),
    4: (-0.5, 2.3, True),
    5: (2.5, 5.3, True),
    6: (5.4, 8.3, True),
    7: (-9.8, -6.9, False),
    8: (-6.8, -3.9, False),
    9: (-3.8, -0.7, False),
    10: (-0.5, 2.3, False),
    11: (2.4, 5.3, False),
    12: (5.4, 8.3, False),
}
OCCUPANTS = {room: 2 for room in ROOMS} | {3: 1}
MAIN_ROOMS = (1, 2, 3, 4, 7, 8, 9, 10)
ALLOCATION = {room: MAIN if room in MAIN_ROOMS else SECONDARY for room in ROOMS}
ROOM_DEPTH_NORTH = (0.4, 4.2)
ROOM_DEPTH_SOUTH = (-4.5, -0.7)
MAIN_PASSAGE = (-3.8, -2.7)
EXITS = {
    MAIN: box(-3.7, 5.0, -2.8, 5.4),
    SECONDARY: box(8.7, -0.3, 8.9, 0.1),
}
# Fire variant: smoke box in the main passage, switched on at SMOKE_ON_S.
SMOKE_BOX = (-3.8, 0.3, -2.7, 2.3)
SMOKE_K_PER_M = 5.0
SMOKE_ON_S = 5.0
SAMPLING_STEP_M = 0.25
FRAME_RATE = 10.0
# Stagger offset (at most 0.02 s) plus one step.
SWITCH_SLACK_S = 0.03


class _BoxSmoke:
    """Step extinction field: K inside ``SMOKE_BOX`` from ``SMOKE_ON_S`` on."""

    def __init__(self, k: float) -> None:
        self.k = k

    def sample_extinction(self, t: float, x: float, y: float) -> float:
        x0, y0, x1, y1 = SMOKE_BOX
        inside = x0 <= x <= x1 and y0 <= y <= y1
        return self.k if t >= SMOKE_ON_S and inside else 0.0


def _room_box(room: int):
    x0, x1, north = ROOMS[room]
    y0, y1 = ROOM_DEPTH_NORTH if north else ROOM_DEPTH_SOUTH
    return box(x0, y0, x1, y1)


def _door_box(room: int):
    x0, x1, north = ROOMS[room]
    xc = (x0 + x1) / 2.0
    lo, hi = xc - DOOR_WIDTH_M / 2.0, xc + DOOR_WIDTH_M / 2.0
    if north:
        return box(lo, CORRIDOR[3] - WALL_M, hi, ROOM_DEPTH_NORTH[0] + WALL_M)
    return box(lo, ROOM_DEPTH_SOUTH[1] - WALL_M, hi, CORRIDOR[1] + WALL_M)


def _walkable():
    x0, y0, x1, y1 = CORRIDOR
    parts = [box(x0, y0, x1, y1)]
    parts += [_room_box(room) for room in ROOMS]
    parts += [_door_box(room) for room in ROOMS]
    parts.append(box(MAIN_PASSAGE[0], y1 - WALL_M, MAIN_PASSAGE[1], 5.5))
    return unary_union(parts)


def _spawn_area(room: int):
    x0, y0, x1, y1 = _room_box(room).bounds
    m = SPAWN_MARGIN_M
    return box(x0 + m, y0 + m, x1 - m, y1 - m)


def _coords(polygon) -> list[list[float]]:
    return [[x, y] for x, y in polygon.exterior.coords]


def _distribution(room: int, pin: tuple[float, float] | None = None) -> dict:
    """The room's spawn area, or one occupant at *pin*."""
    area = _spawn_area(room)
    if pin is not None:
        area = box(
            pin[0] - PIN_HALF_M, pin[1] - PIN_HALF_M, *(p + PIN_HALF_M for p in pin)
        )
    return {
        "type": "polygon",
        "coordinates": _coords(area),
        "parameters": {
            "number": 1 if pin is not None else OCCUPANTS[room],
            "radius": RADIUS_M,
            "v0": SPEED_MPS,
            "use_flow_spawning": False,
            "distribution_mode": "by_number",
            "use_premovement": False,
            "radius_distribution": "constant",
            "v0_distribution": "constant",
        },
    }


def _journey(
    room: int, allocation: dict[int, str], mode: str | None = None
) -> tuple[dict, dict]:
    name = f"room_{room}"
    exit_id = allocation[room]
    transition = {"from": name, "to": exit_id, "journey_id": f"journey_{room}"}
    journey = {
        "id": f"journey_{room}",
        "stages": [name, exit_id],
        "transitions": [transition],
    }
    if mode is not None:
        journey["allocation"] = mode
    return journey, transition


def _scenario(
    allocation: dict[int, str] = ALLOCATION,
    journeys: bool = True,
    mode: str | None = None,
    pins: dict[int, tuple[float, float]] | None = None,
) -> Scenario:
    """The test deck. *mode* is the journeys' ``allocation`` value; *pins* maps a
    room to the one position its single occupant takes, and drops every other room.
    """
    rooms = list(pins) if pins else list(ROOMS)
    pairs = [_journey(room, allocation, mode) for room in rooms] if journeys else []
    sim_params = {
        "max_simulation_time": MAX_TIME_S,
        "model_type": "CollisionFreeSpeedModel",
    }
    raw = {
        "project_version": "2.0",
        "config": {
            "simulation_settings": {
                "simulationParams": sim_params,
                "numberOfSimulations": 1,
                "baseSeed": SEED,
            },
            "ui_state": {"useShortestPaths": False},
        },
        "exits": {
            name: {
                "type": "polygon",
                "coordinates": _coords(poly),
                "enable_throughput_throttling": False,
                "max_throughput": 0,
            }
            for name, poly in EXITS.items()
        },
        "distributions": {
            f"room_{room}": _distribution(room, (pins or {}).get(room))
            for room in rooms
        },
        "checkpoints": {},
        "zones": {},
        "journeys": [journey for journey, _ in pairs],
        "transitions": [transition for _, transition in pairs],
    }
    return Scenario(
        raw=raw,
        walkable_area_wkt=_walkable().wkt,
        model_type="CollisionFreeSpeedModel",
        seed=SEED,
        sim_params=sim_params,
        source_path=None,
    )


def _room_of(x: float, y: float) -> int:
    """The room whose spawn area holds the first position of an agent."""
    point = Point(x, y)
    return next(room for room in ROOMS if _spawn_area(room).covers(point))


def _nearest_exit(x: float, y: float) -> str:
    return min(EXITS, key=lambda name: EXITS[name].distance(Point(x, y)))


def _run(
    rerouting: bool,
    allocation: dict[int, str] = ALLOCATION,
    journeys: bool = True,
    mode: str | None = None,
    pins: dict[int, tuple[float, float]] | None = None,
    smoke_anticipate: bool | None = None,
    smoke_k: float = SMOKE_K_PER_M,
) -> dict:
    """Run the deck. *smoke_anticipate* None means clear air; a bool adds the box
    smoke field with that ``anticipate`` setting, re-evaluated every second."""
    smoke = smoke_anticipate is not None
    params = {"sampling_step_m": SAMPLING_STEP_M, "anticipate": smoke_anticipate}
    reroute = (
        RerouteConfig(
            reevaluation_interval_s=REROUTE_INTERVAL_S,
            cost_config=RouteCostConfig.from_routing_params(params if smoke else {}),
        )
        if rerouting
        else None
    )
    model = (
        SmokeSpeedModel(
            _BoxSmoke(smoke_k),
            SmokeSpeedConfig(fds_dir=".", speed_law="lund", update_interval_s=1.0),
        )
        if smoke
        else None
    )
    with contextlib.redirect_stdout(io.StringIO()):
        result = run_scenario(
            _scenario(allocation, journeys, mode, pins),
            seed=SEED,
            reroute_config=reroute,
            smoke_speed_model=model,
        )
    try:
        df = result.trajectory_dataframe().sort_values(["id", "frame"])
        last = df.groupby("id").last()
        final = {int(i): _nearest_exit(row.x, row.y) for i, row in last.iterrows()}
        home = {
            int(i): _room_of(row.x, row.y)
            for i, row in df.groupby("id").first().iterrows()
        }
        per_room: dict[int, dict[str, list[str]]] = {
            room: {"assigned": [], "final": []} for room in ROOMS
        }
        for rec in result.exit_history or []:
            room = home[rec["agent_id"]]
            per_room[room]["assigned"].append(rec["exit_id"])
            per_room[room]["final"].append(final[rec["agent_id"]])
        at_t_on = df[df.frame >= round(SMOKE_ON_S * FRAME_RATE)].groupby("id").first()
        return {
            "per_room": per_room,
            "home": home,
            "t_end_s": float(df.frame.max()) / FRAME_RATE,
            "at_t_on": {int(i): (r.x, r.y) for i, r in at_t_on.iterrows()},
            "evacuated": result.agents_evacuated,
            "remaining": result.agents_remaining,
            "total": result.total_agents,
            "switches": list(result.route_history or []),
            "has_history": result.route_history is not None,
        }
    finally:
        result.cleanup()


@pytest.fixture(scope="module")
def runs() -> dict[str, dict]:
    return {
        "off": _run(rerouting=False, mode="hard"),
        "on": _run(rerouting=True, mode="hard"),
    }


def test_layout_has_23_occupants_and_the_table_9_allocation():
    assert sum(OCCUPANTS.values()) == 23
    assert sorted(r for r, e in ALLOCATION.items() if e == MAIN) == list(MAIN_ROOMS)
    assert sum(n for r, n in OCCUPANTS.items() if ALLOCATION[r] == MAIN) == 15
    assert sum(n for r, n in OCCUPANTS.items() if ALLOCATION[r] == SECONDARY) == 8


@pytest.mark.parametrize("mode", ["off", "on"])
def test_every_occupant_uses_the_allocated_exit(runs, mode):
    run = runs[mode]
    assert run["total"] == 23
    assert run["evacuated"] == 23
    assert run["remaining"] == 0
    for room, seen in run["per_room"].items():
        want = [ALLOCATION[room]] * OCCUPANTS[room]
        assert seen["assigned"] == want, f"room {room}, rerouting {mode}"
        assert seen["final"] == want, f"room {room}, rerouting {mode}"


def test_rerouting_off_records_no_route_history(runs):
    assert not runs["off"]["has_history"]


def test_rerouting_on_in_clear_air_switches_nobody(runs):
    """The pass runs on hard allocations and finds no reason to leave them.

    Under ``"allocation": "hard"`` the route graph holds only the allocated
    exit, so this shows that rerouting does not drop a journey's exit in clear
    air. That an allocation yields to a clearly cheaper exit, and holds against
    a slightly cheaper one, is shown by the pinned occupants below.
    """
    run = runs["on"]
    assert run["has_history"]
    reasons = [(s["agent_id"], s["reason"]) for s in run["switches"]]
    assert not run["switches"], f"unexpected switches: {reasons}"


def test_predictive_reading_differs_in_rooms_4_and_10():
    """No journeys: the exit comes from the route cost, as for any routed agent.

    Recorded, not a requirement of the standard: it shows that the allocation
    above comes from the journeys and not from the layout.
    """
    run = _run(rerouting=True, journeys=False)
    assert run["evacuated"] == 23
    differing = {
        room
        for room, seen in run["per_room"].items()
        if seen["assigned"] != [ALLOCATION[room]] * OCCUPANTS[room]
    }
    assert differing == {4, 10}
    for room in (4, 10):
        assert run["per_room"][room]["final"] == [SECONDARY] * 2


PINNED_ROOM_4 = {4: (1.95, 0.85)}


@pytest.mark.parametrize("rerouting", [False, True], ids=["off", "on"])
def test_occupant_below_the_anchor_takes_the_secondary_exit(rerouting):
    """Secondary 8.9 m, main 10.0 m: 0.885 of the allocated cost, below 0.9."""
    run = _run(rerouting=rerouting, pins=PINNED_ROOM_4)
    seen = run["per_room"][4]
    assert seen["assigned"] == [SECONDARY]
    assert seen["final"] == [SECONDARY]
    assert run["evacuated"] == 1


@pytest.mark.parametrize("rerouting", [False, True], ids=["off", "on"])
def test_hard_allocation_keeps_the_occupant_below_the_anchor(rerouting):
    run = _run(rerouting=rerouting, mode="hard", pins=PINNED_ROOM_4)
    seen = run["per_room"][4]
    assert seen["assigned"] == [MAIN]
    assert seen["final"] == [MAIN]
    assert not run["switches"]


def _group(run: dict, agent: int) -> str:
    """Where a main-allocated agent stands at the first frame at or after t_on."""
    x, y = run["at_t_on"][agent]
    x0, y0, x1, y1 = SMOKE_BOX
    if not x0 <= x <= x1 or y < y0:
        return "before"
    return "inside" if y <= y1 else "past"


def _main_agents(run: dict) -> dict[int, str]:
    return {a: _group(run, a) for a, room in run["home"].items() if room in MAIN_ROOMS}


def _usage(run: dict) -> dict[int, dict[str, int]]:
    return {
        room: {e: seen["final"].count(e) for e in (MAIN, SECONDARY)}
        for room, seen in run["per_room"].items()
    }


def _reasons(run: dict) -> dict[str, int]:
    reasons: dict[str, int] = {}
    for row in run["switches"]:
        reasons[row["reason"]] = reasons.get(row["reason"], 0) + 1
    return reasons


@pytest.fixture(scope="module")
def smoke_runs(runs) -> dict[str, dict]:
    return {
        "clear": runs["on"],
        "preference": _run(rerouting=True, smoke_anticipate=False),
        "hard": _run(rerouting=True, mode="hard", smoke_anticipate=False),
        "weak": _run(rerouting=True, smoke_anticipate=False, smoke_k=1.0),
        "foresight": _run(rerouting=True, smoke_anticipate=True),
    }


def test_fire_variant_report(smoke_runs):
    """Print exit usage per room with and without smoke, and the switches."""
    for name in ("clear", "preference", "hard", "foresight"):
        run = smoke_runs[name]
        print(
            f"\n{name}: evacuated {run['evacuated']}/{run['total']}, "
            f"end {run['t_end_s']:.1f} s, switches {_reasons(run)}"
        )
        for room, use in _usage(run).items():
            print(f"  room {room:2d}: main {use[MAIN]}, secondary {use[SECONDARY]}")
        assert run["total"] == 23


def test_smoke_in_the_passage_moves_agents_before_it_to_the_secondary_exit(
    smoke_runs,
):
    """Preference allocation, ``anticipate: false``, K = 5 /m from t = 5 s.

    Hand values: the passage box is 2.0 m long, so a main route entered from
    the corridor has tau = 5 x 2.0 = 10 > tau_max = 6 and is refused; the
    secondary route never meets the box, tau = 0. Agents north of y = 2.3 m
    have tau = 0 on the main route and keep it. Clear-air control (seed 42):
    at t = 5 s ten main-allocated agents are before the passage, three inside
    it and two past it. The first pass at or after t_on switches the ten
    within one interval (stagger and step add at most 0.03 s).
    """
    run = smoke_runs["preference"]
    groups = _main_agents(run)
    assert list(groups.values()).count("before") == 10
    assert list(groups.values()).count("past") == 2
    rows: dict[int, list[dict]] = {}
    for row in run["switches"]:
        rows.setdefault(row["agent_id"], []).append(row)
    latest = SMOKE_ON_S + REROUTE_INTERVAL_S + SWITCH_SLACK_S
    for agent, group in groups.items():
        if group == "before":
            moves = [(r["old_exit"], r["new_exit"]) for r in rows[agent]]
            assert moves == [(MAIN, SECONDARY)]
            assert rows[agent][0]["reason"] == "smoke_reroute"
            assert SMOKE_ON_S <= rows[agent][0]["time_s"] <= latest
        if group == "past":
            assert agent not in rows
    for room, seen in run["per_room"].items():
        if ALLOCATION[room] == SECONDARY:
            assert seen["final"] == [SECONDARY] * OCCUPANTS[room]
    secondary_agents = {a for a, r in run["home"].items() if ALLOCATION[r] == SECONDARY}
    assert not secondary_agents & set(rows)
    assert run["evacuated"] == 23
    assert run["remaining"] == 0


def test_agents_inside_the_passage_take_the_cleaner_way_out(smoke_runs):
    """An agent at height y in the box has main tau = 5 (2.3 - y) and, turning
    back, tau = 5 (y - 0.3). It leaves the main exit when main is dirtier by
    more than 0.6, i.e. for y < 1.255 m. Measured at t = 5 s: y = 0.78 (main
    7.6, back 2.4) turns back; y = 1.53 (3.85 against 6.15) and y = 2.07
    (1.15 against 8.85) go on to main.
    """
    run = smoke_runs["preference"]
    switched = {r["agent_id"] for r in run["switches"]}
    inside = [a for a, g in _main_agents(run).items() if g == "inside"]
    assert len(inside) == 3
    for agent in inside:
        y = run["at_t_on"][agent][1]
        assert (agent in switched) == (y < 1.255), f"agent {agent} at y = {y:.2f}"
    assert all(r["new_exit"] == SECONDARY for r in run["switches"])


def test_preference_yields_to_smoke_below_the_refusal_limit(smoke_runs):
    """K = 1 /m: tau = 2.0 on the main route, under tau_max = 6 (not refused),
    and 2.0 above the secondary route's 0, more than the 0.6 band
    (tau_max x tau_deadband). The preference yields on the band alone (D4),
    as at K = 5.
    """
    weak = smoke_runs["weak"]
    groups = _main_agents(weak)
    rows = {r["agent_id"]: r for r in weak["switches"]}
    for agent, group in groups.items():
        if group == "before":
            assert rows[agent]["reason"] == "smoke_reroute"
            assert (rows[agent]["old_exit"], rows[agent]["new_exit"]) == (
                MAIN,
                SECONDARY,
            )
        if group == "past":
            assert agent not in rows
    assert list(groups.values()).count("before") == 10
    assert weak["evacuated"] == 23


def test_hard_allocation_keeps_the_exit_through_the_smoke(smoke_runs):
    """``"allocation": "hard"`` is the documented meaning: the route graph holds
    only the allocated exit, so smoke cannot move anyone (D5). Measured: no
    route row at all, not even a ``fallback``. The refused route is walked at
    Lund f(5) = 1 - 0.057 x 5 / 0.706 = 0.596 of the free speed, which costs
    time: the run ends later than in clear air (17.5 s against 16.0 s).
    """
    clear, hard = smoke_runs["clear"], smoke_runs["hard"]
    assert hard["switches"] == []
    assert _usage(hard) == _usage(clear)
    for room, seen in hard["per_room"].items():
        assert seen["assigned"] == [ALLOCATION[room]] * OCCUPANTS[room]
        assert seen["final"] == seen["assigned"]
    assert hard["evacuated"] == 23
    assert hard["t_end_s"] > clear["t_end_s"]


def test_default_anticipation_never_switches_towards_main(smoke_runs):
    """With foresight the router sees the box at spawn: agents that would meet
    it leave their preference at t = 0 (``allocation_preference``), the rest
    on a later pass (``smoke_reroute``). Reported, not a timing check.
    """
    run = smoke_runs["foresight"]
    assert run["evacuated"] == 23
    assert all(r["new_exit"] == SECONDARY for r in run["switches"])
    assert any(r["reason"] == "allocation_preference" for r in run["switches"])
