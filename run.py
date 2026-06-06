"""Run JSON-first JuPedSim scenarios from the fds-evac repository."""

import argparse
import csv
import json
import pathlib
import shutil

from pyfds_evac.core import (
    export_agents_to_smv,
    inspect_fds_quantities,
    load_scenario,
    run_scenario,
)
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
    parser.add_argument(
        "--output-route-cost-history",
        help="Write ranked route cost snapshots to CSV",
    )
    parser.add_argument(
        "--smv-export",
        action="store_true",
        help="Export agent trajectories as <CHID>_agents.prt5 and patch <CHID>.smv "
        "so Smokeview renders agents alongside smoke (requires --fds-dir)",
    )
    parser.add_argument(
        "--smv-particle-z",
        type=float,
        default=0.0,
        help="Constant agent height in meters for the .prt5 export (default: 0.0)",
    )
    parser.add_argument(
        "--smv-class-id",
        default="Human",
        help="CLASS_OF_PARTICLES label written to the .smv. Bound to an "
        "AVATARDEF in objects.svo via a PROP block so Smokeview draws a "
        "humanoid figure (default: Human)",
    )
    parser.add_argument(
        "--smv-avatar-style",
        choices=("human", "arrow", "sphere"),
        default="human",
        help="Which AVATARDEF to write to <CHID>.svo. 'human' is the "
        "detailed humanoid that rotates with the agent's orientation; "
        "'arrow' is a sphere + red directional marker (makes per-particle "
        "rotation obvious); 'sphere' is a single plain sphere — no "
        "rotation, smallest surface area for sanity-checking size. "
        "(default: human)",
    )
    parser.add_argument(
        "--smv-with-azimuth",
        action="store_true",
        help="Write per-particle AZIMUTH (deg) as a PRT5 quantity column. "
        "Off by default — per-particle avatar rotation is not supported "
        "by current Smokeview (firemodels/smv#2597) and writing the "
        "quantity also triggers a CreatePartBoundFile bug that sticks "
        "playback on frame 0. Enable only if you want the AZIMUTH "
        "colorbar entry and accept broken playback.",
    )
    parser.add_argument(
        "--vis-cache",
        help="Path to vismap pickle cache for visibility-gated route rejection. "
        "Requires --fds-dir and --enable-rerouting. "
        "Cache is created if missing, loaded if present.",
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
        help="Cumulative FED at which an agent is declared incapacitated "
        "(default: 1.0 per FDS+Evac / Korhonen 2021)",
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


def main() -> int:
    """Parse arguments, run the scenario, and export requested outputs."""
    parser = _build_parser()
    args = parser.parse_args()

    if args.smv_export and not args.fds_dir:
        parser.error("--smv-export requires --fds-dir")

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

    if args.output_smoke_history and result.smoke_history is not None:
        _write_smoke_history_csv(result.smoke_history, args.output_smoke_history)
    if args.output_fed_history and result.fed_history is not None:
        _write_fed_history_csv(result.fed_history, args.output_fed_history)
    if args.output_route_history and result.route_history is not None:
        _write_route_history_csv(result.route_history, args.output_route_history)
        print(f"Route switches: {len(result.route_history)}")
    if args.output_route_cost_history and result.route_cost_history is not None:
        _write_route_cost_history_csv(
            result.route_cost_history,
            args.output_route_cost_history,
        )
        print(f"Route cost samples: {len(result.route_cost_history)}")

    if args.output_sqlite and result.sqlite_file:
        output_path = pathlib.Path(args.output_sqlite).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(result.sqlite_file, output_path)

    if args.smv_export:
        prt5_path = export_agents_to_smv(
            pathlib.Path(args.fds_dir),
            result,
            z=args.smv_particle_z,
            class_id=args.smv_class_id,
            avatar_style=args.smv_avatar_style,
            with_azimuth=args.smv_with_azimuth,
        )
        print(f"Wrote agent particles to {prt5_path}")

    if args.cleanup:
        result.cleanup()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
