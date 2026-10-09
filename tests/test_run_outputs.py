"""The run helpers live below the front ends (#528).

``pyfds_evac.core.run_outputs`` holds the output writing, the run summary
and the logging set-up. The execution layer must not import a front end,
and ``pyfds_evac.cli`` keeps exposing the same objects under its names.
"""

from __future__ import annotations

import ast
import pathlib
from types import SimpleNamespace

import pytest

from pyfds_evac import cli
from pyfds_evac.core import run_outputs

PACKAGE = pathlib.Path(__file__).resolve().parents[1] / "pyfds_evac"


def _imports_cli(node: ast.AST, package: str) -> bool:
    """Whether *node* (in a module of *package*) imports ``pyfds_evac.cli``."""
    if isinstance(node, ast.Import):
        return any(
            alias.name == "pyfds_evac.cli" or alias.name.startswith("pyfds_evac.cli.")
            for alias in node.names
        )
    if not isinstance(node, ast.ImportFrom):
        return False
    if node.level:
        base = package.split(".")[: len(package.split(".")) - node.level + 1]
        module = ".".join(base + ([node.module] if node.module else []))
    else:
        module = node.module or ""
    if module == "pyfds_evac.cli" or module.startswith("pyfds_evac.cli."):
        return True
    return module == "pyfds_evac" and any(a.name == "cli" for a in node.names)


def _offenders(subpackage: str) -> list[str]:
    root = PACKAGE / subpackage
    offenders = []
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if _imports_cli(node, f"pyfds_evac.{subpackage}"):
                offenders.append(f"{path.relative_to(PACKAGE)}:{node.lineno}")
    return offenders


@pytest.mark.parametrize("subpackage", ["core", "config"])
def test_execution_layer_does_not_import_cli(subpackage):
    assert (PACKAGE / subpackage).is_dir()
    assert _offenders(subpackage) == []


@pytest.mark.parametrize(
    "source",
    [
        "import pyfds_evac.cli",
        "from pyfds_evac.cli import apply_outputs",
        "from pyfds_evac import cli",
        "from ..cli import apply_outputs",
        "from .. import cli",
    ],
)
def test_import_check_sees_every_form(source):
    node = ast.parse(source).body[0]
    assert _imports_cli(node, "pyfds_evac.core")


def test_import_check_ignores_other_modules():
    for source in ("from .. import config", "from .run_outputs import apply_outputs"):
        assert not _imports_cli(ast.parse(source).body[0], "pyfds_evac.core")


@pytest.mark.parametrize(
    ("cli_name", "core_name"),
    [
        ("apply_outputs", "apply_outputs"),
        ("_summary_line", "summary_line"),
        ("_configure_logging", "configure_logging"),
        ("_RepeatedFdsreaderWarning", "_RepeatedFdsreaderWarning"),
        ("_export_app_bundle", "_export_app_bundle"),
        ("_write_smoke_history_csv", "_write_smoke_history_csv"),
        ("_write_fed_history_csv", "_write_fed_history_csv"),
        ("_write_route_history_csv", "_write_route_history_csv"),
        ("_write_exit_history_csv", "_write_exit_history_csv"),
        ("_write_route_cost_history_csv", "_write_route_cost_history_csv"),
        ("_maybe_write_agent_scalars", "_maybe_write_agent_scalars"),
        ("_copy_manifest", "_copy_manifest"),
        ("_configuration_record", "_configuration_record"),
    ],
)
def test_cli_reexports_the_core_objects(cli_name, core_name):
    assert getattr(cli, cli_name) is getattr(run_outputs, core_name)


def test_route_history_count_is_labelled_as_rows(tmp_path):
    """The printed count is the number of route-history rows, not switches."""
    rows = [
        {
            "time_s": 0.0,
            "agent_id": a,
            "old_exit": "",
            "new_exit": "B",
            "old_cost": 0.0,
            "new_cost": 0.0,
            "reason": "default_route",
        }
        for a in (1, 2)
    ] + [
        {
            "time_s": 5.0,
            "agent_id": 1,
            "old_exit": "",
            "new_exit": "A",
            "old_cost": 0.0,
            "new_cost": 0.0,
            "reason": "initial",
        }
    ]
    result = SimpleNamespace(
        smoke_history=None,
        fed_history=None,
        route_history=rows,
        route_cost_history=None,
        exit_history=None,
        metrics={},
        sqlite_file=None,
    )
    opts = SimpleNamespace(
        output_smoke_history=None,
        output_fed_history=None,
        output_route_history=str(tmp_path / "routes.csv"),
        output_route_cost_history=None,
        output_sqlite=None,
    )
    lines: list[str] = []
    run_outputs.apply_outputs(result, None, opts, log=lines.append)
    assert lines == ["Route history rows: 3"]
