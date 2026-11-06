"""Irritant slowdown after Purser (SFPE Handbook 6th ed. Ch. 70).

``F_irr`` is Eq. 70.11; the smoke and irritant fractions combine additively
(Eq. 70.12) with a floor, in ``combined_speed_factor``.  The behavioural tests
drive the real speed-update functions with a fake agent, so they also pin the
recomposition from ``original_speed`` on every tick (no compounding).
"""

from __future__ import annotations

import math

import pytest
from shapely.geometry import Polygon

from pyfds_evac.core.direct_steering_runtime import (
    FIC_SPEED_FLOOR,
    combined_speed_factor,
    ensure_agent_speed_state,
    restore_agent_speed,
    set_agent_fic_factor,
    set_agent_smoke_factor,
    update_checkpoint_speed,
)
from pyfds_evac.core.fed import TenabilityConfig, irritant_speed_fraction


def _eq_70_11(x: float) -> float:
    return (math.exp(-((1000.0 * x / 160.0) ** 2)) + 0.2 - 0.2 * x) / 1.2


class TestIrritantSpeedFraction:
    @pytest.mark.parametrize(
        ("fic", "expected"),
        [
            (0.0, 1.000),
            (0.05, 0.914),
            (0.1, 0.714),
            (0.2, 0.308),
            (0.3, 0.141),
            (0.5, 0.083),
            (1.0, 0.0),
            (1.5, 0.0),
        ],
    )
    def test_hand_values(self, fic, expected):
        assert irritant_speed_fraction(fic) == pytest.approx(expected, abs=5e-4)

    @pytest.mark.parametrize("fic", [0.0, 0.05, 0.1, 0.2, 0.3, 0.5, 0.99, 1.0])
    def test_matches_the_closed_form(self, fic):
        assert irritant_speed_fraction(fic) == pytest.approx(_eq_70_11(fic), rel=1e-12)

    def test_continuous_at_one_and_zero_beyond(self):
        assert irritant_speed_fraction(1.0) == 0.0
        assert irritant_speed_fraction(1.0 - 1e-9) == pytest.approx(0.0, abs=1e-9)
        assert irritant_speed_fraction(1.0 + 1e-9) == 0.0

    @pytest.mark.parametrize("fic", [-1.0, -0.0, math.nan, math.inf, -math.inf])
    def test_no_usable_fic_means_no_slowdown(self, fic):
        # +inf is "not finite" too: the guard is on the input, not on the sign.
        assert irritant_speed_fraction(fic) == 1.0

    def test_decreases_with_fic(self):
        values = [irritant_speed_fraction(x / 100) for x in range(0, 101)]
        assert values == sorted(values, reverse=True)

    def test_tenability_config_has_no_curve_parameters(self):
        fields = TenabilityConfig.__dataclass_fields__
        assert "fic_alpha" not in fields
        assert "fic_min_factor" not in fields


class TestCombinedSpeedFactor:
    @pytest.mark.parametrize("smoke", [1.0, 0.7, 0.1, 0.05, 0.0])
    def test_fic_off_returns_smoke_unchanged(self, smoke):
        assert combined_speed_factor(smoke, 1.0) == smoke

    def test_additive_sum(self):
        assert combined_speed_factor(0.8, 0.7) == pytest.approx(0.5)
        assert combined_speed_factor(1.0, 0.3) == pytest.approx(0.3)

    def test_floor(self):
        assert FIC_SPEED_FLOOR == 0.1
        assert combined_speed_factor(0.5, 0.0) == pytest.approx(FIC_SPEED_FLOOR)
        assert combined_speed_factor(1.0, 0.0) == pytest.approx(FIC_SPEED_FLOOR)

    def test_never_below_floor_unless_smoke_already_is(self):
        assert combined_speed_factor(0.05, 0.0) == 0.05
        assert combined_speed_factor(0.05, 0.5) == 0.05

    @pytest.mark.parametrize("smoke", [1.0, 0.6, 0.2, 0.05])
    @pytest.mark.parametrize("fic", [0.0, 0.08, 0.3, 0.7, 1.0])
    def test_never_above_smoke(self, smoke, fic):
        assert combined_speed_factor(smoke, fic) <= smoke


class _Model:
    # The runtime looks the speed attribute up by the model's class name.
    def __init__(self, speed: float):
        self.desired_speed = float(speed)


_Model.__name__ = "CollisionFreeSpeedModelState"


class _Agent:
    def __init__(self, speed: float):
        self.model = _Model(speed)

    @property
    def speed(self) -> float:
        return self.model.desired_speed


ZONE = Polygon([(0.0, 0.0), (0.0, 2.0), (2.0, 2.0), (2.0, 0.0)])
IN, OUT = (1.0, 1.0), (5.0, 5.0)
V0 = 1.4


