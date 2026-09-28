"""Pin the per-step speed update before it is optimised (#240).

``update_checkpoint_speed`` runs for every agent at every step, so #240 plans
to precompute the active zones and to return early for agents whose inputs
did not change. These tests fix what the update does today, so such a change
cannot alter an agent's speed unnoticed.

The fake agent records every ``desired_speed`` write. The tests assert the
effective speed and ``active_checkpoint`` after each call, and that a write
happened whenever the speed had to change. They do not count redundant writes:
removing those is the point of #240.
"""

import math

import pytest
from shapely.geometry import Polygon

from pyfds_evac.core.direct_steering_runtime import (
    _find_steering_zone,
    normalize_speed_factor,
    restore_agent_speed,
    set_agent_fic_factor,
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


class UnmappedModelState:
    """A model the runtime has no speed attribute for."""

    def __init__(self, desired_speed: float):
        self.desired_speed = float(desired_speed)


class RecordingAgent:
    def __init__(self, desired_speed: float, model_cls=CollisionFreeSpeedModelState):
        self.model = model_cls(desired_speed)

    @property
    def speed(self) -> float:
        return self.model.desired_speed

    @property
    def writes(self) -> list[float]:
        return self.model.writes


def _square(x0: float, x1: float, y0: float = 0.0, y1: float = 2.0) -> Polygon:
    return Polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])


ZONE = _square(0.0, 2.0)
INSIDE = (1.0, 1.0)
OUTSIDE = (10.0, 1.0)


def _zone(factor, polygon=ZONE) -> dict:
    return {"polygon": polygon, "speed_factor": factor}


def _update(state, info, agent, xy, checkpoint_key=None, stage_cfg=None, agent_id=1):
    update_checkpoint_speed(
        state, info, agent_id, agent, checkpoint_key, stage_cfg, xy[0], xy[1]
    )


def _assert_speed(agent, state, expected, active, agent_id=1):
    """Effective speed and active zone after a call; a change must be written."""
    assert agent.speed == pytest.approx(expected, rel=1e-12, abs=1e-15)
    assert state[agent_id]["active_checkpoint"] == active


# --- normalize_speed_factor -------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0.5, 0.5),
        ("0.5", 0.5),
        (1, 1.0),
        (0.0, 0.0),
        (3.0, 3.0),
        (5.0, 3.0),
        (-0.1, 1.0),
        (None, 1.0),
        ("abc", 1.0),
        (float("nan"), 1.0),
        (float("inf"), 1.0),
        (float("-inf"), 1.0),
        ([0.5], 1.0),
    ],
)
def test_normalize_speed_factor(value, expected):
    assert normalize_speed_factor(value) == expected


# --- entering and leaving a zone --------------------------------------------


