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

from test_rerouting_golden import DECKS, _run_deck  # noqa: E402

_REAL_ADD_AGENT = jps.Simulation.add_agent
_OUTSIDE = (1.0e6, 1.0e6)


def _burn_an_id(self, parameters) -> None:
    """Make one refused add, which uses up a JuPedSim id."""
    refused = copy.copy(parameters)
    refused.position = _OUTSIDE
    with contextlib.suppress(Exception):
        _REAL_ADD_AGENT(self, refused)


def _add_after_a_refusal(self, parameters):
    _burn_an_id(self, parameters)
    return _REAL_ADD_AGENT(self, parameters)


def _key_of(result) -> dict[int, tuple[str, int]]:
    """JuPedSim id -> spawn key, from the exit history."""
    return {r["agent_id"]: (r["origin"], r["spawn_index"]) for r in result.exit_history}


def _by_key(result) -> dict:
    """Trajectories, exits and route switches of one run, keyed by spawn key."""
    key_of = _key_of(result)
    frames = result.trajectory_dataframe()
    trajectories: dict = {}
    for frame, agent_id, x, y in frames[["frame", "id", "x", "y"]].itertuples(
        index=False
    ):
        trajectories.setdefault(key_of[int(agent_id)], []).append((frame, x, y))
    switches = [
        (r["time_s"], key_of[r["agent_id"]], r["old_exit"], r["new_exit"])
        for r in result.route_history or []
    ]
    return {
        "trajectories": trajectories,
        "exits": {key_of[r["agent_id"]]: r["exit_id"] for r in result.exit_history},
        "switches": switches,
        "evacuated": result.agents_evacuated,
    }


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


# t=0 agents on the no-journey path (familiarity 0.5, so the map is a draw)
# and flow agents on the journey path (target point in the checkpoint).
_DECKS = {
    "initial_fallback_mixed": ("blind_spawn_discovery/config_mixed.json", 20.0, 12),
    "flow_journey": ("t_junction/config.json", 25.0, 30),
}


@pytest.mark.parametrize("deck", sorted(_DECKS))
def test_refused_adds_do_not_change_any_agent(deck, monkeypatch):
    config, max_time, agents = _DECKS[deck]
    plain = _run_quiet(_load(config, max_time, agents))
    try:
        expected = _by_key(plain)
        plain_ids = set(_key_of(plain))
    finally:
        plain.cleanup()
    monkeypatch.setattr(jps.Simulation, "add_agent", _add_after_a_refusal)
    burnt = _run_quiet(_load(config, max_time, agents))
    try:
        got = _by_key(burnt)
        burnt_ids = set(_key_of(burnt))
    finally:
        burnt.cleanup()
    assert expected["trajectories"], "the deck spawned nobody"
    # The refusals really did move the ids ...
    assert burnt_ids != plain_ids
    # ... and nothing any agent does.
    assert got == expected


def _even_split_t_junction(max_time: float, agents: int):
    """``t_junction`` with its two journey variants at equal weight."""
    scenario = _load("t_junction/config.json", max_time, agents)
    routing = scenario.raw["waypoint_routing"]["jps-checkpoints_0"]["journey_0"]
    for destination in routing["destinations"]:
        destination["percentage"] = 50
    return scenario


def test_refused_flow_positions_do_not_shift_later_draws(monkeypatch):
    # A refused candidate position is retried at the next one within the same
    # spawn, so positions differ; what each spawn draws must not: its journey
    # variant (#353), its first stage and its target point.
    recorded: dict[int, tuple] = {}
    real_build = simulation_init_mod.build_agent_path_state

    def build(*args, **kwargs):
        state = real_build(*args, **kwargs)
        recorded[kwargs["agent_id"]] = (
            kwargs["variant_data"]["variant_name"],
            state["current_target_stage"],
            state["target"],
            state["base_seed"],
        )
        return state

    monkeypatch.setattr(simulation_init_mod, "build_agent_path_state", build)

    def draws() -> dict:
        recorded.clear()
        result = _run_quiet(_even_split_t_junction(20.0, 20))
        try:
            key_of = _key_of(result)
        finally:
            result.cleanup()
        return {key_of[agent_id]: value for agent_id, value in recorded.items()}

    expected = draws()
    calls = {"n": 0}

    def refuse_every_other(self, parameters):
        calls["n"] += 1
        if calls["n"] % 2:
            _burn_an_id(self, parameters)
            raise RuntimeError("position refused")
        return _REAL_ADD_AGENT(self, parameters)

    monkeypatch.setattr(jps.Simulation, "add_agent", refuse_every_other)
    got = draws()
    assert len(expected) >= 15
    assert len({value[0] for value in expected.values()}) == 2
    common = set(expected) & set(got)
    assert len(common) >= 15
    assert {k: got[k] for k in common} == {k: expected[k] for k in common}


