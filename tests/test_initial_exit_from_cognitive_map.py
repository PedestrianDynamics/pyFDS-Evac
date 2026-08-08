"""The exit an agent walks to at t=0 must be one it knows about.

Behavioural, and deliberately so: the mechanism this covers -- ``rank_routes``
on the agent's ``cognitive_subgraph`` -- is unit-tested to death and still was
not reached from the spawn path, which picked the geometrically nearest exit
before any map existed (issue #86). Only a test that runs the engine and looks
at where agents ended up can tell the difference.

Rerouting is **off** in every case here. With it on, the first reevaluation
fires at spawn and would mask a broken initial assignment by fixing it a moment
later; off, the opening choice is the only choice, so this measures exactly it.

The room is a corridor with three exits. The spawn area sits at the right end,
so ``near`` is the nearest exit by geometry and ``far`` is the farthest -- and
``far`` is the one every agent walked in through.
"""

from __future__ import annotations

import sqlite3

import pytest
from shapely.geometry import Point, Polygon

from pyfds_evac.core.route_graph import RerouteConfig, RouteCostConfig
from pyfds_evac.core.scenario import Scenario, run_scenario

LENGTH_M = 60.0
HEIGHT_M = 8.0
NUM_AGENTS = 40
SEED = 42

EXIT_FAR = "jps-exits_far"
EXIT_MID = "jps-exits_mid"
EXIT_NEAR = "jps-exits_near"

# x-position of each exit; the spawn area is at the right (high-x) end.
_EXIT_X = {EXIT_FAR: 0.0, EXIT_MID: 28.0, EXIT_NEAR: LENGTH_M - 1.0}


def _exit_polygon(x0: float) -> list[list[float]]:
    return [
        [x0, 0.0],
        [x0 + 1.0, 0.0],
        [x0 + 1.0, HEIGHT_M],
        [x0, HEIGHT_M],
        [x0, 0.0],
    ]


def _corridor_scenario(familiarity, entrance: str | None) -> Scenario:
    """Three exits in a row, everyone spawning beside the nearest one."""
    walkable_wkt = (
        f"POLYGON ((0 0, {LENGTH_M} 0, {LENGTH_M} {HEIGHT_M}, 0 {HEIGHT_M}, 0 0))"
    )
    raw = {
        "project_version": "2.0",
        "config": {
            "simulation_settings": {
                "simulationParams": {
                    "max_simulation_time": 300.0,
                    "model_type": "CollisionFreeSpeedModel",
                },
                "numberOfSimulations": 1,
                "baseSeed": SEED,
            },
            "ui_state": {"useShortestPaths": False},
        },
        "exits": {
            exit_id: {
                "type": "polygon",
                "coordinates": _exit_polygon(x0),
                "enable_throughput_throttling": False,
                "max_throughput": 0,
            }
            for exit_id, x0 in _EXIT_X.items()
        },
        "distributions": {
            "jps-distributions_0": {
                "type": "polygon",
                "coordinates": [
                    [LENGTH_M - 12.0, 1.0],
                    [LENGTH_M - 4.0, 1.0],
                    [LENGTH_M - 4.0, HEIGHT_M - 1.0],
                    [LENGTH_M - 12.0, HEIGHT_M - 1.0],
                    [LENGTH_M - 12.0, 1.0],
                ],
                "parameters": {
                    "number": NUM_AGENTS,
                    "radius": 0.15,
                    "v0": 1.3,
                    "use_flow_spawning": False,
                    "use_premovement": False,
                    "familiarity": familiarity,
                    "entrance": entrance,
                    "radius_distribution": "constant",
                    "v0_distribution": "constant",
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
        walkable_area_wkt=walkable_wkt,
        model_type="CollisionFreeSpeedModel",
        seed=SEED,
        sim_params=sim_params,
        source_path=None,
    )


def _exit_shares(familiarity, entrance: str | None) -> dict[str, float]:
    """Run the scenario and return the fraction of agents leaving by each exit.

    An agent is credited to the exit polygon nearest its last recorded position,
    the same rule ``assets/station_fahy/validate.py`` uses.
    """
    result = run_scenario(
        _corridor_scenario(familiarity, entrance),
        seed=SEED,
        reroute_config=None,
    )
    try:
        con = sqlite3.connect(result.sqlite_file)
        try:
            rows = con.execute(
                "SELECT id, pos_x, pos_y FROM trajectory_data ORDER BY frame"
            ).fetchall()
        finally:
            con.close()
        last: dict[int, tuple[float, float]] = {}
        for agent_id, x, y in rows:
            last[agent_id] = (x, y)
    finally:
        result.cleanup()

    assert last, "no trajectory recorded"
    polygons = {exit_id: Polygon(_exit_polygon(x0)) for exit_id, x0 in _EXIT_X.items()}
    counts = dict.fromkeys(_EXIT_X, 0)
    for position in last.values():
        point = Point(*position)
        nearest = min(polygons.items(), key=lambda kv: point.distance(kv[1]))[0]
        counts[nearest] += 1
    total = sum(counts.values())
    return {exit_id: count / total for exit_id, count in counts.items()}


@pytest.fixture(scope="module")
def unfamiliar_shares() -> dict[str, float]:
    return _exit_shares(0.0, EXIT_FAR)


@pytest.fixture(scope="module")
def familiar_shares() -> dict[str, float]:
    return _exit_shares("full", None)


def test_agents_who_know_only_the_entrance_all_use_it(unfamiliar_shares):
    """familiarity = 0 plus an entrance leaves exactly one exit in the map."""
    assert unfamiliar_shares[EXIT_FAR] >= 0.95


def test_familiar_agents_take_the_near_exit_instead(familiar_shares):
    """Knowing the whole building, the cheapest route wins -- and it is not far."""
    assert familiar_shares[EXIT_NEAR] >= 0.95


def test_knowledge_changes_the_opening_choice(unfamiliar_shares, familiar_shares):
    """The two populations must diverge; their being identical was the bug.

    Before the fix both ran on the geometrically nearest exit and agreed to
    three significant figures whatever their familiarity.
    """
    assert unfamiliar_shares[EXIT_FAR] - familiar_shares[EXIT_FAR] >= 0.9


def test_no_reroute_in_the_spawn_timestep():
    """The opening choice *is* the first evaluation; the reroute pass must wait.

    Otherwise the reroute pass runs its own first evaluation in the same
    timestep, differing from the choice just made only in that it now sees an
    ``exit_counts`` tally built from those very assignments -- so the queue term
    immediately scatters a crowd that all knows the same door, and the whole
    population is redirected before anyone has taken a step.

    Run on the ``full`` tier, where every exit is in the map and the queue term
    therefore has somewhere to send people. A discovery agent that knows one
    exit has no alternative to be scattered onto, so it could not detect this.
    """
    result = run_scenario(
        _corridor_scenario("full", None),
        seed=SEED,
        reroute_config=RerouteConfig(
            reevaluation_interval_s=5.0, cost_config=RouteCostConfig()
        ),
    )
    try:
        at_spawn = [s for s in result.route_history or [] if s["time_s"] == 0.0]
    finally:
        result.cleanup()
    assert at_spawn == []
