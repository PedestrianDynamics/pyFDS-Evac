"""Tests for the Smokeview `.prt5` exporter."""

from __future__ import annotations

import os
import struct
import subprocess
from pathlib import Path
from typing import cast

import pandas as pd
import pytest

from pyfds_evac.core import ScenarioResult
from pyfds_evac.core.smv_export import (
    export_agents_to_smv,
    patch_ini_for_avatars,
    patch_smv_file,
    write_agent_prt5,
)


def _read_fortran_record(fh) -> bytes:
    """Read one Fortran-unformatted record; return payload bytes."""
    head = fh.read(4)
    if not head:
        return b""
    (length,) = struct.unpack("<I", head)
    payload = fh.read(length)
    (tail,) = struct.unpack("<I", fh.read(4))
    assert tail == length, f"record length mismatch: {length} vs {tail}"
    return payload


def _read_prt5(path: Path) -> dict:
    """Parse a `.prt5` file written by the exporter back into Python objects."""
    frames: list[dict] = []
    with path.open("rb") as fh:
        (one,) = struct.unpack("<i", _read_fortran_record(fh))
        (version,) = struct.unpack("<i", _read_fortran_record(fh))
        (nclasses,) = struct.unpack("<i", _read_fortran_record(fh))
        numtypes = struct.unpack("<ii", _read_fortran_record(fh))
        n_quantities = numtypes[0]
        quantity_labels: list[tuple[bytes, bytes]] = []
        for _ in range(sum(numtypes)):
            label = _read_fortran_record(fh)
            unit = _read_fortran_record(fh)
            quantity_labels.append((label, unit))
        while True:
            time_rec = _read_fortran_record(fh)
            if not time_rec:
                break
            (t,) = struct.unpack("<f", time_rec)
            (n,) = struct.unpack("<i", _read_fortran_record(fh))
            if n == 0:
                frames.append(
                    {"t": t, "n": 0, "x": [], "y": [], "z": [], "tags": [], "q": []}
                )
                continue
            xyz_bytes = _read_fortran_record(fh)
            assert len(xyz_bytes) == 3 * n * 4
            xs = list(struct.unpack(f"<{n}f", xyz_bytes[0 : 4 * n]))
            ys = list(struct.unpack(f"<{n}f", xyz_bytes[4 * n : 8 * n]))
            zs = list(struct.unpack(f"<{n}f", xyz_bytes[8 * n : 12 * n]))
            tag_bytes = _read_fortran_record(fh)
            tags = list(struct.unpack(f"<{n}i", tag_bytes))
            quantities: list[float] = []
            if n_quantities > 0:
                q_bytes = _read_fortran_record(fh)
                assert len(q_bytes) == n * n_quantities * 4
                quantities = list(struct.unpack(f"<{n * n_quantities}f", q_bytes))
            frames.append(
                {
                    "t": t,
                    "n": n,
                    "x": xs,
                    "y": ys,
                    "z": zs,
                    "tags": tags,
                    "q": quantities,
                }
            )
    return {
        "one": one,
        "version": version,
        "nclasses": nclasses,
        "numtypes": numtypes,
        "quantity_labels": quantity_labels,
        "frames": frames,
    }


@pytest.fixture
def tiny_df() -> pd.DataFrame:
    rows = [
        (0, 1, 1.0, 2.0),
        (0, 2, 3.0, 4.0),
        (10, 1, 1.5, 2.5),
        (10, 2, 3.5, 4.5),
        (20, 2, 4.0, 5.0),
    ]
    return pd.DataFrame(rows, columns=["frame", "id", "x", "y"])


def test_prt5_header_and_frames(tmp_path: Path, tiny_df: pd.DataFrame) -> None:
    out = tmp_path / "demo_agents.prt5"
    write_agent_prt5(out, tiny_df, frame_rate=10.0, z=1.5)
    data = _read_prt5(out)

    assert data["one"] == 1
    assert data["version"] == 600
    assert data["nclasses"] == 1
    assert data["numtypes"] == (0, 0)

    real_frames = [f for f in data["frames"] if f["n"] > 0]
    assert len(real_frames) == 3

    f0 = real_frames[0]
    assert f0["t"] == pytest.approx(0.0)
    assert f0["n"] == 2
    assert f0["x"] == pytest.approx([1.0, 3.0])
    assert f0["y"] == pytest.approx([2.0, 4.0])
    assert f0["z"] == pytest.approx([1.5, 1.5])
    assert f0["tags"] == [1, 2]

    f1 = real_frames[1]
    assert f1["t"] == pytest.approx(1.0)
    assert f1["n"] == 2

    f2 = real_frames[2]
    assert f2["t"] == pytest.approx(2.0)
    assert f2["n"] == 1
    assert f2["tags"] == [2]

    terminator = data["frames"][-1]
    assert terminator["n"] == 0
    assert terminator["t"] == pytest.approx(2.0)


