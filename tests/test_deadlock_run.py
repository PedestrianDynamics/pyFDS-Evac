"""A jammed run stops with end_reason "deadlock" and reports its stuck agents (#760).

Uses the #359 head-on jam of assets/familiarity_test_no_journey: with 5 agents,
seed 23 jams two agents in the CP2 doorway. Before #760 that run stood until the
300 s time limit.
"""

from types import SimpleNamespace

import pytest
from test_familiarity_no_journey import _run, vis_model  # noqa: F401
from test_scheduled_exits import RUN_MODES, SEED, _scenario

from pyfds_evac.core.scenario import _deadlock_held, _mobile_positions, run_scenario

pytestmark = pytest.mark.slow


def test_a_doorway_jam_ends_the_run_as_a_deadlock(tmp_path, vis_model):  # noqa: F811
    result = _run(tmp_path, vis_model, 5, 23)
    try:
        assert result.end_reason == "deadlock"
        assert result.status == "incomplete"
        assert result.evacuation_time < 300.0
        deadlock = result.metrics["deadlock"]
        assert deadlock["agents"] == 5 - result.agents_evacuated == 2
        assert result.evacuation_time == pytest.approx(deadlock["since_s"] + 100.0)
        assert sorted(map(tuple, deadlock["positions"])) == [(3.6, 1.99), (3.92, 1.44)]
    finally:
        result.cleanup()


def test_a_run_that_empties_has_no_deadlock_key(tmp_path, vis_model):  # noqa: F811
    result = _run(tmp_path, vis_model, 5, 1)
    try:
        assert result.end_reason == "all_evacuated"
        assert "deadlock" not in result.metrics
    finally:
        result.cleanup()


@pytest.mark.parametrize("mode", sorted(RUN_MODES))
def test_a_crowd_waiting_for_a_scheduled_exit_is_not_a_deadlock(mode):
    """Both exits open at 150 s: the crowd waits there, then leaves (#373)."""
    opens = {"open_from_s": 150.0}
    scenario = _scenario({"west": opens, "east": opens})
    scenario.sim_params["max_simulation_time"] = 300.0
    result = run_scenario(scenario, seed=SEED, **RUN_MODES[mode])
    try:
        assert result.end_reason == "all_evacuated"
        assert "deadlock" not in result.metrics
    finally:
        result.cleanup()


def _agent(agent_id, speed=1.0, model=None):
    state = type("CollisionFreeSpeedModelState", (), {"desired_speed": speed})()
    return SimpleNamespace(
        id=agent_id,
        position=(float(agent_id), 0.5),
        model=state if model is None else model,
    )


@pytest.mark.parametrize(
    ("agents", "incapacitated", "premovement", "wait_info", "held"),
    [
        ([_agent(1)], set(), {}, {1: {"state": "to_target"}}, False),
        ([_agent(1)], set(), {1: {"activated": True}}, {}, False),
        ([_agent(1)], set(), {1: {"activated": False}}, {}, True),
        ([_agent(1)], set(), {}, {1: {"state": "waiting"}}, True),
        ([_agent(1)], set(), {}, {1: {"state": "idle"}}, True),
        ([_agent(1, 0.0)], set(), {}, {}, True),
        # Incapacitated agents never hold the rule, whatever they report.
        (
            [_agent(1, 0.0), _agent(2)],
            {1},
            {1: {"activated": False}},
            {1: {"state": "idle"}},
            False,
        ),
    ],
    ids=[
        "moving",
        "premovement-done",
        "premovement",
        "waiting",
        "idle",
        "zero-speed",
        "incapacitated-skipped",
    ],
)
def test_deadlock_hold_covers_agents_that_may_move_later(
    agents, incapacitated, premovement, wait_info, held
):
    simulation = SimpleNamespace(agents=lambda: agents)
    assert _deadlock_held(simulation, incapacitated, premovement, wait_info) is held


def test_mobile_positions_skip_incapacitated_agents():
    simulation = SimpleNamespace(agents=lambda: [_agent(1), _agent(2)])
    assert _mobile_positions(simulation, {1}) == {2: (2.0, 0.5)}
