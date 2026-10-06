"""The ``pyfds-evac`` command: run a scenario, optionally with FDS fire data."""

import argparse
import contextlib
import importlib
import json
import sys
from typing import TYPE_CHECKING

from rich_argparse import RawDescriptionRichHelpFormatter

from pyfds_evac.config.parameters import _u_factor as _u_factor  # noqa: F401
from pyfds_evac.config.parameters import add_arguments

# The run helpers live in core.run_outputs; these names stay importable
# from here for the GUI, the scripts and the tests.
from pyfds_evac.core.run_outputs import (
    _configuration_record as _configuration_record,  # noqa: F401
)
from pyfds_evac.core.run_outputs import _copy_manifest as _copy_manifest  # noqa: F401
from pyfds_evac.core.run_outputs import _export_app_bundle
from pyfds_evac.core.run_outputs import (
    _maybe_write_agent_scalars as _maybe_write_agent_scalars,  # noqa: F401
)
from pyfds_evac.core.run_outputs import (
    _RepeatedFdsreaderWarning as _RepeatedFdsreaderWarning,  # noqa: F401
)
from pyfds_evac.core.run_outputs import (
    _write_exit_history_csv as _write_exit_history_csv,  # noqa: F401
)
from pyfds_evac.core.run_outputs import (
    _write_fed_history_csv as _write_fed_history_csv,  # noqa: F401
)
from pyfds_evac.core.run_outputs import (
    _write_route_cost_history_csv as _write_route_cost_history_csv,  # noqa: F401
)
from pyfds_evac.core.run_outputs import (
    _write_route_history_csv as _write_route_history_csv,  # noqa: F401
)
from pyfds_evac.core.run_outputs import (
    _write_smoke_history_csv as _write_smoke_history_csv,  # noqa: F401
)
from pyfds_evac.core.run_outputs import apply_outputs as apply_outputs
from pyfds_evac.core.run_outputs import configure_logging as _configure_logging
from pyfds_evac.core.run_outputs import summary_line as _summary_line

if TYPE_CHECKING:
    from pyfds_evac.core.fds_inventory import inspect_fds_quantities
    from pyfds_evac.core.run_config import build_run_kwargs
    from pyfds_evac.core.scenario import load_scenario, run_scenario

# The simulation stack (JuPedSim, fdsreader, fdsvismap, matplotlib) loads
# only when a run starts, so --help and argument errors return at once.
# The names stay attributes of this module (``run.load_scenario`` through
# the run.py shim, monkeypatching in tests).
_RUN_STACK = {
    "inspect_fds_quantities": "pyfds_evac.core.fds_inventory",
    "build_run_kwargs": "pyfds_evac.core.run_config",
    "load_scenario": "pyfds_evac.core.scenario",
    "run_scenario": "pyfds_evac.core.scenario",
}


def _load_run_stack() -> None:
    """Import the simulation stack; names already set (patched) are kept."""
    namespace = globals()
    for name, module_name in _RUN_STACK.items():
        if name not in namespace:
            namespace[name] = getattr(importlib.import_module(module_name), name)


def __getattr__(name: str):
    if name not in _RUN_STACK:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    _load_run_stack()
    return globals()[name]


_DESCRIPTION = """\
Run a JuPedSim evacuation scenario (JSON, ZIP or directory). Without FDS
data the agents walk in clear air. With --fds-dir, the FDS smoke slows
them and can hide signs, the toxic gases add up to a fractional effective
dose (FED), and route choice weighs smoke as well as congestion. Heat
dose is opt-in (--enable-heat-fed). Results go to a trajectory SQLite
file and optional per-agent CSV histories."""

_EPILOG = """\
examples:
  # clear air, no fire data
  pyfds-evac --scenario scenario.json

  # with FDS output, smoke and toxic gas coupled
  pyfds-evac --scenario scenario.json --fds-dir fds_case/

  # write the trajectories and per-agent histories
  pyfds-evac --scenario scenario.json --fds-dir fds_case/ \\
      --output-sqlite out/run.sqlite --output-smoke-history out/smoke.csv \\
      --output-fed-history out/fed.csv --output-exit-history out/exits.csv

  # the same settings in a browser form (pip install "pyfds-evac[gui]")
  pyfds-evac-gui

  # start a scenario from an FDS deck (see: pyfds-evac import --help)
  pyfds-evac import deck.fds -o scenario/"""


