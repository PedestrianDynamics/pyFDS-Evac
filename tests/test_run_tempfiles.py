"""Where the temporary trajectory of a run ends (#331, #524).

``run_scenario`` writes the trajectory and its manifest to the temp
directory. When it raises, it removes both itself (#331). On success the
caller owns them; the ``pyfds-evac`` command and ``stream_run`` remove them
once the outputs are written (#524).

Each test runs with a temp root of its own (``TMPDIR`` and
``tempfile.tempdir``), so other runs sharing the system temp dir do not
affect the check. The deck is the 10 x 6 m room of ``test_run_outcome``.
"""

from __future__ import annotations

import contextlib
import io
import pathlib
import tempfile

import pytest
from test_run_outcome import ENOUGH_S, _scenario

from pyfds_evac import cli
from pyfds_evac.config import events
from pyfds_evac.core import scenario as scenario_module
from pyfds_evac.core.manifest import manifest_path_for
from pyfds_evac.core.run_stream import options, stream_run
from pyfds_evac.core.scenario import run_scenario


class _Stop(Exception):
    """Raised by a test to end a run early."""


@pytest.fixture
def tmp_root(tmp_path, monkeypatch) -> pathlib.Path:
    root = tmp_path / "tmp"
    root.mkdir()
    monkeypatch.setenv("TMPDIR", str(root))
    monkeypatch.setattr(tempfile, "tempdir", str(root))
    return root


def _left(root: pathlib.Path) -> list[str]:
    return sorted(p.name for p in root.iterdir())


# --- #331: run_scenario removes its files when it raises ---------------------


def test_raising_progress_callback_leaves_no_temp_files(tmp_root):
    """T1: a cancelled run (the callback raises) removes its trajectory."""
    ticks = []

    def stop(event):
        ticks.append(event)
        assert [p.suffix for p in tmp_root.glob("*.sqlite")] == [".sqlite"]
        raise _Stop("cancelled by the test")

    with pytest.raises(_Stop, match="cancelled by the test"):
        run_scenario(_scenario(ENOUGH_S), progress_callback=stop)
    assert len(ticks) == 1
    assert _left(tmp_root) == []


@pytest.mark.parametrize("name", ["SqliteTrajectoryWriter", "Simulation"])
def test_failed_simulation_set_up_leaves_no_temp_files(tmp_root, monkeypatch, name):
    """T2: an error building the writer or the simulation removes the file."""
    calls = []

    def broken(*args, **kwargs):
        calls.append(sorted(p.name for p in tmp_root.glob("*.sqlite")))
        raise RuntimeError(f"{name} rejected the input")

    monkeypatch.setattr(scenario_module.jps, name, broken)
    with pytest.raises(RuntimeError, match=f"{name} rejected the input"):
        run_scenario(_scenario(ENOUGH_S))
    assert len(calls) == 1 and len(calls[0]) == 1  # the file existed
    assert _left(tmp_root) == []


def test_error_after_the_manifest_leaves_no_temp_files(tmp_root, monkeypatch):
    """T3: an error once the manifest is written removes both files."""
    seen = []

    def broken_run_settings(**kwargs):
        (trajectory,) = tmp_root.glob("*.sqlite")
        seen.append((trajectory.is_file(), manifest_path_for(trajectory).is_file()))
        raise ValueError("run settings failed")

    monkeypatch.setattr(scenario_module, "run_settings", broken_run_settings)
    with pytest.raises(ValueError, match="run settings failed"):
        run_scenario(_scenario(ENOUGH_S))
    assert seen == [(True, True)]
    assert _left(tmp_root) == []


def test_interrupted_run_leaves_no_temp_files(tmp_root):
    """A KeyboardInterrupt also removes the files and keeps its type."""

    def interrupt(_event):
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        run_scenario(_scenario(ENOUGH_S), progress_callback=interrupt)
    assert _left(tmp_root) == []


def test_successful_run_keeps_its_files_for_the_caller(tmp_root):
    """On success the caller owns the files until ``cleanup()``."""
    result = run_scenario(_scenario(ENOUGH_S))
    assert result.sqlite_file is not None and result.manifest_file is not None
    assert pathlib.Path(result.sqlite_file).is_file()
    assert pathlib.Path(result.manifest_file).is_file()
    assert not result.trajectory_dataframe().empty
    result.cleanup()
    assert _left(tmp_root) == []


# --- #524: the front ends that discard the result remove its files ----------


def _recording_run(made: list[tuple[str, str]]):
    """``run_scenario``, recording the temp files of the result it returns."""

    def run(*args, **kwargs):
        result = run_scenario(*args, **kwargs)
        assert result.sqlite_file is not None and result.manifest_file is not None
        made.append((result.sqlite_file, result.manifest_file))
        return result

    return run


