"""init --check-solids: walkable area against FDS's solid cells (#715)."""

import json
from pathlib import Path

import numpy as np
import pytest
from shapely.geometry import box

from pyfds_evac import cli_init
from pyfds_evac.core.fds_import import import_fds_deck
from pyfds_evac.core.fds_solids_check import _compare, check_solids

ROOT = Path(__file__).resolve().parents[1]
DECK = ROOT / "assets/t_junction/t_junction.fds"
RUN = ROOT / "scripts/figures/data/t_junction_fire_2MW_PVC_extinction"
PLANT = "&OBST XB=2,4,11,12,0,3 /\n"


def _planted(tmp_path) -> Path:
    text = DECK.read_text(encoding="utf-8")
    anchor = "&OBST XB=23,30"
    assert anchor in text
    path = tmp_path / "t_junction.fds"
    path.write_text(text.replace(anchor, PLANT + anchor, 1), encoding="utf-8")
    return path


def test_shipped_run_agrees_with_the_walkable_area():
    summary = check_solids(RUN, import_fds_deck(DECK))
    assert summary["cells_compared"] == 2400
    assert summary["cells_disagreeing"] == 0
    assert summary["regions"] == []


def test_planted_obstruction_is_one_region(tmp_path):
    result = import_fds_deck(_planted(tmp_path))
    summary = check_solids(RUN, result)
    assert summary["cells_disagreeing"] == 32
    assert summary["regions"] == [[2.0, 4.0, 11.0, 12.0]]
    items = [i for i in result.report.items if "solid" in i.message]
    assert any(i.status == "A" for i in items)


def test_missing_run_is_an_error(tmp_path):
    result = import_fds_deck(DECK)
    check_solids(tmp_path, result)
    assert result.report.errors


def test_cli_writes_the_summary(tmp_path):
    out = tmp_path / "scenario"
    status = cli_init.main(
        [str(DECK), "-o", str(out), "--no-fds", "--check-solids", str(RUN)]
    )
    report = json.loads((out / "import_report.json").read_text(encoding="utf-8"))
    assert status == 0
    assert report["walkable"]["check_solids"]["cells_disagreeing"] == 0


def test_check_solids_with_check_is_a_usage_error(capsys):
    status = cli_init.main([str(DECK), "--check", "--check-solids", str(RUN)])
    assert status == cli_init.EXIT_ERROR
    assert "--check-solids" in capsys.readouterr().err


class _FakeMesh:
    """The slice of fdsreader's Mesh that the check reads."""

    def __init__(self, x, y, z, blocked):
        self.coordinates = {
            "x": np.asarray(x, dtype=np.float32),
            "y": np.asarray(y, dtype=np.float32),
            "z": np.asarray(z, dtype=np.float32),
        }
        shape = (len(x) - 1, len(y) - 1, len(z) - 1)
        mask = np.ones((1, *shape), dtype=bool)
        for cell in blocked:
            mask[(0, *cell)] = False
        self._mask = mask

    def get_obstruction_mask(self, times, cell_centered=False):
        return self._mask


def test_small_solid_island_is_not_a_disagreement():
    # init fills a hole below 0.25 m2: one 0.25 m cell (0.0625 m2) is filled,
    # a block of four (0.25 m2) is kept and so is a real disagreement.
    nodes = np.arange(9) * 0.25
    area = box(0, 0, 2, 2)
    one = _FakeMesh(nodes, nodes, [0.0, 3.0], [(3, 3, 0)])
    assert _compare(one, (0.1, 1.8), area, area).disagree.sum() == 0
    block = [(i, j, 0) for i in (3, 4) for j in (3, 4)]
    four = _FakeMesh(nodes, nodes, [0.0, 3.0], block)
    assert _compare(four, (0.1, 1.8), area, area).disagree.sum() == 4


@pytest.mark.parametrize(
    "cell", [0, 2], ids=["top at the band bottom", "lower face at the band top"]
)
def test_band_edges_follow_the_obstruction_rule_of_init(cell):
    # init applies an obstruction whose z range touches the band (inclusive);
    # a grid node exactly on a band edge must not drop it.
    nodes = np.arange(5) * 1.0
    area = box(0, 0, 4, 4)
    walk = area.difference(box(1, 1, 3, 3))
    blocked = [(i, j, cell) for i in (1, 2) for j in (1, 2)]
    mesh = _FakeMesh(nodes, nodes, [0.0, 1.0, 2.0, 3.0], blocked)
    assert _compare(mesh, (1.0, 2.0), area, walk).disagree.sum() == 0


def test_unmatched_floor_mesh_is_named(tmp_path):
    text = DECK.read_text(encoding="utf-8")
    old = "XB=22.5,30.0,0,13,0,3 /"
    assert old in text
    deck = tmp_path / "t_junction.fds"
    deck.write_text(text.replace(old, "XB=22.5,30.0,0,13,0,3.5 /"), encoding="utf-8")
    summary = check_solids(RUN, import_fds_deck(deck))
    assert summary["meshes_unmatched"] == ["MESH line 9"]
    assert 0 < summary["cells_compared"] < 2400


def test_run_of_another_deck_is_an_error():
    other = ROOT / "assets/fds_evac_guide/Examples/DoorFlowExample.fds"
    result = import_fds_deck(other)
    summary = check_solids(RUN, result)
    assert summary["cells_compared"] == 0
    assert any("no floor mesh matches" in i.message for i in result.report.errors)
