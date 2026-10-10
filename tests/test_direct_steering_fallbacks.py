"""Inputs and outputs of the direct-steering helpers, fallbacks included.

``run_scenario`` steers every agent through these helpers at every step. The
happy paths run in every scenario test; the fallbacks (agents without a model
state, unknown model states, missing geometry, stages without a successor)
only run when something is off, and a silent change there moves agents
somewhere else without failing any golden run.

The tests check only what each public function returns or writes to the agent
and its state dict, so the exit test can be reimplemented (#429) without
touching them. ``_weighted_choice`` is reached through ``advance_path_target``.
"""

from __future__ import annotations

import gc
import math
import random

import jupedsim as jps
import pytest
from shapely.geometry import Point, Polygon, box

from pyfds_evac.core import direct_steering_runtime
from pyfds_evac.core.direct_steering_runtime import (
    EXIT_REACH_TOLERANCE_M,
    TARGET_REACH_MARGIN_M,
    advance_path_target,
    assign_agent_target,
    distance_to_polygon,
    extract_agent_xy,
    get_agent_desired_speed,
    is_inside_polygon,
    pick_stage_target,
    reached_stage,
    sample_wait_time,
    set_agent_desired_speed,
    set_agent_fic_factor,
    set_agent_smoke_factor,
)

UNIT = box(0.0, 0.0, 1.0, 1.0)


def _real_agent():
    """Return a CollisionFreeSpeedModel agent at (1, 2) with v0 = 1.2 m/s."""
    simulation = jps.Simulation(
        model=jps.CollisionFreeSpeedModel(), geometry=box(0.0, 0.0, 10.0, 10.0)
    )
    stage = simulation.add_direct_steering_stage()
    journey = simulation.add_journey(jps.JourneyDescription([stage]))
    agent_id = simulation.add_agent(
        jps.CollisionFreeSpeedModelAgentParameters(
            journey_id=journey,
            stage_id=stage,
            position=(1.0, 2.0),
            desired_speed=1.2,
        )
    )
    return simulation, simulation.agent(agent_id)


class _Obj:
    """Plain attribute bag for duck-typed agents and positions."""

    def __init__(self, **attrs):
        self.__dict__.update(attrs)


# Model-state stand-ins: the runtime keys its speed attribute on the class name.
class CollisionFreeSpeedModelState:
    def __init__(self, desired_speed):
        self.desired_speed = desired_speed


class UnknownModelState:
    def __init__(self):
        self.desired_speed = 1.0


class CollisionFreeSpeedModelV2State:
    """A mapped state whose attribute is read-only and unreadable as a float."""

    @property
    def desired_speed(self):
        return "not a speed"


# -- position and target ---------------------------------------------------


class TestExtractAgentXY:
    def test_real_agent_position(self):
        _, agent = _real_agent()
        assert extract_agent_xy(agent) == (1.0, 2.0)

    def test_list_position(self):
        assert extract_agent_xy(_Obj(position=[3, 4, 5])) == (3.0, 4.0)

    def test_position_with_x_y_attributes(self):
        assert extract_agent_xy(_Obj(position=_Obj(x=5, y=6))) == (5.0, 6.0)

    def test_agent_with_x_y_attributes(self):
        assert extract_agent_xy(_Obj(x=7, y=8)) == (7.0, 8.0)

    def test_short_position_falls_back_to_agent_x_y(self):
        assert extract_agent_xy(_Obj(position=(1.0,), x=2, y=3)) == (2.0, 3.0)

    @pytest.mark.parametrize(
        "agent", [_Obj(), _Obj(position=None), _Obj(position=(1.0,))]
    )
    def test_no_position_returns_none_pair(self, agent):
        assert extract_agent_xy(agent) == (None, None)


