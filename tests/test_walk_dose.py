"""The first leg's dose is that of the agent's walk (#171).

Smoke and time on the first leg are measured on the walk from the agent to
the next node; so is its dose: the FED rate at the walk's midpoint, read at
the decision time, over the walk's travel time. Charging the first segment's
dose pro rata to what is left of it left out the walk back to the origin
node of an agent standing behind it.

The graph is ``_linear`` of the golden tests: D0 (0, 0) -> C0 (10, 0) -> E0
(20, 0), no routing engine (straight walks), clear air, v0 = 1.3 m/s.
A uniform FED rate of 7.8 /min is then 0.1 FED per metre walked.
"""

from __future__ import annotations

import math

import pytest
import test_rerouting_golden as golden

from pyfds_evac.core.route_graph import (
    RouteCostConfig,
    _dose,
    _first_hops,
    evaluate_route,
    policy_for,
)

_PATH = ["D0", "C0", "E0"]


class _Clear:
    def sample_extinction(self, time_s, x, y):
        return 0.0


class _UniformFed:
    def sample_fed_rate(self, time_s, x, y):
        return 7.8


class _FedPatch:
    """6 FED/min where y > 1, none elsewhere."""

    def sample_fed_rate(self, time_s, x, y):
        return 6.0 if y > 1.0 else 0.0


def _config(model: str) -> RouteCostConfig:
    return RouteCostConfig(cost_model=model, base_speed_m_per_s=1.3, anticipate=False)


def _route(position, model="gate", fed=_UniformFed()):
    return evaluate_route(
        golden._linear(),
        _PATH,
        0.0,
        0.0,
        _Clear(),
        fed,
        _config(model),
        agent_position=position,
    )


def test_walk_back_to_the_origin_is_dosed():
    """25 m walked from (-5, 0): 2.5 FED, not the 2.0 of the node legs."""
    assert _route((-5.0, 0.0)).fed_max_route == pytest.approx(2.5, abs=1e-9)


def test_additive_composite_counts_the_walk_back():
    """25 m x 1 + w_fed 10 x 2.5 FED = 50, not 45."""
    rc = _route((-5.0, 0.0), model="additive")
    assert rc.composite_cost == pytest.approx(50.0, abs=1e-9)


@pytest.mark.parametrize(
    ("position", "expected"),
    [((4.0, 0.0), 1.6), ((0.0, 0.0), 2.0), (None, 2.0)],
)
def test_ahead_of_the_origin_the_dose_is_unchanged(position, expected):
    """In a uniform field the walk and the pro-rata share agree."""
    assert _route(position).fed_max_route == pytest.approx(expected, abs=1e-9)


def test_dose_is_read_on_the_walk_not_on_the_segment():
    """From (5, 4) the walk to C0 crosses the patch; the segment D0 -> C0 does not.

    Walk 6.403 m, midpoint (7.5, 2) inside the patch: 6 x 4.925 s / 60.
    The segment's midpoint (5, 0) is outside it, so its share is no dose.
    """
    rc = _route((5.0, 4.0), fed=_FedPatch())
    expected = 6.0 * (math.hypot(5.0, 4.0) / 1.3) / 60.0
    assert expected == pytest.approx(0.4925, abs=1e-4)
    assert rc.fed_max_route == pytest.approx(expected, abs=1e-9)


def test_no_rate_is_no_dose_even_over_an_infinite_walk():
    assert _dose(0.0, math.inf) == 0.0
    assert _dose(6.0, math.inf) == math.inf
    assert _dose(6.0, 10.0) == pytest.approx(1.0, abs=1e-12)


def test_first_hop_weight_counts_the_walk_back():
    """Additive hop to C0 from (-5, 0): 15 m x 1 + w_fed 10 x 1.5 FED = 30."""
    config = _config("additive")
    hops = _first_hops(
        golden._linear(),
        "D0",
        (-5.0, 0.0),
        None,
        0.0,
        _Clear(),
        _UniformFed(),
        config,
        policy_for(config),
        None,
    )
    assert hops["C0"] == pytest.approx(30.0, abs=1e-9)
