"""Shared translation from run options to ``run_scenario`` keyword arguments.

Both the command-line runner (``run.py``) and the web GUI build the same model
configuration objects from the same flat set of options. Keeping that wiring in
one place guarantees the CLI and the GUI produce identical runs.

``opts`` is any object with attribute access whose names match ``run.py``'s
argparse ``dest`` fields (an ``argparse.Namespace`` from the CLI, or one
constructed from the web form). ``log`` receives the same human-readable status
lines the CLI prints; pass ``print`` for CLI parity, or a capturing callable
from the GUI. It defaults to a no-op.
"""

from __future__ import annotations

import csv
import logging
import math
import pathlib
from collections.abc import Callable
from typing import Any

from pyfds_evac.config import messages
from pyfds_evac.config.parameters import option, parameter
from pyfds_evac.config.rules import (
    GAS_SLICES,
    check_options,
    has_discovery_agents,
    inactive_settings,
    is_set,
    predict_mechanisms,
)

from .fds_inventory import inspect_fds_quantities
from .fds_sampling import fds_output_horizon
from .fed import (
    DEFAULT_HEAT_CLOTHING,
    DefaultFedConfig,
    DefaultFedModel,
    DefaultHeatFedModel,
    FdsFedField,
    FdsHeatField,
    TenabilityConfig,
)
from .route_graph import RerouteConfig, RouteCostConfig
from .smoke_speed import (
    ConstantExtinctionField,
    ExtinctionField,
    SmokeSpeedConfig,
    SmokeSpeedModel,
)
from .visibility import VisibilityModel, extract_sign_descriptors

Logger = Callable[[str], None]

_logger = logging.getLogger(__name__)


def _noop(_message: str) -> None:
    """Default logger that discards status messages."""


def scenario_smoke_slice_height(scenario: Any) -> float | None:
    """``simulationParams.smoke_slice_height`` of *scenario* [m], or None.

    The absolute FDS slice height the scenario asks for (an imported FDS+Evac
    deck writes z_floor + HUMAN_SMOKE_HEIGHT); ``--smoke-slice-height``
    overrides it. A value that is not a finite number is an error.
    """
    params = getattr(scenario, "sim_params", None) or {}
    if "smoke_slice_height" not in params:
        return None
    value = params["smoke_slice_height"]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(
            "simulationParams.smoke_slice_height must be a number of metres, "
            f"got {value!r}"
        )
    if not math.isfinite(value):
        raise ValueError(
            f"simulationParams.smoke_slice_height must be finite, got {value!r}"
        )
    return float(value)


def _warn_slice_height_differs(scenario: Any, opts: Any) -> None:
    """Warn when the run samples away from the scenario's slice height.

    Only the CLI applies the key by itself; a GUI, TUI or Python run passes
    its own value, which on an imported upper floor samples the wrong storey.
    """
    wanted = scenario_smoke_slice_height(scenario)
    used = option(opts, "smoke_slice_height")
    if wanted is None or used == wanted:
        return
    _logger.warning(
        "The scenario sets simulationParams.smoke_slice_height = %g m, but this "
        "run samples the FDS slices at %g m.",
        wanted,
        used,
    )


def _build_smoke_model(opts: Any, log: Logger):
    """Build the smoke-speed model from FDS output or a constant extinction."""
    if not opts.fds_dir and opts.constant_extinction is None:
        return None
    log("Configuring smoke calculation.")
    smoke_config = SmokeSpeedConfig(
        fds_dir=opts.fds_dir or ".",
        update_interval_s=opts.smoke_update_interval,
        slice_height_m=opts.smoke_slice_height,
    )
    if opts.constant_extinction is not None:
        field = ConstantExtinctionField(opts.constant_extinction)
    elif not _has_extinction_slice(opts.fds_dir):
        # Not an error, same reasoning as _build_fed_model: a heat-only case
        # carries no soot, and the run continues -- but agents then walk at
        # clear-air speed, which should not pass unnoticed.
        _logger.warning(messages.smoke_without_extinction(opts.fds_dir))
        field = None
    elif opts.fds_dir:
        field = ExtinctionField.from_fds(
            smoke_config.fds_dir,
            slice_height_m=smoke_config.slice_height_m,
            allow_horizon_hold=_allow_hold(opts),
            require_fds_coverage=_require_coverage(opts),
        )
    else:
        field = None
    if field is None:
        return None
    return SmokeSpeedModel(field, smoke_config)


