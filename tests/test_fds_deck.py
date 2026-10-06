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
