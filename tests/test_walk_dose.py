"""An agent behind its route's origin is dosed for the walk back to it (#171).

The first segment's dose is charged pro rata to what is left of it, since
the dose already taken on it is in ``current_fed``. That share is capped at
1, so an agent standing behind the origin node was charged nothing for the
stretch its walk is longer than the segment. That stretch -- the first
``remaining - L0`` metres of the walk from the agent -- is now charged at
its mean FED rate, sampled along it at the decision time, over the walk's
pace. On or ahead of the origin the dose is unchanged.

The graph is ``_linear`` of the golden tests: D0 (0, 0) -> C0 (10, 0) -> E0
(20, 0), no routing engine (straight walks), clear air, v0 = 1.3 m/s, 2 m
sampling steps. A uniform FED rate of 7.8 /min is then 0.1 FED per metre
walked.
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
from pyfds_evac.core.smoke_speed import speed_factor_from_extinction

_PATH = ["D0", "C0", "E0"]
_LEG_S = 10.0 / 1.3  # one node leg
_BACK_S = 5.0 / 1.3  # the 5 m stretch from (-5, 0) back to D0


class _Clear:
    def sample_extinction(self, time_s, x, y):
        return 0.0


class _UniformFed:
    def sample_fed_rate(self, time_s, x, y):
        return 7.8


class _FedBehind:
    """6 FED/min where x < 0, none elsewhere."""

    def sample_fed_rate(self, time_s, x, y):
        return 6.0 if x < 0.0 else 0.0


class _FedPatch:
    """6 FED/min where y > 1, none elsewhere."""

    def sample_fed_rate(self, time_s, x, y):
        return 6.0 if y > 1.0 else 0.0


class _HotCell:
    """0.1 FED/min, and 1.3 in one 0.5 m cell around (-2.5, 0)."""

    def sample_fed_rate(self, time_s, x, y):
        hot = abs(x + 2.5) < 0.25 and abs(y) < 0.25
        return 1.3 if hot else 0.1


def _config(model: str) -> RouteCostConfig:
    return RouteCostConfig(cost_model=model, base_speed_m_per_s=1.3, anticipate=False)


class _Smoke:
    """Extinction 2 /m everywhere."""

    def sample_extinction(self, time_s, x, y):
        return 2.0


def _route(position, model="gate", fed=_UniformFed(), smoke=_Clear()):
    return evaluate_route(
        golden._linear(),
        _PATH,
        0.0,
        0.0,
        smoke,
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
def test_on_or_ahead_of_the_origin_the_dose_is_unchanged(position, expected):
    assert _route(position).fed_max_route == pytest.approx(expected, abs=1e-9)


def test_ahead_of_the_origin_the_segment_is_charged_pro_rata():
    """From (5, 4) the walk to C0 is shorter than D0 -> C0: no stretch is added.

    The walk crosses the patch, the segment's midpoint (5, 0) does not; the
    first segment keeps its pro-rata dose, 0.
    """
    assert _route((5.0, 4.0), fed=_FedPatch()).fed_max_route == 0.0


def test_stretch_behind_the_origin_is_dosed_at_its_mean_rate():
    """The 5 m back to D0 is sampled at x = -5, -3.33, -1.67 and 0.

    Three samples lie in the x < 0 patch: mean 4.5 /min over 3.846 s. The
    node legs' midpoints (x = 5, 15) are clear. A single sample at the
    stretch's midpoint (-2.5, 0) would read 6 /min, a dose of 0.38462.
    """
    rc = _route((-5.0, 0.0), fed=_FedBehind())
    expected = 4.5 * _BACK_S / 60.0
    assert expected == pytest.approx(0.28846, abs=1e-5)
    assert rc.fed_max_route == pytest.approx(expected, abs=1e-9)


def test_one_hot_cell_does_not_make_the_dose_of_the_stretch():
    """A 0.5 m hot cell at the stretch's midpoint does not set its dose.

    The stretch is sampled at x = -5, -3.33, -1.67 and 0, none in the cell,
    so the whole route reads the 0.1 /min background over its 25 m. The
    expected value is the mean at the sample points, not the cell's
    length-weighted share of the stretch: a cell narrower than the sampling
    step counts only where it holds a sample point. A midpoint sample would
    charge the stretch 1.3 /min, 13 times the background.
    """
    rc = _route((-5.0, 0.0), fed=_HotCell())
    background = 0.1 * (2 * _LEG_S + _BACK_S) / 60.0
    assert rc.fed_max_route == pytest.approx(background, abs=1e-9)
    assert rc.fed_max_route < 0.1 * 2 * _LEG_S / 60.0 + 1.3 * _BACK_S / 60.0


def test_stretch_behind_the_origin_is_timed_at_the_walk_pace():
    """In smoke the 5 m back to D0 takes 5 / (1.3 sf) s, not 5 / 1.3 s.

    Every leg is walked at 1.3 sf m/s, so the 25 m take 25 / (1.3 sf) s at
    0.1 FED per metre in clear air: 2.5 / sf.
    """
    config = _config("gate")
    sf = speed_factor_from_extinction(
        2.0,
        alpha=config.alpha,
        beta=config.beta,
        min_speed_factor=config.min_speed_factor,
    )
    assert sf < 0.9
    rc = _route((-5.0, 0.0), smoke=_Smoke())
    assert rc.fed_max_route == pytest.approx(2.5 / sf, abs=1e-9)


def test_a_walk_within_the_tolerance_of_the_segment_is_on_the_origin():
    """1e-7 m behind D0 is on it: the pro-rata dose, bit for bit.

    1e-5 m behind it, the stretch is charged: 2.0 + 0.1 x 1e-5.
    """
    on_origin = _route((0.0, 0.0)).fed_max_route
    assert _route((-1e-7, 0.0)).fed_max_route == on_origin
    behind = _route((-1e-5, 0.0)).fed_max_route
    assert behind == pytest.approx(2.0 + 1e-6, abs=1e-12)


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
        {},
        None,
    )
    assert hops["C0"] == pytest.approx(30.0, abs=1e-9)