def _allow_hold(opts: Any) -> bool:
    """Return whether sampling may hold the last FDS frame (#340)."""
    return bool(option(opts, "allow_fds_horizon_hold"))


def _require_coverage(opts: Any) -> bool:
    """Return whether a sample outside the FDS slices is an error (#426)."""
    return bool(option(opts, "require_fds_coverage"))


def _check_fds_horizon(scenario: Any, opts: Any, log: Logger = _noop) -> None:
    """Raise ValueError when the run can outlast the FDS output (#340).

    Past the last FDS frame there is no smoke data; the samplers raise there
    too, but only once the run gets that far.  Failing at setup saves the
    run.  With ``--allow-fds-horizon-hold`` the overrun is logged instead.
    """
    overrun = _fds_horizon_overrun(scenario, opts)
    if overrun is None:
        return
    if _allow_hold(opts):
        log(messages.horizon_hold(overrun))
        return
    raise ValueError(messages.horizon_error(overrun))


def _fds_horizon_overrun(scenario: Any, opts: Any) -> str | None:
    """Describe how max_simulation_time outlasts the FDS output, or None."""
    max_time = getattr(scenario, "max_simulation_time", None)
    if not opts.fds_dir or max_time is None:
        return None
    horizon = fds_output_horizon(opts.fds_dir)
    if horizon is None:
        return None
    last, interval = horizon
    if float(max_time) <= last + interval:
        return None
    return messages.horizon_overrun(max_time, opts.fds_dir, last, interval)


def _has_extinction_slice(fds_dir: str) -> bool:
    """Return whether the FDS case has a SOOT EXTINCTION COEFFICIENT slice."""
    return "extinction" in inspect_fds_quantities(fds_dir).canonical_slice_names()


def _build_fed_model(opts: Any, log: Logger):
    """Build the default FED model when the FDS run supports it."""
    if not opts.fds_dir:
        return None
    inventory = inspect_fds_quantities(opts.fds_dir)
    if not inventory.supports_default_fed():
        # Not an error: plenty of cases legitimately carry no toxic gas data,
        # and the run continues with smoke-speed only. But the result then has
        # no FED in it at all, and every FED column reads zero, which looks
        # exactly like a survivable fire. Say so rather than letting the user
        # infer tenability from a model that never ran.
        present = sorted(inventory.canonical_slice_names())
        missing = sorted(set(GAS_SLICES).difference(present))
        _logger.warning(messages.fed_without_gases(opts.fds_dir, missing))
        return None
    log("Configuring FED calculation.")
    fed_config = DefaultFedConfig(
        fds_dir=opts.fds_dir,
        update_interval_s=opts.smoke_update_interval,
        slice_height_m=opts.smoke_slice_height,
        o2_threshold_percent=option(opts, "o2_threshold_percent"),
    )
    return DefaultFedModel(
        FdsFedField.from_fds(
            opts.fds_dir,
            slice_height_m=opts.smoke_slice_height,
            allow_horizon_hold=_allow_hold(opts),
            require_fds_coverage=_require_coverage(opts),
        ),
        fed_config,
    )


