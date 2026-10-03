"""Dependency and validation rules of the run options (#484).

Which models a run builds follows from three inputs: the options, the
scenario JSON and, with ``--fds-dir``, the FDS inventory (which slices the
case has). :func:`predict_mechanisms` states that rule once;
``build_run_kwargs`` builds the models and the effective configuration
describes them with it. :func:`inactive_settings` lists the options that are
set but change nothing, with the reason; :func:`check_options` the option
conflicts ``validate_opts`` rejects.

Each rule carries the number of the dependency table (``D…``) and when it
can be checked: ``F`` options only, ``S`` with the scenario, ``I`` with the
FDS inventory, ``B`` when a model is built.

Imports stay light: the FDS inventory and the sign extraction load only
when asked for.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, NamedTuple

from . import messages
from .parameters import is_set_value, option, parameter

GAS_SLICES = ("co", "co2", "o2")


@dataclass(frozen=True)
class FdsFacts:
    """What the FDS case offers: canonical slice names and the horizon.

    ``slices`` uses the names of ``FdsQuantityInventory.canonical_slice_names``
    (``extinction``, ``co``, ``co2``, ``o2``, ``temperature``,
    ``integrated_intensity``). ``horizon`` is ``(last time, output interval)``
    [s] or None.
    """

    slices: frozenset[str]
    horizon: tuple[float, float] | None = None

    def has(self, quantity: str) -> bool:
        return quantity in self.slices

    @classmethod
    def read(cls, fds_dir: str) -> FdsFacts:
        """Inspect *fds_dir* (imports fdsreader)."""
        from pyfds_evac.core.fds_inventory import inspect_fds_quantities
        from pyfds_evac.core.fds_sampling import fds_output_horizon

        inventory = inspect_fds_quantities(fds_dir)
        return cls(
            frozenset(inventory.canonical_slice_names()),
            fds_output_horizon(fds_dir),
        )


class _Unknown:
    """No FDS inventory read yet: every slice counts as present."""

    horizon = None

    def has(self, quantity: str) -> bool:
        return True


UNKNOWN_FDS = _Unknown()


@dataclass(frozen=True)
class Mechanisms:
    """The models a run builds.

    ``smoke`` is ``"fds"``, ``"constant"`` or None; ``visibility`` is
    ``"smoky"``, ``"clear-air"`` or None; ``signs`` is the number of signs
    when a visibility model was asked for (None otherwise).
    """

    smoke: str | None
    gas_fed: bool
    heat_fed: bool
    tenability: bool
    fic: bool
    rerouting: bool
    visibility: str | None
    signs: int | None
    discovery: bool


def has_discovery_agents(raw: Mapping[str, Any]) -> bool:
    """Whether any spawn area starts agents that must find their way."""
    from pyfds_evac.core.cognitive_map import familiarity_probability

    for dist in raw.get("distributions", {}).values():
        value = dist.get("parameters", {}).get("familiarity", "full")
        if value is None:
            continue
        try:
            if familiarity_probability(value) < 1.0:
                return True
        except ValueError:
            continue  # the engine reports the bad value with better context
    return False


def sign_count(raw: Mapping[str, Any]) -> int:
    """Number of signs the visibility model would get (imports shapely)."""
    from pyfds_evac.core.visibility import extract_sign_descriptors

    return len(extract_sign_descriptors(dict(raw)))


def predict_mechanisms(
    opts: Any, raw: Mapping[str, Any], fds: Any = UNKNOWN_FDS
) -> Mechanisms:
    """The models ``build_run_kwargs`` builds for *opts* and the scenario *raw*.

    *fds* answers ``has(quantity)``: an :class:`FdsFacts`, or
    :data:`UNKNOWN_FDS` before the inventory is read (every slice present).
    """
    fds_dir = option(opts, "fds_dir")
    blind = bool(option(opts, "smoke_blind"))
    if fds_dir and option(opts, "constant_extinction") is None:
        smoke = "fds" if fds.has("extinction") else None
    elif option(opts, "constant_extinction") is not None:
        smoke = "constant"
    else:
        smoke = None
    gas = bool(fds_dir) and all(fds.has(q) for q in GAS_SLICES)
    heat = (
        bool(fds_dir)
        and bool(option(opts, "enable_heat_fed"))
        and fds.has("temperature")
    )
    tenability = (gas or heat) and not option(opts, "disable_tenability") and not blind
    discovery = has_discovery_agents(raw)
    visibility, signs = _predict_visibility(opts, raw, fds, discovery)
    return Mechanisms(
        smoke=smoke,
        gas_fed=gas,
        heat_fed=heat,
        tenability=tenability,
        fic=tenability and gas and bool(option(opts, "enable_fic_speed")),
        rerouting=bool(option(opts, "enable_rerouting")) and not blind,
        visibility=visibility,
        signs=signs,
        discovery=discovery,
    )


def _predict_visibility(
    opts: Any, raw: Mapping[str, Any], fds: Any, discovery: bool
) -> tuple[str | None, int | None]:
    """D27, D28: the visibility model and its sign count."""
    if option(opts, "no_visibility"):
        return None, None
    asked = option(opts, "clear_air_visibility") or option(opts, "vis_cache")
    if not asked and not discovery:
        return None, None
    signs = sign_count(raw)
    if not signs:
        return None, 0
    fds_dir = option(opts, "fds_dir")
    smoky = bool(fds_dir) and not option(opts, "smoke_blind") and fds.has("extinction")
    return ("smoky" if smoky else "clear-air"), signs


# --- errors ----------------------------------------------------------------


@dataclass(frozen=True)
class ConfigIssue:
    """A configuration error or a setup warning, with its rule and option."""

    rule: str
    option: str | None
    message: str
    when: str


def check_options(opts: Any) -> list[ConfigIssue]:
    """The option conflicts ``validate_opts`` rejects (D25, D26, D19), in order.

    ``validate_opts`` raises the first; front ends may show them all.
    """
    issues: list[ConfigIssue] = []
    if option(opts, "vis_cache") and not option(opts, "enable_rerouting"):
        issues.append(
            ConfigIssue("D25", "vis_cache", messages.VIS_CACHE_NEEDS_REROUTING, "F")
        )
    if option(opts, "clear_air_visibility") and option(opts, "fds_dir"):
        issues.append(
            ConfigIssue(
                "D26", "clear_air_visibility", messages.CLEAR_AIR_CONTRADICTS_FDS, "F"
            )
        )
    if option(opts, "no_visibility") and option(opts, "clear_air_visibility"):
        issues.append(
            ConfigIssue("D26", "no_visibility", messages.NO_VISIBILITY_CONFLICT, "F")
        )
    layer = _check_heat_layer(opts)
    if layer is not None:
        issues.append(layer)
    return issues


def _check_heat_layer(opts: Any) -> ConfigIssue | None:
    """D19: a layer regime that cannot be built (with --enable-heat-fed)."""
    if not option(opts, "enable_heat_fed") or option(opts, "heat_regime") != "layer":
        return None
    if option(opts, "heat_fed_method") != "total-flux":
        return ConfigIssue("D19", "heat_regime", messages.LAYER_NEEDS_TOTAL_FLUX, "F")
    for dest in ("heat_layer_height", "heat_view_factor", "heat_layer_emissivity"):
        if option(opts, dest) is None:
            message = messages.layer_needs(parameter(dest).flag)
            return ConfigIssue("D19", dest, message, "F")
    if not math.isfinite(option(opts, "heat_layer_height")):
        return ConfigIssue(
            "D19", "heat_layer_height", messages.LAYER_HEIGHT_NOT_FINITE, "F"
        )
    return None


def horizon_overrun(opts: Any, max_time: Any, fds: Any) -> str | None:
    """D32: how max_simulation_time outlasts the FDS output, or None."""
    fds_dir = option(opts, "fds_dir")
    horizon = getattr(fds, "horizon", None)
    if not fds_dir or max_time is None or horizon is None:
        return None
    last, interval = horizon
    if float(max_time) <= last + interval:
        return None
    return messages.horizon_overrun(max_time, fds_dir, last, interval)


def integrated_intensity_issue(opts: Any, fds: Any) -> ConfigIssue | None:
    """D17: raised when the heat model is built with that radiant source."""
    if option(opts, "heat_radiant_source") != "integrated-intensity":
        return None
    if option(opts, "heat_fed_method") != "total-flux":
        message = messages.INTEGRATED_INTENSITY_NEEDS_TOTAL_FLUX
        return ConfigIssue("D17", "heat_radiant_source", message, "B")
    if option(opts, "heat_u_factor") is None:
        message = messages.INTEGRATED_INTENSITY_NEEDS_U
        return ConfigIssue("D17", "heat_u_factor", message, "B")
    if not fds.has("integrated_intensity"):
        message = messages.integrated_intensity_slice_missing(option(opts, "fds_dir"))
        return ConfigIssue("D17", "heat_radiant_source", message, "I")
    return None


# --- options with no effect ------------------------------------------------


@dataclass(frozen=True)
class Inactive:
    """An option set away from its default that changes nothing in this run.

    ``warned`` is True when the run already logs a warning that covers it
    (D12, D13 with --fds-dir, D15, D27), so no second warning is added.
    """

    option: str
    flag: str
    value: Any
    rule: str
    reason: str
    warned: bool = False

    @property
    def message(self) -> str:
        return messages.no_effect(self.flag, self.reason)


def is_set(opts: Any, dest: str) -> bool:
    """Whether *opts* holds another value than the option's default."""
    return is_set_value(parameter(dest), option(opts, dest))


