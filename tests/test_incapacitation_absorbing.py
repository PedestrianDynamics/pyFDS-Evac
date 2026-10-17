"""Incapacitation is absorbing: a dead agent stays, is never counted as
evacuated and is not sampled again; the run ends when every mobile agent
has left (#145, #593, #141).

Decks are synthetic: the corridor of ``tests/verification/harness.py`` with
a uniform lethal CO field (60 000 ppm, collapse at about 23 s) or a lethal
band, so the collapse time is known from the closed form.
"""

from __future__ import annotations

import contextlib
import math
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "verification"))

from harness import (  # noqa: E402
    CorridorSpec,
    TJunctionSpec,
    after,
    corridor_scenario,
    deterministic_tenability,
    first_incapacitation_times,
    make_fed_model,
    make_smoke_model,
    region_x,
    t_junction_scenario,
    uniform,
)

from test_s4_tjunction_reroute import SMOKE_K, _reroute_config  # noqa: E402

from pyfds_evac.core.scenario import run_scenario  # noqa: E402

CO_LETHAL = 0.06  # volume fraction, 60 000 ppm


def _co_model(field, update_interval_s: float = 1.0):
    return make_fed_model(
        co_volume_fraction=field,
        co2_volume_fraction=uniform(0.0),
        o2_volume_fraction=uniform(0.209),
        update_interval_s=update_interval_s,
    )


def _early_low(y_cut: float, until_s: float = 3.0):
    """Lethal CO for agents below ``y_cut`` m during the first ``until_s`` s.

    Splits a spawn group by position: the agents below the cut collapse within
    a second at the low threshold used with it, the others never see the gas
    and stay mobile, so the run goes on with the dead agents inside.
    """
    return lambda t, x, y: CO_LETHAL if (t < until_s and y < y_cut) else 0.0


# Threshold and update interval that collapse an exposed agent within a second.
QUICK = {"threshold": 0.02, "update_interval_s": 0.1}


def _trajectory(result) -> dict[int, list[tuple[float, float, float]]]:
    """Per agent, the (time_s, x, y) rows of the trajectory in time order."""
    with contextlib.closing(sqlite3.connect(result.sqlite_file)) as con:
        fps = float(
            con.execute("SELECT value FROM metadata WHERE key='fps'").fetchone()[0]
        )
        rows = con.execute(
            "SELECT id, frame, pos_x, pos_y FROM trajectory_data ORDER BY frame"
        ).fetchall()
    out: dict[int, list[tuple[float, float, float]]] = {}
    for agent_id, frame, x, y in rows:
        out.setdefault(agent_id, []).append((frame / fps, x, y))
    return out


def _run(spec, field, *, premovement_s=None, update_interval_s=1.0, threshold=1.0):
    scenario = corridor_scenario(spec)
    if premovement_s is not None:
        params = scenario.raw["distributions"]["spawn_near"]["parameters"]
        params["use_premovement"] = True
        params["premovement_distribution"] = "constant"
        params["premovement_param_a"] = premovement_s
    return run_scenario(
        scenario,
        seed=spec.seed,
        fed_model=_co_model(field, update_interval_s),
        tenability_config=deterministic_tenability(threshold),
    )


def test_premovement_does_not_wake_an_incapacitated_agent():
    """#145: the activation at the end of the delay must skip a dead agent."""
    spec = CorridorSpec(num_agents=2, max_simulation_time=80.0)
    result = _run(spec, _early_low(2.5), premovement_s=10.0, **QUICK)
    try:
        incap = first_incapacitation_times(result)
        assert len(incap) == 1
        (dead_id, t_inc) = next(iter(incap.items()))
        assert t_inc < 10.0

        track = _trajectory(result)[dead_id]
        at_collapse = next((x, y) for t, x, y in track if t >= t_inc)
        after_collapse = [(x, y) for t, x, y in track if t >= t_inc]
        assert len(after_collapse) > 100
        for x, y in after_collapse:
            assert x == pytest.approx(at_collapse[0], abs=1e-6)
            assert y == pytest.approx(at_collapse[1], abs=1e-6)

        metrics = result.metrics
        assert metrics["agents_evacuated"] == 1
        assert metrics["agents_remaining"] == 1
    finally:
        result.cleanup()


