import pytest
from shapely.geometry import Polygon

from pyfds_evac.core.direct_steering_runtime import (
    restore_agent_speed,
    set_agent_fic_factor,
    set_agent_smoke_factor,
    update_checkpoint_speed,
)


class CollisionFreeSpeedModelState:
    def __init__(self, desired_speed: float):
        self.v0 = float(desired_speed)


class _FakeAgent:
    def __init__(self, desired_speed: float):
        self.model = CollisionFreeSpeedModelState(desired_speed)


ZONE_POLYGON = Polygon([(0.0, 0.0), (0.0, 2.0), (2.0, 2.0), (2.0, 0.0)])


def test_checkpoint_speed_combines_with_smoke_factor_and_restores_to_smoke_only():
    agent = _FakeAgent(2.0)
    agent_speed_state = {}

    set_agent_smoke_factor(agent_speed_state, 1, agent, 0.5)
    update_checkpoint_speed(
        agent_speed_state,
        {},
        1,
        agent,
        "checkpoint-1",
        {"polygon": ZONE_POLYGON, "speed_factor": 0.5},
        1.0,
        1.0,
    )

    assert agent.model.v0 == 0.5

    update_checkpoint_speed(
        agent_speed_state,
        {},
        1,
        agent,
        None,
        None,
        5.0,
        5.0,
    )

    assert agent.model.v0 == 1.0


class TestFicDoesNotCompound:
    """FIC responds to the concentration present now, so it cannot accumulate.

    It used to. The runtime multiplied the agent's *current* desired speed by
    the factor on every tick, so a constant FIC of 0.5 produced 0.65, then
    0.65^2, then 0.65^3, and the agent halted. `assets/fic_vs_fed_speed` ran
    0/30 evacuated in 400 s because of it; nothing caught it because no test
    ran a simulation with an irritant present.

    The fix is to treat FIC like smoke: cache the factor and recompute from the
    stored baseline, never from the current speed.
    """

    def test_a_constant_factor_applied_repeatedly_holds_the_speed(self):
        agent = _FakeAgent(1.3)
        state = {}
        for _ in range(10):
            set_agent_fic_factor(state, 1, agent, 0.65)
        assert agent.model.v0 == pytest.approx(1.3 * 0.65)

    def test_the_factor_is_measured_from_the_baseline_not_the_current_speed(self):
        """A weaker irritant must speed the agent up again, not slow it further."""
        agent = _FakeAgent(1.3)
        state = {}
        set_agent_fic_factor(state, 1, agent, 0.5)
        assert agent.model.v0 == pytest.approx(0.65)
        set_agent_fic_factor(state, 1, agent, 0.9)
        assert agent.model.v0 == pytest.approx(1.3 * 0.9)

    def test_leaving_the_irritant_restores_full_speed(self):
        agent = _FakeAgent(1.3)
        state = {}
        set_agent_fic_factor(state, 1, agent, 0.65)
        set_agent_fic_factor(state, 1, agent, 1.0)
        assert agent.model.v0 == pytest.approx(1.3)

    def test_it_composes_with_smoke_rather_than_replacing_it(self):
        agent = _FakeAgent(2.0)
        state = {}
        set_agent_smoke_factor(state, 1, agent, 0.5)
        set_agent_fic_factor(state, 1, agent, 0.6)
        assert agent.model.v0 == pytest.approx(2.0 * 0.5 * 0.6)

    def test_a_checkpoint_zone_multiplies_all_three(self):
        agent = _FakeAgent(2.0)
        state = {}
        set_agent_smoke_factor(state, 1, agent, 0.5)
        set_agent_fic_factor(state, 1, agent, 0.6)
        update_checkpoint_speed(
            state,
            {},
            1,
            agent,
            "checkpoint-1",
            {"polygon": ZONE_POLYGON, "speed_factor": 0.5},
            1.0,
            1.0,
        )
        assert agent.model.v0 == pytest.approx(2.0 * 0.5 * 0.6 * 0.5)

    def test_restoring_outside_a_checkpoint_keeps_the_irritant_penalty(self):
        """Leaving a slow zone must not also clear an irritant still present."""
        agent = _FakeAgent(2.0)
        state = {}
        set_agent_fic_factor(state, 1, agent, 0.6)
        update_checkpoint_speed(
            state,
            {},
            1,
            agent,
            "checkpoint-1",
            {"polygon": ZONE_POLYGON, "speed_factor": 0.5},
            1.0,
            1.0,
        )
        restore_agent_speed(state, 1, agent)
        assert agent.model.v0 == pytest.approx(2.0 * 0.6)