class TestAssignAgentTarget:
    def test_real_agent_gets_float_tuple(self):
        _, agent = _real_agent()
        assign_agent_target(agent, (3, 4))
        assert agent.target == (3.0, 4.0)

    @pytest.mark.parametrize("target", [None, ()])
    def test_empty_target_leaves_agent_alone(self, target):
        agent = _Obj(target=(9.0, 9.0))
        assign_agent_target(agent, target)
        assert agent.target == (9.0, 9.0)

    def test_tuple_rejected_falls_back_to_list(self):
        class ListOnly:
            def __setattr__(self, name, value):
                if not isinstance(value, list):
                    raise TypeError("list required")
                super().__setattr__(name, value)

        agent = ListOnly()
        assign_agent_target(agent, (1, 2))
        assert agent.target == [1.0, 2.0]

    def test_read_only_target_is_logged_not_raised(self, caplog):
        class ReadOnly:
            __slots__ = ()

        with caplog.at_level("WARNING"):
            assign_agent_target(ReadOnly(), (1.0, 2.0))
        assert "Failed to assign target" in caplog.text


# -- geometry --------------------------------------------------------------


class TestIsInsidePolygon:
    @pytest.mark.parametrize(
        ("x", "y", "inside"),
        [(0.5, 0.5, True), (1.0, 0.5, True), (0.0, 0.0, True), (1.01, 0.5, False)],
    )
    def test_interior_and_boundary_count(self, x, y, inside):
        assert is_inside_polygon(x, y, UNIT) is inside

    def test_no_polygon(self):
        assert is_inside_polygon(0.5, 0.5, None) is False

    def test_bad_coordinates_are_outside(self):
        assert is_inside_polygon("a", 0.5, UNIT) is False

    def test_cached_bounds_go_with_the_polygon(self):
        """The bounds are cached by id; a freed polygon's entry must go,
        or a later polygon at the same address inherits its bounds."""
        polygon = box(0.0, 0.0, 1.0, 1.0)
        assert is_inside_polygon(0.5, 0.5, polygon)
        key = id(polygon)
        assert key in direct_steering_runtime._POLYGON_BOUNDS
        del polygon
        gc.collect()
        assert key not in direct_steering_runtime._POLYGON_BOUNDS

    def test_a_polygon_at_a_reused_address_is_tested_by_its_own_bounds(self):
        """Polygons made and freed in turn reuse addresses; each is tested
        against its own bounds, not those of a freed one."""
        seen = set()
        reused = 0
        for i in range(200):
            polygon = box(10.0 * i, 0.0, 10.0 * i + 1.0, 1.0)
            reused += id(polygon) in seen
            seen.add(id(polygon))
            assert is_inside_polygon(10.0 * i + 0.5, 0.5, polygon), i
            del polygon
        if not reused:
            pytest.skip("no address was reused")


class TestDistanceToPolygon:
    @pytest.mark.parametrize(
        ("x", "y", "expected"),
        [(0.5, 0.5, 0.0), (1.0, 0.5, 0.0), (3.0, 0.5, 2.0), (4.0, 5.0, 5.0)],
    )
    def test_zero_inside_and_on_edge_euclidean_outside(self, x, y, expected):
        assert distance_to_polygon(x, y, UNIT) == pytest.approx(expected)

    @pytest.mark.parametrize(("x", "polygon"), [("a", UNIT), (0.5, None)])
    def test_failure_is_infinitely_far(self, x, polygon):
        assert distance_to_polygon(x, 0.5, polygon) == math.inf


