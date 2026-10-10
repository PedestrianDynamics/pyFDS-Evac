"""The effective configuration of a run, before it starts (#484).

:func:`effective_configuration` combines the options, the scenario JSON and,
with ``--fds-dir``, the FDS inventory into what the run will do: which
models are on and why, every option with its unit and origin, options that
change nothing, the setup warnings and errors (worded as the run words
them) and the equivalent ``pyfds-evac`` command.

Two levels:

- Level 1, options and scenario: no FDS read (``inspect_fds=False``); every
  slice counts as present.
- Level 2, with the FDS inventory: reads the ``.smv`` (imports fdsreader).

``pyfds-evac --show-config`` prints Level 2; the run manifest records it
under ``configuration``.

Provisional public API (0.3.0): names and the dictionary layout may change
in 0.3.x.
"""

from __future__ import annotations

import math
import os
import pathlib
import shlex
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from . import messages
from .parameters import (
    NO_COUNTERPART,
    PARAMETERS,
    RUN_OPTIONS,
    is_set_value,
    option,
    parameter,
)
from .rules import (
    UNKNOWN_FDS,
    ConfigIssue,
    FdsFacts,
    Inactive,
    Mechanisms,
    check_options,
    heat_value_issue,
    horizon_overrun,
    inactive_settings,
    integrated_intensity_issue,
    no_known_exit_issue,
    no_known_exit_value_issue,
    predict_mechanisms,
    routing_issue,
    spawn_issue,
    speed_alias_issue,
    visibility_value_issue,
)

SCHEMA_VERSION = 1
DEFAULT_SEED = 42
DEFAULT_MAX_SIMULATION_TIME_S = 300.0


@dataclass(frozen=True)
class OptionValue:
    """One run option as the run will use it."""

    option: str
    flag: str
    value: Any
    default: Any
    unit: str | None
    overridden: bool
    departs_from_fds_evac: bool
    active: bool


@dataclass(frozen=True)
class RoutingValue:
    """One key of the scenario's ``routing`` block."""

    key: str
    value: Any
    default: Any
    overridden: bool


@dataclass(frozen=True)
class Mechanism:
    """One model of the run: on or off, a short description and the rule."""

    name: str
    on: bool
    detail: str
    rule: str | None = None


@dataclass(frozen=True)
class EffectiveConfiguration:
    """What a run with these options, scenario and FDS case will do."""

    level: int
    inputs: dict[str, Any]
    mechanisms: tuple[Mechanism, ...]
    options: tuple[OptionValue, ...]
    resolved: dict[str, Any]
    routing: tuple[RoutingValue, ...]
    inactive: tuple[Inactive, ...]
    warnings: tuple[str, ...]
    errors: tuple[ConfigIssue, ...]
    command: str
    fds_slices: tuple[str, ...] | None = None
    _mechanisms: Mechanisms | None = field(default=None, repr=False, compare=False)

    @property
    def ok(self) -> bool:
        """True when no configuration error would stop the run at setup."""
        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        """A JSON-serialisable form, as the run manifest records it.

        Path options given as ``pathlib.Path`` are written as text.
        """
        record: dict[str, Any] = _json_safe(
            {
                "schema": SCHEMA_VERSION,
                "provisional": True,
                "level": self.level,
                "inputs": self.inputs,
                "fds_slices": None
                if self.fds_slices is None
                else list(self.fds_slices),
                "mechanisms": {
                    m.name: {"on": m.on, "detail": m.detail, "rule": m.rule}
                    for m in self.mechanisms
                },
                "options": {
                    o.option: {
                        "value": o.value,
                        "default": o.default,
                        "unit": o.unit,
                        "overridden": o.overridden,
                        "departs_from_fds_evac": o.departs_from_fds_evac,
                        "active": o.active,
                    }
                    for o in self.options
                },
                "resolved": self.resolved,
                "routing": {
                    r.key: {
                        "value": r.value,
                        "default": r.default,
                        "overridden": r.overridden,
                    }
                    for r in self.routing
                },
                "inactive": [
                    {
                        "option": i.option,
                        "value": i.value,
                        "rule": i.rule,
                        "reason": i.reason,
                    }
                    for i in self.inactive
                ],
                "warnings": list(self.warnings),
                "errors": [
                    {"rule": e.rule, "option": e.option, "message": e.message}
                    for e in self.errors
                ],
                "command": self.command,
            }
        )
        return record

    def format_text(self) -> str:
        """The report ``pyfds-evac --show-config`` prints."""
        return _format_text(self)


