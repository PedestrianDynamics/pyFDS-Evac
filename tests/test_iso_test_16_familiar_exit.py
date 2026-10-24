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

import functools
from collections.abc import Callable

import pytest
from shapely.geometry import box

from pyfds_evac.core.route_graph import RerouteConfig, RouteCostConfig
from pyfds_evac.core.scenario import Scenario, run_scenario
from pyfds_evac.core.smoke_speed import SmokeSpeedConfig, SmokeSpeedModel

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


def _repeat_until_stable(
    parameters: dict, exit_used: Callable[[int, dict], str] = _exit_used
) -> tuple[float, int, list[str]]:
    """Run seeds 1, 2, ... until the exit-2 fraction is stable; see module doc."""
    exits: list[str] = []
    quiet = 0
    previous = 0.0
    for seed in range(1, MAX_RUNS + 1):
        exits.append(exit_used(seed, parameters))
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


# --- Fire variant: affiliation against smoke (#850) -------------------------
#
# Smoke fills the east side of the room, x >= SMOKE_X_MIN_M over the full
# height and the exit-2 door strip, from t = 0. The route to exit 2 is then
# smoky over L = 4.5 m (x 6 -> 10 plus 0.5 m into the door); the route to
# exit 1 (west) is clear, tau_1 = 0. The gate model refuses a route above
# tau = K L = tau_max = 6, i.e. K = 1.33 /m, and a current exit yields when its
# tau exceeds the rival's by more than tau_max * tau_deadband = 0.6, i.e.
# K = 0.13 /m. Hand values tau_2 = K * 4.5:
#
#   K = 0.05 /m: tau_2 = 0.23   (below the deadband)
#   K = 0.5  /m: tau_2 = 2.25   (above the deadband, below the refusal 6)
#   K = 3.0  /m: tau_2 = 13.5   (refused)
#
# With ``sampling_step_m = 0.25`` the sampled L is within one step of 4.5 m,
# so each tau is at least 2x away from its threshold. The start is pinned to
# (5, 7.5) +- 0.25 m: the paths to the exit nodes then differ by at most
# 5.75/5.25, so in clear air the preference journey keeps its allocation
# (time anchor 0.9).
#
# Three occupants, each repeated under the module stopping rule:
#
# A  ``discovery`` + ``entrance: "exit_2"`` (the ISO 16 sub-model). It knows
#    exit 2 only, so smoke on its one route cannot move it: it uses exit 2 at
#    every K, including tau = 13.5, and walks through the smoke slowed down.
# B  full familiarity and a journey to exit 2 with ``allocation: "preference"``.
#    The allocation yields as soon as the exit-2 tau exceeds the exit-1 tau by
#    more than 0.6 (the TAU_CLEANER band, intended), so it switches at
#    K = 0.5, well below the refusal threshold.
# C  full familiarity, no journey: picks the cheapest known exit, exit 1.
#
# #362: familiarity does not change willingness to enter smoke. tau_max, the
# deadband and the current-exit discount are the same for every agent. A
# differs from C only in which exits it knows; it enters the smoke because it
# knows no other exit, not because it tolerates more.
SMOKE_X_MIN_M = 6.0
SMOKE_LEVELS_PER_M = (0.05, 0.5, 3.0)
PIN_HALF_M = 0.25
PIN_CENTRE = (ROOM_WIDTH_M / 2.0, ROOM_LENGTH_M / 2.0)
FRAME_S = 0.1
SMOKE_REROUTE_S = 1.0
# Bracket of the deadband K = 0.13: tau_2 = 0.45 and 0.9 against 0.6.
BRACKET_BELOW_PER_M = 0.10
BRACKET_ABOVE_PER_M = 0.20

OCCUPANT_A = (AFFILIATED_EXIT_2, None)
OCCUPANT_B = ({"familiarity": "full"}, "preference")
OCCUPANT_C = ({"familiarity": "full"}, None)
# Exit-2 fraction per smoke level, in SMOKE_LEVELS_PER_M order.
EXPECTED_EXIT_2 = {
    "A": (1.0, 1.0, 1.0),
    "B": (1.0, 0.0, 0.0),
    "C": (0.0, 0.0, 0.0),
}
OCCUPANTS = {"A": OCCUPANT_A, "B": OCCUPANT_B, "C": OCCUPANT_C}


class _BoxSmoke:
    """Static extinction K for x >= ``x_min`` over the full room height."""

    def __init__(self, x_min: float, k: float) -> None:
        self.x_min = x_min
        self.k = k

    def sample_extinction(self, t: float, x: float, y: float) -> float:
        inside = x >= self.x_min and -1.0 <= y <= ROOM_LENGTH_M + 1.0
        return self.k if inside else 0.0


