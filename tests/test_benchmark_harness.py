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


def test_nested_and_non_ascii_results_directory(repo):
    out = repo / "ergebnisse ä" / "batch1"
    (out / "raw" / "läuft").mkdir(parents=True)
    (out / "raw" / "läuft" / "übersicht.csv").write_text("x")
    head, status = benchmark.check_checkout(str(repo), None, str(out))
    assert status == ""


def test_non_ascii_file_outside_results_still_refuses(repo):
    (repo / "übrig.txt").write_text("x")
    with pytest.raises(SystemExit):
        benchmark.check_checkout(str(repo), None, str(repo / "benchmark-results"))


@pytest.mark.parametrize("option", ["--comm=HEAD", "--check=/tmp/x", "--out=/tmp/x"])
def test_abbreviated_options_are_refused(option):
    with pytest.raises(SystemExit):
        benchmark.parser().parse_args(["run", "--case", "W2a", "--seed", "1", option])


def test_batch_item_with_equals_form_is_refused(tmp_path):
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps([{"args": ["--case", "W2a", "--commit=HEAD"]}]))
    with pytest.raises(SystemExit):
        benchmark.batch_items(Namespace(spec=str(spec), outdir=str(tmp_path)))


def test_unreadable_output_is_a_failed_run():
    meas = {"killed_at_cap": False, "returncode": 0}
    assert benchmark.classify(meas, {"parse_errors": ["x"]}) == "failed"


def test_unreadable_output_file_does_not_abort_hashing(tmp_path, monkeypatch):
    (tmp_path / "fed.csv").write_text("x")

    def refuse(path):
        raise PermissionError(path)

    monkeypatch.setattr(benchmark, "sha256_file", refuse)
    assert benchmark.hash_outputs(str(tmp_path))["fed.csv"].startswith("unreadable")


def test_batch_reports_failed_runs(tmp_path, monkeypatch):
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps([{"args": ["--case", "W2a", "--seed", "1"]}]))
    monkeypatch.setattr(
        benchmark, "one_run", lambda a: {"status": "failed", "run_id": "r"}
    )
    a = Namespace(
        spec=str(spec),
        outdir=str(tmp_path),
        checkout=str(tmp_path),
        python="python",
        commit=None,
        dry_run=False,
    )
    assert benchmark.run_batch(a) == 1


def test_added_index_is_a_schema_difference(tmp_path):
    table = "create table t(x); insert into t values (1);"
    make_run(tmp_path / "a", table + "create index i on t(x);", "")
    make_run(tmp_path / "b", table, "")
    report = compare.compare_sqlite(
        str(tmp_path / "a/run.sqlite"), str(tmp_path / "b/run.sqlite")
    )
    assert report["schema_equal"] is False
