"""Fallbacks that used to swallow every exception now name what failed.

B1 an unusable checkpoint or zone polygon in the fallback initialisation,
B2 a failed inner buffer of a spawn polygon, B3 a failed routing query,
B4 a failed read or write of an agent's desired speed.
"""

import logging
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from shapely.errors import GEOSException
from shapely.geometry import box

from pyfds_evac.core import route_graph, simulation_init
from pyfds_evac.core.direct_steering_runtime import (
    get_agent_desired_speed,
    set_agent_desired_speed,
)
from pyfds_evac.core.route_graph import _make_edge, _walkable_waypoints
from pyfds_evac.core.simulation_init import (
    _initialize_with_fallback,
    _random_point_in_polygon,
)

# --- B1 ---------------------------------------------------------------------


def _fallback_data(**extra):
    exit_polygon = [[9, 0], [10, 0], [10, 1], [9, 1], [9, 0]]
    return {"exits": {"e0": {"coordinates": exit_polygon}}, **extra}


def _run_fallback(data):
    return _initialize_with_fallback(
        MagicMock(),
        data,
        SimpleNamespace(polygon=box(0, 0, 10, 10)),
        1,
        "CollisionFreeSpeedModel",
    )


def test_fallback_checkpoint_that_is_no_polygon_raises():
    data = _fallback_data(checkpoints={"cp7": {"coordinates": [[0, 0], [1, 1]]}})
    with pytest.raises(ValueError, match=r"checkpoints\.cp7: coordinates do not form"):
        _run_fallback(data)


def test_fallback_zone_that_is_no_polygon_raises():
    data = _fallback_data(zones={"z3": {"coordinates": [1, 2, 3]}})
    with pytest.raises(ValueError, match=r"zones\.z3: coordinates do not form"):
        _run_fallback(data)


# --- B2 ---------------------------------------------------------------------


class _Polygon:
    """A polygon stand-in whose inner buffer fails."""

    bounds = (0.0, 0.0, 1.0, 1.0)
    wkb = b"stub"

    def __init__(self, error):
        self._error = error

    def buffer(self, distance):
        raise self._error

    def contains(self, point):
        return True


class _Rng:
    def uniform(self, low, high):
        return 0.5 * (low + high)


def test_buffer_geos_failure_warns_once_and_falls_back(caplog):
    polygon = _Polygon(GEOSException("TopologyException"))
    with caplog.at_level(logging.WARNING, logger=simulation_init.__name__):
        assert _random_point_in_polygon(polygon, _Rng()) == (0.5, 0.5)
        assert _random_point_in_polygon(polygon, _Rng()) == (0.5, 0.5)
    warnings = [r for r in caplog.records if "buffer" in r.getMessage()]
    assert len(warnings) == 1
    assert "TopologyException" in warnings[0].getMessage()


def test_buffer_value_error_propagates():
    with pytest.raises(ValueError, match="bad distance"):
        _random_point_in_polygon(_Polygon(ValueError("bad distance")), _Rng())


# --- B3 ---------------------------------------------------------------------


class _Engine:
    def __init__(self, error):
        self._error = error

    def compute_waypoints(self, start, end):
        raise self._error


def test_routing_failure_falls_back_with_one_warning_per_engine(caplog):
    engine = _Engine(RuntimeError("Point (5, 5) is outside of accessible area"))
    with caplog.at_level(logging.WARNING, logger=route_graph.__name__):
        first = _walkable_waypoints(engine, (0.0, 0.0), (3.0, 4.0))
        second = _walkable_waypoints(engine, (1.0, 1.0), (3.0, 4.0))
    assert first == [(0.0, 0.0), (3.0, 4.0)]
    assert second == [(1.0, 1.0), (3.0, 4.0)]
    warnings = [r for r in caplog.records if "outside of accessible" in r.getMessage()]
    assert len(warnings) == 1
    other = _Engine(RuntimeError("again"))
    with caplog.at_level(logging.WARNING, logger=route_graph.__name__):
        _walkable_waypoints(other, (0.0, 0.0), (3.0, 4.0))
    assert len([r for r in caplog.records if "again" in r.getMessage()]) == 1


def test_routing_programming_error_propagates():
    with pytest.raises(TypeError):
        _walkable_waypoints(_Engine(TypeError("bad arguments")), (0, 0), (1, 1))
    nodes = [SimpleNamespace(centroid_x=0.0, centroid_y=0.0, stage_id=i) for i in "ab"]
    with pytest.raises(TypeError):
        _make_edge(nodes[0], nodes[1], _Engine(TypeError("bad arguments")))


# --- B4 ---------------------------------------------------------------------


class CollisionFreeSpeedModelState:
    """Named as JuPedSim names the state, so the speed attribute is mapped.

    The attribute exists (``hasattr`` is true) but cannot be read as a number
    and rejects every write.
    """

    desired_speed = None

    def __setattr__(self, name, value):
        raise ValueError("rejected")


def test_desired_speed_read_failure_names_the_agent():
    agent = SimpleNamespace(id=17, model=CollisionFreeSpeedModelState())
    with pytest.raises(RuntimeError, match="agent 17") as excinfo:
        get_agent_desired_speed(agent)
    assert "CollisionFreeSpeedModelState" in str(excinfo.value)
    assert "desired_speed" in str(excinfo.value)


def test_desired_speed_write_failure_names_the_agent():
    agent = SimpleNamespace(id=17, model=CollisionFreeSpeedModelState())
    with pytest.raises(RuntimeError, match="agent 17") as excinfo:
        set_agent_desired_speed(agent, 1.0)
    assert "CollisionFreeSpeedModelState" in str(excinfo.value)


def test_unmapped_model_still_reads_none_and_writes_false():
    agent = SimpleNamespace(id=1, model=object())
    assert get_agent_desired_speed(agent) is None
    assert set_agent_desired_speed(agent, 1.0) is False
