"""The run options of pyFDS-Evac: one table for the CLI, the GUI and the TUI.

Each :class:`Parameter` holds a flag's name, type, unit, default, choices,
help text and where the value goes in the Python API. The ``pyfds-evac``
parser, the GUI form and the effective configuration are built from
:data:`PARAMETERS`; no front end keeps a default of its own.

:data:`PARAMETERS` is in the order the flags are added to the parser. That
order sets the order of ``parser._actions`` (and so of the GUI's "Other"
section); the order inside each help group follows from it.

This module imports only the standard library and ``pyfds_evac.core.fed``
(constants), so ``pyfds-evac --help`` stays fast (#496).

Provisional public API (0.3.0): names may change in 0.3.x.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

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


class _Same:
    """Marker: the Python API default equals the CLI default."""

    def __repr__(self) -> str:
        return "SAME"


SAME: Any = _Same()


class _NoCounterpart:
    """Marker: FDS+Evac has no counterpart of this option."""

    def __repr__(self) -> str:
        return "NO_COUNTERPART"


NO_COUNTERPART: Any = _NoCounterpart()


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


@dataclass(frozen=True)
class Group:
    """A help group of the CLI."""

    title: str
    description: str | None = None


GROUP_RUN = "Scenario & run"
GROUP_OUTPUTS = "Outputs"
GROUP_FDS = "FDS input & smoke"
GROUP_GAS = "Toxic gas (FED/FIC)"
GROUP_HEAT = "Heat"
GROUP_ROUTING = "Routing"
GROUP_SIGHT = "Visibility & signs"
GROUP_ASET = "ASET/RSET tools"

GROUPS: tuple[Group, ...] = (
    Group(GROUP_RUN),
    Group(GROUP_OUTPUTS, "Files the run writes and keeps."),
    Group(GROUP_FDS, "Where the fire data comes from and how it is sampled."),
    Group(
        GROUP_GAS,
        "Fractional effective dose of the FDS gas slices and the irritant rule.",
    ),
    Group(
        GROUP_HEAT,
        "Heat dose, off unless --enable-heat-fed is given; the other options here "
        "need it.",
    ),
    Group(GROUP_ROUTING),
    Group(GROUP_SIGHT, "What agents can see of the route graph and signs."),
    Group(
        GROUP_ASET,
        "Uncoupled and speed-only runs for comparing egress with and without fire.",
    ),
)


@dataclass(frozen=True)
class Parameter:
    """One run option.

    ``action`` is ``"store"`` (a value), ``"store_true"`` (a switch) or
    ``"boolean_optional"`` (``--x`` / ``--no-x``). ``type`` is the parse
    function (None: text). ``unit`` is the SI unit or None. ``python`` names
    the field(s) of the Python API the value reaches, and ``python_default``
    the default there when it differs from ``default`` (else :data:`SAME`).
    ``fds_evac`` is the value of the FDS+Evac counterpart; a run with another
    value departs from FDS+Evac. ``checked`` says where a value range is
    enforced today (None: not checked). ``run_option`` is False for flags
    that only steer the command (``--show-config``); they never reach
    ``build_run_kwargs`` and front ends do not show them. ``gui_help`` is the
    GUI's own wording of the help; None falls back to ``help``.
    :attr:`tier` is ``"common"`` or ``"advanced"`` (see :data:`TIERS`).
    """

    dest: str
    flags: tuple[str, ...]
    group: str
    help: str
    action: str = "store"
    type: Callable[[str], Any] | None = None
    default: Any = None
    choices: tuple[str, ...] | None = None
    required: bool = False
    unit: str | None = None
    python: str = ""
    python_default: Any = SAME
    fds_evac: Any = NO_COUNTERPART
    checked: str | None = None
    run_option: bool = True
    gui_help: str | None = None

    @property
    def flag(self) -> str:
        """The first (long) option string."""
        return self.flags[0]

    @property
    def tier(self) -> str:
        """``"common"`` for an option of a GUI section, else ``"advanced"``.

        The advanced tier is the GUI's "Other" section plus the command-only
        flags the GUI hides (:data:`GUI_HIDDEN`).
        """
        return TIER_COMMON if self.dest in _COMMON else TIER_ADVANCED

    @property
    def kind(self) -> str:
        """``bool``, ``choice``, ``float``, ``int`` or ``text``."""
        if self.action != "store":
            return "bool"
        if self.choices is not None:
            return "choice"
        if self.type is int:
            return "int"
        if self.type is not None:
            return "float"
        return "text"

    def argparse_kwargs(self) -> dict[str, Any]:
        """Keyword arguments of ``add_argument`` for this option."""
        kwargs: dict[str, Any] = {"help": self.help}
        if self.action == "store_true":
            kwargs["action"] = "store_true"
            return kwargs
        if self.action == "boolean_optional":
            kwargs["action"] = argparse.BooleanOptionalAction
            kwargs["default"] = self.default
            return kwargs
        if self.required:
            kwargs["required"] = True
            return kwargs
        if self.type is not None:
            kwargs["type"] = self.type
        if self.choices is not None:
            kwargs["choices"] = self.choices
        kwargs["default"] = self.default
        return kwargs


# Defaults stated in help texts as well; written once here.
SMOKE_UPDATE_INTERVAL_S = 1.0
SMOKE_SLICE_HEIGHT_M = 1.6
REROUTE_INTERVAL_S = 1.0
VIS_CELL_SIZE_M = 0.25
MAX_SIGN_DISTANCE_M = 30.0
FIC_ALPHA = 0.7
FIC_MIN_FACTOR = 0.3
FED_THRESHOLD = 1.0
O2_THRESHOLD_PERCENT = 20.0
INCAPACITATION_MODES = ("probabilistic", "deterministic")
INCAPACITATION_MODE = "deterministic"
SUSCEPTIBILITY_SIGMA = 0.94
HEAT_FED_METHOD = "convective"
HEAT_RADIANT_SOURCE = "gas"
HEAT_REGIME = "smoke"

_TENABILITY = "TenabilityConfig"
_HEAT_MODEL = "DefaultHeatFedModel"

PARAMETERS: tuple[Parameter, ...] = (
    Parameter(
        "scenario",
        ("--scenario",),
        GROUP_RUN,
        "Scenario JSON, ZIP, or directory",
        required=True,
        python="load_scenario(path)",
        gui_help="Which building + agent setup to run. Each option under assets/ "
        "pairs a floor plan (geometry) with an exits/agents config.",
    ),
    Parameter(
        "seed",
        ("--seed",),
        GROUP_RUN,
        "Random seed; overrides the scenario's seed",
        type=int,
        python="run_scenario(seed=)",
        gui_help="Random seed. Leave blank to use the scenario's own baseSeed, as "
        "run.py does. The same seed reproduces the same run; change it to get a "
        "different random spawn layout and variation.",
    ),
    Parameter(
        "print_summary",
        ("--print-summary",),
        GROUP_RUN,
        "Print the loaded scenario summary before running",
        action="store_true",
        default=False,
        python="Scenario.summary()",
    ),
    Parameter(
        "debug",
        ("--debug",),
        GROUP_RUN,
        "Print debug messages, such as the rerouting trace",
        action="store_true",
        default=False,
        python="logging: pyfds_evac at DEBUG",
    ),
    Parameter(
        "show_config",
        ("--show-config",),
        GROUP_RUN,
        "Print the effective configuration and exit without running: each "
        "model on or off with the reason, every option with its unit and "
        "whether it is the default, options that have no effect, the setup "
        "warnings and errors, and the equivalent command. Reads the FDS "
        "inventory with --fds-dir. Exit status 1 if the configuration has an "
        "error",
        action="store_true",
        default=False,
        python="pyfds_evac.config.effective_configuration()",
        run_option=False,
    ),
    Parameter(
        "output_sqlite",
        ("--output-sqlite",),
        GROUP_OUTPUTS,
        "Copy the generated trajectory SQLite file to this location",
        python="ScenarioResult.sqlite_file (copied, with the manifest)",
    ),
    Parameter(
        "cleanup",
        ("--cleanup",),
        GROUP_OUTPUTS,
        "Delete the temporary trajectory SQLite file after the run",
        action="store_true",
        default=False,
        python="ScenarioResult.cleanup()",
    ),
    Parameter(
        "export_app_bundle",
        ("--export-app-bundle",),
        GROUP_OUTPUTS,
        "Write config.json and geometry.wkt to this directory",
        python="Scenario.raw, Scenario.walkable_area_wkt",
    ),
    Parameter(
        "export_only",
        ("--export-only",),
        GROUP_OUTPUTS,
        "Export the scenario bundle without running the simulation",
        action="store_true",
        default=False,
    ),
    Parameter(
        "fds_dir",
        ("--fds-dir",),
        GROUP_FDS,
        "FDS output directory (the one with the .smv file); smoke, gas and "
        "heat are sampled from it",
        python="SmokeSpeedConfig.fds_dir, DefaultFedConfig.fds_dir, "
        "Fds*Field.from_fds, VisibilityModel(fds_dir)",
        gui_help="Folder of precomputed FDS fire results. Supplies the smoke and "
        "toxic-gas fields agents react to. Leave blank to run with no fire.",
    ),
    Parameter(
        "constant_extinction",
        ("--constant-extinction",),
        GROUP_FDS,
        "Use a constant extinction coefficient K [1/m] instead of FDS input. "
        "Without it, an FDS case with no SOOT EXTINCTION COEFFICIENT slice "
        "runs with no smoke speed reduction (a warning is logged).",
        type=float,
        unit="1/m",
        python="ConstantExtinctionField(K)",
        gui_help="Skip FDS and apply one uniform smoke density K (1/m) everywhere "
        "— a quick way to test smoke slowdown without a full fire run.",
    ),
    Parameter(
        "smoke_update_interval",
        ("--smoke-update-interval",),
        GROUP_FDS,
        f"Time between smoke-speed updates [s] (default: {SMOKE_UPDATE_INTERVAL_S})",
        type=float,
        default=SMOKE_UPDATE_INTERVAL_S,
        unit="s",
        python="SmokeSpeedConfig.update_interval_s, DefaultFedConfig.update_interval_s",
        gui_help="How often (sim seconds) the smoke each agent feels is refreshed. "
        "Smaller is smoother but costs more compute.",
    ),
    Parameter(
        "smoke_slice_height",
        ("--smoke-slice-height",),
        GROUP_FDS,
        "FDS slice height [m] for smoke and heat sampling "
        f"(default: {SMOKE_SLICE_HEIGHT_M}, FDS+Evac HUMAN_SMOKE_HEIGHT; pass 2.0 "
        "for the previous pyFDS-Evac default)",
        type=float,
        default=SMOKE_SLICE_HEIGHT_M,
        unit="m",
        python="slice_height_m of SmokeSpeedConfig, DefaultFedConfig, "
        "FdsFedField, FdsHeatField, VisibilityModel",
        fds_evac=SMOKE_SLICE_HEIGHT_M,
        gui_help="Height (m) of the horizontal FDS slice sampled for smoke — "
        "roughly head height of a standing person. "
        f"{SMOKE_SLICE_HEIGHT_M} by default, as FDS+Evac.",
    ),
    Parameter(
        "allow_fds_horizon_hold",
        ("--allow-fds-horizon-hold",),
        GROUP_FDS,
        "Hold the last FDS frame when the run outlasts the FDS output "
        "(one warning per quantity). Without it, a max_simulation_time past "
        "the FDS end time is an error at setup, and so is any sample past it.",
        action="store_true",
        default=False,
        python="allow_horizon_hold of every field and VisibilityModel",
        gui_help="Let the run outlast the FDS results by holding their last "
        "frame (logged as a warning). Off by default: a run longer than the FDS "
        "results stops with an error at setup.",
    ),
    Parameter(
        "require_fds_coverage",
        ("--require-fds-coverage",),
        GROUP_FDS,
        "Treat the FDS domain as required: the run stops at setup when "
        "the walkable area, an exit, checkpoint, spawn area, sign or route "
        "edge lies outside the FDS slices, and at any smoke, FED, heat or "
        "sign-visibility sample outside them. Without it, those places read "
        "ambient air and clear sight, as in FDS+Evac, with a warning at setup "
        "and in_fds_domain = False in the histories.",
        action="store_true",
        default=False,
        python="run_scenario(require_fds_coverage=), require_fds_coverage of "
        "every field and VisibilityModel",
        fds_evac=False,
        gui_help="Stop the run with an error when an agent, sign, exit or "
        "route edge is sampled outside the FDS slices. Off by default, as "
        "FDS+Evac: places outside the FDS domain read clear, ambient air, with "
        "a warning at setup.",
    ),
    Parameter(
        "output_smoke_history",
        ("--output-smoke-history",),
        GROUP_OUTPUTS,
        "Write smoke speed/extinction history to CSV",
        python="ScenarioResult.smoke_history",
    ),
    Parameter(
        "output_fed_history",
        ("--output-fed-history",),
        GROUP_OUTPUTS,
        "Write FED history to CSV",
        python="ScenarioResult.fed_history",
    ),
    Parameter(
        "inspect_fds",
        ("--inspect-fds",),
        GROUP_FDS,
        "Inspect available FDS quantities with fdsreader and exit",
        action="store_true",
        default=False,
        python="inspect_fds_quantities(fds_dir)",
    ),
    Parameter(
        "enable_rerouting",
        ("--enable-rerouting",),
        GROUP_ROUTING,
        "Dynamic smoke/congestion-based route reevaluation "
        "(default: on; use --no-enable-rerouting to disable)",
        action="boolean_optional",
        default=True,
        python="run_scenario(reroute_config=RerouteConfig(...))",
        python_default=False,
        gui_help="Let agents rethink their route mid-evacuation as smoke and "
        "crowding change, instead of blindly following their first assigned "
        "route.",
    ),
    Parameter(
        "reroute_interval",
        ("--reroute-interval",),
        GROUP_ROUTING,
        "Time between route reevaluations per agent [s] "
        f"(default: {REROUTE_INTERVAL_S:g})",
        type=float,
        default=REROUTE_INTERVAL_S,
        unit="s",
        python="RerouteConfig.reevaluation_interval_s, VisibilityModel.time_step_s",
        python_default=10.0,
        gui_help="How often (sim seconds) each agent rethinks its route. 1 = very "
        "responsive; larger values make agents commit longer before "
        "reconsidering.",
    ),
    Parameter(
        "output_route_history",
        ("--output-route-history",),
        GROUP_OUTPUTS,
        "Write route switch history to CSV",
        python="ScenarioResult.route_history",
    ),
    Parameter(
        "output_route_cost_history",
        ("--output-route-cost-history",),
        GROUP_OUTPUTS,
        "Write ranked route cost snapshots to CSV",
        python="ScenarioResult.route_cost_history; "
        "run_scenario(collect_route_cost_history=True)",
    ),
    Parameter(
        "output_exit_history",
        ("--output-exit-history",),
        GROUP_OUTPUTS,
        "Write each path agent's exit (agent_id, origin, spawn_index, "
        "exit_id) to CSV: the exit it left through, or the one it was heading "
        "for at the end",
        python="ScenarioResult.exit_history",
    ),
    Parameter(
        "smoke_blind",
        ("--smoke-blind",),
        GROUP_ASET,
        "Sample the fire for the smoke and FED histories only: agents walk, "
        "choose exits and see signs as in clear air, rerouting and tenability "
        "are off, and FED still accumulates",
        action="store_true",
        default=False,
        python="run_scenario(smoke_blind=)",
    ),
    Parameter(
        "replay_exits",
        ("--replay-exits",),
        GROUP_ASET,
        "Exit history CSV of an earlier run (--output-exit-history); the "
        "agent spawned n-th from an origin is sent to the exit the n-th agent "
        "from that origin took there, by clear-air costs on the agent's map. "
        "Needs the same scenario and seed",
        python="run_scenario(replay_exits=load_replay_exits(path))",
    ),
    Parameter(
        "vis_cache",
        ("--vis-cache",),
        GROUP_SIGHT,
        "Path to vismap .npz cache for sight gating, which decides which "
        "graph nodes enter an agent's cognitive map; route choice does not read "
        "it. "
        "Requires rerouting enabled (on by default; do not pass "
        "--no-enable-rerouting). With --fds-dir the cache holds the smoke-aware "
        "vismap, without it the clear-air one. Created if missing, loaded if "
        "present.",
        python="VisibilityModel(cache_path=)",
        gui_help="Optional file (.npz) that caches the sign-visibility map "
        "between runs. Blank = no cache. Needs rerouting enabled; without an FDS "
        "dir it holds the clear-air map.",
    ),
    Parameter(
        "clear_air_visibility",
        ("--clear-air-visibility",),
        GROUP_SIGHT,
        "Force clear-air sight gating even on a deck whose agents all "
        "start fully familiar. Such agents never consult it to learn the graph, "
        "and route choice does not read it either (the gate uses the optical "
        "depth K_ave * L of the route polyline), so on such a deck it changes "
        "nothing. Decks with discovery agents get it without asking.",
        action="store_true",
        default=False,
        python="run_scenario(vis_model=VisibilityModel.clear_air(...))",
    ),
    Parameter(
        "no_visibility",
        ("--no-visibility",),
        GROUP_SIGHT,
        "Turn sight gating off entirely. Agents then learn every "
        "neighbour of each node they reach, by contact rather than by seeing "
        "it -- faster, and not a fire scenario.",
        action="store_true",
        default=False,
        python="run_scenario(vis_model=None)",
        python_default=True,
    ),
    Parameter(
        "vis_cell_size",
        ("--vis-cell-size",),
        GROUP_SIGHT,
        "Cell size of the clear-air visibility grid [m]. A wall "
        "thinner than one cell stops occluding, so keep it below the thinnest "
        f"wall that must block sight (default: {VIS_CELL_SIZE_M})",
        type=float,
        default=VIS_CELL_SIZE_M,
        unit="m",
        python="VisibilityModel.clear_air(cell_size_m=)",
        python_default=0.5,
        checked="> 0, when the clear-air model is built",
    ),
    Parameter(
        "max_sign_distance",
        ("--max-sign-distance",),
        GROUP_SIGHT,
        "Farthest distance [m] from which a sign can be read, even "
        "in clear air. A sign's own 'max_distance' overrides it "
        f"(default: {MAX_SIGN_DISTANCE_M:g}, as in fdsvismap)",
        type=float,
        default=MAX_SIGN_DISTANCE_M,
        unit="m",
        python="VisibilityModel(max_sign_distance_m=)",
        checked="finite > 0, when a visibility model is built",
    ),
    Parameter(
        "disable_tenability",
        ("--disable-tenability",),
        GROUP_GAS,
        "Run without a tenability config: disables the FIC speed-reduction "
        "rule, toxic FED incapacitation and heat FED incapacitation. FED is "
        "still accumulated and reported (default: incapacitation active when a "
        "FED or heat FED model is loaded; the FIC rule only with "
        "--enable-fic-speed)",
        action="store_true",
        default=False,
        python="run_scenario(tenability_config=None)",
        python_default=True,
        gui_help="Turn off smoke's effect on people: no slowing from irritants "
        "and no collapse from toxic dose. Agents just walk at normal speed.",
    ),
    Parameter(
        "enable_fic_speed",
        ("--enable-fic-speed",),
        GROUP_GAS,
        "Slow agents by the irritant (FIC) rule max(fic-min-factor, "
        "1 - fic-alpha * FIC) on top of the smoke-speed law. Off by default, "
        "as FDS+Evac has no irritant slowdown; before this became opt-in it "
        "was on whenever a FED model was loaded",
        action="store_true",
        default=False,
        python=f"{_TENABILITY}.enable_fic_speed",
        fds_evac=False,
        gui_help="Let irritant gases slow agents on top of smoke. Off by "
        "default, as in FDS+Evac, which has no irritant slowdown.",
    ),
    Parameter(
        "fic_alpha",
        ("--fic-alpha",),
        GROUP_GAS,
        "Slope of the FIC speed-reduction rule, a pyFDS-Evac "
        "assumption, source unknown (#147); needs --enable-fic-speed "
        f"(default: {FIC_ALPHA})",
        type=float,
        default=FIC_ALPHA,
        python=f"{_TENABILITY}.fic_alpha",
        gui_help="How strongly irritant gases slow an agent. Higher = agents "
        "slow down more in irritating smoke.",
    ),
    Parameter(
        "fic_min_factor",
        ("--fic-min-factor",),
        GROUP_GAS,
        "Lower bound on the FIC speed factor; needs --enable-fic-speed "
        f"(default: {FIC_MIN_FACTOR})",
        type=float,
        default=FIC_MIN_FACTOR,
        python=f"{_TENABILITY}.fic_min_factor",
        gui_help="Floor on irritant slowdown — an agent never drops below this "
        "fraction of its speed from irritants alone.",
    ),
    Parameter(
        "fed_threshold",
        ("--fed-threshold",),
        GROUP_GAS,
        "Cumulative FED at which an agent is incapacitated; the median "
        f"in probabilistic mode (default: {FED_THRESHOLD} per ISO 13571 / "
        "Korhonen 2021)",
        type=float,
        default=FED_THRESHOLD,
        python=f"{_TENABILITY}.fed_threshold",
        gui_help="Toxic dose (FED) at which a typical person is incapacitated. "
        "1.0 is the standard 'untenable' dose (ISO 13571). Lower = agents "
        "succumb sooner.",
    ),
    Parameter(
        "o2_threshold_percent",
        ("--o2-threshold-percent",),
        GROUP_GAS,
        "O2 volume percent at or above which the hypoxia term of the gas "
        f"FED is zero (default: {O2_THRESHOLD_PERCENT}, as FDS/FDS+Evac; 19.5 "
        "was the previous pyFDS-Evac default, the OSHA limit used by Pathfinder)",
        type=float,
        default=O2_THRESHOLD_PERCENT,
        unit="vol %",
        python="DefaultFedConfig.o2_threshold_percent",
        fds_evac=O2_THRESHOLD_PERCENT,
        gui_help="Oxygen level (vol %) below which low oxygen adds to the toxic "
        f"dose. {O2_THRESHOLD_PERCENT} as in FDS+Evac; 19.5 is the OSHA limit "
        "Pathfinder uses.",
    ),
    Parameter(
        "incapacitation_mode",
        ("--incapacitation-mode",),
        GROUP_GAS,
        "deterministic: every agent uses fed-threshold, as FDS+Evac "
        "(default); probabilistic: per-agent threshold ~ "
        "lognormal(median=fed-threshold, susceptibility-sigma), fit to NIST "
        "TN 1797 population bands",
        choices=INCAPACITATION_MODES,
        default=INCAPACITATION_MODE,
        python=f"{_TENABILITY}.incapacitation_mode",
        fds_evac=INCAPACITATION_MODE,
        gui_help="Deterministic (default, as FDS+Evac): every agent shares the "
        "same threshold. Probabilistic: each agent draws its own tolerance from "
        "a population curve (some collapse early, some late).",
    ),
    Parameter(
        "susceptibility_sigma",
        ("--susceptibility-sigma",),
        GROUP_GAS,
        "Log-normal sigma of the per-agent incapacitation threshold in "
        f"probabilistic mode (default: {SUSCEPTIBILITY_SIGMA} -> ~10/50/88%% at "
        "FED 0.3/1/3)",
        type=float,
        default=SUSCEPTIBILITY_SIGMA,
        python=f"{_TENABILITY}.susceptibility_sigma",
        gui_help="Spread of how differently people tolerate toxic smoke, used "
        "only in probabilistic mode. Higher = more variation between agents in "
        "when they're overcome.",
    ),
    Parameter(
        "enable_heat_fed",
        ("--enable-heat-fed",),
        GROUP_HEAT,
        "Accumulate the convective heat FED (ISO 13571:2012 Eq. (9), "
        "fully clothed, or the law of --heat-clothing, --heat-endpoint or "
        "--heat-fed-method) from "
        "the FDS TEMPERATURE slice and incapacitate on it. Off by default, as "
        "FDS+Evac has no heat dose; before this became opt-in it was on "
        "whenever the case had a TEMPERATURE slice",
        action="store_true",
        default=False,
        python=f"run_scenario(heat_fed_model={_HEAT_MODEL}(...))",
        fds_evac=False,
        gui_help="Accumulate a heat dose from the FDS temperature slice and let "
        "it incapacitate. Off by default, as FDS+Evac has no heat dose.",
    ),
    Parameter(
        "heat_clothing",
        ("--heat-clothing",),
        GROUP_HEAT,
        "Convective law of ISO 13571:2012 (8.3) for the heat FED; needs "
        "--enable-heat-fed. clothed (default): Eq. (9), t = 4.1e8 T^-3.61 min, "
        "fully clothed. unclothed: Eq. (10), t = 5e7 T^-3.4 min, unclothed or "
        "lightly clothed, the same law as SFPE Handbook Eq. 63.44 and the "
        "default before the ISO law. No effect with --heat-endpoint or "
        "--heat-fed-method total-flux",
        choices=HEAT_CLOTHING,
        python=f"{_HEAT_MODEL}.clothing (None: clothed)",
        gui_help="clothed (default) or unclothed. Picks the ISO 13571:2012 law "
        "for hot air: fully clothed people tolerate it about three times longer "
        "than unclothed ones. unclothed gives the SFPE Handbook law used before.",
    ),
    Parameter(
        "heat_endpoint",
        ("--heat-endpoint",),
        GROUP_HEAT,
        "Heat endpoint of SFPE Handbook Ch. 63: tolerance (Eq. 63.45), "
        "injury (Eq. 63.46) or fatal (Eq. 63.47) convective law, so that heat "
        "FED = 1 is that endpoint; needs --enable-heat-fed. Samples above "
        "205 C (an assumed limit) or non-finite are flagged. Default: none, the "
        "ISO law of --heat-clothing. "
        "With --heat-fed-method total-flux it selects the dose D of Eq. 63.43 "
        "(default there: fatal)",
        choices=tuple(HEAT_ENDPOINTS),
        python=f"{_HEAT_MODEL}.endpoint",
    ),
    Parameter(
        "heat_fed_method",
        ("--heat-fed-method",),
        GROUP_HEAT,
        "Heat dose law; needs --enable-heat-fed. convective (default): "
        "the ISO law of --heat-clothing or the law of --heat-endpoint. "
        "total-flux: heat flux to the "
        "skin from Eq. 63.49 (both terms in W/m2, divided by 1000 together), "
        "rate q^1.33/D (Eq. 63.43), the radiant term (net or excess, not "
        "incident) counted as zero below 2.5 kW/m2 (ISO 13571:2012 8.2, 8.4); "
        "D of "
        "--heat-endpoint, fatal (16.7) without it",
        choices=HEAT_FED_METHODS,
        default=HEAT_FED_METHOD,
        python=f"{_HEAT_MODEL}.method",
    ),
    Parameter(
        "heat_emissivity",
        ("--heat-emissivity",),
        GROUP_HEAT,
        "Emissivity of the gas at the head for --heat-fed-method "
        f"total-flux (default: {DEFAULT_HEAT_EMISSIVITY}, an assumption: SFPE "
        "p. 2384 gives 'perhaps 0.5 for smoke', 0.05 for a gas)",
        type=float,
        default=DEFAULT_HEAT_EMISSIVITY,
        python=f"{_HEAT_MODEL}.emissivity",
        checked="[0, 1], when the heat model is built",
    ),
    Parameter(
        "heat_convective_coefficient",
        ("--heat-convective-coefficient",),
        GROUP_HEAT,
        "Convective heat transfer coefficient h [W/m2/K] for "
        "--heat-fed-method total-flux (default: "
        f"{DEFAULT_HEAT_CONVECTIVE_COEFFICIENT}, an assumption: SFPE p. 2384 "
        "gives 5-8 for slow-moving air)",
        type=float,
        default=DEFAULT_HEAT_CONVECTIVE_COEFFICIENT,
        unit="W/m²/K",
        python=f"{_HEAT_MODEL}.convective_coefficient",
        checked="finite >= 0, when the heat model is built",
    ),
    Parameter(
        "heat_skin_temperature",
        ("--heat-skin-temperature",),
        GROUP_HEAT,
        "Fixed skin temperature [C] for --heat-fed-method total-flux "
        f"(default: {DEFAULT_HEAT_SKIN_TEMPERATURE_C}, an assumption: not given "
        "by the Handbook for Eq. 63.49)",
        type=float,
        default=DEFAULT_HEAT_SKIN_TEMPERATURE_C,
        unit="°C",
        python=f"{_HEAT_MODEL}.skin_temperature_celsius",
        checked="finite, when the heat model is built",
    ),
    Parameter(
        "heat_radiant_source",
        ("--heat-radiant-source",),
        GROUP_HEAT,
        "Radiant term of --heat-fed-method total-flux. gas (default): "
        "eps sigma (T_g^4 - T_s^4) of Eq. 63.49. integrated-intensity: the "
        "excess f*(U - 4 sigma T_s^4) over an isotropic field at the skin "
        "temperature, from the FDS INTEGRATED INTENSITY slice at the slice "
        "height, replacing the gas term (and the layer term of --heat-regime "
        "layer); needs --heat-u-factor",
        choices=HEAT_RADIANT_SOURCES,
        default=HEAT_RADIANT_SOURCE,
        python=f"{_HEAT_MODEL}.radiant_source",
    ),
    Parameter(
        "heat_u_factor",
        ("--heat-u-factor",),
        GROUP_HEAT,
        "Factor f in [0.25, 1] for --heat-radiant-source "
        "integrated-intensity: the incident radiant flux is f*U, from U/4 "
        "(sphere, or a plate in isotropic radiation) to U (one small source "
        "seen face-on); the dose uses the excess f*(U - 4 sigma T_s^4). No "
        "default: required with that source",
        type=_u_factor,
        python=f"{_HEAT_MODEL}.u_factor",
        checked="[0.25, 1], at parse",
    ),
    Parameter(
        "heat_regime",
        ("--heat-regime",),
        GROUP_HEAT,
        "Where the head is, for --heat-fed-method total-flux; a user "
        "choice, no automatic rule. smoke (default): head in smoke, Eq. 63.49 "
        "at the head. layer: head in clear air below a hot layer, convection at "
        "the head plus the net layer flux phi*eps_L*sigma*(T_L^4 - T_s^4) from "
        "a TEMPERATURE slice at --heat-layer-height, with no radiant term of "
        "the gas at the head; needs --heat-layer-height, --heat-view-factor and "
        "--heat-layer-emissivity. With --heat-radiant-source "
        "integrated-intensity, U supplies the radiant term instead and the "
        "layer term is not added (one warning)",
        choices=HEAT_FLUX_REGIMES,
        default=HEAT_REGIME,
        python=f"{_HEAT_MODEL}.regime",
    ),
    Parameter(
        "heat_layer_height",
        ("--heat-layer-height",),
        GROUP_HEAT,
        "Height [m] of the TEMPERATURE slice read as the hot layer for "
        "--heat-regime layer (no default: it depends on the ceiling height)",
        type=float,
        unit="m",
        python=f"{_HEAT_MODEL}.layer_height_m, layer FdsHeatField",
        checked="finite, with --enable-heat-fed and --heat-regime layer",
    ),
    Parameter(
        "heat_view_factor",
        ("--heat-view-factor",),
        GROUP_HEAT,
        "View factor phi in [0, 1] from the skin to the layer for "
        "--heat-regime layer (no default: about 1 for the crown, about 0.5 "
        "for the face, spec 016, unsourced)",
        type=float,
        python=f"{_HEAT_MODEL}.view_factor",
        checked="[0, 1], when the heat model is built",
    ),
    Parameter(
        "heat_layer_emissivity",
        ("--heat-layer-emissivity",),
        GROUP_HEAT,
        "Layer emissivity eps_L in [0, 1] for --heat-regime layer (no "
        "default: no sourced value)",
        type=float,
        python=f"{_HEAT_MODEL}.layer_emissivity",
        checked="[0, 1], when the heat model is built",
    ),
    Parameter(
        "heat_fed_threshold",
        ("--heat-fed-threshold",),
        GROUP_HEAT,
        "Median cumulative heat FED at which an agent is thermally "
        "incapacitated; needs --enable-heat-fed. Default: none, the value of "
        "--fed-threshold, as ISO 13571:2012 uses one threshold for FED and FEC "
        "(5.4) and sets the heat threshold in the same manner (8.5). Setting it "
        "departs from ISO; the run logs a warning "
        "and the manifest records heat_fed_threshold_override",
        type=float,
        python=f"{_TENABILITY}.heat_fed_threshold (None: fed_threshold)",
        gui_help="Heat dose at which a person is thermally incapacitated. Leave "
        "blank to use the toxic-dose threshold, as ISO 13571:2012 uses one "
        "threshold for FED and FEC and treats heat in the same manner; a value "
        "here departs from ISO and is recorded in the run manifest.",
    ),
    Parameter(
        "heat_incapacitation_mode",
        ("--heat-incapacitation-mode",),
        GROUP_HEAT,
        "Same semantics as --incapacitation-mode, applied to the "
        "independent heat FED track (default: deterministic, as no "
        "population spread for heat is published)",
        choices=INCAPACITATION_MODES,
        default=INCAPACITATION_MODE,
        python=f"{_TENABILITY}.heat_incapacitation_mode",
        gui_help="Same idea as toxic-dose mode, but for heat: deterministic "
        "(default) gives everyone the same tolerance, probabilistic draws one "
        "per agent. Independent of the toxic-gas track.",
    ),
    Parameter(
        "heat_susceptibility_sigma",
        ("--heat-susceptibility-sigma",),
        GROUP_HEAT,
        "Log-normal sigma for the heat incapacitation threshold in "
        f"probabilistic mode (default: {SUSCEPTIBILITY_SIGMA}, reused from the "
        "gas value as a starting assumption -- no independent literature "
        "support for heat)",
        type=float,
        default=SUSCEPTIBILITY_SIGMA,
        python=f"{_TENABILITY}.heat_susceptibility_sigma",
        gui_help="Spread of how differently people tolerate heat exposure, used "
        "only in probabilistic heat mode. Reuses the toxic-gas default as an "
        "assumption — there's no published population data for heat.",
    ),
)

_BY_DEST: dict[str, Parameter] = {p.dest: p for p in PARAMETERS}

#: Default of every option, by ``dest``.
DEFAULTS: dict[str, Any] = {p.dest: p.default for p in PARAMETERS}

#: Options that reach ``build_run_kwargs`` (all but ``--show-config``).
RUN_OPTIONS: tuple[str, ...] = tuple(p.dest for p in PARAMETERS if p.run_option)


def parameter(dest: str) -> Parameter:
    """Return the option named *dest*; KeyError names it when unknown."""
    try:
        return _BY_DEST[dest]
    except KeyError:
        raise KeyError(f"unknown run option: {dest!r}") from None


def default(dest: str) -> Any:
    """Return the CLI default of the option named *dest*."""
    return parameter(dest).default


def option(opts: Any, dest: str) -> Any:
    """Return ``opts.<dest>``, or the option's default when *opts* lacks it.

    ``opts`` may be a partial namespace built by hand (Python API); a
    missing attribute then means the CLI default.
    """
    return getattr(opts, dest, default(dest))


def is_set_value(param: Parameter, value: Any) -> bool:
    """Whether *value* differs from the default of *param*."""
    return bool(value != param.default)


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Add the groups and options of :data:`PARAMETERS` to *parser*."""
    groups = {
        group.title: parser.add_argument_group(group.title, group.description)
        for group in GROUPS
    }
    for param in PARAMETERS:
        groups[param.group].add_argument(*param.flags, **param.argparse_kwargs())


