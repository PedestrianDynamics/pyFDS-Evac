"""Gaussian radii stay within the radius placement spaces for (#709).

Placement keeps agents ``2 b`` apart and ``b`` from the area's edge, with
``b = min(max(mean + 3 std, 0.1), 1.0)`` for a Gaussian radius. Before #709
the draws were clipped to [0.1, 1.0] only, so a draw beyond mean + 3 std
was larger than the spacing assumed, and a mean + 3 std below 0.1 gave a
bound below every draw. The draws are now clipped to [0.1, b], with the
same number of draws, so every in-bound radius and every v0 of a seed is
unchanged.
"""

from __future__ import annotations

import contextlib
import io
import json

import jupedsim as jps
import numpy as np
import pedpy
import pytest

import pyfds_evac.core.simulation_init as simulation_init_mod
from pyfds_evac.core.agent_seed import PURPOSE_AGENT_VALUES, distribution_seed
from pyfds_evac.core.fds_import import _max_radius
from pyfds_evac.core.scenario import load_scenario
from pyfds_evac.core.simulation_init import (
    _get_max_agent_radius,
    _sample_agent_values,
    initialize_simulation_from_json,
)


class _FixedDraws:
    """An rng whose ``normal`` returns the given draws."""

    def __init__(self, draws):
        self.draws = np.asarray(draws, dtype=float)

    def normal(self, mean, std, n):
        assert n == len(self.draws)
        return self.draws.copy()


def _gaussian(mean: float, std: float) -> dict:
    return {"radius": mean, "radius_distribution": "gaussian", "radius_std": std}


@pytest.mark.parametrize(
    ("params", "bound", "draws", "radii"),
    [
        # T1, upper tail: 0.36 > b = 0.35. Gave 0.36 before #709.
        (_gaussian(0.2, 0.05), 0.35, [0.36, 0.20, 0.05], [0.35, 0.20, 0.10]),
        # T2, the 1 m cap: as before.
        (_gaussian(0.9, 0.1), 1.0, [1.25, 0.95], [1.0, 0.95]),
        # T3, lower end: mean + 3 std = 0.08 is raised to 0.1.
        (_gaussian(0.05, 0.01), 0.1, [0.03, 0.08, 0.12], [0.1, 0.1, 0.1]),
    ],
    ids=["upper-tail", "cap", "lower-end"],
)
def test_draws_are_clipped_to_the_spacing_bound(params, bound, draws, radii):
    assert _get_max_agent_radius(params) == pytest.approx(bound, abs=1e-12)
    got, _ = _sample_agent_values(params, len(draws), _FixedDraws(draws))
    assert got.tolist() == pytest.approx(radii, abs=1e-12)
    assert got.max() <= _get_max_agent_radius(params)


def test_the_stream_is_unchanged():
    """T4: same draws; only radii beyond the bound change, and v0s do not."""
    params = {
        **_gaussian(0.2, 0.05),
        "v0": 1.25,
        "v0_distribution": "gaussian",
        "v0_std": 0.3,
    }
    n = 10000
    radii, v0s = _sample_agent_values(params, n, np.random.RandomState(7))

    old_rng = np.random.RandomState(7)
    old_radii = old_rng.normal(0.2, 0.05, n).clip(0.1, 1.0)
    old_v0s = old_rng.normal(1.25, 0.3, n).clip(0.1, 5.0)

    assert np.array_equal(v0s, old_v0s)
    in_bound = old_radii <= 0.35
    assert np.array_equal(radii[in_bound], old_radii[in_bound])
    assert np.count_nonzero(radii != old_radii) == np.count_nonzero(~in_bound) > 0


@pytest.mark.parametrize(
    "params",
    [
        _gaussian(0.2, 0.05),
        _gaussian(0.9, 0.1),
        _gaussian(0.05, 0.01),
        {"radius": 0.2, "radius_distribution": "constant"},
    ],
    ids=["upper-tail", "cap", "lower-end", "constant"],
)
def test_importer_and_run_share_the_bound(params):
    """T5: the importer's capacity check spaces as the run does."""
    assert _max_radius(params) == _get_max_agent_radius(params)


SEED = 420  # station_fahy's baseSeed, the seed of its default run


def _station_fahy(monkeypatch, tmp_path, sampler, max_radius=None):
    """Initialise station_fahy at seed 420 with *sampler* drawing the radii.

    Returns the agents' positions and radii, and the distribution each
    radius was drawn for, told apart by the seed of its stream.
    *max_radius*, if given, replaces the spacing bound placement reads.
    """
    scenario = load_scenario("assets/station_fahy")
    config = tmp_path / "config.json"
    config.write_text(json.dumps(scenario.raw))
    walkable = pedpy.WalkableArea(scenario.walkable_area_wkt)
    # The Mersenne Twister key of a RandomState fingerprints its seed.
    by_stream = {
        tuple(
            np.random.RandomState(
                distribution_seed(SEED, key, PURPOSE_AGENT_VALUES)
            ).get_state()[1][:4]
        ): key
        for key in scenario.raw["distributions"]
    }
    drawn: list[tuple[str, float]] = []

    def record(params, count, rng):
        key = by_stream[tuple(rng.get_state()[1][:4])]
        radii, v0s = sampler(params, count, rng)
        drawn.extend((key, float(r)) for r in radii)
        return radii, v0s

    monkeypatch.setattr(simulation_init_mod, "_sample_agent_values", record)
    if max_radius is not None:
        monkeypatch.setattr(simulation_init_mod, "_get_max_agent_radius", max_radius)
    simulation = jps.Simulation(
        model=jps.CollisionFreeSpeedModel(), geometry=walkable.polygon
    )
    with contextlib.redirect_stdout(io.StringIO()):
        _, positions, agent_radii, _ = initialize_simulation_from_json(
            str(config), simulation, walkable, seed=SEED
        )
    monkeypatch.undo()
    assert sorted(r for _, r in drawn) == sorted(agent_radii.values())
    return positions, drawn


def test_station_fahy_seed_420_moves_one_radius(monkeypatch, tmp_path):
    """T6: one radius changes, 0.2656 -> 0.26 m; positions do not move."""
    real = simulation_init_mod._sample_agent_values

    def before_709(params, count, rng):
        # The same draws, clipped to [0.1, 1.0] only.
        state = rng.get_state()
        radii, v0s = real(params, count, rng)
        replay = np.random.RandomState()
        replay.set_state(state)
        mean, std = params["radius"], params["radius_std"]
        return replay.normal(mean, std, count).clip(0.1, 1.0), v0s

    positions, drawn = _station_fahy(monkeypatch, tmp_path, real)

    def bound_before_709(params):
        mean = params.get("radius", 0.2)
        if params.get("radius_distribution") == "gaussian" and params.get("radius_std"):
            return min(mean + 3 * params["radius_std"], 1.0)
        return mean

    old_positions, old_drawn = _station_fahy(
        monkeypatch, tmp_path, before_709, bound_before_709
    )

    assert len(drawn) == len(positions) == 333
    assert positions == old_positions
    changed = [(new, old) for new, old in zip(drawn, old_drawn) if new != old]
    assert len(changed) == 1
    (new_key, new_r), (old_key, old_r) = changed[0]
    assert new_key == old_key == "jps-distributions_46"
    assert round(old_r, 4) == 0.2656
    assert new_r == pytest.approx(0.26, abs=1e-12)
