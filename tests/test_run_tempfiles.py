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

import pathlib
import tempfile

import pytest
from test_run_outcome import ENOUGH_S, _scenario

from pyfds_evac.core import scenario as scenario_module
from pyfds_evac.core.manifest import manifest_path_for
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
    assert pathlib.Path(result.sqlite_file).is_file()
    assert pathlib.Path(result.manifest_file).is_file()
    assert not result.trajectory_dataframe().empty
    result.cleanup()
    assert _left(tmp_root) == []