def test_exposure_stops_at_the_collapse_row():
    """An incapacitated agent is not sampled again: its last row is the collapse."""
    spec = CorridorSpec(num_agents=5, max_simulation_time=60.0)
    result = _run(spec, _early_low(2.5), **QUICK)
    try:
        incap = first_incapacitation_times(result)
        assert 0 < len(incap) < spec.num_agents
        for agent_id, t_inc in incap.items():
            rows = [r for r in result.fed_history if r["agent_id"] == agent_id]
            assert [r for r in rows if r["time_s"] > t_inc] == []
            assert sum(1 for r in rows if r["incapacitated"]) == 1
    finally:
        result.cleanup()


class _StepObserver:
    """Frame recorder that notes when agents leave and when JuPedSim lists them.

    ``t`` is the simulated time at the start of the next step, which is the time
    the exposure loop samples at.
    """

    def __init__(self):
        self.t = 0.0
        self.left: list[tuple[float, int]] = []
        self.listed: list[tuple[float, list[int]]] = []

    def start(self, *args, **kwargs):
        pass

    def leaves(self, agent_id, exit_id):
        self.left.append((self.t, int(agent_id)))

    def after_step(self, simulation, **kwargs):
        self.t = float(simulation.elapsed_time())
        listed = [int(a) for a in simulation.removed_agents()]
        if listed:
            self.listed.append((self.t, listed))

    def finish(self, *args, **kwargs):
        pass


def _lethal_from(onset_s: float):
    return after(onset_s, uniform(CO_LETHAL))


def _run_with_observer(scenario, seed, field, observer):
    return run_scenario(
        scenario,
        seed=seed,
        fed_model=_co_model(field, update_interval_s=0.005),
        tenability_config=deterministic_tenability(1e-6),
        frame_recorder=observer,
    )


def _throttled_corridor():
    spec = CorridorSpec(num_agents=1, max_simulation_time=80.0)
    scenario = corridor_scenario(spec)
    exit_ = scenario.raw["exits"]["exit_far"]
    exit_["enable_throughput_throttling"] = True
    exit_["max_throughput"] = 2.0
    return spec, scenario


def test_agent_dead_at_the_exit_is_not_marked_for_removal(monkeypatch):
    """#593: collapse in the step the exit is reached must not count as evacuated."""
    import pyfds_evac.core.scenario as scenario_module

    spec, scenario = _throttled_corridor()
    control = _StepObserver()
    reached_at: list[float] = []
    real_reached = scenario_module.reached_stage

    def reached(*args, **kwargs):
        ok = real_reached(*args, **kwargs)
        if ok:
            reached_at.append(control.t)
        return ok

    monkeypatch.setattr(scenario_module, "reached_stage", reached)
    baseline = run_scenario(scenario, seed=spec.seed, frame_recorder=control)
    try:
        assert baseline.metrics["agents_evacuated"] == 1
        assert len(control.left) == 1
    finally:
        baseline.cleanup()
    t_reach = reached_at[-1]
    monkeypatch.undo()

    spec, scenario = _throttled_corridor()
    observer = _StepObserver()
    result = _run_with_observer(scenario, spec.seed, _lethal_from(t_reach), observer)
    try:
        incap = first_incapacitation_times(result)
        assert incap and next(iter(incap.values())) == pytest.approx(t_reach)
        assert observer.left == []
        metrics = result.metrics
        assert metrics["agents_evacuated"] == 0
        assert metrics["agents_remaining"] == 1
        assert result.agents_incapacitated <= metrics["agents_remaining"]
    finally:
        result.cleanup()


