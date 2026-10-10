"""``pyfds-evac init --check`` and the slice check of a plain init (#604).

The check reads the deck only. Its rules copy the runtime's: horizontal
slices, nearest z to the smoke slice height, declaration order on a tie;
extinction, CO, CO2 and O2 slices and ``&TIME T_END`` are required, heat
slices, the output interval and the yields are reported.
"""

from __future__ import annotations

import json
import types
from pathlib import Path

import pytest

from pyfds_evac import cli_init

ROOT = Path(__file__).resolve().parents[1]
GUIDE = ROOT / "assets" / "fds_evac_guide"
T_JUNCTION = ROOT / "assets" / "t_junction" / "t_junction.fds"

# One plain mesh, z 0-3 on a 0.1 m grid, so that the deck's z are on it:
# the check runs at z_floor 0 + 1.6 m.
PLAIN = """\
&HEAD CHID='plain' /
&MESH IJK=20,20,30, XB=0,10,0,10,0,3 /
&VENT XB=0,0,4,6,0,2, SURF_ID='OPEN' /
{time}
{records}
"""
TIME = "&TIME T_END=120. /"
GASES = (
    "&SLCF PBZ=1.6, QUANTITY='VOLUME FRACTION', SPEC_ID='CARBON MONOXIDE' /",
    "&SLCF PBZ=1.6, QUANTITY='VOLUME FRACTION', SPEC_ID='CARBON DIOXIDE' /",
    "&SLCF PBZ=1.6, QUANTITY='VOLUME FRACTION', SPEC_ID='OXYGEN' /",
)
SOOT = "&SLCF PBZ=1.6, QUANTITY='EXTINCTION COEFFICIENT' /"


def _deck(tmp_path, *records: str, time: str = TIME) -> Path:
    path = tmp_path / "plain.fds"
    path.write_text(PLAIN.format(time=time, records="\n".join(records)), "utf-8")
    return path


def _check(capsys, *argv) -> tuple[int, list[str]]:
    status = cli_init.main([str(a) for a in argv])
    return status, capsys.readouterr().out.splitlines()


def _line(lines: list[str], label: str) -> str:
    [line] = [x for x in lines if x[4:].startswith(label)]
    return line


def _entry(tmp_path, deck: Path, key: str) -> dict:
    report = _report(tmp_path, deck)
    return report["recommendations"]["slices"][key]


def _report(tmp_path, deck: Path, *extra) -> dict:
    out = tmp_path / "scenario"
    cli_init.main([str(deck), "-o", str(out), *extra])
    return json.loads((out / "import_report.json").read_text("utf-8"))


# --- reference decks ---------------------------------------------------------------


def test_t_junction_is_ready_and_prints_both_heights(capsys):
    status, lines = _check(capsys, T_JUNCTION, "--check")
    assert status == cli_init.EXIT_OK
    for label in ("Extinction", "CO ", "CO2", "O2"):
        line = _line(lines, label)
        assert line.startswith("  ✓")
        assert "z 2 m (requested 1.6 m" in line
    assert "none" in _line(lines, "Temperature")
    assert _line(lines, "T_END").startswith("  ✓ T_END       300 s")
    assert "1 s (&DUMP DT_SLCF)" in _line(lines, "DT_SLCF")
    assert not [x for x in lines if x.startswith("  !")]


def test_smoke_speed_deck_has_extinction_but_no_gases(capsys):
    deck = GUIDE / "Verification" / "SmokeSpeed_Test" / "soot_vs_speed_500.fds"
    status, lines = _check(capsys, deck, "--check")
    assert status == cli_init.EXIT_NOT_RUNNABLE
    # HUMAN_SMOKE_HEIGHT=1.50 in the deck's &PERS sets the height.
    assert "z 1.5 m (requested 1.5 m" in _line(lines, "Extinction")
    for label in ("CO ", "CO2", "O2"):
        assert _line(lines, label).startswith("  ✗")
    assert _line(lines, "SOOT_YIELD").startswith("  !")
    assert sum("FED needs CO, CO2 and O2" in x for x in lines) == 1


def test_fed_verification_gases_are_vertical_only(capsys):
    deck = GUIDE / "Verification" / "FED_Test" / "fed_verificationA.fds"
    status, lines = _check(capsys, deck, "--check")
    assert status == cli_init.EXIT_NOT_RUNNABLE
    for label in ("CO ", "CO2", "O2"):
        assert "vertical only, the run reads none" in _line(lines, label)
    assert _line(lines, "Extinction").startswith("  ✗")


def test_example_temperature_is_vertical_only_and_not_failed(capsys):
    deck = GUIDE / "Examples" / "evac_example1aA.fds"
    status, lines = _check(capsys, deck, "--check")
    assert status == cli_init.EXIT_NOT_RUNNABLE
    assert _line(lines, "Temperature").startswith("  · Temperature vertical only")
    assert _line(lines, "Extinction").startswith("  ✗")


def test_sportshall_coarse_output_interval_warns(capsys):
    deck = GUIDE / "Validation" / "SportsHall" / "sportshall_logN2.fds"
    status, lines = _check(capsys, deck, "--check")
    assert status == cli_init.EXIT_NOT_RUNNABLE
    assert _line(lines, "DT_SLCF").startswith("  ! DT_SLCF     1e+06 s")


