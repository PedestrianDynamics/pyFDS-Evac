"""A cell-centred slice is ranked at its cell centres, not the upper face (#942).

``tests/data/cell_centred`` is a real FDS 6.10.1 run on one 0.5 m mesh with
an extinction slice at PBZ=1.75 written ``CELL_CENTERED=.TRUE.`` (the cell
1.5-2.0 m) and a node slice at PBZ=2.0. fdsreader 1.14 reports z = 2.0 for
both; only the node slice is there.
"""

import logging
from pathlib import Path

import pytest

DATA = Path(__file__).parent / "data" / "cell_centred"
QUANTITY = "SOOT EXTINCTION COEFFICIENT"


@pytest.fixture
def slices():
    fdsreader = pytest.importorskip("fdsreader")
    sim = fdsreader.Simulation(str(DATA))
    return {s.id: s for s in sim.slices}


def test_heights_are_the_cell_centre_and_the_node(slices):
    from pyfds_evac.core.fds_sampling import _slice_z_mid

    assert slices["ext_cc"].cell_centered
    assert slices["ext_cc"].extent.z_start == pytest.approx(2.0)  # the face
    assert _slice_z_mid(slices["ext_cc"]) == pytest.approx(1.75)
    assert _slice_z_mid(slices["ext_node"]) == pytest.approx(2.0)


@pytest.mark.parametrize(("requested", "chosen"), [(1.75, "ext_cc"), (2.0, "ext_node")])
def test_requested_height_picks_its_slice_without_warning(
    slices, caplog, requested, chosen
):
    from pyfds_evac.core.fds_sampling import select_horizontal_slice

    candidates = [slices["ext_cc"], slices["ext_node"]]
    with caplog.at_level(logging.WARNING):
        picked = select_horizontal_slice(candidates, requested, QUANTITY, str(DATA))
    assert picked is slices[chosen]
    assert "nearest available" not in caplog.text


def test_deck_check_reports_the_cell_centre():
    from pyfds_evac.core.fds_deck import parse_fds_text
    from pyfds_evac.core.fds_import_slices import check_slices

    deck = parse_fds_text(
        "&MESH IJK=4,4,4, XB=0,2,0,2,0,2 /\n"
        "&SLCF PBZ=1.75, QUANTITY='EXTINCTION COEFFICIENT', CELL_CENTERED=.TRUE. /\n"
    )
    item = check_slices(deck, 1.75).to_dict()["EXTINCTION COEFFICIENT"]
    assert item["nearest_pbz"] == pytest.approx(1.75)
