"""JSON-first scenario loading and runtime helpers.

The names below are resolved lazily (PEP 562): importing a submodule such
as ``pyfds_evac.core.fed`` does not load the simulation stack (JuPedSim,
fdsreader, fdsvismap, matplotlib); the first attribute access imports the
defining module.
"""

import importlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .scenario import load_scenario, run_scenario

_EXPORTS = {
    "FdsQuantityInventory": "pyfds_evac.core.fds_inventory",
    "inspect_fds_quantities": "pyfds_evac.core.fds_inventory",
    "list_simulations": "pyfds_evac.core.fds_inventory",
    "SliceFieldSampler": "pyfds_evac.core.fds_sampling",
    "load_slice_sampler": "pyfds_evac.core.fds_sampling",
    "DefaultFedConfig": "pyfds_evac.core.fed",
    "DefaultFedInputs": "pyfds_evac.core.fed",
    "DefaultFedModel": "pyfds_evac.core.fed",
    "FdsFedField": "pyfds_evac.core.fed",
    "FedComponents": "pyfds_evac.core.fed",
    "TenabilityConfig": "pyfds_evac.core.fed",
    "accumulate_default_fed": "pyfds_evac.core.fed",
    "default_fed_components": "pyfds_evac.core.fed",
    "default_fed_rate_per_minute": "pyfds_evac.core.fed",
    "default_fic": "pyfds_evac.core.fed",
    "time_to_fed_threshold_s": "pyfds_evac.core.fed",
    "RerouteConfig": "pyfds_evac.core.route_graph",
    "RouteCostConfig": "pyfds_evac.core.route_graph",
    "StageGraph": "pyfds_evac.core.route_graph",
    "integrated_extinction_along_los": "pyfds_evac.core.route_graph",
    "ProgressEvent": "pyfds_evac.core.scenario",
    "Scenario": "pyfds_evac.core.scenario",
    "ScenarioResult": "pyfds_evac.core.scenario",
    "load_scenario": "pyfds_evac.core.scenario",
    "run_scenario": "pyfds_evac.core.scenario",
    "ConstantExtinctionField": "pyfds_evac.core.smoke_speed",
    "ExtinctionField": "pyfds_evac.core.smoke_speed",
    "SmokeSpeedConfig": "pyfds_evac.core.smoke_speed",
    "SmokeSpeedModel": "pyfds_evac.core.smoke_speed",
    "extinction_from_soot_density": "pyfds_evac.core.smoke_speed",
    "speed_from_soot_density": "pyfds_evac.core.smoke_speed",
    "VisibilityModel": "pyfds_evac.core.visibility",
}

# The stable names: those the documentation uses from this namespace. Every
# other name in _EXPORTS stays importable but may change in a minor release.
__all__ = [
    "load_scenario",
    "run_scenario",
]


def __getattr__(name: str):
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(importlib.import_module(module_name), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(__all__)