def test_prt5_azimuth_round_trip(tmp_path: Path) -> None:
    import math

    rows = [
        (0, 1, 0.0, 0.0, 1.0, 0.0),  # facing +x → 0°
        (0, 2, 1.0, 1.0, 0.0, 1.0),  # facing +y → 90°
        (10, 1, 0.5, 0.0, -1.0, 0.0),  # facing -x → 180°
        (10, 2, 1.0, 1.5, 0.0, -1.0),  # facing -y → 270°
    ]
    df = pd.DataFrame(rows, columns=["frame", "id", "x", "y", "ori_x", "ori_y"])
    out = tmp_path / "agents.prt5"
    write_agent_prt5(out, df, frame_rate=10.0, z=1.0, with_azimuth=True)
    data = _read_prt5(out)

    assert data["numtypes"] == (1, 0)
    assert len(data["quantity_labels"]) == 1
    label, unit = data["quantity_labels"][0]
    assert label.strip() == b"body angle"
    assert unit.strip() == b"deg"
    assert (
        len(label) == 30 and len(unit) == 30
    )  # Smokeview expects fixed 30-char records
    real_frames = [f for f in data["frames"] if f["n"] > 0]
    assert real_frames[0]["q"] == pytest.approx([0.0, 90.0])
    assert real_frames[1]["q"] == pytest.approx([180.0, 270.0])
    # Check Smokeview convention: degrees, range [0, 360)
    for f in real_frames:
        for q in f["q"]:
            assert 0.0 <= q < 360.0 or math.isclose(q, 0.0, abs_tol=1e-4)


def test_prt5_empty_trajectory(tmp_path: Path) -> None:
    empty = pd.DataFrame(columns=["frame", "id", "x", "y"])
    out = tmp_path / "empty.prt5"
    write_agent_prt5(out, empty, frame_rate=10.0, z=1.0)
    data = _read_prt5(out)
    assert data["one"] == 1
    assert data["nclasses"] == 1
    assert len(data["frames"]) == 1
    assert data["frames"][0]["n"] == 0
    assert data["frames"][0]["t"] == pytest.approx(0.0)


def test_prt5_rejects_int32_overflow(tmp_path: Path) -> None:
    df = pd.DataFrame([(0, 2**31, 1.0, 1.0)], columns=["frame", "id", "x", "y"])
    with pytest.raises(ValueError, match="int32 max"):
        write_agent_prt5(tmp_path / "x.prt5", df, frame_rate=10.0, z=1.0)


def test_patch_smv_basic(tmp_path: Path) -> None:
    smv = tmp_path / "demo.smv"
    smv.write_text("TITLE\n demo case\n\nCHID\n demo\n")
    prt5 = tmp_path / "demo_agents.prt5"
    prt5.write_bytes(b"")

    assert patch_smv_file(smv, prt5, class_id="AGENTS", rgb=(0.1, 0.4, 0.9)) is True

    text = smv.read_text()
    assert "PROP" in text
    assert " AGENTS_props" in text
    assert " human_rotating" in text
    assert " human_fixed" in text
    assert text.index(" human_rotating") < text.index(" human_fixed"), (
        "human_rotating must be listed first so Smokeview picks it when the "
        "case-local .svo provides it"
    )
    assert "PRT5     1" in text
    assert " demo_agents.prt5" in text
    assert "CLASS_OF_PARTICLES" in text
    assert " AGENTS % % AGENTS_props" in text
    assert "      0.10000      0.40000      0.90000" in text
    assert text.index("PROP") < text.index("CLASS_OF_PARTICLES"), (
        "PROP must precede CLASS_OF_PARTICLES so GetPropID finds the prop"
    )
    assert text.index("CLASS_OF_PARTICLES") < text.index("PRT5"), (
        "CLASS_OF_PARTICLES must appear before PRT5 — Smokeview parses single-pass"
    )


def test_patch_ini_creates_when_missing(tmp_path: Path) -> None:
    ini = tmp_path / "demo.ini"
    patch_ini_for_avatars(ini, nclasses=1)
    text = ini.read_text()
    assert "partclassdataVIS" in text
    assert " 1\n 4\n" in text  # 1 class, vis_type=PART_SMV_DEVICE


