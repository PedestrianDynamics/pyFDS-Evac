"""ISO 20414:2020 Test 16 (Table 18): affiliation to familiar exits.

Setup of the test: one occupant in a 10 m x 15 m room with two exits of 1 m
width, each the same distance from the occupant (the room, the start and the
caveat that the doors are equidistant only to within the 1 m x 1 m spawn area
are those of ``test_iso_test_9_dynamic_exit.py``). Scenario 1: an unfamiliar
occupant. Scenario 2: an occupant affiliated with exit 2. Each scenario is
repeated until the exit-usage fractions change by less than 1 % per added run.
Expected result: exit 2 is used more in scenario 2 than in scenario 1.

The standard asks the tester to state whether affiliation is a dedicated
sub-model or a user-defined split. Here it is the cognitive-map model, not a
split of the occupants between exits:

- Scenario 1 sets ``familiarity: "discovery"``: the occupant starts knowing
  no exit. With no sign in the room and no known exit it takes the default
  route (``no_known_exit: default_route``), the nearest exit by walking
  distance. Which door that is depends on where the seeded start falls inside
  the spawn area, so exit 2 is used about half the time and the split is
  geometric noise, not a preference.
- Scenario 2 adds ``entrance: "exit_2"``: the exit the occupant walked in
  through, which it knows whatever its familiarity
  (``init_cognitive_map``). Its known graph then holds exit 2 only, and routing
  can pick only a known exit.

No weight, journey or per-run assignment sets the exit. The fractions are
measured, not prescribed. The FDS+Evac import maps a known door to the same
``entrance`` key.

Stopping rule. A run is one seed. After each added run the cumulative
fraction of occupants leaving by exit 2 is compared with the one before; the
rule is met when that change has been below 1 % (0.01) for ``QUIET_RUNS``
consecutive added runs, so a single flat step on the way does not stop it;
this is stricter than the standard's "less than 1 % per added run". The
seeds are 1, 2, 3, ... in order, so the run counts are deterministic.
"""

from __future__ import annotations

import pytest
from shapely.geometry import box

from pyfds_evac.core.route_graph import RerouteConfig
from pyfds_evac.core.scenario import Scenario, run_scenario

pytestmark = [pytest.mark.iso20414, pytest.mark.nist_tn1822]

ROOM_WIDTH_M = 10.0
ROOM_LENGTH_M = 15.0
EXIT_WIDTH_M = 1.0
EXIT_DEPTH_M = 1.0
SPEED_MPS = 1.0
MAX_TIME_S = 40.0
REROUTE = RerouteConfig(reevaluation_interval_s=30.0)
START = (ROOM_WIDTH_M / 2.0, ROOM_LENGTH_M / 2.0)
# Half the side of the spawn area around the centre.
START_AREA_M = 0.5
TOLERANCE = 0.01
QUIET_RUNS = 10
MAX_RUNS = 500
# Scenario 1 is geometric noise (binomial, sd ~ 0.05 at 100 runs around 0.5);
# scenario 2 must exceed it by far more than that.
MIN_MARGIN = 0.25


def _coords(polygon) -> list[list[float]]:
    return [[x, y] for x, y in polygon.exterior.coords]


def _scenario(seed: int, parameters: dict) -> Scenario:
    lo = ROOM_LENGTH_M / 2.0 - EXIT_WIDTH_M / 2.0
    hi = ROOM_LENGTH_M / 2.0 + EXIT_WIDTH_M / 2.0
    doors = {
        "exit_1": box(-EXIT_DEPTH_M, lo, 0.0, hi),
        "exit_2": box(ROOM_WIDTH_M, lo, ROOM_WIDTH_M + EXIT_DEPTH_M, hi),
    }
    walkable = box(0.0, 0.0, ROOM_WIDTH_M, ROOM_LENGTH_M)
    for door in doors.values():
        walkable = walkable.union(door)
    exits = {
        name: {
            "type": "polygon",
            "coordinates": _coords(poly),
            "enable_throughput_throttling": False,
            "max_throughput": 0,
        }
        for name, poly in doors.items()
    }
    x, y = START
    start = box(x - START_AREA_M, y - START_AREA_M, x + START_AREA_M, y + START_AREA_M)
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
                "baseSeed": seed,
            },
            "ui_state": {"useShortestPaths": False},
        },
        "exits": exits,
        "distributions": {
            "occupant": {
                "type": "polygon",
                "coordinates": _coords(start),
                "parameters": {
                    "number": 1,
                    "radius": 0.2,
                    "v0": SPEED_MPS,
                    "use_flow_spawning": False,
                    "distribution_mode": "by_number",
                    "use_premovement": False,
                    "radius_distribution": "constant",
                    "v0_distribution": "constant",
                    **parameters,
                },
            }
        },
        "checkpoints": {},
        "zones": {},
        "journeys": [],
        "transitions": [],
    }
    return Scenario(
        raw=raw,
        walkable_area_wkt=walkable.wkt,
        model_type="CollisionFreeSpeedModel",
        seed=seed,
        sim_params=sim_params,
        source_path=None,
    )


def _exit_used(seed: int, parameters: dict) -> str:
    result = run_scenario(
        _scenario(seed, parameters), seed=seed, reroute_config=REROUTE
    )
    try:
        exits = [r["exit_id"] for r in result.exit_history or []]
        assert result.agents_evacuated == 1, f"seed {seed}: occupant did not leave"
        assert len(exits) == 1, f"seed {seed}: expected one exit record, got {exits}"
        return exits[0]
    finally:
        result.cleanup()


def _repeat_until_stable(parameters: dict) -> tuple[float, int, list[str]]:
    """Run seeds 1, 2, ... until the exit-2 fraction is stable; see module doc."""
    exits: list[str] = []
    quiet = 0
    previous = 0.0
    for seed in range(1, MAX_RUNS + 1):
        exits.append(_exit_used(seed, parameters))
        fraction = exits.count("exit_2") / len(exits)
        quiet = quiet + 1 if seed > 1 and abs(fraction - previous) < TOLERANCE else 0
        previous = fraction
        if quiet >= QUIET_RUNS:
            return fraction, len(exits), exits
    pytest.fail(f"exit-2 fraction not stable within {MAX_RUNS} runs: {previous:.3f}")


UNFAMILIAR = {"familiarity": "discovery"}
AFFILIATED_EXIT_2 = {"familiarity": "discovery", "entrance": "exit_2"}
AFFILIATED_EXIT_1 = {"familiarity": "discovery", "entrance": "exit_1"}


def test_affiliation_raises_exit_2_usage():
    f1, n1, _ = _repeat_until_stable(UNFAMILIAR)
    f2, n2, _ = _repeat_until_stable(AFFILIATED_EXIT_2)
    print(f"scenario 1: exit 2 used {f1:.3f} after {n1} runs")
    print(f"scenario 2: exit 2 used {f2:.3f} after {n2} runs")
    assert f2 > f1 + MIN_MARGIN
    assert f2 == 1.0
    # Unfamiliar occupants have no preference: the split is the start position.
    assert 0.3 < f1 < 0.7


def test_affiliation_is_to_the_named_exit():
    """Naming exit 1 sends the same occupants through exit 1, so exit 2 is not
    favoured by the geometry or the exit order."""
    fraction, _, exits = _repeat_until_stable(AFFILIATED_EXIT_1)
    assert fraction == 0.0
    assert set(exits) == {"exit_1"}