class TestEnterAndLeave:
    def test_steering_zone_slows_then_restores(self):
        agent = RecordingAgent(2.0)
        state = {}
        info = {"slow": _zone(0.5)}

        _update(state, info, agent, OUTSIDE)
        _assert_speed(agent, state, 2.0, None)
        assert agent.writes == []

        _update(state, info, agent, INSIDE)
        _assert_speed(agent, state, 1.0, "slow")
        assert agent.writes[-1] == 1.0

        _update(state, info, agent, INSIDE)
        _assert_speed(agent, state, 1.0, "slow")

        n = len(agent.writes)
        _update(state, info, agent, OUTSIDE)
        _assert_speed(agent, state, 2.0, None)
        assert len(agent.writes) == n + 1 and agent.writes[-1] == 2.0

    def test_checkpoint_slows_then_restores(self):
        agent = RecordingAgent(2.0)
        state = {}
        cfg = _zone(0.25)

        _update(state, {}, agent, INSIDE, "cp", cfg)
        _assert_speed(agent, state, 0.5, "cp")

        _update(state, {}, agent, OUTSIDE, "cp", cfg)
        _assert_speed(agent, state, 2.0, None)

    def test_fast_zone_speeds_up(self):
        agent = RecordingAgent(1.0)
        state = {}
        _update(state, {"fast": _zone(1.5)}, agent, INSIDE)
        _assert_speed(agent, state, 1.5, "fast")

    def test_factor_above_three_is_clamped(self):
        agent = RecordingAgent(1.0)
        state = {}
        _update(state, {"fast": _zone(5.0)}, agent, INSIDE)
        _assert_speed(agent, state, 3.0, "fast")

    def test_zero_factor_stops_the_agent(self):
        agent = RecordingAgent(1.0)
        state = {}
        _update(state, {"stop": _zone(0.0)}, agent, INSIDE)
        _assert_speed(agent, state, 0.0, "stop")
        _update(state, {"stop": _zone(0.0)}, agent, OUTSIDE)
        _assert_speed(agent, state, 1.0, None)

    def test_boundary_counts_as_inside(self):
        agent = RecordingAgent(2.0)
        state = {}
        _update(state, {"slow": _zone(0.5)}, agent, (2.0, 1.0))
        _assert_speed(agent, state, 1.0, "slow")

    def test_moving_between_two_zones_switches_factor(self):
        agent = RecordingAgent(2.0)
        state = {}
        info = {"a": _zone(0.5), "b": _zone(0.75, _square(5.0, 7.0))}
        _update(state, info, agent, INSIDE)
        _assert_speed(agent, state, 1.0, "a")
        _update(state, info, agent, (6.0, 1.0))
        _assert_speed(agent, state, 1.5, "b")
        _update(state, info, agent, INSIDE)
        _assert_speed(agent, state, 1.0, "a")


# --- overlapping zones and precedence ----------------------------------------


class TestOverlap:
    def test_factor_furthest_from_one_wins(self):
        agent = RecordingAgent(2.0)
        state = {}
        info = {"mild": _zone(0.8), "strong": _zone(0.3), "fast": _zone(1.5)}
        _update(state, info, agent, INSIDE)
        _assert_speed(agent, state, 0.6, "strong")

    def test_fast_zone_can_win_over_slow_one(self):
        agent = RecordingAgent(1.0)
        state = {}
        info = {"slow": _zone(0.8), "fast": _zone(2.0)}
        _update(state, info, agent, INSIDE)
        _assert_speed(agent, state, 2.0, "fast")

    @pytest.mark.parametrize(
        ("order", "winner", "speed"),
        [
            (("half", "one_and_half"), "half", 1.0),
            (("one_and_half", "half"), "one_and_half", 3.0),
        ],
    )
    def test_tie_goes_to_first_zone_in_dict_order(self, order, winner, speed):
        factors = {"half": 0.5, "one_and_half": 1.5}
        info = {key: _zone(factors[key]) for key in order}
        agent = RecordingAgent(2.0)
        state = {}
        _update(state, info, agent, INSIDE)
        _assert_speed(agent, state, speed, winner)

    def test_equal_factors_first_key_wins(self):
        info = {"b": _zone(0.5), "a": _zone(0.5)}
        assert _find_steering_zone(info, *INSIDE) == ("b", 0.5)

    def test_zone_outside_is_ignored_even_if_stronger(self):
        info = {"far": _zone(0.1, _square(5.0, 7.0)), "here": _zone(0.9)}
        assert _find_steering_zone(info, *INSIDE) == ("here", 0.9)

    def test_unit_and_invalid_zones_are_skipped(self):
        info = {
            "unit": _zone(1.0),
            "nan": _zone(float("nan")),
            "text": _zone("abc"),
            "neg": _zone(-2.0),
            "missing": {"polygon": ZONE},
            "no_polygon": {"speed_factor": 0.5},
            "none_polygon": {"polygon": None, "speed_factor": 0.5},
        }
        assert _find_steering_zone(info, *INSIDE) is None
        assert _find_steering_zone(None, *INSIDE) is None
        assert _find_steering_zone({}, *INSIDE) is None

    def test_near_unit_factor_within_tolerance_is_inactive(self):
        assert _find_steering_zone({"z": _zone(1.0 + 1e-10)}, *INSIDE) is None
        assert _find_steering_zone({"z": _zone(1.0 + 1e-6)}, *INSIDE) == (
            "z",
            1.0 + 1e-6,
        )

    def test_checkpoint_wins_over_stronger_steering_zone(self):
        """The steering scan is not reached when the checkpoint is active."""
        agent = RecordingAgent(2.0)
        state = {}
        info = {"strong": _zone(0.1)}
        _update(state, info, agent, INSIDE, "cp", _zone(0.9))
        _assert_speed(agent, state, 1.8, "cp")

    def test_checkpoint_outside_falls_through_to_steering_zone(self):
        agent = RecordingAgent(2.0)
        state = {}
        info = {"slow": _zone(0.5)}
        _update(state, info, agent, INSIDE, "cp", _zone(0.9, _square(5.0, 7.0)))
        _assert_speed(agent, state, 1.0, "slow")

    def test_other_checkpoint_in_info_slows_agent_heading_elsewhere(self):
        """Targeting A while standing in B: B slows through the scan."""
        agent = RecordingAgent(2.0)
        state = {}
        info = {"A": _zone(0.9, _square(5.0, 7.0)), "B": _zone(0.5)}
        _update(state, info, agent, INSIDE, "A", info["A"])
        _assert_speed(agent, state, 1.0, "B")


