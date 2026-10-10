"""Start a scenario from an FDS deck: parser, legacy mapping, modern inference.

Every deck here is a synthetic string written by the test (no file from
examples/FDS-Evac-Guide, which is GPLv3). Expectations are closed form:
axis-aligned rectangles, exact parameter mappings, exact integer shares.
Most imports pass ``walkable_wkt`` so the importer is tested apart from the
walkable provider; the walkable-provider tests derive the area.
"""

from __future__ import annotations

import json
import math
import shutil
from pathlib import Path

import pytest
from shapely import wkt as shapely_wkt
from shapely.geometry import Polygon, box

from pyfds_evac import cli, cli_init
from pyfds_evac.core.fds_import import import_fds_deck
from pyfds_evac.core.fds_import_geometry import largest_remainder
from pyfds_evac.core.premovement_distributions import (
    create_premovement_distribution,
)
from pyfds_evac.core.walkable_provider import WalkableResult

AREA_TOL = 1e-9
ROOM_WKT = "POLYGON((0 0,10 0,10 10,0 10,0 0))"

# A 10 x 10 m room: a fire mesh and one evacuation slab at 0.4-1.6 m
# (z_floor 0), dx 0.1 m. {extra} adds records.
ROOM = """\
&HEAD CHID='room' /
&MESH IJK=100,100,24, XB=0,10,0,10,0,2.4 /
&MESH IJK=100,100,1, XB=0,10,0,10,0.4,1.6, EVACUATION=.TRUE.,
      EVAC_HUMANS=.TRUE., ID='Main' /
&TIME T_END=120 /
{extra}
"""
DOOR = "&EXIT ID='Left', IOR=-1, XB=0,0,4.4,5.6,0.4,1.6 /"