def test_unreadable_deck_exits_1(capsys):
    deck = GUIDE / "Validation" / "OfficeStairs" / "OfficeStairsV2_1p0.fds"
    assert cli_init.main([str(deck), "--check"]) == cli_init.EXIT_ERROR
    assert "no closing '/'" in capsys.readouterr().err


# --- slice rules -------------------------------------------------------------------


def test_all_present_is_ready(tmp_path, capsys):
    status, lines = _check(capsys, _deck(tmp_path, SOOT, *GASES), "--check")
    assert status == cli_init.EXIT_OK
    assert lines[-1] == "✓ The deck has what a pyFDS-Evac run reads."


def test_horizontal_xb_slices_count_and_vertical_xb_do_not(tmp_path, capsys):
    records = (
        "&SLCF XB=0,10,0,10,1.6,1.6, QUANTITY='EXTINCTION COEFFICIENT' /",
        "&SLCF XB=5,5,0,10,0,3, QUANTITY='VOLUME FRACTION', SPEC_ID='OXYGEN' /",
        *GASES[:2],
    )
    status, lines = _check(capsys, _deck(tmp_path, *records), "--check")
    assert status == cli_init.EXIT_NOT_RUNNABLE
    assert _line(lines, "Extinction").startswith("  ✓")
    assert "vertical only" in _line(lines, "O2")


@pytest.mark.parametrize("xb", ["5,5,0,10,1.6,1.6", "0,10,5,5,1.6,1.6"])
def test_line_xb_slices_are_vertical_as_in_fdsreader(tmp_path, capsys, xb):
    # fdsreader tests a collapsed x, then y, then z (orientation 1, 2, 3);
    # the runtime reads only orientation 3, so a line at z 1.6 is not read.
    line = f"&SLCF XB={xb}, QUANTITY='EXTINCTION COEFFICIENT' /"
    status, lines = _check(capsys, _deck(tmp_path, line, *GASES), "--check")
    assert status == cli_init.EXIT_NOT_RUNNABLE
    assert "vertical only, the run reads none" in _line(lines, "Extinction")


def test_orientation_rule_matches_fdsreader(monkeypatch):
    """The deck rule against fdsreader's own Slice orientation (x, y, z order)."""
    from fdsreader.slcf.slice import Slice, SubSlice
    from fdsreader.utils import Extent

    from pyfds_evac.core.fds_deck import parse_fds_text
    from pyfds_evac.core.fds_import_slices import _slice
    from pyfds_evac.core.fds_sampling import _is_horizontal

    monkeypatch.setattr(SubSlice, "_load_times", lambda self: [])
    cases = {
        "0,10,0,10,1.6,1.6": "horizontal",
        "5,5,0,10,1.6,1.6": "vertical",
        "0,10,5,5,1.6,1.6": "vertical",
        "5,5,0,10,0,3": "vertical",
        "0,10,5,5,0,3": "vertical",
        "0,10,0,10,0,3": "volume",
    }
    for xb, ours in cases.items():
        mesh_data = {
            "mesh": types.SimpleNamespace(id="m"),
            "quantity": "TEMPERATURE",
            "short_name": "temp",
            "unit": "C",
            "filename": "x.sf",
            "dimension": None,
            "extent": Extent(*(float(v) for v in xb.split(","))),
        }
        runtime = Slice("", "1", False, [mesh_data])
        deck = parse_fds_text(f"&SLCF XB={xb}, QUANTITY='TEMPERATURE' /")
        checked = _slice(deck.group("SLCF")[0])
        assert checked.orientation == ours, xb
        assert _is_horizontal(runtime) == (ours == "horizontal"), xb


def test_evacuation_slices_are_ignored(tmp_path, capsys):
    evac = "&SLCF PBZ=1.6, QUANTITY='EXTINCTION COEFFICIENT', EVACUATION=.TRUE. /"
    status, lines = _check(capsys, _deck(tmp_path, evac, *GASES), "--check")
    assert status == cli_init.EXIT_NOT_RUNNABLE
    assert "none" in _line(lines, "Extinction")


def test_soot_spec_id_counts_and_another_aerosol_does_not(tmp_path, capsys):
    soot = "&SLCF PBZ=1.6, QUANTITY='EXTINCTION COEFFICIENT', SPEC_ID='SOOT' /"
    status, _ = _check(capsys, _deck(tmp_path, soot, *GASES), "--check")
    assert status == cli_init.EXIT_OK
    dust = "&SLCF PBZ=1.6, QUANTITY='EXTINCTION COEFFICIENT', SPEC_ID='DUST' /"
    status, lines = _check(capsys, _deck(tmp_path, dust, *GASES), "--check")
    assert status == cli_init.EXIT_NOT_RUNNABLE
    assert "SPEC_ID DUST is not the soot one" in _line(lines, "Extinction")