# --- stage speed factors that are 1, missing, invalid, non-finite -----------


NEUTRAL_STAGE_FACTORS = [1, 1.0, "1", None, "abc", float("nan"), float("inf"), -1.0]


class TestNeutralCheckpoint:
    @pytest.mark.parametrize("factor", NEUTRAL_STAGE_FACTORS)
    def test_neutral_checkpoint_falls_through_to_steering_zone(self, factor):
        agent = RecordingAgent(2.0)
        state = {}
        info = {"slow": _zone(0.5)}
        _update(state, info, agent, INSIDE, "cp", _zone(factor))
        _assert_speed(agent, state, 1.0, "slow")

    def test_missing_checkpoint_factor_falls_through(self):
        agent = RecordingAgent(2.0)
        state = {}
        _update(state, {"slow": _zone(0.5)}, agent, INSIDE, "cp", {"polygon": ZONE})
        _assert_speed(agent, state, 1.0, "slow")

    @pytest.mark.parametrize("factor", NEUTRAL_STAGE_FACTORS)
    def test_neutral_everywhere_never_writes(self, factor):
        agent = RecordingAgent(2.0)
        state = {}
        info = {"z": _zone(factor)}
        for xy in (INSIDE, OUTSIDE, INSIDE):
            _update(state, info, agent, xy, "z", info["z"])
            _update(state, info, agent, xy)
        _assert_speed(agent, state, 2.0, None)
        assert agent.writes == []

    @pytest.mark.parametrize(
        ("key", "cfg"),
        [("", _zone(0.5)), (None, _zone(0.5)), ("cp", {}), ("cp", None)],
    )
    def test_empty_key_or_config_skips_the_checkpoint(self, key, cfg):
        agent = RecordingAgent(2.0)
        state = {}
        _update(state, {}, agent, INSIDE, key, cfg)
        _assert_speed(agent, state, 2.0, None)
        assert agent.writes == []


# --- smoke, FIC and baseline changes ------------------------------------------