def test_patch_ini_updates_existing(tmp_path: Path) -> None:
    """An existing partclassdataVIS block (e.g. from a prior Smokeview
    session that saved vis_type=1) must be flipped to 4 so avatars
    render without manual menu toggling."""
    ini = tmp_path / "demo.ini"
    ini.write_text("# header\nPART5COLOR\n 0\npartclassdataVIS\n 1\n 1\nPARTSKIP\n 1\n")
    patch_ini_for_avatars(ini, nclasses=1)
    text = ini.read_text()
    assert "partclassdataVIS\n 1\n 4\n" in text
    assert text.count("partclassdataVIS") == 1  # not duplicated
    assert "PART5COLOR" in text
    assert "PARTSKIP" in text


def test_patch_smv_replaces_stale_block(tmp_path: Path) -> None:
    """A stale block for the same prt5 must be overwritten, not duplicated.

    Regression for: rerunning --smv-export after changing n_quantities
    left the old CLASS_OF_PARTICLES with the old (lower) count in place,
    desynchronising Smokeview's frame reader and causing a segfault.
    """
    smv = tmp_path / "demo.smv"
    smv.write_text(
        "TITLE\n demo case\n\nCHID\n demo\n"
        "CLASS_OF_PARTICLES\n AGENTS\n      0.1 0.4 0.9\n  0\n"
        "PRT5     1\n demo_agents.prt5\n      1\n      1\n"
    )
    prt5 = tmp_path / "demo_agents.prt5"
    prt5.write_bytes(b"")

    assert (
        patch_smv_file(smv, prt5, class_id="Human", rgb=(0.1, 0.4, 0.9), n_quantities=1)
        is True
    )
    text = smv.read_text()
    assert text.count("PRT5     1") == 1
    assert text.count("CLASS_OF_PARTICLES") == 1
    assert "  1\n body angle\n AZIMUTH\n" in text
    assert " AGENTS\n" not in text  # stale name gone
    assert " Human % % Human_props" in text


class _FakeResult:
    """Minimal ScenarioResult stand-in for export_agents_to_smv."""

    def __init__(self, df: pd.DataFrame, frame_rate: float = 10.0) -> None:
        self._df = df
        self.frame_rate = frame_rate

    def trajectory_dataframe(self) -> pd.DataFrame:
        return self._df


def test_export_agents_to_smv_end_to_end(tmp_path: Path, tiny_df: pd.DataFrame) -> None:
    fds_dir = tmp_path / "fds"
    fds_dir.mkdir()
    smv = fds_dir / "demo.smv"
    smv.write_text("TITLE\n demo case\n\nCHID\n demo\n")

    result = cast(ScenarioResult, _FakeResult(tiny_df))
    prt5 = export_agents_to_smv(fds_dir, result, z=1.2, class_id="AGENTS")

    assert prt5 == fds_dir / "demo_agents.prt5"
    assert prt5.exists()
    assert "PRT5     1" in smv.read_text()

    svo = fds_dir / "demo.svo"
    assert svo.exists(), (
        "per-case .svo should be written so human_rotating is resolvable"
    )
    svo_text = svo.read_text()
    assert "AVATARDEF" in svo_text
    assert "human_rotating" in svo_text
    assert ":AZIMUTH" in svo_text, "AVATARDEF header must declare :AZIMUTH as indep var"
    assert "$AZIMUTH rotatez" in svo_text, (
        "draw program must reference per-particle azimuth"
    )

    data = _read_prt5(prt5)
    assert data["version"] == 600
    assert data["frames"][0]["z"] == pytest.approx([1.2, 1.2])


def test_export_agents_to_smv_missing_smv(
    tmp_path: Path, tiny_df: pd.DataFrame
) -> None:
    fds_dir = tmp_path / "fds"
    fds_dir.mkdir()
    with pytest.raises(FileNotFoundError):
        export_agents_to_smv(fds_dir, cast(ScenarioResult, _FakeResult(tiny_df)))


@pytest.mark.skipif(
    not os.environ.get("PRT5PARSER"),
    reason="PRT5PARSER env var not set; skipping round-trip against chraibi/prt5parser",
)
def test_prt5parser_roundtrip(tmp_path: Path, tiny_df: pd.DataFrame) -> None:
    """Confirm the file is readable by chraibi/prt5parser (Smokeview-compatible)."""
    out = tmp_path / "demo_agents.prt5"
    write_agent_prt5(out, tiny_df, frame_rate=10.0, z=1.0)
    parser = Path(os.environ["PRT5PARSER"])
    assert parser.exists(), f"PRT5PARSER binary not found: {parser}"
    proc = subprocess.run(
        [str(parser), str(out)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, f"prt5parser failed: {proc.stderr}"
