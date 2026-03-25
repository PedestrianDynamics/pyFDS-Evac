"""Run JSON-first JuPedSim scenarios from the fds-evac repository."""

from __future__ import annotations

import argparse
import csv
import json
import pathlib
import shutil

from src.core import (
    ConstantExtinctionField,
    ExtinctionField,
    inspect_fds_quantities,
    SmokeSpeedConfig,
    SmokeSpeedModel,
    load_scenario,
    run_scenario,
)


def _build_parser() -> argparse.ArgumentParser:
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
        "--inspect-fds",
        action="store_true",
        help="Inspect available FDS quantities with fdsreader and exit",
    )
    return parser


def _export_app_bundle(scenario, output_dir: str) -> None:
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


def main() -> int:
    args = _build_parser().parse_args()

    scenario = load_scenario(args.scenario)

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
    if args.fds_dir or args.constant_extinction is not None:
        smoke_config = SmokeSpeedConfig(
            fds_dir=args.fds_dir or ".",
            update_interval_s=args.smoke_update_interval,
            slice_height_m=args.smoke_slice_height,
        )
        if args.constant_extinction is not None:
            field = ConstantExtinctionField(args.constant_extinction)
        else:
            field = ExtinctionField.from_fds(
                smoke_config.fds_dir,
                slice_height_m=smoke_config.slice_height_m,
            )
        smoke_speed_model = SmokeSpeedModel(
            field,
            smoke_config,
        )

    result = run_scenario(
        scenario,
        seed=args.seed,
        smoke_speed_model=smoke_speed_model,
    )
    print(json.dumps(result.metrics, indent=2, sort_keys=True, default=str))

    if args.output_smoke_history and result.smoke_history is not None:
        _write_smoke_history_csv(result.smoke_history, args.output_smoke_history)

    if args.output_sqlite and result.sqlite_file:
        output_path = pathlib.Path(args.output_sqlite).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(result.sqlite_file, output_path)

    if args.cleanup:
        result.cleanup()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
