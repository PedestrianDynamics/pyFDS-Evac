"""The run helpers live below the front ends (#528).

``pyfds_evac.core.run_outputs`` holds the output writing, the run summary
and the logging set-up. The execution layer must not import a front end,
and ``pyfds_evac.cli`` keeps exposing the same objects under its names.
"""

from __future__ import annotations

import ast
import csv
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


def _csv(path):
    """The header and the rows of a written CSV file."""
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        return reader.fieldnames, rows


FED_COLUMNS = [
    "time_s",
    "agent_id",
    "x",
    "y",
    "co_percent",
    "co2_percent",
    "o2_percent",
    "hcn_ppm",
    "no_ppm",
    "no2_ppm",
    "co_rate_per_min",
    "cn_rate_per_min",
    "nox_rate_per_min",
    "fld_rate_per_min",
    "hv_co2",
    "o2_rate_per_min",
    "fed_rate_per_min",
    "fed_cumulative",
    "temperature_celsius",
    "heat_fed_rate_per_min",
    "heat_fed_cumulative",
    "incapacitation_cause",
    "fic",
    "fic_speed_factor",
    "incapacitated",
    "base_speed",
    "desired_speed",
    "speed_factor",
]
HEAT_COLUMNS = {
    "heat_endpoint": "convective",
    "heat_outside_validity": "True",
    "heat_humidity": "0.5",
    "heat_flux_kw_m2": "1.5",
    "heat_integrated_intensity_kw_m2": "2.5",
    "heat_layer_temperature_c": "80.0",
    "in_fds_domain": "False",
}


def test_fed_csv_has_the_gas_columns_and_each_optional_group_when_present(tmp_path):
    """Every key of a row is written; optional columns follow in a fixed order."""
    gas = {name: str(index) for index, name in enumerate(FED_COLUMNS)}
    plain = tmp_path / "plain.csv"
    run_outputs._write_fed_history_csv([gas], str(plain))
    assert _csv(plain) == (FED_COLUMNS, [gas])

    full = tmp_path / "full.csv"
    run_outputs._write_fed_history_csv([{**gas, **HEAT_COLUMNS}], str(full))
    header, rows = _csv(full)
    assert header == FED_COLUMNS + list(HEAT_COLUMNS)
    assert rows == [{**gas, **HEAT_COLUMNS}]


def test_exit_csv_records_whether_the_exit_was_in_the_agents_map(tmp_path):
    """``exit_in_map`` is written; the writer ignores keys it does not know."""
    path = tmp_path / "exits.csv"
    rows = [
        {
            "agent_id": 3,
            "origin": "hall",
            "spawn_index": 0,
            "exit_id": "A",
            "exit_in_map": False,
            "unlisted": "dropped",
        }
    ]
    run_outputs._write_exit_history_csv(rows, str(path))
    header, written = _csv(path)
    assert header == ["agent_id", "origin", "spawn_index", "exit_id", "exit_in_map"]
    assert written == [
        {
            "agent_id": "3",
            "origin": "hall",
            "spawn_index": "0",
            "exit_id": "A",
            "exit_in_map": "False",
        }
    ]


def test_route_cost_csv_has_the_queue_and_capacity_columns(tmp_path):
    path = tmp_path / "costs.csv"
    columns = [
        "time_s",
        "agent_id",
        "source",
        "current_exit",
        "current_fed",
        "route_rank",
        "exit_id",
        "path",
        "path_length_m",
        "k_ave_route",
        "travel_time_s",
        "fed_max_route",
        "composite_cost",
        "rank_cost",
        "k_max_route",
        "tau_route",
        "k_leg_max",
        "clean",
        "feasible",
        "rejected",
        "rejection_reason",
        "queue_time_s",
        "exit_count",
        "exit_capacity",
    ]
    row = {name: str(index) for index, name in enumerate(columns)}
    run_outputs._write_route_cost_history_csv([row], str(path))
    assert _csv(path) == (columns, [row])


def test_summary_line_names_the_placed_count_and_the_upper_bound():
    """Placed 5 of at most 8: the two numbers differ, so a swap shows."""
    result = SimpleNamespace(
        success=True,
        evacuation_time=12.0,
        agents_evacuated=5,
        total_agents=5,
        fill_placement={"hall": {"placed": 5, "upper_bound": 8}},
    )
    assert run_outputs.summary_line(result) == (
        "Simulation finished in 12.00 s (5/5 evacuated). 'hall' placed 5 of at most 8."
    )