class TestReachedStage:
    EXIT = {"stage_type": "exit", "polygon": UNIT}

    def test_exit_reached_inside_polygon_whatever_the_target(self):
        assert reached_stage(0.5, 0.5, (50.0, 50.0), self.EXIT, 0.2)

    def test_exit_reached_within_tolerance(self):
        x = 1.0 + 0.5 * EXIT_REACH_TOLERANCE_M
        assert reached_stage(x, 0.5, None, self.EXIT, 0.2)

    def test_exit_not_reached_within_agent_radius(self):
        """The radius does not widen an exit: the door bounds the flow."""
        x = 1.0 + 2.0 * EXIT_REACH_TOLERANCE_M
        assert not reached_stage(x, 0.5, (x, 0.5), self.EXIT, 0.5)

    @pytest.mark.parametrize("stage_cfg", [{"stage_type": "exit"}, {}, None])
    def test_without_exit_polygon_uses_target_radius(self, stage_cfg):
        radius = 0.2
        reach = radius + TARGET_REACH_MARGIN_M
        assert reached_stage(reach - 0.01, 0.0, (0.0, 0.0), stage_cfg, radius)
        assert not reached_stage(reach + 0.01, 0.0, (0.0, 0.0), stage_cfg, radius)

    def test_checkpoint_reached_inside_polygon_whatever_the_target(self):
        """A checkpoint is reached inside its polygon (#69)."""
        cfg = {"stage_type": "checkpoint", "polygon": UNIT}
        assert reached_stage(0.5, 0.5, (5.0, 5.0), cfg, 0.2)

    def test_deep_inside_a_large_checkpoint_is_reached(self):
        """Contract case 1 (#69): inside [0,2]^2, 1.98 m from the target."""
        cfg = {"stage_type": "checkpoint", "polygon": box(0.0, 0.0, 2.0, 2.0)}
        assert reached_stage(1.7, 1.7, (0.3, 0.3), cfg, 0.2)

    def test_outside_and_far_from_the_target_is_not_reached(self):
        """Contract case 2 (#69): outside [0,2]^2, 2.0 m from the target."""
        cfg = {"stage_type": "checkpoint", "polygon": box(0.0, 0.0, 2.0, 2.0)}
        assert not reached_stage(2.3, 0.3, (0.3, 0.3), cfg, 0.2)

    def test_outside_a_small_circle_near_the_target_is_reached(self):
        """Contract case 3 (#69): the point test still applies outside."""
        cfg = {"stage_type": "checkpoint", "polygon": Point(0.0, 0.0).buffer(0.245)}
        assert reached_stage(0.6, 0.0, (0.0, 0.0), cfg, 0.2)

    def test_untyped_stage_is_a_checkpoint(self):
        assert reached_stage(0.5, 0.5, (5.0, 5.0), {"polygon": UNIT}, 0.2)

    @pytest.mark.parametrize("stage_type", ["distribution", "zone"])
    def test_patrol_and_zone_stages_keep_the_point_test(self, stage_type):
        """Only checkpoints are reached by containment; a spawn area walked
        to on patrol is reached at its target point, not on entry."""
        cfg = {"stage_type": stage_type, "polygon": box(0.0, 0.0, 2.0, 2.0)}
        assert not reached_stage(1.7, 1.7, (0.3, 0.3), cfg, 0.2)

    def test_no_target_never_reached(self):
        assert not reached_stage(0.0, 0.0, None, {"stage_type": "checkpoint"}, 0.2)

    def test_no_target_inside_checkpoint_polygon_is_reached(self):
        cfg = {"stage_type": "checkpoint", "polygon": UNIT}
        assert reached_stage(0.5, 0.5, None, cfg, 0.2)


class TestPickStageTarget:
    STATE = {"base_seed": 7, "step_index": 2, "agent_radius": 0.25}

    @pytest.mark.parametrize("cfg", [None, {}, {"polygon": None}])
    def test_no_polygon_no_target(self, cfg):
        assert pick_stage_target(self.STATE, cfg) is None

    def test_target_keeps_clearance_from_the_walls(self):
        polygon = box(0.0, 0.0, 4.0, 3.0)
        target = pick_stage_target(self.STATE, {"polygon": polygon})
        clearance = 0.8 * self.STATE["agent_radius"]
        assert polygon.buffer(-clearance).covers(Point(*target))

    def test_same_seed_and_step_same_target(self):
        cfg = {"polygon": box(0.0, 0.0, 4.0, 3.0)}
        assert pick_stage_target(dict(self.STATE), cfg) == pick_stage_target(
            dict(self.STATE), cfg
        )

    def test_next_step_draws_a_new_target(self):
        cfg = {"polygon": box(0.0, 0.0, 4.0, 3.0)}
        later = dict(self.STATE, step_index=3)
        assert pick_stage_target(self.STATE, cfg) != pick_stage_target(later, cfg)

    def test_defaults_without_seed_radius_or_step(self):
        polygon = box(0.0, 0.0, 4.0, 3.0)
        target = pick_stage_target({}, {"polygon": polygon})
        assert polygon.buffer(-0.16).covers(Point(*target))

    def test_polygon_thinner_than_clearance_still_yields_a_point_inside(self):
        polygon = box(0.0, 0.0, 0.2, 3.0)
        target = pick_stage_target({"agent_radius": 0.5}, {"polygon": polygon})
        assert polygon.covers(Point(*target))