class TestFactorChanges:
    def test_smoke_change_takes_effect_on_next_call_outside_zone(self):
        agent = RecordingAgent(2.0)
        state = {}
        _update(state, {}, agent, OUTSIDE)
        set_agent_smoke_factor(state, 1, agent, 0.5)
        _update(state, {}, agent, OUTSIDE)
        _assert_speed(agent, state, 1.0, None)
        set_agent_smoke_factor(state, 1, agent, 0.8)
        _update(state, {}, agent, OUTSIDE)
        _assert_speed(agent, state, 1.6, None)

    def test_smoke_change_takes_effect_on_next_call_inside_zone(self):
        agent = RecordingAgent(2.0)
        state = {}
        info = {"slow": _zone(0.5)}
        _update(state, info, agent, INSIDE)
        _assert_speed(agent, state, 1.0, "slow")
        set_agent_smoke_factor(state, 1, agent, 0.8)
        # set_agent_smoke_factor only caches; the update applies it.
        assert agent.speed == 1.0
        _update(state, info, agent, INSIDE)
        _assert_speed(agent, state, 0.8, "slow")
        set_agent_smoke_factor(state, 1, agent, 1.0)
        _update(state, info, agent, INSIDE)
        _assert_speed(agent, state, 1.0, "slow")

    def test_smoke_clearing_inside_zone_then_leaving_restores_full_speed(self):
        agent = RecordingAgent(2.0)
        state = {}
        info = {"slow": _zone(0.5)}
        set_agent_smoke_factor(state, 1, agent, 0.5)
        _update(state, info, agent, INSIDE)
        _assert_speed(agent, state, 0.5, "slow")
        set_agent_smoke_factor(state, 1, agent, 1.0)
        _update(state, info, agent, OUTSIDE)
        _assert_speed(agent, state, 2.0, None)

    @pytest.mark.xfail(
        strict=True,
        reason="restore_agent_speed skips the write when smoke returns to 1 "
        "outside every zone, so the agent keeps its smoky speed (#246)",
    )
    def test_smoke_clearing_outside_zone_restores_full_speed(self):
        agent = RecordingAgent(2.0)
        state = {}
        set_agent_smoke_factor(state, 1, agent, 0.5)
        _update(state, {}, agent, OUTSIDE)
        set_agent_smoke_factor(state, 1, agent, 1.0)
        _update(state, {}, agent, OUTSIDE)
        assert agent.speed == 2.0

    def test_fic_change_inside_zone_is_reapplied_with_the_zone(self):
        """``set_agent_fic_factor`` drops the zone; the next update restores it.

        Calling it with the same value leaves (original, smoke, fic,
        active_checkpoint) unchanged, yet the speed must still be rewritten.
        """
        agent = RecordingAgent(2.0)
        state = {}
        info = {"slow": _zone(0.5)}
        set_agent_smoke_factor(state, 1, agent, 0.8)
        _update(state, info, agent, INSIDE)
        _assert_speed(agent, state, 0.8, "slow")
        for _ in range(3):
            set_agent_fic_factor(state, 1, agent, 0.6)
            assert agent.speed == pytest.approx(2.0 * 0.8 * 0.6)
            _update(state, info, agent, INSIDE)
            _assert_speed(agent, state, 2.0 * 0.5 * 0.8 * 0.6, "slow")
            assert agent.writes[-1] == pytest.approx(2.0 * 0.5 * 0.8 * 0.6)

    def test_fic_change_takes_effect_on_next_call_outside_zone(self):
        agent = RecordingAgent(2.0)
        state = {}
        set_agent_smoke_factor(state, 1, agent, 0.5)
        _update(state, {}, agent, OUTSIDE)
        set_agent_fic_factor(state, 1, agent, 0.6)
        _update(state, {}, agent, OUTSIDE)
        _assert_speed(agent, state, 0.6, None)
        set_agent_fic_factor(state, 1, agent, 0.9)
        _update(state, {}, agent, OUTSIDE)
        _assert_speed(agent, state, 0.9, None)

    def test_checkpoint_combines_all_factors(self):
        agent = RecordingAgent(2.0)
        state = {}
        set_agent_smoke_factor(state, 1, agent, 0.8)
        set_agent_fic_factor(state, 1, agent, 0.6)
        _update(state, {"z": _zone(0.1)}, agent, INSIDE, "cp", _zone(0.5))
        _assert_speed(agent, state, 2.0 * 0.5 * 0.8 * 0.6, "cp")

    def test_raw_factor_in_state_is_normalised_when_applied(self):
        agent = RecordingAgent(2.0)
        state = {}
        _update(state, {}, agent, OUTSIDE)
        state[1]["smoke_factor"] = float("nan")
        _update(state, {}, agent, OUTSIDE)
        _assert_speed(agent, state, 2.0, None)
        assert agent.writes == [2.0]
        state[1]["fic_factor"] = 7.0
        _update(state, {"slow": _zone(0.5)}, agent, INSIDE)
        _assert_speed(agent, state, 3.0, "slow")

    def test_original_speed_change_with_smoke(self):
        """Premovement activation: new baseline, active zone cleared."""
        agent = RecordingAgent(0.0)
        state = {}
        set_agent_smoke_factor(state, 1, agent, 0.5)
        _update(state, {}, agent, OUTSIDE)
        _assert_speed(agent, state, 0.0, None)

        agent.model.desired_speed = 1.2
        state[1]["original_speed"] = 1.2
        state[1]["active_checkpoint"] = None
        _update(state, {}, agent, OUTSIDE)
        _assert_speed(agent, state, 0.6, None)

    def test_original_speed_change_inside_zone(self):
        agent = RecordingAgent(2.0)
        state = {}
        info = {"slow": _zone(0.5)}
        _update(state, info, agent, INSIDE)
        _assert_speed(agent, state, 1.0, "slow")
        state[1]["original_speed"] = 3.0
        _update(state, info, agent, INSIDE)
        _assert_speed(agent, state, 1.5, "slow")

    def test_original_speed_change_without_any_factor_is_not_written(self):
        """No zone, no smoke, no FIC: the update leaves the speed alone."""
        agent = RecordingAgent(2.0)
        state = {}
        _update(state, {}, agent, OUTSIDE)
        state[1]["original_speed"] = 3.0
        _update(state, {}, agent, OUTSIDE)
        assert agent.speed == 2.0
        assert agent.writes == []

    def test_incapacitation_pins_speed_at_zero_inside_zone(self):
        agent = RecordingAgent(2.0)
        state = {}
        info = {"slow": _zone(0.5)}
        set_agent_smoke_factor(state, 1, agent, 0.5)
        _update(state, info, agent, INSIDE)
        agent.model.desired_speed = 0.0
        state[1].update(
            original_speed=0.0, smoke_factor=1.0, fic_factor=1.0, active_checkpoint=None
        )
        for xy in (INSIDE, OUTSIDE, INSIDE):
            _update(state, info, agent, xy)
            assert agent.speed == 0.0