_Reason = tuple[str, str, bool] | None
_HEAT_LAW_FLAGS = (
    "heat_endpoint",
    "heat_clothing",
    "heat_fed_method",
    "heat_radiant_source",
    "heat_regime",
)


_NO_GAS = "without a gas FED model (the FDS case lacks CO, CO2 or O2)"


def _gas_reason(opts: Any, m: Mechanisms, rule: str) -> _Reason:
    """Why the gas FED model or its tenability track is off (D6-D8, D11)."""
    if not option(opts, "fds_dir"):
        return (rule, "without --fds-dir", False)
    if not m.gas_fed:
        return (rule, _NO_GAS, False)
    return _tenability_off(opts)


def _tenability_off(opts: Any) -> _Reason:
    if option(opts, "disable_tenability"):
        return ("D7", "with --disable-tenability", False)
    if option(opts, "smoke_blind"):
        return ("D7", "with --smoke-blind", False)
    return None


def _no_vis_reason(opts: Any, m: Mechanisms) -> _Reason:
    if option(opts, "no_visibility"):
        return ("D27", "with --no-visibility", False)
    if m.signs == 0:
        return ("D27", "because the scenario has no signs", True)
    return (
        "D27",
        "without a visibility model (every agent starts fully familiar; "
        "--clear-air-visibility builds one)",
        False,
    )