def _json_safe(value: Any) -> Any:
    """*value* with path objects as text, for ``json.dumps``."""
    if isinstance(value, os.PathLike):
        return os.fspath(value)
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)  # strict JSON has no inf or nan
    if isinstance(value, Mapping):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def effective_configuration(
    opts: Any,
    scenario: Any = None,
    *,
    fds: FdsFacts | None = None,
    inspect_fds: bool = True,
) -> EffectiveConfiguration:
    """Describe the run *opts* would start on *scenario*.

    *opts* has the attributes of the ``pyfds-evac`` options (an
    ``argparse.Namespace`` from the CLI or the GUI); missing ones take the
    CLI default. *scenario* is a loaded ``Scenario`` or its raw JSON
    mapping. *fds* supplies the FDS inventory; without it, it is read from
    ``opts.fds_dir`` when *inspect_fds* is True (Level 2), else every slice
    counts as present (Level 1).
    """
    raw = _raw(scenario)
    fds_dir = option(opts, "fds_dir")
    facts: Any = fds
    if facts is None and fds_dir and inspect_fds:
        facts = FdsFacts.read(fds_dir)
    level = 2 if facts is not None or not fds_dir else 1
    known = facts if facts is not None else UNKNOWN_FDS
    max_time = _max_simulation_time(scenario, raw)

    mech = predict_mechanisms(opts, raw, known)
    errors = _errors(opts, mech, known, max_time, raw, scenario)
    invalid = {e.option for e in errors}
    # An option whose value stops the run is an error, never "no effect".
    inactive = [i for i in inactive_settings(opts, mech) if i.option not in invalid]
    inert = {i.option for i in inactive}
    warnings = _warnings(opts, mech, known, max_time, inactive)
    wall_record, wall_warning = _predicted_wall_check(opts, mech, scenario)
    if wall_warning is not None:
        warnings.append(wall_warning)
    return EffectiveConfiguration(
        level=level,
        inputs=_inputs(opts, scenario, raw, max_time, known),
        mechanisms=_describe(opts, mech),
        options=tuple(_option_value(opts, dest, inert) for dest in RUN_OPTIONS),
        resolved={**_resolved(opts, mech), **wall_record},
        routing=_routing(raw),
        inactive=tuple(inactive),
        warnings=tuple(warnings),
        errors=tuple(errors),
        command=cli_command(opts, scenario_path=_scenario_path(opts, scenario)),
        fds_slices=None if facts is None else tuple(sorted(facts.slices)),
        _mechanisms=mech,
    )


def _raw(scenario: Any) -> Mapping[str, Any]:
    if scenario is None:
        return {}
    raw = getattr(scenario, "raw", scenario)
    return raw if isinstance(raw, Mapping) else {}


def _sim_settings(raw: Mapping[str, Any]) -> Mapping[str, Any]:
    return raw.get("config", {}).get("simulation_settings", {}) or {}


def _max_simulation_time(scenario: Any, raw: Mapping[str, Any]) -> float:
    value = getattr(scenario, "max_simulation_time", None)
    if value is not None:
        return float(value)
    params = _sim_settings(raw).get("simulationParams", {}) or {}
    return float(params.get("max_simulation_time", DEFAULT_MAX_SIMULATION_TIME_S))


def _seed(opts: Any, scenario: Any, raw: Mapping[str, Any]) -> tuple[Any, str]:
    """The seed and where it comes from: --seed > JSON baseSeed > 42."""
    if option(opts, "seed") is not None:
        return option(opts, "seed"), "option"
    if "baseSeed" in _sim_settings(raw):
        return _sim_settings(raw)["baseSeed"], "scenario"
    seed = getattr(scenario, "seed", None)
    if seed is not None:
        return seed, "scenario"
    return DEFAULT_SEED, "default"


