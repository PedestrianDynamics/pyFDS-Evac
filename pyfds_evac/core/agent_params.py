"""Agent parameter keys of a scenario JSON, checked without the simulation stack.

``desired_speed``, ``desired_speed_distribution`` and ``desired_speed_std``
are aliases of ``v0``, ``v0_distribution`` and ``v0_std`` (#143). An alias
set alone is used as its ``v0*`` key; an alias and its ``v0*`` key with the
same value are accepted; with different values the deck is rejected.

The run normalises the aliases in place
(:func:`normalize_distribution_speed_aliases`); the configuration check
calls :func:`check_speed_aliases`, which raises the same error and leaves
the scenario untouched. Imports stay light: no JuPedSim, pedpy or shapely,
so ``--show-config``, the TUI and the GUI can call it (#612).

The deck-wide spawn defaults live here too, so the inspection views
show the count the run places (#647), and so does the flow-schedule
normaliser that ``Scenario.set_flow_schedule``, the views and the run
share (#390).
"""

from __future__ import annotations

import json
import logging
import math
from collections.abc import Iterator
from typing import Any

_logger = logging.getLogger(__name__)

SPEED_KEY_ALIASES = (
    ("desired_speed", "v0"),
    ("desired_speed_distribution", "v0_distribution"),
    ("desired_speed_std", "v0_std"),
)


def _check_speed_pairs(params: dict[str, Any], dist_id: str) -> None:
    """Raise ValueError for the first alias whose ``v0*`` key differs."""
    for alias, canonical in SPEED_KEY_ALIASES:
        if alias not in params or canonical not in params:
            continue
        if params[canonical] != params[alias]:
            raise ValueError(
                f"Distribution {dist_id!r} sets {alias}={params[alias]!r} and "
                f"{canonical}={params[canonical]!r}; {alias} is an alias of "
                f"{canonical}, set one of them"
            )


def _normalize_speed_aliases(params: dict[str, Any], dist_id: str) -> None:
    """Copy each ``desired_speed*`` alias to its ``v0*`` key in place.

    ``Scenario.set_agent_params`` writes both key families with equal
    values; a pair with different values is ambiguous and is rejected.
    """
    _check_speed_pairs(params, dist_id)
    for alias, canonical in SPEED_KEY_ALIASES:
        if alias in params and canonical not in params:
            params[canonical] = params[alias]


def parameters_as_dict(params: Any) -> dict[str, Any] | None:
    """Return distribution ``parameters`` as a dict, or None if not one.

    A scenario may give ``parameters`` as an object or as a JSON-encoded
    string; the initialisers read both (#644).
    """
    if isinstance(params, str):
        try:
            params = json.loads(params)
        except json.JSONDecodeError:
            return None
    return params if isinstance(params, dict) else None


def _alias_parameters(data: Any) -> Iterator[tuple[str, dict, dict[str, Any]]]:
    """Yield ``(dist_id, dist_data, params)`` of each distribution with an alias.

    ``params`` is the parsed dict of string-encoded ``parameters`` (a new
    object) or the ``parameters`` dict itself. Anything that is not a dict
    is left for the loaders.
    """
    if not isinstance(data, dict):
        return
    distributions = data.get("distributions")
    if not isinstance(distributions, dict):
        return
    for dist_id, dist_data in distributions.items():
        if not isinstance(dist_data, dict):
            continue
        params = parameters_as_dict(dist_data.get("parameters"))
        if params is None:
            continue
        if not any(alias in params for alias, _ in SPEED_KEY_ALIASES):
            continue
        yield dist_id, dist_data, params


def check_speed_aliases(raw: Any) -> None:
    """Raise the run's ValueError if a distribution sets a conflicting pair.

    Checks the distributions in order and stops at the first conflict, as
    the run does. ``raw`` is not modified.
    """
    for dist_id, _, params in _alias_parameters(raw):
        _check_speed_pairs(params, dist_id)