def _heat_off(opts: Any, dest: str, m: Mechanisms) -> _Reason:
    """D12-D14: a heat option while no heat model is built."""
    if not option(opts, "fds_dir"):
        return ("D14", "without --fds-dir", False)
    if dest == "enable_heat_fed" or option(opts, "enable_heat_fed"):
        reason = "because the FDS case has no TEMPERATURE slice"
        return ("D12", reason, dest == "enable_heat_fed")
    return ("D13", "without --enable-heat-fed", dest in _HEAT_LAW_FLAGS)


def _heat_reason(opts: Any, dest: str, m: Mechanisms) -> _Reason:
    if not m.heat_fed:
        return _heat_off(opts, dest, m)
    method = option(opts, "heat_fed_method")
    if dest == "heat_clothing" and (
        option(opts, "heat_endpoint") is not None or method != "convective"
    ):
        return ("D15", "with --heat-endpoint or --heat-fed-method total-flux", True)
    if dest in _TOTAL_FLUX_ONLY and method != "total-flux":
        return ("D16", "without --heat-fed-method total-flux", False)
    if dest == "heat_u_factor" and (
        option(opts, "heat_radiant_source") != "integrated-intensity"
    ):
        return ("D18", "without --heat-radiant-source integrated-intensity", False)
    if dest in _LAYER_ONLY and option(opts, "heat_regime") != "layer":
        return ("D19", "without --heat-regime layer", False)
    if dest in _HEAT_TENABILITY and not m.tenability:
        return _tenability_off(opts)
    if dest == "heat_susceptibility_sigma":
        if option(opts, "heat_incapacitation_mode") != "probabilistic":
            return (
                "D10",
                "without --heat-incapacitation-mode probabilistic",
                False,
            )
    return None


_TOTAL_FLUX_ONLY = frozenset(
    {"heat_emissivity", "heat_convective_coefficient", "heat_skin_temperature"}
)
_LAYER_ONLY = frozenset(
    {"heat_layer_height", "heat_view_factor", "heat_layer_emissivity"}
)
_HEAT_TENABILITY = frozenset(
    {"heat_fed_threshold", "heat_incapacitation_mode", "heat_susceptibility_sigma"}
)


