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

A small share of runs never finishes: two agents meet head-on in a doorway,
or four jam at CP1, and stand there for the rest of the run (#359). An
exploring agent with nothing left to explore used to patrol, and its patrol
broke such stands up; since it looks from the node point first (#250), the
stand is permanent. The model fix is #359's. Until then the module bounds
the rate of these deadlocks instead of asserting that everyone gets out, and
asserts only aggregate outcomes, never trajectories or exact times.

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

# (agents, seeds, most deadlocked runs allowed); see the rate test.
RATE_CASES = [(5, range(1, 31), 4), (20, range(1, 21), 5)]
# A deadlock leaves at most the four agents of the CP1 jam and the two of the
# CP2 head-on behind; both can occur in one run (seeds 135 and 232 on main,
# #359).
MOST_LEFT_IN_A_DEADLOCK = 6


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


def _run(tmp_path, vis_model, n_agents, seed):
    config = json.loads((DECK / "config.json").read_text())
    cfg = copy.deepcopy(config)
    for dist in cfg["distributions"].values():
        dist["parameters"]["number"] = n_agents
    deck = tmp_path / f"deck_{n_agents}_{seed}"
    deck.mkdir()
    (deck / "config.json").write_text(json.dumps(cfg))
    (deck / "geometry.wkt").write_text((DECK / "geometry.wkt").read_text())
    return run_scenario(
        load_scenario(str(deck)),
        seed=seed,
        reroute_config=RerouteConfig(
            reevaluation_interval_s=1.0, cost_config=RouteCostConfig()
        ),
        vis_model=vis_model,
    )


@pytest.mark.slow
@pytest.mark.parametrize(
    ("n_agents", "seeds", "most_deadlocks"),
    RATE_CASES,
    ids=[f"{n}_agents" for n, _, _ in RATE_CASES],
)
def test_discovery_agents_find_the_exit_but_for_deadlocks(
    tmp_path, vis_model, n_agents, seeds, most_deadlocks
):
    """Every run ends complete or in a #359 deadlock, and deadlocks are rare.

    Measured at c619a046 (0.5.0) with these settings: 5 agents deadlock in
    3 of seeds 1-150 (2.0 %), 20 agents in 7 of seeds 1-60 (11.7 %); at #250,
    5 of 150 and 5 of 60; before #250, 3 of 150 and 0 of 60. Each bound is
    the smallest k with P(X > k) <= 1 % at the #250 rate, binomial over the
    seeds run here: 4 of 30 and 5 of 20. At the c619a046 rate of 20 agents
    that k would be 6.
    """
    config = json.loads((DECK / "config.json").read_text())
    max_time_s = config["config"]["simulation_settings"]["simulationParams"][
        "max_simulation_time"
    ]
    deadlocked = []
    for seed in seeds:
        result = _run(tmp_path, vis_model, n_agents, seed)
        try:
            assert result.total_agents == n_agents, seed
            left = n_agents - result.agents_evacuated
            assert left <= MOST_LEFT_IN_A_DEADLOCK, (seed, left)
            if left:
                deadlocked.append(seed)
            else:
                assert 0.0 < result.evacuation_time < max_time_s, seed
        finally:
            result.cleanup()
    assert len(deadlocked) <= most_deadlocks, deadlocked