KNOWN_PARAMETER_KEYS = frozenset(
    {
        # _spawn_params and the readers of cognitive_map and the views
        "number",
        "radius",
        "v0",
        "use_flow_spawning",
        "flow_start_time",
        "flow_end_time",
        "flow_schedule",
        "initial_number",
        "use_premovement",
        "premovement_distribution",
        "premovement_param_a",
        "premovement_param_b",
        "premovement_seed",
        "premovement_preset",
        "premovement_offset_s",
        "radius_distribution",
        "radius_std",
        "v0_distribution",
        "v0_std",
        "distribution_mode",
        "percentage",
        "familiarity",
        "entrance",
        "no_known_exit",
        # aliases of the v0 keys
        "desired_speed",
        "desired_speed_distribution",
        "desired_speed_std",
        # study labels that travel with the area and are never read as inputs
        "population",
        "fahy_row",
        "fahy_class",
    }
)
"""The ``distributions.*.parameters`` keys the code reads or allows (#1033)."""

_DISTRIBUTION_ENUMS = {
    "v0_distribution": ("constant", "gaussian"),
    "desired_speed_distribution": ("constant", "gaussian"),
    "radius_distribution": ("constant", "gaussian"),
    "distribution_mode": ("by_number", "by_percentage", "fill_area", "until_full"),
}
_STD_KEYS = ("v0_std", "desired_speed_std", "radius_std")


def _distribution_parameters(data: Any) -> Iterator[tuple[str, dict[str, Any]]]:
    """Yield ``(dist_id, params)`` of each distribution whose parameters parse."""
    distributions = data.get("distributions") if isinstance(data, dict) else None
    if not isinstance(distributions, dict):
        return
    for dist_id, dist_data in distributions.items():
        if not isinstance(dist_data, dict):
            continue
        params = parameters_as_dict(dist_data.get("parameters"))
        if params is not None:
            yield dist_id, params


def _check_enum_value(dist_id: str, key: str, value: Any) -> None:
    """Raise ValueError when *key* holds a value the run does not act on."""
    allowed = _DISTRIBUTION_ENUMS[key]
    if isinstance(value, str) and value in allowed:
        return
    raise ValueError(
        f"Distribution {dist_id!r}: {key} {value!r} is not supported; "
        f"allowed values: {', '.join(allowed)}"
    )


def _check_std_value(dist_id: str, key: str, value: Any) -> None:
    """Raise ValueError when *key* is not null or a finite number >= 0."""
    if value is None:
        return
    is_number = isinstance(value, (int, float)) and not isinstance(value, bool)
    if is_number and math.isfinite(value) and value >= 0:
        return
    raise ValueError(
        f"Distribution {dist_id!r}: {key} must be a finite number >= 0 or "
        f"null, got {value!r}"
    )


def check_distribution_values(raw: Any) -> None:
    """Raise ValueError for the first distribution value the run cannot act on.

    An unknown ``v0_distribution``, ``radius_distribution`` or
    ``distribution_mode``, or a ``v0_std`` / ``radius_std`` (and the
    ``desired_speed*`` aliases) that is not null or a finite number >= 0.
    The error names the distribution. ``raw`` is not modified.
    """
    for dist_id, params in _distribution_parameters(raw):
        for key in _DISTRIBUTION_ENUMS:
            if key in params:
                _check_enum_value(dist_id, key, params[key])
        for key in _STD_KEYS:
            if key in params:
                _check_std_value(dist_id, key, params[key])


def warn_unknown_parameter_keys(raw: Any) -> None:
    """Log one warning per distribution and unknown ``parameters`` key (#1033).

    An unknown key is dropped by the set-up, so a misspelling such as
    ``numbr`` runs with the default. Not an error: the deck still loads.
    """
    for dist_id, params in _distribution_parameters(raw):
        for key in params:
            if key in KNOWN_PARAMETER_KEYS:
                continue
            _logger.warning(
                "Distribution '%s': unknown parameters key %r is ignored; "
                "check the spelling against the scenario-json reference",
                dist_id,
                key,
            )


