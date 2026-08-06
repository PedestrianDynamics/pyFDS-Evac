"""An agent's routing origin is its spawn area, not the exit it was assigned.

Regression for issue #61. In no-journey mode -- no explicit journey, no
transitions, agents auto-assigned to their nearest exit -- the by-number spawn
path wrote the *assigned exit* into ``current_origin``. Rerouting ranks every
exit reachable from that node, and an exit is terminal, so the ranking
collapsed to the assigned exit at zero cost. Smoke, FED, congestion and the
cognitive map were all evaluated from a node the agent was not standing at and
could not leave, which meant they were never evaluated at all.

The same path also dropped ``familiarity`` and ``entrance``: the distribution
parameters were copied through an explicit whitelist that did not include them,
so every agent was seeded as fully familiar whatever the scenario asked for.
Sign legibility can only bind on an incomplete map, so this silently disabled
the visibility model too -- and it did so *behind* the origin bug, which is why
fixing the origin alone changed nothing observable.

The flow-spawning path in ``scenario.py`` has always used the spawn key and
carried both fields. These tests pin the by-number path to the same contract.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import jupedsim as jps
import pytest
from shapely.geometry import Polygon

from pyfds_evac.core.route_graph import RouteCostConfig, StageGraph, rank_routes
from pyfds_evac.core.simulation_init import initialize_simulation_from_json

ASSET = Path("assets/exit_visibility_alpha")
CONFIG = ASSET / "config_hidden.json"

SPAWN_KEY = "jps-distributions_0"
NEAR_EXIT = "E_near"
FAR_EXIT = "E_far"


class NoSmoke:
    def sample_extinction(self, time_s, x, y):
        del time_s, x, y
        return 0.0


@pytest.fixture(scope="module")
def raw() -> dict:
    return json.loads(CONFIG.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def wait_info(tmp_path_factory, raw) -> dict[int, dict]:
    """Run the real no-journey initialisation and return its per-agent state."""
    walkable = Polygon(
        [(0.0, 0.0), (4.0, 0.0), (4.0, 30.0), (0.0, 30.0)]
    )  # matches assets/exit_visibility_alpha/geometry.wkt
    out = tmp_path_factory.mktemp("no_journey") / "traj.sqlite"
    simulation = jps.Simulation(
        model=jps.CollisionFreeSpeedModel(),
        geometry=walkable,
        trajectory_writer=jps.SqliteTrajectoryWriter(output_file=out),
    )
    config = tmp_path_factory.mktemp("no_journey_cfg") / "config.json"
    config.write_text(json.dumps(raw), encoding="utf-8")

    _, _, _, spawning_info = initialize_simulation_from_json(
        str(config),
        simulation,
        SimpleNamespace(polygon=walkable),
        seed=1301,
        model_type="CollisionFreeSpeedModel",
        global_parameters=SimpleNamespace(),
    )
    info = spawning_info["agent_wait_info"]
    assert info, "the fixture proves nothing if no agents were placed"
    return info


class TestThePremise:
    """This asset must still be in the mode the bug lived in."""

    def test_the_scenario_declares_no_journey_and_no_transitions(self, raw):
        assert not raw.get("journeys")
        assert not raw.get("transitions")
        assert not raw.get("journeys_v2")

    def test_agents_are_placed_by_number_not_by_flow(self, raw):
        params = raw["distributions"][SPAWN_KEY]["parameters"]
        assert params["distribution_mode"] == "by_number"
        assert params["use_flow_spawning"] is False


class TestRoutingOrigin:
    def test_every_agent_is_rooted_at_its_spawn_area(self, wait_info):
        origins = {w["current_origin"] for w in wait_info.values()}
        assert origins == {SPAWN_KEY}

    def test_the_assigned_exit_is_the_target_not_the_origin(self, wait_info):
        """Origin and target are different roles; the bug conflated them."""
        for w in wait_info.values():
            assert w["current_target_stage"] in {NEAR_EXIT, FAR_EXIT}
            assert w["current_origin"] != w["current_target_stage"]


class TestKnowledgeCarriedFromTheDistribution:
    def test_familiarity_reaches_the_agent(self, wait_info, raw):
        declared = raw["distributions"][SPAWN_KEY]["parameters"]["familiarity"]
        assert declared == "discovery", "asset changed; this test is now vacuous"
        assert {w.get("familiarity") for w in wait_info.values()} == {declared}

    def test_entrance_is_present_even_when_unset(self, wait_info):
        """Absent must mean None, not a missing key the reroute pass re-defaults."""
        for w in wait_info.values():
            assert "entrance" in w
            assert w["entrance"] is None


class TestWhyTheOriginMattered:
    """The consequence, not just the field: ranking from an exit sees one exit.

    Without this the origin assertions above are bookkeeping. This is the
    behaviour the bug actually destroyed.
    """

    @staticmethod
    def _graph(raw) -> StageGraph:
        stages = {
            key: {"polygon": Polygon(value["coordinates"]), "stage_type": "exit"}
            for key, value in raw["exits"].items()
        }
        distributions = {
            key: {"coordinates": value["coordinates"]}
            for key, value in raw["distributions"].items()
        }
        return StageGraph.from_scenario(stages, [], distributions=distributions)

    @staticmethod
    def _ranked_exits(graph, source) -> list[str]:
        return [
            rc.exit_id
            for rc in rank_routes(
                graph,
                source,
                0.0,
                0.0,
                NoSmoke(),
                None,
                RouteCostConfig(base_speed_m_per_s=1.3),
            )
        ]

    def test_from_the_spawn_area_both_exits_are_candidates(self, raw):
        graph = self._graph(raw)
        assert set(self._ranked_exits(graph, SPAWN_KEY)) == {NEAR_EXIT, FAR_EXIT}

    def test_from_an_exit_only_that_exit_is_a_candidate(self, raw):
        """The old behaviour, pinned so it cannot quietly return."""
        graph = self._graph(raw)
        assert self._ranked_exits(graph, NEAR_EXIT) == [NEAR_EXIT]
