"""Property tests for the route leg travel time (#836).

Kind: property or invariant. ``_leg_travel_time`` is
``length / (base_speed * speed_factor(K))`` with the Lund law
``factor = clip(1 + beta K / alpha, min_factor, 1)``.

Precondition: ``alpha > 0``, ``beta <= 0`` (speed does not rise with
extinction), ``base_speed > 0``, ``0 <= min_speed_factor <= 1``. Under it
the speed factor is non-increasing in K, so the travel time is
non-decreasing in K and in the length. A speed factor of 0 gives an
infinite time, which still orders correctly. The parameter ranges bound the
search, they are not the validity range of the law.
"""

import math

from hypothesis import given, settings
from hypothesis import strategies as st

from pyfds_evac.core.route_graph import RouteCostConfig, _leg_travel_time
from pyfds_evac.core.smoke_speed import speed_factor_from_extinction

# Fixed examples so CI runs are reproducible; no example database on disk.
_SETTINGS = settings(derandomize=True, database=None, max_examples=200)

_extinction = st.floats(min_value=0.0, max_value=50.0, allow_nan=False)
_length = st.floats(min_value=0.0, max_value=1000.0, allow_nan=False)
_configs = st.builds(
    RouteCostConfig,
    alpha=st.floats(min_value=0.05, max_value=5.0),
    beta=st.floats(min_value=-5.0, max_value=0.0),
    min_speed_factor=st.floats(min_value=0.0, max_value=1.0),
    base_speed_m_per_s=st.floats(min_value=0.1, max_value=3.0),
)


@_SETTINGS
@given(config=_configs, k1=_extinction, k2=_extinction)
def test_speed_factor_does_not_rise_with_extinction(config, k1, k2):
    low, high = sorted((k1, k2))
    args = {
        "alpha": config.alpha,
        "beta": config.beta,
        "min_speed_factor": config.min_speed_factor,
    }
    assert speed_factor_from_extinction(high, **args) <= speed_factor_from_extinction(
        low, **args
    )


@_SETTINGS
@given(config=_configs, length=_length, k1=_extinction, k2=_extinction)
def test_leg_time_is_non_decreasing_in_extinction(config, length, k1, k2):
    low, high = sorted((k1, k2))
    assert (
        _leg_travel_time(length, high, config)[1]
        >= _leg_travel_time(length, low, config)[1]
    )


@_SETTINGS
@given(config=_configs, k=_extinction, l1=_length, l2=_length)
def test_leg_time_is_non_decreasing_in_length(config, k, l1, l2):
    short, long = sorted((l1, l2))
    assert _leg_travel_time(long, k, config)[1] >= _leg_travel_time(short, k, config)[1]


@_SETTINGS
@given(config=_configs, length=_length, k=_extinction)
def test_leg_time_is_non_negative_and_not_nan(config, length, k):
    travel = _leg_travel_time(length, k, config)[1]
    assert not math.isnan(travel)
    assert travel >= 0.0


@_SETTINGS
@given(
    config=st.builds(
        RouteCostConfig,
        alpha=st.floats(min_value=0.05, max_value=1.0),
        beta=st.floats(min_value=-5.0, max_value=-0.1),
        min_speed_factor=st.floats(min_value=0.0, max_value=0.9),
    ),
    length=st.floats(min_value=0.1, max_value=1000.0),
)
def test_dense_smoke_slows_the_leg(config, length):
    """Not vacuous: the orderings above are strict where the law bites."""
    assert (
        _leg_travel_time(length, 1.0, config)[1]
        > _leg_travel_time(length, 0.0, config)[1]
    )