def test_dead_agent_in_a_checkpoint_deck_is_not_steered(monkeypatch):
    """No arrival test, wait or speed restoration reaches a dead agent."""
    import pyfds_evac.core.scenario as scenario_module
    from test_checkpoint_arrival import _scenario as checkpoint_scenario

    seed = 1
    scenario = checkpoint_scenario(seed)
    scenario.raw["distributions"]["jps-distributions_0"]["parameters"]["number"] = 2
    observer = _StepObserver()
    tested: list[tuple[float, float, float]] = []
    real_reached = scenario_module.reached_stage

    def reached(x, y, *args, **kwargs):
        tested.append((observer.t, x, y))
        return real_reached(x, y, *args, **kwargs)

    monkeypatch.setattr(scenario_module, "reached_stage", reached)
    result = run_scenario(
        scenario,
        seed=seed,
        fed_model=_co_model(_early_low(2.0, until_s=2.0), QUICK["update_interval_s"]),
        tenability_config=deterministic_tenability(QUICK["threshold"]),
        frame_recorder=observer,
    )
    try:
        incap = first_incapacitation_times(result)
        assert len(incap) == 1
        (dead_id, t_inc) = next(iter(incap.items()))

        track = _trajectory(result)[dead_id]
        after_collapse = [(x, y) for t, x, y in track if t >= t_inc]
        assert len(after_collapse) > 100
        for (xa, ya), (xb, yb) in zip(after_collapse, after_collapse[1:]):
            assert math.hypot(xb - xa, yb - ya) < 1e-6
        # The arrival test is never run on the dead agent's position.
        x_dead, y_dead = after_collapse[0]
        assert [
            t
            for t, x, y in tested
            if t > t_inc and math.hypot(x - x_dead, y - y_dead) < 1e-3
        ] == []
        assert result.metrics["agents_evacuated"] == 1
        assert result.metrics["agents_remaining"] == 1
    finally:
        result.cleanup()


def test_dead_agents_are_not_rerouted():
    """The reroute pass skips a dead agent: no route switch after the collapse."""
    spec = TJunctionSpec(seed=42)
    stem = region_x(
        CO_LETHAL,
        x_min=spec.stem_center_x - spec.stem_half_width_m,
        x_max=spec.right_arm_x_min,
    )
    smoke = make_smoke_model(
        after(spec.smoke_onset_s, region_x(SMOKE_K, x_min=spec.right_arm_x_min))
    )
    result = run_scenario(
        t_junction_scenario(spec),
        seed=spec.seed,
        smoke_speed_model=smoke,
        fed_model=_co_model(after(spec.smoke_onset_s, stem), 0.1),
        tenability_config=deterministic_tenability(0.02),
        reroute_config=_reroute_config(),
    )
    try:
        incap = first_incapacitation_times(result)
        assert len(incap) >= 3
        late = [
            row
            for row in result.route_history or []
            if row["agent_id"] in incap and row["time_s"] > incap[row["agent_id"]]
        ]
        assert late == []
        # The agents that were not caught in the stem still reroute.
        assert len(result.route_history or []) > 0
    finally:
        result.cleanup()


def test_run_ends_when_every_mobile_agent_has_left():
    """#141: dead agents inside do not keep the run going to the time limit."""
    spec = CorridorSpec(num_agents=5, max_simulation_time=120.0)
    result = _run(spec, _early_low(2.5), **QUICK)
    try:
        metrics = result.metrics
        assert 0 < result.agents_incapacitated < metrics["total_agents"]
        assert metrics["end_reason"] == "all_mobile_left"
        assert metrics["status"] == "incomplete"
        assert metrics["success"] is False
        assert result.agents_incapacitated == metrics["agents_remaining"]
        assert metrics["agents_evacuated"] + metrics["agents_remaining"] == (
            metrics["total_agents"]
        )
        assert metrics["evacuation_time"] < spec.max_simulation_time - 1.0

        tracks = _trajectory(result)
        end = max(t for track in tracks.values() for t, _, _ in track)
        assert metrics["evacuation_time"] == pytest.approx(end, abs=0.1)

        dead = first_incapacitation_times(result)
        evacuated = [track for a, track in tracks.items() if a not in dead]
        assert len(evacuated) == metrics["agents_evacuated"]
        last_frame = max(track[-1][0] for track in evacuated)
        assert metrics["last_exit_time"] is not None
        assert metrics["last_exit_time"] <= metrics["evacuation_time"]
        # The trajectory has 10 frames per second.
        assert metrics["last_exit_time"] == pytest.approx(last_frame, abs=0.1)
    finally:
        result.cleanup()


