"""The CLI and the GUI work from an installed wheel, not only from a checkout.

``run.py`` at the repository root is not packaged. The command line interface
lives in ``pyfds_evac.cli``, installs as the ``pyfds-evac`` command and runs
as ``python -m pyfds_evac``; ``run.py`` only runs it (#471).
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
ASSETS = REPO / "assets"

# Fast scenarios: ISO-table21 completes (exit 0), t_junction reaches its time
# limit with agents inside (exit 2) and switches routes.
SMALL = "ISO-table21"
INCOMPLETE = "t_junction"


def _run(
    args: list[str], cwd: Path, program: str = sys.executable
) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k != "PYFDS_EVAC_RESULTS_DIR"}
    # JuPedSim's SQLite writer keys the geometry by Python's salted hash() of
    # its WKT, so two runs differ in that key unless the salt is fixed.
    env["PYTHONHASHSEED"] = "0"
    return subprocess.run(
        [program, *args], cwd=cwd, env=env, capture_output=True, text=True
    )


def _outputs(out: Path) -> list[str]:
    return [
        "--output-sqlite",
        str(out / "run.sqlite"),
        "--output-route-history",
        str(out / "route.csv"),
        "--output-route-cost-history",
        str(out / "route_cost.csv"),
        "--output-exit-history",
        str(out / "exit.csv"),
        "--cleanup",
    ]


def _rows(sqlite: Path) -> dict[str, list[tuple]]:
    """Every row of every table, in a stable order."""
    with sqlite3.connect(sqlite) as con:
        tables = [
            name
            for (name,) in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
        ]
        return {t: sorted(con.execute(f'SELECT * FROM "{t}"')) for t in tables}


def _manifest(out: Path) -> dict:
    data = json.loads((out / "run.manifest.json").read_text())
    data.pop("created_utc")  # wall-clock time of the run
    return data


def _log(stdout: str) -> list[str]:
    """Log lines without the progress line, whose wall time varies."""
    return [
        line
        for line in stdout.replace("\r", "\n").splitlines()
        if line.strip() and "wall=" not in line
    ]


# The console script that installing the package creates beside the interpreter.
CONSOLE_SCRIPT = Path(sys.executable).parent / "pyfds-evac"


@pytest.mark.parametrize("command", ["module", "console-script"])
def test_run_py_and_the_command_give_identical_outputs(tmp_path, command):
    """run.py, ``python -m pyfds_evac`` and ``pyfds-evac`` are one CLI (#471)."""
    if command == "console-script" and not CONSOLE_SCRIPT.is_file():
        pytest.skip(f"{CONSOLE_SCRIPT} not installed; run uv sync")
    scenario = str(ASSETS / INCOMPLETE)
    a, b = tmp_path / "run_py", tmp_path / command
    first = _run(["run.py", "--scenario", scenario, *_outputs(a)], REPO)
    args = ["--scenario", scenario, *_outputs(b)]
    if command == "module":
        second = _run(["-m", "pyfds_evac", *args], REPO)
    else:
        second = _run(args, REPO, program=str(CONSOLE_SCRIPT))

    assert first.returncode == second.returncode == 2, first.stderr + second.stderr
    assert _rows(a / "run.sqlite") == _rows(b / "run.sqlite")
    for name in ("route.csv", "route_cost.csv", "exit.csv"):
        assert (a / name).read_bytes() == (b / name).read_bytes(), name
    assert _manifest(a) == _manifest(b)
    assert [line.replace(str(a), "OUT") for line in _log(first.stdout)] == [
        line.replace(str(b), "OUT") for line in _log(second.stdout)
    ]
    assert "Simulation incomplete" in first.stdout


def test_run_py_help_is_the_package_help():
    """Same flags, defaults and help text; only the program name differs."""
    from pyfds_evac import cli

    shown = _run(["run.py", "--help"], REPO)
    assert shown.returncode == 0
    parser = cli._build_parser()
    parser.prog = "run.py"
    assert shown.stdout == parser.format_help()


def test_import_run_is_the_cli_module():
    """Callers of run._build_parser, run.apply_outputs, ... keep working."""
    import run
    from pyfds_evac import cli

    assert run is cli


def test_gui_parser_builds_without_run(tmp_path):
    """The GUI builds its form from pyfds_evac.cli, never from run.py."""
    pytest.importorskip("fasthtml")
    code = (
        "import sys\n"
        "sys.modules['run'] = None\n"  # `import run` now raises ImportError
        "from pyfds_evac.webapp import app, params\n"
        "parser = params._load_parser()\n"
        "assert '--scenario' in parser.format_help()\n"
        "assert params.form_to_opts({'scenario': 'x'}).scenario == 'x'\n"
    )
    result = _run(["-c", code], tmp_path)
    assert result.returncode == 0, result.stderr


@pytest.fixture(scope="module")
def installed_wheel(tmp_path_factory) -> Path:
    """The built wheel, unpacked as it would be into site-packages."""
    uv = shutil.which("uv")
    if uv is None:
        pytest.skip("uv not available to build the wheel")
    dist = tmp_path_factory.mktemp("dist")
    subprocess.run(
        [uv, "build", "--wheel", "--out-dir", str(dist), str(REPO)],
        check=True,
        capture_output=True,
    )
    (wheel,) = dist.glob("pyfds_evac-*.whl")
    site = tmp_path_factory.mktemp("site-packages")
    with zipfile.ZipFile(wheel) as archive:
        archive.extractall(site)
    return site


# Runs the wheel's console script the way its generated wrapper does, with the
# checkout removed from sys.path (an editable install puts it there).
_ENTRY_POINT = """
import importlib.metadata, json, sys
site, repo = sys.argv[1], sys.argv[2]
sys.path[:] = [site] + [p for p in sys.path if p not in ("", ".", repo)]
(dist,) = importlib.metadata.distributions(path=[site])
(ep,) = [e for e in dist.entry_points if e.group == "console_scripts"]
assert ep.name == "pyfds-evac", ep
main = ep.load()
import pyfds_evac
assert pyfds_evac.__file__.startswith(site), pyfds_evac.__file__
try:
    import run
except ImportError:
    pass
else:
    raise AssertionError("run.py is importable: " + run.__file__)
sys.argv = ["pyfds-evac", *sys.argv[3:]]
sys.exit(main())
"""


def test_wheel_contains_the_cli(installed_wheel):
    files = {
        p.relative_to(installed_wheel).as_posix() for p in installed_wheel.rglob("*")
    }
    assert {"pyfds_evac/cli.py", "pyfds_evac/__main__.py"} <= files
    assert "run.py" not in files
    (entry_points,) = installed_wheel.glob("pyfds_evac-*.dist-info/entry_points.txt")
    assert "pyfds-evac = pyfds_evac.cli:main" in entry_points.read_text()


def test_wheel_command_runs_outside_the_repository(installed_wheel, tmp_path):
    script = tmp_path / "entry.py"
    script.write_text(_ENTRY_POINT)
    shutil.copytree(ASSETS / SMALL, tmp_path / SMALL)
    args = [str(script), str(installed_wheel), str(REPO)]

    shown = _run([*args, "--help"], tmp_path)
    assert shown.returncode == 0, shown.stderr
    assert shown.stdout.startswith("usage: pyfds-evac")

    ran = _run(
        [*args, "--scenario", SMALL, "--output-sqlite", "out/run.sqlite"], tmp_path
    )
    assert ran.returncode == 0, ran.stderr
    assert "Simulation finished" in ran.stdout
    assert (tmp_path / "out" / "run.sqlite").is_file()
    assert (tmp_path / "out" / "run.manifest.json").is_file()


def test_wheel_gui_roots_are_the_working_directory(installed_wheel, tmp_path):
    """Installed, the GUI reads ./assets and writes under the working directory."""
    pytest.importorskip("fasthtml")
    code = (
        "import sys\n"
        f"site, repo = {str(installed_wheel)!r}, {str(REPO)!r}\n"
        "sys.path[:] = [site] + [p for p in sys.path if p not in ('', '.', repo)]\n"
        "sys.modules['run'] = None\n"
        "from pathlib import Path\n"
        "from pyfds_evac.webapp import app, params\n"
        "assert params.__file__.startswith(site), params.__file__\n"
        "cwd = Path.cwd().resolve()\n"
        "assert params._WORK_ROOT.resolve() == cwd, params._WORK_ROOT\n"
        "assert params._ASSET_ROOT.resolve() == cwd / 'assets'\n"
        "assert params._UPLOAD_ROOT.resolve() == cwd / 'uploads'\n"
        "assert params.results_root().resolve() == cwd / 'results'\n"
        f"assert params._scenario_options() == [({SMALL!r}, {SMALL!r})]\n"
        "params._load_parser()\n"
    )
    (tmp_path / "assets").mkdir()
    shutil.copytree(ASSETS / SMALL, tmp_path / "assets" / SMALL)
    result = _run(["-c", code], tmp_path)
    assert result.returncode == 0, result.stderr