def _scenario_path(opts: Any, scenario: Any) -> Any:
    """The scenario file the run loaded, else ``opts.scenario``.

    The GUI's ``opts.scenario`` is its picker value (e.g. ``t_junction``),
    not a path; the loaded scenario knows the file.
    """
    return getattr(scenario, "source_path", None) or option(opts, "scenario")


def _scenario_kind(path: Any) -> str | None:
    if not path:
        return None
    candidate = pathlib.Path(str(path))
    if candidate.is_dir():
        return "directory"
    if candidate.suffix.lower() == ".zip":
        return "zip"
    return "json"


def _inputs(
    opts: Any, scenario: Any, raw: Mapping[str, Any], max_time: float, fds: Any
) -> dict[str, Any]:
    seed, origin = _seed(opts, scenario, raw)
    path = _scenario_path(opts, scenario)
    horizon = getattr(fds, "horizon", None)
    outputs = {
        p.dest: option(opts, p.dest)
        for p in PARAMETERS
        if p.group == "Outputs" and p.kind == "text" and option(opts, p.dest)
    }
    return {
        "scenario": None if path is None else str(path),
        "scenario_kind": _scenario_kind(path),
        "fds_dir": option(opts, "fds_dir"),
        "fds_horizon_s": None if horizon is None else list(horizon),
        "seed": seed,
        "seed_origin": origin,
        "max_simulation_time_s": max_time,
        "outputs": outputs,
    }


def _describe(opts: Any, m: Mechanisms) -> tuple[Mechanism, ...]:
    """One line per model, with the rule that switches it."""
    interval = option(opts, "smoke_update_interval")
    height = option(opts, "smoke_slice_height")
    if m.smoke == "fds":
        smoke = Mechanism(
            "smoke_speed",
            True,
            f"FDS extinction at {height} m, every {interval} s",
            "D2",
        )
    elif m.smoke == "constant":
        k = option(opts, "constant_extinction")
        smoke = Mechanism(
            "smoke_speed",
            True,
            f"constant K = {k} 1/m, every {interval} s; also prices routes, "
            "hides no sign",
            "D4",
        )
    elif option(opts, "fds_dir"):
        smoke = Mechanism(
            "smoke_speed", False, "the FDS case has no extinction slice", "D3"
        )
    else:
        smoke = Mechanism("smoke_speed", False, "no fire input", "D2")
    return (
        smoke,
        _gas_mechanism(opts, m),
        _heat_mechanism(opts, m),
        _tenability_mechanism(opts, m),
        _rerouting_mechanism(opts, m),
        _visibility_mechanism(opts, m),
        Mechanism("smoke_blind", bool(option(opts, "smoke_blind")), "", None),
        Mechanism(
            "replay_exits",
            bool(option(opts, "replay_exits")),
            str(option(opts, "replay_exits") or ""),
            None,
        ),
        Mechanism(
            "fds_horizon_hold", bool(option(opts, "allow_fds_horizon_hold")), "", None
        ),
        Mechanism(
            "fds_coverage_required",
            bool(option(opts, "require_fds_coverage")),
            "",
            None,
        ),
    )


def _gas_mechanism(opts: Any, m: Mechanisms) -> Mechanism:
    if m.gas_fed:
        o2 = option(opts, "o2_threshold_percent")
        return Mechanism("gas_fed", True, f"CO, CO2, O2; O2 threshold {o2} vol %", "D6")
    if option(opts, "fds_dir"):
        return Mechanism("gas_fed", False, "the FDS case lacks CO, CO2 or O2", "D6")
    return Mechanism("gas_fed", False, "needs --fds-dir", "D6")


def heat_law(opts: Any) -> str:
    """The heat dose law, as the run's status line names it."""
    endpoint = option(opts, "heat_endpoint")
    method = option(opts, "heat_fed_method")
    if method == "total-flux":
        law = f"total flux, {endpoint or 'fatal'} dose"
        if option(opts, "heat_regime") == "layer":
            law += f", hot layer at {option(opts, 'heat_layer_height')} m"
        return law
    if endpoint is not None:
        return f"{endpoint} endpoint"
    clothing = option(opts, "heat_clothing") or "clothed"
    return f"ISO 13571:2012, {clothing}"


