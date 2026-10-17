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
    spec = CorridorSpec(num_agents=1, max_simulation_time=60.0)
    result = _run(spec, uniform(CO_LETHAL), premovement_s=30.0)
    try:
        incap = first_incapacitation_times(result)
        assert len(incap) == 1
        t_inc = next(iter(incap.values()))
        assert t_inc < 30.0

        (track,) = _trajectory(result).values()
        at_collapse = next((x, y) for t, x, y in track if t >= t_inc)
        for t, x, y in track:
            if t < t_inc:
                continue
            assert x == pytest.approx(at_collapse[0], abs=1e-6)
            assert y == pytest.approx(at_collapse[1], abs=1e-6)

        metrics = result.metrics
        assert metrics["agents_evacuated"] == 0
        assert metrics["agents_remaining"] == 1
    finally:
        result.cleanup()



def test_exposure_stops_at_the_collapse_row():
    """An incapacitated agent is not sampled again: its last row is the collapse."""
    spec = CorridorSpec(num_agents=5, max_simulation_time=60.0)
    result = _run(spec, uniform(CO_LETHAL))
    try:
        incap = first_incapacitation_times(result)
        assert len(incap) == spec.num_agents
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
    observer = _StepObserver()
    tested_at: list[float] = []
    real_reached = scenario_module.reached_stage

    def reached(*args, **kwargs):
        tested_at.append(observer.t)
        return real_reached(*args, **kwargs)

    monkeypatch.setattr(scenario_module, "reached_stage", reached)
    result = run_scenario(
        checkpoint_scenario(seed),
        seed=seed,
        fed_model=_co_model(region_x(CO_LETHAL, x_min=7.0, x_max=8.0), 0.1),
        tenability_config=deterministic_tenability(0.02),
        frame_recorder=observer,
    )
    try:
        incap = first_incapacitation_times(result)
        assert len(incap) == 1
        t_inc = next(iter(incap.values()))
        assert [t for t in tested_at if t > t_inc] == []

        (track,) = _trajectory(result).values()
        after_collapse = [(x, y) for t, x, y in track if t >= t_inc]
        assert len(after_collapse) > 10
        for (xa, ya), (xb, yb) in zip(after_collapse, after_collapse[1:]):
            assert math.hypot(xb - xa, yb - ya) < 1e-6
        assert result.metrics["agents_evacuated"] == 0
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