# --- state lifecycle and robustness -------------------------------------------


class TestState:
    def test_first_call_records_current_speed_as_baseline(self):
        agent = RecordingAgent(1.3)
        state = {}
        _update(state, {}, agent, OUTSIDE, agent_id=7)
        assert list(state) == [7]
        assert state[7]["original_speed"] == 1.3
        assert state[7]["active_checkpoint"] is None
        assert state[7]["smoke_factor"] == 1.0
        assert state[7]["fic_factor"] == 1.0

    def test_state_is_per_agent(self):
        a, b = RecordingAgent(2.0), RecordingAgent(1.0)
        state = {}
        info = {"slow": _zone(0.5)}
        set_agent_smoke_factor(state, 2, b, 0.5)
        _update(state, info, a, INSIDE, agent_id=1)
        _update(state, info, b, OUTSIDE, agent_id=2)
        _assert_speed(a, state, 1.0, "slow", agent_id=1)
        _assert_speed(b, state, 0.5, None, agent_id=2)

    def test_popped_state_is_recreated_from_current_speed(self):
        agent = RecordingAgent(2.0)
        state = {}
        info = {"slow": _zone(0.5)}
        _update(state, info, agent, INSIDE)
        state.pop(1)
        _update(state, info, agent, INSIDE)
        # The slowed speed becomes the new baseline, as today.
        assert state[1]["original_speed"] == 1.0
        _assert_speed(agent, state, 0.5, "slow")

    def test_repeated_identical_calls_keep_speed(self):
        agent = RecordingAgent(2.0)
        state = {}
        info = {"slow": _zone(0.5)}
        set_agent_smoke_factor(state, 1, agent, 0.8)
        for xy in (INSIDE, INSIDE, OUTSIDE, OUTSIDE, INSIDE):
            _update(state, info, agent, xy)
        _assert_speed(agent, state, 0.8, "slow")

    def test_external_write_between_calls_is_overridden_when_a_factor_is_active(self):
        """Every writer must go through the state; this shows why."""
        agent = RecordingAgent(2.0)
        state = {}
        info = {"slow": _zone(0.5)}
        set_agent_smoke_factor(state, 1, agent, 0.5)
        _update(state, info, agent, OUTSIDE)
        agent.model.desired_speed = 9.0
        _update(state, info, agent, OUTSIDE)
        _assert_speed(agent, state, 1.0, None)
        _update(state, info, agent, INSIDE)
        agent.model.desired_speed = 9.0
        _update(state, info, agent, INSIDE)
        _assert_speed(agent, state, 0.5, "slow")

    def test_zone_info_mutated_between_calls_is_seen(self):
        """A cache of active zones must not outlive a change of the dict."""
        agent = RecordingAgent(2.0)
        state = {}
        _update(state, {}, agent, INSIDE)
        _assert_speed(agent, state, 2.0, None)
        _update(state, {"slow": _zone(0.5)}, agent, INSIDE)
        _assert_speed(agent, state, 1.0, "slow")

    def test_unmapped_model_is_left_alone(self):
        agent = RecordingAgent(2.0, model_cls=UnmappedModelState)
        state = {}
        set_agent_smoke_factor(state, 1, agent, 0.5)
        _update(state, {"slow": _zone(0.5)}, agent, INSIDE, "cp", _zone(0.25))
        restore_agent_speed(state, 1, agent)
        assert agent.model.desired_speed == 2.0
        assert state[1]["original_speed"] is None
        assert state[1]["active_checkpoint"] is None