def normalize_distribution_speed_aliases(data: Any) -> None:
    """Apply ``_normalize_speed_aliases`` to every distribution of ``data``.

    String-encoded ``parameters`` are replaced by the parsed dict only when
    they contain an alias; anything else is left for the loaders.
    """
    for dist_id, dist_data, params in _alias_parameters(data):
        _normalize_speed_aliases(params, dist_id)
        dist_data["parameters"] = params


DEFAULT_SPAWN_PARAMS: dict[str, Any] = {"number": 10, "radius": 0.2, "v0": 1.25}
"""Agent count, radius [m] and clear-air speed [m/s] of a distribution that
sets none and whose deck sets no ``simulationParams`` value (FDS+Evac
VEL_MEAN for ``v0``)."""

_SPAWN_DEFAULT_TYPES = {"number": int, "radius": float, "v0": float}
"""How a ``simulationParams`` spawn default is read; ``int`` matches how a
distribution's ``number`` is read when agents are placed."""


def _deck_spawn_defaults(global_parameters) -> dict[str, Any]:
    """``number``, ``radius`` and ``v0`` for a distribution that leaves one out.

    ``simulationParams.number``, ``.radius`` and ``.v0`` are deck-wide
    defaults; a key they do not set takes ``DEFAULT_SPAWN_PARAMS``. The same
    defaults apply with and without journeys, and nothing is taken from
    another distribution (#567). Numeric strings are converted, so both
    initialisers see the same number. ``number`` must be >= 0, ``radius``
    and ``v0`` finite and > 0, and a boolean is not a number (#649).
    Anything else raises ``ValueError`` naming the key.
    """
    defaults = dict(DEFAULT_SPAWN_PARAMS)
    if global_parameters is None:
        return defaults
    for key in _SPAWN_DEFAULT_TYPES:
        value = getattr(global_parameters, key, None)
        if value is not None:
            defaults[key] = _deck_spawn_value(key, value)
    return defaults


def _deck_spawn_value(key: str, value: Any) -> Any:
    """``simulationParams.<key>`` converted; a ``ValueError`` names the key."""
    return _spawn_value(key, value, f"simulationParams.{key}")


def _spawn_value(key: str, value: Any, name: str, zero_v0: bool = False) -> Any:
    """*value* of spawn key *key* converted and range-checked (#567, #649).

    ``number`` is read with ``int()`` and must be >= 0; ``radius`` and
    ``v0`` with ``float()`` and must be finite and > 0, or for ``v0`` >= 0
    when *zero_v0* (a spawn area of stationary agents). A boolean is not a
    number. Anything else raises ``ValueError`` naming *name*.
    """
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a number, got {value!r}")
    try:
        converted = _SPAWN_DEFAULT_TYPES[key](value)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError(f"{name} must be a number, got {value!r}") from error
    if key == "number":
        if converted < 0:
            raise ValueError(f"{name} must be >= 0, got {value!r}")
        return converted
    allow_zero = zero_v0 and key == "v0"
    in_range = converted >= 0 if allow_zero else converted > 0
    if not (math.isfinite(converted) and in_range):
        bound = ">= 0" if allow_zero else "> 0"
        raise ValueError(f"{name} must be finite and {bound}, got {value!r}")
    return converted


class SpawnConfigError(ValueError):
    """A spawn area's flow schedule or start count cannot be run as written."""


