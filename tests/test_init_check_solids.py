"""init --check-solids: walkable area against FDS's solid cells (#715)."""

import json
from pathlib import Path

from pyfds_evac import cli_init
from pyfds_evac.core.fds_import import import_fds_deck
from pyfds_evac.core.fds_solids_check import check_solids

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
