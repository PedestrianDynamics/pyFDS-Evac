"""The base-vs-head routing differential sees what the snapshots round away (#187).

``scripts/routing_differential.py`` is the full-precision gate for the
refactor steps, so its dump must keep every bit and every order, and it must
refuse to compare code it did not import from the checkout under test.
"""

from __future__ import annotations

import importlib.util
import json
import math
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

import pytest
from shapely.geometry import box

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "routing_differential.py"


@pytest.fixture(scope="module")
def diff():
    spec = importlib.util.spec_from_file_location("routing_differential", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
        yield module
    finally:
        sys.modules.pop(spec.name, None)


@dataclass(frozen=True)
class _Record:
    value: float
    hidden: float = field(default=0.0, compare=False)
    kinds: frozenset = frozenset()


def test_dump_keeps_bits_order_and_every_field(diff):
    ulp = math.nextafter(0.1, 1.0)
    record = _Record(ulp, hidden=1 / 3, kinds=frozenset({"b", "a"}))
    dumped = diff._full({"z": record, "a": (1, None, math.inf)})
    assert list(dumped) == ["z", "a"]
    assert dumped["z"] == {"value": ulp, "hidden": 1 / 3, "kinds": ["a", "b"]}
    assert json.loads(json.dumps(dumped))["z"]["value"] == ulp
    assert dumped["a"] == [1, None, math.inf]


def test_dump_writes_geometry_as_wkb(diff):
    assert diff._full(box(0, 0, 1, 1)) == box(0, 0, 1, 1).wkb_hex


def test_dump_refuses_an_unknown_object(diff):
    with pytest.raises(TypeError, match="cannot dump a object"):
        diff._full(object())


def _dump(snapshots: dict) -> dict:
    return {"meta": {}, "snapshots": snapshots}


def test_one_ulp_is_a_difference(diff):
    base = _dump({"case": {"tau": 0.1}})
    head = _dump({"case": {"tau": math.nextafter(0.1, 1.0)}})
    assert diff._differences(base, base) == []
    assert diff._differences(base, head) == ["case.tau: 0.1 vs 0.10000000000000002"]


def test_order_and_type_are_differences(diff):
    base = _dump({"cache": {"a": 1, "b": 2}})
    reordered = _dump({"cache": {"b": 2, "a": 1}})
    assert diff._differences(base, reordered) == [
        "same values, different order of keys"
    ]
    as_float = _dump({"cache": {"a": 1.0, "b": 2}})
    assert diff._differences(base, as_float) == ["cache.a: 1 vs 1.0"]


def test_missing_snapshot_is_a_difference(diff):
    base = _dump({"x": [1], "y": []})
    assert diff._differences(base, _dump({"x": [1]})) == ["y: [] vs '<missing>'"]


def test_compare_refuses_a_folder_that_is_no_checkout(diff, tmp_path, capsys):
    assert diff.compare(tmp_path, REPO) == 2
    assert "is not a pyFDS-Evac checkout" in capsys.readouterr().out


def test_child_refuses_code_from_another_checkout(diff, tmp_path):
    """The dump fails, naming both, when pyfds_evac is not from the root (#721)."""
    other = tmp_path / "other_checkout"
    other.mkdir()
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--dump", str(other), str(tmp_path / "x")],
        cwd=REPO,
        env=diff._child_env(REPO),
        capture_output=True,
        text=True,
    )
    assert proc.returncode != 0
    assert "was imported from" in proc.stderr
    assert str(other) in proc.stderr
    assert not (tmp_path / "x").exists()


def test_patch_refuses_a_missing_helper(diff):
    """A renamed snapshot helper must not leave the rounding in place."""
    golden = SimpleNamespace(
        __name__="golden",
        _r=None,
        _check_golden=None,
        _route_snapshot=None,
        _switch_snapshot=None,
    )
    decisions = SimpleNamespace(__name__="decisions")
    with pytest.raises(SystemExit, match="golden has no _r"):
        diff._patch(golden, decisions, {})


def test_checkout_against_itself_is_identical(diff, capsys, tmp_path):
    """The case builders this checkout holds run and dump deterministically.

    Cache entries keep their segment values, at full precision.
    """
    assert diff.compare(REPO, REPO, keep=tmp_path) == 0
    assert capsys.readouterr().out.rstrip().endswith("identical")
    dump = json.loads((tmp_path / "head.json").read_text(encoding="utf-8"))
    ranks = dump["snapshots"]["routing_decisions/rank_routes.json"]
    lines = [
        line
        for case in ranks.values()
        for variant in case.values()
        if isinstance(variant, dict)
        for line in variant["cache"]
    ]
    assert lines
    for line in lines:
        values = line.split(" | ")[1].split()
        assert "length_m" not in values
        float(values[2])  # length_m
    assert any(len(v) > 8 for line in lines for v in line.split(" | ")[1].split())