def _fed_threshold_reason(opts: Any, m: Mechanisms) -> _Reason:
    """--fed-threshold is the gas threshold and, by default, the heat one."""
    heat_uses_it = m.heat_fed and option(opts, "heat_fed_threshold") is None
    if m.tenability and (m.gas_fed or heat_uses_it):
        return None
    if not m.gas_fed and not m.heat_fed:
        if not option(opts, "fds_dir"):
            return ("D7", "without --fds-dir", False)
        return ("D7", "without a gas or heat FED model", False)
    if not m.tenability:
        return _tenability_off(opts)
    return ("D11", _NO_GAS, False)


def _sigma_reason(opts: Any, m: Mechanisms) -> _Reason:
    if option(opts, "incapacitation_mode") != "probabilistic":
        return ("D10", "without --incapacitation-mode probabilistic", False)
    return _gas_tenability_reason(opts, m)


def _gas_tenability_reason(opts: Any, m: Mechanisms) -> _Reason:
    if m.tenability and m.gas_fed:
        return None
    return _gas_reason(opts, m, "D11")


def _fic_reason(opts: Any, m: Mechanisms) -> _Reason:
    if m.fic:
        return None
    return _gas_reason(opts, m, "D8")


def _fic_param_reason(opts: Any, m: Mechanisms) -> _Reason:
    if m.fic:
        return None
    if not option(opts, "enable_fic_speed"):
        return ("D9", "without --enable-fic-speed", False)
    return _gas_reason(opts, m, "D8")


def _reroute_interval_reason(opts: Any, m: Mechanisms) -> _Reason:
    """D23, D24: also the time step of the smoke-aware vismap."""
    if m.rerouting or m.visibility == "smoky":
        return None
    if not option(opts, "enable_rerouting"):
        return ("D23", "with --no-enable-rerouting", False)
    return ("D24", "with --smoke-blind", False)


def _fds_only(opts: Any, m: Mechanisms) -> _Reason:
    if option(opts, "fds_dir"):
        return None
    return ("D5", "without --fds-dir", False)


def _update_interval_reason(opts: Any, m: Mechanisms) -> _Reason:
    if option(opts, "fds_dir") or option(opts, "constant_extinction") is not None:
        return None
    return ("D5", "without --fds-dir or --constant-extinction", False)


def _vis_cell_reason(opts: Any, m: Mechanisms) -> _Reason:
    if m.visibility == "clear-air":
        return None
    if m.visibility == "smoky":
        return ("D29", "with the smoke-aware visibility model (FDS mesh)", False)
    return _no_vis_reason(opts, m)


def _vis_model_reason(opts: Any, m: Mechanisms) -> _Reason:
    return None if m.visibility is not None else _no_vis_reason(opts, m)


def _disable_tenability_reason(opts: Any, m: Mechanisms) -> _Reason:
    if m.gas_fed or m.heat_fed:
        return None
    return ("D7", "without a gas or heat FED model", False)


def _o2_reason(opts: Any, m: Mechanisms) -> _Reason:
    if m.gas_fed:
        return None
    if not option(opts, "fds_dir"):
        return ("D6", "without --fds-dir", False)
    return ("D6", _NO_GAS, False)


_RULES: dict[str, Callable[[Any, Mechanisms], _Reason]] = {
    "smoke_update_interval": _update_interval_reason,
    "smoke_slice_height": _fds_only,
    "allow_fds_horizon_hold": _fds_only,
    "require_fds_coverage": _fds_only,
    "reroute_interval": _reroute_interval_reason,
    "vis_cache": _vis_model_reason,
    "clear_air_visibility": _vis_model_reason,
    "vis_cell_size": _vis_cell_reason,
    "max_sign_distance": _vis_model_reason,
    "disable_tenability": _disable_tenability_reason,
    "enable_fic_speed": _fic_reason,
    "fic_alpha": _fic_param_reason,
    "fic_min_factor": _fic_param_reason,
    "fed_threshold": _fed_threshold_reason,
    "o2_threshold_percent": _o2_reason,
    "incapacitation_mode": _gas_tenability_reason,
    "susceptibility_sigma": _sigma_reason,
}

