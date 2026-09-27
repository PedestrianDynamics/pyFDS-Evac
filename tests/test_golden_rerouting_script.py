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


def _provenance(golden, commit=BASE, dirty=None, fingerprints=None) -> dict:
    clean = {p: False for p in (*golden.CODE_PATHS, golden.HARNESS)}
    prints = {
        "harness": "h" * 64,
        "run.py": "r" * 64,
        "decks": {DECK: {"config": "c", "geometry": "g", "fds_dir": None}},
    }
    return {
        "commit": commit,
        "dirty": clean | (dirty or {}),
        "fingerprints": prints | (fingerprints or {}),
    }


def _fake_run(golden, out: Path, provenance=None, **manifest) -> Path:
    """Outputs for every run of DECK, and a manifest saying *manifest*."""
    for deck, mode in golden._inventory([DECK]):
        folder = out / deck / mode
        folder.mkdir(parents=True)
        for name in golden.MODES[mode]:
            text = "{}\n" if name.endswith(".json") else "a,b\n1,2\n"
            (folder / name).write_text(text, encoding="utf-8")
    runs = [f"{d}/{m}" for d, m in golden._inventory([DECK])]
    record = {
        "provenance": provenance or _provenance(golden),
        "provenance_changed": [],
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
    b = _fake_run(golden, tmp_path / "b", _provenance(golden, HEAD))
    assert golden._compare(a, b, [DECK], BASE[:7], HEAD[:7]) == 0
    assert golden._compare(a, b, [DECK], BASE, HEAD) == 0


@pytest.mark.parametrize(
    ("head", "expect_base", "expect_head"),
    [
        ({"commit": HEAD}, BASE, BASE),
        ({"commit": HEAD}, HEAD, HEAD),
        ({"commit": HEAD, "dirty": {"pyfds_evac": True}}, BASE, HEAD),
        ({"commit": HEAD, "dirty": {"pyfds_evac": True}}, None, None),
        ({"commit": HEAD, "dirty": {"run.py": True}}, None, None),
        ({"commit": HEAD, "dirty": {"assets": True}}, None, None),
        ({"commit": HEAD}, BASE, HEAD[:6]),
        ({"commit": HEAD, "fingerprints": {"run.py": "x" * 64}}, None, None),
        ({"commit": HEAD, "fingerprints": {"harness": "x" * 64}}, None, None),
        ({"commit": HEAD, "fingerprints": {"decks": {}}}, None, None),
    ],
    ids=[
        "head_mismatch",
        "base_mismatch",
        "dirty_head",
        "dirty_unchecked",
        "dirty_run_py",
        "dirty_assets",
        "short",
        "run_py_differs",
        "harness_differs",
        "deck_inputs_missing",
    ],
)
def test_provenance_fails(golden, tmp_path, head, expect_base, expect_head):
    a = _fake_run(golden, tmp_path / "a")
    b = _fake_run(golden, tmp_path / "b", _provenance(golden, **head))
    assert golden._compare(a, b, [DECK], expect_base, expect_head) == 1


def test_harness_may_be_dirty(golden, tmp_path):
    """A baseline runs a newer harness in an older checkout; the print decides."""
    a = _fake_run(
        golden, tmp_path / "a", _provenance(golden, dirty={golden.HARNESS: True})
    )
    b = _fake_run(golden, tmp_path / "b", _provenance(golden, HEAD))
    assert golden._compare(a, b, [DECK], BASE, HEAD) == 0


def test_provenance_change_or_absence_fails(golden, tmp_path):
    a = _fake_run(golden, tmp_path / "a")
    b = _fake_run(golden, tmp_path / "b", provenance_changed=["commit"])
    assert golden._compare(a, b, [DECK]) == 1
    c = _fake_run(golden, tmp_path / "c")
    manifest = json.loads((c / "manifest.json").read_text(encoding="utf-8"))
    del manifest["provenance"]
    (c / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    assert golden._compare(a, c, [DECK]) == 1


def _write_outputs(argv, **kwargs):
    """Stand-in for the per-run subprocess: write the files a run writes."""
    out = Path(argv[argv.index("--out") + 1])
    mode = argv[argv.index("--mode") + 1]
    out.mkdir(parents=True)
    for name in ("route_history.csv", "egress_summary.json"):
        (out / name).write_text("x\n", encoding="utf-8")
    if mode == "history_on":
        (out / "route_cost_history.csv").write_text("x\n", encoding="utf-8")


def _git_stub(commits, dirty_path=None):
    commits = iter(commits)

    def git(*args):
        if args[0] == "rev-parse":
            return next(commits)
        if args[0] == "status" and args[-1] == dirty_path:
            return f" M {dirty_path}"
        return ""

    return git


def test_run_refuses_a_dirty_run_py(golden, tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(golden, "_git", _git_stub([BASE] * 2, "run.py"))
    monkeypatch.setattr(golden.subprocess, "run", lambda *a, **k: calls.append(a))
    assert golden._run_all([DECK], tmp_path, tmp_path / "out") != 0
    assert calls == []


def test_run_fails_if_the_commit_changes(golden, tmp_path, monkeypatch):
    monkeypatch.setattr(golden, "_git", _git_stub([BASE, HEAD]))
    monkeypatch.setattr(golden.subprocess, "run", _write_outputs)
    out = tmp_path / "out"
    assert golden._run_all([DECK], tmp_path, out) == 1
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["provenance_changed"] == ["commit"]
    assert manifest["provenance"]["commit"] == BASE


def test_run_fails_if_an_input_changes(golden, tmp_path, monkeypatch):
    real = golden._provenance
    seen = []

    def provenance(names, root):
        result = real(names, root)
        if seen:
            result["fingerprints"]["run.py"] = "x" * 64
        seen.append(result)
        return result

    monkeypatch.setattr(golden, "_git", _git_stub([BASE] * 2))
    monkeypatch.setattr(golden, "_provenance", provenance)
    monkeypatch.setattr(golden.subprocess, "run", _write_outputs)
    out = tmp_path / "out"
    assert golden._run_all([DECK], tmp_path, out) == 1
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["provenance_changed"] == ["fingerprints"]


def test_clean_run_records_provenance(golden, tmp_path, monkeypatch):
    monkeypatch.setattr(golden, "_git", _git_stub([BASE] * 2))
    monkeypatch.setattr(golden.subprocess, "run", _write_outputs)
    out = tmp_path / "out"
    assert golden._run_all([DECK], tmp_path, out) == 0
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    prints = manifest["provenance"]["fingerprints"]
    assert prints["harness"] == golden._sha256_file(Path(golden.__file__))
    assert prints["run.py"] == golden._sha256_file(golden.REPO / "run.py")
    assert prints["decks"][DECK]["config"] is not None
    assert manifest["provenance_changed"] == []


def test_compare_refuses_itself(golden, tmp_path):
    a = _fake_run(golden, tmp_path / "a")
    assert golden._compare(a, a, [DECK]) == 1
    assert golden._compare(a, tmp_path / "x" / ".." / "a", [DECK]) == 1
