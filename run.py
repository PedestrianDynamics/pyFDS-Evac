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
from pyfds_evac.core.fed import (
    DEFAULT_HEAT_CONVECTIVE_COEFFICIENT,
    DEFAULT_HEAT_EMISSIVITY,
    DEFAULT_HEAT_SKIN_TEMPERATURE_C,
    HEAT_ENDPOINTS,
    HEAT_FED_METHODS,
)
from pyfds_evac.core.manifest import manifest_path_for
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
        help="Use a constant extinction coefficient K [1/m] instead of FDS input. "
        "Without it, an FDS case with no SOOT EXTINCTION COEFFICIENT slice "
        "runs with no smoke speed reduction (a warning is logged).",
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
        default=1.6,
        help="FDS slice height in meters for smoke and heat sampling "
        "(default: 1.6, FDS+Evac HUMAN_SMOKE_HEIGHT; pass 2.0 for the "
        "previous pyFDS-Evac default)",
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
        help="Path to vismap .npz cache for sight gating, which decides which "
        "graph nodes enter an agent's cognitive map; route choice does not read "
        "it. "
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
        "and route choice does not read it either (the gate uses the optical "
        "depth K_ave * L of the route polyline), so on such a deck it changes "
        "nothing. Decks with discovery agents get it without asking.",
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
        "--max-sign-distance",
        type=float,
        default=30.0,
        help="Farthest distance in meters from which a sign can be read, even "
        "in clear air. A sign's own 'max_distance' overrides it (default: 30, "
        "as in fdsvismap)",
    )
    parser.add_argument(
        "--disable-tenability",
        action="store_true",
        help="Run without a tenability config: disables the FIC speed-reduction "
        "rule, toxic FED incapacitation and heat FED incapacitation. FED is "
        "still accumulated and reported (default: incapacitation active when a "
        "FED or heat FED model is loaded; the FIC rule only with "
        "--enable-fic-speed)",
    )
    parser.add_argument(
        "--enable-fic-speed",
        action="store_true",
        help="Slow agents by the irritant (FIC) rule max(fic-min-factor, "
        "1 - fic-alpha * FIC) on top of the smoke-speed law. Off by default, "
        "as FDS+Evac has no irritant slowdown; before this became opt-in it "
        "was on whenever a FED model was loaded",
    )
    parser.add_argument(
        "--fic-alpha",
        type=float,
        default=0.7,
        help="Slope of the FIC speed-reduction rule, a pyFDS-Evac "
        "assumption, source unknown (#147); needs --enable-fic-speed "
        "(default: 0.7)",
    )
    parser.add_argument(
        "--fic-min-factor",
        type=float,
        default=0.3,
        help="Lower bound on the FIC speed factor; needs --enable-fic-speed "
        "(default: 0.3)",
    )
    parser.add_argument(
        "--fed-threshold",
        type=float,
        default=1.0,
        help="Cumulative FED at which an agent is incapacitated; the median "
        "in probabilistic mode (default: 1.0 per ISO 13571 / Korhonen 2021)",
    )
    parser.add_argument(
        "--o2-threshold-percent",
        type=float,
        default=20.0,
        help="O2 volume percent at or above which the hypoxia term of the gas "
        "FED is zero (default: 20.0, as FDS/FDS+Evac; 19.5 was the previous "
        "pyFDS-Evac default, the OSHA limit used by Pathfinder)",
    )
    parser.add_argument(
        "--incapacitation-mode",
        choices=("probabilistic", "deterministic"),
        default="deterministic",
        help="deterministic: every agent uses fed-threshold, as FDS+Evac "
        "(default); probabilistic: per-agent threshold ~ "
        "lognormal(median=fed-threshold, susceptibility-sigma), fit to NIST "
        "TN 1797 population bands",
    )
    parser.add_argument(
        "--susceptibility-sigma",
        type=float,
        default=0.94,
        help="Log-normal sigma of the per-agent incapacitation threshold in "
        "probabilistic mode (default: 0.94 -> ~10/50/88%% at FED 0.3/1/3)",
    )
    parser.add_argument(
        "--enable-heat-fed",
        action="store_true",
        help="Accumulate the convective heat FED (SFPE Handbook Eq. 63.44, or "
        "the law of --heat-endpoint, or the total-flux law of "
        "--heat-fed-method) from "
        "the FDS TEMPERATURE slice and incapacitate on it. Off by default, as "
        "FDS+Evac has no heat dose; before this became opt-in it was on "
        "whenever the case had a TEMPERATURE slice",
    )
    parser.add_argument(
        "--heat-endpoint",
        choices=tuple(HEAT_ENDPOINTS),
        default=None,
        help="Heat endpoint of SFPE Handbook Ch. 63: tolerance (Eq. 63.45), "
        "injury (Eq. 63.46) or fatal (Eq. 63.47) convective law, so that heat "
        "FED = 1 is that endpoint; needs --enable-heat-fed. Samples above "
        "205 C (an assumed limit) or non-finite are flagged. Default: none, Eq. 63.44. "
        "With --heat-fed-method total-flux it selects the dose D of Eq. 63.43 "
        "(default there: fatal)",
    )
    parser.add_argument(
        "--heat-fed-method",
        choices=HEAT_FED_METHODS,
        default="convective",
        help="Heat dose law; needs --enable-heat-fed. convective (default): "
        "Eq. 63.44 or the law of --heat-endpoint. total-flux: heat flux to the "
        "skin from Eq. 63.49 (both terms in W/m2, divided by 1000 together), "
        "rate q^1.33/D (Eq. 63.43) with no 2.5 kW/m2 threshold; D of "
        "--heat-endpoint, fatal (16.7) without it",
    )
    parser.add_argument(
        "--heat-emissivity",
        type=float,
        default=DEFAULT_HEAT_EMISSIVITY,
        help="Emissivity of the gas at the head for --heat-fed-method "
        f"total-flux (default: {DEFAULT_HEAT_EMISSIVITY}, an assumption: SFPE "
        "p. 2384 gives 'perhaps 0.5 for smoke', 0.05 for a gas)",
    )
    parser.add_argument(
        "--heat-convective-coefficient",
        type=float,
        default=DEFAULT_HEAT_CONVECTIVE_COEFFICIENT,
        help="Convective heat transfer coefficient h [W/m2/K] for "
        "--heat-fed-method total-flux (default: "
        f"{DEFAULT_HEAT_CONVECTIVE_COEFFICIENT}, an assumption: SFPE p. 2384 "
        "gives 5-8 for slow-moving air)",
    )
    parser.add_argument(
        "--heat-skin-temperature",
        type=float,
        default=DEFAULT_HEAT_SKIN_TEMPERATURE_C,
        help="Fixed skin temperature [C] for --heat-fed-method total-flux "
        f"(default: {DEFAULT_HEAT_SKIN_TEMPERATURE_C}, an assumption: not given "
        "by the Handbook for Eq. 63.49)",
    )
    parser.add_argument(
        "--heat-fed-threshold",
        type=float,
        default=1.0,
        help="Median cumulative heat FED (SFPE Handbook Eq. 63.44, or the law "
        "of --heat-endpoint or --heat-fed-method) at which an "
        "agent is thermally incapacitated; needs --enable-heat-fed "
        "(default: 1.0). Independent of "
        "--fed-threshold (toxic gas) -- see fed.py's TenabilityConfig",
    )
    parser.add_argument(
        "--heat-incapacitation-mode",
        choices=("probabilistic", "deterministic"),
        default="deterministic",
        help="Same semantics as --incapacitation-mode, applied to the "
        "independent heat FED track (default: deterministic, as no "
        "population spread for heat is published)",
    )
    parser.add_argument(
        "--heat-susceptibility-sigma",
        type=float,
        default=0.94,
        help="Log-normal sigma for the heat incapacitation threshold in "
        "probabilistic mode (default: 0.94, reused from the gas value as a "
        "starting assumption -- no independent literature support for heat)",
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


def _copy_manifest(result, output_path: pathlib.Path) -> pathlib.Path | None:
    """Copy the run manifest beside the copied trajectory, if there is one."""
    manifest_file = getattr(result, "manifest_file", None)
    if not manifest_file or not pathlib.Path(manifest_file).is_file():
        return None
    destination = manifest_path_for(output_path)
    shutil.copy2(manifest_file, destination)
    return destination


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
        manifest_path = _copy_manifest(result, output_path)
        if manifest_path is not None:
            artifacts.append(f"Run manifest: {manifest_path}")
        _maybe_write_agent_scalars(output_path, result.fed_history)

    if getattr(opts, "cleanup", False):
        result.cleanup()

    return artifacts


if __name__ == "__main__":
    raise SystemExit(main())
