"""JSON-first scenario loading and runtime helpers.

The names below are resolved lazily (PEP 562): importing a submodule such
as ``pyfds_evac.core.fed`` does not load the simulation stack (JuPedSim,
fdsreader, fdsvismap, matplotlib); the first attribute access imports the
defining module.
"""

import importlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .fds_inventory import (
        FdsQuantityInventory,
        inspect_fds_quantities,
        list_simulations,
    )
    from .fds_sampling import SliceFieldSampler, load_slice_sampler
    from .fed import (
        DefaultFedConfig,
        DefaultFedInputs,
        DefaultFedModel,
        FdsFedField,
        FedComponents,
        TenabilityConfig,
        accumulate_default_fed,
        default_fed_components,
        default_fed_rate_per_minute,
        default_fic,
        time_to_fed_threshold_s,
    )
    from .route_graph import (
        RerouteConfig,
        RouteCostConfig,
        StageGraph,
        integrated_extinction_along_los,
    )
    from .scenario import (
        ProgressEvent,
        Scenario,
        ScenarioResult,
        load_scenario,
        run_scenario,
    )
    from .smoke_speed import (
        ConstantExtinctionField,
        ExtinctionField,
        SmokeSpeedConfig,
        SmokeSpeedModel,
        extinction_from_soot_density,
        speed_from_soot_density,
    )
    from .visibility import VisibilityModel

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

__all__ = [
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


def __getattr__(name: str):
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(importlib.import_module(module_name), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
