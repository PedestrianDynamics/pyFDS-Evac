"""Every registered seed of the Station study places every agent (#380).

Both Station decks are covered: ``station_fahy`` on the hand-drawn geometry and
``station_nist`` on the NIST-derived one (#375).

The study registers seeds 4-23. Before the rear bar / dart room area was
widened, seeds 18, 20 and 22 stopped in placement with "Only 26 (27) of 28
could be placed": that area's 28 agents had 13.2 m2.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import sys
from collections import Counter
from pathlib import Path

import jupedsim as jps
import pedpy
import pytest

from pyfds_evac.core.scenario import _build_model, load_scenario
from pyfds_evac.core.simulation_init import initialize_simulation_from_json

ASSETS = ("assets/station_fahy", "assets/station_nist")
REGISTERED_SEEDS = range(4, 24)
REPO = Path(__file__).resolve().parents[1]


def _placed_agents(config_path, seed, tmp_path) -> int:
    scenario = load_scenario(str(config_path))
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
    return simulation.agent_count()


@pytest.mark.parametrize("asset", ASSETS)
@pytest.mark.parametrize("seed", REGISTERED_SEEDS)
def test_every_registered_seed_places_every_agent(asset, seed, tmp_path):
    assert _placed_agents(asset, seed, tmp_path) == 333


@pytest.mark.parametrize("asset", ASSETS)
@pytest.mark.parametrize("seed", REGISTERED_SEEDS)
def test_every_registered_seed_places_all_455_labelled_agents(asset, seed, tmp_path):
    """Placed, unplaced and victim agents all fit (#375, config_full.json)."""
    assert _placed_agents(f"{asset}/config_full.json", seed, tmp_path) == 455


# ---- config_full.json (opt-in --full) ---------------------------------------


@pytest.fixture(scope="module")
def fahy_build():
    path = REPO / "assets/station_fahy/build_scenario.py"
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location("station_fahy_build_pop", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_json(asset, name):
    return json.loads((REPO / asset / name).read_text())


def _by_label(config):
    out: Counter = Counter()
    for d in config["distributions"].values():
        out[d["parameters"]["population"]] += d["parameters"]["number"]
    return out


@pytest.mark.parametrize("asset", ASSETS)
def test_default_config_has_no_labels_and_333_agents(asset):
    dists = _load_json(asset, "config.json")["distributions"].values()
    assert all("population" not in d["parameters"] for d in dists)
    assert sum(d["parameters"]["number"] for d in dists) == 333


@pytest.mark.parametrize("asset", ASSETS)
def test_full_config_is_the_default_plus_labelled_agents(asset, fahy_build):
    base = _load_json(asset, "config.json")
    full = _load_json(asset, "config_full.json")
    assert full == fahy_build.with_populations(base)
    assert {k: v for k, v in full.items() if k != "distributions"} == {
        k: v for k, v in base.items() if k != "distributions"
    }


@pytest.mark.parametrize("asset", ASSETS)
def test_full_config_totals_split_by_label(asset):
    full = _load_json(asset, "config_full.json")
    assert _by_label(full) == {"placed": 333, "unplaced": 22, "victim": 100}


@pytest.mark.parametrize("asset", ASSETS)
def test_full_config_areas_are_proportional_to_placed_survivors(asset, fahy_build):
    full = _load_json(asset, "config_full.json")
    placed = fahy_build.F.agents_per_row()
    per_area: dict[str, Counter] = {row: Counter() for row in placed}
    for d in full["distributions"].values():
        p = d["parameters"]
        per_area[p["fahy_row"]][p["population"]] += p["number"]
    for population, total in (("unplaced", 22), ("victim", 100)):
        for row, n in placed.items():
            exact = total * n / sum(placed.values())
            assert abs(per_area[row][population] - exact) < 1, (row, population)
    assert {r: c["placed"] for r, c in per_area.items()} == placed


# Largest remainder by hand from the placed counts: victims 100 n / 333 floor to
# 96, the four largest remainders (sunroom .80, between bars .71, dance floor
# .52, platform .50) get one more; unplaced 22 n / 333 floor to 15, the seven
# largest (platform .99, dance floor .95, back hallway .92, between bars .92,
# behind dance floor .89, dart room .85, center stage-side .46) get one more.
EXTRA = {  # area: (unplaced, victim)
    "Stage": (0, 1),
    "Near stage door": (1, 5),
    "Near stage or on dance floor": (5, 23),
    "Back wall platform": (1, 5),
    "Sunroom": (1, 5),
    "Behind dance floor": (5, 22),
    "Back hallway": (1, 4),
    "Between bars": (2, 9),
    "Rear bar / dart room": (2, 8),
    "Entryway": (1, 5),
    "Main bar": (2, 11),
    "Center stage-side": (1, 2),
}


@pytest.mark.parametrize("asset", ASSETS)
def test_full_config_extra_agents_per_area_are_the_hand_apportionment(asset):
    full = _load_json(asset, "config_full.json")
    per_area: dict[str, Counter] = {row: Counter() for row in EXTRA}
    for d in full["distributions"].values():
        p = d["parameters"]
        per_area[p["fahy_row"]][p["population"]] += p["number"]
    got = {r: (c["unplaced"], c["victim"]) for r, c in per_area.items()}
    assert got == EXTRA


@pytest.mark.parametrize("asset", ASSETS)
def test_extra_agents_share_the_area_polygon_and_parameters(asset):
    full = _load_json(asset, "config_full.json")
    reference: dict[str, dict] = {}
    for d in full["distributions"].values():
        p = d["parameters"]
        ref = reference.setdefault(p["fahy_row"], d)
        keep = {"number", "familiarity", "fahy_class", "population"}
        assert d["coordinates"] == ref["coordinates"]
        assert {k: v for k, v in p.items() if k not in keep} == {
            k: v for k, v in ref["parameters"].items() if k not in keep
        }