def _heat_mechanism(opts: Any, m: Mechanisms) -> Mechanism:
    if m.heat_fed:
        return Mechanism("heat_fed", True, heat_law(opts), "D12")
    if not option(opts, "fds_dir"):
        return Mechanism(
            "heat_fed", False, "needs --fds-dir and --enable-heat-fed", "D14"
        )
    if not option(opts, "enable_heat_fed"):
        return Mechanism("heat_fed", False, "needs --enable-heat-fed", "D12")
    return Mechanism("heat_fed", False, "the FDS case has no TEMPERATURE slice", "D12")


def _tenability_mechanism(opts: Any, m: Mechanisms) -> Mechanism:
    if m.tenability:
        parts = [f"FIC {'on' if m.fic else 'off'}"]
        if m.gas_fed:
            parts.append(f"gas {option(opts, 'incapacitation_mode')}")
        if m.heat_fed:
            parts.append(f"heat {option(opts, 'heat_incapacitation_mode')}")
        return Mechanism("tenability", True, ", ".join(parts), "D7")
    if not (m.gas_fed or m.heat_fed):
        return Mechanism("tenability", False, "no dose model", "D7")
    if option(opts, "disable_tenability"):
        return Mechanism("tenability", False, "--disable-tenability", "D7")
    return Mechanism("tenability", False, "--smoke-blind", "D7")


def _rerouting_mechanism(opts: Any, m: Mechanisms) -> Mechanism:
    if m.rerouting:
        return Mechanism(
            "rerouting", True, f"every {option(opts, 'reroute_interval')} s", "D23"
        )
    if option(opts, "enable_rerouting"):
        return Mechanism("rerouting", False, "--smoke-blind", "D24")
    return Mechanism("rerouting", False, "--no-enable-rerouting", "D23")


def _visibility_mechanism(opts: Any, m: Mechanisms) -> Mechanism:
    signs = f"{m.signs} sign{'' if m.signs == 1 else 's'}"
    if m.visibility == "smoky":
        step = option(opts, "reroute_interval")
        return Mechanism(
            "visibility", True, f"smoke-aware, {signs}, time step {step} s", "D28"
        )
    if m.visibility == "clear-air":
        cell = option(opts, "vis_cell_size")
        return Mechanism(
            "visibility", True, f"clear air, {signs}, {cell} m grid", "D27"
        )
    if option(opts, "no_visibility"):
        return Mechanism("visibility", False, "--no-visibility", "D27")
    if m.signs == 0:
        return Mechanism("visibility", False, "the scenario has no signs", "D27")
    return Mechanism("visibility", False, "every agent starts fully familiar", "D27")


def _option_value(opts: Any, dest: str, inert: set[str]) -> OptionValue:
    param = parameter(dest)
    value = option(opts, dest)
    departs = param.fds_evac is not NO_COUNTERPART and value != param.fds_evac
    return OptionValue(
        option=dest,
        flag=param.flag,
        value=value,
        default=param.default,
        unit=param.unit,
        overridden=is_set_value(param, value),
        departs_from_fds_evac=departs,
        active=dest not in inert,
    )


def _resolved(opts: Any, m: Mechanisms) -> dict[str, Any]:
    """Values the run derives from others (precedence of section 3.1)."""
    resolved: dict[str, Any] = {}
    if m.heat_fed:
        heat_threshold = option(opts, "heat_fed_threshold")
        resolved["heat_fed_threshold"] = (
            option(opts, "fed_threshold") if heat_threshold is None else heat_threshold
        )
        resolved["heat_law"] = heat_law(opts)
    if m.visibility == "smoky":
        resolved["vismap_time_step_s"] = option(opts, "reroute_interval")
    return resolved