# -- waiting ---------------------------------------------------------------


class TestSampleWaitTime:
    def test_fixed_wait(self):
        assert sample_wait_time({"waiting_time": 4.5}, 0, 0) == 4.5

    def test_missing_wait_is_zero(self):
        assert sample_wait_time({}, 0, 0) == 0.0

    def test_negative_fixed_wait_clamps_to_zero(self):
        assert sample_wait_time({"waiting_time": -2.0}, 0, 0) == 0.0

    def test_gaussian_wait_is_seeded_by_seed_and_step(self):
        cfg = {
            "waiting_time": 5.0,
            "waiting_time_distribution": "gaussian",
            "waiting_time_std": 2.0,
        }
        expected = random.Random(3 + 4 * 131 + 17).gauss(5.0, 2.0)
        assert sample_wait_time(cfg, 3, 4) == pytest.approx(expected)
        assert sample_wait_time(cfg, 3, 4) == sample_wait_time(cfg, 3, 4)

    def test_gaussian_wait_never_below_a_tenth_of_a_second(self):
        cfg = {
            "waiting_time": -100.0,
            "waiting_time_distribution": "gaussian",
            "waiting_time_std": 0.01,
        }
        assert sample_wait_time(cfg, 0, 0) == 0.1

    def test_gaussian_default_std_is_one_second(self):
        cfg = {"waiting_time": 10.0, "waiting_time_distribution": "gaussian"}
        expected = random.Random(17).gauss(10.0, 1.0)
        assert sample_wait_time(cfg, 0, 0) == pytest.approx(expected)


# -- desired speed ---------------------------------------------------------


class TestDesiredSpeedFallbacks:
    @pytest.mark.parametrize(
        "agent",
        [
            _Obj(),
            _Obj(model=None),
            _Obj(model=UnknownModelState()),
            _Obj(model=_Obj()),
        ],
        ids=["no-model", "model-none", "unmapped-state", "plain-object"],
    )
    def test_unknown_model_reads_none_and_refuses_writes(self, agent):
        assert get_agent_desired_speed(agent) is None
        assert set_agent_desired_speed(agent, 0.5) is False

    def test_unmapped_state_keeps_its_speed(self):
        agent = _Obj(model=UnknownModelState())
        set_agent_desired_speed(agent, 0.5)
        assert agent.model.desired_speed == 1.0

    def test_mapped_state_without_the_attribute(self):
        state = CollisionFreeSpeedModelState(1.0)
        del state.desired_speed
        agent = _Obj(model=state)
        assert get_agent_desired_speed(agent) is None
        assert set_agent_desired_speed(agent, 0.5) is False

    def test_unreadable_and_read_only_attribute(self):
        agent = _Obj(model=CollisionFreeSpeedModelV2State())
        assert get_agent_desired_speed(agent) is None
        assert set_agent_desired_speed(agent, 0.5) is False

    def test_write_is_a_float(self):
        agent = _Obj(model=CollisionFreeSpeedModelState(1.0))
        assert set_agent_desired_speed(agent, 1) is True
        assert type(agent.model.desired_speed) is float


class TestFicFactorFallbacks:
    def test_agent_without_speed_caches_factor_and_writes_nothing(self):
        agent = _Obj(model=UnknownModelState())
        state = {}
        set_agent_fic_factor(state, 1, agent, 0.5)
        assert state[1]["fic_factor"] == 0.5
        assert state[1]["original_speed"] is None
        assert agent.model.desired_speed == 1.0

    def test_fic_combines_with_cached_smoke_factor(self):
        agent = _Obj(model=CollisionFreeSpeedModelState(2.0))
        state = {}
        set_agent_smoke_factor(state, 1, agent, 0.5)
        set_agent_fic_factor(state, 1, agent, 0.5)
        assert agent.model.desired_speed == pytest.approx(0.5)

    @pytest.mark.parametrize(
        ("factor", "cached", "speed"),
        [
            (float("nan"), 1.0, 2.0),
            (-1.0, 1.0, 2.0),
            ("bad", 1.0, 2.0),
            (10.0, 3.0, 6.0),
            (0.0, 0.0, 0.0),
        ],
    )
    def test_factor_is_normalised(self, factor, cached, speed):
        """Invalid factors mean no change; factors above 3 are capped."""
        agent = _Obj(model=CollisionFreeSpeedModelState(2.0))
        state = {}
        set_agent_fic_factor(state, 1, agent, factor)
        assert state[1]["fic_factor"] == cached
        assert agent.model.desired_speed == pytest.approx(speed)


