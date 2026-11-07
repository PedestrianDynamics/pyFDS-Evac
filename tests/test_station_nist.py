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
from shapely.geometry import LineString, Point, Polygon, box
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


def _exempt_front_door(nist, passages):
    """The gap finder samples the boundary and can read the 0.91 m front door
    short; that door is checked along its line instead."""
    return [p for p in passages if not nist._is_front_door(p[3])]


def test_no_walkable_opening_is_under_0_90_m_apart_from_the_front_door(nist, deck):
    """The clearance floor: measured on the final floor, not assumed from the cut."""
    _, walkable = deck
    narrow = _exempt_front_door(nist, nist.find_passages(walkable, nist.CLEAR_CHECK))
    assert [(round(p[3].x, 2), round(p[3].y, 2), round(p[0], 3)) for p in narrow] == []
    assert nist.front_door_width(walkable) == pytest.approx(0.91, abs=0.01)


def test_the_default_extraction_is_the_committed_geometry(nist):
    """Acceptance 8, geometry side: ``--ignore-layer`` is opt-in."""
    plain, *_ = nist.EX.extract(
        nist.NIST / "Station210_clean.fds", 0.1, 1.8, 0.05, 0.25
    )
    assert plain.wkt + "\n" == (nist.NIST / "geometry.wkt").read_text()
    ignored = nist.extracted_floor()
    assert ignored.area > plain.area  # baseboards and toe kicks no longer narrow it


def test_trim_framed_openings_are_doors_and_baseboards_do_not_narrow_them(nist):
    floor = nist.regularise(nist.extracted_floor())
    rows = nist.classify_gaps(floor)
    trim = [r for r in rows if r["basis"] == "trim"]
    assert sorted((round(r["x"]), round(r["y"])) for r in trim) == [
        (-6, -7),
        (-3, 2),
        (2, -13),
    ]
    assert all(r["class"] == "door" and r["final"] == 0.90 for r in trim)
    classes = [r["class"] for r in rows]
    assert (classes.count("door"), classes.count("sealed")) == (12, 5)
    assert classes.count("fixture") == 6  # settled by apply_gap_table


def test_every_sealed_fixture_is_not_the_only_access_to_floor_in_use(nist, built):
    """A fixture passage under 0.9 m is sealed unless it is the only access."""
    _, walkable, info = built
    rows = info["rows"]
    fixtures = [r for r in rows if r["basis"] in ("fixture", "only access")]
    assert fixtures
    assert all(r["final"] == 0.90 for r in fixtures if r["class"] == "fixture")
    assert all(r["final"] == 0.0 for r in fixtures if r["class"] == "sealed")
    assert nist.trapped_pockets(walkable) is None


def test_no_agent_is_placed_in_a_bar_service_well(nist, deck):
    config, walkable = deck
    for well in nist.SERVICE_WELLS:
        for name, poly in _areas(config).items():
            inside = poly.intersection(walkable).intersection(well)
            assert inside.area < 1e-6, name
    assert not walkable.contains(Point(3.3, -2.7))  # rear-bar well


def test_sealing_a_slit_that_cuts_off_floor_in_use_stops_the_build(nist, monkeypatch):
    """Two rooms joined only by a 0.40 m passage: sealing it would drop a room."""
    west, east = box(0, 0, 4, 2), box(4.6, 0, 8.6, 2)
    walkable = unary_union([west, east, box(4, 0.8, 4.6, 1.2)])
    monkeypatch.setattr(nist, "_used_floor", lambda: unary_union([west, east]))
    row = {"x": 4.3, "y": 1.0, "class": "sealed"}
    with pytest.raises(SystemExit, match="cuts off floor in use"):
        nist.apply_gap_table(walkable, [row])


def test_regularising_that_drops_floor_in_use_stops_the_build(nist, monkeypatch):
    """Two rooms behind a 0.2 m wall, joined by a 2 cm sliver: regularising keeps
    only one of them."""
    west, east = box(0, 0, 4, 2), box(4.2, 0, 8.2, 2)
    walkable = unary_union([west, east, box(4, 0.99, 4.2, 1.01)])
    monkeypatch.setattr(nist, "_used_floor", lambda: unary_union([west, east]))
    with pytest.raises(SystemExit, match="cuts off floor in use"):
        nist.regularise(walkable)


def test_a_recorded_cut_off_point_does_not_exempt_a_larger_part(nist, monkeypatch):
    """The main-bar well point inside a 25 m2 lost part is not an exemption."""
    (x, y), _ = next(iter(nist.CUT_OFF.items()))
    room = box(x - 2.5, y - 2.5, x + 2.5, y + 2.5)
    kept = box(x + 3.1, y - 2.5, x + 13.1, y + 2.5)
    monkeypatch.setattr(nist, "_used_floor", lambda: room)
    with pytest.raises(SystemExit, match="cuts off floor in use"):
        nist._check_cut_off(unary_union([room, kept]), kept)
