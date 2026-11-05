"""Every registered seed of the Station study places every agent (#380).

The study registers seeds 4-23. Before the rear bar / dart room area was
widened, seeds 18, 20 and 22 stopped in placement with "Only 26 (27) of 28
could be placed": that area's 28 agents had 13.2 m2.
"""

from __future__ import annotations

import contextlib
import io
import json

import jupedsim as jps
import pedpy
import pytest

from pyfds_evac.core.scenario import _build_model, load_scenario
from pyfds_evac.core.simulation_init import initialize_simulation_from_json

ASSET = "assets/station_fahy"
REGISTERED_SEEDS = range(4, 24)


@pytest.mark.parametrize("seed", REGISTERED_SEEDS)
def test_every_registered_seed_places_every_agent(seed, tmp_path):
    scenario = load_scenario(ASSET)
    config = tmp_path / "config.json"
    config.write_text(json.dumps(scenario.raw))
    walkable = pedpy.WalkableArea(scenario.walkable_area_wkt)
    simulation = jps.Simulation(
        model=_build_model(scenario.model_type, scenario.sim_params),
        geometry=walkable.polygon,
    )
    with contextlib.redirect_stdout(io.StringIO()):
        initialize_simulation_from_json(
            str(config),
            simulation,
            walkable,
            seed=seed,
            model_type=scenario.model_type,
        )
    assert simulation.agent_count() == 333
