"""One configuration model for the CLI, the GUI and the TUI (#484).

- :mod:`.parameters`: every run option (name, type, unit, default, choices,
  help, the Python field it sets) and the CLI and GUI layout;
- :mod:`.rules`: which models a run builds, option conflicts, and options
  that change nothing;
- :mod:`.effective`: the effective configuration and the equivalent command;
- :mod:`.script`: the equivalent Python script;
- :mod:`.events`: status events of a run, for a front end that runs it in a
  separate process;
- :mod:`.frontend`: the run folders and outcome wording the GUI and the TUI
  share.

Importing this package loads no simulation stack (JuPedSim, fdsreader,
fdsvismap, matplotlib). Provisional public API in 0.3.0: names may change in
0.3.x.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

from .parameters import (
    DEFAULTS,
    GROUPS,
    PARAMETERS,
    RUN_OPTIONS,
    Parameter,
    default,
    option,
    parameter,
)

if TYPE_CHECKING:
    from .effective import EffectiveConfiguration, cli_command, effective_configuration
    from .rules import FdsFacts, check_options

_LAZY = {
    "EffectiveConfiguration": "pyfds_evac.config.effective",
    "effective_configuration": "pyfds_evac.config.effective",
    "cli_command": "pyfds_evac.config.effective",
    "FdsFacts": "pyfds_evac.config.rules",
    "check_options": "pyfds_evac.config.rules",
    "python_script": "pyfds_evac.config.script",
}

__all__ = [
    "DEFAULTS",
    "GROUPS",
    "PARAMETERS",
    "RUN_OPTIONS",
    "EffectiveConfiguration",
    "FdsFacts",
    "Parameter",
    "check_options",
    "cli_command",
    "default",
    "effective_configuration",
    "option",
    "parameter",
    "python_script",
]


def __getattr__(name: str):
    if name not in _LAZY:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return getattr(importlib.import_module(_LAZY[name]), name)
