"""The stable ``pyfds_evac.core`` names are pinned; the rest stay importable."""

import importlib

import pytest

import pyfds_evac
import pyfds_evac.core

# The names docs/*.md and README.md import from or reach through
# ``pyfds_evac.core``. Changing this list changes the 1.x API: see
# "API stability" in docs/usage.md.
STABLE_CORE_NAMES = ["load_scenario", "run_scenario"]

# Every name that imports from ``pyfds_evac.core``: stable or dropped from
# ``__all__``. Removing one is a breaking change.
ALL_CORE_NAMES = [
    "ConstantExtinctionField",
    "DefaultFedConfig",
    "DefaultFedInputs",
    "DefaultFedModel",
    "ExtinctionField",
    "FdsFedField",
    "FdsQuantityInventory",
    "FedComponents",
    "ProgressEvent",
    "RerouteConfig",
    "RouteCostConfig",
    "Scenario",
    "ScenarioResult",
    "SliceFieldSampler",
    "SmokeSpeedConfig",
    "SmokeSpeedModel",
    "StageGraph",
    "TenabilityConfig",
    "VisibilityModel",
    "accumulate_default_fed",
    "default_fed_components",
    "default_fed_rate_per_minute",
    "default_fic",
    "extinction_from_soot_density",
    "inspect_fds_quantities",
    "integrated_extinction_along_los",
    "list_simulations",
    "load_scenario",
    "load_slice_sampler",
    "run_scenario",
    "speed_from_soot_density",
    "time_to_fed_threshold_s",
]

DROPPED_FROM_ALL = sorted(set(ALL_CORE_NAMES) - set(STABLE_CORE_NAMES))


def test_core_all_is_pinned():
    assert sorted(pyfds_evac.core.__all__) == STABLE_CORE_NAMES
    assert sorted(dir(pyfds_evac.core)) == STABLE_CORE_NAMES


def test_export_table_is_pinned():
    assert sorted(pyfds_evac.core._EXPORTS) == ALL_CORE_NAMES


def test_stable_core_names_are_public_names_too():
    assert set(pyfds_evac.core.__all__) <= set(pyfds_evac.__all__)


@pytest.mark.parametrize("name", DROPPED_FROM_ALL)
def test_dropped_name_stays_importable(name):
    module = importlib.import_module("pyfds_evac.core")
    attribute = getattr(module, name)
    namespace: dict[str, object] = {}
    exec(f"from pyfds_evac.core import {name}", namespace)
    assert namespace[name] is attribute


# Names outside ``pyfds_evac.__all__`` the stable API also lists, by full
# module path ("API stability" in docs/usage.md).
STABLE_SUBMODULE_NAMES = {
    ("pyfds_evac.config", "DEFAULTS"),
    ("pyfds_evac.config", "EffectiveConfiguration"),
    ("pyfds_evac.config", "effective_configuration"),
    ("pyfds_evac.config.frontend", "stop_reason_phrase"),
    ("pyfds_evac.core", "load_scenario"),
    ("pyfds_evac.core", "run_scenario"),
    ("pyfds_evac.core.manifest", "manifest_path_for"),
    ("pyfds_evac.core.run_config", "build_run_kwargs"),
    ("pyfds_evac.core.run_outputs", "apply_outputs"),
}


def test_exported_script_imports_only_stable_names():
    import ast

    from pyfds_evac import cli
    from pyfds_evac.config.script import python_script

    opts = cli._build_parser().parse_args(["--scenario", "scenario.json"])
    imported = set()
    for node in ast.walk(ast.parse(python_script(opts))):
        if isinstance(node, ast.ImportFrom) and node.module.startswith("pyfds_evac"):
            imported |= {(node.module, alias.name) for alias in node.names}
    assert imported
    stable = STABLE_SUBMODULE_NAMES | {
        ("pyfds_evac", name) for name in pyfds_evac.__all__
    }
    assert imported <= stable


def test_stable_submodule_names_exist_and_are_documented():
    from pathlib import Path

    usage = (Path(__file__).resolve().parents[1] / "docs" / "usage.md").read_text()
    section = usage.split("### API stability", 1)[1].split("\n### ", 1)[0]
    for module, name in STABLE_SUBMODULE_NAMES:
        assert hasattr(importlib.import_module(module), name), (module, name)
        assert name in section, name
