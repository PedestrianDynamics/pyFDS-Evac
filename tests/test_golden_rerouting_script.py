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


# Ways one side's provenance can be wrong. Each entry gives the manifest
# changes for the bad side and the --expect-* value to pass for it (the other
# side is always given its right commit).
_BAD_SIDE = {
    "dirty_pyfds_evac": ({"dirty": {"pyfds_evac": True}}, "right"),
    "dirty_run_py": ({"dirty": {"run.py": True}}, "right"),
    "dirty_assets": ({"dirty": {"assets": True}}, "right"),
    "dirty_unchecked": ({"dirty": {"pyfds_evac": True}}, None),
    "commit_mismatch": ({}, "wrong"),
    "short_prefix": ({}, "short"),
    "missing_provenance": ({"provenance": None}, "right"),
    "changed_during_run": ({"provenance_changed": ["commit"]}, "right"),
}


def _side(golden, out: Path, commit: str, change: dict) -> Path:
    change = dict(change)
    dirty = change.pop("dirty", None)
    if change.get("provenance", "keep") is None:
        change.pop("provenance")
        path = _fake_run(golden, out, _provenance(golden, commit))
        manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
        del manifest["provenance"]
        (path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        return path
    return _fake_run(golden, out, _provenance(golden, commit, dirty), **change)


@pytest.mark.parametrize("role", ["base", "head"])
@pytest.mark.parametrize("problem", sorted(_BAD_SIDE))
def test_provenance_fails_on_either_side(golden, tmp_path, role, problem):
    change, expect_kind = _BAD_SIDE[problem]
    commits = {"base": BASE, "head": HEAD}
    expects = dict(commits)
    bad = commits[role]
    expects[role] = {
        "right": bad,
        "wrong": commits["head" if role == "base" else "base"],
        "short": bad[:6],
        None: None,
    }[expect_kind]
    a = _side(golden, tmp_path / "a", BASE, change if role == "base" else {})
    b = _side(golden, tmp_path / "b", HEAD, change if role == "head" else {})
    assert golden._compare(a, b, [DECK], expects["base"], expects["head"]) == 1
    # The same pair with the problem removed passes.
    c = _side(golden, tmp_path / "c", BASE, {})
    d = _side(golden, tmp_path / "d", HEAD, {})
    assert golden._compare(c, d, [DECK], BASE[:7], HEAD[:7]) == 0


@pytest.mark.parametrize(
    "fingerprints",
    [{"run.py": "x" * 64}, {"harness": "x" * 64}, {"decks": {}}],
    ids=["run_py_differs", "harness_differs", "deck_inputs_missing"],
)
@pytest.mark.parametrize("role", ["base", "head"])
def test_fingerprints_must_match(golden, tmp_path, role, fingerprints):
    odd = _provenance(golden, BASE if role == "base" else HEAD, None, fingerprints)
    even = _provenance(golden, HEAD if role == "base" else BASE)
    a = _fake_run(golden, tmp_path / "a", odd if role == "base" else even)
    b = _fake_run(golden, tmp_path / "b", even if role == "base" else odd)
    assert golden._compare(a, b, [DECK]) == 1


def test_harness_may_be_dirty(golden, tmp_path):
    """A baseline runs a newer harness in an older checkout; the print decides."""
    a = _fake_run(
        golden, tmp_path / "a", _provenance(golden, dirty={golden.HARNESS: True})
    )
    b = _fake_run(golden, tmp_path / "b", _provenance(golden, HEAD))
    assert golden._compare(a, b, [DECK], BASE, HEAD) == 0


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


def _drop(key):
    def change(prints):
        del prints[key]
        return prints

    return change


def _set(key, value):
    def change(prints):
        prints[key] = value
        return prints

    return change


def _set_deck(record):
    def change(prints):
        prints["decks"] = {DECK: record} if record is not None else {}
        return prints

    return change


# Incomplete fingerprint records: each must fail, whichever side has it.
_GAPS = {
    "fingerprints_missing": lambda p: None,
    "fingerprints_empty": lambda p: {},
    "harness_missing": _drop("harness"),
    "harness_null": _set("harness", None),
    "harness_empty": _set("harness", ""),
    "run_py_missing": _drop("run.py"),
    "run_py_null": _set("run.py", None),
    "decks_missing": _drop("decks"),
    "decks_null": _set("decks", None),
    "decks_empty": _set_deck(None),
    "deck_absent": _set("decks", {"other": {"config": "c", "geometry": "g"}}),
    "deck_record_empty": _set_deck({}),
    "deck_config_null": _set_deck({"config": None, "geometry": "g"}),
    "deck_geometry_empty": _set_deck({"config": "c", "geometry": ""}),
}


def _gapped(golden, out: Path, commit: str, change, dirty=None) -> Path:
    provenance = _provenance(golden, commit, dirty)
    record = change(provenance["fingerprints"])
    if record is None:
        del provenance["fingerprints"]
    else:
        provenance["fingerprints"] = record
    return _fake_run(golden, out, provenance)


@pytest.mark.parametrize("role", ["base", "head"])
@pytest.mark.parametrize("gap", sorted(_GAPS))
def test_incomplete_fingerprints_fail(golden, tmp_path, role, gap):
    change = _GAPS[gap]
    whole = lambda p: p  # noqa: E731
    a = _gapped(golden, tmp_path / "a", BASE, change if role == "base" else whole)
    b = _gapped(golden, tmp_path / "b", HEAD, change if role == "head" else whole)
    assert golden._compare(a, b, [DECK], BASE, HEAD) == 1


@pytest.mark.parametrize("gap", sorted(_GAPS))
def test_matching_gaps_still_fail(golden, tmp_path, gap):
    """Two records missing the same thing are not a match."""
    a = _gapped(golden, tmp_path / "a", BASE, _GAPS[gap])
    b = _gapped(golden, tmp_path / "b", HEAD, _GAPS[gap])
    assert golden._compare(a, b, [DECK], BASE, HEAD) == 1


def test_dirty_harness_without_fingerprints_fails(golden, tmp_path):
    dirty = {golden.HARNESS: True}
    a = _gapped(golden, tmp_path / "a", BASE, lambda p: None, dirty)
    b = _fake_run(golden, tmp_path / "b", _provenance(golden, HEAD))
    assert golden._compare(a, b, [DECK], BASE, HEAD) == 1


def test_fds_deck_needs_its_fds_hash(golden):
    """A deck with an FDS run must fingerprint it; a clear-air deck need not."""
    fds_deck = next(n for n, d in golden.DECKS.items() if d.fds_dir is not None)
    record = {
        "harness": "h",
        "run.py": "r",
        "decks": {
            fds_deck: {"config": "c", "geometry": "g", "fds_dir": None},
            DECK: {"config": "c", "geometry": "g", "fds_dir": None},
        },
    }
    gaps = golden._fingerprint_gaps(record, "base", Path("x"), [fds_deck, DECK])
    assert gaps == [f"base x has no fds_dir fingerprint for {fds_deck}"]
    record["decks"][fds_deck]["fds_dir"] = "f"
    assert golden._fingerprint_gaps(record, "base", Path("x"), [fds_deck, DECK]) == []


def _summary(golden, **metrics) -> str:
    base = {"agents": [{"id": 1, "t": 2.5}], "deck": {}, "metrics": {"n": 3}}
    base["metrics"] |= metrics
    return golden._summary_text(base)


_COVERAGE = {"walkable_outside_m2": 0.0, "quantities": ["TEMPERATURE"]}


@pytest.mark.parametrize("side", ["a", "b"])
def test_added_metrics_on_one_side_are_listed_not_compared(golden, tmp_path, side):
    """A head with the #426 metrics still matches a base run without them."""
    texts = {"a": _summary(golden), "b": _summary(golden)}
    texts[side] = _summary(
        golden, fds_coverage=_COVERAGE, fds_outside={"rows": 0, "agents": 0}
    )
    a, b = (
        tmp_path / "a" / "egress_summary.json",
        tmp_path / "b" / "egress_summary.json",
    )
    for path, key in ((a, "a"), (b, "b")):
        path.parent.mkdir()
        path.write_text(texts[key], encoding="utf-8")
    assert golden._compare_file(a, b) == []
    role = "base" if side == "a" else "head"
    assert golden._added_notes(a, b) == [
        f"metrics.fds_coverage only in {role}; not compared",
        f"metrics.fds_outside only in {role}; not compared",
    ]


@pytest.mark.parametrize(
    ("metrics_a", "metrics_b"),
    [
        ({}, {"n": 4, "fds_outside": {"rows": 0}}),  # an existing key differs
        ({"fds_outside": {"rows": 0}}, {"fds_outside": {"rows": 1}}),  # both sides
    ],
    ids=["existing_key", "added_on_both"],
)
def test_other_metric_differences_still_count(golden, tmp_path, metrics_a, metrics_b):
    a, b = (
        tmp_path / "a" / "egress_summary.json",
        tmp_path / "b" / "egress_summary.json",
    )
    a.parent.mkdir()
    b.parent.mkdir()
    a.write_text(_summary(golden, **metrics_a), encoding="utf-8")
    b.write_text(_summary(golden, **metrics_b), encoding="utf-8")
    assert golden._compare_file(a, b)


def test_added_metrics_keep_bytes_deciding(golden, tmp_path):
    """Leaving out an added metric does not turn 1.0 and 1 into equals."""
    a, b = (
        tmp_path / "a" / "egress_summary.json",
        tmp_path / "b" / "egress_summary.json",
    )
    a.parent.mkdir()
    b.parent.mkdir()
    a.write_text(_summary(golden, t=1.0), encoding="utf-8")
    b.write_text(_summary(golden, t=1, fds_outside={"rows": 0}), encoding="utf-8")
    assert golden._compare_file(a, b)
