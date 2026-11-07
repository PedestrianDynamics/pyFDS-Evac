"""Acceptance checks of ``assets/station_nist`` (#375).

Station-derived geometry (provenance unverified, #377). The deck puts the Fahy
Table 2 areas on the NIST-derived walkable area. These tests pin what the build
script claims: it regenerates the files on disk, every area is one polygon
inside the walkable area with room for its agents, every area reaches all four
exits, the front interior door is 0.91 m, and ``station_fahy`` is unchanged.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import jupedsim as jps
import pedpy
import pytest
from shapely import wkt
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
DECK = ROOT / "assets" / "station_nist"
FAHY = ROOT / "assets" / "station_fahy"
FRONT_EXIT = "jps-exits_0"
INTERIOR_DOOR_Y = -14.36
PER_AGENT = 2.5 * 3.141592653589793 * 0.20**2  # areas.capacity_report, r = 0.20


def _load(name: str, path: Path):
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def nist():
    return _load("station_nist_build", DECK / "build_scenario.py")


@pytest.fixture(scope="module")
def built(nist):
    return nist.build()


@pytest.fixture(scope="module")
def deck():
    config = json.loads((DECK / "config.json").read_text())
    walkable = wkt.loads((DECK / "geometry.wkt").read_text())
    return config, walkable


def test_the_files_are_what_the_build_script_writes(built, deck):
    config, walkable, _ = built
    assert json.loads(json.dumps(config)) == deck[0]
    assert walkable.wkt + "\n" == (DECK / "geometry.wkt").read_text()


def test_station_fahy_is_what_its_build_script_writes(nist):
    """Acceptance 8: the Fahy deck did not move when this deck was added."""
    config, walkable = nist.FB.build()
    assert json.loads(json.dumps(config)) == json.loads(
        (FAHY / "config.json").read_text()
    )
    assert walkable.wkt + "\n" == (FAHY / "geometry.wkt").read_text()


def _areas(config):
    out: dict[str, Polygon] = {}
    for dist in config["distributions"].values():
        out[dist["parameters"]["fahy_row"]] = Polygon(dist["coordinates"])
    return out


def test_every_area_is_inside_the_walkable_area_and_apart_from_the_others(deck):
    config, walkable = deck
    areas = _areas(config)
    assert len(areas) == 12
    holes = unary_union([Polygon(r) for r in walkable.interiors]).buffer(1e-3)
    for name, poly in areas.items():
        assert poly.is_valid, name
        # the config keeps the outer ring; the engine clips obstacles at spawn
        stray = poly.difference(walkable.buffer(1e-3)).difference(holes)
        assert stray.area < 1e-6, name
    names = list(areas)
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            assert areas[a].intersection(areas[b]).area < 1e-6, (a, b)


def test_every_area_holds_its_agents(deck):
    config, walkable = deck
    counts: dict[str, int] = {}
    for dist in config["distributions"].values():
        row = dist["parameters"]["fahy_row"]
        counts[row] = counts.get(row, 0) + dist["parameters"]["number"]
    assert sum(counts.values()) == 333
    for name, poly in _areas(config).items():
        assert poly.intersection(walkable).area >= counts[name] * PER_AGENT, name


def test_the_bartender_well_is_not_floor_an_agent_can_stand_on(nist, built):
    """The 11 m2 behind the main bar counter opens through 0.39 m: sealed."""
    _, walkable, _ = built
    assert not walkable.contains(Point(-1.8, -11.5))
    assert nist.trapped_pockets(walkable) is None


@pytest.fixture(scope="module")
def routing(deck):
    return jps.RoutingEngine(pedpy.WalkableArea(deck[1]).polygon)


def test_every_area_reaches_all_four_exits(deck, routing):
    config, _ = deck
    assert sorted(config["exits"]) == [f"jps-exits_{i}" for i in range(4)]
    targets = {
        k: Polygon(v["coordinates"]).centroid for k, v in config["exits"].items()
    }
    for name, poly in _areas(config).items():
        start = poly.representative_point()
        for exit_id, target in targets.items():
            path = routing.compute_waypoints((start.x, start.y), (target.x, target.y))
            assert path, (name, exit_id)
            assert Point(path[-1]).distance(target) < 1e-6, (name, exit_id)


def test_the_entryway_reaches_the_front_door_through_the_interior_door(deck, routing):
    """The ticket area lies beside the vestibule; its way out is the 0.91 m door."""
    config, _ = deck
    start = _areas(config)["Entryway"].representative_point()
    target = Polygon(config["exits"][FRONT_EXIT]["coordinates"]).centroid
    path = routing.compute_waypoints((start.x, start.y), (target.x, target.y))
    way = LineString([(start.x, start.y), *map(tuple, path)])
    door = LineString([(2.9, INTERIOR_DOOR_Y), (3.95, INTERIOR_DOOR_Y)])
    assert way.intersects(door)


def test_the_front_interior_door_is_0_91_m(deck):
    _, walkable = deck
    cut = LineString([(2.0, INTERIOR_DOOR_Y), (5.0, INTERIOR_DOOR_Y)])
    runs = walkable.intersection(cut)
    opening = [r for r in getattr(runs, "geoms", [runs]) if 2.5 < r.centroid.x < 4.3]
    assert len(opening) == 1
    assert opening[0].length == pytest.approx(0.91, abs=0.01)


def test_the_gap_table_classifies_every_opening_under_0_9_m(nist):
    extracted = wkt.loads((ROOT / "assets/station/geometry.wkt").read_text())
    rows = nist.classify_gaps(extracted)
    assert len(rows) == 24
    assert {r["class"] for r in rows} == {"door", "fixture", "sealed"}
    assert [r["class"] for r in rows].count("sealed") == 5
    assert all(r["extracted"] < 0.46 for r in rows if r["class"] == "sealed")
    front = [r for r in rows if r["final"] == 0.91]
    assert len(front) == 1 and front[0]["leaf"]
    _, rows_after = nist.final_walkable()
    assert rows_after == rows