def _build_heat_fed_model(opts: Any, log: Logger):
    """Build the heat FED model (SFPE Ch. 63) when asked for.

    The law is the ISO 13571:2012 law of ``opts.heat_clothing`` (Eq. (9),
    clothed, by default; Eq. (10) = SFPE Eq. 63.44 for ``unclothed``), the
    convective law of ``opts.heat_endpoint``, or the total-flux law of
    ``opts.heat_fed_method`` (#223).

    FDS+Evac has no heat dose, so it is opt-in (``opts.enable_heat_fed``) and
    then needs a TEMPERATURE slice.
    """
    if not opts.fds_dir:
        return None
    if not option(opts, "enable_heat_fed"):
        log("Heat FED is off; pass --enable-heat-fed to accumulate it.")
        for dest in _HEAT_LAW_FLAGS:
            if is_set(opts, dest):
                flag = parameter(dest).flag
                _logger.warning(messages.heat_option_without_enable(flag))
        return None
    inventory = inspect_fds_quantities(opts.fds_dir)
    if not inventory.supports_heat_fed():
        # Not an error, same reasoning as _build_fed_model: plenty of cases
        # carry no TEMPERATURE slice, and the run continues without heat FED
        # -- but every heat FED column then reads zero, which looks exactly
        # like a thermally survivable fire. Say so.
        _logger.warning(messages.heat_without_temperature(opts.fds_dir))
        return None
    endpoint = option(opts, "heat_endpoint")
    method = option(opts, "heat_fed_method")
    clothing = _heat_clothing(opts, endpoint, method)
    law = _ISO_LAW_NAMES[clothing] if endpoint is None else f"{endpoint} endpoint"
    if method == "total-flux":
        law = f"total flux, {endpoint or 'fatal'} dose"
    if method == "total-flux" and option(opts, "heat_regime") == "layer":
        law += f", hot layer at {opts.heat_layer_height} m"
    log(f"Configuring heat FED calculation ({law}).")
    heat_fed_config = DefaultFedConfig(
        fds_dir=opts.fds_dir,
        update_interval_s=opts.smoke_update_interval,
        slice_height_m=opts.smoke_slice_height,
    )
    radiant_source = option(opts, "heat_radiant_source")
    field_kwargs = {
        "slice_height_m": opts.smoke_slice_height,
        "allow_horizon_hold": _allow_hold(opts),
        "require_fds_coverage": _require_coverage(opts),
    }
    if radiant_source == "integrated-intensity":
        _check_integrated_intensity_source(opts, method, inventory)
        field_kwargs["integrated_intensity"] = True
        log(f"Radiant flux: {opts.heat_u_factor} x INTEGRATED INTENSITY.")
    return DefaultHeatFedModel(
        FdsHeatField.from_fds(opts.fds_dir, **field_kwargs),
        heat_fed_config,
        endpoint=endpoint,
        method=method,
        clothing=clothing,
        emissivity=option(opts, "heat_emissivity"),
        convective_coefficient=option(opts, "heat_convective_coefficient"),
        skin_temperature_celsius=option(opts, "heat_skin_temperature"),
        radiant_source=radiant_source,
        u_factor=option(opts, "heat_u_factor"),
        **_heat_layer_kwargs(opts),
    )


# Heat law options that warn when given with --fds-dir but no
# --enable-heat-fed (D13).
_HEAT_LAW_FLAGS = (
    "heat_endpoint",
    "heat_clothing",
    "heat_fed_method",
    "heat_radiant_source",
    "heat_regime",
)

_ISO_LAW_NAMES = {
    "clothed": "ISO 13571:2012 Eq. (9), clothed",
    "unclothed": "ISO 13571:2012 Eq. (10) = SFPE Eq. 63.44, unclothed",
}


def _heat_clothing(opts: Any, endpoint: str | None, method: str) -> str:
    """Return the clothing of the ISO law; warn when another law is in use."""
    clothing = option(opts, "heat_clothing")
    if clothing is None:
        return DEFAULT_HEAT_CLOTHING
    if endpoint is not None or method != "convective":
        _logger.warning(messages.HEAT_CLOTHING_OVERRIDDEN)
    return clothing


def _check_integrated_intensity_source(opts: Any, method: str, inventory) -> None:
    """Raise ValueError when the INTEGRATED INTENSITY source cannot run (#221).

    A missing slice is an error, not a warning: the run would otherwise read
    as a case with no radiation.
    """
    if method != "total-flux":
        raise ValueError(messages.INTEGRATED_INTENSITY_NEEDS_TOTAL_FLUX)
    if option(opts, "heat_u_factor") is None:
        raise ValueError(messages.INTEGRATED_INTENSITY_NEEDS_U)
    if "integrated_intensity" not in inventory.canonical_slice_names():
        raise ValueError(messages.integrated_intensity_slice_missing(opts.fds_dir))