def test_extinction_flag_is_named_as_the_trap(tmp_path, capsys):
    trap = "&SLCF PBZ=1.6, QUANTITY='EXTINCTION' /"
    status, lines = _check(capsys, _deck(tmp_path, trap, *GASES), "--check")
    assert status == cli_init.EXIT_NOT_RUNNABLE
    line = _line(lines, "Extinction")
    assert "QUANTITY='EXTINCTION' is FDS's combustion-suppression flag" in line
    assert "fix: add &SLCF PBZ=1.6, QUANTITY='EXTINCTION COEFFICIENT' /" in line


def test_co_without_co2_fails_the_gate_once(tmp_path, capsys):
    records = (SOOT, GASES[0], GASES[2])
    status, lines = _check(capsys, _deck(tmp_path, *records), "--check")
    assert status == cli_init.EXIT_NOT_RUNNABLE
    assert _line(lines, "CO ").startswith("  ✓")
    assert _line(lines, "CO2").startswith("  ✗ CO2         none")
    assert lines[-1].startswith("✗ 1 item missing")
    assert sum("FED needs CO, CO2 and O2" in x for x in lines) == 1


def test_far_slice_warns_without_failing(tmp_path, capsys):
    far = "&SLCF PBZ=2.5, QUANTITY='EXTINCTION COEFFICIENT' /"
    status, lines = _check(capsys, _deck(tmp_path, far, *GASES), "--check")
    assert status == cli_init.EXIT_OK
    line = _line(lines, "Extinction")
    assert line.startswith("  ! Extinction  z 2.5 m (requested 1.6 m")
    assert "0.90 m away" in line


def test_nearest_of_several_matches_the_runtime_rule(tmp_path):
    from pyfds_evac.core.fds_deck import parse_fds_deck
    from pyfds_evac.core.fds_import_slices import check_slices
    from pyfds_evac.core.fds_sampling import select_horizontal_slice

    zs = (0.5, 2.1, 1.1, 2.6)  # 1.1 and 2.1 tie at 1.6; 1.1 is declared second
    records = [f"&SLCF PBZ={z}, QUANTITY='EXTINCTION COEFFICIENT' /" for z in zs]
    deck = parse_fds_deck(
        _deck(tmp_path, "&SLCF PBY=5, QUANTITY='EXTINCTION COEFFICIENT' /", *records)
    )
    for height in (0.0, 1.0, 1.6, 2.4, 3.0):
        fakes = [types.SimpleNamespace(orientation=2, extent=_extent(1.5))] + [
            types.SimpleNamespace(orientation=3, extent=_extent(z)) for z in zs
        ]
        runtime = select_horizontal_slice(fakes, height, "q", "dir")
        item = check_slices(deck, height).items[0]
        assert item.nearest_pbz == runtime.extent.z_start, height


@pytest.mark.parametrize(
    ("case", "quantity", "key"),
    [
        (
            "fed_slice_height",
            "CARBON MONOXIDE VOLUME FRACTION",
            "VOLUME FRACTION CARBON MONOXIDE",
        ),
        ("vis_slice_height", "SOOT EXTINCTION COEFFICIENT", "EXTINCTION COEFFICIENT"),
    ],
)
def test_ranking_on_the_grid_matches_the_runtime_on_tracked_output(case, quantity, key):
    """FDS moves PBZ 1.6 to the 0.5 m grid at 1.5; at 2.0 it ties PBZ 2.5,
    declared first, which the run reads (#687). The deck's z picks 1.6."""
    fdsreader = pytest.importorskip("fdsreader")
    from pyfds_evac.core.fds_deck import parse_fds_deck
    from pyfds_evac.core.fds_import_slices import check_slices
    from pyfds_evac.core.fds_sampling import _slice_z_mid, load_slice_sampler

    folder = ROOT / "assets" / case
    deck = parse_fds_deck(folder / f"{case}.fds")
    sim = fdsreader.Simulation(str(folder / "fds"))
    for height in (0.5, 1.0, 1.6, 1.75, 2.0, 2.4):
        runtime = load_slice_sampler(
            str(folder / "fds"), quantity, simulation=sim, slice_height_m=height
        )
        item = check_slices(deck, height).to_dict()[key]
        assert item["nearest_pbz"] == _slice_z_mid(runtime._slice), height


def test_off_grid_slice_prints_both_z_and_trnz_keeps_the_deck_z(tmp_path, capsys):
    coarse = PLAIN.replace("IJK=20,20,30", "IJK=20,20,6")  # 0.5 m in z
    soot = "&SLCF PBZ=1.6, QUANTITY='EXTINCTION COEFFICIENT' /"
    deck = tmp_path / "coarse.fds"
    deck.write_text(coarse.format(time=TIME, records="\n".join((soot, *GASES))))
    status, lines = _check(capsys, deck, "--check")
    assert status == cli_init.EXIT_OK
    assert "z 1.5 m (deck z 1.6 m, requested 1.6 m" in _line(lines, "Extinction")
    stretched = "&TRNZ IDERIV=0, CC=1, PC=1, MESH_NUMBER=1 /"
    records = "\n".join((stretched, soot, *GASES))
    deck.write_text(coarse.format(time=TIME, records=records))
    status, lines = _check(capsys, deck, "--check")
    assert "z 1.6 m (requested 1.6 m" in _line(lines, "Extinction")
    assert lines[0].endswith(
        "(deck z: &TRNZ stretches the grid, FDS moves a slice onto it):"
    )


