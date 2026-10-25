"""``deck_walkable`` puts ``&OBST`` and ``&HOLE`` on the FDS mesh grid (#715).

The room is 10 x 10 m on ``IJK=20,20,6`` (0.5 m cells, 0.5 m in z). The
expected areas follow FDS's ``READ_OBST``/``READ_HOLE`` rules by hand:
``NINT`` per bound, the quarter-cell collapse, ``THICKEN``, obstructions
that collapse in two axes dropped, and holes cut in index space. A
zero-width wall is widened by ``HALF_CELL_M`` on each side afterwards.
"""

from __future__ import annotations

from pytest import approx
from shapely.geometry import box

from pyfds_evac.core.fds_deck import parse_fds_text
from pyfds_evac.core.fds_import_geometry import polygons_of
from pyfds_evac.core.walkable_provider import FloorSpec, deck_walkable, snap_footprints

MESH = "&MESH IJK=20,20,6, XB=0,10,0,10,0,3 /\n"


def _floor(deck, meshes=True):
    return FloorSpec(
        0.0,
        (0.1, 1.8),
        box(0, 0, 10, 10),
        None,
        tuple(deck.group("OBST")),
        tuple(deck.group("HOLE")),
        meshes=tuple(deck.group("MESH")) if meshes else (),
    )


def _walk(records, meshes=True):
    deck = parse_fds_text("&HEAD CHID='t' /\n" + records)
    return deck_walkable(deck, _floor(deck, meshes))


def _parts(result):
    return len(polygons_of(result.polygon))


def _notes(result, message):
    return [n for n in result.notes if message in n[3]]


def test_tie_rounds_half_up():
    result = _walk(MESH + "&OBST XB=2,2.25,0,10,0,3 /")
    assert result.polygon.area == approx(95.0)
    assert _parts(result) == 2
    assert result.snap["max_shift_m"] == approx(0.25)


def test_quarter_cell_wall_collapses_to_the_nearer_gridline():
    result = _walk(MESH + "&OBST XB=3.2,3.3,0,10,0,3 /")
    assert result.polygon.area == approx(99.0)
    assert _parts(result) == 2
    [note] = _notes(result, "thinner than its mesh cell")
    assert note[:3] == ("A", "warning", "OBST")


def test_obstruction_collapsed_in_two_axes_is_dropped():
    result = _walk(MESH + "&OBST XB=3.0,3.01,0,10,1.0,1.1 /")
    assert result.polygon.area == approx(100.0)
    assert _parts(result) == 1
    [note] = _notes(result, "FDS drops it")
    assert note[:3] == ("A", "warning", "OBST")
    assert result.snap["dropped"] == 1


def test_thicken_makes_a_thin_wall_one_cell_thick():
    result = _walk(MESH + "&OBST XB=3.0,3.05,0,10,0,3, THICKEN=.TRUE. /")
    assert result.polygon.area == approx(95.0)
    assert _parts(result) == 2


def test_thicken_from_misc_applies_when_the_floor_says_so():
    deck = parse_fds_text("&HEAD CHID='t' /\n" + MESH + "&OBST XB=3.0,3.05,0,10,0,3 /")
    floor = _floor(deck)
    plain = deck_walkable(deck, floor)
    thick = deck_walkable(
        deck, FloorSpec(*_args(floor), meshes=floor.meshes, thicken=True)
    )
    assert plain.polygon.area == approx(99.0)
    assert thick.polygon.area == approx(95.0)


def _args(floor):
    return (
        floor.z_floor,
        floor.z_band,
        floor.domain,
        floor.evac_mesh_ids,
        floor.obstructions,
        floor.holes,
    )


def test_hole_on_a_thin_wall():
    result = _walk(
        MESH + "&OBST XB=0,10,4.99,5.0,0,3 /\n&HOLE XB=1.0,1.9,4.8,5.1,0,3 /"
    )
    assert result.polygon.area == approx(99.1)
    assert _parts(result) == 1


