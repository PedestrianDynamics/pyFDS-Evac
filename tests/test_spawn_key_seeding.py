"""Per-agent draws follow the spawn key, not the JuPedSim id (#353, #198).

JuPedSim ids are unique but neither consecutive nor reproducible: a refused
``add_agent`` uses up an id, and ids are numbered per process. These tests
run the same deck with and without extra id-consuming refusals, and several
times in one process, and compare every agent by its ``(origin, n)`` spawn
key. The JuPedSim id must stay each agent's single tracking key.
"""

from __future__ import annotations

import contextlib
import copy
import io
import json
import sys
from pathlib import Path

import jupedsim as jps
import pytest

import pyfds_evac.core.scenario as scenario_mod
import pyfds_evac.core.simulation_init as simulation_init_mod
from pyfds_evac.core.scenario import load_scenario, run_scenario

REPO = Path(__file__).resolve().parents[1]
ASSETS = REPO / "assets"
sys.path.insert(0, str(REPO / "tests"))


_REAL_ADD_AGENT = jps.Simulation.add_agent
_OUTSIDE = (1.0e6, 1.0e6)


def _run_quiet(scenario, **kwargs):
    with contextlib.redirect_stdout(io.StringIO()):
        return run_scenario(scenario, **kwargs)


def _load(config: str, max_time: float, agents: int | None = None):
    scenario = load_scenario(str(ASSETS / config)).copy()
    scenario.set_max_time(max_time)
    for dist in scenario.raw["distributions"].values():
        params = dist["parameters"]
        if agents is not None:
            params["number"] = agents
        # Spawn the whole flow in the first third of the run.
        if params.get("use_flow_spawning"):
            params["flow_end_time"] = max_time / 3
    return scenario


def test_every_agent_keeps_one_id_and_one_key(monkeypatch):
    # A complete-config deck with a flow source and a t=0 spawn area that has
    # no journey, so its agents are not path agents.
    scenario = _load("t_junction/config.json", 15.0, 10)
    dists = scenario.raw["distributions"]
    extra = copy.deepcopy(dists["jps-distributions_0"])
    extra["coordinates"] = [[2, 9.5], [6, 9.5], [6, 11], [2, 11], [2, 9.5]]
    extra["parameters"].update(number=4, use_flow_spawning=False)
    dists["jps-distributions_1"] = extra

    added: list[int] = []
    tables: list[dict] = []

    def record_add(self, parameters):
        agent_id = _REAL_ADD_AGENT(self, parameters)
        added.append(agent_id)
        return agent_id

    real_lookup = scenario_mod.lookup_spawn_key

    def record_lookup(spawn_keys, agent_id, origin=None):
        if not tables or tables[-1] is not spawn_keys:
            tables.append(spawn_keys)
        return real_lookup(spawn_keys, agent_id, origin)

    monkeypatch.setattr(jps.Simulation, "add_agent", record_add)
    monkeypatch.setattr(scenario_mod, "lookup_spawn_key", record_lookup)
    result = _run_quiet(scenario)
    try:
        frames = result.trajectory_dataframe()
        exit_rows = result.exit_history
    finally:
        result.cleanup()

    assert len(tables) == 1
    spawn_keys = tables[0]
    assert len(added) == len(set(added)) == 14
    assert sorted(spawn_keys) == sorted(added)
    assert len(set(spawn_keys.values())) == len(spawn_keys)
    initial = sorted(k[1] for k in spawn_keys.values() if k[0] == "initial")
    flow = sorted(k[1] for k in spawn_keys.values() if k[0] != "initial")
    assert initial == list(range(4))
    assert flow == list(range(10))
    # Output is still labelled by JuPedSim id, and every path agent's exit
    # row carries the key it was given at add_agent.
    assert set(frames["id"]) <= set(added)
    for row in exit_rows:
        assert spawn_keys[row["agent_id"]] == (row["origin"], row["spawn_index"])
    # The t=0 agents without a journey are not path agents.
    assert {r["origin"] for r in exit_rows} == {"flow:jps-distributions_0"}


def test_failure_after_a_flow_add_is_raised_not_retried(monkeypatch):
    added: list[int] = []

    def record_add(self, parameters):
        agent_id = _REAL_ADD_AGENT(self, parameters)
        added.append(agent_id)
        return agent_id

    def broken(*args, **kwargs):
        raise RuntimeError("path state failed")

    monkeypatch.setattr(jps.Simulation, "add_agent", record_add)
    monkeypatch.setattr(simulation_init_mod, "build_agent_path_state", broken)
    with pytest.raises(RuntimeError, match="path state failed"):
        _run_quiet(_load("t_junction/config.json", 5.0, 5))
    assert len(added) == 1


@pytest.mark.parametrize(
    "config",
    sorted(str(p.relative_to(ASSETS)) for p in ASSETS.glob("*/config*.json")),
)
def test_shipped_decks_key_only_path_agents_at_t0(config, tmp_path):
    # Keys used to be given to path agents only; every agent now gets one.
    # Where all t=0 agents are path agents the numbering, and so an exit
    # history's spawn indices, are unchanged.
    from types import SimpleNamespace

    from shapely import wkt

    from pyfds_evac.core.simulation_init import initialize_simulation_from_json

    scenario = load_scenario(str(ASSETS / config))
    walkable = wkt.loads(scenario.walkable_area_wkt)
    path = tmp_path / "config.json"
    path.write_text(json.dumps(scenario.raw), encoding="utf-8")
    simulation = jps.Simulation(model=jps.CollisionFreeSpeedModel(), geometry=walkable)
    with contextlib.redirect_stdout(io.StringIO()):
        _, _, _, info = initialize_simulation_from_json(
            str(path),
            simulation,
            SimpleNamespace(polygon=walkable),
            seed=1,
            model_type="CollisionFreeSpeedModel",
            global_parameters=SimpleNamespace(),
        )
    keys = info["spawn_keys"]
    path_agents = {
        agent_id
        for agent_id, wait in info["agent_wait_info"].items()
        if wait.get("mode") == "path"
    }
    assert len(keys) == simulation.agent_count()
    assert set(keys) == path_agents
    assert sorted(keys.values()) == [("initial", n) for n in range(len(keys))]
