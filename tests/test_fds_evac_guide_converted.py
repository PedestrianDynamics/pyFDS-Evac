"""Protect runnable guide inputs and distinguish FDS input errors from success."""

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from pyfds_evac.core.fds_deck import parse_fds_deck

ROOT = Path(__file__).resolve().parents[1]
COLLECTION = ROOT / "assets/fds_evac_guide_converted"
pytestmark = pytest.mark.skipif(
    not COLLECTION.exists(), reason="guide assets excluded from sdist"
)


def test_manifest_accounts_for_every_original_and_shipped_file():
    manifest = json.loads((COLLECTION / "manifest.json").read_text())
    assert len(manifest["cases"]) == 94
    assert len(manifest["excluded"]) == 88
    assert sum(bool(c["fire_input"]) for c in manifest["cases"]) == 42
    sources = [c["source"] for c in manifest["cases"]] + [
        c["scenario"] for c in manifest["excluded"]
    ]
    originals = ROOT / "assets/fds_evac_guide"
    assert len(set(sources)) == 182
    assert set(sources) == {
        p.relative_to(originals).as_posix() for p in originals.rglob("*.fds")
    }
    for case in manifest["cases"]:
        folder = COLLECTION / "cases" / case["id"]
        provenance = json.loads((folder / "provenance.json").read_text())
        assert (
            hashlib.sha256((originals / case["source"]).read_bytes()).hexdigest()
            == case["source_sha256"]
        )
        for name, digest in provenance["files_sha256"].items():
            assert hashlib.sha256((folder / name).read_bytes()).hexdigest() == digest


def test_fire_inputs_retain_physical_meshes_and_have_in_domain_coupling_slices():
    manifest = json.loads((COLLECTION / "manifest.json").read_text())
    for case in manifest["cases"]:
        if not case["fire_input"]:
            continue
        folder = COLLECTION / "cases" / case["id"]
        original = parse_fds_deck(ROOT / "assets/fds_evac_guide" / case["source"])
        fire = parse_fds_deck(folder / "fire.fds")
        assert not {r.group for r in fire.records} & {
            "EVAC",
            "PERS",
            "EXIT",
            "EVHO",
            "EVSS",
            "ENTR",
            "CORR",
        }
        assert not any(k.startswith("EVAC") for r in fire.records for k in r.params)
        original_meshes = [
            m for m in original.group("MESH") if not m.flag("EVACUATION", False)
        ]
        assert [m.box6() for m in fire.group("MESH")] == [
            m.box6() for m in original_meshes
        ]
        assert [m.values("IJK") for m in fire.group("MESH")] == [
            m.values("IJK") for m in original_meshes
        ]
        assert fire.first("TIME").number("T_END") == original.first("TIME").number(
            "T_END"
        )
        assert [r.params for r in fire.group("REAC")] == [
            r.params for r in original.group("REAC")
        ]
        config = json.loads((folder / "config.json").read_text())
        height = config["config"]["simulation_settings"]["simulationParams"][
            "smoke_slice_height"
        ]
        assert any(m.box6()[4] < height < m.box6()[5] for m in fire.group("MESH"))
        slices = {
            (s.text("QUANTITY"), s.text("SPEC_ID"))
            for s in fire.group("SLCF")
            if s.number("PBZ", -999) == height
        }
        assert ("EXTINCTION COEFFICIENT", None) in slices
        assert ("TEMPERATURE", None) in slices
        if case["coupling"] == "smoke_and_gas":
            for species in ("CARBON MONOXIDE", "CARBON DIOXIDE", "OXYGEN"):
                assert ("VOLUME FRACTION", species) in slices


@pytest.mark.parametrize(
    "code,message,expected",
    [
        (0, "ERROR: FDS was improperly set-up - FDS stopped", False),
        (0, "STOP: FDS completed successfully", True),
        (1, "STOP: FDS completed successfully", False),
        (0, "Starting FDS ...", False),
    ],
)
def test_fds_completion_requires_more_than_zero_exit(code, message, expected, tmp_path):
    spec = importlib.util.spec_from_file_location(
        "guide_runner", ROOT / "scripts/run_fds_evac_guide.py"
    )
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    log = tmp_path / "fds.log"
    log.write_text(message)
    assert runner.fds_completed(code, log) is expected
