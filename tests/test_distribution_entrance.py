"""A distribution's ``entrance`` reaches the agents it spawns (issue #169).

``entrance`` names the exit a spawn area's occupants walked in through; they
know it whatever their familiarity, so a ``discovery`` agent must start with
the route to it in its cognitive map.

The asset is the T-junction: journeys and transitions are declared and the
junction is a checkpoint, so initialisation takes the complete-config path and
agents are steered directly. On that path ``_process_distributions`` built the
parameter dict with an explicit whitelist that omitted ``entrance``, so agents
placed at t = 0 were seeded as if none had been declared. Flow-spawned agents
read ``entrance`` from the raw scenario in ``scenario.py`` and are pinned here
so the two paths keep the same contract.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from pyfds_evac.core.route_graph import RerouteConfig, RouteCostConfig
from pyfds_evac.core.scenario import Scenario, run_scenario

ASSET = Path("assets/t_junction")
SPAWN_KEY = "jps-distributions_0"
ENTRANCE = "exit_B_right"
OTHER_EXIT = "exit_A_left"
NUM_AGENTS = 6
SEED = 42


@pytest.fixture(scope="module")
def base_raw() -> dict:
    return json.loads((ASSET / "config_discovery.json").read_text(encoding="utf-8"))


def _scenario(base_raw: dict, *, use_flow_spawning: bool) -> Scenario:
    raw = copy.deepcopy(base_raw)
    raw["config"]["simulation_settings"]["simulationParams"]["max_simulation_time"] = (
        5.0
    )
    params = raw["distributions"][SPAWN_KEY]["parameters"]
    params.update(
        {
            "number": NUM_AGENTS,
            "use_flow_spawning": use_flow_spawning,
            "flow_start_time": 0,
            "flow_end_time": 2,
            "familiarity": "discovery",
            "entrance": ENTRANCE,
        }
    )
    sim_params = raw["config"]["simulation_settings"]["simulationParams"]
    return Scenario(
        raw=raw,
        walkable_area_wkt=(ASSET / "geometry.wkt").read_text(encoding="utf-8").strip(),
        model_type="CollisionFreeSpeedModel",
        seed=SEED,
        sim_params=sim_params,
        source_path=None,
    )


def _first_maps(scenario: Scenario) -> dict[int, dict]:
    """Each agent's cognitive map as first recorded."""
    result = run_scenario(
        scenario,
        seed=SEED,
        reroute_config=RerouteConfig(
            reevaluation_interval_s=1.0, cost_config=RouteCostConfig()
        ),
        collect_cognitive_map_history=True,
    )
    try:
        history = result.cognitive_map_history or []
    finally:
        result.cleanup()
    first: dict[int, dict] = {}
    for row in history:
        first.setdefault(row["agent_id"], row)
    return first


def test_the_asset_names_both_exits(base_raw):
    """The entrance must be a real exit, and not the only one."""
    assert {ENTRANCE, OTHER_EXIT} <= set(base_raw["exits"])
    assert base_raw["journeys"] and base_raw["checkpoints"]


@pytest.mark.parametrize(
    "use_flow_spawning", [False, True], ids=["placed_at_t0", "flow_spawned"]
)
def test_discovery_agents_start_knowing_the_entrance(base_raw, use_flow_spawning):
    first = _first_maps(_scenario(base_raw, use_flow_spawning=use_flow_spawning))
    assert len(first) == NUM_AGENTS, "the test proves nothing without every agent"
    for agent_id, row in first.items():
        assert row["familiarity"] == "discovery"
        assert ENTRANCE in row["known_nodes"], (
            f"agent {agent_id} does not know its entrance: {row['known_nodes']}"
        )


FULL_KEY = "jps-distributions_full"


def _two_distributions(base_raw: dict) -> Scenario:
    """A placed "full" group listed before a flow-spawned "discovery" group.

    Issue #190: flow entries on the complete-config path carried no
    ``dist_index``, so the flow group looked up familiarity and entrance by
    its position among flow entries (0) and took the placed group's.
    """
    raw = copy.deepcopy(base_raw)
    raw["config"]["simulation_settings"]["simulationParams"]["max_simulation_time"] = (
        5.0
    )
    flow = raw["distributions"].pop(SPAWN_KEY)
    full = copy.deepcopy(flow)
    full["coordinates"] = [[18, 1], [22, 1], [22, 4], [18, 4], [18, 1]]
    full["parameters"].update(
        {"number": 3, "use_flow_spawning": False, "familiarity": "full"}
    )
    flow["coordinates"] = [[18, 5], [22, 5], [22, 8], [18, 8], [18, 5]]
    flow["parameters"].update(
        {
            "number": 3,
            "use_flow_spawning": True,
            "flow_start_time": 0,
            "flow_end_time": 2,
            "familiarity": "discovery",
            "entrance": ENTRANCE,
        }
    )
    raw["distributions"] = {FULL_KEY: full, SPAWN_KEY: flow}
    journey = copy.deepcopy(raw["journeys"][0])
    journey["id"] = "journey_full"
    journey["stages"][0] = FULL_KEY
    for t in journey["transitions"]:
        t["journey_id"] = "journey_full"
        if t["from"] == SPAWN_KEY:
            t["from"] = FULL_KEY
    raw["journeys"].append(journey)
    raw["transitions"] = raw["transitions"] + [
        t for t in journey["transitions"] if t["from"] == FULL_KEY
    ]
    sim_params = raw["config"]["simulation_settings"]["simulationParams"]
    return Scenario(
        raw=raw,
        walkable_area_wkt=(ASSET / "geometry.wkt").read_text(encoding="utf-8").strip(),
        model_type="CollisionFreeSpeedModel",
        seed=SEED,
        sim_params=sim_params,
        source_path=None,
    )


def test_flow_agents_take_their_own_distribution(base_raw):
    first = _first_maps(_two_distributions(base_raw))
    by_familiarity: dict[str, list[dict]] = {}
    for row in first.values():
        by_familiarity.setdefault(row["familiarity"], []).append(row)
    assert len(by_familiarity.get("full", [])) == 3
    assert len(by_familiarity.get("discovery", [])) == 3
    for row in by_familiarity["discovery"]:
        assert ENTRANCE in row["known_nodes"]
        assert OTHER_EXIT not in row["known_nodes"]