def _heat_layer_kwargs(opts: Any) -> dict[str, Any]:
    """Return the layer-regime arguments of the heat model (#222).

    The layer regime loads a second TEMPERATURE slice at
    ``opts.heat_layer_height``; the smoke regime needs none.
    """
    regime = option(opts, "heat_regime")
    if regime != "layer":
        return {"regime": regime}
    return {
        "regime": regime,
        "layer_field": FdsHeatField.from_fds(
            opts.fds_dir,
            slice_height_m=opts.heat_layer_height,
            allow_horizon_hold=_allow_hold(opts),
            require_fds_coverage=_require_coverage(opts),
        ),
        "view_factor": opts.heat_view_factor,
        "layer_emissivity": opts.heat_layer_emissivity,
        "layer_height_m": opts.heat_layer_height,
    }


def _build_reroute_config(scenario: Any, opts: Any, log: Logger):
    """Build the rerouting configuration from scenario routing parameters."""
    if not opts.enable_rerouting:
        return None
    if option(opts, "smoke_blind"):
        log("Smoke-blind: rerouting is off.")
        return None
    cost_config = RouteCostConfig.from_routing_params(scenario.raw.get("routing", {}))
    log("Configuring rerouting.")
    return RerouteConfig(
        reevaluation_interval_s=opts.reroute_interval,
        cost_config=cost_config,
    )


def validate_opts(opts: Any) -> None:
    """Reject invalid option combinations before any expensive FDS reads.

    Public because callers that defer ``build_run_kwargs`` onto a worker
    thread still need these checks to run synchronously: they are pure
    attribute comparisons, and reporting them from a background thread would
    bury a plain user mistake in a run log instead of answering the request.
    """
    issues = check_options(opts)
    if issues:
        raise ValueError(issues[0].message)


def _has_discovery_agents(scenario: Any) -> bool:
    """Whether any spawn area starts agents that must find their way.

    A fully familiar agent holds the whole graph from t=0 and never consults the
    visibility model, so building one for such a deck costs time and changes
    nothing. Route choice does not consult it either: the gate uses the optical
    depth K_ave * L of the route polyline, which needs only the extinction field.
    """
    return has_discovery_agents(scenario.raw)


def _build_vis_model(scenario: Any, opts: Any, log: Logger):
    """Build the sign-visibility model that gates what agents perceive.

    Sight is gated by geometry, sign facing and contrast whether or not there
    is a fire; smoke only adds to what hides a sign.  So a deck with discovery
    agents gets a model either way -- from the FDS extinction field when one is
    given, from clear air otherwise -- and running with no model at all, where
    an agent learns every neighbour of each node it reaches by contact, is now
    something you ask for with ``--no-visibility``.
    """
    if option(opts, "no_visibility"):
        return None
    forced = option(opts, "clear_air_visibility")
    if not forced and not opts.vis_cache and not _has_discovery_agents(scenario):
        return None
    sign_descriptors = extract_sign_descriptors(scenario.raw)
    if not sign_descriptors:
        log(messages.NO_SIGNS)
        return None
    max_distance = option(opts, "max_sign_distance")
    n_signs = len(sign_descriptors)
    plural = "" if n_signs == 1 else "s"
    # A smoke-blind run sees what a run without the fire would see.
    blind = option(opts, "smoke_blind")
    smoky = bool(opts.fds_dir) and not blind and _has_extinction_slice(opts.fds_dir)
    if opts.fds_dir and not blind and not smoky:
        _logger.warning(messages.visibility_without_extinction(opts.fds_dir))
    if not smoky:
        cell = option(opts, "vis_cell_size")
        log(
            f"Configuring clear-air visibility ({n_signs} sign{plural}, {cell} m grid)."
        )
        return VisibilityModel.clear_air(
            scenario.walkable_polygon,
            sign_descriptors,
            cell_size_m=cell,
            cache_path=opts.vis_cache,
            max_sign_distance_m=max_distance,
        )
    log(f"Configuring visibility model ({n_signs} sign{plural}).")
    return VisibilityModel(
        fds_dir=opts.fds_dir,
        sign_descriptors=sign_descriptors,
        cache_path=opts.vis_cache,
        time_step_s=opts.reroute_interval,
        slice_height_m=opts.smoke_slice_height,
        max_sign_distance_m=max_distance,
        allow_horizon_hold=_allow_hold(opts),
        require_fds_coverage=_require_coverage(opts),
    )


