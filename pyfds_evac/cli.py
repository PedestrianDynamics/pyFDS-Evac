"""The ``pyfds-evac`` command: run a scenario, optionally with FDS fire data."""

import argparse
import csv
import importlib
import json
import logging
import pathlib
import shutil
import sys
from typing import TYPE_CHECKING

from rich_argparse import RawDescriptionRichHelpFormatter

from pyfds_evac.config.parameters import _u_factor as _u_factor  # noqa: F401
from pyfds_evac.config.parameters import add_arguments
from pyfds_evac.core.agent_scalars import write_agent_scalars
from pyfds_evac.core.manifest import manifest_path_for

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
  pyfds-evac-gui"""


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


def _export_app_bundle(scenario, output_dir: str) -> None:
    """Write the loaded scenario as `config.json` plus raw `geometry.wkt`."""
    destination = pathlib.Path(output_dir).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "config.json").write_text(
        json.dumps(scenario.raw, indent=2) + "\n",
        encoding="utf-8",
    )
    (destination / "geometry.wkt").write_text(
        scenario.walkable_area_wkt.strip() + "\n",
        encoding="utf-8",
    )


def _write_smoke_history_csv(rows, output_path: str) -> None:
    """Write sampled smoke-speed history rows to a CSV file."""
    destination = pathlib.Path(output_path).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "time_s",
        "agent_id",
        "x",
        "y",
        "base_speed",
        "desired_speed",
        "speed_factor",
        "extinction_per_m",
    ]
    if rows and "in_fds_domain" in rows[0]:
        fieldnames.append("in_fds_domain")
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _write_fed_history_csv(rows, output_path: str) -> None:
    """Write sampled FED history rows to a CSV file."""
    destination = pathlib.Path(output_path).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
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
    if rows and "heat_endpoint" in rows[0]:
        fieldnames += ["heat_endpoint", "heat_outside_validity", "heat_humidity"]
    if rows and "heat_flux_kw_m2" in rows[0]:
        fieldnames.append("heat_flux_kw_m2")
    if rows and "heat_integrated_intensity_kw_m2" in rows[0]:
        fieldnames.append("heat_integrated_intensity_kw_m2")
    if rows and "heat_layer_temperature_c" in rows[0]:
        fieldnames.append("heat_layer_temperature_c")
    if rows and "in_fds_domain" in rows[0]:
        fieldnames.append("in_fds_domain")
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _write_route_history_csv(rows, output_path: str) -> None:
    """Write route switch history rows to a CSV file."""
    destination = pathlib.Path(output_path).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "time_s",
        "agent_id",
        "old_exit",
        "new_exit",
        "old_cost",
        "new_cost",
        "reason",
    ]
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _write_exit_history_csv(rows, output_path: str) -> None:
    """Write per-agent exit rows to a CSV file."""
    destination = pathlib.Path(output_path).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["agent_id", "origin", "spawn_index", "exit_id"]
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _write_route_cost_history_csv(rows, output_path: str) -> None:
    """Write ranked route cost snapshots to a CSV file."""
    destination = pathlib.Path(output_path).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
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
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _maybe_write_agent_scalars(output_path, fed_history) -> None:
    """Write the agent_scalars side table into the copied sqlite if FED ran."""
    if not fed_history:
        return
    write_agent_scalars(pathlib.Path(output_path).resolve(), fed_history)


def _copy_manifest(
    result, output_path: pathlib.Path, configuration: dict | None = None
) -> pathlib.Path | None:
    """Copy the run manifest beside the copied trajectory, if there is one.

    *configuration*, the effective configuration of the run, is added to
    the copy under ``configuration``.
    """
    manifest_file = getattr(result, "manifest_file", None)
    if not manifest_file or not pathlib.Path(manifest_file).is_file():
        return None
    destination = manifest_path_for(output_path)
    shutil.copy2(manifest_file, destination)
    if configuration is not None:
        manifest = json.loads(destination.read_text())
        manifest["configuration"] = configuration
        destination.write_text(json.dumps(manifest, indent=2) + "\n")
    return destination


def _configuration_record(scenario, opts, result) -> dict | None:
    """The configuration the run used, for the manifest, or None if it fails.

    Checked against what ``run_scenario`` reports it used
    (``result.run_settings``); see ``pyfds_evac.config.effective.run_record``.
    """
    from pyfds_evac.config.effective import effective_configuration, run_record

    try:
        configuration = effective_configuration(opts, scenario)
        return run_record(configuration, getattr(result, "run_settings", None))
    except (OSError, ValueError, TypeError) as exc:
        logging.getLogger(__name__).warning(
            "Could not record the effective configuration in the manifest: %s",
            exc,
        )
        return None


# Exit status of a run that reached max_simulation_time with agents inside or
# flow agents still to enter; its outputs are written as for a completed run.
EXIT_INCOMPLETE = 2


class _RepeatedFdsreaderWarning(logging.Filter):
    """Pass the first fdsreader module-parse warning of each kind, drop repeats.

    fdsreader (1.11.7) logs a failure to parse an optional module, such as
    ``vents``, on the root logger every time a ``Simulation`` is opened, and
    a run opens one per sampler. The first occurrence still reaches the
    console. Upstream issue: none yet. Remove when fdsreader reports each
    failure once or through its own logger.
    """

    def __init__(self) -> None:
        super().__init__()
        self._seen: set[str] = set()

    def filter(self, record: logging.LogRecord) -> bool:
        if record.name != "root":
            return True
        message = record.getMessage()
        if not message.startswith("Module ") or "safely ignored" not in message:
            return True
        key = message.splitlines()[0]
        if key in self._seen:
            return False
        self._seen.add(key)
        return True


def _configure_logging(debug: bool) -> None:
    """Collapse repeated fdsreader warnings; with ``debug``, print debug lines."""
    root = logging.getLogger()
    if not any(isinstance(f, _RepeatedFdsreaderWarning) for f in root.filters):
        root.addFilter(_RepeatedFdsreaderWarning())
    if not debug:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    model_logger = logging.getLogger("pyfds_evac")
    model_logger.addHandler(handler)
    model_logger.setLevel(logging.DEBUG)
    # The root logger may gain a handler later (fdsreader's first warning
    # calls basicConfig), which would print every debug line a second time.
    model_logger.propagate = False


def _summary_line(result) -> str:
    """One line on how the run ended; a run cut off by the time limit is incomplete."""
    if result.success:
        return (
            f"Simulation finished in {result.evacuation_time:.2f} s "
            f"({result.agents_evacuated}/{result.total_agents} evacuated)."
        )
    not_spawned = (
        f", {result.agents_not_spawned} not spawned"
        if result.agents_not_spawned
        else ""
    )
    return (
        "Simulation incomplete: time limit reached after "
        f"{result.evacuation_time:.2f} s "
        f"({result.agents_evacuated}/{result.total_agents} evacuated, "
        f"{result.agents_remaining} remaining{not_spawned})."
    )


def _show_config(scenario, args) -> int:
    """Print the effective configuration; 1 if the run would stop at setup."""
    from pyfds_evac.config import effective_configuration

    configuration = effective_configuration(args, scenario)
    print(configuration.format_text())
    return 0 if configuration.ok else 1


def main() -> int:
    """Parse arguments, run the scenario, and export requested outputs."""
    parser = _build_parser()
    args = parser.parse_args()
    _configure_logging(args.debug)
    _load_run_stack()

    scenario = load_scenario(args.scenario)
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
    print(_summary_line(result))

    outside = result.metrics.get("fds_outside")
    if outside and outside["rows"]:
        print(
            f"Outside the FDS domain: {outside['agents']} agent(s), "
            f"{outside['rows']} sample(s), about {outside['agent_seconds']:.1f} "
            "agent-seconds of ambient air and clear sight."
        )

    apply_outputs(result, scenario, args, log=print)
    return 0 if result.success else EXIT_INCOMPLETE


def apply_outputs(result, scenario, opts, log=print) -> list[str]:
    """Write the output/export artifacts requested by ``opts``.

    Shared by the CLI and the web GUI so both honor the same flags. Returns a
    list of human-readable descriptions of the artifacts written. ``cleanup``
    is applied last, after any sqlite copy.
    """
    artifacts: list[str] = []

    if getattr(opts, "export_app_bundle", None):
        _export_app_bundle(scenario, opts.export_app_bundle)
        artifacts.append(f"App bundle: {opts.export_app_bundle}")

    if opts.output_smoke_history and result.smoke_history is not None:
        _write_smoke_history_csv(result.smoke_history, opts.output_smoke_history)
        artifacts.append(f"Smoke history CSV: {opts.output_smoke_history}")
    if opts.output_fed_history and result.fed_history is not None:
        _write_fed_history_csv(result.fed_history, opts.output_fed_history)
        artifacts.append(f"FED history CSV: {opts.output_fed_history}")
    if opts.output_route_history and result.route_history is not None:
        _write_route_history_csv(result.route_history, opts.output_route_history)
        artifacts.append(f"Route history CSV: {opts.output_route_history}")
        log(f"Route switches: {len(result.route_history)}")
    if opts.output_route_cost_history and result.route_cost_history is not None:
        _write_route_cost_history_csv(
            result.route_cost_history, opts.output_route_cost_history
        )
        artifacts.append(f"Route cost CSV: {opts.output_route_cost_history}")
        log(f"Route cost samples: {len(result.route_cost_history)}")
    output_exit_history = getattr(opts, "output_exit_history", None)
    if output_exit_history and result.exit_history is not None:
        _write_exit_history_csv(result.exit_history, output_exit_history)
        artifacts.append(f"Exit history CSV: {output_exit_history}")

    if opts.output_sqlite and result.sqlite_file:
        output_path = pathlib.Path(opts.output_sqlite).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(result.sqlite_file, output_path)
        artifacts.append(f"Trajectory SQLite: {output_path}")
        manifest_path = _copy_manifest(
            result, output_path, _configuration_record(scenario, opts, result)
        )
        if manifest_path is not None:
            artifacts.append(f"Run manifest: {manifest_path}")
        _maybe_write_agent_scalars(output_path, result.fed_history)

    if getattr(opts, "cleanup", False):
        result.cleanup()

    return artifacts


if __name__ == "__main__":
    raise SystemExit(main())
