"""Behaviour of the benchmark harness guards and the exact comparison."""

import importlib.util
import json
import sqlite3
import subprocess
from argparse import Namespace
from pathlib import Path

import pytest

BENCH = Path(__file__).resolve().parents[1] / "scripts" / "benchmark"


def load(name):
    spec = importlib.util.spec_from_file_location(name, BENCH / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


benchmark = load("benchmark")
compare = load("compare_outputs")


def git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q")
    git(root, "config", "user.email", "t@example.org")
    git(root, "config", "user.name", "t")
    (root / "a.txt").write_text("a")
    git(root, "add", "a.txt")
    git(root, "commit", "-q", "-m", "init")
    return root


def test_results_inside_checkout_do_not_dirty_it(repo):
    out = repo / "benchmark-results"
    (out / "raw" / "r1").mkdir(parents=True)
    (out / "summary.csv").write_text("x")
    head, status = benchmark.check_checkout(str(repo), None, str(out))
    assert status == ""


def test_other_untracked_files_still_refuse(repo):
    (repo / "stray.txt").write_text("x")
    with pytest.raises(SystemExit):
        benchmark.check_checkout(str(repo), None, str(repo / "benchmark-results"))


def test_exit_2_needs_the_incomplete_line():
    meas = {"killed_at_cap": False, "returncode": 2}
    assert benchmark.classify(meas, {"status": "incomplete"}) == "incomplete_exit2"
    assert benchmark.classify(meas, {}) == "failed"
    assert benchmark.classify({**meas, "returncode": 0}, {}) == "ok"


def test_batch_item_cannot_override_the_commit(tmp_path):
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps([{"args": ["--case", "W2a", "--commit", "HEAD"]}]))
    with pytest.raises(SystemExit):
        benchmark.batch_items(Namespace(spec=str(spec), outdir=str(tmp_path)))


def test_corrupt_sqlite_is_recorded_not_raised(tmp_path):
    (tmp_path / "run.sqlite").write_bytes(b"not a database")
    out = benchmark.parse_outcome(str(tmp_path), str(tmp_path / "none.txt"))
    assert out["parse_errors"]


def make_run(path, sql, stdout):
    path.mkdir()
    con = sqlite3.connect(path / "run.sqlite")
    con.executescript(sql)
    con.commit()
    con.close()
    (path / "stdout_stamped.txt").write_text(stdout)


def test_schema_difference_is_not_equal(tmp_path):
    make_run(tmp_path / "a", "create table t(x); insert into t values (1);", "")
    make_run(tmp_path / "b", "create table t(y); insert into t values (1);", "")
    report = compare.compare_sqlite(
        str(tmp_path / "a/run.sqlite"), str(tmp_path / "b/run.sqlite")
    )
    assert report["schema_equal"] is False


def test_route_cost_lines_count_unless_allowed_missing(tmp_path):
    make_run(tmp_path / "a", "", "      0.1 Route cost samples: 3\n")
    make_run(tmp_path / "b", "", "      0.1 Route cost samples: 4\n")
    a, b = str(tmp_path / "a"), str(tmp_path / "b")
    assert compare.filtered_stdout(a, False) != compare.filtered_stdout(b, False)
    assert compare.filtered_stdout(a, True) == compare.filtered_stdout(b, True)