HEAT_OPTIONS = (
    "enable_heat_fed",
    "heat_clothing",
    "heat_endpoint",
    "heat_fed_method",
    "heat_emissivity",
    "heat_convective_coefficient",
    "heat_skin_temperature",
    "heat_radiant_source",
    "heat_u_factor",
    "heat_regime",
    "heat_layer_height",
    "heat_view_factor",
    "heat_layer_emissivity",
    "heat_fed_threshold",
    "heat_incapacitation_mode",
    "heat_susceptibility_sigma",
)


def _reason(opts: Any, dest: str, m: Mechanisms) -> _Reason:
    if dest in HEAT_OPTIONS:
        return _heat_reason(opts, dest, m)
    rule = _RULES.get(dest)
    return None if rule is None else rule(opts, m)


def inactive_settings(opts: Any, mechanisms: Mechanisms) -> list[Inactive]:
    """Options set away from their default that change nothing, in flag order.

    Output paths are not listed: the GUI sets every one of them.
    """
    from .parameters import PARAMETERS

    found: list[Inactive] = []
    for param in PARAMETERS:
        if not param.run_option or not is_set(opts, param.dest):
            continue
        reason = _reason(opts, param.dest, mechanisms)
        if reason is None:
            continue
        rule, text, warned = reason
        found.append(
            Inactive(
                param.dest, param.flag, option(opts, param.dest), rule, text, warned
            )
        )
    return found


# --- values checked when a model is built (B) ------------------------------

_HEAT_VALUE_OPTIONS = (
    ("emissivity", "heat_emissivity"),
    ("convective coefficient", "heat_convective_coefficient"),
    ("Skin temperature", "heat_skin_temperature"),
    ("view factor", "heat_view_factor"),
    ("layer emissivity", "heat_layer_emissivity"),
)


def heat_value_issue(opts: Any) -> ConfigIssue | None:
    """The value checks of ``DefaultHeatFedModel``, run without FDS data.

    Calls the same checks the constructor calls, in its order, so the
    message is the one the run raises. Only meaningful when a heat model
    is built (after D17 and the layer field passed).
    """
    from pyfds_evac.core import fed

    method = option(opts, "heat_fed_method")
    regime = option(opts, "heat_regime")
    try:
        fed._check_heat_flux_parameters(
            method,
            option(opts, "heat_emissivity"),
            option(opts, "heat_convective_coefficient"),
            option(opts, "heat_skin_temperature"),
        )
        fed._check_radiant_source(
            option(opts, "heat_radiant_source"), method, option(opts, "heat_u_factor")
        )
        # run_config passes the layer values only in the layer regime.
        layer = regime == "layer"
        fed._check_layer_parameters(
            regime,
            method,
            object() if layer else None,
            option(opts, "heat_view_factor") if layer else None,
            option(opts, "heat_layer_emissivity") if layer else None,
        )
    except ValueError as exc:
        message = str(exc)
        dest = next((d for key, d in _HEAT_VALUE_OPTIONS if key in message), None)
        return ConfigIssue("B", dest, message, "B")
    return None


def visibility_value_issue(
    opts: Any, raw: Mapping[str, Any], mechanisms: Mechanisms
) -> ConfigIssue | None:
    """The value checks of ``VisibilityModel``, run without building the map."""
    if mechanisms.visibility is None:
        return None
    from pyfds_evac.core import visibility

    cell = option(opts, "vis_cell_size")
    if mechanisms.visibility == "clear-air" and cell <= 0:
        message = f"cell_size_m must be positive, got {cell}"
        return ConfigIssue("B", "vis_cell_size", message, "B")
    try:
        visibility._check_max_sign_distance(option(opts, "max_sign_distance"))
    except ValueError as exc:
        return ConfigIssue("B", "max_sign_distance", str(exc), "B")
    try:
        visibility._sign_caps(visibility.extract_sign_descriptors(dict(raw)))
    except ValueError as exc:
        return ConfigIssue("B", None, str(exc), "S")
    return None


# --- whether an option applies, at any value (#485 R1) ---------------------


class Applicability(NamedTuple):
    """Whether an option changes the run, and why not.

    ``active`` False comes with the rule (``D…``) and the reason, worded as
    in the "has no effect" warnings ("without --fds-dir"). ``active`` True
    means no rule says the option is inert; an option without rules (the
    seed, output paths) is always active, and so is an option whose value
    is a configuration error (it must stay editable).
    """

    active: bool
    rule: str | None = None
    reason: str | None = None