# Two meshes side by side, z 0-3: 'fine' with 0.5 m cells, 'coarse' with 1 m.
TWO_GRIDS = (((0, 1, 0, 1, 0, 3), (2, 2, 6)), ((1, 2, 0, 1, 0, 3), (2, 2, 3)))


def _synthetic_case(folder: Path, writes, grids=TWO_GRIDS) -> None:
    """A two-mesh .smv of *grids* with one slice that FDS wrote as *writes*.

    *writes* holds (SLCF or SLCC, mesh number, node K) per mesh written;
    the .sf files hold a header and no frame, enough for the extent.
    """

    def axis(name, lo, hi, n):
        rows = "".join(f"{i} {lo + (hi - lo) * i / n}\n" for i in range(n + 1))
        return f"{name}\n 0\n{rows}\n"

    text = "CHID\n syn\n\nNMESHES\n 2\n\n"
    for n, ((x0, x1, y0, y1, z0, z1), (i, j, k)) in enumerate(grids, start=1):
        text += f"OFFSET\n 0 0 0\n\nGRID MESH_{n}\n {i} {j} {k} 0 0 0 0 0 0\n\n"
        text += f"PDIM\n {x0} {x1} {y0} {y1} {z0} {z1} 0 0 0\n\n"
        text += axis("TRNX", x0, x1, i) + axis("TRNY", y0, y1, j)
        text += axis("TRNZ", z0, z1, k) + "OBST\n 0\n\nVENT\n 0 0\n\nCVENT\n 0\n\n"
    for kind, mesh, k in writes:
        sf = f"syn_{mesh}_1.sf"
        (folder / sf).write_bytes(b"\0" * (3 * 38 + 32))  # fdsreader's header size
        cc_val = 1 if kind == "SLCC" else 0  # FDS dump.f90 writes CC_VAL
        text += f"{kind} {mesh} # STRUCTURED & 0 2 0 2 {k} {k} ! 1 {cc_val} 3\n"
        text += f" {sf}\n SOOT EXTINCTION COEFFICIENT\n ext\n 1/m\n\n"
    (folder / "syn.smv").write_text(text)


# The node K that FDS 6.10 READ_SLCF (read.f90) writes per mesh: a node
# slice NINT((z - ZS)/DZ), halves up; a cell-centred one the last cell
# whose centre is within DZ/2 + 1e-10 m; MESH_NUMBER keeps that mesh only.
COARSE_FIRST = tuple(reversed(TWO_GRIDS))


@pytest.mark.parametrize(
    ("options", "writes", "grids", "z"),
    [
        ("PBZ=1.6", (("SLCF", 1, 3), ("SLCF", 2, 2)), TWO_GRIDS, 1.5),  # lowest
        ("PBZ=1.6", (("SLCF", 1, 2), ("SLCF", 2, 3)), COARSE_FIRST, 1.5),
        ("PBZ=1.6, MESH_NUMBER=2", (("SLCF", 2, 2),), TWO_GRIDS, 2.0),
        (
            "PBZ=1.6, CELL_CENTERED=.TRUE.",
            (("SLCC", 1, 4), ("SLCC", 2, 2)),
            TWO_GRIDS,
            2.0,
        ),
        # On a face both cells are within DZ/2 + 1e-10 m; the last one wins.
        (
            "PBZ=2.0, CELL_CENTERED=.TRUE.",
            (("SLCC", 1, 5), ("SLCC", 2, 3)),
            TWO_GRIDS,
            2.5,
        ),
        ("PBZ=1.75, MESH_NUMBER=1", (("SLCF", 1, 4),), TWO_GRIDS, 2.0),  # 3.5 up
        ("PBZ=1.25, MESH_NUMBER=1", (("SLCF", 1, 3),), TWO_GRIDS, 1.5),  # 2.5 up
    ],
    ids=[
        "two-grids",
        "coarse-first",
        "mesh-number",
        "cell-centred",
        "cell-centred-face",
        "half-cell",
        "half-cell-even",
    ],
)
def test_grid_z_matches_fdsreaders_extent(tmp_path, options, writes, grids, z):
    """The check's z is the one fdsreader gives the run (#687)."""
    fdsreader = pytest.importorskip("fdsreader")
    from pyfds_evac.core.fds_deck import parse_fds_text
    from pyfds_evac.core.fds_import_slices import check_slices
    from pyfds_evac.core.fds_sampling import _slice_z_mid

    meshes = "".join(
        f"&MESH IJK={','.join(map(str, ijk))}, XB={','.join(map(str, xb))} /\n"
        for xb, ijk in grids
    )
    deck = parse_fds_text(
        f"{meshes}&SLCF {options}, QUANTITY='EXTINCTION COEFFICIENT' /\n"
    )
    _synthetic_case(tmp_path, writes, grids)
    [runtime] = fdsreader.Simulation(str(tmp_path)).slices
    assert _slice_z_mid(runtime) == z
    item = check_slices(deck, 1.6).to_dict()["EXTINCTION COEFFICIENT"]
    assert item["nearest_pbz"] == z


