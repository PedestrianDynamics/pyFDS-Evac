"""The golden re-record guard fails without evidence and passes with it (#810)."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "check_golden_rerecord.py"


@pytest.fixture(scope="module")
def guard():
    spec = importlib.util.spec_from_file_location("check_golden_rerecord", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SECTION = "## Golden re-record:\n\nrank_routes/a.json: ranking labels only.\n"


@pytest.mark.parametrize(
    "path",
    [
        "tests/golden/rank_routes/a.json",
        "tests/golden/scenarios/linux-x86_64/b.json",
        "tests/verification/golden/heat_default/fed_history.csv",
        "tests/__snapshots__/test_tui/test_snapshot_results.raw",
    ],
)
def test_a_golden_change_without_the_section_fails(guard, path):
    errors = guard.check([path, "pyfds_evac/route_graph.py"], "Fixes #1.")
    assert errors
    assert f"  {path}" in errors


@pytest.mark.parametrize(
    "path",
    [
        "tests/golden/README.md",
        "tests/verification/golden/heat_default/README.md",
        "tests/verification/golden/heat_default/make_baseline.py",
        "tests/test_rerouting_golden.py",
    ],
)
def test_docs_scripts_and_tests_are_not_golden_data(guard, path):
    assert guard.check([path], "") == []


@pytest.mark.parametrize(
    "body",
    [
        SECTION,
        "Golden re-record: labels only, see the audit memo.",
        "**Golden re-record:**\nlabels only",
    ],
)
def test_a_golden_change_with_the_section_passes(guard, body):
    assert guard.check(["tests/golden/rank_routes/a.json"], body) == []


@pytest.mark.parametrize(
    "body",
    [
        "## Golden re-record:\n\n## Tests\nall pass",
        "<!-- Golden re-record: fill in -->",
        "See the Golden re-record: rule.",
    ],
)
def test_an_empty_commented_or_inline_mention_is_not_a_section(guard, body):
    assert guard.check(["tests/golden/rank_routes/a.json"], body)


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def test_the_command_line_reads_the_diff_and_the_body(tmp_path, monkeypatch):
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "t@example.org")
    _git(tmp_path, "config", "user.name", "t")
    golden = tmp_path / "tests" / "golden" / "a.json"
    golden.parent.mkdir(parents=True)
    golden.write_text("{}")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "base")
    golden.write_text('{"a": 1}')
    _git(tmp_path, "commit", "-q", "-am", "head")

    def run(body):
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--base", "HEAD~1", "--head", "HEAD"],
            cwd=tmp_path,
            env={"PR_BODY": body, "PATH": "/usr/bin:/bin"},
            capture_output=True,
            text=True,
        )

    missing = run("No section.")
    assert missing.returncode == 1
    assert "tests/golden/a.json" in missing.stderr
    assert run(SECTION).returncode == 0
