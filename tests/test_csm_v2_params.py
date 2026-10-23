"""CollisionFreeSpeedModelV2 decks that omit neighbour repulsion keys (#757).

A deck's ``simulationParams`` may omit ``strength_neighbor_repulsion`` or
``range_neighbor_repulsion``. Each missing key takes the value the
CollisionFreeSpeedModel builder uses (2.6, 0.1), on its own. The missing key
used to raise ``AttributeError`` in ``create_agent_parameters``.

Fixture: ``assets/t_junction`` (one distribution, journeys, flow spawning).
"""

from __future__ import annotations

import contextlib
import io
from types import SimpleNamespace

import pytest

from pyfds_evac.core import load_scenario, run_scenario
from pyfds_evac.core.scenario import _build_model
from pyfds_evac.core.simulation_init import create_agent_parameters

V2 = "CollisionFreeSpeedModelV2"
REPULSION_KEYS = ("strength_neighbor_repulsion", "range_neighbor_repulsion")
T_JUNCTION = "assets/t_junction"


def _v2(global_params):
    return create_agent_parameters(
        V2, (0.0, 0.0), {"v0": 1.0}, global_params=global_params
    )


def _repulsion(params):
    return (params.strength_neighbor_repulsion, params.range_neighbor_repulsion)


def test_v2_keys_all_missing_take_the_cfsm_defaults():
    assert _repulsion(_v2(SimpleNamespace())) == pytest.approx((2.6, 0.1))


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ({"strength_neighbor_repulsion": 3.0}, (3.0, 0.1)),
        ({"range_neighbor_repulsion": 0.2}, (2.6, 0.2)),
    ],
)
def test_v2_one_key_missing_keeps_the_other(given, expected):
    assert _repulsion(_v2(SimpleNamespace(**given))) == pytest.approx(expected)


def test_v2_keys_set_pass_through():
    given = SimpleNamespace(
        strength_neighbor_repulsion=3.0, range_neighbor_repulsion=0.15
    )
    assert _repulsion(_v2(given)) == pytest.approx((3.0, 0.15))


def test_v2_geometry_repulsion_and_time_gap_are_unchanged():
    params = _v2(SimpleNamespace())
    assert params.strength_geometry_repulsion == pytest.approx(5.0)
    assert params.range_geometry_repulsion == pytest.approx(0.02)
    assert params.time_gap == pytest.approx(1.0)


@pytest.mark.parametrize(
    "deck",
    [
        {},
        {"strength_neighbor_repulsion": 3.0},
        {"range_neighbor_repulsion": 0.2},
        {"strength_neighbor_repulsion": 3.0, "range_neighbor_repulsion": 0.15},
    ],
)
def test_v2_matches_the_cfsm_builder_for_the_same_deck(deck):
    cfsm = _build_model("CollisionFreeSpeedModel", deck)
    assert _repulsion(_v2(SimpleNamespace(**deck))) == pytest.approx(_repulsion(cfsm))


def _run_counts(keys):
    """Counts of a 1 s run with *keys* set (others removed) on t_junction."""
    scenario = load_scenario(T_JUNCTION)
    scenario.set_model_type(V2)
    for key in REPULSION_KEYS:
        scenario.sim_params.pop(key, None)
        scenario._simulation_params().pop(key, None)
    for key, value in keys.items():
        scenario.sim_params[key] = value
        scenario._simulation_params()[key] = value
    scenario.set_max_time(1)
    with contextlib.redirect_stdout(io.StringIO()):
        result = run_scenario(scenario, seed=1)
    try:
        return {k: result.metrics[k] for k in ("total_agents", "agents_remaining")}
    finally:
        result.cleanup()


def test_v2_scenario_without_repulsion_keys_runs():
    # Missing keys take the defaults, so the run equals the one that sets
    # them explicitly (2.6, 0.1).
    defaults = {"strength_neighbor_repulsion": 2.6, "range_neighbor_repulsion": 0.1}
    counts = _run_counts({})
    assert counts == _run_counts(defaults)
    assert counts["total_agents"] == 1  # seed 1, 1 s: a regression pin
