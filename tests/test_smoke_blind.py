"""Smoke-blind runs and exit replay for ASET/RSET arms (#341).

Three arms share one fire on the T-junction of the verification harness, with
smoke and CO in the right arm only:

* ``none``: no fire at all;
* ``blind`` (U): the fire is sampled, but agents act as in clear air;
* ``speed`` (S): smoke slows agents, rerouting is off and every agent is sent
  to the exit it took in the ``blind`` run.

Replay is keyed by spawn order, but trajectories are compared by agent id,
which JuPedSim numbers process-wide (#198), so every arm runs in its own
interpreter.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

# One worker runs this module, so its module-scoped runs happen once.
pytestmark = pytest.mark.xdist_group("test_smoke_blind")

REPO = Path(__file__).resolve().parents[1]
K_RIGHT_ARM = 2.0  # 1/m, enough for the route gate to refuse the right arm
CO_RIGHT_ARM = 0.01  # volume fraction


def _fire_models(spec):
    """Smoke and FED models with the fire confined to the right arm."""
    from harness import make_fed_model, make_smoke_model, region_x, uniform

    x_min = spec.right_arm_x_min
    smoke = make_smoke_model(region_x(K_RIGHT_ARM, x_min=x_min))
    fed = make_fed_model(
        co_volume_fraction=region_x(CO_RIGHT_ARM, x_min=x_min),
        co2_volume_fraction=uniform(0.0),
        o2_volume_fraction=uniform(0.209),
    )
    return smoke, fed


def _replay_map(rows) -> dict[tuple[str, int], str]:
    """``{(origin, spawn_index): exit_id}`` from exit history rows."""
    return {(r["origin"], r["spawn_index"]): r["exit_id"] for r in rows}


def _run_arm(arm: str, out: Path, replay: Path | None) -> None:
    """Run one arm and dump its trajectories and histories as JSON."""
    sys.path.insert(0, str(REPO / "tests" / "verification"))
    from harness import TJunctionSpec, t_junction_scenario

    from pyfds_evac.core.scenario import run_scenario

    spec = TJunctionSpec(max_simulation_time=60.0)
    kwargs = {}
    if arm != "none":
        kwargs["smoke_speed_model"], kwargs["fed_model"] = _fire_models(spec)
    kwargs["smoke_blind"] = arm == "blind"
    if replay is not None:
        rows = json.loads(replay.read_text(encoding="utf-8"))["exits"]
        kwargs["replay_exits"] = _replay_map(rows)
    result = run_scenario(t_junction_scenario(spec), **kwargs)
    try:
        frames = result.trajectory_dataframe()
        data = {
            "trajectory": frames[["frame", "id", "x", "y"]].values.tolist(),
            "exits": result.exit_history,
            "smoke": result.smoke_history,
            "fed": result.fed_history,
        }
    finally:
        result.cleanup()
    out.write_text(json.dumps(data), encoding="utf-8")


def _isolated(arm: str, tmp_path: Path, replay: Path | None = None) -> dict:
    """Run *arm* in a fresh interpreter (#198) and load its JSON."""
    out = tmp_path / f"{arm}.json"
    args = [sys.executable, __file__, arm, str(out)]
    if replay is not None:
        args.append(str(replay))
    subprocess.run(args, check=True, cwd=REPO, stdout=subprocess.DEVNULL)
    return json.loads(out.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def arms(tmp_path_factory) -> dict[str, dict]:
    tmp = tmp_path_factory.mktemp("arms")
    blind = _isolated("blind", tmp)
    return {
        "none": _isolated("none", tmp),
        "blind": blind,
        "speed": _isolated("speed", tmp, replay=tmp / "blind.json"),
        "speed_free": _isolated("speed", tmp),
    }


def test_blind_fire_walks_like_no_fire(arms):
    assert arms["blind"]["trajectory"] == arms["none"]["trajectory"]
    assert arms["blind"]["exits"] == arms["none"]["exits"]


def test_blind_run_still_writes_histories(arms):
    smoke, fed = arms["blind"]["smoke"], arms["blind"]["fed"]
    assert max(row["extinction_per_m"] for row in smoke) == K_RIGHT_ARM
    assert {row["speed_factor"] for row in smoke} == {1.0}
    assert max(row["fed_cumulative"] for row in fed) > 0.0
    assert "fic" in fed[0]
    assert not any(row["incapacitated"] for row in fed)


def test_replay_changes_the_exits_smoke_would_pick(arms):
    # Without replay the gate keeps agents out of the smoky right arm, so the
    # replay below is what holds S on the exits of U.
    assert arms["speed_free"]["exits"] != arms["blind"]["exits"]


def test_speed_only_equals_blind_where_k_is_zero(arms):
    speed, blind = arms["speed"], arms["blind"]
    assert speed["exits"] == blind["exits"]
    smoky = [r["time_s"] for r in speed["smoke"] if r["extinction_per_m"] > 0.0]
    assert smoky, "the speed-only arm never met smoke"
    first_frame = round(min(smoky) * 10)  # 10 fps trajectories
    before = [row for row in speed["trajectory"] if row[0] <= first_frame]
    assert before == [row for row in blind["trajectory"] if row[0] <= first_frame]
    assert speed["trajectory"] != blind["trajectory"]


def _harness_scenario(max_time: float):
    sys.path.insert(0, str(REPO / "tests" / "verification"))
    from harness import TJunctionSpec, t_junction_scenario

    spec = TJunctionSpec(max_simulation_time=max_time)
    return spec, t_junction_scenario(spec)


def test_replay_in_one_process_follows_spawn_order():
    # The second run's JuPedSim ids are offset (#198); spawn order is not.
    from pyfds_evac.core.scenario import run_scenario

    spec, scenario = _harness_scenario(30.0)
    smoke, _ = _fire_models(spec)
    blind = run_scenario(scenario, smoke_blind=True, smoke_speed_model=smoke)
    blind.cleanup()
    replay = _replay_map(blind.exit_history)
    smoke, _ = _fire_models(spec)
    speed = run_scenario(scenario, smoke_speed_model=smoke, replay_exits=replay)
    manifest = json.loads(Path(speed.manifest_file).read_text(encoding="utf-8"))
    speed.cleanup()
    assert [r["agent_id"] for r in speed.exit_history] != [
        r["agent_id"] for r in blind.exit_history
    ]
    assert _replay_map(speed.exit_history) == replay
    assert manifest["replay_exits"]["agents"] == len(replay)
    assert len(manifest["replay_exits"]["sha256"]) == 64


def test_spawn_keys_count_per_origin():
    # A blocked source spawning late must not shift the other source's keys.
    from pyfds_evac.core.scenario import _spawn_key

    def keys(order):
        spawn_keys, counts = {}, {}
        for agent_id, origin in enumerate(order):
            _spawn_key(spawn_keys, counts, agent_id, origin)
        return sorted(spawn_keys.values())

    assert keys(["a", "b", "a"]) == keys(["a", "a", "b"])
    assert keys(["a", "b", "a"]) == [("a", 0), ("a", 1), ("b", 0)]


def test_replay_that_is_not_applied_fails(monkeypatch):
    # The agent keeps its geometric (right) exit; replay must not pass silently.
    from harness import EXIT_LEFT

    import pyfds_evac.core.scenario as scenario_mod

    _, scenario = _harness_scenario(5.0)
    monkeypatch.setattr(scenario_mod, "_assign_initial_exit", lambda *a, **k: None)
    origins = [f"flow:{key}" for key in scenario.raw["distributions"]]
    replay = {(o, i): EXIT_LEFT for o in origins for i in range(100)}
    with pytest.raises(scenario_mod.ExitReplayError, match="could not be sent"):
        scenario_mod.run_scenario(scenario, replay_exits=replay)


def test_replay_without_the_agent_fails():
    from pyfds_evac.core.scenario import run_scenario

    _, scenario = _harness_scenario(5.0)
    with pytest.raises(
        ValueError, match="no exit for origin .flow:spawn_stem. spawn index 0"
    ):
        run_scenario(scenario, replay_exits={})


def test_replay_with_an_unknown_exit_fails():
    from pyfds_evac.core.scenario import run_scenario

    _, scenario = _harness_scenario(5.0)
    with pytest.raises(ValueError, match="lacks: exit_nowhere"):
        run_scenario(scenario, replay_exits={("initial", 0): "exit_nowhere"})


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("spawn_index,exit_id\n1,e\n", "missing column"),
        ("origin,spawn_index,exit_id\no,one,e\n", "not an integer"),
        ("origin,spawn_index,exit_id\no,1,e\no,1,f\n", "listed twice"),
        ("origin,spawn_index,exit_id\no,1,\n", "has no exit_id"),
    ],
)
def test_bad_replay_file_fails(tmp_path, text, message):
    from pyfds_evac.core.run_config import load_replay_exits

    path = tmp_path / "exits.csv"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        load_replay_exits(path)


