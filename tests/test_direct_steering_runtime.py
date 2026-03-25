from shapely.geometry import Polygon

from src.core.direct_steering_runtime import (
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