def _routing(raw: Mapping[str, Any]) -> tuple[RoutingValue, ...]:
    """The scenario's ``routing`` keys against the code defaults."""
    given = raw.get("routing") or {}
    if not given:
        return ()
    from pyfds_evac.core.route_graph import RouteCostConfig

    base = RouteCostConfig.from_routing_params({})
    rows = []
    for key in sorted(given):
        default = getattr(base, key, None)
        rows.append(RoutingValue(key, given[key], default, given[key] != default))
    return tuple(rows)


def _errors(
    opts: Any,
    m: Mechanisms,
    fds: Any,
    max_time: float,
    raw: Mapping[str, Any],
    scenario: Any = None,
) -> list[ConfigIssue]:
    """The F, I and B errors the run would stop on at setup, in check order."""
    errors = list(check_options(opts))
    overrun = horizon_overrun(opts, max_time, fds)
    if overrun is not None and not option(opts, "allow_fds_horizon_hold"):
        errors.append(
            ConfigIssue("D32", "fds_dir", messages.horizon_error(overrun), "I")
        )
    if m.heat_fed:
        issue = integrated_intensity_issue(opts, fds) or heat_value_issue(opts)
        if issue is not None:
            errors.append(issue)
    issue = visibility_value_issue(opts, raw, m)
    if issue is not None:
        errors.append(issue)
    issue = speed_alias_issue(raw)
    if issue is not None:
        errors.append(issue)
    issue = routing_issue(raw)
    if issue is not None:
        errors.append(issue)
    issue = no_known_exit_value_issue(raw) or no_known_exit_issue(opts, raw)
    if issue is not None:
        errors.append(issue)
    issue = spawn_issue(scenario)
    if issue is not None and issue.message not in {e.message for e in errors}:
        errors.append(issue)
    return errors


def _warnings(
    opts: Any,
    m: Mechanisms,
    fds: Any,
    max_time: float,
    inactive: list[Inactive],
) -> list[str]:
    """The setup warnings of the run, in the order the run logs them."""
    fds_dir = option(opts, "fds_dir")
    found: list[str] = []
    overrun = horizon_overrun(opts, max_time, fds)
    if overrun is not None and option(opts, "allow_fds_horizon_hold"):
        found.append(messages.horizon_hold(overrun))
    if fds_dir and option(opts, "constant_extinction") is None and m.smoke is None:
        found.append(messages.smoke_without_extinction(fds_dir))
    if fds_dir and not m.gas_fed:
        missing = [q for q in ("co", "co2", "o2") if not fds.has(q)]
        found.append(messages.fed_without_gases(fds_dir, missing))
    found += _heat_warnings(opts, m)
    if m.signs == 0:
        found.append(messages.NO_SIGNS)
    if m.visibility == "clear-air" and fds_dir and not option(opts, "smoke_blind"):
        found.append(messages.visibility_without_extinction(fds_dir))
    if m.tenability and m.heat_fed and option(opts, "heat_fed_threshold") is not None:
        found.append(
            messages.heat_threshold_departs(option(opts, "heat_fed_threshold"))
        )
    if (
        option(opts, "replay_exits")
        and option(opts, "enable_rerouting")
        and not option(opts, "smoke_blind")
    ):
        found.append(messages.REPLAY_WITH_REROUTING)
    found += [i.message for i in inactive if not i.warned]
    return found


def _heat_warnings(opts: Any, m: Mechanisms) -> list[str]:
    fds_dir = option(opts, "fds_dir")
    if not fds_dir:
        return []
    if not option(opts, "enable_heat_fed"):
        return [
            messages.heat_option_without_enable(parameter(dest).flag)
            for dest in (
                "heat_endpoint",
                "heat_clothing",
                "heat_fed_method",
                "heat_radiant_source",
                "heat_regime",
            )
            if is_set_value(parameter(dest), option(opts, dest))
        ]
    if not m.heat_fed:
        return [messages.heat_without_temperature(fds_dir)]
    if option(opts, "heat_clothing") is not None and (
        option(opts, "heat_endpoint") is not None
        or option(opts, "heat_fed_method") != "convective"
    ):
        return [messages.HEAT_CLOTHING_OVERRIDDEN]
    return []


# --- equivalent command ----------------------------------------------------


def _cli_value(value: Any) -> str:
    return shlex.quote(str(value))