def test_replay_file_round_trip(tmp_path):
    sys.path.insert(0, str(REPO))
    import run
    from pyfds_evac.core.run_config import load_replay_exits

    path = tmp_path / "exits.csv"
    rows = [
        {"agent_id": 3, "origin": "o", "spawn_index": 0, "exit_id": "a"},
        {"agent_id": 7, "origin": "o", "spawn_index": 1, "exit_id": "b"},
        {"agent_id": 8, "origin": "p", "spawn_index": 0, "exit_id": "a"},
    ]
    run._write_exit_history_csv(rows, str(path))
    assert load_replay_exits(path) == {("o", 0): "a", ("o", 1): "b", ("p", 0): "a"}


def test_smoke_blind_turns_off_rerouting_and_tenability():
    from argparse import Namespace
    from types import SimpleNamespace

    from pyfds_evac.core.run_config import build_run_kwargs

    opts = Namespace(
        seed=None,
        fds_dir=None,
        constant_extinction=0.5,
        smoke_update_interval=1.0,
        smoke_slice_height=2.0,
        enable_rerouting=True,
        reroute_interval=1.0,
        vis_cache=None,
        disable_tenability=False,
        fic_alpha=1.2,
        fic_min_factor=0.0,
        fed_threshold=1.0,
        output_route_cost_history=None,
        smoke_blind=True,
    )
    kwargs = build_run_kwargs(SimpleNamespace(raw={}), opts)
    assert kwargs["smoke_blind"] is True
    assert kwargs["smoke_speed_model"] is not None
    assert kwargs["reroute_config"] is None
    assert kwargs["tenability_config"] is None


if __name__ == "__main__":
    _run_arm(
        sys.argv[1],
        Path(sys.argv[2]),
        Path(sys.argv[3]) if len(sys.argv) > 3 else None,
    )