def test_evacuation_only_deck_does_not_get_the_trnz_note(tmp_path, capsys):
    evac = PLAIN.replace("XB=0,10,0,10,0,3 /", "XB=0,10,0,10,0,3, EVACUATION=.TRUE. /")
    deck = tmp_path / "evac.fds"
    deck.write_text(evac.format(time=TIME, records="\n".join((SOOT, *GASES))))
    _, lines = _check(capsys, deck, "--check")
    assert "&TRNZ" not in lines[0]
    assert "(z on the mesh grid, where FDS writes the slice)" in lines[0]


# A second mesh above the plain one, z 3-6, and an evacuation mesh.
UPPER = "&MESH IJK=20,20,30, XB=0,10,0,10,3,6 /"
EVAC_MESH = "&MESH IJK=20,20,1, XB=0,10,0,10,1,2, EVACUATION=.TRUE. /"
LOW_GASES = tuple(g.replace("PBZ=1.6", "PBZ=1.5") for g in GASES)


@pytest.mark.parametrize(
    ("mesh", "extra", "soot", "reason"),
    [
        (
            "IJK=20,20,15, XB=0,10,0,10,0,1.5",
            (),
            "PBZ=1.6",
            "outside every fire &MESH",
        ),
        (
            "",
            (UPPER,),
            "PBZ=1.6, MESH_NUMBER=2",
            "&MESH 2 (MESH_NUMBER) does not hold it",
        ),
        ("", (UPPER,), "PBZ=1.6, MESH_NUMBER=9", "MESH_NUMBER 9 names no fire &MESH"),
        (
            "",
            (EVAC_MESH, UPPER),
            "PBZ=1.6, MESH_NUMBER=2",
            "&MESH 2 (MESH_NUMBER) does not hold it",
        ),
        ("", (), "XB=20,30,0,10,1.6,1.6", "outside every fire &MESH"),
        (
            "IJK=20,20,15, XB=0,10,0,10,0,1.5",
            ("&TRNZ IDERIV=0, CC=1, PC=1, MESH_NUMBER=1 /",),
            "PBZ=1.6",
            "outside every fire &MESH",
        ),
    ],
    ids=["above-every-mesh", "mesh-number", "no-such-mesh", "evac-mesh", "xy", "trnz"],
)
def test_slice_fds_culls_is_missing_and_named(
    tmp_path, capsys, mesh, extra, soot, reason
):
    """FDS writes no slice it culls (READ_SLCF, read.f90): the check fails
    as with no extinction slice, and names the slice it dropped (#705)."""
    text = PLAIN.replace("&VENT", "\n".join((*extra, "&VENT")))
    if mesh:
        text = text.replace("IJK=20,20,30, XB=0,10,0,10,0,3", mesh)
    records = (f"&SLCF {soot}, QUANTITY='EXTINCTION COEFFICIENT' /", *LOW_GASES)
    deck = tmp_path / "culled.fds"
    text = text.format(time=TIME, records="\n".join(records))
    deck.write_text(text)
    line = text.splitlines().index(records[0]) + 1
    # The evacuation mesh makes an FDS+Evac deck: fix the height there too.
    status, lines = _check(capsys, deck, "--check", "--smoke-slice-height", "1.6")
    assert status == cli_init.EXIT_NOT_RUNNABLE
    assert _line(lines, "Extinction").startswith(
        "  ✗ Extinction  none (requested z 1.6 m)"
    )
    assert _line(lines, "CO2").startswith("  ✓")
    dropped = [x for x in lines if x.startswith("  dropped &SLCF")]
    assert dropped == [
        f"  dropped &SLCF line {line} (EXTINCTION COEFFICIENT, "
        f"z 1.6 m): {reason}, so FDS writes no such slice"
    ]


def test_culled_slice_does_not_outrank_a_written_one(tmp_path, capsys):
    near = "&SLCF PBZ=1.6, MESH_NUMBER=9, QUANTITY='EXTINCTION COEFFICIENT' /"
    far = "&SLCF PBZ=2.0, QUANTITY='EXTINCTION COEFFICIENT' /"
    status, lines = _check(capsys, _deck(tmp_path, near, far, *GASES), "--check")
    assert status == cli_init.EXIT_OK
    assert "z 2 m (requested 1.6 m" in _line(lines, "Extinction")


def test_slice_on_the_mesh_top_is_kept(tmp_path, capsys):
    """READ_SLCF keeps z = ZF: it culls only XB(5) > ZF (#705)."""
    low = PLAIN.replace(
        "IJK=20,20,30, XB=0,10,0,10,0,3", "IJK=20,20,16, XB=0,10,0,10,0,1.6"
    )
    deck = tmp_path / "top.fds"
    deck.write_text(low.format(time=TIME, records="\n".join((SOOT, *GASES))))
    status, lines = _check(capsys, deck, "--check")
    assert status == cli_init.EXIT_OK
    assert not any(x.startswith("  dropped") for x in lines)


