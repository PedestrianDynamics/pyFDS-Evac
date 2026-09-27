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
    record = {"runs": runs, "skipped": {}, "incomplete": {}} | manifest
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
