"""The first leg's dose is that of the agent's walk (#171).

Smoke and time on the first leg are measured on the walk from the agent to
the next node; so is its dose: the mean FED rate at the walk's extinction
sample points, all read at the decision time, over the walk's travel time. Charging the first segment's
dose pro rata to what is left of it left out the walk back to the origin
node of an agent standing behind it.

The graph is ``_linear`` of the golden tests: D0 (0, 0) -> C0 (10, 0) -> E0
(20, 0), no routing engine (straight walks), clear air, v0 = 1.3 m/s, 2 m
sampling steps.
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


class _FedSquare:
    """0.375 y^2 FED/min."""

    def sample_fed_rate(self, time_s, x, y):
        return 0.375 * y * y


class _HotCell:
    """0.1 FED/min, and 1.3 in one 0.5 m cell around (7.5, 2)."""

    def sample_fed_rate(self, time_s, x, y):
        hot = abs(x - 7.5) < 0.25 and abs(y - 2.0) < 0.25
        return 1.3 if hot else 0.1


# The walk from (5, 4) to C0 (10, 0): 6.403 m, sampled at 5 points, at
# y = 4, 3, 2, 1, 0 (the middle one at (7.5, 2)).
_WALK_S = math.hypot(5.0, 4.0) / 1.3


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

    Three of the walk's five samples are in the patch: mean 3.6 /min over
    4.925 s. The segment's midpoint (5, 0) is outside it, so its share is
    no dose.
    """
    rc = _route((5.0, 4.0), fed=_FedPatch())
    expected = 3.6 * _WALK_S / 60.0
    assert expected == pytest.approx(0.29553, abs=1e-5)
    assert rc.fed_max_route == pytest.approx(expected, abs=1e-9)


def test_dose_is_the_mean_rate_on_the_walk():
    """0.375 y^2: mean 0.375 (16 + 9 + 4 + 1 + 0) / 5 = 2.25 /min.

    The midpoint (y = 2) alone reads 1.5 /min, a dose of 0.12314.
    """
    rc = _route((5.0, 4.0), fed=_FedSquare())
    expected = 2.25 * _WALK_S / 60.0
    assert expected == pytest.approx(0.18471, abs=1e-5)
    assert rc.fed_max_route == pytest.approx(expected, abs=1e-9)


def test_one_hot_cell_does_not_make_the_dose_of_the_walk():
    """A hot cell on the walk's midpoint counts as one sample of five.

    Mean (4 x 0.1 + 1.3) / 5 = 0.34 /min, not the 1.3 /min, 13 times the
    background, that a midpoint sample reads. The leg C0 -> E0 adds
    0.1 /min over its 10 m.
    """
    rc = _route((5.0, 4.0), fed=_HotCell())
    walk = rc.fed_max_route - 0.1 * (10.0 / 1.3) / 60.0
    assert walk == pytest.approx(0.34 * _WALK_S / 60.0, abs=1e-9)
    assert walk < 0.3 * (1.3 * _WALK_S / 60.0)


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