def _verbatim(heading: str) -> str:
    """Keep group headings as written, e.g. 'FED/FIC' stays upper case."""
    return heading


class _HelpFormatter(RawDescriptionRichHelpFormatter):
    """Rich help with literal brackets (units such as [m]) and headings."""

    group_name_formatter = _verbatim
    help_markup = False
    text_markup = False


def _build_parser() -> argparse.ArgumentParser:
    """Build the command-line interface for scenario runs and exports."""
    parser = argparse.ArgumentParser(
        usage="%(prog)s --scenario PATH [--fds-dir DIR] [options]",
        description=_DESCRIPTION,
        epilog=_EPILOG,
        formatter_class=_HelpFormatter,
    )
    add_arguments(parser)
    return parser


# Exit status of a run that reached max_simulation_time with agents inside or
# flow agents still to enter; its outputs are written as for a completed run.
EXIT_INCOMPLETE = 2


def _show_config(scenario, args) -> int:
    """Print the effective configuration; 1 if the run would stop at setup."""
    from pyfds_evac.config import effective_configuration

    configuration = effective_configuration(args, scenario)
    print(configuration.format_text())
    return 0 if configuration.ok else 1


# Placeholder for an option the command line did not give, so that a
# scenario key can supply it; the CLI value always wins.
_NOT_GIVEN = object()


def _apply_scenario_settings(scenario, args) -> None:
    """Fill options the command line left out from the scenario JSON."""
    if args.smoke_slice_height is not _NOT_GIVEN:
        return
    from pyfds_evac.config.parameters import default
    from pyfds_evac.core.run_config import scenario_smoke_slice_height

    height = scenario_smoke_slice_height(scenario)
    if height is None:
        args.smoke_slice_height = default("smoke_slice_height")
        return
    args.smoke_slice_height = height
    print(
        f"Smoke slice height {height:g} m from the scenario "
        "(simulationParams.smoke_slice_height); --smoke-slice-height overrides it."
    )


def main() -> int:
    """Parse arguments, run the scenario, and export requested outputs."""
    if sys.argv[1:2] == ["import"]:
        from pyfds_evac.cli_import import main as import_main

        return import_main(sys.argv[2:])
    parser = _build_parser()
    args = parser.parse_args(
        namespace=argparse.Namespace(smoke_slice_height=_NOT_GIVEN)
    )
    _configure_logging(args.debug)
    _load_run_stack()

    scenario = load_scenario(args.scenario)
    _apply_scenario_settings(scenario, args)
    print("Initialization started.")

    if args.print_summary:
        print(scenario.summary())

    if args.export_app_bundle:
        _export_app_bundle(scenario, args.export_app_bundle)

    if args.export_only:
        return 0

    if args.inspect_fds:
        if not args.fds_dir:
            raise ValueError("--inspect-fds requires --fds-dir")
        inventory = inspect_fds_quantities(args.fds_dir)
        print(json.dumps(inventory.__dict__, indent=2, sort_keys=True))
        return 0

    if args.show_config:
        return _show_config(scenario, args)

    run_kwargs = build_run_kwargs(scenario, args, log=print)

    print("Initialization finished.")
    print("Simulation started.")

    result = run_scenario(scenario, **run_kwargs)
    # The temporary trajectory is unreachable once main returns: remove it
    # after the outputs are written, or when writing them fails (#524).
    try:
        print(_summary_line(result))

        outside = result.metrics.get("fds_outside")
        if outside and outside["rows"]:
            print(
                f"Outside the FDS domain: {outside['agents']} agent(s), "
                f"{outside['rows']} sample(s), about {outside['agent_seconds']:.1f} "
                "agent-seconds of ambient air and clear sight."
            )

        apply_outputs(result, scenario, args, log=print)
    finally:
        with contextlib.suppress(OSError):
            result.cleanup()
    return 0 if result.success else EXIT_INCOMPLETE


if __name__ == "__main__":
    raise SystemExit(main())
