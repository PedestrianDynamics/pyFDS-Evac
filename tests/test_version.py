"""``pyfds_evac.__version__`` and ``pyfds-evac --version``."""

import subprocess
import sys
from importlib.metadata import version

import pyfds_evac
from pyfds_evac.cli import _build_parser, main


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


def test_version_is_unknown_without_distribution_metadata(monkeypatch):
    import importlib.metadata

    def missing(name):
        raise importlib.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(importlib.metadata, "version", missing)
    monkeypatch.delattr(pyfds_evac, "__version__", raising=False)
    try:
        assert pyfds_evac.__version__ == "unknown"
        assert hasattr(pyfds_evac, "__version__")
        _build_parser()
    finally:
        monkeypatch.undo()
        vars(pyfds_evac).pop("__version__", None)