# -- next stage ------------------------------------------------------------


def _wait_info(choices, configs, **extra):
    info = {
        "path_choices": choices,
        "stage_configs": configs,
        "current_target_stage": "A",
        "base_seed": 11,
        "step_index": 0,
        "state": "waiting",
        "target_assigned": True,
        "wait_until": 9.0,
    }
    info.update(extra)
    return info


STAGE_B = {"polygon": box(10.0, 0.0, 12.0, 2.0)}
STAGE_C = {"polygon": box(20.0, 0.0, 22.0, 2.0)}


class TestAdvancePathTarget:
    def test_no_successor_goes_idle_at_the_stage(self):
        info = _wait_info({}, {"A": {}})
        advance_path_target(info)
        assert info["state"] == "idle"
        assert info["current_origin"] == "A"
        assert info["current_target_stage"] == "A"

    def test_unknown_successor_ends_the_path(self):
        info = _wait_info({"A": [("Z", 1.0)]}, {"A": {}})
        advance_path_target(info)
        assert info["state"] == "done"
        assert info["current_target_stage"] == "A"

    def test_moves_to_the_successor_and_resets_the_stage_state(self):
        info = _wait_info({"A": [("B", 1.0)]}, {"A": {}, "B": STAGE_B})
        advance_path_target(info)
        assert info["state"] == "to_target"
        assert info["current_origin"] == "A"
        assert info["current_target_stage"] == "B"
        assert info["step_index"] == 1
        assert info["target_assigned"] is False
        assert info["wait_until"] is None
        assert STAGE_B["polygon"].covers(Point(*info["target"]))

    def test_zero_weight_successor_is_never_chosen(self):
        for seed in range(200):
            info = _wait_info(
                {"A": [("B", 0.0), ("C", 1.0)]},
                {"A": {}, "B": STAGE_B, "C": STAGE_C},
                base_seed=seed,
            )
            advance_path_target(info)
            assert info["current_target_stage"] == "C"

    @pytest.mark.parametrize("weights", [(0.0, 0.0), (-1.0, -2.0)])
    def test_no_positive_weight_takes_the_first_candidate(self, weights):
        info = _wait_info(
            {"A": [("B", weights[0]), ("C", weights[1])]},
            {"A": {}, "B": STAGE_B, "C": STAGE_C},
        )
        advance_path_target(info)
        assert info["current_target_stage"] == "B"

    def test_weights_split_agents_in_proportion(self):
        picks = []
        for seed in range(2000):
            info = _wait_info(
                {"A": [("B", 1.0), ("C", 3.0)]},
                {"A": {}, "B": STAGE_B, "C": STAGE_C},
                choice_seed=seed,
            )
            advance_path_target(info)
            picks.append(info["current_target_stage"])
        assert picks.count("C") / len(picks) == pytest.approx(0.75, abs=0.03)

    def test_choice_seed_overrides_base_seed(self):
        def pick(**seeds):
            info = _wait_info(
                {"A": [("B", 1.0), ("C", 1.0)]},
                {"A": {}, "B": STAGE_B, "C": STAGE_C},
                **seeds,
            )
            advance_path_target(info)
            return info["current_target_stage"]

        choices = {pick(base_seed=0, choice_seed=s) for s in range(20)}
        assert choices == {"B", "C"}
        assert {pick(base_seed=b, choice_seed=5) for b in range(20)} == {
            pick(base_seed=0, choice_seed=5)
        }


def test_polygon_with_hole_counts_the_hole_as_outside():
    shell = [(0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (0.0, 4.0)]
    hole = [(1.0, 1.0), (3.0, 1.0), (3.0, 3.0), (1.0, 3.0)]
    ring = Polygon(shell, [hole])
    assert not is_inside_polygon(2.0, 2.0, ring)
    assert distance_to_polygon(2.0, 2.0, ring) == pytest.approx(1.0)