def _deck(tmp_path, text: str, name: str = "deck.fds"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def _room(tmp_path, *records: str, wkt: str = ROOM_WKT, **kwargs):
    path = _deck(tmp_path, ROOM.format(extra="\n".join(records)))
    return import_fds_deck(path, walkable_wkt=wkt, **kwargs)


def _items(result, status=None, group=None):
    return [
        i
        for i in result.report.items
        if (status is None or i.status == status)
        and (group is None or i.group == group)
    ]


def _poly(coordinates) -> Polygon:
    return Polygon(coordinates)


def _same(a, b) -> bool:
    return a.symmetric_difference(b).area <= AREA_TOL


def _params(result, name: str) -> dict:
    return result.raw["distributions"][name]["parameters"]


# --- legacy: exits -----------------------------------------------------------


def test_exit_strip_on_the_room_side(tmp_path):
    result = _room(tmp_path, DOOR)
    strip = _poly(result.raw["exits"]["Left"]["coordinates"])
    assert _same(strip, box(0, 4.4, 0.5, 5.6))


def test_ior_plus_one_puts_the_strip_on_the_left(tmp_path):
    result = _room(tmp_path, "&EXIT ID='R', IOR=1, XB=10,10,4,6,0.4,1.6 /")
    assert _same(_poly(result.raw["exits"]["R"]["coordinates"]), box(9.5, 4, 10, 6))


def test_exit_depth_option(tmp_path):
    result = _room(tmp_path, DOOR, exit_depth=1.0)
    assert _same(_poly(result.raw["exits"]["Left"]["coordinates"]), box(0, 4.4, 1, 5.6))


def test_xyz_becomes_an_omni_sign(tmp_path):
    record = "&EXIT ID='Left', IOR=-1, XYZ=0.2,5,1, XB=0,0,4.4,5.6,0.4,1.6 /"
    result = _room(tmp_path, record)
    assert result.raw["exits"]["Left"]["sign"] == {"x": 0.2, "y": 5.0, "c": 3}


def test_count_only_exit_is_dropped(tmp_path):
    counter = "&EXIT ID='C', IOR=-1, COUNT_ONLY=.TRUE., XB=5,5,4,6,0.4,1.6 /"
    result = _room(tmp_path, DOOR, counter)
    assert list(result.raw["exits"]) == ["Left"]
    assert any(i.id == "C" for i in _items(result, "D", "EXIT"))


def test_exit_schedule_and_warning(tmp_path):
    record = "&EXIT ID='E', IOR=-1, TIME_OPEN=5, TIME_CLOSE=60, XB=0,0,4,6,0.4,1.6 /"
    result = _room(tmp_path, record)
    exit_ = result.raw["exits"]["E"]
    assert (exit_["open_from_s"], exit_["closed_after_s"]) == (5, 60)
    [item] = [i for i in _items(result, "A", "EXIT") if "schedule" in i.message]
    assert item.level == "warning" and "LOCKED_WHEN_CLOSED" in item.message


def test_door_off_the_floor_is_an_exit(tmp_path):
    door = "&DOOR ID='D', IOR=1, TO_NODE='Stair', XB=10,10,4,6,0.4,1.6 /"
    stair = "&CORR ID='Stair' /"
    result = _room(tmp_path, door, stair)
    assert _same(_poly(result.raw["exits"]["D"]["coordinates"]), box(9.5, 4, 10, 6))
    assert result.report.exits[0]["role"] == "door"
    assert any("counted as evacuated" in i.message for i in _items(result, "A", "DOOR"))


def test_door_to_an_entry_on_the_same_floor_is_dropped(tmp_path):
    door = "&DOOR ID='D', IOR=1, TO_NODE='In', XB=10,10,4,6,0.4,1.6 /"
    entr = "&ENTR ID='In', IOR=1, MAX_FLOW=0, XB=0,0,4,6,0.4,1.6 /"
    result = _room(tmp_path, DOOR, door, entr)
    assert list(result.raw["exits"]) == ["Left"]
    assert any("teleport" in i.message for i in _items(result, "D", "DOOR"))


# --- legacy: spawn areas -----------------------------------------------------


EVAC = "&EVAC ID='g', XB=1,9,1,9,1,1, NUMBER_INITIAL_PERSONS=25 {extra} /"


def test_evac_number(tmp_path):
    result = _room(tmp_path, DOOR, EVAC.format(extra=""))
    assert _params(result, "g")["number"] == 25
    assert _same(
        _poly(result.raw["distributions"]["g"]["coordinates"]), box(1, 1, 9, 9)
    )


def test_evho_inside_splits_and_keeps_the_total(tmp_path):
    result = _room(tmp_path, DOOR, EVAC.format(extra=""), "&EVHO XB=2,5,2,5,1,1 /")
    dists = result.raw["distributions"]
    pieces = [_poly(d["coordinates"]) for d in dists.values()]
    assert len(pieces) == 2
    assert all(not p.interiors for p in pieces)
    assert sum(p.area for p in pieces) == pytest.approx(64 - 9, abs=AREA_TOL)
    assert sum(d["parameters"]["number"] for d in dists.values()) == 25
    assert all(p.intersection(box(2, 2, 5, 5)).area <= AREA_TOL for p in pieces)


def test_evho_for_another_group_does_not_apply(tmp_path):
    hole = "&EVHO XB=2,5,2,5,1,1, EVAC_ID='other' /"
    result = _room(tmp_path, DOOR, EVAC.format(extra=""), hole)
    assert list(result.raw["distributions"]) == ["g"]


def test_largest_remainder_is_exact():
    assert largest_remainder(25, [27.5, 27.5]) == [13, 12]
    assert largest_remainder(10, [1, 1, 1]) == [4, 3, 3]
    assert largest_remainder(7, [0.5, 0.25, 0.25]) == [3, 2, 2]  # 3.5, 1.75, 1.75
    assert sum(largest_remainder(101, [3.3, 2.2, 1.1, 0.7])) == 101


def test_pers_adult_speed_is_gaussian_with_the_uniform_moments(tmp_path):
    pers = "&PERS ID='A', DEFAULT_PROPERTIES='Adult' /"
    result = _room(tmp_path, DOOR, pers, EVAC.format(extra=", PERS_ID='A'"))
    params = _params(result, "g")
    assert params["v0"] == 1.25
    assert params["v0_distribution"] == "gaussian"
    assert params["v0_std"] == pytest.approx(0.30 / math.sqrt(3), abs=1e-9)
    assert "radius" not in params
    assert any("three circles" in i.message for i in _items(result, "A", "PERS"))


def test_pers_velocity_dist_overrides_default_properties(tmp_path):
    pers = "&PERS ID='A', DEFAULT_PROPERTIES='Adult', VELOCITY_DIST=0, VEL_MEAN=1.1 /"
    result = _room(tmp_path, DOOR, pers, EVAC.format(extra=", PERS_ID='A'"))
    params = _params(result, "g")
    assert (params["v0"], params["v0_distribution"]) == (1.1, "constant")


def test_missing_pers_is_an_error_naming_both_ids(tmp_path):
    with pytest.raises(ValueError, match="'g'.*'Nobody'"):
        _room(tmp_path, DOOR, EVAC.format(extra=", PERS_ID='Nobody'"))


def _delay(tmp_path, keys: str) -> dict:
    pers = f"&PERS ID='P', {keys} /"
    result = _room(tmp_path, DOOR, pers, EVAC.format(extra=", PERS_ID='P'"))
    params = _params(result, "g")
    return {k: v for k, v in params.items() if k.startswith(("premovement", "use_pre"))}


@pytest.mark.parametrize(
    ("keys", "dist", "a", "b", "offset"),
    [
        ("DET_MEAN=2, PRE_MEAN=3", "constant", 5.0, None, None),
        (
            "DET_MEAN=2, PRE_EVAC_DIST=1, PRE_LOW=5, PRE_HIGH=15",
            "uniform",
            7,
            17,
            None,
        ),
        ("PRE_EVAC_DIST=3, PRE_PARA=2, PRE_PARA2=3", "gamma", 2, 3, None),
        ("PRE_EVAC_DIST=8, PRE_PARA=2, PRE_PARA2=0.1", "weibull", 10, 2, None),
        # I1: offset = DET low + PRE low = 10 s; gamma on the rest, mean 10 s,
        # variance 200/12 s2 -> k = 6, theta = 5/3 (total mean 20 s kept).
        (
            "DET_EVAC_DIST=1, DET_LOW=5, DET_HIGH=15, "
            "PRE_EVAC_DIST=1, PRE_LOW=5, PRE_HIGH=15",
            "gamma",
            6,
            round(5 / 3, 9),
            10,
        ),
        # I1: 5 s + gamma(2, 3) is exact.
        ("DET_MEAN=5, PRE_EVAC_DIST=3, PRE_PARA=2, PRE_PARA2=3", "gamma", 2, 3, 5),
        (
            "PRE_EVAC_DIST=7, PRE_MEAN=10, PRE_LOW=4, PRE_HIGH=16",
            "constant",
            10,
            None,
            None,
        ),
    ],
    ids=[
        "const+const",
        "const+uniform",
        "0+gamma",
        "0+weibull",
        "uniform+uniform",
        "const+gamma",
        "triangular",
    ],
)
def test_detection_plus_premovement(tmp_path, keys, dist, a, b, offset):
    delay = _delay(tmp_path, keys)
    assert delay.get("premovement_offset_s") == offset
    assert delay["use_premovement"] is True
    assert delay["premovement_distribution"] == dist
    assert delay["premovement_param_a"] == pytest.approx(a, abs=1e-9)
    assert delay.get("premovement_param_b") == (None if b is None else pytest.approx(b))


def test_no_delay_keys_leave_the_loader_default(tmp_path):
    assert _delay(tmp_path, "VELOCITY_DIST=0, VEL_MEAN=1.2") == {}


def test_weibull_mapping_has_the_fds_evac_mean():
    """FDS+Evac Weibull (alpha shape, lambda rate): mean Gamma(1+1/alpha)/lambda."""
    alpha, lam = 2.0, 0.1
    sampler = create_premovement_distribution(
        "weibull", {"a": 1 / lam, "b": alpha}, seed=1
    )
    expected = math.gamma(1 + 1 / alpha) / lam
    assert sampler.sample(200_000).mean() == pytest.approx(expected, rel=0.01)


@pytest.mark.parametrize(
    ("extra", "expected"),
    [
        ("", {"familiarity": "discovery"}),
        (", KNOWN_DOOR_NAMES='Left'", {"familiarity": "discovery", "entrance": "Left"}),
        (", KNOWN_DOOR_NAMES='Left','R'", {"familiarity": "full"}),
        (
            ", KNOWN_DOOR_NAMES='Left','R', KNOWN_DOOR_PROBS=0.5,1.0",
            {"familiarity": "discovery", "entrance": "R"},
        ),
    ],
    ids=["none", "one", "all", "partial"],
)
def test_known_doors(tmp_path, extra, expected):
    right = "&EXIT ID='R', IOR=1, XB=10,10,4,6,0.4,1.6 /"
    result = _room(tmp_path, DOOR, right, EVAC.format(extra=extra))
    params = _params(result, "g")
    got = {k: params[k] for k in ("familiarity", "entrance") if k in params}
    assert got == expected


def test_known_door_on_the_exit(tmp_path):
    door = "&EXIT ID='Left', IOR=-1, KNOWN_DOOR=.TRUE., XB=0,0,4.4,5.6,0.4,1.6 /"
    result = _room(tmp_path, door, EVAC.format(extra=""))
    assert _params(result, "g")["familiarity"] == "full"


def test_entr_becomes_flow_spawning(tmp_path):
    entr = (
        "&ENTR ID='In', IOR=1, MAX_FLOW=0.5, TIME_START=10, TIME_STOP=50, "
        "XB=0,0,2,4,0.4,1.6 /"
    )
    result = _room(tmp_path, DOOR, entr)
    dist = result.raw["distributions"]["In"]
    params = dist["parameters"]
    assert params["number"] == 20
    assert params["use_flow_spawning"] is True
    assert (params["flow_start_time"], params["flow_end_time"]) == (10, 50)
    assert _same(_poly(dist["coordinates"]), box(0, 2, 0.5, 4))


def test_entr_without_stop_ends_at_t_end(tmp_path):
    entr = "&ENTR ID='In', IOR=1, MAX_FLOW=0.5, XB=0,0,2,4,0.4,1.6 /"
    params = _params(_room(tmp_path, DOOR, entr), "In")
    assert (params["flow_start_time"], params["flow_end_time"]) == (0, 120)
    assert params["number"] == 60


# --- legacy: floors and smoke height -----------------------------------------


TWO_FLOORS = """\
&HEAD CHID='two' /
&MESH IJK=100,100,24, XB=0,10,0,10,0,8 /
&MESH IJK=100,100,1, XB=0,10,0,10,1.0,1.2, EVACUATION=.TRUE., EVAC_HUMANS=.TRUE.,
      ID='Ground' /
&MESH IJK=100,100,1, XB=0,10,0,10,5.0,5.2, EVACUATION=.TRUE., EVAC_HUMANS=.TRUE.,
      ID='First' /
&PERS ID='P', HUMAN_SMOKE_HEIGHT=1.6 /
&EXIT ID='G', IOR=-1, XB=0,0,4,6,1.0,1.2 /
&EXIT ID='F', IOR=-1, XB=0,0,4,6,5.0,5.2 /
&EVAC ID='g', XB=1,9,1,9,1.1,1.1, NUMBER_INITIAL_PERSONS=10 /
&EVAC ID='f', XB=1,9,1,9,5.1,5.1, NUMBER_INITIAL_PERSONS=30 /
"""


def test_lowest_floor_by_default_and_the_other_reported(tmp_path):
    result = import_fds_deck(_deck(tmp_path, TWO_FLOORS), walkable_wkt=ROOM_WKT)
    assert result.report.floor["id"] == "Ground"
    assert result.report.floor["z_floor"] == pytest.approx(0.1)
    assert list(result.raw["exits"]) == ["G"]
    assert list(result.raw["distributions"]) == ["g"]
    [other] = result.report.floors_not_imported
    assert (other["id"], other["agents"], other["exit"]) == ("First", 30, 1)
    params = result.raw["config"]["simulation_settings"]["simulationParams"]
    assert params["smoke_slice_height"] == pytest.approx(1.7)


def test_floor_option_picks_the_upper_floor(tmp_path):
    path = _deck(tmp_path, TWO_FLOORS)
    result = import_fds_deck(path, walkable_wkt=ROOM_WKT, floor="First")
    assert list(result.raw["exits"]) == ["F"]
    params = result.raw["config"]["simulation_settings"]["simulationParams"]
    assert params["smoke_slice_height"] == pytest.approx(5.7)
    assert params["max_simulation_time"] == 300.0


def test_unknown_floor_is_an_error(tmp_path):
    with pytest.raises(ValueError, match="--floor 'Roof'.*Ground"):
        import_fds_deck(
            _deck(tmp_path, TWO_FLOORS), walkable_wkt=ROOM_WKT, floor="Roof"
        )


# --- modern decks --------------------------------------------------------------


# Two meshes side by side (x 0-10 and 10-20), y 0-10, z 0-3. {vents} adds vents.
MODERN = """\
&HEAD CHID='plain' /
&MESH IJK=50,50,15, XB=0,10,0,10,0,3 /
&MESH IJK=50,50,15, XB=10,20,0,10,0,3 /
{vents}
"""
HALL = "POLYGON((0 0,20 0,20 10,0 10,0 0))"


def _modern(tmp_path, *vents: str, wkt: str = HALL, **kwargs):
    path = _deck(tmp_path, MODERN.format(vents="\n".join(vents)))
    return import_fds_deck(path, walkable_wkt=wkt, **kwargs)


def test_open_vent_on_the_exterior_is_an_exit(tmp_path):
    result = _modern(tmp_path, "&VENT XB=0,0,4,6,0,2, SURF_ID='OPEN' /")
    [(name, exit_)] = result.raw["exits"].items()
    assert name == "vent_1"
    assert _same(_poly(exit_["coordinates"]), box(0, 4, 0.5, 6))
    assert exit_["sign"] == {"x": 0.25, "y": 5.0, "c": 3}
    assert result.report.runnable


@pytest.mark.parametrize(
    "vent",
    [
        "&VENT XB=10,10,4,6,0,2, SURF_ID='OPEN' /",
        "&VENT XB=2,4,2,4,3,3, SURF_ID='OPEN' /",
        "&VENT XB=20,20,4,6,2.5,3, SURF_ID='OPEN' /",
        "&VENT XB=20,20,4,6,0,2, SURF_ID='INERT' /",
    ],
    ids=["mesh-interface", "horizontal", "above-band", "not-open"],
)
def test_vents_that_are_not_exits(tmp_path, vent):
    result = _modern(tmp_path, vent)
    assert result.raw["exits"] == {}
    assert not result.report.runnable


def test_mesh_boundary_vent(tmp_path):
    result = _modern(tmp_path, "&VENT MB='XMAX', SURF_ID='OPEN' /")
    exits = [_poly(e["coordinates"]) for e in result.raw["exits"].values()]
    assert len(exits) == 1
    assert _same(exits[0], box(19.5, 0, 20, 10))
    assert any("wide opening" in i.message for i in _items(result, "A", "VENT"))


def test_no_opening_is_written_but_not_runnable(tmp_path):
    out = tmp_path / "out"
    path = _deck(tmp_path, MODERN.format(vents=""))
    status = cli_init.main([str(path), "-o", str(out), "--walkable", _wkt(tmp_path)])
    assert status == cli_init.EXIT_NOT_RUNNABLE
    report = json.loads((out / "import_report.json").read_text())
    assert report["runnable"] is False
    assert json.loads((out / "config.json").read_text())["exits"] == {}


def _wkt(tmp_path, text: str = HALL) -> str:
    path = tmp_path / "walk.wkt"
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_user_exit_is_added(tmp_path):
    result = _modern(tmp_path, exits=[(20, 2, 20, 3, 1)])
    exit_ = result.raw["exits"]["user_exit_1"]
    assert _same(_poly(exit_["coordinates"]), box(19.5, 2, 20, 3))


OPEN_LEFT = "&VENT XB=0,0,4,6,0,2, SURF_ID='OPEN' /"


def test_evho_on_a_plain_deck_is_a_walkable_hole(tmp_path):
    """#688: an &EVHO keeps the deck plain and cuts 2 x 2 m out of 20 x 10 m."""
    evho = "&EVHO ID='hole', XB=3,5,3,5,0,0 /"
    result = _modern(tmp_path, OPEN_LEFT, evho, wkt=None)
    assert result.report.kind == "modern"
    assert list(result.raw["exits"]) == ["vent_1"]
    assert result.report.walkable["area_m2"] == pytest.approx(196.0)
    assert result.report.walkable["holes"] == 1
    [item] = _items(result, "A", "EVHO")
    assert (item.id, item.level) == ("hole", "info")


def test_evho_on_a_plain_deck_is_not_cut_from_a_given_walkable(tmp_path):
    result = _modern(tmp_path, OPEN_LEFT, "&EVHO XB=3,5,3,5,0,0 /")
    assert result.report.walkable["area_m2"] == pytest.approx(200.0)
    [item] = _items(result, "D", "EVHO")
    assert "--walkable" in item.message


@pytest.mark.parametrize(
    ("evho", "reason"),
    [
        ("&EVHO XB=3,5,3,5,2.5,3 /", "not on the imported floor"),
        ("&EVHO XB=30,32,3,5,0,0 /", "outside the walkable area"),
    ],
)
def test_evho_on_a_plain_deck_off_the_floor_is_ignored(tmp_path, evho, reason):
    result = _modern(tmp_path, OPEN_LEFT, evho, wkt=None)
    assert result.report.walkable["area_m2"] == pytest.approx(200.0)
    assert result.report.walkable["holes"] == 0
    [item] = _items(result, "D", "EVHO")
    assert item.message == f"ignored: {reason}"
    assert not _items(result, "A", "EVHO")


# A ground floor 'room' (z 0-3) under 'upstairs' (z 3-6), both 10 x 10 m.
STOREYS = """\
&HEAD CHID='storeys' /
&MESH ID='room', IJK=50,50,15, XB=0,10,0,10,0,3 /
&MESH ID='upstairs', IJK=50,50,15, XB=0,10,0,10,3,6 /
&VENT XB=0,0,4,6,0,2, SURF_ID='OPEN' /
&EVHO ID='up', MESH_ID='upstairs', XB=3,5,3,5,0,5 /
&EVHO ID='down', MESH_ID='room', XB=6,7,6,7,0,0 /
"""


def test_evho_on_a_plain_deck_honours_mesh_id(tmp_path):
    """Only the &EVHO naming a mesh of the floor cuts it: 100 - 1 m2."""
    result = import_fds_deck(_deck(tmp_path, STOREYS))
    assert result.report.walkable["area_m2"] == pytest.approx(99.0)
    [skipped] = _items(result, "D", "EVHO")
    assert skipped.id == "up"
    assert "MESH_ID 'upstairs'" in skipped.message
    [applied] = _items(result, "A", "EVHO")
    assert applied.id == "down"


def test_evacuation_namelist_on_a_plain_deck_is_ignored(tmp_path):
    result = _modern(tmp_path, OPEN_LEFT, "&EXIT ID='E', IOR=1, XB=20,20,4,6,0,2 /")
    assert result.report.kind == "modern"
    assert list(result.raw["exits"]) == ["vent_1"]
    [item] = _items(result, "D", "EXIT")
    assert item.level == "warning"
    assert "no EVACUATION=.TRUE. mesh" in item.message


def test_spawn_is_the_component_minus_the_strips(tmp_path):
    result = _modern(tmp_path, "&VENT XB=0,0,4,6,0,2, SURF_ID='OPEN' /")
    [spawn] = result.raw["distributions"].values()
    assert _poly(spawn["coordinates"]).area == pytest.approx(200 - 1.0, abs=AREA_TOL)
    assert spawn["parameters"] == {"number": 100}
    assert result.report.distributions[0]["placeholder"] is True
    assert any("placeholder" in i.message for i in _items(result, "A", "spawn"))


def test_agents_shared_by_area_and_a_component_without_exit(tmp_path):
    wkt = (
        "MULTIPOLYGON(((0 0,6 0,6 10,0 10,0 0)),((7 0,9 0,9 10,7 10,7 0)),"
        "((14 0,20 0,20 10,14 10,14 0)))"
    )
    vents = (
        "&VENT XB=0,0,4,6,0,2, SURF_ID='OPEN' /",
        "&VENT XB=20,20,4,6,0,2, SURF_ID='OPEN' /",
    )
    result = _modern(tmp_path, *vents, wkt=wkt, agents=11)
    numbers = sorted(
        d["parameters"]["number"] for d in result.raw["distributions"].values()
    )
    assert numbers == [5, 6]  # equal areas 59: quotas 5.5 each, tie to the first
    assert any("has no exit" in i.message for i in _items(result, "A", "spawn"))


def test_density_above_the_packing_limit_is_flagged(tmp_path):
    result = _modern(tmp_path, "&VENT XB=0,0,4,6,0,2, SURF_ID='OPEN' /", agents=1000)
    assert any("packing limit" in i.message for i in _items(result, "A", "spawn"))


# --- sanity checks -------------------------------------------------------------


def test_exit_far_from_the_walkable_area_is_dropped_with_its_distance(tmp_path):
    result = _room(tmp_path, DOOR, wkt="POLYGON((2 0,10 0,10 10,2 10,2 0))")
    assert result.raw["exits"] == {}
    [item] = [i for i in _items(result, "D", "EXIT") if i.level == "error"]
    assert "2.000 m from the walkable area" in item.message


def test_spawn_outside_the_walkable_area_is_dropped(tmp_path):
    evac = "&EVAC ID='out', XB=20,22,1,3,1,1, NUMBER_INITIAL_PERSONS=5 /"
    result = _room(tmp_path, DOOR, evac)
    assert result.raw["distributions"] == {}
    assert any(i.id == "out" for i in _items(result, "D", "EVAC"))


def test_spawn_in_a_component_without_exit_is_flagged(tmp_path):
    wkt = "MULTIPOLYGON(((0 0,4 0,4 10,0 10,0 0)),((6 0,10 0,10 10,6 10,6 0)))"
    evac = "&EVAC ID='east', XB=7,9,1,9,1,1, NUMBER_INITIAL_PERSONS=5 /"
    result = _room(tmp_path, DOOR, evac, wkt=wkt)
    assert any("cannot reach any exit" in i.message for i in _items(result, "A"))


def test_empty_walkable_writes_nothing(tmp_path):
    with pytest.raises(ValueError, match="empty or invalid"):
        _room(tmp_path, DOOR, wkt="POLYGON EMPTY")


def test_every_non_exact_mapping_is_reported(tmp_path):
    pers = "&PERS ID='P', DEFAULT_PROPERTIES='Adult', TDET_SMOKE_DENS=0.1, COLOR_METHOD=4 /"
    result = _room(tmp_path, DOOR, pers, EVAC.format(extra=", PERS_ID='P', GN_MIN=2"))
    dropped = {(i.group, i.message.split()[0]) for i in _items(result, "D")}
    assert {("PERS", "TDET_SMOKE_DENS"), ("EVAC", "GN_MIN")} <= dropped
    assert result.report.counts()["PERS"]["C"] == 1


# --- determinism and CLI -------------------------------------------------------


def test_import_is_byte_identical(tmp_path):
    records = (DOOR, EVAC.format(extra=""), "&EVHO XB=2,5,2,5,1,1 /")
    first = _room(tmp_path, *records).write(tmp_path / "a")
    second = _room(tmp_path, *records).write(tmp_path / "a2")
    for name in ("config.json", "geometry.wkt"):
        assert (first / name).read_bytes() == (second / name).read_bytes()


def test_import_report_written_in_the_fds_frame(tmp_path):
    out = _room(tmp_path, DOOR, EVAC.format(extra="")).write(tmp_path / "o")
    walkable = shapely_wkt.loads((out / "geometry.wkt").read_text())
    assert _same(walkable, box(0, 0, 10, 10))
    assert json.loads((out / "import_report.json").read_text())["runnable"] is True


def test_cli_init_runnable_and_error(tmp_path, capsys, monkeypatch):
    # The printed command names the folder relative to the working directory
    # when that is shorter, so fix the cwd to make the expected text exact.
    monkeypatch.chdir(tmp_path)
    deck = _deck(tmp_path, ROOM.format(extra=DOOR + "\n" + EVAC.format(extra="")))
    walk = _wkt(tmp_path, ROOM_WKT)
    assert (
        cli_init.main([str(deck), "-o", str(tmp_path / "o"), "--walkable", walk]) == 0
    )
    assert "pyfds-evac --scenario o " in capsys.readouterr().out
    bad = _deck(tmp_path, "&CATF OTHER_FILES='x.fds' /", name="bad.fds")
    assert cli_init.main([str(bad), "-o", str(tmp_path / "b")]) == 1
    assert not (tmp_path / "b").exists()


def test_pyfds_evac_dispatches_the_init_subcommand(tmp_path, monkeypatch):
    deck = _deck(tmp_path, MODERN.format(vents=""))
    argv = ["pyfds-evac", "init", str(deck), "-o", str(tmp_path / "o")]
    monkeypatch.setattr("sys.argv", argv + ["--walkable", _wkt(tmp_path)])
    assert cli.main() == cli_init.EXIT_NOT_RUNNABLE


def test_fds_output_next_to_a_modern_deck_goes_into_the_run_command(tmp_path):
    (tmp_path / "plain.smv").write_text("", encoding="utf-8")
    result = _modern(tmp_path, "&VENT XB=0,0,4,6,0,2, SURF_ID='OPEN' /")
    assert (
        result.run_command("out") == f"pyfds-evac --scenario out --fds-dir {tmp_path}"
    )


def test_fds_output_next_to_a_legacy_deck_is_reported_not_used(tmp_path):
    (tmp_path / "room.smv").write_text("", encoding="utf-8")
    result = _room(tmp_path, DOOR)
    rec = result.report.recommendations
    assert rec["fds_output_found"] and rec["fds_dir"] is None
    assert "not verified" in rec["fds_dir_note"]


# --- walkable provider ---------------------------------------------------------


def test_provider_gets_the_floor_obstructions(tmp_path):
    seen = {}

    def provider(deck, floor):
        seen["obst"] = [r.id for r in floor.obstructions]
        seen["band"] = floor.z_band
        return WalkableResult(box(0, 0, 10, 10), ["test provider"], "derived:test")

    obsts = (
        "&OBST ID='both', XB=1,2,1,2,0,2 /",
        "&OBST ID='fire', XB=1,2,1,2,0,2, EVACUATION=.FALSE. /",
        "&OBST ID='evac', XB=1,2,1,2,0,2, EVACUATION=.TRUE. /",
        "&OBST ID='other', XB=1,2,1,2,0,2, MESH_ID='Elsewhere' /",
        "&OBST ID='high', XB=1,2,1,2,2,2.4 /",
    )
    path = _deck(tmp_path, ROOM.format(extra="\n".join((DOOR, *obsts))))
    result = import_fds_deck(path, derive_walkable=provider)
    assert seen == {"obst": ["both", "evac"], "band": (0.4, 1.6)}
    assert result.report.walkable["source"] == "derived:test"


# Two 10 x 10 m rooms side by side (x 0-10 and 10-20), split by a
# zero-thickness wall at x = 10 (widened to 0.1 m); one OPEN vent on x = 0.
# {extra} adds records.
TWO_ROOMS = """\
&HEAD CHID='rooms' /
&MESH IJK=50,50,15, XB=0,20,0,10,0,3 /
&OBST XB=10,10,0,10,0,3 /
&VENT XB=0,0,4,6,0,2, SURF_ID='OPEN' /
{extra}
"""


def _two_rooms(tmp_path, *extra: str, **kwargs):
    path = _deck(tmp_path, TWO_ROOMS.format(extra="\n".join(extra)))
    return import_fds_deck(path, **kwargs)


def test_mesh_edge_is_a_wall_and_the_room_without_exit_is_dropped(tmp_path):
    result = _two_rooms(tmp_path)
    walkable = shapely_wkt.loads(result.walkable_wkt)
    assert _same(walkable, box(0, 0, 9.95, 10))
    assert result.report.walkable["source"] == "derived:deck"
    assert result.report.walkable["kept_by"] == "spawn"
    [dropped] = result.report.walkable["components_dropped"]
    assert dropped["area_m2"] == pytest.approx(99.5)
    assert dropped["bounds"] == [10.05, 0.0, 20.0, 10.0]
    assert any("dropped: no spawn area" in i.message for i in _items(result, "A"))
    assert result.report.runnable


def test_hole_opens_the_wall(tmp_path):
    result = _two_rooms(tmp_path, "&HOLE XB=9.9,10.1,4,6,0,2.5 /")
    walkable = shapely_wkt.loads(result.walkable_wkt)
    assert walkable.area == pytest.approx(200 - 0.1 * 8)
    assert result.report.walkable["components"] == 1
    assert result.report.walkable["kept_by"] == "single"


def test_hole_above_the_walking_band_does_not_open_the_wall(tmp_path):
    result = _two_rooms(tmp_path, "&HOLE XB=9.9,10.1,4,6,2,3 /")
    assert result.report.walkable["area_m2"] == pytest.approx(99.5)


def test_small_obstruction_is_filled_and_a_larger_one_kept(tmp_path):
    result = _two_rooms(
        tmp_path, "&OBST XB=2,2.4,2,2.4,0,3 /", "&OBST XB=5,6,5,6,0,3 /"
    )
    walkable = shapely_wkt.loads(result.walkable_wkt)
    assert walkable.area == pytest.approx(99.5 - 1.0)
    assert result.report.walkable["holes"] == 1


def test_user_exit_keeps_its_room(tmp_path):
    result = _two_rooms(tmp_path, exits=[(20, 2, 20, 3, 1)])
    assert result.report.walkable["area_m2"] == pytest.approx(199.0)
    assert sorted(result.raw["exits"]) == ["user_exit_1", "vent_1"]


def test_without_spawn_or_exit_every_room_is_kept(tmp_path):
    deck = TWO_ROOMS.replace("&VENT XB=0,0,4,6,0,2, SURF_ID='OPEN' /", "")
    result = import_fds_deck(_deck(tmp_path, deck.format(extra="")))
    assert result.report.walkable["area_m2"] == pytest.approx(199.0)
    assert result.report.walkable["kept_by"] == "all"
    assert not result.report.runnable


def test_multi_line_mesh_and_obst_are_read(tmp_path):
    deck = (
        "&HEAD CHID='ml' /\n&MESH IJK=50,50,15,\n      XB=0,20,0,10,0,3 /\n"
        "&OBST\n  XB=10,10,0,10,0,3 /\n"
        "&VENT XB=0,0,4,6,0,2, SURF_ID='OPEN' /\n"
    )
    result = import_fds_deck(_deck(tmp_path, deck))
    assert result.report.walkable["area_m2"] == pytest.approx(99.5)


def test_upper_storey_mesh_is_not_part_of_the_floor(tmp_path):
    """A mesh above the walking band does not join the floor (200 -> 100 m2)."""
    deck = (
        "&HEAD CHID='stack' /\n"
        "&MESH IJK=50,50,15, XB=0,10,0,10,0,3 /\n"
        "&MESH IJK=50,50,15, XB=10,20,0,10,3,6, ID='Upper' /\n"
        "&VENT XB=0,0,4,6,0,2, SURF_ID='OPEN' /\n"
    )
    result = import_fds_deck(_deck(tmp_path, deck))
    assert result.report.walkable["area_m2"] == pytest.approx(100.0)
    assert result.report.floor["meshes"] == [None]
    [item] = [i for i in _items(result, "A", "MESH") if i.id == "Upper"]
    assert "lies outside the walking band" in item.message
    [spawn] = result.raw["distributions"].values()
    assert max(x for x, _ in spawn["coordinates"]) == pytest.approx(10.0)


def test_floor_split_into_stacked_meshes_is_one_floor(tmp_path):
    """Meshes at z 0-1 and 1-3 over one footprint both meet the band."""
    deck = (
        "&HEAD CHID='split' /\n"
        "&MESH IJK=50,50,5, XB=0,10,0,10,0,1 /\n"
        "&MESH IJK=50,50,10, XB=0,10,0,10,1,3 /\n"
        "&VENT XB=0,0,4,6,0,1, SURF_ID='OPEN' /\n"
    )
    result = import_fds_deck(_deck(tmp_path, deck))
    assert result.report.walkable["area_m2"] == pytest.approx(100.0)
    assert len(result.report.floor["meshes"]) == 2
    assert not [i for i in _items(result, "A", "MESH") if "walking band" in i.message]


def test_low_single_mesh_imports(tmp_path):
    """A 1.5 m high mesh only overlaps the 0.1-1.8 m band; it is the floor."""
    deck = (
        "&HEAD CHID='low' /\n"
        "&MESH IJK=50,50,5, XB=0,10,0,10,0,1.5 /\n"
        "&VENT XB=0,0,4,6,0,1.5, SURF_ID='OPEN' /\n"
    )
    result = import_fds_deck(_deck(tmp_path, deck))
    assert result.report.walkable["area_m2"] == pytest.approx(100.0)
    assert result.report.runnable


# An FDS+Evac room split by a thin wall at x = 5 (widened to 4.95..5.05),
# its only exit at x = 0. {extra} adds records.
SPLIT_ROOM = """\
&HEAD CHID='split' /
&MESH IJK=40,40,1, XB=0,10,0,10,0.4,1.6, EVACUATION=.TRUE.,
      EVAC_HUMANS=.TRUE., ID='Main' /
&OBST XB=5,5,0,10,0,2.4 /
&EXIT ID='West', IOR=-1, XB=0,0,4,6,0.4,1.6 /
{extra}
"""


def _split_room(tmp_path, *extra: str, **kwargs):
    path = _deck(tmp_path, SPLIT_ROOM.format(extra="\n".join(extra)))
    return import_fds_deck(path, **kwargs)


def test_evac_rectangle_is_clipped_to_the_kept_walkable_area(tmp_path):
    evac = "&EVAC ID='g', XB=1,5,1,9,1,1, NUMBER_INITIAL_PERSONS=10 /"
    result = _split_room(tmp_path, evac)
    spawn = _poly(result.raw["distributions"]["g"]["coordinates"])
    assert _same(spawn, box(1, 1, 4.95, 9))
    assert result.report.distributions[0]["area_m2"] == pytest.approx(3.95 * 8)


def test_clipped_evac_pieces_share_the_agents_by_area(tmp_path):
    records = (
        "&OBST XB=1,4,4,5,0,2.4 /",
        "&EVAC ID='g', XB=1,4,1,9,1,1, NUMBER_INITIAL_PERSONS=10 /",
    )
    result = _split_room(tmp_path, *records)
    pieces = result.raw["distributions"]
    areas = {k: _poly(v["coordinates"]).area for k, v in pieces.items()}
    assert areas == pytest.approx({"g_1": 12.0, "g_2": 9.0})
    numbers = {k: v["parameters"]["number"] for k, v in pieces.items()}
    assert numbers == {"g_1": 6, "g_2": 4}


def test_spawn_over_capacity_is_not_runnable(tmp_path):
    """#606 B-1: the runtime would refuse 10 agents on 1 m2 (about 3 fit)."""
    evac = "&EVAC ID='g', XB=1,2,1,2,1,1, NUMBER_INITIAL_PERSONS=10 /"
    result = _split_room(tmp_path, evac)
    [reason] = result.report.not_runnable
    assert reason.startswith(
        "spawn area g (1.000 m2) holds about 3 agents of radius 0.2 m, "
        "but 10 are requested"
    )
    assert "NUMBER_INITIAL_PERSONS" in reason
    status = cli_init.main(
        [str(tmp_path / "deck.fds"), "-o", str(tmp_path / "out"), "--no-fds"]
    )
    assert status == cli_init.EXIT_NOT_RUNNABLE


def test_placeholder_over_capacity_names_agents_option(tmp_path):
    result = _two_rooms(tmp_path, agents=1000)
    [reason] = result.report.not_runnable
    assert "(98.500 m2) holds about 391 agents" in reason and "--agents" in reason


def test_capacity_matches_the_runtime_estimate():
    from pyfds_evac.core.fds_import import spawn_capacity
    from pyfds_evac.core.simulation_init import _estimate_max_capacity

    for area, radius in [
        (1.0, 0.2),
        (25.0, 0.2),
        (15.0, 0.2),
        (3.0, 0.05),
        (99.5, 0.3),
    ]:
        assert spawn_capacity(area, radius) == _estimate_max_capacity(
            box(0, 0, area, 1), radius
        )


def test_repo_t_junction_walkable_is_derived(tmp_path):
    """#505: the derived area equals the asset's hand-written WKT."""
    root = Path(__file__).resolve().parents[1] / "assets" / "t_junction"
    drawn = shapely_wkt.loads((root / "geometry.wkt").read_text(encoding="utf-8"))
    result = import_fds_deck(root / "t_junction.fds", agents=40)
    derived = shapely_wkt.loads(result.walkable_wkt)
    assert derived.area == pytest.approx(150.0)
    assert _same(derived, drawn)
    assert len(result.raw["exits"]) == 2
    assert result.report.runnable


# #672: a 10 x 10 m evacuation mesh split by a zero-thickness wall at x = 5
# (widened to 0.1 m), an &EXIT on the mesh edge at x = 10 and a group at
# x < 5. {extra} adds records.
EVAC_MESH = """\
&HEAD CHID='evac10' /
&MESH IJK=40,40,1, XB=0,10,0,10,0.4,1.6, EVACUATION=.TRUE.,
      EVAC_HUMANS=.TRUE., ID='Main' /
&OBST XB=5,5,0,10,0,2.4 /
&EXIT ID='Out', IOR=+1, XB=10,10,4,6,0.4,1.6 /
{extra}
"""
GROUP = "&EVAC ID='g', XB=1,4,1,9,1,1, NUMBER_INITIAL_PERSONS=10 /"
WALL_HOLE = "&HOLE XB=4.9,5.1,4,5,0,2.4 /"


def _evac_mesh(tmp_path, *extra: str, **kwargs):
    path = _deck(tmp_path, EVAC_MESH.format(extra="\n".join(extra)))
    return import_fds_deck(path, **kwargs)


def test_evac_mesh_hole_joins_the_spawn_and_the_exit(tmp_path):
    result = _evac_mesh(tmp_path, GROUP, WALL_HOLE)
    assert result.report.walkable["source"] == "derived:evac-mesh"
    assert result.report.walkable["area_m2"] == pytest.approx(100 - 1.0 + 0.1)
    assert result.report.walkable["components"] == 1
    assert list(result.raw["exits"]) == ["Out"]
    assert result.report.runnable


def test_evac_mesh_without_hole_drops_the_exit_side(tmp_path):
    result = _evac_mesh(tmp_path, GROUP)
    assert result.report.walkable["area_m2"] == pytest.approx(49.5)
    [dropped] = result.report.walkable["components_dropped"]
    assert dropped["exits"] == ["Out"]
    assert dropped["reason"] == "no spawn area in it"
    assert result.raw["exits"] == {}
    assert not result.report.runnable


def test_zero_width_evac_outside_the_walkable_area_is_named(tmp_path):
    point = "&EVAC ID='out', XB=20,20,5,5,1,1, NUMBER_INITIAL_PERSONS=5 /"
    result = _evac_mesh(tmp_path, point, WALL_HOLE)
    [item] = [i for i in _items(result, "D", "EVAC") if i.id == "out"]
    assert item.level == "error" and item.message.startswith("zero-width XB")
    assert "band lies outside the walkable area" in item.message
    [reason] = result.report.not_runnable
    assert reason.startswith("no agents to place: 1 &EVAC record(s) have a zero-width")


def test_line_evac_becomes_a_band(tmp_path):
    """#675: a line grows to 0.6 m across its zero-width axis."""
    line = "&EVAC ID='line', XB=2,2,1,9,1,1, NUMBER_INITIAL_PERSONS=5 /"
    result = _evac_mesh(tmp_path, line, WALL_HOLE)
    spawn = result.raw["distributions"]["line"]
    assert _same(_poly(spawn["coordinates"]), box(1.7, 1, 2.3, 9))
    assert spawn["parameters"]["number"] == 5
    [report] = result.report.distributions
    assert report["zero_width_expansion"] == {
        "shape": "line",
        "xb": [2.0, 2.0, 1.0, 9.0],
        "band_m": 0.6,
        "band_xb": [1.7, 2.3, 1.0, 9.0],
        "walkable_area_m2": 4.8,
    }
    assert result.report.runnable
    assert any(i.id == "line" for i in _items(result, "A", "EVAC"))


def test_point_evac_becomes_a_square(tmp_path):
    point = "&EVAC ID='p', XB=2,2,5,5,1,1, NUMBER_INITIAL_PERSONS=1 /"
    result = _evac_mesh(tmp_path, point, WALL_HOLE)
    spawn = result.raw["distributions"]["p"]
    assert _same(_poly(spawn["coordinates"]), box(1.7, 4.7, 2.3, 5.3))
    assert result.report.distributions[0]["zero_width_expansion"]["shape"] == "point"


def test_band_is_clipped_to_the_walkable_area(tmp_path):
    """A point by the wall: the band is cut by it into two pieces."""
    point = "&EVAC ID='w', XB=4.9,4.9,8,8,1,1, NUMBER_INITIAL_PERSONS=2 /"
    result = _evac_mesh(tmp_path, point, WALL_HOLE)
    pieces = {k: v for k, v in result.raw["distributions"].items()}
    assert sorted(pieces) == ["w_1", "w_2"]
    areas = sorted(_poly(v["coordinates"]).area for v in pieces.values())
    assert areas == pytest.approx([0.15 * 0.6, 0.35 * 0.6])
    assert sum(v["parameters"]["number"] for v in pieces.values()) == 2


def test_touching_evacuation_meshes_are_reported(tmp_path):
    second = (
        "&MESH IJK=40,40,1, XB=10,20,0,10,0.4,1.6, EVACUATION=.TRUE.,\n"
        "      EVAC_HUMANS=.TRUE., ID='East' /"
    )
    result = _evac_mesh(tmp_path, GROUP, WALL_HOLE, second)
    [item] = [i for i in _items(result, "A", "MESH") if "touch" in i.message]
    assert "'Main' and 'East'" in item.message
    alone = _evac_mesh(tmp_path, GROUP, WALL_HOLE)
    assert not [i for i in _items(alone, "A", "MESH") if "touch" in i.message]


def test_only_exits_and_doors_open_the_evac_mesh_edge(tmp_path):
    """An OPEN fire vent or an &ENTR on the mesh edge is not an exit."""
    edge = (
        "&VENT XB=0,0,4,6,0,2, SURF_ID='OPEN' /",
        "&ENTR ID='In', IOR=+1, XB=0,0,1,2,0.4,1.6, MAX_FLOW=0.0 /",
    )
    result = _evac_mesh(tmp_path, GROUP, WALL_HOLE, *edge)
    assert list(result.raw["exits"]) == ["Out"]
    assert result.report.walkable["area_m2"] == pytest.approx(99.1)


def test_count_only_exit_is_listed_as_a_counter(tmp_path):
    counter = "&EXIT ID='C', IOR=+1, COUNT_ONLY=.TRUE., XB=10,10,7,8,0.4,1.6 /"
    out = tmp_path / "out"
    result = _evac_mesh(tmp_path, GROUP, WALL_HOLE, counter)
    result.write(out)
    report = json.loads((out / "import_report.json").read_text())
    [item] = [i for i in report["items"] if i["id"] == "C"]
    assert (item["status"], item["group"]) == ("D", "EXIT")
    assert item["message"].startswith("COUNT_ONLY counter: not an exit")
    assert list(result.raw["exits"]) == ["Out"]


def test_user_exit_keeps_its_component_on_an_evac_mesh(tmp_path):
    result = _evac_mesh(tmp_path, GROUP, exits=[(10, 1, 10, 2, 1)])
    assert result.report.walkable["area_m2"] == pytest.approx(99.0)
    assert sorted(result.raw["exits"]) == ["Out", "user_exit_1"]


# #673: a 10 x 10 m evacuation mesh with dx = 0.25 m and one group.
GRID = """\
&HEAD CHID='grid' /
&MESH IJK=40,40,1, XB=0,10,0,10,0.4,1.6, EVACUATION=.TRUE.,
      EVAC_HUMANS=.TRUE., ID='Main' /
&EVAC ID='g', XB=1,4,1,9,1,1, NUMBER_INITIAL_PERSONS=10 /
{extra}
"""


def _grid(tmp_path, *extra: str):
    path = _deck(tmp_path, GRID.format(extra="\n".join(extra)))
    return import_fds_deck(path)


def test_exit_off_the_grid_is_kept_and_the_fds_evac_position_reported(tmp_path):
    result = _grid(tmp_path, "&EXIT ID='E', IOR=+1, XB=9.9,9.9,4.1,6,0.4,1.6 /")
    exit_ = result.raw["exits"]["E"]
    assert _same(_poly(exit_["coordinates"]), box(9.4, 4.1, 9.9, 6))
    [entry] = result.report.exits
    assert entry["fds_evac_segment"] == [10.0, 4.0, 10.0, 6.0]
    [item] = [i for i in _items(result, "A", "EXIT") if "evacuation grid" in i.message]
    assert item.level == "info" and "x 10..10, y 4..6" in item.message


def test_exit_beyond_its_named_mesh_is_clipped_in_the_report(tmp_path):
    """MESH_ID names the mesh; FDS+Evac clips the line to it, then rounds."""
    record = "&EXIT ID='E', MESH_ID='Main', IOR=+1, XB=10,10,-0.1,6.1,0.4,1.6 /"
    result = _grid(tmp_path, record)
    exit_ = result.raw["exits"]["E"]
    assert _same(_poly(exit_["coordinates"]), box(9.5, 0, 10, 6.1))
    assert result.report.exits[0]["fds_evac_segment"] == [10.0, 0.0, 10.0, 6.0]


def test_exit_beyond_the_mesh_without_mesh_id_uses_the_one_it_touches(tmp_path):
    record = "&EXIT ID='E', IOR=+1, XB=10,10,-0.1,6.1,0.4,1.6 /"
    result = _grid(tmp_path, record)
    assert result.report.exits[0]["fds_evac_segment"] == [10.0, 0.0, 10.0, 6.0]


def test_exit_on_the_grid_reports_no_fds_evac_position(tmp_path):
    result = _grid(tmp_path, "&EXIT ID='E', IOR=+1, XB=10,10,4,6,0.4,1.6 /")
    assert result.report.exits[0]["fds_evac_segment"] is None
    assert not [i for i in _items(result, "A") if "evacuation grid" in i.message]


def test_exit_behind_a_solid_strip_is_dropped_not_moved(tmp_path):
    """No snapping (maintainer D5): the distance is in the message."""
    records = (
        "&OBST XB=9.4,10,0,10,0,2.4 /",
        "&EXIT ID='E', IOR=+1, XB=10,10,4,6,0.4,1.6 /",
    )
    result = _grid(tmp_path, *records)
    assert result.raw["exits"] == {}
    [item] = [i for i in _items(result, "D", "EXIT") if i.level == "error"]
    assert item.message == (
        "exit dropped: its strip on the room side is empty; "
        "the line is 0.600 m from the walkable area"
    )


def test_exits_narrower_than_the_minimum_name_flow_field_targets(tmp_path):
    slot = "&EXIT ID='S', IOR=+1, XB=10,10,4,4.05,0.4,1.6 /"
    result = _grid(tmp_path, slot)
    [item] = [i for i in _items(result, "D", "EXIT") if i.level == "error"]
    assert "0.050 m wide, below the minimum exit width of 0.1 m" in item.message
    [reason] = result.report.not_runnable
    assert "only as flow-field targets" in reason


def test_exit_width_just_below_the_minimum_prints_below_it(tmp_path):
    slot = "&EXIT ID='S', IOR=+1, XB=10,10,4,4.0999,0.4,1.6 /"
    result = _grid(tmp_path, slot)
    [item] = [i for i in _items(result, "D", "EXIT") if i.level == "error"]
    assert "0.0999 m wide, below the minimum exit width of 0.1 m" in item.message


def test_exit_width_short_by_rounding_noise_prints_the_full_float(tmp_path):
    # 4.1 - 4.0 is 0.09999999999999964 in floating point (CorridorFlowExample).
    slot = "&EXIT ID='S', IOR=+1, XB=10,10,4,4.1,0.4,1.6 /"
    result = _grid(tmp_path, slot)
    [item] = [i for i in _items(result, "D", "EXIT") if i.level == "error"]
    assert (
        "0.09999999999999964 m wide, below the minimum exit width of 0.1 m"
        in item.message
    )


# --- report details --------------------------------------------------------------


def test_fire_surface_in_walkable_space_is_reported(tmp_path):
    burner = (
        "&SURF ID='BURNER', HRRPUA=1000. /\n"
        "&OBST XB=3,4,3,4,0,0.6 /\n"
        "&VENT XB=3,4,3,4,0.6,0.6, SURF_ID='BURNER' /"
    )
    result = _room(tmp_path, DOOR, burner)
    [item] = [i for i in _items(result, "A", "VENT") if "fire surface" in i.message]
    assert "1.000 m2" in item.message
    assert "&EVHO" in item.message


def test_fire_surface_on_a_plain_deck_advises_a_supported_exclusion(tmp_path):
    burner = (
        "&VENT XB=0,0,4,6,0,2, SURF_ID='OPEN' /\n"
        "&SURF ID='BURNER', HRRPUA=1000. /\n"
        "&VENT XB=3,4,3,4,0,0, SURF_ID='BURNER' /"
    )
    result = _modern(tmp_path, burner)
    [item] = [i for i in _items(result, "A", "VENT") if "fire surface" in i.message]
    assert "&EVHO" not in item.message
    advice = item.message.split("; ", 1)[1]
    assert advice.startswith("rerun init with --walkable FILE.wkt")
    assert "cut a notch around it from the edge of the spawn polygon" in advice


def test_report_lists_the_loader_defaults(tmp_path):
    result = _modern(tmp_path, "&VENT XB=0,0,4,6,0,2, SURF_ID='OPEN' /")
    defaults = result.report.distributions[0]["loader_defaults"]
    assert set(defaults) == {"v0", "radius", "premovement", "familiarity"}


def test_bad_ior_drops_the_exit_not_the_import(tmp_path):
    bad = "&EXIT ID='Up', IOR=3, XB=5,5,4,6,0.4,1.6 /"
    result = _room(tmp_path, DOOR, bad)
    assert list(result.raw["exits"]) == ["Left"]
    assert any(i.id == "Up" and i.level == "error" for i in _items(result, "D"))


def test_agents_option_on_a_legacy_deck_is_reported(tmp_path):
    result = _room(tmp_path, DOOR, EVAC.format(extra=""), agents=50)
    assert _params(result, "g")["number"] == 25
    assert any(i.group == "--agents" for i in _items(result, "D"))


def test_round_trip_through_wkt_to_fds(tmp_path):
    """WKT -> wkt_to_fds deck -> import: area error <= perimeter * dx / 2.

    This checks the default walkable provider, not the importer. The deck
    has no OPEN vent, so it says nothing about exits.
    """
    from pyfds_evac.core.wkt_to_fds import wkt_to_fds

    original = shapely_wkt.loads("POLYGON ((0 0, 6 0, 6 4, 10 4, 10 10, 0 10, 0 0))")
    dx = 0.1
    deck = _deck(tmp_path, wkt_to_fds(original, dx=dx, include_fire=False))
    result = import_fds_deck(deck)
    walkable = shapely_wkt.loads(result.walkable_wkt)
    bound = original.length * dx / 2
    assert walkable.symmetric_difference(original).area <= bound


def test_vent_with_a_slash_in_a_comment_is_still_an_exit(tmp_path):
    vent = "&VENT XB=0,0,4,6,0,2, ! main door, see plan A/B\n      SURF_ID='OPEN' /"
    assert list(_modern(tmp_path, vent).raw["exits"]) == ["vent_1"]


def test_repo_t_junction_deck_imports(tmp_path):
    """The deck has ``HRRPUA=1000, ! 1000 kW/m2 ...`` inside a record."""
    root = Path(__file__).resolve().parents[1] / "assets" / "t_junction"
    wkt = (root / "geometry.wkt").read_text(encoding="utf-8")
    result = import_fds_deck(root / "t_junction.fds", walkable_wkt=wkt, agents=40)
    assert result.report.runnable
    assert len(result.raw["exits"]) == 2


def test_default_properties_win_over_vel_mean_without_velocity_dist(tmp_path):
    """FDS+Evac applies the preset while VELOCITY_DIST is unset (evac.f90:1850)."""
    pers = "&PERS ID='A', DEFAULT_PROPERTIES='Adult', VEL_MEAN=1.0 /"
    result = _room(tmp_path, DOOR, pers, EVAC.format(extra=", PERS_ID='A'"))
    params = _params(result, "g")
    assert (params["v0"], params["v0_distribution"]) == (1.25, "gaussian")
    assert any("VEL_MEAN ignored" in i.message for i in _items(result, "A", "PERS"))


def test_uniform_velocity_dist_becomes_gaussian(tmp_path):
    pers = "&PERS ID='U', VELOCITY_DIST=1, VEL_LOW=0.95, VEL_HIGH=1.55 /"
    result = _room(tmp_path, DOOR, pers, EVAC.format(extra=", PERS_ID='U'"))
    params = _params(result, "g")
    assert params["v0"] == pytest.approx(1.25, abs=1e-12)
    assert params["v0_distribution"] == "gaussian"
    assert params["v0_std"] == pytest.approx(0.30 / math.sqrt(3), abs=1e-9)


# --- CLI exit statuses and output ------------------------------------------------


def test_cli_argument_error_exits_one(tmp_path, capsys):
    assert cli_init.main([str(tmp_path / "d.fds"), "--no-such"]) == cli_init.EXIT_ERROR
    assert "unrecognized arguments: --no-such" in capsys.readouterr().err


def test_cli_write_failure_exits_one_and_leaves_nothing(tmp_path, capsys):
    deck = _deck(tmp_path, ROOM.format(extra=DOOR + "\n" + EVAC.format(extra="")))
    blocker = tmp_path / "file"
    blocker.write_text("", encoding="utf-8")
    argv = [
        str(deck),
        "-o",
        str(blocker / "out"),
        "--walkable",
        _wkt(tmp_path, ROOM_WKT),
    ]
    assert cli_init.main(argv) == cli_init.EXIT_ERROR
    assert "cannot write" in capsys.readouterr().err
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "deck.fds",
        "file",
        "walk.wkt",
    ]


