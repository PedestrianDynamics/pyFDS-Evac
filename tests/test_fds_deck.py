"""The FDS namelist parser: records, values, MULT expansion, errors.

The decks are synthetic strings; each test pins one Fortran-namelist rule
as FDS reads it.
"""

from __future__ import annotations

import pytest

from pyfds_evac.core.fds_deck import FdsDeckError, parse_fds_text


def test_record_spans_lines():
    deck = parse_fds_text("&EVAC ID='g',\n      XB=1,2,3,4,5,6 /\n")
    assert deck.first("EVAC").xb() == (1, 2, 3, 4, 5, 6)


def test_whitespace_separated_values():
    deck = parse_fds_text("&MESH IJK=10 10 4, XB= 0,40 0,20, 0,4 /")
    assert deck.first("MESH").xb() == (0, 40, 0, 20, 0, 4)
    assert deck.first("MESH").values("IJK") == [10, 10, 4]


def test_quoted_slash_and_text_after_slash():
    deck = parse_fds_text(
        "&OBST ID='a/b', XB=0,1,0,1,0,1 / trailing CAD layer\n"
        "&SURF ID='W' /TMP_FRONT=500.0,\n"
        "a comment line & not a record\n"
    )
    assert deck.first("OBST").id == "a/b"
    assert not deck.first("SURF").has("TMP_FRONT")
    assert [r.group for r in deck.records] == ["OBST", "SURF"]


def test_logicals_arrays_and_repeats():
    deck = parse_fds_text(
        "&EVAC ID='g', KNOWN_DOOR_NAMES='A','B', KNOWN_DOOR_PROBS=2*1.0 /\n"
        "&MESH EVACUATION=.TRUE., EVAC_HUMANS=T, XB=0,1,0,1,0,1 /"
    )
    evac, mesh = deck.first("EVAC"), deck.first("MESH")
    assert evac.values("KNOWN_DOOR_NAMES") == ["A", "B"]
    assert evac.values("KNOWN_DOOR_PROBS") == [1.0, 1.0]
    assert mesh.flag("EVACUATION") is True
    assert mesh.flag("EVAC_HUMANS") is True


def test_repeated_key_last_wins_with_a_warning():
    deck = parse_fds_text("&PERS ID='p', VEL_MEAN=1.0, VEL_MEAN=1.4 /")
    assert deck.first("PERS").number("VEL_MEAN") == 1.4
    assert any("VEL_MEAN given twice" in i.message for i in deck.issues)


def test_mult_ijk_expansion_count_and_offsets():
    deck = parse_fds_text(
        "&MULT ID='m', DX=2, DY=3, DX0=0.5, I_UPPER=2, J_UPPER=1 /\n"
        "&OBST XB=0,1,0,1,0,1, MULT_ID='m' /"
    )
    xbs = sorted(r.xb() for r in deck.group("OBST"))
    expected = sorted(
        (0.5 + 2 * i, 1.5 + 2 * i, 3 * j, 1 + 3 * j, 0, 1)
        for i in range(3)
        for j in range(2)
    )
    assert xbs == expected


def test_mult_n_expansion_with_dxb():
    deck = parse_fds_text(
        "&MULT ID='s', DXB=0,0,0,0,0.2,0.2, N_LOWER=0, N_UPPER=3 /\n"
        "&OBST XB=0,1,0,1,0,0.2, MULT_ID='s' /"
    )
    tops = [r.xb()[5] for r in deck.group("OBST")]
    assert tops == pytest.approx([0.2, 0.4, 0.6, 0.8])


def test_unsupported_mult_form_is_an_error():
    with pytest.raises(FdsDeckError, match="unsupported &MULT"):
        parse_fds_text(
            "&MULT ID='m', DX=1, N_UPPER=2 /\n&OBST XB=0,1,0,1,0,1, MULT_ID='m' /"
        )


def test_unknown_mult_id_is_an_error():
    with pytest.raises(FdsDeckError, match="names no &MULT"):
        parse_fds_text("&OBST XB=0,1,0,1,0,1, MULT_ID='x' /")


def test_catf_is_an_error():
    with pytest.raises(FdsDeckError, match="&CATF .*not supported.*geom.fds"):
        parse_fds_text("&CATF OTHER_FILES='geom.fds' /")


