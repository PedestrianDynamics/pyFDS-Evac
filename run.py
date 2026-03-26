"""Run JSON-first JuPedSim scenarios from the fds-evac repository."""

import argparse
import csv
import json
import pathlib
import shutil

from src.core import (
    ConstantExtinctionField,
    DefaultFedConfig,
    DefaultFedModel,
    ExtinctionField,
    FdsFedField,
    RerouteConfig,
    RouteCostConfig,
    SmokeSpeedConfig,
    SmokeSpeedModel,
    inspect_fds_quantities,
    load_scenario,
    run_scenario,
)


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
        action="store_true",
        help="Enable dynamic smoke-based route reevaluation",
    )
    parser.add_argument(
        "--reroute-interval",
        type=float,
        default=10.0,
        help="Seconds between route reevaluations per agent (default: 10)",
    )
    parser.add_argument(
        "--output-route-history",
        help="Write route switch history to CSV",
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
        "fed_rate_per_min",
        "fed_cumulative",
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


def main() -> int:
    """Parse arguments, run the scenario, and export requested outputs."""
    args = _build_parser().parse_args()

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

    smoke_speed_model = None
    fed_model = None
    if args.fds_dir or args.constant_extinction is not None:
        print("Configuring smoke calculation.")
        smoke_config = SmokeSpeedConfig(
            fds_dir=args.fds_dir or ".",
            update_interval_s=args.smoke_update_interval,
            slice_height_m=args.smoke_slice_height,
        )
        if args.constant_extinction is not None:
            field = ConstantExtinctionField(args.constant_extinction)
        elif args.fds_dir:
            field = ExtinctionField.from_fds(
                smoke_config.fds_dir,
                slice_height_m=smoke_config.slice_height_m,
            )
        else:
            field = None
        if field is not None:
            smoke_speed_model = SmokeSpeedModel(
                field,
                smoke_config,
            )
    if args.fds_dir:
        inventory = inspect_fds_quantities(args.fds_dir)
        if inventory.supports_default_fed():
            print("Configuring FED calculation.")
            fed_config = DefaultFedConfig(
                fds_dir=args.fds_dir,
                update_interval_s=args.smoke_update_interval,
                slice_height_m=args.smoke_slice_height,
            )
            fed_model = DefaultFedModel(FdsFedField.from_fds(args.fds_dir), fed_config)
    reroute_config = None
    if args.enable_rerouting and smoke_speed_model is not None:
        print("Configuring smoke-based rerouting.")
        reroute_config = RerouteConfig(
            reevaluation_interval_s=args.reroute_interval,
            cost_config=RouteCostConfig(
                base_speed_m_per_s=1.3,
            ),
        )

    print("Initialization finished.")
    print("Simulation started.")

    result = run_scenario(
        scenario,
        seed=args.seed,
        smoke_speed_model=smoke_speed_model,
        fed_model=fed_model,
        reroute_config=reroute_config,
    )
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

    if args.output_smoke_history and result.smoke_history is not None:
        _write_smoke_history_csv(result.smoke_history, args.output_smoke_history)
    if args.output_fed_history and result.fed_history is not None:
        _write_fed_history_csv(result.fed_history, args.output_fed_history)
    if args.output_route_history and result.route_history is not None:
        _write_route_history_csv(result.route_history, args.output_route_history)
        print(f"Route switches: {len(result.route_history)}")

    if args.output_sqlite and result.sqlite_file:
        output_path = pathlib.Path(args.output_sqlite).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(result.sqlite_file, output_path)

    if args.cleanup:
        result.cleanup()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