# --- the two scenario.py call sites -----------------------------------------------


class TestDoubleCall:
    """A path agent is updated with no checkpoint, then with its checkpoint."""

    @pytest.mark.parametrize("xy", [INSIDE, (6.0, 1.0), OUTSIDE])
    @pytest.mark.parametrize("smoke", [1.0, 0.5])
    def test_double_call_equals_checkpoint_call_alone(self, xy, smoke):
        info = {"slow": _zone(0.5), "B": _zone(0.8, _square(5.0, 7.0))}
        cfg = _zone(0.25, _square(0.0, 1.5))
        results = []
        for calls in (("none", "cp"), ("cp",)):
            agent = RecordingAgent(2.0)
            state = {}
            set_agent_smoke_factor(state, 1, agent, smoke)
            for step_xy in (OUTSIDE, xy, xy):
                for call in calls:
                    if call == "none":
                        _update(state, info, agent, step_xy)
                    else:
                        _update(state, info, agent, step_xy, "cp", cfg)
                results.append((agent.speed, state[1]["active_checkpoint"]))
        n = len(results) // 2
        assert results[:n] == results[n:]

    def test_done_agent_restores_after_last_checkpoint(self):
        agent = RecordingAgent(2.0)
        state = {}
        info = {"cp": _zone(0.5)}
        _update(state, info, agent, INSIDE, "cp", info["cp"])
        _assert_speed(agent, state, 1.0, "cp")
        _update(state, info, agent, OUTSIDE)
        _update(state, info, agent, OUTSIDE)
        _assert_speed(agent, state, 2.0, None)


def test_many_steps_match_closed_form():
    """A walk through two zones with changing smoke and FIC, step by step."""
    agent = RecordingAgent(1.5)
    state = {}
    info = {
        "exit": _zone(1.0, _square(18.0, 20.0)),
        "a": _zone(0.5, _square(4.0, 8.0)),
        "b": _zone(0.7, _square(6.0, 12.0)),
    }
    for step in range(200):
        x = step * 0.1
        t = step * 0.01
        if step % 10 == 0:
            set_agent_smoke_factor(state, 1, agent, 1.0 if t < 0.5 else 0.9 - 0.1 * t)
            if t >= 1.0:
                set_agent_fic_factor(state, 1, agent, 0.7)
        _update(state, info, agent, (x, 1.0), "exit", info["exit"])
        _update(state, info, agent, (x, 1.0))
        zone = 0.5 if 4.0 <= x <= 8.0 else (0.7 if 6.0 <= x <= 12.0 else 1.0)
        smoke = 1.0 if t < 0.5 else 0.9 - 0.1 * (math.floor(step / 10) / 10)
        fic = 0.7 if t >= 1.0 else 1.0
        assert agent.speed == pytest.approx(1.5 * zone * smoke * fic, rel=1e-12), step
