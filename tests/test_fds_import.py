"""Start a scenario from an FDS deck: parser, legacy mapping, modern inference.

Every deck here is a synthetic string written by the test (no file from
examples/FDS-Evac-Guide, which is GPLv3). Expectations are closed form:
axis-aligned rectangles, exact parameter mappings, exact integer shares.
Each import passes ``walkable_wkt`` so the importer is tested apart from the
walkable provider, except in the provider tests at the end.
"""

from __future__ import annotations

import json
import math

import pytest
from shapely import wkt as shapely_wkt
from shapely.geometry import Polygon, box

from pyfds_evac import cli, cli_import
from pyfds_evac.core.fds_deck import parse_fds_deck
from pyfds_evac.core.fds_import import import_fds_deck
from pyfds_evac.core.fds_import_geometry import largest_remainder
from pyfds_evac.core.premovement_distributions import (
    create_premovement_distribution,
)
from pyfds_evac.core.walkable_provider import (
    FloorSpec,
    WalkableError,
    WalkableResult,
    script_walkable,
)

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
    ("keys", "dist", "a", "b"),
    [
        ("DET_MEAN=2, PRE_MEAN=3", "constant", 5.0, None),
        ("DET_MEAN=2, PRE_EVAC_DIST=1, PRE_LOW=5, PRE_HIGH=15", "uniform", 7, 17),
        ("PRE_EVAC_DIST=3, PRE_PARA=2, PRE_PARA2=3", "gamma", 2, 3),
        ("PRE_EVAC_DIST=8, PRE_PARA=2, PRE_PARA2=0.1", "weibull", 10, 2),
        (
            "DET_EVAC_DIST=1, DET_LOW=5, DET_HIGH=15, "
            "PRE_EVAC_DIST=1, PRE_LOW=5, PRE_HIGH=15",
            "gamma",
            24,
            0.833333333,
        ),
        (
            "DET_MEAN=5, PRE_EVAC_DIST=3, PRE_PARA=2, PRE_PARA2=3",
            "gamma",
            round(121 / 18, 9),
            round(18 / 11, 9),
        ),
        ("PRE_EVAC_DIST=7, PRE_MEAN=10, PRE_LOW=4, PRE_HIGH=16", "constant", 10, None),
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
def test_detection_plus_premovement(tmp_path, keys, dist, a, b):
    delay = _delay(tmp_path, keys)
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
    status = cli_import.main([str(path), "-o", str(out), "--walkable", _wkt(tmp_path)])
    assert status == cli_import.EXIT_NOT_RUNNABLE
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


def test_cli_import_runnable_and_error(tmp_path, capsys):
    deck = _deck(tmp_path, ROOM.format(extra=DOOR + "\n" + EVAC.format(extra="")))
    walk = _wkt(tmp_path, ROOM_WKT)
    assert (
        cli_import.main([str(deck), "-o", str(tmp_path / "o"), "--walkable", walk]) == 0
    )
    assert "Run: pyfds-evac --scenario" in capsys.readouterr().out
    bad = _deck(tmp_path, "&CATF OTHER_FILES='x.fds' /", name="bad.fds")
    assert cli_import.main([str(bad), "-o", str(tmp_path / "b")]) == 1
    assert not (tmp_path / "b").exists()


def test_pyfds_evac_dispatches_the_import_subcommand(tmp_path, monkeypatch):
    deck = _deck(tmp_path, MODERN.format(vents=""))
    argv = ["pyfds-evac", "import", str(deck), "-o", str(tmp_path / "o")]
    monkeypatch.setattr("sys.argv", argv + ["--walkable", _wkt(tmp_path)])
    assert cli.main() == cli_import.EXIT_NOT_RUNNABLE


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


# A room 2-8 x 2-8 inside a 10 x 10 mesh, walls 0.2 m thick, with a 1 x 1 m
# obstruction whose CAD layer name says "door".
CLOSED_ROOM = """\
&HEAD CHID='closed' /
&MESH IJK=100,100,24, XB=0,10,0,10,0,2.4 /
&OBST XB=1.8,8.2,1.8,2.0,0,2.4 / A-WALL
&OBST XB=1.8,8.2,8.0,8.2,0,2.4 / A-WALL
&OBST XB=1.8,2.0,1.8,8.2,0,2.4 / A-WALL
&OBST XB=8.0,8.2,1.8,8.2,0,2.4 / A-WALL
&OBST XB=4,5,4,5,0,2.0 / door 1
"""


def test_script_provider_layer_rules(tmp_path):
    """Station layer rules are opt-in: by default every solid in band blocks."""
    path = _deck(tmp_path, CLOSED_ROOM)
    plain = import_fds_deck(path)
    station = import_fds_deck(path, layer_rules="station")
    area = {
        r.report.walkable["source"]: r.report.walkable["area_m2"]
        for r in (plain, station)
    }
    assert area == {"derived:script:none": 35.0, "derived:script:station": 36.0}


def test_script_provider_failure_names_the_deck_and_the_way_out(tmp_path):
    path = _deck(tmp_path, MODERN.format(vents=""))
    floor = FloorSpec(0.0, (0.1, 1.8), box(0, 0, 20, 10))
    with pytest.raises(WalkableError, match="deck.fds.*--walkable FILE.wkt"):
        script_walkable(parse_fds_deck(path), floor)


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
