"""``pyfds_evac.__version__`` and ``pyfds-evac --version``."""

import subprocess
import sys
import tomllib
from importlib.metadata import version
from pathlib import Path

import pytest

import pyfds_evac
from pyfds_evac.cli import _build_parser, main


def test_version_matches_installed_metadata():
    assert pyfds_evac.__version__ == version("pyfds-evac")
    assert "__version__" in dir(pyfds_evac)


def test_import_does_not_load_the_simulation_core():
    code = "import sys, pyfds_evac;print('pyfds_evac.core.scenario' in sys.modules)"
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    assert out.stdout.strip() == "False"


def test_cli_version_flag(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["pyfds-evac", "--version"])
    with pytest.raises(SystemExit) as exit_info:
        main()
    assert exit_info.value.code == 0
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


def test_version_matches_pyproject():
    """Catches a stale dist-info (editable install) after a version bump."""
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    if not pyproject.is_file():
        pytest.skip("no pyproject.toml next to the tests")
    declared = tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"][
        "version"
    ]
    assert pyfds_evac.__version__ == declared
