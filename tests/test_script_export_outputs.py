"""The exported script writes the CLI's outputs (#328, #924).

Kind: equivalence. The script and the GUI's worker resolve the same options,
call the same ``apply_outputs`` and so write the same set of files, with the
same CSV headers and sqlite tables, for one seed.
"""

from __future__ import annotations

import contextlib
import json
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("fasthtml")

from pyfds_evac.config.script import python_script  # noqa: E402
from pyfds_evac.core import run_scenario  # noqa: E402
from pyfds_evac.core.run_config import build_run_kwargs  # noqa: E402
from pyfds_evac.core.run_outputs import apply_outputs  # noqa: E402
from pyfds_evac.webapp import params  # noqa: E402
from pyfds_evac.webapp.app import _resolve_form  # noqa: E402

ASSETS = Path(__file__).resolve().parents[1] / "assets"
SEED = 420


def _files(folder: Path) -> set[str]:
    return {p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file()}


def _tables(db: Path) -> set[str]:
    with contextlib.closing(sqlite3.connect(db)) as con:
        rows = con.execute("SELECT name FROM sqlite_master WHERE type='table'")
        return {name for (name,) in rows}


def _header(csv: Path) -> str:
    return csv.read_text().splitlines()[0]


@pytest.fixture(scope="module")
def runs(tmp_path_factory):
    """One GUI-style run and one script run of the same FED-enabled options."""
    root = tmp_path_factory.mktemp("outputs")
    deck = root / "assets" / "labelled"
    shutil.copytree(ASSETS / "single_exit_clear_air", deck)
    config = json.loads((deck / "config.json").read_text())
    config["distributions"]["area_a"]["parameters"]["population"] = "victim"
    (deck / "config.json").write_text(json.dumps(config))
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(params, "_ASSET_ROOT", root / "assets")
    fds = root / "fds"
    shutil.copytree(ASSETS / "fed_slice_height" / "fds", fds)
    form = {
        "scenario": "labelled",
        "seed": str(SEED),
        "fds_dir": str(fds),
        "allow_fds_horizon_hold": "on",
        "output_base": str(root / "gui"),
    }
    scenario, opts = _resolve_form(dict(form))
    gui_dir = Path(opts.output_sqlite).parent
    kwargs = build_run_kwargs(scenario, opts, log=lambda *_: None)
    result = run_scenario(scenario, **kwargs)
    apply_outputs(result, scenario, opts, log=lambda *_: None)
    script_dir = root / "script"
    script = root / "run_script.py"
    script.write_text(
        python_script(
            {**vars(opts), "scenario": str(deck)},
            output_dir=str(script_dir),
        )
    )
    done = subprocess.run(
        [sys.executable, str(script)], cwd=root, capture_output=True, text=True
    )
    assert done.returncode in (0, 2), done.stderr[-3000:]
    monkeypatch.undo()
    return gui_dir, script_dir, opts


def test_the_script_writes_the_files_of_the_gui_run(runs):
    gui_dir, script_dir, opts = runs
    names = _files(gui_dir)
    assert Path(opts.output_sqlite).name in names
    assert "bundle/config.json" in names
    assert _files(script_dir) == names


def test_the_script_csv_headers_equal_the_gui_headers(runs):
    gui_dir, script_dir, _ = runs
    csvs = sorted(p.name for p in gui_dir.glob("*.csv"))
    assert any(name.endswith("_fed_history.csv") for name in csvs)
    for name in csvs:
        assert _header(script_dir / name) == _header(gui_dir / name), name


def test_the_script_sqlite_has_the_side_tables(runs):
    gui_dir, script_dir, opts = runs
    name = Path(opts.output_sqlite).name
    expected = {"agent_scalars", "agent_exits", "agent_distributions"}
    assert expected <= _tables(gui_dir / name)
    assert _tables(script_dir / name) == _tables(gui_dir / name)