def test_write_replaces_files_in_an_existing_folder(tmp_path):
    out = tmp_path / "o"
    out.mkdir()
    (out / "keep.txt").write_text("x", encoding="utf-8")
    _room(tmp_path, DOOR).write(out)
    names = sorted(p.name for p in out.iterdir())
    assert names == ["config.json", "geometry.wkt", "import_report.json", "keep.txt"]
    assert [p.name for p in tmp_path.iterdir() if p.name.startswith(".")] == []


def test_cli_not_runnable_prints_no_run_command(tmp_path, capsys):
    path = _deck(tmp_path, MODERN.format(vents=""))
    argv = [str(path), "-o", str(tmp_path / "o"), "--walkable", _wkt(tmp_path)]
    assert cli_init.main(argv) == cli_init.EXIT_NOT_RUNNABLE
    out = capsys.readouterr().out
    assert "pyfds-evac --scenario" not in out
    assert "no exit found" in out and "pyfds-evac init again" in out


def test_cli_exit_dropped_with_an_error_exits_three(tmp_path, capsys):
    far = "&EXIT ID='Far', IOR=1, XB=20,20,4,6,0.4,1.6 /"
    deck = _deck(
        tmp_path, ROOM.format(extra="\n".join((DOOR, far, EVAC.format(extra=""))))
    )
    argv = [
        str(deck),
        "-o",
        str(tmp_path / "o"),
        "--walkable",
        _wkt(tmp_path, ROOM_WKT),
    ]
    assert cli_init.main(argv) == cli_init.EXIT_NOT_RUNNABLE
    out = capsys.readouterr().out
    assert "✗ 1 error" in out and "Far (line" in out
    assert "pyfds-evac --scenario" in out