def cli_command(
    opts: Any, prog: str = "pyfds-evac", *, scenario_path: Any = None
) -> str:
    """The shortest ``pyfds-evac`` command with the same options.

    Only options away from their default are written, in flag order;
    ``--scenario`` comes first, *scenario_path* when given, else
    ``opts.scenario``. Keys that are not CLI options (GUI-only ones such
    as ``collect_route_cost_history``) are left out.
    """
    scenario = scenario_path if scenario_path is not None else option(opts, "scenario")
    parts = [prog, "--scenario", _cli_value(_absolute(scenario))]
    for param in PARAMETERS:
        if param.dest == "scenario" or not param.run_option:
            continue
        value = option(opts, param.dest)
        if not is_set_value(param, value):
            continue
        parts += _flag_words(param, value)
    return " ".join(parts)


def _absolute(path: Any) -> str:
    """*path* as an absolute path, so the command runs from any directory."""
    return os.path.abspath(os.path.expanduser(str(os.fspath(path))))


def _flag_words(param: Any, value: Any) -> list[str]:
    if param.kind == "text" and not str(value).strip():
        return []  # a blank path is not set, as in the script and the run
    if param.kind == "text":  # every text option is a path
        return [param.flag, _cli_value(_absolute(value))]
    if param.action == "store_true":
        return [param.flag] if value else []
    if param.action == "boolean_optional":
        return [param.flag if value else "--no-" + param.flag[2:]]
    return [param.flag, _cli_value(repr(value) if isinstance(value, float) else value)]


# --- text report -----------------------------------------------------------


def _show(value: Any) -> str:
    if value is None:
        return "-"
    if value is True:
        return "on"
    if value is False:
        return "off"
    return str(value)


def _format_text(cfg: EffectiveConfiguration) -> str:
    lines = [
        f"Effective configuration (level {cfg.level}: options, scenario"
        + (" and FDS inventory)" if cfg.level == 2 else "; FDS case not inspected)"),
        "",
        "Inputs:",
    ]
    inputs = cfg.inputs
    lines.append(
        f"  scenario                {inputs['scenario']} ({inputs['scenario_kind']})"
    )
    lines.append(f"  FDS directory           {_show(inputs['fds_dir'])}")
    if cfg.fds_slices is not None:
        lines.append(f"  FDS slices              {', '.join(cfg.fds_slices) or '-'}")
    if inputs["fds_horizon_s"] is not None:
        last, interval = inputs["fds_horizon_s"]
        lines.append(
            f"  FDS output              ends at {last:.1f} s, interval {interval:.1f} s"
        )
    lines.append(
        f"  seed                    {inputs['seed']} ({inputs['seed_origin']})"
    )
    lines.append(
        f"  max_simulation_time     {inputs['max_simulation_time_s']} s (scenario)"
    )
    for dest, path in inputs["outputs"].items():
        lines.append(f"  {parameter(dest).flag:<24}{path}")
    lines += ["", "Models:"]
    for m in cfg.mechanisms:
        detail = f"  {m.detail}" if m.detail else ""
        lines.append(f"  {m.name:<22}{'on ' if m.on else 'off'}{detail}")
    lines += ["", "Options (* not the default, ! departs from FDS+Evac, - no effect):"]
    for o in cfg.options:
        if o.option == "scenario" or o.option in inputs["outputs"]:
            continue
        marks = ("*" if o.overridden else " ") + (
            "!" if o.departs_from_fds_evac else " "
        )
        marks += " " if o.active else "-"
        unit = f" {o.unit}" if o.unit and o.value is not None else ""
        lines.append(f"  {marks} {o.flag:<32}{_show(o.value)}{unit}")
    for key, value in cfg.resolved.items():
        lines.append(f"      resolved {key:<23}{value}")
    if cfg.routing:
        lines += ["", "Scenario routing block (* not the code default):"]
        for r in cfg.routing:
            mark = "*" if r.overridden else " "
            lines.append(f"  {mark} {r.key:<32}{r.value} (default {r.default})")
    lines += ["", "Options with no effect:"]
    lines += [f"  {i.flag} {_show(i.value)}: {i.reason}" for i in cfg.inactive] or [
        "  none"
    ]
    lines += ["", "Setup warnings:"]
    lines += [f"  {w}" for w in cfg.warnings] or ["  none"]
    lines += ["", "Errors:"]
    lines += [f"  {e.message}" for e in cfg.errors] or ["  none"]
    lines += ["", "Equivalent command:", f"  {cfg.command}"]
    return "\n".join(lines)


