"""Run JSON-first JuPedSim scenarios from the fds-evac repository."""

import argparse
import csv
import json
import pathlib
import shutil

from pyfds_evac.core import (
    inspect_fds_quantities,
    load_scenario,
    run_scenario,
)
from pyfds_evac.core.agent_scalars import write_agent_scalars
from pyfds_evac.core.run_config import build_run_kwargs


def _build_parser() -> argparse.ArgumentParser:
    """Build the command-line interface for scenario runs and exports."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenario", required=True, help="Scenario JSON, ZIP, or directory"
    )
    parser.add_argument("--seed", type=int, default=None, help="Override scenario seed")
    parser.add_argument(
        "--print-summary",
        action="store_true",
        help="Print the loaded scenario summary before running",
    )
    parser.add_argument(
        "--output-sqlite",
        help="Copy the generated trajectory SQLite file to this location",
    )
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Delete the temporary trajectory SQLite file after the run",
    )
    parser.add_argument(
        "--export-app-bundle",
        help="Write config.json and geometry.wkt to this directory",
    )
    parser.add_argument(
        "--export-only",
        action="store_true",
        help="Export the scenario bundle without running the simulation",
    )
    parser.add_argument(
        "--fds-dir",
        help="FDS result directory for smoke-speed updates based on extinction",
    )
    parser.add_argument(
        "--constant-extinction",
        type=float,
        help="Use a constant extinction coefficient K [1/m] instead of FDS input",
    )
    parser.add_argument(
        "--smoke-update-interval",
        type=float,
        default=1.0,
        help="Seconds between smoke-speed updates",
    )
    parser.add_argument(
        "--smoke-slice-height",
        type=float,
        default=2.0,
        help="FDS slice height in meters for extinction sampling",
    )
    parser.add_argument(
        "--output-smoke-history",
        help="Write smoke speed/extinction history to CSV",
    )
    parser.add_argument(
        "--output-fed-history",
        help="Write FED history to CSV",
    )
    parser.add_argument(
        "--inspect-fds",
        action="store_true",
        help="Inspect available FDS quantities with fdsreader and exit",
    )
    parser.add_argument(
        "--enable-rerouting",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Dynamic smoke/congestion-based route reevaluation "
        "(default: on; use --no-enable-rerouting to disable)",
    )
    parser.add_argument(
        "--reroute-interval",
        type=float,
        default=1.0,
        help="Seconds between route reevaluations per agent (default: 1)",
    )
    parser.add_argument(
        "--output-route-history",
        help="Write route switch history to CSV",
    )
    parser.add_argument(
        "--output-route-cost-history",
        help="Write ranked route cost snapshots to CSV",
    )
    parser.add_argument(
        "--vis-cache",
        help="Path to vismap .npz cache for visibility-gated route rejection. "
        "Requires rerouting enabled (on by default; do not pass "
        "--no-enable-rerouting). With --fds-dir the cache holds the smoke-aware "
        "vismap, without it the clear-air one. Created if missing, loaded if "
        "present.",
    )
    parser.add_argument(
        "--clear-air-visibility",
        action="store_true",
        help="Force clear-air sight gating even on a deck whose agents all "
        "start fully familiar. Such agents never consult it to learn the graph, "
        "but the gate route model reads its line of sight, so a gate deck builds "
        "one anyway. Decks with discovery agents get it without asking.",
    )
    parser.add_argument(
        "--no-visibility",
        action="store_true",
        help="Turn sight gating off entirely. Agents then learn every "
        "neighbour of each node they reach, by contact rather than by seeing "
        "it -- faster, and not a fire scenario.",
    )
    parser.add_argument(
        "--vis-cell-size",
        type=float,
        default=0.25,
        help="Resolution of the clear-air visibility grid in meters. A wall "
        "thinner than one cell stops occluding, so keep it below the thinnest "
        "wall that must block sight (default: 0.25)",
    )
    parser.add_argument(
        "--disable-tenability",
        action="store_true",
        help="Disable both the FIC speed-reduction rule and the FED>=1 "
        "incapacitation rule (default: both active when a FED model is loaded)",
    )
    parser.add_argument(
        "--fic-alpha",
        type=float,
        default=0.7,
        help="Slope of the Purser FIC speed-reduction rule (default: 0.7)",
    )
    parser.add_argument(
        "--fic-min-factor",
        type=float,
        default=0.3,
        help="Lower bound on the FIC speed factor (default: 0.3)",
    )
    parser.add_argument(
        "--fed-threshold",
        type=float,
        default=1.0,
        help="Median cumulative FED at which an agent is incapacitated "
        "(default: 1.0 per ISO 13571 / Korhonen 2021)",
    )
    parser.add_argument(
        "--incapacitation-mode",
        choices=("probabilistic", "deterministic"),
        default="probabilistic",
        help="probabilistic: per-agent threshold ~ lognormal(median=fed-threshold, "
        "susceptibility-sigma), fit to NIST TN 1797 population bands (default); "
        "deterministic: every agent uses fed-threshold",
    )
    parser.add_argument(
        "--susceptibility-sigma",
        type=float,
        default=0.94,
        help="Log-normal sigma of the per-agent incapacitation threshold in "
        "probabilistic mode (default: 0.94 -> ~10/50/88%% at FED 0.3/1/3)",
    )
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
        "fic",
        "fic_speed_factor",
        "incapacitated",
        "base_speed",
        "desired_speed",
        "speed_factor",
    ]
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
        "min_visibility_m",
        "band",
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


def main() -> int:
    """Parse arguments, run the scenario, and export requested outputs."""
    parser = _build_parser()
    args = parser.parse_args()

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

    run_kwargs = build_run_kwargs(scenario, args, log=print)

    print("Initialization finished.")
    print("Simulation started.")

    result = run_scenario(scenario, **run_kwargs)
    if result.agents_remaining == 0:
        print(
            f"Simulation finished in {result.evacuation_time:.2f} s "
            f"({result.agents_evacuated}/{result.total_agents} evacuated)."
        )
    else:
        print(
            f"Simulation stopped after {result.evacuation_time:.2f} s "
            f"({result.agents_evacuated}/{result.total_agents} evacuated, "
            f"{result.agents_remaining} remaining)."
        )

    apply_outputs(result, scenario, args, log=print)
    return 0


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

    if opts.output_sqlite and result.sqlite_file:
        output_path = pathlib.Path(opts.output_sqlite).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(result.sqlite_file, output_path)
        artifacts.append(f"Trajectory SQLite: {output_path}")
        _maybe_write_agent_scalars(output_path, result.fed_history)

    if getattr(opts, "cleanup", False):
        result.cleanup()

    return artifacts


if __name__ == "__main__":
    raise SystemExit(main())
