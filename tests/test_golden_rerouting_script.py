"""The golden-run script accepts no stale or incomplete runs (#187).

``scripts/golden_rerouting.py`` is the gate for the FDS decks, so a run it
could not make must fail the comparison rather than leave older files that
compare as identical.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "golden_rerouting.py"
DECK = "familiarity_test_full"
BASE = "a" * 40
HEAD = "b" * 40


@pytest.fixture(scope="module")
def golden():
    spec = importlib.util.spec_from_file_location("golden_rerouting", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    # Dataclasses look their module up in sys.modules while being created.
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
        yield module
    finally:
        sys.modules.pop(spec.name, None)


def _fake_run(golden, out: Path, **manifest) -> Path:
    """Outputs for every run of DECK, and a manifest saying *manifest*."""
    for deck, mode in golden._inventory([DECK]):
        folder = out / deck / mode
        folder.mkdir(parents=True)
        for name in golden.MODES[mode]:
            text = "{}\n" if name.endswith(".json") else "a,b\n1,2\n"
            (folder / name).write_text(text, encoding="utf-8")
    runs = [f"{d}/{m}" for d, m in golden._inventory([DECK])]
    record = {
        "commit": BASE,
        "pyfds_evac_dirty": False,
        "runs": runs,
        "skipped": {},
        "incomplete": {},
    } | manifest
    (out / "manifest.json").write_text(json.dumps(record), encoding="utf-8")
    return out


def test_complete_runs_compare_identical(golden, tmp_path):
    a = _fake_run(golden, tmp_path / "a")
    b = _fake_run(golden, tmp_path / "b")
    assert golden._compare(a, b, [DECK]) == 0


@pytest.mark.parametrize(
    "manifest",
    [
        {"skipped": {f"{DECK}/history_off": ["nowhere"]}},
        {"incomplete": {f"{DECK}/history_on": ["route_history.csv"]}},
        {"runs": [f"{DECK}/history_on"]},
    ],
    ids=["skipped", "incomplete", "unrecorded"],
)
def test_stale_files_do_not_hide_a_bad_run(golden, tmp_path, manifest):
    """Old outputs are all present, but the manifest says the run was not made."""
    a = _fake_run(golden, tmp_path / "a")
    b = _fake_run(golden, tmp_path / "b", **manifest)
    assert golden._compare(a, b, [DECK]) == 1
    assert golden._compare(b, a, [DECK]) == 1


def test_missing_manifest_fails(golden, tmp_path):
    a = _fake_run(golden, tmp_path / "a")
    b = _fake_run(golden, tmp_path / "b")
    (b / "manifest.json").unlink()
    assert golden._compare(a, b, [DECK]) == 1


def test_run_refuses_a_used_folder(golden, tmp_path, monkeypatch):
    out = _fake_run(golden, tmp_path / "old")
    calls = []
    monkeypatch.setattr(golden.subprocess, "run", lambda *a, **k: calls.append(a))
    assert golden._run_all([DECK], tmp_path, out) != 0
    assert calls == []


def test_run_without_outputs_is_incomplete(golden, tmp_path, monkeypatch):
    """A run that wrote nothing is not recorded as made."""
    monkeypatch.setattr(golden.subprocess, "run", lambda *a, **k: None)
    monkeypatch.setattr(golden, "_git", lambda *a: "")
    out = tmp_path / "new"
    assert golden._run_all([DECK], tmp_path, out) == 1
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["runs"] == []
    assert sorted(manifest["incomplete"]) == [
        f"{DECK}/{mode}" for mode in sorted(golden.MODES)
    ]


@pytest.mark.parametrize(
    ("name", "text_a", "text_b"),
    [
        ("egress_summary.json", '{"agents": [], "n": 1}\n', '{"n": 1}\n'),
        ("egress_summary.json", '{"t": 1.0}\n', '{"t": 1}\n'),
        ("route_history.csv", "time_s,cost\n1.0,2\n", "time_s,cost\n1.00,2\n"),
        ("route_history.csv", "a,b\n1,2\n", "a,b\r\n1,2\r\n"),
    ],
    ids=["empty_container", "json_number", "csv_number", "line_ending"],
)
def test_bytes_decide(golden, tmp_path, name, text_a, text_b):
    """Files that parse alike but are written differently are different."""
    a, b = tmp_path / "a" / name, tmp_path / "b" / name
    a.parent.mkdir()
    b.parent.mkdir()
    a.write_bytes(text_a.encode())
    b.write_bytes(text_b.encode())
    assert golden._compare_file(a, b)
    assert golden._compare_file(a, a) == []


def test_provenance_matches(golden, tmp_path):
    a = _fake_run(golden, tmp_path / "a")
    b = _fake_run(golden, tmp_path / "b", commit=HEAD)
    assert golden._compare(a, b, [DECK], BASE[:7], HEAD[:7]) == 0
    assert golden._compare(a, b, [DECK], BASE, HEAD) == 0


@pytest.mark.parametrize(
    ("head_manifest", "expect_base", "expect_head"),
    [
        ({"commit": HEAD}, BASE, BASE),
        ({"commit": HEAD}, HEAD, HEAD),
        ({"commit": HEAD, "pyfds_evac_dirty": True}, BASE, HEAD),
        ({"commit": HEAD, "pyfds_evac_dirty": True}, None, None),
        ({"commit": HEAD}, BASE, HEAD[:6]),
    ],
    ids=["head_mismatch", "base_mismatch", "dirty_head", "dirty_unchecked", "short"],
)
def test_provenance_fails(golden, tmp_path, head_manifest, expect_base, expect_head):
    a = _fake_run(golden, tmp_path / "a")
    b = _fake_run(golden, tmp_path / "b", **head_manifest)
    assert golden._compare(a, b, [DECK], expect_base, expect_head) == 1


def test_compare_refuses_itself(golden, tmp_path):
    a = _fake_run(golden, tmp_path / "a")
    assert golden._compare(a, a, [DECK]) == 1
    assert golden._compare(a, tmp_path / "x" / ".." / "a", [DECK]) == 1