# --- the manifest record ---------------------------------------------------


def predicted_run_settings(
    opts: Any, raw: Mapping[str, Any], cfg: EffectiveConfiguration
) -> dict[str, Any]:
    """What ``build_run_kwargs`` would give ``run_scenario`` for these options.

    The same layout as ``ScenarioResult.run_settings``
    (``pyfds_evac.core.manifest.run_settings``), built from the options,
    the scenario and the predicted models.
    """
    m = cfg._mechanisms
    if m is None:
        raise ValueError("effective configuration without mechanisms")
    sampling = {
        "update_interval_s": option(opts, "smoke_update_interval"),
        "slice_height_m": option(opts, "smoke_slice_height"),
    }
    return {
        "seed": cfg.inputs["seed"],
        "smoke_speed": None
        if m.smoke is None
        else {
            "source": m.smoke,
            "extinction_per_m": option(opts, "constant_extinction"),
            **sampling,
        },
        "gas_fed": None
        if not m.gas_fed
        else {**sampling, "o2_threshold_percent": option(opts, "o2_threshold_percent")},
        "heat_fed": _predicted_heat(opts, sampling) if m.heat_fed else None,
        "tenability": _predicted_tenability(opts, m) if m.tenability else None,
        "rerouting": _predicted_rerouting(opts, raw) if m.rerouting else None,
        "visibility": _predicted_visibility(opts, m, cfg.resolved),
        "smoke_blind": bool(option(opts, "smoke_blind")),
        "replay_exits": bool(option(opts, "replay_exits")),
        "require_fds_coverage": bool(option(opts, "require_fds_coverage")),
    }


def _predicted_heat(opts: Any, sampling: dict[str, Any]) -> dict[str, Any]:
    layer = option(opts, "heat_regime") == "layer"
    return {
        "method": option(opts, "heat_fed_method"),
        "endpoint": option(opts, "heat_endpoint"),
        "clothing": option(opts, "heat_clothing") or "clothed",
        "emissivity": option(opts, "heat_emissivity"),
        "convective_coefficient": option(opts, "heat_convective_coefficient"),
        "skin_temperature_celsius": option(opts, "heat_skin_temperature"),
        "radiant_source": option(opts, "heat_radiant_source"),
        "u_factor": option(opts, "heat_u_factor"),
        "regime": option(opts, "heat_regime"),
        "view_factor": option(opts, "heat_view_factor") if layer else None,
        "layer_emissivity": option(opts, "heat_layer_emissivity") if layer else None,
        "layer_height_m": option(opts, "heat_layer_height") if layer else None,
        **sampling,
    }


def _predicted_tenability(opts: Any, m: Mechanisms) -> dict[str, Any]:
    return {
        "enable_fic_speed": m.fic,
        "fic_alpha": option(opts, "fic_alpha"),
        "fic_min_factor": option(opts, "fic_min_factor"),
        "enable_incapacitation": m.gas_fed,
        "fed_threshold": option(opts, "fed_threshold"),
        "incapacitation_mode": option(opts, "incapacitation_mode"),
        "susceptibility_sigma": option(opts, "susceptibility_sigma"),
        "enable_heat_incapacitation": m.heat_fed,
        "heat_fed_threshold": option(opts, "heat_fed_threshold"),
        "heat_incapacitation_mode": option(opts, "heat_incapacitation_mode"),
        "heat_susceptibility_sigma": option(opts, "heat_susceptibility_sigma"),
    }


