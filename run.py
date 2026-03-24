"""Run JSON-first JuPedSim scenarios from the fds-evac repository."""

from __future__ import annotations

import argparse
import json
import pathlib
import shutil

from src.core import load_scenario, run_scenario


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", required=True, help="Scenario JSON, ZIP, or directory")
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


def main() -> int:
    args = _build_parser().parse_args()

    scenario = load_scenario(args.scenario)

    if args.print_summary:
        print(scenario.summary())

    if args.export_app_bundle:
        _export_app_bundle(scenario, args.export_app_bundle)

    if args.export_only:
        return 0

    result = run_scenario(scenario, seed=args.seed)
    print(json.dumps(result.metrics, indent=2, sort_keys=True, default=str))

    if args.output_sqlite and result.sqlite_file:
        output_path = pathlib.Path(args.output_sqlite).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(result.sqlite_file, output_path)

    if args.cleanup:
        result.cleanup()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