def _normalize_flow_schedule_entry(entry: dict) -> dict:
    """Normalize one configured flow schedule entry to canonical keys.

    Times are finite seconds, the start >= 0 and the end after it, and
    ``number`` a whole number >= 1; anything else, an entry that is not
    an object included, raises ``SpawnConfigError``.
    """
    if not isinstance(entry, dict):
        raise SpawnConfigError(
            f"Each flow schedule entry must be an object, got {entry!r}"
        )
    start_time = entry.get("flow_start_time", entry.get("start_time_s"))
    end_time = entry.get("flow_end_time", entry.get("end_time_s"))
    number = entry.get("number", entry.get("sim_count"))

    if start_time is None or end_time is None or number is None:
        raise SpawnConfigError(
            "Each flow schedule entry must define start/end time and number. "
            "Accepted keys: flow_start_time|start_time_s, flow_end_time|end_time_s, number|sim_count."
        )

    try:
        start_time = float(start_time)
        end_time = float(end_time)
    except (TypeError, ValueError, OverflowError) as error:
        raise SpawnConfigError(
            f"Flow schedule entry {entry!r}: times must be numbers"
        ) from error
    number = _whole_number(number)

    if not (math.isfinite(start_time) and math.isfinite(end_time)):
        raise SpawnConfigError(
            f"Invalid flow window [{start_time}, {end_time}] - times must be finite."
        )
    if start_time < 0:
        raise SpawnConfigError(
            f"Invalid flow window [{start_time}, {end_time}] - start_time must be >= 0."
        )
    if end_time <= start_time:
        raise SpawnConfigError(
            f"Invalid flow window [{start_time}, {end_time}] - end_time must be greater than start_time."
        )
    if number <= 0:
        raise SpawnConfigError(
            f"Flow schedule numbers must be positive integers, got {number!r}"
        )

    return {
        "flow_start_time": start_time,
        "flow_end_time": end_time,
        "number": number,
    }


def _whole_number(value: Any) -> int:
    """A flow schedule's ``number``: an integer, also as ``4.0`` or ``"4"``."""
    if isinstance(value, bool):
        raise SpawnConfigError(
            f"Flow schedule numbers must be whole numbers, got {value!r}"
        )
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise SpawnConfigError(
            f"Flow schedule numbers must be whole numbers, got {value!r}"
        ) from error
    if not number.is_integer():
        raise SpawnConfigError(
            f"Flow schedule numbers must be whole numbers, got {value!r}"
        )
    return int(number)


def _normalized_flow_schedule(params: dict) -> list[dict]:
    """Return the sorted flow schedule for one distribution."""
    raw_schedule = params.get("flow_schedule", [])
    if not raw_schedule:
        return []
    if not isinstance(raw_schedule, list):
        raise SpawnConfigError(f"must be a list of windows, got {raw_schedule!r}")
    normalized = [_normalize_flow_schedule_entry(entry) for entry in raw_schedule]
    normalized.sort(
        key=lambda entry: (entry["flow_start_time"], entry["flow_end_time"])
    )
    return normalized


def deck_default_number(sim_params: Any) -> int:
    """Agents a distribution without ``number`` places (#647).

    *sim_params* is the deck's ``simulationParams`` mapping (or None). The
    count is the run's: ``simulationParams.number``, else
    ``DEFAULT_SPAWN_PARAMS``. An invalid count raises the run's
    ``ValueError``; ``radius`` and ``v0`` are not read.
    """
    value = (sim_params or {}).get("number")
    if value is None:
        return int(DEFAULT_SPAWN_PARAMS["number"])
    return int(_deck_spawn_value("number", value))


SAMPLED_RADIUS_MIN_M = 0.1
"""Smallest radius [m] a Gaussian radius draw is given."""

SAMPLED_RADIUS_MAX_M = 1.0
"""Largest spacing bound [m] of a Gaussian radius."""


def max_agent_radius(params: dict[str, Any]) -> float:
    """The largest radius [m] an agent of *params* gets: the spacing bound.

    Placement keeps agents twice this apart and this far from the area's
    edge. A constant radius is its own bound. A Gaussian radius is bounded
    by ``min(max(radius + 3 * radius_std, 0.1), 1.0)``, and every draw is
    clipped into [0.1, bound], so no agent is larger than the spacing
    assumed (#709). The run's placement and the importer's capacity check
    both read this.
    """
    radius = float(params.get("radius", DEFAULT_SPAWN_PARAMS["radius"]))
    if params.get("radius_distribution") != "gaussian" or not params.get("radius_std"):
        return radius
    bound = radius + 3 * float(params["radius_std"])
    return min(max(bound, SAMPLED_RADIUS_MIN_M), SAMPLED_RADIUS_MAX_M)