def test_nobody_leaving_gives_no_last_exit_time():
    spec = CorridorSpec(num_agents=2, max_simulation_time=60.0)
    result = _run(spec, uniform(CO_LETHAL), **QUICK)
    try:
        assert result.metrics["end_reason"] == "all_mobile_left"
        assert result.metrics["last_exit_time"] is None
        assert result.metrics["agents_evacuated"] == 0
        assert result.metrics["evacuation_time"] < 5.0
    finally:
        result.cleanup()


def test_completed_run_keeps_its_end_reason():
    """Without incapacitation the run still ends all_evacuated, with a last exit."""
    spec = CorridorSpec(num_agents=2, max_simulation_time=80.0)
    result = _run(spec, uniform(0.0), **QUICK)
    try:
        assert result.metrics["end_reason"] == "all_evacuated"
        assert result.metrics["last_exit_time"] == pytest.approx(
            result.metrics["evacuation_time"], abs=0.02
        )
    finally:
        result.cleanup()


def test_incapacitated_agents_are_switched_to_the_direct_steering_stage(monkeypatch):
    """An incapacitated agent leaves its exit journey, so JuPedSim cannot remove it."""
    import jupedsim as jps
    from test_run_outcome import _scenario as room_scenario

    calls: list[tuple[int, int, int]] = []
    real_switch = jps.Simulation.switch_agent_journey

    def switch(self, agent_id, journey_id, stage_id):
        calls.append((agent_id, journey_id, stage_id))
        return real_switch(self, agent_id, journey_id, stage_id)

    monkeypatch.setattr(jps.Simulation, "switch_agent_journey", switch)
    result = run_scenario(
        room_scenario(30.0, number=3),
        seed=3,
        fed_model=_co_model(uniform(CO_LETHAL), QUICK["update_interval_s"]),
        tenability_config=deterministic_tenability(QUICK["threshold"]),
    )
    try:
        assert result.agents_incapacitated == 3
        assert len({(journey, stage) for _, journey, stage in calls}) == 1
        assert sorted(agent for agent, _, _ in calls) == sorted(
            {r["agent_id"] for r in result.fed_history}
        )
    finally:
        result.cleanup()


def _list_everyone_once_at(monkeypatch, t_s: float):
    """Make ``removed_agents`` name every agent once, at the first step from t_s."""
    import jupedsim as jps

    real_removed = jps.Simulation.removed_agents
    done = {"listed": False}

    def removed(self):
        if done["listed"] or self.elapsed_time() < t_s - 1e-9:
            return real_removed(self)
        done["listed"] = True
        return [a.id for a in self.agents()]

    monkeypatch.setattr(jps.Simulation, "removed_agents", removed)


def test_agent_listed_as_removed_is_not_incapacitated_in_the_same_step(monkeypatch):
    """An agent JuPedSim has already listed as removed has left (tie-break)."""
    spec = CorridorSpec(num_agents=1, max_simulation_time=20.0)
    t_list = 5.0
    _list_everyone_once_at(monkeypatch, t_list)
    result = _run(
        spec, _lethal_from(t_list - 1e-6), update_interval_s=0.005, threshold=1e-6
    )
    try:
        t_inc = next(iter(first_incapacitation_times(result).values()))
        # Listed at the step starting at 5.0 s: the sample of that step is
        # skipped, the next one (one time step later) is the first collapse.
        assert t_inc == pytest.approx(t_list + 0.01, abs=0.006)
    finally:
        result.cleanup()


def test_removal_of_an_incapacitated_agent_is_an_error(monkeypatch):
    """JuPedSim removing a dead agent breaks the model; the run says so."""
    spec = CorridorSpec(num_agents=2, max_simulation_time=20.0)
    _list_everyone_once_at(monkeypatch, 5.0)
    with pytest.raises(RuntimeError, match=r"Incapacitated agent\(s\) \[\d+\]"):
        _run(spec, _early_low(2.5), **QUICK)
