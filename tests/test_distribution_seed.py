"""Per-distribution streams are hashed from the distribution key (#360).

Seeding a distribution's streams with ``seed + index`` gave distribution 1
under seed s the streams of distribution 0 under seed s + 1, so an ensemble
over consecutive seeds reused streams across its members.
"""

from __future__ import annotations

import contextlib
import io
import json

import jupedsim as jps
import pedpy
import pytest
from shapely.geometry import box

import pyfds_evac.core.simulation_init as simulation_init_mod
from pyfds_evac.core.agent_seed import (
    PURPOSE_AGENT_VALUES,
    PURPOSE_POSITIONS,
    PURPOSE_PREMOVEMENT,
    PURPOSE_SHUFFLE,
    distribution_seed,
)
from pyfds_evac.core.scenario import load_scenario
from pyfds_evac.core.simulation_init import (
    _seed_shared_areas,
    initialize_simulation_from_json,
)

PURPOSES = (
    PURPOSE_POSITIONS,
    PURPOSE_SHUFFLE,
    PURPOSE_PREMOVEMENT,
    PURPOSE_AGENT_VALUES,
)
KEYS = [f"jps-distributions_{i}" for i in range(47)]
SEEDS = range(1, 21)

# Pinned: a change here changes every seeded placement of every run.
PINNED = [
    ((42, "jps-distributions_0", PURPOSE_POSITIONS), 3662982994),
    ((42, "jps-distributions_1", PURPOSE_POSITIONS), 334539527),
    ((None, "jps-distributions_0", PURPOSE_PREMOVEMENT), 3324857160),
    ((7, "jps-distributions_0", PURPOSE_AGENT_VALUES), 2213880596),
    ((7, "jps-distributions_0", PURPOSE_SHUFFLE), 615044197),
]


@pytest.mark.parametrize(("args", "expected"), PINNED)
def test_distribution_seed_is_pinned(args, expected):
    assert distribution_seed(*args) == expected


@pytest.mark.parametrize("purpose", PURPOSES)
def test_no_stream_is_shared_across_seeds_and_distributions(purpose):
    """The Station study's grid: 20 seeds x 47 distributions, all apart."""
    seeds = [distribution_seed(s, k, purpose) for s in SEEDS for k in KEYS]
    assert len(set(seeds)) == len(seeds)
    assert all(0 <= s < 2**32 for s in seeds)


def test_purposes_are_separate_streams():
    assert len({distribution_seed(3, KEYS[0], p) for p in PURPOSES}) == len(PURPOSES)


def _shared_area_positions(seed):
    """Two congruent rooms, the second 10 m east of the first."""
    params = {"number": 8, "radius": 0.2}
    spawns = [
        {"area": box(0, 0, 4, 4), "params": params, "index": 0, "dist_key": KEYS[0]},
        {"area": box(10, 0, 14, 4), "params": params, "index": 1, "dist_key": KEYS[1]},
    ]
    placed = _seed_shared_areas(spawns, seed)
    room_0 = sorted((round(x, 6), round(y, 6)) for x, y in placed[0])
    room_1 = sorted((round(x - 10.0, 6), round(y, 6)) for x, y in placed[1])
    return room_0, room_1


@pytest.mark.parametrize("seed", [1, 4, 19])
def test_placements_are_independent_across_consecutive_seeds(seed):
    room_0, room_1 = _shared_area_positions(seed)
    next_room_0, _ = _shared_area_positions(seed + 1)
    assert room_1 != next_room_0
    assert room_0 != room_1
    assert _shared_area_positions(seed) == (room_0, room_1)


def test_over_full_shared_area_names_every_distribution():
    """Profiles sharing one polygon are counted together, so all are named (#692)."""
    params = {"number": 300, "radius": 0.2}
    spawns = [
        {"area": box(0, 0, 4, 4), "params": params, "index": i, "dist_key": key}
        for i, key in enumerate(KEYS[:2])
    ]
    with pytest.raises(
        ValueError,
        match=rf"^Distributions '{KEYS[0]}', '{KEYS[1]}': requested 600 agents "
        r"but area can hold at most ~\d+\.",
    ):
        _seed_shared_areas(spawns, 1)


def _record_streams(monkeypatch, config, walkable, seed):
    """Initialise *asset* and return the seed of every per-distribution stream."""
    streams = []

    def record(name, real):
        def wrapper(*args, **kwargs):
            streams.append((name, kwargs["seed"]))
            return real(*args, **kwargs)

        return wrapper

    def record_premovement(dist_type, params, seed=None):
        streams.append(("premovement", seed))
        return real_premovement(dist_type, params, seed)

    def record_agent_values(params, count, rng):
        # The Mersenne Twister key of a RandomState fingerprints its seed.
        streams.append(("agent_values", tuple(rng.get_state()[1][:4])))
        return real_agent_values(params, count, rng)

    real_premovement = simulation_init_mod.create_premovement_distribution
    real_agent_values = simulation_init_mod._sample_agent_values
    for name in ("distribute_by_number", "distribute_until_filled"):
        monkeypatch.setattr(jps, name, record(name, getattr(jps, name)))
    monkeypatch.setattr(
        simulation_init_mod, "create_premovement_distribution", record_premovement
    )
    monkeypatch.setattr(
        simulation_init_mod, "_sample_agent_values", record_agent_values
    )

    simulation = jps.Simulation(
        model=jps.CollisionFreeSpeedModel(), geometry=walkable.polygon
    )
    with contextlib.redirect_stdout(io.StringIO()):
        initialize_simulation_from_json(str(config), simulation, walkable, seed=seed)
    monkeypatch.undo()
    return streams


@pytest.mark.parametrize(
    "asset",
    [
        "assets/station_fahy",  # no journeys: the fallback initialiser
        "assets/Haspel",  # journeys: the full-config initialiser
    ],
)
def test_consecutive_seeds_share_no_distribution_stream(asset, monkeypatch, tmp_path):
    scenario = load_scenario(asset)
    config = tmp_path / "config.json"
    config.write_text(json.dumps(scenario.raw))
    walkable = pedpy.WalkableArea(scenario.walkable_area_wkt)
    first = _record_streams(monkeypatch, config, walkable, 4)
    second = _record_streams(monkeypatch, config, walkable, 5)
    assert first, "no per-distribution stream was drawn"
    assert not set(first) & set(second)
    # Within a run, no two distributions share a stream either.
    assert len(set(first)) == len(first)
    assert _record_streams(monkeypatch, config, walkable, 4) == first