def test_report_lists_the_dropped_slices(tmp_path):
    culled = "&SLCF PBZ=1.6, MESH_NUMBER=9, QUANTITY='EXTINCTION COEFFICIENT' /"
    report = _report(tmp_path, _deck(tmp_path, culled, *GASES))
    rec = report["recommendations"]
    assert rec["slice_check_ok"] is False
    assert rec["slices_dropped"] == [
        {
            "line": 5,
            "quantity": "EXTINCTION COEFFICIENT",
            "spec_id": None,
            "orientation": "horizontal",
            "z": 1.6,
            "reason": "MESH_NUMBER 9 names no fire &MESH",
        }
    ]
    assert rec["slices"]["EXTINCTION COEFFICIENT"]["status"] == "missing"


def _culls(text: str) -> list[str]:
    """The reasons :func:`check_slices` drops the slices of *text*."""
    from pyfds_evac.core.fds_deck import parse_fds_text
    from pyfds_evac.core.fds_import_slices import check_slices

    return [d["reason"] for d in check_slices(parse_fds_text(text), 1.6).dropped]


MESH_0_3 = "&MESH IJK=20,20,30, XB=0,10,0,10,0,3 /\n"


def _soot(options: str) -> str:
    return f"&SLCF {options}, QUANTITY='EXTINCTION COEFFICIENT' /\n"


@pytest.mark.parametrize(
    ("options", "reasons"),
    [
        ("PBZ=3.0", []),  # z = ZF: READ_SLCF culls only XB(5) > ZF
        ("PBZ=0.0", []),  # z = ZS: culls only XB(6) < ZS
        ("PBZ=3.0000000005", ["outside every fire &MESH"]),  # no tolerance
        ("PBZ=-0.0000000005", ["outside every fire &MESH"]),
        ("XB=10,20,0,10,1.6,1.6", ["outside every fire &MESH"]),  # x contact
        ("XB=0,10,-5,0,1.6,1.6", ["outside every fire &MESH"]),  # y contact
        ("XB=5,20,-5,5,1.6,1.6", []),  # partial overlap: clipped to the mesh
        ("PBX=20, PBZ=1.6", ["outside every fire &MESH"]),  # every PB plane
        ("PBY=-1, PBZ=1.6", ["outside every fire &MESH"]),
        ("PBX=5, PBZ=1.6", []),
        ("PBX=10, PBZ=1.6", ["outside every fire &MESH"]),  # IOR 3: x = XF culls
    ],
)
def test_cull_bounds_follow_read_slcf_exactly(options, reasons):
    """FDS 6.10 READ_SLCF: inclusive on the IOR axis, strict on the
    others of a planar slice, no tolerance (#705)."""
    assert _culls(MESH_0_3 + _soot(options)) == reasons


def test_pbx_with_pbz_is_a_vertical_line_the_run_skips(tmp_path, capsys):
    """fdsreader tests x first: PBX with PBZ is a line it reads as an x
    slice, which the run does not read (#705)."""
    line = "&SLCF PBX=5, PBZ=1.6, QUANTITY='EXTINCTION COEFFICIENT' /"
    status, lines = _check(capsys, _deck(tmp_path, line, *GASES), "--check")
    assert status == cli_init.EXIT_NOT_RUNNABLE
    assert "vertical only, the run reads none" in _line(lines, "Extinction")


def test_fds67_deck_keeps_a_slice_touching_a_mesh():
    """A deck with evacuation meshes runs on FDS 6.7.6, whose READ_SLCF
    culls only lo > F or hi < S, on every axis (#705)."""
    evac = "&MESH IJK=10,10,1, XB=0,10,0,10,1,2, EVACUATION=.TRUE. /\n"
    touching = _soot("XB=10,20,0,10,1.6,1.6")
    assert _culls(MESH_0_3 + touching) == ["outside every fire &MESH"]
    assert _culls(MESH_0_3 + evac + touching) == []


def test_mesh_number_counts_mult_copies_and_skips_evacuation_meshes():
    """FDS numbers the MULT copies in order; the fire run of FDS 6.7.6
    skips evacuation meshes (read.f90 of c9da70d7a0, line 750)."""
    deck = (
        "&MULT ID='Z', DZ=3, K_UPPER=1 /\n"
        "&MESH IJK=20,20,30, XB=0,10,0,10,0,3, MULT_ID='Z' /\n"  # 1, 2
        "&MESH IJK=10,10,1, XB=0,10,0,10,1,2, EVACUATION=.TRUE. /\n"
        "&MESH IJK=20,20,30, XB=0,10,0,10,6,9 /\n"  # 3
    )
    assert _culls(deck + _soot("PBZ=1.6, MESH_NUMBER=1")) == []
    assert _culls(deck + _soot("PBZ=1.6, MESH_NUMBER=2")) == [
        "&MESH 2 (MESH_NUMBER) does not hold it"
    ]
    assert _culls(deck + _soot("PBZ=7, MESH_NUMBER=3")) == []
    assert _culls(deck + _soot("PBZ=7, MESH_NUMBER=4")) == [
        "MESH_NUMBER 4 names no fire &MESH"
    ]


