"""Property tests for the route composite under the additive model (#904).

Kind: property or invariant. On a graph of one edge with one exit and no
rival, under the additive cost model with no queue term and no FED field,
the composite is ``length * (1 + w_smoke * K)`` and ``rank_cost`` is that
composite. For ``w_smoke >= 0`` and a constant extinction K it is
non-decreasing in K and in the edge length. The default ``gate`` model ranks
by time instead, so it is not covered here. The ranges bound the search,
they are not the validity range of the model.
"""

import math

from hypothesis import given, settings
from hypothesis import strategies as st

from pyfds_evac.core.route_graph import (
    RouteCostConfig,
    StageEdge,
    StageGraph,
    StageNode,
    evaluate_route,
)
from pyfds_evac.core.smoke_speed import ConstantExtinctionField

# Fixed examples so CI runs are reproducible; no example database on disk.
_SETTINGS = settings(derandomize=True, database=None, max_examples=200)

_extinction = st.floats(min_value=0.0, max_value=50.0, allow_nan=False)
_length = st.floats(min_value=0.1, max_value=1000.0, allow_nan=False)
_w_smoke = st.floats(min_value=0.0, max_value=10.0, allow_nan=False)


def _composite(length: float, k: float, w_smoke: float) -> float:
    graph = StageGraph(
        nodes={
            "spawn": StageNode("spawn", 0.0, 0.0, "distribution"),
            "exit": StageNode("exit", length, 0.0, "exit"),
        },
        edges={"spawn": [StageEdge("spawn", "exit", length)], "exit": []},
    )
    config = RouteCostConfig(cost_model="additive", w_smoke=w_smoke, w_queue=0.0)
    rc = evaluate_route(
        graph,
        ["spawn", "exit"],
        0.0,
        0.0,
        ConstantExtinctionField(k),
        None,
        config,
    )
    assert rc.rank_cost == rc.composite_cost
    return rc.composite_cost


@_SETTINGS
@given(length=_length, w_smoke=_w_smoke, k1=_extinction, k2=_extinction)
def test_composite_is_non_decreasing_in_extinction(length, w_smoke, k1, k2):
    low, high = sorted((k1, k2))
    assert _composite(length, high, w_smoke) >= _composite(length, low, w_smoke)


@_SETTINGS
@given(w_smoke=_w_smoke, k=_extinction, l1=_length, l2=_length)
def test_composite_is_non_decreasing_in_length(w_smoke, k, l1, l2):
    short, long = sorted((l1, l2))
    assert _composite(long, k, w_smoke) >= _composite(short, k, w_smoke)


@_SETTINGS
@given(length=_length, k=_extinction, w_smoke=_w_smoke)
def test_composite_is_finite_and_at_least_the_length(length, k, w_smoke):
    composite = _composite(length, k, w_smoke)
    assert math.isfinite(composite)
    assert composite >= length * (1.0 - 1e-9)


@_SETTINGS
@given(
    length=_length,
    k=st.floats(min_value=0.1, max_value=50.0),
    w_smoke=st.floats(min_value=0.1, max_value=10.0),
)
def test_smoke_raises_the_composite(length, k, w_smoke):
    """Not vacuous: the orderings above are strict where the term bites."""
    assert _composite(length, k, w_smoke) > _composite(length, 0.0, w_smoke)