_ACTIVE = Applicability(True)


class _Probe:
    """*opts* with one option replaced, for asking "what if it were on"."""

    def __init__(self, opts: Any, dest: str, value: Any) -> None:
        self._opts = opts
        self._dest = dest
        self._value = value

    def __getattr__(self, name: str) -> Any:
        if name == self._dest:
            return self._value
        return option(self._opts, name)


# Switches that build a model. At their default the question is whether
# switching them on would do anything, so they are probed in the on state.
_SWITCH_ON: dict[str, Any] = {
    "enable_heat_fed": True,
    "clear_air_visibility": True,
    "vis_cache": "vis-cache",
}


def _switch_reason(opts: Any, dest: str, raw: Mapping[str, Any], fds: Any) -> _Reason:
    """Why switching *dest* on would change nothing, or would be refused."""
    probe = _Probe(opts, dest, _SWITCH_ON[dest])
    for issue in check_options(probe):
        if issue.option == dest:
            text = _CONFLICTS.get((issue.rule, dest), issue.message)
            return (issue.rule, text, False)
    return _reason(probe, dest, predict_mechanisms(probe, raw, fds))


_CONFLICTS = {
    ("D25", "vis_cache"): "with --no-enable-rerouting (they conflict)",
    ("D26", "clear_air_visibility"): "with --fds-dir (they conflict)",
}


def _default_reason(opts: Any, dest: str, m: Mechanisms) -> _Reason:
    """Rules for an option at its default that a set value never needs.

    Kept out of :func:`inactive_settings`, so the run logs no new warning.
    """
    if dest == "enable_rerouting" and option(opts, "smoke_blind"):
        return ("D24", "with --smoke-blind", False)
    return None


def invalid_options(
    opts: Any, raw: Mapping[str, Any], fds: Any, mechanisms: Mechanisms
) -> frozenset[str]:
    """Options named by the errors of the effective configuration."""
    from .effective import _errors, _max_simulation_time

    max_time = _max_simulation_time(None, raw)
    errors = _errors(opts, mechanisms, fds, max_time, raw)
    return frozenset(e.option for e in errors if e.option is not None)


def applies(
    dest: str,
    opts: Any,
    raw: Mapping[str, Any],
    fds: Any = UNKNOWN_FDS,
    *,
    mechanisms: Mechanisms | None = None,
    invalid: frozenset[str] | None = None,
) -> Applicability:
    """Whether the option *dest* changes the run, at the value *opts* holds.

    Unlike :func:`inactive_settings`, also for an option at its default:
    the heat options while heat FED is off report D13 "without
    --enable-heat-fed". A switch at its default (``--enable-heat-fed``,
    ``--clear-air-visibility``, ``--vis-cache``) is active when switching it
    on would build its model. For an option set away from its default the
    answer is the one the effective configuration gives: its ``inactive``
    list, where an option with an invalid value is an error, not inactive.
    *mechanisms* (``predict_mechanisms``) and *invalid*
    (:func:`invalid_options`) may be passed to skip recomputing them.
    """
    parameter(dest)  # KeyError naming an unknown option
    if mechanisms is None:
        mechanisms = predict_mechanisms(opts, raw, fds)
    if invalid is None:
        invalid = invalid_options(opts, raw, fds, mechanisms)
    if dest in invalid:
        return _ACTIVE
    at_default = not is_set(opts, dest)
    if at_default and dest in _SWITCH_ON:
        reason = _switch_reason(opts, dest, raw, fds)
    else:
        reason = _reason(opts, dest, mechanisms)
    if reason is None and at_default:
        reason = _default_reason(opts, dest, mechanisms)
    if reason is None:
        return _ACTIVE
    rule, text, _warned = reason
    return Applicability(False, rule, text)


def applicability(
    opts: Any, raw: Mapping[str, Any], fds: Any = UNKNOWN_FDS
) -> dict[str, Applicability]:
    """:func:`applies` for every run option, by ``dest``, in flag order."""
    from .parameters import PARAMETERS

    mechanisms = predict_mechanisms(opts, raw, fds)
    invalid = invalid_options(opts, raw, fds, mechanisms)
    return {
        p.dest: applies(p.dest, opts, raw, fds, mechanisms=mechanisms, invalid=invalid)
        for p in PARAMETERS
        if p.run_option
    }
