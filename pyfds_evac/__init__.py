"""fds-evac package.

The public names below are resolved lazily (PEP 562): ``import pyfds_evac``
stays cheap, and the first attribute access imports the defining module.
"""

import importlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pyfds_evac.core.fed import (
        DefaultFedConfig,
        DefaultFedModel,
        DefaultHeatFedModel,
        FdsFedField,
        FdsHeatField,
        TenabilityConfig,
    )
    from pyfds_evac.core.route_graph import RerouteConfig, RouteCostConfig
    from pyfds_evac.core.run_config import build_run_kwargs
    from pyfds_evac.core.scenario import (
        ProgressEvent,
        Scenario,
        ScenarioResult,
        load_scenario,
        run_scenario,
    )
    from pyfds_evac.core.smoke_speed import (
        ConstantExtinctionField,
        ExtinctionField,
        SmokeSpeedConfig,
        SmokeSpeedModel,
    )
    from pyfds_evac.core.visibility import VisibilityModel

_EXPORTS = {
    "load_scenario": "pyfds_evac.core.scenario",
    "run_scenario": "pyfds_evac.core.scenario",
    "Scenario": "pyfds_evac.core.scenario",
    "ScenarioResult": "pyfds_evac.core.scenario",
    "ProgressEvent": "pyfds_evac.core.scenario",
    "build_run_kwargs": "pyfds_evac.core.run_config",
    "SmokeSpeedModel": "pyfds_evac.core.smoke_speed",
    "SmokeSpeedConfig": "pyfds_evac.core.smoke_speed",
    "ExtinctionField": "pyfds_evac.core.smoke_speed",
    "ConstantExtinctionField": "pyfds_evac.core.smoke_speed",
    "DefaultFedModel": "pyfds_evac.core.fed",
    "DefaultFedConfig": "pyfds_evac.core.fed",
    "FdsFedField": "pyfds_evac.core.fed",
    "DefaultHeatFedModel": "pyfds_evac.core.fed",
    "FdsHeatField": "pyfds_evac.core.fed",
    "TenabilityConfig": "pyfds_evac.core.fed",
    "RerouteConfig": "pyfds_evac.core.route_graph",
    "RouteCostConfig": "pyfds_evac.core.route_graph",
    "VisibilityModel": "pyfds_evac.core.visibility",
}

__all__ = [
    "ConstantExtinctionField",
    "DefaultFedConfig",
    "DefaultFedModel",
    "DefaultHeatFedModel",
    "ExtinctionField",
    "FdsFedField",
    "FdsHeatField",
    "ProgressEvent",
    "RerouteConfig",
    "RouteCostConfig",
    "Scenario",
    "ScenarioResult",
    "SmokeSpeedConfig",
    "SmokeSpeedModel",
    "TenabilityConfig",
    "VisibilityModel",
    "build_run_kwargs",
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
    return sorted(set(globals()) | set(__all__))