def _collapse_by_key(result) -> dict:
    key_of = _key_of(result)
    times: dict = {}
    for row in result.fed_history or []:
        key = key_of[row["agent_id"]]
        if row["incapacitated"] and key not in times:
            times[key] = row["time_s"]
    return times


def test_incapacitation_thresholds_follow_the_key(monkeypatch):
    # Thresholds used to come from one stream, drawn in the order agents were
    # first evaluated for FED. Reversing that order must not move any draw.
    sys.path.insert(0, str(REPO / "tests" / "verification"))
    from harness import CorridorSpec, corridor_scenario, make_fed_model, uniform

    from pyfds_evac.core.fed import TenabilityConfig

    spec = CorridorSpec(num_agents=20, seed=11, max_simulation_time=60.0)
    tenability = TenabilityConfig(
        enable_fic_speed=False,
        enable_incapacitation=True,
        fed_threshold=1.0,
        incapacitation_mode="probabilistic",
        susceptibility_sigma=0.94,
    )

    def collapse_times() -> dict:
        fed = make_fed_model(
            co_volume_fraction=uniform(0.06),
            co2_volume_fraction=uniform(0.0),
            o2_volume_fraction=uniform(0.209),
            update_interval_s=1.0,
        )
        result = _run_quiet(
            corridor_scenario(spec),
            seed=spec.seed,
            fed_model=fed,
            tenability_config=tenability,
        )
        try:
            return _collapse_by_key(result)
        finally:
            result.cleanup()

    expected = collapse_times()
    real_agents = jps.Simulation.agents
    monkeypatch.setattr(
        jps.Simulation, "agents", lambda self: list(real_agents(self))[::-1]
    )
    monkeypatch.setattr(jps.Simulation, "add_agent", _add_after_a_refusal)
    got = collapse_times()
    assert len(set(expected.values())) > 3, "thresholds should vary"
    assert got == expected


def test_same_run_in_one_process_repeats(monkeypatch):
    # The #198 reproduction: t_junction, 30 agents, gate model, synthetic
    # ramp, seed 1, three times in one process.
    deck = DECKS["tj_full_gate_ramp"]
    runs = []
    for _ in range(3):
        result = _run_deck_keyed(deck)
        runs.append(result)
    assert runs[0]["switches"], "the reproduction must reroute someone"
    assert runs[1] == runs[0]
    assert runs[2] == runs[0]


def _run_deck_keyed(deck) -> dict:
    """``_run_deck`` of the golden test, but keyed by spawn key."""
    captured = {}
    real_run = scenario_mod.run_scenario

    def keep(*args, **kwargs):
        result = real_run(*args, **kwargs)
        captured["keyed"] = _by_key(result)
        return result

    with pytest.MonkeyPatch.context() as mp:
        import test_rerouting_golden

        mp.setattr(test_rerouting_golden, "run_scenario", keep)
        _run_deck(deck)
    return captured["keyed"]


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


def test_flow_variant_without_entry_stage_fails_at_setup():
    flow = [
        {
            "dist_key": "d",
            "journey_info": [
                {"variant_data": {"id": 1, "percentage": 50, "entry_stages": ["a"]}},
                {"variant_data": {"id": 2, "percentage": 50, "entry_stages": ["b"]}},
            ],
        }
    ]
    scenario_mod._check_flow_variants(flow, {"a": 3, "b": 4})
    with pytest.raises(ValueError, match="variant 2 has no valid entry stage"):
        scenario_mod._check_flow_variants(flow, {"a": 3, "b": -1})
    # A variant that is never drawn is not checked.
    flow[0]["journey_info"][1]["variant_data"]["percentage"] = 0
    scenario_mod._check_flow_variants(flow, {"a": 3})


def test_manifest_records_the_seeding_scheme():
    result = _run_quiet(_load("blind_spawn_discovery/config_mixed.json", 1.0, 2))
    try:
        manifest = json.loads(Path(result.manifest_file).read_text(encoding="utf-8"))
    finally:
        result.cleanup()
    assert manifest["agent_seeding"] == "spawn-key-blake2b-v1"


def _next_stage(**seeds) -> str:
    from shapely.geometry import box

    from pyfds_evac.core.direct_steering_runtime import advance_path_target

    stages = {f"s{i}": {"polygon": box(i, 0, i + 1, 1)} for i in range(20)}
    wait_info = {
        "path_choices": {"a": [(name, 1.0) for name in stages]},
        "stage_configs": stages,
        "current_target_stage": "a",
        "step_index": 3,
        **seeds,
    }
    advance_path_target(wait_info)
    return wait_info["current_target_stage"]


def test_next_stage_choice_has_its_own_stream():
    # choice_seed, when present, decides; base_seed then does not.
    picks = {_next_stage(base_seed=b, choice_seed=5) for b in range(10)}
    assert len(picks) == 1
    # A state without choice_seed falls back to base_seed, as before.
    assert _next_stage(base_seed=5) == _next_stage(base_seed=0, choice_seed=5)


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
