"""The ``pyfds-evac`` command: run a scenario, optionally with FDS fire data."""

import argparse
import csv
import json
import logging
import pathlib
import shutil
import sys

from rich_argparse import RawDescriptionRichHelpFormatter

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
    HEAT_CLOTHING,
    HEAT_ENDPOINTS,
    HEAT_FED_METHODS,
    HEAT_FLUX_REGIMES,
    HEAT_RADIANT_SOURCES,
    HEAT_U_FACTOR_RANGE,
)
from pyfds_evac.core.manifest import manifest_path_for
from pyfds_evac.core.run_config import build_run_kwargs


def _u_factor(text: str) -> float:
    """Parse --heat-u-factor: a finite number in [0.25, 1]."""
    low, high = HEAT_U_FACTOR_RANGE
    try:
        value = float(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"not a number: {text!r}") from exc
    if not low <= value <= high:  # also rejects nan
        raise argparse.ArgumentTypeError(f"must be in [{low}, {high}], got {text}")
    return value


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
    run = parser.add_argument_group("Scenario & run")
    outputs = parser.add_argument_group("Outputs", "Files the run writes and keeps.")
    fds = parser.add_argument_group(
        "FDS input & smoke", "Where the fire data comes from and how it is sampled."
    )
    gas = parser.add_argument_group(
        "Toxic gas (FED/FIC)",
        "Fractional effective dose of the FDS gas slices and the irritant rule.",
    )
    heat = parser.add_argument_group(
        "Heat",
        "Heat dose, off unless --enable-heat-fed is given; the other options here "
        "need it.",
    )
    routing = parser.add_argument_group("Routing")
    sight = parser.add_argument_group(
        "Visibility & signs", "What agents can see of the route graph and signs."
    )
    aset = parser.add_argument_group(
        "ASET/RSET tools",
        "Uncoupled and speed-only runs for comparing egress with and without fire.",
    )
    run.add_argument(
        "--scenario", required=True, help="Scenario JSON, ZIP, or directory"
    )
    run.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Random seed; overrides the scenario's seed",
    )
    run.add_argument(
        "--print-summary",
        action="store_true",
        help="Print the loaded scenario summary before running",
    )
    run.add_argument(
        "--debug",
        action="store_true",
        help="Print debug messages, such as the rerouting trace",
    )
    outputs.add_argument(
        "--output-sqlite",
        help="Copy the generated trajectory SQLite file to this location",
    )
    outputs.add_argument(
        "--cleanup",
        action="store_true",
        help="Delete the temporary trajectory SQLite file after the run",
    )
    outputs.add_argument(
        "--export-app-bundle",
        help="Write config.json and geometry.wkt to this directory",
    )
    outputs.add_argument(
        "--export-only",
        action="store_true",
        help="Export the scenario bundle without running the simulation",
    )
    fds.add_argument(
        "--fds-dir",
        help="FDS output directory (the one with the .smv file); smoke, gas and "
        "heat are sampled from it",
    )
    fds.add_argument(
        "--constant-extinction",
        type=float,
        help="Use a constant extinction coefficient K [1/m] instead of FDS input. "
        "Without it, an FDS case with no SOOT EXTINCTION COEFFICIENT slice "
        "runs with no smoke speed reduction (a warning is logged).",
    )
    fds.add_argument(
        "--smoke-update-interval",
        type=float,
        default=1.0,
        help="Time between smoke-speed updates [s] (default: 1.0)",
    )
    fds.add_argument(
        "--smoke-slice-height",
        type=float,
        default=1.6,
        help="FDS slice height [m] for smoke and heat sampling "
        "(default: 1.6, FDS+Evac HUMAN_SMOKE_HEIGHT; pass 2.0 for the "
        "previous pyFDS-Evac default)",
    )
    fds.add_argument(
        "--allow-fds-horizon-hold",
        action="store_true",
        help="Hold the last FDS frame when the run outlasts the FDS output "
        "(one warning per quantity). Without it, a max_simulation_time past "
        "the FDS end time is an error at setup, and so is any sample past it.",
    )
    fds.add_argument(
        "--require-fds-coverage",
        action="store_true",
        help="Treat the FDS domain as required: the run stops at setup when "
        "the walkable area, an exit, checkpoint, spawn area, sign or route "
        "edge lies outside the FDS slices, and at any smoke, FED, heat or "
        "sign-visibility sample outside them. Without it, those places read "
        "ambient air and clear sight, as in FDS+Evac, with a warning at setup "
        "and in_fds_domain = False in the histories.",
    )
    outputs.add_argument(
        "--output-smoke-history",
        help="Write smoke speed/extinction history to CSV",
    )
    outputs.add_argument(
        "--output-fed-history",
        help="Write FED history to CSV",
    )
    fds.add_argument(
        "--inspect-fds",
        action="store_true",
        help="Inspect available FDS quantities with fdsreader and exit",
    )
    routing.add_argument(
        "--enable-rerouting",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Dynamic smoke/congestion-based route reevaluation "
        "(default: on; use --no-enable-rerouting to disable)",
    )
    routing.add_argument(
        "--reroute-interval",
        type=float,
        default=1.0,
        help="Time between route reevaluations per agent [s] (default: 1)",
    )
    outputs.add_argument(
        "--output-route-history",
        help="Write route switch history to CSV",
    )
    outputs.add_argument(
        "--output-route-cost-history",
        help="Write ranked route cost snapshots to CSV",
    )
    outputs.add_argument(
        "--output-exit-history",
        help="Write each path agent's exit (agent_id, origin, spawn_index, "
        "exit_id) to CSV: the exit it left through, or the one it was heading "
        "for at the end",
    )
    aset.add_argument(
        "--smoke-blind",
        action="store_true",
        help="Sample the fire for the smoke and FED histories only: agents walk, "
        "choose exits and see signs as in clear air, rerouting and tenability "
        "are off, and FED still accumulates",
    )
    aset.add_argument(
        "--replay-exits",
        help="Exit history CSV of an earlier run (--output-exit-history); the "
        "agent spawned n-th from an origin is sent to the exit the n-th agent "
        "from that origin took there, by clear-air costs on the agent's map. "
        "Needs the same scenario and seed",
    )
    sight.add_argument(
        "--vis-cache",
        help="Path to vismap .npz cache for sight gating, which decides which "
        "graph nodes enter an agent's cognitive map; route choice does not read "
        "it. "
        "Requires rerouting enabled (on by default; do not pass "
        "--no-enable-rerouting). With --fds-dir the cache holds the smoke-aware "
        "vismap, without it the clear-air one. Created if missing, loaded if "
        "present.",
    )
    sight.add_argument(
        "--clear-air-visibility",
        action="store_true",
        help="Force clear-air sight gating even on a deck whose agents all "
        "start fully familiar. Such agents never consult it to learn the graph, "
        "and route choice does not read it either (the gate uses the optical "
        "depth K_ave * L of the route polyline), so on such a deck it changes "
        "nothing. Decks with discovery agents get it without asking.",
    )
    sight.add_argument(
        "--no-visibility",
        action="store_true",
        help="Turn sight gating off entirely. Agents then learn every "
        "neighbour of each node they reach, by contact rather than by seeing "
        "it -- faster, and not a fire scenario.",
    )
    sight.add_argument(
        "--vis-cell-size",
        type=float,
        default=0.25,
        help="Cell size of the clear-air visibility grid [m]. A wall "
        "thinner than one cell stops occluding, so keep it below the thinnest "
        "wall that must block sight (default: 0.25)",
    )
    sight.add_argument(
        "--max-sign-distance",
        type=float,
        default=30.0,
        help="Farthest distance [m] from which a sign can be read, even "
        "in clear air. A sign's own 'max_distance' overrides it (default: 30, "
        "as in fdsvismap)",
    )
    gas.add_argument(
        "--disable-tenability",
        action="store_true",
        help="Run without a tenability config: disables the FIC speed-reduction "
        "rule, toxic FED incapacitation and heat FED incapacitation. FED is "
        "still accumulated and reported (default: incapacitation active when a "
        "FED or heat FED model is loaded; the FIC rule only with "
        "--enable-fic-speed)",
    )
    gas.add_argument(
        "--enable-fic-speed",
        action="store_true",
        help="Slow agents by the irritant (FIC) rule max(fic-min-factor, "
        "1 - fic-alpha * FIC) on top of the smoke-speed law. Off by default, "
        "as FDS+Evac has no irritant slowdown; before this became opt-in it "
        "was on whenever a FED model was loaded",
    )
    gas.add_argument(
        "--fic-alpha",
        type=float,
        default=0.7,
        help="Slope of the FIC speed-reduction rule, a pyFDS-Evac "
        "assumption, source unknown (#147); needs --enable-fic-speed "
        "(default: 0.7)",
    )
    gas.add_argument(
        "--fic-min-factor",
        type=float,
        default=0.3,
        help="Lower bound on the FIC speed factor; needs --enable-fic-speed "
        "(default: 0.3)",
    )
    gas.add_argument(
        "--fed-threshold",
        type=float,
        default=1.0,
        help="Cumulative FED at which an agent is incapacitated; the median "
        "in probabilistic mode (default: 1.0 per ISO 13571 / Korhonen 2021)",
    )
    gas.add_argument(
        "--o2-threshold-percent",
        type=float,
        default=20.0,
        help="O2 volume percent at or above which the hypoxia term of the gas "
        "FED is zero (default: 20.0, as FDS/FDS+Evac; 19.5 was the previous "
        "pyFDS-Evac default, the OSHA limit used by Pathfinder)",
    )
    gas.add_argument(
        "--incapacitation-mode",
        choices=("probabilistic", "deterministic"),
        default="deterministic",
        help="deterministic: every agent uses fed-threshold, as FDS+Evac "
        "(default); probabilistic: per-agent threshold ~ "
        "lognormal(median=fed-threshold, susceptibility-sigma), fit to NIST "
        "TN 1797 population bands",
    )
    gas.add_argument(
        "--susceptibility-sigma",
        type=float,
        default=0.94,
        help="Log-normal sigma of the per-agent incapacitation threshold in "
        "probabilistic mode (default: 0.94 -> ~10/50/88%% at FED 0.3/1/3)",
    )
    heat.add_argument(
        "--enable-heat-fed",
        action="store_true",
        help="Accumulate the convective heat FED (ISO 13571:2012 Eq. (9), "
        "fully clothed, or the law of --heat-clothing, --heat-endpoint or "
        "--heat-fed-method) from "
        "the FDS TEMPERATURE slice and incapacitate on it. Off by default, as "
        "FDS+Evac has no heat dose; before this became opt-in it was on "
        "whenever the case had a TEMPERATURE slice",
    )
    heat.add_argument(
        "--heat-clothing",
        choices=HEAT_CLOTHING,
        default=None,
        help="Convective law of ISO 13571:2012 (8.3) for the heat FED; needs "
        "--enable-heat-fed. clothed (default): Eq. (9), t = 4.1e8 T^-3.61 min, "
        "fully clothed. unclothed: Eq. (10), t = 5e7 T^-3.4 min, unclothed or "
        "lightly clothed, the same law as SFPE Handbook Eq. 63.44 and the "
        "default before the ISO law. No effect with --heat-endpoint or "
        "--heat-fed-method total-flux",
    )
    heat.add_argument(
        "--heat-endpoint",
        choices=tuple(HEAT_ENDPOINTS),
        default=None,
        help="Heat endpoint of SFPE Handbook Ch. 63: tolerance (Eq. 63.45), "
        "injury (Eq. 63.46) or fatal (Eq. 63.47) convective law, so that heat "
        "FED = 1 is that endpoint; needs --enable-heat-fed. Samples above "
        "205 C (an assumed limit) or non-finite are flagged. Default: none, the "
        "ISO law of --heat-clothing. "
        "With --heat-fed-method total-flux it selects the dose D of Eq. 63.43 "
        "(default there: fatal)",
    )
    heat.add_argument(
        "--heat-fed-method",
        choices=HEAT_FED_METHODS,
        default="convective",
        help="Heat dose law; needs --enable-heat-fed. convective (default): "
        "the ISO law of --heat-clothing or the law of --heat-endpoint. "
        "total-flux: heat flux to the "
        "skin from Eq. 63.49 (both terms in W/m2, divided by 1000 together), "
        "rate q^1.33/D (Eq. 63.43), the radiant term (net or excess, not "
        "incident) counted as zero below 2.5 kW/m2 (ISO 13571:2012 8.2, 8.4); "
        "D of "
        "--heat-endpoint, fatal (16.7) without it",
    )
    heat.add_argument(
        "--heat-emissivity",
        type=float,
        default=DEFAULT_HEAT_EMISSIVITY,
        help="Emissivity of the gas at the head for --heat-fed-method "
        f"total-flux (default: {DEFAULT_HEAT_EMISSIVITY}, an assumption: SFPE "
        "p. 2384 gives 'perhaps 0.5 for smoke', 0.05 for a gas)",
    )
    heat.add_argument(
        "--heat-convective-coefficient",
        type=float,
        default=DEFAULT_HEAT_CONVECTIVE_COEFFICIENT,
        help="Convective heat transfer coefficient h [W/m2/K] for "
        "--heat-fed-method total-flux (default: "
        f"{DEFAULT_HEAT_CONVECTIVE_COEFFICIENT}, an assumption: SFPE p. 2384 "
        "gives 5-8 for slow-moving air)",
    )
    heat.add_argument(
        "--heat-skin-temperature",
        type=float,
        default=DEFAULT_HEAT_SKIN_TEMPERATURE_C,
        help="Fixed skin temperature [C] for --heat-fed-method total-flux "
        f"(default: {DEFAULT_HEAT_SKIN_TEMPERATURE_C}, an assumption: not given "
        "by the Handbook for Eq. 63.49)",
    )
    heat.add_argument(
        "--heat-radiant-source",
        choices=HEAT_RADIANT_SOURCES,
        default="gas",
        help="Radiant term of --heat-fed-method total-flux. gas (default): "
        "eps sigma (T_g^4 - T_s^4) of Eq. 63.49. integrated-intensity: the "
        "excess f*(U - 4 sigma T_s^4) over an isotropic field at the skin "
        "temperature, from the FDS INTEGRATED INTENSITY slice at the slice "
        "height, replacing the gas term (and the layer term of --heat-regime "
        "layer); needs --heat-u-factor",
    )
    heat.add_argument(
        "--heat-u-factor",
        type=_u_factor,
        default=None,
        help="Factor f in [0.25, 1] for --heat-radiant-source "
        "integrated-intensity: the incident radiant flux is f*U, from U/4 "
        "(sphere, or a plate in isotropic radiation) to U (one small source "
        "seen face-on); the dose uses the excess f*(U - 4 sigma T_s^4). No default: "
        "required with that source",
    )
    heat.add_argument(
        "--heat-regime",
        choices=HEAT_FLUX_REGIMES,
        default="smoke",
        help="Where the head is, for --heat-fed-method total-flux; a user "
        "choice, no automatic rule. smoke (default): head in smoke, Eq. 63.49 "
        "at the head. layer: head in clear air below a hot layer, convection at "
        "the head plus the net layer flux phi*eps_L*sigma*(T_L^4 - T_s^4) from "
        "a TEMPERATURE slice at --heat-layer-height, with no radiant term of "
        "the gas at the head; needs --heat-layer-height, --heat-view-factor and "
        "--heat-layer-emissivity. With --heat-radiant-source "
        "integrated-intensity, U supplies the radiant term instead and the "
        "layer term is not added (one warning)",
    )
    heat.add_argument(
        "--heat-layer-height",
        type=float,
        default=None,
        help="Height [m] of the TEMPERATURE slice read as the hot layer for "
        "--heat-regime layer (no default: it depends on the ceiling height)",
    )
    heat.add_argument(
        "--heat-view-factor",
        type=float,
        default=None,
        help="View factor phi in [0, 1] from the skin to the layer for "
        "--heat-regime layer (no default: about 1 for the crown, about 0.5 "
        "for the face, spec 016, unsourced)",
    )
    heat.add_argument(
        "--heat-layer-emissivity",
        type=float,
        default=None,
        help="Layer emissivity eps_L in [0, 1] for --heat-regime layer (no "
        "default: no sourced value)",
    )
    heat.add_argument(
        "--heat-fed-threshold",
        type=float,
        default=None,
        help="Median cumulative heat FED at which an agent is thermally "
        "incapacitated; needs --enable-heat-fed. Default: none, the value of "
        "--fed-threshold, as ISO 13571:2012 uses one threshold for FED and FEC "
        "(5.4) and sets the heat threshold in the same manner (8.5). Setting it departs from ISO; the run logs a warning "
        "and the manifest records heat_fed_threshold_override",
    )
    heat.add_argument(
        "--heat-incapacitation-mode",
        choices=("probabilistic", "deterministic"),
        default="deterministic",
        help="Same semantics as --incapacitation-mode, applied to the "
        "independent heat FED track (default: deterministic, as no "
        "population spread for heat is published)",
    )
    heat.add_argument(
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


def _copy_manifest(result, output_path: pathlib.Path) -> pathlib.Path | None:
    """Copy the run manifest beside the copied trajectory, if there is one."""
    manifest_file = getattr(result, "manifest_file", None)
    if not manifest_file or not pathlib.Path(manifest_file).is_file():
        return None
    destination = manifest_path_for(output_path)
    shutil.copy2(manifest_file, destination)
    return destination


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


def main() -> int:
    """Parse arguments, run the scenario, and export requested outputs."""
    parser = _build_parser()
    args = parser.parse_args()
    _configure_logging(args.debug)

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
        manifest_path = _copy_manifest(result, output_path)
        if manifest_path is not None:
            artifacts.append(f"Run manifest: {manifest_path}")
        _maybe_write_agent_scalars(output_path, result.fed_history)

    if getattr(opts, "cleanup", False):
        result.cleanup()

    return artifacts


if __name__ == "__main__":
    raise SystemExit(main())