def _authored_copy(tmp_path) -> Path:
    """QA's overwrite case: a deck next to its authored scenario."""
    source = (
        Path(__file__).resolve().parents[1] / "assets/schroeder2020_room/hrr060_2door"
    )
    target = tmp_path / "hrr060_2door"
    shutil.copytree(source, target)
    return target


def test_import_refuses_to_overwrite_an_authored_scenario(tmp_path, capsys):
    folder = _authored_copy(tmp_path)
    before = (folder / "config.json").read_bytes()
    argv = [str(folder / "hrr060_2door.fds"), "-o", str(folder)]
    argv += ["--walkable", str(folder / "geometry.wkt")]
    assert cli_init.main(argv) == cli_init.EXIT_ERROR
    assert "--force" in capsys.readouterr().err
    assert (folder / "config.json").read_bytes() == before
    assert not (folder / "import_report.json").exists()
    assert cli_init.main([*argv, "--force"]) == cli_init.EXIT_OK
    assert (folder / "config.json").read_bytes() != before


def test_reimport_into_an_importer_made_folder_is_allowed(tmp_path):
    deck = _deck(tmp_path, ROOM.format(extra=DOOR + "\n" + EVAC.format(extra="")))
    argv = [
        str(deck),
        "-o",
        str(tmp_path / "o"),
        "--walkable",
        _wkt(tmp_path, ROOM_WKT),
    ]
    assert cli_init.main(argv) == cli_init.EXIT_OK
    assert cli_init.main(argv) == cli_init.EXIT_OK


