"""Per-agent routing state built at spawn (``build_agent_path_state``)."""

from shapely.geometry import box

from pyfds_evac.core.agent_seed import steering_seeds
from pyfds_evac.core.simulation_init import build_agent_path_state

# A single journey listing every stage, as the scenario loader emits it.  The
# spurious sequential pairs this creates must not shadow the real transitions.
_ALL_STAGES = [
    "jps-distributions_0",
    "jps-distributions_1",
    "cp_west",
    "cp_east",
]


def _direct_steering_info():
    """Two checkpoints, each reachable from one of two spawn areas."""
    return {
        "cp_west": {"polygon": box(0, 0, 2, 2), "stage_type": "checkpoint"},
        "cp_east": {"polygon": box(20, 0, 22, 2), "stage_type": "checkpoint"},
    }


def _transitions():
    return [
        {"from": "jps-distributions_0", "to": "cp_west", "journey_id": "journey_0"},
        {"from": "jps-distributions_1", "to": "cp_east", "journey_id": "journey_0"},
    ]


def _state_for(spawn_origin, agent_id, position):
    return build_agent_path_state(
        variant_data={"actual_stages": _ALL_STAGES},
        journey_key="journey_0",
        transitions=_transitions(),
        direct_steering_info=_direct_steering_info(),
        waypoint_routing={},
        seed=1,
        agent_id=agent_id,
        initial_position=position,
        spawn_origin=spawn_origin,
        spawn_key=("initial", agent_id),
    )


class TestSpawnOriginIsPerAgent:
    """An agent must be routed from the spawn area it was actually placed in.

    Every bundled scenario before The Station had a single distribution, where
    "the first distribution in the journey" and "this agent's distribution"
    coincide.  With several spawn areas they do not, and routing every agent
    from one of them sends the whole population to whichever exit is nearest
    that single area.
    """

    def test_each_spawn_area_keeps_its_own_origin(self):
        west = _state_for("jps-distributions_0", 1, (1.0, 1.0))
        east = _state_for("jps-distributions_1", 2, (21.0, 1.0))

        assert west["current_origin"] == "jps-distributions_0"
        assert east["current_origin"] == "jps-distributions_1"

    def test_agents_from_different_areas_head_to_different_stages(self):
        west = _state_for("jps-distributions_0", 1, (1.0, 1.0))
        east = _state_for("jps-distributions_1", 2, (21.0, 1.0))

        assert west["current_target_stage"] == "cp_west"
        assert east["current_target_stage"] == "cp_east"

    def test_unknown_spawn_origin_falls_back_to_first_distribution(self):
        """A caller that cannot name the spawn area keeps the old behaviour."""
        state = _state_for("jps-distributions_missing", 3, (1.0, 1.0))

        assert state["current_origin"] == "jps-distributions_0"

    def test_omitted_spawn_origin_falls_back_to_first_distribution(self):
        state = build_agent_path_state(
            variant_data={"actual_stages": _ALL_STAGES},
            journey_key="journey_0",
            transitions=_transitions(),
            direct_steering_info=_direct_steering_info(),
            waypoint_routing={},
            seed=1,
            agent_id=4,
            initial_position=(1.0, 1.0),
        )

        assert state["current_origin"] == "jps-distributions_0"


class TestFlatStageListingWithCrossings:
    """A flat stage listing must not invent edges between unrelated crossings.

    Consecutive entries of a journey's stage listing are only a path when the
    same pair is also a declared transition.  Two crossings listed side by side
    are not, and treating them as one used to shadow the real transition out of
    the first crossing.
    """

    _STAGES = ["jps-distributions_0", "c0", "c1", "e0"]

    def _state(self):
        return build_agent_path_state(
            variant_data={"actual_stages": self._STAGES},
            journey_key="journey_0",
            transitions=[
                {"from": "jps-distributions_0", "to": "c0", "journey_id": "journey_0"},
                {"from": "c0", "to": "e0", "journey_id": "journey_0"},
                {"from": "c1", "to": "e0", "journey_id": "journey_0"},
            ],
            direct_steering_info={
                "c0": {"polygon": box(0, 0, 2, 2), "stage_type": "checkpoint"},
                "c1": {"polygon": box(4, 0, 6, 2), "stage_type": "checkpoint"},
                "e0": {"polygon": box(8, 0, 10, 2), "stage_type": "exit"},
            },
            waypoint_routing={},
            seed=1,
            agent_id=1,
            initial_position=(1.0, 1.0),
            spawn_origin="jps-distributions_0",
        )

    def test_real_transition_out_of_first_crossing_survives(self):
        choices = self._state()["path_choices"]

        assert choices["c0"] == [("e0", 100.0)]

    def test_no_edge_between_the_two_crossings(self):
        choices = self._state()["path_choices"]

        assert "c1" not in [target for target, _ in choices["c0"]]

    def test_spawn_area_keeps_its_declared_transition(self):
        choices = self._state()["path_choices"]

        assert choices["jps-distributions_0"] == [("c0", 100.0)]


class TestSeedingFollowsTheSpawnKey:
    """Draws are seeded from the spawn key; the JuPedSim id is ignored (#353)."""

    def _state(self, agent_id, spawn_key):
        return build_agent_path_state(
            variant_data={"actual_stages": _ALL_STAGES},
            journey_key="journey_0",
            transitions=_transitions(),
            direct_steering_info=_direct_steering_info(),
            waypoint_routing={},
            seed=1,
            agent_id=agent_id,
            initial_position=(1.0, 1.0),
            spawn_origin="jps-distributions_0",
            spawn_key=spawn_key,
        )

    def test_same_key_draws_the_same_whatever_the_id(self):
        assert self._state(1, ("initial", 0)) == self._state(99, ("initial", 0))

    def test_another_key_draws_another_target(self):
        first = self._state(1, ("initial", 0))
        second = self._state(1, ("initial", 1))
        assert first["target"] != second["target"]
        assert first["base_seed"] != second["base_seed"]

    def test_later_draws_get_their_own_streams(self):
        state = self._state(1, ("initial", 0))
        assert steering_seeds(1, ("initial", 0)) == {
            key: state[key] for key in ("base_seed", "wait_seed", "choice_seed")
        }

    def test_without_a_key_the_id_seeds_as_before(self):
        state = self._state(4, None)
        assert state["base_seed"] == 1 + 4 * 9973
        assert "wait_seed" not in state