def test_mult_bounds_are_the_ones_fds_computes():
    """FDS adds (XB + DZ0) + K*DZ: 1.6 here, where XB + (DZ0 + K*DZ) is
    1.5999999999999999 and would cull PBZ=1.6 in mesh 2 (#705)."""
    from pyfds_evac.core.fds_deck import parse_fds_text

    deck = (
        "&MULT ID='Z', DZ0=0.3, DZ=0.6, K_UPPER=1 /\n"
        "&MESH IJK=10,10,6, XB=0,10,0,10,0.1,0.7, MULT_ID='Z' /\n"
    )
    assert parse_fds_text(deck).group("MESH")[1].xb()[5] == 1.6
    assert _culls(deck + _soot("PBZ=1.6, MESH_NUMBER=2")) == []


def test_mesh_number_without_fire_meshes_is_culled():
    """With no fire mesh the check keeps a slice it cannot judge, but not
    one whose MESH_NUMBER names a mesh that does not exist (#705)."""
    evac = "&MESH IJK=10,10,1, XB=0,10,0,10,0,3, EVACUATION=.TRUE. /\n"
    assert _culls(evac + _soot("PBZ=1.6")) == []
    assert _culls(evac + _soot("PBZ=1.6, MESH_NUMBER=9")) == [
        "MESH_NUMBER 9 names no fire &MESH"
    ]


def _extent(z: float):
    return types.SimpleNamespace(z_start=z, z_end=z)


def test_no_t_end_fails(tmp_path, capsys):
    status, lines = _check(capsys, _deck(tmp_path, SOOT, *GASES, time=""), "--check")
    assert status == cli_init.EXIT_NOT_RUNNABLE
    line = _line(lines, "T_END")
    assert "FDS stops at its default T_END of 1 s" in line
    assert "fix: add &TIME T_END=" in line
    # DT_SLCF then comes from FDS's T_END and NFRAMES defaults.
    assert "0.001 s ((T_END - T_BEGIN)/NFRAMES, NFRAMES 1000)" in _line(
        lines, "DT_SLCF"
    )


def test_coarse_dt_slcf_warns(tmp_path, capsys):
    dump = "&DUMP NFRAMES=40 /"  # 120 s / 40 = 3 s
    status, lines = _check(capsys, _deck(tmp_path, dump, SOOT, *GASES), "--check")
    assert status == cli_init.EXIT_OK
    line = _line(lines, "DT_SLCF")
    assert line.startswith("  ! DT_SLCF     3 s")
    assert "coarser than the run's smoke update interval of 1 s" in line


def test_intensity_without_temperature_at_its_z_warns(tmp_path, capsys):
    heat = (
        "&SLCF PBZ=1.6, QUANTITY='TEMPERATURE' /",
        "&SLCF PBZ=1.2, QUANTITY='INTEGRATED INTENSITY' /",
    )
    status, lines = _check(capsys, _deck(tmp_path, SOOT, *GASES, *heat), "--check")
    assert status == cli_init.EXIT_OK
    assert "z 1.6 m; needed for --enable-heat-fed" in _line(lines, "Temperature")
    line = _line(lines, "Intensity")
    assert line.startswith("  ! Intensity   z 1.2 m")
    assert "no TEMPERATURE slice at z 1.2 m" in line


def test_smoke_slice_height_moves_the_requested_z(tmp_path, capsys):
    deck = _deck(tmp_path, SOOT, *GASES)
    status, lines = _check(capsys, deck, "--check", "--smoke-slice-height", "2.5")
    assert status == cli_init.EXIT_OK
    assert "z 1.6 m (requested 2.5 m" in _line(lines, "Extinction")


# --- form ------------------------------------------------------------------------


@pytest.mark.parametrize(
    "extra",
    [
        ["-o", "out"],
        ["--walkable", "w.wkt"],
        ["--exit", "0,4,0,6"],
        ["--agents", "5"],
        ["--exit-depth", "0.5"],
        ["--force"],
        ["--no-fds"],
        ["-v"],
        ["--agents", "0"],
        ["--exit-depth", "0"],
        ["--exit-depth", "-0.0"],
    ],
)
def test_check_rejects_write_options(tmp_path, capsys, extra):
    deck = _deck(tmp_path, SOOT, *GASES)
    assert cli_init.main([str(deck), "--check", *extra]) == cli_init.EXIT_ERROR
    assert "--check writes nothing" in capsys.readouterr().err


def test_smoke_slice_height_needs_check(tmp_path, capsys):
    deck = _deck(tmp_path, SOOT, *GASES)
    argv = [str(deck), "--smoke-slice-height", "2"]
    assert cli_init.main(argv) == cli_init.EXIT_ERROR
    assert "--smoke-slice-height needs --check" in capsys.readouterr().err
    assert sorted(p.name for p in tmp_path.iterdir()) == ["plain.fds"]


def test_check_writes_nothing(tmp_path, capsys, monkeypatch):
    import builtins
    import os

    deck = _deck(tmp_path, SOOT)
    before = sorted(p.name for p in tmp_path.rglob("*"))
    real_open = builtins.open

    def read_only_open(file, mode="r", *args, **kwargs):
        if any(c in mode for c in "wax+"):
            raise AssertionError(f"--check opened {file} with mode {mode!r}")
        return real_open(file, mode, *args, **kwargs)

    def refuse(*args, **kwargs):
        raise AssertionError(f"--check changed the file system: {args}")

    monkeypatch.setattr(builtins, "open", read_only_open)
    for name in ("mkdir", "makedirs", "replace", "rename", "remove", "rmdir"):
        monkeypatch.setattr(os, name, refuse)
    assert cli_init.main([str(deck), "--check"]) == cli_init.EXIT_NOT_RUNNABLE
    monkeypatch.undo()
    assert sorted(p.name for p in tmp_path.rglob("*")) == before