def _build_tenability_config(opts: Any, fed_model, heat_fed_model, log: Logger):
    """Build the tenability configuration when a FED or heat FED model is active.

    A temperature-only FDS case (no CO/CO2/O2, so ``fed_model`` is None) must
    still get heat incapacitation -- the gate below only skips tenability
    entirely when *neither* track has anything to sample.
    """
    if (fed_model is None and heat_fed_model is None) or opts.disable_tenability:
        return None
    if option(opts, "smoke_blind"):
        # Dose still accumulates into the FED history; it stops or slows nobody.
        log("Smoke-blind: FED is recorded, incapacitation and FIC slowdown off.")
        return None
    mode = option(opts, "incapacitation_mode")
    sigma = option(opts, "susceptibility_sigma")
    heat_threshold = option(opts, "heat_fed_threshold")
    if heat_threshold is not None and heat_fed_model is not None:
        _logger.warning(messages.heat_threshold_departs(heat_threshold))
    heat_mode = option(opts, "heat_incapacitation_mode")
    heat_sigma = option(opts, "heat_susceptibility_sigma")
    fic_speed = fed_model is not None and option(opts, "enable_fic_speed")
    log(
        "Configuring tenability "
        f"(FIC slowdown={'on' if fic_speed else 'off'}, "
        f"FIC alpha={opts.fic_alpha}, min={opts.fic_min_factor}, "
        f"FED median={opts.fed_threshold}, incapacitation={mode}, "
        "heat FED median="
        f"{opts.fed_threshold if heat_threshold is None else heat_threshold}, "
        f"heat incapacitation={heat_mode})."
    )
    return TenabilityConfig(
        enable_fic_speed=fic_speed,
        fic_alpha=opts.fic_alpha,
        fic_min_factor=opts.fic_min_factor,
        enable_incapacitation=fed_model is not None,
        fed_threshold=opts.fed_threshold,
        incapacitation_mode=mode,
        susceptibility_sigma=sigma,
        enable_heat_incapacitation=heat_fed_model is not None,
        heat_fed_threshold=heat_threshold,
        heat_incapacitation_mode=heat_mode,
        heat_susceptibility_sigma=heat_sigma,
    )


def load_replay_exits(path: str | pathlib.Path) -> dict[tuple[str, int], str]:
    """Read an exit history CSV into ``{(origin, spawn_index): exit_id}``.

    The file is what ``--output-exit-history`` writes; only its ``origin``,
    ``spawn_index`` and ``exit_id`` columns are read. Raises ValueError on a
    missing column, a non-integer or repeated spawn index, or an empty exit.
    """
    with pathlib.Path(path).open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"origin", "spawn_index", "exit_id"}
        missing = required.difference(reader.fieldnames or [])
        if missing:
            raise ValueError(f"{path}: missing column(s) {', '.join(sorted(missing))}")
        exits: dict[tuple[str, int], str] = {}
        for line, row in enumerate(reader, start=2):
            key, exit_id = _replay_row(path, line, row)
            if key in exits:
                raise ValueError(f"{path}:{line}: spawn {key} is listed twice")
            exits[key] = exit_id
    return exits


def _replay_row(path, line: int, row: dict[str, str]) -> tuple[tuple[str, int], str]:
    """Parse one exit history row; raise ValueError naming the line."""
    try:
        index = int(row["spawn_index"])
    except (TypeError, ValueError):
        raise ValueError(
            f"{path}:{line}: spawn_index {row['spawn_index']!r} is not an integer"
        ) from None
    exit_id = (row["exit_id"] or "").strip()
    if not exit_id:
        raise ValueError(f"{path}:{line}: spawn index {index} has no exit_id")
    return ((row["origin"] or "").strip(), index), exit_id


