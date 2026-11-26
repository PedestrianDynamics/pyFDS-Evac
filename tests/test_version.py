"""``pyfds_evac.__version__`` and ``pyfds-evac --version``."""

import subprocess
import sys
from importlib.metadata import version

import pyfds_evac
from pyfds_evac.cli import main


def test_version_matches_installed_metadata():
    assert pyfds_evac.__version__ == version("pyfds-evac")
    assert "__version__" in dir(pyfds_evac)


def test_import_does_not_read_metadata_or_load_core():
    code = "import sys, pyfds_evac;print('pyfds_evac.core.scenario' in sys.modules)"
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    assert out.stdout.strip() == "False"


def test_cli_version_flag(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["pyfds-evac", "--version"])
    try:
        main()
    except SystemExit as exc:
        assert exc.code == 0
    assert capsys.readouterr().out.strip() == f"pyfds-evac {pyfds_evac.__version__}"
