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
import math
from collections.abc import Iterator
from typing import Any

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


def _normalize_flow_schedule_entry(entry: dict) -> dict:
    """Normalize one configured flow schedule entry to canonical keys.

    Times are finite seconds, the start >= 0 and the end after it, and
    ``number`` a positive integer; anything else, an entry that is not
    an object included, raises ``ValueError``.
    """
    if not isinstance(entry, dict):
        raise ValueError(f"Each flow schedule entry must be an object, got {entry!r}")
    start_time = entry.get("flow_start_time", entry.get("start_time_s"))
    end_time = entry.get("flow_end_time", entry.get("end_time_s"))
    number = entry.get("number", entry.get("sim_count"))

    if start_time is None or end_time is None or number is None:
        raise ValueError(
            "Each flow schedule entry must define start/end time and number. "
            "Accepted keys: flow_start_time|start_time_s, flow_end_time|end_time_s, number|sim_count."
        )

    try:
        start_time = float(start_time)
        end_time = float(end_time)
        number = int(number)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError(
            f"Flow schedule entry {entry!r}: times and number must be numbers"
        ) from error

    if not (math.isfinite(start_time) and math.isfinite(end_time)):
        raise ValueError(
            f"Invalid flow window [{start_time}, {end_time}] - times must be finite."
        )
    if start_time < 0 or end_time <= start_time:
        raise ValueError(
            f"Invalid flow window [{start_time}, {end_time}] - end_time must be greater than start_time."
        )
    if number <= 0:
        raise ValueError(
            f"Flow schedule numbers must be positive integers, got {number!r}"
        )

    return {
        "flow_start_time": start_time,
        "flow_end_time": end_time,
        "number": number,
    }


def _normalized_flow_schedule(params: dict) -> list[dict]:
    """Return the sorted flow schedule for one distribution."""
    raw_schedule = params.get("flow_schedule", [])
    if not raw_schedule:
        return []
    if not isinstance(raw_schedule, list):
        raise ValueError(f"flow_schedule must be a list, got {raw_schedule!r}")
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