def test_thick_hole_on_a_thin_wall():
    result = _walk(
        MESH + "&OBST XB=0,10,4.99,5.0,0,3 /\n&HOLE XB=1.0,2.0,4.5,5.5,0,3 /"
    )
    assert result.polygon.area == approx(99.1)
    assert _parts(result) == 1


def test_hole_snapped_to_nothing_leaves_the_opening_closed():
    result = _walk(MESH + "&OBST XB=0,10,4.5,5.5,0,3 /\n&HOLE XB=2.0,2.2,4.5,5.5,0,3 /")
    assert result.polygon.area == approx(90.0)
    assert _parts(result) == 2
    [note] = _notes(result, "opening stays closed")
    assert note[:3] == ("A", "warning", "HOLE")
    assert result.snap["holes_closed"] == 1


def test_walls_on_two_meshes_snap_to_each_grid():
    records = (
        "&MESH IJK=10,20,6, XB=0,5,0,10,0,3 /\n"
        "&MESH IJK=25,25,6, XB=5,10,0,10,0,3 /\n"
        "&OBST XB=0,10,4.9,5.3,0,3 /"
    )
    result = _walk(records)
    assert result.polygon.area == approx(95.5)
    assert _parts(result) == 2


def test_two_walls_on_one_gridline_merge_and_warn():
    result = _walk(MESH + "&OBST XB=0,10,4.0,4.01,0,3 /\n&OBST XB=0,10,4.11,4.12,0,3 /")
    assert result.polygon.area == approx(99.0)
    assert _parts(result) == 2
    [note] = _notes(result, "same gridline")
    assert note[:3] == ("A", "warning", "OBST")


def test_without_meshes_nothing_is_snapped():
    result = _walk(MESH + "&OBST XB=2,2.25,0,10,0,3 /", meshes=False)
    assert result.polygon.area == approx(97.5)
    assert result.snap is None
    assert result.notes == []


def test_on_grid_records_do_not_move():
    records = MESH + "&OBST XB=2,2.5,0,10,0,3 /"
    result = _walk(records)
    old = _walk(records, meshes=False)
    assert result.polygon.equals_exact(old.polygon, 0)
    assert result.snap["max_shift_m"] == 0
    assert result.notes == []


def test_stretched_grid_is_not_snapped():
    records = (
        MESH
        + "&TRNX IDERIV=0, CC=5, PC=5, MESH_NUMBER=1 /\n"
        + "&OBST XB=2,2.25,0,10,0,3 /"
    )
    result = _walk(records)
    assert result.polygon.area == approx(97.5)
    assert result.snap == {"skipped": "stretched grid (&TRNX/&TRNY)"}
    [note] = _notes(result, "stretched grid")
    assert note[:3] == ("A", "warning", "walkable")


def test_the_largest_shift_is_reported_once_as_info():
    result = _walk(MESH + "&OBST XB=2,2.25,0,10,0,3 /")
    [note] = _notes(result, "moved onto the FDS grid")
    assert note[:3] == ("S", "info", "walkable")
    assert note[4] is None


def test_snap_footprints_gives_one_box_per_record_and_mesh():
    deck = parse_fds_text(
        "&HEAD CHID='t' /\n"
        "&MESH IJK=10,20,6, XB=0,5,0,10,0,3 /\n"
        "&MESH IJK=25,25,6, XB=5,10,0,10,0,3 /\n"
        "&OBST XB=0,10,4.9,5.3,0,3 /\n"
        "&OBST XB=3.0,3.01,0,10,1.0,1.1 /"
    )
    boxes = snap_footprints(
        deck.group("OBST"), deck.group("MESH"), hole=False, thicken=False
    )
    assert [b.box for b in boxes] == [(0, 5, 5.0, 5.5), (5, 10, 4.8, 5.2)]
    assert [b.shift_m for b in boxes] == [approx(0.2), approx(0.1)]