# --- GUI layout ------------------------------------------------------------

#: Sections of the GUI form and the options in each, in display order. An
#: option in no section lands in the form's "Other" section.
GUI_SECTIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Core", ("scenario", "seed")),
    (
        "Smoke",
        (
            "fds_dir",
            "constant_extinction",
            "smoke_update_interval",
            "smoke_slice_height",
            "allow_fds_horizon_hold",
            "require_fds_coverage",
            "smoke_blind",
        ),
    ),
    (
        "FED & Tenability",
        (
            "disable_tenability",
            "incapacitation_mode",
            "susceptibility_sigma",
            "enable_fic_speed",
            "fic_alpha",
            "fic_min_factor",
            "fed_threshold",
            "o2_threshold_percent",
            "enable_heat_fed",
            "heat_incapacitation_mode",
            "heat_susceptibility_sigma",
            "heat_clothing",
            "heat_fed_threshold",
        ),
    ),
    ("Rerouting", ("enable_rerouting", "reroute_interval", "replay_exits")),
    ("Visibility", ("vis_cache",)),
    (
        "Output files",
        (
            "output_sqlite",
            "output_smoke_history",
            "output_fed_history",
            "output_route_history",
            "output_route_cost_history",
            "output_exit_history",
            "export_app_bundle",
        ),
    ),
)

TIER_COMMON = "common"
TIER_ADVANCED = "advanced"
#: The tiers of :attr:`Parameter.tier`: common options follow the GUI's
#: sections, advanced ones are the rest (maintainer decision, #485).
TIERS: tuple[str, ...] = (TIER_COMMON, TIER_ADVANCED)
_COMMON: frozenset[str] = frozenset(
    dest for _title, dests in GUI_SECTIONS for dest in dests
)

#: Flags the GUI form does not show.
GUI_HIDDEN: frozenset[str] = frozenset(
    {"help", "print_summary", "export_only", "inspect_fds", "cleanup"}
    | {p.dest for p in PARAMETERS if not p.run_option}
)

#: Options whose GUI label carries the unit.
GUI_UNIT_LABELS: tuple[str, ...] = (
    "constant_extinction",
    "smoke_update_interval",
    "smoke_slice_height",
    "reroute_interval",
    "o2_threshold_percent",
)
