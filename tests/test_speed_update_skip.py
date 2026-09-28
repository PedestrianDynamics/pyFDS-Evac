"""Internals of the per-step speed update added for #240.

``tests/test_speed_update_pin.py`` pins the resulting speeds. These tests pin
the two mechanisms behind the speed-up: the precomputed active zones, and the
early return outside every zone when the speed state is unchanged.
"""

import pytest
from shapely.geometry import Polygon

from pyfds_evac.core.direct_steering_runtime import (
    _find_steering_zone,
    active_steering_zones,
    set_agent_smoke_factor,
    update_checkpoint_speed,
)


class CollisionFreeSpeedModelState:
    """Named like the JuPedSim state so ``_MODEL_SPEED_ATTRS`` maps it."""

    def __init__(self, desired_speed: float):
        self._speed = float(desired_speed)
        self.writes: list[float] = []

    @property
    def desired_speed(self) -> float:
        return self._speed

    @desired_speed.setter
    def desired_speed(self, value: float) -> None:
        self.writes.append(float(value))
        self._speed = float(value)


class RecordingAgent:
    def __init__(self, desired_speed: float):
        self.model = CollisionFreeSpeedModelState(desired_speed)


def _square(x0: float, x1: float) -> Polygon:
    return Polygon([(x0, 0.0), (x1, 0.0), (x1, 2.0), (x0, 2.0)])


ZONE = _square(0.0, 2.0)
INSIDE = (1.0, 1.0)
OUTSIDE = (10.0, 1.0)


def _update(state, info, agent, xy, **kwargs):
    update_checkpoint_speed(state, info, 1, agent, None, None, *xy, **kwargs)


class TestActiveSteeringZones:
    def test_keeps_only_zones_that_change_speed_in_dict_order(self):
        info = {
            "exit": {"polygon": ZONE},
            "slow": {"polygon": ZONE, "speed_factor": 0.5},
            "unit": {"polygon": ZONE, "speed_factor": 1.0},
            "fast": {"polygon": ZONE, "speed_factor": 5.0},
            "bad": {"polygon": ZONE, "speed_factor": "x"},
        }
        zones = active_steering_zones(info)
        assert [(key, factor) for key, factor, _ in zones] == [
            ("slow", 0.5),
            ("fast", 3.0),
        ]
        assert all(polygon is ZONE for _, _, polygon in zones)

    @pytest.mark.parametrize("info", [None, {}])
    def test_empty_info_has_no_zones(self, info):
        assert active_steering_zones(info) == ()

    def test_precomputed_zones_match_the_scan(self):
        info = {
            "a": {"polygon": ZONE, "speed_factor": 0.8},
            "b": {"polygon": ZONE, "speed_factor": 0.4},
            "c": {"polygon": _square(5.0, 6.0), "speed_factor": 0.1},
        }
        zones = active_steering_zones(info)
        for xy in (INSIDE, OUTSIDE, (5.5, 1.0)):
            assert _find_steering_zone(info, *xy, zones) == _find_steering_zone(
                info, *xy
            )

    def test_precomputed_zones_are_used_as_given(self):
        info = {"z": {"polygon": ZONE, "speed_factor": 0.5}}
        zones = active_steering_zones(info)
        info["z"]["speed_factor"] = 1.0
        assert _find_steering_zone(info, *INSIDE, zones) == ("z", 0.5)
        assert _find_steering_zone(info, *INSIDE) is None


class TestSkipUnchanged:
    def test_unchanged_state_outside_zones_is_not_rewritten(self):
        info = {"z": {"polygon": ZONE, "speed_factor": 0.5}}
        state, agent = {}, RecordingAgent(1.2)
        set_agent_smoke_factor(state, 1, agent, 0.5)
        _update(state, info, agent, OUTSIDE)
        assert agent.model.writes == [pytest.approx(0.6)]
        for _ in range(5):
            _update(state, info, agent, OUTSIDE)
        assert agent.model.writes == [pytest.approx(0.6)]

    def test_inside_a_zone_every_call_writes(self):
        info = {"z": {"polygon": ZONE, "speed_factor": 0.5}}
        state, agent = {}, RecordingAgent(1.2)
        for _ in range(3):
            _update(state, info, agent, INSIDE)
        assert agent.model.writes == [pytest.approx(0.6)] * 3

    def test_leaving_a_zone_restores_despite_unchanged_factors(self):
        info = {"z": {"polygon": ZONE, "speed_factor": 0.5}}
        state, agent = {}, RecordingAgent(1.2)
        set_agent_smoke_factor(state, 1, agent, 0.5)
        _update(state, info, agent, OUTSIDE)
        _update(state, info, agent, INSIDE)
        _update(state, info, agent, OUTSIDE)
        assert agent.model.writes == [
            pytest.approx(0.6),
            pytest.approx(0.3),
            pytest.approx(0.6),
        ]

    def test_state_change_outside_zones_is_applied(self):
        state, agent = {}, RecordingAgent(1.2)
        set_agent_smoke_factor(state, 1, agent, 0.5)
        _update(state, {}, agent, OUTSIDE)
        set_agent_smoke_factor(state, 1, agent, 0.25)
        _update(state, {}, agent, OUTSIDE)
        state[1]["original_speed"] = 2.0
        _update(state, {}, agent, OUTSIDE)
        assert agent.model.writes == [
            pytest.approx(0.6),
            pytest.approx(0.3),
            pytest.approx(0.5),
        ]

    def test_write_without_state_update_is_kept_outside_zones(self):
        """Documents the invariant: writers must update the speed state."""
        state, agent = {}, RecordingAgent(1.2)
        set_agent_smoke_factor(state, 1, agent, 0.5)
        _update(state, {}, agent, OUTSIDE)
        agent.model.desired_speed = 0.9
        _update(state, {}, agent, OUTSIDE)
        assert agent.model.desired_speed == pytest.approx(0.9)
