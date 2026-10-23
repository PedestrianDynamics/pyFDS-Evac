"""``pyfds-evac init``: exit status numbers and the effect of two flags (#836).

The expected values come from the pages and the ``--help`` text, not from
``cli_init``: the exit status table of ``docs/usage.md`` (0 runnable, 3
written but not runnable, 1 error, with ``--check``: 0 ready, 3 an item
missing), ``--no-fds`` leaves ``--fds-dir`` out of the run command, and
``--z-band LO HI`` is the absolute height band whose obstructions block
walking (default 0.1 to 1.8 m above the floor).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from shapely import wkt as shapely_wkt
from shapely.geometry import box

from pyfds_evac import cli_init

ROOT = Path(__file__).resolve().parents[1]

# Two 10 x 10 m meshes side by side (x 0-20, z 0-3) on a 0.1 m grid, one OPEN
# vent on x = 0. {records} adds records.
HALL = """\
&HEAD CHID='plain' /
&MESH IJK=20,20,30, XB=0,10,0,10,0,3 /
&MESH IJK=20,20,30, XB=10,20,0,10,0,3 /
{vent}
&TIME T_END=120. /
{records}
"""
VENT = "&VENT XB=0,0,4,6,0,2, SURF_ID='OPEN' /"
SLICES = (
    "&SLCF PBZ=1.6, QUANTITY='EXTINCTION COEFFICIENT' /",
    "&SLCF PBZ=1.6, QUANTITY='VOLUME FRACTION', SPEC_ID='CARBON MONOXIDE' /",
    "&SLCF PBZ=1.6, QUANTITY='VOLUME FRACTION', SPEC_ID='CARBON DIOXIDE' /",
    "&SLCF PBZ=1.6, QUANTITY='VOLUME FRACTION', SPEC_ID='OXYGEN' /",
)


def _deck(tmp_path, *records: str, vent: str = VENT) -> Path:
    path = tmp_path / "hall.fds"
    path.write_text(HALL.format(vent=vent, records="\n".join(records)), "utf-8")
    return path


def _status(*argv) -> int:
    """The exit status of the installed command, in a fresh process."""
    proc = subprocess.run(
        [sys.executable, "-m", "pyfds_evac", "init", *map(str, argv)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    return proc.returncode


# --- exit status ---------------------------------------------------------------


def test_exit_status_numbers_of_a_plain_init(tmp_path):
    """usage.md: 0 written and runnable; 3 written but not runnable; 1 error."""
    runnable = _deck(tmp_path)
    assert _status(runnable, "-o", tmp_path / "ok", "--agents", 5) == 0
    no_exit = _deck(tmp_path, vent="")
    assert _status(no_exit, "-o", tmp_path / "none", "--agents", 5) == 3
    assert (tmp_path / "none" / "config.json").is_file()
    assert _status(tmp_path / "missing.fds", "-o", tmp_path / "bad") == 1
    assert not (tmp_path / "bad").exists()


def test_exit_status_numbers_of_a_check(tmp_path):
    """usage.md: with --check, 0 the deck has what the run reads; 3 an item is missing."""
    ready = _deck(tmp_path, *SLICES)
    assert _status(ready, "--check") == 0
    assert _status(_deck(tmp_path), "--check") == 3
    assert _status(tmp_path / "missing.fds", "--check") == 1


def test_a_malformed_exit_is_an_argument_error(tmp_path, capsys):
    """--exit takes x0,y0,x1,y1[,ior]: four or five numbers, not six."""
    deck = _deck(tmp_path)
    for spec in ("0,4,0,6", "0,4,0,6,-1"):
        out = tmp_path / spec
        assert cli_init.main([str(deck), "-o", str(out), "--exit", spec]) == 0
    capsys.readouterr()
    bad = cli_init.main(
        [str(deck), "-o", str(tmp_path / "six"), "--exit", "0,4,0,6,-1,9"]
    )
    assert bad == 1
    assert "need x0,y0,x1,y1[,ior]" in capsys.readouterr().err


# --- --no-fds ------------------------------------------------------------------


def _init(tmp_path, capsys, *extra) -> tuple[str, dict]:
    out = tmp_path / "out"
    assert cli_init.main([str(_deck(tmp_path)), "-o", str(out), *extra]) == 0
    report = json.loads((out / "import_report.json").read_text("utf-8"))
    return capsys.readouterr().out, report["recommendations"]


def test_fds_output_next_to_the_deck_goes_into_the_run_command(tmp_path, capsys):
    (tmp_path / "plain.smv").write_text("", encoding="utf-8")
    shown, recommended = _init(tmp_path, capsys, "--agents", "5")
    assert recommended["fds_dir"] == str(tmp_path)
    assert f"--fds-dir {tmp_path}" in shown


def test_no_fds_leaves_the_fds_dir_out_of_the_run_command(tmp_path, capsys):
    """usage.md: when <CHID>.smv lies next to the deck, --no-fds leaves --fds-dir out."""
    (tmp_path / "plain.smv").write_text("", encoding="utf-8")
    shown, recommended = _init(tmp_path, capsys, "--agents", "5", "--no-fds")
    assert recommended["fds_dir"] is None
    assert "--fds-dir" not in shown.split("Next:")[1]


# --- --z-band ------------------------------------------------------------------

# A 1 m wide beam across the hall at z 2.0-2.4 m, above the default band
# (0.1 to 1.8 m above the floor at z 0).
BEAM = "&OBST XB=2,3,0,10,2.0,2.4 /"


def _walkable(tmp_path, *extra):
    out = tmp_path / "out"
    deck = _deck(tmp_path, BEAM)
    assert cli_init.main([str(deck), "-o", str(out), "--agents", "5", *extra]) == 0
    return shapely_wkt.loads((out / "geometry.wkt").read_text("utf-8"))


def test_a_beam_above_the_default_band_does_not_block_walking(tmp_path):
    assert _walkable(tmp_path).equals(box(0, 0, 20, 10))


def test_z_band_makes_the_beam_block_walking(tmp_path):
    """Band 0 to 3 m takes the beam in: it cuts x 2-3 across the hall, and only
    the part with the exit (x 0-2, 20 m2) is kept."""
    walkable = _walkable(tmp_path, "--z-band", "0", "3")
    assert walkable.equals(box(0, 0, 2, 10))
    assert walkable.area == pytest.approx(20.0)