def test_geom_and_controlled_obst_are_reported():
    deck = parse_fds_text("&GEOM ID='g' /\n&OBST XB=0,1,0,1,0,1, DEVC_ID='d' /\n")
    status = {i.group: i.status for i in deck.issues}
    assert status == {"GEOM": "D", "OBST": "A"}


def test_unterminated_record_is_an_error():
    with pytest.raises(FdsDeckError, match="no closing"):
        parse_fds_text("&HEAD CHID='x'\n")


def test_bang_comment_with_slash_does_not_end_the_record():
    """FDS reads ``!`` to the end of the line as a comment, '/' included."""
    deck = parse_fds_text(
        "&VENT XB=0,0,4,6,0,2, ! main door, see plan A/B\n      SURF_ID='OPEN' /\n"
    )
    vent = deck.first("VENT")
    assert vent.xb() == (0, 0, 4, 6, 0, 2)
    assert vent.text("SURF_ID") == "OPEN"


def test_bang_comment_after_a_value():
    deck = parse_fds_text(
        "&SURF ID='FIRE',\n      HRRPUA=1000,  ! 1000 kW/m2 x 2 m2 = 2 MW peak\n"
        "      COLOR='RED' /\n"
    )
    surf = deck.first("SURF")
    assert surf.number("HRRPUA") == 1000
    assert surf.text("COLOR") == "RED"


def test_bang_inside_quotes_is_text():
    assert parse_fds_text("&OBST ID='a!b/c', XB=0,1,0,1,0,1 /").first("OBST").id == (
        "a!b/c"
    )


def test_missing_slash_before_the_next_record_is_an_error():
    text = "&VENT SURF_ID='OPEN' XB=0,0,0,1,0,1\n&OBST XB=2,3,0,1,0,1 /\n"
    with pytest.raises(FdsDeckError, match=r"&VENT \(line 1\).*&OBST on line 2"):
        parse_fds_text(text)


# The FDS User Guide (&MULT): copies are shifted by DX0/DY0/DZ0 plus
# I*DX, J*DY, K*DZ, with I, J, K running over [I_LOWER, I_UPPER] etc.; the
# defaults of every lower and upper index are 0 and of every spacing 0.


def _obst_xbs(text: str) -> list[tuple]:
    return sorted(r.xb() for r in parse_fds_text(text).group("OBST"))


def test_mult_k_and_j_offsets_and_negative_lower_indices():
    """K and J shift z and y; a lower index below 0 gives copies on both sides.

    K = -1, 0, 1 with DZ=2 and J = 0, 1 with DY=3 on a unit box and DZ0=10, DY0=1:
    z0 = 10 + 2K = 8, 10, 12 and y0 = 1 + 3J = 1, 4. Six copies.
    """
    xbs = _obst_xbs(
        "&MULT ID='m', DY0=1, DZ0=10, DY=3, DZ=2,"
        " K_LOWER=-1, K_UPPER=1, J_UPPER=1 /\n"
        "&OBST XB=0,1,0,1,0,1, MULT_ID='m' /"
    )
    expected = sorted((0, 1, y, y + 1, z, z + 1) for y in (1, 4) for z in (8, 10, 12))
    assert xbs == expected


def test_mult_i_lower_shifts_x_to_the_left():
    """I = -2 ... 0 with DX=5 on a box at x 10 to 11 gives 0, 5 and 10."""
    xbs = _obst_xbs(
        "&MULT ID='m', DX=5, I_LOWER=-2 /\n&OBST XB=10,11,0,1,0,1, MULT_ID='m' /"
    )
    assert [xb[0] for xb in xbs] == [0, 5, 10]


def test_mult_without_indices_is_one_copy_shifted_by_the_origin():
    """Every index defaults to 0: one copy, moved by DX0 and DY0 only."""
    xbs = _obst_xbs("&MULT ID='m', DX0=2, DY0=3 /\n&OBST XB=0,1,0,1,0,1, MULT_ID='m' /")
    assert xbs == [(2, 3, 3, 4, 0, 1)]