def _smoke_scenario(seed: int, parameters: dict, journey: str | None) -> Scenario:
    scenario = _scenario(seed, parameters)
    raw = scenario.raw
    x, y = PIN_CENTRE
    pin = box(x - PIN_HALF_M, y - PIN_HALF_M, x + PIN_HALF_M, y + PIN_HALF_M)
    raw["distributions"]["occupant"]["coordinates"] = _coords(pin)
    if journey is None:
        return scenario
    transition = {"from": "occupant", "to": "exit_2", "journey_id": "j"}
    raw["journeys"] = [
        {
            "id": "j",
            "stages": ["occupant", "exit_2"],
            "transitions": [transition],
            "allocation": journey,
        }
    ]
    raw["transitions"] = [transition]
    return scenario


def _smoke_run(seed: int, occupant: tuple[dict, str | None], k: float) -> dict:
    parameters, journey = occupant
    model = SmokeSpeedModel(
        _BoxSmoke(SMOKE_X_MIN_M, k),
        SmokeSpeedConfig(fds_dir=".", speed_law="lund", update_interval_s=1.0),
    )
    reroute = RerouteConfig(
        reevaluation_interval_s=SMOKE_REROUTE_S,
        cost_config=RouteCostConfig.from_routing_params({"sampling_step_m": 0.25}),
    )
    result = run_scenario(
        _smoke_scenario(seed, parameters, journey),
        seed=seed,
        reroute_config=reroute,
        smoke_speed_model=model,
    )
    try:
        frames = result.trajectory_dataframe()["frame"]
        return {
            "exits": [r["exit_id"] for r in result.exit_history or []],
            "routes": [
                (r["time_s"], r["old_exit"], r["new_exit"], r["reason"])
                for r in result.route_history or []
            ],
            "evacuated": result.agents_evacuated,
            "exit_time_s": float(frames.max()) * FRAME_S,
        }
    finally:
        result.cleanup()


def _smoke_exit_used(
    seed: int, parameters: dict, occupant: tuple[dict, str | None], k: float
) -> str:
    run = _smoke_run(seed, occupant, k)
    assert run["evacuated"] == 1, f"seed {seed}, K={k}: occupant did not leave"
    assert len(run["exits"]) == 1, f"seed {seed}, K={k}: exits {run['exits']}"
    return run["exits"][0]


def _smoke_fraction(occupant: tuple[dict, str | None], k: float) -> float:
    exit_used = functools.partial(_smoke_exit_used, occupant=occupant, k=k)
    fraction, runs, _ = _repeat_until_stable(occupant[0], exit_used)
    print(f"  K={k}: exit 2 used {fraction:.3f} after {runs} runs")
    return fraction


def test_smoke_contrast_exit_2_usage_against_k():
    """Exit-2 usage per occupant and K; see the section comment for tau."""
    for name, occupant in OCCUPANTS.items():
        print(f"occupant {name}")
        measured = tuple(_smoke_fraction(occupant, k) for k in SMOKE_LEVELS_PER_M)
        assert measured == EXPECTED_EXIT_2[name], f"occupant {name}: {measured}"


def test_affiliated_occupant_walks_through_any_smoke():
    """A knows exit 2 only: no reroute, no fallback row, slower through smoke."""
    clear = _smoke_run(1, OCCUPANT_A, 0.0)
    smoky = _smoke_run(1, OCCUPANT_A, max(SMOKE_LEVELS_PER_M))
    assert smoky["exits"] == ["exit_2"]
    assert smoky["routes"] == []
    assert smoky["evacuated"] == 1
    assert smoky["exit_time_s"] > clear["exit_time_s"]


@pytest.mark.parametrize("k", SMOKE_LEVELS_PER_M[1:])
def test_preference_allocation_yields_to_smoke_at_spawn(k):
    run = _smoke_run(1, OCCUPANT_B, k)
    assert run["routes"] == [(0.0, "exit_2", "exit_1", "allocation_preference")]


def test_preference_allocation_holds_below_the_deadband():
    assert _smoke_run(1, OCCUPANT_B, SMOKE_LEVELS_PER_M[0])["routes"] == []


def test_preference_allocation_switches_at_the_tau_deadband():
    """tau_2 = 0.45 (K = 0.10) stays; tau_2 = 0.9 (K = 0.20) yields."""
    for seed in (1, 2):
        below = _smoke_run(seed, OCCUPANT_B, BRACKET_BELOW_PER_M)
        above = _smoke_run(seed, OCCUPANT_B, BRACKET_ABOVE_PER_M)
        assert below["exits"] == ["exit_2"], f"seed {seed}"
        assert above["exits"] == ["exit_1"], f"seed {seed}"
