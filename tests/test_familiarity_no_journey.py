"""Behavioral tests for ``assets/familiarity_test_no_journey``.

The deck is the familiarity_test_discovery maze with the manual journey
removed: no journeys, no transitions, ``discovery`` familiarity, authored
direction-facing signs on every checkpoint. Nothing tells an agent where the
exit is -- evacuation works only if frontier exploration, sign perception and
the reroute pass cooperate. That chain is what these tests pin down, across
agent counts and seeds, because the failure mode it guards against was
population-dependent: stale ``path_choices`` legs trapped exactly the agents
that learned the exit mid-leg (fixed alongside this file; see
``TestRerouteAgent.test_reroute_clears_stale_choices_at_new_terminal``).

Coupled JuPedSim runs are not bit-reproducible under a fixed seed, so only
aggregate invariants are asserted (everyone gets out, within the deck's time
budget), never trajectories or exact times.

``VisibilityModel.clear_air`` needs cells thinner than the thinnest wall that
must block sight; this maze's walls are 0.1 m, hence 0.05 m cells (see the
``clear_air`` docstring). The model depends only on geometry and signs, not on
the agent count or seed, so it is built once per module.
"""

import copy
import json
from pathlib import Path

import pytest
from shapely import wkt as shapely_wkt

from pyfds_evac.core import load_scenario
from pyfds_evac.core.route_graph import RerouteConfig, RouteCostConfig
from pyfds_evac.core.scenario import run_scenario
from pyfds_evac.core.visibility import VisibilityModel, extract_sign_descriptors

DECK = Path(__file__).resolve().parents[1] / "assets" / "familiarity_test_no_journey"
CELL_SIZE_M = 0.05

AGENT_COUNTS = [5, 20, 30]
SEEDS = [420, 7, 1234]


def test_deck_declares_what_the_module_assumes():
    """The asset must stay journey-free and discovery-tier, or every run
    below silently degenerates into scripted routing and proves nothing."""
    config = json.loads((DECK / "config.json").read_text())
    assert config["journeys"] == []
    assert config["transitions"] == []
    for dist in config["distributions"].values():
        assert dist["parameters"]["familiarity"] == "discovery"
    for checkpoint in config["checkpoints"].values():
        assert checkpoint.get("sign"), "every checkpoint carries an authored sign"


@pytest.fixture(scope="module")
def vis_model():
    scenario = load_scenario(str(DECK))
    walkable = shapely_wkt.loads((DECK / "geometry.wkt").read_text().strip())
    return VisibilityModel.clear_air(
        walkable, extract_sign_descriptors(scenario.raw), cell_size_m=CELL_SIZE_M
    )


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("n_agents", AGENT_COUNTS)
def test_every_discovery_agent_finds_the_exit(tmp_path, vis_model, n_agents, seed):
    config = json.loads((DECK / "config.json").read_text())
    max_time_s = config["config"]["simulation_settings"]["simulationParams"][
        "max_simulation_time"
    ]
    cfg = copy.deepcopy(config)
    for dist in cfg["distributions"].values():
        dist["parameters"]["number"] = n_agents
    deck = tmp_path / "deck"
    deck.mkdir()
    (deck / "config.json").write_text(json.dumps(cfg))
    (deck / "geometry.wkt").write_text((DECK / "geometry.wkt").read_text())

    result = run_scenario(
        load_scenario(str(deck)),
        seed=seed,
        reroute_config=RerouteConfig(
            reevaluation_interval_s=1.0, cost_config=RouteCostConfig()
        ),
        vis_model=vis_model,
    )
    try:
        assert result.total_agents == n_agents
        assert result.agents_evacuated == n_agents
        assert 0.0 < result.evacuation_time < max_time_s
    finally:
        result.cleanup()
