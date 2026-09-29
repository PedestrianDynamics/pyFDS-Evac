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

import logging
import math
from collections.abc import Callable
from typing import Any

from .cognitive_map import familiarity_probability
from .fds_inventory import inspect_fds_quantities
from .fds_sampling import fds_output_horizon
from .fed import (
    DEFAULT_HEAT_CLOTHING,
    DEFAULT_HEAT_CONVECTIVE_COEFFICIENT,
    DEFAULT_HEAT_EMISSIVITY,
    DEFAULT_HEAT_SKIN_TEMPERATURE_C,
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
from .visibility import (
    DEFAULT_MAX_SIGN_DISTANCE_M,
    VisibilityModel,
    extract_sign_descriptors,
)

Logger = Callable[[str], None]

_logger = logging.getLogger(__name__)


def _noop(_message: str) -> None:
    """Default logger that discards status messages."""


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
        _logger.warning(
            "Smoke speed reduction is disabled for %s: it has no SOOT "
            "EXTINCTION COEFFICIENT slice, so agents walk at clear-air speed. "
            "Pass --constant-extinction to set a uniform extinction instead.",
            opts.fds_dir,
        )
        field = None
    elif opts.fds_dir:
        field = ExtinctionField.from_fds(
            smoke_config.fds_dir,
            slice_height_m=smoke_config.slice_height_m,
            allow_horizon_hold=_allow_hold(opts),
        )
    else:
        field = None
    if field is None:
        return None
    return SmokeSpeedModel(field, smoke_config)


def _allow_hold(opts: Any) -> bool:
    """Return whether sampling may hold the last FDS frame (#340)."""
    return bool(getattr(opts, "allow_fds_horizon_hold", False))


def _check_fds_horizon(scenario: Any, opts: Any) -> None:
    """Raise ValueError when the run can outlast the FDS output (#340).

    Past the last FDS frame there is no smoke data; the samplers raise there
    too, but only once the run gets that far.  Failing at setup saves the
    run.  ``--allow-fds-horizon-hold`` skips the check.
    """
    if not opts.fds_dir or _allow_hold(opts):
        return
    max_time = getattr(scenario, "max_simulation_time", None)
    if max_time is None:
        return
    horizon = fds_output_horizon(opts.fds_dir)
    if horizon is None:
        return
    last, interval = horizon
    if float(max_time) <= last + interval:
        return
    raise ValueError(
        f"max_simulation_time={float(max_time):.1f} s runs past the FDS output "
        f"of {opts.fds_dir}, which ends at t={last:.1f} s (output interval "
        f"{interval:.1f} s). Lower max_simulation_time, extend T_END in the "
        "FDS run, or pass --allow-fds-horizon-hold to hold the last frame."
    )


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
        missing = sorted({"co", "co2", "o2"}.difference(present))
        named = ", ".join(m.upper() for m in missing)
        _logger.warning(
            "FED is disabled for %s: it has no %s %s, and all three of CO, CO2 "
            "and O2 are needed. Results will report zero dose and no "
            "incapacitation. FDS only writes these species when the &REAC line "
            "asks for them (CO needs CO_YIELD); see "
            "docs/fds-case-requirements.md.",
            opts.fds_dir,
            named,
            "slice" if len(missing) == 1 else "slices",
        )
        return None
    log("Configuring FED calculation.")
    fed_config = DefaultFedConfig(
        fds_dir=opts.fds_dir,
        update_interval_s=opts.smoke_update_interval,
        slice_height_m=opts.smoke_slice_height,
        o2_threshold_percent=getattr(opts, "o2_threshold_percent", 20.0),
    )
    return DefaultFedModel(
        FdsFedField.from_fds(
            opts.fds_dir,
            slice_height_m=opts.smoke_slice_height,
            allow_horizon_hold=_allow_hold(opts),
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
    if not getattr(opts, "enable_heat_fed", False):
        log("Heat FED is off; pass --enable-heat-fed to accumulate it.")
        if getattr(opts, "heat_endpoint", None) is not None:
            _logger.warning("--heat-endpoint has no effect without --enable-heat-fed.")
        if getattr(opts, "heat_clothing", None) is not None:
            _logger.warning("--heat-clothing has no effect without --enable-heat-fed.")
        if getattr(opts, "heat_fed_method", "convective") != "convective":
            _logger.warning(
                "--heat-fed-method has no effect without --enable-heat-fed."
            )
        if getattr(opts, "heat_radiant_source", "gas") != "gas":
            _logger.warning(
                "--heat-radiant-source has no effect without --enable-heat-fed."
            )
        if getattr(opts, "heat_regime", "smoke") != "smoke":
            _logger.warning("--heat-regime has no effect without --enable-heat-fed.")
        return None
    inventory = inspect_fds_quantities(opts.fds_dir)
    if not inventory.supports_heat_fed():
        # Not an error, same reasoning as _build_fed_model: plenty of cases
        # carry no TEMPERATURE slice, and the run continues without heat FED
        # -- but every heat FED column then reads zero, which looks exactly
        # like a thermally survivable fire. Say so.
        _logger.warning(
            "Heat FED is disabled for %s: it has no TEMPERATURE slice. "
            "Results will report zero heat dose and no thermal "
            "incapacitation. Add `&SLCF QUANTITY='TEMPERATURE'` to the FDS "
            "deck; see docs/fds-case-requirements.md.",
            opts.fds_dir,
        )
        return None
    endpoint = getattr(opts, "heat_endpoint", None)
    method = getattr(opts, "heat_fed_method", "convective")
    clothing = _heat_clothing(opts, endpoint, method)
    law = _ISO_LAW_NAMES[clothing] if endpoint is None else f"{endpoint} endpoint"
    if method == "total-flux":
        law = f"total flux, {endpoint or 'fatal'} dose"
    if method == "total-flux" and getattr(opts, "heat_regime", "smoke") == "layer":
        law += f", hot layer at {opts.heat_layer_height} m"
    log(f"Configuring heat FED calculation ({law}).")
    heat_fed_config = DefaultFedConfig(
        fds_dir=opts.fds_dir,
        update_interval_s=opts.smoke_update_interval,
        slice_height_m=opts.smoke_slice_height,
    )
    radiant_source = getattr(opts, "heat_radiant_source", "gas")
    field_kwargs = {
        "slice_height_m": opts.smoke_slice_height,
        "allow_horizon_hold": _allow_hold(opts),
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
        emissivity=getattr(opts, "heat_emissivity", DEFAULT_HEAT_EMISSIVITY),
        convective_coefficient=getattr(
            opts, "heat_convective_coefficient", DEFAULT_HEAT_CONVECTIVE_COEFFICIENT
        ),
        skin_temperature_celsius=getattr(
            opts, "heat_skin_temperature", DEFAULT_HEAT_SKIN_TEMPERATURE_C
        ),
        radiant_source=radiant_source,
        u_factor=getattr(opts, "heat_u_factor", None),
        **_heat_layer_kwargs(opts),
    )


_ISO_LAW_NAMES = {
    "clothed": "ISO 13571:2012 Eq. (9), clothed",
    "unclothed": "ISO 13571:2012 Eq. (10) = SFPE Eq. 63.44, unclothed",
}


def _heat_clothing(opts: Any, endpoint: str | None, method: str) -> str:
    """Return the clothing of the ISO law; warn when another law is in use."""
    clothing = getattr(opts, "heat_clothing", None)
    if clothing is None:
        return DEFAULT_HEAT_CLOTHING
    if endpoint is not None or method != "convective":
        _logger.warning(
            "--heat-clothing has no effect with --heat-endpoint or "
            "--heat-fed-method total-flux."
        )
    return clothing


def _check_integrated_intensity_source(opts: Any, method: str, inventory) -> None:
    """Raise ValueError when the INTEGRATED INTENSITY source cannot run (#221).

    A missing slice is an error, not a warning: the run would otherwise read
    as a case with no radiation.
    """
    if method != "total-flux":
        raise ValueError(
            "--heat-radiant-source integrated-intensity needs "
            "--heat-fed-method total-flux."
        )
    if getattr(opts, "heat_u_factor", None) is None:
        raise ValueError(
            "--heat-radiant-source integrated-intensity needs --heat-u-factor "
            "in [0.25, 1]; there is no default."
        )
    if "integrated_intensity" not in inventory.canonical_slice_names():
        raise ValueError(
            f"{opts.fds_dir} has no INTEGRATED INTENSITY slice. Add "
            "`&SLCF QUANTITY='INTEGRATED INTENSITY'` at the slice height."
        )


def _heat_layer_kwargs(opts: Any) -> dict[str, Any]:
    """Return the layer-regime arguments of the heat model (#222).

    The layer regime loads a second TEMPERATURE slice at
    ``opts.heat_layer_height``; the smoke regime needs none.
    """
    regime = getattr(opts, "heat_regime", "smoke")
    if regime != "layer":
        return {"regime": regime}
    return {
        "regime": regime,
        "layer_field": FdsHeatField.from_fds(
            opts.fds_dir,
            slice_height_m=opts.heat_layer_height,
            allow_horizon_hold=_allow_hold(opts),
        ),
        "view_factor": opts.heat_view_factor,
        "layer_emissivity": opts.heat_layer_emissivity,
        "layer_height_m": opts.heat_layer_height,
    }


def _validate_heat_layer_opts(opts: Any) -> None:
    """Reject a layer heat regime that cannot be built (#222)."""
    if not getattr(opts, "enable_heat_fed", False):
        return
    if getattr(opts, "heat_regime", "smoke") != "layer":
        return
    if getattr(opts, "heat_fed_method", "convective") != "total-flux":
        raise ValueError("--heat-regime layer needs --heat-fed-method total-flux")
    for option in ("heat_layer_height", "heat_view_factor", "heat_layer_emissivity"):
        if getattr(opts, option, None) is None:
            flag = "--" + option.replace("_", "-")
            raise ValueError(f"--heat-regime layer needs {flag}")
    if not math.isfinite(opts.heat_layer_height):
        raise ValueError("--heat-layer-height must be finite")


def _build_reroute_config(scenario: Any, opts: Any, log: Logger):
    """Build the rerouting configuration from scenario routing parameters."""
    if not opts.enable_rerouting:
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
    if opts.vis_cache and not opts.enable_rerouting:
        raise ValueError("--vis-cache requires --enable-rerouting")
    if getattr(opts, "clear_air_visibility", False) and opts.fds_dir:
        raise ValueError(
            "--clear-air-visibility contradicts --fds-dir: the deck has a fire, "
            "so its smoke is what decides what an agent can see"
        )
    if getattr(opts, "no_visibility", False) and getattr(
        opts, "clear_air_visibility", False
    ):
        raise ValueError("--no-visibility and --clear-air-visibility conflict")
    _validate_heat_layer_opts(opts)


def _has_discovery_agents(scenario: Any) -> bool:
    """Whether any spawn area starts agents that must find their way.

    A fully familiar agent holds the whole graph from t=0 and never consults the
    visibility model, so building one for such a deck costs time and changes
    nothing. Route choice does not consult it either: the gate uses the optical
    depth K_ave * L of the route polyline, which needs only the extinction field.
    """
    for dist in scenario.raw.get("distributions", {}).values():
        value = dist.get("parameters", {}).get("familiarity", "full")
        if value is None:
            continue
        try:
            if familiarity_probability(value) < 1.0:
                return True
        except ValueError:
            continue  # the engine reports the bad value with better context
    return False


def _build_vis_model(scenario: Any, opts: Any, log: Logger):
    """Build the sign-visibility model that gates what agents perceive.

    Sight is gated by geometry, sign facing and contrast whether or not there
    is a fire; smoke only adds to what hides a sign.  So a deck with discovery
    agents gets a model either way -- from the FDS extinction field when one is
    given, from clear air otherwise -- and running with no model at all, where
    an agent learns every neighbour of each node it reaches by contact, is now
    something you ask for with ``--no-visibility``.
    """
    if getattr(opts, "no_visibility", False):
        return None
    forced = getattr(opts, "clear_air_visibility", False)
    if not forced and not opts.vis_cache and not _has_discovery_agents(scenario):
        return None
    sign_descriptors = extract_sign_descriptors(scenario.raw)
    if not sign_descriptors:
        log("Warning: visibility gating requested but the config has no signs.")
        return None
    max_distance = getattr(opts, "max_sign_distance", DEFAULT_MAX_SIGN_DISTANCE_M)
    n_signs = len(sign_descriptors)
    plural = "" if n_signs == 1 else "s"
    smoky = bool(opts.fds_dir) and _has_extinction_slice(opts.fds_dir)
    if opts.fds_dir and not smoky:
        _logger.warning(
            "Visibility falls back to clear air for %s: it has no SOOT "
            "EXTINCTION COEFFICIENT slice, so smoke hides no sign; geometry "
            "and sign facing still do.",
            opts.fds_dir,
        )
    if not smoky:
        cell = getattr(opts, "vis_cell_size", 0.25)
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
    )


def _build_tenability_config(opts: Any, fed_model, heat_fed_model, log: Logger):
    """Build the tenability configuration when a FED or heat FED model is active.

    A temperature-only FDS case (no CO/CO2/O2, so ``fed_model`` is None) must
    still get heat incapacitation -- the gate below only skips tenability
    entirely when *neither* track has anything to sample.
    """
    if (fed_model is None and heat_fed_model is None) or opts.disable_tenability:
        return None
    mode = getattr(opts, "incapacitation_mode", "deterministic")
    sigma = getattr(opts, "susceptibility_sigma", 0.94)
    heat_threshold = getattr(opts, "heat_fed_threshold", None)
    if heat_threshold is not None and heat_fed_model is not None:
        _logger.warning(
            "--heat-fed-threshold %s departs from ISO 13571:2012, which uses one "
            "threshold for FED and FEC (5.4) and treats heat in the same manner "
            "(8.5); the manifest records it.",
            heat_threshold,
        )
    heat_mode = getattr(opts, "heat_incapacitation_mode", "deterministic")
    heat_sigma = getattr(opts, "heat_susceptibility_sigma", 0.94)
    fic_speed = fed_model is not None and getattr(opts, "enable_fic_speed", False)
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


def build_run_kwargs(scenario: Any, opts: Any, log: Logger = _noop) -> dict[str, Any]:
    """Translate run options into keyword arguments for ``run_scenario``.

    Returns the kwargs dict accepted by ``run_scenario`` (``seed``,
    ``smoke_speed_model``, ``fed_model``, ``heat_fed_model``,
    ``tenability_config``, ``reroute_config``, ``collect_route_cost_history``,
    ``vis_model``). Raises ``ValueError`` for invalid option combinations.
    """
    validate_opts(opts)
    _check_fds_horizon(scenario, opts)
    smoke_speed_model = _build_smoke_model(opts, log)
    fed_model = _build_fed_model(opts, log)
    heat_fed_model = _build_heat_fed_model(opts, log)
    reroute_config = _build_reroute_config(scenario, opts, log)
    vis_model = _build_vis_model(scenario, opts, log)
    tenability_config = _build_tenability_config(opts, fed_model, heat_fed_model, log)

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
    }
