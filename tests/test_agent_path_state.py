"""Per-agent routing state built at spawn (``build_agent_path_state``)."""

from shapely.geometry import box

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
