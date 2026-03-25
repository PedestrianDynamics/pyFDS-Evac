"""JSON-first scenario loading and runtime helpers."""

from .fds_inventory import (
    FdsQuantityInventory,
    inspect_fds_quantities,
    list_simulations,
)
from .fed import (
    DefaultFedInputs,
    DefaultFedConfig,
    DefaultFedModel,
    FdsFedField,
    accumulate_default_fed,
    default_fed_rate_per_minute,
    time_to_fed_threshold_s,
)
from .scenario import Scenario, ScenarioResult, load_scenario, run_scenario
from .smoke_speed import (
    ConstantExtinctionField,
    ExtinctionField,
    SmokeSpeedConfig,
    SmokeSpeedModel,
    extinction_from_soot_density,
    speed_from_soot_density,
)

__all__ = [
    "ConstantExtinctionField",
    "DefaultFedConfig",
    "DefaultFedInputs",
    "DefaultFedModel",
    "ExtinctionField",
    "FdsFedField",
    "FdsQuantityInventory",
    "Scenario",
    "ScenarioResult",
    "SmokeSpeedConfig",
    "SmokeSpeedModel",
    "extinction_from_soot_density",
    "accumulate_default_fed",
    "default_fed_rate_per_minute",
    "speed_from_soot_density",
    "inspect_fds_quantities",
    "list_simulations",
    "load_scenario",
    "run_scenario",
    "time_to_fed_threshold_s",
]
