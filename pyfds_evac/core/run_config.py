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

from typing import Any, Callable, Dict

from .fed import (
    DefaultFedConfig,
    DefaultFedModel,
    FdsFedField,
    TenabilityConfig,
)
from .fds_inventory import inspect_fds_quantities
from .route_graph import RerouteConfig, RouteCostConfig
from .smoke_speed import (
    ConstantExtinctionField,
    ExtinctionField,
    SmokeSpeedConfig,
    SmokeSpeedModel,
)
from .visibility import VisibilityModel, extract_sign_descriptors

Logger = Callable[[str], None]


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
    elif opts.fds_dir:
        field = ExtinctionField.from_fds(
            smoke_config.fds_dir,
            slice_height_m=smoke_config.slice_height_m,
        )
    else:
        field = None
    if field is None:
        return None
    return SmokeSpeedModel(field, smoke_config)


def _build_fed_model(opts: Any, log: Logger):
    """Build the default FED model when the FDS run supports it."""
    if not opts.fds_dir:
        return None
    inventory = inspect_fds_quantities(opts.fds_dir)
    if not inventory.supports_default_fed():
        return None
    log("Configuring FED calculation.")
    fed_config = DefaultFedConfig(
        fds_dir=opts.fds_dir,
        update_interval_s=opts.smoke_update_interval,
        slice_height_m=opts.smoke_slice_height,
    )
    return DefaultFedModel(FdsFedField.from_fds(opts.fds_dir), fed_config)


def _build_reroute_config(scenario: Any, opts: Any, log: Logger):
    """Build the rerouting configuration from scenario routing parameters."""
    if not opts.enable_rerouting:
        return None
    routing_params = scenario.raw.get("routing", {})
    cost_config = RouteCostConfig(
        w_smoke=routing_params.get("w_smoke", 1.0),
        w_fed=routing_params.get("w_fed", 10.0),
        w_queue=routing_params.get("w_queue", 1.0),
        fed_rejection_threshold=routing_params.get("fed_rejection_threshold", 1.0),
        visibility_extinction_threshold=routing_params.get(
            "visibility_extinction_threshold", 0.5
        ),
        sampling_step_m=routing_params.get("sampling_step_m", 2.0),
        base_speed_m_per_s=routing_params.get("base_speed_m_per_s", 1.3),
        alpha=routing_params.get("alpha", 0.706),
        beta=routing_params.get("beta", -0.057),
        min_speed_factor=routing_params.get("min_speed_factor", 0.1),
        default_exit_capacity=routing_params.get("default_exit_capacity", 1.3),
    )
    log("Configuring rerouting.")
    return RerouteConfig(
        reevaluation_interval_s=opts.reroute_interval,
        cost_config=cost_config,
    )


def _validate_opts(opts: Any) -> None:
    """Reject invalid option combinations before any expensive FDS reads."""
    if opts.vis_cache and not opts.fds_dir:
        raise ValueError("--vis-cache requires --fds-dir")
    if opts.vis_cache and not opts.enable_rerouting:
        raise ValueError("--vis-cache requires --enable-rerouting")
    if getattr(opts, "smv_export", False) and not opts.fds_dir:
        raise ValueError("--smv-export requires --fds-dir")


def _build_vis_model(scenario: Any, opts: Any, log: Logger):
    """Build the sign-visibility model used for visibility-gated rerouting."""
    if not opts.vis_cache:
        return None
    sign_descriptors = extract_sign_descriptors(scenario.raw)
    if not sign_descriptors:
        log("Warning: --vis-cache set but no sign descriptors found in config.")
        return None
    log(f"Configuring visibility model ({len(sign_descriptors)} sign(s)).")
    return VisibilityModel(
        fds_dir=opts.fds_dir,
        sign_descriptors=sign_descriptors,
        cache_path=opts.vis_cache,
        time_step_s=opts.reroute_interval,
        slice_height_m=opts.smoke_slice_height,
    )


def _build_tenability_config(opts: Any, fed_model, log: Logger):
    """Build the tenability configuration when a FED model is active."""
    if fed_model is None or opts.disable_tenability:
        return None
    log(
        "Configuring tenability "
        f"(FIC alpha={opts.fic_alpha}, min={opts.fic_min_factor}, "
        f"FED threshold={opts.fed_threshold})."
    )
    return TenabilityConfig(
        enable_fic_speed=True,
        fic_alpha=opts.fic_alpha,
        fic_min_factor=opts.fic_min_factor,
        enable_incapacitation=True,
        fed_threshold=opts.fed_threshold,
    )


def build_run_kwargs(scenario: Any, opts: Any, log: Logger = _noop) -> Dict[str, Any]:
    """Translate run options into keyword arguments for ``run_scenario``.

    Returns the kwargs dict accepted by ``run_scenario`` (``seed``,
    ``smoke_speed_model``, ``fed_model``, ``tenability_config``,
    ``reroute_config``, ``collect_route_cost_history``, ``vis_model``). Raises
    ``ValueError`` for invalid option combinations.
    """
    _validate_opts(opts)
    smoke_speed_model = _build_smoke_model(opts, log)
    fed_model = _build_fed_model(opts, log)
    reroute_config = _build_reroute_config(scenario, opts, log)
    vis_model = _build_vis_model(scenario, opts, log)
    tenability_config = _build_tenability_config(opts, fed_model, log)

    collect_route_cost_history = bool(
        getattr(opts, "output_route_cost_history", None)
    ) or bool(getattr(opts, "collect_route_cost_history", False))

    return {
        "seed": opts.seed,
        "smoke_speed_model": smoke_speed_model,
        "fed_model": fed_model,
        "tenability_config": tenability_config,
        "reroute_config": reroute_config,
        "collect_route_cost_history": collect_route_cost_history,
        "vis_model": vis_model,
    }