def _predicted_rerouting(opts: Any, raw: Mapping[str, Any]) -> dict[str, Any]:
    import dataclasses

    from pyfds_evac.core.route_graph import RerouteConfig, RouteCostConfig

    cost = RouteCostConfig.from_routing_params(raw.get("routing", {}))
    return {
        "reevaluation_interval_s": option(opts, "reroute_interval"),
        "exit_switch_anchor": RerouteConfig.exit_switch_anchor,
        "cost_config": dataclasses.asdict(cost),
    }


def _predicted_visibility(
    opts: Any, m: Mechanisms, resolved: Mapping[str, Any]
) -> dict[str, Any] | None:
    if m.visibility is None:
        return None
    if m.visibility == "clear-air":
        return {
            "kind": "clear-air",
            "cell_size_m": option(opts, "vis_cell_size"),
            "max_sign_distance_m": option(opts, "max_sign_distance"),
            **{k: v for k, v in resolved.items() if k.startswith("thin_wall_")},
        }
    return {
        "kind": "smoky",
        "time_step_s": option(opts, "reroute_interval"),
        "slice_height_m": option(opts, "smoke_slice_height"),
        "max_sign_distance_m": option(opts, "max_sign_distance"),
    }


def _predicted_wall_check(
    opts: Any, m: Mechanisms, scenario: Any
) -> tuple[dict[str, Any], str | None]:
    """The clear-air model's ``thin_wall_*`` record and warning, predicted.

    Computed from the scenario's loaded walkable polygon with the function
    the model uses. Nothing without a clear-air model, without a polygon (a
    raw scenario mapping) or with a cell size the model would reject; the
    run record then lists the keys as differing rather than guessing them.
    """
    walkable = getattr(scenario, "walkable_polygon", None)
    cell = option(opts, "vis_cell_size")
    if m.visibility != "clear-air" or walkable is None:
        return {}, None
    if not isinstance(cell, (int, float)) or cell <= 0:
        return {}, None
    from pyfds_evac.core.visibility import wall_check

    return wall_check(walkable, float(cell))


def _differences(predicted: Any, used: Any, path: str = "") -> list[str]:
    """Dotted names of the settings that differ (``tenability.fic_alpha``)."""
    if isinstance(predicted, Mapping) and isinstance(used, Mapping):
        found: list[str] = []
        for key in list(predicted) + [k for k in used if k not in predicted]:
            name = f"{path}.{key}" if path else str(key)
            found += _differences(predicted.get(key), used.get(key), name)
        return found
    return [] if _same(predicted, used) else [path]


def _same(a: Any, b: Any) -> bool:
    """Equal, with nan equal to nan (an unset float stays nan on both sides)."""
    if (
        isinstance(a, float)
        and isinstance(b, float)
        and math.isnan(a)
        and math.isnan(b)
    ):
        return True
    return bool(a == b)


def run_record(
    cfg: EffectiveConfiguration,
    used: Mapping[str, Any] | None,
    opts: Any = None,
    scenario: Any = None,
) -> dict[str, Any]:
    """The manifest's ``configuration``: what the run used, then the options.

    *used* is ``ScenarioResult.run_settings``, what ``run_scenario`` was
    given. ``source`` says where the record comes from:

    - ``"run"``: the run used the seed, models and model parameters the
      options imply; the whole effective configuration describes it.
    - ``"run, options differ"``: the options do not describe the run (e.g.
      ``run_scenario`` called with other models). Only ``run`` and the
      seed are recorded as facts; the configuration the options imply is
      kept apart under ``predicted_from_options`` with the ``mismatches``.
    - ``"predicted from options"``: the run's settings are not known; every
      field is a prediction from the options.
    """
    record = cfg.to_dict()
    if used is None:
        record["source"] = "predicted from options"
        return record
    run = _json_safe(dict(used))
    predicted = predicted_run_settings(opts, _raw(scenario), cfg)
    mismatches = _differences(predicted, used)
    if not mismatches:
        record["source"] = "run"
        record["run"] = run
        return record
    return {
        "schema": SCHEMA_VERSION,
        "provisional": True,
        "source": "run, options differ",
        "run": run,
        "inputs": {"seed": used.get("seed"), "seed_origin": "run"},
        "mismatches": mismatches,
        "predicted_from_options": record,
    }
