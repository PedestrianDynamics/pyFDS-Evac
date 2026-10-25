"""The mutation check counts a mutant as killed only when tests fail (#816).

A mutant that breaks the import or the syntax makes pytest exit nonzero
without a failed test; that run is invalid, not a kill.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "mutation_check.py"


@pytest.fixture(scope="module")
def check():
    spec = importlib.util.spec_from_file_location("mutation_check", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
        yield module
    finally:
        sys.modules.pop(spec.name, None)


def test_passing_run_is_a_survivor(check):
    assert check._outcome(0, []) == "survived"


def test_failed_test_is_a_kill(check):
    assert check._outcome(1, ["tests/test_fed.py::test_x"]) == "killed"


@pytest.mark.parametrize(
    ("returncode", "failed"),
    [
        (1, []),  # an error in setup, no failed test
        (2, []),  # collection error, e.g. a syntax error in the mutant
        (3, []),  # pytest internal error
        (4, []),  # usage error
        (5, []),  # no tests collected
    ],
)
def test_error_without_failed_test_is_invalid(check, returncode, failed):
    assert check._outcome(returncode, failed) == "invalid"


def test_every_area_snippet_occurs_once(check):
    for area in check.AREAS.values():
        for m in area.mutants:
            text = (check.REPO / (m.module or area.module)).read_text()
            assert text.count(m.old) == 1, m.name


def test_a_timed_out_run_is_a_kill(check):
    # A mutant that hangs the tests (e.g. a search that never ends) is caught.
    assert check._outcome(check.TIMED_OUT, []) == "killed"


def test_run_tests_turns_a_timeout_into_timed_out(check, monkeypatch):
    def run(*args, **kwargs):
        assert kwargs["timeout"] == 7.0
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])

    monkeypatch.setattr(check.subprocess, "run", run)
    assert check._run_tests("python", ("tests/x.py",), 7.0) == (check.TIMED_OUT, [])
