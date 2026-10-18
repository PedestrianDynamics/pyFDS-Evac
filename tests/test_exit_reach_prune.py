"""A point far from an exit polygon is rejected without a shapely Point, and no decision changes (#429)."""

import math

import numpy as np
import pytest
from shapely.geometry import Polygon

from pyfds_evac.core import direct_steering_runtime as dsr
from pyfds_evac.core.direct_steering_runtime import (
    EXIT_REACH_TOLERANCE_M,
    distance_to_polygon,
    reached_stage,
)

TOL = EXIT_REACH_TOLERANCE_M
POLYGONS = {
    "unit": Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]),
    "thin_door": Polygon([(2.0, 0.0), (2.1, 0.0), (2.1, 1.2), (2.0, 1.2)]),
    "l_shape": Polygon([(0, 0), (2, 0), (2, 1), (1, 1), (1, 2), (0, 2)]),
    "triangle": Polygon([(0, 0), (2, 0), (0, 2)]),
    "ring": Polygon(
        [(0, 0), (4, 0), (4, 4), (0, 4)], holes=[[(1, 1), (3, 1), (3, 3), (1, 3)]]
    ),
}


def _old_reached_stage(x, y, target, stage_cfg, agent_radius):
    """``reached_stage`` as it was before #429: the exact distance for every exit test."""
    stage_cfg = stage_cfg or {}
    polygon = stage_cfg.get("polygon")
    stage_type = stage_cfg.get("stage_type", "checkpoint")
    if stage_type == "exit" and polygon is not None:
        return distance_to_polygon(x, y, polygon) <= TOL
    if target is not None:
        reach_dist = float(agent_radius) + dsr.TARGET_REACH_MARGIN_M
        if math.hypot(x - float(target[0]), y - float(target[1])) <= reach_dist:
            return True
    return stage_type == "checkpoint" and dsr.is_inside_polygon(x, y, polygon)


def _probe_points(polygon):
    """Points around, on and just outside the polygon, on the tolerance and one ULP either side."""
    minx, miny, maxx, maxy = polygon.bounds
    xs = np.linspace(minx - 1.0, maxx + 1.0, 41)
    ys = np.linspace(miny - 1.0, maxy + 1.0, 41)
    points = [(x, y) for x in xs for y in ys]
    for edge in (maxx + TOL, minx - TOL):
        for x in (edge, np.nextafter(edge, -np.inf), np.nextafter(edge, np.inf)):
            points += [(x, (miny + maxy) / 2), (x, miny), (x, maxy)]
    for edge in (maxy + TOL, miny - TOL):
        for y in (edge, np.nextafter(edge, -np.inf), np.nextafter(edge, np.inf)):
            points += [((minx + maxx) / 2, y), (minx, y), (maxx, y)]
    corner = TOL / math.sqrt(2.0)
    points += [(maxx + corner, maxy + corner), (minx - corner, miny - corner)]
    return [(float(x), float(y)) for x, y in points]


@pytest.mark.parametrize("name", sorted(POLYGONS))
def test_exit_decision_equals_the_exact_distance(name):
    polygon = POLYGONS[name]
    cfg = {"stage_type": "exit", "polygon": polygon}
    for x, y in _probe_points(polygon):
        assert reached_stage(x, y, None, cfg, 0.2) == _old_reached_stage(
            x, y, None, cfg, 0.2
        ), (x, y)


def test_far_point_builds_no_shapely_point(monkeypatch):
    cfg = {"stage_type": "exit", "polygon": POLYGONS["unit"]}

    def refuse(*_args):
        raise AssertionError("the exact distance ran")

    monkeypatch.setattr(dsr, "distance_to_polygon", refuse)
    assert reached_stage(5.0, 5.0, (9.0, 9.0), cfg, 0.2) is False
    assert reached_stage(1.0 + 2 * TOL, 0.5, None, cfg, 0.2) is False


def test_near_point_takes_the_exact_distance(monkeypatch):
    cfg = {"stage_type": "exit", "polygon": POLYGONS["unit"]}
    calls = []
    real = dsr.distance_to_polygon
    monkeypatch.setattr(
        dsr, "distance_to_polygon", lambda *a: calls.append(a) or real(*a)
    )
    assert reached_stage(1.0 + 0.5 * TOL, 0.5, None, cfg, 0.2) is True
    assert reached_stage(0.5, 0.5, None, cfg, 0.2) is True
    assert len(calls) == 2


def test_the_bounds_corner_is_not_the_polygon():
    """A point near the bounds corner of an L shape is within the bounds gap but far from the polygon."""
    polygon = POLYGONS["l_shape"]
    cfg = {"stage_type": "exit", "polygon": polygon}
    assert distance_to_polygon(1.9, 1.9, polygon) > TOL
    assert reached_stage(1.9, 1.9, None, cfg, 0.2) is False


@pytest.mark.parametrize("bad", [object(), "polygon", 7])
def test_a_polygon_without_bounds_is_not_reached(bad):
    cfg = {"stage_type": "exit", "polygon": bad}
    assert reached_stage(0.5, 0.5, None, cfg, 0.2) is False
    assert reached_stage(0.5, 0.5, None, cfg, 0.2) == _old_reached_stage(
        0.5, 0.5, None, cfg, 0.2
    )


@pytest.mark.parametrize(
    "point", [(float("nan"), 0.5), (0.5, float("nan")), ("a", 0.5)]
)
def test_a_bad_point_is_not_reached(point):
    cfg = {"stage_type": "exit", "polygon": POLYGONS["unit"]}
    assert reached_stage(*point, None, cfg, 0.2) is False
    assert reached_stage(*point, None, cfg, 0.2) == _old_reached_stage(
        *point, None, cfg, 0.2
    )


def test_other_stages_are_unchanged():
    polygon = POLYGONS["unit"]
    checkpoint = {"stage_type": "checkpoint", "polygon": polygon}
    zone = {"stage_type": "zone", "polygon": polygon}
    no_polygon_exit = {"stage_type": "exit"}
    for cfg in (checkpoint, zone, no_polygon_exit, None):
        for x, y in _probe_points(polygon)[::37]:
            for target in (None, (0.5, 0.5), (9.0, 9.0)):
                assert reached_stage(x, y, target, cfg, 0.2) == _old_reached_stage(
                    x, y, target, cfg, 0.2
                )