def _build_replay_exits(opts: Any, log: Logger) -> dict[tuple[str, int], str] | None:
    """Load ``--replay-exits`` and warn when rerouting may undo it."""
    path = option(opts, "replay_exits")
    if not path:
        return None
    exits = load_replay_exits(path)
    log(f"Replaying the exits of {len(exits)} agents from {path}.")
    if opts.enable_rerouting and not option(opts, "smoke_blind"):
        _logger.warning(messages.REPLAY_WITH_REROUTING)
    return exits


class _BuiltFacts:
    """What the built models tell about the FDS case (``FdsFacts.has``).

    The gas, extinction and temperature slices follow from which models
    were built; anything else is read from the inventory on demand.
    """

    def __init__(self, opts: Any, smoke_speed_model, fed_model, heat_fed_model):
        self._opts = opts
        self._smoke = smoke_speed_model
        self._fed = fed_model
        self._heat = heat_fed_model
        self._slices: set[str] | None = None

    def has(self, quantity: str) -> bool:
        if quantity in GAS_SLICES:
            return self._fed is not None
        constant = option(self._opts, "constant_extinction") is not None
        if quantity == "extinction" and not constant:
            return self._smoke is not None
        if quantity == "temperature" and option(self._opts, "enable_heat_fed"):
            return self._heat is not None
        if self._slices is None:
            inventory = inspect_fds_quantities(self._opts.fds_dir)
            self._slices = set(inventory.canonical_slice_names())
        return quantity in self._slices


def _warn_inactive(scenario: Any, opts: Any, facts: _BuiltFacts) -> None:
    """Warn once for each option set away from its default that does nothing.

    Options an earlier warning already names (D12, D13, D15, D27) are left
    out. The effective configuration lists the same options with the same
    reasons (``pyfds_evac.config.rules.inactive_settings``).
    """
    raw = getattr(scenario, "raw", None) or {}
    mechanisms = predict_mechanisms(opts, raw, facts)
    for setting in inactive_settings(opts, mechanisms):
        if not setting.warned:
            _logger.warning(setting.message)


def build_run_kwargs(scenario: Any, opts: Any, log: Logger = _noop) -> dict[str, Any]:
    """Translate run options into keyword arguments for ``run_scenario``.

    Returns the kwargs dict accepted by ``run_scenario`` (``seed``,
    ``smoke_speed_model``, ``fed_model``, ``heat_fed_model``,
    ``tenability_config``, ``reroute_config``, ``collect_route_cost_history``,
    ``vis_model``, ``smoke_blind``, ``replay_exits``,
    ``require_fds_coverage``). Raises ``ValueError`` for invalid option combinations.
    """
    validate_opts(opts)
    _warn_slice_height_differs(scenario, opts)
    _check_fds_horizon(scenario, opts, log)
    smoke_speed_model = _build_smoke_model(opts, log)
    fed_model = _build_fed_model(opts, log)
    heat_fed_model = _build_heat_fed_model(opts, log)
    reroute_config = _build_reroute_config(scenario, opts, log)
    vis_model = _build_vis_model(scenario, opts, log)
    tenability_config = _build_tenability_config(opts, fed_model, heat_fed_model, log)
    replay_exits = _build_replay_exits(opts, log)
    _warn_inactive(
        scenario,
        opts,
        _BuiltFacts(opts, smoke_speed_model, fed_model, heat_fed_model),
    )

    collect_route_cost_history = bool(
        getattr(opts, "output_route_cost_history", None)
    ) or bool(getattr(opts, "collect_route_cost_history", False))

    return {
        "seed": opts.seed,
        "smoke_speed_model": smoke_speed_model,
        "fed_model": fed_model,
        "heat_fed_model": heat_fed_model,
        "tenability_config": tenability_config,
        "reroute_config": reroute_config,
        "collect_route_cost_history": collect_route_cost_history,
        "vis_model": vis_model,
        # Cheap (a size check per agent per timestep) and the GUI's cognitive
        # map growth plot needs it, so there is no reason to gate it.
        "collect_cognitive_map_history": True,
        "smoke_blind": bool(option(opts, "smoke_blind")),
        "replay_exits": replay_exits,
        "require_fds_coverage": _require_coverage(opts),
    }