@pytest.mark.parametrize("value", ["nan", "inf", "-inf"])
def test_non_finite_smoke_slice_height_is_a_usage_error(tmp_path, capsys, value):
    deck = _deck(tmp_path, SOOT, *GASES)
    argv = [str(deck), "--check", f"--smoke-slice-height={value}"]
    assert cli_init.main(argv) == cli_init.EXIT_ERROR
    assert "--smoke-slice-height must be a finite number" in capsys.readouterr().err


def test_check_fds_deck_refuses_a_non_finite_height(tmp_path):
    from pyfds_evac.core.fds_import import FdsImportError, check_fds_deck

    with pytest.raises(FdsImportError, match="finite"):
        check_fds_deck(_deck(tmp_path, SOOT), smoke_slice_height=float("nan"))


def test_ascii_console_maps_the_marks(monkeypatch, capsys):
    printed = []

    def fake_print(text):
        if not printed and not text.isascii():
            printed.append(None)
            raise UnicodeEncodeError("ascii", text, 0, 1, "fake")
        printed.append(text)

    monkeypatch.setattr("builtins.print", fake_print)
    cli_init._emit(["  ✓ a", "  ✗ b", "  · c"])
    assert printed[-1] == "  + a\n  x b\n  - c"


# --- plain init ------------------------------------------------------------------


def test_plain_init_prints_and_records_the_check(tmp_path, capsys):
    deck = _deck(tmp_path, *GASES)
    out = tmp_path / "scenario"
    status = cli_init.main([str(deck), "-o", str(out), "--agents", "5"])
    assert status == cli_init.EXIT_OK  # slices never change init's status
    lines = capsys.readouterr().out.splitlines()
    assert _line(lines, "Extinction").startswith("  ✗")
    assert not [x for x in lines if x.startswith("  · ")]  # compact
    assert any("Details: pyfds-evac init DECK --check" in x for x in lines)
    rec = json.loads((out / "import_report.json").read_text("utf-8"))["recommendations"]
    assert rec["slice_check_ok"] is False
    slices = rec["slices"]
    assert slices["EXTINCTION COEFFICIENT"]["status"] == "missing"
    assert slices["EXTINCTION COEFFICIENT"]["required"] is True
    gas = slices["VOLUME FRACTION CARBON MONOXIDE"]
    assert (gas["nearest_pbz"], gas["ok"], gas["status"]) == (1.6, True, "ok")
    assert gas["z_requested"] == 1.6
    assert gas["orientation_found"] == "horizontal"
    assert {"TEMPERATURE", "INTEGRATED INTENSITY", "T_END", "DT_SLCF"} <= set(slices)
    assert slices["TEMPERATURE"]["required"] is False
    assert (slices["TEMPERATURE"]["nearest_pbz"], slices["TEMPERATURE"]["ok"]) == (
        None,
        False,
    )
    assert slices["T_END"]["ok"] is True
    assert slices["DT_SLCF"]["ok"] is True  # 120 s / 1000 frames


def test_t_junction_report_marks_healthy_items_ok(tmp_path, capsys):
    out = tmp_path / "scenario"
    assert cli_init.main([str(T_JUNCTION), "-o", str(out)]) == cli_init.EXIT_OK
    rec = json.loads((out / "import_report.json").read_text("utf-8"))["recommendations"]
    assert rec["slice_check_ok"] is True
    for key in (
        "EXTINCTION COEFFICIENT",
        "VOLUME FRACTION OXYGEN",
        "T_END",
        "DT_SLCF",
        "optional FED gases",
    ):
        assert rec["slices"][key]["ok"] is True, key
    assert rec["slices"]["EXTINCTION COEFFICIENT"]["nearest_pbz"] == 2.0


def test_plain_init_without_t_end_names_it(tmp_path, capsys):
    deck = _deck(tmp_path, SOOT, *GASES, time="")
    out = tmp_path / "scenario"
    status = cli_init.main([str(deck), "-o", str(out), "--agents", "5"])
    assert status == cli_init.EXIT_OK
    lines = capsys.readouterr().out.splitlines()
    assert _line(lines, "T_END").startswith("  ✗ T_END       none")
    assert any("the ✗ lines say what the run will lack" in x for x in lines)
    assert not any("switches" in x for x in lines)


def test_plain_init_prints_slices_when_the_walkable_step_fails(tmp_path, capsys):
    deck = _deck(tmp_path, SOOT, *GASES)
    empty = tmp_path / "empty.wkt"
    empty.write_text("POLYGON EMPTY", "utf-8")
    argv = [str(deck), "-o", str(tmp_path / "s"), "--walkable", str(empty)]
    assert cli_init.main(argv) == cli_init.EXIT_ERROR
    captured = capsys.readouterr()
    assert "FDS output check at z = 1.6 m" in captured.out
    assert "walkable area (user) is empty" in captured.err
    assert not (tmp_path / "s").exists()