def test_offset_gamma_keeps_mean_variance_and_the_earliest_start():
    """DET U(5,15) + PRE U(2,8): floor 7 s, mean 15 s, variance 100/12 + 36/12."""
    from pyfds_evac.core.fds_import_people import Component, combine_delays

    det = Component("uniform", 5, 15, 10, 100 / 12)
    pre = Component("uniform", 2, 8, 5, 36 / 12)
    delay, status, _ = combine_delays(det, pre)
    assert (delay.kind, status, delay.offset) == ("gamma", "A", 7)
    assert delay.a * delay.b + delay.offset == pytest.approx(15, abs=1e-12)
    assert delay.a * delay.b**2 == pytest.approx(136 / 12, abs=1e-12)


def test_offset_floor_is_zero_for_a_gamma_detection():
    """R6: DET gamma(2, 3) + PRE U(5, 15): floor 0 + 5 s; mean 16 s, var 18 + 100/12."""
    from pyfds_evac.core.fds_import_people import Component, combine_delays

    det = Component("gamma", 2, 3, 6, 18)
    pre = Component("uniform", 5, 15, 10, 100 / 12)
    delay, status, _ = combine_delays(det, pre)
    assert (delay.kind, status, delay.offset) == ("gamma", "A", 5)
    assert delay.a * delay.b + delay.offset == pytest.approx(16, abs=1e-12)
    assert delay.a * delay.b**2 == pytest.approx(18 + 100 / 12, abs=1e-12)


