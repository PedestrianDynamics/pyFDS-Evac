"""``--help`` and argument errors do not load the simulation stack (#496).

The first ``pyfds-evac --help`` after an install took 15 s: the CLI imported
JuPedSim, fdsreader, fdsvismap and matplotlib (with its font cache) before
argparse ran. They now load only when a run starts. numpy, which the heat
constants of the parser pulled in through ``core.fed``, loads with them
(#503): its first load after an install takes up to 1 s on macOS.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

import pyfds_evac.core

HEAVY = (
    "jupedsim",
    "fdsreader",
    "fdsvismap",
    "matplotlib",
    "pedpy",
    "shapely",
    "pyfds_evac.core.scenario",
    "numpy",
    "pyfds_evac.core.fds_sampling",
    "pyfds_evac.core.smoke_speed",
)

_PROBE = """\
import contextlib, io, sys
from {module} import main
out = io.StringIO()
with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
    try:
        main({argv})
    except SystemExit as exc:
        code = exc.code
heavy = [m for m in {heavy!r} if m in sys.modules]
print(code, heavy)
"""


def _probe(module: str, argv: str, prog_args: list[str]) -> str:
    code = _PROBE.format(module=module, argv=argv, heavy=HEAVY)
    proc = subprocess.run(
        [sys.executable, "-c", code, *prog_args],
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout.strip()


@pytest.mark.parametrize(
    ("args", "exit_code"),
    [(["--help"], 0), ([], 2), (["--scenario", "x.json", "--no-such"], 2)],
)
def test_cli_parse_does_not_import_simulation_stack(args, exit_code):
    assert _probe("pyfds_evac.cli", "", args) == f"{exit_code} []"


def test_gui_help_does_not_import_simulation_stack():
    assert _probe("pyfds_evac.webapp.launch", "['--help']", []) == "0 []"


def test_cli_names_resolve_lazily():
    from pyfds_evac import cli
    from pyfds_evac.core.scenario import load_scenario

    assert cli.load_scenario is load_scenario
    with pytest.raises(AttributeError, match="no_such_name"):
        cli.no_such_name  # noqa: B018


def test_core_exports_resolve_to_defining_module():
    assert set(pyfds_evac.core.__all__) == set(pyfds_evac.core._EXPORTS)
    for name in pyfds_evac.core.__all__:
        value = getattr(pyfds_evac.core, name)
        assert value.__name__ == name
        assert value.__module__ == pyfds_evac.core._EXPORTS[name]