def _cli_main(monkeypatch, *argv: str) -> int:
    monkeypatch.setattr(cli, "load_scenario", lambda _path: _scenario(ENOUGH_S))
    monkeypatch.setattr("sys.argv", ["pyfds-evac", "--scenario", "unused", *argv])
    with contextlib.redirect_stdout(io.StringIO()):
        return cli.main()


def test_cli_run_leaves_no_temp_files(tmp_root, tmp_path, monkeypatch):
    """T4: without --cleanup the copy stays and the temp files go."""
    made: list[tuple[str, str]] = []
    monkeypatch.setattr(cli, "run_scenario", _recording_run(made))
    copy = tmp_path / "out" / "run.sqlite"
    assert _cli_main(monkeypatch, "--output-sqlite", str(copy)) == 0
    ((sqlite_file, manifest_file),) = made
    assert pathlib.Path(sqlite_file).parent == tmp_root
    assert pathlib.Path(manifest_file).parent == tmp_root
    assert copy.is_file() and manifest_path_for(copy).is_file()
    assert _left(tmp_root) == []


def test_cli_failed_output_copy_leaves_no_temp_files(tmp_root, monkeypatch):
    """T4: an error writing the outputs still removes the temp files."""
    made: list[tuple[str, str]] = []
    monkeypatch.setattr(cli, "run_scenario", _recording_run(made))

    def broken(*args, **kwargs):
        raise OSError("output folder is read-only")

    monkeypatch.setattr(cli, "apply_outputs", broken)
    with pytest.raises(OSError, match="output folder is read-only"):
        _cli_main(monkeypatch)
    assert len(made) == 1
    assert _left(tmp_root) == []


def test_stream_run_leaves_no_temp_files(tmp_root, tmp_path, monkeypatch):
    """T5: a streamed run keeps its copies and removes the temp files."""
    made: list[tuple[str, str]] = []
    monkeypatch.setattr(scenario_module, "run_scenario", _recording_run(made))
    monkeypatch.setattr(
        scenario_module, "load_scenario", lambda _path: _scenario(ENOUGH_S)
    )
    copy = tmp_path / "out" / "run.sqlite"
    sent: list = []
    outcome = stream_run(
        options({"scenario": "unused", "output_sqlite": str(copy)}), sent.append
    )
    assert outcome.status == events.STATUS_SUCCESS, outcome.error
    assert len(made) == 1
    assert outcome.files == (
        str(copy.resolve()),
        str(manifest_path_for(copy.resolve())),
    )
    assert copy.is_file() and manifest_path_for(copy).is_file()
    assert _left(tmp_root) == []


def _failing_cleanup(_result) -> None:
    raise OSError("permission denied removing the temp trajectory")


def test_cli_cleanup_error_keeps_the_exit_status(tmp_root, tmp_path, monkeypatch):
    """A cleanup OSError neither raises nor changes the exit status."""
    monkeypatch.setattr(scenario_module.ScenarioResult, "cleanup", _failing_cleanup)
    copy = tmp_path / "out" / "run.sqlite"
    assert _cli_main(monkeypatch, "--output-sqlite", str(copy)) == 0
    assert copy.is_file() and manifest_path_for(copy).is_file()


def test_stream_run_cleanup_error_keeps_the_outcome(tmp_root, tmp_path, monkeypatch):
    """A cleanup OSError changes neither the streamed outcome nor its files."""
    monkeypatch.setattr(scenario_module.ScenarioResult, "cleanup", _failing_cleanup)
    monkeypatch.setattr(
        scenario_module, "load_scenario", lambda _path: _scenario(ENOUGH_S)
    )
    copy = tmp_path / "out" / "run.sqlite"
    sent: list = []
    outcome = stream_run(
        options({"scenario": "unused", "output_sqlite": str(copy)}), sent.append
    )
    assert outcome.status == events.STATUS_SUCCESS, outcome.error
    assert outcome.files == (
        str(copy.resolve()),
        str(manifest_path_for(copy.resolve())),
    )
    assert sent[-1] == outcome


def test_cancelled_stream_run_leaves_no_temp_files(tmp_root, monkeypatch):
    """A cancelled streamed run is reported as cancelled and leaves nothing."""
    monkeypatch.setattr(
        scenario_module, "load_scenario", lambda _path: _scenario(ENOUGH_S)
    )
    ticks: list = []

    def cancel() -> bool:
        ticks.append(None)
        return len(ticks) > 1  # past the set-up check, at the first sample

    outcome = stream_run(options({"scenario": "unused"}), [].append, cancel=cancel)
    assert outcome.status == events.STATUS_CANCELLED
    assert _left(tmp_root) == []