# --- pyfds-evac init: default folder and next steps ----------------------------------


OPEN_VENT = "&VENT XB=0,0,4,6,0,2, SURF_ID='OPEN' /"


def _init(tmp_path, capsys, *extra: str, smv: bool = False) -> tuple[int, str]:
    deck = _deck(tmp_path, MODERN.format(vents=OPEN_VENT), name="plain.fds")
    if smv:
        (tmp_path / "plain.smv").write_text("", encoding="utf-8")
    status = cli_init.main([str(deck), "--walkable", _wkt(tmp_path), *extra])
    captured = capsys.readouterr()
    return status, captured.out + captured.err


def test_default_output_folder_is_next_to_the_deck(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    status, out = _init(tmp_path, capsys)
    folder = tmp_path / "plain_scenario"
    assert status == cli_init.EXIT_OK
    assert sorted(p.name for p in folder.iterdir()) == [
        "config.json",
        "geometry.wkt",
        "import_report.json",
    ]
    assert "pyfds-evac --scenario plain_scenario " in out


def test_guard_applies_to_the_default_folder(tmp_path, capsys):
    folder = tmp_path / "plain_scenario"
    folder.mkdir()
    (folder / "config.json").write_text("{}", encoding="utf-8")
    status, out = _init(tmp_path, capsys)
    assert status == cli_init.EXIT_ERROR
    assert "--force" in out
    assert (folder / "config.json").read_text(encoding="utf-8") == "{}"
    status, _ = _init(tmp_path, capsys, "--force")
    assert status == cli_init.EXIT_OK
    assert (folder / "import_report.json").exists()


def test_next_steps_without_fds_output(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _, out = _init(tmp_path, capsys)
    steps = out[out.index("Next:") :].splitlines()
    assert steps[1] == "  1. Run FDS:"
    assert steps[2].strip() == "mpiexec -n 2 fds plain.fds"
    assert steps[3] == "  2. pyfds-evac --scenario plain_scenario --fds-dir ."
    assert "clear air: drop --fds-dir" in steps[4]
    assert (
        steps[5].startswith("  3. Refine in JuPedSim Web")
        and "pyfds-evac-tui" in steps[5]
    )


def test_next_steps_with_fds_output(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _, out = _init(tmp_path, capsys, smv=True)
    steps = out[out.index("Next:") :]
    assert "Run FDS" not in steps
    assert "  1. pyfds-evac --scenario plain_scenario --fds-dir ." in steps
    assert "FDS output found: plain.smv; the run uses it" in out


# --- pyfds-evac init: the quiet summary ---------------------------------------------


def _many_groups(tmp_path, *records: str) -> Path:
    """Three groups with the same delay and dropped keys, one exit off the area."""
    pers = (
        "&PERS ID='P', DEFAULT_PROPERTIES='Adult', "
        "DET_EVAC_DIST=1, DET_LOW=5, DET_HIGH=15, "
        "PRE_EVAC_DIST=1, PRE_LOW=5, PRE_HIGH=15 /"
    )
    far = "&EXIT ID='Far', IOR=1, XB=20,20,4,6,0.4,1.6 /"
    groups = [
        f"&EVAC ID='g{i}', XB={i},{i + 1},1,9,1,1, NUMBER_INITIAL_PERSONS=5, "
        "PERS_ID='P', AGENT_TYPE=2 /"
        for i in (1, 3, 5)
    ]
    extra = "\n".join((DOOR, far, pers, *groups, *records))
    return _deck(tmp_path, ROOM.format(extra=extra))


def _summary(tmp_path, capsys, *extra: str, records: tuple = ()) -> list[str]:
    deck = _many_groups(tmp_path, *records)
    argv = [str(deck), "--walkable", _wkt(tmp_path, ROOM_WKT), *extra]
    assert cli_init.main(argv) == cli_init.EXIT_NOT_RUNNABLE  # one exit dropped
    return capsys.readouterr().out.splitlines()


def test_summary_lists_errors_before_grouped_notes(tmp_path, capsys):
    lines = _summary(tmp_path, capsys)
    errors = lines.index("✗ 1 error")
    notes = next(i for i, line in enumerate(lines) if line.startswith("! "))
    assert errors < notes < lines.index("Next:")
    assert lines[errors + 1].startswith("  Far (line ")
    note_lines = lines[notes + 1 : lines.index("Next:") - 1]
    delay = [line for line in note_lines if line.lstrip().startswith("delay:")]
    assert len(delay) == 1 and delay[0].endswith("3 groups")
    assert "mean 20 s" in delay[0]
    dropped = [line for line in note_lines if "AGENT_TYPE" in line]
    assert len(dropped) == 1 and dropped[0].endswith("3 groups")
    assert int(lines[notes].split()[1]) == len(note_lines)


def test_summary_hides_info_notes_and_the_errored_records_warnings(tmp_path, capsys):
    text = "\n".join(_summary(tmp_path, capsys))
    assert "omni-directional sign" not in text  # info level: report only
    assert "walkable_suspect" not in text  # Far has an error line instead
    assert "[A]" not in text and "[D]" not in text


def test_verbose_prints_every_report_line(tmp_path, capsys):
    lines = _summary(tmp_path, capsys, "--verbose")
    delay = [line for line in lines if "delay: detection + reaction" in line]
    assert len(delay) == 3
    assert any(line.startswith("  [D] error: &EXIT 'Far'") for line in lines)
    assert "Next:" in lines


def test_delay_mean_in_the_report_is_the_total(tmp_path):
    """The written offset + gamma has mean 20 s, and the note says so."""
    pers = (
        "&PERS ID='P', DET_EVAC_DIST=1, DET_LOW=5, DET_HIGH=15, "
        "PRE_EVAC_DIST=1, PRE_LOW=5, PRE_HIGH=15 /"
    )
    result = _room(tmp_path, DOOR, pers, EVAC.format(extra=", PERS_ID='P'"))
    params = _params(result, "g")
    mean = params["premovement_offset_s"] + (
        params["premovement_param_a"] * params["premovement_param_b"]
    )
    assert mean == pytest.approx(20, abs=1e-6)
    [note] = [i.message for i in result.report.items if i.message.startswith("delay:")]
    assert "mean 20 s" in note


def _legacy_init(tmp_path, capsys, monkeypatch, smv: bool) -> str:
    """An FDS+Evac deck (CHID 'room'), with or without room.smv next to it."""
    monkeypatch.chdir(tmp_path)
    deck = _deck(tmp_path, ROOM.format(extra=DOOR + "\n" + EVAC.format(extra="")))
    if smv:
        (tmp_path / "room.smv").write_text("", encoding="utf-8")
    argv = [str(deck), "--walkable", _wkt(tmp_path, ROOM_WKT)]
    assert cli_init.main(argv) == cli_init.EXIT_OK
    return capsys.readouterr().out


@pytest.mark.parametrize("smv", [False, True], ids=["no-output", "evac-output"])
def test_legacy_next_steps_ask_for_a_fire_only_run(tmp_path, capsys, monkeypatch, smv):
    """N1: one message in both cases; never --fds-dir on the deck folder."""
    out = _legacy_init(tmp_path, capsys, monkeypatch, smv)
    steps = out[out.index("Next:") :]
    assert "1. Run FDS on a fire-only copy of the deck" in steps
    assert "EVACUATION=.TRUE." in steps
    assert "--fds-dir <folder of the fire-only run>" in steps
    assert "--fds-dir ." not in out and "room.fds" not in steps
    found = [line for line in out.splitlines() if line.startswith("FDS output found")]
    if not smv:
        assert found == []
        return
    [line] = found
    assert "not used" in line and "fire-only run" in line


def test_summary_counts_deck_groups_not_split_pieces(tmp_path, capsys):
    """F2: three &EVAC records with an &EVHO through each give 'Groups 3'."""
    lines = _summary(tmp_path, capsys, records=("&EVHO XB=0,10,4,5,1,1 /",))
    [overview] = [line for line in lines if "Groups" in line]
    assert "Groups    3 (15 agents)" in overview
    config = json.loads((tmp_path / "deck_scenario" / "config.json").read_text())
    assert len(config["distributions"]) == 6  # each group split in two


def test_summary_names_spawn_areas_on_a_plain_deck(tmp_path, capsys):
    _, out = _init(tmp_path, capsys)
    assert "Spawn     1 area (100 placeholder agents)" in out


def test_summary_shows_result_changing_info_notes(tmp_path, capsys):
    """F1: a missing T_END is an info item, but it sets the run's time limit."""
    deck = _deck(tmp_path, MODERN.format(vents=OPEN_VENT), name="plain.fds")
    status = cli_init.main([str(deck), "--walkable", _wkt(tmp_path), "--agents", "5"])
    out = capsys.readouterr().out
    assert status == cli_init.EXIT_OK
    assert "no T_END: max_simulation_time 300 s" in out