def _tick(state, agent, *, smoke, fic, where=OUT, zone_factor=None):
    """One step as the run loop does it: smoke factor, FIC factor, then zones."""
    set_agent_smoke_factor(state, 1, agent, smoke)
    set_agent_fic_factor(state, 1, agent, fic)
    cfg = (
        None if zone_factor is None else {"polygon": ZONE, "speed_factor": zone_factor}
    )
    update_checkpoint_speed(
        state, {}, 1, agent, "z" if cfg else None, cfg, where[0], where[1]
    )


class TestBehaviourThroughTheSpeedUpdates:
    def test_fic_off_leaves_the_smoke_speed_unchanged(self):
        agent, state = _Agent(V0), {}
        for _ in range(5):
            _tick(state, agent, smoke=0.6, fic=1.0)
        assert agent.speed == pytest.approx(V0 * 0.6)

    def test_fic_on_uses_the_additive_rule(self):
        agent, state = _Agent(V0), {}
        _tick(state, agent, smoke=0.8, fic=0.7)
        assert agent.speed == pytest.approx(V0 * 0.5)

    def test_fic_rises_then_recovers_without_compounding(self):
        agent, state = _Agent(V0), {}
        _tick(state, agent, smoke=0.8, fic=1.0)
        smoke_only = agent.speed
        assert smoke_only == pytest.approx(V0 * 0.8)
        for _ in range(10):  # constant FIC: the same speed every tick
            _tick(state, agent, smoke=0.8, fic=0.7)
            assert agent.speed == pytest.approx(V0 * 0.5)
        for _ in range(3):  # FIC back to 0 -> factor 1
            _tick(state, agent, smoke=0.8, fic=irritant_speed_fraction(0.0))
        assert agent.speed == pytest.approx(smoke_only)

    def test_zone_entry_and_exit(self):
        agent, state = _Agent(V0), {}
        smoke, fic, zone = 0.8, 0.7, 0.5
        combined = combined_speed_factor(smoke, fic)
        _tick(state, agent, smoke=smoke, fic=fic)
        assert agent.speed == pytest.approx(V0 * combined)
        _tick(state, agent, smoke=smoke, fic=fic, where=IN, zone_factor=zone)
        assert agent.speed == pytest.approx(V0 * zone * combined)
        _tick(state, agent, smoke=smoke, fic=fic, where=IN, zone_factor=zone)
        assert agent.speed == pytest.approx(V0 * zone * combined)
        _tick(state, agent, smoke=smoke, fic=fic)
        assert agent.speed == pytest.approx(V0 * combined)

    def test_restore_agent_speed_uses_the_same_rule(self):
        agent, state = _Agent(V0), {}
        ensure_agent_speed_state(state, 1, agent)
        set_agent_smoke_factor(state, 1, agent, 0.8)
        state[1]["fic_factor"] = 0.7
        restore_agent_speed(state, 1, agent)
        assert agent.speed == pytest.approx(V0 * 0.5)

    def test_incapacitated_agent_stays_at_zero(self):
        """scenario.py pins original_speed to 0 and resets both factors to 1."""
        agent, state = _Agent(V0), {}
        _tick(state, agent, smoke=0.8, fic=0.5)
        agent.model.desired_speed = 0.0
        state[1].update(original_speed=0.0, smoke_factor=1.0, fic_factor=1.0)
        for smoke, fic in [(1.0, 1.0), (0.4, 0.2), (0.05, 0.0)]:
            _tick(state, agent, smoke=smoke, fic=fic)
            assert agent.speed == 0.0
            _tick(state, agent, smoke=smoke, fic=fic, where=IN, zone_factor=0.5)
            assert agent.speed == 0.0

    def test_premovement_agent_stays_stopped(self):
        """A premovement agent has speed 0 and original_speed 0 until it starts."""
        agent, state = _Agent(0.0), {}
        for smoke, fic in [(1.0, 1.0), (0.4, 0.2), (0.05, 0.0)]:
            _tick(state, agent, smoke=smoke, fic=fic)
            assert agent.speed == 0.0
        state[1]["original_speed"] = V0  # premovement over, as scenario.py does
        _tick(state, agent, smoke=0.8, fic=0.7)
        assert agent.speed == pytest.approx(V0 * 0.5)

    def test_waiting_agent_in_a_hold_zone_stays_stopped(self):
        """The waiting state runs update_checkpoint_speed with the stage config."""
        agent, state = _Agent(V0), {}
        stage = {"polygon": ZONE, "speed_factor": 0.0}
        for smoke, fic in [(1.0, 1.0), (0.4, 0.2), (0.05, 0.0)]:
            set_agent_smoke_factor(state, 1, agent, smoke)
            set_agent_fic_factor(state, 1, agent, fic)
            update_checkpoint_speed(state, {}, 1, agent, "wait", stage, *IN)
            assert agent.speed == 0.0