def test_mult_n_form_with_a_lower_bound_and_all_axes():
    """N = 1, 2 with DXB = (1, 1, 2, 2, 3, 3) moves each face by N * DXB.

    The box 0,1,0,1,0,1 gives x 1..2 and 2..3, y 2..3 and 4..5 (shift 2 and
    4), z 3..4 and 6..7 (shift 3 and 6), with DX0=0.5 added to x only.
    """
    xbs = _obst_xbs(
        "&MULT ID='m', DX0=0.5, DXB=1,1,2,2,3,3, N_LOWER=1, N_UPPER=2 /\n"
        "&OBST XB=0,1,0,1,0,1, MULT_ID='m' /"
    )
    assert xbs == [(1.5, 2.5, 2, 3, 3, 4), (2.5, 3.5, 4, 5, 6, 7)]


@pytest.mark.parametrize("dxb", ["1,1,1", "1,1,1,1,1,1,1"])
def test_mult_n_form_needs_six_dxb_numbers(dxb):
    with pytest.raises(FdsDeckError, match="DXB needs six numbers"):
        parse_fds_text(
            f"&MULT ID='m', DXB={dxb}, N_UPPER=1 /\n&OBST XB=0,1,0,1,0,1, MULT_ID='m' /"
        )


def test_mult_mixing_the_n_form_with_the_index_form_is_refused():
    """The message names the supported forms; the unknown key case differs."""
    with pytest.raises(FdsDeckError, match="unsupported &MULT 'm'"):
        parse_fds_text(
            "&MULT ID='m', DXB=1,1,1,1,1,1, N_UPPER=1, I_UPPER=1 /\n"
            "&OBST XB=0,1,0,1,0,1, MULT_ID='m' /"
        )
    with pytest.raises(FdsDeckError, match="unsupported &MULT 'm'"):
        parse_fds_text(
            "&MULT ID='m', I_UPPER=1, COLOR='RED' /\n"
            "&OBST XB=0,1,0,1,0,1, MULT_ID='m' /"
        )


@pytest.mark.parametrize("group", ["HOLE", "VENT", "OBST"])
def test_mult_expands_the_documented_groups(group):
    text = f"&MULT ID='m', DX=2, I_UPPER=1 /\n&{group} XB=0,1,0,1,0,1, MULT_ID='m' /"
    xbs = [r.xb() for r in parse_fds_text(text).group(group)]
    assert xbs == [(0, 1, 0, 1, 0, 1), (2, 3, 0, 1, 0, 1)]


def test_mult_expands_a_mesh_and_leaves_other_groups_alone():
    """&MESH is expanded; a &SURF carrying MULT_ID is not (MULT_GROUPS)."""
    deck = parse_fds_text(
        "&MULT ID='m', DX=1, I_UPPER=2 /\n"
        "&MESH IJK=1,1,1, XB=0,1,0,1,0,1, MULT_ID='m' /\n"
        "&SURF ID='s', MULT_ID='m' /"
    )
    assert [r.xb()[0] for r in deck.group("MESH")] == [0, 1, 2]
    assert len(deck.group("SURF")) == 1


def test_mult_needs_xb_on_the_record():
    with pytest.raises(FdsDeckError, match="MULT_ID needs XB"):
        parse_fds_text("&MULT ID='m', I_UPPER=1 /\n&OBST ID='a', MULT_ID='m' /")


# FDS reads Fortran reals: 1.5D+2 is 150, the exponent letter may be E or D
# in either case.


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("1.5D+2", 150.0),
        ("1.5d2", 150.0),
        ("2D-1", 0.2),
        ("-2.5d-1", -0.25),
        (".5D1", 5.0),
        ("1.5E+2", 150.0),
        ("1.5e2", 150.0),
    ],
)
def test_exponent_numbers_read_as_fortran_reals(text, value):
    deck = parse_fds_text(f"&MISC X={text} /")
    assert deck.first("MISC").values("X") == [pytest.approx(value)]


def test_d_exponent_in_xb_and_mult_spacing():
    """XB=0,1D0 and DX=5D-1 read as 0, 1 and 0.5: two copies at x 0 and 0.5."""
    xbs = _obst_xbs(
        "&MULT ID='m', DX=5D-1, I_UPPER=1 /\n&OBST XB=0,1D0,0,1,0,1, MULT_ID='m' /"
    )
    assert xbs == [(0, 1, 0, 1, 0, 1), (0.5, 1.5, 0, 1, 0, 1)]


@pytest.mark.parametrize("text", ["1D", "D2", "1.5D+", "1DD2", "1D2.5"])
def test_a_malformed_exponent_stays_text(text):
    deck = parse_fds_text(f"&MISC X={text} /")
    assert deck.first("MISC").values("X") == [text]
